"""Deterministic, constraint-aware airport simulation engine.

The engine owns all operational state. AI agents never write to it directly: they
choose a recovery *policy* (and parameters) through tools, and the engine computes
the resulting schedule. Every schedule can be checked by `validator.validate`.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from .config import AIRCRAFT_TYPES, CREWS, GATES, RUNWAYS, SIZE_RANK, TIMING
from .flights import Flight

STEP = 0.25  # minute resolution for slot search
HORIZON = 900


# ----------------------------------------------------------------------------- models
@dataclass
class Disruption:
    """A set of operational constraints applied to the day. All synthetic."""
    label: str = "Normal operations"
    kind: str = "none"
    start: float = 0.0
    end: float = 0.0
    runway_closures: list[dict] = field(default_factory=list)      # {runway, start, end}
    capacity_overrides: list[dict] = field(default_factory=list)   # {runway, capacity_per_hour, start, end}
    turnaround_factor: float = 1.0                                  # applies to turnarounds starting in [start, end)
    gate_closures: list[dict] = field(default_factory=list)        # {gate, start, end}
    crews_unavailable: list[str] = field(default_factory=list)
    flight_delays: dict[str, float] = field(default_factory=dict)  # inbound lateness per flight id
    visibility_m: Optional[int] = None
    wind_kt: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Disruption":
        return Disruption(**d)

    def merge(self, other: "Disruption") -> "Disruption":
        m = copy.deepcopy(self)
        if m.kind == "none":
            m.label, m.kind = other.label, other.kind
        else:
            m.label = f"{m.label} + {other.label}"
        if other.end > other.start:
            m.start = other.start if m.end <= m.start else min(m.start, other.start)
            m.end = max(m.end, other.end)
        m.runway_closures += other.runway_closures
        m.capacity_overrides += other.capacity_overrides
        m.turnaround_factor = max(m.turnaround_factor, other.turnaround_factor)
        m.gate_closures += other.gate_closures
        m.crews_unavailable = sorted(set(m.crews_unavailable) | set(other.crews_unavailable))
        for k, v in other.flight_delays.items():
            m.flight_delays[k] = m.flight_delays.get(k, 0) + v
        m.visibility_m = other.visibility_m or m.visibility_m
        m.wind_kt = other.wind_kt or m.wind_kt
        return m


@dataclass
class Policy:
    """How the airport responds. BASELINE = FCFS, planned gates, zone crews."""
    name: str = "Baseline (first-come-first-served)"
    sequencing: str = "fifo"          # fifo | priority
    arrival_protection: str = "none"  # none | fuel (protect arrivals near fuel limit) | all
    gate_policy: str = "fixed"        # fixed | reallocate
    use_remote_stands: bool = False
    crew_policy: str = "zone"         # zone | pooled
    gate_aware: bool = False          # re-sequence arrivals predicted to wait for a gate

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Policy":
        return Policy(**d)


@dataclass
class FlightResult:
    id: str
    airline: str
    aircraft: str
    size: str
    origin: str
    destination: str
    pax: int
    connecting: int
    sta: float
    std: float
    eta: float
    planned_gate: str
    land: Optional[float] = None
    arr_runway: Optional[str] = None
    hold: float = 0.0
    diverted: bool = False
    gate: Optional[str] = None
    gate_kind: Optional[str] = None
    in_request: Optional[float] = None
    gate_in: Optional[float] = None
    apron_wait: float = 0.0
    crew: Optional[str] = None
    ta_start: Optional[float] = None
    ta_end: Optional[float] = None
    ready: Optional[float] = None
    off_block: Optional[float] = None
    takeoff: Optional[float] = None
    dep_runway: Optional[str] = None
    arr_delay: float = 0.0
    dep_delay: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 2)
        return d


# ----------------------------------------------------------------------------- engine
class AirportEngine:
    def __init__(self, flights: list[Flight], disruption: Disruption, policy: Policy):
        self.flights = flights
        self.d = disruption
        self.p = policy
        self.gates = {g["id"]: g for g in GATES}
        self.crews = [c for c in CREWS if c["id"] not in set(disruption.crews_unavailable)]
        self.runway_res: dict[str, list[float]] = {r["id"]: [] for r in RUNWAYS}
        self.gate_res: dict[str, list[tuple[float, float, str]]] = {g: [] for g in self.gates}
        self.crew_res: dict[str, list[tuple[float, float, str]]] = {c["id"]: [] for c in self.crews}

    # ---- runway model
    def runway_open(self, rw: str, t: float) -> bool:
        for c in self.d.runway_closures:
            if c["runway"] == rw and c["start"] <= t < c["end"]:
                return False
        return True

    def capacity(self, rw: str, t: float) -> float:
        cap = next(r["capacity_per_hour"] for r in RUNWAYS if r["id"] == rw)
        for o in self.d.capacity_overrides:
            if o["runway"] == rw and o["start"] <= t < o["end"]:
                cap = min(cap, o["capacity_per_hour"])
        return cap

    def spacing(self, rw: str, t: float) -> float:
        return 60.0 / self.capacity(rw, t)

    def _slot_ok(self, rw: str, t: float) -> bool:
        if not self.runway_open(rw, t):
            return False
        sp = self.spacing(rw, t)
        for r in self.runway_res[rw]:
            if abs(t - r) < max(sp, self.spacing(rw, r)) - 1e-9:
                return False
        return True

    def find_runway_slot(self, earliest: float) -> tuple[str, float]:
        best: Optional[tuple[str, float]] = None
        for r in RUNWAYS:
            rw = r["id"]
            t = earliest
            while t < earliest + HORIZON and not self._slot_ok(rw, t):
                t += STEP
            if best is None or t < best[1] - 1e-9:
                best = (rw, t)
        assert best is not None
        return best

    # ---- gates
    def gate_closed(self, g: str, s: float, e: float) -> bool:
        for c in self.d.gate_closures:
            if c["gate"] == g and s < c["end"] and e > c["start"]:
                return True
        return False

    def gate_conflict_end(self, g: str, s: float, e: float) -> Optional[float]:
        """Return the end of the first interval that clashes with [s, e], or None if free."""
        buf = TIMING["gate_buffer_min"]
        clash_end = None
        for (a, b, _fid) in self.gate_res[g]:
            if s < b + buf and e + buf > a:
                clash_end = max(clash_end or 0, b + buf)
        for c in self.d.gate_closures:
            if c["gate"] == g and s < c["end"] and e > c["start"]:
                clash_end = max(clash_end or 0, c["end"])
        return clash_end

    def compatible(self, gate_id: str, size: str) -> bool:
        return SIZE_RANK[self.gates[gate_id]["size"]] >= SIZE_RANK[size]

    # ---- crews
    def crew_candidates(self, zone: str) -> list[dict]:
        if self.p.crew_policy == "pooled":
            return self.crews
        own = [c for c in self.crews if c["zone"] == zone]
        return own or self.crews  # if a zone has no crew left, borrow (unavoidable)

    def find_crew(self, zone: str, earliest: float, duration: float) -> tuple[str, float, float]:
        best = None
        for c in self.crew_candidates(zone):
            transfer = TIMING["crew_transfer_min"] if c["zone"] != zone else 0.0
            dur = duration + transfer
            cands = [earliest] + [b for (_a, b, _f) in self.crew_res[c["id"]] if b > earliest]
            for s in sorted(cands):
                if all(not (s < b and s + dur > a) for (a, b, _f) in self.crew_res[c["id"]]):
                    if best is None or s < best[1] - 1e-9:
                        best = (c["id"], s, dur)
                    break
        assert best is not None
        return best

    def turnaround_minutes(self, f: Flight, start: float, gate_id: str) -> float:
        base = AIRCRAFT_TYPES[f.aircraft]["turnaround_min"]
        if self.d.start <= start < self.d.end:
            base *= self.d.turnaround_factor
        if self.gates[gate_id]["kind"] == "remote":
            base += TIMING["remote_stand_penalty_min"]
        return base

    # ---- one gate chain (no reservation, pure evaluation)
    def evaluate_gate(self, f: Flight, gate_id: str, in_req: float) -> Optional[dict]:
        t = in_req
        for _ in range(60):
            ta_dur = self.turnaround_minutes(f, t, gate_id)
            crew, ta_start, ta_dur_eff = self.find_crew(self.gates[gate_id]["zone"], t, ta_dur)
            ta_end = ta_start + ta_dur_eff
            ready = max(f.std, ta_end)
            dep_rw, takeoff = self.find_runway_slot(ready + TIMING["taxi_out_min"])
            off = takeoff - TIMING["taxi_out_min"]
            clash = self.gate_conflict_end(gate_id, t, off)
            if clash is None:
                return dict(gate=gate_id, gate_in=t, crew=crew, ta_start=ta_start, ta_end=ta_end,
                            ready=ready, off_block=off, takeoff=takeoff, dep_runway=dep_rw)
            t = max(t + STEP, clash)
        return None

    def candidate_gates(self, f: Flight, in_req: float) -> list[str]:
        if self.p.gate_policy == "fixed":
            if not self.gate_closed(f.planned_gate, in_req, in_req + 1):
                return [f.planned_gate]
            # planned gate closed: baseline moves the aircraft to a compatible contact gate in the same zone
            zone = self.gates[f.planned_gate]["zone"]
            return [g for g in self.gates if self.gates[g]["kind"] == "contact"
                    and self.gates[g]["zone"] == zone
                    and self.compatible(g, f.size) and g != f.planned_gate]
        gates = [g for g in self.gates if self.compatible(g, f.size)
                 and (self.gates[g]["kind"] == "contact" or self.p.use_remote_stands)]
        return gates

    def choose_gate(self, f: Flight, in_req: float) -> Optional[dict]:
        cands = self.candidate_gates(f, in_req)
        if self.p.gate_policy == "fixed" and cands == [f.planned_gate]:
            return self.evaluate_gate(f, f.planned_gate, in_req)
        best, best_key = None, None
        for g in cands:
            r = self.evaluate_gate(f, g, in_req)
            if not r:
                continue
            gate = self.gates[g]
            oversize = SIZE_RANK[gate["size"]] - SIZE_RANK[f.size]
            key = (
                round(r["off_block"] + 15.0 * oversize, 2),  # keep big gates for big aircraft
                round(r["gate_in"], 2),
                0 if g == f.planned_gate else 1,
                0 if gate["kind"] == "contact" else 1,
                SIZE_RANK[gate["size"]],  # keep big gates free for big aircraft
            )
            if best_key is None or key < best_key:
                best, best_key = r, key
        return best

    # ---- run
    def order(self, extra: Optional[dict[str, float]] = None) -> list[Flight]:
        extra = extra or {}

        def eta(f: Flight) -> float:
            return f.sta + self.d.flight_delays.get(f.id, 0.0)

        if self.p.sequencing == "priority":
            key = lambda f: eta(f) - 3.0 * f.priority + extra.get(f.id, 0.0)
        else:
            key = lambda f: eta(f) + extra.get(f.id, 0.0)
        return sorted(self.flights, key=lambda f: (key(f), f.id))

    def run(self) -> list[FlightResult]:
        extra: dict[str, float] = {}
        protected: set[str] = set()
        passes = 1 + (2 if self.p.gate_aware else 0) + (4 if self.p.arrival_protection == "fuel" else 0)
        results: list[FlightResult] = []
        for _ in range(passes):
            self.__init__(self.flights, self.d, self.p)  # reset reservations
            ordered = self.order(extra)
            if self.p.arrival_protection == "all":
                protected = {f.id for f in ordered}
            results = self._run_once(ordered, protected)
            changed = False
            if self.p.arrival_protection == "fuel":
                limit = TIMING["max_airborne_hold_min"] - 15
                for r in results:
                    if (r.diverted or r.hold > limit) and r.id not in protected:
                        protected.add(r.id)
                        changed = True
            if self.p.gate_aware:
                for r in results:
                    if r.apron_wait > 5 and extra.get(r.id, 0.0) < r.apron_wait:
                        extra[r.id] = r.apron_wait
                        changed = True
            if not changed:
                break
        return sorted(results, key=lambda r: (r.sta, r.id))

    def _land(self, f: Flight, res: FlightResult) -> None:
        rw, land = self.find_runway_slot(res.eta)
        res.hold = land - res.eta
        if res.hold > TIMING["max_airborne_hold_min"]:
            res.diverted = True
            return
        self.runway_res[rw].append(land)
        res.land, res.arr_runway = land, rw

    def _turn(self, f: Flight, res: FlightResult) -> None:
        if res.diverted or res.land is None:
            return
        res.in_request = res.land + TIMING["taxi_in_min"]
        chain = self.choose_gate(f, res.in_request)
        if chain is None:  # no gate at all within horizon: treat as diversion
            res.diverted = True
            self.runway_res[res.arr_runway].remove(res.land)
            res.land = None
            return
        g = chain["gate"]
        self.gate_res[g].append((chain["gate_in"], chain["off_block"], f.id))
        self.crew_res[chain["crew"]].append((chain["ta_start"], chain["ta_end"], f.id))
        self.runway_res[chain["dep_runway"]].append(chain["takeoff"])
        res.gate, res.gate_kind = g, self.gates[g]["kind"]
        for k in ("gate_in", "crew", "ta_start", "ta_end", "ready", "off_block", "takeoff", "dep_runway"):
            setattr(res, k, chain[k])
        res.apron_wait = max(0.0, res.gate_in - res.in_request)
        res.arr_delay = max(0.0, res.gate_in - (f.sta + TIMING["taxi_in_min"]))
        res.dep_delay = max(0.0, res.off_block - f.std)

    def _run_once(self, ordered: list[Flight], protected: set[str]) -> list[FlightResult]:
        results = {f.id: FlightResult(
            id=f.id, airline=f.airline, aircraft=f.aircraft, size=f.size, origin=f.origin,
            destination=f.destination, pax=f.pax, connecting=f.connecting, sta=f.sta, std=f.std,
            eta=f.sta + self.d.flight_delays.get(f.id, 0.0), planned_gate=f.planned_gate,
        ) for f in ordered}
        # protected arrivals get their landing slots before any departure is sequenced
        for f in ordered:
            if f.id in protected:
                self._land(f, results[f.id])
        for f in ordered:
            if f.id not in protected:
                self._land(f, results[f.id])
            self._turn(f, results[f.id])
        return list(results.values())


def simulate(flights: list[Flight], disruption: Disruption, policy: Policy) -> list[FlightResult]:
    return AirportEngine(flights, disruption, policy).run()


def assign_planned_gates(flights: list[Flight]) -> list[Flight]:
    """Build the published (normal-day) gate plan with an allocation run, contact gates only."""
    planner = Policy(name="planning", gate_policy="reallocate", crew_policy="zone")
    res = simulate(flights, Disruption(), planner)
    by_id = {r.id: r for r in res}
    out = []
    for f in flights:
        f2 = copy.deepcopy(f)
        r = by_id[f.id]
        f2.planned_gate = r.gate or ""
        # the published schedule is feasible on a normal day: off-block never before the plan allows
        if r.off_block is not None and r.off_block > f2.std:
            f2.std = float(math.ceil(r.off_block / 5.0) * 5)
        out.append(f2)
    return out
