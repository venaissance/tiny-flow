"""Inject memory facts into system prompt with token budget."""
from __future__ import annotations

from datetime import datetime

import tiktoken

from .storage import Fact

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def build_memory_prompt(facts: list[Fact], token_budget: int = 500, min_confidence: float = 0.7) -> str:
    now = datetime.now()
    eligible = [f for f in facts if f.confidence >= min_confidence and f.replaced_by is None]

    def sort_key(f: Fact) -> float:
        try:
            last = datetime.fromisoformat(f.last_verified)
            days = max((now - last).days, 0)
        except (ValueError, TypeError):
            days = 0
        recency = 1.0 / (1 + days / 30)
        return f.confidence * recency

    eligible.sort(key=sort_key, reverse=True)

    selected: dict[str, list[str]] = {}
    total_tokens = 0
    for f in eligible:
        line = f"- {f.content}"
        line_tokens = count_tokens(line)
        if total_tokens + line_tokens > token_budget:
            break
        cat = f.category
        selected.setdefault(cat, []).append(line)
        total_tokens += line_tokens
        f.access_count += 1

    if not selected:
        return ""

    parts = []
    for cat, lines in selected.items():
        parts.append(f"## {cat.title()}\n" + "\n".join(lines))
    return "\n\n".join(parts)
