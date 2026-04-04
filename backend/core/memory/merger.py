"""Merge new facts with existing facts — dedup, conflict detection, decay."""
from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from .storage import Fact

DUPLICATE_THRESHOLD = 0.75
CONTRADICT_THRESHOLD = 0.5


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def merge_facts(new_facts: list[Fact], existing: list[Fact]) -> list[Fact]:
    result = list(existing)
    for new in new_facts:
        best_sim = 0.0
        best_idx = -1
        for i, old in enumerate(result):
            if old.replaced_by is not None:
                continue
            sim = similarity(new.content, old.content)
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_sim >= DUPLICATE_THRESHOLD:
            old = result[best_idx]
            old.confidence = max(old.confidence, new.confidence)
            old.last_verified = datetime.now().isoformat()
        elif CONTRADICT_THRESHOLD <= best_sim < DUPLICATE_THRESHOLD and best_idx >= 0:
            old = result[best_idx]
            if old.category == new.category:
                old.replaced_by = new.id
                new.last_verified = datetime.now().isoformat()
                result.append(new)
            else:
                result.append(new)
        else:
            result.append(new)
    return result
