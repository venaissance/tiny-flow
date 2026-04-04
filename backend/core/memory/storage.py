"""JSON-based memory storage with thread safety."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock


@dataclass
class Fact:
    """A single memory fact."""
    id: str = field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:8]}")
    content: str = ""
    category: str = "context"
    confidence: float = 0.5
    source_thread: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_verified: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    replaced_by: str | None = None


class MemoryStorage:
    """Thread-safe JSON file storage for memory facts."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._lock = Lock()
        self._ensure_exists()

    def _ensure_exists(self):
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._write({"version": "1.0", "facts": []})

    def _read(self) -> dict:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"version": "1.0", "facts": []}

    def _write(self, data: dict):
        tmp = self.file_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self.file_path)

    def get_facts(self, include_replaced: bool = False) -> list[Fact]:
        with self._lock:
            data = self._read()
            facts = [Fact(**f) for f in data.get("facts", [])]
            if not include_replaced:
                facts = [f for f in facts if f.replaced_by is None]
            return facts

    def add_fact(self, fact: Fact):
        with self._lock:
            data = self._read()
            data["facts"].append(asdict(fact))
            self._write(data)

    def save_facts(self, facts: list[Fact]):
        with self._lock:
            data = self._read()
            data["facts"] = [asdict(f) for f in facts]
            self._write(data)

    def apply_decay(self, decay_days: int = 30, decay_factor: float = 0.8):
        with self._lock:
            data = self._read()
            now = datetime.now()
            updated = False
            for f in data.get("facts", []):
                if f.get("replaced_by"):
                    continue
                last = datetime.fromisoformat(f.get("last_verified", now.isoformat()))
                days_old = (now - last).days
                if days_old >= decay_days and f.get("access_count", 0) < 3:
                    cycles = days_old // decay_days
                    f["confidence"] = f.get("confidence", 0.5) * (decay_factor ** cycles)
                    updated = True
            if updated:
                self._write(data)
