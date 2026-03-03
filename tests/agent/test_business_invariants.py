"""
Business invariant regression tests.

TEXT-BASED tests that verify production prompt files contain the right
instructions for critical business rules.  These tests read the actual
.md prompt files and assert that required patterns are present.

Purpose: catch accidental deletion or corruption of business-critical
rules during prompt editing.

Phase 5, Task 5.4 — agent-harmony-latency-hardening.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


# =============================================================================
# Helpers
# =============================================================================

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _PROJECT_ROOT / "agent" / "prompts"
_CORE_DIR = _PROMPTS_DIR / "core"
_MODES_DIR = _PROMPTS_DIR / "modes"


def _read_prompt(relative_path: str) -> str:
    """Read a prompt file relative to agent/prompts/."""
    filepath = _PROMPTS_DIR / relative_path
    if not filepath.exists():
        pytest.skip(f"Prompt file not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


def _read_all_prompts() -> str:
    """Read and concatenate all .md prompt files."""
    texts = []
    for root, _dirs, files in os.walk(str(_PROMPTS_DIR)):
        for fname in sorted(files):
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                texts.append(Path(fpath).read_text(encoding="utf-8"))
    return "\n\n".join(texts)


def _prompt_contains(text: str, pattern: str, flags: int = re.IGNORECASE) -> bool:
    """Check if any line in text matches the regex pattern."""
    return bool(re.search(pattern, text, flags))


# =============================================================================
# Task 5.4.1 — Price-before-images rule
# =============================================================================


class TestPriceBeforeImagesRule:
    """Verify prompt files contain the price-before-images business rule."""

    def test_presupuesto_mode_mentions_price_before_images(self):
        """presupuesto_mode.md must instruct price before images."""
        text = _read_prompt("modes/presupuesto_mode.md")

        assert _prompt_contains(
            text,
            r"precio.*antes.*im[aá]gen|PRECIO\s+ANTES.*im[aá]gen|NUNCA\s+envi.*sin.*precio|precio.*primero",
        ), "presupuesto_mode.md must contain price-before-images rule"

    def test_pricing_rules_mention_communicate_price(self):
        """07_pricing_rules.md must instruct always communicating the price."""
        text = _read_prompt("core/07_pricing_rules.md")

        assert _prompt_contains(
            text,
            r"comunica.*precio|SIEMPRE.*comunica.*precio|di\s+el\s+precio",
        ), "07_pricing_rules.md must mention communicating the price"

    def test_price_before_images_in_any_prompt(self):
        """At least one prompt file must contain explicit price-before-images rule."""
        all_text = _read_all_prompts()

        # Search for the canonical rule statement
        assert _prompt_contains(
            all_text,
            r"precio.*antes.*(?:fotos|im[aá]gen)|NUNCA.*(?:fotos|im[aá]gen).*sin.*precio",
        ), "No prompt file contains the price-before-images rule"


# =============================================================================
# Task 5.4.2 — No-re-identification rule
# =============================================================================


class TestNoReIdentificationRule:
    """Verify prompt files contain the no-re-identification rule."""

    def test_presupuesto_mode_mentions_seleccionar_variante(self):
        """presupuesto_mode.md must instruct using seleccionar_variante_por_respuesta."""
        text = _read_prompt("modes/presupuesto_mode.md")

        assert _prompt_contains(
            text,
            r"seleccionar_variante_por_respuesta",
        ), "presupuesto_mode.md must mention seleccionar_variante_por_respuesta"

    def test_presupuesto_mode_prohibits_re_identification(self):
        """presupuesto_mode.md must prohibit re-identification after variant."""
        text = _read_prompt("modes/presupuesto_mode.md")

        assert _prompt_contains(
            text,
            r"NUNCA.*re-identif|NUNCA.*identificar_y_resolver.*variante|NO.*re-identif",
        ), "presupuesto_mode.md must prohibit re-identification for variants"

    def test_anti_patterns_mention_variant_rule(self):
        """04_anti_patterns.md must mention the variant resolution rule."""
        text = _read_prompt("core/04_anti_patterns.md")

        assert _prompt_contains(
            text,
            r"seleccionar_variante_por_respuesta|variante.*identificar",
        ), "04_anti_patterns.md must mention variant resolution rule"

    def test_no_re_identification_in_any_prompt(self):
        """At least one prompt must prohibit re-identification for variants."""
        all_text = _read_all_prompts()

        assert _prompt_contains(
            all_text,
            r"NUNCA.*(?:re-identif|vuelvas.*identificar_y_resolver)",
        ), "No prompt file contains the no-re-identification rule"


# =============================================================================
# Task 5.4.3 — skip_validation reminder
# =============================================================================


class TestSkipValidationReminder:
    """Verify prompt files contain the skip_validation=True reminder."""

    def test_presupuesto_mode_mentions_skip_validation(self):
        """presupuesto_mode.md must mention skip_validation=True."""
        text = _read_prompt("modes/presupuesto_mode.md")

        assert _prompt_contains(
            text,
            r"skip_validation\s*=\s*True",
        ), "presupuesto_mode.md must mention skip_validation=True"

    def test_tools_efficiency_mentions_skip_validation(self):
        """05_tools_efficiency.md must mention skip_validation."""
        text = _read_prompt("core/05_tools_efficiency.md")

        assert _prompt_contains(
            text,
            r"skip_validation",
        ), "05_tools_efficiency.md must mention skip_validation"

    def test_skip_validation_appears_in_tool_call_examples(self):
        """presupuesto_mode.md must show skip_validation in tool call examples."""
        text = _read_prompt("modes/presupuesto_mode.md")

        # Should appear in the context of calcular_tarifa_con_elementos
        assert _prompt_contains(
            text,
            r"calcular_tarifa_con_elementos.*skip_validation",
        ), (
            "presupuesto_mode.md must show skip_validation=True "
            "in calcular_tarifa_con_elementos examples"
        )

    def test_skip_validation_in_any_prompt(self):
        """At least one prompt must mention skip_validation=True."""
        all_text = _read_all_prompts()

        assert _prompt_contains(
            all_text,
            r"skip_validation\s*=\s*True",
        ), "No prompt file contains skip_validation=True"


# =============================================================================
# Task 5.4.4 — Mode transitions use return-based pattern
# =============================================================================


class TestModeTransitionPattern:
    """Verify mode transition instructions use return-based pattern.

    Mode transitions must happen via returning state updates (e.g.
    ``return {"current_mode": "NEW_MODE"}``) rather than by direct
    mutation of state (e.g. ``state["current_mode"] = ...``).

    These tests verify that the prompts and source code follow this
    convention.
    """

    def test_conversation_state_has_transition_mode_function(self):
        """conversation_state.py must export transition_mode()."""
        from agent.state.conversation_state import transition_mode

        assert callable(transition_mode)

    def test_transition_mode_returns_dict_with_current_mode(self):
        """transition_mode() must return dict containing current_mode."""
        from agent.state.conversation_state import (
            ConversationState,
            create_initial_state,
            transition_mode,
        )

        state = create_initial_state(
            conversation_id="test-123",
            phone="+34600000001",
        )

        result = transition_mode(state, "PRESUPUESTO_MODE")

        assert isinstance(result, dict)
        assert "current_mode" in result
        assert result["current_mode"] == "PRESUPUESTO_MODE"

    def test_transition_mode_does_not_mutate_state(self):
        """transition_mode() must NOT mutate the input state."""
        from agent.state.conversation_state import (
            create_initial_state,
            transition_mode,
        )

        state = create_initial_state(
            conversation_id="test-456",
            phone="+34600000002",
        )
        original_mode = state.get("current_mode")

        _ = transition_mode(state, "EXPEDIENTE_MODE")

        assert state.get("current_mode") == original_mode, (
            "transition_mode() must not mutate the input state"
        )

    def test_prompts_do_not_instruct_direct_state_mutation(self):
        """Prompt files must not instruct direct state mutation.

        We check that no prompt file contains patterns like:
        ``state["current_mode"] = ...`` or ``state.current_mode = ...``
        which would indicate direct mutation instructions.
        """
        all_text = _read_all_prompts()

        # Check for direct mutation patterns
        direct_mutation = re.search(
            r'state\s*\[\s*["\']current_mode["\']\s*\]\s*=',
            all_text,
        )

        if direct_mutation:
            # Find context around the match
            start = max(0, direct_mutation.start() - 50)
            end = min(len(all_text), direct_mutation.end() + 50)
            context = all_text[start:end].strip()

            # Only fail if it's NOT inside a negative example
            lines = all_text[:direct_mutation.start()].splitlines()
            line_num = len(lines)
            nearby_text = all_text[max(0, direct_mutation.start() - 200):direct_mutation.end()]

            is_negative = bool(re.search(
                r"❌|INCORRECTO|WRONG|NUNCA|NO\s+(?:hagas|modifiques|uses)",
                nearby_text,
                re.IGNORECASE,
            ))

            if not is_negative:
                pytest.fail(
                    f"Prompt contains direct state mutation instruction "
                    f"(line ~{line_num}): ...{context}..."
                )

    def test_presupuesto_mode_does_not_instruct_direct_mode_set(self):
        """presupuesto_mode.md must not instruct setting mode directly."""
        text = _read_prompt("modes/presupuesto_mode.md")

        # Look for "current_mode =" or similar direct assignment
        # Exclude negative examples (marked with ❌, INCORRECTO, etc.)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'current_mode\s*=\s*["\']', line):
                # Check if this is a negative example
                start = max(0, i - 5)
                context_block = "\n".join(lines[start : i + 1])
                is_negative = bool(re.search(
                    r"❌|INCORRECTO|WRONG|NUNCA|NO\s+(?:hagas|modifiques)",
                    context_block,
                    re.IGNORECASE,
                ))
                if not is_negative:
                    pytest.fail(
                        f"presupuesto_mode.md line {i + 1} contains "
                        f"direct mode assignment: {line.strip()}"
                    )


# =============================================================================
# Prompt file inventory — ensure critical files exist
# =============================================================================


class TestPromptFileInventory:
    """Verify that all expected prompt files exist."""

    @pytest.mark.parametrize(
        "prompt_path",
        [
            "core/01_security.md",
            "core/02_identity.md",
            "core/03_format_style.md",
            "core/04_anti_patterns.md",
            "core/05_tools_efficiency.md",
            "core/06_escalation.md",
            "core/07_pricing_rules.md",
            "core/08_documentation.md",
            "modes/consulta_mode.md",
            "modes/presupuesto_mode.md",
        ],
    )
    def test_prompt_file_exists(self, prompt_path: str):
        """Critical prompt file must exist."""
        filepath = _PROMPTS_DIR / prompt_path
        assert filepath.exists(), f"Missing critical prompt file: {prompt_path}"

    @pytest.mark.parametrize(
        "prompt_path",
        [
            "core/04_anti_patterns.md",
            "core/05_tools_efficiency.md",
            "core/07_pricing_rules.md",
            "modes/presupuesto_mode.md",
        ],
    )
    def test_prompt_file_is_nonempty(self, prompt_path: str):
        """Critical prompt file must not be empty."""
        filepath = _PROMPTS_DIR / prompt_path
        if not filepath.exists():
            pytest.skip(f"File not found: {prompt_path}")
        content = filepath.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, (
            f"Prompt file {prompt_path} is suspiciously short ({len(content)} chars)"
        )
