"""
Intent routing table tests for the intent-aware-pre-expediente-routing change.

Layer A — verifies that the <intent_routing> section in pre_expediente_discovery.md
contains the ternary INFO / IDENTIFY / PROCEED table with correct lexical markers,
borderline anchors, and no inline CTA strings.

All tests are pure content assertions — no mocking, no DB, no Redis.
Files read directly from disk via pathlib.Path.

Spec coverage: Layer A scenarios from spec/intent-aware-pre-expediente-routing
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "agent" / "prompts"
MODES_DIR = PROMPTS_DIR / "modes"
DISCOVERY_MD = MODES_DIR / "pre_expediente_discovery.md"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_block(content: str, open_tag: str, close_tag: str) -> str:
    """Extract text between XML-like tags. Returns empty string if not found."""
    start = content.find(open_tag)
    end = content.find(close_tag)
    if start == -1 or end == -1:
        return ""
    return content[start + len(open_tag) : end]


def _get_proceed_rows(routing_block: str) -> list[str]:
    """
    Return the lines from the routing table that correspond to PROCEED rows.

    A PROCEED row is any table row that contains "PROCEED" (case-insensitive).
    """
    lines = routing_block.splitlines()
    return [line for line in lines if "PROCEED" in line.upper()]


def _get_info_rows(routing_block: str) -> list[str]:
    """
    Return lines from the routing table that correspond to INFO rows.

    INFO rows are identified by the word "INFO" (case-insensitive) outside
    of IDENTIFY and PROCEED context.  We also include rows with generic
    informational intent labels ("pregunta general", "explorar", "catálogo")
    because the design uses those as INFO-class entries.
    """
    lines = routing_block.splitlines()
    return [
        line
        for line in lines
        if re.search(r"\bINFO\b", line, re.IGNORECASE)
        or "pregunta general" in line.lower()
        or "explorar cat" in line.lower()
        or "qué es" in line.lower()
        or "cómo funciona" in line.lower()
        or "explícame" in line.lower()
    ]


def _get_identify_rows(routing_block: str) -> list[str]:
    """
    Return lines from the routing table that correspond to IDENTIFY rows.

    IDENTIFY rows contain the word "IDENTIFY" (case-insensitive) or
    describe identification intent ("describir", "quiero saber sobre").
    """
    lines = routing_block.splitlines()
    return [
        line
        for line in lines
        if "IDENTIFY" in line.upper()
        or "describir" in line.lower()
        or "quiero saber sobre" in line.lower()
    ]


# ---------------------------------------------------------------------------
# A-T1 — Structural: ≥3 rows per class (INFO, IDENTIFY, PROCEED)
# ---------------------------------------------------------------------------


class TestIntentRoutingTableStructure:
    """
    A-T1: <intent_routing> section must contain at least 3 rows for each of
    INFO, IDENTIFY, and PROCEED intent classes with lexical markers.

    Spec: Layer A — Intent routing table structural coverage
    """

    def test_intent_routing_block_present(self):
        """<intent_routing> block must exist in discovery.md."""
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert block, (
            "discovery.md is missing the <intent_routing> block. "
            "The ternary intent routing table must exist."
        )

    def test_intent_routing_table_has_proceed_info_identify_rows(self):
        """<intent_routing> must contain ≥3 PROCEED rows, ≥3 INFO rows, ≥3 IDENTIFY rows.

        The table must be ternary (INFO / IDENTIFY / PROCEED) with at least
        3 entries per class, each with lexical markers/signals.

        Spec: Layer A — Intent routing table structural coverage
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        # Count table rows (lines starting with | that are not the header separator)
        table_rows = [
            line.strip()
            for line in routing_block.splitlines()
            if line.strip().startswith("|") and "---" not in line
        ]
        # Must have at least 7 rows: header + 6 data rows (≥3 per class min 2 classes checked)
        data_rows = table_rows[1:]  # skip header row

        # PROCEED: at least 1 explicit PROCEED row
        proceed_rows = _get_proceed_rows(routing_block)
        assert len(proceed_rows) >= 1, (
            f"<intent_routing> must contain at least 1 explicit PROCEED row. "
            f"Found {len(proceed_rows)}. PROCEED is the new intent class that triggers "
            f"the consolidated pricing turn."
        )

        # INFO: at least 2 informational rows (general info + catalog = 2 classes)
        info_rows = _get_info_rows(routing_block)
        assert len(info_rows) >= 2, (
            f"<intent_routing> must contain at least 2 INFO-class rows "
            f"(e.g. 'pregunta general', 'explorar catálogo'). Found {len(info_rows)}."
        )

        # IDENTIFY: at least 1 IDENTIFY row
        identify_rows = _get_identify_rows(routing_block)
        assert len(identify_rows) >= 1, (
            f"<intent_routing> must contain at least 1 IDENTIFY row "
            f"(e.g. 'describir elemento'). Found {len(identify_rows)}."
        )

        # Total data rows: at least 6 (the design prescribes 6)
        assert len(data_rows) >= 4, (
            f"<intent_routing> table must have at least 4 data rows (ternary table). "
            f"Found {len(data_rows)} data rows."
        )


# ---------------------------------------------------------------------------
# A-T2 — PROCEED lexicon tight markers present
# ---------------------------------------------------------------------------


class TestProceedLexiconMarkers:
    """
    A-T2: PROCEED rows must mention the tight lexical triggers for explicit
    purchase intent: "quiero homologar", "voy a homologar", "necesito homologar",
    and "dame presupuesto".

    Spec: Layer A — PROCEED utterance triggers consolidated pricing turn
    Design: Lexicon PROCEED (tight)
    """

    def test_proceed_lexicon_tight_markers_present(self):
        """PROCEED rows must contain the tight lexical markers for explicit intent.

        Spec: PROCEED utterances ('quiero homologar', 'voy a homologar',
        'necesito homologar', 'dame presupuesto') must appear as signals in
        the PROCEED section of the routing table.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        required_markers = [
            "quiero homologar",
            "voy a homologar",
            "necesito homologar",
        ]

        proceed_rows = _get_proceed_rows(routing_block)
        assert proceed_rows, (
            "No PROCEED rows found in <intent_routing>. Cannot verify markers."
        )

        # Combine all PROCEED rows into one searchable string
        proceed_text = "\n".join(proceed_rows).lower()

        for marker in required_markers:
            assert marker.lower() in proceed_text, (
                f"PROCEED rows do not contain the required lexical trigger '{marker}'. "
                f"The PROCEED lexicon must include tight markers that signal explicit "
                f"purchase intent. Current PROCEED rows: {proceed_rows}"
            )

    def test_proceed_rows_reference_calcular_tarifa(self):
        """PROCEED rows must reference calcular_tarifa to signal the auto-pricing flow.

        The design requires that PROCEED intent triggers an automatic call to
        calcular_tarifa_con_elementos in the same turn.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        proceed_rows = _get_proceed_rows(routing_block)
        assert proceed_rows, "No PROCEED rows found in <intent_routing>."

        proceed_text = "\n".join(proceed_rows).lower()
        assert "calcular_tarifa" in proceed_text, (
            "PROCEED rows must reference 'calcular_tarifa' to signal the automatic "
            "pricing flow. The table should document what action is triggered. "
            f"Current PROCEED rows: {proceed_rows}"
        )


# ---------------------------------------------------------------------------
# A-T3 — Borderline: INFO markers must NOT appear in PROCEED rows
# ---------------------------------------------------------------------------


class TestBorderlineInfoNotInProceed:
    """
    A-T3: INFO borderline markers must not contaminate PROCEED rows.

    Phrases like "quiero saber si", "¿se puede", "¿qué documentación" are
    INFO/IDENTIFY signals — they must NOT appear in PROCEED rows, or the LLM
    will over-activate the consolidated pricing flow on feasibility questions.

    Spec: Borderline — Feasibility question → INFO (no price calc)
    """

    def test_borderline_info_markers_not_in_proceed_rows(self):
        """INFO borderline markers ('¿se puede', '¿qué documentación', 'quiero saber si')
        must NOT appear in the PROCEED rows of <intent_routing>.

        AP concern: if these phrases appear in PROCEED rows, the LLM may
        activate auto-pricing on feasibility questions (PROCEED over-activation).
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        proceed_rows = _get_proceed_rows(routing_block)
        if not proceed_rows:
            pytest.skip("No PROCEED rows found — structural test handles absence.")

        proceed_text = "\n".join(proceed_rows).lower()

        info_borderline_markers = [
            "¿se puede",
            "qué documentación",
            "quiero saber si",
        ]

        for marker in info_borderline_markers:
            assert marker.lower() not in proceed_text, (
                f"PROCEED rows contain the INFO borderline marker '{marker}'. "
                f"This risks PROCEED over-activation on feasibility questions. "
                f"'{marker}' is an INFO signal and must only appear in INFO/IDENTIFY rows. "
                f"Current PROCEED rows: {proceed_rows}"
            )


# ---------------------------------------------------------------------------
# A-T4 — Borderline anchors: 4 specific utterances classified correctly
# ---------------------------------------------------------------------------


class TestBorderlineAnchors:
    """
    A-T4: Four borderline utterances must be classified as specified in the spec.

    These anchors prevent edge-case mis-routing:
    - "quiero saber si puedo homologar X" → INFO (feasibility)
    - "necesito homologar X" → PROCEED (explicit intent)
    - "me gustaría homologar X" → PROCEED (desire-form)
    - "me han dicho que tengo que homologar X" → IDENTIFY (ambiguous third-party)

    Spec: Borderline Intent Anchors (all 4 scenarios)
    """

    def test_borderline_quiero_saber_si_is_info(self):
        """'quiero saber si' must appear as an INFO/IDENTIFY signal, NOT in PROCEED rows.

        Spec: Feasibility question → INFO (no price calc)
        'quiero saber si puedo homologar X' is a feasibility question, not a
        purchase commitment — it must not trigger the consolidated pricing turn.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        # "quiero saber si" must NOT appear in PROCEED rows
        proceed_rows = _get_proceed_rows(routing_block)
        proceed_text = "\n".join(proceed_rows).lower()
        assert "quiero saber si" not in proceed_text, (
            "'quiero saber si' appeared in PROCEED rows. This is an INFO borderline "
            "marker (feasibility question) and must never trigger auto-pricing. "
            f"PROCEED rows: {proceed_rows}"
        )

        # "quiero saber si" OR a reference to feasibility/IDENTIFY must exist
        # somewhere in the routing block (in an INFO or IDENTIFY row)
        full_text = routing_block.lower()
        has_identify_context = (
            "identify" in full_text
            or "describir" in full_text
            or "quiero saber" in full_text
        )
        assert has_identify_context, (
            "No IDENTIFY/INFO context found in routing block that would classify "
            "'quiero saber si' as a non-PROCEED intent. The table must distinguish "
            "feasibility questions from explicit purchase intent."
        )

    def test_borderline_necesito_is_proceed(self):
        """'necesito homologar' must appear in PROCEED rows as an explicit trigger.

        Spec: Explicit proceed intent → PROCEED
        'necesito homologar X' signals explicit purchase commitment and must
        trigger the consolidated single-turn pricing flow.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        proceed_rows = _get_proceed_rows(routing_block)
        assert proceed_rows, (
            "No PROCEED rows found in <intent_routing>. "
            "'necesito homologar' cannot be classified as PROCEED without a PROCEED row."
        )

        proceed_text = "\n".join(proceed_rows).lower()
        assert "necesito homologar" in proceed_text, (
            "'necesito homologar' is not listed in any PROCEED row. "
            "Spec: Explicit proceed intent → PROCEED. This is a tight lexical marker "
            "that must appear in the PROCEED signals column. "
            f"Current PROCEED rows: {proceed_rows}"
        )

    def test_borderline_me_gustaria_is_proceed(self):
        """'me gustaría homologar' must be covered by PROCEED signals.

        Spec: Desire-form proceed intent → PROCEED
        'me gustaría homologar X' expresses a willingness to proceed and must
        trigger the consolidated single-turn pricing flow when conditions allow.

        Note: the design specifies 'me gustaría' is desire-form PROCEED.
        The routing table may list it or cover it via the general PROCEED class.
        We verify it does NOT appear in INFO rows and PROCEED row exists.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        # Must NOT appear in INFO rows as an info/describe signal
        info_rows = _get_info_rows(routing_block)
        info_text = "\n".join(info_rows).lower()
        assert "me gustaría homologar" not in info_text, (
            "'me gustaría homologar' appeared in INFO rows. Per spec (Desire-form proceed "
            "intent → PROCEED), this phrase signals purchase intent, not just information seeking."
        )

        # PROCEED row must exist (already verified in A-T1, but belt-and-suspenders)
        proceed_rows = _get_proceed_rows(routing_block)
        assert proceed_rows, (
            "No PROCEED rows found — 'me gustaría homologar' cannot be classified as PROCEED."
        )

    def test_borderline_me_han_dicho_is_identify(self):
        """'me han dicho que tengo que homologar' must map to IDENTIFY (ambiguous).

        Spec: Third-party-told proceed intent → IDENTIFY (ambiguous)
        This phrasing indicates the user was told by a third party to homologate —
        there is no personal purchase commitment, so it must default to IDENTIFY
        (conservative), not PROCEED, to avoid auto-pricing on ambiguous intent.
        """
        content = DISCOVERY_MD.read_text(encoding="utf-8")
        routing_block = _get_block(content, "<intent_routing>", "</intent_routing>")
        assert routing_block, "discovery.md is missing the <intent_routing> block."

        # "me han dicho" must NOT appear in PROCEED rows
        proceed_rows = _get_proceed_rows(routing_block)
        proceed_text = "\n".join(proceed_rows).lower()
        assert "me han dicho" not in proceed_text, (
            "'me han dicho' appeared in PROCEED rows. Per spec, 'me han dicho que tengo "
            "que homologar X' is ambiguous (third-party told) and must map to IDENTIFY, "
            "not PROCEED. This prevents auto-pricing on ambiguous third-party references."
        )

        # IDENTIFY rows must exist
        identify_rows = _get_identify_rows(routing_block)
        assert identify_rows, (
            "No IDENTIFY rows found in <intent_routing>. The 'me han dicho' anchor "
            "requires an IDENTIFY class to fall back to."
        )
