"""
Unit tests for actualizar_datos_expediente() vehicle data pre-population.

T5.1 — fix-conversation-ux-issues Phase 5.

Tests the T3.5 change: when datos_vehiculo is missing marca/modelo, the tool
pre-populates them from mode_context["vehiculo"] (set by identificar_tipo_vehiculo()
in PRESUPUESTO_MODE and preserved across the PRESUPUESTO → EXPEDIENTE transition).

Guard: only fills MISSING values — never overwrites explicitly provided ones.

Spec scenarios:
- S1: Pre-populate when marca and modelo are absent from datos_vehiculo
- S2: No-overwrite when marca and modelo are explicitly provided
- S3: No context vehiculo → no pre-population, no crash

Assertion strategy:
    The tool builds merged_vehicle from the (possibly pre-populated) datos_vehiculo
    dict, stores it in updates_for_fsm["vehicle_data"], and then calls
    update_case_fsm_state(fsm_state, updates_for_fsm).  We capture that second
    argument by replacing update_case_fsm_state with a MagicMock spy and
    inspecting mock.call_args.  This is reliable because update_case_fsm_state is
    a regular function (not a dunder), so MagicMock tracks its calls correctly.

    Why not assert on setattr(case, …)?
        Python's MagicMock does NOT auto-track dunder __setattr__ calls; the mock
        framework bypasses special methods for magic names.  Trying to inspect
        mock_case.__setattr__.call_args_list fails with AttributeError.

    Why not assert on the return value alone?
        The tool returns ``fsm_state_update: new_fsm_state``, which is whatever
        update_case_fsm_state() returns — a mocked value, not the real merged dict.
        Inspecting the spy's call args is more direct and regression-proof.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.state.helpers import set_current_state
import agent.tools.case_tools as case_tools_module

# Access the underlying coroutine from the LangChain @tool wrapper
actualizar_datos_expediente_func = case_tools_module.actualizar_datos_expediente.coroutine


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_fsm_state(case_id: str) -> dict:
    """Build a minimal FSM state that satisfies get_case_fsm_state() expectations."""
    return {
        "fsm": {
            "step": "collect_vehicle",
            "case_id": case_id,
            "personal_data": {},
            "vehicle_data": {},
        }
    }


def _build_session_mock(case_id: str) -> AsyncMock:
    """Return an AsyncMock session with a simple MagicMock case object."""
    mock_case = MagicMock()
    mock_case.user_id = None
    mock_case.updated_at = None

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(return_value=mock_case)
    mock_session.commit = AsyncMock()
    return mock_session


def _make_fsm_case_state(case_id: str) -> dict:
    return {
        "step": "collect_vehicle",
        "case_id": case_id,
        "personal_data": {},
        "vehicle_data": {},
    }


# ---------------------------------------------------------------------------
# S1 — Pre-population when marca/modelo are absent
# ---------------------------------------------------------------------------


class TestPrePopulateMarcaModeloFromContext:
    """S1: marca/modelo absent in datos_vehiculo → pre-populated from mode_context."""

    @pytest.mark.asyncio
    async def test_prepopulates_marca_and_modelo_when_missing(self):
        """
        Given:  datos_vehiculo = {matricula: "1234BCD", bastidor: "VIN123", anio: "2020"}
                mode_context   = {vehiculo: {marca: "Fiat", modelo: "Ducato"}}
        When:   actualizar_datos_expediente(datos_vehiculo=datos_vehiculo) is called
        Then:   The tool calls update_case_fsm_state with vehicle_data that contains
                marca="Fiat" and modelo="Ducato" (pre-populated from context).

        Regression: if the pre-population block (lines 1074-1095 in case_tools.py) is
        removed, merged_vehicle will NOT have marca/modelo and this test will fail.
        """
        case_id = str(uuid.uuid4())

        # State with vehiculo in mode_context (from presupuesto phase)
        mock_state = {
            "conversation_id": "test-conv-prepop",
            "user_id": str(uuid.uuid4()),
            "mode_context": {
                "vehiculo": {
                    "marca": "Fiat",
                    "modelo": "Ducato",
                }
            },
            "fsm_state": _make_fsm_state(case_id),
        }
        set_current_state(mock_state)

        # Minimal datos_vehiculo — marca and modelo deliberately absent
        datos_vehiculo = {
            "matricula": "1234BCD",
            "bastidor": "VIN12345678901234",
            "anio": "2020",
        }

        mock_fsm_case_state = _make_fsm_case_state(case_id)
        mock_session = _build_session_mock(case_id)

        # Spy on update_case_fsm_state to capture the updates_for_fsm dict
        spy_update_fsm = MagicMock(return_value={})

        with (
            patch("agent.tools.case_tools.get_case_fsm_state", return_value=mock_fsm_case_state),
            patch("agent.tools.case_tools._get_case_id_with_fallback", return_value=case_id),
            patch("agent.tools.case_tools.get_current_step") as mock_step,
            patch("agent.tools.case_tools.get_async_session", return_value=mock_session),
            patch("agent.tools.case_tools.update_case_fsm_state", spy_update_fsm),
            patch("agent.tools.case_tools.validate_vehicle_data", return_value=(False, [])),
            patch("agent.tools.case_tools.normalize_matricula", side_effect=lambda x: x),
        ):
            from agent.utils.fsm_compat import CollectionStep
            mock_step.return_value = CollectionStep.COLLECT_VEHICLE

            result = await actualizar_datos_expediente_func(
                datos_vehiculo=datos_vehiculo,
            )

        # Tool must succeed
        assert result.get("success") is True, (
            f"Expected success=True, got: {result}"
        )

        # update_case_fsm_state must have been called with vehicle_data
        assert spy_update_fsm.called, (
            "update_case_fsm_state must be called after processing datos_vehiculo"
        )

        # The second positional argument is the updates_for_fsm dict.
        # It must contain vehicle_data with the pre-populated marca and modelo.
        updates_for_fsm = spy_update_fsm.call_args[0][1]  # positional arg index 1
        vehicle_data = updates_for_fsm.get("vehicle_data", {})

        assert vehicle_data.get("marca") == "Fiat", (
            f"Expected vehicle_data['marca']='Fiat' (pre-populated from mode_context), "
            f"got: {vehicle_data}. "
            f"If this fails, the pre-population block in case_tools.py was removed or broken."
        )
        assert vehicle_data.get("modelo") == "Ducato", (
            f"Expected vehicle_data['modelo']='Ducato' (pre-populated from mode_context), "
            f"got: {vehicle_data}. "
            f"If this fails, the pre-population block in case_tools.py was removed or broken."
        )


# ---------------------------------------------------------------------------
# S2 — No-overwrite when marca/modelo are explicitly provided
# ---------------------------------------------------------------------------


class TestNoOverwriteExplicitMarcaModelo:
    """S2: explicit marca/modelo in datos_vehiculo → NOT overwritten by mode_context."""

    @pytest.mark.asyncio
    async def test_does_not_overwrite_explicit_marca_and_modelo(self):
        """
        Given:  datos_vehiculo = {marca: "Ford", modelo: "Transit", matricula: ..., bastidor: ..., anio: ...}
                mode_context   = {vehiculo: {marca: "Fiat", modelo: "Ducato"}}
        When:   actualizar_datos_expediente(datos_vehiculo=datos_vehiculo) is called
        Then:   vehicle_data in the FSM update has marca="Ford" and modelo="Transit"
                (context values "Fiat"/"Ducato" must NOT overwrite explicitly provided ones).

        Regression: if the guard ``if not datos_vehiculo.get(field)`` is removed from the
        pre-population block, context would overwrite explicit values and this test fails.
        """
        case_id = str(uuid.uuid4())

        # State with DIFFERENT vehiculo in mode_context
        mock_state = {
            "conversation_id": "test-conv-nooverwrite",
            "user_id": str(uuid.uuid4()),
            "mode_context": {
                "vehiculo": {
                    "marca": "Fiat",    # Different from explicit
                    "modelo": "Ducato", # Different from explicit
                }
            },
            "fsm_state": _make_fsm_state(case_id),
        }
        set_current_state(mock_state)

        # datos_vehiculo with explicit marca and modelo
        datos_vehiculo = {
            "marca": "Ford",
            "modelo": "Transit",
            "matricula": "5678EFG",
            "bastidor": "VIN98765432109876",
            "anio": "2021",
        }

        mock_fsm_case_state = _make_fsm_case_state(case_id)
        mock_session = _build_session_mock(case_id)

        # Spy on update_case_fsm_state
        spy_update_fsm = MagicMock(return_value={})

        with (
            patch("agent.tools.case_tools.get_case_fsm_state", return_value=mock_fsm_case_state),
            patch("agent.tools.case_tools._get_case_id_with_fallback", return_value=case_id),
            patch("agent.tools.case_tools.get_current_step") as mock_step,
            patch("agent.tools.case_tools.get_async_session", return_value=mock_session),
            patch("agent.tools.case_tools.update_case_fsm_state", spy_update_fsm),
            patch("agent.tools.case_tools.validate_vehicle_data", return_value=(True, [])),
            patch("agent.tools.case_tools._transition_with_db_sync", new_callable=AsyncMock, return_value={}),
            patch("agent.tools.case_tools.normalize_matricula", side_effect=lambda x: x),
        ):
            from agent.utils.fsm_compat import CollectionStep
            mock_step.return_value = CollectionStep.COLLECT_VEHICLE

            result = await actualizar_datos_expediente_func(
                datos_vehiculo=datos_vehiculo,
            )

        # Tool must succeed
        assert result.get("success") is True, (
            f"Expected success=True, got: {result}"
        )

        # update_case_fsm_state must have been called
        assert spy_update_fsm.called, (
            "update_case_fsm_state must be called after processing datos_vehiculo"
        )

        updates_for_fsm = spy_update_fsm.call_args[0][1]
        vehicle_data = updates_for_fsm.get("vehicle_data", {})

        assert vehicle_data.get("marca") == "Ford", (
            f"Expected vehicle_data['marca']='Ford' (explicit value must be preserved), "
            f"got: {vehicle_data}. "
            f"Context value 'Fiat' must NOT overwrite explicitly provided marca."
        )
        assert vehicle_data.get("modelo") == "Transit", (
            f"Expected vehicle_data['modelo']='Transit' (explicit value must be preserved), "
            f"got: {vehicle_data}. "
            f"Context value 'Ducato' must NOT overwrite explicitly provided modelo."
        )


# ---------------------------------------------------------------------------
# S3 — No context vehiculo → no pre-population, no crash
# ---------------------------------------------------------------------------


class TestNoContextVehiculo:
    """S3: no vehiculo in mode_context → tool works normally (no crash, no pre-population)."""

    @pytest.mark.asyncio
    async def test_no_vehiculo_in_context_does_not_crash(self):
        """
        Given:  datos_vehiculo = {matricula: "1234BCD", bastidor: "VIN123", anio: "2020"}
                mode_context   = {}  (no vehiculo key)
        When:   actualizar_datos_expediente() is called
        Then:   Tool succeeds without crashing; vehicle_data has no marca/modelo
                (nothing was pre-populated from context).

        Regression: if the pre-population block crashes when mode_context has no
        "vehiculo" key, this test will fail with an exception.
        """
        case_id = str(uuid.uuid4())

        mock_state = {
            "conversation_id": "test-conv-nocontext",
            "user_id": str(uuid.uuid4()),
            "mode_context": {},  # No vehiculo key
            "fsm_state": _make_fsm_state(case_id),
        }
        set_current_state(mock_state)

        datos_vehiculo = {
            "matricula": "1234BCD",
            "bastidor": "VIN12345678901234",
            "anio": "2020",
        }

        mock_fsm_case_state = _make_fsm_case_state(case_id)
        mock_session = _build_session_mock(case_id)

        # Spy on update_case_fsm_state
        spy_update_fsm = MagicMock(return_value={})

        with (
            patch("agent.tools.case_tools.get_case_fsm_state", return_value=mock_fsm_case_state),
            patch("agent.tools.case_tools._get_case_id_with_fallback", return_value=case_id),
            patch("agent.tools.case_tools.get_current_step") as mock_step,
            patch("agent.tools.case_tools.get_async_session", return_value=mock_session),
            patch("agent.tools.case_tools.update_case_fsm_state", spy_update_fsm),
            patch("agent.tools.case_tools.validate_vehicle_data", return_value=(False, [])),
            patch("agent.tools.case_tools.normalize_matricula", side_effect=lambda x: x),
        ):
            from agent.utils.fsm_compat import CollectionStep
            mock_step.return_value = CollectionStep.COLLECT_VEHICLE

            # Must not raise
            result = await actualizar_datos_expediente_func(
                datos_vehiculo=datos_vehiculo,
            )

        assert result.get("success") is True, (
            f"Tool must succeed even when mode_context has no vehiculo. Got: {result}"
        )

        assert spy_update_fsm.called, (
            "update_case_fsm_state must be called after processing datos_vehiculo"
        )

        updates_for_fsm = spy_update_fsm.call_args[0][1]
        vehicle_data = updates_for_fsm.get("vehicle_data", {})

        # marca and modelo must NOT be in vehicle_data (no pre-population occurred)
        assert "marca" not in vehicle_data, (
            f"marca must NOT be in vehicle_data when mode_context has no vehiculo. "
            f"Got vehicle_data: {vehicle_data}"
        )
        assert "modelo" not in vehicle_data, (
            f"modelo must NOT be in vehicle_data when mode_context has no vehiculo. "
            f"Got vehicle_data: {vehicle_data}"
        )
