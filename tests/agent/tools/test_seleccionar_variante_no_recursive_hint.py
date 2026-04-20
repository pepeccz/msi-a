"""
Tests for seleccionar_variante_por_respuesta no-variants error path.
Batch B — Layer B:
  - B-T3: error payload must NOT mention identificar_y_resolver_elementos
  - B-T4: error payload must have no_variants: True field
  - B-T5: fuzzy-match happy path still works (regression guard)
"""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element_service_mock(
    variants: list | None = None,
    all_elements: list | None = None,
    fuzzy_element: dict | None = None,
):
    """
    Build a mock ElementService that controls the return values of:
      - get_element_variants -> variants (default [])
      - get_elements_by_category -> all_elements (default [])

    If fuzzy_element is provided it will be included in all_elements so the
    fuzzy-match code can find it.
    """
    if variants is None:
        variants = []
    if all_elements is None:
        all_elements = []

    mock_svc = MagicMock()
    # First call to get_element_variants returns given variants
    mock_svc.get_element_variants = AsyncMock(return_value=variants)
    mock_svc.get_elements_by_category = AsyncMock(return_value=all_elements)
    return mock_svc


async def _call_tool(
    categoria: str = "motos-part",
    codigo: str = "SUSPENSION",
    respuesta: str = "delantera",
    mock_service=None,
):
    """Call seleccionar_variante_por_respuesta with the given args, mocking dependencies."""
    from agent.tools.element_tools import seleccionar_variante_por_respuesta

    if mock_service is None:
        mock_service = _make_element_service_mock()

    with (
        patch("agent.tools.element_tools.get_element_service", return_value=mock_service),
        patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new=AsyncMock(return_value="mock-category-id"),
        ),
        patch("agent.tools.element_tools.validate_category_slug", return_value=None),
    ):
        # Use the LangChain StructuredTool coroutine attribute (async variant)
        coro = seleccionar_variante_por_respuesta.coroutine
        result = await coro(
            categoria_vehiculo=categoria,
            codigo_elemento_base=codigo,
            respuesta_usuario=respuesta,
        )
    return result


# ---------------------------------------------------------------------------
# B-T3 — No-variants error must NOT mention identificar_y_resolver_elementos
# ---------------------------------------------------------------------------

class TestNoVariantsErrorNoRecursiveHint:
    """When no variants exist, the error payload must not suggest re-identification."""

    @pytest.mark.asyncio
    async def test_no_variants_error_does_not_contain_identificar_hint(self):
        """
        With no variants found and no fuzzy match, the returned dict MUST NOT
        contain any reference to 'identificar_y_resolver_elementos'.

        Spec Layer B: Tool error response is prescriptive and loop-free.
        """
        result = await _call_tool(
            categoria="motos-part",
            codigo="ELEMENTO_INEXISTENTE",
            respuesta="delantera",
            mock_service=_make_element_service_mock(variants=[], all_elements=[]),
        )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        result_str = str(result)
        assert "identificar_y_resolver_elementos" not in result_str, (
            "Error payload must NOT mention 'identificar_y_resolver_elementos'. "
            f"Got: {result}"
        )

    @pytest.mark.asyncio
    async def test_no_variants_error_does_not_suggest_reidentification(self):
        """
        Triangulation: even with all_elements populated (but no matching variants),
        the error payload must not suggest re-identification as next step.
        """
        # Some elements in catalogue, but still no variants for our code
        mock_svc = _make_element_service_mock(
            variants=[],  # no variants at all for this code
            all_elements=[
                {"code": "BOLA_REMOLQUE", "name": "Bola de remolque", "parent_element_id": None},
                {"code": "SUSPENSION", "name": "Suspensión", "parent_element_id": None},
            ],
        )
        result = await _call_tool(
            categoria="motos-part",
            codigo="ASIDEROS",  # not in catalogue above
            respuesta="delanteros",
            mock_service=mock_svc,
        )

        result_str = str(result)
        assert "identificar_y_resolver_elementos" not in result_str, (
            "Error payload must NOT mention 'identificar_y_resolver_elementos'. "
            f"Got: {result}"
        )


# ---------------------------------------------------------------------------
# B-T4 — No-variants error must have no_variants: True field
# ---------------------------------------------------------------------------

class TestNoVariantsErrorHasNoVariantsField:
    """The error payload must include no_variants: True."""

    @pytest.mark.asyncio
    async def test_no_variants_error_has_no_variants_field(self):
        """
        With no variants found, the returned dict MUST contain
        'no_variants': True.

        Spec Layer B: Tool error response has no_variants field.
        """
        result = await _call_tool(
            categoria="motos-part",
            codigo="ELEMENTO_INEXISTENTE",
            respuesta="delantera",
            mock_service=_make_element_service_mock(variants=[], all_elements=[]),
        )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result.get("no_variants") is True, (
            f"Error payload must have 'no_variants': True. Got: {result}"
        )

    @pytest.mark.asyncio
    async def test_no_variants_error_has_accion_requerida_field(self):
        """
        Triangulation: error payload must also include 'accion_requerida' with
        prescriptive instructions (no re-identification hint).
        """
        result = await _call_tool(
            categoria="motos-part",
            codigo="ELEMENTO_INEXISTENTE",
            respuesta="delantera",
            mock_service=_make_element_service_mock(variants=[], all_elements=[]),
        )

        assert "accion_requerida" in result, (
            f"Error payload must have 'accion_requerida' field. Got: {result}"
        )
        # The accion_requerida must NOT hint at re-identification
        accion = result["accion_requerida"]
        assert "identificar_y_resolver_elementos" not in accion, (
            f"'accion_requerida' must not mention identificar_y_resolver_elementos. "
            f"Got: {accion}"
        )
        # Must contain prescriptive instructions about what to do instead
        assert len(accion) > 30, (
            f"'accion_requerida' must be a descriptive instruction (> 30 chars). Got: {accion!r}"
        )


# ---------------------------------------------------------------------------
# B-T5 — Fuzzy-match happy path regression guard
# ---------------------------------------------------------------------------

def _make_tool_config(mode_context: dict | None = None) -> dict:
    """Build a minimal RunnableConfig with state for tools that call get_tool_state()."""
    state = {
        "conversation_id": "test-b-t5",
        "mode_context": mode_context or {},
    }
    return {"configurable": {"state": state}}


class TestFuzzyMatchHappyPathRegression:
    """The fuzzy-match path must continue to work after the error payload change."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_path_still_works_exact_variant(self):
        """
        When the element code exists with variants, the tool must resolve correctly
        (happy path — no error, returns selected_variant or selected_variants).

        B-T5 scenario: exact code match with real variants.
        """
        from agent.tools.element_tools import seleccionar_variante_por_respuesta

        # Variant that matches "delantera"
        mock_variant = {
            "code": "SUSPENSION_DEL",
            "name": "Suspensión delantera",
            "parent_element_id": "SUSPENSION",
            "keywords": ["delantera", "del"],
        }

        mock_svc = MagicMock()
        mock_svc.get_element_variants = AsyncMock(return_value=[mock_variant])
        mock_svc.get_elements_by_category = AsyncMock(return_value=[])
        mock_svc.get_element_by_code = AsyncMock(return_value={"multi_select_keywords": []})

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_svc),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new=AsyncMock(return_value="mock-category-id"),
            ),
            patch("agent.tools.element_tools.validate_category_slug", return_value=None),
            patch("agent.tools.element_tools.get_settings") as mock_settings,
        ):
            mock_settings.return_value.ENABLE_LLM_VARIANT_INTERPRETATION = False
            coro = seleccionar_variante_por_respuesta.coroutine
            result = await coro(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="SUSPENSION",
                respuesta_usuario="delantera",
                config=_make_tool_config(),
            )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        # Must NOT be a no_variants error
        assert result.get("no_variants") is not True, (
            f"Happy path must not return no_variants error. Got: {result}"
        )
        # Must not contain an error key (or if it does, no_variants must be absent)
        assert "no_variants" not in result, (
            f"Happy path must not have no_variants key. Got: {result}"
        )

    @pytest.mark.asyncio
    async def test_fuzzy_match_path_still_works_approximate_code(self):
        """
        B-T5 triangulation: when the LLM passes an approximate code that fuzzy-matches
        a real element, the tool must resolve correctly (no error returned).
        """
        from agent.tools.element_tools import seleccionar_variante_por_respuesta

        fuzzy_elem = {
            "code": "SUSPENSION_MOTO",
            "name": "Suspensión moto",
            "parent_element_id": None,  # this is a base element
        }
        mock_variant = {
            "code": "SUSPENSION_MOTO_DEL",
            "name": "Suspensión delantera",
            "parent_element_id": "SUSPENSION_MOTO",
            "keywords": ["delantera"],
        }

        mock_svc = MagicMock()
        # First call (exact) returns empty → triggers fuzzy
        # Second call (after fuzzy match) returns the variant
        mock_svc.get_element_variants = AsyncMock(side_effect=[[], [mock_variant]])
        mock_svc.get_elements_by_category = AsyncMock(return_value=[fuzzy_elem])
        mock_svc.get_element_by_code = AsyncMock(return_value={"multi_select_keywords": []})

        with (
            patch("agent.tools.element_tools.get_element_service", return_value=mock_svc),
            patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new=AsyncMock(return_value="mock-category-id"),
            ),
            patch("agent.tools.element_tools.validate_category_slug", return_value=None),
            patch("agent.tools.element_tools.get_settings") as mock_settings,
        ):
            mock_settings.return_value.ENABLE_LLM_VARIANT_INTERPRETATION = False
            coro = seleccionar_variante_por_respuesta.coroutine
            result = await coro(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="SUSPENSION MOTO",  # approximate — spaces, not underscore
                respuesta_usuario="delantera",
                config=_make_tool_config(),
            )

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        # Must NOT be a no_variants error
        assert result.get("no_variants") is not True, (
            f"Fuzzy-match happy path must not return no_variants error. Got: {result}"
        )
