# backend/core/graph/builder.py
"""Build the LangGraph StateGraph — 4-way routing with middleware."""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from core.graph.state import GraphState
from core.memory.engine import MemoryEngine, get_memory_engine
from core.middleware.base import MiddlewareChain
from core.middleware.todo import TodoMiddleware
from core.middleware.loop_detection import LoopDetectionMiddleware
from core.middleware.context_compaction import (
    ContextCompactionMiddleware,
    create_llm_summarizer,
)
from core.models.factory import create_chat_model, _load_config

logger = logging.getLogger(__name__)

# Shared checkpointer — must survive across requests so messages accumulate
# per thread_id. Without this, each build_graph() creates a fresh InMemorySaver
# and compaction never triggers (each request sees only 1 message).
_shared_checkpointer = None


def _get_shared_checkpointer():
    global _shared_checkpointer
    if _shared_checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver
        _shared_checkpointer = InMemorySaver()
    return _shared_checkpointer


def _build_compaction_middleware() -> ContextCompactionMiddleware:
    """Build sync compaction middleware as a SAFETY NET only.

    The primary compaction path is now async (`core.compaction.async_runner`)
    which runs after each turn in the background. This middleware triggers
    only at `safety_max_messages` (far higher than the async trigger) in
    case the background task lags or fails — preventing state bloat.
    """
    config = _load_config()
    cfg = config.get("compaction", {})
    strategy = cfg.get("strategy", "truncate")
    # Use safety threshold, falling back to legacy max_messages * 4 or 40.
    safety = cfg.get("safety_max_messages", max(cfg.get("max_messages", 10) * 4, 40))

    if strategy == "smart":
        summarizer = create_llm_summarizer(
            model_name=cfg.get("summary_model", "glm-4-flash"),
            max_chars=cfg.get("summary_max_chars", 800),
        )
        return ContextCompactionMiddleware(
            max_messages=safety,
            strategy="smart",
            retention_window=cfg.get("retention_window", 10),
            summarizer=summarizer,
        )

    return ContextCompactionMiddleware(max_messages=safety)


def _build_middleware_stacks() -> dict[str, list]:
    """Build per-mode middleware stacks. Called once at graph construction."""
    compaction = _build_compaction_middleware()
    return {
        "flash": [compaction],
        "thinking": [compaction],
        "pro": [TodoMiddleware(), compaction, LoopDetectionMiddleware()],
        "ultra": [TodoMiddleware(), compaction, LoopDetectionMiddleware()],
    }


# Lazy-init: built on first access during graph construction
_MIDDLEWARE_STACKS: dict[str, list] | None = None


def _get_middleware_chain(state: dict) -> MiddlewareChain:
    """Get the appropriate middleware chain for the current execution mode."""
    global _MIDDLEWARE_STACKS
    if _MIDDLEWARE_STACKS is None:
        _MIDDLEWARE_STACKS = _build_middleware_stacks()
    mode = state.get("execution_mode", "flash")
    middlewares = _MIDDLEWARE_STACKS.get(mode, [])
    return MiddlewareChain(middlewares)


def build_graph(
    model_name: str | None = None,
    memory_engine: MemoryEngine | None = None,
) -> Any:
    """Build and compile the agent graph with 4-way routing."""
    config = _load_config()
    roles = (config.get("model") or {}).get("roles") or {}

    # Per-role model: explicit override > caller > config default.
    # Cached per-name so we instantiate each distinct model only once.
    _model_cache: dict[str, Any] = {}

    def _model_for(role: str) -> Any:
        name = model_name or roles.get(role)
        key = name or "__default__"
        if key not in _model_cache:
            _model_cache[key] = create_chat_model(name=name)
        return _model_cache[key]

    max_iterations = config.get("graph", {}).get("max_iterations", 3)

    if memory_engine is None:
        # Shared singleton — persists to data/memory.json and is global across
        # threads so a fact extracted in one thread informs every other.
        memory_engine = get_memory_engine()

    # Import all nodes
    from core.graph.nodes.router import router_node
    from core.graph.nodes.respond import respond_node
    from core.graph.nodes.think_respond import think_respond_node
    from core.graph.nodes.plan import plan_node
    from core.graph.nodes.dispatch import dispatch_node
    from core.graph.nodes.skill_node import skill_node
    from core.graph.nodes.execute import execute_node
    from core.graph.nodes.reflector import reflector_node
    from core.graph.nodes.merge import merge_node

    # ── Node wrappers (bind model + middleware) ──

    def _router(state: GraphState) -> dict:
        mem = memory_engine.inject()
        state_with_mem = {**state, "memory_context": mem}
        output = router_node(state_with_mem, _model_for("router"))
        # Propagate memory_context into the checkpointed state so downstream
        # nodes (respond/think_respond) can read it; the router scope's
        # state_with_mem is a local copy, not a persisted update.
        return {**output, "memory_context": mem}

    def _respond(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        m = _model_for("respond")
        return chain.run_node("respond", state, lambda s: respond_node(s, m))

    def _think_respond(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        m = _model_for("think_respond")
        return chain.run_node("think_respond", state, lambda s: think_respond_node(s, m))

    def _plan(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        m = _model_for("plan")
        return chain.run_node("plan", state, lambda s: plan_node(s, m))

    def _dispatch(state: GraphState) -> dict:
        return dispatch_node(state)

    def _skill(state: GraphState) -> dict:
        return skill_node(state, _model_for("skill_node"))

    def _execute(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        m = _model_for("execute")
        return chain.run_node("execute", state, lambda s: execute_node(s, m))

    def _reflector(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        m = _model_for("reflector")
        return chain.run_node("reflector", state, lambda s: reflector_node(s, m, max_iterations))

    def _merge(state: GraphState) -> dict:
        return merge_node(state, _model_for("merge"))

    # ── Build graph ──

    graph = StateGraph(GraphState)

    graph.add_node("router", _router)
    graph.add_node("respond", _respond)
    graph.add_node("think_respond", _think_respond)
    graph.add_node("plan", _plan)
    graph.add_node("dispatch", _dispatch)
    graph.add_node("skill_node", _skill)
    graph.add_node("execute", _execute)
    graph.add_node("reflector", _reflector)
    graph.add_node("merge", _merge)

    graph.set_entry_point("router")

    # ── Router → 4-way conditional edges ──

    def route_decision(state: GraphState) -> str:
        mode = state.get("execution_mode", "flash")
        if mode == "thinking":
            return "think_respond"
        elif mode in ("pro", "ultra"):
            return "plan"
        return "respond"  # flash

    graph.add_conditional_edges("router", route_decision, {
        "respond": "respond",
        "think_respond": "think_respond",
        "plan": "plan",
    })

    # Flash / Thinking → END
    graph.add_edge("respond", END)
    graph.add_edge("think_respond", END)

    # Plan → conditional: skill match or dispatch
    def plan_next(state: GraphState) -> str:
        mode = state.get("execution_mode", "pro")
        if mode == "ultra":
            return "dispatch"
        return "skill_node"

    graph.add_conditional_edges("plan", plan_next, {
        "skill_node": "skill_node",
        "dispatch": "dispatch",
    })

    # Skill / Dispatch → Execute
    graph.add_edge("skill_node", "execute")
    graph.add_edge("dispatch", "execute")

    # Execute → Reflector (pro) or Merge (ultra)
    def execute_next(state: GraphState) -> str:
        if state.get("execution_mode") == "ultra":
            return "merge"
        return "reflector"

    graph.add_conditional_edges("execute", execute_next, {
        "reflector": "reflector",
        "merge": "merge",
    })

    # Merge → Reflector
    graph.add_edge("merge", "reflector")

    # Reflector → END or loop to execute (pending tasks)
    def reflector_decision(state: GraphState) -> str:
        route = state.get("route")
        if route == "continue_execute":
            return "execute"  # More pending tasks → loop back
        return "end"  # "done" or anything else → terminate

    graph.add_conditional_edges("reflector", reflector_decision, {
        "end": END,
        "execute": "execute",
    })

    return graph.compile(checkpointer=_get_shared_checkpointer())
