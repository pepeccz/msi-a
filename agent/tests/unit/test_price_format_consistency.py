"""
Unit tests for price format and validity phrase consistency across
all 3 PRE_EXPEDIENTE prompt files.

Covers:
- Spec REQ-3.4: "IVA incluido" absent from discovery.md
- Spec REQ-3.5: canonical validity phrase "_Precios válidos por 30 días._" in all 3 files
- Spec REQ-3.6: invented CTA "¿Quieres que empecemos con el expediente?" absent
"""
from __future__ import annotations

from pathlib import Path

_DISCOVERY_MD = (
    Path(__file__).parents[3] / "agent" / "prompts" / "modes" / "pre_expediente_discovery.md"
)
_PRICING_MD = (
    Path(__file__).parents[3] / "agent" / "prompts" / "modes" / "pre_expediente_pricing.md"
)
_POST_PRICE_MD = (
    Path(__file__).parents[3] / "agent" / "prompts" / "modes" / "pre_expediente_post_price.md"
)

_CANONICAL_VALIDITY = "_Precios válidos por 30 días._"
_NON_ITALIC_VALIDITY = "Precios válidos por 30 días."


class TestIVAIncluido:
    """Spec REQ-3.4: 'IVA incluido' must NOT appear in discovery.md."""

    def test_no_iva_incluido_in_discovery(self):
        """
        GIVEN pre_expediente_discovery.md
        WHEN searched for "IVA incluido"
        THEN NO matches are found — canonical format is '*{precio}€ +IVA*'.
        """
        content = _DISCOVERY_MD.read_text(encoding="utf-8")
        assert "IVA incluido" not in content, (
            "pre_expediente_discovery.md must NOT contain 'IVA incluido'. "
            "Use the canonical format '*{precio}€ +IVA*' instead. "
            "See spec REQ-3.4 and pricing.md:42."
        )


class TestValidityPhraseCanonical:
    """Spec REQ-3.5: all 3 prompt files must use '_Precios válidos por 30 días._' (full italic)."""

    def test_pricing_has_canonical_validity_phrase(self):
        """pricing.md must contain the full italic canonical validity phrase."""
        content = _PRICING_MD.read_text(encoding="utf-8")
        assert _CANONICAL_VALIDITY in content, (
            f"pre_expediente_pricing.md must contain '{_CANONICAL_VALIDITY}' "
            "(full italic markdown). See spec REQ-3.5."
        )

    def test_post_price_has_canonical_validity_phrase(self):
        """post_price.md must contain the full italic canonical validity phrase."""
        content = _POST_PRICE_MD.read_text(encoding="utf-8")
        assert _CANONICAL_VALIDITY in content, (
            f"pre_expediente_post_price.md must contain '{_CANONICAL_VALIDITY}' "
            "(full italic markdown). See spec REQ-3.5."
        )

    def test_pricing_has_no_non_italic_validity_phrase(self):
        """pricing.md must NOT contain the non-italic form 'Precios válidos por 30 días.'."""
        content = _PRICING_MD.read_text(encoding="utf-8")
        # Non-italic form: the phrase without surrounding underscores
        # We check the phrase is not followed by a period that isn't preceded by underscore
        # Simple approach: strip italic form, check non-italic standalone not present
        content_stripped = content.replace(_CANONICAL_VALIDITY, "")
        assert _NON_ITALIC_VALIDITY not in content_stripped, (
            f"pre_expediente_pricing.md contains non-italic '{_NON_ITALIC_VALIDITY}'. "
            "Use the italic form '_Precios válidos por 30 días._' everywhere. REQ-3.5."
        )

    def test_post_price_has_no_non_italic_validity_phrase(self):
        """post_price.md must NOT contain the non-italic form."""
        content = _POST_PRICE_MD.read_text(encoding="utf-8")
        content_stripped = content.replace(_CANONICAL_VALIDITY, "")
        assert _NON_ITALIC_VALIDITY not in content_stripped, (
            f"pre_expediente_post_price.md contains non-italic '{_NON_ITALIC_VALIDITY}'. "
            "Use the italic form '_Precios válidos por 30 días._' everywhere. REQ-3.5."
        )


class TestInventedCTAAbsent:
    """Spec REQ-3.6: invented CTA must not appear in any prompt file."""

    _INVENTED_CTA = "¿Quieres que empecemos con el expediente?"

    def test_invented_cta_absent_from_pricing(self):
        """
        GIVEN pre_expediente_pricing.md
        WHEN searched for the invented CTA
        THEN NO matches are found.
        """
        content = _PRICING_MD.read_text(encoding="utf-8")
        assert self._INVENTED_CTA not in content, (
            f"pre_expediente_pricing.md still contains invented CTA: {self._INVENTED_CTA!r}. "
            "Replace with {{{{CTA_5}}}} placeholder. REQ-3.6."
        )

    def test_invented_cta_absent_from_all_prompts(self):
        """None of the 3 prompt files may contain the invented CTA."""
        for path in [_DISCOVERY_MD, _PRICING_MD, _POST_PRICE_MD]:
            content = path.read_text(encoding="utf-8")
            assert self._INVENTED_CTA not in content, (
                f"{path.name} contains invented CTA: {self._INVENTED_CTA!r}. "
                "Replace with {{{{CTA_5}}}} placeholder. REQ-3.6."
            )
