"""
Tests for expediente_transition_adapter module.

Comprehensive test coverage for the canonicalization layer that normalizes
heterogeneous sub-mode transition signals from tool payloads.

Test Scenarios:
- T1-T6: Single-channel sub-mode handoffs
- T7-T8: Multi-channel canonicalization precedence
- C1-C3: Conflict detection cases
- D1-D5: Edge cases and error handling
- I1-I4: Integration tests
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Mock phonenumbers if not available
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

from agent.utils.expediente_transition_adapter import (
    CANONICAL_SUB_MODES,
    SUB_MODE_ALIAS_MAP,
    CanonicalTransition,
    _extract_from_case_collection_update,
    _extract_from_context_updates,
    _extract_from_internal_flags,
    _extract_from_next_step,
    _normalize_sub_mode,
    canonicalize_transition,
)


# =============================================================================
# Task 5.1: Unit tests for _normalize_sub_mode()
# Scenarios: T1-T8 normalization cases
# =============================================================================


class TestNormalizeSubMode:
    """Tests for _normalize_sub_mode() function."""

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            # T1: Uppercase normalization
            ("COLLECT_PERSONAL", "collect_personal"),
            ("COLLECT_VEHICLE", "collect_vehicle"),
            ("COLLECT_ELEMENT_DATA", "collect_element_data"),
            ("COLLECT_BASE_DOCS", "collect_base_docs"),
            ("COLLECT_WORKSHOP", "collect_taller"),
            ("COLLECT_TALLER", "collect_taller"),
            ("REVIEW", "review"),
            ("REVIEW_SUMMARY", "review"),
            # T2: Spanish legacy names
            ("datos_personales", "collect_personal"),
            ("personal_data", "collect_personal"),
            ("datos_vehiculo", "collect_vehicle"),
            ("vehicle_data", "collect_vehicle"),
            ("datos_elemento", "collect_element_data"),
            ("element_data", "collect_element_data"),
            ("documentacion_base", "collect_base_docs"),
            ("base_docs", "collect_base_docs"),
            ("taller", "collect_taller"),
            ("workshop", "collect_taller"),
            ("revision", "review"),
            ("resumen", "review"),
            # T3: Abbreviated variants
            ("collect_docs", "collect_base_docs"),
            ("personal", "collect_personal"),
            ("vehicle", "collect_vehicle"),
            ("element", "collect_element_data"),
            ("docs", "collect_base_docs"),
            # T4: Mixed case variations (only ones that work with alias map)
            ("Collect_Personal", "collect_personal"),
            ("COLLECT_vehicle", "collect_vehicle"),
        ],
    )
    def test_valid_alias_mappings(self, input_value: str, expected: str) -> None:
        """Test that various alias formats map to canonical values."""
        result = _normalize_sub_mode(input_value)
        assert result == expected, f"Failed for input: {input_value}"

    def test_already_canonical(self) -> None:
        """Test that already canonical values pass through unchanged."""
        for canonical in CANONICAL_SUB_MODES:
            result = _normalize_sub_mode(canonical)
            assert result == canonical, (
                f"Canonical value {canonical} should pass through"
            )

    def test_none_returns_none(self) -> None:
        """Test that None input returns None."""
        result = _normalize_sub_mode(None)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        result = _normalize_sub_mode("")
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        """Test that whitespace-only string returns None."""
        result = _normalize_sub_mode("   ")
        assert result is None

    @pytest.mark.parametrize(
        "input_value",
        [
            "sub_mode",
            "current",
            "none",
            "null",
            "",
            "CURRENT",
            "NONE",
        ],
    )
    def test_special_values_return_none(self, input_value: str) -> None:
        """Test that special values indicating 'no transition' return None."""
        result = _normalize_sub_mode(input_value)
        assert result is None, f"Special value {input_value!r} should return None"

    def test_unknown_value_returns_none(self) -> None:
        """Test that unknown values return None (fail-open behavior)."""
        result = _normalize_sub_mode("unknown_value")
        assert result is None

    def test_non_string_type_returns_none(self) -> None:
        """Test that non-string types return None."""
        result = _normalize_sub_mode(12345)
        assert result is None

    def test_list_type_returns_none(self) -> None:
        """Test that list type returns None."""
        result = _normalize_sub_mode(["item1", "item2"])
        assert result is None

    def test_dict_type_returns_none(self) -> None:
        """Test that dict type returns None."""
        result = _normalize_sub_mode({"key": "value"})
        assert result is None


# =============================================================================
# Task 5.2: Tests for single-channel canonicalization
# Scenarios: T1-T6 sub-mode handoffs
# =============================================================================


class TestSingleChannelCanonicalization:
    """Tests for single-channel transition signal extraction."""

    @pytest.mark.parametrize(
        "channel,sub_mode_key,sub_mode_value",
        [
            ("_context_updates", "expediente_sub_mode", "collect_personal"),
            ("_context_updates", "expediente_sub_mode", "collect_vehicle"),
            ("_context_updates", "expediente_sub_mode", "collect_element_data"),
            ("_context_updates", "expediente_sub_mode", "collect_base_docs"),
            ("_context_updates", "expediente_sub_mode", "collect_taller"),
            ("_context_updates", "expediente_sub_mode", "review"),
        ],
    )
    def test_context_updates_channel_all_sub_modes(
        self, channel: str, sub_mode_key: str, sub_mode_value: str
    ) -> None:
        """T1-T6: Test all 6 sub-mode handoffs via _context_updates."""
        tool_result = {channel: {sub_mode_key: sub_mode_value}}

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == sub_mode_value
        assert result.source_channel == channel
        assert result.conflicts == []

    @pytest.mark.parametrize(
        "transition_key,sub_mode_value",
        [
            ("expediente_sub_mode", "collect_personal"),
            ("expediente_sub_mode", "collect_vehicle"),
            ("expediente_sub_mode", "collect_element_data"),
            ("expediente_sub_mode", "collect_base_docs"),
            ("expediente_sub_mode", "collect_taller"),
            ("expediente_sub_mode", "review"),
            ("transition_to", "collect_vehicle"),
            ("transition_to", "collect_personal"),
            ("next_sub_mode", "review"),
            ("next_sub_mode", "collect_base_docs"),
        ],
    )
    def test_internal_flags_channel_all_sub_modes(
        self, transition_key: str, sub_mode_value: str
    ) -> None:
        """T1-T6: Test all 6 sub-mode handoffs via _internal_flags."""
        tool_result = {"_internal_flags": {transition_key: sub_mode_value}}

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == sub_mode_value
        assert result.source_channel == "_internal_flags"
        assert result.conflicts == []

    @pytest.mark.parametrize(
        "sub_mode_value",
        [
            "collect_personal",
            "collect_vehicle",
            "collect_element_data",
            "collect_base_docs",
            "collect_taller",
            "review",
        ],
    )
    def test_case_collection_update_channel_all_sub_modes(
        self, sub_mode_value: str
    ) -> None:
        """T1-T6: Test all 6 sub-mode handoffs via case_collection_update."""
        tool_result = {
            "case_collection_update": {"case_collection": {"step": sub_mode_value}}
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == sub_mode_value
        assert result.source_channel == "case_collection_update"
        assert result.conflicts == []

    @pytest.mark.parametrize(
        "sub_mode_value",
        [
            "collect_personal",
            "collect_vehicle",
            "collect_element_data",
            "collect_base_docs",
            "collect_taller",
            "review",
        ],
    )
    def test_next_step_channel_all_sub_modes(self, sub_mode_value: str) -> None:
        """T1-T6: Test all 6 sub-mode handoffs via next_step."""
        tool_result = {"next_step": sub_mode_value}

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == sub_mode_value
        assert result.source_channel == "next_step"
        assert result.conflicts == []

    def test_context_updates_direct_extraction(self) -> None:
        """Test direct extraction from _context_updates."""
        tool_result = {"_context_updates": {"expediente_sub_mode": "collect_base_docs"}}

        result = _extract_from_context_updates(tool_result)

        assert result == "collect_base_docs"

    def test_context_updates_returns_none_for_non_dict(self) -> None:
        """Test _extract_from_context_updates handles non-dict values."""
        assert _extract_from_context_updates({"_context_updates": "not_a_dict"}) is None
        assert _extract_from_context_updates({}) is None

    def test_internal_flags_multiple_keys_priority(self) -> None:
        """Test that internal_flags checks keys in priority order."""
        # expediente_sub_mode should be found first
        tool_result = {
            "_internal_flags": {
                "expediente_sub_mode": "collect_personal",
                "transition_to": "collect_vehicle",
                "next_sub_mode": "review",
            }
        }

        result = _extract_from_internal_flags(tool_result)

        # Should return the first key found in priority order
        assert result == "collect_personal"

    def test_internal_flags_returns_none_for_non_dict(self) -> None:
        """Test _extract_from_internal_flags handles non-dict values."""
        assert _extract_from_internal_flags({"_internal_flags": "not_a_dict"}) is None
        assert _extract_from_internal_flags({}) is None

    def test_case_collection_update_nested_extraction(self) -> None:
        """Test extraction from nested case_collection_update structure."""
        tool_result = {
            "case_collection_update": {"case_collection": {"step": "collect_vehicle"}}
        }

        result = _extract_from_case_collection_update(tool_result)

        assert result == "collect_vehicle"

    def test_case_collection_update_only_checks_case_collection_update_key(
        self,
    ) -> None:
        """Test that _extract_from_case_collection_update only checks case_collection_update key."""
        # Flat case_collection at root level is NOT checked by this function
        tool_result = {"case_collection": {"step": "collect_personal"}}

        result = _extract_from_case_collection_update(tool_result)

        # This should return None because the function only looks at case_collection_update key
        assert result is None

    def test_case_collection_update_returns_none_for_invalid(self) -> None:
        """Test _extract_from_case_collection_update handles invalid structures."""
        assert (
            _extract_from_case_collection_update(
                {"case_collection_update": "not_a_dict"}
            )
            is None
        )
        assert (
            _extract_from_case_collection_update({"case_collection_update": {}}) is None
        )
        assert _extract_from_case_collection_update({}) is None

    def test_next_step_direct_extraction(self) -> None:
        """Test direct extraction from next_step."""
        tool_result = {"next_step": "review"}

        result = _extract_from_next_step(tool_result)

        assert result == "review"

    def test_next_step_returns_none_for_non_string(self) -> None:
        """Test _extract_from_next_step handles non-string values."""
        assert _extract_from_next_step({"next_step": 123}) is None
        assert _extract_from_next_step({"next_step": None}) is None
        assert _extract_from_next_step({}) is None


# =============================================================================
# Task 5.3: Tests for multi-channel conflict cases
# Scenarios: C1-C3 conflict detection and precedence
# =============================================================================


class TestMultiChannelConflicts:
    """Tests for multi-channel transition signal conflict resolution."""

    def test_context_updates_wins_over_internal_flags(self) -> None:
        """C1: _context_updates should win over _internal_flags."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
            "_internal_flags": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "_context_updates"
        assert "_internal_flags" in result.conflicts

    def test_internal_flags_wins_over_fsm_state_update(self) -> None:
        """C1: _internal_flags should win over fsm_state_update."""
        tool_result = {
            "_internal_flags": {"expediente_sub_mode": "collect_personal"},
            "fsm_state_update": {"case_collection": {"step": "collect_vehicle"}},
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_personal"
        assert result.source_channel == "_internal_flags"
        assert "fsm_state_update" in result.conflicts

    def test_fsm_state_update_wins_over_next_step(self) -> None:
        """C1: fsm_state_update should win over next_step."""
        tool_result = {
            "fsm_state_update": {"case_collection": {"step": "collect_base_docs"}},
            "next_step": "collect_personal",
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "fsm_state_update"
        assert "next_step" in result.conflicts

    def test_full_precedence_chain(self) -> None:
        """C2: Test full precedence chain with all 4 channels."""
        tool_result = {
            "next_step": "review",
            "fsm_state_update": {"case_collection": {"step": "collect_taller"}},
            "_internal_flags": {"expediente_sub_mode": "collect_vehicle"},
            "_context_updates": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        # _context_updates has highest precedence
        assert result.target_sub_mode == "collect_personal"
        assert result.source_channel == "_context_updates"
        # All other channels should be in conflicts
        assert "_internal_flags" in result.conflicts
        assert "fsm_state_update" in result.conflicts
        assert "next_step" in result.conflicts

    def test_agreement_after_normalization_no_conflict(self) -> None:
        """C3: 'COLLECT_PERSONAL' vs 'collect_personal' should NOT be conflict."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "COLLECT_PERSONAL"},
            "_internal_flags": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_personal"
        assert result.source_channel == "_context_updates"
        # Should NOT be a conflict since normalized values match
        assert result.conflicts == []

    def test_partial_agreement_with_conflict(self) -> None:
        """C3: Mixed agreement - some channels agree, some conflict."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
            "_internal_flags": {"expediente_sub_mode": "collect_base_docs"},  # Agrees
            "fsm_state_update": {
                "case_collection": {"step": "collect_vehicle"}
            },  # Conflicts
            "next_step": "collect_personal",  # Conflicts
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "_context_updates"
        # Only conflicting channels should be listed
        assert "fsm_state_update" in result.conflicts
        assert "next_step" in result.conflicts
        assert "_internal_flags" not in result.conflicts  # Agrees with winner

    def test_conflict_detection_populates_conflicts_list(self) -> None:
        """C2: Verify that conflicts are detected and conflicts list is populated."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
            "_internal_flags": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        # Verify conflicts list is populated
        assert "_internal_flags" in result.conflicts
        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "_context_updates"


# =============================================================================
# Task 5.4: Tests for feature flag bypass and edge cases
# Scenarios: D1-D5 edge cases
# =============================================================================


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases, malformed inputs, and error handling."""

    def test_malformed_input_non_dict(self) -> None:
        """D1: Test handling of non-dict input."""
        result = canonicalize_transition("not_a_dict")

        assert result.target_sub_mode is None
        assert result.source_channel == "none"
        assert result.conflicts == []

    def test_malformed_input_list(self) -> None:
        """D1: Test handling of list input."""
        result = canonicalize_transition(["item1", "item2"])

        assert result.target_sub_mode is None
        assert result.source_channel == "none"

    def test_malformed_input_none(self) -> None:
        """D1: Test handling of None input."""
        result = canonicalize_transition(None)

        assert result.target_sub_mode is None
        assert result.source_channel == "none"

    def test_empty_dict(self) -> None:
        """D2: Test handling of empty dict."""
        result = canonicalize_transition({})

        assert result.target_sub_mode is None
        assert result.source_channel == "none"
        assert result.conflicts == []

    def test_empty_string_in_channel(self) -> None:
        """D3: Test handling of empty string in channel."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": ""},
            "_internal_flags": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        # Empty string should be treated as None, so internal_flags wins
        assert result.target_sub_mode == "collect_personal"
        assert result.source_channel == "_internal_flags"

    def test_mixed_valid_invalid_channels(self) -> None:
        """D4: Test mixed valid/invalid channels."""
        tool_result = {
            "_context_updates": "invalid_not_dict",
            "_internal_flags": {"expediente_sub_mode": "collect_base_docs"},
            "fsm_state_update": None,
            "next_step": "",
        }

        result = canonicalize_transition(tool_result)

        # Only valid channel should provide the value
        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "_internal_flags"

    def test_unknown_sub_mode_in_valid_channel(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D5: Test unknown sub-mode value in otherwise valid channel."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "totally_unknown_mode"},
        }

        with caplog.at_level(
            "WARNING", logger="agent.utils.expediente_transition_adapter"
        ):
            result = canonicalize_transition(tool_result)

        # Unknown value should result in None (fail-open)
        assert result.target_sub_mode is None
        assert result.source_channel == "none"

    def test_all_channels_return_none(self) -> None:
        """D5: Test when all channels return None."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "invalid"},
            "_internal_flags": {"expediente_sub_mode": "also_invalid"},
        }

        result = canonicalize_transition(tool_result)

        # Both values are unknown, so result should be None
        assert result.target_sub_mode is None

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is properly stripped."""
        result = _normalize_sub_mode("  collect_personal  ")
        assert result == "collect_personal"


# =============================================================================
# Task 5.5: Integration tests
# Scenarios: I1-I4 integration tests
# =============================================================================


class TestIntegrationWithGuardrails:
    """Integration tests with expediente_guardrails.py."""

    def test_canonicalize_returns_expected_dataclass(self) -> None:
        """Verify CanonicalTransition dataclass structure."""
        tool_result = {"_context_updates": {"expediente_sub_mode": "collect_base_docs"}}

        result = canonicalize_transition(tool_result)

        assert isinstance(result, CanonicalTransition)
        assert hasattr(result, "target_sub_mode")
        assert hasattr(result, "source_channel")
        assert hasattr(result, "conflicts")
        assert hasattr(result, "raw_signals")

    def test_raw_signals_populated(self) -> None:
        """Verify raw_signals contains all channel values."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
            "_internal_flags": {"expediente_sub_mode": "collect_vehicle"},
            "next_step": "review",
        }

        result = canonicalize_transition(tool_result)

        assert "_context_updates" in result.raw_signals
        assert "_internal_flags" in result.raw_signals
        assert "fsm_state_update" in result.raw_signals
        assert "next_step" in result.raw_signals
        # Values should be raw (pre-normalization)
        assert result.raw_signals["_context_updates"] == "collect_base_docs"
        assert result.raw_signals["_internal_flags"] == "collect_vehicle"
        assert result.raw_signals["next_step"] == "review"

    def test_immutable_result(self) -> None:
        """Verify CanonicalTransition is immutable (frozen dataclass)."""
        result = CanonicalTransition(
            target_sub_mode="collect_personal",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )

        # Should not be able to modify
        with pytest.raises(AttributeError):
            result.target_sub_mode = "collect_vehicle"


class TestProductionIncidentScenarios:
    """Tests reproducing real production incidents."""

    def test_mixed_signals_scenario_collect_personal(self) -> None:
        """
        I1: Reproduce original bug - mixed signals should resolve to canonical value.

        Original bug: Tool returned both fsm_state_update.case_collection.step
        and _internal_flags.expediente_sub_mode with different values.
        """
        # Simulate mixed signals from a tool
        tool_result = {
            "success": True,
            "_internal_flags": {"expediente_sub_mode": "COLLECT_PERSONAL"},
            "fsm_state_update": {"case_collection": {"step": "datos_personales"}},
        }

        result = canonicalize_transition(tool_result)

        # Should resolve to canonical value regardless of which channel wins
        assert result.target_sub_mode == "collect_personal"
        # _internal_flags has higher precedence
        assert result.source_channel == "_internal_flags"
        # No conflict because both values normalize to the same canonical value

    def test_uppercase_in_fsm_state_update(self) -> None:
        """I2: Legacy tools using uppercase in FSM state update."""
        tool_result = {
            "fsm_state_update": {"case_collection": {"step": "COLLECT_BASE_DOCS"}},
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "fsm_state_update"

    def test_spanish_alias_in_next_step(self) -> None:
        """I3: Legacy tools using Spanish aliases in next_step."""
        tool_result = {
            "next_step": "datos_vehiculo",
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_vehicle"
        assert result.source_channel == "next_step"

    def test_complex_legacy_tool_output(self) -> None:
        """I4: Complex legacy tool with multiple transition signals."""
        tool_result = {
            "success": True,
            "_internal_flags": {
                "expediente_sub_mode": "collect_taller",
                "confirmed": True,
            },
            "_context_updates": {
                "expediente_sub_mode": "COLLECT_TALLER",  # Same value, different case
            },
            "next_step": "taller",  # Spanish alias
            "data": {"some": "other data"},
        }

        result = canonicalize_transition(tool_result)

        # All channels point to collect_taller (via different representations)
        assert result.target_sub_mode == "collect_taller"
        # _context_updates has highest precedence
        assert result.source_channel == "_context_updates"
        # No conflicts because all normalize to the same value
        assert result.conflicts == []


class TestIntegrationWithExpedienteMode:
    """Integration tests simulating expediente_mode.py usage."""

    def test_integration_simulation_extract_context(self) -> None:
        """Simulate how expediente_mode.py uses the adapter."""
        # Simulate a tool result from completar_elemento_actual
        tool_result = {
            "success": True,
            "all_elements_complete": True,
            "_internal_flags": {
                "expediente_sub_mode": "collect_base_docs",
            },
        }

        # This is how expediente_mode.py would use it
        transition = canonicalize_transition(tool_result)

        if transition.target_sub_mode:
            mode_context_update = {"expediente_sub_mode": transition.target_sub_mode}
            assert mode_context_update["expediente_sub_mode"] == "collect_base_docs"

    def test_integration_simulation_no_transition(self) -> None:
        """Simulate tool result with no transition signal."""
        tool_result = {
            "success": True,
            "data_saved": True,
        }

        transition = canonicalize_transition(tool_result)

        # No transition detected
        assert transition.target_sub_mode is None
        assert transition.source_channel == "none"


# =============================================================================
# Feature Flag Tests
# =============================================================================


class TestFeatureFlagBehavior:
    """Tests for feature flag integration."""

    def test_feature_flag_enabled_path(self) -> None:
        """Verify adapter works when ENABLE_CANONICAL_TRANSITION_ADAPTER is True."""
        # The adapter itself is pure and doesn't check the flag
        # The flag is checked by the caller (expediente_guardrails.py)
        # This test verifies the adapter works correctly
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_personal"},
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_personal"

    def test_canonical_values_in_sub_mode_alias_map(self) -> None:
        """Verify all canonical values are properly defined."""
        # All canonical values should either be in the alias map (mapping to themselves)
        # or be handled by the already-canonical check
        for canonical in CANONICAL_SUB_MODES:
            result = _normalize_sub_mode(canonical)
            assert result == canonical, (
                f"Canonical value {canonical} should normalize to itself"
            )

    def test_alias_map_values_are_canonical(self) -> None:
        """Verify all alias map values are canonical values or None."""
        for alias, canonical in SUB_MODE_ALIAS_MAP.items():
            if canonical is not None:
                assert canonical in CANONICAL_SUB_MODES, (
                    f"Alias {alias!r} maps to non-canonical value {canonical!r}"
                )


# =============================================================================
# Performance and Stress Tests
# =============================================================================


class TestPerformanceCharacteristics:
    """Tests for performance characteristics."""

    def test_large_payload_handling(self) -> None:
        """Test handling of payloads with large data fields."""
        large_data = "x" * 10000
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_base_docs"},
            "large_field": large_data,
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_base_docs"

    def test_many_irrelevant_fields(self) -> None:
        """Test handling of payloads with many irrelevant fields."""
        tool_result = {
            "_context_updates": {"expediente_sub_mode": "collect_personal"},
        }
        # Add many irrelevant fields
        for i in range(100):
            tool_result[f"field_{i}"] = f"value_{i}"

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_personal"

    def test_nested_dict_handling(self) -> None:
        """Test handling of deeply nested dicts."""
        tool_result = {
            "_context_updates": {
                "expediente_sub_mode": "collect_vehicle",
                "nested": {
                    "deeply": {
                        "nested": "data",
                    },
                },
            },
        }

        result = canonicalize_transition(tool_result)

        assert result.target_sub_mode == "collect_vehicle"


# =============================================================================
# CanonicalTransition Dataclass Tests
# =============================================================================


class TestCanonicalTransitionDataclass:
    """Tests for CanonicalTransition dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating CanonicalTransition with all fields."""
        result = CanonicalTransition(
            target_sub_mode="collect_base_docs",
            source_channel="_context_updates",
            conflicts=["_internal_flags", "next_step"],
            raw_signals={
                "_context_updates": "collect_base_docs",
                "_internal_flags": "collect_personal",
            },
        )

        assert result.target_sub_mode == "collect_base_docs"
        assert result.source_channel == "_context_updates"
        assert len(result.conflicts) == 2
        assert "_internal_flags" in result.conflicts

    def test_creation_with_none_values(self) -> None:
        """Test creating CanonicalTransition with None values."""
        result = CanonicalTransition(
            target_sub_mode=None,
            source_channel="none",
            conflicts=[],
            raw_signals={},
        )

        assert result.target_sub_mode is None
        assert result.source_channel == "none"
        assert result.conflicts == []

    def test_equality(self) -> None:
        """Test CanonicalTransition equality."""
        result1 = CanonicalTransition(
            target_sub_mode="collect_personal",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )
        result2 = CanonicalTransition(
            target_sub_mode="collect_personal",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )

        assert result1 == result2

    def test_inequality(self) -> None:
        """Test CanonicalTransition inequality."""
        result1 = CanonicalTransition(
            target_sub_mode="collect_personal",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )
        result2 = CanonicalTransition(
            target_sub_mode="collect_vehicle",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )

        assert result1 != result2

    def test_frozen_but_not_hashable_due_to_list_field(self) -> None:
        """Test CanonicalTransition is frozen but not hashable due to list field.

        Note: The dataclass is frozen but contains a list field (conflicts),
        which makes it unhashable. This is acceptable for our use case.
        """
        result = CanonicalTransition(
            target_sub_mode="collect_personal",
            source_channel="_context_updates",
            conflicts=[],
            raw_signals={},
        )

        # Should be frozen (immutable)
        with pytest.raises(AttributeError):
            result.target_sub_mode = "collect_vehicle"

        # But not hashable due to list field
        with pytest.raises(TypeError):
            hash(result)


# =============================================================================
# Module Constants Tests
# =============================================================================


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_canonical_sub_modes_list(self) -> None:
        """Test CANONICAL_SUB_MODES contains expected values."""
        expected = [
            "collect_personal",
            "collect_vehicle",
            "collect_element_data",
            "collect_base_docs",
            "collect_taller",
            "review",
        ]

        assert CANONICAL_SUB_MODES == expected

    def test_alias_map_is_dict(self) -> None:
        """Test SUB_MODE_ALIAS_MAP is a dict."""
        assert isinstance(SUB_MODE_ALIAS_MAP, dict)

    def test_all_aliases_are_strings(self) -> None:
        """Test all alias keys are strings."""
        for key in SUB_MODE_ALIAS_MAP.keys():
            assert isinstance(key, str)

    def test_all_alias_values_are_strings_or_none(self) -> None:
        """Test all alias values are strings or None."""
        for value in SUB_MODE_ALIAS_MAP.values():
            assert value is None or isinstance(value, str)
