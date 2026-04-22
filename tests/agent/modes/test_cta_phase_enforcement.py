"""
Unit tests for context-aware CTA enforcer (_enforce_phase_cta) and CTA guard policy.

Spec reference: fix-cta-phase-awareness-and-prompt-coverage
  - F1: _enforce_phase_cta branches CTA 4 vs CTA 5 based on imagenes_enviadas_codigos
  - F2: guard_cta_policy POST_PRICE allows CTA 4 (no false-positive strip)
  - F6: _detect_cta_emitted telemetry helper
  - F7: _WRONG_CTA_PATTERNS narrowed — CTA 2 canonical not stripped

All tests are pure unit tests — no DB, no Redis, no LLM.
"""

from __future__ import annotations

import pytest

from agent.prompts.ctas_catalog import get_cta

# ---------------------------------------------------------------------------
# Shared canonical values (sourced from catalog — single source of truth)
# ---------------------------------------------------------------------------

CTA_2 = get_cta(2)  # "¿Te interesa alguno? Puedo darte el precio exacto."
CTA_4 = get_cta(4)  # "¿Te enseño ejemplos de fotos o abrimos el expediente?"
CTA_5 = get_cta(5)  # "¿Abrimos expediente o tienes alguna duda?"


# ===========================================================================
# Phase 1 RED — F1: _enforce_phase_cta
# ===========================================================================


class TestEnforcePhaseCtaCta4Branch:
    """F1-a: price communicated, no images sent → CTA 4 appended, CTA 5 absent."""

    def test_cta4_appended_when_no_images(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "El presupuesto para el escape es de 410€ +IVA."
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert result.rstrip().endswith(CTA_4), f"Expected ending with CTA 4, got: {result!r}"
        assert CTA_5 not in result, "CTA 5 must NOT appear when images not sent"

    def test_original_text_preserved_with_cta4(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "El presupuesto es de 520€ +IVA."
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert "520€ +IVA" in result
        assert result.rstrip().endswith(CTA_4)


class TestEnforcePhaseCtaCta5Branch:
    """F1-b: price communicated AND images already sent → CTA 5 appended, CTA 4 absent."""

    def test_cta5_appended_when_images_sent(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "Ya te envié las fotos de ejemplo."
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=["ESCAPE"])

        assert result.rstrip().endswith(CTA_5), f"Expected ending with CTA 5, got: {result!r}"
        assert CTA_4 not in result, "CTA 4 must NOT appear when images already sent"

    def test_cta5_with_multiple_image_codes(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "Aquí tienes los ejemplos."
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=["ESCAPE", "SUSPENSION"])

        assert result.rstrip().endswith(CTA_5)


class TestEnforcePhaseCtaNoop:
    """F1-c: price NOT communicated → response unchanged."""

    def test_noop_when_price_not_communicated(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "Aquí tienes información sobre homologaciones."
        result = _enforce_phase_cta(text, precio_comunicado=False, imagenes_enviadas_codigos=[])

        assert result == text

    def test_noop_with_images_but_no_price(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = "Esto es una respuesta."
        result = _enforce_phase_cta(text, precio_comunicado=False, imagenes_enviadas_codigos=["ESCAPE"])

        assert result == text


class TestEnforcePhaseCtaPassthroughCta4:
    """F1-d: response already ends with CTA 4 canonical → no duplicate."""

    def test_no_duplicate_when_cta4_already_present(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = f"El presupuesto es de 410€. {CTA_4}"
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert result.count(CTA_4) == 1


class TestEnforcePhaseCtaReplacesCta5WhenNoImages:
    """F1-e: response ends with CTA 5 but images not sent → CTA 5 removed, CTA 4 appended."""

    def test_cta5_replaced_by_cta4_when_no_images(self):
        from agent.modes.pre_expediente_mode import _enforce_phase_cta

        text = f"El presupuesto es de 410€. {CTA_5}"
        result = _enforce_phase_cta(text, precio_comunicado=True, imagenes_enviadas_codigos=[])

        assert CTA_5 not in result, "CTA 5 must be removed when images not sent"
        assert result.rstrip().endswith(CTA_4), "CTA 4 must be appended instead"


# ===========================================================================
# Phase 1 RED — F2: guard_cta_policy POST_PRICE allows CTA 4
# ===========================================================================


class TestGuardPostPriceAllowsCta4:
    """F2-a: POST_PRICE + no images → CTA 4 preserved by guard (not stripped)."""

    def test_cta4_preserved_in_post_price_no_images(self):
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = f"El presupuesto es de 410€ +IVA. {CTA_4}"
        result = guard_cta_policy(
            text=text,
            mc={"imagenes_enviadas_codigos": []},
            phase="PRE_EXPEDIENTE_POST_PRICE",
        )

        assert CTA_4 in result, f"CTA 4 must be preserved in POST_PRICE, got: {result!r}"

    def test_cta4_standalone_preserved_in_post_price(self):
        from agent.modes.pre_expediente_mode import guard_cta_policy

        result = guard_cta_policy(
            text=CTA_4,
            mc={"imagenes_enviadas_codigos": []},
            phase="PRE_EXPEDIENTE_POST_PRICE",
        )

        assert CTA_4 in result


class TestGuardPostPriceStripsWrongPattern:
    """F2-b: POST_PRICE → wrong patterns still stripped (not CTA 4/5)."""

    def test_wrong_cta_stripped_in_post_price(self):
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = "El presupuesto ya lo tienes. ¿Tienes alguna pregunta al respecto?"
        result = guard_cta_policy(
            text=text,
            mc={},
            phase="PRE_EXPEDIENTE_POST_PRICE",
        )

        assert "¿Tienes alguna pregunta" not in result


# ===========================================================================
# Phase 1 RED — F7: CTA 2 canonical NOT stripped in DISCOVERY
# ===========================================================================


class TestGuardDiscoveryCta2NotStripped:
    """F7-a: DISCOVERY phase — CTA 2 canonical must pass guard unchanged."""

    def test_cta2_canonical_not_stripped_in_discovery(self):
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = f"El escape deportivo está disponible. {CTA_2}"
        result = guard_cta_policy(
            text=text,
            mc={},
            phase="PRE_EXPEDIENTE_DISCOVERY",
        )

        assert CTA_2 in result, f"CTA 2 canonical must NOT be stripped, got: {result!r}"


class TestGuardDiscoveryCta2DriftStripped:
    """F7-b: DISCOVERY phase — drift variant of CTA 2 IS stripped."""

    def test_cta2_drift_stripped_in_discovery(self):
        from agent.modes.pre_expediente_mode import guard_cta_policy

        text = "El escape deportivo está disponible. ¿te interesa alguno de esos modelos?"
        result = guard_cta_policy(
            text=text,
            mc={},
            phase="PRE_EXPEDIENTE_DISCOVERY",
        )

        # The drift variant should be stripped
        assert "¿te interesa alguno de esos modelos?" not in result.lower()


# ===========================================================================
# Phase 2 RED — F6: _detect_cta_emitted telemetry helper
# ===========================================================================


class TestDetectCtaEmitted:
    """F6: _detect_cta_emitted returns correct label for each CTA."""

    def test_detects_cta4_canonical(self):
        from agent.modes.pre_expediente_mode import _detect_cta_emitted

        text = f"El presupuesto es de 410€. {CTA_4}"
        result = _detect_cta_emitted(text)

        assert result == "cta_4"

    def test_detects_cta5_canonical(self):
        from agent.modes.pre_expediente_mode import _detect_cta_emitted

        text = f"Ya tienes las fotos. {CTA_5}"
        result = _detect_cta_emitted(text)

        assert result == "cta_5"

    def test_returns_none_when_no_cta(self):
        from agent.modes.pre_expediente_mode import _detect_cta_emitted

        text = "El presupuesto es de 410€ +IVA."
        result = _detect_cta_emitted(text)

        assert result == "none"

    def test_detects_cta2_canonical(self):
        from agent.modes.pre_expediente_mode import _detect_cta_emitted

        text = f"Tenemos varias opciones. {CTA_2}"
        result = _detect_cta_emitted(text)

        assert result == "cta_2"
