"""Middleware infrastructure — before/after hooks for graph nodes."""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Middleware:
    """Base class. Override before_node and/or after_node."""

    def before_node(self, state: dict, node_name: str) -> dict:
        return state

    def after_node(self, state: dict, node_name: str, output: dict) -> dict:
        return output


class MiddlewareChain:
    """Executes middleware around a node function.

    before_node: forward order  (mw1 -> mw2 -> mw3)
    after_node:  reverse order  (mw3 -> mw2 -> mw1) — Koa onion model
    """

    def __init__(self, middlewares: list[Middleware] | None = None):
        self.middlewares = middlewares or []

    def run_node(
        self,
        node_name: str,
        state: dict,
        node_fn: Callable[[dict], dict],
    ) -> dict:
        current_state = state
        for mw in self.middlewares:
            try:
                current_state = mw.before_node(current_state, node_name)
            except Exception as e:
                logger.warning(
                    f"Middleware {mw.__class__.__name__}.before_node failed: {e}"
                )

        output = node_fn(current_state)

        for mw in reversed(self.middlewares):
            try:
                output = mw.after_node(current_state, node_name, output)
            except Exception as e:
                logger.warning(
                    f"Middleware {mw.__class__.__name__}.after_node failed: {e}"
                )

        return output
