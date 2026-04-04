# backend/core/graph/nodes/merge.py
"""Merge node — synthesize results from parallel subagent execution (Ultra mode)."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.executor.task import TaskResult
from core.graph.state import GraphState

logger = logging.getLogger(__name__)

MERGE_SYSTEM_PROMPT = (
    "你是一个综合分析助手。下面是多个子任务的执行结果，请将它们综合成一个"
    "全面、结构清晰的最终回复。\n\n"
    "要求：\n"
    "- 去除重复内容\n"
    "- 保留每个子任务的关键信息\n"
    "- 使用清晰的结构组织输出"
)


def merge_node(state: GraphState, model: Any) -> dict:
    """Synthesize results from parallel subagent execution (Ultra mode)."""
    completed: list[TaskResult] = state.get("completed_tasks", [])
    outputs = [t.output for t in completed if t.output and t.status == "completed"]

    if not outputs:
        errors = [t.error for t in completed if t.error]
        content = "任务执行遇到问题：\n" + "\n".join(errors) if errors else "无法完成请求。"
        return {"messages": [AIMessage(content=content)]}

    if len(outputs) == 1:
        return {"messages": [AIMessage(content=outputs[0])]}

    # Multiple outputs — ask LLM to synthesize
    numbered = "\n\n".join(
        f"--- 子任务 {i + 1} ---\n{out}" for i, out in enumerate(outputs)
    )
    try:
        response = model.invoke([
            SystemMessage(content=MERGE_SYSTEM_PROMPT),
            HumanMessage(content=numbered),
        ])
        return {"messages": [response]}
    except Exception as e:
        logger.warning("Merge node LLM synthesis failed: %s", e)
        return {"messages": [AIMessage(content="\n\n".join(outputs))]}
