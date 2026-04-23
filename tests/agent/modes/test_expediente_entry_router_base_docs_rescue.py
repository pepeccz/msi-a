"""
Unit tests for entry_router base_docs → collect_personal rescue branch.

Phase 3 of `fix-base-docs-transition-guard`:
- When `sub_mode == collect_base_docs` AND docs sufficient AND user message
  contains personal-data signals (DNI, NIE, email, matrícula, "me llamo",
  "nombre", "marca", "modelo"), the router rescues the turn by routing
  directly to `collect_personal_node`.
- Rescue emits both `expediente_sub_mode == collect_personal` and
  `_transition_to == "collect_personal"` in the Command update.
- Original `user_message` is preserved so the personal node can extract data.
- When docs are insufficient or signal is absent, router DOES NOT rescue.
- Flexible routing for non-base_docs sub-modes is untouched.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.modes.expediente_nodes as expediente_nodes_mod
from agent.modes.expediente_nodes import entry_router
from agent.utils.expediente_types import CollectionStep


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_state(
    case_id: str = "test-case-id",
    sub_mode: str = CollectionStep.COLLECT_BASE_DOCS.value,
    user_message: str = "",
    **extra,
) -> dict:
    base = {
        "case_id": case_id,
        "conversation_id": "conv-1",
        "expediente_sub_mode": sub_mode,
        "user_message": user_message,
        "element_phase": None,
        "current_element_code": None,
        "element_data_status": {},
        "personal_collected": False,
        "vehicle_collected": False,
        "workshop_collected": False,
        "taller_propio": None,
        "messages": [],
        "base_docs_registered": False,
    }
    base.update(extra)
    return base


def _mock_get_session_active_case():
    """get_async_session that returns a case with status 'collecting' (non-terminal)."""
    mock_case = MagicMock()
    mock_case.status = "collecting"

    mock_result = MagicMock()
    mock_result.first.return_value = mock_case

    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _fake():
        yield mock_session

    return _fake


# ---------------------------------------------------------------------------
# Test unit: _has_personal_data_signal (pure)
# ---------------------------------------------------------------------------


class TestHasPersonalDataSignal:
    @pytest.mark.parametrize(
        "msg",
        [
            "mi DNI es 12345678Z",
            "12345678Z",
            "X1234567L",  # NIE
            "juan@example.com",
            "me llamo Juan",
            "Mi nombre es Juan",
            "matrícula 1234ABC",
            "la marca del coche",
            "el modelo es Ibiza",
            "1234ABC",  # bare plate
        ],
    )
    def test_detects_personal_signals(self, msg):
        from agent.modes.expediente_nodes import _has_personal_data_signal

        assert _has_personal_data_signal(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "",
            "hola",
            "buenas",
            "listo",
            "ok gracias",
            "no sé qué hacer",
        ],
    )
    def test_rejects_non_personal(self, msg):
        from agent.modes.expediente_nodes import _has_personal_data_signal

        assert _has_personal_data_signal(msg) is False


# ---------------------------------------------------------------------------
# Router rescue branch
# ---------------------------------------------------------------------------


class TestRouterRescuesToPersonal:
    @pytest.mark.asyncio
    async def test_router_rescues_dni_in_base_docs(self):
        """Sub_mode=base_docs + sufficient docs + DNI → rescue to collect_personal."""
        state = _make_state(
            user_message="mi DNI es 12345678Z",
            base_docs_registered=True,  # short-circuit sufficient
        )

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ):
            cmd = await entry_router(state)

        assert cmd.goto == "collect_personal_node"
        assert cmd.update is not None
        assert cmd.update.get("expediente_sub_mode") == CollectionStep.COLLECT_PERSONAL.value
        assert cmd.update.get("_transition_to") == CollectionStep.COLLECT_PERSONAL.value
        # user_message preserved (NOT rewritten)
        assert "user_message" not in cmd.update or cmd.update["user_message"] == state["user_message"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "msg",
        [
            "juan.perez@example.com",
            "matrícula 1234ABC",
            "me llamo Juan Pérez",
            "mi NIE es X1234567L",
            "la marca es Seat",
        ],
    )
    async def test_router_rescues_email_matricula_address(self, msg):
        state = _make_state(user_message=msg, base_docs_registered=True)

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ):
            cmd = await entry_router(state)

        assert cmd.goto == "collect_personal_node"
        assert cmd.update.get("_transition_to") == CollectionStep.COLLECT_PERSONAL.value

    @pytest.mark.asyncio
    async def test_router_does_not_rescue_insufficient_docs(self):
        """Personal signal + insufficient docs → NO rescue, stays in base_docs flow."""
        state = _make_state(
            user_message="mi DNI es 12345678Z",
            base_docs_registered=False,
        )

        # Force _base_docs_sufficient to return False by patching
        async def _insufficient(*args, **kwargs):
            return False

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ), patch.object(
            expediente_nodes_mod,
            "_base_docs_sufficient",
            new=_insufficient,
        ):
            cmd = await entry_router(state)

        # Must NOT rescue to collect_personal_node
        assert cmd.goto != "collect_personal_node"
        if cmd.update is not None:
            assert cmd.update.get("_transition_to") != CollectionStep.COLLECT_PERSONAL.value

    @pytest.mark.asyncio
    async def test_router_does_not_rescue_non_personal_text(self):
        """No personal signal → no rescue."""
        state = _make_state(
            user_message="hola",
            base_docs_registered=True,
        )

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ):
            cmd = await entry_router(state)

        assert cmd.goto != "collect_personal_node" or (
            cmd.update is None or cmd.update.get("_transition_to") != CollectionStep.COLLECT_PERSONAL.value
        )
        # Should fall through to default routing (target = collect_base_docs_node)
        assert cmd.goto == "collect_base_docs_node"

    @pytest.mark.asyncio
    async def test_router_flexible_routing_unchanged_for_personal_sub_mode(self):
        """sub_mode=collect_personal with vehicle keywords → existing WS6 behavior."""
        state = _make_state(
            sub_mode=CollectionStep.COLLECT_PERSONAL.value,
            user_message="mi matrícula es 1234ABC",
            base_docs_registered=True,
        )

        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ):
            cmd = await entry_router(state)

        # WS6 flexible routing should send us to vehicle (vehicle_hits > personal_hits)
        # or at minimum NOT to collect_personal_node via rescue
        assert cmd.goto == "collect_vehicle_node"


class TestRouterBaseDocsSufficientShortCircuit:
    @pytest.mark.asyncio
    async def test_base_docs_registered_flag_avoids_db_read(self):
        """When state.base_docs_registered is True, _base_docs_sufficient returns True without DB call."""
        from agent.modes.expediente_nodes import _base_docs_sufficient

        state = {"base_docs_registered": True}
        # If short-circuit works, this returns True without hitting DB helpers
        result = await _base_docs_sufficient("case-1", state)
        assert result is True


class TestStructlogEvents:
    """Verify structlog events are emitted for rescue branches."""

    @pytest.mark.asyncio
    async def test_rescue_emits_log_event(self):
        state = _make_state(
            user_message="mi DNI es 12345678Z",
            base_docs_registered=True,
        )

        mock_logger = MagicMock()
        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ), patch.object(expediente_nodes_mod, "logger", mock_logger):
            await entry_router(state)

        info_events = [call.args[0] for call in mock_logger.info.call_args_list]
        assert "base_docs.rescue_to_personal" in info_events

    @pytest.mark.asyncio
    async def test_rescue_skipped_emits_log_event(self):
        state = _make_state(
            user_message="mi DNI es 12345678Z",
            base_docs_registered=False,
        )

        async def _insufficient(*args, **kwargs):
            return False

        mock_logger = MagicMock()
        with patch.object(
            expediente_nodes_mod,
            "get_async_session",
            new=_mock_get_session_active_case(),
        ), patch.object(
            expediente_nodes_mod,
            "_base_docs_sufficient",
            new=_insufficient,
        ), patch.object(expediente_nodes_mod, "logger", mock_logger):
            await entry_router(state)

        info_events = [call.args[0] for call in mock_logger.info.call_args_list]
        assert "base_docs.rescue_skipped_insufficient_docs" in info_events
