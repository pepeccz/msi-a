"""
Integration tests for ConversationActionService (T08).

TDD cycle: RED → GREEN → REFACTOR

Covers:
  T08.1 - pause_bot creates snapshot + sets bot_paused_at + state_snapshot_version=1
  T08.2 - pause_bot idempotent (second call updates reason, no new snapshot)
  T08.3 - resume_bot without pause → BotNotPausedError
  T08.4 - resume_bot restores state + injects messages + clears flags
  T08.5 - send_human_message inside 24h window → sends + creates ConversationMessage
  T08.6 - send_human_message outside 24h → OutsideWindow24hError
  T08.7 - send_human_message auto_pause_if_bot_on with bot ON → pauses first
  T08.8 - send_template_message sends template + creates ConversationMessage
  T08.9 - send_human_message Chatwoot failure → DB committed + delivery_failed flag
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from typing import Annotated, Any, TypedDict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agent.state.mutation_config import STATE_MUTATION_AS_NODE


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_conv(
    *,
    bot_paused_at: datetime | None = None,
    state_snapshot: dict | None = None,
    state_snapshot_version: int | None = None,
    bot_pause_reason: str | None = None,
    bot_paused_by_user_id=None,
    last_inbound_at: datetime | None = None,
) -> MagicMock:
    """Build a mock ConversationHistory ORM object."""
    conv = MagicMock()
    conv.id = uuid4()
    conv.conversation_id = "12345"
    conv.bot_paused_at = bot_paused_at
    conv.bot_resumed_at = None
    conv.state_snapshot = state_snapshot
    conv.state_snapshot_version = state_snapshot_version
    conv.bot_pause_reason = bot_pause_reason
    conv.bot_paused_by_user_id = bot_paused_by_user_id
    conv.last_inbound_at = last_inbound_at
    return conv


def _make_session(conv: MagicMock) -> AsyncMock:
    """Return an AsyncSession mock that yields *conv* on scalar_one_or_none()."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = conv
    # Support multiple execute calls (for messages query, etc.)
    execute_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


def _make_chatwoot() -> AsyncMock:
    chatwoot = AsyncMock()
    chatwoot.send_message = AsyncMock(return_value=True)
    chatwoot.send_template_message = AsyncMock(return_value=True)
    return chatwoot


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_graph() -> AsyncMock:
    graph = AsyncMock()
    snap = MagicMock()
    snap.values = {
        "current_mode": "PRE_EXPEDIENTE_MODE",
        "previous_mode": "START",
        "mode_history": ["START", "PRE_EXPEDIENTE_MODE"],
        "mode_context": {},
        "draft_contexts": {},
        "shared_context": {},
        "user_phone": "+34666000001",
        "user_name": "Test User",
        "user_id": str(uuid4()),
        "client_type": "particular",
        "is_first_interaction": False,
        "escalation_triggered": False,
        "pending_human_decision": False,
        "messages": [],
        "total_message_count": 3,
    }
    snap.config = {"configurable": {"thread_id": "12345"}}
    graph.aget_state = AsyncMock(return_value=snap)
    graph.aupdate_state = AsyncMock()
    return graph


class _MiniState(TypedDict, total=False):
    """Minimal schema — NOT the real conversation graph (which compiles the
    expediente subgraph + every mode node); the as_node inference bug depends
    only on checkpoint/versions_seen/node names, never on node bodies."""

    messages: Annotated[list, add_messages]
    current_mode: str
    mode_context: dict


def _make_real_graph() -> Any:
    """Compile a minimal StateGraph + MemorySaver (NOT AsyncMock). Entry node
    name == STATE_MUTATION_AS_NODE, same as the real "preprocess" node."""
    graph = StateGraph(_MiniState)
    graph.add_node(STATE_MUTATION_AS_NODE, lambda state: {})
    graph.add_node("router", lambda state: {})
    graph.add_edge(START, STATE_MUTATION_AS_NODE)
    graph.add_edge(STATE_MUTATION_AS_NODE, "router")
    graph.add_edge("router", END)
    return graph.compile(checkpointer=MemorySaver())


def _make_snapshot_v1(conv_id: str = "12345") -> dict:
    return {
        "version": 1,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "thread_id": conv_id,
        "state": {
            "current_mode": "PRE_EXPEDIENTE_MODE",
            "previous_mode": "START",
            "mode_history": ["START", "PRE_EXPEDIENTE_MODE"],
            "mode_context": {},
            "draft_contexts": {},
            "shared_context": {},
            "user_phone": "+34666000001",
            "user_name": "Test User",
            "user_id": str(uuid4()),
            "client_type": "particular",
            "is_first_interaction": False,
            "escalation_triggered": False,
            "pending_human_decision": False,
            "messages": [],
            "total_message_count": 3,
        },
    }


# ---------------------------------------------------------------------------
# T08.1 — pause_bot creates snapshot + sets bot_paused_at + version=1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_bot_sets_fields_and_snapshot(
) -> None:
    """pause_bot sets bot_paused_at, bot_paused_by_user_id, state_snapshot, version=1."""
    conv = _make_conv()
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    user_id = uuid4()
    conv_history_id = conv.id

    with (
        patch("api.services.conversation_action_service.snapshot_state") as mock_snapshot,
    ):
        mock_snapshot.return_value = _make_snapshot_v1()

        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )
        result = await service.pause_bot(
            conversation_history_id=conv_history_id,
            paused_by_user_id=user_id,
            reason="Toma de control manual",
        )

    assert result is conv
    assert conv.bot_paused_at is not None
    assert conv.bot_paused_by_user_id == user_id
    assert conv.state_snapshot is not None
    assert conv.state_snapshot_version == 1
    assert conv.bot_pause_reason == "Toma de control manual"
    session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# T08.2 — pause_bot idempotent (already paused: update reason, no new snapshot)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_bot_idempotent_when_already_paused() -> None:
    """pause_bot with an already-paused conv updates reason but keeps existing snapshot."""
    existing_paused_at = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    existing_snapshot = _make_snapshot_v1()
    conv = _make_conv(
        bot_paused_at=existing_paused_at,
        state_snapshot=existing_snapshot,
        state_snapshot_version=1,
        bot_pause_reason="razón original",
    )
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    user_id = uuid4()

    with patch("api.services.conversation_action_service.snapshot_state") as mock_snapshot:
        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )
        result = await service.pause_bot(
            conversation_history_id=conv.id,
            paused_by_user_id=user_id,
            reason="razón nueva",
        )

    # Snapshot function must NOT be called again (idempotent)
    mock_snapshot.assert_not_called()
    # bot_paused_at stays the same (not reset)
    assert conv.bot_paused_at == existing_paused_at
    # Reason updated
    assert conv.bot_pause_reason == "razón nueva"
    assert result is conv


# ---------------------------------------------------------------------------
# T08.3 — resume_bot without pause → BotNotPausedError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_bot_not_paused_raises() -> None:
    """resume_bot on a non-paused conversation raises BotNotPausedError."""
    conv = _make_conv(bot_paused_at=None)
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    from api.services.conversation_action_service import (
        ConversationActionService,
        BotNotPausedError,
    )

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    with pytest.raises(BotNotPausedError):
        await service.resume_bot(
            conversation_history_id=conv.id,
            resumed_by_user_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# T08.4 — resume_bot restores state + injects messages + clears flags
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_bot_restores_state_and_clears_flags() -> None:
    """resume_bot calls restore_state + inject_human_messages + clears bot_paused_at."""
    paused_at = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    conv = _make_conv(
        bot_paused_at=paused_at,
        state_snapshot=_make_snapshot_v1(),
        state_snapshot_version=1,
    )
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    with (
        patch("api.services.conversation_action_service.restore_state") as mock_restore,
        patch(
            "api.services.conversation_action_service.inject_human_messages_to_state"
        ) as mock_inject,
    ):
        mock_restore.return_value = None
        mock_inject.return_value = 2  # injected 2 messages

        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )
        result = await service.resume_bot(
            conversation_history_id=conv.id,
            resumed_by_user_id=uuid4(),
        )

    mock_restore.assert_awaited_once()
    mock_inject.assert_awaited_once()

    # bot_paused_at must be cleared
    assert conv.bot_paused_at is None
    assert conv.state_snapshot is None
    assert conv.bot_resumed_at is not None
    session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# Regression (fix-resume-bot-ambiguous-update) — resume_bot() through a real
# MemorySaver-backed graph (no AsyncMock, no patching restore_state /
# inject_human_messages_to_state). Supplements — does not replace — T08.4
# above, which still covers snapshot-serialization/version-guard behavior.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_bot_succeeds_with_real_memorysaver_graph() -> None:
    """resume_bot() completes end to end against a real compiled graph.

    The paused thread has no prior checkpoint, so restore_state's first
    aupdate_state call writes a degenerate versions_seen map; without an
    explicit as_node the next two calls (inject_human_messages_to_state)
    raise InvalidUpdateError today.
    """
    paused_at = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    conv = _make_conv(
        bot_paused_at=paused_at,
        state_snapshot=_make_snapshot_v1(),
        state_snapshot_version=1,
    )
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    real_graph = _make_real_graph()

    # Fake interval message returned by the session query inside
    # inject_human_messages_to_state (the SQL statement is built but this
    # session mock never actually executes it against a database).
    interval_msg = MagicMock()
    interval_msg.id = uuid4()
    interval_msg.author_type = "human_agent"
    interval_msg.author_user_id = uuid4()
    interval_msg.content = "Un agente humano te atendió mientras tanto"
    interval_msg.created_at = datetime(2026, 5, 10, 13, 0, 0, tzinfo=UTC)
    interval_msg.chatwoot_message_id = None

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = conv
    execute_result.scalars.return_value.all.return_value = [interval_msg]
    session.execute = AsyncMock(return_value=execute_result)

    from api.services.conversation_action_service import ConversationActionService

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=real_graph,
    )

    result = await service.resume_bot(
        conversation_history_id=conv.id,
        resumed_by_user_id=uuid4(),
    )

    assert result is conv
    assert conv.bot_paused_at is None
    assert conv.state_snapshot is None
    assert conv.bot_resumed_at is not None
    session.commit.assert_awaited()

    config = {"configurable": {"thread_id": conv.conversation_id}}
    checkpoint = await real_graph.aget_state(config)
    injected = [
        msg
        for msg in checkpoint.values["messages"]
        if getattr(msg, "additional_kwargs", {}).get("author_type") == "human_agent"
    ]
    assert len(injected) == 1
    assert injected[0].content == "Un agente humano te atendió mientras tanto"


# ---------------------------------------------------------------------------
# T08.5 — send_human_message inside 24h → sends + creates ConversationMessage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_human_message_within_window_sends_and_persists() -> None:
    """send_human_message within 24h window sends via Chatwoot and persists DB record."""
    recent = datetime.now(UTC) - timedelta(hours=2)
    conv = _make_conv(
        bot_paused_at=datetime.now(UTC) - timedelta(hours=1),  # already paused
        last_inbound_at=recent,
    )
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()
    author_user_id = uuid4()

    from api.services.conversation_action_service import ConversationActionService

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    result = await service.send_human_message(
        conversation_history_id=conv.id,
        content="Hola, ¿en qué puedo ayudarle?",
        author_user_id=author_user_id,
        auto_pause_if_bot_on=False,  # already paused
    )

    chatwoot.send_message.assert_awaited_once()
    session.add.assert_called()  # ConversationMessage was added
    session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# T08.6 — send_human_message outside 24h → OutsideWindow24hError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_human_message_outside_window_raises() -> None:
    """send_human_message outside 24h window raises OutsideWindow24hError."""
    old = datetime.now(UTC) - timedelta(hours=25)
    conv = _make_conv(last_inbound_at=old)
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    from api.services.conversation_action_service import (
        ConversationActionService,
        OutsideWindow24hError,
    )

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    with pytest.raises(OutsideWindow24hError):
        await service.send_human_message(
            conversation_history_id=conv.id,
            content="Hola",
            author_user_id=uuid4(),
        )

    chatwoot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# T08.6b — send_human_message with last_inbound_at=None → OutsideWindow24hError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_human_message_no_inbound_raises() -> None:
    """send_human_message with no last_inbound_at raises OutsideWindow24hError."""
    conv = _make_conv(last_inbound_at=None)
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()

    from api.services.conversation_action_service import (
        ConversationActionService,
        OutsideWindow24hError,
    )

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    with pytest.raises(OutsideWindow24hError):
        await service.send_human_message(
            conversation_history_id=conv.id,
            content="Hola",
            author_user_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# T08.7 — send_human_message auto_pause_if_bot_on → pauses first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_human_message_auto_pause_when_bot_on() -> None:
    """send_human_message triggers pause_bot when bot is active and auto_pause=True."""
    recent = datetime.now(UTC) - timedelta(hours=1)
    conv = _make_conv(bot_paused_at=None, last_inbound_at=recent)
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()
    author_user_id = uuid4()

    with patch("api.services.conversation_action_service.snapshot_state") as mock_snap:
        mock_snap.return_value = _make_snapshot_v1()

        from api.services.conversation_action_service import ConversationActionService

        service = ConversationActionService(
            session=session,
            chatwoot_client=chatwoot,
            redis_client=redis,
            graph=graph,
        )
        await service.send_human_message(
            conversation_history_id=conv.id,
            content="Hola",
            author_user_id=author_user_id,
            auto_pause_if_bot_on=True,
        )

    # Auto-pause should have set bot_paused_at
    assert conv.bot_paused_at is not None
    # snapshot should have been called as part of pause
    mock_snap.assert_called_once()
    # Chatwoot send_message still called
    chatwoot.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# T08.8 — send_template_message sends + persists ConversationMessage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_template_message_sends_and_persists() -> None:
    """send_template_message calls Chatwoot template API and persists ConversationMessage."""
    conv = _make_conv()  # no 24h window requirement for templates
    session = _make_session(conv)
    chatwoot = _make_chatwoot()
    redis = _make_redis()
    graph = _make_graph()
    author_user_id = uuid4()

    from api.services.conversation_action_service import ConversationActionService

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    result = await service.send_template_message(
        conversation_history_id=conv.id,
        template_name="bienvenida",
        params={"1": "Juan García"},
        language="es",
        author_user_id=author_user_id,
    )

    chatwoot.send_template_message.assert_awaited_once()
    session.add.assert_called()
    session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# T08.9 — send_human_message Chatwoot failure → DB committed + delivery_failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_human_message_chatwoot_failure_commits_db_with_flag() -> None:
    """If Chatwoot fails, the ConversationMessage is still committed with delivery_failed."""
    recent = datetime.now(UTC) - timedelta(hours=1)
    conv = _make_conv(
        bot_paused_at=datetime.now(UTC) - timedelta(minutes=30),  # already paused
        last_inbound_at=recent,
    )
    session = _make_session(conv)
    redis = _make_redis()
    graph = _make_graph()

    # Chatwoot fails
    chatwoot = _make_chatwoot()
    chatwoot.send_message.return_value = False  # delivery failure

    author_user_id = uuid4()
    added_messages: list = []

    def capture_add(obj):
        added_messages.append(obj)

    session.add.side_effect = capture_add

    from api.services.conversation_action_service import ConversationActionService

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    result = await service.send_human_message(
        conversation_history_id=conv.id,
        content="Mensaje con fallo",
        author_user_id=author_user_id,
        auto_pause_if_bot_on=False,
    )

    # DB must have been committed regardless
    session.commit.assert_awaited()
    # At least one ConversationMessage-like object added
    assert len(added_messages) >= 1

    # The message should carry a delivery failure flag (transient Python attribute)
    msg_objects = [o for o in added_messages if hasattr(o, "delivery_failed")]
    assert len(msg_objects) >= 1
    assert msg_objects[0].delivery_failed is True


# ---------------------------------------------------------------------------
# W1 FIX — send_template_message Chatwoot failure → DB committed + delivery_failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_template_message_chatwoot_failure_commits_db_with_flag() -> None:
    """If Chatwoot raises on send_template_message, DB is committed and delivery_failed=True.

    Analogous to test_send_human_message_chatwoot_failure_commits_db_with_flag.
    Design R6: DB commit BEFORE network call; if Chatwoot fails → log + flag.
    """
    conv = _make_conv()
    session = _make_session(conv)
    redis = _make_redis()
    graph = _make_graph()
    author_user_id = uuid4()

    # Chatwoot raises on template send
    chatwoot = _make_chatwoot()
    chatwoot.send_template_message.side_effect = Exception("Chatwoot unavailable")

    added_messages: list = []

    def capture_add(obj):
        added_messages.append(obj)

    session.add.side_effect = capture_add

    from api.services.conversation_action_service import ConversationActionService

    service = ConversationActionService(
        session=session,
        chatwoot_client=chatwoot,
        redis_client=redis,
        graph=graph,
    )
    result = await service.send_template_message(
        conversation_history_id=conv.id,
        template_name="bienvenida",
        params={"1": "Juan García"},
        language="es",
        author_user_id=author_user_id,
    )

    # DB must have been committed regardless of Chatwoot failure
    session.commit.assert_awaited()
    # At least one message object must have been added
    assert len(added_messages) >= 1
    # The returned ConversationMessage must carry delivery_failed=True
    assert result is not None
    msg_objects = [o for o in added_messages if hasattr(o, "delivery_failed")]
    assert len(msg_objects) >= 1
    assert msg_objects[0].delivery_failed is True
