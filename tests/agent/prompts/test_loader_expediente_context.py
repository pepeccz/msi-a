"""
Unit tests for categoria_slug injection in format_mode_context().

fix-expediente-context-gaps Phase 1: verifies that the prompt layer injects
'Categoría: {slug}' into the EXPEDIENTE_MODE context when categoria_slug is
present.

These are pure unit tests (no DB, no Redis, no LLM).
"""

import pytest

from agent.prompts.loader import format_mode_context


# =============================================================================
# Phase 1 — Task 1.1: Categoría slug injection
# =============================================================================


class TestCategoriaSlugInjection:
    """Tests for 'Categoría: {slug}' injection in format_mode_context."""

    @pytest.mark.parametrize(
        "mode,categoria_slug,expected_present",
        [
            pytest.param(
                "EXPEDIENTE_MODE",
                "motos-part",
                True,
                id="expediente-motos-part",
            ),
            pytest.param(
                "EXPEDIENTE_MODE",
                "aseicars-prof",
                True,
                id="expediente-aseicars-prof",
            ),
            pytest.param(
                "EXPEDIENTE_MODE",
                None,
                False,
                id="expediente-no-slug",
            ),
            pytest.param(
                "EXPEDIENTE_MODE",
                "",
                False,
                id="expediente-empty-slug",
            ),
            pytest.param(
                "EXPEDIENTE_COLLECT_ELEMENT_DATA",
                "motos-part",
                True,
                id="submode-collect-element-data",
            ),
        ],
    )
    def test_categoria_slug_injection(
        self,
        mode: str,
        categoria_slug: str | None,
        expected_present: bool,
    ):
        """
        format_mode_context must include 'Categoría: {slug}' when
        categoria_slug is truthy, and omit it otherwise.
        """
        context: dict = {
            "expediente_sub_mode": "collect_base_docs",
        }
        if categoria_slug is not None:
            context["categoria_slug"] = categoria_slug

        result = format_mode_context(mode, context)

        if expected_present:
            assert f"Categoría: {categoria_slug}" in result
        else:
            assert "Categoría:" not in result
