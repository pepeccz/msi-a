"""
Unit tests for element_tools.py docstring accuracy (T16).

Spec REQ-4.1: the calcular_tarifa_con_elementos docstring must reflect
current behavior — precio_comunicado is set by pre_expediente_mode.py,
NOT by the tool's _state_update.

Covers:
- Docstring contains "pre_expediente_mode.py" reference
- Docstring does NOT contain "REFACTOR-001"
"""
from __future__ import annotations


def _get_tool_doc() -> str:
    """Return the effective documentation string for calcular_tarifa_con_elementos.

    LangChain's @tool decorator overwrites __doc__ with a generic message,
    but preserves the original docstring in the .description attribute.
    We check .description (the source of truth for the tool's behavior docs).
    """
    from agent.tools.element_tools import calcular_tarifa_con_elementos

    # LangChain StructuredTool exposes the real docstring as .description
    return getattr(calcular_tarifa_con_elementos, "description", "") or ""


class TestCalcularTarifaDocstring:
    """Docstring must accurately describe current behavior re: precio_comunicado."""

    def test_docstring_references_pre_expediente_mode(self):
        """
        GIVEN calcular_tarifa_con_elementos tool
        WHEN its description is inspected (LangChain stores real docstring in .description)
        THEN it must contain "pre_expediente_mode.py" to describe who sets precio_comunicado.
        """
        doc = _get_tool_doc()
        assert "pre_expediente_mode.py" in doc, (
            "calcular_tarifa_con_elementos.description must reference 'pre_expediente_mode.py' "
            "to describe who sets precio_comunicado=True. See spec REQ-4.1."
        )

    def test_docstring_does_not_contain_refactor_001(self):
        """
        GIVEN calcular_tarifa_con_elementos tool
        WHEN its description is inspected
        THEN it must NOT contain "REFACTOR-001" (obsolete note).
        """
        doc = _get_tool_doc()
        assert "REFACTOR-001" not in doc, (
            "calcular_tarifa_con_elementos.description must NOT contain 'REFACTOR-001'. "
            "This note is obsolete — the tool no longer sets precio_comunicado via _state_update. "
            "See spec REQ-4.1."
        )
