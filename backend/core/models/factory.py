"""LLM model factory -- single entry point for creating chat models."""
from __future__ import annotations

import logging
import yaml
from pathlib import Path
from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from .providers import detect_provider

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load and cache config.yaml."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_default_model() -> str:
    cfg = _load_config()
    return cfg.get("model", {}).get("default", "gpt-4o")


def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create a chat model by name.

    Args:
        name: Model name (e.g. "gpt-4o", "claude-sonnet-4-20250514").
              Defaults to config default.
        thinking_enabled: Enable extended thinking (Claude only).
        reasoning_effort: Reasoning effort level (Claude only).

    Returns:
        A LangChain BaseChatModel instance.
    """
    model_name = name or get_default_model()
    provider = detect_provider(model_name)

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        model_kwargs: dict[str, Any] = {}
        if thinking_enabled:
            model_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 8000,
            }
        return ChatAnthropic(model=model_name, streaming=True, **model_kwargs, **kwargs)
    elif provider == "glm":
        import os
        from langchain_openai import ChatOpenAI

        base_url = "https://open.bigmodel.cn/api/paas/v4"
        return ChatOpenAI(
            model=model_name,
            streaming=True,
            base_url=base_url,
            api_key=os.environ.get("GLM_API_KEY", ""),
            **kwargs,
        )
    elif provider == "minimax":
        import os
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            streaming=True,
            base_url="https://api.minimaxi.com/v1",
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            **kwargs,
        )
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_name, streaming=True, **kwargs)
