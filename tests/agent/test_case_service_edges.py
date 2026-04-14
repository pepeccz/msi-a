"""
Tests for taller_propio guard in case_service.update_workshop_data().

Tasks 1.4, 1.5, 1.6 — harden-client-type-edges

Requirements verified:
  - 1.4: professional with taller_propio=True is blocked with error_code
          PROFESSIONAL_NO_TALLER_PROPIO
  - 1.5: professional with taller_propio=False is allowed (success=True)
  - 1.6: particular with taller_propio=True is allowed (existing behavior unchanged)

Import strategy:
  - Import case_service directly
  - Build minimal state/mode_context dicts matching production patterns
  - Mock get_async_session for DB calls
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workshop_state(
    *,
    client_type: str = "particular",
    case_id: str | None = None,
) -> dict:
    """Build a minimal LangGraph state with a COLLECT_WORKSHOP mode_context.

    Note: get_mode_context() reads 'expediente_sub_mode' for the step value,
    NOT 'current_step'. And get_current_step() reads mc.get('step') from
    the CaseCollectionState built by get_mode_context().
    client_type lives on mode_context for the professional guard.
    """
    _case_id = case_id or str(uuid.uuid4())
    return {
        "current_mode": "EXPEDIENTE_MODE",
        # client_type lives at top-level state (not in mode_context)
        "client_type": client_type,
        "mode_context": {
            "case_id": _case_id,
            "expediente_sub_mode": "collect_workshop",
            "taller_propio": None,
            "taller_data": {},
        },
    }


def _noop_session_ctx():
    """Async session context that does nothing (for tests that don't hit DB)."""
    @asynccontextmanager
    async def _ctx():
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        yield session

    return _ctx


# ---------------------------------------------------------------------------
# Task 1.4 — professional with taller_propio=True is BLOCKED
# ---------------------------------------------------------------------------


class TestProfessionalTallerPropioTrueBlocked:
    """1.4: update_workshop_data must reject taller_propio=True for professionals."""

    async def test_professional_taller_propio_true_returns_error(self):
        """When client_type='professional' and taller_propio=True,
        the response must have success=False and error_code=PROFESSIONAL_NO_TALLER_PROPIO."""
        from agent.services.case_service import update_workshop_data

        state = _make_workshop_state(client_type="professional")

        result = await update_workshop_data(
            taller_propio=True,
            datos_taller=None,
            state=state,
        )

        assert result.get("success") is False, (
            f"Expected success=False for professional + taller_propio=True. "
            f"Got: {result!r}"
        )
        assert result.get("error_code") == "PROFESSIONAL_NO_TALLER_PROPIO", (
            f"Expected error_code='PROFESSIONAL_NO_TALLER_PROPIO'. "
            f"Got error_code={result.get('error_code')!r}. Full result: {result!r}"
        )

    async def test_professional_taller_propio_true_does_not_persist(self):
        """No DB write should happen when the professional guard triggers.

        The guard returns before any DB interaction — get_async_session is
        never entered as a context manager.
        """
        from agent.services.case_service import update_workshop_data

        state = _make_workshop_state(client_type="professional")

        db_entered = {"called": False}

        @asynccontextmanager
        async def _tracking_session_ctx():
            db_entered["called"] = True
            session = AsyncMock()
            yield session

        with patch(
            "agent.services.case_service.get_async_session",
            _tracking_session_ctx,
        ):
            result = await update_workshop_data(
                taller_propio=True,
                datos_taller=None,
                state=state,
            )

        # The guard must fire before any DB interaction
        assert result.get("success") is False
        assert result.get("error_code") == "PROFESSIONAL_NO_TALLER_PROPIO"
        # DB session was never entered (early return before any DB call)
        assert db_entered["called"] is False, (
            "get_async_session should NOT have been called — the guard must "
            "return before reaching any DB code."
        )


# ---------------------------------------------------------------------------
# Task 1.5 — professional with taller_propio=False is ALLOWED
# ---------------------------------------------------------------------------


class TestProfessionalTallerPropioFalseAllowed:
    """1.5: update_workshop_data must allow taller_propio=False for professionals."""

    async def test_professional_taller_propio_false_is_allowed(self):
        """When client_type='professional' and taller_propio=False,
        the tool must not block — it should proceed normally (success=True or
        transition to REVIEW_SUMMARY)."""
        from agent.services.case_service import update_workshop_data

        case_id = str(uuid.uuid4())
        state = _make_workshop_state(client_type="professional", case_id=case_id)

        # Mock DB session: session.get(Case, ...) → mock case object
        mock_case = MagicMock()
        mock_case.id = uuid.UUID(case_id)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_case)
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def _ctx():
            yield mock_session

        with patch("agent.services.case_service.get_async_session", _ctx):
            result = await update_workshop_data(
                taller_propio=False,
                datos_taller=None,
                state=state,
            )

        # Must NOT have the professional guard error
        assert result.get("error_code") != "PROFESSIONAL_NO_TALLER_PROPIO", (
            "Professional taller_propio=False must NOT be blocked by the guard. "
            f"Got: {result!r}"
        )
        assert result.get("success") is True, (
            f"Expected success=True for professional + taller_propio=False. "
            f"Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Task 1.6 — particular with taller_propio=True is ALLOWED (unchanged behavior)
# ---------------------------------------------------------------------------


class TestParticularTallerPropioTrueAllowed:
    """1.6: update_workshop_data must not block taller_propio=True for particulars."""

    async def test_particular_taller_propio_true_is_not_blocked(self):
        """When client_type='particular' and taller_propio=True,
        the tool must NOT return PROFESSIONAL_NO_TALLER_PROPIO."""
        from agent.services.case_service import update_workshop_data

        case_id = str(uuid.uuid4())
        state = _make_workshop_state(client_type="particular", case_id=case_id)

        mock_case = MagicMock()
        mock_case.id = uuid.UUID(case_id)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_case)
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def _ctx():
            yield mock_session

        with patch("agent.services.case_service.get_async_session", _ctx):
            result = await update_workshop_data(
                taller_propio=True,
                datos_taller=None,
                state=state,
            )

        assert result.get("error_code") != "PROFESSIONAL_NO_TALLER_PROPIO", (
            "Particular users must NOT be blocked by the professional guard. "
            f"Got: {result!r}"
        )
        # For a particular with taller_propio=True, success=True is expected
        assert result.get("success") is True, (
            f"Expected success=True for particular + taller_propio=True. "
            f"Got: {result!r}"
        )
