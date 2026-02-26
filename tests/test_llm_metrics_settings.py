"""
Unit tests for _estimate_cost() in agent/services/llm_metrics_persistence.py.

Verifies that pricing is read from get_settings() at call time, not hardcoded.

Run with: pytest tests/test_llm_metrics_settings.py -v
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from agent.services.llm_metrics_persistence import _estimate_cost
from shared.llm_router import LLMMetrics, TaskType, ModelTier, Provider


def _make_metrics(
    provider: Provider = Provider.OPENROUTER,
    input_tokens: int = 1_000_000,
    output_tokens: int = 1_000_000,
) -> LLMMetrics:
    """Build a minimal LLMMetrics object for testing."""
    return LLMMetrics(
        task_type=TaskType.CONVERSATION,
        tier=ModelTier.CLOUD_STANDARD,
        provider=provider,
        model="deepseek/deepseek-chat",
        latency_ms=500,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        success=True,
    )


def _make_settings(input_price: str, output_price: str) -> MagicMock:
    """Return a mock Settings object with the given pricing values."""
    settings_mock = MagicMock()
    settings_mock.TOKEN_PRICE_INPUT = Decimal(input_price)
    settings_mock.TOKEN_PRICE_OUTPUT = Decimal(output_price)
    return settings_mock


# =============================================================================
# S2 — Unit tests
# =============================================================================


@pytest.mark.unit
def test_estimate_cost_uses_settings_values():
    """_estimate_cost() must compute cost from get_settings() pricing, not hardcoded numbers."""
    mocked_settings = _make_settings("1.00", "2.00")

    with patch(
        "agent.services.llm_metrics_persistence.get_settings",
        return_value=mocked_settings,
    ):
        metrics = _make_metrics(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = _estimate_cost(metrics)

    # 1_000_000 * (1.00 / 1_000_000) + 1_000_000 * (2.00 / 1_000_000)
    assert cost == Decimal("3.00"), f"Expected 3.00 but got {cost}"


@pytest.mark.unit
def test_estimate_cost_changes_when_settings_change():
    """Changing mocked settings values must change the returned cost (not cached)."""
    metrics = _make_metrics(input_tokens=1_000_000, output_tokens=1_000_000)

    with patch(
        "agent.services.llm_metrics_persistence.get_settings",
        return_value=_make_settings("1.00", "2.00"),
    ):
        cost_a = _estimate_cost(metrics)

    with patch(
        "agent.services.llm_metrics_persistence.get_settings",
        return_value=_make_settings("0.10", "0.20"),
    ):
        cost_b = _estimate_cost(metrics)

    assert cost_a != cost_b, "Cost must change when settings change"
    assert cost_b == Decimal("0.30"), f"Expected 0.30 but got {cost_b}"


@pytest.mark.unit
def test_estimate_cost_returns_none_for_ollama():
    """_estimate_cost() must return None for non-openrouter providers (no billing)."""
    mocked_settings = _make_settings("1.00", "2.00")

    with patch(
        "agent.services.llm_metrics_persistence.get_settings",
        return_value=mocked_settings,
    ):
        metrics = _make_metrics(
            provider=Provider.OLLAMA,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        cost = _estimate_cost(metrics)

    assert cost is None


@pytest.mark.unit
def test_estimate_cost_zero_tokens_returns_none():
    """_estimate_cost() must return None when both token counts are zero."""
    mocked_settings = _make_settings("1.00", "2.00")

    with patch(
        "agent.services.llm_metrics_persistence.get_settings",
        return_value=mocked_settings,
    ):
        metrics = _make_metrics(input_tokens=0, output_tokens=0)
        cost = _estimate_cost(metrics)

    assert cost is None
