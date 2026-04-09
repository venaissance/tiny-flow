# tests/test_graph_nodes.py
"""P0 tests for all graph node pure functions."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tests.conftest import MockChatModel, make_state
from core.executor.task import TaskSpec, TaskResult, TodoItem


# ═══════════════════════════════════════════════════════════════════════════
# plan_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.plan import plan_node, _extract_user_query, _parse_plan


class TestParsePlan:
    def test_plain_json(self):
        steps, parallel = _parse_plan('{"steps": ["a", "b"], "parallel": true}')
        assert steps == ["a", "b"]
        assert parallel is True

    def test_markdown_wrapped_json(self):
        text = '```json\n{"steps": ["x"], "parallel": false}\n```'
        steps, parallel = _parse_plan(text)
        assert steps == ["x"]
        assert parallel is False

    def test_empty_steps_raises(self):
        with pytest.raises(ValueError, match="Empty or invalid"):
            _parse_plan('{"steps": [], "parallel": false}')

    def test_non_list_steps_raises(self):
        with pytest.raises(ValueError, match="Empty or invalid"):
            _parse_plan('{"steps": "not a list", "parallel": false}')


class TestExtractUserQuery:
    def test_returns_last_human_message(self):
        state = make_state("first")
        state["messages"].append(AIMessage(content="reply"))
        state["messages"].append(HumanMessage(content="second"))
        assert _extract_user_query(state) == "second"

    def test_empty_messages(self):
        state = make_state()
        state["messages"] = []
        assert _extract_user_query(state) == ""


class TestPlanNode:
    def test_normal_sequential_plan(self):
        llm = MockChatModel(['{"steps": ["step1", "step2"], "parallel": false}'])
        result = plan_node(make_state("do something", execution_mode="pro"), llm)
        assert len(result["todos"]) == 2
        assert result["todos"][0].content == "step1"
        # Not parallel, so no mode upgrade
        assert "execution_mode" not in result

    def test_parallel_plan_upgrades_pro_to_ultra(self):
        llm = MockChatModel(['{"steps": ["a", "b"], "parallel": true}'])
        result = plan_node(make_state("parallel task", execution_mode="pro"), llm)
        assert result["execution_mode"] == "ultra"
        assert result["metadata"]["subtasks"] == ["a", "b"]

    def test_parallel_single_step_no_upgrade(self):
        """parallel=true but only 1 step should NOT upgrade."""
        llm = MockChatModel(['{"steps": ["only one"], "parallel": true}'])
        result = plan_node(make_state("single", execution_mode="pro"), llm)
        assert "execution_mode" not in result

    def test_parse_failure_falls_back_to_user_query(self):
        llm = MockChatModel(["not valid json at all"])
        result = plan_node(make_state("my query", execution_mode="pro"), llm)
        assert len(result["todos"]) == 1
        assert result["todos"][0].content == "my query"

    def test_ultra_mode_preserves_subtasks_metadata(self):
        llm = MockChatModel(['{"steps": ["x", "y"], "parallel": false}'])
        result = plan_node(make_state("task", execution_mode="ultra"), llm)
        assert result["metadata"]["subtasks"] == ["x", "y"]


# ═══════════════════════════════════════════════════════════════════════════
# dispatch_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.dispatch import dispatch_node


class TestDispatchNode:
    def test_pro_single_task(self):
        state = make_state("build a page", execution_mode="pro", metadata={"task_description": "build a page"})
        result = dispatch_node(state)
        assert len(result["pending_tasks"]) == 1
        task = result["pending_tasks"][0]
        assert task.type == "subagent"
        assert task.description == "build a page"
        assert "web_search" in task.tools

    def test_ultra_multiple_tasks(self):
        state = make_state(
            "parallel",
            execution_mode="ultra",
            metadata={"subtasks": ["task A", "task B", "task C"]},
        )
        result = dispatch_node(state)
        assert len(result["pending_tasks"]) == 3
        assert result["pending_tasks"][0].description == "task A"
        assert result["pending_tasks"][2].description == "task C"

    def test_ultra_empty_subtasks_falls_back_to_single(self):
        state = make_state("query", execution_mode="ultra", metadata={"subtasks": []})
        result = dispatch_node(state)
        assert len(result["pending_tasks"]) == 1

    def test_pro_no_description_uses_last_message(self):
        state = make_state("from messages", execution_mode="pro", metadata={})
        result = dispatch_node(state)
        assert result["pending_tasks"][0].description == "from messages"


# ═══════════════════════════════════════════════════════════════════════════
# respond_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.respond import respond_node


class TestRespondNode:
    def test_without_memory(self):
        llm = MockChatModel(["answer"])
        result = respond_node(make_state("hi"), llm)
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "answer"

    def test_with_memory_prepends_system_message(self):
        """When memory_context is set, a SystemMessage should be passed to the model."""
        invoked_messages = []

        class CaptureLLM(MockChatModel):
            def invoke(self, messages, **kwargs):
                invoked_messages.extend(messages)
                return super().invoke(messages, **kwargs)

        llm = CaptureLLM(["response with memory"])
        state = make_state("hi", memory_context="user likes cats")
        respond_node(state, llm)

        assert isinstance(invoked_messages[0], SystemMessage)
        assert "user likes cats" in invoked_messages[0].content


# ═══════════════════════════════════════════════════════════════════════════
# think_respond_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.think_respond import think_respond_node, THINK_SYSTEM_PROMPT


class TestThinkRespondNode:
    def test_think_system_prompt_present(self):
        invoked_messages = []

        class CaptureLLM(MockChatModel):
            def invoke(self, messages, **kwargs):
                invoked_messages.extend(messages)
                return super().invoke(messages, **kwargs)

        llm = CaptureLLM(["<thinking>reason</thinking>\nanswer"])
        think_respond_node(make_state("explain X"), llm)

        assert isinstance(invoked_messages[0], SystemMessage)
        assert THINK_SYSTEM_PROMPT in invoked_messages[0].content

    def test_with_memory_appended_to_system(self):
        invoked_messages = []

        class CaptureLLM(MockChatModel):
            def invoke(self, messages, **kwargs):
                invoked_messages.extend(messages)
                return super().invoke(messages, **kwargs)

        llm = CaptureLLM(["answer"])
        think_respond_node(make_state("q", memory_context="user is a dev"), llm)

        system_content = invoked_messages[0].content
        assert THINK_SYSTEM_PROMPT in system_content
        assert "user is a dev" in system_content


# ═══════════════════════════════════════════════════════════════════════════
# merge_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.merge import merge_node


class TestMergeNode:
    def test_no_outputs_returns_error(self):
        state = make_state(completed_tasks=[
            TaskResult(task_id="1", status="failed", error="boom"),
        ])
        result = merge_node(state, MockChatModel())
        msg = result["messages"][0]
        assert "boom" in msg.content

    def test_no_outputs_no_errors(self):
        state = make_state(completed_tasks=[])
        result = merge_node(state, MockChatModel())
        assert "无法完成" in result["messages"][0].content

    def test_single_output_passthrough(self):
        state = make_state(completed_tasks=[
            TaskResult(task_id="1", status="completed", output="only result"),
        ])
        result = merge_node(state, MockChatModel())
        assert result["messages"][0].content == "only result"

    def test_multiple_outputs_calls_llm(self):
        llm = MockChatModel(["synthesized result"])
        state = make_state(completed_tasks=[
            TaskResult(task_id="1", status="completed", output="result A"),
            TaskResult(task_id="2", status="completed", output="result B"),
        ])
        result = merge_node(state, llm)
        assert result["messages"][0].content == "synthesized result"

    def test_multiple_outputs_llm_failure_concatenates(self):
        class FailLLM:
            def invoke(self, messages, **kwargs):
                raise RuntimeError("LLM down")

        state = make_state(completed_tasks=[
            TaskResult(task_id="1", status="completed", output="A"),
            TaskResult(task_id="2", status="completed", output="B"),
        ])
        result = merge_node(state, FailLLM())
        content = result["messages"][0].content
        assert "A" in content and "B" in content


# ═══════════════════════════════════════════════════════════════════════════
# skill_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.skill_node import skill_node


class TestSkillNode:
    def test_no_match_falls_back_to_subagent(self):
        with patch("core.graph.nodes.skill_node.get_all_skills", return_value=[]), \
             patch("core.graph.nodes.skill_node.select_best_skill", return_value=None):
            state = make_state("do something")
            result = skill_node(state, MockChatModel())

        assert len(result["pending_tasks"]) == 1
        assert result["pending_tasks"][0].type == "subagent"

    def test_tool_skill_creates_per_todo_tasks(self):
        from core.skills.types import Skill
        from pathlib import Path

        mock_skill = Skill(
            name="research",
            description="research skill",
            content="You are a researcher.",
            path=Path("/fake"),
            tools=["web_search"],
            timeout=120,
        )
        todos = [
            TodoItem(content="step 1", status="pending"),
            TodoItem(content="step 2", status="pending"),
        ]
        state = make_state("research AI", todos=todos)

        with patch("core.graph.nodes.skill_node.get_all_skills", return_value=[mock_skill]), \
             patch("core.graph.nodes.skill_node.select_best_skill", return_value=mock_skill):
            result = skill_node(state, MockChatModel())

        assert len(result["pending_tasks"]) == 2
        assert result["pending_tasks"][0].type == "skill_subagent"
        assert result["pending_tasks"][0].description == "step 1"
        assert result["pending_tasks"][0].skill_name == "research"
        assert result["pending_tasks"][0].tools == ["web_search"]

    def test_direct_generation_skill_creates_single_task(self):
        from core.skills.types import Skill
        from pathlib import Path

        mock_skill = Skill(
            name="chart",
            description="chart builder",
            content="Build charts.",
            path=Path("/fake"),
            tools=[],
            execution_mode="prompt_injection",
        )
        state = make_state("draw a chart")

        with patch("core.graph.nodes.skill_node.get_all_skills", return_value=[mock_skill]), \
             patch("core.graph.nodes.skill_node.select_best_skill", return_value=mock_skill), \
             patch("core.graph.nodes.skill_node.skill_to_task") as mock_to_task:
            mock_to_task.return_value = TaskSpec(
                type="skill_inject", description="injected", skill_name="chart",
            )
            result = skill_node(state, MockChatModel())

        assert len(result["pending_tasks"]) == 1
        assert result["pending_tasks"][0].skill_name == "chart"


# ═══════════════════════════════════════════════════════════════════════════
# reflector_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.reflector import reflector_node


class TestReflectorNode:
    def test_ultra_mode_passthrough(self):
        state = make_state(execution_mode="ultra")
        result = reflector_node(state, MockChatModel())
        assert result == {"route": None}

    def test_pending_tasks_continue(self):
        tasks = [TaskSpec(description="remaining")]
        state = make_state(execution_mode="pro", pending_tasks=tasks)
        result = reflector_node(state, MockChatModel())
        assert result["route"] == "continue_execute"

    def test_max_iterations_terminate(self):
        state = make_state(
            execution_mode="pro",
            iteration=5,
            completed_tasks=[TaskResult(task_id="1", status="completed", output="done")],
        )
        result = reflector_node(state, MockChatModel(), max_iterations=3)
        assert "messages" in result
        assert "done" in result["messages"][0].content

    def test_similar_output_terminates(self):
        output = "exact same output content for similarity check"
        state = make_state(
            execution_mode="pro",
            iteration=1,
            previous_round_output=output,
            completed_tasks=[TaskResult(task_id="1", status="completed", output=output)],
        )
        result = reflector_node(state, MockChatModel(), max_iterations=10)
        assert "messages" in result

    def test_completed_results_output_directly(self):
        state = make_state(
            execution_mode="pro",
            iteration=1,
            completed_tasks=[
                TaskResult(task_id="1", status="completed", output="research result"),
            ],
        )
        result = reflector_node(state, MockChatModel(), max_iterations=10)
        assert "messages" in result
        assert "research result" in result["messages"][0].content

    def test_no_output_shows_error(self):
        state = make_state(
            execution_mode="pro",
            iteration=1,
            completed_tasks=[
                TaskResult(task_id="1", status="failed", error="timeout"),
            ],
        )
        result = reflector_node(state, MockChatModel(), max_iterations=10)
        assert "messages" in result
        assert "timeout" in result["messages"][0].content


# ═══════════════════════════════════════════════════════════════════════════
# execute_node
# ═══════════════════════════════════════════════════════════════════════════

from core.graph.nodes.execute import execute_node


class TestExecuteNode:
    def test_empty_tasks(self):
        state = make_state(execution_mode="pro", pending_tasks=[], iteration=2)
        result = execute_node(state, MockChatModel())
        assert result["pending_tasks"] == []
        assert result["iteration"] == 3

    def test_pro_single_task_execution(self):
        from core.executor.task import SubagentResult, SubagentStatus

        mock_sub_result = SubagentResult(
            task_id="t1",
            status=SubagentStatus.COMPLETED,
            output="task output",
        )
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_sub_result
        mock_runner.tool_call_log = []

        task = TaskSpec(id="t1", description="do work", tools=["web_search"])
        todo = TodoItem(content="do work", status="pending")
        state = make_state(
            execution_mode="pro",
            pending_tasks=[task],
            todos=[todo],
            iteration=0,
        )

        with patch("core.graph.nodes.execute.SubagentRunner", return_value=mock_runner):
            result = execute_node(state, MockChatModel())

        assert result["iteration"] == 1
        assert len(result["completed_tasks"]) == 1
        assert result["completed_tasks"][0].status == "completed"
        assert result["pending_tasks"] == []

    def test_pro_leaves_remaining_tasks_pending(self):
        from core.executor.task import SubagentResult, SubagentStatus

        mock_sub_result = SubagentResult(
            task_id="t1",
            status=SubagentStatus.COMPLETED,
            output="done",
        )
        mock_runner = MagicMock()
        mock_runner.run.return_value = mock_sub_result
        mock_runner.tool_call_log = []

        tasks = [
            TaskSpec(id="t1", description="first", tools=["web_search"]),
            TaskSpec(id="t2", description="second", tools=["web_search"]),
        ]
        state = make_state(execution_mode="pro", pending_tasks=tasks, iteration=0)

        with patch("core.graph.nodes.execute.SubagentRunner", return_value=mock_runner):
            result = execute_node(state, MockChatModel())

        # Pro mode: only first task executed, second remains pending
        assert len(result["completed_tasks"]) == 1
        assert len(result["pending_tasks"]) == 1
        assert result["pending_tasks"][0].id == "t2"

    def test_skill_inject_skips_runner(self):
        task = TaskSpec(id="inj1", type="skill_inject", description="injected content")
        state = make_state(execution_mode="pro", pending_tasks=[task], iteration=0)

        result = execute_node(state, MockChatModel())

        assert len(result["completed_tasks"]) == 1
        assert result["completed_tasks"][0].status == "completed"
        assert result["completed_tasks"][0].output == "injected content"
