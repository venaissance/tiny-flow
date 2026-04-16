# backend/tests/evals/conftest.py
"""Shared fixtures for agent behavior evals.

These fixtures build realistic conversation scenarios — the kind a real user
would generate, not synthetic minimal inputs. They're the "dataset" side of
the eval: construct plausible inputs, then assert behavior on outputs.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


# ---------------------------------------------------------------------------
# Conversation builders
# ---------------------------------------------------------------------------


def build_greeting_then_real_ask(
    fact: str = "q4_forecast_v2.docx",
    noise_turns: int = 14,
) -> list:
    """Realistic conversation: greeting, then user mentions a key fact,
    then noise_turns turns of chat, then user asks about the fact again.

    This is the single most common real-world failure pattern for naive
    compaction: the important info is NOT in message[0] or message[1],
    it's in message[2-5] where the user actually states their goal.
    """
    msgs: list[Any] = [
        HumanMessage(content="你好"),
        AIMessage(content="你好，有什么可以帮你？"),
        HumanMessage(content=f"我要分析一份文件，叫 {fact}"),
        AIMessage(content="好的，记下了。你想做什么分析？"),
        HumanMessage(content="请提取 top-line 营收"),
        AIMessage(content="明白，开工。"),
    ]
    for i in range(noise_turns):
        msgs.append(HumanMessage(content=f"另外顺便看下 item {i}"))
        msgs.append(AIMessage(content=f"好的，item {i} 已处理。"))
    msgs.append(HumanMessage(content="对了，我最开始让你分析的那个文件叫什么名字？"))
    return msgs


def build_tool_call_pair_at_boundary(max_messages: int = 10) -> list:
    """Conversation where a tool_call/tool_response pair straddles the
    truncate boundary. Naive truncate (keep first 2 + last max-2) drops
    the tool_call but keeps the tool_response, creating a protocol-violating
    orphan.

    For max_messages=10: kept = indices [0, 1] + [19..26] on a 27-message list.
    tool_call placed at idx 18 (DROPPED).
    tool_response placed at idx 20 (KEPT → orphan).
    """
    msgs: list[Any] = []
    msgs.append(HumanMessage(content="Hi"))
    msgs.append(AIMessage(content="Hi!"))
    # Noise that will be dropped (indices 2..17, 16 messages)
    for i in range(16):
        msgs.append(HumanMessage(content=f"noise {i}"))
    # Tool call in the drop zone (index 18)
    msgs.append(
        AIMessage(
            content="Let me call a tool.",
            tool_calls=[{"id": "call_123", "name": "search", "args": {"q": "revenue"}}],
        )
    )
    # One buffer message (index 19, first kept in the tail)
    msgs.append(HumanMessage(content="ok sure"))
    # Tool response in the kept tail (index 20) — orphan when truncate drops its call
    msgs.append(ToolMessage(tool_call_id="call_123", content="Revenue: $1.2M Q4"))
    # Fill out the tail so retention covers the response (indices 21..26)
    for i in range(6):
        msgs.append(HumanMessage(content=f"tail {i}"))
    return msgs  # total 27 messages


def build_long_conversation(num_turns: int = 30, fact: str = "ProjectPhoenix") -> list:
    """Build a conversation of num_turns turns where the user mentions
    a specific fact at turn 3, and asks about it again at the end.
    Used by efficiency evals to stress the compaction path.
    """
    msgs: list[Any] = [
        HumanMessage(content="Hi"),
        AIMessage(content="Hi there."),
        HumanMessage(content=f"I'm working on {fact}, please keep it in mind."),
        AIMessage(content=f"Noted: {fact}."),
    ]
    for i in range(num_turns):
        msgs.append(HumanMessage(content=f"Quick question {i}?"))
        msgs.append(AIMessage(content=f"Answer {i}."))
    msgs.append(HumanMessage(content=f"What project was I working on?"))
    return msgs


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conversation_with_early_fact():
    """35-message conversation; key fact in turn 3 (not turn 1)."""
    return build_greeting_then_real_ask()


@pytest.fixture
def conversation_with_tool_pair():
    """Conversation with tool_call/tool_response near retention boundary."""
    return build_tool_call_pair_at_boundary()


@pytest.fixture
def long_conversation():
    """Long conversation that triggers compaction."""
    return build_long_conversation(num_turns=30)


@pytest.fixture
def stub_summarizer():
    """Deterministic summarizer for reproducible evals — no LLM calls.

    Returns a callable(prior_summary: str, messages: list) -> str that
    produces a content-aware summary: extracts HumanMessage text and
    joins with prior summary. This simulates what a real LLM summary
    *should* preserve (user intents) without the nondeterminism.
    """
    def _summarize(prior_summary: str, messages: list) -> str:
        user_text_fragments = []
        for m in messages:
            if isinstance(m, HumanMessage):
                # Keep the first ~80 chars of user utterances
                user_text_fragments.append(str(m.content)[:80])
        combined = "; ".join(user_text_fragments)
        if prior_summary:
            return f"{prior_summary}\n---\n{combined}"
        return combined

    return _summarize
