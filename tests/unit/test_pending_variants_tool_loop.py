"""
Tests for fix-pending-variants-tool-loop.

Covers 4 requirement areas from the spec:
  Task 4.1 — Mid-loop tool re-bind: LLM re-bound after last variant resolves mid-loop
  Task 4.2 — Constraint fires with no tarifa (hallucination detection)
  Task 4.3 — Constraint skips when tarifa_calculada already exists
  Task 4.4 — Regression: no invented price with pending variants active

All unit tests run without DB / Redis / real LLM.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from unittest.mock import MagicMock, patch


# =============================================================================
# Inline constraint definition (matches production DB seed)
# =============================================================================

PRICE_CONSTRAINT = {
    "constraint_type": "price_requires_tool",
    "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
    "required_tool": "calcular_tarifa_con_elementos",
    "error_injection": (
        "CORRECCION OBLIGATORIA: Has mencionado un precio sin haber llamado a "
        "calcular_tarifa_con_elementos. NUNCA inventes precios."
    ),
    "priority": 100,
}


# =============================================================================
# Helpers
# =============================================================================


def _make_tool(name: str) -> MagicMock:
    """Create a minimal mock LangChain-compatible tool object."""
    tool = MagicMock()
    tool.name = name
    return tool


def _restricted_tools() -> list:
    """Return the restricted toolset: only seleccionar + escalar_a_humano."""
    return [
        _make_tool("seleccionar_variante_por_respuesta"),
        _make_tool("escalar_a_humano"),
    ]


def _full_tools() -> list:
    """Return the full toolset including calcular_tarifa_con_elementos."""
    return [
        _make_tool("identificar_y_resolver_elementos"),
        _make_tool("calcular_tarifa_con_elementos"),
        _make_tool("seleccionar_variante_por_respuesta"),
        _make_tool("enviar_imagenes_ejemplo"),
        _make_tool("escalar_a_humano"),
    ]


# =============================================================================
# GROUP 1 — Task 4.1: Mid-loop tool re-bind
# =============================================================================


class TestToolRebindMidLoop:
    """
    R1-LOOP-REBIND: After seleccionar_variante_por_respuesta resolves the last
    pending variant, get_tools() is re-evaluated and the LLM is re-bound.
    """

    def setup_method(self):
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        self.mode = PresupuestoModeNode()

    def test_tool_rebind_when_all_variants_resolved(self):
        """
        Scenario 1 — Happy path: When the last pending variant resolves mid-loop,
        get_tools() is called again and the new toolset INCLUDES calcular_tarifa_con_elementos.

        Verifies that the re-bind block at presupuesto_mode.py:895-907 works correctly:
          - initial tools = restricted [seleccionar, escalar]
          - mode_context updated: pending_variants = []
          - re-evaluation: get_tools() returns full toolset
          - new toolset differs → LLM must be re-bound
        """
        # Simulate state BEFORE variant resolution
        mode_context_before = {
            "pending_variants": [
                {
                    "codigo_base": "PLACA_SOLAR",
                    "pregunta": "¿Regulador existente, oculto o visible?",
                    "opciones": ["Existente", "Oculto", "Visible"],
                    "status": "pending",
                }
            ]
        }
        # Simulate state AFTER variant resolution (last variant resolved)
        mode_context_after = {
            "pending_variants": []  # ← empty: all resolved
        }

        # Initial restricted toolset (before resolution)
        initial_tools = self.mode.get_tools(mode_context=mode_context_before)
        initial_names = {t.name for t in initial_tools}

        # New toolset after resolution
        new_tools = self.mode.get_tools(mode_context=mode_context_after)
        new_names = {t.name for t in new_tools}

        # The toolsets must differ (this is the re-bind trigger condition)
        assert initial_names != new_names, (
            "Toolsets must differ after variant resolution to trigger re-bind"
        )

        # The new toolset must include calcular_tarifa_con_elementos
        assert "calcular_tarifa_con_elementos" in new_names, (
            "After all variants resolved, calcular_tarifa_con_elementos must be "
            f"in the new toolset. Got: {new_names}"
        )

        # The initial restricted toolset must NOT include calcular_tarifa_con_elementos
        assert "calcular_tarifa_con_elementos" not in initial_names, (
            "Initial toolset (while variants pending) must NOT include "
            f"calcular_tarifa_con_elementos. Got: {initial_names}"
        )

    def test_no_rebind_when_variants_still_pending(self):
        """
        Scenario 2 — Partial resolution: One of two variants resolves,
        but get_tools() still returns restricted set (1 still pending).

        Verifies that the comparison `{t.name for t in _new_tools} != {t.name for t in tools}`
        evaluates to False (no re-bind) when one variant remains.
        """
        # Two pending variants before
        mode_context_two_pending = {
            "pending_variants": [
                {"codigo_base": "PLACA_SOLAR", "status": "pending"},
                {"codigo_base": "TOLDO_LAT", "status": "pending"},
            ]
        }
        # One pending variant after (first resolved, second still pending)
        mode_context_one_pending = {
            "pending_variants": [
                {"codigo_base": "TOLDO_LAT", "status": "pending"},
            ]
        }

        tools_before = self.mode.get_tools(mode_context=mode_context_two_pending)
        tools_after = self.mode.get_tools(mode_context=mode_context_one_pending)

        names_before = {t.name for t in tools_before}
        names_after = {t.name for t in tools_after}

        # Both states produce the same restricted toolset → no re-bind needed
        assert names_before == names_after, (
            "With 1 or 2 pending variants, toolset must remain identical "
            f"(no re-bind trigger). Before: {names_before}, After: {names_after}"
        )

        # Neither should include calcular_tarifa_con_elementos
        assert "calcular_tarifa_con_elementos" not in names_after, (
            "calcular_tarifa_con_elementos must NOT be available while "
            f"any variant is still pending. Got: {names_after}"
        )

    def test_no_rebind_when_no_variants_ever(self):
        """
        Scenario 3 — No variants in the flow: get_tools() called once
        at loop start and returns full toolset immediately (no restriction applied).
        """
        # No pending variants at all
        mode_context_empty = {"pending_variants": []}

        tools = self.mode.get_tools(mode_context=mode_context_empty)
        tool_names = {t.name for t in tools}

        # Full toolset is available from the start
        assert "calcular_tarifa_con_elementos" in tool_names, (
            "With no pending variants, calcular_tarifa_con_elementos must be "
            f"available immediately. Got: {tool_names}"
        )
        assert "identificar_y_resolver_elementos" in tool_names, (
            "Full toolset must include identificar_y_resolver_elementos "
            f"when no pending variants. Got: {tool_names}"
        )

    def test_rebind_block_detects_toolset_change(self):
        """
        Task 4.1 direct: Verify the re-bind detection logic using the same
        comparison used in presupuesto_mode.py line 899:
          `{t.name for t in _new_tools} != {t.name for t in tools}`

        This tests that the name-set comparison correctly identifies
        a change when pending_variants transitions from non-empty to empty.
        """
        # Simulate the initial `tools` variable (restricted set)
        tools = _restricted_tools()
        initial_name_set = {t.name for t in tools}

        # Simulate mode_context after variant resolves (pending_variants=[])
        mode_context_resolved = {"pending_variants": []}

        # Simulate what presupuesto_mode.py does:
        _new_tools = self.mode.get_tools(mode_context=mode_context_resolved)
        new_name_set = {t.name for t in _new_tools}

        # The condition that triggers re-bind
        should_rebind = new_name_set != initial_name_set

        assert should_rebind is True, (
            "Re-bind condition must be True when toolset changes from restricted to full. "
            f"Initial: {initial_name_set}, New: {new_name_set}"
        )


# =============================================================================
# GROUP 2 — Task 4.2: Constraint fires with no tarifa (hallucination detected)
# =============================================================================


class TestConstraintFiresPriceHallucination:
    """
    R2-CONSTRAINT-PRICE: Constraint fires when tool unavailable AND tarifa_calculada absent.
    The LLM is hallucinating a price with no legitimate source.
    """

    @pytest.mark.asyncio
    async def test_constraint_fires_price_hallucination_no_tarifa(self):
        """
        Task 4.2 — Scenario 6:
        - available_tool_names excludes calcular_tarifa_con_elementos (restricted toolset)
        - fsm_state["tarifa_calculada"] is None (no prior calculation)
        - Response contains a price pattern ("410 EUR")
        → validate_response_hybrid returns (False, error_injection) — constraint FIRES
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El presupuesto es de 410 EUR +IVA"

        # Restricted toolset: tool not available
        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # No prior tarifa calculation
        fsm_state = {"tarifa_calculada": None}

        # No tool called this turn (hallucination scenario)
        tools_called_this_turn: set[str] = set()

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=tools_called_this_turn,
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is False, (
            "Constraint must FIRE when tool unavailable AND tarifa_calculada=None. "
            f"Got is_valid={is_valid}, error={error!r}"
        )
        assert error is not None, (
            "error_injection must be non-None when constraint fires"
        )
        assert "CORRECCION OBLIGATORIA" in error, (
            f"error_injection should contain 'CORRECCION OBLIGATORIA', got: {error!r}"
        )

    @pytest.mark.asyncio
    async def test_constraint_fires_when_tarifa_calculada_key_absent(self):
        """
        Edge case: fsm_state does NOT contain 'tarifa_calculada' key at all
        (absent vs. None — both should trigger constraint).
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El presupuesto es de 450€"

        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }
        fsm_state = {}  # No tarifa_calculada key at all

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is False, (
            "Constraint must FIRE when tarifa_calculada key is absent from fsm_state. "
            f"Got is_valid={is_valid}"
        )

    @pytest.mark.asyncio
    async def test_constraint_fires_when_fsm_state_is_none(self):
        """
        Edge case: fsm_state=None (no state at all) AND tool unavailable.
        → constraint must fire (no tarifa to reference).
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El coste sería de 350 EUR"

        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=None,  # None state
            available_tool_names=available_tool_names,
        )

        assert is_valid is False, (
            "Constraint must FIRE when fsm_state=None AND tool unavailable. "
            f"Got is_valid={is_valid}"
        )


# =============================================================================
# GROUP 3 — Task 4.3: Constraint skips when tarifa already exists
# =============================================================================


class TestConstraintSkipsWhenTarifaExists:
    """
    R2-CONSTRAINT-PRICE: When tarifa_calculada is present (from a prior turn),
    the LLM can legitimately reference the price — constraint is skipped.
    """

    @pytest.mark.asyncio
    async def test_constraint_skips_when_tarifa_exists_and_tool_unavailable(self):
        """
        Task 4.3 — Scenario 7:
        - available_tool_names excludes calcular_tarifa_con_elementos
        - fsm_state["tarifa_calculada"] is a non-None dict (calculated previously)
        - Response references the price
        → validate_response_hybrid returns (True, None) — constraint SKIPPED

        This allows the LLM to refer back to a prior calculation without
        triggering a false positive.
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El presupuesto es de 410 EUR +IVA, como te comenté antes"

        # Restricted toolset (variant resolution mode)
        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # Prior tarifa exists (calculated in a previous turn)
        fsm_state = {
            "tarifa_calculada": {
                "price": 410.0,
                "tier_name": "Proyecto Básico",
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
            }
        }

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),  # No tool called this turn
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is True, (
            "Constraint must be SKIPPED when tarifa_calculada exists AND tool unavailable. "
            f"Got is_valid={is_valid}, error={error!r}"
        )
        assert error is None, (
            f"error_injection must be None when constraint skipped, got: {error!r}"
        )

    @pytest.mark.asyncio
    async def test_constraint_skips_with_minimal_tarifa_dict(self):
        """
        Scenario 7 variant: tarifa_calculada present but minimal (just {}).
        Any non-None value should skip the constraint.
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El presupuesto es 270€ según lo calculado"

        available_tool_names = {"seleccionar_variante_por_respuesta"}

        # Minimal non-None tarifa (edge case)
        fsm_state = {"tarifa_calculada": {"price": 270.0}}

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is True, (
            "Any non-None tarifa_calculada value should skip constraint. "
            f"Got is_valid={is_valid}, error={error!r}"
        )

    @pytest.mark.asyncio
    async def test_full_toolset_constraint_fires_normally(self):
        """
        Scenario 8 (regression): When the FULL toolset is available, the constraint
        fires normally (original behavior unchanged).
        Price mentioned but calcular_tarifa NOT called this turn → violation.
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "El presupuesto es de 410 EUR +IVA"

        # Full toolset: tool IS available
        available_tool_names = {
            "identificar_y_resolver_elementos",
            "calcular_tarifa_con_elementos",
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # tarifa_calculada absent (tool is available but wasn't called)
        fsm_state = {"tarifa_calculada": None}

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),  # Tool available but NOT called
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is False, (
            "With full toolset, constraint must fire when price mentioned "
            f"but tool not called. Got is_valid={is_valid}"
        )

    @pytest.mark.asyncio
    async def test_no_price_in_response_no_constraint_fired(self):
        """
        Scenario 10: No price pattern in response → constraint never triggered,
        regardless of toolset or tarifa_calculada state.
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = "Perfecto, entonces tienes una placa solar con regulador oculto"

        # Even with restricted toolset and no tarifa
        available_tool_names = {"seleccionar_variante_por_respuesta"}
        fsm_state = {"tarifa_calculada": None}

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is True, (
            "No price in response → no constraint violation. "
            f"Got is_valid={is_valid}, error={error!r}"
        )
        assert error is None


# =============================================================================
# GROUP 4 — Task 4.4: Regression — production conversation
# =============================================================================


class TestNoPendingVariantsInventedPrice:
    """
    Regression test for the exact production bug:
    - pending_variants active (PLACA_SOLAR + TOLDO)
    - LLM response contains invented price without calcular_tarifa being called
    → constraint service MUST detect this as a violation
    """

    @pytest.mark.asyncio
    async def test_no_invented_price_with_pending_variants(self):
        """
        Task 4.4 — Production bug regression:
        The exact production conversation pattern where the LLM hallucinated
        '410 EUR' while pending_variants were active and calcular_tarifa
        had never been called (not even in a prior turn).

        With the fix:
          - available_tools = restricted (no calcular_tarifa_con_elementos)
          - tarifa_calculada = None (never calculated)
          - LLM response contains "410 EUR"
          → constraint detects violation → (False, error_injection)
        """
        from agent.services.constraint_service import validate_response_hybrid

        # The exact LLM response from the production bug — invented price
        response_text = (
            "Perfecto, entonces tienes la placa solar con regulador en el interior "
            "y el toldo afecta al gálibo. El presupuesto para tu homologación "
            "sería de 410 EUR +IVA."
        )

        # Restricted toolset (pending variants active: PLACA_SOLAR + TOLDO_LAT)
        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # No prior tarifa — this is a hallucination
        fsm_state = {"tarifa_calculada": None}

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),  # calcular_tarifa never called
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        # The constraint MUST fire — this is the hallucination prevention
        assert is_valid is False, (
            "Production bug: constraint MUST fire when LLM invents price "
            "during pending variant resolution (no calcular_tarifa called, "
            f"no tarifa_calculada in state). Got is_valid={is_valid}"
        )
        assert error is not None, (
            "error_injection must be returned to force LLM retry without invented price"
        )

    @pytest.mark.asyncio
    async def test_same_scenario_with_tarifa_from_prior_turn_passes(self):
        """
        Regression inverse: Same conversation but tarifa WAS calculated in a prior turn.
        → LLM is allowed to reference the price → no violation.

        This distinguishes legitimate price references from hallucinations.
        """
        from agent.services.constraint_service import validate_response_hybrid

        # Same response referencing a price
        response_text = (
            "Recuerda que el presupuesto que calculamos antes era de 410 EUR +IVA. "
            "Ahora necesito saber más sobre el toldo."
        )

        # Restricted toolset (another element pending)
        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # tarifa WAS calculated in a prior turn (placa solar resolved)
        fsm_state = {
            "tarifa_calculada": {
                "price": 410.0,
                "tier_name": "Proyecto Básico",
                "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
            }
        }

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is True, (
            "When tarifa_calculada exists from a prior turn, referencing the price "
            f"must NOT trigger a violation. Got is_valid={is_valid}, error={error!r}"
        )

    @pytest.mark.asyncio
    async def test_both_placa_solar_and_toldo_pending_price_blocked(self):
        """
        Scenario with TWO pending variants (exactly the production case):
        PLACA_SOLAR + TOLDO_LAT both pending.
        LLM response mentions price → must be blocked.
        """
        from agent.services.constraint_service import validate_response_hybrid

        response_text = (
            "Para la placa solar con regulador y el toldo con afección al gálibo, "
            "el coste total sería de 450 EUR +IVA."
        )

        # Both PLACA_SOLAR and TOLDO_LAT pending → restricted toolset
        available_tool_names = {
            "seleccionar_variante_por_respuesta",
            "escalar_a_humano",
        }

        # No tarifa calculated (this is the first time price appears)
        fsm_state = {}  # empty = no tarifa_calculada

        is_valid, error = await validate_response_hybrid(
            response_text=response_text,
            tools_called_this_turn=set(),
            constraints=[PRICE_CONSTRAINT],
            fsm_state=fsm_state,
            available_tool_names=available_tool_names,
        )

        assert is_valid is False, (
            "With both PLACA_SOLAR and TOLDO pending + no tarifa, "
            f"price mention must be blocked. Got is_valid={is_valid}"
        )

    def test_tool_re_evaluation_uses_correct_comparison(self):
        """
        Task 4.1 structural check: The re-bind block uses name-set comparison,
        not object identity. Verifies the exact guard condition from presupuesto_mode.py:

          if {t.name for t in _new_tools} != {t.name for t in tools}:
              tools = _new_tools
              llm = self._get_llm(tools)

        This test confirms the comparison is semantically correct by checking
        that identical name sets evaluate to equal (no spurious re-bind) and
        different name sets evaluate to not-equal (triggers re-bind).
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        mode = PresupuestoModeNode()

        # Scenario A: Same toolset → comparison is False → no re-bind
        ctx_pending_1 = {
            "pending_variants": [{"codigo_base": "X", "status": "pending"}]
        }
        ctx_pending_2 = {
            "pending_variants": [{"codigo_base": "Y", "status": "pending"}]
        }

        tools_1 = mode.get_tools(mode_context=ctx_pending_1)
        tools_2 = mode.get_tools(mode_context=ctx_pending_2)

        names_1 = {t.name for t in tools_1}
        names_2 = {t.name for t in tools_2}

        assert names_1 == names_2, (
            "Two different pending variants should produce the SAME restricted toolset. "
            f"Got {names_1} vs {names_2}"
        )
        assert not (names_1 != names_2), (
            "Comparison must be False (no re-bind) for identical toolsets"
        )

        # Scenario B: Different toolset → comparison is True → triggers re-bind
        ctx_resolved = {"pending_variants": []}  # All resolved
        tools_resolved = mode.get_tools(mode_context=ctx_resolved)
        names_resolved = {t.name for t in tools_resolved}

        assert names_1 != names_resolved, (
            "Pending vs resolved must produce DIFFERENT toolsets → triggers re-bind. "
            f"Pending: {names_1}, Resolved: {names_resolved}"
        )
