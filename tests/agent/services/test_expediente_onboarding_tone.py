"""
Batch 3 — Layer C: Warm Tone Rewrite tests.

B3-T1 [RED]: golden-string test — opener whitelist + enviar_imagenes_ejemplo +
             invitation to ask for examples.
B3-T2 [RED]: contract test — forbidden-behaviors block keywords preserved.

Spec domain: expediente-onboarding-tone
Design section: Layer C — warm opener whitelist
"""

from __future__ import annotations

import pytest

from agent.services.expediente_onboarding import build_new_expediente_case_instructions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPENER_WHITELIST = [
    "¡Estupendo!",
    "¡Perfecto!",
    "¡Dale!",
]


def _build(
    first_element_display: str = "SUBCHASIS",
    total_elements: int = 3,
    prefilled_context: str = "",
    element_photo_instructions: str = "",
) -> str:
    return build_new_expediente_case_instructions(
        first_element_display=first_element_display,
        total_elements=total_elements,
        prefilled_context=prefilled_context,
        element_photo_instructions=element_photo_instructions,
    )


# ---------------------------------------------------------------------------
# B3-T1 — Golden-string: opener whitelist + tool call + invitation
# ---------------------------------------------------------------------------


class TestWarmToneGoldenStrings:
    """B3-T1: assert the warm-tone contract on the instruction string."""

    def test_contains_opener_from_whitelist(self):
        """
        B3-T1a: the instruction MUST contain at least one opener from the
        whitelist ["¡Estupendo!", "¡Perfecto!", "¡Dale!"].

        RED: fails while 'EXPEDIENTE CREADO' opener is still in place.
        """
        result = _build()
        found = any(opener in result for opener in _OPENER_WHITELIST)
        assert found, (
            f"Expected at least one opener from whitelist {_OPENER_WHITELIST!r} "
            f"but none found.\nGot:\n{result}"
        )

    def test_does_not_start_with_bureaucratic_opener(self):
        """
        B3-T1b: the instruction MUST NOT contain 'EXPEDIENTE CREADO' — the old
        bureaucratic opener that the design explicitly prohibits.

        RED: fails on current implementation.
        """
        result = _build()
        assert "EXPEDIENTE CREADO" not in result, (
            "'EXPEDIENTE CREADO' is the forbidden bureaucratic opener. "
            f"It must be replaced by a warm opener from the whitelist.\nGot:\n{result}"
        )

    def test_references_enviar_imagenes_ejemplo(self):
        """
        B3-T1c: the instruction MUST tell the LLM to call enviar_imagenes_ejemplo
        so the photo descriptions come from the gate (not invented).

        Stays GREEN after rewrite (already present), included here as a
        regression anchor.
        """
        result = _build()
        assert "enviar_imagenes_ejemplo" in result, (
            "enviar_imagenes_ejemplo must be referenced so the LLM gets literal "
            f"photo descriptions from the dual-mode gate.\nGot:\n{result}"
        )

    def test_contains_invitation_to_ask_for_examples(self):
        """
        B3-T1d: the instruction MUST invite the user to ask for example images
        using the canonical voseo phrase 'Si querés ver ejemplos'.

        RED: fails on current implementation (no such phrase exists).
        """
        result = _build()
        assert "Si querés ver ejemplos" in result, (
            "The instruction must close with an invitation for the user to ask "
            "for example images. Expected 'Si querés ver ejemplos' substring.\n"
            f"Got:\n{result}"
        )

    def test_element_and_total_still_present(self):
        """
        B3-T1e: placeholders first_element_display and total_elements must be
        rendered (regression anchor — must survive warm rewrite).
        """
        result = _build(first_element_display="ESCAPE", total_elements=2)
        assert "ESCAPE" in result, "first_element_display placeholder missing after rewrite."
        assert "2" in result, "total_elements placeholder missing after rewrite."


# ---------------------------------------------------------------------------
# B3-T2 — Contract: forbidden-behaviors block preserved
# ---------------------------------------------------------------------------


class TestForbiddenBehaviorsBlockPreserved:
    """B3-T2: keywords from the forbidden-behaviors section must survive rewrite."""

    def test_iniciar_expediente_forbidden_preserved(self):
        """
        B3-T2a: the instruction MUST warn the LLM NOT to call iniciar_expediente().
        This is a hard safety rail — removing it would allow re-creation bugs.

        Stays RED if the forbidden-behaviors section is accidentally dropped.
        """
        result = _build()
        assert "iniciar_expediente" in result, (
            "The forbidden-behaviors block MUST warn about iniciar_expediente(). "
            f"It appears to have been removed.\nGot:\n{result}"
        )

    def test_finalizar_expediente_gatekeeper_preserved(self):
        """
        B3-T2b: the instruction MUST warn about finalizar_expediente() being the
        gatekeeper — LLM must not declare expediente complete without it.

        Stays RED if the gatekeeper warning is accidentally dropped.
        """
        result = _build()
        assert "finalizar_expediente" in result, (
            "The forbidden-behaviors block MUST reference finalizar_expediente() "
            f"as the gatekeeper. It appears to have been removed.\nGot:\n{result}"
        )

    def test_prefilled_context_injected(self):
        """
        B3-T2c: prefilled_context kwarg must appear verbatim in the output.
        """
        ctx = "Contexto previo: cliente vip."
        result = _build(prefilled_context=ctx)
        assert ctx in result, (
            f"prefilled_context {ctx!r} must appear verbatim in the output.\n"
            f"Got:\n{result}"
        )

    def test_element_photo_instructions_injected(self):
        """
        B3-T2d: element_photo_instructions kwarg must appear verbatim in the output.
        """
        extra = "FOTOS ADICIONALES: panorámica del vano motor."
        result = _build(element_photo_instructions=extra)
        assert extra in result, (
            f"element_photo_instructions {extra!r} must appear verbatim.\n"
            f"Got:\n{result}"
        )
