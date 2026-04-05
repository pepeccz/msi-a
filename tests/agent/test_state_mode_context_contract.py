"""
State contract tests for mode_context and state update validation.

Verifies that the canonical key sets in mode_context_keys.py are
comprehensive and that the validation helpers behave correctly under
both enforcement ON and OFF scenarios.

Phase 5, Task 5.1 — agent-harmony-latency-hardening.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from agent.state.mode_context_keys import (
    CANONICAL_MODE_CONTEXT_KEYS,
    CANONICAL_STATE_UPDATE_KEYS,
    validate_mode_context_update,
    validate_state_update,
)


# =============================================================================
# Helpers
# =============================================================================


def _settings_with_enforcement(enforce: bool):
    """Create a mock settings object with the enforcement flag set."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.ENABLE_STATE_CONTRACT_ENFORCEMENT = enforce
    return settings


# =============================================================================
# Task 5.1.1 — CANONICAL_MODE_CONTEXT_KEYS completeness
# =============================================================================


class TestCanonicalModeContextKeysCompleteness:
    """Verify CANONICAL_MODE_CONTEXT_KEYS covers all keys used in modes."""

    def test_contains_typed_dict_keys(self):
        """All keys from ModeContextData TypedDict must be in canonical set."""
        from agent.state.conversation_state import ModeContextData

        typed_dict_keys = set(ModeContextData.__annotations__.keys())
        missing = typed_dict_keys - CANONICAL_MODE_CONTEXT_KEYS
        assert missing == set(), (
            f"ModeContextData keys missing from CANONICAL_MODE_CONTEXT_KEYS: {missing}"
        )

    def test_contains_core_presupuesto_keys(self):
        """Critical presupuesto keys must be in canonical set."""
        presupuesto_keys = {
            "categoria_slug",
            "elemento_tentativo",
            "elemento_confirmado",
            "elementos_confirmados",
            "element_codes",
            "tarifa_calculada",
            "precio_comunicado",
            "imagenes_enviadas",
            "pending_variants",
        }
        missing = presupuesto_keys - CANONICAL_MODE_CONTEXT_KEYS
        assert missing == set(), f"Missing presupuesto keys: {missing}"

    def test_contains_expediente_sub_mode_keys(self):
        """Expediente sub-mode keys must be in canonical set."""
        expediente_keys = {
            "case_id",
            "datos_personales",
            "datos_vehiculo",
            "documentacion_elementos",
            "documentacion_base",
            "datos_taller",
            "taller_propio",
            "expediente_sub_mode",
        }
        missing = expediente_keys - CANONICAL_MODE_CONTEXT_KEYS
        assert missing == set(), f"Missing expediente keys: {missing}"

    def test_contains_tool_flag_keys(self):
        """Tool _internal_flags keys must be in canonical set."""
        tool_flag_keys = {
            "precio_comunicado",
            "imagenes_enviadas",
            "imagenes_envio_intent_creado",
            "pending_variants",
            "elemento_confirmado",
            "element_codes",
            "elementos_confirmados",
            "tarifa_calculada",
            "categoria_slug",
            "_transition_to",
            "_chain_next_mode",
        }
        missing = tool_flag_keys - CANONICAL_MODE_CONTEXT_KEYS
        assert missing == set(), f"Missing tool flag keys: {missing}"

    def test_canonical_set_is_frozenset(self):
        """Canonical set must be immutable."""
        assert isinstance(CANONICAL_MODE_CONTEXT_KEYS, frozenset)

    def test_canonical_set_is_nonempty(self):
        """Canonical set must not be empty."""
        assert len(CANONICAL_MODE_CONTEXT_KEYS) > 0


# =============================================================================
# Task 5.1.2 — CANONICAL_STATE_UPDATE_KEYS completeness
# =============================================================================


class TestCanonicalStateUpdateKeysCompleteness:
    """Verify CANONICAL_STATE_UPDATE_KEYS covers all ConversationState keys."""

    def test_contains_all_conversation_state_keys(self):
        """All ConversationState TypedDict keys must be in canonical set."""
        from agent.state.conversation_state import ConversationState

        state_keys = set(ConversationState.__annotations__.keys())
        missing = state_keys - CANONICAL_STATE_UPDATE_KEYS
        assert missing == set(), (
            f"ConversationState keys missing from CANONICAL_STATE_UPDATE_KEYS: {missing}"
        )

    def test_contains_core_metadata_keys(self):
        """Core metadata keys must be in canonical set."""
        metadata_keys = {
            "conversation_id",
            "user_phone",
            "user_name",
            "user_id",
            "client_type",
        }
        missing = metadata_keys - CANONICAL_STATE_UPDATE_KEYS
        assert missing == set(), f"Missing metadata keys: {missing}"

    def test_contains_mode_management_keys(self):
        """Mode management keys must be in canonical set."""
        mode_keys = {
            "current_mode",
            "previous_mode",
            "mode_history",
            "mode_context",
            "draft_contexts",
        }
        missing = mode_keys - CANONICAL_STATE_UPDATE_KEYS
        assert missing == set(), f"Missing mode keys: {missing}"

    def test_contains_chaining_keys(self):
        """Mode chaining transient keys must be in canonical set."""
        chaining_keys = {"_chain_next_mode", "_is_chained_turn"}
        missing = chaining_keys - CANONICAL_STATE_UPDATE_KEYS
        assert missing == set(), f"Missing chaining keys: {missing}"

    def test_canonical_state_set_is_frozenset(self):
        """Canonical state set must be immutable."""
        assert isinstance(CANONICAL_STATE_UPDATE_KEYS, frozenset)

    def test_canonical_state_set_is_nonempty(self):
        """Canonical state set must not be empty."""
        assert len(CANONICAL_STATE_UPDATE_KEYS) > 0


# =============================================================================
# Task 5.1.3 — validate_mode_context_update() with valid updates
# =============================================================================


class TestValidateModeContextUpdateValid:
    """Test that validate_mode_context_update passes valid updates."""

    @patch("shared.config.get_settings")
    def test_valid_update_passes_enforcement_off(self, mock_get_settings):
        """Valid updates pass with no warnings when enforcement is OFF."""
        mock_get_settings.return_value = _settings_with_enforcement(False)

        updates = {
            "categoria_slug": "motos-part",
            "precio_comunicado": True,
            "elementos_confirmados": [{"code": "ESCAPE"}],
        }
        cleaned, warnings = validate_mode_context_update(updates, "PRESUPUESTO_MODE")

        assert cleaned == updates
        assert warnings == []

    @patch("shared.config.get_settings")
    def test_valid_update_passes_enforcement_on(self, mock_get_settings):
        """Valid updates pass with no warnings when enforcement is ON."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates = {
            "case_id": "some-uuid",
            "datos_personales": {"nombre": "Test"},
        }
        cleaned, warnings = validate_mode_context_update(updates, "EXPEDIENTE_MODE")

        assert cleaned == updates
        assert warnings == []

    @patch("shared.config.get_settings")
    def test_empty_update_passes(self, mock_get_settings):
        """Empty update dict should pass with no warnings."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        cleaned, warnings = validate_mode_context_update({}, "CONSULTA_MODE")

        assert cleaned == {}
        assert warnings == []


# =============================================================================
# Task 5.1.4 — validate_mode_context_update() warns on unknown keys
# =============================================================================


class TestValidateModeContextUpdateUnknownKeys:
    """Test that validate_mode_context_update handles unknown keys correctly."""

    @patch("shared.config.get_settings")
    def test_unknown_keys_stripped_when_enforcement_on(self, mock_get_settings):
        """Unknown keys are stripped and warned when enforcement is ON."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates = {
            "categoria_slug": "motos-part",
            "totally_bogus_key": "should be removed",
            "another_unknown": 42,
        }
        cleaned, warnings = validate_mode_context_update(updates, "PRESUPUESTO_MODE")

        assert "totally_bogus_key" not in cleaned
        assert "another_unknown" not in cleaned
        assert "categoria_slug" in cleaned
        assert len(warnings) == 2
        assert any("totally_bogus_key" in w for w in warnings)
        assert any("another_unknown" in w for w in warnings)

    @patch("shared.config.get_settings")
    def test_unknown_keys_preserved_when_enforcement_off(self, mock_get_settings):
        """Unknown keys are kept but warned when enforcement is OFF."""
        mock_get_settings.return_value = _settings_with_enforcement(False)

        updates = {
            "categoria_slug": "motos-part",
            "totally_bogus_key": "should be kept",
        }
        cleaned, warnings = validate_mode_context_update(updates, "PRESUPUESTO_MODE")

        assert "totally_bogus_key" in cleaned
        assert "categoria_slug" in cleaned
        assert len(warnings) == 1
        assert "totally_bogus_key" in warnings[0]

    @patch("shared.config.get_settings")
    def test_warning_messages_include_mode_name(self, mock_get_settings):
        """Warning messages should include the mode name for context."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates = {"nonexistent_key": "value"}
        _, warnings = validate_mode_context_update(updates, "CONSULTA_MODE")

        assert len(warnings) == 1
        assert "CONSULTA_MODE" in warnings[0]
        assert "nonexistent_key" in warnings[0]


# =============================================================================
# Task 5.1.5 — validate_state_update() with valid updates
# =============================================================================


class TestValidateStateUpdateValid:
    """Test that validate_state_update passes valid updates."""

    @patch("shared.config.get_settings")
    def test_valid_state_update_passes(self, mock_get_settings):
        """Valid state updates pass with no warnings."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates: dict[str, Any] = {
            "current_mode": "PRESUPUESTO_MODE",
            "ai_response": "Test response",
            "mode_context": {"categoria_slug": "motos-part"},
        }
        cleaned, warnings = validate_state_update(updates, "PRESUPUESTO_MODE")

        assert cleaned == updates
        assert warnings == []

    @patch("shared.config.get_settings")
    def test_transition_keys_pass(self, mock_get_settings):
        """Mode transition keys (current_mode, previous_mode, etc.) pass."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates: dict[str, Any] = {
            "current_mode": "EXPEDIENTE_MODE",
            "previous_mode": "PRESUPUESTO_MODE",
            "mode_history": ["PRESUPUESTO_MODE"],
            "retry_state": {"retry_count": 0},
        }
        cleaned, warnings = validate_state_update(updates, "EXPEDIENTE_MODE")

        assert cleaned == updates
        assert warnings == []


# =============================================================================
# Task 5.1.6 — validate_state_update() warns on unknown keys
# =============================================================================


class TestValidateStateUpdateUnknownKeys:
    """Test that validate_state_update handles unknown keys correctly."""

    @patch("shared.config.get_settings")
    def test_unknown_state_keys_stripped_when_enforcement_on(self, mock_get_settings):
        """Unknown state keys are stripped when enforcement is ON."""
        mock_get_settings.return_value = _settings_with_enforcement(True)

        updates: dict[str, Any] = {
            "current_mode": "PRESUPUESTO_MODE",
            "weird_key_that_doesnt_exist": True,
        }
        cleaned, warnings = validate_state_update(updates, "PRESUPUESTO_MODE")

        assert "weird_key_that_doesnt_exist" not in cleaned
        assert "current_mode" in cleaned
        assert len(warnings) == 1

    @patch("shared.config.get_settings")
    def test_unknown_state_keys_preserved_when_enforcement_off(self, mock_get_settings):
        """Unknown state keys are kept when enforcement is OFF."""
        mock_get_settings.return_value = _settings_with_enforcement(False)

        updates: dict[str, Any] = {
            "current_mode": "PRESUPUESTO_MODE",
            "weird_key_that_doesnt_exist": True,
        }
        cleaned, warnings = validate_state_update(updates, "PRESUPUESTO_MODE")

        assert "weird_key_that_doesnt_exist" in cleaned
        assert len(warnings) == 1
