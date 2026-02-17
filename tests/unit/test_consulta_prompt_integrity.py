"""
Tests for consulta_mode.md prompt integrity.

Verifies that the CONSULTA_MODE prompt does not contain hardcoded prices
or references to tools not available in _get_consulta_tools().
"""

import re
from pathlib import Path

import pytest

# Resolve path relative to the project root (works both on host and inside Docker container)
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent  # tests/unit/ → tests/ → project root

# Try project root first; fall back to /app (Docker container layout)
_candidate = _PROJECT_ROOT / "agent" / "prompts" / "modes" / "consulta_mode.md"
PROMPT_PATH = _candidate if _candidate.exists() else Path("/app/agent/prompts/modes/consulta_mode.md")


class TestConsultaPromptNoPrices:
    """Verify no hardcoded prices leak into CONSULTA_MODE prompt."""

    def test_no_eur_prices(self):
        """Prompt must not contain prices like '410 EUR' or '170 EUR'."""
        content = PROMPT_PATH.read_text()
        # Match patterns like: 410 EUR, ~170 EUR, 410€, etc.
        price_patterns = [
            r"\d+\s*EUR",
            r"\d+\s*€",
            r"~\d+\s*EUR",
            r"\d+\s*\+\s*IVA",
        ]
        for pattern in price_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert not matches, (
                f"Found hardcoded price pattern '{pattern}' in consulta_mode.md: {matches}. "
                f"Prices must only come from calcular_tarifa_con_elementos tool."
            )

    def test_no_orientativo_price_table(self):
        """Prompt must not contain a 'Precios Típicos' section."""
        content = PROMPT_PATH.read_text()
        assert "Precios Típicos" not in content, (
            "Found 'Precios Típicos' section in consulta_mode.md. "
            "This was removed to prevent hardcoded price leaks."
        )

    def test_no_precio_orientativo_instruction(self):
        """Prompt must not instruct to give 'precios orientativos'."""
        content = PROMPT_PATH.read_text()
        # The word "orientativo" should only appear in prohibition context, not as instruction
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "orientativo" in line.lower():
                # Check it's in a prohibition/NUNCA context
                assert any(word in line.lower() for word in ["nunca", "no ", "prohib"]), (
                    f"Line {i} mentions 'orientativo' without prohibition context: '{line.strip()}'. "
                    f"CONSULTA_MODE must not instruct giving orientative prices."
                )


class TestConsultaPromptToolCoherence:
    """Verify prompt only references tools in _get_consulta_tools()."""

    # These are the ONLY tools available in CONSULTA_MODE
    ALLOWED_TOOLS = {
        "listar_categorias",
        "listar_elementos",
        "obtener_servicios_adicionales",
        "escalar_a_humano",
    }

    # Tools that must NOT be referenced
    FORBIDDEN_TOOLS = {
        "identificar_tipo_vehiculo",
        "calcular_tarifa_con_elementos",
        "identificar_y_resolver_elementos",
        "seleccionar_variante_por_respuesta",
        "enviar_imagenes_ejemplo",
        "confirmar_presupuesto",
        "consultar_documentacion_rag",  # RAG system disabled
    }

    def test_no_forbidden_tool_references(self):
        """Prompt must not reference tools not in _get_consulta_tools()."""
        content = PROMPT_PATH.read_text()
        for tool_name in self.FORBIDDEN_TOOLS:
            # Allow references in prohibition context (e.g., "NO uses calcular_tarifa...")
            lines_with_tool = [
                (i, line) for i, line in enumerate(content.split("\n"), 1)
                if tool_name in line
            ]
            for line_num, line in lines_with_tool:
                is_prohibition = any(
                    word in line.lower() for word in ["no ", "nunca", "no está disponible"]
                )
                assert is_prohibition, (
                    f"Line {line_num} references forbidden tool '{tool_name}' "
                    f"without prohibition: '{line.strip()}'"
                )

    def test_no_viabilidad_mode_reference(self):
        """Prompt must not reference VIABILIDAD_MODE (deprecated, merged into PRESUPUESTO)."""
        content = PROMPT_PATH.read_text()
        assert "VIABILIDAD_MODE" not in content, (
            "Found 'VIABILIDAD_MODE' in consulta_mode.md. "
            "VIABILIDAD was merged into PRESUPUESTO_MODE."
        )
