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
