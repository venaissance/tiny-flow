# backend/core/compaction/async_runner.py
"""Async background context compaction.

Design goals (vs Hermes's synchronous compressor):
  * Main agent turn NEVER awaits the summarizer LLM — summarization
    runs in a fire-and-forget asyncio task after the user's SSE stream
    has finished.
  * We do NOT mutate LangGraph state. Instead we maintain an external
    per-thread record (`summary + summarized_up_to_idx`) that respond
    nodes consult to know which tail slice to show the model. Keeps
    state reducer semantics pristine and dodges the RemoveMessage
    ID-matching flakiness.
  * Per-thread asyncio.Lock prevents concurrent summarizations on the
    same thread; a content hash dedups no-op calls.
  * Summary tokens are generated via a model tagged
    `compaction_summarizer` so the SSE handler filters them out of the
    user-facing content stream (see chat.py).
  * A high-threshold synchronous middleware still exists as a safety
    net (see graph/builder.py `_build_compaction_middleware`) in case
    the background worker misses a thread entirely.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).parent.parent.parent / "data" / "compaction.json"


@dataclass(frozen=True)
class CompactionRecord:
    summary: str
    summarized_up_to: int  # index into the thread's messages list
    generated_at: float


class AsyncCompactor:
    def __init__(
        self,
        *,
        threshold: int = 6,
        retention_window: int = 4,
        summarizer_model_name: str = "glm-4-flash",
        summary_max_chars: int = 800,
        store_path: str | Path | None = None,
    ) -> None:
        self.threshold = threshold
        self.retention_window = retention_window
        self.summarizer_model_name = summarizer_model_name
        self.summary_max_chars = summary_max_chars
        self.store_path = Path(store_path or _DEFAULT_STORE_PATH)
        self._io_lock = threading.Lock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._hashes: dict[str, str] = {}
        self._records: dict[str, CompactionRecord] = {}
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Disk persistence
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Hydrate _records from the JSON store (if any) on boot."""
        try:
            if not self.store_path.exists():
                return
            with self.store_path.open(encoding="utf-8") as f:
                data = json.load(f) or {}
            records = data.get("records") or {}
            for tid, rec in records.items():
                try:
                    self._records[tid] = CompactionRecord(
                        summary=rec.get("summary", ""),
                        summarized_up_to=int(rec.get("summarized_up_to", 0)),
                        generated_at=float(rec.get("generated_at", 0.0)),
                    )
                except Exception:
                    continue
            logger.info(
                "AsyncCompactor loaded %d persisted records from %s",
                len(self._records), self.store_path,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("AsyncCompactor load failed: %s", e)

    def _save_to_disk(self) -> None:
        """Atomic write of the full records map. Called after each
        successful compaction — cheap because state is small."""
        with self._io_lock:
            try:
                self.store_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "version": "1.0",
                    "records": {tid: asdict(r) for tid, r in self._records.items()},
                }
                tmp = self.store_path.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp.rename(self.store_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("AsyncCompactor save failed: %s", e)

    def forget_thread(self, thread_id: str) -> None:
        """Drop a thread's summary — call when the thread is deleted."""
        self._records.pop(thread_id, None)
        self._hashes.pop(thread_id, None)
        self._save_to_disk()

    # ------------------------------------------------------------------
    # Read API (called sync from main agent)
    # ------------------------------------------------------------------

    def get(self, thread_id: str) -> Optional[CompactionRecord]:
        return self._records.get(thread_id)

    def get_summary(self, thread_id: str) -> Optional[str]:
        rec = self._records.get(thread_id)
        return rec.summary if rec else None

    def effective_messages(
        self, thread_id: str, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """Return the tail slice the model should actually see.

        If a summary exists covering the head of `messages`, return the
        last `retention_window` items (plus any newer messages since
        the summary was generated). Otherwise return all messages.
        """
        rec = self._records.get(thread_id)
        if not rec:
            return list(messages)
        if len(messages) <= self.retention_window:
            return list(messages)
        # Keep everything after the summarized zone; minimum = retention_window.
        cutoff = max(rec.summarized_up_to, len(messages) - self.retention_window)
        cutoff = min(cutoff, len(messages) - self.retention_window)
        return list(messages[cutoff:])

    # ------------------------------------------------------------------
    # Write API (fire-and-forget from SSE stream `finally`)
    # ------------------------------------------------------------------

    def schedule(self, thread_id: str, graph: Any, config: dict) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("AsyncCompactor.schedule called outside event loop")
            return
        loop.create_task(self._run(thread_id, graph, config))

    async def _run(self, thread_id: str, graph: Any, config: dict) -> None:
        lock = self._lock_for(thread_id)
        if lock.locked():
            return
        async with lock:
            started = time.perf_counter()
            try:
                snapshot = graph.get_state(config)
                messages = list((snapshot.values or {}).get("messages", []))
            except Exception as e:  # noqa: BLE001
                logger.warning("AsyncCompactor[%s] get_state failed: %s", thread_id, e)
                return

            if len(messages) <= self.threshold:
                return

            content_hash = self._hash_messages(messages)
            if self._hashes.get(thread_id) == content_hash:
                return

            compaction_zone = messages[: -self.retention_window]

            prior = self._records.get(thread_id)
            prior_text = prior.summary if prior else ""

            try:
                from core.middleware.context_compaction import create_llm_summarizer
            except Exception as e:  # noqa: BLE001
                logger.warning("AsyncCompactor: import create_llm_summarizer failed: %s", e)
                return
            summarizer = create_llm_summarizer(
                model_name=self.summarizer_model_name,
                max_chars=self.summary_max_chars,
            )

            try:
                new_summary = await asyncio.to_thread(
                    summarizer, prior_text, compaction_zone
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("AsyncCompactor[%s] summarizer failed: %s", thread_id, e)
                return

            self._hashes[thread_id] = content_hash
            self._records[thread_id] = CompactionRecord(
                summary=new_summary,
                summarized_up_to=len(messages) - self.retention_window,
                generated_at=time.time(),
            )
            # Persist so the summary survives backend restarts / reloads.
            self._save_to_disk()

            dt = time.perf_counter() - started
            logger.warning(
                "AsyncCompactor[%s] summary ready: %d → tail %d (summary %d chars, %.2fs bg)",
                thread_id, len(messages), self.retention_window,
                len(new_summary), dt,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _lock_for(self, thread_id: str) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    @staticmethod
    def _hash_messages(messages: list[BaseMessage]) -> str:
        h = hashlib.sha256()
        for m in messages:
            h.update(type(m).__name__.encode())
            h.update(b"\0")
            h.update(str(getattr(m, "content", "") or "").encode("utf-8", "replace"))
            h.update(b"\0")
        return h.hexdigest()


# ----------------------------------------------------------------------
# Singleton accessor
# ----------------------------------------------------------------------

_instance: Optional[AsyncCompactor] = None


def get_async_compactor() -> AsyncCompactor:
    global _instance
    if _instance is not None:
        return _instance
    from core.models.factory import _load_config

    cfg = (_load_config().get("compaction") or {})
    _instance = AsyncCompactor(
        threshold=cfg.get("max_messages", 6),
        retention_window=cfg.get("retention_window", 4),
        summarizer_model_name=cfg.get("summary_model", "glm-4-flash"),
        summary_max_chars=cfg.get("summary_max_chars", 800),
    )
    return _instance


def ensure_message_ids(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Assign an id to any BaseMessage that lacks one. Kept for forward
    compatibility — the current design does not rely on IDs, but the
    first-class checkpointer reducer does, and downstream tooling may."""
    for m in messages:
        if not getattr(m, "id", None):
            try:
                m.id = str(uuid.uuid4())
            except Exception:
                pass
    return messages
