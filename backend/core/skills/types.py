"""Skill data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Skill:
    """A skill loaded from SKILL.md."""
    name: str
    description: str
    content: str
    path: Path
    triggers: list[str] = field(default_factory=list)
    execution_mode: Literal["prompt_injection", "subagent"] = "prompt_injection"
    tools: list[str] = field(default_factory=list)
    priority: int = 0
    timeout: int = 300

    def keyword_match(self, query: str) -> int:
        """Count how many triggers match the query. 0 = no match."""
        query_lower = query.lower()
        return sum(1 for t in self.triggers if t.lower() in query_lower)
