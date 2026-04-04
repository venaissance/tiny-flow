"""Tests for core.middleware — onion-model execution."""
from __future__ import annotations

import pytest

from core.middleware import Middleware, MiddlewareChain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class RecorderMiddleware(Middleware):
    """Records call order for assertion."""

    def __init__(self, tag: str, log: list[str]):
        self.tag = tag
        self.log = log

    def before_node(self, state: dict, node_name: str) -> dict:
        self.log.append(f"{self.tag}:before")
        return state

    def after_node(self, state: dict, node_name: str, output: dict) -> dict:
        self.log.append(f"{self.tag}:after")
        return output


class StateModifyingMiddleware(Middleware):
    """Injects a key into state during before_node."""

    def __init__(self, key: str, value):
        self.key = key
        self.value = value

    def before_node(self, state: dict, node_name: str) -> dict:
        return {**state, self.key: self.value}


class OutputModifyingMiddleware(Middleware):
    """Appends a marker to output during after_node."""

    def __init__(self, key: str, value):
        self.key = key
        self.value = value

    def after_node(self, state: dict, node_name: str, output: dict) -> dict:
        return {**output, self.key: self.value}


class FailingBeforeMiddleware(Middleware):
    """Raises in before_node to test error resilience."""

    def before_node(self, state: dict, node_name: str) -> dict:
        raise RuntimeError("boom in before")


class FailingAfterMiddleware(Middleware):
    """Raises in after_node to test error resilience."""

    def after_node(self, state: dict, node_name: str, output: dict) -> dict:
        raise RuntimeError("boom in after")


def identity_node(state: dict) -> dict:
    return {"echo": state.get("input", "none")}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMiddlewareBase:
    """Verify the base Middleware class is a safe no-op."""

    def test_before_node_returns_state_unchanged(self):
        mw = Middleware()
        state = {"a": 1}
        assert mw.before_node(state, "n") is state

    def test_after_node_returns_output_unchanged(self):
        mw = Middleware()
        output = {"b": 2}
        assert mw.after_node({}, "n", output) is output


class TestMiddlewareChainOrder:
    """Verify forward-before / reverse-after onion ordering."""

    def test_before_forward_after_reverse(self):
        log: list[str] = []
        chain = MiddlewareChain([
            RecorderMiddleware("A", log),
            RecorderMiddleware("B", log),
            RecorderMiddleware("C", log),
        ])
        chain.run_node("test", {"input": "x"}, identity_node)

        assert log == [
            "A:before", "B:before", "C:before",
            "C:after", "B:after", "A:after",
        ]

    def test_single_middleware(self):
        log: list[str] = []
        chain = MiddlewareChain([RecorderMiddleware("X", log)])
        chain.run_node("test", {}, identity_node)
        assert log == ["X:before", "X:after"]


class TestMiddlewareStateModification:
    """Verify middleware can transform state and output."""

    def test_before_injects_key_visible_to_node(self):
        """State modified by before_node is passed to the node function."""
        mw = StateModifyingMiddleware("injected", 42)
        chain = MiddlewareChain([mw])

        def node_fn(state: dict) -> dict:
            return {"saw_injected": state.get("injected")}

        result = chain.run_node("test", {}, node_fn)
        assert result == {"saw_injected": 42}

    def test_after_appends_to_output(self):
        mw = OutputModifyingMiddleware("extra", "added")
        chain = MiddlewareChain([mw])

        result = chain.run_node("test", {"input": "hi"}, identity_node)
        assert result == {"echo": "hi", "extra": "added"}

    def test_chained_state_modifications(self):
        """Multiple middlewares compose state transforms left-to-right."""
        chain = MiddlewareChain([
            StateModifyingMiddleware("a", 1),
            StateModifyingMiddleware("b", 2),
        ])

        def node_fn(state: dict) -> dict:
            return {"a": state.get("a"), "b": state.get("b")}

        result = chain.run_node("test", {}, node_fn)
        assert result == {"a": 1, "b": 2}


class TestEmptyChain:
    """An empty chain must simply forward to the node function."""

    def test_empty_chain_returns_node_output(self):
        chain = MiddlewareChain()
        result = chain.run_node("test", {"input": "hello"}, identity_node)
        assert result == {"echo": "hello"}

    def test_empty_chain_with_explicit_empty_list(self):
        chain = MiddlewareChain([])
        result = chain.run_node("test", {"input": "world"}, identity_node)
        assert result == {"echo": "world"}


class TestMiddlewareErrorResilience:
    """Middleware failures are logged but do not crash the chain."""

    def test_failing_before_does_not_block_node(self):
        chain = MiddlewareChain([FailingBeforeMiddleware()])
        result = chain.run_node("test", {"input": "ok"}, identity_node)
        assert result == {"echo": "ok"}

    def test_failing_after_does_not_lose_output(self):
        chain = MiddlewareChain([FailingAfterMiddleware()])
        result = chain.run_node("test", {"input": "ok"}, identity_node)
        assert result == {"echo": "ok"}

    def test_healthy_middleware_still_runs_around_failing_one(self):
        log: list[str] = []
        chain = MiddlewareChain([
            RecorderMiddleware("A", log),
            FailingBeforeMiddleware(),
            RecorderMiddleware("B", log),
        ])
        chain.run_node("test", {}, identity_node)
        assert "A:before" in log
        assert "B:before" in log
        assert "B:after" in log
        assert "A:after" in log
