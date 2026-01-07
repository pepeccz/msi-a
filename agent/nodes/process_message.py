"""
MSI Automotive - Process incoming message node.

This node handles incoming user messages and prepares the state
for the conversational agent.
"""

import logging
from datetime import datetime, UTC
from typing import Any

from agent.state.helpers import add_message
from agent.state.schemas import ConversationState

logger = logging.getLogger(__name__)


async def process_incoming_message_node(state: ConversationState) -> dict[str, Any]:
    """
    Process incoming user message and update state.

    This node:
    1. Adds the user message to conversation history
    2. Detects if this is the first interaction
    3. Updates timestamps

    Args:
        state: Current conversation state

    Returns:
        State updates dict
    """
    conversation_id = state.get("conversation_id", "unknown")
    user_message = state.get("user_message", "")
    messages = state.get("messages", [])
    total_count = state.get("total_message_count", 0)

    logger.info(
        f"Processing incoming message | conversation_id={conversation_id}",
        extra={
            "conversation_id": conversation_id,
            "message_length": len(user_message) if user_message else 0,
        },
    )

    # Check if first interaction (no messages yet)
    is_first = len(messages) == 0

    # Add user message to history
    updated_messages = add_message(
        messages=messages,
        role="user",
        content=user_message,
    )

    # Prepare state updates
    updates: dict[str, Any] = {
        "messages": updated_messages,
        "total_message_count": total_count + 1,
        "is_first_interaction": is_first,
        "updated_at": datetime.now(UTC),
        "last_node": "process_incoming_message",
    }

    # Set initial state if first interaction
    if is_first:
        updates["current_state"] = "greeting"
        updates["created_at"] = datetime.now(UTC)
        logger.info(
            f"First interaction detected | conversation_id={conversation_id}",
            extra={"conversation_id": conversation_id},
        )

    return updates
