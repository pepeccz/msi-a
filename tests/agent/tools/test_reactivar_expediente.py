"""
Batch 3 — T-B3-2 (RED): Tests for reactivar_expediente_abandonado tool.

Spec 4 coverage:
  - Success: abandoned case reactivated to collecting, abandoned_at cleared
  - Blocked: another active case exists for same user → error returned
  - Not found: case_id doesn't exist → error
  - Wrong status: case is not abandoned → error
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _make_case(
    status: str,
    case_id: str = "aaaa0000-0000-0000-0000-000000000002",
    user_id_str: str = "aaaa0000-0000-0000-0000-000000000001",
    element_codes: list[str] | None = None,
    abandoned_at: datetime | None = None,
) -> MagicMock:
    """Build a minimal mock Case for testing the tool."""
    import uuid as _uuid

    case = MagicMock()
    case.status = status
    case.user_id = _uuid.UUID(user_id_str)
    case.element_codes = element_codes or ["ESCAPE"]
    case.abandoned_at = abandoned_at or datetime(2026, 4, 8, 14, 0, 0, tzinfo=UTC)
    case.last_activity_at = None
    case.category = MagicMock()
    case.category.slug = "motos-part"
    case.category_id = MagicMock()
    case.tariff_amount = 410.0
    case.created_at = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    # Use a real UUID for id — tool uses str(case.id) for the response
    case.id = _uuid.UUID(case_id)
    return case


# =============================================================================
# Success path
# =============================================================================


class TestReactivarExpedienteSuccess:
    """
    Spec 4 — Successful reactivation:
    - Given case has status='abandoned' and no other active case for user
    - When reactivar_expediente_abandonado(case_id) is called
    - Then status='collecting', abandoned_at=None, last_activity_at=now()
    - And case details are returned
    """

    @pytest.mark.asyncio
    async def test_success_returns_case_details(self):
        """
        Spec 4/Success: reactivar_expediente_abandonado must return a dict
        with success=True and case summary on valid abandoned case.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(
            status="abandoned",
            case_id=case_id,
        )

        mock_session = AsyncMock()
        # First query: find the case
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        # Second query: check for existing active case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            result = await reactivar_expediente_abandonado.ainvoke(
                {"case_id": case_id}
            )

        assert isinstance(result, dict), "Tool must return a dict"
        assert result.get("success") is True, (
            f"Expected success=True, got: {result}"
        )
        assert "case_id" in result, "Result must include case_id"

    @pytest.mark.asyncio
    async def test_success_sets_status_collecting(self):
        """
        Spec 4/Success: reactivar must set case.status='collecting'.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="abandoned", case_id=case_id)

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            await reactivar_expediente_abandonado.ainvoke({"case_id": case_id})

        assert case.status == "collecting", (
            "reactivar must set case.status='collecting'"
        )

    @pytest.mark.asyncio
    async def test_success_clears_abandoned_at(self):
        """
        Spec 4/Success: reactivar must set case.abandoned_at=None.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="abandoned", case_id=case_id)

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            await reactivar_expediente_abandonado.ainvoke({"case_id": case_id})

        assert case.abandoned_at is None, (
            "reactivar must set case.abandoned_at=None"
        )

    @pytest.mark.asyncio
    async def test_success_sets_last_activity_at(self):
        """
        Spec 4/Success: reactivar must set case.last_activity_at to now().
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="abandoned", case_id=case_id)
        case.last_activity_at = None

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            await reactivar_expediente_abandonado.ainvoke({"case_id": case_id})

        assert case.last_activity_at is not None, (
            "reactivar must set case.last_activity_at to now()"
        )


# =============================================================================
# Blocked: existing active case
# =============================================================================


class TestReactivarExpedienteBlockedByActiveCase:
    """
    Spec 4 — Reactivation blocked:
    - Given case has status='abandoned' AND another collecting case exists
    - When reactivar_expediente_abandonado(case_id) is called
    - Then error is returned, no changes to either case
    """

    @pytest.mark.asyncio
    async def test_blocked_returns_error(self):
        """
        Spec 4/Blocked: When another active case exists, tool must return
        success=False with an error message.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="abandoned", case_id=case_id)
        existing_active = _make_case(
            status="collecting",
            case_id="bbbb0000-0000-0000-0000-000000000003",
        )

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = existing_active
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            result = await reactivar_expediente_abandonado.ainvoke(
                {"case_id": case_id}
            )

        assert result.get("success") is False, (
            "Tool must return success=False when another active case exists"
        )
        assert "error" in result or "message" in result, (
            "Error result must include error or message key"
        )

    @pytest.mark.asyncio
    async def test_blocked_does_not_modify_case(self):
        """
        Spec 4/Blocked: Abandoned case status must NOT change when blocked.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="abandoned", case_id=case_id)
        existing_active = _make_case(status="collecting")

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_active_result = MagicMock()
        mock_active_result.scalar_one_or_none.return_value = existing_active
        mock_session.execute = AsyncMock(
            side_effect=[mock_case_result, mock_active_result]
        )
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            await reactivar_expediente_abandonado.ainvoke({"case_id": case_id})

        assert case.status == "abandoned", (
            "Case status must remain 'abandoned' when reactivation is blocked"
        )
        mock_session.commit.assert_not_called()


# =============================================================================
# Not found
# =============================================================================


class TestReactivarExpedienteNotFound:
    """
    Spec 4 — Case not found:
    - Given case_id doesn't exist in DB
    - When reactivar_expediente_abandonado(case_id) is called
    - Then error result returned, no DB write
    """

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self):
        """
        Spec 4/Not found: Non-existent case_id must return error result.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000099"

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_case_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            result = await reactivar_expediente_abandonado.ainvoke(
                {"case_id": case_id}
            )

        assert result.get("success") is False, (
            "Non-existent case must return success=False"
        )
        mock_session.commit.assert_not_called()


# =============================================================================
# Wrong status (not abandoned)
# =============================================================================


class TestReactivarExpedienteWrongStatus:
    """
    Spec 4 — Case not abandoned:
    - Given case has status != 'abandoned'
    - When reactivar_expediente_abandonado(case_id) is called
    - Then error result returned, no DB write
    """

    @pytest.mark.asyncio
    async def test_wrong_status_returns_error(self):
        """
        Spec 4/Wrong status: Case with status='collecting' must return error.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="collecting", case_id=case_id)

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_session.execute = AsyncMock(return_value=mock_case_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            result = await reactivar_expediente_abandonado.ainvoke(
                {"case_id": case_id}
            )

        assert result.get("success") is False, (
            "Case with wrong status must return success=False"
        )
        assert case.status == "collecting", (
            "Case status must be unchanged after failed reactivation"
        )
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_completed_case_returns_error(self):
        """
        Triangulation: Case with status='completed' also returns error.
        """
        from agent.tools.case_tools import reactivar_expediente_abandonado

        case_id = "aaaa0000-0000-0000-0000-000000000002"
        case = _make_case(status="completed", case_id=case_id)

        mock_session = AsyncMock()
        mock_case_result = MagicMock()
        mock_case_result.scalar_one_or_none.return_value = case
        mock_session.execute = AsyncMock(return_value=mock_case_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "database.connection.get_async_session",
            return_value=mock_ctx,
        ):
            result = await reactivar_expediente_abandonado.ainvoke(
                {"case_id": case_id}
            )

        assert result.get("success") is False, (
            "Case with status='completed' must also return error"
        )
        mock_session.commit.assert_not_called()
