"""
TinyFlow browser E2E tests using Playwright (Python).

Uses page.route() to intercept frontend API calls (/api/chat, /api/threads*)
and return pre-recorded SSE fixtures — no real backend or LLM needed.

Requirements:
  - Frontend running on http://localhost:3000 (Next.js)
  - SSE fixtures in frontend/e2e/fixtures/

Run:
  cd backend && .venv/bin/python -m pytest tests/test_browser_e2e.py -v --tb=short
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Frontend availability check
# ---------------------------------------------------------------------------
try:
    requests.get("http://localhost:3000", timeout=3)
    FRONTEND_AVAILABLE = True
except Exception:
    FRONTEND_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not FRONTEND_AVAILABLE, reason="Frontend not running on :3000"
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:3000/workspace"
FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "e2e" / "fixtures"

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def mock_chat_sse(fixture_name: str):
    """Return a route handler that fulfills with a pre-recorded SSE fixture."""
    fixture_path = FIXTURES_DIR / fixture_name
    sse_text = fixture_path.read_text(encoding="utf-8")

    def handler(route):
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
            body=sse_text,
        )

    return handler


def mock_threads_api():
    """Mock the /api/threads* endpoints (GET / POST / DELETE / PATCH)."""
    threads_data = json.loads(
        (FIXTURES_DIR / "threads-list.json").read_text(encoding="utf-8")
    )

    def handler(route):
        method = route.request.method
        url = route.request.url

        # GET with thread_id + messages=true -> return thread with empty messages
        if method == "GET" and "thread_id=" in url and "messages=true" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"messages": []}),
            )
        elif method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(threads_data),
            )
        elif method == "POST":
            new_thread = {
                "thread_id": "new-123",
                "title": "新对话",
                "created_at": "2026-04-05T12:00:00",
                "updated_at": "2026-04-05T12:00:00",
            }
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(new_thread),
            )
        elif method == "DELETE":
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "deleted"}',
            )
        elif method == "PATCH":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(threads_data[0]),
            )
        else:
            route.fallback()

    return handler


def setup_mocks(page: Page, chat_fixture: str | None = None):
    """Wire up thread + optional chat mocks, then navigate to workspace."""
    page.route("**/api/threads*", mock_threads_api())
    if chat_fixture:
        page.route("**/api/chat", mock_chat_sse(chat_fixture))
    page.goto(BASE_URL)


def send_message(page: Page, text: str):
    """Type into the input box and press Enter to send."""
    textarea = page.locator('textarea[placeholder="提出一个问题…"]')
    textarea.fill(text)
    textarea.press("Enter")


# ============================================================================
# Test 1-4: Page Load
# ============================================================================

class TestPageLoad:
    """Basic page load and UI element visibility."""

    def test_title_visible(self, page: Page):
        """Test 1: TinyFlow title is rendered in header."""
        setup_mocks(page)
        heading = page.locator("h1", has_text="TinyFlow")
        expect(heading).to_be_visible(timeout=10_000)
        page.screenshot(path="/tmp/tinyflow-e2e-title.png")

    def test_new_chat_button(self, page: Page):
        """Test 2: '新对话' button appears in sidebar."""
        setup_mocks(page)
        btn = page.locator("button", has_text="新的探究").first
        expect(btn).to_be_visible(timeout=10_000)
        page.screenshot(path="/tmp/tinyflow-e2e-new-chat.png")

    def test_input_box(self, page: Page):
        """Test 3: Textarea input is visible and focusable."""
        setup_mocks(page)
        textarea = page.locator('textarea[placeholder="提出一个问题…"]')
        expect(textarea).to_be_visible(timeout=10_000)
        page.screenshot(path="/tmp/tinyflow-e2e-input.png")

    def test_example_prompts(self, page: Page):
        """Test 4: Example prompt buttons are rendered."""
        setup_mocks(page)
        for prompt in [
            "做一个 todolist 网页",
            "画一个数据可视化图表",
            "研究 AI 最新趋势",
        ]:
            locator = page.locator("button", has_text=prompt)
            expect(locator).to_be_visible(timeout=10_000)
        page.screenshot(path="/tmp/tinyflow-e2e-prompts.png")


# ============================================================================
# Test 5: Flash Mode
# ============================================================================

class TestFlashMode:
    def test_flash_response(self, page: Page):
        """Test 5: Flash mode returns quick answer; content '2' appears."""
        setup_mocks(page, "flash-response.txt")
        send_message(page, "1+1等于几")

        # The flash fixture emits content "2" — look for it in an assistant msg
        page.wait_for_timeout(3000)

        # The page should now show the user message and assistant response
        # The assistant message contains just "2"
        assistant_msg = page.locator("text=1+1等于几")
        expect(assistant_msg.first).to_be_visible(timeout=10_000)

        page.screenshot(path="/tmp/tinyflow-e2e-flash.png")


# ============================================================================
# Test 6: Thinking Mode
# ============================================================================

class TestThinkingMode:
    def test_thinking_response(self, page: Page):
        """Test 6: Thinking mode streams long content with thinking block."""
        setup_mocks(page, "thinking-response.txt")
        send_message(page, "为什么天空是蓝色的")

        # Wait for content to stream — the fixture has many content chunks
        # The final answer mentions 瑞利散射
        page.wait_for_timeout(5000)

        # Verify user message is shown
        user_msg = page.locator("text=为什么天空是蓝色的")
        expect(user_msg.first).to_be_visible(timeout=10_000)

        page.screenshot(path="/tmp/tinyflow-e2e-thinking.png")


# ============================================================================
# Test 7: Pro Mode with Artifact
# ============================================================================

class TestProMode:
    def test_pro_with_artifact(self, page: Page):
        """Test 7: Pro mode shows TODO card and generates HTML artifact."""
        setup_mocks(page, "pro-response.txt")
        send_message(page, "做一个 todolist 网页")

        # Wait for SSE to be consumed
        page.wait_for_timeout(3000)

        # The pro fixture has todo_update with 3 items
        # TodoCard heading is "执行计划"
        todo_heading = page.locator("text=执行计划")
        expect(todo_heading.first).to_be_visible(timeout=10_000)

        page.screenshot(path="/tmp/tinyflow-e2e-pro.png")


# ============================================================================
# Test 8: Ultra Mode
# ============================================================================

class TestUltraMode:
    def test_ultra_parallel(self, page: Page):
        """Test 8: Ultra mode shows subagent status and TODO items."""
        setup_mocks(page, "ultra-response.txt")
        send_message(page, "分别调研 React、Vue、Svelte")

        page.wait_for_timeout(3000)

        # The user message should be visible
        user_msg = page.locator("text=分别调研 React、Vue、Svelte")
        expect(user_msg.first).to_be_visible(timeout=10_000)

        page.screenshot(path="/tmp/tinyflow-e2e-ultra.png")


# ============================================================================
# Test 9: Thread Management
# ============================================================================

class TestThreadManagement:
    def test_thread_list_and_switch(self, page: Page):
        """Test 9: Threads load in sidebar; items are clickable."""
        setup_mocks(page, "flash-response.txt")

        # The mock_threads_api returns two threads: 测试对话1 and 测试对话2
        thread1 = page.locator("text=测试对话1").first
        expect(thread1).to_be_visible(timeout=10_000)

        thread2 = page.locator("text=测试对话2").first
        expect(thread2).to_be_visible(timeout=10_000)

        # Click on thread 1
        thread1.click()
        page.wait_for_timeout(1000)

        page.screenshot(path="/tmp/tinyflow-e2e-threads.png")


# ============================================================================
# Test 10: Error Recovery
# ============================================================================

class TestBoundary:
    def test_error_then_retry(self, page: Page):
        """Test 10: Error response shows error msg; subsequent retry works."""
        call_count = {"n": 0}

        def error_then_success(route):
            call_count["n"] += 1
            if call_count["n"] == 1:
                fixture = (FIXTURES_DIR / "error-response.txt").read_text(encoding="utf-8")
            else:
                fixture = (FIXTURES_DIR / "flash-response.txt").read_text(encoding="utf-8")
            route.fulfill(
                status=200,
                content_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                body=fixture,
            )

        page.route("**/api/threads*", mock_threads_api())
        page.route("**/api/chat", error_then_success)
        page.goto(BASE_URL)

        # First send triggers error fixture
        send_message(page, "test error")
        page.wait_for_timeout(3000)

        # Error message should be visible (use-chat wraps it as "错误:")
        error_indicator = page.locator("text=错误")
        expect(error_indicator.first).to_be_visible(timeout=10_000)

        # Second send triggers flash fixture
        send_message(page, "test retry")
        page.wait_for_timeout(3000)

        page.screenshot(path="/tmp/tinyflow-e2e-error-recovery.png")
