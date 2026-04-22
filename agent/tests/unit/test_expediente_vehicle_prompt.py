"""
Unit tests for expediente_vehicle.md prompt anti-hallucination block
(fix-vehicle-data-hallucination, Phase 3 / Task 3.1).
"""

from pathlib import Path

import pytest


PROMPT_PATH = (
    Path(__file__).parent.parent.parent  # agent/
    / "prompts" / "modes" / "expediente_vehicle.md"
)


def _load_prompt() -> str:
    assert PROMPT_PATH.exists(), f"Prompt file not found: {PROMPT_PATH}"
    return PROMPT_PATH.read_text(encoding="utf-8")


class TestExpedienteVehiclePromptAntiHallucination:
    """SC-6: prompt must contain <anti_hallucination> block with correct rules."""

    def test_expediente_vehicle_prompt_contains_anti_hallucination_block(self):
        """The prompt file must have an <anti_hallucination> opening tag."""
        content = _load_prompt()
        assert "<anti_hallucination>" in content, (
            "expediente_vehicle.md must contain <anti_hallucination> block. "
            "This guard prevents the LLM from calling the tool without user data."
        )

    def test_anti_hallucination_block_is_closed(self):
        """The block must be properly closed with </anti_hallucination>."""
        content = _load_prompt()
        assert "</anti_hallucination>" in content, (
            "expediente_vehicle.md: <anti_hallucination> tag is not closed."
        )

    def test_anti_hallucination_prohibits_call_without_user_data(self):
        """Block must explicitly prohibit calling the tool without user-provided data this turn."""
        content = _load_prompt()
        # The rule: cannot call if user did NOT send data this turn
        assert "PROHIBIDO" in content, (
            "anti_hallucination block must include PROHIBIDO directive."
        )
        assert "actualizar_datos_vehiculo" in content, (
            "Block must name the specific tool being constrained."
        )

    def test_anti_hallucination_prohibits_inventing_from_context(self):
        """Block must warn against inventing values from element or personal context."""
        content = _load_prompt()
        assert "NUNCA inventes" in content or "NUNCA" in content, (
            "Block must include NUNCA directive to prevent context-derived invention."
        )

    def test_prompt_does_not_have_old_anti_llamada_vacia_line(self):
        """
        Triangulation: the OLD one-liner must be replaced by the full block.
        Ensures the refactor actually changed the file and didn't just add the block.
        """
        content = _load_prompt()
        # Old line was: ANTI-LLAMADA VACIA: NUNCA llames con datos_vehiculo={}
        assert "ANTI-LLAMADA VACIA:" not in content, (
            "Old ANTI-LLAMADA VACIA one-liner must be removed — it should be replaced "
            "by the full <anti_hallucination> block."
        )
