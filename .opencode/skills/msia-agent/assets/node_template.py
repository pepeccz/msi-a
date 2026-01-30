"""
Template for MSI-a LangGraph node.

Usage:
1. Copy this file to agent/nodes/
2. Rename to your_node_name.py
3. Update the function name and docstring
4. Implement the node logic
5. Add to conversation_flow.py graph
"""

import logging
from typing import Any

from agent.state.schemas import ConversationState

logger = logging.getLogger(__name__)


async def my_node_name(state: ConversationState) -> dict[str, Any]:
    """
    Description of what this node does.

    This node is responsible for:
    - First responsibility
    - Second responsibility

    Args:
        state: Current conversation state containing:
            - messages: Conversation history
            - user_message: Current user message
            - conversation_id: Thread ID for logging

    Returns:
        State updates to merge:
            - last_node: Node name for debugging
            - Any other state fields to update

    Raises:
        ValueError: If required state fields are missing
    """
    # Get conversation_id for logging
    conversation_id = state.get("conversation_id", "unknown")
    
    logger.info(
        "Processing in my_node_name",
        extra={"conversation_id": conversation_id},
    )

    # Access state with safe defaults
    messages = state.get("messages", [])
    user_message = state.get("user_message", "")
    context = state.get("context", {})

    # Your processing logic here
    # Example:
    result = await process_something(user_message)

    # Return state updates (will be merged with current state)
    return {
        "last_node": "my_node_name",
        "context": {
            **context,
            "processed_by_my_node": True,
            "result": result,
        },
    }


async def process_something(message: str) -> str:
    """Helper function for node logic."""
    # Implement your logic
    return f"Processed: {message}"
