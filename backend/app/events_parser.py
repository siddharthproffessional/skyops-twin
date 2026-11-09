"""Turn a free-text event (typed by a judge) into a supported disruption."""
from __future__ import annotations

import json
import re
from typing import Optional

from .ai.base import ProviderUnavailable, extract_json
from .ai.router import ModelRouter
from .simulation import scenarios as sc
from .simulation.engine import Disruption

SUPPORTED = ("sandstorm", "runway_closure(runway, start_min, duration_min)",
             "capacity_reduction(runway, capacity_per_hour, start_min, duration_min)",
             "flight_delay(flight_id, minutes)", "crew_unavailable(count)", "gate_closure(gate, duration_min)")


def _num(pattern: str, text: str, default: float) -> float:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else default


def _duration(text: str, default: float = 60) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)\b", text)
    if m:
        return float(m.group(1)) * 60
    m = re.search(r"(\d+)\s*(m|min|mins|minutes)\b", text)
    return float(m.group(1)) if m else default


def _start(text: str, default: float = 30) -> float:
    m = re.search(r"\b(?:at|from)\s*(\d{1,2})[:.](\d{2})", text)
    if m:
        return max(0.0, (int(m.group(1)) - 14) * 60 + int(m.group(2)))
    return default


def rule_parse(text: str, flight_ids: list[str]) -> Optional[dict]:
    t = text.lower()
    if re.search(r"sand|dust|haboob", t):
        return {"type": "sandstorm", "params": {}}
    rw = re.search(r"\b(30l|30r)\b", t)
    rw_id = rw.group(1).upper() if rw else "30L"
    if re.search(r"clos|shut|block|inspection|debris|fod", t) and ("runway" in t or rw):
        return {"type": "runway_closure", "params": {"runway": rw_id, "start_min": _start(t), "duration_min": _duration(t)}}
    if re.search(r"capacity|movements|per hour|/h|low visibility|fog", t):
        cap = _num(r"(\d+)\s*(?:movements|mvts|per hour|/h)", t, 14)
        return {"type": "capacity_reduction", "params": {"runway": rw.group(1).upper() if rw else "30R",
                                                         "capacity_per_hour": cap, "start_min": _start(t),
                                                         "duration_min": _duration(t, 90)}}
    for fid in flight_ids:
        if fid.lower() in t:
            mins = _num(r"(\d+)\s*(?:m|min|mins|minutes)\b", t, _duration(t, 45))
            return {"type": "flight_delay", "params": {"flight_id": fid, "minutes": mins}}
    if re.search(r"crew|handler|staff|strike|sick", t):
        n = int(_num(r"(\d+)\s*(?:crew|crews|team|teams|handlers)", t, 2))
        return {"type": "crew_unavailable", "params": {"count": n}}
    g = re.search(r"\bgate\s*([ab]\d{1,2}|r\d)\b", t)
    if g:
        return {"type": "gate_closure", "params": {"gate": g.group(1).upper(), "duration_min": _duration(t, 120)}}
    return None


def build(spec: dict) -> Disruption:
    tp, p = spec["type"], spec.get("params", {})
    if tp == "sandstorm":
        return sc.operation_sandstorm()
    if tp == "runway_closure":
        s = float(p.get("start_min", 30))
        return sc.runway_closure(p.get("runway", "30L"), s, s + float(p.get("duration_min", 60)))
    if tp == "capacity_reduction":
        s = float(p.get("start_min", 30))
        return sc.capacity_reduction(p.get("runway", "30R"), int(p.get("capacity_per_hour", 14)), s,
                                     s + float(p.get("duration_min", 90)))
    if tp == "flight_delay":
        return sc.flight_delay(p["flight_id"], float(p.get("minutes", 45)))
    if tp == "crew_unavailable":
        n = max(1, min(6, int(p.get("count", 2))))
        ids = ["GH-A1", "GH-A2", "GH-B1", "GH-A3", "GH-B2", "GH-A5"][:n]
        return sc.crew_unavailable(ids)
    if tp == "gate_closure":
        return sc.gate_closure(p["gate"], 0, float(p.get("duration_min", 120)))
    raise ValueError(f"unsupported event type {tp}")


async def parse(text: str, flight_ids: list[str], router: ModelRouter) -> tuple[Optional[dict], str]:
    """Returns (spec or None, method)."""
    if router.claude_enabled():
        try:
            turn = await router.specialist.turn(
                "Map an airport operations event description to ONE supported disruption type for a simulated "
                "airport (t=0 is 14:00, times in minutes). Supported: " + "; ".join(SUPPORTED) +
                f". Valid flight ids: {', '.join(flight_ids)}. Runways: 30L, 30R. Return JSON "
                "{\"type\": ..., \"params\": {...}} or {\"type\": \"unsupported\", \"reason\": ...}.",
                [{"role": "user", "content": text}], max_tokens=300)
            data = extract_json(turn.text)
            if data.get("type") == "unsupported":
                return None, "claude"
            build(data)  # validates
            return data, "claude"
        except (ProviderUnavailable, ValueError, KeyError, json.JSONDecodeError):
            pass
    return rule_parse(text, flight_ids), "rules"
