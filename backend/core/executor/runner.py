"""SubagentRunner — two-phase: deterministic search + LLM report generation."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from .task import SubagentResult, SubagentStatus

logger = logging.getLogger(__name__)


def _get_tool_by_name(name: str) -> BaseTool | None:
    from core.tools.web_search import web_search
    return {"web_search": web_search}.get(name)


def resolve_tools(tool_names: list[str] | None) -> list[BaseTool]:
    if not tool_names:
        return []
    return [t for name in tool_names if (t := _get_tool_by_name(name))]


class SubagentRunner:
    """Two-phase research runner:
    Phase 1: Deterministic search (always runs, no model dependency)
    Phase 2: LLM report generation from search results
    """

    def __init__(
        self,
        model: Any,
        system_prompt: str = "",
        tools: list[BaseTool] | None = None,
        tool_names: list[str] | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or resolve_tools(tool_names)
        self.tool_call_log: list[dict] = []

    def run(self, task_description: str, task_id: str = "unknown") -> SubagentResult:
        result = SubagentResult(task_id=task_id, status=SubagentStatus.RUNNING, started_at=time.time())
        try:
            if self.tools:
                return asyncio.run(self._research_and_report(task_description, result))
            else:
                return asyncio.run(self._direct_response(task_description, result))
        except Exception as e:
            logger.exception(f"SubagentRunner failed: {e}")
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = time.time()
            return result

    async def _direct_response(self, task: str, result: SubagentResult) -> SubagentResult:
        """No tools — just call the model directly."""
        messages = []
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))
        messages.append(HumanMessage(content=task))
        resp = await asyncio.to_thread(
            self.model.invoke,
            messages,
        )
        result.output = resp.content if isinstance(resp.content, str) else str(resp.content)
        result.status = SubagentStatus.COMPLETED
        result.completed_at = time.time()
        return result

    async def _research_and_report(self, task: str, result: SubagentResult) -> SubagentResult:
        """Phase 1: Search → Phase 2: Report. Deterministic, no model tool-calling needed."""
        search_tool = next((t for t in self.tools if t.name == "web_search"), None)
        if not search_tool:
            return await self._direct_response(task, result)

        # --- Phase 1: Deterministic search ---
        # Generate 2-3 search queries from the task
        queries = self._generate_queries(task)
        all_results = []

        for query in queries:
            logger.info(f"Searching: {query}")
            self.tool_call_log.append({"name": "web_search", "args": {"query": query}})
            try:
                search_result = await asyncio.to_thread(search_tool.invoke, {"query": query})
                search_str = str(search_result)
                self.tool_call_log[-1]["result_preview"] = search_str[:200]
                all_results.append(f"## 搜索 \"{query}\" 的结果:\n{search_str}")
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")
                self.tool_call_log[-1]["result_preview"] = f"Error: {e}"

        if not all_results:
            return await self._direct_response(task, result)

        # --- Phase 2: LLM report generation ---
        combined = "\n\n---\n\n".join(all_results)
        prompt = f"""基于以下搜索结果，撰写一份关于「{task}」的结构化中文 Markdown 研究报告。

要求：
- 使用搜索结果中的真实数据和事实，不要编造
- 包含标题、摘要、正文章节、数据表格（如适用）、结论
- 引用来源 URL

搜索结果：
{combined}"""

        try:
            resp = await asyncio.to_thread(
                self.model.invoke,
                [SystemMessage(content="你是专业研究分析师，基于搜索结果撰写高质量报告。"),
                 HumanMessage(content=prompt)],
            )
            result.output = resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception as e:
            result.output = f"报告生成失败: {e}\n\n原始搜索结果:\n{combined}"

        result.status = SubagentStatus.COMPLETED
        result.messages = [{"tool_calls": self.tool_call_log}]
        result.completed_at = time.time()
        return result

    def _generate_queries(self, task: str) -> list[str]:
        """Generate 2-3 search queries from the task description."""
        # Simple approach: use the task itself + variations
        base = task.strip()
        if len(base) > 60:
            base = base[:60]

        queries = [base]

        # Add a more specific query
        keywords = [w for w in base.split() if len(w) > 1]
        if len(keywords) >= 3:
            queries.append(" ".join(keywords[:4]) + " 数据")
        if len(keywords) >= 2:
            queries.append(" ".join(keywords[:3]) + " 最新")

        return queries[:3]
