# Architecture

```
 Browser (React/TS/Tailwind)                    FastAPI backend (modular monolith)
 ┌──────────────────────────────┐   REST       ┌───────────────────────────────────────────────┐
 │ Command Centre (SVG twin)    │ ───────────▶ │ main.py  /api/*  disruptions, plans, approve  │
 │ Agent Control Room           │ ◀─────────── │          /ws/operations  live event stream    │
 │ Recovery & Analytics         │   WebSocket  ├───────────────────────────────────────────────┤
 └──────────────────────────────┘              │ agents/orchestrator.py  task loop, versions,  │
                                               │   conflicts, plan ranking, review, approval   │
                                               │ agents/agents.py  Weather Runway Flight Gate  │
                                               │   Ground Recovery  (Claude brain | policy)    │
                                               │ agents/tools.py   deterministic tools only    │
                                               ├───────────────────────────────────────────────┤
                                               │ simulation/engine.py     owns all state       │
                                               │ simulation/validator.py  independent checks   │
                                               │ simulation/metrics.py    every number shown   │
                                               ├───────────────────────────────────────────────┤
                                               │ ai/ claude_client · openai_client · router    │
                                               │ db.py SQLite: incidents, agent_events, plans, │
                                               │   approvals, audit_events                     │
                                               └───────────────────────────────────────────────┘
```

## Principles

1. **LLMs propose, Python disposes.** Agents can only call tools. A proposal is a recovery
   *lever* (sequencing, arrival protection, gate policy, remote stands, crew policy, gate-aware
   re-sequencing). Unknown levers or values are discarded. The engine computes the schedule and
   the validator checks it independently.
2. **Every number is computed.** Metrics come from `metrics.py` over a seeded, reproducible run.
3. **Real coordination.** The message feed is the backend's own event log, streamed over WebSocket.
4. **Human in the loop.** Plans are only applied after approval; every decision is audit-logged.
5. **Graceful degradation.** Any provider failure switches that agent to its deterministic policy.

## Orchestration loop

1. Weather Agent publishes restrictions → Runway Agent quantifies capacity loss and diversion risk.
2. Flight, Gate and Ground agents assess impact in parallel and propose levers.
3. Orchestrator merges proposals into a versioned shared plan (v2…).
4. Gate, Ground and Runway agents re-check the draft. Conflicts trigger re-planning:
   e.g. Gate → Flight "your sequence lands aircraft before a gate is free" → Flight tests
   gate-aware re-sequencing in simulation and adopts it only if it helps; Ground withdraws crew
   pooling when the simulation shows transfer time costs more than it saves. Max 4 iterations.
5. Recovery Agent simulates the negotiated plan and searches the full lever space
   (72 combinations, each simulated and validated), and ranks plans by the objective.
6. Independent reviewer (OpenAI or deterministic) critiques the recommendation with its own
   passenger-centric criterion; disagreements are escalated to the controller.
7. Controller approves or rejects; approved plan becomes the active schedule (state version bump).

## Simulation model (synthetic)

- 2 parallel runways (32 movements/h each), separation enforced by capacity.
- 26 stands: 3 code F, 9 code E, 10 code C contact gates, 4 remote stands (+12 min turnaround).
- 36 rotations (A380, 777-300ER, A350, A321neo, 737 MAX) in a 3-hour bank, seeded.
- 17 ground crews in zones A/B/R; one turnaround per crew; cross-zone transfer +6 min.
- Fuel assumption: an arrival holding more than 45 min diverts.
- Operation Sandstorm: 30L closed 14:20–15:50, 30R limited to 12 movements/h, turnarounds +30%,
  gates A6/B6 closed, one crew stood down.

Objective (lower is better): passenger-delay hours + 0.8 × connections at risk + 0.5 × apron-wait
minutes, where a diverted passenger counts as 240 delay minutes. All weights are configurable.

## Integration adapters (Round 3)

- METAR feed: functional parser (wind, gusts, visibility, SA/DU/SS/DS codes) → operating restrictions.
- AODB, A-CDM (TOBT/TSAT/TTOT), resource management: mapping contracts in `adapters.py`.

## Known limitations

- Synthetic airport and traffic; parameters are assumptions, not certified values.
- Runway model uses capacity-based separation, not wake-category separation.
- Taxi times are fixed; no taxiway conflict modelling.
- Live-AI mode not exercised against real APIs during the build (unit-tested with fake clients).
