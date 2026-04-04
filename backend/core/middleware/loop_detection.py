# backend/core/middleware/loop_detection.py
"""Middleware that detects and terminates stale reflector loops."""
from __future__ import annotations

import logging
from difflib import SequenceMatcher

from core.middleware.base import Middleware

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(Middleware):
    """Terminate the reflector loop when iterations are exhausted or output
    has stopped changing (high similarity with the previous round)."""

    def __init__(
        self,
        max_iterations: int = 3,
        similarity_threshold: float = 0.9,
    ) -> None:
        self.max_iterations = max_iterations
        self.similarity_threshold = similarity_threshold

    # ------------------------------------------------------------------
    # after_node — only acts on the reflector
    # ------------------------------------------------------------------
    def after_node(self, state: dict, node_name: str, output: dict) -> dict:
        if node_name != "reflector":
            return output

        iteration = state.get("iteration", 1)
        previous = state.get("previous_round_output", "")

        # Build a text snapshot of the current output for comparison.
        current_text = self._output_text(output)

        # --- hard limit ---
        if iteration >= self.max_iterations:
            logger.info(
                "LoopDetection: hard limit reached (%d/%d)",
                iteration,
                self.max_iterations,
            )
            return self._terminate(output, reason=f"max iterations reached ({iteration}/{self.max_iterations})")

        # --- similarity check ---
        if previous and current_text:
            ratio = SequenceMatcher(None, previous, current_text).ratio()
            if ratio >= self.similarity_threshold:
                logger.info(
                    "LoopDetection: output similarity %.2f >= %.2f, terminating",
                    ratio,
                    self.similarity_threshold,
                )
                return self._terminate(
                    output,
                    reason=f"output similarity {ratio:.2f} >= {self.similarity_threshold}",
                )

        return output

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _output_text(output: dict) -> str:
        """Extract a comparable text representation from the node output."""
        messages = output.get("messages", [])
        if messages:
            last = messages[-1]
            content = getattr(last, "content", None) or str(last)
            return content
        return str(output)

    @staticmethod
    def _terminate(output: dict, *, reason: str) -> dict:
        output["_loop_terminated"] = True
        output["_loop_reason"] = reason
        # Prevent routing back into the subagent branch.
        if output.get("route") == "subagent":
            output["route"] = None
        return output
