# backend/core/middleware/context_compaction.py
"""Middleware that bounds the message list to avoid context-window overflow.

Two strategies are supported:

- ``truncate`` (default, backward compatible): keep ``messages[:2]`` and
  ``messages[-(max-2):]``. Fast, simple, but fragile — drops the middle
  entirely, can orphan tool_call/tool_response pairs, and silently loses
  the user's original intent if they greeted the agent before stating it.

- ``smart`` (opt-in): bucketing + rolling summary + invariance constraints
  + tool-pair preservation, inspired by LangChain Deep Agent SDK's
  compaction design. Retention window keeps the tail verbatim; the
  compaction zone is compressed via a provided summarizer; the first
  substantive HumanMessage is kept verbatim to preserve user intent; and
  orphan tool_responses (whose tool_call would be dropped) are removed
  to maintain LLM protocol validity.

The smart strategy relies on:
  * ``state["metadata"]["context_summary"]`` for the rolling summary
    (persists across compactions within a thread).
  * a caller-provided ``summarizer`` callable; when absent, falls back
    to a deterministic stub that preserves the text of HumanMessages.

On summarizer failure, smart gracefully degrades to truncate — we never
want the middleware to crash the graph. LangGraph's checkpointer
(InMemorySaver in this codebase) retains the pre-compaction state, so
even lossy compression is recoverable in traces.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from core.middleware.base import Middleware

logger = logging.getLogger(__name__)

# Patterns treated as pure greetings; a HumanMessage that starts with one of
# these AND is short is skipped when searching for the user's "first substantive
# intent". Kept intentionally small and conservative.
_DEFAULT_GREETING_PATTERNS: tuple[str, ...] = (
    "你好", "hello", "hi", "嗨", "早", "good morning", "good afternoon", "hey",
)
_GREETING_MAX_LEN = 12  # a "你好，帮我..." at 20+ chars is NOT a pure greeting


SummarizerFn = Callable[[str, list[BaseMessage]], str]


class ContextCompactionMiddleware(Middleware):
    """Bound the message list before every graph node.

    Args:
        max_messages: Trigger threshold. No-op when ``len(messages) <= max_messages``.
        strategy: ``"truncate"`` (default, original behavior) or ``"smart"``.
        retention_window: (smart only) Number of tail messages kept verbatim.
        summarizer: (smart only) Callable ``(prior_summary, compaction_zone) -> str``.
            If ``None``, a deterministic stub is used.
        greeting_patterns: (smart only) Override the greeting-detection patterns.
    """

    def __init__(
        self,
        max_messages: int = 30,
        strategy: str = "truncate",
        *,
        retention_window: int = 10,
        summarizer: Optional[SummarizerFn] = None,
        greeting_patterns: tuple[str, ...] = _DEFAULT_GREETING_PATTERNS,
    ) -> None:
        if strategy not in {"truncate", "smart"}:
            raise ValueError(
                f"Unknown strategy {strategy!r}; expected 'truncate' or 'smart'."
            )
        self.max_messages = max_messages
        self.strategy = strategy
        self.retention_window = retention_window
        self.summarizer = summarizer
        self.greeting_patterns = greeting_patterns

    # ------------------------------------------------------------------
    # Public hook
    # ------------------------------------------------------------------

    def before_node(self, state: dict, node_name: str) -> dict:
        messages = state.get("messages", [])
        if len(messages) <= self.max_messages:
            return state

        if self.strategy == "smart":
            return self._apply_smart(state, messages)
        return self._apply_truncate(state, messages)

    # ------------------------------------------------------------------
    # Strategy: truncate (original, backward compatible)
    # ------------------------------------------------------------------

    def _apply_truncate(self, state: dict, messages: list) -> dict:
        keep_tail = self.max_messages - 2
        state["messages"] = messages[:2] + messages[-keep_tail:]
        state["_context_compacted"] = True
        state["_original_count"] = len(messages)
        state["_compacted_count"] = len(state["messages"])
        logger.info(
            "ContextCompaction[truncate]: %d -> %d",
            state["_original_count"],
            state["_compacted_count"],
        )
        return state

    # ------------------------------------------------------------------
    # Strategy: smart (Deep Agent SDK inspired)
    # ------------------------------------------------------------------

    def _apply_smart(self, state: dict, messages: list) -> dict:
        # Step 1 — bucketing: split into retention window and compaction zone
        if self.retention_window >= len(messages):
            retention = list(messages)
            compaction_zone: list[BaseMessage] = []
        else:
            retention = list(messages[-self.retention_window :])
            compaction_zone = list(messages[: -self.retention_window])

        # Step 2 — invariance: find the user's first substantive message
        first_human = self._first_substantive_human_msg(messages)

        # Step 3 — structure: drop orphan tool_responses before summary
        retention = self._remove_orphan_tool_responses(retention, compaction_zone)

        # Step 4 — summarize the compaction zone
        summarizer = self.summarizer or self._default_stub_summarizer
        metadata = dict(state.get("metadata") or {})
        prior_summary = str(metadata.get("context_summary") or "")

        try:
            new_summary = summarizer(prior_summary, compaction_zone)
        except Exception as e:  # graceful degradation — never crash the graph
            logger.warning(
                "ContextCompaction[smart]: summarizer failed (%s); "
                "falling back to truncate for this compaction.",
                e,
            )
            return self._apply_truncate(state, messages)

        # Step 5 — roll summary forward in metadata
        metadata["context_summary"] = new_summary

        # Step 6 — assemble final message list
        summary_msg = SystemMessage(content=f"[Prior context summary]\n{new_summary}")
        retention_ids = {id(m) for m in retention}

        new_messages: list[BaseMessage] = []
        if first_human is not None and id(first_human) not in retention_ids:
            new_messages.append(first_human)
        new_messages.append(summary_msg)
        new_messages.extend(retention)

        state["messages"] = new_messages
        state["metadata"] = metadata
        state["_context_compacted"] = True
        state["_original_count"] = len(messages)
        state["_compacted_count"] = len(new_messages)

        logger.info(
            "ContextCompaction[smart]: %d -> %d (summary %d chars, retention %d)",
            state["_original_count"],
            state["_compacted_count"],
            len(new_summary),
            len(retention),
        )
        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _first_substantive_human_msg(
        self, messages: Iterable[BaseMessage]
    ) -> Optional[HumanMessage]:
        """First HumanMessage whose content isn't a pure greeting.

        A pure greeting is short text starting with one of the configured
        greeting patterns. Longer messages starting with a greeting
        (e.g. "你好，帮我分析...") are treated as substantive.
        """
        for msg in messages:
            if not isinstance(msg, HumanMessage):
                continue
            content = str(msg.content or "").strip().lower()
            is_greeting_prefix = any(
                content.startswith(p.lower()) for p in self.greeting_patterns
            )
            if is_greeting_prefix and len(content) <= _GREETING_MAX_LEN:
                continue
            return msg
        return None

    @staticmethod
    def _remove_orphan_tool_responses(
        retention: list[BaseMessage],
        compaction_zone: list[BaseMessage],  # noqa: ARG004 — kept for symmetry/clarity
    ) -> list[BaseMessage]:
        """Remove ToolMessages in retention whose matching tool_call is NOT
        also in retention (i.e. the call was dropped to the compaction zone).

        Orphan tool_responses violate LLM chat protocol — the downstream
        model will either error out or hallucinate. Safer to drop them;
        the rolling summary will record what the tool call produced.
        """
        call_ids_in_retention: set[str] = set()
        for m in retention:
            if isinstance(m, AIMessage):
                for tc in (m.tool_calls or []):
                    tc_id = (
                        tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")
                    )
                    if tc_id:
                        call_ids_in_retention.add(tc_id)

        cleaned: list[BaseMessage] = []
        dropped = 0
        for m in retention:
            if (
                isinstance(m, ToolMessage)
                and m.tool_call_id
                and m.tool_call_id not in call_ids_in_retention
            ):
                dropped += 1
                continue
            cleaned.append(m)

        if dropped:
            logger.info(
                "ContextCompaction[smart]: dropped %d orphan tool_response(s)",
                dropped,
            )
        return cleaned

    @staticmethod
    def _default_stub_summarizer(
        prior: str,
        messages: list[BaseMessage],
    ) -> str:
        """Deterministic fallback used when no real summarizer is configured.

        Preserves HumanMessage text and tool_call names — the two anchors
        that real LLM summaries must also preserve. Not as nuanced as an
        LLM summary, but reproducible and not catastrophically lossy.
        """
        fragments: list[str] = []
        for m in messages:
            if isinstance(m, HumanMessage):
                snippet = str(m.content or "").strip()[:80]
                if snippet:
                    fragments.append(f"user: {snippet}")
            elif isinstance(m, AIMessage) and m.tool_calls:
                tool_names = []
                for tc in m.tool_calls:
                    name = (
                        tc.get("name")
                        if isinstance(tc, dict)
                        else getattr(tc, "name", "?")
                    )
                    tool_names.append(name or "?")
                fragments.append(f"tool_call: {'+'.join(tool_names)}")
        combined = " / ".join(fragments)
        return f"{prior}\n---\n{combined}" if prior else combined
