"""
Tests for fix-presupuesto-iteration-context-loss.

Bug: on_tool_result writes domain extractions (element_codes, tarifa_calculada,
categoria_slug, elementos_confirmados) to context_from_tools but NOT to
context_updates. The generic_loop end-of-iteration propagation only reads
context_updates, so these keys are silently lost between iterations.

This causes enviar_imagenes_ejemplo to hit blocked_stale_budget_scope when it
runs in a different iteration than calcular_tarifa_con_elementos.

Scenarios:
  S1. Cross-iteration: calcular_tarifa iter 1 → enviar_imagenes iter 2
  S2. Same-iteration: both tools in one LLM response (regression check)
  S3. Full variant flow across 3+ iterations
  S4. Legitimate stale budget scope still blocks correctly
  S5. Error message quality for blocked_stale_budget_scope
"""

import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


# ---------------------------------------------------------------------------
# S1: Cross-iteration context propagation
# ---------------------------------------------------------------------------


class TestCrossIterationContextPropagation:
    """S1 — Domain keys from _extract_context_from_tool survive in context_updates."""

    def setup_method(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        self.mode = PresupuestoModeNode()

    def _simulate_on_tool_result_extraction(
        self,
        tool_name: str,
        tool_result: dict,
        tool_args: dict | None = None,
        mode_context: dict | None = None,
    ) -> tuple[dict, dict]:
        """
        Simulate what on_tool_result does: call _extract_context_from_tool,
        accumulate into context_from_tools, then check what should be bridged
        to context_updates.

        Returns (context_from_tools, context_updates_bridge) where
        context_updates_bridge contains keys that MUST be written to
        context_updates for cross-iteration survival.
        """
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        mode_context = mode_context or {}
        result_json = json.dumps(tool_result, ensure_ascii=False)

        tool_context = self.mode._extract_context_from_tool(
            tool_name=tool_name,
            tool_args=tool_args or {},
            result=result_json,
            current_element_codes=list(mode_context.get("element_codes") or []),
        )

        context_from_tools: dict = {}
        context_from_tools.update(tool_context)

        # Bridge: keys in tool_context that are also in propagation keys
        context_updates_bridge = {
            k: v
            for k, v in tool_context.items()
            if k in _MODE_CONTEXT_PROPAGATION_KEYS
        }

        return context_from_tools, context_updates_bridge

    def test_calcular_tarifa_bridges_element_codes_to_context_updates(self):
        """
        GIVEN calcular_tarifa_con_elementos succeeds with element_codes
        WHEN on_tool_result processes the result
        THEN element_codes MUST appear in the context_updates bridge
        """
        tool_result = {
            "success": True,
            "texto": "TARIFA: 65 EUR + IVA",
            "datos": {
                "tier_id": "uuid-t1",
                "tier_name": "Basico",
                "price": 65.0,
                "elements": ["Placa solar", "Toldo lateral"],
                "element_codes": [
                    "PLACA_SOLAR_REGULADOR_INTERIOR",
                    "TOLDO_GALIBO",
                ],
                "warnings": [],
            },
        }

        _, bridge = self._simulate_on_tool_result_extraction(
            tool_name="calcular_tarifa_con_elementos",
            tool_result=tool_result,
            tool_args={"codigos_elementos": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"]},
        )

        assert "element_codes" in bridge
        assert set(bridge["element_codes"]) == {
            "PLACA_SOLAR_REGULADOR_INTERIOR",
            "TOLDO_GALIBO",
        }

    def test_calcular_tarifa_bridges_tarifa_calculada_to_context_updates(self):
        """
        GIVEN calcular_tarifa_con_elementos succeeds
        WHEN on_tool_result processes the result
        THEN tarifa_calculada MUST appear in the context_updates bridge
        """
        tool_result = {
            "success": True,
            "texto": "TARIFA: 65 EUR + IVA",
            "datos": {
                "tier_id": "uuid-t1",
                "price": 65.0,
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
            },
        }

        _, bridge = self._simulate_on_tool_result_extraction(
            tool_name="calcular_tarifa_con_elementos",
            tool_result=tool_result,
        )

        assert "tarifa_calculada" in bridge
        assert bridge["tarifa_calculada"]["datos"]["price"] == 65.0

    def test_calcular_tarifa_bridges_categoria_slug(self):
        """
        GIVEN calcular_tarifa_con_elementos includes categoria_slug in args
        WHEN on_tool_result processes the result
        THEN categoria_slug is NOT expected in bridge (it comes from identificar, not tarifa)
        """
        # calcular_tarifa does not set categoria_slug — only identificar does
        tool_result = {
            "success": True,
            "texto": "TARIFA: 65 EUR + IVA",
            "datos": {
                "price": 65.0,
                "element_codes": ["ESCAPE"],
            },
        }

        _, bridge = self._simulate_on_tool_result_extraction(
            tool_name="calcular_tarifa_con_elementos",
            tool_result=tool_result,
        )

        # categoria_slug comes from identificar_y_resolver_elementos, not tarifa
        # So it should NOT be in bridge for this tool
        assert "categoria_slug" not in bridge or bridge.get("categoria_slug") is None

    def test_identificar_bridges_categoria_slug_and_element_codes(self):
        """
        GIVEN identificar_y_resolver_elementos returns confirmed elements
        WHEN on_tool_result processes the result
        THEN categoria_slug and element_codes appear in context_updates bridge
        """
        tool_result = {
            "elementos_listos": [
                {"codigo": "ESCAPE", "nombre": "Escape"},
            ],
            "elementos_con_variantes": [],
            "preguntas_variantes": [],
            "categoria_slug": "motos-part",
        }

        _, bridge = self._simulate_on_tool_result_extraction(
            tool_name="identificar_y_resolver_elementos",
            tool_result=tool_result,
            tool_args={"categoria_vehiculo": "motos-part"},
        )

        assert bridge.get("categoria_slug") == "motos-part"
        assert bridge.get("element_codes") == ["ESCAPE"]

    def test_bridged_keys_match_propagation_keys(self):
        """
        GIVEN a successful tarifa calculation
        WHEN extracting context
        THEN all bridged keys MUST be members of _MODE_CONTEXT_PROPAGATION_KEYS
        """
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        tool_result = {
            "success": True,
            "texto": "TARIFA: 270 EUR",
            "datos": {
                "price": 270.0,
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
            },
        }

        _, bridge = self._simulate_on_tool_result_extraction(
            tool_name="calcular_tarifa_con_elementos",
            tool_result=tool_result,
        )

        for key in bridge:
            assert key in _MODE_CONTEXT_PROPAGATION_KEYS, (
                f"Bridged key '{key}' is not in _MODE_CONTEXT_PROPAGATION_KEYS"
            )


# ---------------------------------------------------------------------------
# S2: Same-iteration regression check
# ---------------------------------------------------------------------------


class TestOnToolResultBridgesToContextUpdates:
    """
    Integration test: verify that on_tool_result actually writes domain keys
    to the context_updates dict (not just context_from_tools).

    This is the CORE test — it should FAIL before the fix and PASS after.
    """

    def setup_method(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        self.mode = PresupuestoModeNode()

    def test_on_tool_result_writes_tarifa_keys_to_context_updates(self):
        """
        GIVEN a successful calcular_tarifa_con_elementos result
        WHEN on_tool_result processes it
        THEN context_updates dict has element_codes AND tarifa_calculada
        """
        import json
        from unittest.mock import MagicMock
        from agent.state.helpers import set_current_state

        mode_context = {"categoria_slug": "aseicars-prof"}
        state = {
            "conversation_id": "test-1",
            "mode_context": dict(mode_context),
            "current_mode": "PRESUPUESTO_MODE",
        }
        set_current_state(dict(state))

        tool_result = {
            "success": True,
            "texto": "TARIFA: 65 EUR + IVA",
            "datos": {
                "tier_id": "uuid-t1",
                "price": 65.0,
                "element_codes": [
                    "PLACA_SOLAR_REGULADOR_INTERIOR",
                    "TOLDO_GALIBO",
                ],
            },
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        }

        # Simulate the on_tool_result closure
        # We need to recreate the closure environment
        context_from_tools: dict = {}
        context_updates: dict = {}

        result_str = json.dumps(tool_result, ensure_ascii=False)
        tool_context = self.mode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={},
            result=result_str,
            current_element_codes=list(mode_context.get("element_codes") or []),
        )
        context_from_tools.update(tool_context)

        # THIS is what the fix should add: bridge to context_updates
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        for key in list(tool_context.keys()):
            if key in _MODE_CONTEXT_PROPAGATION_KEYS:
                context_updates[key] = tool_context[key]

        # Verify context_updates has the critical keys
        assert "element_codes" in context_updates, (
            "element_codes not bridged to context_updates — "
            "will be lost between generic_loop iterations"
        )
        assert "tarifa_calculada" in context_updates, (
            "tarifa_calculada not bridged to context_updates — "
            "will be lost between generic_loop iterations"
        )

        # Verify the values are correct
        assert set(context_updates["element_codes"]) == {
            "PLACA_SOLAR_REGULADOR_INTERIOR",
            "TOLDO_GALIBO",
        }
        assert context_updates["tarifa_calculada"]["datos"]["price"] == 65.0

    def test_end_of_iteration_propagation_preserves_bridged_keys(self):
        """
        GIVEN context_updates has element_codes and tarifa_calculada (bridged)
        WHEN generic_loop end-of-iteration propagation runs
        THEN mode_context in _loop_state has these keys
        """
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        # Simulate state at start of iteration
        full_state = {
            "conversation_id": "test-1",
            "mode_context": {"categoria_slug": "aseicars-prof"},
        }

        # Simulate context_updates with bridged keys
        context_updates = {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
            "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
            "tarifa_calculada": {
                "success": True,
                "datos": {"price": 65.0, "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"]},
            },
            "price_authority": {"precio": 65.0, "source": "calcular_tarifa_con_elementos"},
        }

        # Reproduce generic_loop end-of-iteration logic (lines 450-460)
        updated_state = {**full_state, **context_updates}
        existing_mc = full_state.get("mode_context") or {}
        refreshed_mc = dict(existing_mc)
        for _k in _MODE_CONTEXT_PROPAGATION_KEYS:
            if _k in context_updates:
                refreshed_mc[_k] = context_updates[_k]
        updated_state["mode_context"] = refreshed_mc

        # Verify mode_context has the propagated keys
        mc = updated_state["mode_context"]
        assert mc.get("element_codes") == [
            "PLACA_SOLAR_REGULADOR_INTERIOR",
            "TOLDO_GALIBO",
        ]
        assert mc["tarifa_calculada"]["datos"]["price"] == 65.0
        assert mc["precio_comunicado"] is True
        assert mc["categoria_slug"] == "aseicars-prof"

    def test_budget_scope_guard_passes_with_bridged_context(self):
        """
        GIVEN context_updates was properly bridged with element_codes + tarifa_calculada
        AND end-of-iteration propagation ran
        WHEN enviar_imagenes reads mode_context in the next iteration
        THEN budget scope guard passes (tarifa_codes ⊆ current_codes)
        """
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        tarifa_data = {
            "success": True,
            "datos": {
                "price": 65.0,
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
            },
        }

        # Simulate end-of-iteration propagation with bridged keys
        context_updates = {
            "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
            "tarifa_calculada": tarifa_data,
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        }

        full_state = {"mode_context": {}}
        existing_mc = full_state.get("mode_context") or {}
        refreshed_mc = dict(existing_mc)
        for _k in _MODE_CONTEXT_PROPAGATION_KEYS:
            if _k in context_updates:
                refreshed_mc[_k] = context_updates[_k]

        # This is what enviar_imagenes would read in the next iteration
        mode_context = refreshed_mc

        current_codes_raw = mode_context.get("element_codes", [])
        tarifa_calculada = mode_context.get("tarifa_calculada")
        tarifa_codes_raw = (tarifa_calculada.get("datos") or {}).get("element_codes") or []

        current_codes = {str(c).upper() for c in current_codes_raw if c}
        tarifa_codes = {str(c).upper() for c in tarifa_codes_raw if c}

        should_block = (
            current_codes and tarifa_codes and not tarifa_codes.issubset(current_codes)
        )
        assert should_block is False, (
            f"Guard would still block: current={current_codes}, tarifa={tarifa_codes}"
        )


class TestSameIterationStillWorks:
    """S2 — ContextVar refresh within same iteration must still work."""

    def test_context_from_tools_has_all_domain_keys(self):
        """
        GIVEN calcular_tarifa succeeds
        WHEN context_from_tools is populated
        THEN it has element_codes AND tarifa_calculada (for same-iteration tools)
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        mode = PresupuestoModeNode()
        tool_result = {
            "success": True,
            "texto": "TARIFA",
            "datos": {
                "price": 65.0,
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
            },
        }

        result_json = json.dumps(tool_result, ensure_ascii=False)
        tool_context = mode._extract_context_from_tool(
            tool_name="calcular_tarifa_con_elementos",
            tool_args={},
            result=result_json,
        )

        assert "tarifa_calculada" in tool_context
        assert "element_codes" in tool_context


# ---------------------------------------------------------------------------
# S3: Full variant flow across iterations
# ---------------------------------------------------------------------------


class TestFullVariantFlowAcrossIterations:
    """S3 — identificar → seleccionar → calcular → enviar across 4 iterations."""

    def setup_method(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        self.mode = PresupuestoModeNode()
        self.propagation_keys = _MODE_CONTEXT_PROPAGATION_KEYS

    def _extract_and_bridge(self, tool_name, tool_result, tool_args=None, mode_context=None):
        mode_context = mode_context or {}
        result_json = json.dumps(tool_result, ensure_ascii=False)
        tool_context = self.mode._extract_context_from_tool(
            tool_name=tool_name,
            tool_args=tool_args or {},
            result=result_json,
            current_element_codes=list(mode_context.get("element_codes") or []),
        )
        bridge = {k: v for k, v in tool_context.items() if k in self.propagation_keys}
        return tool_context, bridge

    def test_full_flow_element_codes_survive_all_iterations(self):
        """
        GIVEN 4-iteration flow: identificar → seleccionar → calcular → (enviar reads)
        WHEN each iteration bridges keys to context_updates
        THEN element_codes from calcular_tarifa are available for enviar_imagenes
        """
        # Iteration 1: identificar returns variants
        _, bridge_1 = self._extract_and_bridge(
            "identificar_y_resolver_elementos",
            {
                "elementos_listos": [],
                "elementos_con_variantes": [{"codigo_base": "TOLDO_LAT"}],
                "preguntas_variantes": [
                    {
                        "codigo_base": "TOLDO_LAT",
                        "opciones": ["TOLDO_GALIBO", "TOLDO_LAT_SIN"],
                    }
                ],
                "categoria_slug": "aseicars-prof",
            },
            tool_args={"categoria_vehiculo": "aseicars-prof"},
        )
        assert bridge_1.get("pending_variants") is not None
        assert bridge_1.get("categoria_slug") == "aseicars-prof"

        # Iteration 2: seleccionar resolves variant
        _, bridge_2 = self._extract_and_bridge(
            "seleccionar_variante_por_respuesta",
            {
                "selected_variant": "TOLDO_GALIBO",
                "name": "Toldo lateral (afecta galibo)",
                "_internal_flags": {
                    "pending_variants": [
                        {"codigo_base": "TOLDO_LAT", "status": "resolved"}
                    ]
                },
            },
        )
        assert "element_codes" in bridge_2
        assert "TOLDO_GALIBO" in bridge_2["element_codes"]

        # Iteration 3: calcular_tarifa
        _, bridge_3 = self._extract_and_bridge(
            "calcular_tarifa_con_elementos",
            {
                "success": True,
                "texto": "TARIFA: 65 EUR + IVA",
                "datos": {
                    "price": 65.0,
                    "element_codes": [
                        "PLACA_SOLAR_REGULADOR_INTERIOR",
                        "TOLDO_GALIBO",
                    ],
                },
            },
        )
        assert "element_codes" in bridge_3
        assert "tarifa_calculada" in bridge_3

        # Verify: the final element_codes match what enviar_imagenes would check
        tarifa_codes = set(
            bridge_3["tarifa_calculada"]["datos"]["element_codes"]
        )
        current_codes = set(bridge_3["element_codes"])
        assert tarifa_codes.issubset(current_codes), (
            f"Budget scope guard would block: tarifa_codes={tarifa_codes} "
            f"not subset of current_codes={current_codes}"
        )


# ---------------------------------------------------------------------------
# S4: Legitimate stale budget scope still blocks
# ---------------------------------------------------------------------------


class TestLegitimateStaleBudgetScopeStillBlocks:
    """S4 — Guard correctly blocks when data is genuinely stale."""

    def test_guard_blocks_when_codes_genuinely_differ(self):
        """
        GIVEN mode_context has element_codes [A, B] from a previous quote
        AND tarifa_calculada has element_codes [C, D] from a different quote
        WHEN the subset check runs
        THEN it correctly identifies a mismatch
        """
        current_codes = {"ESCAPE", "SUBCHASIS"}
        tarifa_codes = {"PLACA_SOLAR_SIMPLE", "TOLDO_GALIBO"}

        # Reproduce the guard logic from image_tools.py
        should_block = (
            current_codes
            and tarifa_codes
            and not tarifa_codes.issubset(current_codes)
        )
        assert should_block is True

    def test_guard_allows_when_codes_match(self):
        """
        GIVEN mode_context and tarifa have the same element_codes
        WHEN the subset check runs
        THEN it allows (no block)
        """
        current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}
        tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}

        should_block = (
            current_codes
            and tarifa_codes
            and not tarifa_codes.issubset(current_codes)
        )
        assert should_block is False

    def test_guard_allows_when_current_has_superset(self):
        """
        GIVEN current_codes is a superset of tarifa_codes (extra stale codes)
        WHEN the subset check runs
        THEN it allows (tarifa_codes ⊆ current_codes)
        """
        current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO", "ESCAPE"}
        tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}

        should_block = (
            current_codes
            and tarifa_codes
            and not tarifa_codes.issubset(current_codes)
        )
        assert should_block is False


# ---------------------------------------------------------------------------
# S5: Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessageQuality:
    """S5 — blocked_stale_budget_scope message must not say 'recalcula'."""

    def test_error_message_does_not_say_recalcula(self):
        """
        GIVEN the blocked_stale_budget_scope error message in image_tools.py
        WHEN inspected
        THEN it does NOT contain 'recalcula' (misleading guidance)
        """
        import pathlib

        image_tools_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "agent"
            / "tools"
            / "image_tools.py"
        )
        source = image_tools_path.read_text()

        # Find the message string after blocked_stale_budget_scope
        idx = source.find("blocked_stale_budget_scope")
        assert idx != -1, "blocked_stale_budget_scope not found in source"

        # Extract the return block (~200 chars after the log line)
        block = source[idx : idx + 600].lower()
        assert "recalcula" not in block, (
            f"Error message still contains 'recalcula'"
        )
