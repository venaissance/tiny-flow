# backend/core/graph/nodes/dispatch.py
"""Dispatch node — construct TaskSpec(s) for subagent execution."""
from __future__ import annotations

from core.executor.task import TaskSpec
from core.graph.state import GraphState


def dispatch_node(state: GraphState) -> dict:
    """Build TaskSpec(s) from router decision.

    Pro mode:  single task with web_search
    Ultra mode: one task per subtask for parallel execution
    """
    meta = state.get("metadata", {})
    mode = state.get("execution_mode", "pro")

    # Ultra mode: create parallel tasks from subtasks list
    if mode == "ultra":
        subtasks = meta.get("subtasks", [])
        if subtasks and len(subtasks) > 1:
            tasks = [
                TaskSpec(
                    type="subagent",
                    description=st,
                    tools=["web_search", "run_skill"],
                )
                for st in subtasks
            ]
            return {"pending_tasks": tasks}

    # Pro mode / fallback: single task
    description = meta.get("task_description", "")
    if not description:
        for msg in reversed(state["messages"]):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                description = msg.content
                break

    task = TaskSpec(
        type="subagent",
        description=description,
        agent_type=meta.get("suggested_agent_type", "general"),
        tools=["web_search", "run_skill"],
    )

    return {"pending_tasks": [task]}
