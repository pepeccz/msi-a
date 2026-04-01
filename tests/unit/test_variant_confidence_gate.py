"""
RED-phase tests for fix-element-data-tools-fsm-state — Bare-letter confidence gate.

Bug (REQ-3): When `seleccionar_variante_por_respuesta` processes a fragment via
the LLM interpretation service, the bare-letter guard at element_tools.py:1254
maps the bare letter to a positional variant even when the LLM's average
confidence in that allocation is very low (e.g., 0.07).

This means a user typing "sí" can cause the LLM to hallucinate "a" as the
allocation code, and the system will silently commit to variant position 1 —
even if the element in question has nothing to do with gálibo vocabulary.

Expected behavior (after Phase 3 fix):
- If avg_confidence < 0.3 when a bare-letter positional fallback is used,
  return needs_clarification=True instead of committing the variant.
- If the fragment contains gálibo/ancho domain vocabulary, bare-letter mapping
  is still allowed (domain confirmation overrides low confidence).
- If avg_confidence >= 0.3, the variant is committed normally.

These tests FAIL today (RED phase) because the confidence gate does not exist
yet. They will pass after the Phase 3 fix.

Tasks covered: 1.4, 1.5, 1.6 from the SDD tasks artifact.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_variant(
    code: str,
    name: str,
    variant_position: int,
    keywords: list[str] | None = None,
    variant_code: str | None = None,
) -> dict:
    """Build a minimal variant dict (as returned by element_service.get_element_variants)."""
    return {
        "code": code,
        "name": name,
        "variant_position": variant_position,
        "keywords": keywords or [],
        "variant_code": variant_code or code.lower(),
        "parent_element_id": "some-parent-id",  # marks it as a variant (not base)
    }


def _make_pending_variant_group(
    codigo_base: str = "TOLDO",
    opciones: list[str] | None = None,
    cantidad_pendiente: int = 1,
) -> dict:
    """Build a minimal PendingVariantGroup dict."""
    opciones = opciones or ["Tipo A - Sin gálibo", "Tipo B - Con gálibo"]
    return {
        "pending_id": str(uuid.uuid4()),
        "codigo_base": codigo_base,
        "pregunta": f"¿Qué tipo de {codigo_base} quieres?",
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
    """Build a minimal ConversationState with a pending variant group."""
    return {
        "current_mode": current_mode,
        "mode_context": {
            "pending_variants": [pending],
            "categoria_slug": "motos-part",
            "element_codes": [pending["codigo_base"]],
            "elementos_confirmados": [pending["codigo_base"]],
        },
    }


def _low_confidence_interpretation(
    variant_code: str = "a",
) -> VariantInterpretationResult:
    """Build a VariantInterpretationResult with very low confidence (below gate threshold)."""
    return VariantInterpretationResult(
        allocations=[
            VariantAllocation(
                variant_code=variant_code,
                quantity=1,
                confidence=0.07,  # Very low — below the 0.3 gate
            )
        ],
        needs_clarification=False,
        clarification_reason=None,
        raw_response='{"allocations": [{"variant_code": "a", "quantity": 1, "confidence": 0.07}]}',
    )


def _high_confidence_interpretation(
    variant_code: str = "a",
) -> VariantInterpretationResult:
    """Build a VariantInterpretationResult with high confidence (above gate threshold)."""
    return VariantInterpretationResult(
        allocations=[
            VariantAllocation(
                variant_code=variant_code,
                quantity=1,
                confidence=0.85,  # High — above the 0.3 gate
            )
        ],
        needs_clarification=False,
        clarification_reason=None,
        raw_response='{"allocations": [{"variant_code": "a", "quantity": 1, "confidence": 0.85}]}',
    )


def _make_toldo_variants() -> list[dict]:
    """Build variants for a hypothetical TOLDO element (no gálibo vocabulary in Tipo A)."""
    return [
        _make_variant(
            "TOLDO_A",
            "Tipo A - Sin gálibo",
            variant_position=1,
            keywords=["sin galibo", "tipo a"],
        ),
        _make_variant(
            "TOLDO_B",
            "Tipo B - Con gálibo",
            variant_position=2,
            keywords=["con galibo", "galibo", "tipo b"],
        ),
    ]


def _make_base_element_mock(code: str = "TOLDO") -> dict:
    """Build a minimal base element dict."""
    return {
        "code": code,
        "name": code.capitalize(),
        "parent_element_id": None,
        "multi_select_keywords": [],
        "keywords": [],
    }


def _build_seleccionar_patches(
    state: dict,
    variants: list[dict],
    interpretation_result: VariantInterpretationResult,
    categoria_slug: str = "motos-part",
    base_element: dict | None = None,
) -> list:
    """
    Build the set of patches needed to isolate seleccionar_variante_por_respuesta
    from all I/O (DB, settings, current state).

    Returns a list of context manager patches.
    """
    category_id = str(uuid.uuid4())
    base_element = base_element or _make_base_element_mock()

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


# ---------------------------------------------------------------------------
# T4 — Low confidence + no domain vocabulary → needs_clarification=True
# ---------------------------------------------------------------------------


class TestLowConfidenceBareLetterReturnsNeedsClarification:
    """
    T4 — When the LLM interpretation returns a bare letter ("a") as the
    allocation code, the positional fallback is found (position 1 exists),
    BUT the average confidence is below 0.3 AND the fragment contains no
    gálibo-related vocabulary.

    Expected (after fix): return needs_clarification=True, NO variant committed.

    THIS TEST FAILS TODAY (RED phase) because the confidence gate does not
    exist — the system auto-commits to the positional fallback regardless of
    confidence.
    """

    @pytest.mark.asyncio
    async def test_low_confidence_no_domain_vocab_returns_clarification(self):
        """
        Given:  Fragment "sí" (no gálibo vocabulary)
                LLM interpretation returns "a" with confidence=0.07
                TOLDO element has positional variant at position 1
        When:   seleccionar_variante_por_respuesta is called
        Then:   result contains needs_clarification=True
                NO variant is auto-selected with the bare letter code

        BUG today: The system maps "a" → position 1 → TOLDO_A and commits.
        Expected: The gate fires, returning needs_clarification=True.
        """
        toldo_variants = _make_toldo_variants()
        pending = _make_pending_variant_group("TOLDO", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)
        low_conf_result = _low_confidence_interpretation("a")

        patches = _build_seleccionar_patches(state, toldo_variants, low_conf_result)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            result = await func(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="TOLDO",
                respuesta_usuario="sí",
            )

        assert isinstance(result, dict), "Must return a dict."
        assert result.get("needs_clarification") is True, (
            "Low-confidence bare-letter mapping (0.07 < 0.3) with no domain vocabulary "
            "must return needs_clarification=True. "
            f"Got: {result}"
        )

    @pytest.mark.asyncio
    async def test_low_confidence_does_not_emit_bare_letter_mapped_log(self, caplog):
        """
        Given:  Low confidence (0.07) interpretation returning bare letter "a"
        When:   seleccionar_variante_por_respuesta runs
        Then:   The 'seleccionar_variante_bare_letter_mapped' log event is NOT emitted.
                (It's only emitted when mapping actually proceeds, not when the gate rejects.)

        THIS TEST FAILS TODAY (RED) because the gate doesn't exist — the
        'seleccionar_variante_bare_letter_mapped' event IS emitted at line 1256.
        """
        import logging

        toldo_variants = _make_toldo_variants()
        pending = _make_pending_variant_group("TOLDO", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)
        low_conf_result = _low_confidence_interpretation("a")

        patches = _build_seleccionar_patches(state, toldo_variants, low_conf_result)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            caplog.at_level(logging.DEBUG),
        ):
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            await func(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="TOLDO",
                respuesta_usuario="sí",
            )

        # The "bare_letter_mapped" event must NOT appear in logs when gate rejects
        emitted_events = [r.getMessage() for r in caplog.records]
        bare_letter_mapped_logged = any(
            "bare_letter_mapped" in msg for msg in emitted_events
        )
        assert not bare_letter_mapped_logged, (
            "seleccionar_variante_bare_letter_mapped must NOT be logged when the "
            "confidence gate rejects the low-confidence allocation. "
            f"Log records found: {emitted_events[:5]}"
        )


# ---------------------------------------------------------------------------
# T5 — Sufficient confidence (>= 0.3) → normal variant committed
# ---------------------------------------------------------------------------


class TestSufficientConfidenceProceedsNormally:
    """
    T5 — When confidence >= 0.3, the bare-letter positional fallback
    should proceed and a variant should be committed (no clarification needed).

    This validates that the confidence gate is not over-broad — it only blocks
    very-low-confidence selections.
    """

    @pytest.mark.asyncio
    async def test_high_confidence_bare_letter_commits_variant(self):
        """
        Given:  Fragment "a" (bare letter)
                LLM interpretation returns "a" with confidence=0.85
                TOLDO element has positional variant at position 1
        When:   seleccionar_variante_por_respuesta is called
        Then:   result does NOT contain needs_clarification=True
                A variant is selected (selected_variant is set)

        This is the normal path — high confidence allows bare-letter mapping.
        """
        toldo_variants = _make_toldo_variants()
        pending = _make_pending_variant_group("TOLDO", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)
        high_conf_result = _high_confidence_interpretation("a")

        patches = _build_seleccionar_patches(state, toldo_variants, high_conf_result)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            result = await func(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="TOLDO",
                respuesta_usuario="a",
            )

        assert isinstance(result, dict)
        # High confidence should NOT trigger clarification
        assert result.get("needs_clarification") is not True, (
            "High confidence (0.85 >= 0.3) bare-letter mapping should NOT trigger "
            "needs_clarification. "
            f"Got: {result}"
        )
        # A variant should be selected
        assert "selected_variant" in result or result.get("success", False), (
            "High confidence bare-letter mapping should result in a selected variant. "
            f"Got: {result}"
        )


# ---------------------------------------------------------------------------
# T6 — Low score but domain vocabulary match → bare_letter IS allowed
# ---------------------------------------------------------------------------


class TestDomainVocabOverridesLowConfidence:
    """
    T6 — When the fragment contains explicit gálibo/ancho domain vocabulary,
    bare-letter mapping proceeds even if avg_confidence < 0.3.

    Rationale: Domain vocabulary confirms the user's intent — the low confidence
    is about format, not about meaning. If the user says "galibo a" and the
    LLM maps "a" with low confidence, we know they meant option A related to gálibo.

    This test documents the DESIRED behavior after Phase 3 fix.
    It will FAIL today since there is no gate (and no domain vocab check),
    though it might coincidentally pass because the current code auto-commits.
    After fix, the gate must have a domain-vocabulary exception.
    """

    @pytest.mark.asyncio
    async def test_galibo_fragment_allows_bare_letter_despite_low_confidence(self):
        """
        Given:  Fragment "galibo b" (contains gálibo domain keyword)
                LLM interpretation returns "b" with confidence=0.2
                TOLDO element has "galibo" in variant B keywords
        When:   seleccionar_variante_por_respuesta is called
        Then:   result does NOT contain needs_clarification=True
                The bare-letter mapping proceeds (domain match overrides gate)

        TODAY: This may auto-commit WITHOUT the gate. But we write the test to
        document that this case should ALWAYS proceed, even after the gate is
        added (gálibo vocabulary acts as an override).
        """
        toldo_variants = _make_toldo_variants()
        pending = _make_pending_variant_group("TOLDO", cantidad_pendiente=1)
        state = _make_state_with_pending_variant(pending)

        galibo_low_conf = VariantInterpretationResult(
            allocations=[
                VariantAllocation(
                    variant_code="b",  # "b" maps to position 2 = "Con gálibo"
                    quantity=1,
                    confidence=0.2,  # Low confidence but domain vocab present
                )
            ],
            needs_clarification=False,
            clarification_reason=None,
        )

        patches = _build_seleccionar_patches(state, toldo_variants, galibo_low_conf)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            func = et_module.seleccionar_variante_por_respuesta.coroutine
            result = await func(
                categoria_vehiculo="motos-part",
                codigo_elemento_base="TOLDO",
                respuesta_usuario="galibo b",  # Fragment contains domain vocabulary
            )

        assert isinstance(result, dict)
        # Domain vocab present → gate should NOT fire even with low confidence
        assert result.get("needs_clarification") is not True, (
            "When the user's fragment contains domain vocabulary ('galibo'), "
            "bare-letter mapping should be allowed regardless of confidence. "
            f"Got: {result}"
        )
