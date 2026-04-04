# backend/core/graph/nodes/skill_node.py
"""Skill node — two-phase match then create TaskSpec."""
from __future__ import annotations

import logging
from typing import Any

from core.executor.task import TaskSpec
from core.graph.state import GraphState
from core.skills.executor import skill_to_task
from core.skills.registry import get_all_skills
from core.skills.router import select_best_skill

logger = logging.getLogger(__name__)


def skill_node(state: GraphState, model: Any) -> dict:
    """Match skill and produce TaskSpec."""
    meta = state.get("metadata", {})
    query = meta.get("skill_query", "")

    if not query:
        for msg in reversed(state["messages"]):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                query = msg.content
                break

    skills = get_all_skills()
    matched = select_best_skill(skills, query, model)

    if matched is None:
        # Fallback: degrade to subagent
        logger.info("No skill matched, falling back to subagent")
        task = TaskSpec(type="subagent", description=query)
        return {"pending_tasks": [task], "route": "subagent"}

    task = skill_to_task(matched, query)
    return {"pending_tasks": [task]}
