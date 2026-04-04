"""Provider configuration for LLM models."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    name: str
    api_key_env: str

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)

    @property
    def is_available(self) -> bool:
        return self.api_key is not None


def detect_provider(model_name: str) -> str:
    """Detect provider from model name prefix."""
    name_lower = model_name.lower()
    if name_lower.startswith("claude"):
        return "claude"
    if name_lower.startswith("glm"):
        return "glm"
    return "openai"
