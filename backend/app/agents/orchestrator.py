"""Operations Orchestrator: task-based coordination loop over the specialist agents.

LLMs propose, Python disposes: specialists propose recovery levers, the orchestrator
merges them into a versioned shared plan, specialists re-check it and raise conflicts,
the Recovery agent searches and validates alternatives, an independent reviewer
critiques the result, and a human controller approves or rejects.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Awaitable, Callable, Optional

from ..ai.base import ProviderUnavailable, extract_json
from ..ai.router import ModelRouter
from ..simulation.config import TIMING
from ..simulation.engine import Disruption
from ..simulation.flights import Flight
from ..simulation.metrics import objective
from .agents import (FlightAgent, GateAgent, GroundOpsAgent, RecoveryAgent, RunwayAgent, WeatherAgent)
from .tools import LEVERS, Workspace, call_tool, hhmm

Emit = Callable[[dict], Awaitable[None]]
MAX_ITERATIONS = 4

LEVER_LABELS = {
    "sequencing": {"fifo": "First-come-first-served", "priority": "Passenger-weighted sequencing"},
    "arrival_protection": {"none": "No arrival protection", "fuel": "Fuel-aware arrival protection",
                           "all": "Arrivals before departures"},
    "gate_policy": {"fixed": "Planned gates", "reallocate": "Dynamic gate reallocation"},
    "use_remote_stands": {False: "Contact gates only", True: "Remote stands open"},
    "crew_policy": {"zone": "Zone crews", "pooled": "Pooled crews"},
    "gate_aware": {False: "", True: "Gate-aware re-sequencing"},
}


def describe(levers: dict) -> list[str]:
    out = []
    for k, v in levers.items():
        lab = LEVER_LABELS.get(k, {}).get(v)
        if lab:
            out.append(lab)
    return out


def plan_actions(ws: Workspace, levers: dict) -> list[dict]:
    """Concrete operational actions: the diff between the plan and the baseline response."""
    base, _ = ws.run({})
    plan, _ = ws.run(levers)
    b = {r.id: r for r in base}
    acts = []
    for r in sorted(plan, key=lambda r: r.sta):
        o = b[r.id]
        if o.diverted and not r.diverted:
            acts.append({"kind": "diversion_avoided", "flight": r.id,
                         "text": f"{r.id} protected: lands {hhmm(r.land)} on {r.arr_runway} (baseline diverts, {r.pax} pax)"})
        if r.gate and r.planned_gate and r.gate != r.planned_gate:
            kind = "remote_stand" if r.gate_kind == "remote" else "gate_change"
            acts.append({"kind": kind, "flight": r.id,
                         "text": f"{r.id} {r.aircraft}: {r.planned_gate} -> {r.gate}"
                                 + (" (remote stand, bussing)" if kind == "remote_stand" else "")})
        if r.land is not None and o.land is not None and r.land < o.land - 3:
            acts.append({"kind": "resequence", "flight": r.id,
                         "text": f"{r.id} lands {hhmm(r.land)} instead of {hhmm(o.land)} ({round(o.land - r.land)} min earlier)"})
    return acts


def plan_record(ws: Workspace, pid: str, name: str, levers: dict, source: str) -> dict:
    res, m = ws.run(levers)
    from ..simulation.validator import validate
    v = validate(res, ws.disruption)
    return {"id": pid, "name": name, "source": source, "levers": levers, "lever_labels": describe(levers),
            "metrics": m, "objective": objective(m), "feasible": not v, "violations": v,
            "schedule": [r.to_dict() for r in res],
            "actions": plan_actions(ws, levers) if levers else []}


class Orchestrator:
    name = "orchestrator"

    def __init__(self, flights: list[Flight], disruption: Disruption, emit: Emit,
                 router: Optional[ModelRouter] = None, pace: Optional[float] = None):
        self.ws = Workspace(flights=flights, disruption=disruption)
        self.router = router or ModelRouter()
        default_pace = "0.15" if self.router.claude_enabled() else "0.55"  # live models add their own latency
        self.pace = float(os.getenv("SKYOPS_DEMO_PACE", default_pace)) if pace is None else pace
        self.incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        self._emit_raw = emit
        client = self.router.specialist if self.router.claude_enabled() else None
        mk = lambda cls: cls(self.ws, self.emit, client)
        self.weather, self.runway, self.flight = mk(WeatherAgent), mk(RunwayAgent), mk(FlightAgent)
        self.gate, self.ground, self.recovery = mk(GateAgent), mk(GroundOpsAgent), mk(RecoveryAgent)
        self.iteration = 0

    async def emit(self, ev: dict) -> None:
        ev.setdefault("incident", self.incident_id)
        ev.setdefault("iteration", self.iteration)
        ev.setdefault("state_version", self.ws.version)
        await self._emit_raw(ev)
        if ev["type"] in ("message", "agent_status", "conflict") and self.pace:
            await asyncio.sleep(self.pace)
        elif ev["type"] == "tool_call" and self.pace:
            await asyncio.sleep(self.pace * 0.5)

    async def say(self, to: str, text: str, kind: str = "task", frm: str = "orchestrator", data=None):
        await self.emit({"type": "message", "from": frm, "to": to, "kind": kind, "text": text, "data": data})

    async def report(self, out: dict, to: str = "orchestrator"):
        kind = "conflict" if out["status"] == "conflict" else ("proposal" if out["proposed_actions"] else "finding")
        await self.emit({"type": "message", "from": out["agent"], "to": to, "kind": kind,
                         "text": out["message"], "findings": out["findings"], "output": out})

    def adopt(self, actions: list[dict]) -> list[dict]:
        changed = []
        for a in actions:
            if self.ws.candidate.get(a["lever"]) != a["value"]:
                self.ws.candidate[a["lever"]] = a["value"]
                changed.append(a)
        return changed

    async def brief(self, prompt: str, fallback: str) -> str:
        """Orchestrator narration via Claude when available; deterministic text otherwise."""
        if not self.router.claude_enabled():
            return fallback
        try:
            turn = await self.router.orchestrator.turn(
                "You are the Operations Orchestrator of SkyOps Twin, a simulated airport recovery system. "
                "Write 2-3 crisp sentences for an airport operations controller. Use only the numbers given.",
                [{"role": "user", "content": prompt}], max_tokens=300)
            return turn.text.strip() or fallback
        except ProviderUnavailable:
            return fallback

    # ------------------------------------------------------------------ main loop
    async def run(self) -> dict:
        d = self.ws.disruption
        await self.emit({"type": "incident", "status": "open", "disruption": d.to_dict(),
                         "ai": self.router.status()})
        await self.emit({"type": "agent_status", "agent": "orchestrator", "status": "working",
                         "note": "Incident opened"})
        await self.say("all", f"Incident {self.incident_id} opened: {d.label}. Weather Agent, assess the event.")

        # Phase 1: weather -> runway (sequential: runway depends on weather)
        w = await self.weather.run("Assess the weather event and publish restrictions.")
        await self.report(w)
        await self.say("runway", "Runway Agent: quantify capacity loss and diversion risk.")
        r = await self.runway.run("Assess runway capacity and airborne holding.")
        await self.report(r)

        # Phase 2: parallel impact assessment
        await self.say("flight,gate,ground", "Flight, Gate and Ground agents: assess impact in parallel.")
        f, g, gr = await asyncio.gather(
            self.flight.run("Identify affected flights and propose sequencing."),
            self.gate.run("Identify gate conflicts and propose reallocation."),
            self.ground.run("Identify ground crew shortages."))
        for out in (f, g, gr):
            await self.report(out)
        proposals = r["proposed_actions"] + f["proposed_actions"] + g["proposed_actions"] + gr["proposed_actions"]
        self.adopt(proposals)
        self.ws.bump()
        await self.emit({"type": "state_version", "candidate": dict(self.ws.candidate),
                         "labels": describe(self.ws.candidate), "reason": "Merged specialist proposals"})
        await self.say("all", "Draft plan v%d: %s. All agents: re-check against your constraints."
                       % (self.ws.version, "; ".join(describe(self.ws.candidate))))

        # Phase 3: conflict / re-plan loop
        for self.iteration in range(1, MAX_ITERATIONS + 1):
            levers = dict(self.ws.candidate)
            g2, gr2, r2 = await asyncio.gather(
                self.gate.run("Check the draft plan for gate conflicts.", {"levers": levers}),
                self.ground.run("Check the draft plan for crew bottlenecks.", {"levers": levers}),
                self.runway.run("Check the draft plan for diversion risk.", {"levers": levers}))
            changes = []
            for out in (g2, gr2, r2):
                await self.report(out)
            if g2["status"] == "conflict":
                await self.emit({"type": "conflict", "between": ["gate", "flight"], "text": g2["findings"][0]})
                await self.say("flight", "Gate Agent reports a conflict with your sequence. Re-plan around gate availability.",
                               kind="reassess", frm="gate")
                await self.flight.status("replanning")
                f2 = await self.flight.run("Revise the sequence around gate availability.",
                                           {"levers": levers, "conflict": g2["findings"]})
                await self.report(f2)
                changes += self.adopt(f2["proposed_actions"])
            changes += self.adopt(gr2["proposed_actions"]) + self.adopt(r2["proposed_actions"])
            if not changes:
                await self.say("all", f"Iteration {self.iteration}: no open conflicts. Plan v{self.ws.version} agreed.",
                               kind="decision")
                break
            self.ws.bump()
            await self.emit({"type": "state_version", "candidate": dict(self.ws.candidate),
                             "labels": describe(self.ws.candidate),
                             "reason": "; ".join(c["reason"] for c in changes)[:300]})
            await self.say("all", f"Plan v{self.ws.version}: " + "; ".join(describe(self.ws.candidate))
                           + ". Re-checking.", kind="decision")

        # Phase 4: recovery search and ranking
        self.iteration = 0
        await self.say("recovery", "Recovery Agent: simulate alternatives against the baseline and rank them.")
        await self.emit({"type": "search", "status": "running", "text": "Simulating and validating 72 recovery lever combinations"})
        rec = await self.recovery.run("Rank recovery plans.", {"levers": dict(self.ws.candidate)})
        await self.emit({"type": "search", "status": "done"})
        await self.report(rec)
        plans = self.build_plans(rec)
        await self.emit({"type": "plans", "plans": [{k: v for k, v in p.items() if k != "schedule"} for p in plans]})

        # Phase 5: independent review
        recommended = next(p for p in plans if p.get("recommended"))
        review = await self.review(plans, recommended)
        await self.emit({"type": "review", **review})

        # Phase 6: recommendation
        base = next(p for p in plans if p["id"] == "baseline")["metrics"]
        m = recommended["metrics"]
        fallback = (f"Recommend {recommended['name']}: diversions {base['diversions']} -> {m['diversions']}, "
                    f"passenger-delay hours {base['passenger_delay_hours']} -> {m['passenger_delay_hours']}, "
                    f"connections at risk {base['connections_at_risk']} -> {m['connections_at_risk']}. "
                    f"All hard constraints pass. Awaiting controller approval.")
        text = await self.brief(json.dumps({"baseline": base, "recommended": m,
                                            "levers": recommended["lever_labels"], "review": review["summary"]}),
                                fallback)
        await self.emit({"type": "agent_status", "agent": "orchestrator", "status": "completed"})
        await self.emit({"type": "recommendation", "plan_id": recommended["id"], "text": text,
                         "requires_approval": True})
        return {"incident": self.incident_id, "plans": plans, "review": review, "recommendation": text}

    # ------------------------------------------------------------------ plans
    def build_plans(self, rec: dict) -> list[dict]:
        ws = self.ws
        search = rec["evidence"]["search"]["top"]
        plans = [plan_record(ws, "baseline", "Baseline response", {}, "Standard procedures (FCFS, planned gates)")]
        negotiated = plan_record(ws, "plan-a", "Plan A - negotiated", dict(ws.candidate), "Agent negotiation")
        plans.append(negotiated)
        seen = {json.dumps(negotiated["levers"], sort_keys=True)}
        letter = iter("BCD")
        for top in search:
            key = json.dumps(top["levers"], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            L = next(letter, None)
            if not L:
                break
            plans.append(plan_record(ws, f"plan-{L.lower()}", f"Plan {L} - search", top["levers"],
                                     "Recovery Agent search"))
            if len(plans) >= 4:
                break
        feas = [p for p in plans if p["feasible"] and p["id"] != "baseline"]
        best = min(feas, key=lambda p: p["objective"])
        best["recommended"] = True
        return plans

    # ------------------------------------------------------------------ review
    async def review(self, plans: list[dict], rec: dict) -> dict:
        await self.emit({"type": "agent_status", "agent": "reviewer", "status": "working",
                         "note": "Independent review"})
        check = await asyncio.to_thread(call_tool, self.ws, "validate_plan", {"levers": rec["levers"]})
        await self.emit({"type": "tool_call", "agent": "reviewer", "tool": "validate_plan",
                         "args": {"levers": rec["levers"]}, "result": check, "ms": 0})
        alts = [p for p in plans if p["id"] not in ("baseline", rec["id"]) and p["feasible"]]
        # the reviewer applies its own passenger-centric criterion: protect connections first
        fewest = min([rec] + alts, key=lambda p: (p["metrics"]["connections_at_risk"] + 0 * p["objective"],
                                                  p["metrics"]["passenger_delay_hours"]))
        review = None
        if self.router.openai_enabled():
            try:
                review = await self._openai_review(rec, alts, check)
            except (ProviderUnavailable, ValueError, KeyError):
                await self.say("orchestrator", "OpenAI reviewer unavailable, using deterministic reviewer.",
                               kind="fallback", frm="reviewer")
        if review is None:
            review = self._deterministic_review(rec, fewest, check)
        review["python_validation"] = {"feasible": check["feasible"], "violations": check["violations"],
                                       "checks": check["checks"]}
        if review.get("disagreement"):
            await self.emit({"type": "conflict", "between": ["reviewer", "recovery"], "text": review["disagreement"]})
            review["escalated_to_human"] = True
        await self.emit({"type": "message", "from": "reviewer", "to": "orchestrator",
                         "kind": "conflict" if review.get("disagreement") else "finding",
                         "text": review["summary"], "findings": review["findings"],
                         "output": {"brain": review["reviewer"]}})
        await self.emit({"type": "agent_status", "agent": "reviewer", "status": "completed"})
        return review

    def _deterministic_review(self, rec: dict, fewest: dict, check: dict) -> dict:
        m = rec["metrics"]
        findings = [f"Python validation: {'all hard constraints pass' if check['feasible'] else str(len(check['violations'])) + ' violations'} "
                    f"({len(check['checks'])} rule families)."]
        if check["count_worse"]:
            w = check["flights_worse_than_baseline"][0]
            findings.append(f"{check['count_worse']} flights are worse off than in the baseline; largest "
                            f"{w['flight']} {w['baseline_delay']} -> {w['plan_delay']} min.")
        if check["remote_stand_pax"]:
            findings.append(f"{check['remote_stand_pax']} passengers bussed from remote stands.")
        findings.append(f"Maximum departure delay in plan: {check['max_delay_min']} min.")
        disagreement = None
        if fewest["id"] != rec["id"]:
            fm = fewest["metrics"]
            disagreement = (f"Reviewer prefers {fewest['name']}: it protects more connections "
                            f"({fm['connections_at_risk']} vs {m['connections_at_risk']} at risk) but disrupts "
                            f"{fm['disrupted_flights']} flights vs {m['disrupted_flights']}. Recovery Agent prefers "
                            f"{rec['name']} on the overall objective ({rec['objective']} vs {fewest['objective']}). "
                            f"Both pass Python validation: trade-off escalated to the controller.")
        return {"reviewer": "deterministic", "verdict": "approve_with_notes" if check["feasible"] else "reject",
                "summary": "Plan is feasible under all modelled constraints." if check["feasible"]
                else "Plan violates hard constraints.", "findings": findings, "disagreement": disagreement,
                "alternative": fewest["id"] if disagreement else None}

    async def _openai_review(self, rec: dict, alts: list[dict], check: dict) -> dict:
        system = ("You are an independent airport operations plan reviewer. Critically review a recovery plan "
                  "proposed by another AI system for a SIMULATED airport. Use only the evidence provided. "
                  "Return JSON: {\"verdict\": \"approve|approve_with_notes|reject\", \"summary\": string, "
                  "\"findings\": [string], \"disagreement\": string|null, \"alternative\": string|null}.")
        evidence = {"recommended": {k: rec[k] for k in ("id", "name", "lever_labels", "metrics", "objective")},
                    "alternatives": [{k: a[k] for k in ("id", "name", "lever_labels", "metrics", "objective")} for a in alts],
                    "python_validation": check}
        turn = await self.router.reviewer.turn(system, [{"role": "user", "content": json.dumps(evidence, default=str)}])
        data = extract_json(turn.text)
        return {"reviewer": f"openai:{turn.model}", "verdict": data.get("verdict", "approve_with_notes"),
                "summary": data.get("summary", ""), "findings": list(data.get("findings", []))[:6],
                "disagreement": data.get("disagreement"), "alternative": data.get("alternative")}
