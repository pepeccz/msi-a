"""
MSI Automotive - State helper functions.

Provides utility functions for managing conversation state.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from langchain_core.runnables import ensure_config

from agent.state.conversation_state import PendingVariantGroup

logger = logging.getLogger(__name__)


def get_tool_state(config: Any | None = None) -> dict[str, Any]:
    """
    Get conversation state for tool execution via RunnableConfig.

    Priority:
    1. ``config["configurable"]["state"]`` — explicit config passed as parameter.
    2. ``ensure_config()["configurable"]["state"]`` — LangChain thread-local
       config propagated during ``ainvoke(tool_args, config=config)``.

    This means tools can receive state in two ways:
    - Via ``config: Annotated[RunnableConfig, InjectedToolArg]`` parameter.
    - Via ``ensure_config()`` if tool does not declare a config parameter.
    Both cases work when ``custom_tool_node`` calls
    ``tool_fn.ainvoke(tool_args, config=config)``.

    Args:
        config: Optional RunnableConfig dict. When None, falls back to
                ``ensure_config()`` to read the thread-local config.

    Returns:
        State dict from configurable["state"].

    Raises:
        RuntimeError: If neither path finds configurable.state.
    """
    # Path 1: explicit config parameter
    if config is not None:
        configurable = config.get("configurable") if isinstance(config, dict) else None
        if isinstance(configurable, dict) and "state" in configurable:
            return configurable["state"]

    # Path 2: LangChain thread-local config (propagated via ainvoke)
    try:
        lc_config = ensure_config()
        configurable = lc_config.get("configurable") if isinstance(lc_config, dict) else None
        if isinstance(configurable, dict) and "state" in configurable:
            return configurable["state"]
    except Exception:
        pass

    raise RuntimeError(
        "get_tool_state() requires RunnableConfig with configurable.state"
    )


def create_full_state_for_tools(
    state: dict[str, Any],
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a full state dict for passing to tools via RunnableConfig.

    CRITICAL: This preserves the nested structure of mode_context.
    Tools access data via state.get("mode_context", {}).get("key").

    WARNING: Do NOT use {**state, **mode_context} - this flattens mode_context
    to the root level, breaking tools that expect nested structure.

    Args:
        state: Current conversation state
        mode_context: Current mode context dict

    Returns:
        Full state dict with mode_context properly nested
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


def _extract_role(msg: Any) -> str:
    """Extract role from a message, handling both dict and BaseMessage.

    BaseMessage uses ``.type`` (``"human"``, ``"ai"``, ``"tool"``), while
    plain dicts use ``msg["role"]`` (``"user"``, ``"assistant"``).
    Normalises BaseMessage names to the OpenAI convention used by the LLM.
    """
    # BaseMessage path — .type is always present on BaseMessage subclasses
    msg_type = getattr(msg, "type", None)
    if msg_type is not None:
        return {"human": "user", "ai": "assistant"}.get(msg_type, msg_type)
    # Dict path (legacy / backward compat)
    if isinstance(msg, dict):
        return msg.get("role", "")
    return ""


def _extract_content(msg: Any) -> str:
    """Extract content from a message, handling both dict and BaseMessage."""
    content = getattr(msg, "content", None)
    if content is not None:
        return str(content)
    if isinstance(msg, dict):
        return msg.get("content", "")
    return ""


def format_messages_for_llm(
    messages: list,
    max_messages: int = 20,
    compress_old_tools: bool = True,
    recent_threshold: int = 6,
    conversation_summary: str | None = None,
) -> list[dict[str, str]]:
    """
    Format messages for LLM input with security wrapping and tool compression.

    Handles both plain dicts (legacy) and BaseMessage objects (after
    ``add_messages`` migration) transparently via duck-typing helpers.

    User messages are wrapped in <USER_MESSAGE> tags to help the LLM
    distinguish between trusted system instructions and untrusted user input.
    This is a defense against prompt injection attacks.

    Tool results older than `recent_threshold` messages are compressed
    to reduce token usage (saves ~500-1500 tokens per conversation).

    Windowing: Only the last ``max_messages`` messages are sent to the LLM.
    The full history remains in the checkpoint for debugging.

    Args:
        messages: Raw message list (dicts or BaseMessage objects)
        max_messages: Maximum messages to include (default: 20)
        compress_old_tools: Whether to compress old tool results (default: True)
        recent_threshold: Keep last N messages uncompressed (default: 6)
        conversation_summary: Optional structured summary to prepend as context

    Returns:
        Cleaned message list with only role and content
    """
    # Apply windowing — keep only most recent messages
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    formatted = []

    # Inject conversation summary as leading context when available
    if conversation_summary:
        formatted.append({
            "role": "system",
            "content": f"[Resumen de conversación anterior]:\n{conversation_summary}",
        })

    total = len(messages)

    for i, msg in enumerate(messages):
        content = _extract_content(msg)
        if not content:
            continue

        role = _extract_role(msg)

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
