"""Two-phase skill routing: keyword pre-filter + LLM semantic select."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from .types import Skill

logger = logging.getLogger(__name__)


def keyword_filter(skills: list[Skill], query: str, max_candidates: int = 5) -> list[Skill]:
    """Phase 1: O(n) keyword scan, returns top candidates sorted by relevance."""
    scored = []
    for skill in skills:
        match_count = skill.keyword_match(query)
        if match_count > 0:
            scored.append((match_count, skill.priority, skill))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [s[2] for s in scored[:max_candidates]]


def select_best_skill(skills: list[Skill], query: str, model: Any | None = None) -> Skill | None:
    """Synchronous two-phase routing."""
    candidates = keyword_filter(skills, query)
    if not candidates:
        return None
    if len(candidates) == 1 or model is None:
        return candidates[0]

    # Phase 2: synchronous LLM call
    candidates_text = "\n".join(f"- {s.name}: {s.description}" for s in candidates)
    prompt = f"用户请求: {query}\n\n候选 Skills:\n{candidates_text}\n\n请选择最匹配的 skill 名称。如果没有合适的，回复 \"none\"。只回复名称。"

    try:
        response = model.invoke([HumanMessage(content=prompt)])
        answer = response.content.strip().lower()
        if answer == "none":
            return None
        for s in candidates:
            if s.name.lower() == answer or s.name.lower() in answer:
                return s
        return candidates[0]
    except Exception as e:
        logger.warning(f"LLM skill select failed: {e}")
        return candidates[0]
