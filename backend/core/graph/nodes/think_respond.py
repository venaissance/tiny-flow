# backend/core/graph/nodes/think_respond.py
"""Think-respond node — response with visible reasoning chain."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.graph.state import GraphState

THINK_SYSTEM_PROMPT = (
    "你是一个有帮助的 AI 助手。回答用户问题时，请先在 <thinking>...</thinking> "
    "标签中展示你的推理过程，然后给出最终答案。\n\n"
    "格式：\n"
    "<thinking>\n你的分析和推理过程\n</thinking>\n\n最终答案"
)


def think_respond_node(state: GraphState, model: Any) -> dict:
    """Response with visible reasoning chain."""
    messages = list(state["messages"])
    memory = state.get("memory_context", "")

    system_parts = [THINK_SYSTEM_PROMPT]
    if memory:
        system_parts.append(f"\n已知用户信息:\n{memory}")

    messages = [SystemMessage(content="".join(system_parts))] + messages

    response = model.invoke(messages)
    return {"messages": [response]}
