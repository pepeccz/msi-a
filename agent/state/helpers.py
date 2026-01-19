"""
MSI Automotive - State helper functions.

Provides utility functions for managing conversation state.
"""

import logging
from contextvars import ContextVar
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger(__name__)

# ContextVar for passing state to tools during execution
# This allows tools like escalar_a_humano() to access conversation_id
_current_state: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_state", default=None
)


def set_current_state(state: dict[str, Any]) -> None:
    """
    Set the current state for tools to access.

    Call this before executing tools so they can access conversation context.

    Args:
        state: Current conversation state dict
    """
    _current_state.set(state)


def get_current_state() -> dict[str, Any] | None:
    """
    Get the current state from context.

    Tools can use this to access conversation_id, user_id, etc.

    Returns:
        Current state dict or None if not set
    """
    return _current_state.get()


def clear_current_state() -> None:
    """
    Clear the current state after tool execution.

    Call this after tools finish to clean up context.
    """
    _current_state.set(None)


def add_message(
    messages: list[dict[str, Any]],
    role: str,
    content: str,
    max_messages: int = 20,
) -> list[dict[str, Any]]:
    """
    Add a message to the conversation history with FIFO windowing.

    Args:
        messages: Current message history list
        role: Message role ("user", "assistant", or "system")
        content: Message content text
        max_messages: Maximum messages to keep (default: 20)

    Returns:
        Updated message list with new message appended (and old messages pruned)

    Example:
        >>> messages = []
        >>> messages = add_message(messages, "user", "Hello!")
        >>> messages = add_message(messages, "assistant", "Hi there!")
        >>> len(messages)
        2
    """
    # Create new message dict
    new_message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Create new list with message appended
    updated_messages = messages + [new_message]

    # Apply FIFO windowing if over limit
    if len(updated_messages) > max_messages:
        # Keep most recent messages
        updated_messages = updated_messages[-max_messages:]
        logger.debug(f"Message window trimmed to {max_messages} messages")

    return updated_messages


def should_summarize(total_message_count: int, threshold: int = 30) -> bool:
    """
    Check if conversation should be summarized.

    Args:
        total_message_count: Total number of messages in conversation
        threshold: Number of messages before summarization (default: 30)

    Returns:
        True if summarization should occur
    """
    return total_message_count >= threshold and total_message_count % threshold == 0


def format_messages_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Format messages for LLM input with security wrapping.

    User messages are wrapped in <USER_MESSAGE> tags to help the LLM
    distinguish between trusted system instructions and untrusted user input.
    This is a defense against prompt injection attacks.

    Args:
        messages: Raw message list with timestamps

    Returns:
        Cleaned message list with only role and content
    """
    formatted = []
    for msg in messages:
        if not msg.get("content"):
            continue

        if msg["role"] == "user":
            # Wrap user messages in security tags to prevent prompt injection
            wrapped_content = f"<USER_MESSAGE>\n{msg['content']}\n</USER_MESSAGE>"
            formatted.append({"role": msg["role"], "content": wrapped_content})
        else:
            formatted.append({"role": msg["role"], "content": msg["content"]})

    return formatted
