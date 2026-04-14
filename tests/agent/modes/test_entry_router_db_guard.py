"""
Unit tests for entry_router DB guard — fix-expediente-mode-not-reset.

Tests that entry_router checks case status in DB and exits EXPEDIENTE_MODE
for terminal statuses.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.modes.expediente_nodes as expediente_nodes_mod
from agent.modes.expediente_nodes import entry_router, _TERMINAL_CASE_STATUSES


def _make_state(
    case_id: str = "test-case-id",
    sub_mode: str = "review_summary",
    **extra,
) -> dict:
    """Build a minimal ExpedienteState-like dict for entry_router."""
    base = {
        "case_id": case_id,
        "conversation_id": "conv-1",
        "expediente_sub_mode": sub_mode,
        "user_message": "hola",
        "element_phase": None,
        "current_element_code": None,
        "element_data_status": {},
        "personal_collected": False,
        "vehicle_collected": False,
        "workshop_collected": False,
        "taller_propio": None,
        "messages": [],
    }
    base.update(extra)
    return base


def _mock_get_session_returning(case_status: str):
    """Create a mock get_async_session that returns a case with given status."""
    mock_case = MagicMock()
    mock_case.status = case_status

    mock_result = MagicMock()
    mock_result.first.return_value = mock_case

    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _fake():
        yield mock_session

    return _fake


def _mock_get_session_raising(exc: Exception):
    """Create a mock get_async_session that raises on scalars()."""
    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(side_effect=exc)

    @asynccontextmanager
    async def _fake():
        yield mock_session

    return _fake


class TestTerminalCaseStatuses:
    """_TERMINAL_CASE_STATUSES must include all terminal states."""

    def test_contains_expected_statuses(self):
        assert "pending_review" in _TERMINAL_CASE_STATUSES
        assert "resolved" in _TERMINAL_CASE_STATUSES
        assert "cancelled" in _TERMINAL_CASE_STATUSES
        assert "abandoned" in _TERMINAL_CASE_STATUSES

    def test_does_not_contain_active_statuses(self):
        assert "collecting" not in _TERMINAL_CASE_STATUSES
        assert "pending_images" not in _TERMINAL_CASE_STATUSES


class TestEntryRouterDbGuard:
    """entry_router must check case status in DB for terminal cases."""

    @pytest.mark.asyncio
    async def test_pending_review_exits_expediente(self):
        """
        Spec: case status pending_review → Command with current_mode CONSULTA_MODE
        and ai_response set.
        """
        state = _make_state()

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_returning("pending_review"),
        ):
            cmd = await entry_router(state)

        assert cmd.update is not None
        assert cmd.update["_transition_to"] == "CONSULTA_MODE"
        assert cmd.update.get("ai_response")

    @pytest.mark.asyncio
    async def test_cancelled_exits_expediente(self):
        """
        Spec: case status cancelled → Command with current_mode CONSULTA_MODE.
        """
        state = _make_state()

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_returning("cancelled"),
        ):
            cmd = await entry_router(state)

        assert cmd.update is not None
        assert cmd.update["_transition_to"] == "CONSULTA_MODE"

    @pytest.mark.asyncio
    async def test_collecting_continues_normally(self):
        """
        Spec: case status collecting → normal routing, no current_mode change.
        """
        state = _make_state()

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_returning("collecting"),
        ):
            cmd = await entry_router(state)

        # Normal routing — update may be None or dict without current_mode
        if cmd.update is not None:
            assert "_transition_to" not in cmd.update

    @pytest.mark.asyncio
    async def test_db_failure_continues_normally(self):
        """
        Spec: DB query fails → normal routing, warning logged.
        """
        state = _make_state()

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_raising(Exception("PoolClosed")),
        ):
            cmd = await entry_router(state)

        # Fallback: normal routing, no mode change
        if cmd.update is not None:
            assert "_transition_to" not in cmd.update
