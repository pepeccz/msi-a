"""
Unit tests for C4 — R-5 guard: guard_no_reprice_post_price.

Spec: R1 — Post-Price Response Purity Guard.
AC-1.1: POST_PRICE guard strips price, ⚠️, doc sections when delivery_intent_created=True.
AC-1.2: PRICING first-turn narration unaffected (guard does not fire).

The guard is a pure function — no mocking needed.

RED before C4: guard_no_reprice_post_price does not exist yet.
"""
from __future__ import annotations

import pytest


def _mc_gate_on(**overrides) -> dict:
    """Mode context that triggers the guard."""
    mc = {
        "precio_comunicado": True,
        "delivery_intent_created": True,
        "delivery_scope": "presupuesto",
        "tarifa_calculada": {"price": 410.0},
    }
    mc.update(overrides)
    return mc


def _mc_gate_off(**overrides) -> dict:
    """Mode context that does NOT trigger the guard."""
    mc = {
        "precio_comunicado": False,
        "delivery_intent_created": False,
        "delivery_scope": None,
        "tarifa_calculada": None,
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
# AC-1.2 — gate off → passthrough (PRICING or no delivery intent)
# ---------------------------------------------------------------------------

class TestGateOffPassthrough:
    """When gate conditions are not met, the text must pass through unchanged."""

    def test_precio_false_passthrough(self):
        text = "El presupuesto es de *410€ +IVA*.\n⚠️ Advertencia.\n\nDocumentación general:\n- Ficha técnica."
        mc = _mc_gate_off(precio_comunicado=False)
        result = _call(text, mc)
        assert result == text, (
            f"Gate should NOT fire when precio_comunicado=False. Got: {result!r}"
        )

    def test_delivery_intent_false_passthrough(self):
        """Add/remove element path: tarifa called but enviar_imagenes NOT called."""
        text = "El nuevo presupuesto es *510€ +IVA*."
        mc = _mc_gate_on(delivery_intent_created=False)
        result = _call(text, mc)
        assert result == text, (
            f"Gate should NOT fire when delivery_intent_created=False. Got: {result!r}"
        )

    def test_delivery_scope_elemento_passthrough(self):
        """delivery_scope=elemento is a different scope — gate must not fire."""
        text = "El presupuesto es de *410€ +IVA*."
        mc = _mc_gate_on(delivery_scope="elemento")
        result = _call(text, mc)
        assert result == text, (
            f"Gate should NOT fire when delivery_scope=elemento. Got: {result!r}"
        )

    def test_no_tarifa_calculada_passthrough(self):
        mc = _mc_gate_on(tarifa_calculada=None)
        text = "Algún texto con 410 €."
        result = _call(text, mc)
        assert result == text


# ---------------------------------------------------------------------------
# AC-1.1 — gate on → strip offending paragraphs
# ---------------------------------------------------------------------------

class TestGateOnStripping:
    """When gate fires, offending paragraphs must be removed."""

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
