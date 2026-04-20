"""
Unit tests for pre_expediente_discovery.md prompt content.

Covers AC-1.1: <post_tool_behavior> block present.
Covers AC-1.2: "PROHIBIDO pedir confirmación" hard rule present.
Covers AC-1.3: "No presiones" scoped to pre-tool phase or absent.
Covers AC-1.4: "pregunta explícitamente" scoped with pre-tool temporal qualifier.

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

_DISCOVERY_MD = (
    Path(__file__).parents[3] / "agent" / "prompts" / "modes" / "pre_expediente_discovery.md"
)


# ---------------------------------------------------------------------------
# Helper — load file content once per call (fast, no caching issues)
# ---------------------------------------------------------------------------


def _load() -> str:
    return _DISCOVERY_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-1.1 — <post_tool_behavior> block must be present
# ---------------------------------------------------------------------------


class TestPostToolBehaviorBlock:
    """AC-1.1: discovery.md MUST contain a <post_tool_behavior> block."""

    def test_post_tool_behavior_block_present(self):
        """
        GIVEN the discovery markdown is read from disk
        WHEN searched for a <post_tool_behavior> block
        THEN the substring '<post_tool_behavior>' MUST be found (case-insensitive).

        This block establishes the HARD post-tool precedence rule: after
        identificar_y_resolver_elementos returns elementos_listos, the LLM
        MUST emit docs+warnings+CTA immediately without asking confirmation.
        """
        content = _load()
        assert "<post_tool_behavior>" in content.lower(), (
            "pre_expediente_discovery.md must contain a <post_tool_behavior> block. "
            "This block holds the HARD post-tool precedence rule. AC-1.1."
        )


# ---------------------------------------------------------------------------
# AC-1.2 — "PROHIBIDO pedir confirmación" hard rule must be present
# ---------------------------------------------------------------------------


class TestProhibidoConfirmacionRule:
    """AC-1.2: the hard-rule text MUST appear verbatim in discovery.md."""

    def test_prohibido_confirmacion_rule_present(self):
        """
        GIVEN the discovery markdown is read from disk
        WHEN searched for the hard rule text
        THEN the exact string 'PROHIBIDO pedir confirmación' MUST be found
        (case-sensitive — it is a deliberate CAPS marker for LLM emphasis).

        This rule prevents the LLM from asking confirmation questions after
        the tool has already successfully identified the elements. AC-1.2.
        """
        content = _load()
        assert "PROHIBIDO pedir confirmación" in content, (
            "pre_expediente_discovery.md must contain the exact text "
            "'PROHIBIDO pedir confirmación' within the <post_tool_behavior> block. "
            "AC-1.2."
        )


# ---------------------------------------------------------------------------
# AC-1.3 — "No presiones" must be scoped or absent
# ---------------------------------------------------------------------------


class TestNoPresionesScoped:
    """AC-1.3: 'No presiones' must be absent OR scoped inside <category_inference>."""

    def test_no_presiones_scoped_or_removed(self):
        """
        GIVEN the discovery markdown is read from disk
        WHEN the phrase 'No presiones' is searched (case-insensitive)
        THEN it MUST either:
          (a) be absent from the file entirely, OR
          (b) appear ONLY inside the <category_inference>...</category_inference> block, OR
          (c) appear ONLY on a line that also contains 'antes' (case-insensitive)

        'No presiones' at the top-level persona sentence (line 2) has no temporal
        scope and causes the LLM to apply it post-tool, suppressing directive
        emission. It must be scoped to the pre-identification phase. AC-1.3.
        """
        content = _load()
        content_lower = content.lower()

        # If completely absent — test passes trivially
        if "no presiones" not in content_lower:
            return

        # Extract <category_inference> block content (if present)
        ci_content = ""
        ci_start = content_lower.find("<category_inference>")
        ci_end = content_lower.find("</category_inference>")
        if ci_start != -1 and ci_end != -1:
            ci_content = content_lower[ci_start:ci_end + len("</category_inference>")]

        # Find all lines containing "no presiones"
        lines_with_phrase = [
            line for line in content.splitlines()
            if "no presiones" in line.lower()
        ]

        for line in lines_with_phrase:
            line_lower = line.lower()
            # Option (b): line is inside category_inference block
            in_category_inference = "no presiones" in ci_content and any(
                line.strip() in ci_content for line in lines_with_phrase
            )
            # Option (c): same line also contains 'antes'
            has_antes_qualifier = "antes" in line_lower

            assert in_category_inference or has_antes_qualifier, (
                f"AC-1.3: 'No presiones' found on line '{line.strip()}' without "
                "temporal scope. It must be absent, inside <category_inference>, or "
                "qualified with 'antes de identificar' / 'antes de llamar'."
            )


# ---------------------------------------------------------------------------
# AC-1.4 — "pregunta explícitamente" must be scoped with pre-tool qualifier
# ---------------------------------------------------------------------------


class TestPreguntaFallbackScoped:
    """AC-1.4: 'pregunta explícitamente' must co-occur with a pre-tool temporal marker."""

    def test_pregunta_fallback_scoped(self):
        """
        GIVEN the discovery markdown is read from disk
        WHEN the phrase 'pregunta explícitamente' is found (case-insensitive)
        THEN each occurrence MUST appear on the same line as 'ANTES' or 'antes'
        OR the phrase is absent (trivially passes).

        Without temporal scoping, the LLM can apply 'pregunta explícitamente'
        post-tool (e.g., triggered by a user typo causing low confidence), leading
        to confirmation questions after successful identification. AC-1.4.
        """
        content = _load()

        # If phrase is absent — test passes trivially
        if "pregunta explícitamente" not in content.lower():
            return

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "pregunta explícitamente" in line.lower():
                # Check same line for 'antes' qualifier
                has_qualifier_on_line = "antes" in line.lower()
                # Check next line as well (tolerance for multi-line constructs)
                has_qualifier_on_next = (
                    i + 1 < len(lines) and "antes" in lines[i + 1].lower()
                )
                assert has_qualifier_on_line or has_qualifier_on_next, (
                    f"AC-1.4: 'pregunta explícitamente' found on line '{line.strip()}' "
                    "without a pre-tool temporal qualifier ('ANTES de llamar "
                    "identificar_y_resolver_elementos' or equivalent). "
                    "Scope this instruction to the pre-identification phase. AC-1.4."
                )


# ---------------------------------------------------------------------------
# T4 (Optional) — Snapshot regression guard for all hardening markers
# ---------------------------------------------------------------------------


class TestDiscoveryHardeningMarkers:
    """
    Regression guard: asserts all 4 critical hardening substrings in one sweep.

    Future edits that accidentally revert the caution-bias hardening will fail
    this test. It is intentionally broad — any prompt refactor that removes
    these markers must first update this test and get review sign-off.
    """

    def test_discovery_prompt_contains_hardening_markers(self):
        """
        GIVEN the updated discovery markdown with caution-bias hardening
        WHEN inspected for all 4 critical structural markers
        THEN all 4 MUST be present — this prevents accidental reversion.

        Markers:
          1. <post_tool_behavior> block open tag
          2. PROHIBIDO pedir confirmación (hard rule text)
          3. "antes" qualifier on the same line as "no presiones" (scoping)
          4. "ANTES de llamar identificar_y_resolver_elementos" (explicit pre-tool scope)
        """
        content = _load()
        content_lower = content.lower()

        # Marker 1: post_tool_behavior block
        assert "<post_tool_behavior>" in content_lower, (
            "Hardening marker 1 missing: <post_tool_behavior> block removed. "
            "This block must remain — it holds the HARD post-tool precedence rule."
        )

        # Marker 2: PROHIBIDO hard rule
        assert "PROHIBIDO pedir confirmación" in content, (
            "Hardening marker 2 missing: 'PROHIBIDO pedir confirmación' text removed. "
            "This exact text must remain as the LLM hard rule against confirmation questions."
        )

        # Marker 3: "no presiones" must carry "antes" qualifier
        if "no presiones" in content_lower:
            lines_with_phrase = [
                line for line in content.splitlines()
                if "no presiones" in line.lower()
            ]
            for line in lines_with_phrase:
                assert "antes" in line.lower(), (
                    f"Hardening marker 3 degraded: 'No presiones' on line "
                    f"'{line.strip()}' has lost its temporal scope qualifier ('antes'). "
                    "This re-opens the caution bias post-tool."
                )

        # Marker 4: explicit pre-tool scope on category inference fallback
        assert "antes de llamar identificar_y_resolver_elementos" in content_lower, (
            "Hardening marker 4 missing: 'ANTES de llamar identificar_y_resolver_elementos' "
            "qualifier removed from category_inference block. "
            "This re-scopes 'pregunta explícitamente' as unconditional."
        )


# ---------------------------------------------------------------------------
# AC-2.1 — Lexical PROCEED rule must contain the core trigger phrases
# ---------------------------------------------------------------------------


class TestProceedLexicalRule:
    """AC-2.1: <tool_rules> MUST contain the deterministic lexical trigger phrases for PROCEED.

    Background: intent-aware routing confused "quiero homologar X" with IDENTIFY,
    causing the LLM to skip calcular_tarifa and omit price in the first turn.
    Fix: make PROCEED match strictly lexical — any of these phrases → always PROCEED.
    """

    # Single source of truth: import from lexical_triggers instead of hardcoding
    from agent.prompts.lexical_triggers import PROCEED_PHRASES as REQUIRED_PROCEED_PHRASES

    def test_all_proceed_lexical_phrases_present(self):
        """
        GIVEN the discovery markdown with lexical PROCEED hardening
        WHEN searched for each required phrase
        THEN every phrase in REQUIRED_PROCEED_PHRASES MUST appear (case-insensitive).

        These are the deterministic lexical triggers that force calcular_tarifa
        in the same turn. Losing any of them re-opens the ambiguity bug.
        """
        content = _load().lower()
        missing = [p for p in self.REQUIRED_PROCEED_PHRASES if p not in content]
        assert not missing, (
            f"Discovery prompt missing PROCEED lexical triggers: {missing}. "
            "These phrases must appear in <tool_rules> so the LLM treats them as "
            "deterministic PROCEED markers (not interpretive intent). AC-2.1."
        )

    def test_lexical_rule_hard_marker_present(self):
        """
        GIVEN the lexical PROCEED rule in <tool_rules>
        WHEN searched for the hard-rule header
        THEN 'REGLA LÉXICA DURA' MUST appear (case-sensitive, Spanish CAPS marker).

        This header signals to the LLM that the rule is non-negotiable —
        without it, the block reads as soft guidance.
        """
        content = _load()
        assert "REGLA LÉXICA DURA" in content, (
            "Discovery prompt missing 'REGLA LÉXICA DURA' header. "
            "This exact CAPS text is the LLM's signal that the rule overrides "
            "interpretive intent classification. AC-2.1."
        )


# ---------------------------------------------------------------------------
# AC-2.2 — CTA estado-4 must be gated by "calcular_tarifa called this turn"
# ---------------------------------------------------------------------------


class TestCtaEstado4Gated:
    """AC-2.2: discovery.md MUST forbid CTA estado-4 when calcular_tarifa was not called."""

    def test_cta_estado_4_gated_rule_present(self):
        """
        GIVEN the discovery markdown
        WHEN searched for the CTA estado-4 gating rule
        THEN the prompt MUST state that CTA estado-4 is PROHIBIDO without calcular_tarifa.

        Background: the LLM emitted CTA estado-4 ("¿abrimos el expediente directamente?")
        in turns where it had NOT called calcular_tarifa, resulting in an
        expediente-open offer without communicated price. The hard rule blocks this.
        """
        content = _load()
        # Must mention the CTA estado-4 literal AND the gate in the same sentence/block
        assert "CTA estado-4" in content, (
            "Discovery prompt missing reference to 'CTA estado-4' in gating rule. AC-2.2."
        )
        # Look for a PROHIBIDO marker co-occurring with calcular_tarifa
        content_lower = content.lower()
        has_gate = (
            "prohibido" in content_lower
            and "cta estado-4" in content_lower
            and "calcular_tarifa" in content_lower
        )
        assert has_gate, (
            "Discovery prompt missing hard gate: 'PROHIBIDO emitir CTA estado-4 sin "
            "calcular_tarifa_con_elementos'. Without this gate the LLM can offer "
            "expediente-open without a communicated price. AC-2.2."
        )


# ---------------------------------------------------------------------------
# AC-2.3 — <post_tool_behavior> must branch on intent (not hardcoded CTA estado-3)
# ---------------------------------------------------------------------------


class TestPostToolBehaviorBranchesOnIntent:
    """AC-2.3: <post_tool_behavior> MUST branch on intent (PROCEED vs IDENTIFY).

    Background: previous version of <post_tool_behavior> hardcoded CTA estado-3
    as the post-tool emission, which took precedence over <tool_rules> and
    caused the LLM to skip calcular_tarifa even for PROCEED intents.
    Fix: <post_tool_behavior> must explicitly route PROCEED → calcular_tarifa
    and IDENTIFY → CTA estado-3.
    """

    def test_post_tool_behavior_mentions_calcular_tarifa_for_proceed(self):
        """
        GIVEN the <post_tool_behavior> block
        WHEN searched for intent-based branching
        THEN it MUST mention calcular_tarifa_con_elementos as the PROCEED branch.

        Without this, the LLM follows the hardcoded "emit CTA estado-3" path
        and never calculates the tariff, regressing the bug. AC-2.3.
        """
        content = _load()
        # Extract <post_tool_behavior> block
        ptb_start = content.find("<post_tool_behavior>")
        ptb_end = content.find("</post_tool_behavior>")
        assert ptb_start != -1 and ptb_end != -1, (
            "Cannot locate <post_tool_behavior> block boundaries."
        )
        ptb_block = content[ptb_start:ptb_end]

        assert "calcular_tarifa_con_elementos" in ptb_block, (
            "<post_tool_behavior> must mention calcular_tarifa_con_elementos as the "
            "PROCEED branch. Otherwise the LLM defaults to CTA estado-3 always. AC-2.3."
        )
        # Must reference both CTA estado-3 and CTA estado-4 (or proceed_contract)
        has_estado3 = "estado-3" in ptb_block.lower()
        has_proceed_path = (
            "estado-4" in ptb_block.lower() or "proceed_contract" in ptb_block.lower()
        )
        assert has_estado3 and has_proceed_path, (
            "<post_tool_behavior> must reference both IDENTIFY branch (CTA estado-3) "
            "and PROCEED branch (CTA estado-4 or <proceed_contract>). "
            "Missing branches re-introduce the bug. AC-2.3."
        )


# ---------------------------------------------------------------------------
# CTA deduplication — no literal CTA strings in discovery.md (use {{CTA_N}})
# ---------------------------------------------------------------------------


class TestCtaDeduplicationDiscovery:
    """Spec REQ-3.1: no literal CTA strings in discovery.md — use {{CTA_N}} placeholders."""

    _LITERAL_CTAS = [
        "¿Quieres que te ayude con alguna homologación?",
        "¿Te interesa alguno? Puedo darte el precio exacto.",
        "¿Te muestro ejemplos de cómo deben ser las fotos o te calculo el presupuesto?",
        "¿Te enseño ejemplos de las fotos que necesitaremos o abrimos el expediente directamente?",
        "¿Abrimos expediente o tienes alguna duda?",
    ]

    def test_no_literal_cta_in_discovery(self):
        """
        GIVEN pre_expediente_discovery.md
        WHEN searched for any of the 5 canonical CTA literal strings
        THEN NO matches are found — all references use {{CTA_N}} placeholders.
        """
        content = _load()
        found = [cta for cta in self._LITERAL_CTAS if cta in content]
        assert not found, (
            f"Literal CTA strings found in discovery.md — replace with {{{{CTA_N}}}} placeholders: {found}"
        )


# ---------------------------------------------------------------------------
# T11: Priority hierarchy block — <priority_hierarchy> with L1–L5 levels
# ---------------------------------------------------------------------------


class TestPriorityHierarchyBlock:
    """Spec REQ-3.3: discovery.md must contain a <priority_hierarchy> block
    near the document start with 5 levels (L1–L5) each with a description."""

    def test_priority_hierarchy_block_present(self):
        """
        GIVEN pre_expediente_discovery.md
        WHEN the file is inspected
        THEN a <priority_hierarchy> block must exist.
        """
        content = _load()
        assert "<priority_hierarchy>" in content, (
            "pre_expediente_discovery.md must contain a <priority_hierarchy> block near the start."
        )

    def test_priority_hierarchy_has_five_levels(self):
        """
        GIVEN pre_expediente_discovery.md
        WHEN <priority_hierarchy> block is inspected
        THEN it must declare exactly 5 levels L1 through L5.
        """
        content = _load()
        for level in ["L1", "L2", "L3", "L4", "L5"]:
            assert f"**{level}" in content or f"{level} —" in content or f"{level}:" in content, (
                f"priority_hierarchy block missing level {level}"
            )

    def test_precedencia_rules_have_level_tags(self):
        """
        GIVEN pre_expediente_discovery.md
        WHEN rules that previously used PRECEDENCIA language are inspected
        THEN they must be prefixed with a level tag (L1–L5).
        """
        content = _load()
        # At least 3 rules should carry level tags
        level_tag_occurrences = sum(
            content.count(f"(L{n})")
            for n in range(1, 6)
        )
        assert level_tag_occurrences >= 3, (
            f"Expected at least 3 level tags (L1)–(L5) in discovery.md PRECEDENCIA rules, "
            f"found {level_tag_occurrences}"
        )
