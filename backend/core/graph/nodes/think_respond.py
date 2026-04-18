# backend/core/graph/nodes/think_respond.py
"""Think-respond node — response with visible reasoning chain."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.graph.nodes.respond import _build_system_prompt
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
    """Response with visible reasoning chain.

    Thinking mode uses a stronger model (GLM-5.1) that can follow the
    anti-echo instruction while still benefiting from the compaction
    summary. We also pull the summary from AsyncCompactor (async path)
    before falling back to state metadata (sync safety-net path).
    """
    from core.compaction import get_async_compactor

    thread_id = (state.get("metadata") or {}).get("thread_id", "")
    all_msgs = list(state["messages"])
    effective = get_async_compactor().effective_messages(thread_id, all_msgs)

    memory = state.get("memory_context", "")
    summary = get_async_compactor().get_summary(thread_id) or (
        (state.get("metadata") or {}).get("context_summary", "")
    )

    system_prompt = _build_system_prompt(THINK_SYSTEM_PROMPT, memory, summary)
    messages = [SystemMessage(content=system_prompt)] + effective

    response = model.invoke(messages)
    return {"messages": [response]}
