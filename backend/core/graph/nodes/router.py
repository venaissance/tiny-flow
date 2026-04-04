# backend/core/graph/nodes/router.py
"""Router node — 3-way decision via LLM function calling."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from core.graph.state import GraphState

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """你是一个任务路由器。分析用户的请求，决定最佳处理方式。
使用提供的工具来做出路由决策。

路由规则（按优先级）：
1. **创造/生成类请求 → RouteSkillArgs**：用户要求创建、制作、生成具体产物时（如网页、图表、代码、UI、前端页面、可视化等）。
   示例："做一个 todolist 网页"、"画一个柱状图"、"写一个登录页面"、"生成一个 dashboard"
2. **研究/调研类请求 → RouteSubagentArgs**：用户要求调研、搜索、分析某个主题，需要从网上获取信息时。
   示例："调研一下 React vs Vue"、"帮我查一下最新 AI 新闻"、"分析一下竞品"
3. **简单问答 → RouteDirectArgs**：简单事实性问题或闲聊。

关键区分：
- "做/创建/生成/写/画/制作" + 具体产物 → skill（创造类）
- "查/研究/调研/分析/搜索/了解" + 主题 → subagent（研究类）
- 如果用户要求创造某个东西（即使描述复杂），优先走 skill 而非 subagent"""

# Use Pydantic models for cross-provider compatibility (OpenAI + Claude)
from pydantic import BaseModel, Field


class RouteDirectArgs(BaseModel):
    """简单问答，直接回答用户"""
    pass


class RouteSubagentArgs(BaseModel):
    """研究/调研类任务：需要搜索网络、获取外部信息、撰写分析报告。不用于创建/生成具体产物。"""
    task_description: str = Field(description="任务描述")
    suggested_agent_type: str = Field(
        default="general", description="agent 类型: general, code, research"
    )


class RouteSkillArgs(BaseModel):
    """创造/生成类任务：用户要求创建网页、图表、代码、UI 组件等具体产物。也用于匹配其他已注册的结构化工作流。"""
    skill_query: str = Field(description="用于匹配 skill 的查询")


ROUTER_TOOLS = [RouteDirectArgs, RouteSubagentArgs, RouteSkillArgs]


def _keyword_route_fallback(query: str) -> dict | None:
    """Keyword-based routing fallback when LLM function calling fails.

    Checks if the query matches any registered skill keywords. If so,
    routes to skill. Also detects research-intent keywords for subagent.
    """
    from core.skills.registry import get_all_skills
    from core.skills.router import keyword_filter

    skills = get_all_skills()
    candidates = keyword_filter(skills, query, max_candidates=1)
    if candidates:
        logger.info(f"Keyword fallback matched skill: {candidates[0].name}")
        return {"route": "skill", "metadata": {"skill_query": query}}

    # Research intent keywords
    research_keywords = ["研究", "调研", "分析", "搜索", "查", "了解", "调查", "比较"]
    if any(kw in query for kw in research_keywords):
        return {"route": "subagent", "metadata": {"task_description": query}}

    return None


def router_node(state: GraphState, model: Any) -> dict:
    """Decide routing: direct / subagent / skill.

    Uses LLM function calling first, then falls back to keyword matching
    if the model doesn't produce a tool call (common with weaker models).
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

            if name == "RouteDirectArgs":
                # Before accepting "direct", double-check with keyword fallback
                # because weaker models often default to direct for everything
                fallback = _keyword_route_fallback(user_query)
                if fallback:
                    logger.info(f"LLM said direct but keyword fallback overrides to {fallback['route']}")
                    return {**fallback, "metadata": {**state.get("metadata", {}), **fallback.get("metadata", {})}}
                return {"route": "direct"}
            elif name == "RouteSubagentArgs":
                return {"route": "subagent", "metadata": {
                    **state.get("metadata", {}),
                    "task_description": args.get("task_description", ""),
                    "suggested_agent_type": args.get("suggested_agent_type", "general"),
                }}
            elif name == "RouteSkillArgs":
                return {"route": "skill", "metadata": {
                    **state.get("metadata", {}),
                    "skill_query": args.get("skill_query", ""),
                }}
    except Exception as e:
        logger.warning(f"Router LLM failed: {e}, trying keyword fallback")

    # Fallback: keyword-based routing
    fallback = _keyword_route_fallback(user_query)
    if fallback:
        return {**fallback, "metadata": {**state.get("metadata", {}), **fallback.get("metadata", {})}}

    return {"route": "direct"}
