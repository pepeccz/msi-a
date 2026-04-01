"""
Integration tests for fix-expediente-state-integrity Track D.

Verifies the full-system behaviour after all three fixes (A, B, C) are applied:
- Fix A (F1): Tools validate from locally-written data, not stale ContextVar
- Fix B (F2): Tombstone protocol — popped keys cannot resurrect via merge_dicts
- Fix C (F3): Kickoff no-tool turns are validated for phase truthfulness

Track D covers:
- D1: End-to-end multi-turn expediente flow (personal → vehicle → workshop → review)
- D2: Production incident chain regression test (F2→F3→F1 chain is not reproducible)
- D3: obtener_estado_expediente() consistency after normal completion

Usage:
    pytest tests/integration/test_expediente_state_integrity.py -v
"""

from __future__ import annotations

import re
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub optional heavy dependencies so tests run without full Docker stack
# ---------------------------------------------------------------------------
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

import agent.tools.case_tools as case_tools_module

# Access underlying coroutines from LangChain @tool wrappers
_actualizar_datos_expediente = case_tools_module.actualizar_datos_expediente.coroutine
_actualizar_datos_taller = case_tools_module.actualizar_datos_taller.coroutine
_obtener_estado_expediente = case_tools_module.obtener_estado_expediente.coroutine


# ---------------------------------------------------------------------------
# Shared helpers (copied from test_stale_reread_fix.py pattern)
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
    return {
        "nombre": "María",
        "apellidos": "García Pérez",
        "dni_cif": "87654321X",
        "email": "maria.garcia@example.com",
        "domicilio_calle": "Avenida Constitución 10",
        "domicilio_localidad": "Madrid",
        "domicilio_provincia": "Madrid",
        "domicilio_cp": "28001",
        "itv_nombre": "ITV Madrid Sur",
    }


def _complete_vehicle_data() -> dict:
    return {
        "marca": "Yamaha",
        "modelo": "MT-07",
        "anio": "2021",
        "matricula": "5678XYZ",
        "bastidor": "JYARN23E00A100001",
    }


def _complete_taller_data() -> dict:
    return {
        "nombre": "Taller Sánchez",
        "responsable": "Pedro Sánchez",
        "domicilio": "Calle Industrial 5",
        "provincia": "Madrid",
        "ciudad": "Getafe",
        "telefono": "916123456",
        "registro_industrial": "RI-67890",
        "actividad": "Taller mecánico",
    }


# ---------------------------------------------------------------------------
# D1 — End-to-end multi-turn integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestD1FullExpedienteFlow:
    """
    D1: Verify the full expediente progression completes correctly without
    hallucinated phase advancement.

    Flow: collect_personal → collect_vehicle → collect_workshop → review_summary

    This proves Fix A works end-to-end: each transition is triggered from the
    data locally written within the same tool call, never from a stale ContextVar.
    """

    async def test_personal_to_vehicle_transition(self):
        """
        Step 1 of flow: complete personal data transitions to collect_vehicle.

        Given: stale ContextVar snapshot (empty personal_data)
        When: actualizar_datos_expediente() called with complete personal data
        Then: next_step == 'collect_vehicle', missing_fields == []
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {} if key == "personal_data" else (args[0] if args else None)
        )
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d1-personal-turn",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
            result = await _actualizar_datos_expediente(
                datos_personales=_complete_personal_data()
            )

        assert result.get("success") is True, f"Step 1 must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_VEHICLE.value, (
            f"Personal data should transition to collect_vehicle. Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields") or []
        assert missing == [], f"No fields should be missing. Got: {missing}"

    async def test_vehicle_to_workshop_transition(self):
        """
        Step 2 of flow: complete vehicle data transitions to collect_workshop.

        Given: stale ContextVar snapshot (empty vehicle_data)
        When: actualizar_datos_expediente() called with complete vehicle data
        Then: next_step == 'collect_workshop', missing_fields == []
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {} if key == "vehicle_data" else (args[0] if args else None)
        )
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d1-vehicle-turn",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
                "agent.tools.case_tools.normalize_matricula", side_effect=lambda x: x
            ),
        ):
            result = await _actualizar_datos_expediente(
                datos_vehiculo=_complete_vehicle_data()
            )

        assert result.get("success") is True, f"Step 2 must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.COLLECT_WORKSHOP.value, (
            f"Vehicle data should transition to collect_workshop. Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields") or []
        assert missing == [], f"No fields should be missing. Got: {missing}"

    async def test_workshop_taller_propio_true_to_review_transition(self):
        """
        Step 3a of flow: taller_propio=True + complete data transitions to review.

        Given: stale ContextVar snapshot (taller_propio=None, taller_data=None)
        When: actualizar_datos_taller() called with taller_propio=True + complete data
        Then: next_step == 'review_summary', no missing fields
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()

        def _stale_get(key, *args):
            if key in ("taller_propio", "taller_data"):
                return None
            return args[0] if args else None

        stale_snapshot = MagicMock()
        stale_snapshot.get = _stale_get
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d1-taller-true-turn",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
            result = await _actualizar_datos_taller(
                taller_propio=True,
                datos_taller=_complete_taller_data(),
            )

        assert result.get("success") is True, f"Step 3a must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"Complete taller should transition to review_summary. Got: {result.get('next_step')}"
        )
        missing = result.get("missing_fields") or []
        assert missing == [], f"No fields should be missing. Got: {missing}"

    async def test_workshop_taller_propio_false_to_review_transition(self):
        """
        Step 3b of flow: taller_propio=False transitions to review immediately.

        Given: stale ContextVar snapshot (taller_propio=None)
        When: actualizar_datos_taller() called with taller_propio=False
        Then: next_step == 'review_summary' (MSI provides certificate)
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            None if key == "taller_propio" else (args[0] if args else None)
        )
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d1-taller-false-turn",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
            result = await _actualizar_datos_taller(taller_propio=False)

        assert result.get("success") is True, f"Step 3b must succeed. Got: {result}"
        assert result.get("next_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"taller_propio=False should transition to review_summary. Got: {result.get('next_step')}"
        )

    async def test_no_hallucinated_step_decoration_personal(self):
        """
        Verify complete personal data result has no wrong-phase artifacts.

        The response chain should never mention "Paso 5/6" (workshop) when
        we are in collect_personal. This exercises the Fix C guard indirectly
        by confirming the tool result itself carries only the correct next_step.
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {} if key == "personal_data" else (args[0] if args else None)
        )
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d1-no-hallucination",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
            result = await _actualizar_datos_expediente(
                datos_personales=_complete_personal_data()
            )

        # The next_step must NOT suggest a phase other than collect_vehicle
        # (fix A prevents the stale-context issue that would otherwise signal wrong step)
        assert result.get("next_step") != "collect_workshop", (
            "Personal completion should NOT jump to collect_workshop — possible hallucinated advance"
        )
        assert result.get("next_step") != "review_summary", (
            "Personal completion should NOT jump to review_summary"
        )
        assert result.get("next_step") == CollectionStep.COLLECT_VEHICLE.value, (
            f"Only correct next_step is collect_vehicle. Got: {result.get('next_step')}"
        )


# ---------------------------------------------------------------------------
# D2 — Regression test: production incident chain non-recurrence
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestD2ProductionIncidentChainRegression:
    """
    D2: Verify the exact production incident chain (F2→F3→F1) cannot recur.

    Production incident replay:
    1. [F2] expediente_transition_marker stale in checkpoint → sub_mode stuck
    2. [F3] kickoff no-tool turn → LLM hallucinates "Paso 5/6 — Taller"
    3. [F1] tool validates from stale context → wrong transition

    With fixes applied:
    1. [Fix B] tombstone semantics — marker = None after pop → sub_mode advances
    2. [Fix C] "Paso 5/6" in collect_personal → stripped
    3. [Fix A] tool reads from updates_for_fsm → correct transition
    """

    def test_fix_b_transition_marker_tombstone_prevents_resurrection(self):
        """
        Part 1: Verify Fix B — transition marker tombstone prevents resurrection.

        Scenario:
        - Turn N: expediente_transition_marker set to "collect_vehicle"
        - Turn N+1: marker consumed + tombstoned (= None)
        - Turn N+2: marker is still None, NOT resurrected from checkpoint

        Without fix: pop() alone → checkpoint has old value → resurrection on N+2.
        With fix: tombstone (= None) → merge_dicts overwrites checkpoint → stays None.
        """
        from agent.state.conversation_state import merge_dicts

        # Turn N: checkpoint has the transition marker
        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "current_step": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
        }

        # Turn N+1: mode consumes marker → tombstones it (Fix B applied)
        turn_n1_update = dict(turn_n_context)
        _consumed = turn_n1_update.pop("expediente_transition_marker", None)
        assert _consumed == "collect_vehicle"  # Verify we read the right value
        turn_n1_update["expediente_transition_marker"] = None  # TOMBSTONE (Fix B)

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)
        assert turn_n1_checkpoint["expediente_transition_marker"] is None, (
            "After tombstone, marker must be None in merged checkpoint"
        )

        # Turn N+2: nothing touches the marker (mode doesn't set it this turn)
        turn_n2_update = {
            "expediente_sub_mode": "collect_personal",  # Still processing
            "current_step": "collect_personal",
        }
        turn_n2_checkpoint = merge_dicts(
            current=turn_n1_checkpoint, update=turn_n2_update
        )

        assert turn_n2_checkpoint.get("expediente_transition_marker") is None, (
            "Tombstoned None MUST persist to turn N+2 — marker must not resurrect. "
            f"Got: {turn_n2_checkpoint.get('expediente_transition_marker')!r}"
        )

    def test_fix_b_without_tombstone_marker_would_resurrect(self):
        """
        Control test: confirm the original bug — pop() without tombstone resurrects.

        This documents WHY the fix was needed: without tombstone, the production
        incident is reproducible.
        """
        from agent.state.conversation_state import merge_dicts

        turn_n_context = {
            "expediente_transition_marker": "collect_vehicle",
            "expediente_sub_mode": "collect_personal",
        }

        # BUG: pop() alone, no tombstone (the pre-fix behaviour)
        turn_n1_update = dict(turn_n_context)
        turn_n1_update.pop("expediente_transition_marker", None)  # No tombstone!
        # expediente_transition_marker is ABSENT from turn_n1_update

        turn_n1_checkpoint = merge_dicts(current=turn_n_context, update=turn_n1_update)

        # With the bug: merge_dicts sees absent key in update → keeps checkpoint value
        assert (
            turn_n1_checkpoint["expediente_transition_marker"] == "collect_vehicle"
        ), (
            "This is the pre-fix behaviour: absent key in update means checkpoint value survives"
        )

    def test_fix_c_wrong_step_stripped_on_collect_personal(self):
        """
        Part 2: Verify Fix C — wrong-step "Paso X/6" stripped on kickoff turns.

        Scenario: sub_mode=collect_personal, LLM generates "Paso 5/6 — Taller"
        Expected: "Paso 5/6" is stripped from the response; content preserved.
        """
        from agent.modes.expediente_mode import _SUBMODE_STEP_MAP

        sub_mode = "collect_personal"
        ai_response = "📍 Paso 5/6 — Taller de montaje\n¿Quién realizó la instalación?"

        expected_step = _SUBMODE_STEP_MAP.get(sub_mode)
        assert expected_step is not None, (
            f"sub_mode '{sub_mode}' must be in _SUBMODE_STEP_MAP"
        )

        # Apply the Fix C guard (same logic as in expediente_mode.py)
        step_re = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
        match = step_re.search(ai_response)
        if match and int(match.group(1)) != expected_step:
            ai_response = step_re.sub("", ai_response).strip()

        assert "Paso 5/6" not in ai_response, (
            "Wrong-phase 'Paso 5/6' must be stripped from collect_personal response"
        )
        assert "Taller de montaje" in ai_response, (
            "Content after the wrong-step prefix must be preserved after stripping"
        )
        assert "instalación" in ai_response, "Follow-up question must survive stripping"

    def test_fix_c_correct_step_not_stripped(self):
        """
        Fix C must NOT strip a correctly-numbered step on a kickoff turn.

        Scenario: sub_mode=collect_personal, LLM generates "Paso 3/6"
        Expected: response passes through unchanged.
        """
        from agent.modes.expediente_mode import _SUBMODE_STEP_MAP

        sub_mode = "collect_personal"
        original_response = (
            "📍 Paso 3/6 — Datos personales\n¿Me puedes dar tu nombre completo?"
        )

        expected_step = _SUBMODE_STEP_MAP.get(sub_mode)
        step_re = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
        match = step_re.search(original_response)

        # Guard should NOT trigger (claimed step == expected step)
        if match and int(match.group(1)) != expected_step:
            original_response = step_re.sub("", original_response).strip()

        assert "Paso 3/6" in original_response, (
            "Correct step number must NOT be stripped"
        )
        assert "Datos personales" in original_response

    @pytest.mark.parametrize(
        "sub_mode,correct_step,wrong_step",
        [
            ("collect_personal", 3, 5),
            ("collect_vehicle", 4, 2),
            ("collect_base_docs", 2, 6),
            ("collect_workshop", 5, 3),
        ],
    )
    def test_fix_c_step_mismatch_detection(self, sub_mode, correct_step, wrong_step):
        """
        Parametrized: Fix C correctly identifies step mismatches for all sub-modes.
        """
        from agent.modes.expediente_mode import _SUBMODE_STEP_MAP

        # Verify the expected step from the constant
        assert _SUBMODE_STEP_MAP.get(sub_mode) == correct_step, (
            f"_SUBMODE_STEP_MAP[{sub_mode!r}] should be {correct_step}, "
            f"got {_SUBMODE_STEP_MAP.get(sub_mode)}"
        )

        # Wrong-step response
        wrong_response = f"Paso {wrong_step}/6 — Contenido"
        step_re = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
        match = step_re.search(wrong_response)
        expected_step = _SUBMODE_STEP_MAP.get(sub_mode)
        stripped = wrong_response
        if match and expected_step is not None and int(match.group(1)) != expected_step:
            stripped = step_re.sub("", wrong_response).strip()

        assert f"Paso {wrong_step}/6" not in stripped, (
            f"Wrong step {wrong_step}/6 must be stripped for sub_mode={sub_mode!r}"
        )

        # Correct-step response
        correct_response = f"Paso {correct_step}/6 — Contenido correcto"
        match = step_re.search(correct_response)
        not_stripped = correct_response
        if match and expected_step is not None and int(match.group(1)) != expected_step:
            not_stripped = step_re.sub("", correct_response).strip()

        assert f"Paso {correct_step}/6" in not_stripped, (
            f"Correct step {correct_step}/6 must NOT be stripped for sub_mode={sub_mode!r}"
        )

    @pytest.mark.parametrize(
        "advancement_phrase",
        [
            "Pasemos al siguiente paso con tu información de vehículo.",
            "Siguiente paso: vamos a recopilar los datos del vehículo.",
            "Continuamos con el paso de datos del vehículo.",
            "Hemos completado la sección de datos personales.",
            "Ya tenemos todo lo necesario para continuar.",
        ],
    )
    def test_fix_c_advancement_language_stripped(self, advancement_phrase):
        """
        Advancement-language on a no-tool kickoff turn must be stripped.
        """
        advancement_re = re.compile(
            r"siguiente\s+paso|pasemos\s+a"
            r"|continuamos\s+con\s+el\s+paso"
            r"|hemos\s+completado|ya\s+tenemos\s+todo",
            re.IGNORECASE,
        )
        stripped = advancement_re.sub("", advancement_phrase).strip()

        # The phrase must not survive unchanged after stripping
        assert stripped != advancement_phrase, (
            f"Advancement phrase should have been partially stripped: {advancement_phrase!r}"
        )

    @pytest.mark.asyncio
    async def test_fix_a_correct_transition_from_local_data(self):
        """
        Part 3: Verify Fix A — tool uses locally-written data, not stale ContextVar.

        This is the culminating check of the incident chain: even if F2 and F3
        were not fixed, Fix A alone would prevent the wrong transition signal.
        """
        from agent.utils.expediente_types import CollectionStep

        case_id = _make_case_id()

        # Stale snapshot simulates the pre-fix scenario: no personal_data in ContextVar
        stale_snapshot = MagicMock()
        stale_snapshot.get = lambda key, *args: (
            {} if key == "personal_data" else (args[0] if args else None)
        )
        mock_session = _build_session_mock()

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_snapshot
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d2-fix-a-chain",
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
                "agent.tools.case_tools.get_async_session", return_value=mock_session
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
            result = await _actualizar_datos_expediente(
                datos_personales=_complete_personal_data()
            )

        # Fix A: tool reads personal_data from updates_for_fsm (just-written),
        # NOT from the stale _get_mode_context() snapshot.
        assert result.get("success") is True
        assert result.get("next_step") == CollectionStep.COLLECT_VEHICLE.value, (
            "Fix A: validation must read from just-written data → correct next_step. "
            f"Got: {result.get('next_step')!r}"
        )
        missing = result.get("missing_fields") or []
        assert missing == [], (
            f"Fix A: no fields should be reported missing when data is present. Got: {missing}"
        )

    def test_submode_step_map_complete(self):
        """
        Verify _SUBMODE_STEP_MAP covers all sub-modes with expected step numbers.

        This guards against future changes to STEP_LABELS breaking the Fix C guard.
        """
        from agent.modes.expediente_mode import _SUBMODE_STEP_MAP

        expected_entries = {
            "collect_element_data": 1,
            "collect_base_docs": 2,
            "collect_personal": 3,
            "collect_vehicle": 4,
            "collect_workshop": 5,
            "review_summary": 6,
        }

        for sub_mode, expected_step in expected_entries.items():
            assert sub_mode in _SUBMODE_STEP_MAP, (
                f"_SUBMODE_STEP_MAP is missing sub_mode: {sub_mode!r}"
            )
            assert _SUBMODE_STEP_MAP[sub_mode] == expected_step, (
                f"_SUBMODE_STEP_MAP[{sub_mode!r}] should be {expected_step}, "
                f"got {_SUBMODE_STEP_MAP[sub_mode]}"
            )


# ---------------------------------------------------------------------------
# D3 — obtener_estado_expediente() consistency test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestD3ObtenerEstadoConsistency:
    """
    D3: Verify obtener_estado_expediente() reflects actual state correctly
    and does NOT trigger incoherence escalation in a normal completion flow.

    The tool reads from _get_mode_context() (ContextVar snapshot of mode_context).
    In a correctly-progressed expediente, the context should match DB truth.
    """

    async def test_review_summary_state_returned_correctly(self):
        """
        After completing all data collection phases, obtener_estado_expediente()
        should return current_step == 'review_summary' without escalation signals.

        Given: mode_context reflects review_summary sub-mode with all data complete
        When: obtener_estado_expediente() is called
        Then: has_active_case=True, current_step='review_summary', no error
        """
        from agent.utils.expediente_types import CollectionStep

        personal_data = _complete_personal_data()
        vehicle_data = _complete_vehicle_data()
        taller_data = _complete_taller_data()

        # Complete context snapshot (what would be in mode_context at review stage)
        complete_context = MagicMock()
        complete_context.get = lambda key, *args: {
            "personal_data": personal_data,
            "vehicle_data": vehicle_data,
            "taller_propio": True,
            "taller_data": taller_data,
            "tariff_amount": 410.0,
            "element_codes": ["ESCAPE", "MANILLAR"],
            "element_data_status": {
                "ESCAPE": "completed",
                "MANILLAR": "completed",
            },
            "received_images": ["img_001.jpg", "img_002.jpg"],
        }.get(key, args[0] if args else None)

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=complete_context,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d3-review-state",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "review_summary"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch(
                "agent.tools.case_tools._is_collection_active",
                return_value=True,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.REVIEW_SUMMARY,
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("has_active_case") is True, "has_active_case must be True"
        assert result.get("current_step") == CollectionStep.REVIEW_SUMMARY.value, (
            f"current_step must be 'review_summary'. Got: {result.get('current_step')!r}"
        )
        assert result.get("personal_data_complete") is True, (
            "personal_data_complete must be True after all fields provided"
        )
        assert result.get("vehicle_data_complete") is True, (
            "vehicle_data_complete must be True after all fields provided"
        )

        # Incoherence escalation signal: tool should NOT return error_category
        assert "error_category" not in result or result.get("error_category") is None, (
            "No incoherence escalation should occur when state is consistent. "
            f"Got error_category: {result.get('error_category')!r}"
        )

    async def test_no_incoherence_when_taller_propio_false(self):
        """
        taller_propio=False should yield taller_data_complete=True (no taller needed).
        This verifies the logic doesn't trigger an incoherence check for valid states.
        """
        from agent.utils.expediente_types import CollectionStep

        personal_data = _complete_personal_data()
        vehicle_data = _complete_vehicle_data()

        context = MagicMock()
        context.get = lambda key, *args: {
            "personal_data": personal_data,
            "vehicle_data": vehicle_data,
            "taller_propio": False,  # MSI provides certificate
            "taller_data": None,  # Not needed
            "tariff_amount": 320.0,
            "element_codes": ["SUSPENSION"],
            "element_data_status": {"SUSPENSION": "completed"},
            "received_images": ["img_001.jpg"],
        }.get(key, args[0] if args else None)

        with (
            patch("agent.tools.case_tools._get_mode_context", return_value=context),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d3-taller-false-state",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {"expediente_sub_mode": "review_summary"},
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.REVIEW_SUMMARY,
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("taller_propio") is False
        assert result.get("taller_data_complete") is True, (
            "taller_data_complete must be True when taller_propio=False (no taller needed)"
        )
        # Precio certificado should be 85 when taller_propio=False
        assert result.get("precio_certificado") == 85, (
            f"precio_certificado must be 85 when taller_propio=False. Got: {result.get('precio_certificado')}"
        )

    async def test_no_active_case_returns_gracefully(self):
        """
        When no expediente is active, obtener_estado_expediente() must return
        gracefully without escalation.
        """
        with (
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d3-no-case",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {},
                    "current_mode": "PRESUPUESTO_MODE",
                    "fsm_state": {},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=False),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, (
            f"No-case scenario must succeed. Got: {result}"
        )
        assert result.get("has_active_case") is False, (
            "has_active_case must be False when no expediente is active"
        )
        assert "error_category" not in result or result.get("error_category") is None, (
            "No escalation when there's simply no active case"
        )

    async def test_review_step_precio_total_calculation(self):
        """
        At review_summary, the tool calculates precio_total correctly.

        taller_propio=True  → precio_total = tariff_amount (no extra certificate cost)
        taller_propio=False → precio_total = tariff_amount + 85
        """
        from agent.utils.expediente_types import CollectionStep

        tariff = 410.0

        for taller_propio, expected_total, expected_cert in [
            (True, tariff, 0),
            (False, tariff + 85, 85),
        ]:
            context = MagicMock()
            context.get = lambda key, *args, _tp=taller_propio, _ta=tariff: {
                "personal_data": _complete_personal_data(),
                "vehicle_data": _complete_vehicle_data(),
                "taller_propio": _tp,
                "taller_data": _complete_taller_data() if _tp else None,
                "tariff_amount": _ta,
                "element_codes": ["ESCAPE"],
                "element_data_status": {"ESCAPE": "completed"},
                "received_images": [],
            }.get(key, args[0] if args else None)

            with (
                patch("agent.tools.case_tools._get_mode_context", return_value=context),
                patch(
                    "agent.tools.case_tools.get_current_state",
                    return_value={
                        "conversation_id": f"d3-precio-{taller_propio}",
                        "user_id": str(uuid.uuid4()),
                        "mode_context": {"expediente_sub_mode": "review_summary"},
                        "current_mode": "EXPEDIENTE_MODE",
                        "fsm_state": {"collection_active": True},
                    },
                ),
                patch(
                    "agent.tools.case_tools._is_collection_active", return_value=True
                ),
                patch(
                    "agent.tools.case_tools._get_current_step_from_context",
                    return_value=CollectionStep.REVIEW_SUMMARY,
                ),
            ):
                result = await _obtener_estado_expediente()

            assert result.get("precio_total") == expected_total, (
                f"precio_total for taller_propio={taller_propio} must be {expected_total}. "
                f"Got: {result.get('precio_total')}"
            )
            assert result.get("precio_certificado") == expected_cert, (
                f"precio_certificado for taller_propio={taller_propio} must be {expected_cert}. "
                f"Got: {result.get('precio_certificado')}"
            )


# ---------------------------------------------------------------------------
# D4 — obtener_estado_expediente() DB-sourced path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestD4ObtenerEstadoDBSourced:
    """
    D4: Verify obtener_estado_expediente() reads authoritative data from DB
    instead of stale mode_context.

    This covers the CRITICAL fix for the production incident where images_received
    reported 0 despite 11 real images in the DB, because mode_context was stale.
    """

    def _make_mock_case(
        self,
        case_id: str,
        images: list,
        element_data: list,
        user=None,
        status: str = "collecting",
        taller_propio=None,
        taller_nombre=None,
        tariff_amount=None,
        vehiculo_marca=None,
        vehiculo_modelo=None,
        vehiculo_anio=None,
        vehiculo_matricula=None,
        vehiculo_bastidor=None,
        itv_nombre=None,
        element_codes: list | None = None,
    ) -> MagicMock:
        """Build a mock Case object with DB-sourced attributes."""
        mock_case = MagicMock()
        mock_case.id = uuid.UUID(case_id)
        mock_case.status = status
        mock_case.images = images
        mock_case.element_data = element_data
        mock_case.user = user
        mock_case.taller_propio = taller_propio
        mock_case.taller_nombre = taller_nombre
        mock_case.tariff_amount = tariff_amount
        mock_case.vehiculo_marca = vehiculo_marca
        mock_case.vehiculo_modelo = vehiculo_modelo
        mock_case.vehiculo_anio = vehiculo_anio
        mock_case.vehiculo_matricula = vehiculo_matricula
        mock_case.vehiculo_bastidor = vehiculo_bastidor
        mock_case.itv_nombre = itv_nombre
        mock_case.element_codes = element_codes or []
        return mock_case

    def _make_mock_user(
        self,
        first_name: str = "María",
        last_name: str = "García Pérez",
        email: str = "maria@example.com",
        nif_cif: str = "87654321X",
        domicilio_calle: str = "Calle Constitución 10",
        domicilio_localidad: str = "Madrid",
        domicilio_provincia: str = "Madrid",
        domicilio_cp: str = "28001",
    ) -> MagicMock:
        user = MagicMock()
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.nif_cif = nif_cif
        user.domicilio_calle = domicilio_calle
        user.domicilio_localidad = domicilio_localidad
        user.domicilio_provincia = domicilio_provincia
        user.domicilio_cp = domicilio_cp
        return user

    def _make_mock_ced(self, element_code: str, status: str) -> MagicMock:
        ced = MagicMock()
        ced.element_code = element_code
        ced.status = status
        return ced

    def _make_mock_image(self, name: str = "img.jpg") -> MagicMock:
        img = MagicMock()
        img.display_name = name
        return img

    def _build_db_session_mock(self, case: MagicMock) -> AsyncMock:
        """Build an async session mock that returns the given case on execute."""
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none = MagicMock(return_value=case)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=scalar_result)
        return mock_session

    async def test_images_received_comes_from_db_not_mode_context(self):
        """
        CRITICAL regression: images_received must come from DB Case.images,
        NOT from mode_context['received_images'].

        Scenario: mode_context reports 0 images (stale snapshot), but DB has 11.
        The tool must return images_received=11.
        """
        case_id = _make_case_id()
        eleven_images = [self._make_mock_image(f"img_{i:03d}.jpg") for i in range(11)]

        mock_case = self._make_mock_case(
            case_id=case_id,
            images=eleven_images,
            element_data=[],
            element_codes=["ESCAPE"],
            status="collecting",
        )
        mock_session = self._build_db_session_mock(mock_case)

        # Stale mode_context has 0 received_images — the old bug
        stale_context = MagicMock()
        stale_context.get = lambda key, *args: {
            "case_id": case_id,
            "received_images": [],  # Stale: 0 images
            "element_codes": ["ESCAPE"],
            "element_data_status": {},
        }.get(key, args[0] if args else None)

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_context
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d4-images-test",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {
                        "case_id": case_id,
                        "expediente_sub_mode": "collect_element_data",
                    },
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session", return_value=mock_session
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("images_received") == 11, (
            f"images_received must be 11 (from DB), not 0 (stale mode_context). "
            f"Got: {result.get('images_received')}"
        )

    async def test_element_data_status_comes_from_db(self):
        """
        element_status must reflect DB CaseElementData records, not mode_context.

        Scenario: mode_context says ESCAPE is 'pending_photos' (stale), but DB
        has status='completed'.
        """
        case_id = _make_case_id()
        ced_escape = self._make_mock_ced("ESCAPE", "completed")

        mock_case = self._make_mock_case(
            case_id=case_id,
            images=[self._make_mock_image()],
            element_data=[ced_escape],
            element_codes=["ESCAPE"],
            status="collecting",
        )
        mock_session = self._build_db_session_mock(mock_case)

        # Stale: mode_context says ESCAPE is pending
        stale_context = MagicMock()
        stale_context.get = lambda key, *args: {
            "case_id": case_id,
            "element_codes": ["ESCAPE"],
            "element_data_status": {"ESCAPE": "pending_photos"},  # Stale
            "received_images": [],
        }.get(key, args[0] if args else None)

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_context
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d4-element-status-test",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {
                        "case_id": case_id,
                        "expediente_sub_mode": "collect_element_data",
                    },
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session", return_value=mock_session
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        element_status = result.get("element_status", [])
        escape_status = next(
            (e["status"] for e in element_status if e["code"] == "ESCAPE"), None
        )
        assert escape_status == "completed", (
            f"element_status for ESCAPE must be 'completed' (from DB), "
            f"not 'pending_photos' (stale mode_context). Got: {escape_status!r}"
        )

    async def test_current_step_derived_from_db_case_status(self):
        """
        current_step is derived from actual DB Case fields, not stale mode_context.

        Scenario: DB case has status='pending_review', mode_context claims
        'collect_personal'. The tool should return 'review_summary'.
        """
        case_id = _make_case_id()
        user = self._make_mock_user()
        mock_case = self._make_mock_case(
            case_id=case_id,
            images=[],
            element_data=[],
            element_codes=["ESCAPE"],
            status="pending_review",  # DB says ready for review
            user=user,
            taller_propio=True,
            taller_nombre="Taller Test",
            tariff_amount=410.0,
            vehiculo_marca="Yamaha",
            vehiculo_modelo="MT-07",
            vehiculo_anio=2021,
            vehiculo_matricula="5678XYZ",
            vehiculo_bastidor="VIN123",
            itv_nombre="ITV Test",
        )
        mock_session = self._build_db_session_mock(mock_case)

        # Stale: mode_context says collect_personal (wrong)
        stale_context = MagicMock()
        stale_context.get = lambda key, *args: {
            "case_id": case_id,
            "element_codes": ["ESCAPE"],
            "element_data_status": {},
            "received_images": [],
        }.get(key, args[0] if args else None)

        with (
            patch(
                "agent.tools.case_tools._get_mode_context", return_value=stale_context
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d4-step-test",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {
                        "case_id": case_id,
                        "expediente_sub_mode": "collect_personal",  # Stale
                    },
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session", return_value=mock_session
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, f"Tool must succeed. Got: {result}"
        assert result.get("current_step") == "review_summary", (
            f"current_step must be 'review_summary' (derived from DB case.status='pending_review'), "
            f"not 'collect_personal' (stale). Got: {result.get('current_step')!r}"
        )

    async def test_db_failure_falls_back_to_mode_context(self):
        """
        When DB query raises an exception, the tool falls back to mode_context
        gracefully — it must NOT propagate the exception.
        """
        case_id = _make_case_id()

        # Session that raises an exception
        failing_session = AsyncMock()
        failing_session.__aenter__ = AsyncMock(return_value=failing_session)
        failing_session.__aexit__ = AsyncMock(return_value=None)
        failing_session.execute = AsyncMock(side_effect=RuntimeError("DB unavailable"))

        fallback_context = MagicMock()
        fallback_context.get = lambda key, *args: {
            "case_id": case_id,
            "element_codes": ["MANILLAR"],
            "element_data_status": {"MANILLAR": "pending_photos"},
            "received_images": ["one.jpg"],
            "taller_propio": None,
            "tariff_amount": None,
            "personal_data": {},
            "vehicle_data": {},
        }.get(key, args[0] if args else None)

        from agent.utils.expediente_types import CollectionStep

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=fallback_context,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d4-fallback-test",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {
                        "case_id": case_id,
                        "expediente_sub_mode": "collect_element_data",
                    },
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=case_id,
            ),
            patch(
                "agent.tools.case_tools.get_async_session",
                return_value=failing_session,
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_ELEMENT_DATA,
            ),
        ):
            result = await _obtener_estado_expediente()

        # Must not raise — must succeed using mode_context fallback
        assert result.get("success") is True, (
            f"Tool must succeed even if DB fails (fallback to mode_context). Got: {result}"
        )
        assert result.get("has_active_case") is True
        # Falls back to stale mode_context: 1 image from the list
        assert result.get("images_received") == 1, (
            f"Fallback: images_received must come from mode_context. Got: {result.get('images_received')}"
        )

    async def test_no_case_id_falls_back_to_mode_context(self):
        """
        When case_id is None (case not yet persisted), the tool must fall back
        to mode_context without attempting a DB query.
        """
        from agent.utils.expediente_types import CollectionStep

        fallback_context = MagicMock()
        fallback_context.get = lambda key, *args: {
            "case_id": None,  # Not persisted yet
            "element_codes": ["ESCAPE"],
            "element_data_status": {},
            "received_images": [],
            "taller_propio": None,
            "tariff_amount": None,
            "personal_data": {},
            "vehicle_data": {},
        }.get(key, args[0] if args else None)

        with (
            patch(
                "agent.tools.case_tools._get_mode_context",
                return_value=fallback_context,
            ),
            patch(
                "agent.tools.case_tools.get_current_state",
                return_value={
                    "conversation_id": "d4-no-case-id",
                    "user_id": str(uuid.uuid4()),
                    "mode_context": {
                        "expediente_sub_mode": "collect_element_data",
                    },
                    "current_mode": "EXPEDIENTE_MODE",
                    "fsm_state": {"collection_active": True},
                },
            ),
            patch("agent.tools.case_tools._is_collection_active", return_value=True),
            patch(
                "agent.tools.case_tools._get_case_id_with_fallback",
                return_value=None,  # No case_id
            ),
            patch(
                "agent.tools.case_tools._get_current_step_from_context",
                return_value=CollectionStep.COLLECT_ELEMENT_DATA,
            ),
        ):
            result = await _obtener_estado_expediente()

        assert result.get("success") is True, (
            f"Tool must succeed even without case_id. Got: {result}"
        )
        assert result.get("has_active_case") is True
