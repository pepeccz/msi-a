"""
State snapshot service — serialize/restore LangGraph ConversationState to JSONB.

This module is intentionally kept free of ORM imports for testability.
It operates on raw dicts and calls graph.aget_state / graph.aupdate_state
via the compiled LangGraph graph passed by the caller.

Design decisions (Design D1, D2):
- Snapshot schema v1: {version, snapshot_at, thread_id, state{...persistent fields...}}
- Transient fields are excluded from the snapshot to keep it compact and safe.
- Messages are serialized as plain dicts (langchain_core.messages.message_to_dict or
  fallback to str representation for non-standard types).
- restore_state raises UnsupportedSnapshotVersionError for any version != 1.
- inject_human_messages_to_state injects LangChain HumanMessage objects with
  additional_kwargs carrying author attribution.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from agent.state.mutation_config import (
    STATE_MUTATION_AS_NODE,
    build_state_mutation_config,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Transient fields excluded from the snapshot (non-persistent / non-serializable)
# Design D1: "Excluidos (transient, no se serializan)"
# ---------------------------------------------------------------------------
_EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "user_message",
        "ai_response",
        "pending_images",
        "tarifa_actual",
        "incoming_attachments",
        "pending_outbound_messages",
        "retry_state",
        "last_node",
        "updated_at",
        "last_activity_at",
        "image_delivery_outcome",
    }
)

# Persistent fields that form the v1 snapshot (allow-list beats block-list for safety)
_PERSISTENT_FIELDS: frozenset[str] = frozenset(
    {
        "current_mode",
        "previous_mode",
        "mode_history",
        "mode_context",
        "draft_contexts",
        "shared_context",
        "user_phone",
        "user_name",
        "user_id",
        "client_type",
        "is_first_interaction",
        "escalation_triggered",
        "escalation_reason",
        "pending_human_decision",
        "user_profile",
        "draft_quote",
        "conversation_summary",
        "total_message_count",
        "mode_message_count",
        "presupuesto_offered_count",
        "last_nudge_message_count",
        "created_at",
        "messages",
    }
)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class UnsupportedSnapshotVersionError(Exception):
    """Raised when a snapshot payload carries an unknown version."""

    def __init__(self, version: Any) -> None:
        super().__init__(
            f"Unsupported snapshot version: {version!r}. Only version 1 is supported."
        )
        self.version = version


# ---------------------------------------------------------------------------
# Internal sentinel for when graph is not used in tests
# ---------------------------------------------------------------------------

def _get_graph() -> None:
    """Placeholder — the graph is always passed as an argument; never called at runtime."""
    return None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _safe_serialize_value(value: Any) -> Any:
    """Recursively make a value JSON-safe, dropping non-serializable objects."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: _safe_serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_serialize_value(item) for item in value]
    # Try langchain message serialization
    try:
        from langchain_core.load import dumpd
        return dumpd(value)
    except Exception:
        pass
    # Last resort: str representation for debuggability
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # Drop non-serializable fields silently
        return f"<non-serializable:{type(value).__name__}>"


def _serialize_messages(messages: list[Any]) -> list[dict]:
    """Serialize LangChain messages to plain dicts for JSONB storage."""
    result = []
    for msg in messages:
        try:
            from langchain_core.load import dumpd
            result.append(dumpd(msg))
        except Exception:
            # Fallback: best-effort dict
            try:
                result.append(
                    {
                        "type": type(msg).__name__,
                        "content": str(getattr(msg, "content", "")),
                        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                    }
                )
            except Exception:
                pass
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def snapshot_state(
    chatwoot_conversation_id: str,
    graph: Any,
) -> dict[str, Any]:
    """Read the current LangGraph checkpoint and build a v1 snapshot dict.

    The returned dict is JSON-safe and ready to be stored in
    ``ConversationHistory.state_snapshot`` (JSONB).

    Args:
        chatwoot_conversation_id: Chatwoot conversation ID used as LangGraph thread_id.
        graph: Compiled LangGraph graph (CompiledStateGraph).

    Returns:
        Snapshot dict with schema::

            {
                "version": 1,
                "snapshot_at": "<ISO 8601>",
                "thread_id": "<chatwoot_conversation_id>",
                "state": { ...persistent ConversationState fields... }
            }

    Raises:
        Exception: If the graph cannot be read (e.g. Redis connection error).
    """
    config = build_state_mutation_config(
        {"configurable": {"thread_id": chatwoot_conversation_id}}
    )
    checkpoint = await graph.aget_state(config)
    state_values: dict[str, Any] = checkpoint.values if checkpoint else {}

    # Build snapshot state: only persistent fields, safe serialization
    snapshot_state_dict: dict[str, Any] = {}
    for field in _PERSISTENT_FIELDS:
        if field not in state_values:
            continue
        raw_value = state_values[field]
        if field == "messages":
            snapshot_state_dict[field] = _serialize_messages(raw_value or [])
        else:
            snapshot_state_dict[field] = _safe_serialize_value(raw_value)

    # Cap messages at last 30 turns (R8 risk mitigation from design)
    if "messages" in snapshot_state_dict:
        msgs = snapshot_state_dict["messages"]
        if len(msgs) > 60:  # 60 half-turns ≈ 30 full turns
            snapshot_state_dict["messages"] = msgs[-60:]
            _log.warning(
                "snapshot_messages_truncated",
                conversation_id=chatwoot_conversation_id,
                original_count=len(msgs),
                truncated_to=60,
            )

    snapshot: dict[str, Any] = {
        "version": 1,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "thread_id": chatwoot_conversation_id,
        "state": snapshot_state_dict,
    }

    # Validate JSON-serializability before returning
    try:
        json.dumps(snapshot)
    except (TypeError, ValueError) as exc:
        _log.error(
            "snapshot_not_json_serializable",
            conversation_id=chatwoot_conversation_id,
            error=str(exc),
        )
        raise

    _log.info(
        "state_snapshotted",
        conversation_id=chatwoot_conversation_id,
        version=1,
        message_count=len(snapshot_state_dict.get("messages", [])),
    )
    return snapshot


async def restore_state(
    chatwoot_conversation_id: str,
    snapshot: dict[str, Any],
    graph: Any,
) -> None:
    """Restore a v1 snapshot to the LangGraph checkpointer.

    Args:
        chatwoot_conversation_id: Chatwoot conversation ID (thread_id).
        snapshot: The JSONB snapshot dict previously produced by ``snapshot_state``.
        graph: Compiled LangGraph graph.

    Raises:
        UnsupportedSnapshotVersionError: If ``snapshot["version"] != 1``.
    """
    version = snapshot.get("version")
    if version != 1:
        raise UnsupportedSnapshotVersionError(version)

    config = build_state_mutation_config(
        {"configurable": {"thread_id": chatwoot_conversation_id}}
    )
    restored_state = snapshot.get("state", {})

    # Deserialize messages back to LangChain objects
    if "messages" in restored_state:
        restored_state = dict(restored_state)
        restored_state["messages"] = _deserialize_messages(
            restored_state.get("messages", [])
        )

    await graph.aupdate_state(config, restored_state, as_node=STATE_MUTATION_AS_NODE)
    _log.info(
        "state_restored",
        conversation_id=chatwoot_conversation_id,
        version=version,
    )


def _deserialize_messages(raw_messages: list[dict]) -> list[Any]:
    """Attempt to reconstruct LangChain message objects from stored dicts."""
    result = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        try:
            from langchain_core.load import load
            result.append(load(raw))
        except Exception:
            # Fallback: reconstruct from known keys
            try:
                from langchain_core.messages import (
                    AIMessage,
                    HumanMessage,
                    SystemMessage,
                )
                msg_type = raw.get("type", "")
                content = raw.get("content", "")
                additional_kwargs = raw.get("additional_kwargs", {})
                if msg_type in ("HumanMessage", "human"):
                    result.append(HumanMessage(content=content, additional_kwargs=additional_kwargs))
                elif msg_type in ("AIMessage", "ai"):
                    result.append(AIMessage(content=content, additional_kwargs=additional_kwargs))
                elif msg_type in ("SystemMessage", "system"):
                    result.append(SystemMessage(content=content))
            except Exception:
                pass
    return result


async def inject_human_messages_to_state(
    chatwoot_conversation_id: str,
    conversation_history_id: UUID,
    paused_at: datetime,
    session: "AsyncSession",
    graph: Any,
) -> int:
    """Inject messages from the pause interval into the LangGraph state.

    Queries ConversationMessages scoped to the specific conversation
    (``conversation_history_id == conversation_history_id``),
    with ``created_at > paused_at`` and
    ``author_type IN ('human_agent', 'user')``, and injects them as
    ``HumanMessage`` objects via ``graph.aupdate_state``.

    Also appends a SystemMessage resume marker as the final message so the LLM
    has explicit context about the pause interval (Design D2).

    Args:
        chatwoot_conversation_id: Chatwoot conversation ID (thread_id).
        conversation_history_id: PK of ConversationHistory — used to scope the
            query to a single conversation and prevent cross-conversation injection.
        paused_at: The timestamp when the bot was paused.
        session: SQLAlchemy AsyncSession for DB queries.
        graph: Compiled LangGraph graph.

    Returns:
        Number of messages injected (excluding the SystemMessage marker).
    """
    from sqlalchemy import and_, select

    from database.models import ConversationMessage

    # Scope query to this specific conversation to avoid injecting messages
    # from other conversations that may be paused in the same time window (C1).
    stmt = (
        select(ConversationMessage)
        .where(
            and_(
                ConversationMessage.conversation_history_id == conversation_history_id,
                ConversationMessage.created_at > paused_at,
                ConversationMessage.author_type.in_(["human_agent", "user"]),
            )
        )
        .order_by(ConversationMessage.created_at)
    )
    result = await session.execute(stmt)
    interval_messages = result.scalars().all()

    if not interval_messages:
        _log.info(
            "inject_no_messages",
            conversation_id=chatwoot_conversation_id,
            paused_at=paused_at.isoformat(),
        )
        return 0

    from langchain_core.messages import HumanMessage, SystemMessage

    injected: list[Any] = []
    for msg in interval_messages:
        human_msg = HumanMessage(
            content=msg.content or "",
            additional_kwargs={
                "author_type": msg.author_type,
                "author_user_id": str(msg.author_user_id) if msg.author_user_id else None,
                "sent_at": msg.created_at.isoformat() if msg.created_at else None,
                "msia_msg_id": str(msg.id),
                "chatwoot_message_id": str(msg.chatwoot_message_id) if msg.chatwoot_message_id else None,
            },
        )
        injected.append(human_msg)

    config = build_state_mutation_config(
        {"configurable": {"thread_id": chatwoot_conversation_id}}
    )

    # Inject human messages first
    await graph.aupdate_state(
        config, {"messages": injected}, as_node=STATE_MUTATION_AS_NODE
    )

    # Append SystemMessage resume marker (Design D2 step 6)
    now_iso = datetime.now(UTC).isoformat()
    paused_iso = paused_at.isoformat()
    marker = SystemMessage(
        content=(
            f"[Reanudación] El cliente fue atendido por un agente humano "
            f"desde {paused_iso} hasta {now_iso}. "
            f"Se inyectaron {len(injected)} mensaje(s) del intervalo. "
            "Continúa la conversación con el contexto de la pausa."
        )
    )
    await graph.aupdate_state(
        config, {"messages": [marker]}, as_node=STATE_MUTATION_AS_NODE
    )

    _log.info(
        "messages_injected",
        conversation_id=chatwoot_conversation_id,
        count=len(injected),
        paused_at=paused_iso,
    )
    return len(injected)
