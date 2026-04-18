"""Score facts by confidence: explicitness + repetition + consistency.

Confidence formula (each component is in [0, 1]):
    confidence = 0.3 * explicitness + 0.4 * repetition + 0.3 * consistency

Components:
    - explicitness: 0.9 if the fact is verbose (>20 chars), 0.5 otherwise.
      Longer statements are treated as more deliberate/explicit.
    - repetition: min(1.0, 0.3 * N) where N = count of existing facts with
      similarity ≥ 0.5 to this fact. Facts mentioned across turns earn trust.
    - consistency: 1.0 if no same-category fact exists, or all same-category
      facts share high similarity. Drops to 0.5 when there's a potentially
      conflicting fact (similarity in [0.3, 0.75)).

The weights (0.3 / 0.4 / 0.3) favor repetition since a fact mentioned multiple
times is more reliable than a single verbose statement or a consistent outlier.
"""
from __future__ import annotations

from .merger import similarity
from .storage import Fact

# Public weights — surfaced to the UI so the tooltip shows the formula.
WEIGHTS = {"explicitness": 0.3, "repetition": 0.4, "consistency": 0.3}


def score_fact(new_fact: Fact, existing_facts: list[Fact]) -> float:
    explicitness = _score_explicitness(new_fact)
    repetition = _score_repetition(new_fact, existing_facts)
    consistency = _score_consistency(new_fact, existing_facts)
    confidence = round(
        WEIGHTS["explicitness"] * explicitness
        + WEIGHTS["repetition"] * repetition
        + WEIGHTS["consistency"] * consistency,
        3,
    )
    # Attach the breakdown so the UI can render how this number was built.
    new_fact.score_breakdown = {
        "explicitness": round(explicitness, 3),
        "repetition": round(repetition, 3),
        "consistency": round(consistency, 3),
    }
    return confidence


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
