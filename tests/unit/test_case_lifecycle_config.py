"""
Tests for Case Lifecycle Config Settings — Batch 1 (RED phase)

Spec 5: Lifecycle Timing Settings

Requirements verified:
  - CASE_REMINDER_HOURS exists on Settings with default=20.0
  - CASE_ABANDON_DAYS exists on Settings with default=4.0
  - CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES exists on Settings with default=15
  - CASE_REMINDER_MESSAGE_TEMPLATE exists on Settings with non-empty default
  - Default template contains {name} and {elements} placeholders
  - All four fields are overridable via environment variables
  - CASE_REMINDER_HOURS and CASE_ABANDON_DAYS are float typed
  - CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES is int typed
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch


def _make_settings(**overrides: Any):
    """Return a fresh Settings instance with given env var overrides.

    Bypasses lru_cache and skips .env file to guarantee isolation.
    """
    from shared.config import Settings

    base_env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "CASE_REMINDER_HOURS",
            "CASE_ABANDON_DAYS",
            "CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES",
            "CASE_REMINDER_MESSAGE_TEMPLATE",
        )
    }
    base_env.update({k: str(v) for k, v in overrides.items()})

    with patch.dict(os.environ, base_env, clear=True):
        return Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            REDIS_URL="redis://localhost:6379/0",
            CHATWOOT_API_URL="http://localhost",
            CHATWOOT_API_TOKEN="test",
            CHATWOOT_ACCOUNT_ID="1",
            CHATWOOT_INBOX_ID="1",
            CHATWOOT_WEBHOOK_TOKEN="test",
            ADMIN_JWT_SECRET="a" * 32,
            _env_file=None,
        )


class TestSettingsFieldDeclaration:
    """Settings class must declare all four lifecycle fields."""

    def test_case_reminder_hours_field_exists(self) -> None:
        """CASE_REMINDER_HOURS must be declared in Settings.model_fields."""
        from shared.config import Settings

        assert "CASE_REMINDER_HOURS" in Settings.model_fields

    def test_case_abandon_days_field_exists(self) -> None:
        """CASE_ABANDON_DAYS must be declared in Settings.model_fields."""
        from shared.config import Settings

        assert "CASE_ABANDON_DAYS" in Settings.model_fields

    def test_case_lifecycle_scan_interval_minutes_field_exists(self) -> None:
        """CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES must be declared in Settings.model_fields."""
        from shared.config import Settings

        assert "CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES" in Settings.model_fields

    def test_case_reminder_message_template_field_exists(self) -> None:
        """CASE_REMINDER_MESSAGE_TEMPLATE must be declared in Settings.model_fields."""
        from shared.config import Settings

        assert "CASE_REMINDER_MESSAGE_TEMPLATE" in Settings.model_fields


class TestSettingsDefaults:
    """All four fields must have correct defaults when no env vars are set."""

    def test_case_reminder_hours_default_is_20(self) -> None:
        """CASE_REMINDER_HOURS default must be 20.0."""
        settings = _make_settings()
        assert settings.CASE_REMINDER_HOURS == 20.0, (
            f"Expected 20.0 but got {settings.CASE_REMINDER_HOURS}"
        )

    def test_case_abandon_days_default_is_4(self) -> None:
        """CASE_ABANDON_DAYS default must be 4.0."""
        settings = _make_settings()
        assert settings.CASE_ABANDON_DAYS == 4.0, (
            f"Expected 4.0 but got {settings.CASE_ABANDON_DAYS}"
        )

    def test_case_lifecycle_scan_interval_minutes_default_is_15(self) -> None:
        """CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES default must be 15."""
        settings = _make_settings()
        assert settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES == 15, (
            f"Expected 15 but got {settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES}"
        )

    def test_case_reminder_message_template_default_is_non_empty(self) -> None:
        """CASE_REMINDER_MESSAGE_TEMPLATE default must be non-empty."""
        settings = _make_settings()
        assert settings.CASE_REMINDER_MESSAGE_TEMPLATE, (
            "CASE_REMINDER_MESSAGE_TEMPLATE default must not be empty"
        )

    def test_case_reminder_message_template_contains_name_placeholder(self) -> None:
        """Default template must contain {name} placeholder."""
        settings = _make_settings()
        assert "{name}" in settings.CASE_REMINDER_MESSAGE_TEMPLATE, (
            "Default CASE_REMINDER_MESSAGE_TEMPLATE must contain {name} placeholder"
        )

    def test_case_reminder_message_template_contains_elements_placeholder(self) -> None:
        """Default template must contain {elements} placeholder."""
        settings = _make_settings()
        assert "{elements}" in settings.CASE_REMINDER_MESSAGE_TEMPLATE, (
            "Default CASE_REMINDER_MESSAGE_TEMPLATE must contain {elements} placeholder"
        )


class TestSettingsEnvVarOverrides:
    """All four fields must be overridable via environment variables."""

    def test_case_reminder_hours_env_override(self) -> None:
        """CASE_REMINDER_HOURS must be settable via env var."""
        settings = _make_settings(CASE_REMINDER_HOURS=48.0)
        assert settings.CASE_REMINDER_HOURS == 48.0, (
            f"Expected 48.0 but got {settings.CASE_REMINDER_HOURS}"
        )

    def test_case_abandon_days_env_override(self) -> None:
        """CASE_ABANDON_DAYS must be settable via env var (Spec 5 scenario)."""
        settings = _make_settings(CASE_ABANDON_DAYS=7.0)
        assert settings.CASE_ABANDON_DAYS == 7.0, (
            f"Expected 7.0 but got {settings.CASE_ABANDON_DAYS}"
        )

    def test_case_lifecycle_scan_interval_minutes_env_override(self) -> None:
        """CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES must be settable via env var."""
        settings = _make_settings(CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES=30)
        assert settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES == 30, (
            f"Expected 30 but got {settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES}"
        )

    def test_case_reminder_message_template_env_override(self) -> None:
        """CASE_REMINDER_MESSAGE_TEMPLATE must be settable via env var."""
        custom = "Hola {name}, tu expediente con {elements} sigue pendiente."
        settings = _make_settings(CASE_REMINDER_MESSAGE_TEMPLATE=custom)
        assert settings.CASE_REMINDER_MESSAGE_TEMPLATE == custom, (
            f"Expected '{custom}' but got '{settings.CASE_REMINDER_MESSAGE_TEMPLATE}'"
        )


class TestSettingsTypes:
    """Field types must match the spec."""

    def test_case_reminder_hours_is_float(self) -> None:
        """CASE_REMINDER_HOURS must be float, not int."""
        settings = _make_settings()
        assert isinstance(settings.CASE_REMINDER_HOURS, float), (
            f"Expected float but got {type(settings.CASE_REMINDER_HOURS)}"
        )

    def test_case_abandon_days_is_float(self) -> None:
        """CASE_ABANDON_DAYS must be float, not int."""
        settings = _make_settings()
        assert isinstance(settings.CASE_ABANDON_DAYS, float), (
            f"Expected float but got {type(settings.CASE_ABANDON_DAYS)}"
        )

    def test_case_lifecycle_scan_interval_minutes_is_int(self) -> None:
        """CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES must be int."""
        settings = _make_settings()
        assert isinstance(settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES, int), (
            f"Expected int but got {type(settings.CASE_LIFECYCLE_SCAN_INTERVAL_MINUTES)}"
        )

    def test_case_reminder_message_template_is_str(self) -> None:
        """CASE_REMINDER_MESSAGE_TEMPLATE must be str."""
        settings = _make_settings()
        assert isinstance(settings.CASE_REMINDER_MESSAGE_TEMPLATE, str), (
            f"Expected str but got {type(settings.CASE_REMINDER_MESSAGE_TEMPLATE)}"
        )
