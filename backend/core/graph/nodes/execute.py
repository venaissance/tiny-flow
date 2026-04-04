# backend/core/graph/nodes/execute.py
"""Execute node — runs tasks, parallel for Ultra mode."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.executor.runner import SubagentRunner
from core.executor.task import TaskResult, TaskSpec
from core.graph.state import GraphState

logger = logging.getLogger(__name__)

# Shared pool for Ultra parallel execution (max 3 concurrent, matches DeerFlow)
_ULTRA_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ultra")


def _run_single_task(task: TaskSpec, model: Any) -> tuple[TaskResult, list[dict]]:
    """Execute a single task. Returns (TaskResult, tool_call_log)."""
    start = time.time()

    if task.type == "skill_inject":
        return TaskResult(
            task_id=task.id, status="completed", output=task.description,
        ), []

    runner = SubagentRunner(
        model=model,
        system_prompt=task.skill_system_prompt or "",
        tool_names=task.tools,
    )
    sub_result = runner.run(task.description, task.id)

    tool_calls = [
        {
            "name": tc.get("name", ""),
            "query": tc.get("args", {}).get("query", ""),
            "preview": tc.get("result_preview", "")[:150],
        }
        for tc in runner.tool_call_log
    ]

    duration = time.time() - start
    return TaskResult(
        task_id=task.id,
        status=sub_result.status.value,
        output=sub_result.output,
        error=sub_result.error,
        skill_name=task.skill_name,
        duration_seconds=duration,
    ), tool_calls


def execute_node(state: GraphState, model: Any) -> dict:
    """Execute pending tasks. Ultra mode runs in parallel via ThreadPool."""
    tasks = state.get("pending_tasks", [])
    if not tasks:
        return {"pending_tasks": [], "iteration": state.get("iteration", 0) + 1}

    mode = state.get("execution_mode", "pro")
    all_results: list[TaskResult] = []
    all_tool_calls: list[dict] = []

    todos = list(state.get("todos", []))
    pending_todos = [t for t in todos if t.status == "pending"]

    if mode == "ultra" and len(tasks) > 1:
        # ── Ultra: parallel execution ──
        # Mark all TODOs as in_progress simultaneously
        for t in pending_todos:
            t.status = "in_progress"

        logger.info(f"Ultra mode: executing {len(tasks)} tasks in parallel")
        futures = {
            _ULTRA_POOL.submit(_run_single_task, task, model): (task, i)
            for i, task in enumerate(tasks)
        }

        for future in as_completed(futures):
            task, idx = futures[future]
            try:
                result, tool_calls = future.result()
                all_results.append(result)
                all_tool_calls.extend(tool_calls)
                # Mark corresponding TODO as completed
                if idx < len(pending_todos):
                    pending_todos[idx].status = "completed" if result.status == "completed" else "failed"
                logger.info(f"Task {task.id} completed: {result.status} ({result.duration_seconds:.1f}s)")
            except Exception as e:
                logger.exception(f"Task {task.id} failed: {e}")
                all_results.append(TaskResult(task_id=task.id, status="failed", error=str(e)))
                if idx < len(pending_todos):
                    pending_todos[idx].status = "failed"
    else:
        # ── Pro/single: sequential execution with per-TODO progress ──
        for i, task in enumerate(tasks):
            # Mark current TODO as in_progress
            if i < len(pending_todos):
                pending_todos[i].status = "in_progress"

            result, tool_calls = _run_single_task(task, model)
            all_results.append(result)
            all_tool_calls.extend(tool_calls)

            # Mark current TODO as completed/failed
            if i < len(pending_todos):
                pending_todos[i].status = "completed" if result.status == "completed" else "failed"

        # Mark any remaining TODOs as completed (single task covers all steps)
        for t in pending_todos:
            if t.status == "pending" or t.status == "in_progress":
                t.status = "completed"

    return {
        "pending_tasks": [],
        "completed_tasks": state.get("completed_tasks", []) + all_results,
        "iteration": state.get("iteration", 0) + 1,
        "last_tool_calls": all_tool_calls,
        "todos": todos,
    }
