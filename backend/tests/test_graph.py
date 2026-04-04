# backend/tests/test_graph.py
"""Tests for the agent graph."""
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from core.graph.state import GraphState
from core.graph.nodes.router import router_node
from core.graph.nodes.reflector import _is_similar, _format_results
from core.executor.task import TaskResult


class TestReflectorHelpers:
    def test_is_similar_identical(self):
        assert _is_similar("hello world", "hello world") is True

    def test_is_similar_different(self):
        assert _is_similar("hello", "completely different text") is False

    def test_format_results(self):
        results = [
            TaskResult(task_id="1", status="completed", output="Result A"),
            TaskResult(task_id="2", status="failed", error="timeout"),
        ]
        text = _format_results(results)
        assert "Result A" in text
        assert "FAILED" in text


class TestRouterNode:
    def test_fallback_to_direct(self):
        """When model fails, should fallback to direct."""
        model = MagicMock()
        model.bind_tools.side_effect = Exception("mock error")

        state: GraphState = {
            "messages": [HumanMessage(content="hello")],
            "route": None,
            "pending_tasks": [],
            "completed_tasks": [],
            "previous_round_output": "",
            "iteration": 0,
            "memory_context": "",
            "metadata": {},
        }
        result = router_node(state, model)
        assert result["route"] == "direct"
