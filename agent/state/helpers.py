"""
MSI Automotive - State helper functions.

Provides utility functions for managing conversation state.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime, UTC
from typing import Any

from agent.state.conversation_state import PendingVariantGroup

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


def get_tool_state(config: Any | None = None) -> dict[str, Any]:
    """
    Get conversation state for tool execution.

    Migration bridge (AD-2): Reads ``config.configurable["state"]`` first
    (ToolNode path), and falls back to the ContextVar ``_current_state``
    (legacy generic_llm_loop path) during the transition period.

    Priority:
    1. ``config["configurable"]["state"]`` — set by ToolNode caller via
       ``RunnableConfig``; always fresh (no staleness bug).
    2. ``_current_state.get()`` — legacy ContextVar set by
       ``set_current_state()`` before tool execution; may be stale.
    3. ``{}`` — neither source available; return empty dict (never None).

    Args:
        config: Optional RunnableConfig dict from LangGraph (or similar).
                May be None when called from the legacy loop path.

    Returns:
        State dict. Always a dict (never None).
    """
    if config is not None:
        configurable = config.get("configurable") if isinstance(config, dict) else None
        if isinstance(configurable, dict) and "state" in configurable:
            return configurable["state"]

    # ContextVar fallback (legacy path — remains until Phase 4)
    cv_state = _current_state.get()
    if cv_state is not None:
        return cv_state

    return {}


def clear_current_state() -> None:
    """
    Clear the current state after tool execution.

    Call this after tools finish to clean up context.
    """
    _current_state.set(None)


def create_full_state_for_tools(
    state: dict[str, Any],
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a full state dict for passing to tools via ContextVar.

    CRITICAL: This preserves the nested structure of mode_context.
    Tools access data via state.get("mode_context", {}).get("key").

    WARNING: Do NOT use {**state, **mode_context} - this flattens mode_context
    to the root level, breaking tools that expect nested structure.

    Args:
        state: Current conversation state
        mode_context: Current mode context dict

    Returns:
        Full state dict with mode_context properly nested

    Example:
        >>> full_state = create_full_state_for_tools(state, mode_context)
        >>> set_current_state(full_state)  # Single call sufficient after T2.5
    """
    full_state = dict(state)
    full_state["mode_context"] = mode_context
    return full_state


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
    max_messages: int = 20,
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

    Windowing: Only the last ``max_messages`` messages are sent to the LLM.
    The full history remains in the checkpoint for debugging.

    Args:
        messages: Raw message list with timestamps
        max_messages: Maximum messages to include (default: 20)
        compress_old_tools: Whether to compress old tool results (default: True)
        recent_threshold: Keep last N messages uncompressed (default: 6)

    Returns:
        Cleaned message list with only role and content
    """
    # Apply windowing — keep only most recent messages
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

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


# ---------------------------------------------------------------------------
# Pending Variant Normalization
# ---------------------------------------------------------------------------


def normalize_pending_variants(
    raw_variants: list[dict[str, Any]],
) -> list[PendingVariantGroup]:
    """
    Up-convert legacy pending variant entries to the enriched PendingVariantGroup shape.

    Legacy entries (from ``identificar_y_resolver_elementos``) contain only:
      - codigo_base (str)
      - pregunta (str)
      - opciones (list[str])

    This function adds the multi-element quantity/resolution fields with sensible
    defaults so that downstream code can always rely on the full shape.

    Idempotent: if an entry already has the new fields, it is returned as-is.

    Args:
        raw_variants: List of pending variant dicts (legacy or enriched).

    Returns:
        List of PendingVariantGroup dicts with all fields populated.
    """
    if not raw_variants:
        return []

    normalized: list[PendingVariantGroup] = []

    for idx, entry in enumerate(raw_variants):
        # Already normalized — detect by presence of ``pending_id``
        if entry.get("pending_id") is not None:
            # Ensure derived field is consistent
            entry_copy = dict(entry)
            resuelta = entry_copy.get("cantidad_resuelta", 0)
            total = entry_copy.get("cantidad_total", 1)
            entry_copy["cantidad_pendiente"] = total - resuelta

            # Derive status from quantities
            if resuelta == 0:
                entry_copy["status"] = "pending"
            elif resuelta >= total:
                entry_copy["status"] = "resolved"
            else:
                entry_copy["status"] = "partial"

            normalized.append(entry_copy)  # type: ignore[arg-type]
            continue

        # Legacy entry — up-convert
        codigo_base = entry.get("codigo_base", f"UNKNOWN_{idx}")
        normalized.append(
            PendingVariantGroup(
                pending_id=f"{codigo_base}_{idx}",
                codigo_base=codigo_base,
                pregunta=entry.get("pregunta", ""),
                opciones=entry.get("opciones", []),
                cantidad_total=1,
                cantidad_resuelta=0,
                cantidad_pendiente=1,
                resoluciones=[],
                status="pending",
            )
        )

    return normalized
