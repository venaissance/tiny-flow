# backend/core/graph/nodes/reflector.py
"""Reflector node — quality check and loop control."""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from core.executor.task import TaskResult
from core.graph.state import GraphState

logger = logging.getLogger(__name__)

REFLECTOR_PROMPT = """你是一个任务质量审查员。审查以下任务执行结果，判断是否满足用户的原始请求。

用户请求: {user_query}

执行结果:
{results}

当前迭代: {iteration} / {max_iterations}

如果结果足够好，请直接基于执行结果给出综合回复。
如果结果不够好且需要补充，说明原因并描述需要补充的任务。

回复格式：
- 如果满意：直接给出综合回复
- 如果不满意：以 "[NEED_MORE_WORK]" 开头，说明原因"""


def reflector_node(
    state: GraphState,
    model: Any,
    max_iterations: int = 3,
) -> dict:
    """Review completed tasks and decide: respond or loop back."""
    # Ultra mode: Merge node already synthesized the response, just pass through
    if state.get("execution_mode") == "ultra":
        return {}

    iteration = state.get("iteration", 1)
    completed = state.get("completed_tasks", [])
    previous_output = state.get("previous_round_output", "")

    # Format results
    results_text = _format_results(completed)

    # Soft limit: check if output is similar to previous round
    if previous_output and _is_similar(results_text, previous_output, threshold=0.9):
        logger.info("Reflector: output similar to previous round, terminating")
        return _make_final_response(completed, state)

    # Hard limit
    if iteration >= max_iterations:
        logger.info(f"Reflector: reached max iterations ({max_iterations})")
        return _make_final_response(completed, state)

    # For research tasks with completed results, skip LLM review — just output
    has_output = any(t.output and t.status == "completed" for t in completed)
    if has_output:
        logger.info("Reflector: research completed, outputting results directly")
        return _make_final_response(completed, state)

    # Only use LLM review if no useful output was produced
    return _make_final_response(completed, state)


def _format_results(tasks: list[TaskResult]) -> str:
    parts = []
    for t in tasks:
        status_label = {"completed": "OK", "failed": "FAILED", "timed_out": "TIMEOUT"}
        parts.append(f"[{status_label.get(t.status, t.status)}] {t.output or t.error or 'no output'}")
    return "\n\n".join(parts)


def _is_similar(a: str, b: str, threshold: float = 0.9) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _get_user_query(state: GraphState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _make_final_response(completed: list[TaskResult], state: GraphState) -> dict:
    """Synthesize a response from completed tasks."""
    outputs = [t.output for t in completed if t.output and t.status == "completed"]
    if outputs:
        content = "\n\n".join(outputs)
    else:
        errors = [t.error for t in completed if t.error]
        content = "任务执行遇到问题：\n" + "\n".join(errors) if errors else "无法完成请求。"
    return {"messages": [AIMessage(content=content)]}
