# SkyOps Twin — Autonomous Multi-Agent Airport Recovery

AI Agent Arena · TechX Dubai 2026 · Domain: Aviation & Airport Operations

SkyOps Twin is a digital twin of a synthetic hub airport. When a disruption hits, a team of
AI agents analyses it, negotiates a recovery plan, has the plan independently reviewed,
validates it against hard constraints in a deterministic simulation, and gives a human
operations controller measured before/after results to approve.

> This is a simulated planning tool on a synthetic airport, not an air traffic control system.
> All airport, airline and operating parameters are labelled synthetic assumptions.

## Headline result (Operation Sandstorm, computed by the engine, reproducible)

| Metric | Standard procedures | SkyOps plan | Change |
|---|---|---|---|
| Diversions | 2 (590 passengers) | 0 | −100% |
| Passenger-delay hours | 4,918 | 1,970 | −60% |
| Connections at risk | 1,023 | 40 | −96% |
| Total departure delay (min) | 1,136 | 512 | −55% |
| Flights delayed or diverted | 18 | 15 | −17% |
| Max airborne hold (min) | 46 | 38 | −19% |

All hard constraints pass in every plan (runway closure, separation, gate compatibility,
double-booking, gate closures, crew availability and double-booking, turnaround order,
no early departures).

## Run it (one command)

Requirements: Python 3.11+, Node 18+.

```bash
cp .env.example .env      # optional: add ANTHROPIC_API_KEY / OPENAI_API_KEY
./start.sh                # builds the UI on first run, serves http://localhost:8000
```

Development mode (hot reload):

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api and /ws)
```

Tests: `cd backend && python3 -m pytest -v` (21 tests).

## AI modes

| Mode | When | What runs |
|---|---|---|
| Live AI | `ANTHROPIC_API_KEY` set | Each specialist is a Claude agent with its own instructions and tool allow-list (tool-use loop). Orchestrator narration by Claude. |
| + Independent reviewer | `OPENAI_API_KEY` set too | OpenAI reviews the recommended plan and evidence; disagreements are escalated to the controller. |
| Deterministic | no keys, or `SKYOPS_AI_MODE=offline` | Each agent runs its own coded decision policy over the same tools. Also the automatic fallback when a provider times out or rate-limits. |

The UI header always shows which mode is active. **Test the live-AI mode on your own machine
before the event**: it was written against the Anthropic Messages and OpenAI Chat Completions APIs
and unit-tested with fake clients, but not run against the real APIs during this build.
Set `SKYOPS_CLAUDE_MODEL`, `SKYOPS_CLAUDE_FAST_MODEL` and `SKYOPS_OPENAI_MODEL` to models your
accounts can use.

## Deploy

One service serves both API and UI (simplest and most reliable for a demo):

- **Render**: push the repo to GitHub, "New Blueprint" → it picks up `render.yaml` and the `Dockerfile`.
  Add the API keys as environment variables.
- **Docker anywhere**: `docker build -t skyops . && docker run -p 8000:8000 skyops`
- Split hosting (Vercel UI + Render API) also works: build the frontend with
  `VITE_API_BASE=https://your-api.onrender.com`.

Always keep the local copy ready for the venue: venue Wi-Fi is the most likely failure.

## Repository

```
backend/app/simulation/   engine.py (constraint-aware scheduler), validator.py (independent hard checks),
                          metrics.py, scenarios.py, flights.py (seeded synthetic bank), config.py
backend/app/agents/       tools.py (deterministic tools), agents.py (6 specialists), orchestrator.py
backend/app/ai/           base.py, claude_client.py, openai_client.py, router.py
backend/app/              main.py (REST + WebSocket), db.py (SQLite audit), events_parser.py, adapters.py (METAR, AODB, A-CDM)
frontend/src/             App.tsx, components/ (AirportTwin, AgentFeed, ControlRoom, Recovery, Controls), lib/
```

See ARCHITECTURE.md, DEMO_SCRIPT.md and TEST_REPORT.md.

## Vercel (serverless mode)

`vercel.json` deploys the UI as static files and the backend as one Python function (`api/index.py`).
Vercel functions have no WebSockets or shared memory, so the hosted build runs in serverless mode:
each incident is computed in a single `/api/run` request (the real agent run), and the browser then
streams that recorded message log at a readable pace. Use `./start.sh` locally for the fully live,
WebSocket version.
