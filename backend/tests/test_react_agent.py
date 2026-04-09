"""TDD tests for ReAct SubagentRunner upgrade.

Tests cover:
1. ReAct loop: think → act → observe cycle
2. Multi-tool support: web_search + run_skill
3. Complex scenarios: pulse, research-then-slides
4. Max iterations / timeout termination
5. Backward compatibility with existing two-phase runner
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from core.executor.runner import SubagentRunner
from core.executor.task import SubagentStatus


# ── Helpers ──

def _make_tool_call_response(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    """Create an AIMessage with a tool_call (LangChain format)."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


def _make_final_response(text: str) -> AIMessage:
    """Create a plain text AIMessage (no tool calls = agent done)."""
    return AIMessage(content=text)


class FakeSearchTool:
    """Mock web_search tool."""
    name = "web_search"
    description = "Search the web"

    def invoke(self, args):
        query = args.get("query", "") if isinstance(args, dict) else args
        return json.dumps({"results": [{"title": f"Result for {query}", "url": "https://example.com"}]})


class FakeSkillTool:
    """Mock run_skill tool."""
    name = "run_skill"
    description = "Run a Claude Code skill"

    def invoke(self, args):
        skill_name = args.get("skill_name", "") if isinstance(args, dict) else args
        return json.dumps({"status": "completed", "output": f"Skill {skill_name} executed successfully"})


# ── Test: ReAct Loop Basics ──

class TestReActLoop:
    """Core ReAct loop: LLM decides tools, agent executes, loop until final answer."""

    def test_single_tool_call_then_answer(self):
        """LLM calls one tool, gets result, then produces final answer."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "AI news"}),
            _make_final_response("Here is the AI news summary."),
        ]

        runner = SubagentRunner(model=model, tools=[FakeSearchTool()])
        result = runner.run("Research AI news", "task_1")

        assert result.status == SubagentStatus.COMPLETED
        assert "AI news summary" in result.output
        assert len(runner.tool_call_log) == 1
        assert runner.tool_call_log[0]["name"] == "web_search"

    def test_multi_step_tool_calls(self):
        """LLM makes multiple tool calls before final answer."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "topic A"}, "c1"),
            _make_tool_call_response("web_search", {"query": "topic B"}, "c2"),
            _make_final_response("Combined report on A and B."),
        ]

        runner = SubagentRunner(model=model, tools=[FakeSearchTool()])
        result = runner.run("Compare A and B", "task_2")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 2

    def test_no_tools_direct_response(self):
        """No tools available — LLM answers directly (backward compatible)."""
        model = MagicMock()
        model.invoke.return_value = _make_final_response("Direct answer.")

        runner = SubagentRunner(model=model, tools=[])
        result = runner.run("Simple question", "task_3")

        assert result.status == SubagentStatus.COMPLETED
        assert result.output == "Direct answer."
        assert len(runner.tool_call_log) == 0

    def test_max_iterations_prevents_infinite_loop(self):
        """Agent terminates after max_iterations even if LLM keeps calling tools."""
        model = MagicMock()
        # LLM calls tools for 3 iterations, then forced summary prompt gets a text response
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "loop forever"}),
            _make_tool_call_response("web_search", {"query": "loop forever"}),
            _make_tool_call_response("web_search", {"query": "loop forever"}),
            _make_final_response("Forced summary after max iterations."),  # forced summary
        ]

        runner = SubagentRunner(model=model, tools=[FakeSearchTool()], max_iterations=3)
        result = runner.run("Infinite loop scenario", "task_4")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 3  # Capped at max_iterations
        assert result.output  # Should have a forced summary

    def test_tool_error_graceful_recovery(self):
        """Tool raises exception → agent logs error, continues to next step."""
        broken_tool = FakeSearchTool()
        broken_tool.invoke = MagicMock(side_effect=RuntimeError("API down"))

        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "test"}),
            _make_final_response("Recovered despite tool error."),
        ]

        runner = SubagentRunner(model=model, tools=[broken_tool])
        result = runner.run("Handle errors", "task_5")

        assert result.status == SubagentStatus.COMPLETED
        assert "Recovered" in result.output


# ── Test: Multi-Tool Support ──

class TestMultiToolSupport:
    """Runner supports multiple tool types, LLM picks the right one."""

    def test_run_skill_tool(self):
        """LLM decides to run a skill instead of web_search."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("run_skill", {"skill_name": "pulse"}),
            _make_final_response("Pulse briefing generated."),
        ]

        runner = SubagentRunner(
            model=model,
            tools=[FakeSearchTool(), FakeSkillTool()],
        )
        result = runner.run("Generate today's pulse", "task_6")

        assert result.status == SubagentStatus.COMPLETED
        assert runner.tool_call_log[0]["name"] == "run_skill"

    def test_mixed_tool_calls(self):
        """LLM uses web_search first, then run_skill."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "AI trends 2026"}),
            _make_tool_call_response("run_skill", {"skill_name": "frontend-slides", "args": "Make a presentation about AI trends"}),
            _make_final_response("Research done and slides created."),
        ]

        runner = SubagentRunner(
            model=model,
            tools=[FakeSearchTool(), FakeSkillTool()],
        )
        result = runner.run("Research AI trends then make slides", "task_7")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 2
        assert runner.tool_call_log[0]["name"] == "web_search"
        assert runner.tool_call_log[1]["name"] == "run_skill"

    def test_unknown_tool_skipped(self):
        """LLM calls a tool not in the tool list → skip gracefully."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("nonexistent_tool", {"arg": "val"}),
            _make_final_response("Proceeded without missing tool."),
        ]

        runner = SubagentRunner(model=model, tools=[FakeSearchTool()])
        result = runner.run("Test unknown tool", "task_8")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 1
        assert "error" in runner.tool_call_log[0].get("result_preview", "").lower() or \
               runner.tool_call_log[0].get("error") is not None


# ── Test: Complex Scenarios ──

class TestComplexScenarios:
    """Ultra mode scenarios: pulse, research+slides, multi-step research."""

    def test_pulse_scenario(self):
        """Pulse briefing: agent calls run_skill(pulse) then summarizes."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("run_skill", {"skill_name": "pulse"}),
            _make_final_response("# Pulse | 🌅 — 2026年4月9日\n\n## Product Hunts\n..."),
        ]

        runner = SubagentRunner(
            model=model,
            tools=[FakeSkillTool()],
            system_prompt="你是一个新闻简报助手。",
        )
        result = runner.run("生成今日 Pulse 日报", "task_pulse")

        assert result.status == SubagentStatus.COMPLETED
        assert "Pulse" in result.output

    def test_research_then_slides_scenario(self):
        """Complex: search → gather data → create slides via skill."""
        model = MagicMock()
        model.invoke.side_effect = [
            _make_tool_call_response("web_search", {"query": "AI Agent 2026 trends"}),
            _make_tool_call_response("web_search", {"query": "Claude Code agent framework"}),
            _make_tool_call_response("run_skill", {
                "skill_name": "frontend-slides",
                "args": "Create slides about AI Agent trends",
            }),
            _make_final_response("研究报告和演示文稿已完成。"),
        ]

        runner = SubagentRunner(
            model=model,
            tools=[FakeSearchTool(), FakeSkillTool()],
            max_iterations=10,
        )
        result = runner.run(
            "先调研 AI Agent 最新趋势，然后制作一个 PPT", "task_slides"
        )

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 3
        # First two are searches, last is skill
        assert runner.tool_call_log[0]["name"] == "web_search"
        assert runner.tool_call_log[1]["name"] == "web_search"
        assert runner.tool_call_log[2]["name"] == "run_skill"

    def test_system_prompt_passed_to_model(self):
        """System prompt is included in the first LLM call."""
        model = MagicMock()
        model.invoke.return_value = _make_final_response("ok")

        runner = SubagentRunner(
            model=model,
            tools=[],
            system_prompt="You are a research assistant.",
        )
        runner.run("test", "t1")

        call_args = model.invoke.call_args[0][0]
        # First message should be SystemMessage
        from langchain_core.messages import SystemMessage
        assert any(isinstance(m, SystemMessage) for m in call_args)


# ── Test: Backward Compatibility ──

class TestBackwardCompatibility:
    """Ensure existing callers (execute_node) still work without changes."""

    def test_tool_names_resolve(self):
        """tool_names=["web_search"] still works as before."""
        model = MagicMock()
        model.invoke.return_value = _make_final_response("Direct response")

        # Use tool_names (string list) instead of tool instances
        with patch("core.executor.runner._get_tool_by_name") as mock_get:
            mock_get.return_value = FakeSearchTool()
            runner = SubagentRunner(model=model, tool_names=["web_search"])
            assert len(runner.tools) == 1
            assert runner.tools[0].name == "web_search"

    def test_result_structure_unchanged(self):
        """SubagentResult fields are the same as before."""
        model = MagicMock()
        model.invoke.return_value = _make_final_response("test output")

        runner = SubagentRunner(model=model, tools=[])
        result = runner.run("hello", "task_compat")

        assert hasattr(result, "task_id")
        assert hasattr(result, "status")
        assert hasattr(result, "output")
        assert hasattr(result, "error")
        assert hasattr(result, "started_at")
        assert hasattr(result, "completed_at")
        assert result.task_id == "task_compat"
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at
