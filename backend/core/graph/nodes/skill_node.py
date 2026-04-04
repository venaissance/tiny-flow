# backend/core/graph/nodes/skill_node.py
"""Skill node — match skill, create TaskSpec(s) aligned with TODOs."""
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
    """Match skill and produce TaskSpec(s).

    For tool-based skills (research/search): one task per pending TODO
    → enables per-TODO graph loop with real-time SSE updates.

    For direct-generation skills (frontend-design, chart): single task
    → the LLM generates everything in one shot.
    """
    meta = state.get("metadata", {})
    query = meta.get("skill_query", "") or meta.get("task_description", "")

    if not query:
        for msg in reversed(state["messages"]):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                query = msg.content
                break

    skills = get_all_skills()
    matched = select_best_skill(skills, query, model)

    if matched is None:
        logger.info("No skill matched, falling back to subagent")
        task = TaskSpec(type="subagent", description=query, tools=["web_search"])
        return {"pending_tasks": [task]}

    todos = state.get("todos", [])
    pending_todos = [t for t in todos if t.status == "pending"]

    # Tool-based skills (research, code-review): split into per-TODO tasks
    if matched.tools and pending_todos:
        logger.info(f"Skill '{matched.name}' has tools, creating {len(pending_todos)} tasks (one per TODO)")
        tasks = [
            TaskSpec(
                type="skill_subagent",
                description=t.content,
                skill_name=matched.name,
                skill_system_prompt=matched.content,
                tools=matched.tools,
                timeout=matched.timeout,
            )
            for t in pending_todos
        ]
        return {"pending_tasks": tasks}

    # Direct-generation skills (frontend-design, chart): single task
    logger.info(f"Skill '{matched.name}' is direct-generation, creating single task")
    task = skill_to_task(matched, query)
    return {"pending_tasks": [task]}
