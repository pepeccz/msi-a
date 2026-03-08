"""Unit tests for the unconditional parent-code guard in calcular_tarifa_con_elementos.

Change: variant-bypass-skip-validation (Phase 4 — Tests)

Tests that `calcular_tarifa_con_elementos` rejects parent element codes
(elements with children / variants) REGARDLESS of `skip_validation`,
returning ERROR_VARIANTE_REQUERIDA with actionable variant info.

Also covers:
- Resolved variant codes passing through (e.g. TOLDO_SIMPLE)
- Mixed parent + resolved codes
- Error response format contract
- Leaf elements without children passing through
- TOLDO_SIMPLE / TOLDO_GALIBO presence in tier_mappings T6_ELEMENTS
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock element data
# ---------------------------------------------------------------------------

# Category UUID stub
CATEGORY_ID = "cat-aseicars-part-uuid"

# Parent element — has children, should be REJECTED
TOLDO_LAT_ELEMENT: dict[str, Any] = {
    "id": "elem-toldo-lat-uuid",
    "code": "TOLDO_LAT",
    "name": "Toldo lateral",
    "parent_element_id": None,
    "question_hint": "¿El toldo afecta al gálibo del vehículo?",
    "keywords": ["toldo", "lateral"],
    "aliases": [],
}

# Child variant A — resolved, should PASS
TOLDO_SIMPLE_ELEMENT: dict[str, Any] = {
    "id": "elem-toldo-simple-uuid",
    "code": "TOLDO_SIMPLE",
    "name": "Toldo simple (sin afectar gálibo)",
    "parent_element_id": "elem-toldo-lat-uuid",
    "question_hint": None,
    "keywords": ["toldo", "simple"],
    "aliases": [],
}

# Child variant B — resolved, should PASS
TOLDO_GALIBO_ELEMENT: dict[str, Any] = {
    "id": "elem-toldo-galibo-uuid",
    "code": "TOLDO_GALIBO",
    "name": "Toldo que afecta al gálibo",
    "parent_element_id": "elem-toldo-lat-uuid",
    "question_hint": None,
    "keywords": ["toldo", "galibo"],
    "aliases": [],
}

# Another parent element — PLACA_SOLAR with children
PLACA_SOLAR_ELEMENT: dict[str, Any] = {
    "id": "elem-placa-solar-uuid",
    "code": "PLACA_SOLAR",
    "name": "Placa solar",
    "parent_element_id": None,
    "question_hint": "¿Dónde se ubica el regulador de la placa solar?",
    "keywords": ["placa", "solar"],
    "aliases": [],
}

PLACA_SOLAR_SIMPLE_ELEMENT: dict[str, Any] = {
    "id": "elem-placa-solar-simple-uuid",
    "code": "PLACA_SOLAR_SIMPLE",
    "name": "Placa solar con regulador del vehículo",
    "parent_element_id": "elem-placa-solar-uuid",
    "question_hint": None,
    "keywords": [],
    "aliases": [],
}

PLACA_SOLAR_REG_INT_ELEMENT: dict[str, Any] = {
    "id": "elem-placa-solar-reg-int-uuid",
    "code": "PLACA_SOLAR_REGULADOR_INTERIOR",
    "name": "Placa solar con regulador interior",
    "parent_element_id": "elem-placa-solar-uuid",
    "question_hint": None,
    "keywords": [],
    "aliases": [],
}

# Leaf element — no children, should always PASS
ANTENA_PAR_ELEMENT: dict[str, Any] = {
    "id": "elem-antena-par-uuid",
    "code": "ANTENA_PAR",
    "name": "Antena parabólica",
    "parent_element_id": None,
    "question_hint": None,
    "keywords": ["antena"],
    "aliases": [],
}

# Full catalog for the mocked category
ALL_ELEMENTS: list[dict[str, Any]] = [
    TOLDO_LAT_ELEMENT,
    TOLDO_SIMPLE_ELEMENT,
    TOLDO_GALIBO_ELEMENT,
    PLACA_SOLAR_ELEMENT,
    PLACA_SOLAR_SIMPLE_ELEMENT,
    PLACA_SOLAR_REG_INT_ELEMENT,
    ANTENA_PAR_ELEMENT,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_state(*, pending_variants: list | None = None) -> dict:
    """Build a minimal conversation state for the tool."""
    return {
        "conversation_id": "test-parent-guard",
        "current_mode": "PRESUPUESTO_MODE",
        "client_type": "particular",
        "mode_context": {
            "pending_variants": pending_variants or [],
        },
    }


def _mock_element_service() -> MagicMock:
    """Create a mock element service that returns ALL_ELEMENTS."""
    svc = MagicMock()
    svc.get_elements_by_category = AsyncMock(return_value=ALL_ELEMENTS)
    svc.get_element_warnings = AsyncMock(return_value=[])
    svc.get_element_with_images = AsyncMock(return_value={"images": []})
    return svc


def _mock_tarifa_service(*, price: float = 75.0) -> MagicMock:
    """Create a mock tarifa service for successful tariff calculation."""
    svc = MagicMock()
    svc.get_active_categories = AsyncMock(return_value=[
        {"id": CATEGORY_ID, "slug": "aseicars-part", "name": "Autocaravanas Particular"},
    ])
    svc.select_tariff_by_rules = AsyncMock(return_value={
        "tier_id": "tier-t6-uuid",
        "tier_name": "T6",
        "price": price,
        "conditions": None,
        "warnings": [],
        "element_validation": {"valid": True},
        "additional_services": [],
    })
    svc.get_category_data = AsyncMock(return_value={
        "base_documentation": [],
    })
    return svc


async def _invoke_calcular_tarifa(
    codigos: list[str],
    *,
    skip_validation: bool = True,
    categoria: str = "aseicars-part",
    state: dict | None = None,
    element_service: MagicMock | None = None,
    tarifa_service: MagicMock | None = None,
) -> dict:
    """Invoke calcular_tarifa_con_elementos with mocked services, return parsed JSON."""
    from agent.tools.element_tools import calcular_tarifa_con_elementos
    from agent.state.helpers import set_current_state, clear_current_state

    es = element_service or _mock_element_service()
    ts = tarifa_service or _mock_tarifa_service()
    st = state or _build_state()

    try:
        set_current_state(st)

        with patch(
            "agent.tools.element_tools.validate_category_slug"
        ), patch(
            "agent.tools.element_tools.get_tarifa_service",
            return_value=ts,
        ), patch(
            # _validate_element_codes does a local import of get_tarifa_service
            "agent.services.tarifa_service.get_tarifa_service",
            return_value=ts,
        ), patch(
            "agent.tools.element_tools.get_element_service",
            return_value=es,
        ), patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=CATEGORY_ID,
        ):
            result_str = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": categoria,
                "codigos_elementos": codigos,
                "skip_validation": skip_validation,
            })

        # The tool returns a JSON string
        return json.loads(result_str)
    finally:
        clear_current_state()


# ===========================================================================
# Test 1: Parent code rejected WITH skip_validation=True
# ===========================================================================

class TestParentCodeRejectedWithSkipValidation:
    """Parent codes must be rejected even when skip_validation=True."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_parent_code_rejected_with_skip_validation_true(self) -> None:
        """TOLDO_LAT is a parent → must be rejected with ERROR_VARIANTE_REQUERIDA."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
        )

        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"
        assert len(result["parent_elements_rejected"]) == 1

        rejected = result["parent_elements_rejected"][0]
        assert rejected["code"] == "TOLDO_LAT"
        # Children should be listed
        child_codes = [c["code"] for c in rejected["children"]]
        assert "TOLDO_SIMPLE" in child_codes
        assert "TOLDO_GALIBO" in child_codes

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_placa_solar_parent_rejected_with_skip_validation_true(self) -> None:
        """PLACA_SOLAR is a parent → also rejected."""
        result = await _invoke_calcular_tarifa(
            ["PLACA_SOLAR"],
            skip_validation=True,
        )

        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"
        rejected = result["parent_elements_rejected"][0]
        assert rejected["code"] == "PLACA_SOLAR"


# ===========================================================================
# Test 2: Resolved variant code passes through
# ===========================================================================

class TestResolvedVariantCodePassesThrough:
    """Resolved variant codes (children) should NOT be rejected."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_toldo_simple_passes_through(self) -> None:
        """TOLDO_SIMPLE is a child variant → should pass to tariff calculation."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_SIMPLE"],
            skip_validation=True,
        )

        # Should reach the tariff calculation (success path)
        # The mock tarifa_service returns a valid tariff
        assert "success" not in result or result.get("success") is not False
        # The datos section should be present (from tariff response)
        assert "datos" in result
        assert result["datos"]["tier_name"] == "T6"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_toldo_galibo_passes_through(self) -> None:
        """TOLDO_GALIBO is a child variant → should pass to tariff calculation."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_GALIBO"],
            skip_validation=True,
        )

        assert "datos" in result
        assert result["datos"]["tier_name"] == "T6"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_placa_solar_regulador_interior_passes_through(self) -> None:
        """PLACA_SOLAR_REGULADOR_INTERIOR is a resolved variant → passes through."""
        result = await _invoke_calcular_tarifa(
            ["PLACA_SOLAR_REGULADOR_INTERIOR"],
            skip_validation=True,
        )

        assert "datos" in result


# ===========================================================================
# Test 3: Mixed parent and resolved codes
# ===========================================================================

class TestMixedParentAndResolvedCodes:
    """When mix of parent + resolved codes is passed, parent causes rejection."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_mixed_parent_and_resolved_rejects(self) -> None:
        """["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_LAT"] → rejected because TOLDO_LAT is parent."""
        result = await _invoke_calcular_tarifa(
            ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_LAT"],
            skip_validation=True,
        )

        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"

        rejected_codes = [p["code"] for p in result["parent_elements_rejected"]]
        assert "TOLDO_LAT" in rejected_codes
        # PLACA_SOLAR_REGULADOR_INTERIOR should NOT be in the rejected list
        assert "PLACA_SOLAR_REGULADOR_INTERIOR" not in rejected_codes

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_parents_all_rejected(self) -> None:
        """["PLACA_SOLAR", "TOLDO_LAT"] → both parents rejected."""
        result = await _invoke_calcular_tarifa(
            ["PLACA_SOLAR", "TOLDO_LAT"],
            skip_validation=True,
        )

        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"

        rejected_codes = {p["code"] for p in result["parent_elements_rejected"]}
        assert rejected_codes == {"PLACA_SOLAR", "TOLDO_LAT"}


# ===========================================================================
# Test 4: Parent code rejected WITHOUT skip_validation (double layer)
# ===========================================================================

class TestParentCodeRejectedWithoutSkipValidation:
    """Parent codes rejected with skip_validation=False via _validate_element_codes."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_parent_code_rejected_without_skip_validation(self) -> None:
        """TOLDO_LAT with skip_validation=False → rejected by _validate_element_codes guard.

        When skip_validation=False, _validate_element_codes detects the parent code
        and returns valid=False + ERROR_VARIANTE_REQUERIDA. The outer tool then wraps
        it in a plain-text error string (not JSON), so we check the raw string.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos
        from agent.state.helpers import set_current_state, clear_current_state

        ts = _mock_tarifa_service()
        es = _mock_element_service()
        st = _build_state()

        try:
            set_current_state(st)

            with patch(
                "agent.tools.element_tools.validate_category_slug"
            ), patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=ts,
            ), patch(
                "agent.services.tarifa_service.get_tarifa_service",
                return_value=ts,
            ), patch(
                "agent.tools.element_tools.get_element_service",
                return_value=es,
            ), patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value=CATEGORY_ID,
            ):
                result_str = await calcular_tarifa_con_elementos.ainvoke({
                    "categoria_vehiculo": "aseicars-part",
                    "codigos_elementos": ["TOLDO_LAT"],
                    "skip_validation": False,
                })
        finally:
            clear_current_state()

        # With skip_validation=False, the tool returns a plain error string
        # (not JSON) when _validate_element_codes finds invalid codes.
        # The string should mention variant requirement.
        result_lower = result_str.lower() if isinstance(result_str, str) else ""

        # Try JSON first (in case implementation changes)
        try:
            result = json.loads(result_str)
            assert result.get("success") is False or result.get("valid") is False
        except (json.JSONDecodeError, TypeError):
            # Plain string error — verify it contains variant-related info
            assert "variante" in result_lower or "error" in result_lower, (
                f"Expected parent-code rejection message, got: {result_str[:200]}"
            )


# ===========================================================================
# Test 5: Error format matches contract
# ===========================================================================

class TestErrorFormatMatchesContract:
    """Verify the exact structure of the ERROR_VARIANTE_REQUERIDA response."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_error_format_matches_contract(self) -> None:
        """Verify full error response structure for parent code rejection."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
        )

        # Top-level keys
        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"
        assert "message" in result
        assert "parent_elements_rejected" in result
        assert "_internal_flags" in result

        # _internal_flags contract
        flags = result["_internal_flags"]
        assert flags["precio_comunicado"] is False

        # parent_elements_rejected array structure
        rejected = result["parent_elements_rejected"]
        assert isinstance(rejected, list)
        assert len(rejected) >= 1

        entry = rejected[0]
        assert "code" in entry, "Missing 'code' in parent_elements_rejected entry"
        assert "name" in entry, "Missing 'name' in parent_elements_rejected entry"
        assert "children" in entry, "Missing 'children' in parent_elements_rejected entry"
        assert "question_hint" in entry, "Missing 'question_hint' in parent_elements_rejected entry"

        # Children structure
        child = entry["children"][0]
        assert "code" in child, "Missing 'code' in children entry"
        assert "name" in child, "Missing 'name' in children entry"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_question_hint_from_element_data(self) -> None:
        """question_hint should use the element's question_hint when available."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
        )

        rejected = result["parent_elements_rejected"][0]
        assert rejected["question_hint"] == "¿El toldo afecta al gálibo del vehículo?"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_question_hint_fallback_when_missing(self) -> None:
        """When question_hint is None, a generated fallback is used."""
        # Create an element without question_hint
        elements_no_hint = list(ALL_ELEMENTS)
        # Replace PLACA_SOLAR with a copy that has no question_hint
        placa_no_hint = {**PLACA_SOLAR_ELEMENT, "question_hint": None}
        elements_no_hint = [
            placa_no_hint if e["code"] == "PLACA_SOLAR" else e
            for e in elements_no_hint
        ]

        es = MagicMock()
        es.get_elements_by_category = AsyncMock(return_value=elements_no_hint)
        es.get_element_warnings = AsyncMock(return_value=[])
        es.get_element_with_images = AsyncMock(return_value={"images": []})

        result = await _invoke_calcular_tarifa(
            ["PLACA_SOLAR"],
            skip_validation=True,
            element_service=es,
        )

        rejected = result["parent_elements_rejected"][0]
        # Should contain a generated question
        assert "placa solar" in rejected["question_hint"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_message_contains_variant_instructions(self) -> None:
        """The message field should contain actionable instructions for the LLM."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
        )

        message = result["message"]
        assert "VARIANTE" in message.upper()
        assert "variante" in message.lower() or "VARIANTE" in message
        assert "TOLDO_SIMPLE" in message or "Toldo simple" in message


# ===========================================================================
# Test 6: Non-parent (leaf) element passes through
# ===========================================================================

class TestNonParentElementPasses:
    """Leaf elements with NO children should pass through the guard."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_antena_par_passes_through(self) -> None:
        """ANTENA_PAR has no children → passes through to tariff calculation."""
        result = await _invoke_calcular_tarifa(
            ["ANTENA_PAR"],
            skip_validation=True,
        )

        # Should reach tariff calculation (success path)
        assert "datos" in result
        assert result["datos"]["tier_name"] == "T6"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_leaf_elements_all_pass(self) -> None:
        """Multiple leaf elements all pass through."""
        result = await _invoke_calcular_tarifa(
            ["ANTENA_PAR", "TOLDO_SIMPLE"],
            skip_validation=True,
        )

        # Both are leaves / resolved variants → should reach tariff
        assert "datos" in result


# ===========================================================================
# Test 7: TOLDO variants in tier_mappings T6_ELEMENTS
# ===========================================================================

class TestToldoVariantsInTierMappings:
    """Verify TOLDO_SIMPLE and TOLDO_GALIBO exist in tier_mappings T6_ELEMENTS."""

    @pytest.mark.unit
    def test_toldo_simple_in_aseicars_part_t6(self) -> None:
        """TOLDO_SIMPLE must be in ASEICARS_PART_MAPPINGS T6_ELEMENTS."""
        from database.seeds.data.tier_mappings import ASEICARS_PART_MAPPINGS

        t6_elements = ASEICARS_PART_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_SIMPLE" in t6_elements, (
            f"TOLDO_SIMPLE missing from ASEICARS_PART T6_ELEMENTS: {t6_elements}"
        )

    @pytest.mark.unit
    def test_toldo_galibo_in_aseicars_part_t6(self) -> None:
        """TOLDO_GALIBO must be in ASEICARS_PART_MAPPINGS T6_ELEMENTS."""
        from database.seeds.data.tier_mappings import ASEICARS_PART_MAPPINGS

        t6_elements = ASEICARS_PART_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_GALIBO" in t6_elements, (
            f"TOLDO_GALIBO missing from ASEICARS_PART T6_ELEMENTS: {t6_elements}"
        )

    @pytest.mark.unit
    def test_toldo_simple_in_aseicars_prof_t6(self) -> None:
        """TOLDO_SIMPLE must be in ASEICARS_PROF_MAPPINGS T6_ELEMENTS."""
        from database.seeds.data.tier_mappings import ASEICARS_PROF_MAPPINGS

        t6_elements = ASEICARS_PROF_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_SIMPLE" in t6_elements, (
            f"TOLDO_SIMPLE missing from ASEICARS_PROF T6_ELEMENTS: {t6_elements}"
        )

    @pytest.mark.unit
    def test_toldo_galibo_in_aseicars_prof_t6(self) -> None:
        """TOLDO_GALIBO must be in ASEICARS_PROF_MAPPINGS T6_ELEMENTS."""
        from database.seeds.data.tier_mappings import ASEICARS_PROF_MAPPINGS

        t6_elements = ASEICARS_PROF_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_GALIBO" in t6_elements, (
            f"TOLDO_GALIBO missing from ASEICARS_PROF T6_ELEMENTS: {t6_elements}"
        )

    @pytest.mark.unit
    def test_toldo_lat_backward_compat_in_aseicars_part_t6(self) -> None:
        """TOLDO_LAT (parent) still in T6_ELEMENTS for backward compatibility."""
        from database.seeds.data.tier_mappings import ASEICARS_PART_MAPPINGS

        t6_elements = ASEICARS_PART_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_LAT" in t6_elements, (
            "TOLDO_LAT should remain in T6_ELEMENTS for backward compatibility"
        )

    @pytest.mark.unit
    def test_toldo_lat_backward_compat_in_aseicars_prof_t6(self) -> None:
        """TOLDO_LAT (parent) still in T6_ELEMENTS for backward compatibility."""
        from database.seeds.data.tier_mappings import ASEICARS_PROF_MAPPINGS

        t6_elements = ASEICARS_PROF_MAPPINGS["T6_ELEMENTS"]
        assert "TOLDO_LAT" in t6_elements, (
            "TOLDO_LAT should remain in T6_ELEMENTS for backward compatibility"
        )

    @pytest.mark.unit
    def test_get_element_tier_level_returns_t6_for_toldo_simple(self) -> None:
        """get_element_tier_level should return T6 for TOLDO_SIMPLE."""
        from database.seeds.data.tier_mappings import get_element_tier_level

        tier = get_element_tier_level("aseicars-part", "TOLDO_SIMPLE")
        assert tier == "T6", f"Expected T6 for TOLDO_SIMPLE, got {tier}"

    @pytest.mark.unit
    def test_get_element_tier_level_returns_t6_for_toldo_galibo(self) -> None:
        """get_element_tier_level should return T6 for TOLDO_GALIBO."""
        from database.seeds.data.tier_mappings import get_element_tier_level

        tier = get_element_tier_level("aseicars-part", "TOLDO_GALIBO")
        assert tier == "T6", f"Expected T6 for TOLDO_GALIBO, got {tier}"


# ===========================================================================
# Test 8: Edge cases and guard robustness
# ===========================================================================

class TestParentGuardEdgeCases:
    """Edge cases for the unconditional parent-code guard."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_empty_codigos_returns_error(self) -> None:
        """Empty element codes list returns an error (before guard runs)."""
        from agent.tools.element_tools import calcular_tarifa_con_elementos
        from agent.state.helpers import set_current_state, clear_current_state

        st = _build_state()
        try:
            set_current_state(st)
            with patch("agent.tools.element_tools.validate_category_slug"), \
                 patch("agent.tools.element_tools.get_tarifa_service", return_value=_mock_tarifa_service()), \
                 patch("agent.tools.element_tools.get_element_service", return_value=_mock_element_service()), \
                 patch("agent.tools.element_tools.get_or_fetch_category_id", new_callable=AsyncMock, return_value=CATEGORY_ID):
                result_str = await calcular_tarifa_con_elementos.ainvoke({
                    "categoria_vehiculo": "aseicars-part",
                    "codigos_elementos": [],
                    "skip_validation": True,
                })
        finally:
            clear_current_state()

        assert "error" in result_str.lower() or "al menos un" in result_str.lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_guard_does_not_add_extra_db_queries(self) -> None:
        """Guard reuses already-fetched `elements` list — no new DB calls."""
        es = _mock_element_service()

        await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
            element_service=es,
        )

        # get_elements_by_category should be called exactly once
        # (the guard reuses the same data, no additional DB queries)
        assert es.get_elements_by_category.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_internal_flags_precio_comunicado_false_on_rejection(self) -> None:
        """When parent code is rejected, _internal_flags.precio_comunicado must be False."""
        result = await _invoke_calcular_tarifa(
            ["TOLDO_LAT"],
            skip_validation=True,
        )

        assert result["_internal_flags"]["precio_comunicado"] is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_case_insensitive_code_matching(self) -> None:
        """Parent guard handles case variations (lowercase input)."""
        # The tool uppercases codes via normalize_element_codes,
        # so "toldo_lat" should be normalized to "TOLDO_LAT" and rejected.
        result = await _invoke_calcular_tarifa(
            ["toldo_lat"],
            skip_validation=True,
        )

        # Should still be rejected (codes are normalized to uppercase)
        assert result["success"] is False
        assert result["status"] == "ERROR_VARIANTE_REQUERIDA"
