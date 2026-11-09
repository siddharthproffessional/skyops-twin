"""Model adapter interface."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional


class ProviderUnavailable(Exception):
    """Raised when a provider has no key, times out, or keeps failing."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    model: str = ""
    latency_ms: int = 0


class LLMClient:
    provider = "base"

    def available(self) -> bool:
        return False

    async def turn(self, system: str, messages: list[dict], tools: Optional[list[dict]] = None,
                   max_tokens: int = 1200) -> ModelTurn:
        raise NotImplementedError


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON object")
