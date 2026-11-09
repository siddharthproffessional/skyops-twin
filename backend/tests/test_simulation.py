import copy

import pytest

from app.simulation.engine import Disruption, Policy, simulate, assign_planned_gates
from app.simulation.flights import build_flights
from app.simulation.metrics import compute_metrics
from app.simulation.scenarios import (operation_sandstorm, runway_closure, crew_unavailable,
                                      flight_delay, gate_closure, capacity_reduction)
from app.simulation.validator import validate

RECOVERY = Policy(name="recovery", sequencing="priority", arrival_protection="fuel",
                  gate_policy="reallocate", use_remote_stands=True, gate_aware=True)


@pytest.fixture(scope="module")
def flights():
    return assign_planned_gates(build_flights())


def run(flights, d, p):
    res = simulate(flights, d, p)
    return [r.to_dict() for r in res], compute_metrics(res, d)


def test_normal_day_is_feasible_and_on_time(flights):
    sched, m = run(flights, Disruption(), Policy())
    assert validate(sched, Disruption()) == []
    assert m["delayed_flights"] == 0 and m["diversions"] == 0


@pytest.mark.parametrize("policy", [Policy(), RECOVERY,
                                    Policy(sequencing="priority", arrival_protection="all",
                                           gate_policy="reallocate", use_remote_stands=True,
                                           crew_policy="pooled")])
def test_sandstorm_plans_respect_all_hard_constraints(flights, policy):
    d = operation_sandstorm()
    sched, _ = run(flights, d, policy)
    assert validate(sched, d) == []


def test_runway_closure_no_movements_on_closed_runway(flights):
    d = runway_closure("30L", 30, 90)
    sched, _ = run(flights, d, Policy())
    for r in sched:
        if r["diverted"]:
            continue
        for t, rw in ((r["land"], r["arr_runway"]), (r["takeoff"], r["dep_runway"])):
            assert not (rw == "30L" and 30 <= t < 90)
    assert validate(sched, d) == []


def test_gate_closure_respected(flights):
    d = gate_closure("A1", 0, 200)
    sched, _ = run(flights, d, RECOVERY)
    assert all(r["gate"] != "A1" for r in sched if not r["diverted"] and r["gate_in"] < 200)
    assert validate(sched, d) == []


def test_aircraft_gate_compatibility(flights):
    sched, _ = run(flights, operation_sandstorm(), RECOVERY)
    a380 = [r for r in sched if r["aircraft"] == "A388" and not r["diverted"]]
    assert a380 and all(r["gate"] in {"A1", "A2", "A3"} for r in a380)


def test_ground_crew_shortage_never_uses_unavailable_crew(flights):
    d = crew_unavailable(["GH-A1", "GH-A2", "GH-A3"])
    sched, _ = run(flights, d, Policy(crew_policy="pooled", gate_policy="reallocate"))
    assert all(r["crew"] not in {"GH-A1", "GH-A2", "GH-A3"} for r in sched if not r["diverted"])
    assert validate(sched, d) == []


def test_multiple_simultaneous_flight_delays(flights):
    d = Disruption()
    for f in flights[:5]:
        d = d.merge(flight_delay(f.id, 45))
    sched, m = run(flights, d, RECOVERY)
    assert validate(sched, d) == []
    assert m["delayed_flights"] >= 1


def test_recovery_beats_baseline_on_sandstorm(flights):
    d = operation_sandstorm()
    _, base = run(flights, d, Policy())
    _, rec = run(flights, d, RECOVERY)
    assert rec["passenger_delay_hours"] < base["passenger_delay_hours"]
    assert rec["diversions"] <= base["diversions"]


def test_simulation_is_reproducible(flights):
    d = operation_sandstorm()
    a, _ = run(flights, d, RECOVERY)
    b, _ = run(assign_planned_gates(build_flights()), d, RECOVERY)
    assert a == b


def test_validator_rejects_invalid_plan(flights):
    d = operation_sandstorm()
    sched, _ = run(flights, d, RECOVERY)
    bad = copy.deepcopy(sched)
    a380 = next(r for r in bad if r["aircraft"] == "A388" and not r["diverted"])
    a380["gate"] = "B1"                                   # incompatible gate
    other = next(r for r in bad if not r["diverted"] and r["id"] != a380["id"] and r["size"] == "C")
    twin = next(r for r in bad if not r["diverted"] and r["id"] not in (a380["id"], other["id"]))
    twin["gate"], twin["gate_in"], twin["off_block"] = other["gate"], other["gate_in"], other["off_block"]
    twin["size"] = "C"
    moved = next(r for r in bad if not r["diverted"] and r["arr_runway"] == "30R" and 30 < r["land"] < 100)
    moved["arr_runway"] = "30L"                           # closed during the storm
    rules = {x["rule"] for x in validate(bad, d)}
    assert {"gate_compatibility", "gate_double_booking", "runway_closed"} <= rules


def test_capacity_reduction_spacing(flights):
    d = capacity_reduction("30R", 10, 0, 300)
    sched, _ = run(flights, d, Policy())
    assert validate(sched, d) == []
