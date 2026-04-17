# backend/core/graph/nodes/think_respond.py
"""Think-respond node — response with visible reasoning chain."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.graph.state import GraphState

THINK_SYSTEM_PROMPT = (
    "你是一个善于深度思考的 AI 助手。回答用户问题时，你必须严格按照以下格式输出：\n\n"
    "<thinking>\n"
    "在这里写出你的分析和推理过程，包括：\n"
    "- 问题的关键点\n"
    "- 不同角度的分析\n"
    "- 你的推理链路\n"
    "</thinking>\n\n"
    "在这里写最终答案。\n\n"
    "重要：你必须先输出 <thinking> 标签包裹的推理过程，再输出最终答案。不要跳过推理部分。"
)


def think_respond_node(state: GraphState, model: Any) -> dict:
    """Response with visible reasoning chain."""
    messages = list(state["messages"])
    memory = state.get("memory_context", "")
    summary = (state.get("metadata") or {}).get("context_summary", "")

    system_parts = [THINK_SYSTEM_PROMPT]
    if summary:
        system_parts.append(f"对话历史摘要（仅供参考，不要复述）:\n{summary}")
    if memory:
        system_parts.append(f"已知用户信息:\n{memory}")

    messages = [SystemMessage(content="\n\n".join(system_parts))] + messages

    response = model.invoke(messages)
    return {"messages": [response]}
