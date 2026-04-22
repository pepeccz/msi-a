"""
Unit tests for case_service.py guards and response fields.

Phase 2 TDD:
  2.1/2.2 — empty-dict guard returns EMPTY_DATA_PROVIDED error
  2.3/2.4 — missing-fields response includes missing_field_keys
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.services.case_service import update_personal_data, update_workshop_data
from agent.utils.expediente_types import CollectionStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CASE_ID = "00000000-0000-0000-0000-000000000001"

_FSM_STATE_COLLECT_PERSONAL = {
    "case_id": _FAKE_CASE_ID,
    "current_step": CollectionStep.COLLECT_PERSONAL.value,
    "personal_data": {},
    "vehicle_data": {},
    "taller_propio": None,
    "taller_data": {},
}

_FSM_STATE_COLLECT_VEHICLE = {
    **_FSM_STATE_COLLECT_PERSONAL,
    "current_step": CollectionStep.COLLECT_VEHICLE.value,
}

_MINIMAL_STATE: dict = {}


def _patch_context(step: CollectionStep, case_id: str = _FAKE_CASE_ID, fsm_state: dict | None = None):
    """Return a stack of patches that simulate a live FSM context."""
    fsm = fsm_state or {
        "case_id": case_id,
        "current_step": step.value,
        "personal_data": {},
        "vehicle_data": {},
        "taller_propio": None,
        "taller_data": {},
    }
    return [
        patch("agent.services.case_service.get_mode_context", return_value=fsm),
        patch("agent.services.case_service.get_current_step", return_value=step),
        patch("agent.services.case_service._get_case_id_with_fallback", return_value=case_id),
    ]


# ---------------------------------------------------------------------------
# 2.1 / 2.2  Empty-dict guard
# ---------------------------------------------------------------------------

class TestEmptyDictGuard:
    """
    The service must reject datos_personales={} or datos_vehiculo={} with
    error_code="EMPTY_DATA_PROVIDED" instead of proceeding silently.
    """

    @pytest.mark.asyncio
    async def test_empty_datos_personales_returns_error(self):
        patches = _patch_context(CollectionStep.COLLECT_PERSONAL)
        with patches[0], patches[1], patches[2]:
            result = await update_personal_data(
                datos_personales={},
                datos_vehiculo=None,
                state=_MINIMAL_STATE,
            )
        assert result.get("error_code") == "EMPTY_DATA_PROVIDED", (
            f"Expected EMPTY_DATA_PROVIDED, got: {result.get('error_code')!r}"
        )
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_empty_datos_vehiculo_returns_error(self):
        patches = _patch_context(CollectionStep.COLLECT_VEHICLE)
        with patches[0], patches[1], patches[2]:
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo={},
                state=_MINIMAL_STATE,
            )
        assert result.get("error_code") == "EMPTY_DATA_PROVIDED", (
            f"Expected EMPTY_DATA_PROVIDED, got: {result.get('error_code')!r}"
        )
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_none_datos_personales_returns_different_error(self):
        """datos_personales=None with datos_vehiculo=None → existing NO_DATA_PROVIDED, not EMPTY_DATA_PROVIDED."""
        patches = _patch_context(CollectionStep.COLLECT_PERSONAL)
        with patches[0], patches[1], patches[2]:
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo=None,
                state=_MINIMAL_STATE,
            )
        assert result.get("error_code") != "EMPTY_DATA_PROVIDED"
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_nonempty_datos_personales_does_not_trigger_guard(self):
        """Non-empty dict must NOT trigger EMPTY_DATA_PROVIDED (may fail for other reasons)."""
        patches = _patch_context(CollectionStep.COLLECT_PERSONAL)
        with patches[0], patches[1], patches[2]:
            result = await update_personal_data(
                datos_personales={"nombre": "Juan"},
                datos_vehiculo=None,
                state=_MINIMAL_STATE,
            )
        # The guard must NOT fire — any other error is acceptable here
        assert result.get("error_code") != "EMPTY_DATA_PROVIDED"


# ---------------------------------------------------------------------------
# 2.3 / 2.4  missing_field_keys in response
# ---------------------------------------------------------------------------

FULL_PERSONAL = {
    "nombre": "Pepe",
    "apellidos": "Cabeza Cruz",
    "email": "pepe@example.com",
    "dni_cif": "77429548W",
    "domicilio_calle": "Calle Mayor 12",
    "domicilio_localidad": "Mijas",
    "domicilio_provincia": "Málaga",
    "domicilio_cp": "29650",
    "itv_nombre": "ITV Guadalhorce",
}

FULL_VEHICLE = {
    "marca": "Honda",
    "modelo": "CBR 1000",
    "anio": "2019",
    "matricula": "1234ABC",
    "bastidor": "WVWZZZ3CZWE123456",
}


class TestMissingFieldKeysInResponse:
    """
    When the service returns a missing-fields response, the dict must contain
    both `missing_fields` (human labels) AND `missing_field_keys` (field_keys).
    """

    @pytest.mark.asyncio
    async def test_personal_data_missing_field_response_includes_field_keys(self):
        """Partial personal data → validation rejects before commit, response has missing_field_keys.

        After fix-vehicle-data-hallucination (atomic validate-then-commit):
        partial data now returns success=False — nothing is persisted.
        """
        # FSM has empty personal_data so the incoming data is NEW (not idempotent path)
        partial = {"nombre": "Pepe", "apellidos": "Cabeza"}
        fsm = {
            "case_id": _FAKE_CASE_ID,
            "current_step": CollectionStep.COLLECT_PERSONAL.value,
            "personal_data": {},  # empty so incoming is treated as new data
            "vehicle_data": {},
            "taller_propio": None,
            "taller_data": {},
        }
        patches = _patch_context(CollectionStep.COLLECT_PERSONAL, fsm_state=fsm)
        mock_session_cm = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session_cm)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patches[0], patches[1], patches[2], \
             patch("agent.services.case_service.get_async_session", return_value=mock_session_ctx):
            result = await update_personal_data(
                datos_personales=partial,
                datos_vehiculo=None,
                state=_MINIMAL_STATE,
            )

        # Atomicity: partial data must not persist → success=False
        assert result.get("success") is False, (
            f"Partial personal data must return success=False (atomic validate-then-commit). Got: {result}"
        )
        assert "missing_field_keys" in result, (
            f"Response is missing 'missing_field_keys' key. Got: {list(result.keys())}"
        )
        missing_keys = result["missing_field_keys"]
        assert isinstance(missing_keys, list)
        assert "itv_nombre" in missing_keys
        # session.commit must NOT have been called
        mock_session_cm.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_vehicle_data_missing_field_response_includes_field_keys(self):
        """Partial vehicle data → validation rejects before commit, response has missing_field_keys.

        After fix-vehicle-data-hallucination (atomic validate-then-commit):
        partial data now returns success=False — nothing is persisted.
        """
        partial = {"marca": "Honda", "modelo": "CBR"}
        fsm = {
            "case_id": _FAKE_CASE_ID,
            "current_step": CollectionStep.COLLECT_VEHICLE.value,
            "personal_data": {},
            "vehicle_data": {},  # empty so incoming is treated as new data
            "taller_propio": None,
            "taller_data": {},
        }
        patches = _patch_context(CollectionStep.COLLECT_VEHICLE, fsm_state=fsm)
        mock_session_cm = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session_cm)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patches[0], patches[1], patches[2], \
             patch("agent.services.case_service.get_async_session", return_value=mock_session_ctx):
            result = await update_personal_data(
                datos_personales=None,
                datos_vehiculo=partial,
                state=_MINIMAL_STATE,
            )

        # Atomicity: partial data must not persist → success=False
        assert result.get("success") is False, (
            f"Partial vehicle data must return success=False (atomic validate-then-commit). Got: {result}"
        )
        assert "missing_field_keys" in result, (
            f"Response missing 'missing_field_keys'. Got keys: {list(result.keys())}"
        )
        missing_keys = result["missing_field_keys"]
        assert "bastidor" in missing_keys
        assert "matricula" in missing_keys
        # session.commit must NOT have been called
        mock_session_cm.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_workshop_missing_field_response_includes_field_keys(self):
        """Partial workshop data → response has missing_field_keys."""
        partial = {"nombre": "Taller García", "responsable": "Luis"}
        patches = _patch_context(CollectionStep.COLLECT_WORKSHOP)
        fake_case = MagicMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.get = AsyncMock(return_value=fake_case)
        mock_session_cm.commit = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session_cm)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patches[0], patches[1], patches[2], \
             patch("agent.services.case_service.get_async_session", return_value=mock_session_ctx):
            result = await update_workshop_data(
                taller_propio=True,
                datos_taller=partial,
                state=_MINIMAL_STATE,
            )

        assert result.get("success") is True
        assert "missing_field_keys" in result, (
            f"Workshop response missing 'missing_field_keys'. Got: {list(result.keys())}"
        )
        missing_keys = result["missing_field_keys"]
        assert isinstance(missing_keys, list)
        assert "registro_industrial" in missing_keys
