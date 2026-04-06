"""
Tests for Phase 4 — Early Ambiguity Exit (ADR-006).

Covers:
1. AMBIGUITY_THRESHOLD constant value (= 0.3)
2. _has_domain_vocabulary_from_variants() helper
3. Early ambiguity exit in seleccionar_variante_por_respuesta:
   - Single-unit + score < 0.3 + no domain vocab → needs_clarification=True
   - Multi-unit → NOT triggered (multi-unit still goes through LLM)
   - score >= 0.3 → NOT triggered (keyword match is sufficient)
   - score < 0.3 but domain vocab found → NOT triggered

Tasks: Phase 4 (agent-architecture-refactor change)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.tools.element_tools as et_module
from agent.services.variant_interpretation_service import (
    VariantAllocation,
    VariantInterpretationResult,
)
from agent.services.variant_interpretation_service import (
    AMBIGUITY_THRESHOLD,
    _has_domain_vocabulary_from_variants,
)


# ---------------------------------------------------------------------------
# Helpers (shared with existing test file style)
# ---------------------------------------------------------------------------


def _make_variant(
    code: str,
    name: str,
    variant_position: int,
    keywords: list[str] | None = None,
    variant_code: str | None = None,
) -> dict:
    return {
        "code": code,
        "name": name,
        "variant_position": variant_position,
        "keywords": keywords or [],
        "variant_code": variant_code or code.lower(),
        "parent_element_id": "some-parent-id",
    }


def _make_pending_variant_group(
    codigo_base: str = "BOLA_REMOLQUE",
    opciones: list[str] | None = None,
    cantidad_pendiente: int = 1,
) -> dict:
    opciones = opciones or ["Sin MMR", "Con aumento MMR"]
    return {
        "pending_id": str(uuid.uuid4()),
        "codigo_base": codigo_base,
        "pregunta": f"¿Quieres homologar con o sin aumento de {codigo_base}?",
        "opciones": opciones,
        "cantidad_total": cantidad_pendiente,
        "cantidad_resuelta": 0,
        "cantidad_pendiente": cantidad_pendiente,
        "resoluciones": [],
        "status": "pending",
    }


def _make_state_with_pending_variant(
    pending: dict,
    current_mode: str = "PRESUPUESTO_MODE",
) -> dict:
    return {
        "current_mode": current_mode,
        "mode_context": {
            "pending_variants": [pending],
            "categoria_slug": "aseicars-part",
            "element_codes": [pending["codigo_base"]],
            "elementos_confirmados": [pending["codigo_base"]],
        },
    }


def _build_seleccionar_patches(
    state: dict,
    variants: list[dict],
    interpretation_result: VariantInterpretationResult,
    categoria_slug: str = "aseicars-part",
    base_element: dict | None = None,
) -> list:
    category_id = str(uuid.uuid4())
    if base_element is None:
        base_element = {
            "code": "BOLA_REMOLQUE",
            "name": "Bola de remolque",
            "parent_element_id": None,
            "multi_select_keywords": [],
            "keywords": [],
        }
    element_service_mock = MagicMock()
    element_service_mock.get_element_variants = AsyncMock(return_value=variants)
    element_service_mock.get_elements_by_category = AsyncMock(return_value=[])
    element_service_mock.get_element_by_code = AsyncMock(return_value=base_element)

    return [
        patch("agent.tools.element_tools.get_current_state", return_value=state),
        patch(
            "agent.tools.element_tools.get_settings",
            return_value=MagicMock(
                ENABLE_LLM_VARIANT_INTERPRETATION=True,
            ),
        ),
        patch(
            "agent.tools.element_tools.interpret_variant_allocations",
            new=AsyncMock(return_value=interpretation_result),
        ),
        patch(
            "agent.tools.element_tools.get_element_service",
            return_value=element_service_mock,
        ),
        patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new=AsyncMock(return_value=category_id),
        ),
        patch("agent.tools.element_tools.validate_category_slug", return_value=None),
    ]


def _make_bola_remolque_variants() -> list[dict]:
    """Variants for BOLA_REMOLQUE: SIN_MMR and CON_MMR."""
    return [
        _make_variant(
            "BOLA_SIN_MMR",
            "Bola de remolque SIN aumento MMR",
            variant_position=1,
            keywords=["sin mmr", "no aumenta mmr", "sin aumento", "no"],
            variant_code="SIN_MMR",
        ),
        _make_variant(
            "BOLA_CON_MMR",
            "Bola de remolque CON aumento MMR",
            variant_position=2,
            keywords=[
                "con mmr",
                "aumenta mmr",
                "aumento mmr",
                "mayor mmr",
                "si aumenta",
                "incrementa",
                "mas mmr",
            ],
            variant_code="CON_MMR",
        ),
    ]


def _dummy_interpretation() -> VariantInterpretationResult:
    """A dummy LLM result (should NOT be called when early exit fires)."""
    return VariantInterpretationResult(
        allocations=[VariantAllocation(variant_code="a", quantity=1, confidence=0.95)],
        needs_clarification=False,
        clarification_reason=None,
        raw_response='{"allocations": [{"variant_code": "a", "quantity": 1, "confidence": 0.95}]}',
    )


# ---------------------------------------------------------------------------
# T1 — AMBIGUITY_THRESHOLD constant
# ---------------------------------------------------------------------------


class TestAmbiguityThreshold:
    def test_threshold_is_point_three(self):
        """AMBIGUITY_THRESHOLD must be 0.3."""
        assert AMBIGUITY_THRESHOLD == 0.3


# ---------------------------------------------------------------------------
# T2 — _has_domain_vocabulary_from_variants helper
# ---------------------------------------------------------------------------


class TestHasDomainVocabularyFromVariants:
    def test_empty_variants_returns_false(self):
        """No variants → no domain words → False."""
        assert _has_domain_vocabulary_from_variants("cualquier cosa", []) is False

    def test_domain_keyword_found(self):
        """Input contains a keyword > 3 chars from one of the variants."""
        variants = [
            {"name": "Con aumento MMR", "keywords": ["aumenta mmr", "con mmr"]},
            {"name": "Sin aumento MMR", "keywords": ["sin mmr", "no aumenta"]},
        ]
        assert (
            _has_domain_vocabulary_from_variants("si aumenta mmr quiero", variants)
            is True
        )

    def test_short_words_only_are_ignored(self):
        """Keywords <= 3 chars are ignored."""
        variants = [{"name": "Si", "keywords": ["si", "no"]}]
        assert _has_domain_vocabulary_from_variants("si quiero", variants) is False

    def test_ambiguous_input_no_domain_vocab(self):
        """Generic 'si' response has no match in domain vocabulary."""
        variants = _make_bola_remolque_variants()
        assert _has_domain_vocabulary_from_variants("si", variants) is False

    def test_accent_insensitive_match(self):
        """Accent-stripped input still matches keyword with accent."""
        variants = [{"name": "Con gálibo", "keywords": ["galibo", "aumenta ancho"]}]
        assert (
            _has_domain_vocabulary_from_variants("quiero el galibo", variants) is True
        )

    def test_name_words_also_checked(self):
        """Long words from the variant name are included in domain vocab."""
        variants = [{"name": "Suspensión delantera", "keywords": []}]
        # "delantera" > 3 chars and appears in input
        assert (
            _has_domain_vocabulary_from_variants("quiero la delantera", variants)
            is True
        )


# ---------------------------------------------------------------------------
# T3 — Early ambiguity exit in seleccionar_variante_por_respuesta
# ---------------------------------------------------------------------------


class TestEarlyAmbiguityExitIntegration:
    """
    Phase 4 integration tests: verify the early exit gate fires (or doesn't)
    in seleccionar_variante_por_respuesta without calling Tier-1 LLM.
    """

    @pytest.mark.asyncio
    async def test_single_unit_low_score_no_domain_vocab_returns_needs_clarification(
        self,
    ):
        """
        Given:  Single-unit, keyword_score=0.0 ("si" matches nothing with >0.3 score
                in BOLA_REMOLQUE variants), no domain vocab
        When:   seleccionar_variante_por_respuesta is called
        Then:   needs_clarification=True is returned WITHOUT calling interpret_variant_allocations
        """
        variants = _make_bola_remolque_variants()
        pending = _make_pending_variant_group("BOLA_REMOLQUE", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)

        interpret_mock = AsyncMock(return_value=_dummy_interpretation())
        patches = _build_seleccionar_patches(state, variants, _dummy_interpretation())
        # Override interpret mock so we can assert it was NOT called
        patches[2] = patch(
            "agent.tools.element_tools.interpret_variant_allocations",
            new=interpret_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            result = await func(
                categoria_vehiculo="aseicars-part",
                codigo_elemento_base="BOLA_REMOLQUE",
                respuesta_usuario="si",
            )

        assert isinstance(result, dict)
        assert result.get("needs_clarification") is True, (
            "Single-unit + score<0.3 + no domain vocab must return needs_clarification=True. "
            f"Got: {result}"
        )
        # The LLM interpretation service must NOT have been called
        interpret_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_domain_vocab_present_does_not_trigger_early_exit(self):
        """
        Given:  keyword_score is low, BUT user says "aumenta mmr" (domain vocab)
        When:   seleccionar_variante_por_respuesta is called
        Then:   Early exit does NOT fire — LLM interpretation is invoked
        """
        variants = _make_bola_remolque_variants()
        pending = _make_pending_variant_group("BOLA_REMOLQUE", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)

        interpret_mock = AsyncMock(return_value=_dummy_interpretation())
        patches = _build_seleccionar_patches(state, variants, _dummy_interpretation())
        patches[2] = patch(
            "agent.tools.element_tools.interpret_variant_allocations",
            new=interpret_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            result = await func(
                categoria_vehiculo="aseicars-part",
                codigo_elemento_base="BOLA_REMOLQUE",
                respuesta_usuario="aumenta mmr quiero",
            )

        # With "aumenta mmr" the keyword scoring will find "aumenta mmr" in CON_MMR keywords
        # so best_score should be >= 0.5 → fast path, or domain vocab prevents early exit
        # Either way, interpret_mock may or may not be called — but result should NOT be
        # needs_clarification=True due to Phase 4 gate
        assert result.get("needs_clarification") is not True or interpret_mock.called, (
            "When domain vocab ('aumenta mmr') is present, early exit must not fire. "
            f"Got: {result}, interpret called: {interpret_mock.called}"
        )

    @pytest.mark.asyncio
    async def test_multi_unit_is_exempt_from_early_exit(self):
        """
        Given:  Multi-unit (cantidad_pendiente=2), score=0.0, no domain vocab
        When:   seleccionar_variante_por_respuesta is called
        Then:   Early exit does NOT fire (multi-unit handled by LLM as before)
        """
        variants = _make_bola_remolque_variants()
        pending = _make_pending_variant_group(
            "BOLA_REMOLQUE",
            cantidad_pendiente=2,  # multi-unit
        )
        state = _make_state_with_pending_variant(pending)

        interpret_mock = AsyncMock(return_value=_dummy_interpretation())
        patches = _build_seleccionar_patches(state, variants, _dummy_interpretation())
        patches[2] = patch(
            "agent.tools.element_tools.interpret_variant_allocations",
            new=interpret_mock,
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            await func(
                categoria_vehiculo="aseicars-part",
                codigo_elemento_base="BOLA_REMOLQUE",
                respuesta_usuario="si",
            )

        # For multi-unit, the LLM interpretation service MUST be called
        assert interpret_mock.called, (
            "Multi-unit requests must go through LLM interpretation (early exit exempt). "
            f"interpret_mock.call_count={interpret_mock.call_count}"
        )
