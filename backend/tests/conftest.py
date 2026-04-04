"""Shared test fixtures."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage


class MockChatModel:
    """Mock LLM that returns predefined responses."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Mock response"]
        self._call_count = 0

    def invoke(self, messages, **kwargs):
        resp = self.responses[self._call_count % len(self.responses)]
        self._call_count += 1
        return AIMessage(content=resp)

    def bind_tools(self, tools, **kwargs):
        """Return self for chaining -- tool calls are mocked via responses."""
        return self


@pytest.fixture
def mock_llm():
    return MockChatModel()


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config.yaml."""
    config = tmp_path / "config.yaml"
    config.write_text("""
model:
  default: "gpt-4o-mini"
executor:
  scheduler_workers: 2
  execution_workers: 2
  default_timeout: 30
memory:
  token_budget: 200
  decay_days: 30
  decay_factor: 0.8
  min_confidence: 0.5
  max_facts: 20
skills:
  dirs: []
graph:
  max_iterations: 2
""")
    return config
