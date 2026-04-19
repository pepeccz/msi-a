"""
Integration test: PRICING→POST_PRICE same-turn transition — CTA regression guard (Fix C).

Covers:
  AC-C.1: Assembled PRICING prompt (precio_comunicado=False) MUST contain _CTA_5 in
          the <natural_ctas> block for the "precio comunicado + imágenes enviadas" case.
  AC-C.2: Assembled PRICING prompt MUST NOT contain the old closed CTA.

WHY this test exists
--------------------
In the production Turn 2 scenario (calcular_tarifa + enviar_imagenes in the same turn),
`precio_comunicado` is False DURING the tool loop (the post-loop setter in _process_message
flips it to True AFTER the loop exits). This means the LLM assembles its final response
using the PRICING prompt — specifically the <natural_ctas> row for "Precio comunicado +
imágenes enviadas". If that row contains the old closed CTA ('¿Empezamos con el
expediente?'), the LLM emits the old CTA to the user.

Fix A replaced that line with _CTA_5. This test is the regression guard: it verifies that
the PRICING prompt's <natural_ctas> block contains _CTA_5 so that any future revert of
pricing.md (or drift of _CTA_5) will immediately break this test and Fix A's unit tests.

Approach (prompt-assembly, not full LLM)
-----------------------------------------
Same degradation approach as test_pre_expediente_post_price_flow.py: test the system
prompt that the LLM RECEIVES, not the LLM's generated text. The LLM is deterministic
given its system prompt — if the prompt contains the correct CTA, the LLM will use it.

The test does NOT mock the tool calls themselves. It assembles the prompt for the state
that would exist at the FINAL llm_node iteration in the same turn (precio_comunicado=False,
tarifa_calculada present, element_codes present). This is the exact state the LLM sees
when generating its final response in the PRICING→POST_PRICE turn.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assemble_pricing_prompt(context: dict) -> str:
    """
    Assemble the full system prompt for a PRE_EXPEDIENTE PRICING turn.

    Mirrors what pre_expediente_mode._assemble_prompt does at the final
    llm_node iteration of a PRICING→POST_PRICE turn:
      1. load_mode_module → resolves to PRE_EXPEDIENTE_PRICING (precio_comunicado=False)
      2. format_mode_context → adds context block with tarifa, elements, etc.

    This is the prompt the LLM receives when precio_comunicado is still False
    but calcular_tarifa + enviar_imagenes have already been called in the same turn.
    """
    from agent.prompts.loader import format_mode_context, load_mode_module

    mode_module = load_mode_module(
        "PRE_EXPEDIENTE_MODE",
        sub_mode=None,
        mode_context=context,
    )
    mode_context_str = format_mode_context("PRE_EXPEDIENTE_MODE", context)
    return f"{mode_module}\n\n{mode_context_str}"


def _pricing_transition_context(precio: int = 410) -> dict:
    """
    Minimal PRICING context at the final llm_node iteration of a same-turn
    calcular_tarifa + enviar_imagenes turn.

    precio_comunicado=False because the post-loop setter has not fired yet.
    tarifa_calculada is present (calcular_tarifa already ran).
    element_codes are set (identificar_y_resolver_elementos ran in a prior turn).
    """
    return {
        "precio_comunicado": False,
        "tarifa_calculada": {"precio_final": precio},
        "element_codes": ["ASIDEROS", "SUBCHASIS"],
        "categoria_slug": "motos-part",
        "imagenes_enviadas_codigos": [],
    }


def _get_cta5() -> str:
    from agent.modes.pre_expediente_mode import _CTA_5
    return _CTA_5


# ---------------------------------------------------------------------------
# AC-C.1, AC-C.2 — Pricing prompt contains _CTA_5, not old CTA
# ---------------------------------------------------------------------------


class TestPricingToPostPriceTransitionPrompt:
    """
    AC-C.1, AC-C.2: The assembled PRICING prompt (pricing phase, pre-flip)
    MUST contain _CTA_5 in <natural_ctas> and MUST NOT contain the old CTA.

    This is the regression guard for Fix A: if pricing.md line ~90 is
    reverted or _CTA_5 drifts, this test fails immediately.
    """

    _OLD_CLOSED_CTA = "¿Empezamos con el expediente?"

    def test_pricing_prompt_contains_cta5_in_natural_ctas(self):
        """
        GIVEN a PRICING context (precio_comunicado=False, tarifa_calculada present)
        WHEN the system prompt is assembled for PRE_EXPEDIENTE_MODE
        THEN the <natural_ctas> section MUST contain the exact _CTA_5 value.

        This represents the state of the system prompt at the final llm_node
        iteration of a same-turn calcular_tarifa + enviar_imagenes turn.
        AC-C.1.
        """
        cta5 = _get_cta5()
        context = _pricing_transition_context()
        prompt = _assemble_pricing_prompt(context)

        # Locate <natural_ctas> section in the assembled prompt.
        natural_ctas_start = prompt.find("<natural_ctas>")
        natural_ctas_end = prompt.find("</natural_ctas>")
        assert natural_ctas_start != -1, (
            "<natural_ctas> section not found in assembled PRICING prompt. "
            "The pricing.md module must include a <natural_ctas> block."
        )
        natural_section = prompt[natural_ctas_start:natural_ctas_end]
        assert cta5 in natural_section, (
            f"_CTA_5 {cta5!r} not found in <natural_ctas> of assembled PRICING prompt. "
            "Fix A must be applied: update pre_expediente_pricing.md line ~90. AC-C.1."
        )

    def test_pricing_prompt_no_old_cta(self):
        """
        GIVEN a PRICING context
        WHEN the system prompt is assembled
        THEN the assembled prompt MUST NOT contain the old closed CTA anywhere.

        AC-C.2.
        """
        context = _pricing_transition_context()
        prompt = _assemble_pricing_prompt(context)
        assert self._OLD_CLOSED_CTA not in prompt, (
            f"Old CTA {self._OLD_CLOSED_CTA!r} found in assembled PRICING prompt. "
            "This CTA was replaced by _CTA_5 in Fix A. Do not revert pricing.md. AC-C.2."
        )

    def test_pricing_prompt_resolves_to_pricing_module_not_post_price(self):
        """
        GIVEN a PRICING context (precio_comunicado=False)
        WHEN the system prompt is assembled
        THEN the mode module MUST be the PRICING module (contains <pricing> tag),
             NOT the POST_PRICE module.

        This confirms the phase resolution is correct: during the transition
        turn, the LLM still receives the PRICING prompt (not POST_PRICE).
        Triangulation for AC-C.1.
        """
        context = _pricing_transition_context()
        prompt = _assemble_pricing_prompt(context)
        assert "<pricing>" in prompt, (
            "Assembled prompt for PRICING context must include <pricing> module. "
            "Phase resolution for precio_comunicado=False must return PRICING."
        )
        assert "<post_price>" not in prompt, (
            "Assembled PRICING prompt must NOT include <post_price> module. "
            "precio_comunicado=False must resolve to PRICING phase."
        )

    def test_post_price_prompt_contains_cta5_for_completeness(self):
        """
        GIVEN a POST_PRICE context (precio_comunicado=True)
        WHEN the system prompt is assembled
        THEN the assembled prompt MUST also contain _CTA_5.

        Completeness check: both PRICING and POST_PRICE prompts use _CTA_5.
        This ensures the CTA is consistent across the transition boundary.
        """
        cta5 = _get_cta5()
        context = {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 410},
            "element_codes": ["ASIDEROS", "SUBCHASIS"],
            "categoria_slug": "motos-part",
            "imagenes_enviadas_codigos": [],
        }
        prompt = _assemble_pricing_prompt(context)
        assert cta5 in prompt, (
            f"_CTA_5 {cta5!r} not found in assembled POST_PRICE prompt. "
            "Both PRICING and POST_PRICE prompts must use _CTA_5. AC-C.1 completeness."
        )
