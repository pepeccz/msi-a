"""
Unit tests for P0 Fix 3 — tool_validation.py fail-closed on missing categoria_slug.

Before the fix, SemanticValidator.validate() used `continue` when categoria_slug
was missing for element_code / tier_id validation, silently treating invalid params
as valid (fail-open). After the fix it appends an error and returns (False, [...]).

Tests avoid DB calls entirely by mocking the imported constraint_service functions.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure structlog stub is present (conftest may not have loaded yet in some
# runners). The conftest.py in tests/unit/ normally handles this, but we add
# a guard here for direct execution.
# ---------------------------------------------------------------------------
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog


# ---------------------------------------------------------------------------
# Minimal BaseTool stub (avoids full langchain import chain in unit tests)
# ---------------------------------------------------------------------------
class _FakeTool:
    """Minimal stub for langchain_core.tools.BaseTool."""

    def __init__(self, name: str):
        self.name = name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _call_semantic_validate(
    param_name: str,
    param_value: str,
    params: dict,
    state: dict | None = None,
):
    """
    Import SemanticValidator and call validate() with a mocked tool.

    All DB-touching functions are patched to avoid actual queries.
    """
    from agent.utils.tool_validation import SemanticValidator

    validator = SemanticValidator()
    tool = _FakeTool(
        name="obtener_campos_elemento"
    )  # uses element_code + categoria_slug

    # Patch the constraint_service imports inside SemanticValidator.validate()
    with (
        patch(
            "agent.services.constraint_service.validate_categoria_slug",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.services.constraint_service.validate_element_code",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.services.constraint_service.validate_case_id",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.services.constraint_service.validate_user_id",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.services.constraint_service.validate_tier_id",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
    ):
        return await validator.validate(
            tool=tool,  # type: ignore[arg-type]
            params={param_name: param_value, **params},
            state=state or {},
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSemanticValidatorFailClosed:
    """
    Verifies that missing categoria_slug produces (False, [error]) for
    element_code and tier_id parameters — no longer silently skipped.
    """

    @pytest.mark.asyncio
    async def test_element_code_without_categoria_slug_returns_false(self):
        """
        element_code present but categoria_slug absent → (False, non-empty errors).
        Previously returned (True, []) — fail-open bug.
        """
        is_valid, errors = await _call_semantic_validate(
            param_name="element_code",
            param_value="ESCAPE",
            params={},  # no categoria_slug in params
            state={},  # no categoria_slug in state either
        )

        assert is_valid is False, (
            f"Expected False for element_code without categoria_slug, got {is_valid}"
        )
        assert len(errors) > 0, "Expected at least one error message"
        assert any("element_code" in e for e in errors), (
            f"Expected error referencing 'element_code', got: {errors}"
        )
        assert any("categoria_slug" in e for e in errors), (
            f"Expected error mentioning 'categoria_slug' requirement, got: {errors}"
        )

    @pytest.mark.asyncio
    async def test_tier_id_without_categoria_slug_returns_false(self):
        """
        tier_id present but categoria_slug absent → (False, non-empty errors).
        Previously returned (True, []) — fail-open bug.
        """
        # Use iniciar_expediente which validates tier_id
        from agent.utils.tool_validation import SemanticValidator

        validator = SemanticValidator()
        tool = _FakeTool(name="iniciar_expediente")

        with (
            patch(
                "agent.services.constraint_service.validate_categoria_slug",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_tier_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_element_code",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_case_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_user_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
        ):
            is_valid, errors = await validator.validate(
                tool=tool,  # type: ignore[arg-type]
                params={"tier_id": "some-tier-uuid"},  # no categoria_slug
                state={},
            )

        assert is_valid is False, (
            f"Expected False for tier_id without categoria_slug, got {is_valid}"
        )
        assert len(errors) > 0, "Expected at least one error message"
        assert any("tier_id" in e for e in errors), (
            f"Expected error referencing 'tier_id', got: {errors}"
        )
        assert any("categoria_slug" in e for e in errors), (
            f"Expected error mentioning 'categoria_slug' requirement, got: {errors}"
        )

    @pytest.mark.asyncio
    async def test_element_code_with_categoria_slug_runs_normally(self):
        """
        When categoria_slug IS present, validation runs the DB check normally.
        No regression: valid element_code + category → (True, []).
        """
        from agent.utils.tool_validation import SemanticValidator

        validator = SemanticValidator()
        tool = _FakeTool(name="obtener_campos_elemento")

        with (
            patch(
                "agent.services.constraint_service.validate_categoria_slug",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_element_code",
                new_callable=AsyncMock,
                return_value=(True, None),  # DB says valid
            ),
            patch(
                "agent.services.constraint_service.validate_case_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_user_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "agent.services.constraint_service.validate_tier_id",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
        ):
            is_valid, errors = await validator.validate(
                tool=tool,  # type: ignore[arg-type]
                params={
                    "element_code": "ESCAPE",
                    "categoria_slug": "motos-part",  # present → DB call proceeds
                },
                state={},
            )

        assert is_valid is True, (
            f"Expected True when both element_code and categoria_slug are present, got {is_valid}"
        )
        assert errors == [], f"Expected no errors, got: {errors}"
