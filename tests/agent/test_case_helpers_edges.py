"""
Tests for edge cases in case_helpers.get_or_create_active_case().

Tasks 1.1, 1.2, 1.3 — harden-client-type-edges

Requirements verified:
  - 1.1: `case_creation_new_user_fallback` log event is emitted when user_id=None,
          client_type="particular"
  - 1.2: When user_id=None, _find_active_case queries by conversation_id (not user_id)
  - 1.3: Professional with active case returns created=False via conversation-scoped lookup

Import strategy:
  - Import agent.services.case_helpers directly (no heavy FastAPI deps at module level)
  - Patch get_async_session via context manager mock
  - Patch the module-level structlog logger to capture log calls
    (avoids module-level `import structlog.testing` which interacts badly with
    the conftest sys.modules snapshot that contains structlog=None)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_case(
    *,
    conversation_id: str = "CONV-TEST",
    status: str = "collecting",
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock Case object."""
    case = MagicMock()
    case.id = uuid.uuid4()
    case.conversation_id = conversation_id
    case.status = status
    case.user_id = user_id
    return case


def _make_session_with_no_existing(
    insert_rowcount: int = 1,
    case_to_refresh: MagicMock | None = None,
) -> MagicMock:
    """Build a mock AsyncSession where no existing case is found.

    execute() returns rowcount=insert_rowcount for the INSERT.
    get() is not used by this path.
    """
    session = AsyncMock()

    # For the ON CONFLICT INSERT, we need a result with .rowcount
    execute_result = MagicMock()
    execute_result.rowcount = insert_rowcount

    # For _select_case_by_id after a successful insert
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(
        return_value=case_to_refresh
    )

    # First execute() → INSERT result, subsequent → SELECT result
    session.execute = AsyncMock(
        side_effect=[execute_result, select_result]
    )
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    return session


def _session_ctx(session: MagicMock):
    """Return an async context manager that yields the session."""
    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


# ---------------------------------------------------------------------------
# Task 1.1 — `case_creation_new_user_fallback` log emitted for particular
#             with user_id=None
# ---------------------------------------------------------------------------


class TestNewUserFallbackLogsEvent:
    """1.1: `case_creation_new_user_fallback` log event must be emitted when
    user_id=None and client_type="particular"."""

    async def test_log_event_emitted_for_particular_without_user_id(self):
        """The `case_creation_new_user_fallback` event MUST appear in structured
        logs when a particular user has no DB record (user_id=None)."""
        from agent.services.case_helpers import get_or_create_active_case

        conversation_id = "CONV-NEW-USER"
        mock_case = _make_mock_case(conversation_id=conversation_id)

        # _find_active_case query (conversation-scoped SELECT) returns nothing
        find_result = MagicMock()
        find_result.scalar_one_or_none = MagicMock(return_value=None)

        # plain INSERT session — add + commit + refresh
        insert_session = AsyncMock()
        insert_session.add = MagicMock()
        insert_session.commit = AsyncMock()
        insert_session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", mock_case.id)
        )

        find_session = AsyncMock()
        find_session.execute = AsyncMock(return_value=find_result)

        call_count = {"n": 0}

        @asynccontextmanager
        async def _multi_session_ctx():
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield find_session
            else:
                yield insert_session

        # Patch the module-level logger to capture structured log calls
        mock_logger = MagicMock()
        with patch("agent.services.case_helpers.logger", mock_logger):
            with patch(
                "agent.services.case_helpers.get_async_session",
                _multi_session_ctx,
            ):
                case, created = await get_or_create_active_case(
                    user_id=None,
                    conversation_id=conversation_id,
                    client_type="particular",
                )

        # Check that logger.info was called with "case_creation_new_user_fallback"
        info_calls = [call.args[0] for call in mock_logger.info.call_args_list]
        assert "case_creation_new_user_fallback" in info_calls, (
            f"Expected logger.info('case_creation_new_user_fallback', ...) to be called. "
            f"Actual info call events: {info_calls}"
        )

    async def test_log_event_includes_conversation_id(self):
        """The `case_creation_new_user_fallback` log call MUST be made with conversation_id."""
        from agent.services.case_helpers import get_or_create_active_case

        conversation_id = "CONV-FALLBACK-CTX"
        mock_case = _make_mock_case(conversation_id=conversation_id)

        find_result = MagicMock()
        find_result.scalar_one_or_none = MagicMock(return_value=None)

        find_session = AsyncMock()
        find_session.execute = AsyncMock(return_value=find_result)

        insert_session = AsyncMock()
        insert_session.add = MagicMock()
        insert_session.commit = AsyncMock()
        insert_session.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", mock_case.id)
        )

        call_count = {"n": 0}

        @asynccontextmanager
        async def _multi_session_ctx():
            call_count["n"] += 1
            if call_count["n"] == 1:
                yield find_session
            else:
                yield insert_session

        mock_logger = MagicMock()
        with patch("agent.services.case_helpers.logger", mock_logger):
            with patch(
                "agent.services.case_helpers.get_async_session",
                _multi_session_ctx,
            ):
                await get_or_create_active_case(
                    user_id=None,
                    conversation_id=conversation_id,
                    client_type="particular",
                )

        # Find the specific call
        fallback_call = next(
            (call for call in mock_logger.info.call_args_list
             if call.args and call.args[0] == "case_creation_new_user_fallback"),
            None,
        )
        assert fallback_call is not None, (
            "No logger.info('case_creation_new_user_fallback', ...) call found."
        )
        # The conversation_id must be passed as a keyword argument
        assert fallback_call.kwargs.get("conversation_id") == conversation_id, (
            f"Expected conversation_id={conversation_id!r} in logger call kwargs, "
            f"got {fallback_call.kwargs!r}."
        )


# ---------------------------------------------------------------------------
# Task 1.2 — _find_active_case queries by conversation_id when user_id=None
# ---------------------------------------------------------------------------


class TestNewUserFallbackUsesConversationScope:
    """1.2: When user_id=None, _find_active_case must use conversation_id
    scoped lookup, NOT a user_id-based query."""

    async def test_conversation_scoped_lookup_when_no_user_id(self):
        """When user_id=None, _find_active_case returns existing case
        found via conversation_id scope."""
        from agent.services.case_helpers import _find_active_case

        conversation_id = "CONV-SCOPE-TEST"
        existing_case = _make_mock_case(conversation_id=conversation_id)

        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=existing_case)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)

        @asynccontextmanager
        async def _ctx():
            yield mock_session

        with patch("agent.services.case_helpers.get_async_session", _ctx):
            result = await _find_active_case(
                user_id=None,
                conversation_id=conversation_id,
                client_type="particular",
            )

        assert result is existing_case, (
            "Expected the existing case to be returned via conversation_id scope. "
            f"Got: {result!r}"
        )

    async def test_no_case_found_returns_none_when_none_in_db(self):
        """_find_active_case returns None when no case exists for conversation_id."""
        from agent.services.case_helpers import _find_active_case

        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)

        @asynccontextmanager
        async def _ctx():
            yield mock_session

        with patch("agent.services.case_helpers.get_async_session", _ctx):
            result = await _find_active_case(
                user_id=None,
                conversation_id="CONV-EMPTY",
                client_type="particular",
            )

        assert result is None, f"Expected None, got {result!r}"


# ---------------------------------------------------------------------------
# Task 1.3 — Professional with active case returns created=False via
#             conversation-scoped lookup
# ---------------------------------------------------------------------------


class TestProfessionalExistingCaseFoundByConversation:
    """1.3: A professional user with an existing active case for the same
    conversation_id MUST get created=False."""

    async def test_professional_existing_case_returns_created_false(self):
        """When a professional already has an active case for CONV-PRO,
        get_or_create_active_case must return (case, False)."""
        from agent.services.case_helpers import get_or_create_active_case

        conversation_id = "CONV-PRO"
        existing_case = _make_mock_case(conversation_id=conversation_id)

        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=existing_case)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)

        @asynccontextmanager
        async def _ctx():
            yield mock_session

        with patch("agent.services.case_helpers.get_async_session", _ctx):
            case, created = await get_or_create_active_case(
                user_id="11111111-1111-1111-1111-111111111111",
                conversation_id=conversation_id,
                client_type="professional",
            )

        assert created is False, (
            f"Expected created=False (existing case found), got created={created!r}"
        )
        assert case is existing_case, (
            "Expected the existing case object to be returned, got different object"
        )
