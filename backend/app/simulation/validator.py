"""Independent hard-constraint validator.

Checks a schedule (list of FlightResult dicts or objects) against the airport model
without trusting the engine or any AI agent. A plan is feasible only if this returns
no violations.
"""
from __future__ import annotations

from typing import Any

from .config import CREWS, GATES, RUNWAYS, SIZE_RANK, TIMING
from .engine import Disruption

TOL = 0.02  # schedules are exchanged rounded to 0.01 min


def _g(r: Any, k: str):
    return r[k] if isinstance(r, dict) else getattr(r, k)


def _runway_open(d: Disruption, rw: str, t: float) -> bool:
    return not any(c["runway"] == rw and c["start"] <= t < c["end"] for c in d.runway_closures)


def _spacing(d: Disruption, rw: str, t: float) -> float:
    cap = next(r["capacity_per_hour"] for r in RUNWAYS if r["id"] == rw)
    for o in d.capacity_overrides:
        if o["runway"] == rw and o["start"] <= t < o["end"]:
            cap = min(cap, o["capacity_per_hour"])
    return 60.0 / cap


def validate(schedule: list, disruption: Disruption) -> list[dict]:
    v: list[dict] = []
    gates = {g["id"]: g for g in GATES}
    crews_ok = {c["id"] for c in CREWS} - set(disruption.crews_unavailable)
    buf = TIMING["gate_buffer_min"]
    movements: dict[str, list[tuple[float, str]]] = {r["id"]: [] for r in RUNWAYS}

    for r in schedule:
        fid = _g(r, "id")
        if _g(r, "diverted"):
            continue
        land, takeoff = _g(r, "land"), _g(r, "takeoff")
        arw, drw = _g(r, "arr_runway"), _g(r, "dep_runway")
        gate, size = _g(r, "gate"), _g(r, "size")
        for t, rw, what in ((land, arw, "landing"), (takeoff, drw, "take-off")):
            if rw not in movements:
                v.append({"rule": "runway_exists", "flight": fid, "detail": f"unknown runway {rw}"})
                continue
            if not _runway_open(disruption, rw, t):
                v.append({"rule": "runway_closed", "flight": fid,
                          "detail": f"{what} on closed runway {rw} at t={t:.1f}"})
            movements[rw].append((t, fid))
        if gate not in gates:
            v.append({"rule": "gate_exists", "flight": fid, "detail": f"unknown gate {gate}"})
            continue
        if SIZE_RANK[gates[gate]["size"]] < SIZE_RANK[size]:
            v.append({"rule": "gate_compatibility", "flight": fid,
                      "detail": f"{_g(r, 'aircraft')} (code {size}) cannot use gate {gate} (code {gates[gate]['size']})"})
        gi, ob = _g(r, "gate_in"), _g(r, "off_block")
        for c in disruption.gate_closures:
            if c["gate"] == gate and gi < c["end"] and ob > c["start"]:
                v.append({"rule": "gate_closed", "flight": fid, "detail": f"gate {gate} closed during use"})
        if gi + TOL < land + TIMING["taxi_in_min"]:
            v.append({"rule": "taxi_in", "flight": fid, "detail": "on gate before taxi-in completes"})
        ts, te = _g(r, "ta_start"), _g(r, "ta_end")
        if ts + TOL < gi:
            v.append({"rule": "turnaround_start", "flight": fid, "detail": "turnaround starts before on-gate"})
        if ob + TOL < te:
            v.append({"rule": "turnaround_complete", "flight": fid, "detail": "off-block before turnaround completes"})
        if ob + TOL < _g(r, "std"):
            v.append({"rule": "early_departure", "flight": fid, "detail": "off-block before scheduled time"})
        if takeoff + TOL < ob + TIMING["taxi_out_min"]:
            v.append({"rule": "taxi_out", "flight": fid, "detail": "take-off before taxi-out completes"})
        if _g(r, "crew") not in crews_ok:
            v.append({"rule": "crew_available", "flight": fid, "detail": f"crew {_g(r, 'crew')} unavailable"})

    # runway separation
    for rw, ms in movements.items():
        ms.sort()
        for (t1, f1), (t2, f2) in zip(ms, ms[1:]):
            need = max(_spacing(disruption, rw, t1), _spacing(disruption, rw, t2))
            if t2 - t1 + TOL < need:
                v.append({"rule": "runway_separation", "flight": f2,
                          "detail": f"{f1}/{f2} on {rw} only {t2 - t1:.2f} min apart (need {need:.2f})"})

    # gate and crew double-booking
    flown = [r for r in schedule if not _g(r, "diverted")]
    for key, start, end, label, gap in (("gate", "gate_in", "off_block", "gate_double_booking", buf),
                                        ("crew", "ta_start", "ta_end", "crew_double_booking", 0.0)):
        by: dict[str, list] = {}
        for r in flown:
            by.setdefault(_g(r, key), []).append((_g(r, start), _g(r, end), _g(r, "id")))
        for res, iv in by.items():
            iv.sort()
            for (a1, b1, f1), (a2, b2, f2) in zip(iv, iv[1:]):
                if a2 + TOL < b1 + gap:
                    v.append({"rule": label, "flight": f2, "detail": f"{f1} and {f2} overlap on {res}"})
    return v
