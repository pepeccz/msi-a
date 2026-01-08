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


def should_continue_to_agent(state: ConversationState) -> str:
    """
    Decide whether to continue to conversational agent or end early.

    If agent is disabled (panic button), skip directly to END.
    Otherwise, continue to conversational_agent node.

    Args:
        state: Current conversation state

    Returns:
        Node name to route to: "conversational_agent" or END
    """
    if state.get("agent_disabled"):
        logger.info(
            "Skipping conversational_agent (agent disabled)",
            extra={"conversation_id": state.get("conversation_id")},
        )
        return END
    return "conversational_agent"


def create_conversation_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> StateGraph:
    """
    Create the conversation StateGraph.

    This graph has a conditional flow:
    1. process_incoming_message - Add user message to history (or auto-respond if agent disabled)
    2. [conditional] If agent_disabled: END, else continue to conversational_agent
    3. conversational_agent - Generate AI response
    4. END

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

    # Define edges with conditional routing
    graph.set_entry_point("process_incoming_message")

    # Conditional edge: skip conversational_agent if agent is disabled
    graph.add_conditional_edges(
        "process_incoming_message",
        should_continue_to_agent,
        {
            "conversational_agent": "conversational_agent",
            END: END,
        }
    )

    graph.add_edge("conversational_agent", END)

    # Compile with checkpointer
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Conversation graph created successfully")

    return compiled
