"""
Unit tests for prompt loader template substitution (T05/T10).

Covers spec Capability 2: prompt-loader
- CTA placeholder {{CTA_N}} is substituted with catalog literal
- Unknown placeholder {{NOT_A_KEY}} is left unchanged
- {{LEXICAL_PROCEED_PHRASES}} is substituted with comma-sep quoted list
- get_prompt_stats() with no args does not raise NameError (CORE_MODULES fix)
- Snapshot: assembled prompt after placeholder edits is byte-identical to pre-edit snapshot
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

_SNAPSHOT_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "prompt_snapshots"


class TestCtaPlaceholderSubstitution:
    """{{CTA_N}} placeholders are replaced at load time."""

    def test_cta_placeholder_substituted(self, tmp_path: Path):
        """
        GIVEN a prompt file containing {{CTA_3}}
        WHEN _apply_prompt_catalog is called on its content
        THEN the returned string contains the literal CTA and NOT the placeholder.
        """
        from agent.prompts.loader import _apply_prompt_catalog

        raw = "Aquí va el CTA: {{CTA_3}}"
        result = _apply_prompt_catalog(raw)

        expected_literal = "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"
        assert expected_literal in result, (
            f"CTA_3 literal not found in result. Got: {result!r}"
        )
        assert "{{CTA_3}}" not in result, (
            f"Placeholder {{{{CTA_3}}}} still present in result. Got: {result!r}"
        )

    def test_all_cta_placeholders_substituted(self):
        """All 5 CTA placeholders must be substituted in one pass."""
        from agent.prompts.loader import _apply_prompt_catalog
        from agent.prompts.ctas_catalog import CTAS

        raw = " ".join(f"{{{{CTA_{n}}}}}" for n in range(1, 6))
        result = _apply_prompt_catalog(raw)

        for n in range(1, 6):
            assert f"{{{{CTA_{n}}}}}" not in result, (
                f"Placeholder {{{{CTA_{n}}}}} still present after substitution"
            )
            assert CTAS[n] in result, (
                f"CTAS[{n}] literal {CTAS[n]!r} not found in result"
            )


class TestUnknownPlaceholderPassthrough:
    """Unknown {{...}} patterns are left unchanged."""

    def test_unknown_placeholder_unchanged(self):
        """
        GIVEN a prompt containing {{NOT_A_CATALOG_KEY}}
        WHEN _apply_prompt_catalog is called
        THEN the placeholder survives unchanged and no exception is raised.
        """
        from agent.prompts.loader import _apply_prompt_catalog

        raw = "Keep this: {{NOT_A_CATALOG_KEY}} and also {{SOME_OTHER}}"
        result = _apply_prompt_catalog(raw)

        assert "{{NOT_A_CATALOG_KEY}}" in result, (
            "Unknown placeholder {{NOT_A_CATALOG_KEY}} was incorrectly removed"
        )
        assert "{{SOME_OTHER}}" in result, (
            "Unknown placeholder {{SOME_OTHER}} was incorrectly removed"
        )

    def test_single_brace_cta_not_touched(self):
        """Single-brace {CTA_3} must NOT be substituted (only double-brace)."""
        from agent.prompts.loader import _apply_prompt_catalog

        raw = "Single brace: {CTA_3}"
        result = _apply_prompt_catalog(raw)
        assert "{CTA_3}" in result, (
            "Single-brace {CTA_3} was incorrectly substituted — only {{CTA_N}} double-brace supported"
        )


class TestLexicalProceedPhrasesInjection:
    """{{LEXICAL_PROCEED_PHRASES}} is replaced with a comma-separated quoted list."""

    def test_lexical_proceed_phrases_injected(self):
        """
        GIVEN a prompt containing {{LEXICAL_PROCEED_PHRASES}}
        WHEN _apply_prompt_catalog is called
        THEN the placeholder is replaced with a quoted comma-separated list of phrases
        AND the raw placeholder is absent.
        """
        from agent.prompts.loader import _apply_prompt_catalog
        from agent.prompts.lexical_triggers import PROCEED_PHRASES

        raw = "Frases: {{LEXICAL_PROCEED_PHRASES}}"
        result = _apply_prompt_catalog(raw)

        assert "{{LEXICAL_PROCEED_PHRASES}}" not in result, (
            "Placeholder {{LEXICAL_PROCEED_PHRASES}} still present after substitution"
        )
        # Each phrase should appear quoted in the output
        for phrase in PROCEED_PHRASES:
            assert f'"{phrase}"' in result, (
                f'Phrase {phrase!r} not found quoted in substitution result'
            )

    def test_render_proceed_phrases_format(self):
        """_render_proceed_phrases must return a comma-separated quoted string."""
        from agent.prompts.loader import _render_proceed_phrases

        rendered = _render_proceed_phrases()
        assert '"quiero homologar"' in rendered
        assert '"legalizar"' in rendered
        # comma-separated
        assert "," in rendered


class TestGetPromptStatsNoArgs:
    """get_prompt_stats() with no args must not raise NameError (CORE_MODULES fix)."""

    def test_get_prompt_stats_no_args_ok(self):
        """
        GIVEN loader.py with corrected CORE_MODULE reference
        WHEN get_prompt_stats() is called with no arguments
        THEN it returns a dict without raising NameError.
        """
        from agent.prompts.loader import get_prompt_stats

        result = get_prompt_stats()
        assert isinstance(result, dict), (
            f"get_prompt_stats() must return a dict, got {type(result).__name__}"
        )
        # Must have these keys from the stats structure
        assert "core_modules_count" in result
        assert "mode_modules" in result


# ---------------------------------------------------------------------------
# T10: Snapshot verification — assembled output byte-identical after edits
# ---------------------------------------------------------------------------


import pytest


class TestSnapshotVerification:
    """Assembled prompt output MUST be byte-identical to pre-edit snapshots.

    After replacing literal CTAs with {{CTA_N}} placeholders in prompt files,
    the loader's substitution must restore the exact original strings.
    """

    @pytest.mark.parametrize("phase,mode_context,snapshot_file", [
        (
            "DISCOVERY",
            {},
            "pre_expediente_discovery_before.txt",
        ),
        (
            "PRICING",
            {"element_codes": ["ESCAPE"]},
            "pre_expediente_pricing_before.txt",
        ),
        (
            "POST_PRICE",
            {"element_codes": ["ESCAPE"], "precio_comunicado": True},
            "pre_expediente_post_price_before.txt",
        ),
    ])
    def test_assembled_prompt_matches_snapshot(self, phase, mode_context, snapshot_file):
        """
        GIVEN the prompt files with {{CTA_N}} placeholders
        WHEN assemble_system_prompt() is called
        THEN the output is byte-identical to the pre-edit snapshot (substitution preserves behavior).
        """
        snapshot_path = _SNAPSHOT_DIR / snapshot_file
        if not snapshot_path.exists():
            pytest.skip(f"Snapshot {snapshot_file} not found — run T08 first")

        expected = snapshot_path.read_text(encoding="utf-8")

        from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache
        clear_prompt_cache()
        result = assemble_system_prompt("PRE_EXPEDIENTE_MODE", mode_context=mode_context)

        assert result == expected, (
            f"Phase {phase}: assembled prompt does not match pre-edit snapshot. "
            f"Substitution changed behavior. First diff at char "
            f"{next((i for i, (a, b) in enumerate(zip(result, expected)) if a != b), min(len(result), len(expected)))}"
        )
