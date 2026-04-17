# backend/core/graph/nodes/respond.py
"""Respond node — direct LLM response for simple queries."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.graph.state import GraphState


def respond_node(state: GraphState, model: Any) -> dict:
    """Generate a direct response using the LLM."""
    messages = list(state["messages"])
    memory = state.get("memory_context", "")
    summary = (state.get("metadata") or {}).get("context_summary", "")

    system_parts = ["你是一个有帮助的 AI 助手。直接回答用户的问题。"]
    if summary:
        system_parts.append(f"对话历史摘要（仅供参考，不要复述）:\n{summary}")
    if memory:
        system_parts.append(f"已知用户信息:\n{memory}")

    if len(system_parts) > 1:
        messages = [SystemMessage(content="\n\n".join(system_parts))] + messages

    response = model.invoke(messages)
    return {"messages": [response]}
