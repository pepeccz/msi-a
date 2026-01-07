"""
MSI Automotive - State helper functions.

Provides utility functions for managing conversation state.
"""

import logging
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger(__name__)


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
    Format messages for LLM input.

    Args:
        messages: Raw message list with timestamps

    Returns:
        Cleaned message list with only role and content
    """
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
        if msg.get("content")
    ]
