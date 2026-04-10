"""SubagentRunner — ReAct Agent: Observe → Think → Act → Observe loop."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from .task import SubagentResult, SubagentStatus

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 6


def _get_tool_by_name(name: str) -> BaseTool | None:
    from core.tools.web_search import web_search
    from core.tools.run_skill import run_skill
    return {"web_search": web_search, "run_skill": run_skill}.get(name)


def resolve_tools(tool_names: list[str] | None) -> list[BaseTool]:
    if not tool_names:
        return []
    return [t for name in tool_names if (t := _get_tool_by_name(name))]


class SubagentRunner:
    """ReAct Agent runner.

    With tools: runs a Think→Act→Observe loop until the LLM produces a
    final answer (no tool_calls) or max_iterations is reached.

    Without tools: calls the model directly for a single response.
    """

    def __init__(
        self,
        model: Any,
        system_prompt: str = "",
        tools: list | None = None,
        tool_names: list[str] | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        **kwargs: Any,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or resolve_tools(tool_names)
        self.max_iterations = max_iterations
        self.tool_call_log: list[dict] = []
        self._tool_map: dict[str, Any] = {t.name: t for t in self.tools}

        # Bind tools to model so it can produce structured tool_calls
        self._bound_model = self._bind_tools_to_model()

    def _bind_tools_to_model(self):
        """Bind LangChain tools to model for structured tool_calls output."""
        if not self.tools:
            return self.model
        # Filter to real LangChain BaseTool instances that support bind_tools
        lc_tools = [t for t in self.tools if isinstance(t, BaseTool)]
        if lc_tools and hasattr(self.model, "bind_tools"):
            try:
                return self.model.bind_tools(lc_tools)
            except Exception as e:
                logger.warning(f"bind_tools failed: {e}, using unbound model")
        return self.model

    def run(self, task_description: str, task_id: str = "unknown") -> SubagentResult:
        result = SubagentResult(
            task_id=task_id,
            status=SubagentStatus.RUNNING,
            started_at=time.time(),
        )
        try:
            if self.tools:
                self._react_loop(task_description, result)
            else:
                self._direct_response(task_description, result)
        except Exception as e:
            logger.exception(f"SubagentRunner failed: {e}")
            result.status = SubagentStatus.FAILED
            result.error = str(e)
            result.completed_at = time.time()
        return result

    def _direct_response(self, task: str, result: SubagentResult) -> None:
        """No tools — call the model directly."""
        messages: list = []
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))
        messages.append(HumanMessage(content=task))

        resp = self.model.invoke(messages)
        result.output = resp.content if isinstance(resp.content, str) else str(resp.content)
        result.status = SubagentStatus.COMPLETED
        result.completed_at = time.time()

    def _get_current_date_context(self) -> str:
        """Get current date/time context string."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
        except Exception:
            now = datetime.now()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return f"当前时间：{now.strftime('%Y年%m月%d日')} {weekdays[now.weekday()]} {now.strftime('%H:%M')} (Asia/Shanghai)"

    def _react_loop(self, task: str, result: SubagentResult) -> None:
        """ReAct loop: Think → Act → Observe, repeat until done."""
        date_ctx = self._get_current_date_context()
        messages: list = []
        if self.system_prompt:
            messages.append(SystemMessage(content=f"{date_ctx}\n\n{self.system_prompt}"))
        else:
            tool_descriptions = "\n".join(
                f"- {t.name}: {getattr(t, 'description', 'No description')}"
                for t in self.tools
            )
            messages.append(SystemMessage(
                content=(
                    f"{date_ctx}\n\n"
                    "你是一个智能助手，可以使用以下工具完成任务。"
                    "搜索时必须在查询中包含今天的日期以获取最新信息。"
                    "每次只调用一个工具，根据结果决定下一步。"
                    "当你认为任务完成时，直接回复最终答案（不调用工具）。\n\n"
                    f"可用工具：\n{tool_descriptions}"
                )
            ))
        messages.append(HumanMessage(content=task))

        for iteration in range(self.max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{self.max_iterations}")

            resp = self._bound_model.invoke(messages)
            messages.append(resp)

            # Check if LLM produced tool calls
            tool_calls = getattr(resp, "tool_calls", None) or []
            if not tool_calls:
                # No tool calls → final answer
                result.output = resp.content if isinstance(resp.content, str) else str(resp.content)
                result.status = SubagentStatus.COMPLETED
                result.completed_at = time.time()
                return

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                call_id = tc.get("id", f"call_{iteration}")

                log_entry = {"name": tool_name, "args": tool_args}

                tool = self._tool_map.get(tool_name)
                if tool is None:
                    error_msg = f"Tool '{tool_name}' not found"
                    logger.warning(error_msg)
                    log_entry["error"] = error_msg
                    log_entry["result_preview"] = f"Error: {error_msg}"
                    self.tool_call_log.append(log_entry)
                    # Feed error back to LLM so it can adapt
                    from langchain_core.messages import ToolMessage
                    messages.append(ToolMessage(
                        content=json.dumps({"error": error_msg}),
                        tool_call_id=call_id,
                    ))
                    continue

                try:
                    tool_result = tool.invoke(tool_args)
                    tool_result_str = str(tool_result)
                    log_entry["result_preview"] = tool_result_str[:200]
                    self.tool_call_log.append(log_entry)
                    from langchain_core.messages import ToolMessage
                    messages.append(ToolMessage(
                        content=tool_result_str,
                        tool_call_id=call_id,
                    ))
                except Exception as e:
                    error_msg = f"Tool error: {e}"
                    logger.warning(f"Tool {tool_name} failed: {e}")
                    log_entry["error"] = str(e)
                    log_entry["result_preview"] = error_msg
                    self.tool_call_log.append(log_entry)
                    from langchain_core.messages import ToolMessage
                    messages.append(ToolMessage(
                        content=json.dumps({"error": str(e)}),
                        tool_call_id=call_id,
                    ))

        # Max iterations reached — force a final summary
        logger.warning(f"ReAct hit max_iterations ({self.max_iterations}), forcing summary")
        messages.append(HumanMessage(
            content="已达到最大迭代次数，请根据目前收集到的信息给出最终回答。"
        ))
        resp = self._bound_model.invoke(messages)
        result.output = resp.content if isinstance(resp.content, str) else str(resp.content)
        result.status = SubagentStatus.COMPLETED
        result.messages = [{"tool_calls": self.tool_call_log}]
        result.completed_at = time.time()
