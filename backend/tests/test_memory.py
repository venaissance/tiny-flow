"""Tests for memory system."""
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from core.memory.storage import MemoryStorage, Fact
from core.memory.merger import merge_facts, similarity
from core.memory.injector import build_memory_prompt, count_tokens
from core.memory.scorer import score_fact


class TestSimilarity:
    def test_identical(self):
        assert similarity("hello world", "hello world") == 1.0

    def test_similar(self):
        s = similarity("用户是前端工程师", "用户是一名前端工程师")
        assert s > 0.7

    def test_different(self):
        s = similarity("用户喜欢 Python", "天气真好")
        assert s < 0.3


class TestMergeFacts:
    def test_dedup_high_similarity(self):
        existing = [Fact(id="f1", content="用户是前端工程师", category="context", confidence=0.8, source_thread="t1")]
        new_facts = [Fact(id="f2", content="用户是一名前端工程师", category="context", confidence=0.7, source_thread="t2")]
        result = merge_facts(new_facts, existing)
        assert len(result) == 1
        assert result[0].confidence == 0.8

    def test_new_fact_appended(self):
        existing = [Fact(id="f1", content="用户喜欢 Python", category="preference", confidence=0.9, source_thread="t1")]
        new_facts = [Fact(id="f2", content="用户在字节跳动工作", category="context", confidence=0.8, source_thread="t2")]
        result = merge_facts(new_facts, existing)
        assert len(result) == 2


class TestMemoryStorage:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStorage(path)
        fact = Fact(id="f1", content="test", category="context", confidence=0.9)
        store.add_fact(fact)
        store2 = MemoryStorage(path)
        facts = store2.get_facts()
        assert len(facts) == 1
        assert facts[0].content == "test"

    def test_decay(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStorage(path)
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        fact = Fact(id="f1", content="old fact", category="context", confidence=1.0, last_verified=old_date, access_count=1)
        store.add_fact(fact)
        store.apply_decay(decay_days=30, decay_factor=0.8)
        facts = store.get_facts()
        assert facts[0].confidence < 1.0


class TestInjector:
    def test_budget_respected(self):
        facts = [Fact(id=f"f{i}", content=f"Fact number {i} with some content", category="context", confidence=0.9) for i in range(50)]
        prompt = build_memory_prompt(facts, token_budget=100)
        assert count_tokens(prompt) <= 120

    def test_low_confidence_filtered(self):
        facts = [
            Fact(id="f1", content="High confidence fact", category="context", confidence=0.9),
            Fact(id="f2", content="Low confidence fact", category="context", confidence=0.3),
        ]
        prompt = build_memory_prompt(facts, min_confidence=0.7)
        assert "High confidence" in prompt
        assert "Low confidence" not in prompt


class TestScorer:
    def test_new_fact_score(self):
        fact = Fact(content="用户是一名全栈工程师，有五年经验", category="context")
        score = score_fact(fact, [])
        assert 0.0 < score <= 1.0

    def test_repeated_fact_higher_score(self):
        fact = Fact(content="用户使用 React", category="knowledge")
        existing = [Fact(content="用户使用 React 框架", category="knowledge", confidence=0.8)]
        score = score_fact(fact, existing)
        fact2 = Fact(content="用户喜欢吃苹果", category="preference")
        score2 = score_fact(fact2, existing)
        assert score > score2
