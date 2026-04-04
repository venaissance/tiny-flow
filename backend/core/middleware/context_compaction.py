# backend/core/middleware/context_compaction.py
"""Middleware that trims the message list to avoid context-window overflow."""
from __future__ import annotations

import logging

from core.middleware.base import Middleware

logger = logging.getLogger(__name__)


class ContextCompactionMiddleware(Middleware):
    """Keep the message list within *max_messages* by dropping the middle
    portion while preserving the first 2 (system/user seed) and the most
    recent messages."""

    def __init__(self, max_messages: int = 30) -> None:
        self.max_messages = max_messages

    # ------------------------------------------------------------------
    # before_node — trim before every node so the LLM never sees a
    #               context that exceeds the budget.
    # ------------------------------------------------------------------
    def before_node(self, state: dict, node_name: str) -> dict:
        messages = state.get("messages", [])
        original_len = len(messages)

        if original_len <= self.max_messages:
            return state

        keep_tail = self.max_messages - 2
        state["messages"] = messages[:2] + messages[-keep_tail:]
        state["_context_compacted"] = True
        state["_original_count"] = original_len
        state["_compacted_count"] = len(state["messages"])

        logger.info(
            "ContextCompaction: trimmed messages from %d to %d",
            original_len,
            state["_compacted_count"],
        )
        return state
