# backend/core/graph/state.py
"""Agent state definition for the LangGraph state machine."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from core.executor.task import TaskSpec, TaskResult, TodoItem


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    route: str | None                          # "direct" | "subagent" | "skill"
    pending_tasks: list[TaskSpec]
    completed_tasks: list[TaskResult]
    previous_round_output: str
    iteration: int
    memory_context: str
    metadata: dict
    last_tool_calls: list[dict]                # tool calls from last execute round
    todos: list                                # list of TodoItem (execution plan)
    execution_mode: str                        # "flash" | "thinking" | "pro" | "ultra"
