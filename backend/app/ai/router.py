"""Decides which brain runs each agent. Falls back to the deterministic policy when needed."""
from __future__ import annotations

import os

from .claude_client import ClaudeClient
from .openai_client import OpenAIClient


class ModelRouter:
    def __init__(self):
        mode = os.getenv("SKYOPS_AI_MODE", "auto").lower()  # auto | offline
        self.mode = mode
        self.orchestrator = ClaudeClient(os.getenv("SKYOPS_CLAUDE_MODEL", "claude-sonnet-5-5"))
        self.specialist = ClaudeClient(os.getenv("SKYOPS_CLAUDE_FAST_MODEL", "claude-haiku-5-5"), timeout=25)
        self.reviewer = OpenAIClient()

    def claude_enabled(self) -> bool:
        return self.mode != "offline" and self.specialist.available()

    def openai_enabled(self) -> bool:
        return self.mode != "offline" and self.reviewer.available()

    def status(self) -> dict:
        return {
            "mode": "live-ai" if self.claude_enabled() else "offline-deterministic",
            "claude": {"enabled": self.claude_enabled(), "orchestrator_model": self.orchestrator.model,
                       "specialist_model": self.specialist.model},
            "openai": {"enabled": self.openai_enabled(), "reviewer_model": self.reviewer.model},
        }
