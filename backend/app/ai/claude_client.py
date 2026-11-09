"""Anthropic Messages API adapter with tool use. Key from ANTHROPIC_API_KEY only."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import httpx

from .base import LLMClient, ModelTurn, ProviderUnavailable, ToolCall

API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: Optional[str] = None, timeout: float = 30.0):
        self.key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("SKYOPS_CLAUDE_MODEL", "claude-sonnet-5-5")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.key)

    async def turn(self, system, messages, tools=None, max_tokens=1200) -> ModelTurn:
        if not self.key:
            raise ProviderUnavailable("ANTHROPIC_API_KEY not set")
        body = {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        last_err: Exception | None = None
        for attempt in range(3):
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r = await c.post(API_URL, json=body, headers=headers)
                if r.status_code in (429, 500, 502, 503, 529):
                    last_err = ProviderUnavailable(f"HTTP {r.status_code}")
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                turn = ModelTurn(raw=data, model=self.model, latency_ms=int((time.perf_counter() - t0) * 1000))
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        turn.text += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        turn.tool_calls.append(ToolCall(block["id"], block["name"], block.get("input") or {}))
                return turn
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                await asyncio.sleep(1.0 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                raise ProviderUnavailable(f"Anthropic error {e.response.status_code}: {e.response.text[:200]}")
        raise ProviderUnavailable(f"Anthropic unavailable: {last_err}")

    @staticmethod
    def tool_specs(tools: dict, allowed: list[str]) -> list[dict]:
        specs = []
        for name in allowed:
            t = tools[name]
            props = {k: {"type": v, "description": "Recovery levers, e.g. {\"sequencing\": \"priority\"}"}
                     for k, v in t["params"].items()}
            specs.append({"name": name, "description": t["desc"],
                          "input_schema": {"type": "object", "properties": props}})
        return specs

    @staticmethod
    def assistant_message(turn: ModelTurn) -> dict:
        return {"role": "assistant", "content": turn.raw.get("content", [])}

    @staticmethod
    def tool_results_message(results: list[tuple[str, str]]) -> dict:
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": content} for tid, content in results]}
