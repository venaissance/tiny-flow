# backend/core/graph/builder.py
"""Build the LangGraph StateGraph — assembles all nodes with conditional routing."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from core.graph.state import GraphState
from core.memory.engine import MemoryEngine
from core.models.factory import create_chat_model, _load_config

logger = logging.getLogger(__name__)


def build_graph(
    model_name: str | None = None,
    memory_engine: MemoryEngine | None = None,
) -> Any:
    """Build and compile the agent graph.

    Returns a compiled LangGraph that can be invoked or streamed.
    """
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

    # Import nodes
    from core.graph.nodes.router import router_node
    from core.graph.nodes.respond import respond_node
    from core.graph.nodes.dispatch import dispatch_node
    from core.graph.nodes.skill_node import skill_node
    from core.graph.nodes.execute import execute_node
    from core.graph.nodes.reflector import reflector_node

    # Define node wrappers (bind model + config)
    def _router(state: GraphState) -> dict:
        # Inject memory before routing
        state_with_mem = {**state, "memory_context": memory_engine.inject()}
        return router_node(state_with_mem, model)

    def _respond(state: GraphState) -> dict:
        return respond_node(state, model)

    def _dispatch(state: GraphState) -> dict:
        return dispatch_node(state)

    def _skill(state: GraphState) -> dict:
        return skill_node(state, model)

    def _execute(state: GraphState) -> dict:
        return execute_node(state, model)

    def _reflector(state: GraphState) -> dict:
        return reflector_node(state, model, max_iterations)

    # Build graph
    graph = StateGraph(GraphState)

    graph.add_node("router", _router)
    graph.add_node("respond", _respond)
    graph.add_node("dispatch", _dispatch)
    graph.add_node("skill_node", _skill)
    graph.add_node("execute", _execute)
    graph.add_node("reflector", _reflector)

    # Entry
    graph.set_entry_point("router")

    # Router -> conditional edges
    def route_decision(state: GraphState) -> str:
        route = state.get("route", "direct")
        if route == "subagent":
            return "dispatch"
        elif route == "skill":
            return "skill_node"
        return "respond"

    graph.add_conditional_edges("router", route_decision, {
        "respond": "respond",
        "dispatch": "dispatch",
        "skill_node": "skill_node",
    })

    # Respond -> END
    graph.add_edge("respond", END)

    # Dispatch / Skill -> Execute
    graph.add_edge("dispatch", "execute")
    graph.add_edge("skill_node", "execute")

    # Execute -> Reflector
    graph.add_edge("execute", "reflector")

    # Reflector -> conditional: END or loop back
    def reflector_decision(state: GraphState) -> str:
        # If reflector set route to "subagent", it wants more work -> loop back
        if state.get("route") == "subagent":
            return "router"
        # Otherwise reflector is satisfied (added a final message) -> end
        return "end"

    graph.add_conditional_edges("reflector", reflector_decision, {
        "end": END,
        "router": "router",
    })

    # Compile with in-memory checkpointer (supports both sync and async)
    checkpointer = InMemorySaver()

    return graph.compile(checkpointer=checkpointer)
