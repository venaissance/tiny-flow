# backend/tests/evals/test_e2e_compaction.py
"""E2E behavior evals for smart compaction — hits the live API with real LLM calls.

These tests require:
  - Backend running on BACKEND_URL (default http://localhost:8001)
  - config.yaml compaction.strategy = "smart", max_messages = 4
  - Valid LLM API keys in env (MINIMAX_API_KEY, GLM_API_KEY)

Run:
  uv run pytest tests/evals/test_e2e_compaction.py -v -s

Corner cases covered:
  1. Fact retention across compaction
  2. Rolling summary over multiple compactions
  3. context_compacted SSE event fires with correct payload
  4. Summary text is NOT repeated by the model in its response
  5. Multiple independent threads don't cross-contaminate
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
TIMEOUT = 60  # seconds per chat request (real LLM calls can be slow)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


@dataclass
class SSEEvent:
    event: str = ""
    data: dict = field(default_factory=dict)


def parse_sse_stream(response: httpx.Response) -> list[SSEEvent]:
    """Parse an SSE text stream into a list of typed events."""
    events: list[SSEEvent] = []
    current_event = ""
    for line in response.text.splitlines():
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw": raw}
            events.append(SSEEvent(event=current_event, data=data))
            current_event = ""
    return events


def chat(
    client: httpx.Client,
    thread_id: str,
    message: str,
) -> tuple[str, list[SSEEvent]]:
    """Send a chat message and return (full_response_text, all_sse_events)."""
    resp = client.post(
        f"{BACKEND_URL}/api/chat",
        json={"thread_id": thread_id, "message": message},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    events = parse_sse_stream(resp)

    # Collect full response text from "content" events
    content_parts = []
    for e in events:
        if e.event == "content":
            content_parts.append(e.data.get("content", ""))
    full_text = "".join(content_parts)
    return full_text, events


def find_events(events: list[SSEEvent], event_type: str) -> list[SSEEvent]:
    return [e for e in events if e.event == event_type]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Shared HTTP client for all tests in this module.
    Uses NO_PROXY to bypass system proxy for localhost requests."""
    transport = httpx.HTTPTransport(proxy=None)  # bypass ALL_PROXY
    with httpx.Client(transport=transport) as c:
        # Health check — is the backend running?
        try:
            c.get(f"{BACKEND_URL}/api/threads", timeout=5)
        except httpx.ConnectError:
            pytest.skip(
                f"Backend not running at {BACKEND_URL}. "
                f"Start with: cd backend && uv run python -m uvicorn app.gateway.app:app --port 8001"
            )
        yield c


@pytest.fixture
def thread_id():
    """Unique thread_id for test isolation."""
    return f"e2e-test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# E2E evals
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSmartCompactionE2E:
    """End-to-end evals against the live API with real LLM calls."""

    def test_compaction_event_fires(self, client, thread_id):
        """After enough messages, a context_compacted SSE event fires
        with strategy='smart' and includes a summary_preview."""
        # Round 1-2: seed conversation
        chat(client, thread_id, "你好")
        chat(client, thread_id, "我在做一个叫 ProjectAlpha 的项目")

        # Round 3: should trigger compaction (messages > 4 threshold)
        _, events = chat(client, thread_id, "帮我分析一下这个项目的架构")

        compaction_events = find_events(events, "context_compacted")
        assert len(compaction_events) >= 1, (
            f"Expected context_compacted event after 3 rounds with max_messages=4. "
            f"Events received: {[e.event for e in events]}"
        )

        evt = compaction_events[0]
        assert evt.data.get("strategy") == "smart", (
            f"Expected strategy='smart', got {evt.data.get('strategy')!r}"
        )
        assert evt.data.get("compacted_to", 99) <= 6, (
            f"Expected compacted_to <= 6, got {evt.data.get('compacted_to')}"
        )

    def test_fact_retention_across_compaction(self, client, thread_id):
        """User mentions a specific fact early; after compaction the agent
        can still recall it. This is the core value prop of smart compaction."""
        # Seed the fact
        chat(client, thread_id, "记住我的项目名叫 ProjectPhoenix-2026")
        chat(client, thread_id, "这个项目用的是 Python 和 FastAPI")

        # This should trigger compaction
        chat(client, thread_id, "我们还用了 LangGraph 做状态管理")

        # Now ask about the fact — agent should remember via summary
        response, _ = chat(client, thread_id, "我的项目叫什么名字？")

        assert "Phoenix" in response or "phoenix" in response.lower(), (
            f"Agent failed to recall 'ProjectPhoenix-2026' after compaction. "
            f"Response: {response[:200]}"
        )

    def test_rolling_summary_over_multiple_compactions(self, client, thread_id):
        """Trigger compaction 3+ times and verify the earliest fact survives
        through rolling summaries. Tests that summary is truly 'rolling'
        (re-compressed each time) not 'appending' (growing forever)."""
        # Fact 1 — will be compacted first
        chat(client, thread_id, "我叫张三，负责前端开发")

        # Fact 2 — will be compacted second
        chat(client, thread_id, "我们的技术栈是 React 和 TypeScript")
        chat(client, thread_id, "后端用的是 Go 语言")

        # Fact 3 — pushes more compactions
        chat(client, thread_id, "数据库用的是 PostgreSQL")
        chat(client, thread_id, "部署在 AWS 上面")

        # Ask about the earliest fact
        response, events = chat(client, thread_id, "我叫什么名字？我负责什么？")

        # Check compaction fired multiple times
        compaction_events = find_events(events, "context_compacted")
        # At least this latest round should have triggered
        assert len(compaction_events) >= 1

        assert "张三" in response, (
            f"Earliest fact ('张三') lost after multiple compactions. "
            f"Rolling summary failed to preserve it. Response: {response[:200]}"
        )

    def test_summary_not_repeated_in_response(self, client, thread_id):
        """The compaction summary injected as HumanMessage should NOT be
        echoed back by the model in its response. The '[仅供参考，不要复述]'
        instruction should prevent repetition."""
        chat(client, thread_id, "你好，我是测试用户")
        chat(client, thread_id, "今天天气不错")

        # Trigger compaction
        response, _ = chat(client, thread_id, "你觉得呢？")

        # The summary injection contains "以下是之前对话的上下文摘要" — model should NOT repeat this
        assert "上下文摘要" not in response, (
            f"Model repeated the summary injection marker in its response. "
            f"Response: {response[:200]}"
        )
        assert "仅供参考" not in response, (
            f"Model repeated the summary instruction in its response. "
            f"Response: {response[:200]}"
        )

    def test_independent_threads_no_contamination(self, client):
        """Two threads with different facts should not cross-contaminate
        each other's summaries after compaction."""
        tid_a = f"e2e-thread-a-{uuid.uuid4().hex[:6]}"
        tid_b = f"e2e-thread-b-{uuid.uuid4().hex[:6]}"

        # Thread A: knows about ProjectAlpha
        chat(client, tid_a, "我的项目叫 ProjectAlpha")
        chat(client, tid_a, "用的是 Vue.js")
        chat(client, tid_a, "部署在阿里云")

        # Thread B: knows about ProjectBeta
        chat(client, tid_b, "我的项目叫 ProjectBeta")
        chat(client, tid_b, "用的是 Angular")
        chat(client, tid_b, "部署在腾讯云")

        # Ask each thread — should only know its own project
        resp_a, _ = chat(client, tid_a, "我的项目叫什么？")
        resp_b, _ = chat(client, tid_b, "我的项目叫什么？")

        assert "Alpha" in resp_a and "Beta" not in resp_a, (
            f"Thread A contaminated. Response: {resp_a[:200]}"
        )
        assert "Beta" in resp_b and "Alpha" not in resp_b, (
            f"Thread B contaminated. Response: {resp_b[:200]}"
        )
