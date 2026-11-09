"""Deterministic tools the agents call. Agents never touch state except through these.

Each tool returns plain JSON-serialisable data computed by the simulation engine.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

from ..simulation.config import CREWS, GATES, RUNWAYS, TIMING
from ..simulation.engine import Disruption, Policy, simulate
from ..simulation.flights import Flight
from ..simulation.metrics import compute_metrics, objective
from ..simulation.validator import validate

LEVERS = {
    "sequencing": ["fifo", "priority"],
    "arrival_protection": ["none", "fuel", "all"],
    "gate_policy": ["fixed", "reallocate"],
    "use_remote_stands": [False, True],
    "crew_policy": ["zone", "pooled"],
    "gate_aware": [False, True],
}


@dataclass
class Workspace:
    """Shared, versioned operational context for one incident."""
    flights: list[Flight]
    disruption: Disruption
    version: int = 1
    candidate: dict = field(default_factory=dict)       # lever -> value agreed so far
    _cache: dict = field(default_factory=dict)

    def bump(self) -> int:
        self.version += 1
        return self.version

    def policy(self, levers: dict | None = None, name: str = "candidate") -> Policy:
        p = Policy(name=name)
        for k, v in (levers if levers is not None else self.candidate).items():
            if k in LEVERS and v in LEVERS[k]:
                setattr(p, k, v)
        return p

    def run(self, levers: dict | None) -> tuple[list, dict]:
        key = tuple(sorted((levers or {}).items()))
        if key not in self._cache:
            res = simulate(self.flights, self.disruption, self.policy(levers or {}))
            self._cache[key] = (res, compute_metrics(res, self.disruption))
        return self._cache[key]


def hhmm(t: float | None) -> str:
    if t is None:
        return "--:--"
    m = int(round(t)) + 14 * 60
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


# ----------------------------------------------------------------------------- tools
def get_weather_impact(ws: Workspace, **_) -> dict:
    d = ws.disruption
    return {
        "event": d.label,
        "window": f"{hhmm(d.start)}-{hhmm(d.end)}" if d.end > d.start else "n/a",
        "visibility_m": d.visibility_m,
        "wind_kt": d.wind_kt,
        "runway_closures": [{**c, "window": f"{hhmm(c['start'])}-{hhmm(c['end'])}"} for c in d.runway_closures],
        "capacity_limits": [{**o, "window": f"{hhmm(o['start'])}-{hhmm(o['end'])}"} for o in d.capacity_overrides],
        "turnaround_factor": d.turnaround_factor,
        "gate_closures": d.gate_closures,
        "crews_unavailable": d.crews_unavailable,
        "assumption": "Synthetic low-visibility and crosswind parameters from scenario configuration.",
    }


def runway_capacity_profile(ws: Workspace, **_) -> dict:
    """Hourly capacity vs scheduled demand in 30-minute buckets."""
    d = ws.disruption
    buckets = []
    for b in range(0, 300, 30):
        cap = 0.0
        for r in RUNWAYS:
            rw = r["id"]
            for t in range(b, b + 30):
                if any(c["runway"] == rw and c["start"] <= t < c["end"] for c in d.runway_closures):
                    continue
                c = r["capacity_per_hour"]
                for o in d.capacity_overrides:
                    if o["runway"] == rw and o["start"] <= t < o["end"]:
                        c = min(c, o["capacity_per_hour"])
                cap += c / 60.0
        demand = sum(1 for f in ws.flights if b <= f.sta + d.flight_delays.get(f.id, 0) < b + 30)
        demand += sum(1 for f in ws.flights if b <= f.std + TIMING["taxi_out_min"] < b + 30)
        buckets.append({"window": f"{hhmm(b)}-{hhmm(b + 30)}", "capacity": round(cap, 1), "demand": demand,
                        "overload": max(0, round(demand - cap, 1))})
    return {"buckets": buckets, "total_overload": round(sum(x["overload"] for x in buckets), 1)}


def predict_airborne_holds(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    limit = TIMING["max_airborne_hold_min"]
    risky = sorted([r for r in res if r.hold > limit - 15 or r.diverted], key=lambda r: -r.hold)
    return {
        "fuel_hold_limit_min": limit,
        "max_hold_min": m["max_airborne_hold_min"],
        "diversions": m["diversions"],
        "diverted_pax": m["diverted_pax"],
        "flights_near_fuel_limit": [
            {"flight": r.id, "aircraft": r.aircraft, "pax": r.pax, "hold_min": round(r.hold, 1),
             "outcome": "DIVERTS" if r.diverted else "lands"} for r in risky[:8]],
    }


def affected_flights(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    thr = TIMING["delay_threshold_min"]
    hit = sorted([r for r in res if r.diverted or r.dep_delay > thr],
                 key=lambda r: -(r.dep_delay if not r.diverted else 999))
    return {
        "delayed_flights": m["delayed_flights"],
        "diversions": m["diversions"],
        "passenger_delay_hours": m["passenger_delay_hours"],
        "connections_at_risk": m["connections_at_risk"],
        "worst": [{"flight": r.id, "aircraft": r.aircraft, "pax": r.pax, "connecting": r.connecting,
                   "dep_delay_min": round(r.dep_delay, 1), "diverted": r.diverted} for r in hit[:8]],
    }


def priority_ranking(ws: Workspace, **_) -> dict:
    ranked = sorted(ws.flights, key=lambda f: -f.priority)
    return {
        "rule": "priority = (passengers + 2 x connecting passengers) / 100 (synthetic weighting)",
        "top": [{"flight": f.id, "aircraft": f.aircraft, "pax": f.pax, "connecting": f.connecting,
                 "priority": f.priority} for f in ranked[:8]],
    }


def gate_conflicts(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    closed = sorted({c["gate"] for c in ws.disruption.gate_closures})
    waits = sorted([r for r in res if r.apron_wait > 2], key=lambda r: -r.apron_wait)
    moved = [r for r in res if r.gate and r.planned_gate and r.gate != r.planned_gate]
    return {
        "closed_gates": closed,
        "apron_holds": m["apron_holds"],
        "apron_wait_min": m["apron_wait_min"],
        "aircraft_waiting_for_gate": [
            {"flight": r.id, "aircraft": r.aircraft, "planned_gate": r.planned_gate, "gate": r.gate,
             "wait_min": round(r.apron_wait, 1)} for r in waits[:8]],
        "gate_changes": len(moved),
        "remote_stand_turns": m["remote_stand_turns"],
        "contact_gate_utilisation_pct": m["contact_gate_utilisation_pct"],
    }


def crew_load(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    avail = [c for c in CREWS if c["id"] not in set(ws.disruption.crews_unavailable)]
    zones = {}
    for z in ("A", "B", "R"):
        crews = [c["id"] for c in avail if c["zone"] == z]
        peak = 0
        for t in range(0, 360, 5):
            busy = sum(1 for r in res if r.crew in crews and r.ta_start is not None and r.ta_start <= t < r.ta_end)
            peak = max(peak, busy)
        zones[z] = {"crews": len(crews), "peak_concurrent_turnarounds": peak,
                    "saturated": peak >= len(crews) and len(crews) > 0}
    cross = sum(1 for r in res if r.crew and r.gate and
                next(c["zone"] for c in CREWS if c["id"] == r.crew) != next(g["zone"] for g in GATES if g["id"] == r.gate))
    return {"zones": zones, "crew_utilisation_pct": m["crew_utilisation_pct"],
            "cross_zone_assignments": cross, "unavailable": ws.disruption.crews_unavailable}


def simulate_plan(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    v = validate(res, ws.disruption)
    return {"levers": levers or {}, "metrics": m, "objective": objective(m),
            "feasible": not v, "violations": v[:5]}


def explore_plans(ws: Workspace, anchor: dict | None = None, **_) -> dict:
    """Exhaustive search over the recovery lever space (72 combinations), each simulated and validated."""
    out = []
    keys = list(LEVERS)
    for combo in itertools.product(*(LEVERS[k] for k in keys)):
        lv = dict(zip(keys, combo))
        if lv["gate_policy"] == "fixed" and lv["use_remote_stands"]:
            continue
        res, m = ws.run(lv)
        out.append((objective(m), lv, m, not validate(res, ws.disruption)))
    out.sort(key=lambda x: x[0])
    feasible = [x for x in out if x[3]]
    return {"evaluated": len(out), "feasible": len(feasible),
            "top": [{"levers": lv, "objective": o, "metrics": m} for o, lv, m, _ in feasible[:5]]}


def validate_plan(ws: Workspace, levers: dict | None = None, **_) -> dict:
    res, m = ws.run(levers or {})
    v = validate(res, ws.disruption)
    base_res, base_m = ws.run({})
    base = {r.id: r for r in base_res}
    worse = []
    for r in res:
        b = base[r.id]
        if not r.diverted and not b.diverted and r.dep_delay > b.dep_delay + 5:
            worse.append({"flight": r.id, "baseline_delay": round(b.dep_delay, 1),
                          "plan_delay": round(r.dep_delay, 1)})
    worse.sort(key=lambda x: -(x["plan_delay"] - x["baseline_delay"]))
    return {
        "feasible": not v,
        "violations": v,
        "checks": ["runway closure", "runway separation", "gate compatibility", "gate double-booking",
                   "gate closures", "crew availability", "crew double-booking", "taxi and turnaround order",
                   "no early departures"],
        "flights_worse_than_baseline": worse[:8],
        "count_worse": len(worse),
        "remote_stand_pax": sum(r.pax for r in res if r.gate_kind == "remote"),
        "max_delay_min": m["max_departure_delay_min"],
    }


TOOLS: dict[str, dict[str, Any]] = {
    "get_weather_impact": {"fn": get_weather_impact, "desc": "Interpret the active weather/disruption event: windows, runway closures, capacity limits.", "params": {}},
    "runway_capacity_profile": {"fn": runway_capacity_profile, "desc": "Runway capacity vs scheduled demand in 30-minute buckets.", "params": {}},
    "predict_airborne_holds": {"fn": predict_airborne_holds, "desc": "Simulate airborne holding and diversions for a lever set (empty = baseline).", "params": {"levers": "object"}},
    "affected_flights": {"fn": affected_flights, "desc": "Delayed/diverted flights, passenger delay hours and connections at risk for a lever set.", "params": {"levers": "object"}},
    "priority_ranking": {"fn": priority_ranking, "desc": "Flights ranked by passenger/connection priority.", "params": {}},
    "gate_conflicts": {"fn": gate_conflicts, "desc": "Closed gates, aircraft waiting for a gate, gate changes for a lever set.", "params": {"levers": "object"}},
    "crew_load": {"fn": crew_load, "desc": "Ground crew saturation by zone for a lever set.", "params": {"levers": "object"}},
    "simulate_plan": {"fn": simulate_plan, "desc": "Simulate and validate a full lever set; returns metrics and objective.", "params": {"levers": "object"}},
    "explore_plans": {"fn": explore_plans, "desc": "Search the full recovery lever space; returns top feasible plans.", "params": {}},
    "validate_plan": {"fn": validate_plan, "desc": "Independent hard-constraint validation and trade-off check of a lever set.", "params": {"levers": "object"}},
}


def call_tool(ws: Workspace, name: str, args: dict | None = None) -> dict:
    if name not in TOOLS:
        raise KeyError(f"unknown tool {name}")
    fn: Callable = TOOLS[name]["fn"]
    return fn(ws, **(args or {}))
