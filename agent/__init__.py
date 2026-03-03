"""
MSI Automotive - Agent module (current architecture).

Mode-based conversational AI agent for vehicle homologation services.

This module contains the LangGraph-based AI agent with:
- Intent routing (9 intents)
- 4 conversation modes (CONSULTA, PRESUPUESTO, EXPEDIENTE, ESCALATION)
- Digression handling
- Per-mode fallback policies
"""

from agent.graph.conversation_graph import create_compiled_graph
from agent.state.conversation_state import ConversationState

__all__ = [
    "create_compiled_graph",
    "ConversationState",
]
