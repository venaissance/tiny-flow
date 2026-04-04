# tests/test_4way_router.py
"""Tests for the 4-way keyword routing fallback."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# Patch skill imports before importing the router module so tests
# don't depend on a real skill registry.
_empty_skills_patch = patch(
    "core.skills.registry.get_all_skills", return_value=[]
)
_empty_filter_patch = patch(
    "core.skills.router.keyword_filter", return_value=[]
)


@pytest.fixture(autouse=True)
def _patch_skills():
    with _empty_skills_patch, _empty_filter_patch:
        yield


from core.graph.nodes.router import _keyword_route_fallback_4way  # noqa: E402


# ---------------------------------------------------------------------------
# Flash — no keyword match returns None (caller defaults to flash)
# ---------------------------------------------------------------------------

class TestFlashFallback:
    def test_simple_factual_question(self):
        result = _keyword_route_fallback_4way("Python 的 GIL 是什么？")
        assert result is None

    def test_greeting(self):
        result = _keyword_route_fallback_4way("你好")
        assert result is None

    def test_plain_english(self):
        result = _keyword_route_fallback_4way("What is HTTP?")
        assert result is None


# ---------------------------------------------------------------------------
# Thinking — deep reasoning keywords
# ---------------------------------------------------------------------------

class TestThinkingFallback:
    def test_why_question(self):
        result = _keyword_route_fallback_4way("为什么 Rust 比 C++ 更安全？")
        assert result is not None
        assert result["execution_mode"] == "thinking"
        assert result["route"] == "direct"

    def test_analysis_keyword(self):
        result = _keyword_route_fallback_4way("分析一下单体和微服务的区别")
        assert result is not None
        assert result["execution_mode"] == "thinking"

    def test_explain_keyword(self):
        result = _keyword_route_fallback_4way("解释 CAP 定理")
        assert result is not None
        assert result["execution_mode"] == "thinking"

    def test_compare_keyword(self):
        result = _keyword_route_fallback_4way("对比 REST 和 GraphQL")
        assert result is not None
        assert result["execution_mode"] == "thinking"

    def test_reasoning_keyword(self):
        result = _keyword_route_fallback_4way("推理一下这个逻辑是否成立")
        assert result is not None
        assert result["execution_mode"] == "thinking"


# ---------------------------------------------------------------------------
# Pro — research keywords (skill match is tested separately)
# ---------------------------------------------------------------------------

class TestProFallback:
    def test_research_keyword(self):
        result = _keyword_route_fallback_4way("研究一下 WebSocket 协议")
        assert result is not None
        assert result["execution_mode"] == "pro"
        assert result["route"] == "subagent"

    def test_investigate_keyword(self):
        result = _keyword_route_fallback_4way("调研一下竞品方案")
        assert result is not None
        assert result["execution_mode"] == "pro"

    def test_search_keyword(self):
        result = _keyword_route_fallback_4way("搜索最新的 AI 论文")
        assert result is not None
        assert result["execution_mode"] == "pro"

    def test_lookup_keyword(self):
        result = _keyword_route_fallback_4way("查一下 Node.js 20 的新特性")
        assert result is not None
        assert result["execution_mode"] == "pro"

    def test_compare_research_keyword(self):
        result = _keyword_route_fallback_4way("比较 PostgreSQL 和 MySQL")
        assert result is not None
        assert result["execution_mode"] == "pro"

    def test_skill_match_routes_to_pro(self):
        """When a skill keyword matches, route should be pro."""
        mock_skill = MagicMock()
        mock_skill.name = "webpage_builder"
        with patch("core.skills.registry.get_all_skills", return_value=[mock_skill]), \
             patch("core.skills.router.keyword_filter", return_value=[mock_skill]):
            result = _keyword_route_fallback_4way("做一个网页")
        assert result is not None
        assert result["execution_mode"] == "pro"
        assert result["route"] == "subagent"


# ---------------------------------------------------------------------------
# Ultra — parallel intent with enumeration
# ---------------------------------------------------------------------------

class TestUltraFallback:
    def test_parallel_with_enumeration(self):
        result = _keyword_route_fallback_4way("分别总结这三篇文章：A、B、C")
        assert result is not None
        assert result["execution_mode"] == "ultra"
        assert result["route"] == "subagent"

    def test_simultaneous_with_comma(self):
        result = _keyword_route_fallback_4way("同时查一下 React，Vue 的最新版本")
        assert result is not None
        assert result["execution_mode"] == "ultra"

    def test_each_with_enumeration(self):
        result = _keyword_route_fallback_4way("各自分析这两个方案的优缺点，A、B")
        assert result is not None
        assert result["execution_mode"] == "ultra"

    def test_parallel_keyword_without_enumeration_falls_through(self):
        """Parallel keyword alone without enumeration should not trigger ultra."""
        result = _keyword_route_fallback_4way("同时学习")
        # No enumeration markers, so ultra should not match.
        # May match something else or return None.
        if result is not None:
            assert result["execution_mode"] != "ultra"


# ---------------------------------------------------------------------------
# Priority: skill match > ultra > thinking > research
# ---------------------------------------------------------------------------

class TestPriority:
    def test_skill_beats_reasoning(self):
        """Skill keyword match should take priority over reasoning keywords."""
        mock_skill = MagicMock()
        mock_skill.name = "analyzer"
        with patch("core.skills.registry.get_all_skills", return_value=[mock_skill]), \
             patch("core.skills.router.keyword_filter", return_value=[mock_skill]):
            result = _keyword_route_fallback_4way("分析并生成一个报告")
        assert result is not None
        assert result["execution_mode"] == "pro"

    def test_reasoning_beats_none(self):
        """Reasoning keywords should match when nothing higher-priority does."""
        result = _keyword_route_fallback_4way("为什么天是蓝的")
        assert result is not None
        assert result["execution_mode"] == "thinking"
