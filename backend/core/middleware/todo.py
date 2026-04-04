"""Middleware that injects and updates TODO plan state across graph nodes."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage

from core.executor.task import TodoItem
from core.middleware.base import Middleware

_STATUS_ICONS: dict[str, str] = {
    "pending": "\u25cb",       # ○
    "in_progress": "\u25c9",   # ◉
    "completed": "\u2705",     # ✅
    "failed": "\u274c",        # ❌
}


class TodoMiddleware(Middleware):
    """Injects a TODO summary into messages and reconciles completion signals."""

    # ---- before_node --------------------------------------------------------

    def before_node(
        self,
        state: dict[str, Any],
        node_name: str,
    ) -> dict[str, Any]:
        todos: list[TodoItem] | None = state.get("todos")
        if not todos:
            return state

        summary = self._build_summary(todos)
        todo_message = SystemMessage(content=summary)

        messages = list(state.get("messages", []))
        messages.append(todo_message)
        state["messages"] = messages

        return state

    # ---- after_node ---------------------------------------------------------

    def after_node(
        self,
        state: dict[str, Any],
        node_name: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        todos: list[TodoItem] | None = state.get("todos")
        if not todos:
            return output

        todo_index: dict[str, TodoItem] = {t.id: t for t in todos}
        changed = False

        for tid in output.get("completed_todo_ids", []):
            if tid in todo_index:
                todo_index[tid].status = "completed"
                changed = True

        for tid in output.get("failed_todo_ids", []):
            if tid in todo_index:
                todo_index[tid].status = "failed"
                changed = True

        if changed:
            output["todos"] = todos

        return output

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _build_summary(todos: list[TodoItem]) -> str:
        lines = ["Current TODO status:"]
        for item in todos:
            icon = _STATUS_ICONS.get(item.status, "?")
            lines.append(f"  {icon} [{item.id}] {item.content}")
        return "\n".join(lines)
