"""
Unit tests for expediente_onboarding.py — expediente-transition-ux BUG-3.

BUG-3: build_new_expediente_case_instructions() had contradictory image instruction.
The INSTRUCCIONES OBLIGATORIAS block instructed the LLM to ASK the user if they want
to see example images ("1. Pregunta al usuario si quiere ver imágenes de ejemplo..."),
while expediente_documentacion_elementos.md line 86 said to send automatically.
The <CASE_CONTEXT> block has higher priority than the .md prompt, so the LLM asked.

Fix: Instruction 1 now says "ENVÍA AUTOMÁTICAMENTE las fotos de ejemplo".
     Instruction 2 now says "Narra el envío DESPUÉS de recibir el resultado...".

Scenarios:
  1. Output contains "ENVÍA AUTOMÁTICAMENTE"
  2. Output does NOT contain "Pregunta al usuario si quiere ver imágenes"
  3. Output references enviar_imagenes_ejemplo()
  4. intro_already_sent=True path: output contains "automáticamente" (the auto-send variant)
  5. intro_already_sent=False path: output contains "COMUNICA al usuario" (the embed variant)
"""

from __future__ import annotations

import pytest

from agent.services.expediente_onboarding import build_new_expediente_case_instructions


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestBuildNewExpedienteCaseInstructionsBUG3:
    """BUG-3 — build_new_expediente_case_instructions() must instruct auto-send."""

    def _build(self, intro_already_sent: bool = True) -> str:
        """Helper to build instructions with default args."""
        return build_new_expediente_case_instructions(
            first_element_display="ESCAPE",
            total_elements=2,
            prefilled_context="",
            element_photo_instructions="",
            intro_already_sent=intro_already_sent,
            auto_created=True,
        )

    def test_contains_auto_send_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        WHEN intro_already_sent=True (auto-create path)
        THEN the output MUST contain 'ENVÍA AUTOMÁTICAMENTE'
        """
        result = self._build(intro_already_sent=True)
        assert "ENVÍA AUTOMÁTICAMENTE" in result, (
            f"Expected 'ENVÍA AUTOMÁTICAMENTE' in case_instructions, got:\n{result}"
        )

    def test_does_not_contain_ask_first_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN the output MUST NOT contain the old 'ask first' instruction
        """
        result = self._build(intro_already_sent=True)
        assert "Pregunta al usuario si quiere ver imágenes" not in result, (
            f"Old 'ask first' instruction must not appear in case_instructions, got:\n{result}"
        )

    def test_references_enviar_imagenes_ejemplo(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN the output MUST reference enviar_imagenes_ejemplo()
        """
        result = self._build(intro_already_sent=True)
        assert "enviar_imagenes_ejemplo()" in result, (
            f"Expected 'enviar_imagenes_ejemplo()' reference in case_instructions, got:\n{result}"
        )

    def test_narrate_after_result_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN instruction 2 must say to narrate AFTER receiving result, not before
        """
        result = self._build(intro_already_sent=True)
        assert "DESPUÉS de recibir el resultado" in result, (
            f"Expected 'DESPUÉS de recibir el resultado' in case_instructions, got:\n{result}"
        )

    def test_intro_already_sent_true_uses_auto_send_variant(self):
        """
        GIVEN intro_already_sent=True
        WHEN the instructions are built
        THEN the intro block should say the system sends the overview automatically
        (NOT embed the full overview text in case_instructions)
        """
        result = self._build(intro_already_sent=True)
        # The auto-send variant says "automáticamente"
        assert "automáticamente" in result.lower(), (
            f"Expected 'automáticamente' in intro block for intro_already_sent=True, got:\n{result}"
        )
        # The full overview embed variant says "COMUNICA al usuario exactamente este mensaje"
        assert "COMUNICA al usuario exactamente este mensaje" not in result, (
            f"intro_already_sent=True must NOT embed full overview; got:\n{result}"
        )

    def test_intro_already_sent_false_embeds_full_overview(self):
        """
        GIVEN intro_already_sent=False
        WHEN the instructions are built
        THEN the intro block must embed the full overview (COMUNICA directive)
        """
        result = self._build(intro_already_sent=False)
        assert "COMUNICA al usuario exactamente este mensaje" in result, (
            f"Expected full overview embed for intro_already_sent=False, got:\n{result}"
        )
