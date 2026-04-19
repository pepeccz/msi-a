"""
Unit tests for format_mode_context — PRE_EXPEDIENTE POST_PRICE branch (Batch B).

Covers AC-1.1: when precio_comunicado=True, format_mode_context MUST NOT emit
any raw price value tokens as an actionable instruction — only the no-repeat
marker with price as a parenthetical reference.

Covers AC-1.2 (reprice guard): when precio_comunicado=True, the price value IS
retained as a parenthetical reference so the LLM can handle reprice scenarios,
but it must be framed as "ya comunicado", NOT as "calculado — DEBES comunicarlo".

Design: pure function tests — format_mode_context is a deterministic
transformation from (mode, context) → str. No mocks, no async.
These tests fail when the branch drifts.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    *,
    precio_comunicado: bool,
    tarifa_calculada: dict | None = None,
    element_codes: list[str] | None = None,
    categoria_slug: str | None = None,
) -> dict:
    ctx: dict = {
        "precio_comunicado": precio_comunicado,
    }
    if tarifa_calculada is not None:
        ctx["tarifa_calculada"] = tarifa_calculada
    if element_codes is not None:
        ctx["element_codes"] = element_codes
    if categoria_slug is not None:
        ctx["categoria_slug"] = categoria_slug
    return ctx


def _format(context: dict) -> str:
    from agent.prompts.loader import format_mode_context
    return format_mode_context("PRE_EXPEDIENTE_MODE", context)


# ---------------------------------------------------------------------------
# AC-1.1 — Price suppression: no actionable price instruction when communicated
# ---------------------------------------------------------------------------


class TestPriceSuppressedWhenCommunicated:
    """AC-1.1: format_mode_context with precio_comunicado=True must not emit
    an actionable price instruction (no 'DEBES comunicarlo' or bare numeric price)."""

    def test_no_debes_comunicarlo_when_precio_comunicado(self):
        """
        GIVEN a context with precio_comunicado=True and a tarifa_calculada
        WHEN format_mode_context is called
        THEN the output MUST NOT contain 'DEBES comunicarlo' instruction.

        Rationale: that instruction causes the LLM to repeat the price to the
        user even though it was already communicated in a prior turn.
        """
        tarifa = {"precio_final": 350}
        context = _make_context(precio_comunicado=True, tarifa_calculada=tarifa)
        result = _format(context)
        assert "DEBES comunicarlo" not in result, (
            "format_mode_context with precio_comunicado=True must not contain "
            "'DEBES comunicarlo' — that instruction fires on uncommunicated prices only. AC-1.1."
        )

    def test_output_contains_ya_comunicado_marker(self):
        """
        GIVEN a context with precio_comunicado=True and a tarifa_calculada
        WHEN format_mode_context is called
        THEN the output MUST contain 'ya comunicado' marker.

        This marker tells the LLM the price was already delivered; it is the
        no-repeat signal per design Q1.
        """
        tarifa = {"precio_final": 350}
        context = _make_context(precio_comunicado=True, tarifa_calculada=tarifa)
        result = _format(context)
        assert "ya comunicado" in result.lower(), (
            "format_mode_context with precio_comunicado=True must emit a 'ya comunicado' "
            "marker so the LLM knows not to repeat the price. AC-1.1."
        )

    def test_precio_comunicado_false_still_emits_debes(self):
        """
        GIVEN a context with precio_comunicado=False and a tarifa_calculada
        WHEN format_mode_context is called
        THEN the output MUST still contain 'DEBES comunicarlo' (reprice path works).

        Triangulation: confirms the suppression only fires when precio_comunicado=True.
        """
        tarifa = {"precio_final": 350}
        context = _make_context(precio_comunicado=False, tarifa_calculada=tarifa)
        result = _format(context)
        assert "DEBES comunicarlo" in result, (
            "format_mode_context with precio_comunicado=False must retain 'DEBES comunicarlo' "
            "so the LLM knows it needs to communicate the price. Triangulation for AC-1.1."
        )


# ---------------------------------------------------------------------------
# AC-1.2 (reprice guard) — Price value retained as parenthetical reference
# ---------------------------------------------------------------------------


class TestPriceRetainedAsParenthetical:
    """AC-1.2 reprice guard: price value must appear in output even when
    precio_comunicado=True — but as a parenthetical, not an instruction."""

    def test_price_value_present_in_output_when_precio_comunicado(self):
        """
        GIVEN precio_comunicado=True and tarifa_calculada with precio_final=450
        WHEN format_mode_context is called
        THEN the output MUST contain '450' (price value as parenthetical reference).

        Rationale: if the user says 'es muy caro', the LLM needs the numeric anchor
        to engage with the reprice scenario without calling calcular_tarifa again.
        """
        tarifa = {"precio_final": 450}
        context = _make_context(precio_comunicado=True, tarifa_calculada=tarifa)
        result = _format(context)
        assert "450" in result, (
            "format_mode_context with precio_comunicado=True must still include the "
            "price value (450) as a parenthetical reference for reprice scenarios. AC-1.2."
        )

    def test_price_value_in_no_repeat_marker_form(self):
        """
        GIVEN precio_comunicado=True and tarifa_calculada with precio_final=275
        WHEN format_mode_context is called
        THEN the output line containing the price MUST also contain 'ya comunicado'
        AND MUST contain 'NO repetir' or 'no repetir' or 'NO repetir'.

        This verifies the exact no-repeat marker format per design Q1:
        'Precio: ya comunicado (275€ — NO repetir salvo reprice)'.
        """
        tarifa = {"precio_final": 275}
        context = _make_context(precio_comunicado=True, tarifa_calculada=tarifa)
        result = _format(context)
        assert "275" in result, "Price value must be present as parenthetical."
        assert "ya comunicado" in result.lower(), "No-repeat marker must be present."
        # The marker must contain a no-repeat signal
        assert any(
            phrase in result
            for phrase in ["NO repetir", "no repetir", "no volver", "salvo reprice"]
        ), (
            "The price line must contain a no-repeat signal "
            "(e.g. 'NO repetir salvo reprice'). AC-1.2 reprice guard."
        )
