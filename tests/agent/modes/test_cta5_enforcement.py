"""
Unit tests for CTA 5 post-images enforcement — escenario 7.bis / regla 9.

Spec reference: docs/system/01-agente/flujo-pre-expediente.md
  - Escenario 7.bis: Enforcement determinístico de CTA 5 post-imágenes
  - Regla 9: CTA 5 es determinística post-imágenes (anexar, no sustituir)

Contract (pure function _enforce_cta5_if_needed):
  - Preconditions met (precio_comunicado=True AND imagenes_enviadas_codigos non-empty):
    - Case 1: LLM produced useful text WITHOUT CTA 5 → append CTA 5 at the end
    - Case 2: LLM produced text WITH CTA 5 already → no duplication
    - Case 3: ai_response is empty or whitespace only → emit CTA 5 as sole content
  - Preconditions NOT met (no price or no images) → passthrough unchanged

All tests are pure unit tests — no DB, no Redis, no LLM.
"""

import pytest

from agent.modes.pre_expediente_mode import _enforce_cta5_if_needed

# The canonical CTA 5 text (must match exactly what's defined in pre_expediente_mode.py)
CTA_5 = "¿Empezamos con el expediente?"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preconditions_met(precio_comunicado: bool = True, codigos: list | None = None) -> tuple:
    """Return (precio_comunicado, imagenes_enviadas_codigos) for the test cases."""
    if codigos is None:
        codigos = ["ESCAPE"]
    return precio_comunicado, codigos


# ---------------------------------------------------------------------------
# Case 1: Preconditions met + text without CTA 5 → append CTA 5
# ---------------------------------------------------------------------------


class TestAppendsWhenMissingCta5:
    """Preconditions met, LLM text has no CTA 5 → CTA 5 appended at end."""

    def test_appends_cta5_to_llm_text(self):
        """Basic case: LLM produced useful text without CTA 5."""
        llm_text = "El presupuesto para el escape es de 410€ +IVA."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.rstrip().endswith(CTA_5)
        # LLM text must be preserved
        assert llm_text.strip() in result

    def test_preserves_llm_text_content(self):
        """The LLM text (price, warnings, context) is preserved before the appended CTA 5."""
        llm_text = "El presupuesto es de 520€ +IVA. Recuerda que necesitarás los documentos del taller."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        # Both original content and CTA 5 must be present
        assert "520€ +IVA" in result
        assert "documentos del taller" in result
        assert result.rstrip().endswith(CTA_5)

    def test_appends_with_separator(self):
        """
        Appended CTA 5 is separated from LLM text.
        Result should NOT be: "...text.¿Empezamos con el expediente?" (no space).
        """
        llm_text = "Aquí tienes los ejemplos de fotos."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        # CTA 5 must appear at the end, separated from the rest
        assert result.rstrip().endswith(CTA_5)
        # The original text must come BEFORE the CTA 5
        cta5_idx = result.rindex(CTA_5)
        assert llm_text.strip() in result[:cta5_idx]

    def test_multiple_image_codes_still_enforces(self):
        """Having multiple imagenes_enviadas_codigos still triggers enforcement."""
        llm_text = "Ya te envié las fotos de ejemplo."
        precio, codigos = _preconditions_met(codigos=["ESCAPE", "SUSPENSION"])
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.rstrip().endswith(CTA_5)

    def test_cta5_appears_only_once_when_appended(self):
        """CTA 5 appears exactly once in result when appended (no duplication)."""
        llm_text = "Te he enviado los ejemplos."
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1


# ---------------------------------------------------------------------------
# Case 2: Preconditions met + LLM text already contains CTA 5 → no duplication
# ---------------------------------------------------------------------------


class TestNoDuplicationWhenCta5Present:
    """Preconditions met, LLM already included CTA 5 → passthrough (no duplicate)."""

    def test_no_duplication_exact_cta5_at_end(self):
        """LLM text ends exactly with CTA 5 → no duplicate."""
        llm_text = f"Aquí tienes las fotos de ejemplo. {CTA_5}"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1
        assert result.rstrip().endswith(CTA_5)

    def test_no_duplication_cta5_with_trailing_whitespace(self):
        """LLM text ends with CTA 5 + trailing whitespace → no duplicate."""
        llm_text = f"Ya puedes ver las fotos. {CTA_5}  "
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1

    def test_no_duplication_cta5_with_trailing_newline(self):
        """LLM text ends with CTA 5 + newline → no duplicate."""
        llm_text = f"Perfecto, ya ves cómo son las fotos.\n{CTA_5}\n"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert result.count(CTA_5) == 1

    def test_preserves_text_when_cta5_already_present(self):
        """When CTA 5 is already present, the full original text is preserved."""
        llm_text = f"El presupuesto fue de 410€. {CTA_5}"
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed(llm_text, precio, codigos)

        assert "410€" in result
        assert result.count(CTA_5) == 1


# ---------------------------------------------------------------------------
# Case 3: Preconditions met + empty/whitespace ai_response → CTA 5 as sole content
# ---------------------------------------------------------------------------


class TestEmptyResponseBecomescta5:
    """Preconditions met, ai_response is empty or whitespace → CTA 5 as sole output."""

    def test_empty_string_becomes_cta5(self):
        """Empty string ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("", precio, codigos)

        assert result == CTA_5

    def test_whitespace_only_becomes_cta5(self):
        """Whitespace-only ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("   \n\t  ", precio, codigos)

        assert result == CTA_5

    def test_newline_only_becomes_cta5(self):
        """Newline-only ai_response → CTA 5 as sole content."""
        precio, codigos = _preconditions_met()
        result = _enforce_cta5_if_needed("\n\n\n", precio, codigos)

        assert result == CTA_5


# ---------------------------------------------------------------------------
# Case 4: Preconditions NOT met → passthrough unchanged
# ---------------------------------------------------------------------------


class TestPassthroughWhenPreconditionsNotMet:
    """When preconditions are not met, ai_response is returned unchanged."""

    def test_no_price_communicated_passthrough(self):
        """precio_comunicado=False → no CTA 5 enforcement."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert result == llm_text

    def test_empty_imagenes_passthrough(self):
        """imagenes_enviadas_codigos=[] → no CTA 5 enforcement."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert result == llm_text

    def test_none_imagenes_passthrough(self):
        """imagenes_enviadas_codigos=None → no CTA 5 enforcement."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=True, imagenes_enviadas_codigos=None)

        assert result == llm_text

    def test_no_price_no_images_passthrough(self):
        """Both preconditions False → passthrough."""
        llm_text = "Aquí tienes algo."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=None)

        assert result == llm_text

    def test_passthrough_preserves_text_exactly(self):
        """Passthrough returns the exact same string object or identical content."""
        llm_text = "Texto cualquiera sin modificar."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert result == llm_text

    def test_passthrough_does_not_add_cta5(self):
        """No preconditions → CTA 5 never injected."""
        llm_text = "Texto sin CTA 5."
        result = _enforce_cta5_if_needed(llm_text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert CTA_5 not in result
