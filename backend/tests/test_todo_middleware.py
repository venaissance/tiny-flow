"""Tests for TodoMiddleware — TODO plan injection and status reconciliation."""
from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from core.executor.task import TodoItem
from core.middleware.todo import TodoMiddleware


@pytest.fixture
def mw() -> TodoMiddleware:
    return TodoMiddleware()


@pytest.fixture
def sample_todos() -> list[TodoItem]:
    return [
        TodoItem(id="t1", content="Design schema", status="completed"),
        TodoItem(id="t2", content="Implement API", status="in_progress"),
        TodoItem(id="t3", content="Write tests", status="pending"),
    ]


# ---- before_node -----------------------------------------------------------


class TestBeforeNodeInjectsTodos:
    """before_node should append a SystemMessage summarising TODO status."""

    def test_injects_summary_when_todos_exist(
        self, mw: TodoMiddleware, sample_todos: list[TodoItem]
    ):
        state: dict = {
            "messages": [HumanMessage(content="hello")],
            "todos": sample_todos,
        }

        result = mw.before_node(state, "some_node")

        # Original message preserved, plus one new SystemMessage
        assert len(result["messages"]) == 2
        injected = result["messages"][-1]
        assert isinstance(injected, SystemMessage)

        # Verify status icons appear
        assert "\u2705" in injected.content   # completed icon
        assert "\u25c9" in injected.content   # in_progress icon
        assert "\u25cb" in injected.content   # pending icon

        # Verify todo IDs and content appear
        assert "t1" in injected.content
        assert "Design schema" in injected.content

    def test_no_modification_when_no_todos(self, mw: TodoMiddleware):
        state: dict = {"messages": [HumanMessage(content="hi")]}

        result = mw.before_node(state, "node_a")

        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "hi"

    def test_no_modification_when_todos_empty(self, mw: TodoMiddleware):
        state: dict = {"messages": [HumanMessage(content="hi")], "todos": []}

        result = mw.before_node(state, "node_a")

        assert len(result["messages"]) == 1


# ---- after_node ------------------------------------------------------------


class TestAfterNodeUpdatesStatus:
    """after_node should reconcile completed/failed IDs from node output."""

    def test_updates_completed_todo_ids(
        self, mw: TodoMiddleware, sample_todos: list[TodoItem]
    ):
        state: dict = {"todos": sample_todos}
        output: dict = {"completed_todo_ids": ["t3"]}

        result = mw.after_node(state, "node_b", output)

        assert result["todos"] is not None
        updated = {t.id: t for t in result["todos"]}
        assert updated["t3"].status == "completed"
        # Others unchanged
        assert updated["t1"].status == "completed"
        assert updated["t2"].status == "in_progress"

    def test_updates_failed_todo_ids(
        self, mw: TodoMiddleware, sample_todos: list[TodoItem]
    ):
        state: dict = {"todos": sample_todos}
        output: dict = {"failed_todo_ids": ["t2"]}

        result = mw.after_node(state, "node_c", output)

        updated = {t.id: t for t in result["todos"]}
        assert updated["t2"].status == "failed"
        assert updated["t3"].status == "pending"

    def test_no_update_when_ids_missing(
        self, mw: TodoMiddleware, sample_todos: list[TodoItem]
    ):
        state: dict = {"todos": sample_todos}
        output: dict = {"answer": "done"}

        result = mw.after_node(state, "node_d", output)

        # Output passes through unchanged — no "todos" key injected
        assert "todos" not in result
        assert result["answer"] == "done"

    def test_ignores_unknown_todo_ids(
        self, mw: TodoMiddleware, sample_todos: list[TodoItem]
    ):
        state: dict = {"todos": sample_todos}
        output: dict = {"completed_todo_ids": ["nonexistent"]}

        result = mw.after_node(state, "node_e", output)

        # No matching ID, so no status changed, no todos in output
        assert "todos" not in result
