# backend/core/graph/nodes/plan.py
"""Plan node — decompose task, auto-upgrade to Ultra if steps are independent."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.executor.task import TodoItem
from core.graph.state import GraphState

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = (
    "分析用户请求，将其分解为 2-3 个子任务（最多 3 个）。\n"
    "判断这些子任务之间是否完全独立（可以并行执行）还是有先后依赖（必须顺序执行）。\n\n"
    "输出 JSON:\n"
    '{"steps": ["子任务1", "子任务2", ...], "parallel": true/false}\n\n'
    "parallel=true 表示子任务之间完全独立，可以并行执行。\n"
    "parallel=false 表示子任务有先后依赖，必须顺序执行。\n\n"
    "例如：\n"
    '- "研究 AI 最新趋势" → {"steps": ["研究 AI 在 NLP 领域的最新趋势", "研究 AI 在计算机视觉领域的最新趋势"], "parallel": true}\n'
    '- "做一个网页" → {"steps": ["设计 UI", "实现功能", "添加交互"], "parallel": false}\n\n'
    "只输出 JSON。"
)


def plan_node(state: GraphState, model: Any) -> dict:
    """Decompose task into TODO steps. Auto-upgrade to Ultra if steps are independent."""
    user_query = _extract_user_query(state)
    mode = state.get("execution_mode", "pro")

    try:
        response = model.invoke([
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=user_query),
        ])
        steps, parallel = _parse_plan(response.content)
    except Exception as e:
        logger.warning("Plan node failed: %s", e)
        steps, parallel = [user_query], False

    todos = [TodoItem(content=step) for step in steps]
    result: dict = {"todos": todos}

    # Auto-upgrade: if steps are independent and we're in Pro, upgrade to Ultra
    if parallel and len(steps) > 1 and mode == "pro":
        logger.info(f"Plan: {len(steps)} independent steps detected, upgrading pro → ultra")
        result["execution_mode"] = "ultra"
        result["metadata"] = {**state.get("metadata", {}), "subtasks": steps}
    elif mode == "ultra":
        result["metadata"] = {**state.get("metadata", {}), "subtasks": steps}

    return result


def _extract_user_query(state: GraphState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _parse_plan(text: str) -> tuple[list[str], bool]:
    """Parse steps and parallel flag from LLM output."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    data = json.loads(cleaned)
    steps = data.get("steps", [])
    parallel = data.get("parallel", False)
    if not steps or not isinstance(steps, list):
        raise ValueError("Empty or invalid steps list")
    return [str(s) for s in steps], bool(parallel)
