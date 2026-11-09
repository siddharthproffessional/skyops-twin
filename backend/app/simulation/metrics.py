"""Performance metrics. Every number shown in the UI is computed here from a schedule."""
from __future__ import annotations

from .config import CREWS, GATES, TIMING
from .engine import Disruption, FlightResult


def compute_metrics(results: list[FlightResult], disruption: Disruption) -> dict:
    thr = TIMING["delay_threshold_min"]
    flown = [r for r in results if not r.diverted]
    diverted = [r for r in results if r.diverted]
    dep_delays = [r.dep_delay for r in flown]
    total_dep_delay = sum(dep_delays) + TIMING["diversion_passenger_delay_min"] * len(diverted)
    total_arr_delay = sum(r.arr_delay for r in flown)
    delayed = [r for r in flown if r.dep_delay > thr]
    div_min = TIMING["diversion_passenger_delay_min"]
    pax_delay_min = sum(r.dep_delay * r.pax for r in flown)
    pax_delay_min += sum(r.pax * TIMING["diversion_passenger_delay_min"] for r in diverted)
    conn_risk = sum(r.connecting for r in flown
                    if r.arr_delay > TIMING["missed_connection_arrival_delay_min"])
    conn_risk += sum(r.connecting for r in diverted)
    apron_holds = [r for r in flown if r.apron_wait > 2.0]
    max_hold = max((r.hold for r in results), default=0.0)

    crews_avail = [c for c in CREWS if c["id"] not in set(disruption.crews_unavailable)]
    t0 = min((r.ta_start for r in flown if r.ta_start is not None), default=0.0)
    t1 = max((r.ta_end for r in flown if r.ta_end is not None), default=1.0)
    busy = sum((r.ta_end - r.ta_start) for r in flown if r.ta_start is not None)
    crew_util = busy / max(1.0, (t1 - t0) * max(1, len(crews_avail)))

    contact = [g for g in GATES if g["kind"] == "contact"]
    remote_used = len([r for r in flown if r.gate_kind == "remote"])
    gate_minutes = sum((r.off_block - r.gate_in) for r in flown
                       if r.gate_in is not None and r.gate_kind == "contact")
    gate_util = gate_minutes / max(1.0, (t1 - t0) * len(contact))

    # Recovery: minutes after the disruption ends until departures are back within threshold
    late_after = [r.off_block for r in flown if r.dep_delay > thr]
    recovery_end = max(late_after) if late_after else disruption.end
    recovery_min = max(0.0, recovery_end - disruption.end) if disruption.end > 0 else 0.0

    return {
        "flights_total": len(results),
        "flights_operated": len(flown),
        "diversions": len(diverted),
        "diverted_pax": sum(r.pax for r in diverted),
        "delayed_flights": len(delayed),
        "disrupted_flights": len(delayed) + len(diverted),
        "on_time_pct": round(100.0 * (len(flown) - len(delayed)) / max(1, len(results)), 1),
        "total_departure_delay_min": round(total_dep_delay, 1),
        "total_arrival_delay_min": round(total_arr_delay, 1),
        "avg_departure_delay_min": round(total_dep_delay / max(1, len(results)), 1),
        "max_departure_delay_min": round(max(dep_delays, default=0.0), 1),
        "passenger_delay_hours": round(pax_delay_min / 60.0, 1),
        "connections_at_risk": int(conn_risk),
        "apron_holds": len(apron_holds),
        "apron_wait_min": round(sum(r.apron_wait for r in flown), 1),
        "max_airborne_hold_min": round(max_hold, 1),
        "remote_stand_turns": remote_used,
        "crew_utilisation_pct": round(100.0 * crew_util, 1),
        "contact_gate_utilisation_pct": round(100.0 * gate_util, 1),
        "recovery_time_min": round(recovery_min, 1),
    }


def objective(m: dict) -> float:
    """Recovery objective (lower is better). Weights are configurable synthetic assumptions."""
    return round(
        m["passenger_delay_hours"] * 1.0
        + m["connections_at_risk"] * 0.8
        + m["apron_wait_min"] * 0.5,
        1,
    )
