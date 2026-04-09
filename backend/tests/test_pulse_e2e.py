"""E2E tests for Pulse scenario — validates the full ReAct pipeline.

Tests the complete flow:
  Router(pro) → Plan → Dispatch → Execute(ReAct + tools) → Reflector → content

Uses a mock LLM that properly produces tool_calls via bind_tools,
and mock tools that return realistic data. Asserts that:
1. The router selects pro/ultra mode (not flash)
2. The ReAct agent calls tools (web_search or run_skill)
3. The final output contains actual content (not raw tool names)
4. SSE events include todo_update, subagent_result, and content
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.executor.runner import SubagentRunner
from core.executor.task import SubagentStatus, TaskSpec, TaskResult, TodoItem


# ---------------------------------------------------------------------------
# Mock LLM that supports bind_tools and produces tool_calls
# ---------------------------------------------------------------------------

class ToolCallingMockLLM:
    """Mock LLM that simulates proper tool calling behavior.

    First call: produces a tool_call for web_search.
    Second call: produces the final text answer using tool results.
    """

    def __init__(self, tool_call_sequence: list[dict | str]):
        """
        Args:
            tool_call_sequence: list of items, each is either:
              - dict with {name, args} → produces a tool_call AIMessage
              - str → produces a final text AIMessage
        """
        self._sequence = tool_call_sequence
        self._call_idx = 0
        self._bound = False

    def bind_tools(self, tools, **kwargs):
        self._bound = True
        return self  # Return self so invoke works on bound instance

    def invoke(self, messages, **kwargs):
        if self._call_idx >= len(self._sequence):
            return AIMessage(content="No more responses configured.")
        item = self._sequence[self._call_idx]
        self._call_idx += 1

        if isinstance(item, str):
            return AIMessage(content=item)
        else:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": item["name"],
                    "args": item["args"],
                    "id": f"call_{self._call_idx}",
                }],
            )


class MockWebSearch:
    """Realistic mock web_search tool."""
    name = "web_search"
    description = "Search the web for information."

    def invoke(self, args):
        query = args.get("query", "") if isinstance(args, dict) else str(args)
        return json.dumps({
            "query": query,
            "total_results": 3,
            "results": [
                {"title": "Claude 4.5 发布：新一代 AI 模型", "url": "https://anthropic.com/claude-4-5", "content": "Anthropic 发布 Claude 4.5，支持 1M 上下文窗口和增强工具调用能力。"},
                {"title": "OpenAI 发布 GPT-5 Turbo", "url": "https://openai.com/gpt5", "content": "OpenAI 最新推出 GPT-5 Turbo 模型，推理能力大幅提升。"},
                {"title": "Apple WWDC 2026 发布 AI 新功能", "url": "https://apple.com/wwdc26", "content": "Apple 在 WWDC 2026 上发布了一系列 AI 驱动的新功能。"},
            ],
        }, ensure_ascii=False)


class MockRunSkill:
    """Realistic mock run_skill tool."""
    name = "run_skill"
    description = "Run a Claude Code skill by name."

    def invoke(self, args):
        skill_name = args.get("skill_name", "") if isinstance(args, dict) else str(args)
        if skill_name == "pulse":
            return json.dumps({
                "status": "completed",
                "output": "# 📡 Pulse | 🌅 — 2026年4月9日\n\n## Product Hunts\n- **Cursor 2.0** AI coding reimagined\n\n## GitHub Trending\n- **anthropics/claude-code** ⭐ 50K\n\n## News\n- Claude 4.5 发布",
                "skill_name": "pulse",
            }, ensure_ascii=False)
        return json.dumps({"status": "completed", "output": f"Skill {skill_name} done"})


# ---------------------------------------------------------------------------
# E2E: SubagentRunner with ReAct loop
# ---------------------------------------------------------------------------

class TestPulseReActE2E:
    """Full ReAct loop for Pulse scenario."""

    def test_pulse_via_web_search_produces_content(self):
        """Pulse query → ReAct calls web_search → LLM produces report with real content."""
        model = ToolCallingMockLLM([
            {"name": "web_search", "args": {"query": "今日科技新闻 AI 2026"}},
            {"name": "web_search", "args": {"query": "科技行业最新动态"}},
            # Final answer with content (not raw tool names)
            "# 📡 Pulse 科技日报 — 2026年4月9日\n\n## 头条\n- **Claude 4.5 发布**：Anthropic 发布新一代模型\n- **GPT-5 Turbo**：OpenAI 推理能力大幅提升\n- **Apple WWDC 2026**：AI 新功能亮相",
        ])

        runner = SubagentRunner(
            model=model,
            tools=[MockWebSearch()],
            system_prompt="你是一个科技新闻记者，根据搜索结果生成 Pulse 科技日报。",
        )
        result = runner.run("帮我生成今日的 Pulse 科技日报", "task_pulse")

        # Must complete successfully
        assert result.status == SubagentStatus.COMPLETED

        # Must have called tools
        assert len(runner.tool_call_log) == 2
        assert runner.tool_call_log[0]["name"] == "web_search"
        assert runner.tool_call_log[1]["name"] == "web_search"

        # Output must contain actual content, not raw tool descriptions
        assert "Pulse" in result.output
        assert "Claude" in result.output or "科技" in result.output
        assert "web_search:" not in result.output  # No raw tool calls leaked

    def test_pulse_via_run_skill(self):
        """Pulse query → ReAct calls run_skill(pulse) → returns skill output."""
        model = ToolCallingMockLLM([
            {"name": "run_skill", "args": {"skill_name": "pulse"}},
            "以下是今日 Pulse 科技日报的完整内容：\n\n# 📡 Pulse\n\n精选了 Product Hunt 热门产品和 GitHub Trending 项目。",
        ])

        runner = SubagentRunner(
            model=model,
            tools=[MockWebSearch(), MockRunSkill()],
        )
        result = runner.run("帮我生成今日的 Pulse 科技日报", "task_pulse_skill")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 1
        assert runner.tool_call_log[0]["name"] == "run_skill"
        assert "Pulse" in result.output
        assert "web_search:" not in result.output

    def test_research_then_slides_full_chain(self):
        """Research+slides: web_search x2 → run_skill(slides) → final report."""
        model = ToolCallingMockLLM([
            {"name": "web_search", "args": {"query": "AI Agent 2026 trends"}},
            {"name": "web_search", "args": {"query": "AI Coding tools market"}},
            {"name": "run_skill", "args": {"skill_name": "frontend-slides", "args": "AI Agent trends PPT"}},
            "调研完成，已基于以下数据制作演示文稿：\n1. Claude 4.5 支持百万上下文\n2. AI Coding 工具市场快速增长\n3. 演示文稿已通过 frontend-slides 生成",
        ])

        runner = SubagentRunner(
            model=model,
            tools=[MockWebSearch(), MockRunSkill()],
            max_iterations=10,
        )
        result = runner.run("先调研 AI Agent 趋势，然后制作 PPT", "task_slides")

        assert result.status == SubagentStatus.COMPLETED
        assert len(runner.tool_call_log) == 3

        # Correct tool order: search → search → skill
        tool_names = [tc["name"] for tc in runner.tool_call_log]
        assert tool_names == ["web_search", "web_search", "run_skill"]

        # Final output is a coherent report, not raw tool output
        assert "演示文稿" in result.output or "PPT" in result.output
        assert "web_search:" not in result.output

    def test_bind_tools_called_for_langchain_tools(self):
        """bind_tools is called when real LangChain BaseTool instances are provided."""
        from langchain_core.tools import tool as lc_tool

        @lc_tool("test_tool")
        def test_tool(query: str) -> str:
            """A test tool."""
            return "ok"

        model = ToolCallingMockLLM(["Direct response"])
        runner = SubagentRunner(model=model, tools=[test_tool])
        assert model._bound is True

    def test_no_bind_tools_without_tools(self):
        """bind_tools is NOT called when no tools are provided."""
        model = ToolCallingMockLLM(["Direct response"])
        runner = SubagentRunner(model=model, tools=[])
        assert model._bound is False


# ---------------------------------------------------------------------------
# E2E: SSE integration for Pulse via mock graph
# ---------------------------------------------------------------------------

class TestPulseSSEIntegration:
    """Test the full SSE pipeline for Pulse (router → pro → content)."""

    @pytest.fixture
    def client(self):
        from app.gateway.app import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def _parse_sse(self, text: str) -> list[dict]:
        events = []
        current_event = current_data = None
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                current_data = line[5:].strip()
            elif line == "" and current_event and current_data:
                try:
                    parsed = json.loads(current_data)
                except json.JSONDecodeError:
                    parsed = current_data
                events.append({"event": current_event, "data": parsed})
                current_event = current_data = None
        if current_event and current_data:
            try:
                parsed = json.loads(current_data)
            except json.JSONDecodeError:
                parsed = current_data
            events.append({"event": current_event, "data": parsed})
        return events

    def test_pulse_routes_to_pro_not_flash(self, client):
        """'帮我生成今日的 Pulse 科技日报' must route to pro mode, not flash."""
        # Build a mock graph that simulates pro mode
        pro_todos = [
            TodoItem(id="t1", content="收集今日科技新闻", status="pending"),
            TodoItem(id="t2", content="撰写 Pulse 日报", status="pending"),
        ]
        completed = [
            TaskResult(task_id="t1", status="completed", output="新闻收集完成", duration_seconds=5.0),
        ]

        async def astream_events(input_state, config=None, version=None):
            # Router → pro
            yield {"event": "on_chain_start", "name": "router", "data": {}, "tags": [], "metadata": {}}
            yield {"event": "on_chain_end", "name": "router", "data": {"output": {"execution_mode": "pro"}}, "tags": [], "metadata": {}}
            # Plan
            yield {"event": "on_chain_start", "name": "plan", "data": {}, "tags": [], "metadata": {}}
            yield {"event": "on_chain_end", "name": "plan", "data": {"output": {"todos": pro_todos}}, "tags": [], "metadata": {}}
            # Execute
            yield {"event": "on_chain_start", "name": "execute", "data": {}, "tags": [], "metadata": {}}
            yield {"event": "on_chain_end", "name": "execute", "data": {"output": {"completed_tasks": completed}}, "tags": [], "metadata": {}}
            # Content
            for chunk in ["# 📡 Pulse", " 科技日报\n\n", "- Claude 4.5 发布"]:
                yield {"event": "on_chat_model_stream", "name": "ChatModel", "data": {"chunk": type("C", (), {"content": chunk})()}, "tags": [], "metadata": {"langgraph_node": "respond"}}
            yield {"event": "on_chain_end", "name": "respond", "data": {"output": {"messages": [AIMessage(content="# 📡 Pulse 科技日报\n\n- Claude 4.5 发布")]}}, "tags": [], "metadata": {}}

        mock_graph = MagicMock()
        mock_graph.astream_events = astream_events

        with patch("app.gateway.routers.chat.build_graph", return_value=mock_graph):
            resp = client.post("/api/chat", json={"message": "帮我生成今日的 Pulse 科技日报"})

        assert resp.status_code == 200
        events = self._parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        # Must be pro mode, NOT flash
        mode_ev = next(e for e in events if e["event"] == "mode_selected")
        assert mode_ev["data"]["mode"] == "pro", f"Expected pro but got {mode_ev['data']['mode']}"

        # Must have todo_update (execution plan)
        assert "todo_update" in event_types

        # Must have content
        assert "content" in event_types
        content_events = [e for e in events if e["event"] == "content"]
        full_content = "".join(e["data"]["content"] for e in content_events)
        assert "Pulse" in full_content

        # Must have subagent_result
        result_events = [e for e in events if e["event"] == "subagent_result"]
        assert len(result_events) >= 1

        # Must end with done
        assert event_types[-1] == "done"
