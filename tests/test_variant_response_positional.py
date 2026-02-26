"""
Tests unitarios para el sistema de resolución posicional de variantes via variant_position.

Arquitectura:
- `variant_position` es un campo canónico en la BD que asigna la posición de presentación
  al usuario (1=A, 2=B, 3=C...).
- Se asigna automáticamente al crear una variante via API.
- La Fase 0 en seleccionar_variante_por_respuesta() mapea directamente "a"→1, "b"→2, etc.
- Esto reemplaza el parche temporal de índice en array (que era frágil a reordenamientos).

Casos cubiertos:
    1.  "A" → variant_position=1 (primera variante)
    2.  "B" → variant_position=2 (segunda variante)
    3.  "C" → variant_position=3 (tercera variante, en GLP con 3 variantes)
    4.  "1"/"2"/"3" → NO activan Fase 0 (números excluidos por colisión con FAROS_LA keywords)
    5.  Mayúsculas "A", "B" → normalizadas correctamente
    6.  Respuesta "interior" → sigue funcionando por keyword (sin regresión)
    7.  Respuesta "oculto" → sigue funcionando por keyword (sin regresión, score 0.8)
    8.  "D" con elemento de solo 2 variantes (ninguna con variant_position=4) → no match → keyword
    9.  "ambos" con multi_select_keywords → NO afectada por Fase 0 (multi-select primero)
    10. Respuesta vacía "" → no activa Fase 0
    11. Respuesta "ab" (2 chars) → no activa Fase 0
    12. Variante sin variant_position (None) → no incluida en match posicional
    13. confidence es 0.95 (más alta que la Fase 0 anterior de 0.85)
    14. match_method es "variant_position"
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

FAKE_CATEGORY_ID = "aaaaaaaa-0000-0000-0000-000000000001"

# Variantes de PLACA_SOLAR (2 variantes con variant_position)
VARIANTS_PLACA_SOLAR = [
    {
        "code": "PLACA_SOLAR_SIMPLE",
        "name": "Placa Solar - Regulador existente",
        "variant_code": "REGULADOR_EXISTENTE",
        "keywords": ["existente", "regulador existente", "ya tiene regulador"],
        "sort_order": 10,
        "variant_position": 1,
        "parent_element_id": "parent-uuid",
        "multi_select_keywords": [],
    },
    {
        "code": "PLACA_SOLAR_MALETERO",
        "name": "Placa Solar - Regulador en maletero",
        "variant_code": "REGULADOR_MALETERO",
        "keywords": ["maletero", "exterior", "oculto", "regulador maletero"],
        "sort_order": 20,
        "variant_position": 2,
        "parent_element_id": "parent-uuid",
        "multi_select_keywords": [],
    },
]

# Variantes de GLP_INSTALACION (3 variantes con variant_position)
VARIANTS_GLP = [
    {
        "code": "GLP_BOMBONA",
        "name": "GLP - Bombona",
        "variant_code": "BOMBONA",
        "keywords": ["bombona", "gas"],
        "sort_order": 161,
        "variant_position": 1,
        "parent_element_id": "parent-uuid-glp",
        "multi_select_keywords": [],
    },
    {
        "code": "GLP_DEPOSITO_FIJO",
        "name": "GLP - Depósito Fijo",
        "variant_code": "DEPOSITO_FIJO",
        "keywords": ["deposito", "fijo", "deposito fijo"],
        "sort_order": 162,
        "variant_position": 2,
        "parent_element_id": "parent-uuid-glp",
        "multi_select_keywords": [],
    },
    {
        "code": "GLP_DUOCONTROL",
        "name": "GLP - Duocontrol",
        "variant_code": "DUOCONTROL",
        "keywords": ["duocontrol", "duo"],
        "sort_order": 163,
        "variant_position": 3,
        "parent_element_id": "parent-uuid-glp",
        "multi_select_keywords": [],
    },
]

# Variantes sin variant_position (legado / NULL en BD)
VARIANTS_NO_POSITION = [
    {
        "code": "ELEM_A",
        "name": "Elemento A",
        "variant_code": "A",
        "keywords": ["opcion a", "primera"],
        "sort_order": 10,
        "variant_position": None,
        "parent_element_id": "parent-uuid",
        "multi_select_keywords": [],
    },
    {
        "code": "ELEM_B",
        "name": "Elemento B",
        "variant_code": "B",
        "keywords": ["opcion b", "segunda"],
        "sort_order": 20,
        "variant_position": None,
        "parent_element_id": "parent-uuid",
        "multi_select_keywords": [],
    },
]

# Base element sin multi_select_keywords
BASE_ELEMENT_NO_MULTI = {
    "code": "PLACA_SOLAR",
    "multi_select_keywords": [],
}

# Base element con multi_select_keywords (INTERMITENTES)
BASE_ELEMENT_MULTI = {
    "code": "INTERMITENTES",
    "multi_select_keywords": ["ambos", "todos", "los dos"],
}

# Variantes INTERMITENTES para multi-select (con variant_position)
VARIANTS_INTERMITENTES = [
    {
        "code": "INTERMITENTES_DEL",
        "name": "Intermitentes Delanteros",
        "variant_code": "DEL",
        "keywords": ["delantero", "delantera", "frontal"],
        "sort_order": 82,
        "variant_position": 1,
        "parent_element_id": "parent-uuid-int",
        "multi_select_keywords": [],
    },
    {
        "code": "INTERMITENTES_TRAS",
        "name": "Intermitentes Traseros",
        "variant_code": "TRAS",
        "keywords": ["trasero", "trasera", "posterior"],
        "sort_order": 84,
        "variant_position": 2,
        "parent_element_id": "parent-uuid-int",
        "multi_select_keywords": [],
    },
]


def _make_tool_call(variants, base_element, respuesta: str, category_id=FAKE_CATEGORY_ID):
    """
    Simula la llamada a seleccionar_variante_por_respuesta con mocks.
    Retorna el dict parseado del JSON que devuelve la tool.
    """
    import asyncio
    from agent.tools.element_tools import seleccionar_variante_por_respuesta

    with (
        patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new=AsyncMock(return_value=category_id),
        ),
        patch(
            "agent.tools.element_tools.get_element_service",
        ) as mock_get_svc,
        patch(
            "agent.tools.element_tools.validate_category_slug",
            return_value=None,
        ),
    ):
        mock_svc = MagicMock()
        mock_svc.get_element_variants = AsyncMock(return_value=variants)
        mock_svc.get_element_by_code = AsyncMock(return_value=base_element)
        mock_get_svc.return_value = mock_svc

        result = asyncio.run(
            seleccionar_variante_por_respuesta.ainvoke(
                {
                    "categoria_vehiculo": "aseicars-prof",
                    "codigo_elemento_base": base_element["code"],
                    "respuesta_usuario": respuesta,
                }
            )
        )

    return json.loads(result)


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Fase 0: variant_position matching
# ─────────────────────────────────────────────────────────────────────────────


class TestVariantPositionMatching:
    """Tests para la Fase 0: detección posicional A/B/C → variante via variant_position."""

    def test_letter_a_selects_variant_position_1(self):
        """'A' → variante con variant_position=1 con confidence 0.95."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "A")

        assert "selected_variant" in result, f"Debería haber selected_variant, got: {result}"
        assert result["selected_variant"] == "PLACA_SOLAR_SIMPLE"
        assert result["confidence"] == 0.95
        assert result.get("match_method") == "variant_position"
        assert result.get("variant_position") == 1

    def test_letter_b_selects_variant_position_2(self):
        """'B' → variante con variant_position=2."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "B")

        assert result["selected_variant"] == "PLACA_SOLAR_MALETERO"
        assert result["confidence"] == 0.95
        assert result.get("match_method") == "variant_position"
        assert result.get("variant_position") == 2

    def test_letter_c_selects_variant_position_3(self):
        """'C' → variante con variant_position=3 (GLP con 3 variantes)."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "C")

        assert result["selected_variant"] == "GLP_DUOCONTROL"
        assert result.get("match_method") == "variant_position"
        assert result.get("variant_position") == 3

    def test_letter_a_in_glp_selects_position_1(self):
        """'A' → GLP_BOMBONA (variant_position=1)."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "A")

        assert result["selected_variant"] == "GLP_BOMBONA"
        assert result.get("variant_position") == 1

    def test_letter_b_in_glp_selects_position_2(self):
        """'B' → GLP_DEPOSITO_FIJO (variant_position=2)."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "B")

        assert result["selected_variant"] == "GLP_DEPOSITO_FIJO"
        assert result.get("variant_position") == 2

    def test_number_1_does_not_activate_positional(self):
        """
        '1' → Los números NO activan la Fase 0 posicional.
        Razón: FAROS_LA_2F tiene "2" como keyword → ambigüedad.
        Los números caen al keyword matching normal.
        """
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "1")

        assert result.get("match_method") != "variant_position"
        assert "error" in result

    def test_number_2_does_not_activate_positional(self):
        """'2' → No activa Fase 0 (números excluidos por colisión con FAROS_LA keywords)."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "2")

        assert result.get("match_method") != "variant_position"

    def test_number_3_does_not_activate_positional(self):
        """'3' → números excluidos de Fase 0, cae a keyword matching → error."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "3")

        assert result.get("match_method") != "variant_position"

    def test_uppercase_a_is_normalized(self):
        """'A' (mayúscula) debe normalizarse a 'a' y funcionar igual."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "A")
        assert "selected_variant" in result
        assert result.get("match_method") == "variant_position"

    def test_letter_d_with_no_matching_position_falls_to_keyword(self):
        """
        'D' con elemento de solo 2 variantes (sin variant_position=4).
        La Fase 0 busca variant_position=4 → no encontrado → cae al keyword matching.
        """
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "D")

        assert result.get("match_method") != "variant_position"
        # Con 2 variantes y "D" → keyword score 0 → error
        assert "error" in result

    def test_response_with_spaces_stripped(self):
        """'  B  ' (con espacios) → stripped a 'b' → variant_position=2."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "  B  ")

        assert result["selected_variant"] == "PLACA_SOLAR_MALETERO"
        assert result.get("match_method") == "variant_position"

    def test_variants_without_position_skip_positional(self):
        """
        Variantes con variant_position=None → la Fase 0 no encuentra match → keyword matching.
        Esto es el comportamiento de fallback para variantes legado sin position asignada.
        """
        base = {"code": "ELEM_BASE", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_NO_POSITION, base, "A")

        # Sin variant_position, la Fase 0 no puede matchear → cae a keyword
        assert result.get("match_method") != "variant_position"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — No regresión: keyword matching sigue funcionando
# ─────────────────────────────────────────────────────────────────────────────


class TestKeywordRegressionAfterPositionalFix:
    """Verifica que el keyword matching sigue funcionando tras cambiar Fase 0."""

    def test_keyword_existente_still_works(self):
        """'existente' sigue dando match por keyword (no por posición)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "existente"
        )
        assert "selected_variant" in result
        assert result["selected_variant"] == "PLACA_SOLAR_SIMPLE"
        assert result.get("match_method") != "variant_position"

    def test_keyword_oculto_still_works(self):
        """'oculto' sigue dando match por keyword (score 0.8)."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "oculto"
        )
        assert "selected_variant" in result
        assert result["selected_variant"] == "PLACA_SOLAR_MALETERO"
        assert result.get("match_method") != "variant_position"

    def test_keyword_maletero_still_works(self):
        """'maletero' → PLACA_SOLAR_MALETERO por keyword."""
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "maletero"
        )
        assert result["selected_variant"] == "PLACA_SOLAR_MALETERO"

    def test_keyword_bombona_glp_still_works(self):
        """'bombona' → GLP_BOMBONA por keyword (no por posición)."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "bombona")

        assert result["selected_variant"] == "GLP_BOMBONA"
        assert result.get("match_method") != "variant_position"

    def test_keyword_deposito_fijo_glp_still_works(self):
        """'deposito fijo' → GLP_DEPOSITO_FIJO por keyword."""
        base_glp = {"code": "GLP_INSTALACION", "multi_select_keywords": []}
        result = _make_tool_call(VARIANTS_GLP, base_glp, "deposito fijo")

        assert result["selected_variant"] == "GLP_DEPOSITO_FIJO"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Multi-select no afectado
# ─────────────────────────────────────────────────────────────────────────────


class TestMultiSelectNotAffected:
    """La Fase 0 no interfiere con el multi-select check que va antes."""

    def test_ambos_triggers_multi_select(self):
        """
        'ambos' con multi_select_keywords → retorna selected_variants (multi-select).
        La Fase 0 va DESPUÉS del multi-select check, así que no interfiere.
        """
        result = _make_tool_call(
            VARIANTS_INTERMITENTES, BASE_ELEMENT_MULTI, "ambos"
        )

        assert "selected_variants" in result
        assert result.get("mode") == "multi_select"
        assert "INTERMITENTES_DEL" in result["selected_variants"]
        assert "INTERMITENTES_TRAS" in result["selected_variants"]

    def test_todos_triggers_multi_select(self):
        """'todos' con multi_select_keywords → multi-select."""
        result = _make_tool_call(
            VARIANTS_INTERMITENTES, BASE_ELEMENT_MULTI, "todos"
        )
        assert "selected_variants" in result
        assert result.get("mode") == "multi_select"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Casos edge
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Casos borde para asegurar robustez de la Fase 0."""

    def test_empty_response_does_not_activate_positional(self):
        """
        Respuesta vacía '' → stripped es '' → no está en LETTER_TO_POSITION.
        Cae a keyword matching → error.
        """
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, ""
        )
        assert result.get("match_method") != "variant_position"
        assert "error" in result

    def test_two_char_response_does_not_activate_positional(self):
        """
        'ab' (2 chars) → stripped es 'ab' → no en LETTER_TO_POSITION.
        Cae a keyword matching → error.
        """
        result = _make_tool_call(
            VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "ab"
        )
        assert result.get("match_method") != "variant_position"

    def test_positional_includes_instrucciones(self):
        """El resultado posicional incluye 'instrucciones' para que el LLM sepa qué hacer."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "A")
        assert "instrucciones" in result
        assert "calcular_tarifa_con_elementos" in result["instrucciones"]

    def test_positional_includes_variant_code(self):
        """El resultado posicional incluye variant_code para contexto."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "A")
        assert "variant_code" in result
        assert result["variant_code"] == "REGULADOR_EXISTENTE"

    def test_positional_includes_variant_position_field(self):
        """El resultado posicional incluye el campo variant_position para trazabilidad."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "B")
        assert "variant_position" in result
        assert result["variant_position"] == 2

    def test_confidence_is_higher_than_old_phase_0(self):
        """La nueva Fase 0 tiene confidence 0.95 (mayor que el antiguo 0.85)."""
        result = _make_tool_call(VARIANTS_PLACA_SOLAR, BASE_ELEMENT_NO_MULTI, "A")
        assert result["confidence"] == 0.95
