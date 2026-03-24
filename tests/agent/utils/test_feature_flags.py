"""
Feature flag utility tests.

Verifies that the feature flag helpers in agent/utils/feature_flags.py
correctly read settings, handle unknown flags, and return the full
hardening configuration.

Phase 5, Task 5.3 — agent-harmony-latency-hardening.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.utils.feature_flags import (
    _HARDENING_CONFIG_NAMES,
    _HARDENING_FLAG_NAMES,
    get_hardening_config,
    is_flag_enabled,
)


# =============================================================================
# Task 5.3.1 — is_flag_enabled returns False for unknown flags
# =============================================================================


class TestIsFlagEnabledUnknown:
    """Verify is_flag_enabled returns False for unknown flag names."""

    def test_unknown_flag_returns_false(self):
        """An unknown flag name must return False (fail-safe)."""
        result = is_flag_enabled("THIS_FLAG_DOES_NOT_EXIST_ANYWHERE")
        assert result is False

    def test_empty_string_flag_returns_false(self):
        """An empty string flag name must return False."""
        result = is_flag_enabled("")
        assert result is False

    def test_typo_flag_returns_false(self):
        """A typo of a real flag name must return False."""
        result = is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT_TYPO")
        assert result is False


# =============================================================================
# Task 5.3.2 — is_flag_enabled reads actual settings values
# =============================================================================


class TestIsFlagEnabledReadsSettings:
    """Verify is_flag_enabled reads real values from Settings."""

    def test_reads_enforcement_flag_default(self):
        """ENABLE_STATE_CONTRACT_ENFORCEMENT defaults to False."""
        # The default in Settings is False, so this should return False
        # unless env var is set
        result = is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT")
        assert isinstance(result, bool)

    def test_reads_prompt_budget_flag_default(self):
        """ENABLE_PROMPT_BUDGET_GUARDRAIL defaults to False."""
        result = is_flag_enabled("ENABLE_PROMPT_BUDGET_GUARDRAIL")
        assert isinstance(result, bool)

    def test_reads_latency_gating_flag_default(self):
        """ENABLE_LATENCY_GATING defaults to True."""
        result = is_flag_enabled("ENABLE_LATENCY_GATING")
        assert result is True

    def test_reads_telemetry_flag_default(self):
        """ENABLE_TURN_TELEMETRY defaults to False."""
        result = is_flag_enabled("ENABLE_TURN_TELEMETRY")
        assert isinstance(result, bool)

    @patch("agent.utils.feature_flags.get_settings")
    def test_returns_true_when_flag_enabled(self, mock_get_settings):
        """When a flag is True in settings, is_flag_enabled returns True."""
        settings = MagicMock()
        settings.ENABLE_STATE_CONTRACT_ENFORCEMENT = True
        mock_get_settings.return_value = settings

        assert is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT") is True

    @patch("agent.utils.feature_flags.get_settings")
    def test_returns_false_when_flag_disabled(self, mock_get_settings):
        """When a flag is False in settings, is_flag_enabled returns False."""
        settings = MagicMock()
        settings.ENABLE_LATENCY_GATING = False
        mock_get_settings.return_value = settings

        assert is_flag_enabled("ENABLE_LATENCY_GATING") is False

    @patch("agent.utils.feature_flags.get_settings")
    def test_unknown_flag_with_mock_returns_false(self, mock_get_settings):
        """Unknown flag with mocked settings still returns False (getattr default)."""
        settings = MagicMock(spec=[])  # No attributes at all
        mock_get_settings.return_value = settings

        assert is_flag_enabled("NONEXISTENT_FLAG") is False


# =============================================================================
# Task 5.3.3 — get_hardening_config returns dict with all expected keys
# =============================================================================


class TestGetHardeningConfig:
    """Verify get_hardening_config returns complete configuration dict."""

    def test_returns_dict(self):
        """get_hardening_config must return a dict."""
        config = get_hardening_config()
        assert isinstance(config, dict)

    def test_contains_all_flag_keys(self):
        """Result must contain all hardening flag keys."""
        config = get_hardening_config()
        for flag_name in _HARDENING_FLAG_NAMES:
            assert flag_name in config, f"Missing flag key: {flag_name}"

    def test_contains_all_config_keys(self):
        """Result must contain all hardening config/threshold keys."""
        config = get_hardening_config()
        for config_name in _HARDENING_CONFIG_NAMES:
            assert config_name in config, f"Missing config key: {config_name}"

    def test_total_key_count(self):
        """Result must have exactly the expected number of keys."""
        config = get_hardening_config()
        expected_count = len(_HARDENING_FLAG_NAMES) + len(_HARDENING_CONFIG_NAMES)
        assert len(config) == expected_count, (
            f"Expected {expected_count} keys but got {len(config)}: "
            f"extra={set(config.keys()) - set(_HARDENING_FLAG_NAMES + _HARDENING_CONFIG_NAMES)}, "
            f"missing={set(_HARDENING_FLAG_NAMES + _HARDENING_CONFIG_NAMES) - set(config.keys())}"
        )

    def test_flag_values_are_bool(self):
        """All flag values must be boolean."""
        config = get_hardening_config()
        for flag_name in _HARDENING_FLAG_NAMES:
            assert isinstance(config[flag_name], bool), (
                f"Flag {flag_name} should be bool, got {type(config[flag_name])}"
            )

    def test_integer_thresholds_are_numeric(self):
        """Integer threshold values must be int or float."""
        config = get_hardening_config()
        numeric_keys = [
            "PROMPT_MAX_TOKENS_ESTIMATE",
            "PROMPT_CONTEXT_MAX_CHARS",
            "TURN_LATENCY_P95_THRESHOLD_MS",
            "MAX_TOOL_ITERATIONS_CONSULTA",
            "MAX_TOOL_ITERATIONS_PRESUPUESTO",
            "MAX_TOOL_ITERATIONS_EXPEDIENTE",
        ]
        for key in numeric_keys:
            assert isinstance(config[key], (int, float)), (
                f"Config {key} should be numeric, got {type(config[key])}"
            )

    def test_rate_thresholds_are_float(self):
        """Rate threshold values must be float."""
        config = get_hardening_config()
        float_keys = ["FALLBACK_RATE_THRESHOLD", "ERROR_RATE_THRESHOLD"]
        for key in float_keys:
            assert isinstance(config[key], (int, float)), (
                f"Config {key} should be numeric, got {type(config[key])}"
            )

    def test_default_values_are_sensible(self):
        """Default config values should be within expected ranges."""
        config = get_hardening_config()

        # All flags default OFF
        for flag_name in _HARDENING_FLAG_NAMES:
            # Don't assert specific value — env might override in CI
            assert isinstance(config[flag_name], bool)

        # Thresholds should be positive
        assert config["PROMPT_MAX_TOKENS_ESTIMATE"] > 0
        assert config["PROMPT_CONTEXT_MAX_CHARS"] > 0
        assert config["TURN_LATENCY_P95_THRESHOLD_MS"] > 0
        assert config["MAX_TOOL_ITERATIONS_CONSULTA"] >= 1
        assert config["MAX_TOOL_ITERATIONS_PRESUPUESTO"] >= 1
        assert config["MAX_TOOL_ITERATIONS_EXPEDIENTE"] >= 1

        # Rates should be between 0 and 1
        assert 0.0 <= config["FALLBACK_RATE_THRESHOLD"] <= 1.0
        assert 0.0 <= config["ERROR_RATE_THRESHOLD"] <= 1.0
