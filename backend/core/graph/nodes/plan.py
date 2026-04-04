# backend/core/graph/nodes/plan.py
"""Plan node — decompose user request into ordered TODO steps."""
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
    "分析用户请求，将其分解为 2-3 个独立的子任务（最多 3 个，系统并行上限为 3）。"
    "每个子任务应该是一个完整的、可独立执行的查询。"
    "\n\n例如：用户说'分别调研 React、Vue、Svelte 的最新版本'，"
    "应拆分为：['调研 React 最新版本和特性', '调研 Vue 最新版本和特性', '调研 Svelte 最新版本和特性']"
    "\n\n输出 JSON: {\"steps\": [\"子任务1\", \"子任务2\", ...]}"
    "\n只输出 JSON。"
)


def plan_node(state: GraphState, model: Any) -> dict:
    """Decompose task into TODO steps using LLM."""
    user_query = _extract_user_query(state)

    try:
        response = model.invoke([
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=user_query),
        ])
        steps = _parse_steps(response.content)
    except Exception as e:
        logger.warning("Plan node failed to decompose task: %s", e)
        steps = [user_query]

    todos = [TodoItem(content=step) for step in steps]
    result: dict = {"todos": todos}

    # Ultra mode: also populate metadata.subtasks for dispatch parallelism
    mode = state.get("execution_mode", "pro")
    if mode == "ultra":
        result["metadata"] = {**state.get("metadata", {}), "subtasks": steps}

    return result


def _extract_user_query(state: GraphState) -> str:
    """Pull the latest user message from conversation history."""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _parse_steps(text: str) -> list[str]:
    """Parse JSON steps from LLM output, tolerating markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    data = json.loads(cleaned)
    steps = data.get("steps", [])
    if not steps or not isinstance(steps, list):
        raise ValueError("Empty or invalid steps list")
    return [str(s) for s in steps]
