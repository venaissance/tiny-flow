"""Task types for subagent execution."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class SubagentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class TaskSpec:
    """Specification for a task to be executed."""
    id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    type: Literal["subagent", "skill_subagent", "skill_inject"] = "subagent"
    description: str = ""
    agent_type: str | None = None
    skill_name: str | None = None
    skill_system_prompt: str | None = None
    tools: list[str] | None = None
    timeout: int = 300


@dataclass
class TaskResult:
    """Result of a completed task."""
    task_id: str
    status: Literal["completed", "failed", "timed_out"]
    output: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    tool_calls: list[dict] = field(default_factory=list)
    skill_name: str | None = None


@dataclass
class SubagentResult:
    """Internal result from subagent execution."""
    task_id: str
    status: SubagentStatus = SubagentStatus.PENDING
    messages: list = field(default_factory=list)
    output: str = ""
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class TodoItem:
    """A single step in the execution plan."""
    id: str = field(default_factory=lambda: f"todo_{uuid.uuid4().hex[:6]}")
    content: str = ""
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    error: str | None = None
