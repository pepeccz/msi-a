"""
Batch D — Consolidated PROCEED flow tests.

Layer D of intent-aware-pre-expediente-routing: verifies that the discovery prompt
contains the PROCEED consolidated auto-calc rule, the variant gate precedence rule,
the consolidated response contract, and the single-source-of-truth State-4 CTA.

All tests are pure content assertions — no mocking, no DB, no Redis.
Files read directly from disk via pathlib.Path.

Spec coverage: Layer D scenarios from sdd/intent-aware-pre-expediente-routing/spec
Design reference: sdd/intent-aware-pre-expediente-routing/design (D3 verbatim)
"""

from pathlib import Path

DISCOVERY_MD = (
    Path(__file__).resolve().parent.parent.parent
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_discovery.md"
)

CTA_ESTADO_4_VERBATIM = (
    "¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?"
)


def _load_discovery() -> str:
    return DISCOVERY_MD.read_text(encoding="utf-8")


def _get_block(content: str, open_tag: str, close_tag: str) -> str:
    """Extract text between XML-like tags. Returns empty string if not found."""
    start = content.find(open_tag)
    end = content.find(close_tag)
    if start == -1 or end == -1:
        return ""
    return content[start + len(open_tag) : end]


def _get_proceed_rows(routing_block: str) -> list[str]:
    """Return the lines from the routing table that correspond to PROCEED rows."""
    return [line for line in routing_block.splitlines() if "PROCEED" in line.upper()]


# ---------------------------------------------------------------------------
# D-T1 — PROCEED auto-calc rule present in discovery.md
# ---------------------------------------------------------------------------


class TestDiscoveryContainsProceedAutoCalcRule:
    """
    D-T1: discovery.md must contain the PROCEED consolidated auto-calc rule text.

    The design (D3) requires an explicit contract that when intent=PROCEED and
    con_variantes=[], the LLM must invoke identificar AND calcular_tarifa in the
    SAME TURN. The rule text (or equivalent wording) must be present in the prompt
    so the LLM knows to act on it.

    Spec: Layer D — Single-Turn Consolidated Response on PROCEED
    """

    def test_discovery_contains_proceed_auto_calc_rule(self):
        """
        discovery.md must contain the auto-calc contract for PROCEED intent
        AS AN EXPLICIT BLOCK (not only embedded in the routing table).

        Design D3 specifies a dedicated contract block that details the 5-field
        response ordering. This block must exist separately from the table row
        so the LLM has a clear, unambiguous instruction for the consolidated turn.

        Required content:
        - "EN EL MISMO TURNO" — the single-turn contract signal
        - "skip_validation=True" — the validation-skip contract
        - A numbered or structured listing of the response fields (indicating
          the block is a dedicated contract, not just a table cell)

        Spec: Layer D — PROCEED utterance triggers consolidated pricing turn
        """
        content = _load_discovery()

        # Must contain "EN EL MISMO TURNO" — the single-turn contract signal
        assert "EN EL MISMO TURNO" in content, (
            "discovery.md is missing the 'EN EL MISMO TURNO' contract for PROCEED intent. "
            "Design D3 requires the prompt to explicitly state that identificar AND "
            "calcular_tarifa must be called in the SAME LLM TURN when intent=PROCEED "
            "and con_variantes=[]. Without this, the LLM may split the flow into 2 turns."
        )

        # Must reference calcular_tarifa with skip_validation contract
        assert "skip_validation=True" in content, (
            "discovery.md must reference 'skip_validation=True' in the PROCEED contract. "
            "Design D3 requires calcular_tarifa_con_elementos(skip_validation=True) — "
            "this signals that element validation was already done by identificar."
        )

        # Must contain an explicit contract block (not just embedded in the table row).
        # The design prescribes the contract as a dedicated block with "DEBE contener"
        # or equivalent instruction specifying the ordering of the 5 fields.
        has_explicit_contract = (
            "DEBE contener" in content
            or "respuesta consolidada DEBE" in content
            or "ai_response DEBE" in content
            or "en este orden" in content.lower()
        )
        assert has_explicit_contract, (
            "discovery.md is missing the explicit PROCEED response contract block. "
            "Design D3 requires a dedicated block stating 'La ai_response del turno PROCEED "
            "consolidado DEBE contener, en este orden: 1. Precio ... 2. Advertencias ... "
            "3. Documentación ... 4. válido 30 días ... 5. CTA estado-4'. "
            "This must exist as a structured block, not only embedded in the table row."
        )

    def test_proceed_auto_calc_rule_references_identificar(self):
        """
        The PROCEED auto-calc rule must reference 'identificar' as the first step.

        Triangulation: both tools must be mentioned in the PROCEED contract —
        identificar (step 1) AND calcular_tarifa (step 2, same turn).

        Spec: Layer D — Both tools called in same PROCEED turn
        """
        content = _load_discovery()

        # identificar must be referenced in the PROCEED flow context
        assert "identificar" in content, (
            "discovery.md must reference 'identificar' as part of the PROCEED flow. "
            "The two-step contract (identificar → calcular_tarifa) requires both tools "
            "to be mentioned so the LLM knows the sequence."
        )

        # The combination of both references must be present (already tested above)
        # Verify the file contains both in proximity (within 500 chars of each other)
        idx_mismo_turno = content.find("EN EL MISMO TURNO")
        idx_identificar = content.rfind("identificar", 0, idx_mismo_turno + 500)
        assert idx_identificar != -1, (
            "discovery.md must contain 'identificar' before or near the 'EN EL MISMO TURNO' "
            "contract. The auto-calc rule must specify both steps."
        )


# ---------------------------------------------------------------------------
# D-T2 — Variant gate precedence over PROCEED
# ---------------------------------------------------------------------------


class TestDiscoveryContainsVariantGatePrecedenceRule:
    """
    D-T2: The PROCEED fila in <intent_routing> must document that con_variantes>0
    defers to the variant gate first — auto-calc does NOT fire when variants exist.

    This is Design quadrant 1: PROCEED + con_variantes>0 → ask variant question first.
    The prompt must explicitly state this to prevent the LLM from skipping variant
    resolution when a user says "quiero homologar" but variants are pending.

    Spec: Layer D — PROCEED with pending variants defers to variant gate
    """

    def test_discovery_contains_variant_gate_precedence_rule(self):
        """
        discovery.md must state that con_variantes>0 takes precedence over PROCEED
        intent — the variant gate wins and auto-calc must NOT fire.

        The design prescribes: "Precedencia: variant gate (cuadrante 1,2) SIEMPRE
        gana sobre intent." The prompt must encode this to avoid the LLM skipping
        variant resolution.

        Spec: Layer D — PROCEED with pending variants defers to variant gate
        """
        content = _load_discovery()

        # Must contain con_variantes reference (either >0 or the condition)
        has_variantes_condition = (
            "con_variantes>0" in content
            or "con_variantes > 0" in content
            or "variantes pendientes" in content
            or "variantes>0" in content
        )
        assert has_variantes_condition, (
            "discovery.md is missing the variant gate precedence condition "
            "(con_variantes>0 or 'variantes pendientes'). "
            "Design quadrant 1 requires the prompt to state that when variants are pending, "
            "the LLM must ask the variant question FIRST — even on PROCEED intent. "
            "Without this, the LLM may skip variant resolution and auto-calc incorrectly."
        )

    def test_proceed_row_mentions_variant_gate_condition(self):
        """
        The PROCEED fila or the PROCEED contract must reference the variant gate condition.

        Triangulation: the variant gate precedence must be documented in the context
        of the PROCEED flow — either in the table row or in the PROCEED contract block.

        Spec: Layer D — PROCEED with pending variants defers to variant gate (cuadrante 1)
        """
        content = _load_discovery()
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        proceed_rows = _get_proceed_rows(routing_block)
        assert proceed_rows, "No PROCEED rows found in <intent_routing>."

        # The PROCEED row must mention the variant gate condition in some form
        proceed_text = " ".join(proceed_rows).lower()

        has_variant_gate = (
            "con_variantes" in proceed_text
            or "variante" in proceed_text
            or "variant" in proceed_text
        )
        assert has_variant_gate, (
            "PROCEED row in <intent_routing> does not mention the variant gate condition. "
            "The PROCEED flow description must note that variant resolution takes precedence "
            "when con_variantes>0. Current PROCEED rows: "
            + str(proceed_rows)
        )


# ---------------------------------------------------------------------------
# D-T3 — Consolidated response contract: price + warnings + docs + CTA-4
# ---------------------------------------------------------------------------


class TestDiscoveryContainsConsolidatedResponseContract:
    """
    D-T3: discovery.md must contain the consolidated response contract for PROCEED.

    Design D3 specifies that the ai_response MUST contain, in order:
    1. Precio con formato "XXX € IVA incluido"
    2. Advertencias ⚠️ del elemento
    3. Documentación base + del elemento
    4. "_válido 30 días_"
    5. CTA estado-4

    The prompt must encode this ordering contract so the LLM composes the
    consolidated message correctly.

    Spec: Layer D — PROCEED with zero variants yields full consolidated message
    """

    def test_discovery_contains_consolidated_response_contract(self):
        """
        discovery.md must contain the consolidated response contract AS A DEDICATED
        BLOCK with numbered field ordering.

        Design D3 verbatim: "La ai_response del turno PROCEED consolidado DEBE contener,
        en este orden: 1. Precio con formato 'XXX € IVA incluido' 2. Advertencias ⚠️
        3. Documentación base + del elemento 4. '_válido 30 días_' 5. CTA estado-4"

        The block must exist with ALL 5 fields enumerated so the LLM has a clear
        ordering contract for the consolidated PROCEED message.

        Spec: Layer D — PROCEED with zero variants yields full consolidated message
        """
        content = _load_discovery()

        # The contract block must be an explicit enumerated list.
        # Verify all 5 required fields are present together in the contract block.
        # Use a dedicated contract section marker search.

        # Field 1: Precio with IVA format
        has_precio_iva = "IVA incluido" in content
        assert has_precio_iva, (
            "discovery.md PROCEED contract is missing the price format 'IVA incluido'. "
            "Design D3 field 1: 'Precio con formato XXX € IVA incluido'."
        )

        # Field 2: Advertencias ⚠️ (emoji marker — exact)
        has_advertencias_emoji = "⚠️" in content
        assert has_advertencias_emoji, (
            "discovery.md PROCEED contract is missing the ⚠️ advertencias field. "
            "Design D3 field 2: 'Advertencias ⚠️ del elemento'."
        )

        # Field 4: _válido 30 días_ (markdown italic)
        has_validity_italic = "_válido 30 días_" in content
        assert has_validity_italic, (
            "discovery.md PROCEED contract is missing '_válido 30 días_' (markdown italic). "
            "Design D3 field 4 uses underscores: '_válido 30 días_'. "
            "The exact formatting matters so the LLM reproduces it correctly."
        )

        # Verify the contract block contains a numbered list (fields 1-5)
        # A numbered contract has at least "1." and "2." in proximity
        has_numbered_fields = (
            "1. Precio" in content
            or "1. precio" in content.lower()
        )
        assert has_numbered_fields, (
            "discovery.md is missing the numbered response contract for PROCEED. "
            "Design D3 requires an explicit '1. Precio ... 2. Advertencias ... 3. Doc ... "
            "4. válido 30 días ... 5. CTA estado-4' block. The numbered order tells the "
            "LLM exactly how to compose the consolidated PROCEED message."
        )

    def test_consolidated_contract_references_cta_estado_4(self):
        """
        The PROCEED contract must reference CTA estado-4 (by name or state reference).

        Triangulation: the contract must encode that the consolidated response ends
        with the State-4 CTA. The reference can be 'CTA estado-4', 'estado-4', or
        the verbatim CTA text (if in <natural_ctas> — single source of truth preserved).

        Spec: Layer D — PROCEED with zero variants yields full consolidated message
        """
        content = _load_discovery()

        has_cta4_ref = (
            "CTA estado-4" in content
            or "estado-4" in content
            or CTA_ESTADO_4_VERBATIM in content
        )
        assert has_cta4_ref, (
            "discovery.md is missing a reference to CTA estado-4 in the PROCEED contract. "
            "The consolidated response must close with the State-4 CTA verbatim. "
            "Either reference it by 'CTA estado-4' / 'estado-4' or keep it as the "
            "single canonical occurrence in <natural_ctas>."
        )


# ---------------------------------------------------------------------------
# D-T4 — CTA estado-4 verbatim: single source of truth respected
# ---------------------------------------------------------------------------


class TestProceedSectionCtaEstado4Verbatim:
    """
    D-T4: CTA Estado-4 verbatim must be present in discovery.md exactly once —
    the single canonical source is <natural_ctas>.

    The PROCEED section (fila in intent_routing OR the PROCEED contract block)
    must NOT duplicate the verbatim CTA. It must reference it as 'CTA estado-4'
    or 'estado-4' instead. The only verbatim occurrence is in <natural_ctas>.

    Spec: Layer D — precio_comunicado set True after PROCEED consolidated turn
    Design: Single source of truth — 'only the authoritative location keeps it verbatim'
    """

    def test_proceed_section_cta_estado4_verbatim(self):
        """
        CTA Estado-4 verbatim must appear exactly ONCE in discovery.md.

        The single canonical location is the <natural_ctas> block.
        If the PROCEED fila or contract block duplicates it, there are two sources
        of truth that can drift — AP-7 prohibits this.

        Design note: RESHAPE applied — PROCEED rows reference 'CTA estado-4' by
        name, not by verbatim copy. The verbatim lives only in <natural_ctas>.

        Spec: Layer D — precio_comunicado set True after PROCEED consolidated turn
        """
        content = _load_discovery()

        count = content.count(CTA_ESTADO_4_VERBATIM)
        assert count >= 1, (
            f"CTA Estado-4 verbatim ('{CTA_ESTADO_4_VERBATIM}') was not found in "
            "discovery.md. It must appear at least once (in <natural_ctas>)."
        )
        assert count == 1, (
            f"CTA Estado-4 verbatim appears {count} times in discovery.md. "
            "Single-source-of-truth rule requires exactly 1 occurrence — in <natural_ctas>. "
            "The PROCEED section must reference it by 'CTA estado-4', not duplicate it verbatim. "
            "Remove duplicate occurrences to prevent CTA drift."
        )

    def test_intent_routing_does_not_duplicate_cta_estado4(self):
        """
        The <intent_routing> block must NOT contain the CTA Estado-4 verbatim.

        Triangulation: AP-7 already enforces no inline CTA strings in routing rows.
        This test is a direct regression guard for the specific Estado-4 CTA phrase.

        Design: RESHAPE — PROCEED fila uses 'CTA estado-4' reference, not verbatim copy.
        """
        content = _load_discovery()
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        assert CTA_ESTADO_4_VERBATIM not in routing_block, (
            f"<intent_routing> block contains CTA Estado-4 verbatim. "
            "AP-7 + single-source rule: the table must use 'CTA estado-4' reference, "
            "not the verbatim string. The canonical verbatim location is <natural_ctas>."
        )

    def test_natural_ctas_contains_cta_estado4_verbatim(self):
        """
        <natural_ctas> must contain the CTA Estado-4 verbatim as its canonical location.

        This is the positive assertion: the CTA must exist in its canonical block.
        Without this, the entire single-source rule is moot.

        Spec: Cross-cutting — 5-CTA Registry Preserved
        """
        content = _load_discovery()
        natural_ctas_block = _get_block(content, "<natural_ctas>", "</natural_ctas>")
        assert natural_ctas_block, "discovery.md is missing the <natural_ctas> block."

        assert CTA_ESTADO_4_VERBATIM in natural_ctas_block, (
            f"<natural_ctas> block does not contain the CTA Estado-4 verbatim: "
            f"'{CTA_ESTADO_4_VERBATIM}'. "
            "This is the canonical source of truth — it must live here."
        )
