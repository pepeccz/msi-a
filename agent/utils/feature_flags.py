"""
Feature flag utilities for agent hardening.

Provides a clean API for checking hardening flags and collecting
the full set of flag values for telemetry/logging.

All flags are sourced from ``shared.config.get_settings()`` — NEVER
from ``os.getenv()``.

Usage::

    from agent.utils.feature_flags import is_flag_enabled, get_hardening_config

    if is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT"):
        ...  # enforcement logic

    config = get_hardening_config()  # dict for telemetry payload
"""

from __future__ import annotations

from typing import Any

import structlog

from shared.config import get_settings

logger = structlog.get_logger(__name__)

# All hardening feature flag names (must match Settings field names)
_HARDENING_FLAG_NAMES: tuple[str, ...] = (
    "ENABLE_STATE_CONTRACT_ENFORCEMENT",
    "ENABLE_PROMPT_BUDGET_GUARDRAIL",
    "ENABLE_LATENCY_GATING",
    "ENABLE_TURN_TELEMETRY",
)

# All hardening threshold/config names
_HARDENING_CONFIG_NAMES: tuple[str, ...] = (
    "PROMPT_MAX_TOKENS_ESTIMATE",
    "PROMPT_CONTEXT_MAX_CHARS",
    "TURN_LATENCY_P95_THRESHOLD_MS",
    "FALLBACK_RATE_THRESHOLD",
    "ERROR_RATE_THRESHOLD",
)


def is_flag_enabled(flag_name: str) -> bool:
    """
    Check if a hardening feature flag is enabled.

    Reads the flag value from the centralized Settings instance.
    Returns ``False`` for unknown flag names (fail-safe).

    Args:
        flag_name: Name of the flag setting (e.g. ``"ENABLE_STATE_CONTRACT_ENFORCEMENT"``).

    Returns:
        ``True`` if the flag is enabled, ``False`` otherwise.
    """
    settings = get_settings()
    value = getattr(settings, flag_name, None)

    if value is None:
        logger.warning(
            "unknown_hardening_flag",
            flag_name=flag_name,
        )
        return False

    return bool(value)


def get_hardening_config() -> dict[str, Any]:
    """
    Return all hardening flags and thresholds as a dict.

    Useful for:
    - Telemetry payloads (attach to turn events)
    - Debug logging (log active config at startup)
    - Admin panel display (show current hardening state)

    Returns:
        Dict mapping setting names to their current values.

    Example::

        {
            "ENABLE_STATE_CONTRACT_ENFORCEMENT": False,
            "ENABLE_PROMPT_BUDGET_GUARDRAIL": False,
            "ENABLE_LATENCY_GATING": False,
            "ENABLE_TURN_TELEMETRY": False,
            "PROMPT_MAX_TOKENS_ESTIMATE": 4000,
            "PROMPT_CONTEXT_MAX_CHARS": 8000,
            "TURN_LATENCY_P95_THRESHOLD_MS": 3000,
            "FALLBACK_RATE_THRESHOLD": 0.03,
            "ERROR_RATE_THRESHOLD": 0.005,
        }
    """
    settings = get_settings()
    config: dict[str, Any] = {}

    for name in _HARDENING_FLAG_NAMES + _HARDENING_CONFIG_NAMES:
        value = getattr(settings, name, None)
        # Preserve bool type (bool has __float__ in Python, skip it)
        if isinstance(value, bool):
            config[name] = value
        elif isinstance(value, (int, float)):
            config[name] = value
        elif hasattr(value, "__float__"):
            # Convert Decimal to float for JSON serialization
            config[name] = float(value)
        else:
            config[name] = value

    return config
