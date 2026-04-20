"""
Tests for seleccionar_variante_por_respuesta tool description/docstring.
Batch B — Layer B: tool description must state calling precondition.
"""

import inspect

import pytest


def _get_tool_function():
    """Import the tool function directly to inspect its docstring."""
    from agent.tools.element_tools import seleccionar_variante_por_respuesta
    return seleccionar_variante_por_respuesta


def _get_docstring() -> str:
    tool_fn = _get_tool_function()
    # LangGraph/LangChain @tool wraps the function; the docstring may be on .func
    # or on the tool object description attribute.
    doc = None
    if hasattr(tool_fn, "description"):
        doc = tool_fn.description
    if not doc and hasattr(tool_fn, "func"):
        doc = inspect.getdoc(tool_fn.func) or ""
    if not doc:
        doc = inspect.getdoc(tool_fn) or ""
    return doc


class TestSeleccionarVarianteDescription:
    """
    The description / docstring of seleccionar_variante_por_respuesta must
    state the calling precondition: only call when pending_variants is non-empty.
    """

    def test_seleccionar_variante_description_states_only_when_variants_exist(self):
        """
        The tool description MUST reference 'pending_variants' AND include a
        condition that prohibits/restricts calls when no variants are pending.

        Design D4 + Spec Layer B:
          - 'pending_variants' must appear in description
          - phrase indicating 'only when' / 'solo cuando' / 'SOLO' condition
        """
        doc = _get_docstring()
        assert doc, "seleccionar_variante_por_respuesta has no description/docstring"

        assert "pending_variants" in doc, (
            f"Tool description must reference 'pending_variants'. "
            f"Got description: {doc[:300]}"
        )

        # Must include a conditional / restrictive phrase
        has_restriction = (
            "solo" in doc.lower()
            or "only" in doc.lower()
            or "SOLO" in doc
            or "PROHIBIDO" in doc
            or "no invoques" in doc.lower()
            or "no llames" in doc.lower()
        )
        assert has_restriction, (
            f"Tool description must include a restriction phrase (solo/only/PROHIBIDO/no invoques). "
            f"Got description: {doc[:300]}"
        )

    def test_seleccionar_variante_description_is_non_empty(self):
        """Baseline: the tool must have a description at all."""
        doc = _get_docstring()
        assert len(doc) > 20, (
            f"Tool description is too short (< 20 chars): {doc!r}"
        )
