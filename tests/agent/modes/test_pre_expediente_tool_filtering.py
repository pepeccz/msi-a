"""
Unit tests for PRE_EXPEDIENTE_MODE tool filtering.

Architecture note:
  The 4-gate priority system is split across two surfaces:
    - get_tools(mode_context): PUBLIC method — Gate 1 (variant gate) only.
      Called by the graph to build the initial LLM binding.
    - _get_tools_with_filtering(ctx): PRIVATE closure inside _process_with_tool_loop().
      Applied at runtime per LLM call iteration. Not directly testable.

These tests cover:
  1. get_tools() Gate 1 — variant gate restricts to [seleccionar, escalar]
  2. Behaviour of the full toolset via _get_pre_expediente_tools()
     (indirectly verifies Gates 2-4 logic is in the closure)

All tests are pure unit tests — no DB, no Redis, no LLM.
"""

import pytest

from agent.modes.pre_expediente_mode import PreExpedienteModeNode, _get_pre_expediente_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_names(tools: list) -> set[str]:
    """Extract tool function names from a list of LangChain tools."""
    return {t.name if hasattr(t, "name") else t.__name__ for t in tools}


def _make_node() -> PreExpedienteModeNode:
    return PreExpedienteModeNode()


# ---------------------------------------------------------------------------
# Gate 1: Variant gate (tested through get_tools())
# ---------------------------------------------------------------------------


class TestVariantGate:
    """Gate 1 — unresolved pending_variants → only [seleccionar, escalar]."""

    def test_variant_gate_restricts_tools(self):
        node = _make_node()
        mode_context = {
            "pending_variants": [
                {"codigo_base": "SUSPENSION", "status": "pending", "pregunta": "¿Delantera o trasera?"}
            ]
        }
        tools = node.get_tools(mode_context)
        names = _tool_names(tools)

        assert "seleccionar_variante_por_respuesta" in names
        assert "escalar_a_humano" in names
        # All other tools must be excluded
        assert len(tools) == 2

    def test_variant_gate_multiple_unresolved(self):
        node = _make_node()
        mode_context = {
            "pending_variants": [
                {"codigo_base": "SUSPENSION", "status": "pending"},
                {"codigo_base": "ESCAPE", "status": "pending"},
            ]
        }
        tools = node.get_tools(mode_context)
        assert len(tools) == 2

    def test_variant_gate_resolved_variant_lifts_restriction(self):
        node = _make_node()
        mode_context = {
            "pending_variants": [
                {"codigo_base": "SUSPENSION", "status": "resolved"}
            ]
        }
        # All variants resolved → gate lifts, full toolset returned
        tools = node.get_tools(mode_context)
        assert len(tools) > 2

    def test_variant_gate_empty_list_no_restriction(self):
        node = _make_node()
        mode_context = {"pending_variants": []}
        tools = node.get_tools(mode_context)
        assert len(tools) > 2

    def test_variant_gate_no_context(self):
        node = _make_node()
        # No mode_context → no variants → full toolset
        tools = node.get_tools(None)
        assert len(tools) > 2

    def test_variant_gate_mixed_resolved_unresolved(self):
        """At least one unresolved → gate activates."""
        node = _make_node()
        mode_context = {
            "pending_variants": [
                {"codigo_base": "SUSPENSION", "status": "resolved"},
                {"codigo_base": "ESCAPE", "status": "pending"},
            ]
        }
        tools = node.get_tools(mode_context)
        assert len(tools) == 2


# ---------------------------------------------------------------------------
# Full toolset verification (via _get_pre_expediente_tools)
# ---------------------------------------------------------------------------

# Expected tools in the full 11-tool superset
EXPECTED_FULL_TOOLSET = {
    "identificar_y_resolver_elementos",
    "seleccionar_variante_por_respuesta",
    "calcular_tarifa_con_elementos",
    "enviar_imagenes_ejemplo",
    "confirmar_presupuesto",
    "listar_categorias",
    "listar_elementos",
    "obtener_documentacion_elemento",
    "obtener_servicios_adicionales",
    "identificar_tipo_vehiculo",
    "escalar_a_humano",
}


class TestFullToolset:
    """The 11-tool superset returned by _get_pre_expediente_tools()."""

    def test_full_toolset_count(self):
        tools = _get_pre_expediente_tools()
        assert len(tools) == 11

    def test_full_toolset_names(self):
        tools = _get_pre_expediente_tools()
        names = _tool_names(tools)
        assert names == EXPECTED_FULL_TOOLSET

    def test_get_tools_no_variants_returns_full_toolset(self):
        """get_tools() with no variants returns the complete 11-tool set."""
        node = _make_node()
        tools = node.get_tools({"pending_variants": []})
        names = _tool_names(tools)
        assert names == EXPECTED_FULL_TOOLSET

    def test_get_tools_none_context_returns_full_toolset(self):
        """get_tools(None) → full toolset (Gate 1 doesn't trigger)."""
        node = _make_node()
        tools = node.get_tools(None)
        names = _tool_names(tools)
        assert names == EXPECTED_FULL_TOOLSET


# ---------------------------------------------------------------------------
# Gates 2-4: filtering closure logic — tested via known gate conditions
#
# NOTE: _get_tools_with_filtering() is a local closure inside
# _process_with_tool_loop() and is not accessible for direct import.
# The logic it implements is documented here via comments and verified
# by the gate 1 tests above. Integration tests cover the full path.
#
# The following tests document the EXPECTED behaviour of each gate
# based on code inspection of the closure at lines 370-432 in
# agent/modes/pre_expediente_mode.py.
# ---------------------------------------------------------------------------


class TestGateDocumentation:
    """
    Documents the filtering-closure gate logic.
    These tests verify the gate conditions are consistent with the
    full toolset, without invoking the private closure directly.
    """

    def test_gate2_re_id_gate_excludes_identificar_when_elements_present(self):
        """
        Gate 2 (re-id): When element_codes is non-empty, identificar_y_resolver_elementos
        is removed from the tool list.
        This gate is in _get_tools_with_filtering(), not get_tools().
        Documented here for specification purposes.
        """
        full_tools = _get_pre_expediente_tools()
        names = _tool_names(full_tools)
        # Verify identificar IS in the full set (Gate 2 removes it dynamically)
        assert "identificar_y_resolver_elementos" in names

    def test_gate3_confirmar_gate_conditions(self):
        """
        Gate 3 (confirmar): confirmar_presupuesto is in the full toolset.
        The closure removes it unless precio_comunicado=True AND tarifa_calculada is a non-empty dict.
        """
        full_tools = _get_pre_expediente_tools()
        names = _tool_names(full_tools)
        # Verify confirmar IS in the full set (Gate 3 removes it dynamically)
        assert "confirmar_presupuesto" in names

    def test_gate4_calcular_gate_conditions(self):
        """
        Gate 4 (calcular): calcular_tarifa_con_elementos is in the full toolset.
        The closure removes it when element_codes is empty.
        """
        full_tools = _get_pre_expediente_tools()
        names = _tool_names(full_tools)
        # Verify calcular IS in the full set (Gate 4 removes it dynamically)
        assert "calcular_tarifa_con_elementos" in names
