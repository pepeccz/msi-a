"""
Tests for hard rules in pre_expediente_discovery.md.
Batch B — Layer B: PROHIBIDO rule for variant invention.
"""

from pathlib import Path

DISCOVERY_MD = (
    Path(__file__).parent.parent.parent.parent
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_discovery.md"
)


def _load_discovery() -> str:
    return DISCOVERY_MD.read_text(encoding="utf-8")


def _extract_post_tool_behavior(content: str) -> str:
    """Extract the text inside <post_tool_behavior>…</post_tool_behavior>."""
    start = content.find("<post_tool_behavior>")
    end = content.find("</post_tool_behavior>")
    assert start != -1, "<post_tool_behavior> block not found in discovery.md"
    assert end != -1, "</post_tool_behavior> closing tag not found in discovery.md"
    return content[start:end + len("</post_tool_behavior>")]


class TestPostToolBehaviorHardRules:
    """The <post_tool_behavior> block must contain the PROHIBIDO invent-variant rule."""

    def test_post_tool_behavior_contains_prohibido_invent_variant_rule(self):
        """
        Asserts that <post_tool_behavior> contains the PROHIBIDO rule for
        seleccionar_variante_por_respuesta when elementos_con_variantes=[].

        Design D1 verbatim (required substrings):
          - "PROHIBIDO llamar seleccionar_variante_por_respuesta"
          - "elementos_con_variantes=[]"  (or variant: "elementos_con_variantes" + "[]" nearby)
          - "PROHIBIDO inventar preguntas de desambiguación"
        """
        content = _load_discovery()
        post_tool = _extract_post_tool_behavior(content)

        assert "PROHIBIDO llamar seleccionar_variante_por_respuesta" in post_tool, (
            "Missing: 'PROHIBIDO llamar seleccionar_variante_por_respuesta' "
            "in <post_tool_behavior> block"
        )
        assert "elementos_con_variantes" in post_tool, (
            "Missing: 'elementos_con_variantes' reference in <post_tool_behavior> block"
        )
        assert "[]" in post_tool, (
            "Missing: '[]' (empty list marker) in <post_tool_behavior> block"
        )
        assert "PROHIBIDO inventar preguntas de desambiguación" in post_tool, (
            "Missing: 'PROHIBIDO inventar preguntas de desambiguación' "
            "in <post_tool_behavior> block"
        )

    def test_post_tool_behavior_has_precedence_note(self):
        """
        The PROHIBIDO rule must explicitly state it has PRECEDENCIA
        (matches design: 'Esta regla tiene PRECEDENCIA sobre cualquier señal de cautela').
        """
        content = _load_discovery()
        post_tool = _extract_post_tool_behavior(content)

        assert "PRECEDENCIA" in post_tool, (
            "Missing: 'PRECEDENCIA' keyword in <post_tool_behavior> block. "
            "The PROHIBIDO rule must state it overrides caution signals."
        )

    def test_post_tool_behavior_references_listos_condition(self):
        """
        The rule must reference the positive condition (listos > 0 / at least one element
        identified) alongside the empty-variants condition.
        Design: 'CUANDO identificar_y_resolver_elementos retornó ... listos>0'
        """
        content = _load_discovery()
        post_tool = _extract_post_tool_behavior(content)

        # Either "listos>0" or "listos > 0" or "al menos un elemento" is acceptable
        has_listos = (
            "listos>0" in post_tool
            or "listos > 0" in post_tool
            or "listos=" in post_tool
            or "al menos un elemento" in post_tool
            or "elementos_listos" in post_tool
        )
        assert has_listos, (
            "Missing: a reference to the 'listos>0' condition in <post_tool_behavior>. "
            "The rule must specify it applies only when at least one element was identified."
        )
