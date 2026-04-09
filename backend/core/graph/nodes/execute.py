# backend/core/graph/nodes/execute.py
"""Execute node — runs one task per cycle (Pro) or all in parallel (Ultra)."""
from __future__ import annotations

import logging
import time
from concurrent.futures import as_completed
from typing import Any

from core.executor.pool import get_executor_pool
from core.executor.runner import SubagentRunner
from core.executor.task import TaskResult, TaskSpec
from core.graph.state import GraphState

logger = logging.getLogger(__name__)


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
    """Execute tasks.

    Pro mode: ONE task per invocation (enables per-TODO SSE updates via graph loop).
    Ultra mode: ALL tasks in parallel via ThreadPool.
    """
    tasks = state.get("pending_tasks", [])
    if not tasks:
        return {"pending_tasks": [], "iteration": state.get("iteration", 0) + 1}

    mode = state.get("execution_mode", "pro")
    todos = list(state.get("todos", []))
    pending_todos = [t for t in todos if t.status == "pending"]
    all_results: list[TaskResult] = []
    all_tool_calls: list[dict] = []

    if mode == "ultra" and len(tasks) > 1:
        # ── Ultra: all tasks in parallel via ExecutorPool ──
        for t in pending_todos:
            t.status = "in_progress"

        pool = get_executor_pool()
        logger.info(f"Ultra mode: executing {len(tasks)} tasks in parallel")
        futures = {
            pool.submit_scheduled(
                _run_single_task, task.timeout or 300, task, model,
            ): (task, i)
            for i, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            task, idx = futures[future]
            try:
                result, tool_calls = future.result()
                all_results.append(result)
                all_tool_calls.extend(tool_calls)
                if idx < len(pending_todos):
                    pending_todos[idx].status = "completed" if result.status == "completed" else "failed"
            except TimeoutError:
                logger.warning(f"Task {task.id} timed out after {task.timeout}s")
                all_results.append(TaskResult(task_id=task.id, status="timed_out", error=f"Timed out after {task.timeout}s"))
                if idx < len(pending_todos):
                    pending_todos[idx].status = "failed"
            except Exception as e:
                logger.exception(f"Task {task.id} failed: {e}")
                all_results.append(TaskResult(task_id=task.id, status="failed", error=str(e)))
                if idx < len(pending_todos):
                    pending_todos[idx].status = "failed"

        remaining_tasks: list[TaskSpec] = []
    else:
        # ── Pro: execute FIRST task only, leave rest pending ──
        first_task = tasks[0]
        remaining_tasks = tasks[1:]

        # Mark first pending TODO as in_progress
        if pending_todos:
            pending_todos[0].status = "in_progress"

        result, tool_calls = _run_single_task(first_task, model)
        all_results.append(result)
        all_tool_calls.extend(tool_calls)

        # Mark first pending TODO as completed/failed
        if pending_todos:
            pending_todos[0].status = "completed" if result.status == "completed" else "failed"

        # For single-task skills (no tools), mark ALL remaining pending TODOs as completed
        if not remaining_tasks and result.status == "completed":
            for t in todos:
                if t.status == "pending":
                    t.status = "completed"

    return {
        "pending_tasks": remaining_tasks,
        "completed_tasks": state.get("completed_tasks", []) + all_results,
        "iteration": state.get("iteration", 0) + 1,
        "last_tool_calls": all_tool_calls,
        "todos": todos,
    }
