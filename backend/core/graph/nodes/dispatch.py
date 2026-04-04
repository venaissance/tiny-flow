# backend/core/graph/nodes/dispatch.py
"""Dispatch node — construct TaskSpec for subagent execution."""
from __future__ import annotations

from core.executor.task import TaskSpec
from core.graph.state import GraphState


def dispatch_node(state: GraphState) -> dict:
    """Build TaskSpec from router's subagent decision — always includes web_search."""
    meta = state.get("metadata", {})
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
        tools=["web_search"],  # Always enable search for subagent tasks
    )

    return {"pending_tasks": [task]}
