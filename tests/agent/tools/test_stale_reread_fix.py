"""
Unit tests for fix-expediente-state-integrity Track A:
Stale _get_mode_context() reread fix in actualizar_datos_expediente() and
actualizar_datos_taller().

Root cause: Both tools called _get_mode_context() a SECOND time after writing
to the DB. That second read hits the ContextVar snapshot set BEFORE the tool
ran — it does NOT contain the data just written. Validation ran against stale
state, producing wrong missing_fields and wrong next_step.

Fix: Remove the second _get_mode_context() call. Read personal_data,
vehicle_data, taller_propio, and taller_data from updates_for_fsm (the
just-merged dict), falling back to the initial case_fsm_state snapshot only
for sections this call didn't touch.

Spec scenarios (from fix-expediente-state-integrity spec):
- F1-S1 (stale-context, personal): tool receives complete personal data,
  _get_mode_context() snapshot has no personal_data → missing_fields must be
  empty and next_step must be collect_vehicle.
- F1-S2 (stale-context, vehicle): same for vehicle data → next_step collect_workshop.
- F1-S3 (happy-path): no stale context needed, complete data → same result.
- F1-S4 (stale-context, taller_propio=False): _get_mode_context() snapshot
  has taller_propio=None → tool must read from updates_for_fsm and transition
  to collect_review.
- F1-S5 (stale-context, taller data): taller_propio=True + complete taller
  data, stale snapshot has no taller_data → transitions to collect_review.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.tools.case_tools as case_tools_module

# Access underlying coroutines from LangChain @tool wrappers
actualizar_datos_expediente_func = (
    case_tools_module.actualizar_datos_expediente.coroutine
)
actualizar_datos_taller_func = case_tools_module.actualizar_datos_taller.coroutine


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_case_id() -> str:
    return str(uuid.uuid4())


def _build_session_mock() -> AsyncMock:
    """Return a minimal async session mock that commits without error."""
    mock_case = MagicMock()
    mock_case.user_id = None
    mock_case.updated_at = None

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(return_value=mock_case)
    mock_session.commit = AsyncMock()
    return mock_session


def _complete_personal_data() -> dict:
    """Return a complete personal data dict that passes validate_personal_data."""
    return {
        "nombre": "Ana",
        "apellidos": "Martínez López",
        "dni_cif": "12345678Z",
        "email": "ana.martinez@example.com",
        "domicilio_calle": "Calle Real 42",
        "domicilio_localidad": "Sevilla",
        "domicilio_provincia": "Sevilla",
        "domicilio_cp": "41001",
        "itv_nombre": "ITV Sevilla Norte",
    }


def _complete_vehicle_data() -> dict:
    """Return a complete vehicle data dict that passes validate_vehicle_data."""
    return {
        "marca": "Honda",
        "modelo": "CBR600RR",
        "anio": "2019",
        "matricula": "1234BCD",
        "bastidor": "JH2PC37CXKM100001",
    }


def _complete_taller_data() -> dict:
    """Return a complete taller data dict that passes validate_workshop_data."""
    return {
        "nombre": "Taller Hermanos García",
        "responsable": "Carlos García",
        "domicilio": "Polígono Industrial Sur, Nave 3",
        "provincia": "Sevilla",
        "ciudad": "Dos Hermanas",
        "telefono": "955123456",
        "registro_industrial": "RI-12345",
        "actividad": "Taller mecánico",
    }


# ---------------------------------------------------------------------------
# F1-S1 — Stale context: complete personal data → collect_vehicle transition
# ---------------------------------------------------------------------------


class TestA1StaleContextPersonalData:
    """
    F1-S1: _get_mode_context() snapshot has empty personal_data (stale).
    The tool receives complete personal data in datos_personales.
    After fix, validation reads from updates_for_fsm → missing_fields is empty
    and next_step is collect_vehicle.
    """

    @pytest.mark.asyncio
    async def test_personal_data_transition_despite_stale_context(self):
        """
        Given:  _get_mode_context() returns a snapshot with personal_data={}
                (simulating stale ContextVar before the tool's writes are reflected)
                datos_personales contains complete data
        When:   actualizar_datos_expediente() is called
        Then:   next_step == 'collect_vehicle'
                missing_fields is empty
        """
        case_id = _make_case_id()

        # Stale snapshot: personal_data is EMPTY (as if the ContextVar wasn't updated yet)
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {}  # empty personal_data for any key
            if key == "personal_data"
            else (args[0] if args else None)
        )

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-stale-personal",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_personal"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_PERSONAL,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_expediente_func(
                datos_personales=_complete_personal_data(),
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_VEHICLE.value, (
            f"Expected next_step='collect_vehicle' — validation must use just-written "
            f"data from updates_for_fsm, not stale snapshot. Got: {result.get('next_step')}"
        )
        assert (
            result.get("missing_fields") == [] or result.get("missing_fields") is None
        ), (
            f"Expected no missing_fields after complete personal data. "
            f"Got: {result.get('missing_fields')}"
        )

    @pytest.mark.asyncio
    async def test_incomplete_personal_data_stays_in_collect_personal(self):
        """
        Given:  complete datos_personales EXCEPT domicilio_cp is absent
        When:   actualizar_datos_expediente() is called
        Then:   next_step stays at collect_personal (not transitioning prematurely)
                missing_fields includes 'codigo postal'
        """
        case_id = _make_case_id()
        incomplete_personal = _complete_personal_data()
        del incomplete_personal["domicilio_cp"]  # Missing CP

        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {}
            if key in ("personal_data", "vehicle_data")
            else (args[0] if args else None)
        )

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-incomplete-personal",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_personal"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_PERSONAL,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_expediente_func(
                datos_personales=incomplete_personal,
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_PERSONAL.value, (
            f"Expected next_step='collect_personal' (data incomplete). Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields", [])
        assert len(missing) > 0, (
            "Expected missing_fields to be non-empty for incomplete data"
        )
        # CP is missing — validate_personal_data should report it
        assert any("postal" in f.lower() or "cp" in f.lower() for f in missing), (
            f"Expected missing_fields to include CP. Got: {missing}"
        )


# ---------------------------------------------------------------------------
# F1-S2 — Stale context: complete vehicle data → collect_workshop transition
# ---------------------------------------------------------------------------


class TestA1StaleContextVehicleData:
    """
    F1-S2: _get_mode_context() snapshot has empty vehicle_data (stale).
    The tool receives complete vehicle data in datos_vehiculo.
    After fix, validation reads from updates_for_fsm → next_step is collect_workshop.
    """

    @pytest.mark.asyncio
    async def test_vehicle_data_transition_despite_stale_context(self):
        """
        Given:  _get_mode_context() returns stale snapshot with vehicle_data={}
                datos_vehiculo contains complete data
        When:   actualizar_datos_expediente() is called
        Then:   next_step == 'collect_workshop'
                missing_fields is empty
        """
        case_id = _make_case_id()

        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {} if key == "vehicle_data" else (args[0] if args else None)
        )

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-stale-vehicle",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_vehicle"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_VEHICLE,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools.normalize_matricula",
                side_effect=lambda x: x,
            ),
        ):
            result = await actualizar_datos_expediente_func(
                datos_vehiculo=_complete_vehicle_data(),
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_WORKSHOP.value, (
            f"Expected next_step='collect_workshop' — validation must use just-written "
            f"data from updates_for_fsm, not stale snapshot. Got: {result.get('next_step')}"
        )
        assert (
            result.get("missing_fields") == [] or result.get("missing_fields") is None
        ), (
            f"Expected no missing_fields after complete vehicle data. "
            f"Got: {result.get('missing_fields')}"
        )


# ---------------------------------------------------------------------------
# F1-S4 — Stale context: taller_propio=False → collect_review transition
# ---------------------------------------------------------------------------


class TestA2StaleContextTallerPropioFalse:
    """
    F1-S4: _get_mode_context() snapshot has taller_propio=None (stale).
    The tool receives taller_propio=False.
    After fix, current_taller_propio reads from updates_for_fsm → is False
    → transitions to collect_review.
    """

    @pytest.mark.asyncio
    async def test_taller_propio_false_transitions_to_review_despite_stale_context(
        self,
    ):
        """
        Given:  _get_mode_context() returns stale snapshot with taller_propio=None
                taller_propio=False is passed to actualizar_datos_taller()
        When:   actualizar_datos_taller() is called
        Then:   next_step == 'review_summary' (MSI provides certificate)
        """
        case_id = _make_case_id()

        # Stale snapshot: taller_propio is None (not yet written to ContextVar)
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            None  # stale: taller_propio is not set
            if key == "taller_propio"
            else (args[0] if args else None)
        )

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-stale-taller-false",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_workshop"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_WORKSHOP,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_taller_func(
                taller_propio=False,
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"Expected next_step='review_summary' — taller_propio=False must come from "
            f"updates_for_fsm, not stale snapshot with taller_propio=None. "
            f"Got: {result.get('next_step')}"
        )


# ---------------------------------------------------------------------------
# F1-S5 — Stale context: complete taller data → collect_review transition
# ---------------------------------------------------------------------------


class TestA2StaleContextTallerData:
    """
    F1-S5: _get_mode_context() snapshot has taller_data=None and taller_propio=None (stale).
    The tool receives taller_propio=True and complete datos_taller.
    After fix, both reads from updates_for_fsm → transitions to collect_review.
    """

    @pytest.mark.asyncio
    async def test_taller_data_transition_to_review_despite_stale_context(self):
        """
        Given:  _get_mode_context() returns stale snapshot:
                  taller_propio=None, taller_data=None
                taller_propio=True and complete datos_taller are passed
        When:   actualizar_datos_taller() is called
        Then:   next_step == 'review_summary'
                missing_fields is empty
        """
        case_id = _make_case_id()

        # Stale snapshot: neither taller_propio nor taller_data are set
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: args[0] if args else None

        # Ensure taller_propio returns None and taller_data returns None
        def _stale_get(key, *args):
            if key in ("taller_propio", "taller_data"):
                return None
            return args[0] if args else None

        stale_snapshot.get = _stale_get

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-stale-taller-data",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_workshop"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_WORKSHOP,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_taller_func(
                taller_propio=True,
                datos_taller=_complete_taller_data(),
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"Expected next_step='review_summary' — taller_data must come from "
            f"updates_for_fsm, not stale snapshot with taller_data=None. "
            f"Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields", [])
        assert not missing, (
            f"Expected no missing_fields for complete taller data. Got: {missing}"
        )

    @pytest.mark.asyncio
    async def test_incomplete_taller_data_stays_in_collect_workshop(self):
        """
        Given:  _get_mode_context() returns stale snapshot with taller_propio=None
                taller_propio=True and INCOMPLETE datos_taller (missing nombre)
        When:   actualizar_datos_taller() is called
        Then:   next_step stays at collect_workshop
                missing_fields is non-empty
        """
        case_id = _make_case_id()
        incomplete_taller = _complete_taller_data()
        del incomplete_taller["nombre"]  # Remove required field

        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: args[0] if args else None

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=stale_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-incomplete-taller",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_workshop"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_WORKSHOP,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_taller_func(
                taller_propio=True,
                datos_taller=incomplete_taller,
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_WORKSHOP.value, (
            f"Expected next_step='collect_workshop' for incomplete taller data. "
            f"Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields", [])
        assert len(missing) > 0, (
            "Expected missing_fields to be non-empty for incomplete taller"
        )


# ---------------------------------------------------------------------------
# Happy-path: no stale context needed, same results
# ---------------------------------------------------------------------------


class TestA1A2HappyPath:
    """
    F1-S3: Happy-path verification — complete data with fresh context also works.
    These tests ensure no regression when context IS fresh.
    """

    @pytest.mark.asyncio
    async def test_personal_data_happy_path(self):
        """
        When _get_mode_context() returns a fresh snapshot (with personal_data already set),
        complete datos_personales still transitions correctly.
        """
        case_id = _make_case_id()
        personal = _complete_personal_data()

        # "Fresh" snapshot — personal_data is already present (not stale)
        fresh_snapshot = MagicMock()
        fresh_snapshot.get = lambda key, *args: (
            personal
            if key == "personal_data"
            else ({} if key == "vehicle_data" else (args[0] if args else None))
        )

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=fresh_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-happy-personal",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_personal"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_PERSONAL,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_expediente_func(
                datos_personales=personal,
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_VEHICLE.value, (
            f"Expected next_step='collect_vehicle' on happy path. Got: {result.get('next_step')}"
        )

    @pytest.mark.asyncio
    async def test_taller_propio_false_happy_path(self):
        """
        taller_propio=False happy path: transitions to review_summary normally.
        """
        case_id = _make_case_id()

        fresh_snapshot = MagicMock()
        fresh_snapshot.get = lambda key, *args: args[0] if args else None

        mock_session = _build_session_mock()

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=fresh_snapshot,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "test-happy-taller-false",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "collect_workshop"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {},
                },
            ),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_WORKSHOP,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=mock_session,
            ),
            patch(
                "agent.tools.case_tools._build_case_update",
                return_value={"case_collection": {}},
            ),
            patch(
                "agent.tools.case_tools._transition_with_db_sync",
                new_callable=AsyncMock,
                return_value={"case_collection": {}},
            ),
        ):
            result = await actualizar_datos_taller_func(
                taller_propio=False,
            )

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"Expected next_step='review_summary'. Got: {result.get('next_step')}"
        )
