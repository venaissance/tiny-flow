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

    if memory:
        system = SystemMessage(content=f"你是一个有帮助的 AI 助手。\n\n已知用户信息:\n{memory}")
        messages = [system] + messages

    response = model.invoke(messages)
    return {"messages": [response]}
