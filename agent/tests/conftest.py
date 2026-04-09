"""
Conftest for agent unit tests.

Patches heavy agent submodules (graph, state.checkpointer) that require
external services (Redis, Postgres) before any test collection occurs.
This allows unit tests for pure-utility modules (validators, helpers, etc.)
to run without a live infrastructure.
"""

import sys
import types


def _stub_module(name: str) -> types.ModuleType:
    """Create and register a stub module in sys.modules."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub out submodules that pull in infrastructure dependencies.
# We do this BEFORE any agent submodule is imported so that the package
# __init__.py can resolve its imports without failing.
_heavy = [
    "langgraph.checkpoint.redis",
    "langgraph.checkpoint.redis.aio",
    "agent.state.checkpointer",
    "agent.graph",
    "agent.graph.conversation_graph",
    "agent.state",
    "agent.state.conversation_state",
]
for _name in _heavy:
    if _name not in sys.modules:
        _stub_module(_name)

# Provide the two names that agent/__init__.py tries to import
_graph_stub = sys.modules["agent.graph.conversation_graph"]
_graph_stub.create_compiled_graph = None  # type: ignore[attr-defined]

_state_stub = sys.modules["agent.state.conversation_state"]
_state_stub.ConversationState = None  # type: ignore[attr-defined]
