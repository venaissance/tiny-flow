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
    "分析用户请求，将其分解为 2-5 个有序执行步骤。"
    "输出 JSON: {\"steps\": [\"步骤1\", ...]}"
    "\n\n注意：只输出 JSON，不要包含其他内容。"
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
    return {"todos": todos}


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
