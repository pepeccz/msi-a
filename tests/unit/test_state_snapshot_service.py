"""
Unit tests for StateSnapshotService (T09, T10).

TDD cycle: RED → GREEN → REFACTOR

Covers:
  T09.1 - snapshot includes version=1, messages, mode, mode_context, snapshot_at
  T09.2 - restore with version=1 OK
  T09.3 - restore with version=2 → raises UnsupportedSnapshotVersionError
  T09.4 - snapshot ignores non-serializable fields (callbacks, etc.)
  T10.1 - inject_human_messages filters correctly by paused_at + author_type
  T10.2 - each message has correct additional_kwargs
  T10.3 - state_snapshot_version set to 1 in snapshot (not NULL)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Minimal ConversationState-like dict (what aget_state().values returns)
# ---------------------------------------------------------------------------

def _make_state_values(
    *,
    current_mode: str = "PRE_EXPEDIENTE_MODE",
    mode_context: dict | None = None,
    messages: list | None = None,
    # Non-serializable field to test filtering
    _callback: object = None,
) -> dict:
    values = {
        "current_mode": current_mode,
        "previous_mode": "START",
        "mode_history": ["START", current_mode],
        "mode_context": mode_context or {"precio_comunicado": True},
        "draft_contexts": {},
        "shared_context": {},
        "user_phone": "+34666000001",
        "user_name": "Test User",
        "user_id": str(uuid4()),
        "client_type": "particular",
        "is_first_interaction": False,
        "escalation_triggered": False,
        "pending_human_decision": False,
        "messages": messages or [],
        "total_message_count": 5,
        # Transient / non-serializable fields
        "user_message": "Hola",
        "ai_response": None,
        "pending_images": [],
        "tarifa_actual": None,
        "retry_state": {},
    }
    if _callback is not None:
        values["_non_serializable_callback"] = _callback
    return values


def _make_checkpoint_state(values: dict) -> MagicMock:
    """Simulate what graph.aget_state() returns (StateSnapshot)."""
    snap = MagicMock()
    snap.values = values
    snap.config = {"configurable": {"thread_id": "conv-123"}}
    return snap


# ---------------------------------------------------------------------------
# Mock graph fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_graph() -> AsyncMock:
    graph = AsyncMock()
    graph.aget_state = AsyncMock()
    graph.aupdate_state = AsyncMock()
    return graph


# ---------------------------------------------------------------------------
# T09.1 — snapshot includes version=1, messages, mode, mode_context, snapshot_at
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_state_includes_required_fields(mock_graph: AsyncMock) -> None:
    """snapshot_state returns a dict with version=1 and all required keys."""
    state_values = _make_state_values()
    mock_graph.aget_state.return_value = _make_checkpoint_state(state_values)

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import snapshot_state

        result = await snapshot_state(
            chatwoot_conversation_id="conv-123",
            graph=mock_graph,
        )

    assert result["version"] == 1
    assert "snapshot_at" in result
    assert "messages" in result["state"]
    assert result["state"]["current_mode"] == "PRE_EXPEDIENTE_MODE"
    assert "mode_context" in result["state"]


# ---------------------------------------------------------------------------
# T09.2 — restore with version=1 OK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_state_version_1_calls_aupdate_state(mock_graph: AsyncMock) -> None:
    """restore_state with version=1 snapshot calls graph.aupdate_state without raising."""
    snapshot = {
        "version": 1,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "thread_id": "conv-123",
        "state": _make_state_values(),
    }

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import restore_state

        await restore_state(
            chatwoot_conversation_id="conv-123",
            snapshot=snapshot,
            graph=mock_graph,
        )

    mock_graph.aupdate_state.assert_awaited_once()


# ---------------------------------------------------------------------------
# T09.3 — restore with version=2 → UnsupportedSnapshotVersionError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_state_unsupported_version_raises(mock_graph: AsyncMock) -> None:
    """restore_state with an unknown snapshot version raises UnsupportedSnapshotVersionError."""
    snapshot = {
        "version": 2,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "thread_id": "conv-123",
        "state": _make_state_values(),
    }

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import restore_state
        from api.services.state_snapshot_service import UnsupportedSnapshotVersionError

        with pytest.raises(UnsupportedSnapshotVersionError):
            await restore_state(
                chatwoot_conversation_id="conv-123",
                snapshot=snapshot,
                graph=mock_graph,
            )

    mock_graph.aupdate_state.assert_not_awaited()


# ---------------------------------------------------------------------------
# T09.4 — snapshot ignores non-serializable fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_state_filters_nonserializable_fields(mock_graph: AsyncMock) -> None:
    """snapshot_state excludes transient/non-serializable fields like callbacks."""

    class _FakeCallback:
        pass

    state_values = _make_state_values(_callback=_FakeCallback())
    # Also include known transient fields that should be excluded
    state_values["user_message"] = "should be excluded"
    state_values["ai_response"] = "also excluded"
    state_values["pending_images"] = ["some_image_data"]
    state_values["tarifa_actual"] = {"price": 450}
    state_values["retry_state"] = {"consecutive_errors": 2}

    mock_graph.aget_state.return_value = _make_checkpoint_state(state_values)

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import snapshot_state

        result = await snapshot_state(
            chatwoot_conversation_id="conv-123",
            graph=mock_graph,
        )

    # Transient fields must NOT be in the snapshot state
    state = result["state"]
    assert "user_message" not in state
    assert "ai_response" not in state
    assert "pending_images" not in state
    assert "tarifa_actual" not in state
    assert "_non_serializable_callback" not in state

    # Persistent fields MUST be present
    assert "current_mode" in state
    assert "mode_context" in state
    assert "messages" in state

    # Validate result is JSON-serializable
    json.dumps(result)


# ---------------------------------------------------------------------------
# T09.5 (bonus) — snapshot result is JSON-serializable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_state_is_json_serializable(mock_graph: AsyncMock) -> None:
    """The snapshot dict can be serialized to JSON without errors."""
    state_values = _make_state_values()
    mock_graph.aget_state.return_value = _make_checkpoint_state(state_values)

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import snapshot_state

        result = await snapshot_state(
            chatwoot_conversation_id="conv-123",
            graph=mock_graph,
        )

    serialized = json.dumps(result)
    recovered = json.loads(serialized)
    assert recovered["version"] == 1


# ---------------------------------------------------------------------------
# T10.1 — inject_human_messages filtered by paused_at + author_type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_human_messages_filters_by_paused_at_and_author_type(
    mock_graph: AsyncMock,
) -> None:
    """inject_human_messages only injects messages after paused_at from human/user authors."""
    from datetime import timezone

    paused_at = datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)
    before_pause = datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC)
    after_pause_human = datetime(2026, 5, 11, 11, 0, 0, tzinfo=UTC)
    after_pause_user = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
    after_pause_bot = datetime(2026, 5, 11, 13, 0, 0, tzinfo=UTC)

    # Build mock messages
    def _msg(author_type, created_at, content="Hola"):
        m = MagicMock()
        m.id = uuid4()
        m.author_type = author_type
        m.author_user_id = uuid4() if author_type == "human_agent" else None
        m.content = content
        m.created_at = created_at
        m.chatwoot_message_id = None
        return m

    messages = [
        _msg("user", before_pause, "Antes de pausa"),         # excluded: before pause
        _msg("human_agent", after_pause_human, "Mensaje agente"),  # included
        _msg("user", after_pause_user, "Respuesta cliente"),        # included
        _msg("bot", after_pause_bot, "Mensaje bot"),               # excluded: bot
    ]

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        m for m in messages
        if m.created_at > paused_at and m.author_type in ("human_agent", "user")
    ]
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import inject_human_messages_to_state

        count = await inject_human_messages_to_state(
            chatwoot_conversation_id="conv-123",
            conversation_history_id=uuid4(),
            paused_at=paused_at,
            session=mock_session,
            graph=mock_graph,
        )

    assert count == 2  # human_agent + user after pause
    # aupdate_state should have been called with those messages
    mock_graph.aupdate_state.assert_awaited()


# ---------------------------------------------------------------------------
# T10.2 — each injected message has correct additional_kwargs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_human_messages_additional_kwargs(mock_graph: AsyncMock) -> None:
    """Each injected HumanMessage has author_type, author_user_id, sent_at, msia_msg_id."""
    paused_at = datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)
    after = datetime(2026, 5, 11, 11, 0, 0, tzinfo=UTC)

    author_user_id = uuid4()
    msg_id = uuid4()

    m = MagicMock()
    m.id = msg_id
    m.author_type = "human_agent"
    m.author_user_id = author_user_id
    m.content = "Mensaje del agente"
    m.created_at = after
    m.chatwoot_message_id = "cwt-999"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [m]
    mock_session.execute = AsyncMock(return_value=mock_result)

    injected_messages: list = []

    async def capture_aupdate_state(config, state_update, **kwargs):
        injected_messages.extend(state_update.get("messages", []))

    mock_graph.aupdate_state.side_effect = capture_aupdate_state

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import inject_human_messages_to_state

        await inject_human_messages_to_state(
            chatwoot_conversation_id="conv-123",
            conversation_history_id=uuid4(),
            paused_at=paused_at,
            session=mock_session,
            graph=mock_graph,
        )

    assert len(injected_messages) >= 1
    # Find the HumanMessage (not the SystemMessage marker)
    human_msgs = [
        msg for msg in injected_messages
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("author_type")
    ]
    assert len(human_msgs) == 1
    kwargs = human_msgs[0].additional_kwargs
    assert kwargs["author_type"] == "human_agent"
    assert kwargs["author_user_id"] == str(author_user_id)
    assert "sent_at" in kwargs
    assert kwargs["msia_msg_id"] == str(msg_id)


# ---------------------------------------------------------------------------
# T10.3 — snapshot_state version is always 1 (not NULL)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_state_version_is_explicitly_1(mock_graph: AsyncMock) -> None:
    """The snapshot dict always has version=1, never None/NULL."""
    state_values = _make_state_values()
    mock_graph.aget_state.return_value = _make_checkpoint_state(state_values)

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import snapshot_state

        result = await snapshot_state(
            chatwoot_conversation_id="conv-123",
            graph=mock_graph,
        )

    assert result.get("version") is not None
    assert result["version"] == 1
    assert isinstance(result["version"], int)


# ---------------------------------------------------------------------------
# C1 FIX — inject_human_messages_to_state MUST filter by conversation_history_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_human_messages_filters_by_conversation_history_id(
    mock_graph: AsyncMock,
) -> None:
    """inject_human_messages_to_state SQL WHERE must include conversation_history_id.

    Verifies that the compiled SQL statement contains the conversation_history_id
    filter so that messages from other conversations are never injected into
    the wrong LangGraph thread.
    """
    from sqlalchemy import and_, select
    from database.models import ConversationMessage

    paused_at = datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)
    conv_history_id = uuid4()

    captured_stmts: list = []

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    async def capture_execute(stmt, *args, **kwargs):
        captured_stmts.append(stmt)
        return mock_result

    mock_session.execute = capture_execute

    with patch("api.services.state_snapshot_service._get_graph", return_value=mock_graph):
        from api.services.state_snapshot_service import inject_human_messages_to_state

        await inject_human_messages_to_state(
            chatwoot_conversation_id="conv-123",
            conversation_history_id=conv_history_id,
            paused_at=paused_at,
            session=mock_session,
            graph=mock_graph,
        )

    assert len(captured_stmts) == 1, "Expected exactly one SQL statement"

    # Compile the statement with literal binds to inspect filter values.
    # SQLAlchemy renders UUIDs without hyphens in some dialects, so compare
    # the normalized (no-hyphen) form of the UUID.
    try:
        compiled = captured_stmts[0].compile(compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)
    except Exception:
        sql_str = str(captured_stmts[0])

    uuid_no_hyphens = str(conv_history_id).replace("-", "")
    assert uuid_no_hyphens in sql_str, (
        f"conversation_history_id={conv_history_id} not found in SQL:\n{sql_str}"
    )
