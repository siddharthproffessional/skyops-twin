"""OpenAI Chat Completions adapter, used only for the independent plan reviewer."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import httpx

from .base import LLMClient, ModelTurn, ProviderUnavailable

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, model: Optional[str] = None, timeout: float = 40.0):
        self.key = os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("SKYOPS_OPENAI_MODEL", "gpt-5-mini")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.key)

    async def turn(self, system, messages, tools=None, max_tokens=1200) -> ModelTurn:
        if not self.key:
            raise ProviderUnavailable("OPENAI_API_KEY not set")
        body = {"model": self.model, "messages": [{"role": "system", "content": system}] + messages,
                "response_format": {"type": "json_object"}}
        headers = {"authorization": f"Bearer {self.key}", "content-type": "application/json"}
        last_err: Exception | None = None
        for attempt in range(3):
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    r = await c.post(API_URL, json=body, headers=headers)
                if r.status_code in (429, 500, 502, 503):
                    last_err = ProviderUnavailable(f"HTTP {r.status_code}")
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"].get("content") or ""
                return ModelTurn(text=text, raw=data, model=self.model,
                                 latency_ms=int((time.perf_counter() - t0) * 1000))
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                await asyncio.sleep(1.0 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                raise ProviderUnavailable(f"OpenAI error {e.response.status_code}: {e.response.text[:200]}")
        raise ProviderUnavailable(f"OpenAI unavailable: {last_err}")
