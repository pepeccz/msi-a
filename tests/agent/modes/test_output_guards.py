"""
Unit tests for PRE_EXPEDIENTE output guard pipeline.

Spec reference: pre-expediente-output-guards spec (engram #4417)
Design reference: pre-expediente-output-guards design (engram #4418)

Each test corresponds to one spec scenario. Tests are RED-first per Strict TDD.
All guards are pure functions: (text, mode_context, ...) -> str.

Test style mirrors test_tariff_gate_self_heal.py:
  - _MODULE constant for module-level patches
  - node._logger = MagicMock() for log assertions
  - mode_context dicts built inline (no fixtures)
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

_MODULE = "agent.modes.pre_expediente_mode"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mc_images_sent(*codes: str) -> dict:
    """mode_context with imagenes_enviadas_codigos populated (images delivered)."""
    return {"imagenes_enviadas_codigos": list(codes)}


def _mc_images_not_sent() -> dict:
    """mode_context with imagenes_enviadas_codigos empty (no images sent yet)."""
    return {"imagenes_enviadas_codigos": []}


_CANONICAL_IMAGE_PHRASE = "Ya tienes los ejemplos arriba."


# ---------------------------------------------------------------------------
# T-1: guard_image_send_truth — RED tests (5 scenarios from spec S1-1..S1-5)
# ---------------------------------------------------------------------------


class TestGuardImageSendTruth:
    """
    Unit tests for guard_image_send_truth(text, mc) -> str.

    Design AD-3: paragraph-level keyword co-occurrence detection.
    Design AD-5: strip offending paragraph + append canonical phrase.
    """

    def test_strips_failure_paragraph_wording_a(self):
        """
        S1-1: GIVEN images sent, WHEN LLM emits failure paragraph wording A,
        THEN paragraph is stripped AND canonical phrase appended.
        """
        from agent.modes.pre_expediente_mode import guard_image_send_truth

        text = (
            "Aquí tienes la información que necesitas.\n\n"
            "Ha habido un problema técnico con el envío de las imágenes.\n\n"
            "¿Tienes alguna pregunta?"
        )
        mc = _mc_images_sent("SUBCHASIS")

        result = guard_image_send_truth(text, mc)

        assert _CANONICAL_IMAGE_PHRASE in result, (
            f"S1-1: canonical phrase must appear in result. Got: {result!r}"
        )
        assert "Ha habido un problema técnico" not in result, (
            f"S1-1: failure paragraph must be stripped. Got: {result!r}"
        )

    def test_strips_failure_paragraph_wording_b(self):
        """
        S1-2: GIVEN images sent, WHEN LLM emits failure paragraph wording B,
        THEN paragraph is stripped AND canonical phrase appended.
        """
        from agent.modes.pre_expediente_mode import guard_image_send_truth

        text = (
            "Perfecto, ya tienes el presupuesto.\n\n"
            "Hubo un fallo en el envío de los ejemplos.\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_images_sent("MOTOR")

        result = guard_image_send_truth(text, mc)

        assert _CANONICAL_IMAGE_PHRASE in result, (
            f"S1-2: canonical phrase must appear in result. Got: {result!r}"
        )
        assert "Hubo un fallo" not in result, (
            f"S1-2: failure paragraph must be stripped. Got: {result!r}"
        )

    def test_no_fire_clean_text(self):
        """
        S1-3: GIVEN images sent, WHEN text references images WITHOUT negative keywords,
        THEN text is unchanged AND guard does NOT fire.
        """
        from agent.modes.pre_expediente_mode import guard_image_send_truth

        text = "Ya tienes los ejemplos de homologación. ¿Quieres proceder?"
        mc = _mc_images_sent("SUBCHASIS")

        result = guard_image_send_truth(text, mc)

        assert result == text, (
            f"S1-3: clean text must pass through unchanged. Got: {result!r}"
        )

    def test_no_fire_images_not_sent(self):
        """
        S1-4: GIVEN images NOT sent, WHEN text mentions image delivery problems,
        THEN text is unchanged AND guard does NOT fire.
        """
        from agent.modes.pre_expediente_mode import guard_image_send_truth

        text = (
            "Ha habido un problema técnico con el envío de las imágenes. "
            "Lo resolveremos pronto."
        )
        mc = _mc_images_not_sent()

        result = guard_image_send_truth(text, mc)

        assert result == text, (
            f"S1-4: guard must NOT fire when imagenes_enviadas_codigos is empty. "
            f"Got: {result!r}"
        )

    def test_no_fire_false_positive_separate_paragraphs(self):
        """
        S1-5: GIVEN text contains 'imagen' and 'problema' in SEPARATE paragraphs,
        THEN text is unchanged (AD-4 false-positive defense).
        """
        from agent.modes.pre_expediente_mode import guard_image_send_truth

        text = (
            "Para la homologación necesitas una imagen del vehículo.\n\n"
            "El problema de documentación es habitual en estos casos.\n\n"
            "¿Tienes alguna duda?"
        )
        mc = _mc_images_sent("SUBCHASIS")

        result = guard_image_send_truth(text, mc)

        assert result == text, (
            f"S1-5: guard must NOT fire when keywords are in separate paragraphs. "
            f"Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# T-4: guard_no_premature_price — RED tests (3 scenarios from spec S2-1..S2-3)
# ---------------------------------------------------------------------------


def _mc_no_price_no_tariff() -> dict:
    """mode_context: no price communicated, no tariff calculated."""
    return {"precio_comunicado": False, "tarifa_calculada": None}


def _mc_tariff_calculated() -> dict:
    """mode_context: tariff has been legitimately calculated."""
    return {"precio_comunicado": False, "tarifa_calculada": {"total": 410}}


class TestGuardNoPrematurePrice:
    """
    Unit tests for guard_no_premature_price(text, mc) -> str.

    Design AD-3: sentence-level strip (split on '. ').
    Design AD-5: strip only; no canonical replacement appended.
    Spec S2-1..S2-3.
    """

    def test_strips_price_sentence(self):
        """
        S2-1: GIVEN precio_comunicado=False AND tarifa_calculada empty,
        WHEN outbound text contains "El precio es 410€.",
        THEN that sentence is stripped AND guard fires.
        """
        from agent.modes.pre_expediente_mode import guard_no_premature_price

        text = (
            "Aquí tienes la información sobre el proceso. "
            "El precio es 410€. "
            "¿Tienes alguna pregunta?"
        )
        mc = _mc_no_price_no_tariff()

        result = guard_no_premature_price(text, mc)

        assert "410€" not in result, (
            f"S2-1: price sentence must be stripped. Got: {result!r}"
        )
        assert "Aquí tienes la información" in result, (
            f"S2-1: non-price content must be preserved. Got: {result!r}"
        )

    def test_no_fire_tariff_calculated(self):
        """
        S2-2: GIVEN tarifa_calculada is non-empty,
        WHEN outbound text contains "410€",
        THEN text is unchanged AND guard does NOT fire.
        """
        from agent.modes.pre_expediente_mode import guard_no_premature_price

        text = "El presupuesto es 410€ más IVA. ¿Lo aprobamos?"
        mc = _mc_tariff_calculated()

        result = guard_no_premature_price(text, mc)

        assert result == text, (
            f"S2-2: guard must NOT fire when tarifa_calculada is set. Got: {result!r}"
        )

    def test_strips_multiple_price_sentences_preserves_rest(self):
        """
        S2-3: GIVEN precio_comunicado=False AND tarifa_calculada empty,
        WHEN outbound text has multiple sentences with €,
        THEN ALL price-mentioning sentences are stripped; non-price sentences preserved.
        """
        from agent.modes.pre_expediente_mode import guard_no_premature_price

        text = (
            "La homologación cubre varios elementos. "
            "El coste total es 350€. "
            "Además hay que considerar los impuestos que son 70€ más. "
            "¿Quieres proceder con el expediente?"
        )
        mc = _mc_no_price_no_tariff()

        result = guard_no_premature_price(text, mc)

        assert "350€" not in result, (
            f"S2-3: first price sentence must be stripped. Got: {result!r}"
        )
        assert "70€" not in result, (
            f"S2-3: second price sentence must be stripped. Got: {result!r}"
        )
        assert "La homologación cubre varios elementos" in result, (
            f"S2-3: non-price sentence must be preserved. Got: {result!r}"
        )
        assert "¿Quieres proceder" in result, (
            f"S2-3: closing sentence must be preserved. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# T-7: guard_no_premature_transition_claim — RED tests (2 scenarios S3-1..S3-2)
# ---------------------------------------------------------------------------


class TestGuardNoPrematureTransitionClaim:
    """
    Unit tests for guard_no_premature_transition_claim(text, mc, pending_updates) -> str.

    Design AD-3: TRANSITION_CLAIM_PATTERNS list; sentence-level strip.
    Design AD-5: strip only; no canonical replacement appended.
    Spec S3-1..S3-2.
    """

    def test_strips_transition_claim_no_pending(self):
        """
        S3-1: GIVEN no _transition_to in pending_updates,
        WHEN outbound text contains "vamos a abrir tu expediente",
        THEN that sentence is stripped AND guard fires.
        """
        from agent.modes.pre_expediente_mode import guard_no_premature_transition_claim

        text = (
            "Perfecto, con esos datos ya tengo todo lo necesario. "
            "Vamos a abrir tu expediente ahora mismo. "
            "¿Tienes alguna duda antes de continuar?"
        )
        pending_updates: dict = {}

        result = guard_no_premature_transition_claim(text, {}, pending_updates)

        assert "Vamos a abrir tu expediente" not in result, (
            f"S3-1: transition claim sentence must be stripped. Got: {result!r}"
        )
        assert "Perfecto, con esos datos" in result, (
            f"S3-1: non-claim content must be preserved. Got: {result!r}"
        )

    def test_no_fire_transition_set(self):
        """
        S3-2: GIVEN _transition_to=EXPEDIENTE_MODE in pending_updates,
        WHEN outbound text contains "vamos a abrir expediente",
        THEN text is unchanged AND guard does NOT fire.
        """
        from agent.modes.pre_expediente_mode import guard_no_premature_transition_claim

        text = "Perfecto, vamos a abrir expediente ahora. ¿Listo?"
        pending_updates = {"_transition_to": "EXPEDIENTE_MODE"}

        result = guard_no_premature_transition_claim(text, {}, pending_updates)

        assert result == text, (
            f"S3-2: guard must NOT fire when _transition_to is set. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# T-9: guard_cta_policy — RED tests (4 scenarios from spec S4-1..S4-3 + ordering)
# ---------------------------------------------------------------------------


def _mc_post_price() -> dict:
    """mode_context: price communicated, tariff calculated, images sent → POST_PRICE phase."""
    return {
        "precio_comunicado": True,
        "element_codes": ["SUBCHASIS"],
        "tarifa_calculada": {"total": 410},
        "imagenes_enviadas_codigos": ["SUBCHASIS"],
    }


def _mc_pricing() -> dict:
    """mode_context: elements identified, tariff not yet calculated → PRICING phase."""
    return {
        "precio_comunicado": False,
        "element_codes": ["SUBCHASIS"],
        "tarifa_calculada": None,
        "imagenes_enviadas_codigos": [],
    }


def _mc_discovery() -> dict:
    """mode_context: no elements identified yet → DISCOVERY phase."""
    return {
        "precio_comunicado": False,
        "element_codes": [],
        "tarifa_calculada": None,
        "imagenes_enviadas_codigos": [],
    }


class TestGuardCtaPolicy:
    """
    Unit tests for guard_cta_policy(text, mc, phase) -> str.

    Design AD-5: strip incompatible CTAs; no canonical append (that's _enforce_cta5_if_needed).
    Design AD-9: guard_cta_policy runs BEFORE _enforce_cta5_if_needed.
    Spec S4-1..S4-3.
    """

    def test_post_price_strips_wrong_cta(self):
        """
        S4-1: GIVEN phase is PRE_EXPEDIENTE_POST_PRICE,
        WHEN outbound text contains a non-CTA-5 closing question,
        THEN that CTA is stripped AND guard fires.
        CTA 5 itself must NOT be stripped (it's the allowed one for POST_PRICE).
        """
        from agent.modes.pre_expediente_mode import guard_cta_policy

        # Wrong CTA for POST_PRICE: "¿Tienes alguna pregunta?" (not CTA 5)
        text = (
            "Ya tienes el presupuesto completo. "
            "¿Tienes alguna pregunta antes de continuar?"
        )
        mc = _mc_post_price()

        result = guard_cta_policy(text, mc, "PRE_EXPEDIENTE_POST_PRICE")

        assert "¿Tienes alguna pregunta antes de continuar?" not in result, (
            f"S4-1: wrong CTA must be stripped in POST_PRICE phase. Got: {result!r}"
        )
        assert "Ya tienes el presupuesto completo" in result, (
            f"S4-1: non-CTA content must be preserved. Got: {result!r}"
        )

    def test_post_price_allows_cta5(self):
        """
        S4-1 no-fire: GIVEN phase is PRE_EXPEDIENTE_POST_PRICE,
        WHEN outbound text contains canonical CTA 5,
        THEN text is unchanged AND guard does NOT fire.
        """
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = "Ya tienes el presupuesto. ¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_post_price()

        result = guard_cta_policy(text, mc, "PRE_EXPEDIENTE_POST_PRICE")

        assert result == text, (
            f"S4-1 no-fire: CTA 5 must NOT be stripped in POST_PRICE phase. Got: {result!r}"
        )

    def test_pricing_strips_cta5(self):
        """
        S4-2: GIVEN phase is PRE_EXPEDIENTE_PRICING,
        WHEN outbound text contains CTA 5 "¿Abrimos expediente o tienes alguna duda?",
        THEN that CTA is stripped AND guard fires.
        """
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = (
            "Aquí tienes la información sobre el proceso de homologación. "
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_pricing()

        result = guard_cta_policy(text, mc, "PRE_EXPEDIENTE_PRICING")

        assert "¿Abrimos expediente o tienes alguna duda?" not in result, (
            f"S4-2: CTA 5 must be stripped in PRICING phase. Got: {result!r}"
        )
        assert "Aquí tienes la información" in result, (
            f"S4-2: non-CTA content must be preserved. Got: {result!r}"
        )

    def test_discovery_strips_any_cta(self):
        """
        S4-3: GIVEN phase is PRE_EXPEDIENTE_DISCOVERY,
        WHEN outbound text contains any CTA variant,
        THEN that CTA is stripped AND guard fires.
        """
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = (
            "Para una homologación de subchasis necesitas varios documentos. "
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_discovery()

        result = guard_cta_policy(text, mc, "PRE_EXPEDIENTE_DISCOVERY")

        assert "¿Abrimos expediente" not in result, (
            f"S4-3: any CTA must be stripped in DISCOVERY phase. Got: {result!r}"
        )
        assert "Para una homologación" in result, (
            f"S4-3: non-CTA content must be preserved. Got: {result!r}"
        )

    def test_pipeline_order_strip_before_append(self):
        """
        Pipeline ordering (AD-9): guard_cta_policy strips wrong CTAs BEFORE
        _enforce_cta5_if_needed appends the canonical one.
        GIVEN POST_PRICE phase AND text has a wrong CTA variant,
        WHEN both functions run in the correct AD-9 order,
        THEN the wrong CTA is absent AND canonical CTA 5 appears exactly once.
        """
        from agent.modes.pre_expediente_mode import guard_cta_policy, _enforce_cta5_if_needed

        wrong_cta_text = (
            "Ya tienes el presupuesto. "
            "¿Quieres que procedamos con el expediente?"
        )
        mc = _mc_post_price()

        # Step 1: guard_cta_policy strips wrong CTA
        after_strip = guard_cta_policy(wrong_cta_text, mc, "PRE_EXPEDIENTE_POST_PRICE")

        assert "¿Quieres que procedamos" not in after_strip, (
            f"Pipeline order: wrong CTA must be stripped before enforce. Got: {after_strip!r}"
        )

        # Step 2: _enforce_cta5_if_needed appends canonical CTA 5
        after_enforce = _enforce_cta5_if_needed(
            ai_response=after_strip,
            precio_comunicado=True,
            imagenes_enviadas_codigos=["SUBCHASIS"],
        )

        canonical = "¿Abrimos expediente o tienes alguna duda?"
        count = after_enforce.count(canonical)
        assert count == 1, (
            f"Pipeline order: canonical CTA 5 must appear exactly once. "
            f"Found {count} times in: {after_enforce!r}"
        )


# ---------------------------------------------------------------------------
# T-12: pipeline idempotency smoke test
# ---------------------------------------------------------------------------


class TestPipelineIdempotent:
    """
    Idempotency smoke: running guards twice on the same input must produce
    the same output as running them once. No canonical phrase must appear
    twice, no content must be stripped that was safe to keep.

    Covers AD-5 (strip-then-append must not re-append on second pass) and
    AD-9 (pipeline composition must not amplify artifacts).
    """

    def test_pipeline_idempotent(self):
        """
        GIVEN POST_PRICE context (images sent, price communicated),
        WHEN the guard pipeline (image truth → cta_policy → _enforce_cta5)
          is applied to the same text TWICE in sequence,
        THEN the second pass output equals the first pass output.

        This catches double-append bugs where _enforce_cta5_if_needed would
        append the canonical CTA a second time even though it was already
        present from the first pass.
        """
        from agent.modes.pre_expediente_mode import (
            guard_image_send_truth,
            guard_cta_policy,
            _enforce_cta5_if_needed,
        )

        original_text = (
            "Aquí tienes toda la información sobre la homologación. "
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_post_price()
        phase = "PRE_EXPEDIENTE_POST_PRICE"
        imagenes_enviadas = ["SUBCHASIS"]

        def _run_pipeline(text: str) -> str:
            t = guard_image_send_truth(text, mc)
            t = guard_cta_policy(t, mc, phase)
            t = _enforce_cta5_if_needed(
                ai_response=t,
                precio_comunicado=True,
                imagenes_enviadas_codigos=imagenes_enviadas,
            )
            return t

        first_pass = _run_pipeline(original_text)
        second_pass = _run_pipeline(first_pass)

        assert first_pass == second_pass, (
            f"Pipeline must be idempotent: second pass differs from first.\n"
            f"First:  {first_pass!r}\n"
            f"Second: {second_pass!r}"
        )

        canonical = "¿Abrimos expediente o tienes alguna duda?"
        count = first_pass.count(canonical)
        assert count == 1, (
            f"Canonical CTA must appear exactly once after one pass. "
            f"Found {count} times in: {first_pass!r}"
        )
