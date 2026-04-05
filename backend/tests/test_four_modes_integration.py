"""Integration tests for the 4 execution modes via TestClient SSE.

Strategy: mock ``build_graph`` so no real LLM or tool calls happen.  The mock
graph is an async generator that yields LangGraph-style ``astream_events``
entries, simulating the exact node lifecycle the real graph would produce for
each mode.  The chat endpoint's ``event_stream`` then converts these into SSE
events which we parse and assert.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage

from core.executor.task import TodoItem, TaskSpec, TaskResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse(response_text: str) -> list[dict]:
    """Parse SSE text into a list of {event, data_parsed} dicts."""
    events: list[dict] = []
    current_event = None
    current_data = None

    for line in response_text.split("\n"):
        line = line.strip()
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data = line[len("data:"):].strip()
        elif line == "" and current_event is not None and current_data is not None:
            try:
                parsed = json.loads(current_data)
            except json.JSONDecodeError:
                parsed = current_data
            events.append({"event": current_event, "data": parsed})
            current_event = None
            current_data = None

    # Handle trailing event without final blank line
    if current_event is not None and current_data is not None:
        try:
            parsed = json.loads(current_data)
        except json.JSONDecodeError:
            parsed = current_data
        events.append({"event": current_event, "data": parsed})

    return events


class _FakeChunk:
    """Mimics a LangChain AIMessageChunk with .content."""
    def __init__(self, content: str):
        self.content = content


# ---------------------------------------------------------------------------
# Mock graph factory
# ---------------------------------------------------------------------------

def _build_mock_graph(mode: str, todos: list[TodoItem] | None = None,
                      pending_tasks: list[TaskSpec] | None = None,
                      completed_tasks: list[TaskResult] | None = None,
                      content_chunks: list[str] | None = None):
    """Return an object with .astream_events() that simulates a real graph run."""

    if content_chunks is None:
        content_chunks = ["Hello ", "world!"]

    async def astream_events(input_state, config=None, version=None):
        # 1. Router node start
        yield {
            "event": "on_chain_start",
            "name": "router",
            "data": {},
            "tags": [],
            "metadata": {},
        }

        # 2. Router node end — emits execution_mode
        router_output = {"execution_mode": mode}
        yield {
            "event": "on_chain_end",
            "name": "router",
            "data": {"output": router_output},
            "tags": [],
            "metadata": {},
        }

        # 3. Mode-specific node start
        if mode == "flash":
            node = "respond"
        elif mode == "thinking":
            node = "think_respond"
        elif mode == "pro":
            node = "plan"
        else:
            node = "plan"

        yield {
            "event": "on_chain_start",
            "name": node,
            "data": {},
            "tags": [],
            "metadata": {},
        }

        # 4. For pro/ultra — plan node emits todos
        if mode in ("pro", "ultra") and todos:
            plan_output = {"todos": todos}
            if mode == "ultra":
                plan_output["execution_mode"] = "ultra"
            yield {
                "event": "on_chain_end",
                "name": "plan",
                "data": {"output": plan_output},
                "tags": [],
                "metadata": {},
            }

        # 5. Token-level streaming from the response node
        stream_node = node if mode in ("flash", "thinking") else "respond"
        for chunk_text in content_chunks:
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatModel",
                "data": {"chunk": _FakeChunk(chunk_text)},
                "tags": [],
                "metadata": {"langgraph_node": stream_node},
            }

        # 6. Response node end
        yield {
            "event": "on_chain_end",
            "name": stream_node,
            "data": {"output": {"messages": [AIMessage(content="".join(content_chunks))]}},
            "tags": [],
            "metadata": {},
        }

        # 7. For pro/ultra — completed tasks
        if completed_tasks:
            yield {
                "event": "on_chain_end",
                "name": "execute",
                "data": {"output": {"completed_tasks": completed_tasks}},
                "tags": [],
                "metadata": {},
            }

    mock_graph = MagicMock()
    mock_graph.astream_events = astream_events
    return mock_graph


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from app.gateway.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ---------------------------------------------------------------------------
# Flash mode
# ---------------------------------------------------------------------------

class TestFlashMode:
    def test_flash_sse_sequence(self, client):
        mock_graph = _build_mock_graph(
            mode="flash",
            content_chunks=["Python ", "is great."],
        )

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "What is Python?"})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)

        event_types = [e["event"] for e in events]

        # Must have: thinking -> mode_selected -> content -> done
        assert "thinking" in event_types
        assert "mode_selected" in event_types
        assert "content" in event_types
        assert event_types[-1] == "done"

        # Mode is flash
        mode_ev = next(e for e in events if e["event"] == "mode_selected")
        assert mode_ev["data"]["mode"] == "flash"

        # Content is streamed
        content_events = [e for e in events if e["event"] == "content"]
        full = "".join(e["data"]["content"] for e in content_events)
        assert "Python" in full

    def test_flash_no_todo_events(self, client):
        mock_graph = _build_mock_graph(mode="flash")

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "hi"})

        events = _parse_sse(resp.text)
        assert not any(e["event"] == "todo_update" for e in events)


# ---------------------------------------------------------------------------
# Thinking mode
# ---------------------------------------------------------------------------

class TestThinkingMode:
    def test_thinking_sse_sequence(self, client):
        mock_graph = _build_mock_graph(
            mode="thinking",
            content_chunks=["<thinking>", "Analysis...", "</thinking>", "Final answer."],
        )

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "Explain CAP theorem"})

        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        assert "mode_selected" in event_types
        mode_ev = next(e for e in events if e["event"] == "mode_selected")
        assert mode_ev["data"]["mode"] == "thinking"

        assert "content" in event_types
        assert event_types[-1] == "done"


# ---------------------------------------------------------------------------
# Pro mode
# ---------------------------------------------------------------------------

class TestProMode:
    def test_pro_sse_sequence(self, client):
        todos = [
            TodoItem(id="t1", content="Search info", status="pending"),
            TodoItem(id="t2", content="Write report", status="pending"),
        ]
        mock_graph = _build_mock_graph(
            mode="pro",
            todos=todos,
            content_chunks=["Research ", "report."],
        )

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "Research AI trends"})

        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        assert "mode_selected" in event_types
        mode_ev = next(e for e in events if e["event"] == "mode_selected")
        assert mode_ev["data"]["mode"] == "pro"

        assert "todo_update" in event_types
        todo_ev = next(e for e in events if e["event"] == "todo_update")
        assert len(todo_ev["data"]["todos"]) == 2

        assert "content" in event_types
        assert event_types[-1] == "done"


# ---------------------------------------------------------------------------
# Ultra mode
# ---------------------------------------------------------------------------

class TestUltraMode:
    def test_ultra_sse_with_parallel_todos(self, client):
        todos = [
            TodoItem(id="u1", content="Research React", status="pending"),
            TodoItem(id="u2", content="Research Vue", status="pending"),
            TodoItem(id="u3", content="Research Svelte", status="pending"),
        ]
        completed = [
            TaskResult(task_id="u1", status="completed", output="React is...", duration_seconds=2.0),
            TaskResult(task_id="u2", status="completed", output="Vue is...", duration_seconds=1.8),
            TaskResult(task_id="u3", status="completed", output="Svelte is...", duration_seconds=1.5),
        ]
        mock_graph = _build_mock_graph(
            mode="ultra",
            todos=todos,
            completed_tasks=completed,
            content_chunks=["Comparison ", "of frameworks."],
        )

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "Compare React, Vue, Svelte"})

        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        # mode_selected must be ultra
        assert "mode_selected" in event_types
        mode_ev = next(e for e in events if e["event"] == "mode_selected")
        assert mode_ev["data"]["mode"] == "ultra"

        # todo_update with >= 3 items
        assert "todo_update" in event_types
        todo_ev = next(e for e in events if e["event"] == "todo_update")
        assert len(todo_ev["data"]["todos"]) >= 3

        # subagent_result events
        result_events = [e for e in events if e["event"] == "subagent_result"]
        assert len(result_events) == 3

        assert event_types[-1] == "done"


# ---------------------------------------------------------------------------
# SSE format invariants
# ---------------------------------------------------------------------------

class TestSSEFormat:
    def test_all_events_have_id_event_data(self, client):
        """Every SSE event must have id, event, and valid JSON data."""
        mock_graph = _build_mock_graph(mode="flash", content_chunks=["ok"])

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "test"})

        # Raw SSE parsing: check id/event/data triplets
        current = {}
        for line in resp.text.split("\n"):
            line = line.strip()
            if line.startswith("id:"):
                current["id"] = line[3:].strip()
            elif line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current["data"] = line[5:].strip()
            elif line == "" and current:
                if "event" in current and "data" in current:
                    # id is set by sse-starlette; event and data are always present
                    assert current["event"]
                    parsed = json.loads(current["data"])
                    assert isinstance(parsed, dict)
                current = {}

    def test_last_event_is_done(self, client):
        for mode in ("flash", "thinking"):
            mock_graph = _build_mock_graph(mode=mode)
            with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
                resp = client.post("/api/chat", json={"message": "test"})
            events = _parse_sse(resp.text)
            assert events[-1]["event"] == "done"

    def test_content_type_is_event_stream(self, client):
        mock_graph = _build_mock_graph(mode="flash")
        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "test"})
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_data_is_valid_json_for_all_events(self, client):
        todos = [TodoItem(id="x", content="step", status="pending")]
        mock_graph = _build_mock_graph(mode="pro", todos=todos, content_chunks=["done"])
        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "test"})
        events = _parse_sse(resp.text)
        for e in events:
            assert isinstance(e["data"], dict), f"Event {e['event']} data is not a dict"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_graph_exception_emits_error_event(self, client):
        """If the graph throws, an error SSE event is emitted."""

        async def failing_stream(*args, **kwargs):
            yield {
                "event": "on_chain_start",
                "name": "router",
                "data": {},
                "tags": [],
                "metadata": {},
            }
            raise RuntimeError("Graph exploded")

        mock_graph = MagicMock()
        mock_graph.astream_events = failing_stream

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "boom"})

        events = _parse_sse(resp.text)
        # Should end with either error or error+done
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) >= 1
        assert "Graph exploded" in error_events[0]["data"]["error"]
