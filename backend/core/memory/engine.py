"""Memory engine — orchestrates Extract -> Score -> Merge -> Inject."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage

from .extractor import extract_facts
from .injector import build_memory_prompt
from .merger import merge_facts
from .scorer import score_facts
from .storage import MemoryStorage

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_PATH = Path(__file__).parent.parent.parent / "data" / "memory.json"


class MemoryEngine:
    def __init__(self, storage_path: str | Path | None = None, token_budget: int = 500,
                 min_confidence: float = 0.7, decay_days: int = 30, decay_factor: float = 0.8):
        self.storage = MemoryStorage(storage_path or _DEFAULT_MEMORY_PATH)
        self.token_budget = token_budget
        self.min_confidence = min_confidence
        self.decay_days = decay_days
        self.decay_factor = decay_factor

    def inject(self) -> str:
        self.storage.apply_decay(self.decay_days, self.decay_factor)
        facts = self.storage.get_facts()
        return build_memory_prompt(facts, self.token_budget, self.min_confidence)

    def process_conversation(self, messages: list[BaseMessage], model: Any, thread_id: str = ""):
        def _run():
            try:
                new_facts = extract_facts(messages, model, thread_id)
                if not new_facts:
                    return
                existing = self.storage.get_facts()
                scored = score_facts(new_facts, existing)
                merged = merge_facts(scored, existing)
                self.storage.save_facts(merged)
                logger.info(f"Memory updated: {len(new_facts)} new facts processed")
            except Exception as e:
                logger.warning(f"Memory pipeline failed: {e}")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def get_facts(self):
        return self.storage.get_facts()
