"""
Unit tests for expediente_onboarding.py — expediente-transition-ux BUG-3 + T3c.

BUG-3: build_new_expediente_case_instructions() had contradictory image instruction.
The INSTRUCCIONES OBLIGATORIAS block instructed the LLM to ASK the user if they want
to see example images ("1. Pregunta al usuario si quiere ver imágenes de ejemplo..."),
while expediente_documentacion_elementos.md line 86 said to send automatically.
The <CASE_CONTEXT> block has higher priority than the .md prompt, so the LLM asked.

Fix: Instruction 1 now says "ENVÍA AUTOMÁTICAMENTE las fotos de ejemplo".
     Instruction 2 now says "Narra el envío DESPUÉS de recibir el resultado...".

T3c update: intro_already_sent parameter removed — subgraph (entry_router) now owns
delivery of the 6-phase overview. There is ONE code path; LLM always starts directly
with phase 1 content. Scenarios 4 and 5 updated to reflect the new contract.

Scenarios:
  1. Output contains "ENVÍA AUTOMÁTICAMENTE"
  2. Output does NOT contain "Pregunta al usuario si quiere ver imágenes"
  3. Output references enviar_imagenes_ejemplo()
  4. Output contains "automáticamente" (subgraph delivers overview — always true)
  5. Output does NOT contain "COMUNICA al usuario exactamente" (no inline embed)
"""

from __future__ import annotations

import pytest

from agent.services.expediente_onboarding import build_new_expediente_case_instructions


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestBuildNewExpedienteCaseInstructionsBUG3:
    """BUG-3 + T3c — build_new_expediente_case_instructions() must instruct auto-send
    and must have a single code path (intro_already_sent parameter removed)."""

    def _build(self) -> str:
        """Helper to build instructions with default args (no intro_already_sent)."""
        return build_new_expediente_case_instructions(
            first_element_display="ESCAPE",
            total_elements=2,
            prefilled_context="",
            element_photo_instructions="",
        )

    def test_contains_auto_send_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN the output MUST contain 'ENVÍA AUTOMÁTICAMENTE'
        """
        result = self._build()
        assert "ENVÍA AUTOMÁTICAMENTE" in result, (
            f"Expected 'ENVÍA AUTOMÁTICAMENTE' in case_instructions, got:\n{result}"
        )

    def test_does_not_contain_ask_first_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN the output MUST NOT contain the old 'ask first' instruction
        """
        result = self._build()
        assert "Pregunta al usuario si quiere ver imágenes" not in result, (
            f"Old 'ask first' instruction must not appear in case_instructions, got:\n{result}"
        )

    def test_references_enviar_imagenes_ejemplo(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN the output MUST reference enviar_imagenes_ejemplo()
        """
        result = self._build()
        assert "enviar_imagenes_ejemplo()" in result, (
            f"Expected 'enviar_imagenes_ejemplo()' reference in case_instructions, got:\n{result}"
        )

    def test_narrate_after_result_instruction(self):
        """
        GIVEN build_new_expediente_case_instructions() is called
        THEN instruction 2 must say to narrate AFTER receiving result, not before
        """
        result = self._build()
        assert "DESPUÉS de recibir el resultado" in result, (
            f"Expected 'DESPUÉS de recibir el resultado' in case_instructions, got:\n{result}"
        )

    def test_single_code_path_says_system_delivers_overview(self):
        """
        T3c: After simplification, there is ONE code path.
        The subgraph (entry_router) delivers the 6-phase overview separately.
        The LLM instructions must mention this (e.g. "ya ha enviado" or "automáticamente").
        """
        result = self._build()
        assert "automáticamente" in result.lower(), (
            f"Expected 'automáticamente' indicating subgraph owns overview delivery, got:\n{result}"
        )

    def test_no_inline_embed_of_overview(self):
        """
        T3c: The 6-phase overview must NOT be embedded inline in case_instructions.
        The subgraph emits it as a standalone AIMessage before this prompt runs.
        """
        result = self._build()
        assert "COMUNICA al usuario exactamente este mensaje" not in result, (
            f"case_instructions must NOT embed the full overview inline after T3c, got:\n{result}"
        )

    def test_no_intro_already_sent_param(self):
        """
        T3c: intro_already_sent parameter must be removed from the function signature.
        """
        import inspect

        sig = inspect.signature(build_new_expediente_case_instructions)
        assert "intro_already_sent" not in sig.parameters, (
            "intro_already_sent must be removed from build_new_expediente_case_instructions"
        )
