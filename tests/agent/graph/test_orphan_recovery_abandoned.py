"""
Batch 3 — T-B3-1 (RED): Orphan recovery for abandoned cases.

Tests the extended _try_recover_orphaned_expediente() and the preprocess_node
branching when a recovered case has was_abandoned=True.

Spec coverage: Spec 4 — Intelligent Re-entry for Abandoned Cases
  - Abandoned case found → pending_abandoned_case set, current_mode stays START
  - pending_recovery_case is NOT set for abandoned cases
  - Active case (collecting) → still forces EXPEDIENTE_MODE (regression guard)
  - was_abandoned: True present in recovery dict for abandoned cases
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


def _make_case(
    status: str,
    case_id: str = "aaaa0000-0000-0000-0000-000000000002",
    user_id: str = "aaaa0000-0000-0000-0000-000000000001",
    conversation_id: str = "conv-old-001",
    element_codes: list[str] | None = None,
    abandoned_at: datetime | None = None,
) -> MagicMock:
    """Build a mock Case object for tests."""
    case = MagicMock()
    case.id = MagicMock()
    case.id.__str__ = lambda self: case_id
    case.status = status
    case.user_id = user_id
    case.conversation_id = conversation_id
    case.element_codes = element_codes or ["ESCAPE", "SUSPENSION"]
    case.abandoned_at = abandoned_at
    case.category = MagicMock()
    case.category.slug = "motos-part"
    case.category_id = MagicMock()
    case.category_id.__str__ = lambda self: "cat-uuid-001"
    case.tariff_tier_id = None
    case.tariff_amount = None
    case.created_at = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    case.updated_at = datetime(2026, 4, 8, 14, 0, 0, tzinfo=UTC)
    case.vehiculo_marca = None
    case.vehiculo_modelo = None
    case.itv_nombre = None
    return case


def _make_state(
    user_id: str = "aaaa0000-0000-0000-0000-000000000001",
    conversation_id: str = "conv-new-001",
    current_mode: str = "START",
    total_message_count: int = 0,
) -> dict:
    """Build a minimal ConversationState dict for tests.

    total_message_count=0 means preprocess_node will compute total=1,
    which triggers the orphan recovery check (condition: total == 1).
    """
    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "current_mode": current_mode,
        "messages": [{"role": "user", "content": "hola"}],
        "user_message": "hola",
        "total_message_count": total_message_count,
        "mode_message_count": 0,
        "agent_disabled": False,
        "pending_images": None,
        "tarifa_actual": None,
        "incoming_attachments": [],
    }


# =============================================================================
# T-B3-1a: _try_recover_orphaned_expediente — abandoned case
# =============================================================================


class TestTryRecoverOrphanedExpedienteAbandoned:
    """
    Unit tests for _try_recover_orphaned_expediente() with abandoned case.

    Spec 4 — "Abandoned case found on first message":
    - was_abandoned: True in returned dict
    - abandoned_at ISO string present
    - element_codes present
    """

    @pytest.mark.asyncio
    async def test_abandoned_case_returns_was_abandoned_true(self):
        """
        Spec 4: When the DB has a case with status='abandoned', the recovery
        dict must include was_abandoned=True.
        """
        abandoned_at = datetime(2026, 4, 8, 14, 0, 0, tzinfo=UTC)
        case = _make_case(
            status="abandoned",
            abandoned_at=abandoned_at,
        )
        state = _make_state()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        mock_ced_result = MagicMock()
        mock_ced_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_ced_result]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            from agent.graph.conversation_graph import (
                _try_recover_orphaned_expediente,
            )

            result = await _try_recover_orphaned_expediente(state)

        assert result is not None, "Abandoned case must be recovered (not None)"
        assert result.get("was_abandoned") is True, (
            "Recovery dict must have was_abandoned=True for abandoned case"
        )

    @pytest.mark.asyncio
    async def test_abandoned_case_includes_abandoned_at_iso(self):
        """
        Spec 4: Recovery dict for abandoned case must include abandoned_at
        as ISO-format string.
        """
        abandoned_at = datetime(2026, 4, 8, 14, 0, 0, tzinfo=UTC)
        case = _make_case(status="abandoned", abandoned_at=abandoned_at)
        state = _make_state()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        mock_ced_result = MagicMock()
        mock_ced_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_ced_result]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            from agent.graph.conversation_graph import (
                _try_recover_orphaned_expediente,
            )

            result = await _try_recover_orphaned_expediente(state)

        assert result is not None
        assert "abandoned_at" in result, (
            "Recovery dict must include abandoned_at for abandoned case"
        )
        assert result["abandoned_at"] == abandoned_at.isoformat(), (
            "abandoned_at must be ISO-format string"
        )

    @pytest.mark.asyncio
    async def test_abandoned_case_includes_element_codes(self):
        """
        Spec 4: element_codes must be present in the recovery dict.
        """
        case = _make_case(
            status="abandoned",
            element_codes=["ESCAPE", "MANILLAR"],
        )
        state = _make_state()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        mock_ced_result = MagicMock()
        mock_ced_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_ced_result]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            from agent.graph.conversation_graph import (
                _try_recover_orphaned_expediente,
            )

            result = await _try_recover_orphaned_expediente(state)

        assert result is not None
        assert result.get("element_codes") == ["ESCAPE", "MANILLAR"], (
            "element_codes must be included in abandoned recovery dict"
        )

    @pytest.mark.asyncio
    async def test_active_case_does_not_have_was_abandoned(self):
        """
        Spec 4 (regression): Active case (status='collecting') must NOT have
        was_abandoned=True in the recovery dict.
        """
        case = _make_case(status="collecting")
        state = _make_state()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = case
        mock_ced_result = MagicMock()
        mock_ced_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_ced_result]
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            from agent.graph.conversation_graph import (
                _try_recover_orphaned_expediente,
            )

            result = await _try_recover_orphaned_expediente(state)

        assert result is not None
        assert not result.get("was_abandoned"), (
            "Active case recovery dict must NOT have was_abandoned=True"
        )


# =============================================================================
# T-B3-1b: preprocess_node branching — abandoned case → pending_abandoned_case
# =============================================================================


class TestPreprocessNodeAbandonedBranching:
    """
    Tests for preprocess_node branching when recovery returns was_abandoned=True.

    Spec 4:
    - Abandoned case injects pending_abandoned_case, stays in START
    - pending_recovery_case is NOT set for abandoned cases
    - Active case still forces EXPEDIENTE_MODE (regression guard)
    """

    @pytest.mark.asyncio
    async def test_abandoned_recovery_sets_pending_abandoned_case(self):
        """
        Spec 4: When was_abandoned=True, preprocess_node must inject
        pending_abandoned_case into mode_context.
        """
        from agent.graph.conversation_graph import preprocess_node

        abandoned_recovery = {
            "case_id": "case-uuid-001",
            "status": "abandoned",
            "was_abandoned": True,
            "element_codes": ["ESCAPE"],
            "abandoned_at": "2026-04-08T14:00:00+00:00",
            "time_gap_hours": 72.0,
        }
        state = _make_state()

        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=abandoned_recovery),
        ):
            result = await preprocess_node(state)

        mode_context = result.get("mode_context")
        if hasattr(mode_context, "__wrapped__"):
            mode_context = mode_context.__wrapped__
        actual_context = (
            mode_context.value
            if hasattr(mode_context, "value")
            else mode_context
        )

        assert actual_context is not None, "mode_context must be set"
        assert "pending_abandoned_case" in actual_context, (
            "pending_abandoned_case must be in mode_context for abandoned recovery"
        )
        assert actual_context["pending_abandoned_case"]["case_id"] == "case-uuid-001"

    @pytest.mark.asyncio
    async def test_abandoned_recovery_does_not_set_pending_recovery_case(self):
        """
        Spec 4: When was_abandoned=True, pending_recovery_case must NOT be set.
        """
        from agent.graph.conversation_graph import preprocess_node

        abandoned_recovery = {
            "case_id": "case-uuid-001",
            "status": "abandoned",
            "was_abandoned": True,
            "element_codes": ["ESCAPE"],
            "abandoned_at": "2026-04-08T14:00:00+00:00",
            "time_gap_hours": 72.0,
        }
        state = _make_state()

        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=abandoned_recovery),
        ):
            result = await preprocess_node(state)

        mode_context = result.get("mode_context")
        actual_context = (
            mode_context.value
            if hasattr(mode_context, "value")
            else mode_context
        )

        assert actual_context is not None
        assert "pending_recovery_case" not in actual_context, (
            "pending_recovery_case must NOT be set for abandoned case recovery"
        )

    @pytest.mark.asyncio
    async def test_abandoned_recovery_keeps_current_mode_start(self):
        """
        Spec 4: When was_abandoned=True, current_mode must remain START
        (NOT forced to EXPEDIENTE_MODE).
        """
        from agent.graph.conversation_graph import preprocess_node

        abandoned_recovery = {
            "case_id": "case-uuid-001",
            "status": "abandoned",
            "was_abandoned": True,
            "element_codes": ["ESCAPE"],
            "abandoned_at": "2026-04-08T14:00:00+00:00",
            "time_gap_hours": 72.0,
        }
        state = _make_state()

        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=abandoned_recovery),
        ):
            result = await preprocess_node(state)

        assert result.get("current_mode") != "EXPEDIENTE_MODE", (
            "Abandoned recovery must NOT force EXPEDIENTE_MODE"
        )

    @pytest.mark.asyncio
    async def test_active_recovery_still_forces_expediente_mode(self):
        """
        Spec 4 (regression): Active case recovery must still set
        current_mode=EXPEDIENTE_MODE and inject pending_recovery_case.
        """
        from agent.graph.conversation_graph import preprocess_node

        active_recovery = {
            "case_id": "case-uuid-002",
            "status": "collecting",
            "element_codes": ["ALUMBRADO"],
            "time_gap_hours": 2.0,
            "inferred_sub_mode": "collect_element_data",
        }
        state = _make_state()

        with patch(
            "agent.graph.conversation_graph._try_recover_orphaned_expediente",
            new=AsyncMock(return_value=active_recovery),
        ):
            result = await preprocess_node(state)

        assert result.get("current_mode") == "EXPEDIENTE_MODE", (
            "Active case recovery must still force EXPEDIENTE_MODE"
        )

        mode_context = result.get("mode_context")
        actual_context = (
            mode_context.value
            if hasattr(mode_context, "value")
            else mode_context
        )
        assert "pending_recovery_case" in actual_context, (
            "Active case recovery must inject pending_recovery_case"
        )
