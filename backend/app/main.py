"""SkyOps Twin API: REST + WebSocket. Run: uvicorn app.main:app --port 8000"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .adapters import ADAPTERS, metar_to_disruption, parse_metar
from .agents.agents import AGENT_META
from .agents.orchestrator import Orchestrator
from .ai.router import ModelRouter
from .events_parser import SUPPORTED, build, parse
from .simulation import config as cfg
from .simulation.engine import Disruption, Policy, assign_planned_gates, simulate
from .simulation.flights import build_flights
from .simulation.metrics import compute_metrics
from .simulation.scenarios import SCENARIOS

app = FastAPI(title="SkyOps Twin", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, ev: dict) -> None:
        msg = json.dumps(ev, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


class State:
    def __init__(self):
        self.router = ModelRouter()
        self.reset()

    def reset(self):
        self.flights = assign_planned_gates(build_flights())
        self.disruption = Disruption()
        self.incident: Optional[dict] = None
        self.task: Optional[asyncio.Task] = None
        self.approved_plan: Optional[str] = None
        self.version = 1


hub = Hub()
S = State()


def _nominal_schedule() -> list[dict]:
    return [r.to_dict() for r in simulate(S.flights, Disruption(), Policy())]


def _active_schedule() -> tuple[str, list[dict]]:
    inc = S.incident
    if inc and S.approved_plan:
        p = next(p for p in inc["plans"] if p["id"] == S.approved_plan)
        return p["name"], p["schedule"]
    if S.disruption.kind != "none":
        res = simulate(S.flights, S.disruption, Policy())
        return "Baseline response (unmitigated)", [r.to_dict() for r in res]
    return "Normal operations", _nominal_schedule()


async def _emit(ev: dict) -> None:
    ev["ts"] = time.time()
    if S.incident is not None:
        S.incident["events"].append(ev)
        db.log_event(S.incident["id"], ev)
    await hub.broadcast(ev)


async def _run_incident(label: str) -> None:
    orch = Orchestrator(S.flights, S.disruption, _emit, S.router)
    S.incident = {"id": orch.incident_id, "label": label, "status": "running", "events": [], "plans": [],
                  "review": None, "recommendation": None, "started": time.time(),
                  "disruption": S.disruption.to_dict()}
    db.execute("INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
               (orch.incident_id, time.time(), label, json.dumps(S.disruption.to_dict()), "running", None,
                S.router.status()["mode"]))
    db.audit("incident_opened", {"incident": orch.incident_id, "label": label})
    try:
        out = await orch.run()
        S.incident.update(plans=out["plans"], review=out["review"], recommendation=out["recommendation"],
                          status="awaiting_approval")
        for p in out["plans"]:
            db.execute("INSERT OR REPLACE INTO recovery_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (orch.incident_id, p["id"], p["name"], json.dumps(p["levers"]), json.dumps(p["metrics"]),
                        p["objective"], int(p["feasible"]), int(bool(p.get("recommended")))))
        db.execute("UPDATE incidents SET status=?, recommendation=? WHERE id=?",
                   ("awaiting_approval", out["recommendation"], orch.incident_id))
        await hub.broadcast({"type": "incident_status", "status": "awaiting_approval", "incident": orch.incident_id})
    except Exception as e:  # never leave the UI hanging
        S.incident["status"] = "failed"
        db.audit("incident_failed", {"incident": orch.incident_id, "error": repr(e)})
        await hub.broadcast({"type": "incident_status", "status": "failed", "error": repr(e)})
        raise


async def _start(d: Disruption, label: str) -> dict:
    if S.task and not S.task.done():
        raise HTTPException(409, "An incident is already being worked. Wait for it to finish or reset.")
    # a new event on top of an unresolved disruption compounds it; after an approval it starts fresh
    S.disruption = d if (S.disruption.kind == "none" or S.approved_plan) else S.disruption.merge(d)
    S.approved_plan = None
    S.version += 1
    await hub.broadcast({"type": "disruption", "disruption": S.disruption.to_dict()})
    S.task = asyncio.create_task(_run_incident(label))
    await asyncio.sleep(0.05)
    return {"incident": S.incident["id"] if S.incident else None, "disruption": S.disruption.to_dict()}


# ------------------------------------------------------------------ models
class DisruptionIn(BaseModel):
    scenario_id: Optional[str] = None
    type: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class FreeTextIn(BaseModel):
    text: str = Field(min_length=3, max_length=500)


class MetarIn(BaseModel):
    raw: str = Field(min_length=10, max_length=300)


class DecisionIn(BaseModel):
    note: str = ""


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    return {"ok": True, "ai": S.router.status()}


@app.get("/api/airport")
def airport():
    return {"airport": cfg.AIRPORT, "runways": cfg.RUNWAYS, "gates": cfg.GATES, "crews": cfg.CREWS,
            "aircraft_types": cfg.AIRCRAFT_TYPES, "timing": cfg.TIMING, "airlines": cfg.AIRLINES,
            "base_clock": cfg.BASE_CLOCK, "adapters": ADAPTERS}


@app.get("/api/flights")
def flights():
    return [f.to_dict() for f in S.flights]


@app.get("/api/scenarios")
def scenarios():
    return [{k: v for k, v in s.items() if k != "build"} for s in SCENARIOS.values()]


@app.get("/api/agents")
def agents():
    return AGENT_META + [
        {"id": "orchestrator", "title": "Operations Orchestrator", "tools": ["dispatch", "merge", "approve"],
         "instructions": "Coordinates specialists, versions the shared plan, resolves conflicts."},
        {"id": "reviewer", "title": "Independent Reviewer", "tools": ["validate_plan"],
         "instructions": "Independently critiques the recommended plan (OpenAI when configured)."}]


@app.get("/api/state")
def state():
    name, sched = _active_schedule()
    inc = S.incident
    return {
        "ai": S.router.status(), "version": S.version, "disruption": S.disruption.to_dict(),
        "schedule_name": name, "schedule": sched, "approved_plan": S.approved_plan,
        "running": bool(S.task and not S.task.done()),
        "incident": None if not inc else {
            "id": inc["id"], "label": inc["label"], "status": inc["status"], "events": inc["events"],
            "plans": [{k: v for k, v in p.items() if k != "schedule"} for p in inc["plans"]],
            "review": inc["review"], "recommendation": inc["recommendation"]},
    }


@app.post("/api/scenarios/{scenario_id}/inject")
async def inject_scenario(scenario_id: str):
    if scenario_id not in SCENARIOS:
        raise HTTPException(404, "unknown scenario")
    s = SCENARIOS[scenario_id]
    db.audit("disruption_injected", {"scenario": scenario_id})
    return await _start(s["build"](), s["name"])


@app.post("/api/disruptions")
async def inject(d: DisruptionIn):
    if d.scenario_id:
        return await inject_scenario(d.scenario_id)
    if not d.type:
        raise HTTPException(422, "type or scenario_id required")
    try:
        dis = build({"type": d.type, "params": d.params})
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))
    db.audit("disruption_injected", {"type": d.type, "params": d.params})
    return await _start(dis, dis.label)


@app.post("/api/events/freetext")
async def freetext(body: FreeTextIn):
    spec, method = await parse(body.text, [f.id for f in S.flights], S.router)
    if not spec:
        return {"accepted": False, "method": method,
                "message": "Could not map this event to a supported disruption type.", "supported": SUPPORTED}
    dis = build(spec)
    db.audit("freetext_event", {"text": body.text, "spec": spec, "method": method})
    res = await _start(dis, f"{dis.label} (from: \"{body.text[:60]}\")")
    return {"accepted": True, "method": method, "spec": spec, **res}


@app.post("/api/adapters/metar")
async def metar(body: MetarIn):
    decoded = parse_metar(body.raw)
    dis = metar_to_disruption(body.raw)
    if dis is None:
        return {"accepted": False, "decoded": decoded, "message": "METAR within normal operating limits."}
    db.audit("metar_event", {"raw": body.raw})
    return {"accepted": True, "decoded": decoded, **(await _start(dis, dis.label))}


@app.get("/api/plans")
def plans():
    if not S.incident:
        return []
    return S.incident["plans"]


@app.post("/api/plans/{plan_id}/approve")
async def approve(plan_id: str, body: DecisionIn):
    inc = S.incident
    if not inc or not inc["plans"]:
        raise HTTPException(404, "no plans to approve")
    p = next((p for p in inc["plans"] if p["id"] == plan_id), None)
    if not p:
        raise HTTPException(404, "unknown plan")
    if not p["feasible"]:
        raise HTTPException(422, "plan failed validation and cannot be approved")
    S.approved_plan, inc["status"] = plan_id, "approved"
    S.version += 1
    db.execute("INSERT INTO approvals (incident, plan_id, decision, note, ts) VALUES (?, ?, ?, ?, ?)",
               (inc["id"], plan_id, "approved", body.note, time.time()))
    db.execute("UPDATE incidents SET status=? WHERE id=?", ("approved", inc["id"]))
    db.audit("plan_approved", {"incident": inc["id"], "plan": plan_id, "note": body.note})
    ev = {"type": "approval", "decision": "approved", "plan_id": plan_id, "plan_name": p["name"],
          "incident": inc["id"], "version": S.version}
    inc["events"].append(ev)
    await hub.broadcast(ev)
    return ev


@app.post("/api/plans/{plan_id}/reject")
async def reject(plan_id: str, body: DecisionIn):
    inc = S.incident
    if not inc:
        raise HTTPException(404, "no incident")
    db.execute("INSERT INTO approvals (incident, plan_id, decision, note, ts) VALUES (?, ?, ?, ?, ?)",
               (inc["id"], plan_id, "rejected", body.note, time.time()))
    db.audit("plan_rejected", {"incident": inc["id"], "plan": plan_id, "note": body.note})
    inc["status"] = "rejected"
    ev = {"type": "approval", "decision": "rejected", "plan_id": plan_id, "incident": inc["id"]}
    inc["events"].append(ev)
    await hub.broadcast(ev)
    return ev


@app.get("/api/schedules/{plan_id}")
def schedule(plan_id: str):
    if plan_id == "nominal":
        return _nominal_schedule()
    if not S.incident:
        raise HTTPException(404, "no incident")
    p = next((p for p in S.incident["plans"] if p["id"] == plan_id), None)
    if not p:
        raise HTTPException(404, "unknown plan")
    return p["schedule"]


@app.get("/api/analytics")
def analytics():
    nominal = compute_metrics(simulate(S.flights, Disruption(), Policy()), Disruption())
    out = {"nominal": nominal, "plans": []}
    if S.incident:
        out["plans"] = [{"id": p["id"], "name": p["name"], "metrics": p["metrics"], "objective": p["objective"],
                         "recommended": p.get("recommended", False), "feasible": p["feasible"]}
                        for p in S.incident["plans"]]
    return out


@app.get("/api/audit")
def audit_log():
    rows = db.query("SELECT ts, action, detail FROM audit_events ORDER BY id DESC LIMIT 100")
    return [{"ts": r[0], "action": r[1], "detail": json.loads(r[2]) if r[2].startswith("{") else r[2]} for r in rows]


@app.post("/api/reset")
async def reset():
    if S.task and not S.task.done():
        S.task.cancel()
    S.reset()
    db.audit("reset", {})
    await hub.broadcast({"type": "reset"})
    return {"ok": True}


@app.websocket("/ws/operations")
async def ws_ops(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "ai": S.router.status()}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.clients.discard(ws)


# ------------------------------------------------------------------ serverless (stateless) mode
class RunIn(BaseModel):
    scenario_id: Optional[str] = None
    type: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None
    metar: Optional[str] = None


async def _resolve(body: RunIn) -> tuple[Disruption, str, dict]:
    if body.scenario_id:
        if body.scenario_id not in SCENARIOS:
            raise HTTPException(404, "unknown scenario")
        s = SCENARIOS[body.scenario_id]
        return s["build"](), s["name"], {}
    if body.text:
        spec, method = await parse(body.text, [f.id for f in S.flights], S.router)
        if not spec:
            raise HTTPException(422, "Could not map this event to a supported disruption type.")
        d = build(spec)
        return d, f"{d.label} (from: \"{body.text[:60]}\")", {"spec": spec, "method": method}
    if body.metar:
        d = metar_to_disruption(body.metar)
        if d is None:
            raise HTTPException(422, "METAR within normal operating limits.")
        return d, d.label, {"decoded": parse_metar(body.metar)}
    if body.type:
        try:
            d = build({"type": body.type, "params": body.params})
        except (ValueError, KeyError) as e:
            raise HTTPException(422, str(e))
        return d, d.label, {}
    raise HTTPException(422, "scenario_id, type, text or metar required")


@app.post("/api/preview")
async def preview(body: RunIn):
    """Fast: the disruption and the unmitigated baseline schedule, so the twin can start playing."""
    d, label, extra = await _resolve(body)
    return {"disruption": d.to_dict(), "label": label,
            "schedule": [r.to_dict() for r in simulate(S.flights, d, Policy())], **extra}


@app.post("/api/run")
async def run_stateless(body: RunIn):
    """Runs the full agent incident in one request and returns the complete, real event log."""
    d, label, extra = await _resolve(body)
    events: list[dict] = []

    async def collect(ev: dict) -> None:
        ev["ts"] = time.time()
        if ev.get("type") == "tool_call" and ev.get("tool") == "explore_plans":
            r = dict(ev["result"]); r["top"] = r.get("top", [])[:3]; ev["result"] = r
        events.append(ev)

    orch = Orchestrator(S.flights, d, collect, S.router, pace=0)
    db.audit("serverless_incident", {"incident": orch.incident_id, "label": label})
    out = await orch.run()
    return {"incident": orch.incident_id, "label": label, "disruption": d.to_dict(), "events": events,
            "plans": out["plans"], "review": out["review"], "recommendation": out["recommendation"],
            "ai": S.router.status(), **extra}


# ------------------------------------------------------------------ static frontend
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
