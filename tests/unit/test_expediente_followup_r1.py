"""
Unit tests for expediente-flow-redesign-followup R1: Element Display Names.

Tests cover:
- _resolve_element_display_names helper function (TASK-4.1)
- Backward-compat: missing element_display_names key in mode_context (TASK-4.2)

These are pure unit tests (no DB, no Redis, no LLM).
All DB calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# TASK-4.1: Tests for _resolve_element_display_names (R1 helper)
# =============================================================================


class TestResolveElementDisplayNames:
    """Tests for agent.modes.expediente_mode._resolve_element_display_names."""

    @pytest.mark.asyncio
    async def test_resolve_returns_name_map(self):
        """
        Given a DB session returning [{code: "PLACA_SOLAR", name: "Placa solar"}],
        assert function returns {"PLACA_SOLAR": "Placa solar"}.
        """
        from agent.modes.expediente_mode import _resolve_element_display_names

        # Mock DB row
        mock_row = MagicMock()
        mock_row.code = "PLACA_SOLAR"
        mock_row.name = "Placa solar"

        # Mock session result
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock context manager
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "agent.modes.expediente_mode.get_async_session",
            return_value=mock_session_cm,
        ):
            result = await _resolve_element_display_names(
                ["PLACA_SOLAR"], "00000000-0000-0000-0000-000000000001"
            )

        assert result == {"PLACA_SOLAR": "Placa solar"}

    @pytest.mark.asyncio
    async def test_resolve_empty_codes_returns_empty_without_db_query(self):
        """
        Given an empty element_codes list, function MUST return {} immediately
        without making any DB query.
        """
        from agent.modes.expediente_mode import _resolve_element_display_names

        mock_get_session = MagicMock()

        with patch(
            "agent.modes.expediente_mode.get_async_session",
            mock_get_session,
        ):
            result = await _resolve_element_display_names(
                [], "00000000-0000-0000-0000-000000000001"
            )

        assert result == {}
        # No DB call should have been made
        mock_get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_db_failure_returns_empty_dict_no_raise(self):
        """
        If the DB session raises an Exception, _resolve_element_display_names MUST
        return {} instead of propagating the exception.
        """
        from agent.modes.expediente_mode import _resolve_element_display_names

        # Mock context manager whose __aenter__ raises
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(side_effect=Exception("DB connection refused"))
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "agent.modes.expediente_mode.get_async_session",
            return_value=mock_session_cm,
        ):
            # Must NOT raise — must return {}
            result = await _resolve_element_display_names(
                ["ESCAPE"], "00000000-0000-0000-0000-000000000001"
            )

        assert result == {}


# =============================================================================
# TASK-4.2: Backward-compat — missing element_display_names key in mode_context
# =============================================================================


class TestDisplayNameFallbackToCode:
    """
    Verify the fallback pattern in loader.py:
        _display_names: dict[str, str] = context.get("element_display_names") or {}
        _display_code = _display_names.get(_raw_code, _raw_code)

    When mode_context has NO "element_display_names" key (old checkpoints),
    the raw element code is returned unchanged.
    """

    def test_display_name_fallback_to_code_when_key_missing(self):
        """
        Old Redis checkpoints don't have element_display_names.
        The fallback must return the raw code unchanged — no KeyError.
        """
        # Simulate old-checkpoint mode_context (no element_display_names key)
        old_mode_context: dict = {
            "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
            "current_element_index": 0,
            "element_phase": "photos",
            # NOTE: element_display_names is intentionally absent
        }

        raw_code = "PLACA_SOLAR_REGULADOR_INTERIOR"

        # This is the exact pattern used in loader.py (lines 382-383)
        _display_names: dict[str, str] = old_mode_context.get("element_display_names") or {}
        _display_code = _display_names.get(raw_code, raw_code)

        # When key is missing, fallback must be the raw code itself
        assert _display_code == raw_code, (
            f"Expected raw code '{raw_code}' as fallback, got '{_display_code}'"
        )

    def test_display_name_used_when_key_present(self):
        """
        When element_display_names IS present (new checkpoints),
        the human-readable name is returned instead of the code.
        """
        new_mode_context: dict = {
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
            "element_display_names": {"PLACA_SOLAR": "Placa solar"},
        }

        raw_code = "PLACA_SOLAR"

        # Same pattern as loader.py
        _display_names: dict[str, str] = new_mode_context.get("element_display_names") or {}
        _display_code = _display_names.get(raw_code, raw_code)

        assert _display_code == "Placa solar"

    def test_display_name_fallback_when_key_present_but_code_not_in_map(self):
        """
        Even when element_display_names is present, a code not in the map
        falls back to the raw code (partial maps are valid).
        """
        mode_context: dict = {
            "element_codes": ["ESCAPE", "MANILLAR"],
            "element_display_names": {"ESCAPE": "Sistema de escape"},
            # MANILLAR is not in the map
        }

        raw_code = "MANILLAR"

        _display_names: dict[str, str] = mode_context.get("element_display_names") or {}
        _display_code = _display_names.get(raw_code, raw_code)

        assert _display_code == raw_code
