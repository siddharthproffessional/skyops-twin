# Test report

Run: `cd backend && python3 -m pytest -v` (offline AI mode, 2026-11-09)

```
tests/test_agents.py::test_llm_brain_runs_tool_loop_and_filters_invalid_levers PASSED
tests/test_agents.py::test_provider_failure_falls_back_to_deterministic_policy PASSED
tests/test_agents.py::test_clean_actions_rejects_unknown_values PASSED
tests/test_agents.py::test_conflicting_recommendations_are_escalated PASSED
tests/test_agents.py::test_openai_reviewer_failure_falls_back PASSED
tests/test_api.py::test_sandstorm_end_to_end_with_websocket_and_approval PASSED
tests/test_api.py::test_reject_and_freetext_and_metar PASSED
tests/test_api.py::test_invalid_requests PASSED
tests/test_simulation.py::test_normal_day_is_feasible_and_on_time PASSED
tests/test_simulation.py::test_sandstorm_plans_respect_all_hard_constraints[policy0] PASSED
tests/test_simulation.py::test_sandstorm_plans_respect_all_hard_constraints[policy1] PASSED
tests/test_simulation.py::test_sandstorm_plans_respect_all_hard_constraints[policy2] PASSED
tests/test_simulation.py::test_runway_closure_no_movements_on_closed_runway PASSED
tests/test_simulation.py::test_gate_closure_respected PASSED
tests/test_simulation.py::test_aircraft_gate_compatibility PASSED
tests/test_simulation.py::test_ground_crew_shortage_never_uses_unavailable_crew PASSED
tests/test_simulation.py::test_multiple_simultaneous_flight_delays PASSED
tests/test_simulation.py::test_recovery_beats_baseline_on_sandstorm PASSED
tests/test_simulation.py::test_simulation_is_reproducible PASSED
tests/test_simulation.py::test_validator_rejects_invalid_plan PASSED
tests/test_simulation.py::test_capacity_reduction_spacing PASSED
======================== 21 passed in 68.25s (0:01:08) =========================
```

## Coverage against the brief

| Requirement | Test |
|---|---|
| Runway closure | test_runway_closure_no_movements_on_closed_runway |
| Gate conflict / double booking | test_sandstorm_plans_respect_all_hard_constraints, test_validator_rejects_invalid_plan |
| Aircraft–gate incompatibility | test_aircraft_gate_compatibility, test_validator_rejects_invalid_plan |
| Ground resource shortage | test_ground_crew_shortage_never_uses_unavailable_crew |
| Multiple simultaneous delays | test_multiple_simultaneous_flight_delays |
| Claude API failure | test_provider_failure_falls_back_to_deterministic_policy |
| OpenAI API failure | test_openai_reviewer_failure_falls_back |
| Conflicting agent recommendations | test_conflicting_recommendations_are_escalated |
| Plan approval / rejection | test_sandstorm_end_to_end_with_websocket_and_approval, test_reject_and_freetext_and_metar |
| Reproducibility | test_simulation_is_reproducible |
| Invalid plan rejected | test_validator_rejects_invalid_plan, test_invalid_requests |
| Live-AI tool loop | test_llm_brain_runs_tool_loop_and_filters_invalid_levers (fake model) |

Not tested here: real Anthropic/OpenAI API calls (no keys in the build environment).
