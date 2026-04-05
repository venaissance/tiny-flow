"""E2E tests with real GLM API -- verifies the full pipeline works.

Requires GLM_API_KEY to be set in the environment or .env file.
Skipped automatically in CI or when the key is absent.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import pytest

# Load .env so API key is available even when running pytest directly
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

requires_llm = pytest.mark.skipif(
    not os.getenv("GLM_API_KEY"),
    reason="Requires GLM_API_KEY environment variable",
)


@requires_llm
class TestModelFactory:
    """Test that GLM model can be created and invoked."""

    def test_create_glm_model(self):
        from core.models.factory import create_chat_model

        model = create_chat_model(name="glm-4-flash-250414")
        assert model is not None

    def test_glm_simple_invoke(self):
        from core.models.factory import create_chat_model
        from langchain_core.messages import HumanMessage

        model = create_chat_model(name="glm-4-flash-250414")
        response = model.invoke([HumanMessage(content="Say 'hello world' and nothing else.")])
        assert response.content is not None
        assert len(response.content) > 0
        print(f"GLM response: {response.content}")


@requires_llm
class TestDirectResponse:
    """Test the Router -> Respond path (simple questions)."""

    def test_simple_question(self):
        from core.models.factory import create_chat_model
        from core.graph.nodes.respond import respond_node
        from langchain_core.messages import HumanMessage

        model = create_chat_model(name="glm-4-flash-250414")
        state = {
            "messages": [HumanMessage(content="1+1等于几？只回答数字")],
            "route": "direct",
            "pending_tasks": [],
            "completed_tasks": [],
            "previous_round_output": "",
            "iteration": 0,
            "memory_context": "",
            "metadata": {},
        }
        result = respond_node(state, model)
        assert "messages" in result
        content = result["messages"][0].content
        print(f"Direct response: {content}")
        assert "2" in content


@requires_llm
class TestSkillMatching:
    """Test skill routing with real queries."""

    def test_deep_research_matches(self):
        from core.skills.registry import scan_skills
        from core.skills.router import keyword_filter

        skills = scan_skills(["skills/"])
        candidates = keyword_filter(skills, "帮我研究一下 Python 的异步编程")
        assert len(candidates) > 0
        assert any(s.name == "deep-research" for s in candidates)

    def test_code_review_matches(self):
        from core.skills.registry import scan_skills
        from core.skills.router import keyword_filter

        skills = scan_skills(["skills/"])
        candidates = keyword_filter(skills, "review 这段代码")
        assert len(candidates) > 0
        assert any(s.name == "code-review" for s in candidates)


@requires_llm
class TestMemoryPipeline:
    """Test memory extract -> score -> merge -> inject with real LLM."""

    def test_extract_and_inject(self, tmp_path):
        from core.models.factory import create_chat_model
        from core.memory.engine import MemoryEngine
        from langchain_core.messages import HumanMessage, AIMessage

        model = create_chat_model(name="glm-4-flash-250414")
        engine = MemoryEngine(storage_path=tmp_path / "memory.json", min_confidence=0.3)

        messages = [
            HumanMessage(content="我是一名前端工程师，主要用 React 和 TypeScript"),
            AIMessage(content="了解，React 和 TypeScript 是很好的技术栈。"),
        ]

        # Process synchronously for testing
        from core.memory.extractor import extract_facts
        from core.memory.scorer import score_facts
        from core.memory.merger import merge_facts

        new_facts = extract_facts(messages, model, "test-thread")
        print(f"Extracted {len(new_facts)} facts:")
        for f in new_facts:
            print(f"  [{f.category}] {f.content}")

        if new_facts:
            scored = score_facts(new_facts, [])
            merged = merge_facts(scored, [])
            engine.storage.save_facts(merged)

            prompt = engine.inject()
            print(f"Injected memory prompt:\n{prompt}")
            # Should contain something about React/TypeScript/frontend
            assert len(prompt) > 0


@requires_llm
class TestFullChatEndpoint:
    """Test the FastAPI chat endpoint with SSE streaming."""

    def test_chat_sse_stream(self):
        from fastapi.testclient import TestClient
        from app.gateway.app import app

        client = TestClient(app)

        response = client.post(
            "/api/chat",
            json={"message": "你好，请用一句话介绍你自己", "thread_id": "test-e2e"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Parse SSE events
        events = []
        for line in response.text.split("\n"):
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    events.append(data)
                except json.JSONDecodeError:
                    pass

        print(f"Received {len(events)} SSE events")
        # Should have at least one content event
        content_events = [e for e in events if "content" in e]
        assert len(content_events) > 0
        full_content = "".join(e.get("content", "") for e in content_events)
        print(f"Full response: {full_content}")
        assert len(full_content) > 0
