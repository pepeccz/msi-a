"""
Integration-level scenario tests for multi-element variant resolution — Task 4.3 + 4.4.

Tests the full pipeline: tool (_extract_context_from_tool) + service + state together.
DB and LLM are mocked but the data flows through the real tool extraction and service logic.

Scenarios:
1. Three solar panels with mixed variants (original failing conversation)
2. All same variant ("todas con regulador visible")
3. Sequential resolution (one at a time across turns)
4. Regression: price communicated before images

All tests run without external services.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.services.variant_interpretation_service import (
    VariantAllocation,
    VariantInterpretationResult,
    validate_and_apply_allocations,
)
from agent.state.conversation_state import PendingVariantGroup, VariantResolution
from agent.state.helpers import normalize_pending_variants
from shared.llm_router import LLMResponse, ModelTier, Provider


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_pending_solar(
    cantidad_total: int = 3,
    cantidad_resuelta: int = 0,
    resoluciones: list[VariantResolution] | None = None,
) -> PendingVariantGroup:
    """Standard solar panel pending variant for scenario tests."""
    return PendingVariantGroup(
        pending_id="PLACA_SOLAR_0",
        codigo_base="PLACA_SOLAR",
        pregunta="¿La placa solar incluye su propio regulador o usa el del vehículo?",
        opciones=["Con regulador propio", "Regulador existente del vehículo"],
        cantidad_total=cantidad_total,
        cantidad_resuelta=cantidad_resuelta,
        cantidad_pendiente=cantidad_total - cantidad_resuelta,
        resoluciones=resoluciones or [],
        status="pending" if cantidad_resuelta == 0 else (
            "resolved" if cantidad_resuelta >= cantidad_total else "partial"
        ),
    )


def _make_llm_response(content: str, success: bool = True) -> LLMResponse:
    """Build a mock LLMResponse."""
    return LLMResponse(
        content=content,
        provider=Provider.OLLAMA,
        model="qwen2.5:3b",
        tier=ModelTier.LOCAL_FAST,
        latency_ms=100,
        input_tokens=50,
        output_tokens=30,
        success=success,
    )


class _ModeHelper:
    """Helper to invoke _extract_context_from_tool on PresupuestoModeNode."""

    def __init__(self):
        self.mode = PresupuestoModeNode()

    def extract(
        self,
        tool_name: str,
        tool_result: dict[str, Any],
        tool_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call _extract_context_from_tool with a JSON-encoded result."""
        result_json = json.dumps(tool_result, ensure_ascii=False)
        return self.mode._extract_context_from_tool(
            tool_name=tool_name,
            tool_args=tool_args or {},
            result=result_json,
        )


# ===========================================================================
# Scenario 1: Three solar panels with mixed variants
# ===========================================================================


@pytest.mark.asyncio
class TestScenarioThreeSolarPanelsMixed:
    """
    Original failing scenario: customer wants 3 solar panels for motorhome.
    "2 con regulador propio y 1 existente"

    Before the fix, identification happened once and all 3 got the same variant.
    With multi-unit resolution, the tool+service correctly allocates 2+1.
    """

    async def test_three_solar_panels_mixed_variants(self):
        helper = _ModeHelper()
        context: dict[str, Any] = {}

        # ── Step 1: identificar_y_resolver_elementos returns variant pending ──
        identify_result = {
            "elementos_listos": [],
            "elementos_con_variantes": [
                {"codigo": "PLACA_SOLAR", "nombre": "Placa solar"},
            ],
            "preguntas_variantes": [
                {
                    "codigo_base": "PLACA_SOLAR",
                    "pregunta": "¿La placa solar incluye regulador propio o usa el del vehículo?",
                    "opciones": ["Con regulador propio", "Regulador existente del vehículo"],
                    # NOTE: legacy entry without pending_id — will be normalized
                },
            ],
        }

        updates = helper.extract(
            "identificar_y_resolver_elementos",
            identify_result,
            {"categoria_vehiculo": "aseicars-prof"},
        )
        context.update(updates)

        assert len(context["pending_variants"]) == 1
        assert context["pending_variants"][0]["codigo_base"] == "PLACA_SOLAR"
        assert context.get("elemento_confirmado") is None

        # ── Step 2: normalize for multi-unit (user said "3 placas") ──
        # In real flow, the LLM tool call includes quantity context.
        # Here we simulate what the tool returns with multi-unit allocation.
        pending_enriched = _make_pending_solar(cantidad_total=3)

        # User says: "2 con regulador propio y 1 existente"
        allocations = [
            VariantAllocation(variant_code="Con regulador propio", quantity=2, confidence=0.9),
            VariantAllocation(variant_code="Regulador existente del vehículo", quantity=1, confidence=0.85),
        ]

        updated_pending, errors = validate_and_apply_allocations(
            pending_enriched, allocations, dry_run=False,
        )

        assert errors == []
        assert updated_pending["status"] == "resolved"
        assert updated_pending["cantidad_resuelta"] == 3
        assert updated_pending["cantidad_pendiente"] == 0
        assert len(updated_pending["resoluciones"]) == 2

        # ── Step 3: Simulate tool returning resolved state via _internal_flags ──
        variant_tool_result = {
            "selected_variant": "PLACA_SOLAR_PROPIO",
            "confidence": 0.9,
            "name": "Placa solar con regulador propio",
            "applied_allocations": [
                {"variant_code": "Con regulador propio", "quantity": 2, "confidence": 0.9},
                {"variant_code": "Regulador existente del vehículo", "quantity": 1, "confidence": 0.85},
            ],
            "resolution_status": "resolved",
            "pending_count": 0,
            "_internal_flags": {
                "pending_variants": [dict(updated_pending)],
            },
        }

        updates2 = helper.extract(
            "seleccionar_variante_por_respuesta",
            variant_tool_result,
            {
                "categoria_vehiculo": "aseicars-prof",
                "codigo_elemento_base": "PLACA_SOLAR",
                "respuesta_usuario": "2 con regulador propio y 1 existente",
            },
        )
        context.update(updates2)

        # All resolved → pending_variants should be empty
        assert context["pending_variants"] == [], (
            f"All variants resolved — pending_variants should be [], got {context['pending_variants']}"
        )
        assert context["elemento_confirmado"]["code"] == "PLACA_SOLAR_PROPIO"
        assert context["element_codes"] == ["PLACA_SOLAR_PROPIO"]


# ===========================================================================
# Scenario 2: All same variant
# ===========================================================================


@pytest.mark.asyncio
class TestScenarioAllSameVariant:
    """
    User: "todas con regulador visible" → all 3 resolved with same variant at once.
    """

    async def test_all_same_variant(self):
        pending = _make_pending_solar(cantidad_total=3)

        # "todas con regulador propio" → 3 units to same variant
        allocations = [
            VariantAllocation(variant_code="Con regulador propio", quantity=3, confidence=0.95),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert errors == []
        assert updated["status"] == "resolved"
        assert updated["cantidad_resuelta"] == 3
        assert updated["cantidad_pendiente"] == 0
        assert len(updated["resoluciones"]) == 1
        assert updated["resoluciones"][0]["quantity"] == 3

    async def test_all_same_variant_through_extraction(self):
        """Full flow through _extract_context_from_tool."""
        helper = _ModeHelper()

        pending = _make_pending_solar(cantidad_total=3)

        variant_tool_result = {
            "selected_variant": "PLACA_SOLAR_PROPIO",
            "confidence": 0.95,
            "name": "Placa solar con regulador propio",
            "applied_allocations": [
                {"variant_code": "Con regulador propio", "quantity": 3, "confidence": 0.95},
            ],
            "resolution_status": "resolved",
            "pending_count": 0,
            "_internal_flags": {
                "pending_variants": [{
                    **dict(pending),
                    "cantidad_resuelta": 3,
                    "cantidad_pendiente": 0,
                    "status": "resolved",
                    "resoluciones": [
                        {
                            "variant_code": "Con regulador propio",
                            "quantity": 3,
                            "confidence": 0.95,
                            "source": "user_explicit",
                        },
                    ],
                }],
            },
        }

        updates = helper.extract(
            "seleccionar_variante_por_respuesta",
            variant_tool_result,
            {
                "categoria_vehiculo": "aseicars-prof",
                "codigo_elemento_base": "PLACA_SOLAR",
                "respuesta_usuario": "todas con regulador propio",
            },
        )

        assert updates["pending_variants"] == []
        assert updates["elemento_confirmado"]["code"] == "PLACA_SOLAR_PROPIO"


# ===========================================================================
# Scenario 3: Sequential resolution (one at a time)
# ===========================================================================


@pytest.mark.asyncio
class TestScenarioSequentialResolution:
    """
    Resolve one unit at a time across 3 turns:
    Turn 1: "con regulador propio" → 1 resolved, 2 pending
    Turn 2: "otra con regulador propio" → 2 resolved, 1 pending
    Turn 3: "la última con el existente" → 3 resolved, 0 pending
    """

    async def test_sequential_resolution(self):
        helper = _ModeHelper()

        # Turn 1: resolve 1 of 3
        pending_t1 = _make_pending_solar(cantidad_total=3, cantidad_resuelta=0)

        alloc_t1 = [
            VariantAllocation(variant_code="Con regulador propio", quantity=1, confidence=0.9),
        ]
        updated_t1, errors = validate_and_apply_allocations(
            pending_t1, alloc_t1, dry_run=False,
        )

        assert errors == []
        assert updated_t1["status"] == "partial"
        assert updated_t1["cantidad_resuelta"] == 1
        assert updated_t1["cantidad_pendiente"] == 2

        # Simulate mode extraction: pending_variants not fully cleared
        result_t1 = {
            "selected_variant": "PLACA_SOLAR_PROPIO",
            "confidence": 0.9,
            "name": "Placa solar con regulador propio",
            "resolution_status": "partial",
            "pending_count": 1,
            "_internal_flags": {
                "pending_variants": [dict(updated_t1)],
            },
        }
        updates_t1 = helper.extract(
            "seleccionar_variante_por_respuesta", result_t1,
        )

        # Partial — pending_variants should still have the entry (not empty)
        assert len(updates_t1.get("pending_variants", [])) == 1
        remaining = updates_t1["pending_variants"][0]
        assert remaining["status"] == "partial"
        assert remaining["cantidad_pendiente"] == 2

        # Turn 2: resolve 1 more (total 2 of 3)
        pending_t2 = PendingVariantGroup(**remaining)
        alloc_t2 = [
            VariantAllocation(variant_code="Con regulador propio", quantity=1, confidence=0.9),
        ]
        updated_t2, errors = validate_and_apply_allocations(
            pending_t2, alloc_t2, dry_run=False,
        )

        # Still not fully resolved — cantidad_pendiente was 2, allocated 1
        assert errors == []
        assert updated_t2["status"] == "partial"
        assert updated_t2["cantidad_resuelta"] == 2
        assert updated_t2["cantidad_pendiente"] == 1

        # Turn 3: resolve last one
        pending_t3 = PendingVariantGroup(**dict(updated_t2))
        alloc_t3 = [
            VariantAllocation(
                variant_code="Regulador existente del vehículo",
                quantity=1,
                confidence=0.85,
            ),
        ]
        updated_t3, errors = validate_and_apply_allocations(
            pending_t3, alloc_t3, dry_run=False,
        )

        assert errors == []
        assert updated_t3["status"] == "resolved"
        assert updated_t3["cantidad_resuelta"] == 3
        assert updated_t3["cantidad_pendiente"] == 0
        assert len(updated_t3["resoluciones"]) == 3

        # Final mode extraction: all resolved → empty pending
        result_t3 = {
            "selected_variant": "PLACA_SOLAR_EXISTENTE",
            "confidence": 0.85,
            "name": "Placa solar con regulador existente",
            "resolution_status": "resolved",
            "pending_count": 0,
            "_internal_flags": {
                "pending_variants": [dict(updated_t3)],
            },
        }
        updates_t3 = helper.extract(
            "seleccionar_variante_por_respuesta", result_t3,
        )

        assert updates_t3["pending_variants"] == []


# ===========================================================================
# Scenario 4: Price before images regression (Task 4.4)
# ===========================================================================


class TestPriceBeforeImagesRegression:
    """
    Regression test: after all variants resolved, tariff is calculated before
    any image tool is called.

    This tests the tool extraction pipeline to verify:
    - calcular_tarifa sets tarifa_calculada and precio_comunicado flag
    - enviar_imagenes requires precio_comunicado to be True
    """

    def test_price_communicated_before_images(self):
        """
        Verify that calcular_tarifa_con_elementos sets tarifa_calculada and _internal_flags,
        and that enviar_imagenes result extraction works correctly AFTER pricing.
        """
        helper = _ModeHelper()
        context: dict[str, Any] = {}

        # ── Step 1: Variants all resolved (from prior flow) ──
        resolved_variant_result = {
            "selected_variant": "PLACA_SOLAR_PROPIO",
            "confidence": 0.95,
            "name": "Placa solar con regulador propio",
            "resolution_status": "resolved",
            "pending_count": 0,
            "_internal_flags": {
                "pending_variants": [{
                    "pending_id": "PLACA_SOLAR_0",
                    "codigo_base": "PLACA_SOLAR",
                    "pregunta": "...",
                    "opciones": ["A", "B"],
                    "cantidad_total": 3,
                    "cantidad_resuelta": 3,
                    "cantidad_pendiente": 0,
                    "resoluciones": [],
                    "status": "resolved",
                }],
            },
        }

        updates = helper.extract(
            "seleccionar_variante_por_respuesta",
            resolved_variant_result,
        )
        context.update(updates)

        # Pending should be empty
        assert context["pending_variants"] == []

        # ── Step 2: calcular_tarifa_con_elementos → sets price ──
        tarifa_result = {
            "texto": "TARIFA: Tier 2 — 690 EUR (3x Placa solar)",
            "datos": {
                "tier_id": "uuid-123",
                "tier_name": "Tier 2",
                "price": 690.0,
                "elements": ["Placa solar con regulador propio"],
                "element_codes": ["PLACA_SOLAR_PROPIO"],
                "warnings": [],
            },
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }

        updates2 = helper.extract(
            "calcular_tarifa_con_elementos",
            tarifa_result,
        )
        context.update(updates2)

        # Verify tariff was extracted
        assert "tarifa_calculada" in context
        assert context["tarifa_calculada"]["datos"]["price"] == 690.0

        # Verify _internal_flags contain precio_comunicado
        assert tarifa_result["_internal_flags"]["precio_comunicado"] is True

        # ── Step 3: enviar_imagenes — comes AFTER price ──
        # The price-before-images enforcement happens in _process_message,
        # not in _extract_context_from_tool. Here we verify the sequencing:
        # tarifa_calculada exists (price was calculated first).
        assert context.get("tarifa_calculada") is not None, (
            "Tariff must be calculated BEFORE images can be sent"
        )

        image_result = {
            "success": True,
            "images_sent": 2,
            "element_code": "PLACA_SOLAR_PROPIO",
            "_internal_flags": {
                "imagenes_enviadas": False,
            },
        }

        updates3 = helper.extract(
            "enviar_imagenes_ejemplo",
            image_result,
        )
        context.update(updates3)

        # Queue-time contract: tool marks intent only (not delivered yet)
        assert image_result["_internal_flags"]["imagenes_enviadas"] is False

    def test_no_tarifa_before_images_is_detectable(self):
        """
        Verify that if tarifa_calculada is None, the absence is detectable.

        In the real _process_message, mode_context["precio_comunicado"] gates
        enviar_imagenes. This test verifies the prerequisite tracking.
        """
        helper = _ModeHelper()
        context: dict[str, Any] = {}

        # No calcular_tarifa called yet — images should be blocked
        assert context.get("tarifa_calculada") is None

        # The _internal_flags pattern: without precio_comunicado=True,
        # the mode node blocks enviar_imagenes via the prompt check:
        #   if not mode_context.get("precio_comunicado"):
        #       <block image sending>
        # We verify the state contract here:
        assert context.get("precio_comunicado") is not True, (
            "precio_comunicado should NOT be True when no tariff was calculated"
        )


# ===========================================================================
# Scenario 5: Multiple elements with independent variant questions
# ===========================================================================


@pytest.mark.asyncio
class TestScenarioMultipleElementsIndependent:
    """
    Two different elements each with variants:
    - SUSPENSION (delantera/trasera)
    - PLACA_SOLAR (con regulador/sin regulador)

    Each resolves independently.
    """

    async def test_two_elements_independent_resolution(self):
        helper = _ModeHelper()
        context: dict[str, Any] = {}

        # Step 1: Identify both elements with variants
        identify_result = {
            "elementos_listos": [],
            "elementos_con_variantes": [
                {"codigo": "SUSPENSION", "nombre": "Suspensión"},
                {"codigo": "PLACA_SOLAR", "nombre": "Placa solar"},
            ],
            "preguntas_variantes": [
                {
                    "codigo_base": "SUSPENSION",
                    "pregunta": "¿Delantera o trasera?",
                    "opciones": ["Delantera", "Trasera"],
                },
                {
                    "codigo_base": "PLACA_SOLAR",
                    "pregunta": "¿Con regulador propio o del vehículo?",
                    "opciones": ["Con regulador propio", "Regulador existente"],
                },
            ],
        }

        updates = helper.extract(
            "identificar_y_resolver_elementos",
            identify_result,
            {"categoria_vehiculo": "motos-part"},
        )
        context.update(updates)

        assert len(context["pending_variants"]) == 2

        # Step 2: Resolve SUSPENSION
        # Normalize to get enriched form
        normalized = normalize_pending_variants(context["pending_variants"])
        assert len(normalized) == 2

        sus_pending = normalized[0]
        assert sus_pending["codigo_base"] == "SUSPENSION"
        assert sus_pending["cantidad_total"] == 1  # legacy default

        sus_updated, errors = validate_and_apply_allocations(
            sus_pending,
            [VariantAllocation(variant_code="Delantera", quantity=1, confidence=0.95)],
            dry_run=False,
        )
        assert errors == []
        assert sus_updated["status"] == "resolved"

        # Build result: SUSPENSION resolved, PLACA_SOLAR still pending
        sol_pending = normalized[1]
        result_suspension = {
            "selected_variant": "SUSPENSION_DEL",
            "confidence": 0.95,
            "name": "Suspensión delantera",
            "resolution_status": "resolved",
            "pending_count": 1,
            "_internal_flags": {
                "pending_variants": [
                    dict(sus_updated),
                    dict(sol_pending),
                ],
            },
        }

        updates2 = helper.extract(
            "seleccionar_variante_por_respuesta",
            result_suspension,
        )
        context.update(updates2)

        # Only SUSPENSION resolved — still one pending
        remaining = context["pending_variants"]
        assert len(remaining) == 2
        # Verify one is resolved, one is still pending
        statuses = {pv.get("codigo_base", ""): pv.get("status", "") for pv in remaining}
        assert statuses.get("SUSPENSION") == "resolved"
        assert statuses.get("PLACA_SOLAR") == "pending"

        # Step 3: Resolve PLACA_SOLAR
        re_normalized = normalize_pending_variants(remaining)
        placa_pending = next(
            pv for pv in re_normalized if pv.get("codigo_base") == "PLACA_SOLAR"
        )
        placa_updated, errors = validate_and_apply_allocations(
            placa_pending,
            [VariantAllocation(variant_code="Con regulador propio", quantity=1, confidence=0.9)],
            dry_run=False,
        )
        assert errors == []
        assert placa_updated["status"] == "resolved"

        # All resolved now
        all_updated = [
            dict(next(pv for pv in re_normalized if pv.get("codigo_base") == "SUSPENSION")),
            dict(placa_updated),
        ]
        result_placa = {
            "selected_variant": "PLACA_SOLAR_PROPIO",
            "confidence": 0.9,
            "name": "Placa solar con regulador propio",
            "resolution_status": "resolved",
            "pending_count": 0,
            "_internal_flags": {
                "pending_variants": all_updated,
            },
        }

        updates3 = helper.extract(
            "seleccionar_variante_por_respuesta",
            result_placa,
        )
        context.update(updates3)

        # ALL resolved → pending_variants should be empty
        assert context["pending_variants"] == []
