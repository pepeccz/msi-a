"""
Tests for finalizar_expediente() _internal_flags — Bug 1: case_finalized flag.

Fix: finalizar_expediente() now returns _internal_flags: {"case_finalized": True}
on BOTH the primary (first finalization) and idempotent (already_finalized) paths.
Error paths must NOT carry this flag.

Architecture notes:
- get_case_fsm_state() reads from ContextVar (mode_context), not fsm_state param.
- current_mode must be "EXPEDIENTE_MODE" for the ContextVar to yield a real step.
- case_id comes from mode_context["case_id"].
- expediente_sub_mode maps to CollectionStep (e.g. "review_summary").
- ChatwootClient is imported inside the try block, so patch via `shared.chatwoot_client`.

Scenarios covered:
  1. Primary success path  → _internal_flags.case_finalized == True
  2. Idempotent path       → _internal_flags.case_finalized == True
  3. Wrong-phase error     → no _internal_flags.case_finalized
  4. No active case error  → no _internal_flags.case_finalized
  5. DB exception          → no _internal_flags.case_finalized
"""

import uuid
from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.state.helpers import set_current_state
from agent.tools.case_tools import finalizar_expediente


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state_at_review_summary(case_id: str) -> dict[str, Any]:
    """
    Build a conversation state that places the tool in REVIEW_SUMMARY.
    The ContextVar (get_case_fsm_state) reads from mode_context, so:
      - current_mode = "EXPEDIENTE_MODE"
      - mode_context.expediente_sub_mode = "review_summary"
      - mode_context.case_id = <case_id>
    Note: conversation_id must be numeric-string because finalizar_expediente
    does int(conversation_id) before calling Chatwoot.
    """
    return {
        "conversation_id": "42",  # Must be numeric for int() cast in tool
        "user_id": str(uuid.uuid4()),
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "expediente_sub_mode": "review_summary",
            "case_id": case_id,
            "category_slug": "motos-part",
            "element_codes": ["ESCAPE"],
            "tariff_amount": 350.0,
        },
        "fsm_state": {},
    }


def _make_state_at_step(step: str, case_id: str | None = None) -> dict[str, Any]:
    """Build state at an arbitrary sub-mode step."""
    return {
        "conversation_id": "42",  # Must be numeric for int() cast in tool
        "user_id": str(uuid.uuid4()),
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "expediente_sub_mode": step,
            "case_id": case_id or str(uuid.uuid4()),
            "category_slug": "motos-part",
            "element_codes": ["ESCAPE"],
        },
        "fsm_state": {},
    }


def _make_mock_case(status: str, case_id: str) -> MagicMock:
    """Build a minimal mock Case ORM object."""
    case = MagicMock()
    case.id = uuid.UUID(case_id)
    case.status = status
    case.metadata_ = {}
    case.completed_at = None
    case.updated_at = None
    return case


def _make_mock_session(case: MagicMock) -> AsyncMock:
    """Build an AsyncMock DB session that returns the given case on .get()."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=case)
    session.commit = AsyncMock()
    return session


def _make_mock_chatwoot() -> MagicMock:
    """Build a mock ChatwootClient."""
    cw = AsyncMock()
    cw.add_private_note = AsyncMock(return_value=True)
    cw.add_labels = AsyncMock(return_value=True)
    return cw


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestFinalizarExpedienteFlags:
    """Bug 1 — _internal_flags.case_finalized must be True on success paths."""

    # ------------------------------------------------------------------
    # Scenario 1: Primary success path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_primary_success_path_sets_case_finalized_flag(self):
        """
        GIVEN finalizar_expediente() succeeds on first call (case.status == "open")
        THEN  result contains _internal_flags.case_finalized == True
        """
        case_id = str(uuid.uuid4())
        mock_state = _make_state_at_review_summary(case_id)
        set_current_state(mock_state)

        case = _make_mock_case(status="open", case_id=case_id)
        session = _make_mock_session(case)
        cw = _make_mock_chatwoot()

        with patch("agent.tools.case_tools.get_async_session", return_value=session), \
             patch("agent.tools.case_tools.get_current_state", return_value=mock_state), \
             patch("shared.chatwoot_client.ChatwootClient", return_value=cw):

            result = await finalizar_expediente.coroutine()

        assert result.get("success") is True, f"Expected success=True, got: {result}"
        flags = result.get("_internal_flags", {})
        assert flags.get("case_finalized") is True, (
            f"Expected _internal_flags.case_finalized=True, got: {flags}"
        )

    # ------------------------------------------------------------------
    # Scenario 2: Idempotent path (already pending_review)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_idempotent_path_sets_case_finalized_flag(self):
        """
        GIVEN finalizar_expediente() called but case is already pending_review
        THEN  result.already_finalized == True AND _internal_flags.case_finalized == True
        """
        case_id = str(uuid.uuid4())
        mock_state = _make_state_at_review_summary(case_id)
        set_current_state(mock_state)

        # Case already finalized — no Chatwoot call needed (idempotent path)
        case = _make_mock_case(status="pending_review", case_id=case_id)
        session = _make_mock_session(case)

        with patch("agent.tools.case_tools.get_async_session", return_value=session), \
             patch("agent.tools.case_tools.get_current_state", return_value=mock_state):

            result = await finalizar_expediente.coroutine()

        assert result.get("success") is True, f"Expected success=True, got: {result}"
        assert result.get("already_finalized") is True
        flags = result.get("_internal_flags", {})
        assert flags.get("case_finalized") is True, (
            f"Expected _internal_flags.case_finalized=True on idempotent path, got: {flags}"
        )

    # ------------------------------------------------------------------
    # Scenario 3: Wrong phase — case_finalized must NOT be in result
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_wrong_phase_error_does_not_set_case_finalized_flag(self):
        """
        GIVEN finalizar_expediente() called while in collect_personal (wrong phase)
        THEN  result.success == False AND _internal_flags.case_finalized is absent/False
        """
        case_id = str(uuid.uuid4())
        mock_state = _make_state_at_step("collect_personal", case_id)
        set_current_state(mock_state)

        with patch("agent.tools.case_tools.get_current_state", return_value=mock_state):
            result = await finalizar_expediente.coroutine()

        assert result.get("success") is False, (
            f"Expected success=False for wrong-phase call, got: {result}"
        )
        flags = result.get("_internal_flags", {})
        assert not flags.get("case_finalized"), (
            f"Expected case_finalized absent/False on error path, got: {flags}"
        )

    # ------------------------------------------------------------------
    # Scenario 4: No active case — case_finalized must NOT be in result
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_active_case_error_does_not_set_case_finalized_flag(self):
        """
        GIVEN finalizar_expediente() called but mode_context has no case_id
        THEN  result.success == False AND _internal_flags.case_finalized absent/False
        """
        # State WITHOUT case_id in mode_context
        mock_state: dict[str, Any] = {
            "conversation_id": "42",  # Numeric so int() cast doesn't fail first
            "user_id": str(uuid.uuid4()),
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "review_summary",
                # No case_id key — this triggers NO_ACTIVE_CASE error
            },
            "fsm_state": {},
        }
        set_current_state(mock_state)

        with patch("agent.tools.case_tools.get_current_state", return_value=mock_state):
            result = await finalizar_expediente.coroutine()

        assert result.get("success") is False, (
            f"Expected success=False when no case, got: {result}"
        )
        flags = result.get("_internal_flags", {})
        assert not flags.get("case_finalized"), (
            f"Expected case_finalized absent/False when no case, got: {flags}"
        )

    # ------------------------------------------------------------------
    # Scenario 5: DB exception — case_finalized must NOT be in result
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_db_exception_does_not_set_case_finalized_flag(self):
        """
        GIVEN DB commit raises an exception
        WHEN  finalizar_expediente() is called at review_summary phase
        THEN  result.success == False AND _internal_flags.case_finalized absent/False
        """
        case_id = str(uuid.uuid4())
        mock_state = _make_state_at_review_summary(case_id)
        set_current_state(mock_state)

        # Case found but commit explodes
        case = _make_mock_case(status="open", case_id=case_id)
        session = _make_mock_session(case)
        session.commit = AsyncMock(side_effect=Exception("DB connection lost"))

        with patch("agent.tools.case_tools.get_async_session", return_value=session), \
             patch("agent.tools.case_tools.get_current_state", return_value=mock_state):

            result = await finalizar_expediente.coroutine()

        assert result.get("success") is False, (
            f"Expected success=False on DB error, got: {result}"
        )
        flags = result.get("_internal_flags", {})
        assert not flags.get("case_finalized"), (
            f"Expected case_finalized absent/False on DB error, got: {flags}"
        )
