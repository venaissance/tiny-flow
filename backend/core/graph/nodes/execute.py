# backend/core/graph/nodes/execute.py
"""Execute node — runs research tasks directly (no thread pool)."""
from __future__ import annotations

import logging
from typing import Any

from core.executor.runner import SubagentRunner
from core.executor.task import TaskResult, TaskSpec
from core.graph.state import GraphState

logger = logging.getLogger(__name__)


def execute_node(state: GraphState, model: Any) -> dict:
    """Execute all pending tasks synchronously for immediate SSE feedback."""
    tasks = state.get("pending_tasks", [])
    if not tasks:
        return {"pending_tasks": [], "iteration": state.get("iteration", 0) + 1}

    all_results: list[TaskResult] = []
    all_tool_calls: list[dict] = []

    for task in tasks:
        if task.type == "skill_inject":
            all_results.append(TaskResult(
                task_id=task.id, status="completed", output=task.description,
            ))
            continue

        # Run directly — no thread pool, so graph progresses and SSE events flow
        runner = SubagentRunner(
            model=model,
            system_prompt=task.skill_system_prompt or "",
            tool_names=task.tools,
        )
        sub_result = runner.run(task.description, task.id)

        # Collect tool calls
        for tc in runner.tool_call_log:
            all_tool_calls.append({
                "name": tc.get("name", ""),
                "query": tc.get("args", {}).get("query", ""),
                "preview": tc.get("result_preview", "")[:150],
            })

        all_results.append(TaskResult(
            task_id=task.id,
            status=sub_result.status.value,
            output=sub_result.output,
            error=sub_result.error,
            skill_name=task.skill_name,
        ))

    return {
        "pending_tasks": [],
        "completed_tasks": state.get("completed_tasks", []) + all_results,
        "iteration": state.get("iteration", 0) + 1,
        "last_tool_calls": all_tool_calls,
    }
