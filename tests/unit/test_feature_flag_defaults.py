"""
Tests for Feature Flag Defaults — Fix Round B, Task B2 (RED phase)

Spec 2: Guardrail Flags Have Explicit False Defaults in Settings

Requirements verified:
  - EXPEDIENTE_V2_ENABLED exists on Settings with default=False
  - ENABLE_STATE_CONTRACT_ENFORCEMENT exists on Settings with default=False
  - ENABLE_SAME_TURN_TRANSITION_CLOSURE exists on Settings with default=False
  - get_settings() returns False for all three with no .env overrides
  - is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT") returns False by default
  - is_flag_enabled("EXPEDIENTE_V2_ENABLED") returns False by default
  - is_flag_enabled("ENABLE_SAME_TURN_TRANSITION_CLOSURE") returns False by default
  - is_flag_enabled() returns False for unknown flag names (existing behaviour)
  - get_hardening_config() includes ENABLE_STATE_CONTRACT_ENFORCEMENT key

Design reference: AD-1 (guardrail flags) in design.md
Spec reference:   Spec 2 in spec.md
"""

from __future__ import annotations

import os
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-import stubs — avoid import-time failures for heavy optional deps
# ---------------------------------------------------------------------------


def _stub_module(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Stub PIL (not installed in test env)
for _mod in ["PIL", "PIL.Image", "PIL.ImageFile"]:
    if _mod not in sys.modules:
        _stub_module(_mod)

# Stub structlog
if "structlog" not in sys.modules:
    _sl = _stub_module("structlog")
    _sl.get_logger = lambda *a, **kw: MagicMock()

# Stub redis
if "redis" not in sys.modules:
    _stub_module("redis")
if "redis.asyncio" not in sys.modules:
    _stub_module("redis.asyncio")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings_no_env(**overrides: Any):
    """Return a fresh Settings instance with no .env file and given overrides."""
    # Clear env vars that would interfere
    env_clean = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "EXPEDIENTE_V2_ENABLED",
            "ENABLE_STATE_CONTRACT_ENFORCEMENT",
            "ENABLE_SAME_TURN_TRANSITION_CLOSURE",
        )
    }
    env_clean.update({k: str(v) for k, v in overrides.items()})

    from shared.config import Settings

    # Build Settings directly (bypass get_settings() lru_cache)
    with patch.dict(os.environ, env_clean, clear=True):
        return Settings(
            # Provide required fields that have no default
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            REDIS_URL="redis://localhost:6379/0",
            CHATWOOT_API_URL="http://localhost",
            CHATWOOT_API_TOKEN="test",
            CHATWOOT_ACCOUNT_ID="1",
            CHATWOOT_INBOX_ID="1",
            CHATWOOT_TEAM_GROUP_ID="1",
            CHATWOOT_WEBHOOK_TOKEN="test",
            ADMIN_JWT_SECRET="a" * 32,
            _env_file=None,  # Don't load .env file
        )


# ---------------------------------------------------------------------------
# Test: Settings declares the three flags with default=False
# ---------------------------------------------------------------------------


class TestSettingsFieldDeclaration:
    """Settings class must declare all three flags with default=False."""

    def test_settings_has_expediente_v2_enabled_field(self) -> None:
        """EXPEDIENTE_V2_ENABLED must be a declared field on Settings."""
        from shared.config import Settings

        assert "EXPEDIENTE_V2_ENABLED" in Settings.model_fields, (
            "EXPEDIENTE_V2_ENABLED is missing from Settings.model_fields — "
            "add it to shared/config.py with default=False"
        )

    def test_settings_has_enable_state_contract_enforcement_field(self) -> None:
        """ENABLE_STATE_CONTRACT_ENFORCEMENT must be a declared field on Settings."""
        from shared.config import Settings

        assert "ENABLE_STATE_CONTRACT_ENFORCEMENT" in Settings.model_fields, (
            "ENABLE_STATE_CONTRACT_ENFORCEMENT is missing from Settings.model_fields — "
            "add it to shared/config.py with default=False"
        )

    def test_settings_has_enable_same_turn_transition_closure_field(self) -> None:
        """ENABLE_SAME_TURN_TRANSITION_CLOSURE must be a declared field on Settings."""
        from shared.config import Settings

        assert "ENABLE_SAME_TURN_TRANSITION_CLOSURE" in Settings.model_fields, (
            "ENABLE_SAME_TURN_TRANSITION_CLOSURE is missing from Settings.model_fields — "
            "add it to shared/config.py with default=False"
        )

    def test_expediente_v2_enabled_default_is_false(self) -> None:
        """EXPEDIENTE_V2_ENABLED default must be False (not True)."""
        from shared.config import Settings

        field_info = Settings.model_fields["EXPEDIENTE_V2_ENABLED"]
        assert field_info.default is False, (
            f"EXPEDIENTE_V2_ENABLED default is {field_info.default!r} — expected False. "
            "Guardrails must be OFF by default (safe-off principle)."
        )

    def test_enable_state_contract_enforcement_default_is_false(self) -> None:
        """ENABLE_STATE_CONTRACT_ENFORCEMENT default must be False."""
        from shared.config import Settings

        field_info = Settings.model_fields["ENABLE_STATE_CONTRACT_ENFORCEMENT"]
        assert field_info.default is False, (
            f"ENABLE_STATE_CONTRACT_ENFORCEMENT default is {field_info.default!r} — "
            "expected False."
        )

    def test_enable_same_turn_transition_closure_default_is_false(self) -> None:
        """ENABLE_SAME_TURN_TRANSITION_CLOSURE default must be False."""
        from shared.config import Settings

        field_info = Settings.model_fields["ENABLE_SAME_TURN_TRANSITION_CLOSURE"]
        assert field_info.default is False, (
            f"ENABLE_SAME_TURN_TRANSITION_CLOSURE default is {field_info.default!r} — "
            "expected False."
        )


# ---------------------------------------------------------------------------
# Test: is_flag_enabled() uses Settings — returns False for all three by default
# ---------------------------------------------------------------------------


class TestIsFlagEnabledReturnsDefault:
    """is_flag_enabled() must return False for all three flags when Settings is default."""

    def _mock_settings(self, **flag_values: bool):
        """Return a MagicMock Settings instance with given flag values."""
        mock = MagicMock()
        # Set defaults for all known flags to False
        defaults = {
            "EXPEDIENTE_V2_ENABLED": False,
            "ENABLE_STATE_CONTRACT_ENFORCEMENT": False,
            "ENABLE_SAME_TURN_TRANSITION_CLOSURE": False,
            "ENABLE_PROMPT_BUDGET_GUARDRAIL": False,
            "ENABLE_LATENCY_GATING": False,
            "ENABLE_TURN_TELEMETRY": False,
        }
        defaults.update(flag_values)
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_is_flag_enabled_expediente_v2_returns_false_by_default(self) -> None:
        """is_flag_enabled('EXPEDIENTE_V2_ENABLED') must return False when not set."""
        with patch(
            "agent.utils.feature_flags.get_settings", return_value=self._mock_settings()
        ):
            from agent.utils.feature_flags import is_flag_enabled

            result = is_flag_enabled("EXPEDIENTE_V2_ENABLED")
        assert result is False, (
            "is_flag_enabled('EXPEDIENTE_V2_ENABLED') returned True — "
            "expected False (safe-off default)."
        )

    def test_is_flag_enabled_state_contract_returns_false_by_default(self) -> None:
        """is_flag_enabled('ENABLE_STATE_CONTRACT_ENFORCEMENT') must return False when not set."""
        with patch(
            "agent.utils.feature_flags.get_settings", return_value=self._mock_settings()
        ):
            from agent.utils.feature_flags import is_flag_enabled

            result = is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT")
        assert result is False

    def test_is_flag_enabled_same_turn_returns_false_by_default(self) -> None:
        """is_flag_enabled('ENABLE_SAME_TURN_TRANSITION_CLOSURE') must return False when not set."""
        with patch(
            "agent.utils.feature_flags.get_settings", return_value=self._mock_settings()
        ):
            from agent.utils.feature_flags import is_flag_enabled

            result = is_flag_enabled("ENABLE_SAME_TURN_TRANSITION_CLOSURE")
        assert result is False

    def test_is_flag_enabled_unknown_flag_returns_false(self) -> None:
        """is_flag_enabled() must return False for unknown flag names (existing safety net).

        We use a SimpleNamespace instead of MagicMock because MagicMock
        auto-creates attributes on access (returning truthy MagicMock objects),
        which defeats the getattr(..., None) guard in is_flag_enabled().
        """
        from types import SimpleNamespace

        ns = SimpleNamespace(
            EXPEDIENTE_V2_ENABLED=False,
            ENABLE_STATE_CONTRACT_ENFORCEMENT=False,
            ENABLE_SAME_TURN_TRANSITION_CLOSURE=False,
        )
        with patch("agent.utils.feature_flags.get_settings", return_value=ns):
            from agent.utils.feature_flags import is_flag_enabled

            result = is_flag_enabled("NONEXISTENT_FLAG_XYZ")
        assert result is False

    def test_is_flag_enabled_returns_true_when_explicitly_enabled(self) -> None:
        """Triangulation: is_flag_enabled() returns True when flag IS enabled."""
        with patch(
            "agent.utils.feature_flags.get_settings",
            return_value=self._mock_settings(EXPEDIENTE_V2_ENABLED=True),
        ):
            from agent.utils.feature_flags import is_flag_enabled

            result = is_flag_enabled("EXPEDIENTE_V2_ENABLED")
        assert result is True, (
            "is_flag_enabled() must return True when the flag IS set — "
            "this triangulates that the logic actually reads the setting."
        )


# ---------------------------------------------------------------------------
# Test: get_hardening_config() includes ENABLE_STATE_CONTRACT_ENFORCEMENT
# ---------------------------------------------------------------------------


class TestGetHardeningConfigIncludes:
    """get_hardening_config() must expose ENABLE_STATE_CONTRACT_ENFORCEMENT for telemetry."""

    def test_get_hardening_config_includes_state_contract_key(self) -> None:
        """ENABLE_STATE_CONTRACT_ENFORCEMENT must appear in the hardening config dict."""
        mock_settings = MagicMock()
        mock_settings.ENABLE_STATE_CONTRACT_ENFORCEMENT = False
        mock_settings.ENABLE_PROMPT_BUDGET_GUARDRAIL = False
        mock_settings.ENABLE_LATENCY_GATING = False
        mock_settings.ENABLE_TURN_TELEMETRY = False
        # Numeric thresholds
        for attr in (
            "PROMPT_MAX_TOKENS_ESTIMATE",
            "PROMPT_CONTEXT_MAX_CHARS",
            "TURN_LATENCY_P95_THRESHOLD_MS",
            "FALLBACK_RATE_THRESHOLD",
            "ERROR_RATE_THRESHOLD",
        ):
            setattr(mock_settings, attr, 0)

        with patch(
            "agent.utils.feature_flags.get_settings", return_value=mock_settings
        ):
            from agent.utils.feature_flags import get_hardening_config

            config = get_hardening_config()

        assert "ENABLE_STATE_CONTRACT_ENFORCEMENT" in config, (
            "ENABLE_STATE_CONTRACT_ENFORCEMENT missing from get_hardening_config() output — "
            "needed for telemetry payloads."
        )
        assert config["ENABLE_STATE_CONTRACT_ENFORCEMENT"] is False

    def test_get_hardening_config_returns_dict(self) -> None:
        """get_hardening_config() must return a dict."""
        mock_settings = MagicMock()
        for attr in (
            "ENABLE_STATE_CONTRACT_ENFORCEMENT",
            "ENABLE_PROMPT_BUDGET_GUARDRAIL",
            "ENABLE_LATENCY_GATING",
            "ENABLE_TURN_TELEMETRY",
        ):
            setattr(mock_settings, attr, False)
        for attr in (
            "PROMPT_MAX_TOKENS_ESTIMATE",
            "PROMPT_CONTEXT_MAX_CHARS",
            "TURN_LATENCY_P95_THRESHOLD_MS",
            "FALLBACK_RATE_THRESHOLD",
            "ERROR_RATE_THRESHOLD",
        ):
            setattr(mock_settings, attr, 0)

        with patch(
            "agent.utils.feature_flags.get_settings", return_value=mock_settings
        ):
            from agent.utils.feature_flags import get_hardening_config

            config = get_hardening_config()

        assert isinstance(config, dict)
