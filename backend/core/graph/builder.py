# backend/core/graph/builder.py
"""Build the LangGraph StateGraph — 4-way routing with middleware."""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from core.graph.state import GraphState
from core.memory.engine import MemoryEngine
from core.middleware.base import MiddlewareChain
from core.middleware.todo import TodoMiddleware
from core.middleware.loop_detection import LoopDetectionMiddleware
from core.middleware.context_compaction import ContextCompactionMiddleware
from core.models.factory import create_chat_model, _load_config

logger = logging.getLogger(__name__)

# Middleware stacks per execution mode
MIDDLEWARE_STACKS = {
    "flash": [],
    "thinking": [ContextCompactionMiddleware()],
    "pro": [TodoMiddleware(), ContextCompactionMiddleware(), LoopDetectionMiddleware()],
    "ultra": [TodoMiddleware(), ContextCompactionMiddleware(), LoopDetectionMiddleware()],
}


def _get_middleware_chain(state: dict) -> MiddlewareChain:
    """Get the appropriate middleware chain for the current execution mode."""
    mode = state.get("execution_mode", "flash")
    middlewares = MIDDLEWARE_STACKS.get(mode, [])
    return MiddlewareChain(middlewares)


def build_graph(
    model_name: str | None = None,
    memory_engine: MemoryEngine | None = None,
) -> Any:
    """Build and compile the agent graph with 4-way routing."""
    from langgraph.checkpoint.memory import InMemorySaver

    model = create_chat_model(name=model_name)
    config = _load_config()
    max_iterations = config.get("graph", {}).get("max_iterations", 3)

    if memory_engine is None:
        mem_cfg = config.get("memory", {})
        memory_engine = MemoryEngine(
            token_budget=mem_cfg.get("token_budget", 500),
            min_confidence=mem_cfg.get("min_confidence", 0.7),
            decay_days=mem_cfg.get("decay_days", 30),
            decay_factor=mem_cfg.get("decay_factor", 0.8),
        )

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
        state_with_mem = {**state, "memory_context": memory_engine.inject()}
        return router_node(state_with_mem, model)

    def _respond(state: GraphState) -> dict:
        return respond_node(state, model)

    def _think_respond(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        return chain.run_node("think_respond", state, lambda s: think_respond_node(s, model))

    def _plan(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        return chain.run_node("plan", state, lambda s: plan_node(s, model))

    def _dispatch(state: GraphState) -> dict:
        return dispatch_node(state)

    def _skill(state: GraphState) -> dict:
        return skill_node(state, model)

    def _execute(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        return chain.run_node("execute", state, lambda s: execute_node(s, model))

    def _reflector(state: GraphState) -> dict:
        chain = _get_middleware_chain(state)
        return chain.run_node("reflector", state, lambda s: reflector_node(s, model, max_iterations))

    def _merge(state: GraphState) -> dict:
        return merge_node(state, model)

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

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)
