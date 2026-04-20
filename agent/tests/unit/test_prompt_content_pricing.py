"""
Unit tests for pre_expediente_pricing.md prompt content (Batch A).

Covers AC-4.1: warning bullets use per-line ⚠️ pattern.
Covers AC-4.4: missing-image instruction for base docs (DNI/permiso).

These are prompt-snapshot tests — they read the markdown file on disk and
assert its content. They fail when the prompt drifts from the spec.

Design: pure file-content assertions. No mocks, no async, no imports
beyond pathlib. The tests act as a living spec for the prompt author.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Path to the prompt file under test
# ---------------------------------------------------------------------------

_PRICING_MD = (
    Path(__file__).parents[3] / "agent" / "prompts" / "modes" / "pre_expediente_pricing.md"
)


# ---------------------------------------------------------------------------
# Helper — load file content once per process (fast, no caching issues)
# ---------------------------------------------------------------------------


def _load() -> str:
    return _PRICING_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-4.1 — Warning bullets: per-line ⚠️ pattern, NOT "forma natural" prose
# ---------------------------------------------------------------------------


class TestWarningBulletFormat:
    """AC-4.1: each warning MUST be emitted on its own line with ⚠️ prefix."""

    def test_pricing_md_does_not_instruct_cursiva_forma_natural(self):
        """
        GIVEN the pricing markdown
        WHEN inspected for the old inline-prose instruction
        THEN 'en cursiva y forma natural' MUST NOT appear (case-insensitive).

        This instruction caused the LLM to merge warnings into a single italic
        sentence instead of separate bullet lines.
        """
        content = _load()
        assert "forma natural" not in content.lower(), (
            "pre_expediente_pricing.md still contains the old 'forma natural' "
            "instruction. Replace it with a per-line ⚠️ bullet rule per AC-4.1."
        )

    def test_pricing_md_instructs_per_line_warning_bullet(self):
        """
        GIVEN the pricing markdown
        WHEN inspected for the per-line bullet instruction
        THEN the file MUST contain an instruction for ⚠️ per-line format.

        We accept any phrasing that includes '⚠️' followed by a reference to
        'línea' or 'bullet' or 'separada', OR simply contains the bullet template
        '⚠️ [' which explicitly teaches the LLM the output format.
        """
        content = _load()
        has_bullet_template = "⚠️ [" in content
        has_per_line_instruction = any(
            phrase in content.lower()
            for phrase in ["por línea", "línea separada", "cada advertencia en", "cada ⚠️"]
        )
        assert has_bullet_template or has_per_line_instruction, (
            "pre_expediente_pricing.md must contain a per-line ⚠️ bullet instruction "
            "(e.g. '⚠️ [texto]' template or explicit line-per-warning rule). AC-4.1."
        )


# ---------------------------------------------------------------------------
# AC-4.4 — Explicit missing-image note for base docs
# ---------------------------------------------------------------------------


class TestMissingImageInstructionForBaseDocs:
    """AC-4.4: when a base doc has no example image, LLM must say so explicitly."""

    def test_pricing_md_instructs_explicit_note_for_docs_without_image(self):
        """
        GIVEN the pricing markdown
        WHEN inspected for a missing-image instruction for base documents
        THEN the file MUST mention an explicit instruction for when no image URL
        exists for a document (e.g. DNI, permiso de circulación).

        We accept any phrasing that covers the concept of "no image" + "explain"
        or "standard document" + "no photo needed".
        """
        content = _load()
        # The instruction should contain keywords about missing image for docs
        has_no_image_note = any(
            phrase in content.lower()
            for phrase in [
                "no tiene imagen",
                "sin imagen",
                "no hay imagen",
                "no tiene foto",
                "no dispone de imagen",
                "no requiere foto",
                "documento estándar",
                "documento estandar",
                "no se requiere foto",
                "imagen de ejemplo",
            ]
        )
        assert has_no_image_note, (
            "pre_expediente_pricing.md must contain an instruction telling the LLM "
            "to explicitly mention when a base document (e.g. DNI, permiso) has no "
            "example image, rather than silently skipping it. AC-4.4."
        )


# ---------------------------------------------------------------------------
# CTA deduplication — no literal CTA strings in pricing.md (use {{CTA_N}})
# ---------------------------------------------------------------------------


class TestCtaDeduplicationPricing:
    """Spec REQ-3.1: no literal CTA strings in pricing.md — use {{CTA_N}} placeholders."""

    _LITERAL_CTAS = [
        "¿Quieres que te ayude con alguna homologación?",
        "¿Te interesa alguno? Puedo darte el precio exacto.",
        "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?",
        "¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?",
        "¿Abrimos expediente o tienes alguna duda?",
    ]

    def test_no_literal_cta_in_pricing(self):
        """
        GIVEN pre_expediente_pricing.md
        WHEN searched for any of the 5 canonical CTA literal strings
        THEN NO matches are found — all references use {{CTA_N}} placeholders.
        """
        content = _load()
        found = [cta for cta in self._LITERAL_CTAS if cta in content]
        assert not found, (
            f"Literal CTA strings found in pricing.md — replace with {{{{CTA_N}}}} placeholders: {found}"
        )


# ---------------------------------------------------------------------------
# T15: multi_element gate — must reference PROCEED exception
# ---------------------------------------------------------------------------


class TestMultiElementProceedException:
    """Spec REQ-3.7: <multi_element> must reference PROCEED exception (skip confirmation for PROCEED)."""

    def test_multi_element_has_proceed_exception(self):
        """
        GIVEN pre_expediente_pricing.md <multi_element> section
        WHEN inspected
        THEN it must reference REGLA LÉXICA DURA / PROCEED and state confirmation is skipped/omitted.
        """
        content = _load()

        # Extract <multi_element> section
        me_start = content.find("<multi_element>")
        me_end = content.find("</multi_element>")
        assert me_start != -1 and me_end != -1, (
            "pre_expediente_pricing.md is missing <multi_element> block"
        )
        me_block = content[me_start:me_end].lower()

        has_proceed_ref = "regla léxica dura" in me_block or "proceed" in me_block
        has_skip_ref = "omitir" in me_block or "calcular directamente" in me_block or "omite" in me_block

        assert has_proceed_ref and has_skip_ref, (
            "<multi_element> must reference the PROCEED exception: when the original message "
            "matches REGLA LÉXICA DURA PROCEED, confirmation is skipped and calculation proceeds "
            "directly. Missing either the PROCEED reference or the skip/omit instruction. REQ-3.7."
        )
