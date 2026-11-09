"""Agent brains: live-AI tool loop (with a fake model), provider failure fallback, conflicting proposals."""
import asyncio
import json

from app.agents.agents import GateAgent, RunwayAgent, clean_actions
from app.agents.orchestrator import Orchestrator
from app.agents.tools import Workspace
from app.ai.base import ModelTurn, ProviderUnavailable, ToolCall
from app.ai.router import ModelRouter
from app.simulation.engine import assign_planned_gates
from app.simulation.flights import build_flights
from app.simulation.scenarios import operation_sandstorm


class FakeClaude:
    model = "fake-claude"

    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    async def turn(self, system, messages, tools=None, max_tokens=1200):
        self.calls += 1
        if self.calls == 1:
            return ModelTurn(tool_calls=[ToolCall("tu_1", "gate_conflicts", {"levers": {}})],
                             raw={"content": [{"type": "tool_use", "id": "tu_1", "name": "gate_conflicts",
                                               "input": {"levers": {}}}]}, model=self.model)
        # second turn must contain the tool result we produced
        assert messages[-1]["content"][0]["type"] == "tool_result"
        reply = {"findings": ["Apron holds detected"], "message": "Reallocate gates",
                 "proposed_actions": [{"lever": "gate_policy", "value": "reallocate", "reason": "waits"},
                                      {"lever": "teleport_aircraft", "value": True, "reason": "invalid"}],
                 "evidence": {}, "uncertainty": "low", "constraints": []}
        return ModelTurn(text="```json\n" + json.dumps(reply) + "\n```", raw={}, model=self.model)


class DeadClaude:
    model = "dead"

    def available(self):
        return True

    async def turn(self, *a, **k):
        raise ProviderUnavailable("HTTP 529")


def ws():
    return Workspace(flights=assign_planned_gates(build_flights()), disruption=operation_sandstorm())


def test_llm_brain_runs_tool_loop_and_filters_invalid_levers():
    events = []

    async def emit(e):
        events.append(e)

    out = asyncio.run(GateAgent(ws(), emit, FakeClaude()).run("assess"))
    assert out["brain"] == "claude:fake-claude"
    assert out["proposed_actions"] == [{"lever": "gate_policy", "value": "reallocate", "reason": "waits"}]
    assert any(e["type"] == "tool_call" and e["tool"] == "gate_conflicts" for e in events)


def test_provider_failure_falls_back_to_deterministic_policy():
    events = []

    async def emit(e):
        events.append(e)

    out = asyncio.run(RunwayAgent(ws(), emit, DeadClaude()).run("assess"))
    assert out["brain"] == "deterministic" and out["findings"]
    assert any(e.get("kind") == "fallback" for e in events)


def test_clean_actions_rejects_unknown_values():
    assert clean_actions([{"lever": "sequencing", "value": "random"}]) == []


def test_conflicting_recommendations_are_escalated(monkeypatch):
    monkeypatch.setenv("SKYOPS_AI_MODE", "offline")
    events = []

    async def emit(e):
        events.append(e)

    o = Orchestrator(assign_planned_gates(build_flights()), operation_sandstorm(), emit, ModelRouter(), pace=0)
    out = asyncio.run(o.run())
    conflicts = [e for e in events if e["type"] == "conflict"]
    assert any(c["between"] == ["gate", "flight"] for c in conflicts)
    assert out["review"]["python_validation"]["feasible"]
    if out["review"]["disagreement"]:
        assert out["review"]["escalated_to_human"]


def test_openai_reviewer_failure_falls_back(monkeypatch):
    monkeypatch.setenv("SKYOPS_AI_MODE", "offline")
    router = ModelRouter()
    router.openai_enabled = lambda: True

    async def boom(*a, **k):
        raise ProviderUnavailable("timeout")

    router.reviewer.turn = boom
    events = []

    async def emit(e):
        events.append(e)

    o = Orchestrator(assign_planned_gates(build_flights()), operation_sandstorm(), emit, router, pace=0)
    out = asyncio.run(o.run())
    assert out["review"]["reviewer"] == "deterministic"
    assert any(e.get("kind") == "fallback" and e.get("from") == "reviewer" for e in events)
