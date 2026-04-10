"""Tests for _extract_node_events() serialization in chat.py."""
from __future__ import annotations

import json

import pytest

from app.gateway.routers.chat import _extract_node_events
from core.executor.task import TaskResult, TaskSpec, TodoItem


# ---------------------------------------------------------------------------
# Helper: deterministic evt() builder (mirrors the one inside event_stream)
# ---------------------------------------------------------------------------

def _make_evt():
    counter = [0]

    def evt(event_type: str, data: dict) -> dict:
        counter[0] += 1
        return {
            "id": str(counter[0]),
            "event": event_type,
            "data": json.dumps(data, ensure_ascii=False),
        }

    return evt


# ---------------------------------------------------------------------------
# mode_selected
# ---------------------------------------------------------------------------

class TestModeSelected:
    @pytest.mark.parametrize("mode,expected_label", [
        ("flash", "\u26a1 \u5feb\u901f\u56de\u7b54"),     # ⚡ 快速回答
        ("thinking", "\U0001f9e0 \u6df1\u5ea6\u63a8\u7406"),   # 🧠 深度推理
        ("pro", "\U0001f4cb \u89c4\u5212\u6267\u884c"),     # 📋 规划执行
        ("ultra", "\U0001f680 \u5e76\u884c\u7814\u7a76"),   # 🚀 并行研究
    ])
    def test_mode_selected_for_each_mode(self, mode, expected_label):
        evt = _make_evt()
        output = {"execution_mode": mode}
        events = _extract_node_events("router", output, evt)

        mode_events = [e for e in events if e["event"] == "mode_selected"]
        assert len(mode_events) == 1

        data = json.loads(mode_events[0]["data"])
        assert data["mode"] == mode
        assert expected_label in data["reason"]

    def test_mode_selected_not_emitted_when_empty(self):
        evt = _make_evt()
        output = {"execution_mode": ""}
        events = _extract_node_events("router", output, evt)
        mode_events = [e for e in events if e["event"] == "mode_selected"]
        assert len(mode_events) == 0

    def test_mode_selected_not_emitted_when_missing(self):
        evt = _make_evt()
        events = _extract_node_events("router", {}, evt)
        mode_events = [e for e in events if e["event"] == "mode_selected"]
        assert len(mode_events) == 0

    def test_mode_selected_also_emits_thinking_event(self):
        evt = _make_evt()
        output = {"execution_mode": "pro"}
        events = _extract_node_events("router", output, evt)
        thinking_events = [e for e in events if e["event"] == "thinking"]
        assert len(thinking_events) == 1
        data = json.loads(thinking_events[0]["data"])
        assert data["node"] == "router"


# ---------------------------------------------------------------------------
# todo_update
# ---------------------------------------------------------------------------

class TestTodoUpdate:
    def test_todo_update_with_items(self):
        evt = _make_evt()
        todos = [
            TodoItem(id="t1", content="Search for info", status="pending"),
            TodoItem(id="t2", content="Write report", status="in_progress"),
        ]
        output = {"todos": todos}
        events = _extract_node_events("plan", output, evt)

        todo_events = [e for e in events if e["event"] == "todo_update"]
        assert len(todo_events) == 1

        data = json.loads(todo_events[0]["data"])
        assert len(data["todos"]) == 2
        assert data["todos"][0]["id"] == "t1"
        assert data["todos"][0]["content"] == "Search for info"
        assert data["todos"][0]["status"] == "pending"
        assert data["todos"][1]["status"] == "in_progress"

    def test_todo_update_empty_list_no_event(self):
        evt = _make_evt()
        output = {"todos": []}
        events = _extract_node_events("plan", output, evt)
        todo_events = [e for e in events if e["event"] == "todo_update"]
        assert len(todo_events) == 0

    def test_todo_update_missing_key_no_event(self):
        evt = _make_evt()
        events = _extract_node_events("plan", {}, evt)
        todo_events = [e for e in events if e["event"] == "todo_update"]
        assert len(todo_events) == 0

    def test_todo_update_with_error_field(self):
        evt = _make_evt()
        todos = [TodoItem(id="t1", content="Failing task", status="failed", error="timeout")]
        output = {"todos": todos}
        events = _extract_node_events("execute", output, evt)

        data = json.loads(events[0]["data"])
        assert data["todos"][0]["error"] == "timeout"

    def test_todo_update_malformed_item_no_crash(self):
        """Items without proper attributes should be serialized gracefully."""
        evt = _make_evt()
        # Simulate a malformed todo item (plain string instead of TodoItem)
        output = {"todos": ["just a string", 42]}
        events = _extract_node_events("plan", output, evt)
        # Should not crash, and should produce a todo_update
        todo_events = [e for e in events if e["event"] == "todo_update"]
        assert len(todo_events) == 1
        data = json.loads(todo_events[0]["data"])
        assert len(data["todos"]) == 2
        # Malformed items get fallback serialization
        for t in data["todos"]:
            assert "id" in t
            assert "content" in t
            assert "status" in t


# ---------------------------------------------------------------------------
# subagent_status (from pending_tasks)
# ---------------------------------------------------------------------------

class TestSubagentStatus:
    def test_subagent_status_from_pending_tasks(self):
        evt = _make_evt()
        tasks = [
            TaskSpec(id="task_abc", type="subagent", skill_name="deep-research"),
            TaskSpec(id="task_def", type="skill_subagent", agent_type="general"),
        ]
        output = {"pending_tasks": tasks}
        events = _extract_node_events("dispatch", output, evt)

        status_events = [e for e in events if e["event"] == "subagent_status"]
        assert len(status_events) == 2

        d0 = json.loads(status_events[0]["data"])
        assert d0["task_id"] == "task_abc"
        assert d0["status"] == "running"
        assert "deep-research" in d0["label"]

        d1 = json.loads(status_events[1]["data"])
        assert d1["task_id"] == "task_def"
        assert "general" in d1["label"]

    def test_subagent_status_empty_pending(self):
        evt = _make_evt()
        output = {"pending_tasks": []}
        events = _extract_node_events("dispatch", output, evt)
        assert all(e["event"] != "subagent_status" for e in events)

    def test_subagent_status_no_skill_name_fallback(self):
        """When both skill_name and agent_type are None, label uses 'research'."""
        evt = _make_evt()
        task = TaskSpec(id="t1", type="subagent", skill_name=None, agent_type=None)
        output = {"pending_tasks": [task]}
        events = _extract_node_events("dispatch", output, evt)

        data = json.loads(events[0]["data"])
        assert "research" in data["label"]


# ---------------------------------------------------------------------------
# subagent_result (from completed_tasks)
# ---------------------------------------------------------------------------

class TestSubagentResult:
    def test_subagent_result_completed(self):
        evt = _make_evt()
        results = [
            TaskResult(task_id="r1", status="completed", output="done", duration_seconds=1.5),
        ]
        output = {"completed_tasks": results}
        events = _extract_node_events("execute", output, evt)

        result_events = [e for e in events if e["event"] == "subagent_result"]
        assert len(result_events) == 1

        data = json.loads(result_events[0]["data"])
        assert data["task_id"] == "r1"
        assert data["status"] == "completed"
        assert "1.5s" in data["label"]

    def test_subagent_result_failed(self):
        evt = _make_evt()
        results = [
            TaskResult(task_id="r2", status="failed", error="timeout"),
        ]
        output = {"completed_tasks": results}
        events = _extract_node_events("execute", output, evt)

        data = json.loads(events[0]["data"])
        assert data["status"] == "failed"
        assert "\u4efb\u52a1\u5931\u8d25" in data["label"]  # "任务失败"

    def test_subagent_result_from_dict(self):
        """completed_tasks can also be plain dicts (e.g., from deserialization)."""
        evt = _make_evt()
        output = {"completed_tasks": [{"task_id": "d1", "status": "completed"}]}
        events = _extract_node_events("execute", output, evt)

        result_events = [e for e in events if e["event"] == "subagent_result"]
        assert len(result_events) == 1
        data = json.loads(result_events[0]["data"])
        assert data["task_id"] == "d1"

    def test_subagent_result_empty(self):
        evt = _make_evt()
        output = {"completed_tasks": []}
        events = _extract_node_events("execute", output, evt)
        assert all(e["event"] != "subagent_result" for e in events)


# ---------------------------------------------------------------------------
# tool_calls (from last_tool_calls)
# ---------------------------------------------------------------------------

class TestToolCalls:
    def test_tool_calls_emitted(self):
        evt = _make_evt()
        output = {
            "last_tool_calls": [
                {"name": "web_search", "query": "Python GIL", "preview": "results..."},
            ]
        }
        events = _extract_node_events("execute", output, evt)

        tc_events = [e for e in events if e["event"] == "tool_call"]
        assert len(tc_events) == 1
        data = json.loads(tc_events[0]["data"])
        assert data["name"] == "web_search"
        assert data["query"] == "Python GIL"

    def test_tool_calls_empty(self):
        evt = _make_evt()
        output = {"last_tool_calls": []}
        events = _extract_node_events("execute", output, evt)
        assert all(e["event"] != "tool_call" for e in events)

    def test_tool_calls_defaults_for_missing_keys(self):
        evt = _make_evt()
        output = {"last_tool_calls": [{}]}
        events = _extract_node_events("execute", output, evt)

        data = json.loads(events[0]["data"])
        assert data["name"] == "web_search"  # default
        assert data["query"] == ""
        assert data["preview"] == ""


# ---------------------------------------------------------------------------
# loop_warning
# ---------------------------------------------------------------------------

class TestLoopWarning:
    def test_loop_terminated_emits_warning(self):
        evt = _make_evt()
        output = {"_loop_terminated": True, "_loop_reason": "Max iterations reached"}
        events = _extract_node_events("reflector", output, evt)

        warns = [e for e in events if e["event"] == "loop_warning"]
        assert len(warns) == 1
        data = json.loads(warns[0]["data"])
        assert data["message"] == "Max iterations reached"

    def test_loop_not_terminated_no_warning(self):
        evt = _make_evt()
        output = {"_loop_terminated": False}
        events = _extract_node_events("reflector", output, evt)
        warns = [e for e in events if e["event"] == "loop_warning"]
        assert len(warns) == 0

    def test_loop_terminated_default_reason(self):
        evt = _make_evt()
        output = {"_loop_terminated": True}
        events = _extract_node_events("reflector", output, evt)
        data = json.loads(events[0]["data"])
        assert "\u68c0\u6d4b\u5230\u5faa\u73af" in data["message"]  # "检测到循环"


# ---------------------------------------------------------------------------
# context_compacted
# ---------------------------------------------------------------------------

class TestContextCompacted:
    def test_context_compacted_event(self):
        evt = _make_evt()
        output = {
            "_context_compacted": True,
            "_original_count": 20,
            "_compacted_count": 5,
        }
        events = _extract_node_events("think_respond", output, evt)

        cc_events = [e for e in events if e["event"] == "context_compacted"]
        assert len(cc_events) == 1
        data = json.loads(cc_events[0]["data"])
        assert data["original_messages"] == 20
        assert data["compacted_to"] == 5

    def test_context_not_compacted_no_event(self):
        evt = _make_evt()
        output = {"_context_compacted": False}
        events = _extract_node_events("think_respond", output, evt)
        cc_events = [e for e in events if e["event"] == "context_compacted"]
        assert len(cc_events) == 0


# ---------------------------------------------------------------------------
# reflector content emission
# ---------------------------------------------------------------------------

class TestReflectorContent:
    def test_reflector_does_not_duplicate_content(self):
        """Reflector messages are NOT re-emitted (already streamed via execute)."""
        evt = _make_evt()

        class FakeMessage:
            content = "Line 1\nLine 2\nLine 3"

        output = {"messages": [FakeMessage()]}
        events = _extract_node_events("reflector", output, evt)

        content_events = [e for e in events if e["event"] == "content"]
        assert len(content_events) == 0  # No duplicate emission

    def test_non_reflector_does_not_emit_content(self):
        """Only the reflector node emits content from messages in output."""
        evt = _make_evt()

        class FakeMessage:
            content = "should not appear"

        output = {"messages": [FakeMessage()]}
        events = _extract_node_events("respond", output, evt)
        content_events = [e for e in events if e["event"] == "content"]
        assert len(content_events) == 0


# ---------------------------------------------------------------------------
# Event format invariants
# ---------------------------------------------------------------------------

class TestEventFormat:
    def test_evt_has_required_fields(self):
        evt = _make_evt()
        output = {"execution_mode": "flash", "todos": [TodoItem(content="step 1")]}
        events = _extract_node_events("router", output, evt)

        for e in events:
            assert "id" in e
            assert "event" in e
            assert "data" in e
            # data must be valid JSON
            parsed = json.loads(e["data"])
            assert isinstance(parsed, dict)

    def test_evt_ids_are_sequential(self):
        evt = _make_evt()
        output = {
            "execution_mode": "pro",
            "todos": [TodoItem(content="a"), TodoItem(content="b")],
        }
        events = _extract_node_events("router", output, evt)
        ids = [int(e["id"]) for e in events]
        assert ids == sorted(ids)
        # IDs start at 1 and increment
        assert ids[0] == 1

    def test_combined_output_produces_multiple_event_types(self):
        """A single node output dict can produce events of different types."""
        evt = _make_evt()
        output = {
            "execution_mode": "ultra",
            "todos": [TodoItem(content="task A")],
            "_loop_terminated": True,
            "last_tool_calls": [{"name": "web_search", "query": "test"}],
        }
        events = _extract_node_events("execute", output, evt)
        event_types = {e["event"] for e in events}
        assert "mode_selected" in event_types
        assert "todo_update" in event_types
        assert "loop_warning" in event_types
        assert "tool_call" in event_types
