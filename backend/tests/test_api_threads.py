"""Tests for thread CRUD endpoints and memory API."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with _DATA_DIR / _THREADS_FILE redirected to tmp_path."""
    import app.gateway.routers.threads as threads_mod

    monkeypatch.setattr(threads_mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(threads_mod, "_THREADS_FILE", tmp_path / "threads.json")

    from app.gateway.app import app
    from fastapi.testclient import TestClient

    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/threads
# ---------------------------------------------------------------------------

class TestCreateThread:
    def test_create_returns_thread_id_and_default_title(self, client):
        resp = client.post("/api/threads")
        assert resp.status_code == 200
        body = resp.json()
        assert "thread_id" in body
        assert len(body["thread_id"]) == 12
        assert body["title"] == "\u65b0\u5bf9\u8bdd"  # "新对话"

    def test_create_includes_timestamps(self, client):
        body = client.post("/api/threads").json()
        assert "created_at" in body
        assert "updated_at" in body

    def test_create_multiple_threads_unique_ids(self, client):
        ids = {client.post("/api/threads").json()["thread_id"] for _ in range(5)}
        assert len(ids) == 5


# ---------------------------------------------------------------------------
# GET /api/threads
# ---------------------------------------------------------------------------

class TestListThreads:
    def test_empty_list_initially(self, client):
        resp = client.get("/api/threads")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_populated_after_create(self, client):
        client.post("/api/threads")
        client.post("/api/threads")
        items = client.get("/api/threads").json()
        assert len(items) == 2

    def test_sorted_by_updated_at_descending(self, client):
        t1 = client.post("/api/threads").json()
        t2 = client.post("/api/threads").json()
        # Update t1 so its updated_at is newer
        client.patch(f"/api/threads/{t1['thread_id']}", json={"title": "Updated"})
        items = client.get("/api/threads").json()
        assert items[0]["thread_id"] == t1["thread_id"]


# ---------------------------------------------------------------------------
# GET /api/threads/{id}
# ---------------------------------------------------------------------------

class TestGetThread:
    def test_get_existing_thread(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        resp = client.get(f"/api/threads/{tid}")
        assert resp.status_code == 200
        assert resp.json()["thread_id"] == tid

    def test_get_nonexistent_thread_returns_default(self, client):
        resp = client.get("/api/threads/nonexistent")
        body = resp.json()
        assert body["thread_id"] == "nonexistent"
        assert body["title"] == "\u65b0\u5bf9\u8bdd"

    def test_get_without_messages_flag(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        body = client.get(f"/api/threads/{tid}").json()
        assert "messages" not in body

    def test_get_with_messages_flag_empty(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        body = client.get(f"/api/threads/{tid}?messages=true").json()
        assert body["messages"] == []

    def test_get_with_messages_flag_populated(self, client, tmp_path):
        tid = client.post("/api/threads").json()["thread_id"]
        msgs = [{"role": "user", "content": "hello"}]
        client.patch(f"/api/threads/{tid}", json={"messages": msgs})
        body = client.get(f"/api/threads/{tid}?messages=true").json()
        assert body["messages"] == msgs


# ---------------------------------------------------------------------------
# PATCH /api/threads/{id}
# ---------------------------------------------------------------------------

class TestUpdateThread:
    def test_update_title(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        resp = client.patch(f"/api/threads/{tid}", json={"title": "My Chat"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "My Chat"

    def test_update_creates_thread_if_missing(self, client):
        resp = client.patch("/api/threads/brand_new", json={"title": "Created"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Created"

    def test_save_messages_creates_file(self, client, tmp_path):
        tid = client.post("/api/threads").json()["thread_id"]
        msgs = [{"role": "assistant", "content": "hi"}]
        client.patch(f"/api/threads/{tid}", json={"messages": msgs})
        msg_file = tmp_path / f"messages_{tid}.json"
        assert msg_file.exists()
        assert json.loads(msg_file.read_text()) == msgs

    def test_auto_title_via_first_message(self, client):
        """When first_message is sent, _auto_title generates a title via LLM."""
        tid = client.post("/api/threads").json()["thread_id"]

        mock_model = MagicMock()
        mock_model.invoke.return_value = AIMessage(content="Python GIL \u7b80\u4ecb")

        with patch("core.models.factory.create_chat_model", return_value=mock_model):
            resp = client.patch(
                f"/api/threads/{tid}",
                json={"first_message": "Python \u7684 GIL \u662f\u4ec0\u4e48\uff1f"},
            )
        assert resp.json()["title"] == "Python GIL \u7b80\u4ecb"

    def test_auto_title_fallback_on_model_failure(self, client):
        """When LLM fails, _auto_title falls back to truncation."""
        tid = client.post("/api/threads").json()["thread_id"]

        with patch("core.models.factory.create_chat_model", side_effect=Exception("boom")):
            resp = client.patch(
                f"/api/threads/{tid}",
                json={"first_message": "a" * 50},
            )
        title = resp.json()["title"]
        assert title == "a" * 27 + "..."

    def test_auto_title_fallback_short_message(self, client):
        """Short messages are returned as-is when LLM fails."""
        tid = client.post("/api/threads").json()["thread_id"]

        with patch("core.models.factory.create_chat_model", side_effect=Exception("boom")):
            resp = client.patch(
                f"/api/threads/{tid}",
                json={"first_message": "short title"},
            )
        assert resp.json()["title"] == "short title"

    def test_auto_title_rejects_too_long_llm_output(self, client):
        """If LLM returns a title > 30 chars, fall back to truncation."""
        tid = client.post("/api/threads").json()["thread_id"]

        mock_model = MagicMock()
        mock_model.invoke.return_value = AIMessage(content="x" * 40)

        with patch("core.models.factory.create_chat_model", return_value=mock_model):
            resp = client.patch(
                f"/api/threads/{tid}",
                json={"first_message": "y" * 50},
            )
        # Falls through to truncation because LLM title is > 30 chars
        title = resp.json()["title"]
        assert title == "y" * 27 + "..."

    def test_auto_title_rejects_too_short_llm_output(self, client):
        """If LLM returns a 1-char title, fall back to truncation."""
        tid = client.post("/api/threads").json()["thread_id"]

        mock_model = MagicMock()
        mock_model.invoke.return_value = AIMessage(content="X")

        with patch("core.models.factory.create_chat_model", return_value=mock_model):
            resp = client.patch(
                f"/api/threads/{tid}",
                json={"first_message": "What is X?"},
            )
        # Falls through to truncation because LLM title is < 2 chars
        assert resp.json()["title"] == "What is X?"


# ---------------------------------------------------------------------------
# DELETE /api/threads/{id}
# ---------------------------------------------------------------------------

class TestDeleteThread:
    def test_delete_removes_from_list(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        client.delete(f"/api/threads/{tid}")
        items = client.get("/api/threads").json()
        assert all(t["thread_id"] != tid for t in items)

    def test_delete_returns_status(self, client):
        tid = client.post("/api/threads").json()["thread_id"]
        resp = client.delete(f"/api/threads/{tid}")
        assert resp.json() == {"status": "deleted"}

    def test_delete_removes_message_file(self, client, tmp_path):
        tid = client.post("/api/threads").json()["thread_id"]
        msgs = [{"role": "user", "content": "bye"}]
        client.patch(f"/api/threads/{tid}", json={"messages": msgs})
        msg_file = tmp_path / f"messages_{tid}.json"
        assert msg_file.exists()
        client.delete(f"/api/threads/{tid}")
        assert not msg_file.exists()

    def test_delete_nonexistent_is_noop(self, client):
        resp = client.delete("/api/threads/does_not_exist")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}


# ---------------------------------------------------------------------------
# GET /api/memory
# ---------------------------------------------------------------------------

class TestMemoryEndpoint:
    def test_get_memory_returns_facts_list(self, client, tmp_path, monkeypatch):
        """Memory endpoint returns a structured response."""
        from core.memory.storage import Fact

        mock_engine = MagicMock()
        mock_engine.get_facts.return_value = [
            Fact(id="f1", content="user likes Python", category="preference", confidence=0.9),
        ]

        with patch("app.gateway.routers.threads.MemoryEngine", return_value=mock_engine):
            resp = client.get("/api/memory")

        assert resp.status_code == 200
        body = resp.json()
        assert "facts" in body
        assert "stats" in body
        assert body["stats"]["total"] == 1
        assert body["facts"][0]["content"] == "user likes Python"

    def test_get_memory_empty(self, client, monkeypatch):
        mock_engine = MagicMock()
        mock_engine.get_facts.return_value = []

        with patch("app.gateway.routers.threads.MemoryEngine", return_value=mock_engine):
            resp = client.get("/api/memory")

        body = resp.json()
        assert body["facts"] == []
        assert body["stats"]["total"] == 0
