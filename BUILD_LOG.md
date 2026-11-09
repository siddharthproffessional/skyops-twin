# Build log

- Engine: constraint-aware greedy scheduler with runway slot search, gate/crew interval allocation,
  priority sequencing, fuel-aware arrival protection, gate-aware re-sequencing. Published schedule is
  generated feasible on a normal day (0 delayed flights), so all disruption effects are attributable.
- Validator written separately from the engine; it caught a real rounding defect during development
  (schedules now exchanged at 0.01 min precision).
- Scenario tuned (seed 36, 30R at 12 movements/h, 45-min fuel hold limit) so baseline and optimised
  responses genuinely diverge; the engine computes both.
- Finding during build: crew pooling looks attractive but loses once gates are reallocated (transfer
  time). The Ground agent now discovers and withdraws it live, which became part of the demo.
- Decision: one service serves API + UI to reduce venue failure points.
