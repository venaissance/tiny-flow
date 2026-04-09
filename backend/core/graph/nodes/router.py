# backend/core/graph/nodes/router.py
"""Router node — 4-way decision via LLM function calling."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from core.graph.state import GraphState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — 4-way routing rules
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = """你是一个任务路由器。分析用户的请求，决定最佳处理方式。
使用提供的工具来做出路由决策。

路由规则（按优先级从高到低）：

1. **多个独立子任务 → RouteUltraArgs**：用户请求包含多个可以并行处理的独立子任务。
   示例：
   - "分别总结这三篇文章"
   - "同时查一下 React 和 Vue 的最新版本，再帮我生成一个对比表"
   - "帮我写一个登录页面，同时调研一下 OAuth 最佳实践"

2. **需要工具/搜索/生成/技能 → RouteProArgs**：用户要求创建、生成具体产物，或需要搜索网络获取信息，或需要调用技能（如 pulse 日报、制作 PPT/演示文稿），任务可分解为有序步骤。
   示例：
   - "做一个 todolist 网页"
   - "帮我查一下最新 AI 新闻"
   - "画一个柱状图"
   - "调研一下 React vs Vue"
   - "生成今日 Pulse 科技日报"
   - "帮我做一个演示文稿/PPT"

3. **需要深度分析推理 → RouteThinkingArgs**：用户的问题需要深入分析、推理、对比或解释，但不需要搜索外部信息或生成具体产物。
   示例：
   - "为什么 Rust 的所有权模型比 GC 更安全？"
   - "分析一下微服务和单体架构的优劣"
   - "解释 CAP 定理在分布式数据库中的取舍"
   - "对比 REST 和 GraphQL 的适用场景"

4. **简单问答 → RouteFlashArgs**：简单事实性问题或闲聊，一句话就能答完。
   示例：
   - "Python 的 GIL 是什么？"
   - "今天星期几？"
   - "HTTP 状态码 404 是什么意思？"

关键区分：
- 多个独立任务关键词（分别/各自/并行/同时 + 多个事项）→ ultra
- "做/创建/生成/写/画/制作" + 具体产物，或 "查/搜索/调研" + 信息获取 → pro
- 提到具体技能名（pulse/日报/PPT/演示文稿/slides）→ pro
- "分析/对比/为什么/解释/推理" + 深度思考 → thinking
- 简单事实性问题 → flash"""

# ---------------------------------------------------------------------------
# Pydantic schemas — one per route
# ---------------------------------------------------------------------------


class RouteFlashArgs(BaseModel):
    """简单问答，一句话能答完"""
    pass


class RouteThinkingArgs(BaseModel):
    """需要深度分析推理，但不需要搜索或生成具体产物"""
    reasoning_hint: str = Field(description="推理方向提示")


class RouteProArgs(BaseModel):
    """需要工具调用（搜索/生成网页/图表等），可分解为有序步骤"""
    task_description: str = Field(description="任务描述")
    estimated_steps: int = Field(default=3, description="预估步骤数")


class RouteUltraArgs(BaseModel):
    """多个独立子任务，需要并行执行"""
    subtasks: list[str] = Field(description="子任务列表")


ROUTER_TOOLS = [RouteFlashArgs, RouteThinkingArgs, RouteProArgs, RouteUltraArgs]

# Mapping: schema name → execution_mode
_SCHEMA_TO_MODE: dict[str, str] = {
    "RouteFlashArgs": "flash",
    "RouteThinkingArgs": "thinking",
    "RouteProArgs": "pro",
    "RouteUltraArgs": "ultra",
}

# Mapping: execution_mode → legacy route value consumed by builder.py
_MODE_TO_ROUTE: dict[str, str] = {
    "flash": "direct",
    "thinking": "direct",
    "pro": "subagent",
    "ultra": "subagent",
}

# ---------------------------------------------------------------------------
# Keyword-based fallback (4-way)
# ---------------------------------------------------------------------------


def _keyword_route_fallback_4way(query: str) -> dict | None:
    """Keyword-based 4-way routing fallback when LLM function calling fails.

    Priority order mirrors the system prompt:
      1. Skill keyword match → "pro"
      2. Parallel intent (分别/各自/并行/同时 + multiple items) → "ultra"
      3. Deep reasoning keywords → "thinking"
      4. Research keywords → "pro"
      5. No match → None  (caller defaults to flash)
    """
    # --- 0. Tool/skill trigger keywords → pro (HIGHEST PRIORITY) ---
    tool_keywords = [
        "pulse", "日报", "简报", "新闻速递",
        "ppt", "PPT", "演示文稿", "slides", "制作幻灯片",
        "生成", "制作", "创建", "做一个",
    ]
    if any(kw.lower() in query.lower() for kw in tool_keywords):
        return {
            "route": "subagent",
            "execution_mode": "pro",
            "metadata": {"task_description": query, "estimated_steps": 3},
        }

    # --- 1. Parallel intent → ultra (HIGHEST PRIORITY) ---
    # Must check BEFORE skill match, otherwise "调研" matches deep-research
    # and returns pro before ultra check runs.
    parallel_keywords = ["分别", "各自", "并行", "同时"]
    # Heuristic: parallel keyword present AND query contains list-like structure
    # (Chinese enumeration markers or multiple verbs/items)
    if any(kw in query for kw in parallel_keywords):
        # Check for enumeration patterns: 、 or multiple comma-separated items
        enum_markers = query.count("、") + query.count("，")
        if enum_markers >= 1:
            return {
                "route": "subagent",
                "execution_mode": "ultra",
                "metadata": {"subtasks": [query]},
            }

    # --- 2. Skill keyword match → pro ---
    from core.skills.registry import get_all_skills
    from core.skills.router import keyword_filter

    skills = get_all_skills()
    candidates = keyword_filter(skills, query, max_candidates=1)
    if candidates:
        logger.info(f"Keyword fallback matched skill: {candidates[0].name}")
        return {
            "route": "subagent",
            "execution_mode": "pro",
            "metadata": {"task_description": query, "estimated_steps": 3},
        }

    # --- 3. Deep reasoning keywords → thinking ---
    reasoning_keywords = ["分析", "对比", "为什么", "解释", "推理"]
    if any(kw in query for kw in reasoning_keywords):
        return {
            "route": "direct",
            "execution_mode": "thinking",
            "metadata": {"reasoning_hint": query},
        }

    # --- 4. Research keywords → pro ---
    research_keywords = ["研究", "调研", "搜索", "查", "了解", "调查", "比较"]
    if any(kw in query for kw in research_keywords):
        return {
            "route": "subagent",
            "execution_mode": "pro",
            "metadata": {"task_description": query, "estimated_steps": 3},
        }

    # --- 5. No match → None (defaults to flash) ---
    return None


# ---------------------------------------------------------------------------
# Main router node
# ---------------------------------------------------------------------------


def router_node(state: GraphState, model: Any) -> dict:
    """Decide routing: flash / thinking / pro / ultra.

    Uses LLM function calling first, then falls back to keyword matching
    if the model doesn't produce a tool call (common with weaker models).

    Returns dict with ``route`` (legacy, for builder.py edges) and
    ``execution_mode`` (new 4-way label) in addition to ``metadata``.
    """
    messages = state["messages"]
    user_query = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and isinstance(msg.content, str):
            user_query = msg.content
            break

    try:
        from langchain_core.messages import SystemMessage

        router_messages = [SystemMessage(content=ROUTER_SYSTEM)] + list(messages)
        bound = model.bind_tools(ROUTER_TOOLS)
        response = bound.invoke(router_messages)

        if response.tool_calls:
            call = response.tool_calls[0]
            name = call["name"]
            args = call.get("args", {})

            execution_mode = _SCHEMA_TO_MODE.get(name, "flash")
            route = _MODE_TO_ROUTE[execution_mode]

            if name == "RouteFlashArgs":
                # Before accepting flash, double-check with keyword fallback
                # because weaker models often default to flash for everything
                fallback = _keyword_route_fallback_4way(user_query)
                if fallback:
                    logger.info(
                        "LLM said flash but keyword fallback overrides "
                        f"to {fallback['execution_mode']}"
                    )
                    return {
                        **fallback,
                        "metadata": {
                            **state.get("metadata", {}),
                            **fallback.get("metadata", {}),
                        },
                    }
                return {"route": "direct", "execution_mode": "flash"}

            elif name == "RouteThinkingArgs":
                return {
                    "route": route,
                    "execution_mode": execution_mode,
                    "metadata": {
                        **state.get("metadata", {}),
                        "reasoning_hint": args.get("reasoning_hint", ""),
                    },
                }

            elif name == "RouteProArgs":
                # Check if pro should actually be ultra (LLM often misses parallel signals)
                fallback = _keyword_route_fallback_4way(user_query)
                if fallback and fallback.get("execution_mode") == "ultra":
                    logger.info("LLM said pro but keyword detects ultra (parallel signals)")
                    return {**fallback, "metadata": {**state.get("metadata", {}), **fallback.get("metadata", {})}}
                return {
                    "route": route,
                    "execution_mode": execution_mode,
                    "metadata": {
                        **state.get("metadata", {}),
                        "task_description": args.get("task_description", ""),
                        "estimated_steps": args.get("estimated_steps", 3),
                    },
                }

            elif name == "RouteUltraArgs":
                return {
                    "route": route,
                    "execution_mode": execution_mode,
                    "metadata": {
                        **state.get("metadata", {}),
                        "subtasks": args.get("subtasks", []),
                    },
                }

    except Exception as e:
        logger.warning(f"Router LLM failed: {e}, trying keyword fallback")

    # Fallback: keyword-based routing
    fallback = _keyword_route_fallback_4way(user_query)
    if fallback:
        return {
            **fallback,
            "metadata": {
                **state.get("metadata", {}),
                **fallback.get("metadata", {}),
            },
        }

    return {"route": "direct", "execution_mode": "flash"}
