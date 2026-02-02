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


def compress_tool_result(content: str, max_length: int = 300) -> str:
    """
    Compress a tool result to reduce token usage.
    
    Long tool results (>max_length chars) are truncated to their first line
    plus a summary indicator. This reduces context bloat from old tool calls.
    
    Args:
        content: Original tool result content
        max_length: Maximum length before compression (default: 300 chars)
        
    Returns:
        Compressed content if over limit, original otherwise
    """
    if len(content) <= max_length:
        return content
    
    # Extract first meaningful line (skip empty lines)
    lines = content.strip().split("\n")
    first_line = ""
    for line in lines:
        line = line.strip()
        if line and not line.startswith("[") and not line.startswith("{"):
            first_line = line[:150]  # Limit first line too
            break
    
    if not first_line:
        first_line = content[:100]
    
    return f"[RESULTADO RESUMIDO]: {first_line}..."


def format_messages_for_llm(
    messages: list[dict[str, Any]],
    compress_old_tools: bool = True,
    recent_threshold: int = 6,
) -> list[dict[str, str]]:
    """
    Format messages for LLM input with security wrapping and tool compression.

    User messages are wrapped in <USER_MESSAGE> tags to help the LLM
    distinguish between trusted system instructions and untrusted user input.
    This is a defense against prompt injection attacks.
    
    Tool results older than `recent_threshold` messages are compressed
    to reduce token usage (saves ~500-1500 tokens per conversation).

    Args:
        messages: Raw message list with timestamps
        compress_old_tools: Whether to compress old tool results (default: True)
        recent_threshold: Keep last N messages uncompressed (default: 6)

    Returns:
        Cleaned message list with only role and content
    """
    formatted = []
    total = len(messages)
    
    for i, msg in enumerate(messages):
        if not msg.get("content"):
            continue
        
        role = msg["role"]
        content = msg["content"]
        
        # Check if this is an "old" message (not in recent threshold)
        is_old = (total - i) > recent_threshold
        
        if role == "user":
            # Wrap user messages in security tags to prevent prompt injection
            wrapped_content = f"<USER_MESSAGE>\n{content}\n</USER_MESSAGE>"
            formatted.append({"role": role, "content": wrapped_content})
        elif role == "tool" and compress_old_tools and is_old:
            # Compress old tool results to save tokens
            compressed = compress_tool_result(content)
            formatted.append({"role": role, "content": compressed})
            if compressed != content:
                logger.debug(
                    f"Compressed old tool result: {len(content)} -> {len(compressed)} chars"
                )
        else:
            formatted.append({"role": role, "content": content})

    return formatted
