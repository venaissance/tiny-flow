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

from core.compaction import ensure_message_ids, get_async_compactor
from core.graph.builder import build_graph
from core.memory.engine import get_memory_engine
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)
router = APIRouter()

NODE_LABELS = {
    "router": "正在分析您的问题...",
    "respond": "正在生成回复...",
    "think_respond": "正在深度推理...",
    "plan": "正在制定执行计划...",
    "dispatch": "正在分派并行任务...",
    "skill_node": "正在匹配专业技能...",
    "execute": "正在执行任务...",
    "merge": "正在汇总并行结果...",
    "reflector": "正在审查执行结果...",
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
            "messages": ensure_message_ids([HumanMessage(content=request.message)]),
            "route": None,
            "pending_tasks": [],
            "completed_tasks": [],
            "previous_round_output": "",
            "iteration": 0,
            "memory_context": "",
            "metadata": {"thread_id": request.thread_id},
            "last_tool_calls": [],
            "todos": [],
            "execution_mode": "",
        }
        config = {"configurable": {"thread_id": request.thread_id}, "recursion_limit": 50}

        def _current_summary_event() -> dict | None:
            """Build a context_compacted event from the async compactor's
            latest record, or None if there isn't one yet."""
            rec = get_async_compactor().get(request.thread_id)
            if not rec or not rec.summary:
                return None
            retention = get_async_compactor().retention_window
            return evt("context_compacted", {
                "original_messages": rec.summarized_up_to + retention,
                "compacted_to": retention,
                "strategy": "smart",
                "summary_preview": rec.summary[:200],
                "_summary_gen_at": rec.generated_at,
            })

        try:
            # Surface durable cross-thread user memory at stream start.
            try:
                _facts = get_memory_engine().get_facts()
                if _facts:
                    yield evt("user_memory", {
                        "facts": [
                            {
                                "id": f.id,
                                "content": f.content,
                                "category": f.category,
                                "confidence": round(f.confidence, 3),
                                "access_count": f.access_count,
                                "score_breakdown": f.score_breakdown or {},
                            }
                            for f in _facts
                        ],
                    })
            except Exception:  # noqa: BLE001
                pass

            # Surface any prior per-thread summary as well.
            _last_seen = None
            initial_evt = _current_summary_event()
            if initial_evt is not None:
                _last_seen = initial_evt["data"]
                yield initial_evt

            # Track which nodes we've seen to send progress events once
            seen_nodes: set[str] = set()
            # Track which node is currently producing LLM tokens
            current_llm_node: str | None = None
            # Buffer to detect node-level outputs (for tool calls, tasks, etc.)
            pending_node_output: dict | None = None
            # Track <think>...</think> blocks for filtering (MiniMax M2.7)
            in_think = False

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
                    if isinstance(output, dict):
                        # Extract events from ANY node output (not just NODE_LABELS)
                        for e in _extract_node_events(name, output, evt):
                            yield e
                        # Progress label for known nodes
                        if name in NODE_LABELS and name not in seen_nodes:
                            pass  # already sent via on_chain_start

                # --- Token-level LLM streaming ---
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        # Filter <think>...</think> reasoning blocks (MiniMax M2.7)
                        # Track in_think state across streaming chunks
                        if "<think>" in content:
                            in_think = True
                            content = content.split("<think>")[0]
                        if in_think:
                            if "</think>" in content:
                                in_think = False
                                content = content.split("</think>", 1)[-1]
                            else:
                                continue  # Still inside think block, skip
                        if not content:
                            continue
                        # Only stream content from respond/reflector nodes (final output)
                        tags = event.get("tags", []) or []
                        parent = event.get("metadata", {}).get("langgraph_node", "")
                        # Skip compaction summarizer tokens — they run inside
                        # respond's before_node and would otherwise leak the
                        # "米泽 is…" summary into the reply stream.
                        if "compaction_summarizer" in tags:
                            continue
                        if parent in ("respond", "think_respond", "reflector", "execute", "merge"):
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

            # Before closing, check if an async compaction finished DURING
            # this stream — if so, surface the fresh summary now instead of
            # making the user wait for the next turn.
            late_evt = _current_summary_event()
            if late_evt is not None and late_evt["data"] != _last_seen:
                yield late_evt

            yield evt("done", {})
        except Exception as e:
            logger.exception(f"Chat stream error: {e}")
            yield evt("error", {"error": str(e)})
        finally:
            # Fire-and-forget: both run off the hot path so user never waits.
            #   1. Rolling per-thread summary (AsyncCompactor)
            #   2. Durable cross-thread user facts (MemoryEngine)
            try:
                get_async_compactor().schedule(request.thread_id, graph, config)
            except Exception as e:  # noqa: BLE001
                logger.warning("AsyncCompactor schedule failed: %s", e)
            try:
                get_memory_engine().schedule_extraction(request.thread_id, graph, config)
            except Exception as e:  # noqa: BLE001
                logger.warning("MemoryEngine schedule failed: %s", e)

    return EventSourceResponse(event_stream())


def _extract_node_events(node_name: str, output: dict, evt) -> list[dict]:
    """Extract SSE events from a node's structured output."""
    events = []

    # NOTE: Reflector messages are NOT re-emitted here — their content was
    # already streamed via on_chat_model_stream during the execute phase.
    # Emitting again would duplicate the output.

    # Execution mode selected (4-way router)
    if "execution_mode" in output and output["execution_mode"]:
        mode = output["execution_mode"]
        mode_labels = {"flash": "⚡ 快速回答", "thinking": "🧠 深度推理", "pro": "📋 规划执行", "ultra": "🚀 并行研究"}
        desc = mode_labels.get(mode, mode)
        events.append(evt("mode_selected", {"mode": mode, "reason": f"自动选择 {desc} 模式"}))
        events.append(evt("thinking", {"node": "router", "content": f"决策: {desc}"}))

    # TODO updates (from plan node or execute node)
    if "todos" in output and output["todos"]:
        todos = output["todos"]
        todo_data = []
        for t in todos:
            try:
                todo_data.append({
                    "id": getattr(t, "id", str(t)),
                    "content": getattr(t, "content", str(t)),
                    "status": getattr(t, "status", "pending"),
                    "error": getattr(t, "error", None),
                })
            except Exception:
                todo_data.append({"id": "?", "content": str(t), "status": "pending", "error": None})
        if todo_data:
            events.append(evt("todo_update", {"todos": todo_data}))

    # Loop detection warning
    if output.get("_loop_terminated"):
        events.append(evt("loop_warning", {"iteration": 0, "message": output.get("_loop_reason", "检测到循环")}))

    # Context compaction
    if output.get("_context_compacted"):
        summary = output.get("_context_summary", "")
        strategy = output.get("_compaction_strategy", "truncate")
        events.append(evt("context_compacted", {
            "original_messages": output.get("_original_count", 0),
            "compacted_to": output.get("_compacted_count", 0),
            "strategy": strategy,
            "summary_preview": summary[:200] if summary else "",
        }))

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
            if status == "completed":
                label = f"研究完成 ({dur:.1f}s)"
            elif status == "timed_out":
                label = "任务超时"
            else:
                label = "任务失败"
            events.append(evt("subagent_result", {"task_id": tid, "status": status, "label": label}))

    return events


async def _process_node_output(node_name: str, output: dict, evt, stream):
    """Side-effect processing for node outputs (logging, etc.)."""
    pass
