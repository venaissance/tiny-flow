# backend/core/graph/nodes/reflector.py
"""Reflector node — quality check and loop control."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from core.executor.task import TaskResult
from core.graph.state import GraphState

logger = logging.getLogger(__name__)


def reflector_node(
    state: GraphState,
    model: Any,
    max_iterations: int = 3,
) -> dict:
    """Review completed tasks and decide: respond or loop back.

    ALWAYS terminates unless there are pending tasks remaining.
    This prevents the graph from looping indefinitely.
    """
    # Ultra mode: Merge node already synthesized the response
    if state.get("execution_mode") == "ultra":
        logger.info("Reflector: ultra mode, terminating")
        return {"route": "done"}

    # If there are pending tasks AND we haven't hit max iterations, continue
    pending = state.get("pending_tasks", [])
    iteration = state.get("iteration", 1)

    if pending and iteration < max_iterations:
        logger.info(f"Reflector: {len(pending)} tasks still pending, looping back")
        return {"route": "continue_execute"}

    # ALL other cases: terminate with final response
    completed = state.get("completed_tasks", [])
    logger.info(f"Reflector: terminating (iteration={iteration}, completed={len(completed)})")
    return _make_final_response(completed)


def _make_final_response(completed: list[TaskResult]) -> dict:
    """Synthesize a response from completed tasks and TERMINATE."""
    outputs = [t.output for t in completed if t.output and t.status == "completed"]
    if outputs:
        content = "\n\n".join(outputs)
    else:
        errors = [t.error for t in completed if t.error]
        content = "任务执行遇到问题：\n" + "\n".join(errors) if errors else "无法完成请求。"
    return {
        "messages": [AIMessage(content=content)],
        "route": "done",
        "pending_tasks": [],
    }
