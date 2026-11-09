"""Specialist agents.

Every agent has its own instructions, its own tool allow-list and returns the same
structured output. An agent's "brain" is either:
  * LLMBrain  - Claude with tool use (live AI mode), or
  * its deterministic policy method (offline mode, or automatic fallback on API failure).
Both brains call the same deterministic tools, and all tool calls are logged.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

from ..ai.base import ProviderUnavailable, extract_json
from ..ai.claude_client import ClaudeClient
from .tools import LEVERS, TOOLS, Workspace, call_tool, hhmm

Emit = Callable[[dict], Awaitable[None]]

OUTPUT_SCHEMA = """Return ONLY a JSON object:
{"findings": [string], "proposed_actions": [{"lever": string, "value": any, "reason": string}],
 "evidence": object, "uncertainty": "low|medium|high", "constraints": [string], "message": string}
Levers you may propose: sequencing (fifo|priority), arrival_protection (none|fuel|all),
gate_policy (fixed|reallocate), use_remote_stands (true|false), crew_policy (zone|pooled),
gate_aware (true|false). Use only numbers returned by tools. Never invent flights or values.
This is a simulated planning tool, not certified air traffic control."""


def agent_output(agent: str, task_id: str, findings: list, actions: list, evidence: dict,
                 uncertainty: str = "low", constraints: Optional[list] = None, message: str = "",
                 status: str = "completed", brain: str = "deterministic") -> dict:
    return {"agent": agent, "task_id": task_id, "findings": findings, "proposed_actions": actions,
            "evidence": evidence, "uncertainty": uncertainty, "constraints": constraints or [],
            "status": status, "message": message, "brain": brain}


def clean_actions(actions: list) -> list:
    ok = []
    for a in actions or []:
        lv, val = a.get("lever"), a.get("value")
        if lv in LEVERS and val in LEVERS[lv]:
            ok.append({"lever": lv, "value": val, "reason": str(a.get("reason", ""))[:300]})
    return ok


class Agent:
    name = "agent"
    title = "Agent"
    instructions = ""
    tools: list[str] = []

    def __init__(self, ws: Workspace, emit: Emit, client: Optional[ClaudeClient] = None):
        self.ws, self.emit, self.client = ws, emit, client

    # -- tool invocation (logged)
    async def tool(self, name: str, args: Optional[dict] = None) -> dict:
        if name not in self.tools:
            raise PermissionError(f"{self.name} may not call {name}")
        t0 = time.perf_counter()
        result = await asyncio.to_thread(call_tool, self.ws, name, args or {})
        await self.emit({"type": "tool_call", "agent": self.name, "tool": name, "args": args or {},
                         "result": result, "ms": int((time.perf_counter() - t0) * 1000)})
        return result

    async def status(self, s: str, note: str = "") -> None:
        await self.emit({"type": "agent_status", "agent": self.name, "status": s, "note": note})

    async def run(self, task: str, payload: Optional[dict] = None) -> dict:
        task_id = f"T-{uuid.uuid4().hex[:6].upper()}"
        await self.status("working", task)
        out = None
        if self.client is not None and self.client.available():
            try:
                out = await self.llm_think(task, task_id, payload or {})
            except (ProviderUnavailable, ValueError, KeyError, json.JSONDecodeError) as e:
                await self.emit({"type": "message", "from": self.name, "to": "orchestrator", "kind": "fallback",
                                 "text": f"Model unavailable ({str(e)[:80]}). Switching to deterministic policy."})
        if out is None:
            out = await self.think(task, task_id, payload or {})
        await self.status("conflict" if out["status"] == "conflict" else "completed")
        return out

    # -- live AI brain
    async def llm_think(self, task: str, task_id: str, payload: dict) -> dict:
        system = (f"You are the {self.title} in SkyOps Twin, a multi-agent airport disruption recovery "
                  f"system running on a synthetic airport. {self.instructions}\n{OUTPUT_SCHEMA}")
        ctx = {"task": task, "shared_state_version": self.ws.version, "agreed_levers": self.ws.candidate,
               **payload}
        messages: list[dict] = [{"role": "user", "content": json.dumps(ctx, default=str)}]
        specs = ClaudeClient.tool_specs(TOOLS, self.tools)
        for _ in range(5):
            turn = await self.client.turn(system, messages, specs, max_tokens=1500)
            if not turn.tool_calls:
                data = extract_json(turn.text)
                return agent_output(self.name, task_id, list(data.get("findings", []))[:6],
                                    clean_actions(data.get("proposed_actions", [])),
                                    data.get("evidence", {}), data.get("uncertainty", "medium"),
                                    data.get("constraints", []), data.get("message", ""),
                                    brain=f"claude:{turn.model}")
            messages.append(ClaudeClient.assistant_message(turn))
            results = []
            for tc in turn.tool_calls:
                if tc.name not in self.tools:
                    results.append((tc.id, json.dumps({"error": "tool not permitted"})))
                    continue
                res = await self.tool(tc.name, tc.args)
                results.append((tc.id, json.dumps(res, default=str)[:6000]))
            messages.append(ClaudeClient.tool_results_message(results))
        raise ValueError("agent exceeded tool-call budget")

    # -- deterministic brain (overridden)
    async def think(self, task: str, task_id: str, payload: dict) -> dict:
        raise NotImplementedError


# ============================================================================ specialists
class WeatherAgent(Agent):
    name, title = "weather", "Weather Agent"
    instructions = "Interpret the weather event and state its operational restrictions and time window."
    tools = ["get_weather_impact"]

    async def think(self, task, task_id, payload):
        w = await self.tool("get_weather_impact")
        f = []
        if w["visibility_m"]:
            f.append(f"Visibility {w['visibility_m']} m, crosswind {w['wind_kt']} kt, window {w['window']}.")
        for c in w["runway_closures"]:
            f.append(f"Runway {c['runway']} unavailable {c['window']}.")
        for o in w["capacity_limits"]:
            f.append(f"Runway {o['runway']} limited to {o['capacity_per_hour']} movements/h {o['window']}.")
        if w["turnaround_factor"] > 1:
            f.append(f"Ground handling slowed: turnarounds x{w['turnaround_factor']:.1f} during the event.")
        if w["gate_closures"]:
            f.append("Gates closed: " + ", ".join(g["gate"] for g in w["gate_closures"]) + ".")
        if w["crews_unavailable"]:
            f.append("Crews stood down: " + ", ".join(w["crews_unavailable"]) + ".")
        return agent_output(self.name, task_id, f or ["No weather restrictions active."], [], w,
                            "medium", ["Weather parameters are synthetic scenario inputs."],
                            "Restrictions published to Runway, Gate and Ground agents.")


class RunwayAgent(Agent):
    name, title = "runway", "Runway Agent"
    instructions = ("Own runway availability and capacity. Quantify demand vs capacity, predict airborne "
                    "holding against the fuel limit, and protect arrivals at risk of diversion.")
    tools = ["runway_capacity_profile", "predict_airborne_holds", "simulate_plan"]

    async def think(self, task, task_id, payload):
        levers = payload.get("levers")
        if levers is None:
            prof = await self.tool("runway_capacity_profile")
            over = [b for b in prof["buckets"] if b["overload"] > 0]
            holds = await self.tool("predict_airborne_holds", {"levers": {}})
            f = []
            if over:
                f.append(f"Demand exceeds capacity in {len(over)} half-hour windows, worst "
                         f"{max(over, key=lambda b: b['overload'])['window']} "
                         f"(+{max(b['overload'] for b in over)} movements).")
            f.append(f"Baseline max airborne hold {holds['max_hold_min']} min vs fuel limit "
                     f"{holds['fuel_hold_limit_min']} min: {holds['diversions']} diversion(s), "
                     f"{holds['diverted_pax']} passengers.")
            actions = []
            if holds["diversions"] or holds["flights_near_fuel_limit"]:
                names = ", ".join(x["flight"] for x in holds["flights_near_fuel_limit"][:4])
                actions.append({"lever": "arrival_protection", "value": "fuel",
                                "reason": f"Give landing priority to arrivals near the fuel limit ({names})."})
            return agent_output(self.name, task_id, f, actions, {"capacity": prof, "holds": holds},
                                "low", ["Single-runway operation during the event."],
                                "Recommend fuel-aware arrival protection." if actions else "No diversion risk.")
        # reassessment against the agreed plan
        holds = await self.tool("predict_airborne_holds", {"levers": levers})
        if holds["diversions"] == 0:
            return agent_output(self.name, task_id,
                                [f"Agreed plan: max hold {holds['max_hold_min']} min, no diversions."], [],
                                holds, "low", [], "Runway sequence accepted.")
        stronger = {**levers, "arrival_protection": "all"}
        sim = await self.tool("simulate_plan", {"levers": stronger})
        acts = []
        if sim["metrics"]["diversions"] < holds["diversions"]:
            acts.append({"lever": "arrival_protection", "value": "all",
                         "reason": f"Fuel protection still leaves {holds['diversions']} diversion(s); "
                                   f"protecting all arrivals gives {sim['metrics']['diversions']}."})
        return agent_output(self.name, task_id,
                            [f"Agreed plan still diverts {holds['diversions']} flight(s)."], acts,
                            {"holds": holds, "alternative": sim["metrics"]}, "medium", [],
                            "Escalating arrival protection." if acts else "Cannot remove remaining diversions.",
                            status="conflict" if acts else "completed")


class FlightAgent(Agent):
    name, title = "flight", "Flight Agent"
    instructions = ("Own the flight schedule. Identify affected flights, passengers and connections; "
                    "propose sequencing; revise it when other agents report conflicts.")
    tools = ["affected_flights", "priority_ranking", "simulate_plan"]

    async def think(self, task, task_id, payload):
        if payload.get("conflict"):
            levers = payload["levers"]
            a = await self.tool("simulate_plan", {"levers": {**levers, "gate_aware": False}})
            b = await self.tool("simulate_plan", {"levers": {**levers, "gate_aware": True}})
            better = b["objective"] < a["objective"]
            f = [f"Gate-aware re-sequencing: objective {a['objective']} -> {b['objective']}, "
                 f"apron holds {a['metrics']['apron_holds']} -> {b['metrics']['apron_holds']}."]
            acts = [{"lever": "gate_aware", "value": True,
                     "reason": "Land aircraft whose gate is not yet free after those whose gate is ready."}] if better else []
            return agent_output(self.name, task_id, f, acts, {"without": a["metrics"], "with": b["metrics"]},
                                "low", [], "Schedule revised around gate availability." if better
                                else "Re-sequencing does not help; keeping current order.")
        aff = await self.tool("affected_flights", {"levers": {}})
        pr = await self.tool("priority_ranking")
        f = [f"Baseline: {aff['delayed_flights']} delayed, {aff['diversions']} diverted, "
             f"{aff['passenger_delay_hours']} passenger-delay hours, {aff['connections_at_risk']} connections at risk."]
        if aff["worst"]:
            w = aff["worst"][0]
            f.append(f"Worst hit: {w['flight']} ({w['aircraft']}, {w['pax']} pax) "
                     + ("diverts." if w["diverted"] else f"+{w['dep_delay_min']} min."))
        top = ", ".join(x["flight"] for x in pr["top"][:3])
        acts = [{"lever": "sequencing", "value": "priority",
                 "reason": f"Sequence by passengers and connections; highest priority {top}."}]
        return agent_output(self.name, task_id, f, acts, {"affected": aff, "priority": pr}, "low",
                            ["Priority weights are synthetic and configurable."],
                            "Proposing passenger-weighted sequencing.")


class GateAgent(Agent):
    name, title = "gate", "Gate Agent"
    instructions = ("Own gates and stands. Detect closed gates, double bookings and aircraft waiting for a "
                    "gate; reallocate by aircraft size; report conflicts with the proposed schedule.")
    tools = ["gate_conflicts", "simulate_plan"]

    async def think(self, task, task_id, payload):
        levers = payload.get("levers")
        g = await self.tool("gate_conflicts", {"levers": levers or {}})
        if levers is None:
            f = [f"Closed gates: {', '.join(g['closed_gates']) or 'none'}.",
                 f"Baseline keeps planned gates: {g['apron_holds']} aircraft wait on the apron, "
                 f"{g['apron_wait_min']} min in total."]
            if g["aircraft_waiting_for_gate"]:
                w = g["aircraft_waiting_for_gate"][0]
                f.append(f"Worst: {w['flight']} ({w['aircraft']}) waits {w['wait_min']} min for {w['planned_gate']}.")
            acts = [{"lever": "gate_policy", "value": "reallocate",
                     "reason": "Move aircraft to any free size-compatible gate instead of waiting."}]
            test = await self.tool("simulate_plan", {"levers": {"gate_policy": "reallocate", "use_remote_stands": True}})
            if test["metrics"]["remote_stand_turns"] > 0:
                acts.append({"lever": "use_remote_stands", "value": True,
                             "reason": f"Open remote stands R1-R4 ({test['metrics']['remote_stand_turns']} turns) to relieve the contact pier."})
            return agent_output(self.name, task_id, f, acts, g, "low",
                                ["Code F (A380) only at A1-A3.", "5-min buffer between aircraft on a gate."],
                                "Proposing dynamic gate reallocation.")
        # conflict check against the agreed plan
        worst = max((x["wait_min"] for x in g["aircraft_waiting_for_gate"]), default=0.0)
        if g["apron_holds"] > 2 and (not levers.get("gate_aware") or worst > 15):
            w = g["aircraft_waiting_for_gate"][:3]
            names = ", ".join(f"{x['flight']} {x['wait_min']}m" for x in w)
            return agent_output(self.name, task_id,
                                [f"Conflict: proposed sequence lands {g['apron_holds']} aircraft before a gate is free "
                                 f"({g['apron_wait_min']} min apron wait). {names}."],
                                [], g, "low", [], "Requesting Flight Agent to re-sequence around gate availability.",
                                status="conflict")
        return agent_output(self.name, task_id,
                            [f"No blocking gate conflicts (longest apron hold {worst} min): {g['gate_changes']} gate changes, "
                             f"{g['remote_stand_turns']} remote-stand turns, {g['apron_holds']} short apron holds."],
                            [], g, "low", [], "Gate plan accepted.")


class GroundOpsAgent(Agent):
    name, title = "ground", "Ground Operations Agent"
    instructions = ("Own ground handling crews. Detect crew shortages and bottlenecks; propose crew "
                    "rebalancing and withdraw proposals that the simulation shows to be harmful.")
    tools = ["crew_load", "simulate_plan"]

    async def think(self, task, task_id, payload):
        levers = payload.get("levers")
        c = await self.tool("crew_load", {"levers": levers or {}})
        sat = [z for z, v in c["zones"].items() if v["saturated"]]
        if levers is None:
            f = [f"Zone {z}: {v['peak_concurrent_turnarounds']}/{v['crews']} crews busy at peak"
                 + (" - SATURATED." if v["saturated"] else ".") for z, v in c["zones"].items() if v["crews"]]
            acts = []
            if sat or c["unavailable"]:
                acts.append({"lever": "crew_policy", "value": "pooled",
                             "reason": f"Pool crews across zones (zones saturated: {', '.join(sat) or 'none'}; "
                                       f"stood down: {', '.join(c['unavailable']) or 'none'})."})
            return agent_output(self.name, task_id, f, acts, c, "medium",
                                ["Cross-zone transfer adds 6 min per turnaround (synthetic)."],
                                "Proposing crew pooling." if acts else "Crew capacity sufficient.")
        if levers.get("crew_policy") != "pooled":
            return agent_output(self.name, task_id, ["Zone crews cover the agreed plan."], [], c, "low", [],
                                "Crew plan accepted.")
        a = await self.tool("simulate_plan", {"levers": {**levers, "crew_policy": "zone"}})
        b = await self.tool("simulate_plan", {"levers": levers})
        if a["objective"] < b["objective"]:
            return agent_output(self.name, task_id,
                                [f"Pooling causes {c['cross_zone_assignments']} cross-zone transfers; objective "
                                 f"{b['objective']} pooled vs {a['objective']} zone crews."],
                                [{"lever": "crew_policy", "value": "zone",
                                  "reason": "Withdrawing pooling: transfer time costs more than it saves once gates are reallocated."}],
                                {"pooled": b["metrics"], "zone": a["metrics"]}, "low", [],
                                "Withdrawing my crew-pooling proposal.", status="conflict")
        return agent_output(self.name, task_id, [f"Pooling confirmed: objective {b['objective']} vs {a['objective']}."],
                            [], {"pooled": b["metrics"], "zone": a["metrics"]}, "low", [], "Crew pooling confirmed.")


class RecoveryAgent(Agent):
    name, title = "recovery", "Recovery Agent"
    instructions = ("Build alternative recovery plans, simulate and validate each, and rank them by the "
                    "recovery objective. Recommend the best feasible plan.")
    tools = ["simulate_plan", "explore_plans"]

    async def think(self, task, task_id, payload):
        agreed = payload["levers"]
        base = await self.tool("simulate_plan", {"levers": {}})
        neg = await self.tool("simulate_plan", {"levers": agreed})
        search = await self.tool("explore_plans")
        best = search["top"][0]
        f = [f"Negotiated plan objective {neg['objective']} vs baseline {base['objective']}.",
             f"Searched {search['evaluated']} lever combinations, {search['feasible']} feasible; "
             f"best objective {best['objective']}."]
        diff = {k: v for k, v in best["levers"].items() if agreed.get(k, LEVERS[k][0]) != v}
        if diff and best["objective"] < neg["objective"]:
            f.append("Search improves on the negotiated plan by changing: "
                     + ", ".join(f"{k}={v}" for k, v in diff.items()) + ".")
        return agent_output(self.name, task_id, f, [], {"baseline": base, "negotiated": neg, "search": search},
                            "low", ["Objective weights are synthetic and configurable."],
                            "Plans ranked; recommending the best feasible plan.")


AGENT_CLASSES = [WeatherAgent, RunwayAgent, FlightAgent, GateAgent, GroundOpsAgent, RecoveryAgent]
AGENT_META = [{"id": c.name, "title": c.title, "instructions": c.instructions, "tools": c.tools}
              for c in AGENT_CLASSES]
