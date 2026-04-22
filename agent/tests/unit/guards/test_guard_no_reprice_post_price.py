"""
Unit tests for R-5 guard: guard_no_reprice_post_price.

Spec: R8 — Post-Price Response Purity Guard (widened trigger, replaces R1).
AC-8.1: Guard fires on elemento re-narration (delivery_scope=elemento).
AC-8.2: Guard fires on free-text POST_PRICE turn (no tool, no delivery_intent_created).
AC-8.3: Guard does NOT fire when precio_comunicado=False (PRICING regression).
AC-9.3: Guard does NOT fire when reprice_allowed_this_turn=True (reprice escape).

The guard is a pure function — no mocking needed.
"""
from __future__ import annotations

import pytest


def _mc_gate_on(**overrides) -> dict:
    """Mode context that triggers the guard (precio=True, no reprice escape)."""
    mc = {
        "precio_comunicado": True,
        "reprice_allowed_this_turn": False,
    }
    mc.update(overrides)
    return mc


def _mc_gate_off(**overrides) -> dict:
    """Mode context that does NOT trigger the guard."""
    mc = {
        "precio_comunicado": False,
    }
    mc.update(overrides)
    return mc


def _call(text: str, mc: dict) -> str:
    from agent.modes.pre_expediente_mode import guard_no_reprice_post_price

    return guard_no_reprice_post_price(
        text=text,
        mc=mc,
        node_logger=None,  # unit tests skip structlog telemetry
        conversation_id="test-conv",
    )


# ---------------------------------------------------------------------------
# AC-8.3 — gate off → passthrough (precio_comunicado=False)
# ---------------------------------------------------------------------------

class TestGateOffPassthrough:
    """When precio_comunicado=False, the guard must never fire."""

    def test_precio_false_passthrough(self):
        """Regression: PRICING first-turn narration must never be stripped."""
        text = "El presupuesto es de *410€ +IVA*.\n⚠️ Advertencia.\n\nDocumentación general:\n- Ficha técnica."
        mc = _mc_gate_off()
        result = _call(text, mc)
        assert result == text, (
            f"Gate must NOT fire when precio_comunicado=False. Got: {result!r}"
        )

    def test_precio_false_full_narration_passthrough(self):
        """Full pricing narration must pass unchanged on PRICING turn."""
        text = (
            "El presupuesto es de *410 € +IVA*.\n\n"
            "⚠️ Requiere certificación adicional.\n\n"
            "Documentación general:\n- Ficha técnica\n\n"
            "_Precios válidos por 30 días._"
        )
        mc = _mc_gate_off()
        result = _call(text, mc)
        assert result == text


# ---------------------------------------------------------------------------
# AC-9.3 — reprice_allowed=True → passthrough (add/remove element reprice)
# ---------------------------------------------------------------------------

class TestRepriceAllowedPassthrough:
    """When reprice_allowed_this_turn=True, the guard must not strip."""

    def test_reprice_allowed_passthrough(self):
        """Add-element reprice: new narration must pass through unstripped."""
        text = "El nuevo presupuesto es *510€ +IVA*."
        mc = _mc_gate_on(reprice_allowed_this_turn=True)
        result = _call(text, mc)
        assert result == text, (
            f"Guard must NOT fire when reprice_allowed_this_turn=True. Got: {result!r}"
        )

    def test_reprice_allowed_full_narration_passthrough(self):
        """Full reprice narration allowed when reprice_allowed_this_turn=True."""
        text = (
            "El presupuesto actualizado es de *510 € +IVA*.\n\n"
            "⚠️ El escape requiere certificación.\n\n"
            "Documentación del Escape:\n- Foto del escape\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_gate_on(reprice_allowed_this_turn=True)
        result = _call(text, mc)
        assert result == text


# ---------------------------------------------------------------------------
# AC-8.1, AC-8.2 — gate on → strip offending paragraphs
# (regardless of delivery_intent_created or delivery_scope)
# ---------------------------------------------------------------------------

class TestGateOnStripping:
    """When gate fires, offending paragraphs must be removed regardless of scope."""

    def test_strips_currency_paragraph(self):
        """Paragraph containing a price numeric with € must be removed."""
        text = "El presupuesto es de 410 € +IVA.\n\n¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert "410" not in result or "€" not in result, (
            f"Currency paragraph not stripped. Got: {result!r}"
        )
        assert "¿Abrimos expediente" in result, (
            f"CTA_5 should survive stripping. Got: {result!r}"
        )

    def test_strips_warning_emoji_paragraph(self):
        """Paragraph containing ⚠️ must be removed."""
        text = "⚠️ Esta advertencia ya fue comunicada.\n\n¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert "⚠️" not in result, (
            f"Warning paragraph not stripped. Got: {result!r}"
        )

    def test_strips_documentacion_general_header(self):
        """Paragraph containing 'Documentación general:' must be removed."""
        text = (
            "Documentación general:\n"
            "- Ficha técnica\n"
            "- Permiso de circulación\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert "Documentación general:" not in result, (
            f"Documentacion general header not stripped. Got: {result!r}"
        )
        assert "¿Abrimos expediente" in result

    def test_strips_documentacion_del_element(self):
        """Paragraph containing 'Documentación del' must be removed."""
        text = (
            "Documentación del Escape:\n"
            "- Foto del escape\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert "Documentación del" not in result, (
            f"Documentacion del element not stripped. Got: {result!r}"
        )

    def test_strips_footer(self):
        """Paragraph containing '_Precios válidos por 30 días._' must be removed."""
        text = "_Precios válidos por 30 días._\n\n¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert "_Precios válidos" not in result, (
            f"Footer not stripped. Got: {result!r}"
        )

    def test_pure_cta5_unchanged(self):
        """If text is only CTA_5, it must pass through unchanged."""
        text = "¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_gate_on()
        result = _call(text, mc)
        assert result.strip() == text.strip(), (
            f"Pure CTA_5 should not be stripped. Got: {result!r}"
        )

    def test_delivery_intent_false_still_strips(self):
        """AC-8.2: guard fires even when delivery_intent_created=False (no tool).

        Old R1 would NOT fire here. R8 MUST fire.
        """
        text = "El nuevo presupuesto es *510€ +IVA*."
        # No delivery_intent_created in mc — only precio=True, reprice_allowed=False
        mc = {
            "precio_comunicado": True,
            "reprice_allowed_this_turn": False,
        }
        result = _call(text, mc)
        assert "510" not in result or "€" not in result, (
            f"R8: guard must strip even without delivery_intent_created. Got: {result!r}"
        )

    def test_delivery_scope_elemento_still_strips(self):
        """AC-8.1: guard fires regardless of delivery_scope value.

        Old R1 would NOT fire on scope=elemento. R8 MUST fire.
        """
        text = "El presupuesto es de *410€ +IVA*."
        mc = _mc_gate_on()
        # delivery_scope present but irrelevant to R8 trigger
        mc["delivery_scope"] = "elemento"
        result = _call(text, mc)
        assert "410" not in result or "€" not in result, (
            f"R8: guard must strip regardless of delivery_scope. Got: {result!r}"
        )

    def test_no_tarifa_calculada_still_strips(self):
        """R8: tarifa_calculada absence is irrelevant — only precio_comunicado matters."""
        mc = _mc_gate_on()
        mc["tarifa_calculada"] = None  # no stored tariff
        text = "Algún texto con 410 €."
        result = _call(text, mc)
        assert "410" not in result or "€" not in result, (
            f"R8: guard must strip even without tarifa_calculada. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# TRIANGULATION — full reprice + CTA response
# ---------------------------------------------------------------------------

class TestFullRepriceStripped:
    """Full multi-paragraph reprice narration must be stripped, CTA preserved."""

    def test_full_reprice_response(self):
        text = (
            "Aquí tienes el resumen del presupuesto:\n\n"
            "El presupuesto es de *410 € +IVA*.\n\n"
            "⚠️ El escape requiere certificación adicional.\n\n"
            "Documentación general:\n"
            "- Ficha técnica\n"
            "- Permiso de circulación\n\n"
            "Documentación del Escape:\n"
            "- Foto del escape con matrícula visible\n\n"
            "_Precios válidos por 30 días._\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_gate_on()
        result = _call(text, mc)

        # All offending content stripped
        assert "410 €" not in result
        assert "⚠️" not in result
        assert "Documentación general:" not in result
        assert "Documentación del" not in result
        assert "_Precios válidos" not in result
        # CTA preserved
        assert "¿Abrimos expediente" in result

    def test_full_reprice_with_reprice_allowed_passes_through(self):
        """Triangulation: same text with reprice_allowed=True must NOT be stripped."""
        text = (
            "El presupuesto es de *410 € +IVA*.\n\n"
            "⚠️ Advertencia.\n\n"
            "¿Abrimos expediente o tienes alguna duda?"
        )
        mc = _mc_gate_on(reprice_allowed_this_turn=True)
        result = _call(text, mc)
        # Full text preserved
        assert "410 €" in result
        assert "⚠️" in result
