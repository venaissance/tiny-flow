# backend/tests/evals/test_compaction_evals.py
"""Behavior evals for ContextCompactionMiddleware.

These evals ask: "After compaction, can the agent still answer the user?"
They are NOT the same as the unit tests in tests/test_loop_context_mw.py,
which ask "Did the middleware execute its rule (cut to N messages)?"

Each eval is parametrized over the middleware's strategy parameter.
Truncate is the current naive implementation. Smart is the Deep Agent
SDK-inspired implementation (sliding window + summary + invariance
constraints + tool-pair preservation).

Expected outcomes:
  - Correctness evals: truncate FAILS on 2/3, smart PASSES all 3.
  - Efficiency evals: both meet targets, but smart should be within
    acceptable overhead vs truncate (latency < 2s, summary cost < 1000 tokens).
"""
from __future__ import annotations

import time
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from core.middleware.context_compaction import ContextCompactionMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compacted_text(messages: list) -> str:
    """Join all compacted message contents into a single searchable string."""
    parts = []
    for m in messages:
        content = getattr(m, "content", "")
        if isinstance(content, str):
            parts.append(content)
    return " ".join(parts)


def _run_compaction(
    middleware: ContextCompactionMiddleware,
    messages: list,
    prior_summary: str = "",
) -> dict:
    """Run before_node and return the resulting state."""
    state: dict[str, Any] = {
        "messages": messages,
        "metadata": {"context_summary": prior_summary},
    }
    return middleware.before_node(state, "dispatch")


# ---------------------------------------------------------------------------
# Correctness evals
# ---------------------------------------------------------------------------


@pytest.mark.eval_category("retrieval")
@pytest.mark.correctness
@pytest.mark.parametrize("strategy", ["truncate", "smart"])
def test_eval_early_fact_retention(
    conversation_with_early_fact,
    stub_summarizer,
    strategy,
):
    """[retrieval] Fact mentioned in turn 2 survives compaction.

    Why this matters: naive compaction drops the middle, but most real users
    don't state their intent in message[0] — they say 'hi' first, then state
    the goal in message[2-5]. If compaction drops that region, the agent
    silently forgets what the user wants.

    User-facing failure: "What was the file you asked me to analyze?" →
    agent says "I don't see any file name in our conversation".
    """
    kwargs: dict[str, Any] = {"max_messages": 10, "strategy": strategy}
    if strategy == "smart":
        kwargs["summarizer"] = stub_summarizer
        kwargs["retention_window"] = 8

    mw = ContextCompactionMiddleware(**kwargs)
    result = _run_compaction(mw, conversation_with_early_fact)

    content = _compacted_text(result["messages"])
    # Also check the rolling summary (smart strategy persists here)
    content += " " + result.get("metadata", {}).get("context_summary", "")

    assert "q4_forecast_v2.docx" in content, (
        f"[{strategy}] Critical fact (filename) lost after compaction. "
        f"Agent can no longer recall what file the user asked about."
    )


@pytest.mark.eval_category("invariance")
@pytest.mark.correctness
@pytest.mark.parametrize("strategy", ["truncate", "smart"])
def test_eval_user_original_goal_preserved(
    conversation_with_early_fact,
    stub_summarizer,
    strategy,
):
    """[invariance] The user's ORIGINAL goal statement is always preserved
    verbatim (not summarized away).

    Deep Agent SDK rule: 'unchanging constraints' — user's first
    substantive ask must never be lossy-compressed.

    In this scenario, the real intent is turn 2 ('我要分析一份文件...'),
    not turn 0 ('你好'). A truly smart strategy picks the first
    HumanMessage with actual content, not just index 0.
    """
    kwargs: dict[str, Any] = {"max_messages": 10, "strategy": strategy}
    if strategy == "smart":
        kwargs["summarizer"] = stub_summarizer
        kwargs["retention_window"] = 8

    mw = ContextCompactionMiddleware(**kwargs)
    result = _run_compaction(mw, conversation_with_early_fact)

    # Scan the compacted messages for the original goal phrase (preserved verbatim,
    # not merely mentioned in a summary paraphrase).
    found_verbatim = False
    for m in result["messages"]:
        if isinstance(m, HumanMessage) and "我要分析一份文件" in str(m.content):
            found_verbatim = True
            break

    assert found_verbatim, (
        f"[{strategy}] User's original goal HumanMessage was not preserved verbatim. "
        f"Smart compaction must identify and keep the user's actual intent message, "
        f"not blindly keep messages[:2] (which may just be greetings)."
    )


@pytest.mark.eval_category("tool_use")
@pytest.mark.correctness
@pytest.mark.parametrize("strategy", ["truncate", "smart"])
def test_eval_tool_call_pair_integrity(
    conversation_with_tool_pair,
    stub_summarizer,
    strategy,
):
    """[tool_use] tool_call / tool_response pairs are never orphaned by compaction.

    Deep Agent SDK rule: 'structured content loss' anti-pattern.

    If a tool_call is dropped but its tool_response survives (or vice versa),
    the LLM sees an orphan. LangChain/OpenAI spec: tool_response without
    matching tool_call is a protocol violation — the model will error or hallucinate.
    """
    kwargs: dict[str, Any] = {"max_messages": 10, "strategy": strategy}
    if strategy == "smart":
        kwargs["summarizer"] = stub_summarizer
        kwargs["retention_window"] = 8

    mw = ContextCompactionMiddleware(**kwargs)
    result = _run_compaction(mw, conversation_with_tool_pair)

    # Collect surviving tool_call ids and tool_response ids
    surviving_call_ids: set[str] = set()
    surviving_response_ids: set[str] = set()
    for m in result["messages"]:
        if isinstance(m, AIMessage):
            for tc in (m.tool_calls or []):
                surviving_call_ids.add(tc.get("id", ""))
        elif isinstance(m, ToolMessage):
            surviving_response_ids.add(m.tool_call_id)

    orphan_responses = surviving_response_ids - surviving_call_ids
    orphan_calls = surviving_call_ids - surviving_response_ids

    assert not orphan_responses, (
        f"[{strategy}] Orphan tool_response(s) survived compaction without their "
        f"matching tool_call: {orphan_responses}. This violates LLM protocol."
    )
    assert not orphan_calls, (
        f"[{strategy}] Orphan tool_call(s) survived compaction without their "
        f"matching tool_response: {orphan_calls}. This violates LLM protocol."
    )


# ---------------------------------------------------------------------------
# Efficiency evals
# ---------------------------------------------------------------------------


@pytest.mark.eval_category("efficiency")
@pytest.mark.efficiency
@pytest.mark.parametrize("strategy", ["truncate", "smart"])
def test_eval_compaction_latency(
    long_conversation,
    stub_summarizer,
    strategy,
):
    """[efficiency] One compaction invocation completes in < 2 seconds.

    With a stub summarizer (no real LLM), both strategies should be
    well under this bound — this is the regression guard for production
    (real LLM will be ~800ms; we budget 2s total).
    """
    kwargs: dict[str, Any] = {"max_messages": 10, "strategy": strategy}
    if strategy == "smart":
        kwargs["summarizer"] = stub_summarizer
        kwargs["retention_window"] = 8

    mw = ContextCompactionMiddleware(**kwargs)

    t0 = time.perf_counter()
    _run_compaction(mw, long_conversation)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 2000, (
        f"[{strategy}] Compaction took {elapsed_ms:.1f}ms, exceeds 2000ms budget."
    )


@pytest.mark.eval_category("efficiency")
@pytest.mark.efficiency
@pytest.mark.parametrize("strategy", ["truncate", "smart"])
def test_eval_compacted_size_within_budget(
    long_conversation,
    stub_summarizer,
    strategy,
):
    """[efficiency] After compaction, the hot context is bounded.

    Agent eval rule: correctness first, efficiency next. Both strategies
    must actually keep the message count bounded — correctness without
    size reduction is pointless.

    Target: compacted message count <= max_messages * 1.2 (small slack
    for smart strategy which injects summary messages).
    """
    kwargs: dict[str, Any] = {"max_messages": 10, "strategy": strategy}
    if strategy == "smart":
        kwargs["summarizer"] = stub_summarizer
        kwargs["retention_window"] = 8

    mw = ContextCompactionMiddleware(**kwargs)
    result = _run_compaction(mw, long_conversation)

    compacted_count = len(result["messages"])
    budget = int(10 * 1.2) + 2  # small slack for first_human + summary injection

    assert compacted_count <= budget, (
        f"[{strategy}] Compacted to {compacted_count} messages, exceeds "
        f"budget of {budget} (max_messages={10} * 1.2 + 2)."
    )
