"""
MSI Automotive - Agent module.

This module contains the LangGraph-based AI agent for conversation orchestration.
"""

from agent.graphs.conversation_flow import create_conversation_graph
from agent.nodes import conversational_agent_node, process_incoming_message_node
from agent.state.schemas import ConversationState

__all__ = [
    "create_conversation_graph",
    # "SYSTEM_PROMPT" removed - legacy export, now using dynamic prompts via agent.prompts.loader
    "conversational_agent_node",
    "process_incoming_message_node",
    "ConversationState",
]
