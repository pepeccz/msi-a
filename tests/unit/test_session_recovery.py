"""
Unit tests for session recovery UX — Phase 3 (T-21 through T-28).

Tasks covered:
  T-21 — Time gap signals in _try_recover_orphaned_expediente
  T-23 — 11_session_recovery.md file existence and content
  T-25 — Conditional loading of 11_session_recovery.md in loader.py
  T-27 — recovery_acknowledged flag lifecycle

All tests are placed in tests/unit/ so that unit conftest stubs are in effect.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, UTC, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest


# ---------------------------------------------------------------------------
# T-21: Time gap signals
# ---------------------------------------------------------------------------


class TestTimeGapSignals:
    """
    Verify that _try_recover_orphaned_expediente adds time_gap_hours and
    last_activity_at_iso to the recovery dict.

    These tests mock the DB session so no actual DB query is issued.
    """

    def _make_fake_case(
        self,
        updated_at: datetime | None,
        conversation_id: str = "other-conv",
        status: str = "collecting",
    ) -> MagicMock:
        """Build a minimal Case mock."""
        case = MagicMock()
        case.id = "case-uuid-001"
        case.conversation_id = conversation_id
        case.status = status
        case.updated_at = updated_at
        case.created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        case.element_codes = ["SUSPENSION", "ESCAPE"]
        case.category_id = "cat-uuid"
        case.tariff_tier_id = "tier-uuid"
        case.tariff_amount = 410.0
        case.vehiculo_marca = "Honda"
        case.vehiculo_modelo = "CBR600"
        case.itv_nombre = None
        case.taller_propio = None
        # category relationship
        cat = MagicMock()
        cat.slug = "motos-part"
        case.category = cat
        return case

    def _make_ced_result(self) -> MagicMock:
        """Empty CaseElementData result."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    async def _run_recovery(self, fake_case) -> dict | None:
        """Helper: run _try_recover_orphaned_expediente with a fake case, no DB."""
        state = {"user_id": "12345678-1234-1234-1234-123456789012", "conversation_id": "new-conv"}

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _scalar_result(fake_case),
                self._make_ced_result(),
            ]
        )
        ctx_mgr = MagicMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=None)

        with patch("database.connection.get_async_session", return_value=ctx_mgr):
            from agent.graph.conversation_graph import _try_recover_orphaned_expediente

            return await _try_recover_orphaned_expediente(state)

    @pytest.mark.asyncio
    async def test_72h_gap_returns_correct_hours(self):
        """Case.updated_at 72h ago → time_gap_hours == 72.0, valid ISO 8601."""
        now = datetime.now(UTC)
        updated_at = now - timedelta(hours=72)
        fake_case = self._make_fake_case(updated_at)

        result = await self._run_recovery(fake_case)

        assert result is not None
        assert result["time_gap_hours"] == 72.0
        # Verify ISO 8601 format (no exception on parse)
        parsed = datetime.fromisoformat(result["last_activity_at_iso"])
        assert parsed is not None

    @pytest.mark.asyncio
    async def test_25_min_gap_returns_fractional_hours(self):
        """Case.updated_at 25 min ago → time_gap_hours == 0.4."""
        now = datetime.now(UTC)
        updated_at = now - timedelta(minutes=25)
        fake_case = self._make_fake_case(updated_at)

        result = await self._run_recovery(fake_case)

        assert result is not None
        assert result["time_gap_hours"] == 0.4

    @pytest.mark.asyncio
    async def test_none_updated_at_returns_none_fields(self):
        """Case.updated_at None → both time_gap_hours and last_activity_at_iso are None, no exception."""
        fake_case = self._make_fake_case(updated_at=None)
        # Force both updated_at and created_at to None to test the None path
        fake_case.updated_at = None
        fake_case.created_at = None

        # Must not raise
        result = await self._run_recovery(fake_case)

        assert result is not None
        assert result["time_gap_hours"] is None
        assert result["last_activity_at_iso"] is None

    @pytest.mark.asyncio
    async def test_30_seconds_ago_never_negative(self):
        """Case.updated_at 30s ago → time_gap_hours == 0.0 (never negative)."""
        now = datetime.now(UTC)
        updated_at = now - timedelta(seconds=30)
        fake_case = self._make_fake_case(updated_at)

        result = await self._run_recovery(fake_case)

        assert result is not None
        assert result["time_gap_hours"] == 0.0
        assert result["time_gap_hours"] >= 0  # never negative


# ---------------------------------------------------------------------------
# T-23: 11_session_recovery.md content
# ---------------------------------------------------------------------------


class TestSessionRecoveryPromptFile:
    """Verify 11_session_recovery.md exists and has required content."""

    def _get_prompt_path(self) -> Path:
        return (
            Path(__file__).parent.parent.parent
            / "agent"
            / "prompts"
            / "core"
            / "11_session_recovery.md"
        )

    def test_file_exists(self):
        """File must exist at agent/prompts/core/11_session_recovery.md."""
        path = self._get_prompt_path()
        assert path.exists(), f"Expected file not found: {path}"

    def test_contains_pending_recovery_case(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        assert "pending_recovery_case" in content, (
            "Prompt must reference pending_recovery_case key"
        )

    def test_contains_recovery_acknowledged(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        assert "recovery_acknowledged" in content, (
            "Prompt must reference recovery_acknowledged key"
        )

    def test_contains_time_gap_hours(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        assert "time_gap_hours" in content, "Prompt must reference time_gap_hours key"

    def test_contains_hour_thresholds(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        assert "24" in content, "Prompt must contain '24' hour threshold"
        assert "1" in content, "Prompt must contain '1' hour threshold"

    def test_contains_continuamos(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        assert "Continuamos" in content or "continuamos" in content, (
            "Prompt must include 'Continuamos' option text"
        )

    def test_contains_new_option(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        # Must offer an option to start over
        assert "nuevo" in content.lower() or "empezar" in content.lower(), (
            "Prompt must offer a 'start new' option"
        )

    def test_all_in_spanish(self):
        content = self._get_prompt_path().read_text(encoding="utf-8")
        # Sanity check: Spanish words present
        spanish_indicators = ["usuario", "expediente", "tiempo", "el"]
        found = [w for w in spanish_indicators if w in content.lower()]
        assert len(found) >= 3, (
            f"Prompt appears not to be in Spanish. Found only: {found}"
        )


# ---------------------------------------------------------------------------
# T-25: Conditional loading in loader.py
# ---------------------------------------------------------------------------


class TestSessionRecoveryConditionalLoading:
    """Verify assemble_system_prompt conditionally includes recovery module."""

    def _make_mode_context(
        self,
        pending_recovery_case: dict | None = None,
        recovery_acknowledged: bool | None = None,
    ) -> dict:
        ctx: dict = {}
        if pending_recovery_case is not None:
            ctx["pending_recovery_case"] = pending_recovery_case
        if recovery_acknowledged is not None:
            ctx["recovery_acknowledged"] = recovery_acknowledged
        return ctx

    def _fake_recovery_case(self) -> dict:
        return {
            "case_id": "case-001",
            "status": "collecting",
            "time_gap_hours": 48.0,
            "last_activity_at_iso": "2026-04-06T10:00:00+00:00",
            "element_codes": ["SUSPENSION"],
            "inferred_sub_mode": "collect_element_data",
        }

    def test_recovery_prompt_included_when_pending_and_no_acknowledged(self):
        """mode_context with pending_recovery_case + no recovery_acknowledged → prompt includes recovery header."""
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        mode_context = self._make_mode_context(
            pending_recovery_case=self._fake_recovery_case()
        )
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=mode_context,
            sub_mode="collect_element_data",
        )
        # The file header should appear in the assembled prompt
        assert "Recuperación de sesión" in prompt or "recuperación" in prompt.lower(), (
            "Recovery prompt must be included when pending_recovery_case is set"
        )

    def test_recovery_prompt_excluded_when_no_pending(self):
        """mode_context without pending_recovery_case → recovery section NOT included."""
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        mode_context = self._make_mode_context()
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=mode_context,
            sub_mode="collect_element_data",
        )
        assert "pending_recovery_case" not in prompt, (
            "Recovery prompt must NOT be included when pending_recovery_case is absent"
        )

    def test_recovery_prompt_excluded_when_acknowledged(self):
        """mode_context with pending_recovery_case + recovery_acknowledged=True → NOT included."""
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        mode_context = self._make_mode_context(
            pending_recovery_case=self._fake_recovery_case(),
            recovery_acknowledged=True,
        )
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=mode_context,
            sub_mode="collect_element_data",
        )
        # Once acknowledged, the recovery block must NOT re-appear
        # We check that the recovery-specific marker isn't present
        assert "recovery_acknowledged" not in prompt or (
            # Allowed: recovery_acknowledged appears only in a context dump, not a full rule block
            "Recuperación de sesión" not in prompt
        ), (
            "Recovery prompt must NOT be included when recovery_acknowledged=True"
        )

    def test_no_exception_when_mode_context_is_none(self):
        """No exception when mode_context is None."""
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        # Must not raise
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=None,
            sub_mode="collect_element_data",
        )
        assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# T-27: recovery_acknowledged flag lifecycle
# ---------------------------------------------------------------------------


class TestRecoveryAcknowledgedLifecycle:
    """Verify recovery_acknowledged is set after first tool call and prevents re-inclusion."""

    @pytest.mark.asyncio
    async def test_first_turn_recovery_prompt_included(self):
        """
        When pending_recovery_case is in mode_context and recovery_acknowledged is absent,
        the assembled prompt must include the recovery section.
        """
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        mode_context = {
            "pending_recovery_case": {
                "case_id": "case-001",
                "time_gap_hours": 48.0,
                "last_activity_at_iso": "2026-04-06T10:00:00+00:00",
            }
        }
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=mode_context,
        )
        assert "Recuperación de sesión" in prompt or "recuperación" in prompt.lower()

    @pytest.mark.asyncio
    async def test_after_first_tool_call_recovery_acknowledged_set(self):
        """
        After the first tool call when pending_recovery_case is present,
        the returned state updates must include recovery_acknowledged=True in mode_context.
        """
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        mode_context = {
            "pending_recovery_case": {
                "case_id": "case-001",
                "time_gap_hours": 48.0,
            }
            # recovery_acknowledged absent
        }
        state = {
            "_mode_context": mode_context,
            "_conversation_id": "conv-001",
            "messages": [],
        }
        result_dict = {"success": True}

        updates = await expediente_post_tool_hook(
            tool_name="obtener_estado_expediente",
            result_dict=result_dict,
            state=state,
        )

        assert "mode_context" in updates
        assert updates["mode_context"].get("recovery_acknowledged") is True

    @pytest.mark.asyncio
    async def test_second_turn_with_acknowledged_excludes_recovery(self):
        """
        With recovery_acknowledged=True in mode_context, assemble_system_prompt
        must NOT include the recovery section.
        """
        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

        clear_prompt_cache()

        mode_context = {
            "pending_recovery_case": {
                "case_id": "case-001",
                "time_gap_hours": 48.0,
                "last_activity_at_iso": "2026-04-06T10:00:00+00:00",
            },
            "recovery_acknowledged": True,
        }
        prompt = assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=mode_context,
        )
        # Recovery section must not appear
        assert "Recuperación de sesión" not in prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scalar_result(obj):
    """Build a mock execute result that returns obj from scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result
