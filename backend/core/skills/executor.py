"""Skill executor — dual execution modes."""
from __future__ import annotations

from core.executor.task import TaskSpec
from .types import Skill


def skill_to_task(skill: Skill, user_query: str) -> TaskSpec:
    """Convert a matched skill into a TaskSpec for the Execute node."""
    if skill.execution_mode == "prompt_injection":
        augmented_prompt = f"[Skill: {skill.name}]\n{skill.content}\n\n---\n用户请求: {user_query}"
        return TaskSpec(type="skill_inject", description=augmented_prompt, skill_name=skill.name, timeout=skill.timeout)
    else:
        # Separate skill content (system prompt) from user query (description)
        # so the runner can use a proper SystemMessage for the skill instructions
        return TaskSpec(
            type="skill_subagent",
            description=user_query,
            skill_name=skill.name,
            skill_system_prompt=skill.content,
            tools=skill.tools if skill.tools else None,
            timeout=skill.timeout,
        )
