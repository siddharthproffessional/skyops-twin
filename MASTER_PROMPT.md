# MASTER BUILD PROMPT — SKYOPS TWIN (v2)

Autonomous Multi-Agent Airport Operations & Disruption Recovery System
Competition: AI Agent Arena, TechX Dubai 2026 — Domain: Aviation & Airport Operations

You are the principal architect and lead engineer for SkyOps Twin. You are building a
competition-grade, solo-developer prototype in eight evening-sized development days.
Optimise for a flawless live demonstration and for proving genuine agent autonomy —
not for building a commercial platform.

Before writing any code: confirm with the organisers whether pre-built code is allowed
before problem statements are released (18 Nov). If not, build only reusable libraries
and practise, and rebuild the product during the event.

---

## 1. Product

SkyOps Twin is a digital twin of a synthetic hub airport. When a disruption hits, a team
of AI agents analyses it, negotiates a recovery plan, has the plan independently
reviewed, validates it against hard constraints in a deterministic simulation, and
presents measured before/after results to a human operations controller for approval.

Signature scenario: OPERATION SANDSTORM — visibility drops, one runway closes, the
remaining runway loses capacity, ground crews slow down, gates jam.

This is a simulated planning tool, not an air traffic control system. Never present
simulated decisions as certified aviation safety decisions. Label every number that
comes from synthetic assumptions.

## 2. Non-negotiable principles

1. The Python simulation engine owns all operational state. AI models never write state
   directly; they call tools, and every proposed action is validated by Python.
2. Every metric on screen is computed by the engine from a reproducible run
   (seeded, parameters stored). Never fabricate improvement percentages.
3. Agent activity shown in the UI is the real backend message log, streamed live.
   A recorded replay of a real run is allowed only if labelled "REPLAY".
4. A human approves or rejects every recovery plan. Every decision is audit-logged.
5. The system must keep working when an AI provider is slow, rate-limited or offline:
   a deterministic fallback policy runs the same orchestration loop and tools.

## 3. Stack (keep it small)

- Backend: Python 3.11+, FastAPI, Pydantic, sqlite3 (no ORM), WebSockets, httpx.
- AI: Anthropic Claude (orchestrator + specialists), OpenAI (independent reviewer only).
  Model adapter layer: `ai/base.py`, `ai/claude_client.py`, `ai/openai_client.py`,
  `ai/router.py`. Timeouts, one retry with backoff, provider-unavailable fallback.
  Keys only from environment variables; never sent to the browser.
- Frontend: React + TypeScript + Vite + Tailwind. Recharts optional. SVG airport map
  (no 3D modelling).
- Tests: pytest for all hard constraints. No browser test suite.
- Deploy: frontend on Vercel, backend on Render, plus a one-command local start.

## 4. Agents (one orchestrator + six specialists + one reviewer)

| Agent | Responsibility | Tools |
|---|---|---|
| Operations Orchestrator (Claude) | Opens the incident, assigns tasks, keeps shared context, resolves conflicts, caps iterations, produces the recommendation | dispatch, get_state, request_review, request_approval |
| Weather & Runway | Turns weather into runway availability and hourly capacity | get_weather, set_runway_status, runway_capacity |
| Flight | Finds affected flights, re-sequences departures/arrivals by priority | affected_flights, sequence_runway_slots |
| Gate | Re-allocates gates/remote stands by aircraft size and time windows; flags conflicts | gate_conflicts, allocate_gates |
| Ground Operations | Allocates turnaround crews; detects shortages and bottlenecks | crew_load, allocate_crews |
| Recovery | Builds alternative plans, simulates each, ranks them | simulate_plan, compare_plans |
| Independent Reviewer (OpenAI) | Critically reviews the chosen plan and evidence; lists disagreements | validate_plan |

Each specialist runs with its own instructions and tools and returns structured JSON:
`agent, task_id, findings[], proposed_actions[], evidence{}, uncertainty, constraints[], status`.
LLM "confidence" is not a probability of safety.

Run independent agents in parallel (Flight, Gate and Ground after Weather & Runway).
Use a fast model for specialists, the strongest model for the orchestrator.

Coordination must be real: e.g. Flight proposes a sequence → Gate finds conflicts with it →
Flight/Gate re-plan → Recovery validates. Implement message history, task assignment,
status (idle, working, completed, conflict, replanning, failed), tool-call logs,
state versioning, max iterations and timeouts.

## 5. Simulation engine

Synthetic hub (all values configurable and labelled synthetic): 2 parallel runways,
14 contact gates + 4 remote stands with size classes, 28 flights in a 3-hour bank with
mixed aircraft (A380, B777, A350, A321, B737), passenger counts, connecting passengers,
6 ground crews. Turnaround times by aircraft type.

Hard constraints (pytest-covered): no two aircraft at one gate at once (with buffer);
no aircraft on a closed runway; no aircraft at an incompatible gate; runway separation /
hourly capacity respected; crews never double-booked; no departure before its
turnaround completes.

Two strategies with identical inputs:
- BASELINE: first-come-first-served, keeps planned gates, waits when a gate is busy.
- OPTIMISED: the agents' plan — priority sequencing (passengers, connections, curfew),
  gate/remote-stand re-allocation, crew rebalancing.

Metrics: total delay minutes, delayed flights (>15 min), passengers delayed,
connections at risk, gate conflicts, crew utilisation, recovery time.
Tune the scenario so baseline and optimised genuinely diverge; the engine still computes both.

## 6. Screens (three, not six)

1. Command Centre — KPI strip, SVG airport twin (runways, taxiways, gates, aircraft,
   sandstorm overlay, closed runway), live agent feed, disruption controls.
2. Agent Control Room — every agent's status, messages, tool calls, conflicts, iterations.
3. Recovery & Analytics — baseline vs optimised charts, plan actions, reviewer findings,
   constraint check, approve / reject.

Disruption controls: sandstorm, close runway, reduce capacity, delay a flight, remove a
crew, plus a free-text event box (orchestrator maps it to a supported type or says it can't).

## 7. Round-specific requirements

- Round 2 (Adapt and Test): any judge-supplied event must be accepted through the
  free-text box or controls and re-planned live.
- Round 3 (Make It Work in Practice): include an adapter layer showing where real
  airport feeds (AODB, A-CDM milestones, METAR weather) would plug in.

## 8. Build order (UI visible from day 2)

1. Data model, synthetic dataset, engine, constraint tests.
2. Agent framework, orchestrator loop, WebSocket feed, a bare UI showing the feed.
3. Weather & Runway, Flight, Gate agents.
4. Ground Ops, Recovery agents; conflict/replan loop.
5. Reviewer, plan comparison, approval flow.
6. Full UI polish: map animation, control room, analytics.
7. Failure handling, free-text events, extra scenarios, replay mode.
8. Deploy, rehearse 3×, record backup video, feature freeze.

## 9. Docs to maintain

README.md, ARCHITECTURE.md, DEMO_SCRIPT.md, TEST_REPORT.md, BUILD_LOG.md.
