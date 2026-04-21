"""
Unit tests for expediente_onboarding.py — expediente-transition-ux BUG-3 + T3c + Layer C.

BUG-3: build_new_expediente_case_instructions() had contradictory image instruction.
The INSTRUCCIONES OBLIGATORIAS block instructed the LLM to ASK the user if they want
to see example images ("1. Pregunta al usuario si quiere ver imágenes de ejemplo..."),
while expediente_documentacion_elementos.md line 86 said to send automatically.
The <CASE_CONTEXT> block has higher priority than the .md prompt, so the LLM asked.

Layer C (Batch 3) warm-tone rewrite: replaced bureaucratic "EXPEDIENTE CREADO" opener
with a 3-option warm opener whitelist. The LLM now CALLS enviar_imagenes_ejemplo() and
reasons about photo descriptions from the gate — instead of auto-narrating. The invitation
"Si querés ver ejemplos" closes the turn.

T3c update: intro_already_sent parameter removed — subgraph (entry_router) now owns
delivery of the 6-phase overview. There is ONE code path; LLM always starts directly
with phase 1 content.

Scenarios:
  1. Output does NOT contain "Pregunta al usuario si quiere ver imágenes" (no ask-first)
  2. Output references enviar_imagenes_ejemplo (the tool call must be instructed)
  3. Output contains "automáticamente" (subgraph delivers overview — always true)
  4. Output does NOT contain "COMUNICA al usuario exactamente" (no inline embed)
  5. Output contains opener from whitelist (Layer C — warm tone)
  6. Output does NOT contain "EXPEDIENTE CREADO" (forbidden bureaucratic opener)
  7. intro_already_sent parameter absent (T3c)
"""

from __future__ import annotations

import pytest

from agent.services.expediente_onboarding import build_new_expediente_case_instructions


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestBuildNewExpedienteCaseInstructionsBUG3:
    """BUG-3 + T3c + Layer C — build_new_expediente_case_instructions() must use
    warm opener whitelist, instruct the LLM to call the tool, and have a single
    code path (intro_already_sent parameter removed)."""

    _OPENER_WHITELIST = ["¡Estupendo!", "¡Perfecto!", "¡Dale!"]

    def _build(self) -> str:
        """Helper to build instructions with default args."""
        return build_new_expediente_case_instructions(
            first_element_display="ESCAPE",
            total_elements=2,
            prefilled_context="",
            element_photo_instructions="",
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
        THEN the output MUST reference enviar_imagenes_ejemplo (tool call instructed)

        Layer C: the LLM is instructed to CALL the tool so descriptions come from
        the dual-mode gate — not invented or auto-narrated.
        """
        result = self._build()
        assert "enviar_imagenes_ejemplo" in result, (
            f"Expected 'enviar_imagenes_ejemplo' reference in case_instructions, got:\n{result}"
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

    def test_contains_warm_opener_from_whitelist(self):
        """
        Layer C: the instruction MUST contain at least one opener from the whitelist.
        Ensures the LLM starts with a warm phrase instead of a bureaucratic one.
        """
        result = self._build()
        found = any(opener in result for opener in self._OPENER_WHITELIST)
        assert found, (
            f"Expected at least one opener from {self._OPENER_WHITELIST!r}.\nGot:\n{result}"
        )

    def test_does_not_contain_bureaucratic_opener(self):
        """
        Layer C: 'EXPEDIENTE CREADO' is the forbidden bureaucratic opener.
        It must be absent after the warm-tone rewrite.
        """
        result = self._build()
        assert "EXPEDIENTE CREADO" not in result, (
            f"'EXPEDIENTE CREADO' must not appear after Layer C rewrite.\nGot:\n{result}"
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
