"""Scenario and disruption library (synthetic)."""
from __future__ import annotations

from .engine import Disruption

SANDSTORM_START = 20.0   # 14:20
SANDSTORM_END = 110.0    # 15:50


def operation_sandstorm() -> Disruption:
    return Disruption(
        label="Operation Sandstorm",
        kind="sandstorm",
        start=SANDSTORM_START,
        end=SANDSTORM_END,
        runway_closures=[{"runway": "30L", "start": SANDSTORM_START, "end": SANDSTORM_END}],
        capacity_overrides=[{"runway": "30R", "capacity_per_hour": 12,
                             "start": SANDSTORM_START, "end": SANDSTORM_END}],
        turnaround_factor=1.3,
        gate_closures=[{"gate": "A6", "start": SANDSTORM_START, "end": SANDSTORM_END + 30},
                       {"gate": "B6", "start": SANDSTORM_START, "end": SANDSTORM_END + 30}],
        crews_unavailable=["GH-A4"],
        visibility_m=600,
        wind_kt=38,
    )


def runway_closure(runway: str = "30L", start: float = 30, end: float = 90) -> Disruption:
    return Disruption(label=f"Runway {runway} closed", kind="runway_closure", start=start, end=end,
                      runway_closures=[{"runway": runway, "start": start, "end": end}])


def capacity_reduction(runway: str = "30R", cap: int = 20, start: float = 30, end: float = 120) -> Disruption:
    return Disruption(label=f"Runway {runway} capacity {cap}/h", kind="capacity_reduction",
                      start=start, end=end,
                      capacity_overrides=[{"runway": runway, "capacity_per_hour": cap,
                                           "start": start, "end": end}])


def flight_delay(flight_id: str, minutes: float) -> Disruption:
    return Disruption(label=f"{flight_id} inbound +{int(minutes)} min", kind="flight_delay",
                      flight_delays={flight_id: float(minutes)})


def crew_unavailable(crew_ids: list[str]) -> Disruption:
    return Disruption(label=f"Ground crew unavailable: {', '.join(crew_ids)}", kind="crew_unavailable",
                      start=0, end=300, crews_unavailable=list(crew_ids))


def gate_closure(gate: str, start: float = 0, end: float = 180) -> Disruption:
    return Disruption(label=f"Gate {gate} closed", kind="gate_closure", start=start, end=end,
                      gate_closures=[{"gate": gate, "start": start, "end": end}])


SCENARIOS = {
    "sandstorm": {
        "id": "sandstorm",
        "name": "Operation Sandstorm",
        "description": "Visibility 600 m, crosswind 38 kt. 30L closed 14:20-15:50, 30R limited to "
                       "12 movements/h, turnarounds +30%, gates A6/B6 closed, one ground crew stood down.",
        "build": operation_sandstorm,
    },
    "runway_closure": {
        "id": "runway_closure",
        "name": "Runway 30L closure",
        "description": "Unplanned runway inspection closes 30L from 14:30 to 15:30.",
        "build": runway_closure,
    },
    "crew_shortage": {
        "id": "crew_shortage",
        "name": "Ground crew shortage",
        "description": "Two zone-A ground crews unavailable for the afternoon bank.",
        "build": lambda: crew_unavailable(["GH-A3", "GH-A4"]),
    },
}
