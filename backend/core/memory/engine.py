"""Memory engine — orchestrates Extract -> Score -> Merge -> Inject.

Durable cross-thread user memory:
  * Persistent JSON storage on disk (data/memory.json) — survives restarts.
  * Global scope — facts extracted in one thread are injected into every
    other thread's system prompt.
  * Confidence decay — stale facts fade unless reinforced.
  * Background extraction — the extraction LLM call never blocks the user.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Optional

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
                 min_confidence: float = 0.7, decay_days: int = 30, decay_factor: float = 0.8,
                 extraction_model_name: str = "glm-4-flash"):
        self.storage = MemoryStorage(storage_path or _DEFAULT_MEMORY_PATH)
        self.token_budget = token_budget
        self.min_confidence = min_confidence
        self.decay_days = decay_days
        self.decay_factor = decay_factor
        self.extraction_model_name = extraction_model_name
        self._extract_lock = threading.Lock()  # one extraction at a time is plenty

    def inject(self) -> str:
        self.storage.apply_decay(self.decay_days, self.decay_factor)
        facts = self.storage.get_facts()
        return build_memory_prompt(facts, self.token_budget, self.min_confidence)

    def process_conversation(self, messages: list[BaseMessage], model: Any, thread_id: str = ""):
        """Background thread form — left for callers that already have a model bound."""
        def _run():
            self._extract_and_save(messages, model, thread_id)

        threading.Thread(target=_run, daemon=True).start()

    def schedule_extraction(self, thread_id: str, graph: Any, config: dict) -> None:
        """Asyncio-friendly entry point: fetches the thread's latest messages
        from the LangGraph checkpointer, extracts facts with our own model
        (from config), merges into the global store. Fire-and-forget."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("MemoryEngine.schedule_extraction outside event loop")
            return
        loop.create_task(self._run(thread_id, graph, config))

    async def _run(self, thread_id: str, graph: Any, config: dict) -> None:
        if self._extract_lock.locked():
            return
        try:
            snapshot = graph.get_state(config)
            messages = list((snapshot.values or {}).get("messages", []))
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryEngine[%s] get_state failed: %s", thread_id, e)
            return
        if not messages:
            return

        # Import here to avoid circular dependency at module load.
        from core.models.factory import create_chat_model
        model = create_chat_model(name=self.extraction_model_name)

        # Run extraction on a worker thread so we don't block the event loop.
        await asyncio.to_thread(self._extract_and_save, messages, model, thread_id)

    def _extract_and_save(self, messages: list[BaseMessage], model: Any, thread_id: str) -> None:
        if not self._extract_lock.acquire(blocking=False):
            return
        try:
            new_facts = extract_facts(messages, model, thread_id)
            if not new_facts:
                return
            existing = self.storage.get_facts()
            scored = score_facts(new_facts, existing)
            merged = merge_facts(scored, existing)
            self.storage.save_facts(merged)
            logger.info(
                "MemoryEngine[%s] +%d facts (total now %d)",
                thread_id, len(new_facts), len(merged),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryEngine[%s] pipeline failed: %s", thread_id, e)
        finally:
            self._extract_lock.release()

    def get_facts(self):
        return self.storage.get_facts()


# ----------------------------------------------------------------------
# Process-wide singleton
# ----------------------------------------------------------------------

_instance: Optional[MemoryEngine] = None


def get_memory_engine() -> MemoryEngine:
    global _instance
    if _instance is not None:
        return _instance
    # Lazy config load to avoid circular import.
    try:
        from core.models.factory import _load_config
        cfg = (_load_config().get("memory") or {})
    except Exception:
        cfg = {}
    _instance = MemoryEngine(
        token_budget=cfg.get("token_budget", 500),
        min_confidence=cfg.get("min_confidence", 0.7),
        decay_days=cfg.get("decay_days", 30),
        decay_factor=cfg.get("decay_factor", 0.8),
        extraction_model_name=cfg.get("extraction_model", "glm-4-flash"),
    )
    return _instance
