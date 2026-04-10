"""State machine tests — verify GraphState transitions through node calls."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tests.conftest import MockChatModel, make_state
from core.executor.task import TaskSpec, TaskResult, TodoItem


# ---------------------------------------------------------------------------
# Router node
# ---------------------------------------------------------------------------

# Patch skill registry/router so router_node never hits real skills.
@pytest.fixture(autouse=True)
def _patch_skills():
    with patch("core.skills.registry.get_all_skills", return_value=[]), \
         patch("core.skills.router.keyword_filter", return_value=[]):
        yield


class TestInitialState:
    """Verify the default state factory values."""

    def test_route_is_none(self):
        state = make_state()
        assert state["route"] is None

    def test_execution_mode_empty(self):
        state = make_state()
        assert state["execution_mode"] == ""

    def test_iteration_zero(self):
        state = make_state()
        assert state["iteration"] == 0

    def test_pending_tasks_empty(self):
        state = make_state()
        assert state["pending_tasks"] == []

    def test_completed_tasks_empty(self):
        state = make_state()
        assert state["completed_tasks"] == []


class TestRouterNode:
    """Router node should set route + execution_mode via keyword fallback."""

    def _run_router(self, query: str) -> dict:
        from core.graph.nodes.router import router_node
        # MockChatModel returns plain text (no tool_calls), so the router
        # will fall through to keyword-based fallback every time.
        model = MockChatModel(responses=["I don't know"])
        state = make_state(message=query)
        return router_node(state, model)

    def test_flash_route(self):
        result = self._run_router("你好")
        assert result["route"] == "direct"
        assert result["execution_mode"] == "flash"

    def test_thinking_route(self):
        result = self._run_router("为什么天空是蓝色的？")
        assert result["route"] == "direct"
        assert result["execution_mode"] == "thinking"

    def test_pro_route(self):
        result = self._run_router("搜索最新的 Python 教程")
        assert result["route"] == "subagent"
        assert result["execution_mode"] == "pro"

    def test_ultra_route(self):
        result = self._run_router("分别总结这两篇文章：A、B")
        assert result["route"] == "subagent"
        assert result["execution_mode"] == "ultra"

    def test_route_values_in_allowed_set(self):
        """Any route value returned must be one of the known values."""
        allowed_routes = {"direct", "subagent"}
        allowed_modes = {"flash", "thinking", "pro", "ultra"}
        for query in ["你好", "为什么", "搜索资料", "分别总结 A、B"]:
            result = self._run_router(query)
            assert result["route"] in allowed_routes, f"Unexpected route: {result['route']}"
            assert result["execution_mode"] in allowed_modes, f"Unexpected mode: {result['execution_mode']}"


# ---------------------------------------------------------------------------
# Plan node
# ---------------------------------------------------------------------------

class TestPlanNode:
    """Plan node decomposes tasks and may upgrade pro -> ultra."""

    def test_creates_todos_with_pending_status(self):
        from core.graph.nodes.plan import plan_node

        plan_json = json.dumps({"steps": ["step A", "step B"], "parallel": False})
        model = MockChatModel(responses=[plan_json])
        state = make_state(execution_mode="pro")

        result = plan_node(state, model)

        assert "todos" in result
        assert len(result["todos"]) == 2
        for todo in result["todos"]:
            assert isinstance(todo, TodoItem)
            assert todo.status == "pending"

    def test_parallel_true_upgrades_pro_to_ultra(self):
        from core.graph.nodes.plan import plan_node

        plan_json = json.dumps({"steps": ["A", "B"], "parallel": True})
        model = MockChatModel(responses=[plan_json])
        state = make_state(execution_mode="pro")

        result = plan_node(state, model)

        assert result.get("execution_mode") == "ultra"

    def test_parallel_true_single_step_no_upgrade(self):
        """A single step, even if parallel=true, should NOT upgrade."""
        from core.graph.nodes.plan import plan_node

        plan_json = json.dumps({"steps": ["only one"], "parallel": True})
        model = MockChatModel(responses=[plan_json])
        state = make_state(execution_mode="pro")

        result = plan_node(state, model)

        # No upgrade: only 1 step
        assert result.get("execution_mode") is None

    def test_parallel_false_no_upgrade(self):
        from core.graph.nodes.plan import plan_node

        plan_json = json.dumps({"steps": ["A", "B"], "parallel": False})
        model = MockChatModel(responses=[plan_json])
        state = make_state(execution_mode="pro")

        result = plan_node(state, model)

        assert "execution_mode" not in result

    def test_fallback_on_bad_json(self):
        """If LLM returns garbage, plan_node should not crash."""
        from core.graph.nodes.plan import plan_node

        model = MockChatModel(responses=["this is not json"])
        state = make_state(message="do something", execution_mode="pro")

        result = plan_node(state, model)

        # Falls back to a single TODO containing the user query
        assert len(result["todos"]) == 1
        assert result["todos"][0].content == "do something"


# ---------------------------------------------------------------------------
# Execute node
# ---------------------------------------------------------------------------

class TestExecuteNode:
    """Execute node increments iteration and moves tasks."""

    def _make_task(self, desc="task1") -> TaskSpec:
        return TaskSpec(type="skill_inject", description=desc)

    def test_increments_iteration(self):
        from core.graph.nodes.execute import execute_node

        task = self._make_task()
        state = make_state(pending_tasks=[task], iteration=0, execution_mode="pro")
        model = MockChatModel()

        result = execute_node(state, model)

        assert result["iteration"] == 1

    def test_moves_task_to_completed(self):
        from core.graph.nodes.execute import execute_node

        task = self._make_task()
        state = make_state(
            pending_tasks=[task],
            completed_tasks=[],
            execution_mode="pro",
        )
        model = MockChatModel()

        result = execute_node(state, model)

        assert len(result["completed_tasks"]) == 1
        assert result["completed_tasks"][0].task_id == task.id
        assert result["completed_tasks"][0].status == "completed"

    def test_pro_mode_executes_one_at_a_time(self):
        """Pro mode should execute only the first task, leaving the rest pending."""
        from core.graph.nodes.execute import execute_node

        t1 = self._make_task("task1")
        t2 = self._make_task("task2")
        state = make_state(
            pending_tasks=[t1, t2],
            completed_tasks=[],
            execution_mode="pro",
        )
        model = MockChatModel()

        result = execute_node(state, model)

        assert len(result["completed_tasks"]) == 1
        assert len(result["pending_tasks"]) == 1
        assert result["pending_tasks"][0].id == t2.id

    def test_empty_pending_still_increments(self):
        from core.graph.nodes.execute import execute_node

        state = make_state(pending_tasks=[], iteration=2, execution_mode="pro")
        model = MockChatModel()

        result = execute_node(state, model)

        assert result["iteration"] == 3
        assert result["pending_tasks"] == []

    def test_updates_todo_status(self):
        """Execute node should mark corresponding todo item as completed."""
        from core.graph.nodes.execute import execute_node

        task = self._make_task()
        todo = TodoItem(content="task1", status="pending")
        state = make_state(
            pending_tasks=[task],
            todos=[todo],
            execution_mode="pro",
        )
        model = MockChatModel()

        result = execute_node(state, model)

        # The todo list in the result should have the first item completed
        updated_todos = result["todos"]
        assert updated_todos[0].status == "completed"


# ---------------------------------------------------------------------------
# Reflector node
# ---------------------------------------------------------------------------

class TestReflectorNode:
    """Reflector decides whether to loop or return a final response."""

    def test_no_pending_with_completed_returns_final(self):
        from core.graph.nodes.reflector import reflector_node

        completed = [TaskResult(task_id="t1", status="completed", output="Done.")]
        state = make_state(
            pending_tasks=[],
            completed_tasks=completed,
            iteration=1,
            execution_mode="pro",
        )
        model = MockChatModel()

        result = reflector_node(state, model, max_iterations=3)

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert "Done." in result["messages"][0].content

    def test_pending_tasks_returns_continue(self):
        from core.graph.nodes.reflector import reflector_node

        pending = [TaskSpec(description="remaining")]
        state = make_state(
            pending_tasks=pending,
            completed_tasks=[],
            iteration=1,
            execution_mode="pro",
        )
        model = MockChatModel()

        result = reflector_node(state, model, max_iterations=3)

        assert result.get("route") == "continue_execute"

    def test_ultra_mode_passes_through(self):
        """Ultra mode should return empty dict (merge already handled it)."""
        from core.graph.nodes.reflector import reflector_node

        state = make_state(
            pending_tasks=[],
            completed_tasks=[],
            execution_mode="ultra",
        )
        model = MockChatModel()

        result = reflector_node(state, model, max_iterations=3)

        assert result == {"route": "done"}

    def test_max_iterations_terminates(self):
        from core.graph.nodes.reflector import reflector_node

        completed = [TaskResult(task_id="t1", status="completed", output="partial")]
        state = make_state(
            pending_tasks=[],
            completed_tasks=completed,
            iteration=3,
            execution_mode="pro",
        )
        model = MockChatModel()

        result = reflector_node(state, model, max_iterations=3)

        # Should produce a final response, not loop
        assert "messages" in result


# ---------------------------------------------------------------------------
# Respond and ThinkRespond nodes (simple pass-through)
# ---------------------------------------------------------------------------

class TestRespondNode:
    def test_returns_ai_message(self):
        from core.graph.nodes.respond import respond_node

        model = MockChatModel(responses=["hello back"])
        state = make_state()

        result = respond_node(state, model)

        assert "messages" in result
        assert result["messages"][0].content == "hello back"


class TestThinkRespondNode:
    def test_returns_ai_message(self):
        from core.graph.nodes.think_respond import think_respond_node

        model = MockChatModel(responses=["<thinking>reason</thinking>\nanswer"])
        state = make_state()

        result = think_respond_node(state, model)

        assert "messages" in result
        assert "<thinking>" in result["messages"][0].content
