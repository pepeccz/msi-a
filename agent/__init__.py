"""
MSI Automotive - Agent module.

This module contains the LangGraph-based AI agent for conversation orchestration.
"""

from agent.graphs.conversation_flow import create_conversation_graph, SYSTEM_PROMPT
from agent.nodes import conversational_agent_node, process_incoming_message_node
from agent.state.schemas import ConversationState

__all__ = [
    "create_conversation_graph",
    "SYSTEM_PROMPT",
    "conversational_agent_node",
    "process_incoming_message_node",
    "ConversationState",
]
