"""
Tests unitarios para el fix del bug de pending_variants en PresupuestoModeNode.

Bug: _extract_context_from_tool() buscaba data.get("success") o data.get("codigo")
para detectar selección exitosa de variante. La tool seleccionar_variante_por_respuesta
retorna "selected_variant" (single) o "selected_variants" (multi-select), NO esos campos.

Fix (AG-1): La condición ahora detecta has_selection con los campos correctos.

Casos cubiertos:
    1. Selección única exitosa → limpia pending_variants, actualiza elemento_confirmado
    2. Error de matching → NO limpia pending_variants (sigue bloqueando calcular_tarifa)
    3. Multi-selección → limpia pending_variants, actualiza element_codes con lista
    4. Flujo completo sin bloqueo (integración mínima)
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import pytest
from unittest.mock import patch, MagicMock


class TestVariantResolution:
    """Tests unitarios que ejercitan _extract_context_from_tool directamente."""

    def setup_method(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode
        self.mode = PresupuestoModeNode()

    def _call_extract(
        self,
        tool_name: str,
        tool_result: dict,
        tool_args: dict | None = None,
    ) -> dict:
        """
        Helper: llama _extract_context_from_tool con el resultado JSON-encoded.

        _extract_context_from_tool espera result como str (JSON) y lo parsea
        internamente. Reflejamos ese contrato aquí.
        """
        updates = {}
        result_json = json.dumps(tool_result, ensure_ascii=False)
        updates = self.mode._extract_context_from_tool(
            tool_name=tool_name,
            tool_args=tool_args or {},
            result=result_json,
        )
        return updates

    # ─────────────────────────────────────────────────────────────────────────
    # Caso 1: Selección única exitosa limpia pending_variants
    # ─────────────────────────────────────────────────────────────────────────

    def test_single_selection_clears_pending_variants(self):
        """
        Caso 1: La tool retorna selected_variant → pending_variants queda vacío.

        Antes del fix, data.get("success") era False y data.get("codigo") era None,
        por tanto la condición nunca era True y pending_variants NUNCA se limpiaba.
        """
        tool_result = {
            "selected_variant": "PLACA_SOLAR_SIMPLE",
            "confidence": 0.85,
            "name": "Placa solar conectada a regulador existente del vehículo",
            "variant_code": "REGULADOR_EXISTENTE",
            "instrucciones": "Usa el código 'PLACA_SOLAR_SIMPLE' en calcular_tarifa_con_elementos.",
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
            tool_args={
                "categoria_vehiculo": "motos-part",
                "codigo_elemento_base": "PLACA_SOLAR",
                "respuesta_usuario": "sí, quiero la simple",
            },
        )

        # pending_variants debe quedar vacío → desbloquea calcular_tarifa
        assert "pending_variants" in updates, (
            "Se debe incluir pending_variants en las actualizaciones"
        )
        assert updates["pending_variants"] == [], (
            f"pending_variants debe ser [] pero es {updates['pending_variants']!r}"
        )

        # elemento_confirmado debe actualizarse con el código correcto
        assert "elemento_confirmado" in updates, (
            "Se debe actualizar elemento_confirmado"
        )
        assert updates["elemento_confirmado"]["code"] == "PLACA_SOLAR_SIMPLE", (
            f"código incorrecto: {updates['elemento_confirmado']['code']!r}"
        )
        assert updates["elemento_confirmado"]["name"] == "Placa solar conectada a regulador existente del vehículo"

        # element_codes también debe actualizarse
        assert updates.get("element_codes") == ["PLACA_SOLAR_SIMPLE"], (
            f"element_codes incorrecto: {updates.get('element_codes')!r}"
        )

    def test_single_selection_high_confidence(self):
        """Caso 1 variante: confidence 1.0 también funciona correctamente."""
        tool_result = {
            "selected_variant": "SUSPENSION_DEL",
            "confidence": 1.0,
            "name": "Suspensión delantera",
            "variant_code": "DELANTERA",
            "instrucciones": "...",
        }

        updates = self._call_extract("seleccionar_variante_por_respuesta", tool_result)

        assert updates["pending_variants"] == []
        assert updates["elemento_confirmado"]["code"] == "SUSPENSION_DEL"
        assert updates.get("element_codes") == ["SUSPENSION_DEL"]

    # ─────────────────────────────────────────────────────────────────────────
    # Caso 2: Error de matching NO limpia pending_variants
    # ─────────────────────────────────────────────────────────────────────────

    def test_error_does_not_clear_pending_variants(self):
        """
        Caso 2: La tool retorna error → pending_variants NO se modifica.

        Si la tool no pudo determinar la variante, pending_variants debe
        mantenerse intacto para que calcular_tarifa siga bloqueado.
        """
        tool_result = {
            "error": "No se pudo determinar la variante con certeza.",
            "sugerencia": "Pregunta al usuario de forma más específica.",
            "opciones_disponibles": [
                "- Placa solar conectada a regulador existente del vehículo",
                "- Placa solar con regulador propio incluido",
            ],
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
        )

        # pending_variants NO debe estar en updates (no se toca)
        assert "pending_variants" not in updates, (
            "pending_variants NO debe modificarse cuando hay error de matching"
        )
        # elemento_confirmado tampoco
        assert "elemento_confirmado" not in updates, (
            "elemento_confirmado NO debe modificarse con error"
        )
        assert "element_codes" not in updates, (
            "element_codes NO debe modificarse con error"
        )

    def test_error_with_partial_selection_does_not_clear(self):
        """
        Caso 2 variante: Aunque haya selected_variant, si hay error, no se limpia.

        Garantizamos que `has_selection and not data.get("error")` es la condición correcta.
        """
        # Escenario hipotético: error + selected_variant (baja confianza)
        tool_result = {
            "error": "Confianza demasiado baja",
            "selected_variant": "PLACA_SOLAR_SIMPLE",  # presente pero con error
            "confidence": 0.3,
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
        )

        # Con error, pending_variants NO debe limpiarse
        assert "pending_variants" not in updates, (
            "Con error presente, pending_variants NO debe modificarse aunque haya selected_variant"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Caso 3: Multi-selección limpia pending_variants y actualiza element_codes
    # ─────────────────────────────────────────────────────────────────────────

    def test_multi_select_clears_pending_and_sets_codes(self):
        """
        Caso 3: La tool retorna selected_variants (multi-select).

        Verifica:
        - pending_variants = []
        - element_codes = lista completa
        - elemento_confirmado apunta al primero de la lista
        """
        tool_result = {
            "selected_variants": ["INTERMITENTES_DEL", "INTERMITENTES_TRAS"],
            "mode": "multi_select",
            "matched_keyword": "ambos",
            "names": [
                "Intermitentes delanteros",
                "Intermitentes traseros",
            ],
            "instrucciones": "Usa todos los códigos en calcular_tarifa_con_elementos.",
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
            tool_args={
                "categoria_vehiculo": "motos-part",
                "codigo_elemento_base": "INTERMITENTES",
                "respuesta_usuario": "ambos",
            },
        )

        # pending_variants debe limpiarse
        assert updates.get("pending_variants") == [], (
            f"pending_variants debe ser [] en multi-select pero es {updates.get('pending_variants')!r}"
        )

        # element_codes debe contener TODOS los códigos seleccionados
        assert updates.get("element_codes") == ["INTERMITENTES_DEL", "INTERMITENTES_TRAS"], (
            f"element_codes incorrecto: {updates.get('element_codes')!r}"
        )

        # elemento_confirmado apunta al primero
        assert updates.get("elemento_confirmado") == {
            "code": "INTERMITENTES_DEL",
            "name": "Intermitentes delanteros",
        }, f"elemento_confirmado incorrecto: {updates.get('elemento_confirmado')!r}"

    def test_multi_select_without_names_uses_codes_as_names(self):
        """
        Caso 3 variante: Multi-select sin campo names → usa códigos como fallback.
        """
        tool_result = {
            "selected_variants": ["BOLA_CON_MMR", "BOLA_SIN_MMR"],
            "mode": "multi_select",
            # Sin "names"
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
        )

        assert updates.get("pending_variants") == []
        assert updates.get("element_codes") == ["BOLA_CON_MMR", "BOLA_SIN_MMR"]
        # elemento_confirmado debe tener el primer código como name también
        assert updates["elemento_confirmado"]["code"] == "BOLA_CON_MMR"
        assert updates["elemento_confirmado"]["name"] == "BOLA_CON_MMR"

    # ─────────────────────────────────────────────────────────────────────────
    # Caso 4: Flujo completo sin bloqueo (integración mínima)
    # ─────────────────────────────────────────────────────────────────────────

    def test_full_flow_no_blocking(self):
        """
        Caso 4: Flujo completo en 3 pasos:
            1. identificar_y_resolver_elementos → populate pending_variants
            2. seleccionar_variante_por_respuesta → empty pending_variants
            3. calcular_tarifa_con_elementos no está bloqueado (pending_variants=[])

        Simula la lógica que ejecuta _process_message internamente a través de
        _extract_context_from_tool, sin necesitar BD ni Redis.
        """
        # ── Paso 1: identificar_y_resolver_elementos retorna variantes pendientes ──
        identificar_result = {
            "elementos_listos": [],
            "elementos_con_variantes": [
                {
                    "codigo": "PLACA_SOLAR",
                    "nombre": "Placa solar",
                }
            ],
            "preguntas_variantes": [
                {
                    "codigo_base": "PLACA_SOLAR",
                    "pregunta": "¿La placa solar incluye su propio regulador o usa el del vehículo?",
                    "opciones": ["Con regulador propio", "Regulador existente del vehículo"],
                }
            ],
        }

        context = {}  # Simula mode_context acumulado

        updates_1 = self._call_extract(
            tool_name="identificar_y_resolver_elementos",
            tool_result=identificar_result,
            tool_args={"categoria_vehiculo": "motos-part"},
        )
        context.update(updates_1)

        # Verificar que pending_variants se populó
        assert len(context.get("pending_variants", [])) > 0, (
            "Paso 1: pending_variants debe popularse con las variantes pendientes"
        )
        assert context.get("elemento_confirmado") is None, (
            "Paso 1: elemento_confirmado debe ser None cuando hay variantes"
        )

        # ── Paso 2: seleccionar_variante_por_respuesta resuelve la variante ──
        seleccionar_result = {
            "selected_variant": "PLACA_SOLAR_SIMPLE",
            "confidence": 0.9,
            "name": "Placa solar conectada a regulador existente del vehículo",
            "variant_code": "REGULADOR_EXISTENTE",
            "instrucciones": "...",
        }

        updates_2 = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=seleccionar_result,
            tool_args={
                "categoria_vehiculo": "motos-part",
                "codigo_elemento_base": "PLACA_SOLAR",
                "respuesta_usuario": "la que usa el regulador del vehículo",
            },
        )
        context.update(updates_2)

        # Verificar que pending_variants se vació (desbloquea calcular_tarifa)
        assert context.get("pending_variants") == [], (
            "Paso 2: pending_variants debe vaciarse tras seleccionar variante"
        )
        assert context.get("elemento_confirmado") is not None, (
            "Paso 2: elemento_confirmado debe actualizarse"
        )
        assert context["elemento_confirmado"]["code"] == "PLACA_SOLAR_SIMPLE"

        # ── Paso 3: Verificar que calcular_tarifa NO estaría bloqueado ──
        # En producción, calcular_tarifa_con_elementos lee state.get("mode_context", {})
        # y comprueba pending_variants. Aquí simulamos esa misma lógica.
        pending_after_resolution = context.get("pending_variants", [])
        assert pending_after_resolution == [], (
            "Paso 3: pending_variants está vacío → calcular_tarifa NO estaría bloqueado"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Compatibilidad hacia atrás: campos legacy (success / codigo)
    # ─────────────────────────────────────────────────────────────────────────

    def test_legacy_success_field_still_works(self):
        """
        Compatibilidad: Si una versión futura o alternativa de la tool retorna
        success=True (forward-compat), el fix también debe funcionar.
        """
        tool_result = {
            "success": True,
            "codigo": "ESCAPE_MECANICO",
            "nombre": "Escape mecánico",
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
        )

        assert updates.get("pending_variants") == [], (
            "Compatibilidad legacy: success=True debe limpiar pending_variants"
        )

    def test_legacy_codigo_field_still_works(self):
        """
        Compatibilidad: Si una versión legada retorna solo 'codigo' (sin 'success'),
        el fix también debe funcionar.
        """
        tool_result = {
            "codigo": "MANILLAR_ALTO",
            "nombre": "Manillar alto",
        }

        updates = self._call_extract(
            tool_name="seleccionar_variante_por_respuesta",
            tool_result=tool_result,
        )

        assert updates.get("pending_variants") == [], (
            "Compatibilidad legacy: 'codigo' solo debe limpiar pending_variants"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # No regresión: otras tools no se ven afectadas
    # ─────────────────────────────────────────────────────────────────────────

    def test_other_tools_unaffected(self):
        """
        No regresión: el cambio no afecta el procesamiento de otras tools.
        identificar_y_resolver_elementos sin variantes sigue funcionando.
        """
        tool_result = {
            "elementos_listos": [{"codigo": "ESCAPE", "nombre": "Escape"}],
            "elementos_con_variantes": [],
            "preguntas_variantes": [],
        }

        updates = self._call_extract(
            tool_name="identificar_y_resolver_elementos",
            tool_result=tool_result,
            tool_args={"categoria_vehiculo": "motos-part"},
        )

        # Sin variantes → pending_variants vacío, element_codes con el código
        assert updates.get("pending_variants") == []
        assert updates.get("element_codes") == ["ESCAPE"]
        assert updates.get("categoria_slug") == "motos-part"

    def test_calcular_tarifa_context_extraction(self):
        """
        No regresión: calcular_tarifa_con_elementos sigue extrayendo tarifa_calculada.
        """
        tool_result = {
            "texto": "TARIFA RECOMENDADA: Tier 1\nPrecio: 350 EUR",
            "datos": {
                "tier_id": "uuid-1",
                "tier_name": "Tier 1",
                "price": 350.0,
                "elements": ["Escape"],
                "element_codes": ["ESCAPE"],
                "warnings": [],
            },
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }

        updates = self._call_extract(
            tool_name="calcular_tarifa_con_elementos",
            tool_result=tool_result,
        )

        assert "tarifa_calculada" in updates, "tarifa_calculada debe extraerse"
        assert updates["tarifa_calculada"]["datos"]["price"] == 350.0
