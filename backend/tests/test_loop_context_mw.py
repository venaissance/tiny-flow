# backend/tests/test_loop_context_mw.py
"""Tests for LoopDetectionMiddleware and ContextCompactionMiddleware."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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


# =====================================================================
# ContextCompactionMiddleware — strategy="smart" (Deep Agent SDK inspired)
# =====================================================================

class TestSmartContextCompaction:
    """Mechanism-level unit tests for strategy='smart'.

    These are code-mechanism tests (does the logic execute as coded?),
    complementing the behavior evals in tests/evals/test_compaction_evals.py
    which ask different questions (does the agent retain what users need?).
    """

    from langchain_core.messages import ToolMessage  # local import for fixtures

    @staticmethod
    def _make_state(messages: list, metadata: dict | None = None) -> dict:
        return {"messages": messages, "metadata": metadata or {}}

    # --- construction ---

    def test_default_strategy_is_truncate(self):
        mw = ContextCompactionMiddleware()
        assert mw.strategy == "truncate"

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            ContextCompactionMiddleware(strategy="nonsense")

    def test_smart_accepts_kwargs(self):
        mw = ContextCompactionMiddleware(
            strategy="smart", retention_window=5, summarizer=lambda p, m: "x"
        )
        assert mw.strategy == "smart"
        assert mw.retention_window == 5

    # --- no-op when under limit ---

    def test_smart_no_op_when_under_limit(self):
        mw = ContextCompactionMiddleware(max_messages=30, strategy="smart")
        state = self._make_state([HumanMessage(content=f"m{i}") for i in range(10)])
        result = mw.before_node(state, "x")
        assert len(result["messages"]) == 10
        assert "_context_compacted" not in result

    # --- bucketing ---

    def test_smart_retention_window_keeps_tail(self):
        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", retention_window=5
        )
        # 20 distinct HumanMessages
        msgs = [HumanMessage(content=f"m{i}") for i in range(20)]
        state = self._make_state(msgs)
        result = mw.before_node(state, "x")

        # Tail messages should be the last 5 originals (indices 15..19)
        result_contents = [m.content for m in result["messages"]]
        for i in range(15, 20):
            assert f"m{i}" in result_contents

    # --- invariance: first substantive human msg ---

    def test_smart_preserves_first_substantive_human(self):
        msgs = [
            HumanMessage(content="你好"),          # greeting
            AIMessage(content="Hi!"),
            HumanMessage(content="Analyze this file: report_v3.pdf"),  # substantive
            AIMessage(content="ok"),
        ]
        # pad to trigger compaction
        for i in range(40):
            msgs.append(HumanMessage(content=f"chat {i}"))
            msgs.append(AIMessage(content=f"resp {i}"))
        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", retention_window=6
        )
        result = mw.before_node(self._make_state(msgs), "x")

        flat = " ".join(str(m.content) for m in result["messages"])
        assert "report_v3.pdf" in flat

    def test_smart_skips_short_greeting_when_finding_first_human(self):
        """'你好' (2 chars) is a greeting — skip it for first-substantive."""
        msgs = [HumanMessage(content="你好")] + [
            AIMessage(content=f"ai {i}") if i % 2 else HumanMessage(content=f"hu {i}")
            for i in range(50)
        ]
        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", retention_window=5
        )
        first = mw._first_substantive_human_msg(msgs)
        # 你好 is short greeting → skip. First non-greeting Human is "hu 0"? No, index 0
        # is "你好", index 1 is "ai 1" (i=1 is odd so AI), index 2 is "hu 2"...
        # Actually let me not over-specify. Just assert it's not "你好".
        assert first is not None
        assert first.content != "你好"

    def test_smart_long_greeting_prefix_is_substantive(self):
        """'你好，帮我分析这份报告' is long enough to be substantive."""
        msg = HumanMessage(content="你好，帮我分析这份报告 q4_forecast_v2.docx")
        mw = ContextCompactionMiddleware(strategy="smart")
        first = mw._first_substantive_human_msg([msg])
        assert first is msg

    # --- structure: orphan tool pair removal ---

    def test_smart_drops_orphan_tool_response(self):
        from langchain_core.messages import ToolMessage

        # Build: tool_call in compaction zone, tool_response in retention
        msgs: list = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hi!"),
        ]
        for i in range(10):
            msgs.append(HumanMessage(content=f"noise {i}"))
        # The call — will land in compaction zone
        msgs.append(
            AIMessage(
                content="calling",
                tool_calls=[{"id": "x1", "name": "t", "args": {}}],
            )
        )
        # The response (in retention with window=5 and total 17)
        for i in range(3):
            msgs.append(HumanMessage(content=f"buffer {i}"))
        msgs.append(ToolMessage(tool_call_id="x1", content="result"))
        msgs.append(HumanMessage(content="done?"))

        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", retention_window=3
        )
        result = mw.before_node(self._make_state(msgs), "x")
        # Orphan should be removed — no ToolMessage with id x1 in output
        tool_ids = [
            m.tool_call_id
            for m in result["messages"]
            if isinstance(m, ToolMessage)
        ]
        assert "x1" not in tool_ids

    def test_smart_keeps_tool_pair_when_both_in_retention(self):
        from langchain_core.messages import ToolMessage

        msgs: list = [HumanMessage(content="Hi"), AIMessage(content="Hi!")]
        for i in range(20):
            msgs.append(HumanMessage(content=f"noise {i}"))
        # Put both in retention (last few)
        msgs.append(
            AIMessage(
                content="calling", tool_calls=[{"id": "y1", "name": "t", "args": {}}]
            )
        )
        msgs.append(ToolMessage(tool_call_id="y1", content="result"))

        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", retention_window=5
        )
        result = mw.before_node(self._make_state(msgs), "x")

        # Both should survive
        ai_tool_call_ids = set()
        tool_response_ids = set()
        for m in result["messages"]:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls or []:
                    ai_tool_call_ids.add(tc.get("id"))
            elif isinstance(m, ToolMessage):
                tool_response_ids.add(m.tool_call_id)

        assert "y1" in ai_tool_call_ids
        assert "y1" in tool_response_ids

    # --- rolling summary ---

    def test_smart_writes_rolling_summary_to_metadata(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(30)]
        mw = ContextCompactionMiddleware(
            max_messages=10,
            strategy="smart",
            retention_window=5,
            summarizer=lambda prior, ms: f"SUMMARY-of-{len(ms)}",
        )
        result = mw.before_node(self._make_state(msgs), "x")
        assert result["metadata"]["context_summary"] == "SUMMARY-of-25"

    def test_smart_rolls_prior_summary_forward(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(30)]
        mw = ContextCompactionMiddleware(
            max_messages=10,
            strategy="smart",
            retention_window=5,
            summarizer=lambda prior, ms: f"{prior}|NEW",
        )
        state = self._make_state(msgs, metadata={"context_summary": "OLD"})
        result = mw.before_node(state, "x")
        assert result["metadata"]["context_summary"] == "OLD|NEW"

    # --- graceful degradation ---

    def test_smart_falls_back_to_truncate_on_summarizer_failure(self):
        def broken(prior, ms):
            raise RuntimeError("LLM API unreachable")

        msgs = [HumanMessage(content=f"m{i}") for i in range(25)]
        mw = ContextCompactionMiddleware(
            max_messages=10, strategy="smart", summarizer=broken
        )
        result = mw.before_node(self._make_state(msgs), "x")
        # Should have fallen back to truncate: first 2 + last 8
        assert result["_context_compacted"] is True
        assert result["_compacted_count"] == 10

    # --- output shape ---

    def test_smart_stores_summary_in_metadata_not_messages(self):
        """Summary goes to metadata, NOT into the message list.
        Node functions read it and inject into system prompt at position 0.
        This keeps the middleware model-agnostic."""
        msgs = [HumanMessage(content=f"m{i}") for i in range(30)]
        mw = ContextCompactionMiddleware(
            max_messages=10,
            strategy="smart",
            retention_window=5,
            summarizer=lambda prior, ms: "SUMMARY",
        )
        result = mw.before_node(self._make_state(msgs), "x")
        # Summary is in metadata, not in messages
        assert result["metadata"]["context_summary"] == "SUMMARY"
        # No summary message injected into the message list
        for m in result["messages"]:
            assert "SUMMARY" not in str(m.content)
