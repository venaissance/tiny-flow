# backend/app/gateway/routers/chat.py
"""Chat endpoint — SSE streaming from agent graph with token-level streaming."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.graph.builder import build_graph
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)
router = APIRouter()

NODE_LABELS = {
    "router": "正在分析您的问题...",
    "respond": "正在生成回复...",
    "dispatch": "正在准备研究任务...",
    "skill_node": "正在匹配专业技能...",
    "execute": "研究员正在工作中，请稍候...",
    "reflector": "正在审查研究结果...",
}


class ChatRequest(BaseModel):
    thread_id: str = "default"
    message: str
    model: str | None = None


@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream agent responses via SSE using astream_events for token-level streaming."""
    graph = build_graph(model_name=request.model)

    async def event_stream() -> AsyncGenerator[dict, None]:
        counter = 0

        def evt(event_type: str, data: dict) -> dict:
            nonlocal counter
            counter += 1
            return {"id": str(counter), "event": event_type, "data": json.dumps(data, ensure_ascii=False)}

        input_state = {
            "messages": [HumanMessage(content=request.message)],
            "route": None,
            "pending_tasks": [],
            "completed_tasks": [],
            "previous_round_output": "",
            "iteration": 0,
            "memory_context": "",
            "metadata": {"thread_id": request.thread_id},
            "last_tool_calls": [],
        }
        config = {"configurable": {"thread_id": request.thread_id}}

        try:
            # Track which nodes we've seen to send progress events once
            seen_nodes: set[str] = set()
            # Track which node is currently producing LLM tokens
            current_llm_node: str | None = None
            # Buffer to detect node-level outputs (for tool calls, tasks, etc.)
            pending_node_output: dict | None = None

            async for event in graph.astream_events(
                input_state, config=config, version="v2"
            ):
                kind = event["event"]

                # --- Node lifecycle events ---
                if kind == "on_chain_start":
                    name = event.get("name", "")
                    if name in NODE_LABELS and name not in seen_nodes:
                        seen_nodes.add(name)
                        yield evt("thinking", {"node": name, "content": NODE_LABELS[name]})

                elif kind == "on_chain_end":
                    name = event.get("name", "")
                    output = event.get("data", {}).get("output")
                    if isinstance(output, dict) and name in NODE_LABELS:
                        # Process structured node outputs (route decisions, tasks, tool calls)
                        await _process_node_output(name, output, evt, event_stream)
                        # Yield all buffered events from node output
                        for e in _extract_node_events(name, output, evt):
                            yield e

                # --- Token-level LLM streaming ---
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        # Only stream content from respond/reflector nodes (final output)
                        # Router node tokens are internal decisions, not user-facing
                        tags = event.get("tags", [])
                        parent = event.get("metadata", {}).get("langgraph_node", "")
                        if parent in ("respond", "reflector", "execute"):
                            yield evt("content", {"content": content})

                # --- Tool call events from within subagent ---
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    tool_input = event.get("data", {}).get("input", {})
                    query = tool_input.get("query", "") if isinstance(tool_input, dict) else str(tool_input)
                    yield evt("tool_call", {"name": tool_name, "query": query, "preview": ""})

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    output = event.get("data", {}).get("output", "")
                    output_str = str(output)[:200] if output else ""
                    yield evt("tool_result", {"name": tool_name, "preview": output_str})

            yield evt("done", {})
        except Exception as e:
            logger.exception(f"Chat stream error: {e}")
            yield evt("error", {"error": str(e)})

    return EventSourceResponse(event_stream())


def _extract_node_events(node_name: str, output: dict, evt) -> list[dict]:
    """Extract SSE events from a node's structured output."""
    events = []

    # Reflector/execute messages — these nodes don't call LLM, so content wasn't
    # streamed via on_chat_model_stream. Emit line-by-line here.
    if node_name in ("reflector",) and "messages" in output:
        for msg in output["messages"]:
            full = msg.content if hasattr(msg, "content") else str(msg)
            for line in full.split("\n"):
                events.append(evt("content", {"content": line + "\n"}))

    # Route decision
    if "route" in output and output["route"]:
        route = output["route"]
        desc = {"direct": "直接回答", "subagent": "启动深度研究", "skill": "匹配到专业技能"}.get(route, route)
        events.append(evt("thinking", {"node": "router", "content": f"决策: {desc}"}))

    # Pending tasks (dispatch created them)
    if "pending_tasks" in output and output["pending_tasks"]:
        for task in output["pending_tasks"]:
            skill = getattr(task, "skill_name", None) or getattr(task, "agent_type", None) or "research"
            events.append(evt("subagent_status", {
                "task_id": getattr(task, "id", ""),
                "status": "running",
                "type": getattr(task, "type", "subagent"),
                "label": f"技能 [{skill}] 执行中",
            }))

    # Tool calls from execute node
    if "last_tool_calls" in output and output["last_tool_calls"]:
        for tc in output["last_tool_calls"]:
            events.append(evt("tool_call", {
                "name": tc.get("name", "web_search"),
                "query": tc.get("query", ""),
                "preview": tc.get("preview", ""),
            }))

    # Completed tasks
    if "completed_tasks" in output and output["completed_tasks"]:
        for task in output["completed_tasks"]:
            dur = getattr(task, "duration_seconds", 0) if hasattr(task, "duration_seconds") else 0
            status = task.status if hasattr(task, "status") else task.get("status", "completed")
            tid = task.task_id if hasattr(task, "task_id") else task.get("task_id", "")
            label = f"研究完成 ({dur:.1f}s)" if status == "completed" else "任务失败"
            events.append(evt("subagent_result", {"task_id": tid, "status": status, "label": label}))

    return events


async def _process_node_output(node_name: str, output: dict, evt, stream):
    """Side-effect processing for node outputs (logging, etc.)."""
    pass
