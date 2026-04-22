"""
Unit tests for AC-11 — Conversational regurgitation guard.

Spec R11: When precio_comunicado=True AND no tool called AND reprice_allowed=False,
if LLM ai_response contains ≥2 distinct budget signal patterns, replace with
a canned message ending in CTA_5.

The guard is a pure function — no mocking needed.
"""
from __future__ import annotations

import pytest

_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"
_EXPECTED_REPLACEMENT = f"Ya te comuniqué el presupuesto arriba. {_CTA_5}"


def _mc_gate_on(**overrides) -> dict:
    """mc that activates the guard."""
    mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
    mc.update(overrides)
    return mc


def _call(text: str, mc: dict, tools_called: list[str] | None = None) -> str:
    from agent.modes.pre_expediente_mode import guard_no_reprice_without_tool

    return guard_no_reprice_without_tool(
        text=text,
        mc=mc,
        tools_called_this_turn=tools_called or [],
        node_logger=None,
        conversation_id="test-conv",
    )


# ---------------------------------------------------------------------------
# AC-11.1 — ≥2 signals → replace with canned string
# ---------------------------------------------------------------------------

class TestTwoSignalsReplaced:
    """When ≥2 distinct signal patterns hit → replacement fires."""

    def test_currency_and_warning_replaced(self):
        """2 signals: price € + ⚠️ emoji → replaced."""
        text = "Son 410€ +IVA.\n\n⚠️ El escape requiere certificación.\n\n¿Abrimos expediente o tienes alguna duda?"
        result = _call(text, _mc_gate_on())
        assert result == _EXPECTED_REPLACEMENT, (
            f"Expected canned replacement, got: {result!r}"
        )

    def test_currency_and_doc_general_replaced(self):
        """2 signals: price € + Documentación general → replaced."""
        text = "El coste es de 410€.\n\nDocumentación general:\n- Ficha técnica."
        result = _call(text, _mc_gate_on())
        assert result == _EXPECTED_REPLACEMENT

    def test_currency_and_doc_del_replaced(self):
        """2 signals: price € + Documentación del → replaced."""
        text = "El total es 410€.\n\nDocumentación del Escape:\n- Foto del escape."
        result = _call(text, _mc_gate_on())
        assert result == _EXPECTED_REPLACEMENT

    def test_warning_and_foto_bullet_replaced(self):
        """2 signals: ⚠️ + foto bullet → replaced."""
        text = "⚠️ Requiere certificación.\n\n- Foto del escape con matrícula visible."
        result = _call(text, _mc_gate_on())
        assert result == _EXPECTED_REPLACEMENT

    def test_three_signals_replaced(self):
        """3 signals → also replaced (threshold is ≥2)."""
        text = (
            "El presupuesto es de 410€ +IVA.\n\n"
            "⚠️ Advertencia de certificación.\n\n"
            "Documentación general:\n- Ficha técnica."
        )
        result = _call(text, _mc_gate_on())
        assert result == _EXPECTED_REPLACEMENT

    def test_replacement_contains_cta5(self):
        """Replacement string must end with CTA_5."""
        text = "Son 410€. ⚠️ Advertencia."
        result = _call(text, _mc_gate_on())
        assert result.endswith(_CTA_5), f"Replacement must end with CTA_5. Got: {result!r}"


# ---------------------------------------------------------------------------
# AC-11.2 — 0 signals → untouched
# ---------------------------------------------------------------------------

class TestZeroSignalsUntouched:
    """When 0 signals → text must pass through unchanged."""

    def test_benign_response_untouched(self):
        text = "De nada, ¿Abrimos expediente o tienes alguna duda?"
        result = _call(text, _mc_gate_on())
        assert result == text

    def test_simple_question_answer_untouched(self):
        text = "Claro, puedo ayudarte con eso."
        result = _call(text, _mc_gate_on())
        assert result == text


# ---------------------------------------------------------------------------
# AC-11.3 — 1 signal → untouched (below threshold)
# ---------------------------------------------------------------------------

class TestOneSignalUntouched:
    """When 1 signal only → text must pass through (threshold requires ≥2)."""

    def test_price_only_untouched(self):
        """Single signal: price mention → NOT replaced."""
        text = "Tal como te dije, son 410€, ¿seguimos?"
        result = _call(text, _mc_gate_on())
        assert result == text, f"Single signal must not trigger guard. Got: {result!r}"

    def test_warning_only_untouched(self):
        """Single signal: ⚠️ only → NOT replaced."""
        text = "⚠️ Recuerda revisar los documentos antes de continuar."
        result = _call(text, _mc_gate_on())
        assert result == text


# ---------------------------------------------------------------------------
# Gate conditions — guard must NOT fire
# ---------------------------------------------------------------------------

class TestGateConditions:
    """Guard must not fire when gate conditions are not met."""

    def test_tool_called_skips_guard(self):
        """When tools were called this turn → guard must not fire (R-5 handles that case)."""
        text = "Son 410€.\n\n⚠️ Advertencia.\n\nDocumentación general:\n- X."
        # ≥2 signals but tool was called
        result = _call(text, _mc_gate_on(), tools_called=["calcular_tarifa_con_elementos"])
        assert result == text, f"Guard must skip when tool was called. Got: {result!r}"

    def test_reprice_allowed_skips_guard(self):
        """When reprice_allowed_this_turn=True → guard must not fire."""
        text = "El presupuesto actualizado es de 510€.\n\n⚠️ Advertencia."
        result = _call(text, _mc_gate_on(reprice_allowed_this_turn=True))
        assert result == text

    def test_precio_false_skips_guard(self):
        """When precio_comunicado=False → guard must not fire (PRICING regression)."""
        text = "El coste sería 410€.\n\n⚠️ Certificación requerida.\n\nDocumentación general:\n- X."
        mc = {"precio_comunicado": False}
        result = _call(text, mc)
        assert result == text, f"Guard must not fire when precio_comunicado=False. Got: {result!r}"

    def test_empty_text_skips_guard(self):
        """Empty text → no signals → guard no-op."""
        result = _call("", _mc_gate_on())
        assert result == ""
