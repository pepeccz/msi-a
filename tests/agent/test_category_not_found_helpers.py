"""
Tests for category-not-found helpers in fallback_handler and element_tools.

Tasks 5.2, 5.3, 5.4, 5.5 — fix-category-routing-and-retry-contamination

Coverage:
- _is_category_not_found_error() — correct detection
- get_validation_reprompt() — backward compat + new category-not-found branch
- identificar_y_resolver_elementos() — enriched category_not_found error (async)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.fallback.fallback_handler import (
    FallbackHandler,
    FallbackAction,
    RetryPolicy,
    _is_category_not_found_error,
)
from agent.state.conversation_state import create_empty_retry_state


# =============================================================================
# HELPERS
# =============================================================================

def make_retry_state(retry_count: int = 1, consecutive_errors: int = 0) -> dict:
    """Build a minimal retry state dict for testing."""
    base = dict(create_empty_retry_state())
    base["retry_count"] = retry_count
    base["consecutive_errors"] = consecutive_errors
    return base


def make_handler() -> FallbackHandler:
    """Create a FallbackHandler with a test policy for non-escalation testing."""
    handler = FallbackHandler()
    handler.policies["TEST_MODE"] = RetryPolicy(
        mode="TEST_MODE",
        max_retries=4,
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="progressive",
        msg_retry_1="Retry 1 message",
        msg_retry_2="Retry 2 message",
        msg_limit="Limit reached message",
    )
    return handler


# =============================================================================
# Task 5.2 — Test _is_category_not_found_error
# =============================================================================

class TestIsCategoryNotFoundError:
    """Unit tests for the _is_category_not_found_error helper."""

    def test_is_category_not_found_true(self):
        """Returns True when error == 'category_not_found' and key present."""
        error_dict = {
            "error": "category_not_found",
            "available_categories": [{"slug": "motos-part", "name": "Motos"}],
        }
        assert _is_category_not_found_error(error_dict) is True

    def test_is_category_not_found_true_empty_list(self):
        """Returns True even when available_categories list is empty."""
        error_dict = {
            "error": "category_not_found",
            "available_categories": [],
        }
        assert _is_category_not_found_error(error_dict) is True

    def test_is_category_not_found_false_wrong_error_key(self):
        """Returns False when error key is different."""
        error_dict = {
            "error": "other_error",
            "available_categories": [],
        }
        assert _is_category_not_found_error(error_dict) is False

    def test_is_category_not_found_false_missing_available_categories_key(self):
        """Returns False when available_categories key is absent."""
        error_dict = {"error": "category_not_found"}  # missing key
        assert _is_category_not_found_error(error_dict) is False

    def test_is_category_not_found_false_non_dict_string(self):
        """Returns False for plain string input."""
        assert _is_category_not_found_error("not a dict") is False

    def test_is_category_not_found_false_none(self):
        """Returns False for None input."""
        assert _is_category_not_found_error(None) is False

    def test_is_category_not_found_false_empty_dict(self):
        """Returns False for empty dict."""
        assert _is_category_not_found_error({}) is False

    def test_is_category_not_found_false_integer(self):
        """Returns False for integer input."""
        assert _is_category_not_found_error(42) is False

    def test_is_category_not_found_false_list(self):
        """Returns False for list input."""
        assert _is_category_not_found_error([{"error": "category_not_found"}]) is False


# =============================================================================
# Task 5.3 — Test get_validation_reprompt backward compat + new behavior
# =============================================================================

class TestGetValidationReprompt:
    """Tests for get_validation_reprompt() — backward compat and category_not_found branch."""

    def test_reprompt_without_error_dict_returns_string(self):
        """Calling without error_dict returns existing progressive message (backward compat)."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)

        result = handler.get_validation_reprompt(retry_state, policy)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_reprompt_without_error_dict_none_explicit(self):
        """Passing error_dict=None explicitly is same as omitting it."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)

        result_default = handler.get_validation_reprompt(retry_state, policy)
        result_none = handler.get_validation_reprompt(retry_state, policy, error_dict=None)

        assert result_default == result_none

    def test_reprompt_first_retry_generic_message(self):
        """First retry (count=1) without category error returns generic message."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)

        result = handler.get_validation_reprompt(retry_state, policy)

        # Should be something instructive, not empty
        assert len(result) > 5

    def test_reprompt_with_category_not_found_includes_wrong_slug(self):
        """Message includes the wrong slug that was used."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)
        error_dict = {
            "error": "category_not_found",
            "categoria_usada": "tuning-prof",
            "available_categories": [
                {"slug": "aseicars-prof", "name": "Autocaravanas prof"},
            ],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        assert "tuning-prof" in result

    def test_reprompt_with_category_not_found_includes_available_slug(self):
        """Message includes available category slugs."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)
        error_dict = {
            "error": "category_not_found",
            "categoria_usada": "tuning-prof",
            "available_categories": [
                {"slug": "aseicars-prof", "name": "Autocaravanas prof"},
            ],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        assert "aseicars-prof" in result

    def test_reprompt_with_category_not_found_mentions_listar_categorias(self):
        """Message always advises to call listar_categorias()."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)
        error_dict = {
            "error": "category_not_found",
            "categoria_usada": "bad-slug",
            "available_categories": [
                {"slug": "motos-part", "name": "Motos part"},
            ],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        assert "listar_categorias" in result

    def test_reprompt_with_category_not_found_empty_available_categories(self):
        """When available_categories is empty, still returns actionable message."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)
        error_dict = {
            "error": "category_not_found",
            "categoria_usada": "bad-slug",
            "available_categories": [],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        assert "bad-slug" in result
        assert "listar_categorias" in result

    def test_reprompt_with_category_not_found_multiple_categories(self):
        """Message shows multiple available slugs when provided."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=2)
        error_dict = {
            "error": "category_not_found",
            "categoria_usada": "invalid-cat",
            "available_categories": [
                {"slug": "motos-part", "name": "Motos particulares"},
                {"slug": "motos-prof", "name": "Motos profesionales"},
                {"slug": "aseicars-part", "name": "Autocaravanas part"},
            ],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        # At least the first category slug must appear
        assert "motos-part" in result

    def test_reprompt_category_not_found_bypasses_count_check(self):
        """category_not_found path returns immediately regardless of retry_count."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")

        # Even at retry_count=0, should return the actionable category message
        for retry_count in [0, 1, 3, 99]:
            retry_state = make_retry_state(retry_count=retry_count)
            error_dict = {
                "error": "category_not_found",
                "categoria_usada": "wrong-slug",
                "available_categories": [{"slug": "motos-part", "name": "Motos"}],
            }
            result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)
            assert "wrong-slug" in result, f"Expected slug in message for retry_count={retry_count}"
            assert "motos-part" in result

    def test_reprompt_non_category_error_dict_uses_normal_path(self):
        """When error_dict is present but NOT category_not_found, uses normal reprompt path."""
        handler = make_handler()
        policy = handler.get_policy("TEST_MODE")
        retry_state = make_retry_state(retry_count=1)
        # This is a regular validation error dict, not category_not_found
        error_dict = {
            "error": "some_other_error",
            "available_categories": [],
        }

        result = handler.get_validation_reprompt(retry_state, policy, error_dict=error_dict)

        # Should NOT reference category slugs — just a normal reprompt message
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Task 5.4 — Test identificar_y_resolver_elementos: category_not_found enriched error
# =============================================================================

@pytest.mark.asyncio
class TestIdentificarElementosCategoryNotFound:
    """Async tests for the category_not_found enriched error in element_tools."""

    async def test_category_not_found_returns_structured_error(self):
        """When category slug is unknown, returns structured error dict with available_categories."""
        mock_categories = [
            {"slug": "motos-part", "name": "Motos particulares"},
            {"slug": "aseicars-prof", "name": "Autocaravanas profesionales"},
        ]

        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(return_value=mock_categories)

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    # Import tool function directly (unwrapped from @tool decorator)
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "tuning-part", "descripcion": "escape deportivo"}
                    )

        result = json.loads(raw_result)
        assert result["error"] == "category_not_found"
        assert "available_categories" in result
        assert isinstance(result["available_categories"], list)
        assert result["elementos_listos"] == []
        assert result["elementos_con_variantes"] == []

    async def test_category_not_found_includes_categoria_usada(self):
        """Error response includes the slug that was used."""
        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(return_value=[])

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "unknown-slug-xyz", "descripcion": "algo"}
                    )

        result = json.loads(raw_result)
        assert result["categoria_usada"] == "unknown-slug-xyz"

    async def test_category_not_found_includes_sugerencia(self):
        """Error response includes a sugerencia field pointing to listar_categorias."""
        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(return_value=[])

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "bad-cat", "descripcion": "escape"}
                    )

        result = json.loads(raw_result)
        assert "sugerencia" in result
        assert "listar_categorias" in result["sugerencia"]

    async def test_category_not_found_maps_available_categories(self):
        """available_categories contains slug/name pairs from get_active_categories."""
        mock_categories = [
            {"slug": "motos-part", "name": "Motos particulares", "extra_field": "ignored"},
            {"slug": "motos-prof", "name": "Motos profesionales"},
        ]

        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(return_value=mock_categories)

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "bad-cat", "descripcion": "escape"}
                    )

        result = json.loads(raw_result)
        slugs = [c["slug"] for c in result["available_categories"]]
        assert "motos-part" in slugs
        assert "motos-prof" in slugs
        # Each entry must only have slug + name
        for cat in result["available_categories"]:
            assert set(cat.keys()) == {"slug", "name"}


# =============================================================================
# Task 5.5 — Test graceful degradation when get_active_categories raises
# =============================================================================

@pytest.mark.asyncio
class TestIdentificarElementosCategoryNotFoundGracefulDegradation:
    """Graceful degradation when get_active_categories raises an exception."""

    async def test_graceful_degradation_returns_empty_available_categories(self):
        """When get_active_categories raises, available_categories must be [] (no propagation)."""
        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    # Must NOT raise
                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "bad-cat", "descripcion": "algo"}
                    )

        result = json.loads(raw_result)
        assert result["error"] == "category_not_found"
        assert result["available_categories"] == []

    async def test_graceful_degradation_no_exception_propagates(self):
        """Exception from get_active_categories must be swallowed — no exception to caller."""
        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(
            side_effect=RuntimeError("Unexpected runtime error")
        )

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    try:
                        raw_result = await identificar_y_resolver_elementos.ainvoke(
                            {"categoria_vehiculo": "bad-cat", "descripcion": "algo"}
                        )
                    except Exception as exc:
                        pytest.fail(
                            f"Exception should NOT propagate from graceful degradation path, got: {exc}"
                        )

        # Parsing must succeed
        result = json.loads(raw_result)
        assert isinstance(result["available_categories"], list)
        assert result["available_categories"] == []

    async def test_graceful_degradation_still_includes_error_key(self):
        """Even with DB failure, error='category_not_found' must be set."""
        mock_tarifa_service = MagicMock()
        mock_tarifa_service.get_active_categories = AsyncMock(
            side_effect=ConnectionError("Redis down")
        )

        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_service,
            ):
                with patch("agent.tools.element_tools.get_current_state", return_value={}):
                    from agent.tools.element_tools import identificar_y_resolver_elementos

                    raw_result = await identificar_y_resolver_elementos.ainvoke(
                        {"categoria_vehiculo": "bad-cat", "descripcion": "escape"}
                    )

        result = json.loads(raw_result)
        assert result["error"] == "category_not_found"
        assert "categoria_usada" in result
