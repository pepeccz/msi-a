"""Tests for backward-compatible tool alias routing.

Task 3.3-3.4: Old checkpoint tool calls for 'actualizar_datos_expediente'
must route to the correct new split tool based on args inspection.
"""

from __future__ import annotations

from agent.modes.tool_executor import _resolve_tool_alias, TOOL_ALIASES


class TestToolAliasResolution:
    """Alias map routes old tool name to correct new tool."""

    def test_old_name_is_registered(self):
        """actualizar_datos_expediente must be in the alias map."""
        assert "actualizar_datos_expediente" in TOOL_ALIASES

    def test_routes_to_personal_when_datos_personales(self):
        """Args with datos_personales should route to actualizar_datos_personales."""
        result = _resolve_tool_alias(
            "actualizar_datos_expediente",
            {"datos_personales": {"nombre": "Pepe"}},
        )
        assert result == "actualizar_datos_personales"

    def test_routes_to_vehiculo_when_datos_vehiculo(self):
        """Args with datos_vehiculo should route to actualizar_datos_vehiculo."""
        result = _resolve_tool_alias(
            "actualizar_datos_expediente",
            {"datos_vehiculo": {"marca": "Honda"}},
        )
        assert result == "actualizar_datos_vehiculo"

    def test_defaults_to_personal_when_empty(self):
        """Empty args default to personal (most common case)."""
        result = _resolve_tool_alias(
            "actualizar_datos_expediente",
            {},
        )
        assert result == "actualizar_datos_personales"

    def test_non_aliased_tool_returns_unchanged(self):
        """Tools not in alias map return unchanged."""
        result = _resolve_tool_alias("some_other_tool", {})
        assert result == "some_other_tool"
