"""Score facts by confidence: explicitness + repetition + consistency."""
from __future__ import annotations

from .merger import similarity
from .storage import Fact


def score_fact(new_fact: Fact, existing_facts: list[Fact]) -> float:
    explicitness = _score_explicitness(new_fact)
    repetition = _score_repetition(new_fact, existing_facts)
    consistency = _score_consistency(new_fact, existing_facts)
    return round(0.3 * explicitness + 0.4 * repetition + 0.3 * consistency, 3)


def _score_explicitness(fact: Fact) -> float:
    if len(fact.content) > 20:
        return 0.9
    return 0.5


def _score_repetition(fact: Fact, existing: list[Fact]) -> float:
    count = 0
    for old in existing:
        if old.replaced_by is not None:
            continue
        if similarity(fact.content, old.content) >= 0.5:
            count += 1
    return min(1.0, count * 0.3)


def _score_consistency(fact: Fact, existing: list[Fact]) -> float:
    same_cat = [f for f in existing if f.category == fact.category and f.replaced_by is None]
    if not same_cat:
        return 1.0
    for old in same_cat:
        sim = similarity(fact.content, old.content)
        if 0.3 <= sim < 0.75:
            return 0.5
    return 1.0


def score_facts(new_facts: list[Fact], existing: list[Fact]) -> list[Fact]:
    for fact in new_facts:
        fact.confidence = score_fact(fact, existing)
    return new_facts
