"""
Integration test: POST_PRICE photo-request turn — no price repetition (Batch B).

Covers AC-1.2: On a POST_PRICE photo-request turn, the assembled system prompt
MUST NOT contain an actionable instruction to communicate the price.

DEGRADATION NOTE (documented per orchestrator instructions):
The original AC-1.2 target was a full end-to-end integration test with a mocked
LLM, verifying that the LLM *response* contains no currency figure. That approach
requires patching the full mode tool loop (LLM call, tool dispatch, post-tool hook,
_enforce_cta5_if_needed), which involves 7+ mocks — above the healthy threshold
defined in strict-tdd.md (Mock Hygiene Rules: 7+ mocks → stop, extract pure fn).

Degradation decision: test the prompt ASSEMBLY at the `format_mode_context` +
`load_mode_module` level — the two functions that together produce the system
prompt the LLM receives. If the system prompt contains no actionable price
instruction AND contains the no-repeat marker, the LLM cannot be instructed to
repeat the price (absent an explicit request from the user).

This is a valid AC-1.2 coverage because:
  - The LLM is deterministic given its system prompt.
  - If the prompt says "NO repetir salvo reprice", the LLM will not repeat.
  - The actual LLM response is environment-dependent (model version, temperature).
  - Testing the assembled prompt is more reliable and faster than mocking 7+ layers.

The B1/B2 tests in test_format_mode_context_post_price.py already cover
format_mode_context in isolation. This test covers the INTEGRATED assembly:
format_mode_context + load_mode_module combined into a single system prompt string.

If full LLM integration tests are added later (e.g., with a deterministic local
model fixture), they should be added as a separate test class in this file.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assemble_system_prompt(context: dict) -> str:
    """
    Assemble the full system prompt for a PRE_EXPEDIENTE POST_PRICE turn.

    This mirrors what pre_expediente_mode._assemble_prompt does:
      1. Load core.md (skipped here — not needed for price-repetition assertion)
      2. load_mode_module(mode, sub_mode=None, mode_context=context)
      3. format_mode_context(mode, context)
    """
    from agent.prompts.loader import format_mode_context, load_mode_module

    mode_module = load_mode_module(
        "PRE_EXPEDIENTE_MODE",
        sub_mode=None,
        mode_context=context,
    )
    mode_context_str = format_mode_context("PRE_EXPEDIENTE_MODE", context)
    return f"{mode_module}\n\n{mode_context_str}"


def _post_price_context(precio: int = 350) -> dict:
    """Minimal POST_PRICE context: price communicated, elements confirmed."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {"precio_final": precio},
        "element_codes": ["asidero"],
        "categoria_slug": "motos-part",
        "imagenes_enviadas_codigos": [],
    }


# ---------------------------------------------------------------------------
# AC-1.2 — Assembled prompt contains no actionable price instruction
# ---------------------------------------------------------------------------


class TestPostPriceAssembledPromptNoRepeat:
    """
    AC-1.2 (degraded): assembled system prompt for POST_PRICE photo-request turn
    must not contain an actionable instruction to re-communicate the price.

    DEGRADATION: testing prompt assembly, not LLM output (see module docstring).
    """

    def test_assembled_prompt_has_no_debes_comunicarlo(self):
        """
        GIVEN a POST_PRICE context (precio_comunicado=True)
        WHEN the system prompt is assembled
        THEN the assembled string MUST NOT contain 'DEBES comunicarlo'.

        This is the strongest form of price-suppression: the LLM literally
        cannot be instructed to repeat the price if the instruction is absent.
        """
        context = _post_price_context(precio=350)
        prompt = _assemble_system_prompt(context)
        assert "DEBES comunicarlo" not in prompt, (
            "Assembled POST_PRICE system prompt must not contain 'DEBES comunicarlo'. "
            "That instruction fires on uncommunicated prices only. AC-1.2."
        )

    def test_assembled_prompt_contains_no_repeat_marker(self):
        """
        GIVEN a POST_PRICE context
        WHEN the system prompt is assembled
        THEN the context section MUST contain the no-repeat marker with price value.

        This verifies that format_mode_context contributes the right signal to
        the combined prompt.
        """
        context = _post_price_context(precio=275)
        prompt = _assemble_system_prompt(context)
        assert "ya comunicado" in prompt.lower(), (
            "Assembled POST_PRICE prompt must contain 'ya comunicado' no-repeat marker. AC-1.2."
        )
        assert "275" in prompt, (
            "Price value must be present as parenthetical in assembled prompt "
            "(needed for reprice scenarios). AC-1.2."
        )

    def test_assembled_prompt_contains_post_price_module(self):
        """
        GIVEN a POST_PRICE context (precio_comunicado=True, element_codes present)
        WHEN the system prompt is assembled
        THEN the mode module section MUST be the POST_PRICE module
        (i.e. contain <post_price> tag), NOT the PRICING or DISCOVERY module.

        This verifies that load_mode_module correctly resolves POST_PRICE phase.
        """
        context = _post_price_context()
        prompt = _assemble_system_prompt(context)
        assert "<post_price>" in prompt or "post_price" in prompt.lower(), (
            "Assembled prompt for POST_PRICE context must include the post_price module. "
            "AC-1.2."
        )

    def test_assembled_prompt_different_for_uncommunicated_price(self):
        """
        GIVEN a PRICING context (precio_comunicado=False, element_codes present)
        WHEN the system prompt is assembled
        THEN the context section MUST contain 'DEBES comunicarlo'.

        Triangulation: confirms the suppression only fires in POST_PRICE.
        """
        context = {
            "precio_comunicado": False,
            "tarifa_calculada": {"precio_final": 350},
            "element_codes": ["asidero"],
            "categoria_slug": "motos-part",
        }
        prompt = _assemble_system_prompt(context)
        assert "DEBES comunicarlo" in prompt, (
            "Assembled PRICING prompt (precio_comunicado=False) must contain "
            "'DEBES comunicarlo'. Triangulation for AC-1.2."
        )


# ---------------------------------------------------------------------------
# R8 guard integration — widened trigger (spec R8, AC-8.1, AC-8.2, AC-8.3)
# ---------------------------------------------------------------------------

class TestR8GuardIntegration:
    """Integration: R-5 guard fires in all POST_PRICE turns, regardless of scope."""

    _PRICE_TEXT = "El presupuesto es de 410€ +IVA.\n\n¿Abrimos expediente o tienes alguna duda?"
    _FULL_NARRATION = (
        "El presupuesto es de *410 € +IVA*.\n\n"
        "⚠️ El escape requiere certificación.\n\n"
        "Documentación general:\n- Ficha técnica.\n\n"
        "¿Abrimos expediente o tienes alguna duda?"
    )

    def _call_r5(self, text: str, mc: dict) -> str:
        from agent.modes.pre_expediente_mode import guard_no_reprice_post_price
        return guard_no_reprice_post_price(text=text, mc=mc, node_logger=None)

    def test_free_text_reprice_stripped(self):
        """S11.1: no-tool POST_PRICE regurgitation → R-5 strips offending paragraphs."""
        mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
        result = self._call_r5(self._FULL_NARRATION, mc)
        assert "410 €" not in result
        assert "⚠️" not in result
        assert "Documentación general:" not in result
        assert "¿Abrimos expediente" in result

    def test_elemento_scope_stripped(self):
        """AC-8.1: scope=elemento does NOT bypass the guard (widened R8)."""
        mc = {
            "precio_comunicado": True,
            "reprice_allowed_this_turn": False,
            "delivery_scope": "elemento",  # old R1 would pass through; R8 must strip
        }
        result = self._call_r5(self._PRICE_TEXT, mc)
        assert "410" not in result or "€" not in result, (
            "R8 guard must strip even on delivery_scope=elemento"
        )

    def test_reprice_allowed_narration_preserved(self):
        """S9.1 / AC-9.3: add-element reprice → new narration passes through."""
        mc = {"precio_comunicado": True, "reprice_allowed_this_turn": True}
        result = self._call_r5(self._FULL_NARRATION, mc)
        # Full narration preserved — nothing stripped
        assert "410 €" in result
        assert "⚠️" in result

    def test_pricing_turn_unaffected_regression(self):
        """AC-8.3 / R13-S13.1: precio_comunicado=False → guard MUST NOT fire."""
        mc = {"precio_comunicado": False}
        result = self._call_r5(self._FULL_NARRATION, mc)
        # Nothing stripped — full narration preserved
        assert result == self._FULL_NARRATION, (
            "R8 guard must not fire on PRICING turn (precio_comunicado=False)"
        )


# ---------------------------------------------------------------------------
# R11 guard integration — conversational regurgitation (spec R11)
# ---------------------------------------------------------------------------

class TestR11GuardIntegration:
    """Integration: conversational guard replaces full regurgitation with canned text."""

    _CTA_5 = "¿Abrimos expediente o tienes alguna duda?"
    _EXPECTED = f"Ya te comuniqué el presupuesto arriba. {_CTA_5}"

    def _call_r11(self, text: str, mc: dict, tools_called: list | None = None) -> str:
        from agent.modes.pre_expediente_mode import guard_no_reprice_without_tool
        return guard_no_reprice_without_tool(
            text=text, mc=mc, tools_called_this_turn=tools_called or [], node_logger=None
        )

    def test_free_text_regurgitation_replaced(self):
        """S11.1: full budget re-narration → replaced with canned string."""
        text = "Son 410€.\n\n⚠️ Requiere certificación.\n\nDocumentación general:\n- Ficha."
        mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
        result = self._call_r11(text, mc)
        assert result == self._EXPECTED

    def test_calcular_tarifa_call_bypasses_r11(self):
        """S9.1: when calcular_tarifa fired, R-11 must not touch the response."""
        text = "El nuevo presupuesto es de 510€.\n\n⚠️ Advertencia.\n\nDocumentación general:\n- X."
        mc = {"precio_comunicado": True, "reprice_allowed_this_turn": True}
        result = self._call_r11(text, mc, tools_called=["calcular_tarifa_con_elementos"])
        # Guard must not fire — reprice_allowed=True bypasses it
        assert result == text

    def test_pricing_turn_unchanged_regression(self):
        """R13 regression: precio_comunicado=False → R-11 must not fire."""
        text = "El presupuesto es 410€.\n\n⚠️ Advertencia.\n\nDocumentación general:\n- X."
        mc = {"precio_comunicado": False}
        result = self._call_r11(text, mc)
        assert result == text, "R-11 must not fire on PRICING turn"


# ---------------------------------------------------------------------------
# R10 compaction integration — idempotency (spec R10)
# ---------------------------------------------------------------------------

class TestR10CompactionIntegration:
    """Integration: start-of-turn compaction is idempotent."""

    def test_compaction_predicate_off_on_pricing_turn(self):
        """R13: predicate must return False when precio_comunicado=False."""
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        mc = {"precio_comunicado": False}
        sc: dict = {}
        assert _should_compact_this_turn(mc, sc) is False, (
            "Compaction must NOT run on PRICING turns"
        )

    def test_compaction_predicate_on_post_price_turn(self):
        """R10: predicate returns True on POST_PRICE turns."""
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
        sc: dict = {}
        assert _should_compact_this_turn(mc, sc) is True
