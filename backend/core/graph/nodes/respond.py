# backend/core/graph/nodes/respond.py
"""Respond node — direct LLM response for simple queries."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.graph.state import GraphState


_ANTI_ECHO = (
    "严禁在回答中复述、引用或以任何形式重复上方标签内的原文。"
    "把这些信息当作你已经知道的事实自然融入回答；不要用"
    "「用户是…」「用户喜欢…」这种第三人称陈述开头。"
    "直接回应用户当前这句话。"
)


def _build_system_prompt(base: str, memory: str, summary: str) -> str:
    parts = [base]
    bg: list[str] = []
    if memory:
        bg.append(f"<user_profile>\n{memory}\n</user_profile>")
    if summary:
        bg.append(f"<conversation_summary>\n{summary}\n</conversation_summary>")
    if bg:
        parts.append("以下是后台已知的上下文：\n" + "\n".join(bg) + "\n\n" + _ANTI_ECHO)
    return "\n\n".join(parts)


_FLASH_BASE_PROMPT = (
    "你是一个友好的 AI 助手。回答保持简洁自然，"
    "直接回应用户这一句话，不要用「用户…」「你正在…」这种第三人称陈述开头。"
)


def respond_node(state: GraphState, model: Any) -> dict:
    """Flash-mode LLM response.

    Feeds the model:
      1. The tail of the conversation (retention window) — what the
         model can "see verbatim".
      2. The rolling summary from AsyncCompactor, embedded in the
         system prompt with strict anti-echo instructions — so the
         agent remembers what fell off the tail (project name, user's
         daughter's name, planned trip, etc.) without parroting it.

    The summarizer's tokens themselves never reach the user because
    they carry the `compaction_summarizer` tag and chat.py's SSE
    streamer filters on that tag.
    """
    from core.compaction import get_async_compactor

    thread_id = (state.get("metadata") or {}).get("thread_id", "")
    all_msgs = list(state["messages"])
    effective = get_async_compactor().effective_messages(thread_id, all_msgs)

    memory = state.get("memory_context", "")
    summary = get_async_compactor().get_summary(thread_id) or (
        (state.get("metadata") or {}).get("context_summary", "")
    )
    system_prompt = _build_system_prompt(_FLASH_BASE_PROMPT, memory, summary)
    messages = [SystemMessage(content=system_prompt)] + effective

    response = model.invoke(messages)
    return {"messages": [response]}
