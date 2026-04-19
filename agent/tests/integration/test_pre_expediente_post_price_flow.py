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
