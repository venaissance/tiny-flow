# backend/tests/test_loop_context_mw.py
"""Tests for LoopDetectionMiddleware and ContextCompactionMiddleware."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.middleware.loop_detection import LoopDetectionMiddleware
from core.middleware.context_compaction import ContextCompactionMiddleware


# =====================================================================
# LoopDetectionMiddleware
# =====================================================================

class TestLoopDetectionMiddleware:
    """Unit tests for loop detection logic."""

    def _make_state(self, *, iteration: int = 1, previous: str = "") -> dict:
        return {
            "iteration": iteration,
            "previous_round_output": previous,
            "messages": [HumanMessage(content="hello")],
        }

    def _make_output(self, text: str = "result", route: str | None = None) -> dict:
        out: dict = {"messages": [AIMessage(content=text)]}
        if route is not None:
            out["route"] = route
        return out

    # --- passthrough for non-reflector nodes ---

    def test_ignores_non_reflector_nodes(self):
        mw = LoopDetectionMiddleware()
        state = self._make_state()
        output = self._make_output("anything")
        result = mw.after_node(state, "router", output)
        assert "_loop_terminated" not in result

    # --- hard iteration limit ---

    def test_terminates_at_max_iterations(self):
        mw = LoopDetectionMiddleware(max_iterations=3)
        state = self._make_state(iteration=3)
        output = self._make_output("answer")
        result = mw.after_node(state, "reflector", output)
        assert result["_loop_terminated"] is True
        assert "max iterations" in result["_loop_reason"]

    def test_does_not_terminate_below_max_iterations(self):
        mw = LoopDetectionMiddleware(max_iterations=3)
        state = self._make_state(iteration=2)
        output = self._make_output("fresh answer")
        result = mw.after_node(state, "reflector", output)
        assert "_loop_terminated" not in result

    # --- similarity detection ---

    def test_terminates_on_similar_output(self):
        mw = LoopDetectionMiddleware(similarity_threshold=0.9)
        state = self._make_state(iteration=1, previous="The quick brown fox")
        output = self._make_output("The quick brown fox")  # identical
        result = mw.after_node(state, "reflector", output)
        assert result["_loop_terminated"] is True
        assert "similarity" in result["_loop_reason"]

    def test_does_not_terminate_on_different_output(self):
        mw = LoopDetectionMiddleware(similarity_threshold=0.9)
        state = self._make_state(iteration=1, previous="completely different text")
        output = self._make_output("The quick brown fox jumps over the lazy dog")
        result = mw.after_node(state, "reflector", output)
        assert "_loop_terminated" not in result

    def test_skips_similarity_when_no_previous_output(self):
        mw = LoopDetectionMiddleware(similarity_threshold=0.9)
        state = self._make_state(iteration=1, previous="")
        output = self._make_output("first round")
        result = mw.after_node(state, "reflector", output)
        assert "_loop_terminated" not in result

    # --- route clearing ---

    def test_clears_subagent_route_on_termination(self):
        mw = LoopDetectionMiddleware(max_iterations=2)
        state = self._make_state(iteration=2)
        output = self._make_output("answer", route="subagent")
        result = mw.after_node(state, "reflector", output)
        assert result["_loop_terminated"] is True
        assert result["route"] is None

    def test_preserves_non_subagent_route(self):
        mw = LoopDetectionMiddleware(max_iterations=2)
        state = self._make_state(iteration=2)
        output = self._make_output("answer", route="direct")
        result = mw.after_node(state, "reflector", output)
        assert result["_loop_terminated"] is True
        # "direct" != "subagent", so route stays unchanged.
        assert result["route"] == "direct"


# =====================================================================
# ContextCompactionMiddleware
# =====================================================================

class TestContextCompactionMiddleware:
    """Unit tests for context compaction logic."""

    @staticmethod
    def _msgs(n: int) -> list:
        """Generate *n* numbered messages (alternating Human/AI)."""
        msgs = []
        for i in range(n):
            cls = HumanMessage if i % 2 == 0 else AIMessage
            msgs.append(cls(content=f"msg-{i}"))
        return msgs

    def test_no_compaction_when_under_limit(self):
        mw = ContextCompactionMiddleware(max_messages=30)
        state = {"messages": self._msgs(10)}
        result = mw.before_node(state, "router")
        assert len(result["messages"]) == 10
        assert "_context_compacted" not in result

    def test_no_compaction_at_exact_limit(self):
        mw = ContextCompactionMiddleware(max_messages=10)
        state = {"messages": self._msgs(10)}
        result = mw.before_node(state, "router")
        assert len(result["messages"]) == 10
        assert "_context_compacted" not in result

    def test_compaction_trims_to_limit(self):
        mw = ContextCompactionMiddleware(max_messages=10)
        msgs = self._msgs(20)
        state = {"messages": msgs}
        result = mw.before_node(state, "dispatch")
        assert result["_context_compacted"] is True
        assert result["_original_count"] == 20
        assert result["_compacted_count"] == 10
        assert len(result["messages"]) == 10

    def test_keeps_first_two_messages(self):
        mw = ContextCompactionMiddleware(max_messages=6)
        msgs = self._msgs(15)
        state = {"messages": msgs}
        result = mw.before_node(state, "dispatch")
        # First two messages must be the originals.
        assert result["messages"][0].content == "msg-0"
        assert result["messages"][1].content == "msg-1"

    def test_keeps_last_n_messages(self):
        mw = ContextCompactionMiddleware(max_messages=6)
        msgs = self._msgs(15)
        state = {"messages": msgs}
        result = mw.before_node(state, "dispatch")
        # tail = max_messages - 2 = 4 last messages
        expected_tail = [m.content for m in msgs[-4:]]
        actual_tail = [m.content for m in result["messages"][2:]]
        assert actual_tail == expected_tail

    def test_metadata_fields_are_set(self):
        mw = ContextCompactionMiddleware(max_messages=5)
        state = {"messages": self._msgs(12)}
        result = mw.before_node(state, "router")
        assert result["_context_compacted"] is True
        assert result["_original_count"] == 12
        assert result["_compacted_count"] == 5
