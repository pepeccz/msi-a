"""
MSI Automotive - LangGraph conversation flow.

Defines the StateGraph for conversation orchestration.
This is a simplified version that can be extended with FSM and tools later.
"""

import logging
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from agent.state.schemas import ConversationState

logger = logging.getLogger(__name__)

# Load system prompt from file
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system.md"


def load_system_prompt() -> str:
    """Load the system prompt from file."""
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"System prompt not found at {SYSTEM_PROMPT_PATH}, using default")
        return """Eres MSI-a, el asistente virtual de MSI Automotive.
Tu trabajo es ayudar a los clientes con consultas sobre homologaciones de vehículos en España.
Responde de forma profesional pero cercana, en español.
Si no sabes algo, indica que pasarás la consulta a un humano."""


SYSTEM_PROMPT = load_system_prompt()


def create_conversation_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> StateGraph:
    """
    Create the conversation StateGraph.

    This graph has a simple flow:
    1. process_incoming_message - Add user message to history
    2. conversational_agent - Generate AI response
    3. END

    Args:
        checkpointer: Optional Redis checkpointer for state persistence

    Returns:
        Compiled StateGraph ready for invocation
    """
    from agent.nodes.conversational_agent import conversational_agent_node
    from agent.nodes.process_message import process_incoming_message_node

    # Create StateGraph with ConversationState schema
    graph = StateGraph(ConversationState)

    # Add nodes
    graph.add_node("process_incoming_message", process_incoming_message_node)
    graph.add_node("conversational_agent", conversational_agent_node)

    # Define edges (simple linear flow)
    graph.set_entry_point("process_incoming_message")
    graph.add_edge("process_incoming_message", "conversational_agent")
    graph.add_edge("conversational_agent", END)

    # Compile with checkpointer
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Conversation graph created successfully")

    return compiled
