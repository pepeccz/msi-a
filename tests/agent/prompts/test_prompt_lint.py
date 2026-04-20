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
CORE_MD = PROMPTS_DIR / "core.md"


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
        CORE_MD,
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


# ---------------------------------------------------------------------------
# Class 7: core.md identity neutralization (AP-4 prompt side)
# ---------------------------------------------------------------------------


class TestCoreMdIdentityNeutralization:
    """core.md must NOT contain the identity phrase that would cause duplication.

    The identity phrase 'Eres el asistente con IA de MSI Automotive' was moved
    exclusively to the runtime guard in main.py (injected on first turn only).
    core.md line 2 must use neutral agent role language instead.
    """

    def test_core_md_no_redundant_identity(self):
        """core.md line 2 must NOT contain 'Eres el asistente con IA de MSI Automotive'.

        This phrase is injected by the main.py guard on first interaction only.
        Having it in core.md causes duplication every turn — AP-4.
        """
        content = CORE_MD.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Check specifically lines 1-5 (0-indexed: 0-4) to catch line 2
        early_content = "\n".join(lines[:5])
        assert "Eres el asistente con IA de MSI Automotive" not in early_content, (
            "core.md lines 1-5 still contain 'Eres el asistente con IA de MSI Automotive'. "
            "This phrase must be replaced with neutral agent role language (AP-4). "
            "Identity injection happens only in main.py on first turn."
        )

    def test_core_md_contains_msi_automotive_context(self):
        """core.md must still establish MSI Automotive context with homologaciones and vehículos."""
        content = CORE_MD.read_text(encoding="utf-8")
        lines = content.splitlines()
        early_content = "\n".join(lines[:5])
        assert "MSI Automotive" in early_content, (
            "core.md must still reference 'MSI Automotive' in the opening lines."
        )
        assert "homologaciones" in early_content or "homologación" in early_content, (
            "core.md must reference 'homologaciones' in the opening lines to establish context."
        )
        assert "vehículos" in early_content or "vehículo" in early_content, (
            "core.md must reference 'vehículos' in the opening lines to establish context."
        )


# ---------------------------------------------------------------------------
# Class 8: discovery.md CTA discipline (AP-1, AP-2, AP-3, AP-6, AP-7, AP-8, AP-9)
# ---------------------------------------------------------------------------


class TestDiscoveryCTADiscipline:
    """discovery.md must enforce strict CTA discipline — no escape hatches, no improvisation.

    AP-1: Escape hatch removal — "si ninguna aplica" phrase must be gone.
    AP-6, AP-9: Inline example CTAs must match canonical wording exactly.
    AP-7: intent_routing rows must NOT contain inline CTA strings.
    AP-8: documentacion field must be bound to template via directive.
    AP-2, AP-3: Single canonical source of truth for CTA State-3.
    """

    CANONICAL_STATE3_CTA = (
        "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?"
    )

    def _get_block(self, content: str, open_tag: str, close_tag: str) -> str:
        """Extract text between XML-like tags. Returns empty string if not found."""
        start = content.find(open_tag)
        end = content.find(close_tag)
        if start == -1 or end == -1:
            return ""
        return content[start + len(open_tag) : end]

    def test_no_escape_hatch_substring(self):
        """discovery.md must NOT contain the escape-hatch phrase 'ninguna aplica'.

        AP-1: The old 'Si ninguna aplica, simplemente cierra con algo natural'
        is an escape hatch that lets the LLM improvise a non-canonical CTA.
        It must be replaced with a strict prohibition.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "ninguna aplica" not in content, (
            "discovery.md still contains the escape-hatch phrase 'ninguna aplica'. "
            "AP-1 requires removing this and replacing with 'PROHIBIDO inventar preguntas'."
        )

    def test_prohibido_enforcement_present(self):
        """The <natural_ctas> block must contain both 'PROHIBIDO' and 'EXACTAMENTE'.

        AP-2, AP-3: The enforcement language must be strengthened beyond the
        old 'Usa SOLO estas' to explicit prohibition with verbatim copy instruction.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        natural_ctas_block = self._get_block(content, "<natural_ctas>", "</natural_ctas>")
        assert natural_ctas_block, (
            "discovery.md is missing the <natural_ctas> block entirely."
        )
        assert "PROHIBIDO" in natural_ctas_block, (
            "discovery.md <natural_ctas> block must contain 'PROHIBIDO' enforcement language. "
            "AP-2 requires explicit prohibition of improvised CTAs."
        )
        assert "EXACTAMENTE" in natural_ctas_block, (
            "discovery.md <natural_ctas> block must contain 'EXACTAMENTE' (verbatim copy instruction). "
            "AP-3 requires the LLM to copy CTAs exactly as written."
        )

    def test_intent_routing_no_cta_strings(self):
        """<intent_routing> rows must NOT contain inline CTA strings.

        AP-7: Inline CTAs in the routing table are a second source of truth that
        can drift from <natural_ctas>. The table rows must reference the CTA state
        by description only (e.g. 'CTA estado-3'), not contain the verbatim CTA.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = self._get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, (
            "discovery.md is missing the <intent_routing> block."
        )
        forbidden_substrings = [
            "¿Te muestro",
            "¿Te enseño",
            "¿Fotos de ejemplo",
            "fotos o te calculo",
        ]
        for phrase in forbidden_substrings:
            assert phrase not in routing_block, (
                f"discovery.md <intent_routing> block contains inline CTA phrase: '{phrase}'. "
                "AP-7 requires removing inline CTAs from routing rows — reference canonical list instead."
            )

    def test_single_source_cta_count(self):
        """CTA State-3 must appear exactly once in discovery.md (literal or {{CTA_3}} placeholder).

        AP-2: Single source of truth for canonical State-3 CTA.
        If it appears more than once, there is a duplicate source that can drift.
        Since centralize-pre-expediente-prompts, the file uses {{CTA_3}} instead of the literal.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        # Accept either the literal form or the canonical {{CTA_3}} placeholder
        literal_count = content.count("¿Te muestro ejemplos")
        placeholder_count = content.count("{{CTA_3}}")
        total_count = literal_count + placeholder_count
        assert total_count == 1, (
            f"CTA State-3 (literal or {{{{CTA_3}}}}) appears {total_count} times in discovery.md. "
            "AP-2 requires exactly 1 occurrence (single canonical source in <natural_ctas>). "
            "Remove duplicate occurrences from intent_routing and prose examples."
        )

    def test_documentation_boundary_directive(self):
        """<how_to_present_documentation> must contain a CTA-closing boundary directive.

        AP-8: After presenting documentation, the agent must close with the canonical
        CTA. A directive must be present to enforce this — 'CIERRA OBLIGATORIAMENTE'
        or equivalent strong closing instruction.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        doc_block = self._get_block(
            content, "<how_to_present_documentation>", "</how_to_present_documentation>"
        )
        assert doc_block, (
            "discovery.md is missing the <how_to_present_documentation> block."
        )
        assert "CIERRA OBLIGATORIAMENTE" in doc_block, (
            "discovery.md <how_to_present_documentation> block is missing "
            "'CIERRA OBLIGATORIAMENTE' boundary directive. "
            "AP-8 requires an explicit instruction to close with the canonical CTA "
            "after presenting documentation."
        )

    def test_tool_documentacion_directive_present(self):
        """discovery.md must contain a directive binding the documentacion field to the template.

        AP-8 (Decision 3): The directive must explicitly state that the documentacion
        field from identificar_y_resolver_elementos is rendered ONLY with this template.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        assert "documentacion" in content, (
            "discovery.md must reference the 'documentacion' field from the tool result."
        )
        assert "PROHIBIDO resumir" in content or "PROHIBIDO expandir" in content or (
            "PROHIBIDO resumir" in content
        ), (
            "discovery.md must contain a directive 'PROHIBIDO resumir' to bind the documentacion "
            "field to the template. AP-8 Decision 3 requires prompt-level enforcement."
        )

    def test_inline_example_ctas_match_canonical(self):
        """The <how_to_present_documentation> examples must reference canonical State-3 CTA.

        AP-6, AP-9: Examples must NOT use improvised CTA paraphrases like
        '¿Quieres que te muestre fotos?' or '¿Fotos de ejemplo o presupuesto?'.
        Instead they must reference 'CTA estado-3 de <natural_ctas>' or equivalent,
        pointing to the single canonical source (the <natural_ctas> list).

        The verbatim CTA text lives ONLY in <natural_ctas> (single-source rule).
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        doc_block = self._get_block(
            content, "<how_to_present_documentation>", "</how_to_present_documentation>"
        )
        assert doc_block, (
            "discovery.md is missing <how_to_present_documentation> block."
        )
        # AP-6/AP-9: examples must reference the canonical CTA source, not improvise
        forbidden_paraphrases = [
            "¿Quieres que te muestre",
            "¿Fotos de ejemplo o presupuesto?",
            "¿Quieres ver fotos",
        ]
        for phrase in forbidden_paraphrases:
            assert phrase not in doc_block, (
                f"discovery.md <how_to_present_documentation> contains improvised CTA paraphrase: "
                f"'{phrase}'. AP-6/AP-9 require examples to reference 'CTA estado-3 de <natural_ctas>'."
            )
        # The examples must reference natural_ctas as the canonical source
        assert "natural_ctas" in doc_block or "estado-3" in doc_block, (
            "discovery.md <how_to_present_documentation> must reference 'natural_ctas' or 'estado-3' "
            "to point examples at the canonical CTA source. AP-6/AP-9."
        )


# ---------------------------------------------------------------------------
# 30-day price validity directive (spec: docs/system/04-reglas-negocio/precio-y-tarifas.md rule 11)
# ---------------------------------------------------------------------------


VALIDITY_PHRASE = "_Precios válidos por 30 días._"


class TestPriceValidity30Days:
    """Rule 11 of precio-y-tarifas spec: every price communication MUST include
    the 30-day validity disclaimer.

    Applies to both PRICING phase (first communication) and POST_PRICE phase
    (recalculations after add/remove elements). Enforced via prompt directive,
    not code-level validation.
    """

    def test_pricing_prompt_contains_validity_phrase(self):
        """pre_expediente_pricing.md must include the 30-day validity directive."""
        content = PRICING_MD.read_text(encoding="utf-8")
        assert VALIDITY_PHRASE in content, (
            f"pre_expediente_pricing.md must contain the literal phrase "
            f"'{VALIDITY_PHRASE}' so the LLM communicates price validity. "
            f"See spec rule 11 in docs/system/04-reglas-negocio/precio-y-tarifas.md."
        )

    def test_post_price_prompt_contains_validity_phrase(self):
        """pre_expediente_post_price.md must include the 30-day validity directive
        for recalculation scenarios (add/remove elements)."""
        content = POST_PRICE_MD.read_text(encoding="utf-8")
        assert VALIDITY_PHRASE in content, (
            f"pre_expediente_post_price.md must contain the literal phrase "
            f"'{VALIDITY_PHRASE}' so the LLM communicates price validity when "
            f"recomputing after add/remove. See spec rule 11 in "
            f"docs/system/04-reglas-negocio/precio-y-tarifas.md."
        )

    def test_validity_directive_is_mandatory_in_pricing_rules(self):
        """The validity instruction must appear in the <rules> section of pricing.md
        with an imperative marker (SIEMPRE) so the LLM treats it as non-negotiable."""
        content = PRICING_MD.read_text(encoding="utf-8")
        rules_match = re.search(
            r"<rules>(.*?)</rules>", content, re.DOTALL
        )
        assert rules_match, "pricing.md is missing <rules> block."
        rules_block = rules_match.group(1)
        assert VALIDITY_PHRASE in rules_block, (
            f"Validity directive must live inside <rules> block of pricing.md, "
            f"not elsewhere. See spec rule 11."
        )
        assert "SIEMPRE" in rules_block or "siempre" in rules_block, (
            "Validity directive must be marked as mandatory (SIEMPRE) within "
            "the <rules> block of pricing.md."
        )


# ---------------------------------------------------------------------------
# Class 9: Loader first-interaction directive (AP-5 prompt side)
# ---------------------------------------------------------------------------

LOADER_PY = Path(__file__).resolve().parent.parent.parent.parent / "agent" / "prompts" / "loader.py"

# Legal identity phrase that must always be present
LEGAL_IDENTITY_PHRASE = "asistente con IA de MSI Automotive"

# The greeting instruction that must be REMOVED from the directive
FORBIDDEN_SALUDA_SIEMPRE = "Saluda siempre"

# A fragment that unambiguously signals the prohibition against adding a second greeting
SECOND_GREETING_PROHIBITION_MARKERS = [
    "PROHIBIDO añadir otro saludo",
    "PROHIBIDO añadir un saludo",
    "no añadas otro saludo",
    "NO añadas otro saludo",
    "no añadas un saludo",
    "NO añadas un saludo",
]


def _extract_first_interaction_block(source: str) -> str:
    """Return the string literal injected inside the _is_first_interaction branch.

    Strategy: find the line containing ``_is_first_interaction`` and extract
    the text between the first ``parts.append(`` that follows and its matching
    closing parenthesis.  This avoids any runtime import of loader.py.
    """
    # Find the _is_first_interaction block
    marker = "_is_first_interaction"
    idx = source.find(marker)
    assert idx != -1, f"Could not find '{marker}' in loader.py source"

    # Find the next parts.append( after that marker
    append_start = source.find("parts.append(", idx)
    assert append_start != -1, "Could not find 'parts.append(' after _is_first_interaction"

    # Find the matching closing paren — walk forward counting open/close parens
    paren_depth = 0
    scan_from = append_start + len("parts.append(")
    end_idx = scan_from
    for i, ch in enumerate(source[scan_from:], start=scan_from):
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            if paren_depth == 0:
                end_idx = i
                break
            paren_depth -= 1
    return source[scan_from:end_idx]


class TestLoaderFirstInteractionDirective:
    """loader.py first-interaction directive must enforce AP-5 (no duplicate greeting).

    AP-5: the LLM already outputs the identity phrase; adding 'Saluda siempre'
    causes a second greeting paragraph.  The fix removes that instruction and
    adds an explicit PROHIBIDO to prevent the model from adding another saludo.
    """

    def _get_block(self) -> str:
        source = LOADER_PY.read_text(encoding="utf-8")
        return _extract_first_interaction_block(source)

    def test_loader_first_interaction_no_saluda_siempre(self):
        """The _is_first_interaction directive must NOT contain 'Saluda siempre'.

        'Saluda siempre' caused the LLM to emit a second greeting paragraph
        after the identity phrase — the root cause of the AP-5 double-saludo bug.
        """
        block = self._get_block()
        assert FORBIDDEN_SALUDA_SIEMPRE not in block, (
            "loader.py _is_first_interaction directive still contains 'Saluda siempre'. "
            "This instruction triggers a second greeting after the identity phrase (AP-5). "
            "Remove it and add an explicit PROHIBIDO prohibition instead."
        )

    def test_loader_first_interaction_has_prohibition(self):
        """The _is_first_interaction directive must contain an explicit prohibition
        against adding a second greeting after the identity phrase.

        AP-5: The LLM identity phrase IS the saludo — the directive must make
        it unambiguous that no additional greeting should be appended.
        """
        block = self._get_block()
        found = any(marker in block for marker in SECOND_GREETING_PROHIBITION_MARKERS)
        assert found, (
            "loader.py _is_first_interaction directive is missing an explicit prohibition "
            "against adding a second greeting. Expected one of: "
            + str(SECOND_GREETING_PROHIBITION_MARKERS)
            + ". AP-5 requires the directive to state that the identity phrase IS the saludo."
        )

    def test_loader_preserves_legal_identity_phrase(self):
        """The _is_first_interaction directive must still contain the legal identity phrase.

        Regression guard: the Reglamento UE 2024/1689 compliance phrase and the
        'asistente con IA de MSI Automotive' identity sentence must not be removed.
        """
        block = self._get_block()
        assert LEGAL_IDENTITY_PHRASE in block, (
            f"loader.py _is_first_interaction directive is missing the legal identity phrase "
            f"'{LEGAL_IDENTITY_PHRASE}'. This phrase is required by Reglamento UE 2024/1689 "
            f"and must always be present in the first-interaction directive."
        )
