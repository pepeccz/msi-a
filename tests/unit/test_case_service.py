"""
Unit tests for agent/services/case_service.py

Tests each public service method using pytest + unittest.mock.
No real DB, Redis, or LLM access — all external dependencies are mocked.

Pattern:
  - Set ContextVar state via set_current_state / clear_current_state
  - Mock DB sessions with AsyncMock
  - Assert return dicts match expected shapes
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.utils.expediente_types import CollectionStep


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_modules():
    """Prevent module cache pollution between tests."""
    yield
    # Remove any cached service module so imports are fresh
    for key in list(sys.modules.keys()):
        if "case_service" in key:
            del sys.modules[key]


@pytest.fixture(autouse=True)
def reset_context():
    """Clear the shared ContextVar before and after each test."""
    from agent.state.helpers import clear_current_state

    clear_current_state()
    yield
    clear_current_state()


def _set_state(state: dict) -> None:
    from agent.state.helpers import set_current_state

    set_current_state(state)


def _make_expediente_state(
    sub_mode: str = CollectionStep.IDLE.value,
    case_id: str | None = None,
    element_codes: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "current_mode": "EXPEDIENTE_MODE",
        "conversation_id": "conv-test-001",
        "user_id": "user-uuid-001",
        "client_type": "particular",
        "fsm_state": {},
        "mode_context": {
            "expediente_sub_mode": sub_mode,
            "case_id": case_id,
            "element_codes": element_codes or [],
            **extra,
        },
    }


# ---------------------------------------------------------------------------
# cancel_case
# ---------------------------------------------------------------------------


class TestCancelCase:
    @pytest.mark.asyncio
    async def test_cancel_no_case_id_returns_error(self):
        """When mode_context has no case_id, return NO_ACTIVE_CASE error."""
        state = _make_expediente_state(sub_mode=CollectionStep.IDLE.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.cancel_case(
            motivo="test",
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "NO_ACTIVE_CASE"

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_is_idempotent(self):
        """When case is already cancelled, return success without DB write."""
        case_id = "case-001"
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id=case_id,
        )
        _set_state(state)

        mock_case = MagicMock()
        mock_case.status = "cancelled"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_case)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        from agent.services import case_service

        with patch("agent.services.case_service.get_async_session", return_value=mock_session):
            result = await case_service.cancel_case(
                motivo="test",
                fsm_state={},
                state=state,
            )

        assert result["success"] is True
        assert result.get("already_cancelled") is True
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_active_case_sets_cancelled_status(self):
        """Cancelling an active case commits status=cancelled to DB."""
        case_id = "case-002"
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id=case_id,
        )
        _set_state(state)

        mock_case = MagicMock()
        mock_case.status = "collecting"
        mock_case.notes = ""

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_case)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        from agent.services import case_service

        with patch("agent.services.case_service.get_async_session", return_value=mock_session):
            result = await case_service.cancel_case(
                motivo="Usuario no desea continuar",
                fsm_state={},
                state=state,
            )

        assert result["success"] is True
        assert mock_case.status == "cancelled"
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_case_status
# ---------------------------------------------------------------------------


class TestGetCaseStatus:
    @pytest.mark.asyncio
    async def test_no_active_collection_returns_no_active_case(self):
        """When FSM is IDLE, return has_active_case=False without DB access."""
        state = _make_expediente_state(sub_mode=CollectionStep.IDLE.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.get_case_status(fsm_state={}, state=state)

        assert result["success"] is True
        assert result["has_active_case"] is False

    @pytest.mark.asyncio
    async def test_active_collection_returns_case_status(self):
        """When collection is active and DB returns case, build status dict."""
        case_id = "case-status-001"
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id=case_id,
        )
        _set_state(state)

        mock_image = MagicMock()
        mock_element_data = MagicMock()
        mock_element_data.element_code = "ESCAPE"
        mock_element_data.status = "completed"

        mock_case = MagicMock()
        mock_case.element_codes = ["ESCAPE"]
        mock_case.images = [mock_image]
        mock_case.element_data = [mock_element_data]
        mock_case.taller_propio = None
        mock_case.taller_nombre = None
        mock_case.tariff_amount = None
        mock_case.itv_nombre = None
        mock_case.status = "collecting"
        mock_case.vehiculo_marca = None
        mock_case.vehiculo_modelo = None
        mock_case.vehiculo_anio = None
        mock_case.vehiculo_matricula = None
        mock_case.vehiculo_bastidor = None
        mock_case.user = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_case)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        from agent.services import case_service

        with patch("agent.services.case_service.get_async_session", return_value=mock_session):
            result = await case_service.get_case_status(
                fsm_state={},
                state=state,
            )

        assert result["success"] is True
        assert result["has_active_case"] is True
        assert result["images_received"] == 1
        assert result["elements"] == ["ESCAPE"]
        assert result["data_source"] == "db"


# ---------------------------------------------------------------------------
# update_personal_data
# ---------------------------------------------------------------------------


class TestUpdatePersonalData:
    @pytest.mark.asyncio
    async def test_no_data_returns_validation_error(self):
        """Calling with both params None returns NO_DATA_PROVIDED error."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-pers-001",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.update_personal_data(
            datos_personales=None,
            datos_vehiculo=None,
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "NO_DATA_PROVIDED"

    @pytest.mark.asyncio
    async def test_no_case_id_returns_no_active_case(self):
        """When there is no case_id in context, return NO_ACTIVE_CASE."""
        state = _make_expediente_state(sub_mode=CollectionStep.COLLECT_PERSONAL.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.update_personal_data(
            datos_personales={"nombre": "Ana"},
            datos_vehiculo=None,
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "NO_ACTIVE_CASE"

    @pytest.mark.asyncio
    async def test_wrong_phase_returns_wrong_phase_error(self):
        """Calling outside COLLECT_PERSONAL / COLLECT_VEHICLE returns WRONG_PHASE."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id="case-pers-002",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.update_personal_data(
            datos_personales={"nombre": "Ana"},
            datos_vehiculo=None,
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "WRONG_PHASE"

    @pytest.mark.asyncio
    async def test_invalid_email_returns_validation_error(self):
        """Invalid email triggers INVALID_EMAIL before touching DB."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-pers-003",
        )
        _set_state(state)

        from agent.services import case_service

        with patch(
            "agent.utils.tool_decorators.validate_email",
            return_value=(False, "formato incorrecto"),
        ):
            result = await case_service.update_personal_data(
                datos_personales={"email": "not-valid"},
                datos_vehiculo=None,
                fsm_state={},
                state=state,
            )

        assert result["success"] is False
        assert result["error_code"] == "INVALID_EMAIL"


# ---------------------------------------------------------------------------
# update_workshop_data
# ---------------------------------------------------------------------------


class TestUpdateWorkshopData:
    @pytest.mark.asyncio
    async def test_no_case_id_returns_error(self):
        """Without a case_id, return NO_ACTIVE_CASE."""
        state = _make_expediente_state(sub_mode=CollectionStep.COLLECT_WORKSHOP.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.update_workshop_data(
            taller_propio=False,
            datos_taller=None,
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "NO_ACTIVE_CASE"

    @pytest.mark.asyncio
    async def test_wrong_phase_returns_error(self):
        """Calling outside COLLECT_WORKSHOP returns WRONG_PHASE."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-ws-001",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.update_workshop_data(
            taller_propio=False,
            datos_taller=None,
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "WRONG_PHASE"

    @pytest.mark.asyncio
    async def test_msi_certificate_transitions_to_review(self):
        """taller_propio=False should transition to REVIEW_SUMMARY."""
        case_id = "case-ws-002"
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
            case_id=case_id,
        )
        _set_state(state)

        mock_case = MagicMock()
        mock_case.taller_propio = None

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_case)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        from agent.services import case_service

        with patch("agent.services.case_service.get_async_session", return_value=mock_session):
            result = await case_service.update_workshop_data(
                taller_propio=False,
                datos_taller=None,
                fsm_state={},
                state=state,
            )

        assert result["success"] is True
        assert result["next_step"] == CollectionStep.REVIEW_SUMMARY.value
        assert result["_state_update"]["can_narrate_completion"] is True


# ---------------------------------------------------------------------------
# edit_case
# ---------------------------------------------------------------------------


class TestEditCase:
    @pytest.mark.asyncio
    async def test_wrong_phase_returns_error(self):
        """Editing is only allowed from REVIEW_SUMMARY."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-edit-001",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.edit_case(
            seccion="vehiculo",
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "WRONG_PHASE"

    @pytest.mark.asyncio
    async def test_restricted_section_returns_error(self):
        """Trying to edit 'elementos' section is rejected."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id="case-edit-002",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.edit_case(
            seccion="elementos",
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result.get("error") == "NO_PUEDE_EDITAR_ELEMENTOS"

    @pytest.mark.asyncio
    async def test_unknown_section_returns_error(self):
        """Unrecognised section name returns INVALID_SECTION."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id="case-edit-003",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.edit_case(
            seccion="desconocida",
            fsm_state={},
            state=state,
        )

        assert result["success"] is False
        assert result["error_code"] == "INVALID_SECTION"


# ---------------------------------------------------------------------------
# finalize_case
# ---------------------------------------------------------------------------


class TestFinalizeCase:
    @pytest.mark.asyncio
    async def test_no_case_id_returns_error(self):
        """Without case_id, return NO_ACTIVE_CASE."""
        state = _make_expediente_state(sub_mode=CollectionStep.REVIEW_SUMMARY.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.finalize_case(fsm_state={}, state=state)

        assert result["success"] is False
        assert result["error_code"] == "NO_ACTIVE_CASE"

    @pytest.mark.asyncio
    async def test_wrong_phase_returns_error(self):
        """Calling outside REVIEW_SUMMARY returns WRONG_PHASE."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
            case_id="case-fin-001",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.finalize_case(fsm_state={}, state=state)

        assert result["success"] is False
        assert result["error_code"] == "WRONG_PHASE"

    @pytest.mark.asyncio
    async def test_already_finalized_is_idempotent(self):
        """Calling finalize twice returns success without re-processing."""
        case_id = "case-fin-002"
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id=case_id,
        )
        _set_state(state)

        mock_case = MagicMock()
        mock_case.status = "pending_review"
        mock_case.category = MagicMock(slug="motos-part")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_case)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        from agent.services import case_service

        with patch("agent.services.case_service.get_async_session", return_value=mock_session):
            result = await case_service.finalize_case(fsm_state={}, state=state)

        assert result["success"] is True
        assert result.get("already_finalized") is True
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_finalization(self):
        """Normal finalization commits status=pending_review and notifies Chatwoot."""
        case_id = "case-fin-003"
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id=case_id,
        )
        state["conversation_id"] = "42"
        _set_state(state)

        mock_case = MagicMock()
        mock_case.status = "collecting"
        mock_case.metadata_ = {}
        mock_case.element_codes = ["ESCAPE"]
        mock_case.taller_propio = False
        mock_case.tariff_amount = "410.00"
        mock_case.itv_nombre = "ITV Madrid"
        mock_case.category = MagicMock(slug="motos-part")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_case)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_chatwoot = AsyncMock()
        mock_chatwoot.add_private_note = AsyncMock()
        mock_chatwoot.add_labels = AsyncMock()

        from agent.services import case_service

        with (
            patch("agent.services.case_service.get_async_session", return_value=mock_session),
            patch("shared.chatwoot_client.ChatwootClient", return_value=mock_chatwoot),
        ):
            result = await case_service.finalize_case(fsm_state={}, state=state)

        assert result["success"] is True
        assert mock_case.status == "pending_review"
        assert result["_state_update"]["case_finalized"] is True
        assert result["_state_update"]["can_narrate_completion"] is True


# ---------------------------------------------------------------------------
# handle_query_during_case
# ---------------------------------------------------------------------------


class TestHandleQueryDuringCase:
    @pytest.mark.asyncio
    async def test_responder_with_active_case(self):
        """responder action with active case returns step context message."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-q-001",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.handle_query_during_case(
            consulta="¿Cuánto tarda?",
            accion="responder",
            fsm_state={},
            state=state,
        )

        assert result["success"] is True
        assert result["has_active_case"] is True
        assert "datos personales" in result["message"]

    @pytest.mark.asyncio
    async def test_pausar_returns_paused_flag(self):
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_VEHICLE.value,
            case_id="case-q-002",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.handle_query_during_case(
            consulta=None,
            accion="pausar",
            fsm_state={},
            state=state,
        )

        assert result["success"] is True
        assert result.get("paused") is True

    @pytest.mark.asyncio
    async def test_reanudar_returns_resumed_flag(self):
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
            case_id="case-q-003",
        )
        _set_state(state)

        from agent.services import case_service

        result = await case_service.handle_query_during_case(
            consulta=None,
            accion="reanudar",
            fsm_state={},
            state=state,
        )

        assert result["success"] is True
        assert result.get("resumed") is True

    @pytest.mark.asyncio
    async def test_no_active_case_responds_freely(self):
        """When FSM is idle, tool tells LLM to respond freely."""
        state = _make_expediente_state(sub_mode=CollectionStep.IDLE.value)
        _set_state(state)

        from agent.services import case_service

        result = await case_service.handle_query_during_case(
            consulta="¿Hola?",
            accion="responder",
            fsm_state={},
            state=state,
        )

        assert result["success"] is True
        assert result["has_active_case"] is False


# ---------------------------------------------------------------------------
# Tool wrapper smoke-test: tools call service and propagate result
# ---------------------------------------------------------------------------


class TestCaseToolWrappers:
    """Smoke-tests that verify each tool delegates to case_service correctly."""

    @pytest.mark.asyncio
    async def test_cancelar_expediente_tool_delegates(self):
        """cancelar_expediente tool calls cancel_case and returns its result."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            case_id="case-w-001",
        )

        expected = {"success": True, "message": "Cancelado."}

        from agent.tools.case_tools import cancelar_expediente
        from agent.services import case_service

        with (
            patch("agent.state.helpers.get_current_state", return_value=state),
            patch.object(case_service, "cancel_case", AsyncMock(return_value=expected)) as mock_svc,
        ):
            result = await cancelar_expediente.ainvoke({"motivo": "test"})

        mock_svc.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_obtener_estado_expediente_tool_delegates(self):
        """obtener_estado_expediente delegates to get_case_status."""
        state = _make_expediente_state(sub_mode=CollectionStep.IDLE.value)
        expected = {"success": True, "has_active_case": False}

        from agent.tools.case_tools import obtener_estado_expediente
        from agent.services import case_service

        with (
            patch("agent.state.helpers.get_current_state", return_value=state),
            patch.object(case_service, "get_case_status", AsyncMock(return_value=expected)) as mock_svc,
        ):
            result = await obtener_estado_expediente.ainvoke({})

        mock_svc.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_finalizar_expediente_tool_delegates(self):
        """finalizar_expediente delegates to finalize_case."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id="case-w-003",
        )
        expected = {"success": True, "case_id": "case-w-003"}

        from agent.tools.case_tools import finalizar_expediente
        from agent.services import case_service

        with (
            patch("agent.state.helpers.get_current_state", return_value=state),
            patch.object(case_service, "finalize_case", AsyncMock(return_value=expected)) as mock_svc,
        ):
            result = await finalizar_expediente.ainvoke({})

        mock_svc.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_editar_expediente_tool_delegates(self):
        """editar_expediente delegates to edit_case."""
        state = _make_expediente_state(
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            case_id="case-w-004",
        )
        expected = {"success": True, "next_step": "collect_personal"}

        from agent.tools.case_tools import editar_expediente
        from agent.services import case_service

        with (
            patch("agent.state.helpers.get_current_state", return_value=state),
            patch.object(case_service, "edit_case", AsyncMock(return_value=expected)) as mock_svc,
        ):
            result = await editar_expediente.ainvoke({"seccion": "personal"})

        mock_svc.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_tools_handle_missing_state(self):
        """All tools return error when get_current_state returns None."""
        from agent.tools.case_tools import (
            cancelar_expediente,
            finalizar_expediente,
            obtener_estado_expediente,
        )

        with patch("agent.state.helpers.get_current_state", return_value=None):
            r1 = await cancelar_expediente.ainvoke({})
            r2 = await finalizar_expediente.ainvoke({})
            r3 = await obtener_estado_expediente.ainvoke({})

        for r in (r1, r2, r3):
            assert r.get("success") is False or r.get("error_code") is not None
