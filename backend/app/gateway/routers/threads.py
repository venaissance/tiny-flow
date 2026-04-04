# backend/app/gateway/routers/threads.py
"""Thread and memory management endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from core.memory.engine import MemoryEngine

logger = logging.getLogger(__name__)
router = APIRouter()

# Thread metadata stored as JSON file
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_THREADS_FILE = _DATA_DIR / "threads.json"


def _load_threads() -> dict[str, dict]:
    """Load thread index from disk."""
    if _THREADS_FILE.exists():
        try:
            return json.loads(_THREADS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_threads(threads: dict[str, dict]) -> None:
    """Persist thread index to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _THREADS_FILE.write_text(json.dumps(threads, ensure_ascii=False, indent=2))


class UpdateThreadRequest(BaseModel):
    title: str | None = None
    first_message: str | None = None
    messages: list[dict] | None = None


@router.post("/threads")
async def create_thread():
    thread_id = uuid4().hex[:12]
    threads = _load_threads()
    threads[thread_id] = {
        "thread_id": thread_id,
        "title": "新对话",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    _save_threads(threads)
    return threads[thread_id]


@router.get("/threads")
async def list_threads():
    threads = _load_threads()
    # Return sorted by updated_at descending
    items = sorted(threads.values(), key=lambda t: t.get("updated_at", ""), reverse=True)
    return items


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, messages: bool = False):
    threads = _load_threads()
    result = threads.get(thread_id, {"thread_id": thread_id, "title": "新对话", "metadata": {}})
    if messages:
        msg_file = _DATA_DIR / f"messages_{thread_id}.json"
        if msg_file.exists():
            try:
                result["messages"] = json.loads(msg_file.read_text())
            except (json.JSONDecodeError, OSError):
                result["messages"] = []
        else:
            result["messages"] = []
    return result


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: str, req: UpdateThreadRequest):
    threads = _load_threads()
    if thread_id not in threads:
        threads[thread_id] = {
            "thread_id": thread_id,
            "title": "新对话",
            "created_at": datetime.now().isoformat(),
        }

    if req.title:
        threads[thread_id]["title"] = req.title
    if req.first_message:
        threads[thread_id]["title"] = _auto_title(req.first_message)
    if req.messages is not None:
        # Save messages to a separate file per thread
        msg_file = _DATA_DIR / f"messages_{thread_id}.json"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        msg_file.write_text(json.dumps(req.messages, ensure_ascii=False))

    threads[thread_id]["updated_at"] = datetime.now().isoformat()
    _save_threads(threads)
    return threads[thread_id]


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    threads = _load_threads()
    threads.pop(thread_id, None)
    _save_threads(threads)
    msg_file = _DATA_DIR / f"messages_{thread_id}.json"
    msg_file.unlink(missing_ok=True)
    return {"status": "deleted"}


def _auto_title(message: str) -> str:
    """Generate a short title from the first user message."""
    # Take first line, truncate to 30 chars
    first_line = message.strip().split("\n")[0].strip()
    if len(first_line) <= 30:
        return first_line
    return first_line[:27] + "..."


# --- Memory endpoints ---

@router.get("/memory")
async def get_memory():
    engine = MemoryEngine()
    facts = engine.get_facts()
    return {
        "facts": [
            {
                "id": f.id,
                "content": f.content,
                "category": f.category,
                "confidence": f.confidence,
            }
            for f in facts
        ],
        "stats": {"total": len(facts)},
    }
