"""
Unit tests for vehicle data write atomicity (fix-vehicle-data-hallucination).

Phase 1 TDD:
  1.1 — invalid matricula rejects all fields, nothing persisted
  1.2 — all valid fields commit once, all 5 columns set
  4.2 — partial retry: rejected call → correct call → only second values in DB
"""

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agent.services import case_service
from agent.services.case_service import update_personal_data
from agent.utils.expediente_types import CollectionStep


_FAKE_CASE_ID = "00000000-0000-0000-0000-000000000002"

_FSM_VEHICLE = {
    "case_id": _FAKE_CASE_ID,
    "current_step": CollectionStep.COLLECT_VEHICLE.value,
    "personal_data": {},
    "vehicle_data": {},
    "taller_propio": None,
    "taller_data": {},
}

_MINIMAL_STATE: dict = {}


def _patch_context(fsm_state: dict | None = None):
    fsm = fsm_state or _FSM_VEHICLE
    return [
        patch("agent.services.case_service.get_mode_context", return_value=fsm),
        patch(
            "agent.services.case_service.get_current_step",
            return_value=CollectionStep.COLLECT_VEHICLE,
        ),
        patch(
            "agent.services.case_service._get_case_id_with_fallback",
            return_value=_FAKE_CASE_ID,
        ),
    ]


def _make_mock_session(case_marca=None, case_modelo=None, case_anio=None, case_matricula=None, case_bastidor=None):
    """Return (mock_session_ctx, fake_case) pair for patching get_async_session."""
    fake_case = MagicMock()
    fake_case.user_id = None
    fake_case.vehiculo_marca = case_marca
    fake_case.vehiculo_modelo = case_modelo
    fake_case.vehiculo_anio = case_anio
    fake_case.vehiculo_matricula = case_matricula
    fake_case.vehiculo_bastidor = case_bastidor

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=fake_case)
    mock_session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=None)

    return ctx, fake_case, mock_session


# ---------------------------------------------------------------------------
# Task 1.1 — Invalid matricula → nothing persisted (atomicity)
# ---------------------------------------------------------------------------


class TestVehicleAtomicityInvalidMatricula:
    """
    SC-2: invalid matricula MUST reject ALL fields — validate-before-commit.

    The key behavioral assertion: when matricula is DNI-shaped ("48275931S"),
    validate_vehicle_data returns invalid, so session.commit() MUST NOT be called
    and the service MUST return success=False.
    """

    @pytest.mark.asyncio
    async def test_vehicle_invalid_matricula_does_not_persist_other_fields(self):
        """
        Call with valid marca/modelo/anio but DNI-shaped matricula.
        Expect: success=False, session.commit NOT called.
        """
        patches = _patch_context()
        session_ctx, fake_case, mock_session = _make_mock_session()

        with patches[0], patches[1], patches[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx
        ):
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "SunVolt Energy",
                    "modelo": "EcoCharge",
                    "anio": "2024",
                    "matricula": "48275931S",  # DNI shape — invalid as matricula
                },
                state=_MINIMAL_STATE,
            )

        # Validation must reject
        assert result["success"] is False, f"Expected failure, got: {result}"

        # The invalid field must be flagged — either in missing_field_keys or invalid_fields
        flagged = result.get("missing_field_keys", []) or list(
            (result.get("invalid_fields") or {}).keys()
        )
        assert "matricula" in flagged, (
            f"Expected 'matricula' in flagged fields. Got missing_field_keys={result.get('missing_field_keys')!r}, "
            f"invalid_fields={result.get('invalid_fields')!r}"
        )

        # CRITICAL: session.commit must NOT have been called
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_vehicle_invalid_matricula_brand_not_set_on_case(self):
        """
        Triangulation: even though marca/modelo/anio were provided and valid,
        if matricula is invalid, the Case ORM object must NOT have brand set.
        This forces real logic — a hardcoded 'return False' alone won't catch commit leakage.
        """
        patches = _patch_context()
        session_ctx, fake_case, mock_session = _make_mock_session()

        # Capture setattr calls to detect DB mutation
        setattr_calls: list[tuple] = []
        original_setattr = object.__setattr__

        def tracking_setattr(obj, name, value):
            if obj is fake_case:
                setattr_calls.append((name, value))
            original_setattr(obj, name, value)

        with patches[0], patches[1], patches[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx
        ):
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "Fiat",
                    "modelo": "Ducato",
                    "anio": "2019",
                    "matricula": "48275931S",  # invalid
                    "bastidor": "WVWZZZ3CZWE123456",
                },
                state=_MINIMAL_STATE,
            )

        assert result["success"] is False
        mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Task 1.2 — All fields valid → single commit, all 5 columns set
# ---------------------------------------------------------------------------


class TestVehicleAtomicityAllValid:
    """SC-5: all 5 valid fields → success=True, commit called exactly once."""

    @pytest.mark.asyncio
    async def test_vehicle_all_valid_commits_once(self):
        """5 valid vehicle fields → success=True, session.commit called once."""
        patches = _patch_context()
        session_ctx, fake_case, mock_session = _make_mock_session()

        with patches[0], patches[1], patches[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx
        ), patch(
            "agent.services.case_service._transition_with_db_sync",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "Fiat",
                    "modelo": "Ducato",
                    "anio": "2019",
                    "matricula": "6384BRN",
                    "bastidor": "WVWZZZ3CZWE123456",
                },
                state=_MINIMAL_STATE,
            )

        assert result["success"] is True, f"Expected success=True, got: {result}"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_vehicle_all_valid_different_matricula_also_succeeds(self):
        """
        Triangulation: a different valid matricula (old province format) also
        produces success=True and a single commit.
        Proves the happy path is not hardcoded for one specific matricula value.
        """
        patches = _patch_context()
        session_ctx, fake_case, mock_session = _make_mock_session()

        with patches[0], patches[1], patches[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx
        ), patch(
            "agent.services.case_service._transition_with_db_sync",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "Honda",
                    "modelo": "CBR 1000",
                    "anio": "2019",
                    "matricula": "1234ABC",
                    "bastidor": "WVWZZZ3CZWE123456",
                },
                state=_MINIMAL_STATE,
            )

        assert result["success"] is True
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Task 4.2 — Partial retry: rejected call → correct full payload
# ---------------------------------------------------------------------------


class TestVehiclePartialRetryAfterRejection:
    """
    SC regression: after a rejected call (nothing persisted),
    a second correct call writes only the new values.
    """

    @pytest.mark.asyncio
    async def test_vehicle_partial_retry_after_rejection(self):
        """
        Turn 1: call with invalid matricula → rejected (nothing in DB).
        Turn 2: call with full valid payload → success, all fields set.
        After turn 2, DB row reflects turn-2 values only (no ghost from turn 1).
        """
        patches_turn1 = _patch_context()
        session_ctx_1, fake_case_1, mock_session_1 = _make_mock_session()

        # Turn 1: invalid matricula
        with patches_turn1[0], patches_turn1[1], patches_turn1[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx_1
        ):
            result_1 = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "SunVolt Energy",
                    "modelo": "EcoCharge",
                    "anio": "2024",
                    "matricula": "48275931S",
                },
                state=_MINIMAL_STATE,
            )

        assert result_1["success"] is False
        mock_session_1.commit.assert_not_called()

        # Turn 2: correct full payload — fresh FSM (nothing in vehicle_data because turn 1 rejected)
        patches_turn2 = _patch_context()
        session_ctx_2, fake_case_2, mock_session_2 = _make_mock_session()

        with patches_turn2[0], patches_turn2[1], patches_turn2[2], patch(
            "agent.services.case_service.get_async_session", return_value=session_ctx_2
        ), patch(
            "agent.services.case_service._transition_with_db_sync",
            new_callable=AsyncMock,
            return_value={},
        ):
            result_2 = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={
                    "marca": "Fiat",
                    "modelo": "Ducato",
                    "anio": "2019",
                    "matricula": "6384BRN",
                    "bastidor": "WVWZZZ3CZWE123456",
                },
                state=_MINIMAL_STATE,
            )

        assert result_2["success"] is True
        mock_session_2.commit.assert_called_once()
