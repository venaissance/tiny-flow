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
    # Drop the persisted compaction summary for this thread.
    try:
        from core.compaction import get_async_compactor
        get_async_compactor().forget_thread(thread_id)
    except Exception:  # noqa: BLE001
        pass
    return {"status": "deleted"}


def _auto_title(message: str) -> str:
    """Generate a concise title using LLM, with truncation fallback."""
    try:
        from core.models.factory import create_chat_model
        from langchain_core.messages import HumanMessage, SystemMessage

        model = create_chat_model()
        response = model.invoke([
            SystemMessage(content=(
                "根据用户的第一条消息，生成一个简洁的对话标题（5-15个字）。"
                "只输出标题文字，不要引号、标点或解释。"
            )),
            HumanMessage(content=message),
        ])
        title = response.content.strip().strip('"\'""')
        if 2 <= len(title) <= 30:
            return title
    except Exception:
        pass
    # Fallback: truncate
    first_line = message.strip().split("\n")[0].strip()
    if len(first_line) <= 30:
        return first_line
    return first_line[:27] + "..."


# --- Memory endpoints ---

class MemoryFactUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    confidence: float | None = None


@router.get("/memory")
async def get_memory():
    from core.memory.engine import get_memory_engine
    from core.memory.scorer import WEIGHTS
    engine = get_memory_engine()
    facts = engine.get_facts()
    return {
        "facts": [
            {
                "id": f.id,
                "content": f.content,
                "category": f.category,
                "confidence": round(f.confidence, 3),
                "source_thread": f.source_thread,
                "created_at": f.created_at,
                "last_verified": f.last_verified,
                "access_count": f.access_count,
                "score_breakdown": f.score_breakdown or {},
            }
            for f in facts
        ],
        "stats": {"total": len(facts)},
        "scoring": {
            "weights": WEIGHTS,
            "formula": "confidence = 0.3·explicitness + 0.4·repetition + 0.3·consistency",
            "components": {
                "explicitness": "事实越具体/越长 → 越可信（>20字=0.9, 否则=0.5）",
                "repetition": "多次提到相似信息 → 越可信（每次相似度>0.5 +0.3，上限1.0）",
                "consistency": "与已有同类记忆不冲突 → 越可信（无冲突=1.0, 疑似冲突=0.5）",
            },
        },
    }


@router.delete("/memory/{fact_id}")
async def delete_memory_fact(fact_id: str):
    from core.memory.engine import get_memory_engine
    engine = get_memory_engine()
    removed = engine.storage.delete_fact(fact_id)
    return {"removed": removed, "fact_id": fact_id}


@router.patch("/memory/{fact_id}")
async def update_memory_fact(fact_id: str, payload: MemoryFactUpdate):
    from core.memory.engine import get_memory_engine
    engine = get_memory_engine()
    fields = {k: v for k, v in payload.dict().items() if v is not None}
    if not fields:
        return {"updated": False, "reason": "no fields provided"}
    updated = engine.storage.update_fact(fact_id, **fields)
    if updated is None:
        return {"updated": False, "reason": "not found"}
    return {
        "updated": True,
        "fact": {
            "id": updated.id,
            "content": updated.content,
            "category": updated.category,
            "confidence": round(updated.confidence, 3),
            "score_breakdown": updated.score_breakdown or {},
        },
    }


@router.delete("/memory")
async def clear_memory():
    from core.memory.engine import get_memory_engine
    engine = get_memory_engine()
    engine.storage.clear_all()
    return {"cleared": True}
