"""
Prompt lint tests for the prompt-alignment-pre-expediente change.

These tests verify the final state of all prompt files changed in Batch 1 and
Batch 2 of the change. All tests are pure content assertions — no mocking, no
DB, no Redis. They read prompt files directly from disk via pathlib.Path.

Requirements covered:
- CTA-01, CTA-02, CTA-03, CTA-04
- DEDUP-01, DEDUP-03, DEDUP-05
- PRICE-01, PRICE-02
- HAND-01
- CAT-01, CAT-02
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "agent" / "prompts"
MODES_DIR = PROMPTS_DIR / "modes"
CORE_DIR = PROMPTS_DIR / "core"

# Mode files
DISCOVERY_MD = MODES_DIR / "pre_expediente_discovery.md"
PRICING_MD = MODES_DIR / "pre_expediente_pricing.md"
POST_PRICE_MD = MODES_DIR / "pre_expediente_post_price.md"

# Expediente files
DATOS_PERSONALES_MD = MODES_DIR / "expediente_datos_personales.md"
DATOS_VEHICULO_MD = MODES_DIR / "expediente_datos_vehiculo.md"

# Core files
CORE_04_MD = CORE_DIR / "04_anti_patterns.md"


# ---------------------------------------------------------------------------
# Sanity check — files must exist
# ---------------------------------------------------------------------------


def test_prompt_files_exist():
    """All prompt files referenced by these tests must exist on disk."""
    required = [
        DISCOVERY_MD,
        PRICING_MD,
        POST_PRICE_MD,
        DATOS_PERSONALES_MD,
        DATOS_VEHICULO_MD,
        CORE_04_MD,
    ]
    for path in required:
        assert path.exists(), f"Required prompt file not found: {path}"


# ---------------------------------------------------------------------------
# Class 1: No expediente actions in pre-expediente mode files (CTA-04)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_path,label",
    [
        pytest.param(DISCOVERY_MD, "discovery", id="discovery"),
        pytest.param(PRICING_MD, "pricing", id="pricing"),
        pytest.param(POST_PRICE_MD, "post_price", id="post_price"),
    ],
)
class TestNoExpedienteActionsInPreExpediente:
    """Pre-expediente mode files must not contain expediente-mode actions (CTA-04)."""

    def test_no_tipo_elemento(self, file_path: Path, label: str):
        """enviar_imagenes_ejemplo(tipo="elemento") must NOT appear as an instruction.

        tipo="elemento" is valid in prohibition clauses ("NO uses tipo=\"elemento\""),
        but calling enviar_imagenes_ejemplo with tipo="elemento" is an EXPEDIENTE_MODE
        action that must never appear as an affirmative instruction in pre-expediente files.
        """
        content = file_path.read_text(encoding="utf-8")
        # The forbidden pattern is the tool call with tipo="elemento" as an argument.
        # Prohibition mentions like 'NO uses tipo="elemento"' are expected and correct.
        assert 'enviar_imagenes_ejemplo(tipo="elemento")' not in content, (
            f'{label}.md contains enviar_imagenes_ejemplo(tipo="elemento") as a call instruction. '
            "Pre-expediente images must always use tipo=\"presupuesto\". "
            "This is an EXPEDIENTE_MODE action that should never appear as an instruction here."
        )

    def test_no_fotos_una_por_una(self, file_path: Path, label: str):
        """'fotos una por una' must NOT appear — that phrasing implies element collection.

        Element-by-element photo collection is exclusively EXPEDIENTE_MODE behavior.
        """
        content = file_path.read_text(encoding="utf-8")
        assert "fotos una por una" not in content, (
            f"{label}.md contains the phrase 'fotos una por una' which belongs to "
            "EXPEDIENTE_MODE element collection, not pre-expediente."
        )


# ---------------------------------------------------------------------------
# Class 2: CTA Prescriptivo sections presence
# ---------------------------------------------------------------------------


class TestCTAPrescriptivoPresence:
    """All pre-expediente mode files must have a CTA Prescriptivo section (CTA-01 to CTA-04)."""

    def test_cta_prescriptivo_heading_in_discovery(self):
        """discovery.md must have the '## CTA Prescriptivo' heading."""
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "## CTA Prescriptivo" in content, (
            "discovery.md is missing the '## CTA Prescriptivo' section. "
            "This section was added in T-09 to replace the open-ended 'CTA según contexto'."
        )

    def test_cta_prescriptivo_in_pricing(self):
        """pricing.md must have the 'CTA tras comunicar precio' heading."""
        content = PRICING_MD.read_text(encoding="utf-8")
        assert "CTA tras comunicar precio" in content, (
            "pricing.md is missing the 'CTA tras comunicar precio' section. "
            "This section was added in T-10 to formalize post-price CTA."
        )

    def test_cta_prescriptivo_heading_in_post_price(self):
        """post_price.md must have the '## CTA Prescriptivo' heading."""
        content = POST_PRICE_MD.read_text(encoding="utf-8")
        assert "## CTA Prescriptivo" in content, (
            "post_price.md is missing the '## CTA Prescriptivo' section. "
            "This section was added in T-12 to govern post-price CTAs."
        )

    def test_no_cta_segun_contexto_in_discovery(self):
        """The old '## CTA según contexto' section must NOT exist in discovery.md.

        It was replaced by '## CTA Prescriptivo' in T-09.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "## CTA según contexto" not in content, (
            "discovery.md still contains the old '## CTA según contexto' heading. "
            "This should have been replaced by '## CTA Prescriptivo' in T-09."
        )

    def test_no_adapta_el_cta_in_discovery(self):
        """The old 'Adapta el CTA' instruction must NOT exist in discovery.md.

        It was part of the removed 'CTA según contexto' section.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "Adapta el CTA" not in content, (
            "discovery.md still contains 'Adapta el CTA' from the old free-form CTA section. "
            "This should have been removed in T-09 along with '## CTA según contexto'."
        )

    @pytest.mark.parametrize(
        "file_path,label",
        [
            pytest.param(DISCOVERY_MD, "discovery", id="discovery"),
            pytest.param(POST_PRICE_MD, "post_price", id="post_price"),
        ],
    )
    def test_prohibido_line_in_cta_section(self, file_path: Path, label: str):
        """The '## CTA Prescriptivo' section must include a PROHIBIDO enforcement line."""
        content = file_path.read_text(encoding="utf-8")
        assert "PROHIBIDO" in content, (
            f"{label}.md is missing a PROHIBIDO enforcement line. "
            "CTA sections must explicitly forbid inventing CTAs outside the table."
        )


# ---------------------------------------------------------------------------
# Class 3: Deduplication (DEDUP-01, DEDUP-03, DEDUP-05)
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Duplicate rule content must be removed and canonical sources retained (DEDUP-*)."""

    def test_no_importante_block_in_discovery(self):
        """The 'IMPORTANTE: Usa SIEMPRE' duplicate block must be gone from discovery.md.

        T-01 removed the duplicate IMPORTANTE paragraph that appeared after the
        'Usuario pide ver fotos' flow block. Rule 8 is the canonical source.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "IMPORTANTE: Usa SIEMPRE" not in content, (
            "discovery.md still contains the 'IMPORTANTE: Usa SIEMPRE tipo=\"presupuesto\"' "
            "duplicate block that should have been removed in T-01. Rule 8 is the canonical rule."
        )

    def test_no_verbose_reidentify_text_in_discovery(self):
        """The full verbose no-re-identify text must NOT remain in discovery.md.

        T-02 shortened Rule 2 to a reference: '→ aplica regla anti-re-identificación (core/04)'.
        The old full explanation should be gone.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        verbose_fragment = "una vez hay `element_codes` en el contexto"
        assert verbose_fragment not in content, (
            "discovery.md still contains the verbose no-re-identify explanation. "
            "T-02 should have shortened Rule 2 to a core/04 reference."
        )

    def test_no_verbose_reidentify_text_in_pricing(self):
        """The full verbose no-re-identify text must NOT remain in pricing.md.

        T-03 shortened Rule 3 to a reference: '→ aplica regla anti-re-identificación (core/04)'.
        The old full explanation should be gone.
        """
        content = PRICING_MD.read_text(encoding="utf-8")
        verbose_fragment = "para respuestas de variante usa siempre"
        assert verbose_fragment not in content, (
            "pricing.md still contains the verbose no-re-identify explanation. "
            "T-03 should have shortened Rule 3 to a core/04 reference."
        )

    @pytest.mark.parametrize(
        "file_path,label",
        [
            pytest.param(DISCOVERY_MD, "discovery", id="discovery"),
            pytest.param(PRICING_MD, "pricing", id="pricing"),
        ],
    )
    def test_core04_reference_present(self, file_path: Path, label: str):
        """Both discovery.md and pricing.md must reference core/04 for no-re-identify rule.

        After T-02 and T-03, the verbose text was replaced with 'aplica regla
        anti-re-identificación (core/04)' as the canonical short form.
        """
        content = file_path.read_text(encoding="utf-8")
        assert "core/04" in content, (
            f"{label}.md is missing the 'core/04' reference for the no-re-identify rule. "
            "The shortened Rule 2/3 must reference the canonical core/04 document."
        )

    def test_core04_has_anti_reidentify_canonical_rule(self):
        """core/04_anti_patterns.md must still contain the canonical no-re-identify rule.

        The mode files now reference core/04 — if core/04 loses the rule, the
        system has no no-re-identify guidance at all.
        """
        content = CORE_04_MD.read_text(encoding="utf-8")
        assert "seleccionar_variante_por_respuesta" in content, (
            "core/04_anti_patterns.md is missing the 'seleccionar_variante_por_respuesta' "
            "canonical anti-re-identify rule. Discovery and pricing reference this file — "
            "it must contain the full rule."
        )


# ---------------------------------------------------------------------------
# Class 4: Category inference (CAT-01, CAT-02)
# ---------------------------------------------------------------------------


class TestCategoryInference:
    """discovery.md must contain the brand/model inference section (CAT-01, CAT-02)."""

    def test_inference_section_present(self):
        """'## Inferencia por marca/modelo' section must exist in discovery.md."""
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "## Inferencia por marca/modelo" in content, (
            "discovery.md is missing the '## Inferencia por marca/modelo' section. "
            "This was added in T-11 to implement CAT-01."
        )

    def test_ducato_in_inference_section(self):
        """'Ducato' must appear in the inference section in discovery.md."""
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "Ducato" in content, (
            "discovery.md does not mention 'Ducato' in the inference section. "
            "Fiat Ducato must be listed as a van base requiring user confirmation (CAT-02)."
        )

    def test_sprinter_in_inference_section(self):
        """'Sprinter' must appear in the inference section in discovery.md."""
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "Sprinter" in content, (
            "discovery.md does not mention 'Sprinter' in the inference section. "
            "Mercedes Sprinter must be listed as a van base requiring user confirmation (CAT-02)."
        )

    def test_ducato_sprinter_require_confirmation(self):
        """Ducato/Sprinter/Crafter must be marked as always requiring confirmation (CAT-02).

        These vans can be either motorhomes (aseicars) or camper vans (camper),
        so the agent must ALWAYS ask the user which type it is.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        # Check the mandatory confirmation rule appears near the Ducato/Sprinter mention
        # The spec mandates: "Ducato/Sprinter/Crafter SIEMPRE requieren confirmación"
        assert "SIEMPRE requieren confirmación" in content, (
            "discovery.md is missing 'SIEMPRE requieren confirmación' for Ducato/Sprinter/Crafter. "
            "CAT-02 requires these vans to always prompt the user for vehicle type clarification."
        )


# ---------------------------------------------------------------------------
# Class 5: Hardcoded prices removed (PRICE-01, PRICE-02)
# ---------------------------------------------------------------------------


class TestHardcodedPrices:
    """Hardcoded '85€' must be replaced with {cert_supplement_eur} placeholder (PRICE-01, PRICE-02)."""

    def test_no_hardcoded_price_in_datos_personales(self):
        """expediente_datos_personales.md must NOT contain the hardcoded '85€' price."""
        content = DATOS_PERSONALES_MD.read_text(encoding="utf-8")
        assert "85€" not in content, (
            "expediente_datos_personales.md still contains the hardcoded '85€' price. "
            "T-05 should have replaced it with '{cert_supplement_eur}€'."
        )

    def test_cert_supplement_placeholder_in_datos_personales(self):
        """expediente_datos_personales.md must contain '{cert_supplement_eur}' placeholder."""
        content = DATOS_PERSONALES_MD.read_text(encoding="utf-8")
        assert "{cert_supplement_eur}" in content, (
            "expediente_datos_personales.md is missing the '{cert_supplement_eur}' placeholder. "
            "T-05 should have replaced the hardcoded '85€' with this loader-substituted placeholder."
        )

    def test_no_hardcoded_price_in_datos_vehiculo(self):
        """expediente_datos_vehiculo.md must NOT contain the hardcoded '85€' price."""
        content = DATOS_VEHICULO_MD.read_text(encoding="utf-8")
        assert "85€" not in content, (
            "expediente_datos_vehiculo.md still contains the hardcoded '85€' price. "
            "T-06 should have replaced it with '{cert_supplement_eur}€'."
        )

    def test_cert_supplement_placeholder_in_datos_vehiculo(self):
        """expediente_datos_vehiculo.md must contain '{cert_supplement_eur}' placeholder."""
        content = DATOS_VEHICULO_MD.read_text(encoding="utf-8")
        assert "{cert_supplement_eur}" in content, (
            "expediente_datos_vehiculo.md is missing the '{cert_supplement_eur}' placeholder. "
            "T-06 should have replaced the hardcoded '85€' with this loader-substituted placeholder."
        )


# ---------------------------------------------------------------------------
# Class 6: Handoff coherence (HAND-01)
# ---------------------------------------------------------------------------


class TestHandoffCoherence:
    """post_price.md must contain correct handoff guidance to EXPEDIENTE_MODE (HAND-01)."""

    def test_auto_transition_clarification_in_post_price(self):
        """post_price.md must state that the system transitions automatically to EXPEDIENTE_MODE.

        T-12 added explicit clarification to prevent the agent from anticipating
        expediente questions before the mode actually transitions.
        """
        content = POST_PRICE_MD.read_text(encoding="utf-8")
        assert "transiciona automáticamente a EXPEDIENTE_MODE" in content, (
            "post_price.md is missing the 'transiciona automáticamente a EXPEDIENTE_MODE' "
            "clarification in Rama B — Expediente. T-12 should have added this to prevent "
            "the agent from anticipating expediente data collection prematurely."
        )

    def test_no_anticipate_expediente_questions(self):
        """post_price.md must explicitly tell the agent NOT to anticipate expediente questions.

        After confirmar_presupuesto(), the agent should not start asking for DNI,
        email, etc. — EXPEDIENTE_MODE's own prompt handles the kickoff.
        """
        content = POST_PRICE_MD.read_text(encoding="utf-8")
        assert "NO anticipes preguntas del expediente" in content, (
            "post_price.md is missing the 'NO anticipes preguntas del expediente' rule. "
            "T-12 added this to prevent the agent from leaking EXPEDIENTE_MODE data "
            "collection into the post_price phase."
        )
