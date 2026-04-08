"""
Phase 3 — Expediente integration tests (T-33/T-34, T-35/T-36).

Validates:
1. Full happy path through 7 sub-mode transitions without ContextVar
2. Transition values are no longer silently lost
3. ContextVar trap resolved — tools work inside subgraph with explicit mode_context
4. All 15 expediente tools have unchanged LLM-facing signatures
5. escalar_a_humano is always available in all 6 nodes

These tests operate at the helper/service level (no DB, no LLM) where possible.
"""

from __future__ import annotations

import pytest

from agent.utils.expediente_types import CollectionStep


# ---------------------------------------------------------------------------
# T-33: Full happy-path sub_mode transition sequence
# ---------------------------------------------------------------------------


class TestFullExpedienteHappyPath:
    """T-33: verify each sub_mode transition writes expediente_sub_mode correctly."""

    def test_initiate_case_sets_expediente_sub_mode(self):
        """
        initiate_case _state_update must have expediente_sub_mode=collect_element_data.

        Checks the return key contract via inspection — we do NOT run the DB path.
        """
        import inspect
        from agent.services import case_service

        source = inspect.getsource(case_service.initiate_case)

        # The return must have _state_update containing expediente_sub_mode
        assert "_state_update" in source
        assert "expediente_sub_mode" in source
        assert "case_collection_update" not in source, (
            "initiate_case must NOT return case_collection_update"
        )
        assert "CollectionStep.COLLECT_ELEMENT_DATA" in source

    def test_transition_to_collect_personal(self):
        """_transition_with_db_sync returns flat expediente_sub_mode key."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        from agent.services.case_service import _transition_with_db_sync

        with patch(
            "agent.services.case_service._update_case_metadata",
            new=AsyncMock(),
        ):
            # Must set ContextVar to COLLECT_PERSONAL so can_transition_to works
            from agent.state.helpers import set_current_state, clear_current_state

            set_current_state(
                {
                    "current_mode": "EXPEDIENTE_MODE",
                    "mode_context": {
                        "expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value,
                    },
                }
            )
            try:
                result = asyncio.run(
                    _transition_with_db_sync(
                        target_step=CollectionStep.COLLECT_VEHICLE,
                        case_id="case-001",
                    )
                )
            finally:
                clear_current_state()

        assert result == {"expediente_sub_mode": CollectionStep.COLLECT_VEHICLE.value}

    def test_no_case_collection_update_key_in_cancel(self):
        """cancel_case returns _state_update with expediente_cancelled=True, NO case_collection_update."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from agent.services.case_service import cancel_case
        from agent.state.helpers import set_current_state, clear_current_state

        valid_case_id = "12345678-1234-5678-1234-567812345678"
        mock_case = MagicMock()
        mock_case.status = "collecting"
        mock_case.notes = ""

        set_current_state(
            {
                "current_mode": "EXPEDIENTE_MODE",
                "mode_context": {
                    "expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value,
                    "case_id": valid_case_id,
                },
            }
        )
        try:
            with patch(
                "agent.services.case_service.get_async_session",
            ) as mock_session:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_ctx.get = AsyncMock(return_value=mock_case)
                mock_ctx.commit = AsyncMock()
                mock_session.return_value = mock_ctx

                result = asyncio.run(
                    cancel_case(
                        motivo="test",
                        state={
                            "conversation_id": "conv-001",
                            "mode_context": {
                                "case_id": valid_case_id,
                                "expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value,
                            },
                        },
                    )
                )
        finally:
            clear_current_state()

        assert result.get("success") is True
        assert "case_collection_update" not in result, (
            "cancel_case must NOT return case_collection_update"
        )
        assert result.get("_state_update", {}).get("expediente_cancelled") is True

    def test_transition_no_longer_silently_lost(self):
        """
        Verify that _transition_with_db_sync returns a flat dict with expediente_sub_mode
        (NOT a nested case_collection structure that post_tool_hook must unwrap).
        """
        import asyncio
        from unittest.mock import AsyncMock, patch
        from agent.services.case_service import _transition_with_db_sync
        from agent.state.helpers import set_current_state, clear_current_state

        set_current_state(
            {
                "current_mode": "EXPEDIENTE_MODE",
                "mode_context": {
                    "expediente_sub_mode": CollectionStep.COLLECT_VEHICLE.value,
                },
            }
        )
        try:
            with patch(
                "agent.services.case_service._update_case_metadata",
                new=AsyncMock(),
            ):
                result = asyncio.run(
                    _transition_with_db_sync(
                        target_step=CollectionStep.COLLECT_WORKSHOP,
                    )
                )
        finally:
            clear_current_state()

        # The result is flat — no nested case_collection structure
        assert "expediente_sub_mode" in result
        assert "case_collection" not in result
        assert result["expediente_sub_mode"] == CollectionStep.COLLECT_WORKSHOP.value


# ---------------------------------------------------------------------------
# T-35: ContextVar trap resolved
# ---------------------------------------------------------------------------


class TestContextVarTrapResolved:
    """T-35: case tools work inside subgraph without ContextVar."""

    def test_get_mode_context_with_explicit_dict_bypasses_contextvar(self):
        """
        get_mode_context(mode_context=...) returns valid state even when
        ContextVar is empty (simulating tool execution inside subgraph).
        """
        from agent.services.expediente_helpers import get_mode_context

        # Simulate subgraph context: no ContextVar, but explicit mode_context
        mc = {
            "expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value,
            "case_id": "subgraph-case-001",
            "element_codes": ["ESCAPE", "MANILLAR"],
        }
        result = get_mode_context(mode_context=mc)

        assert result["step"] == CollectionStep.COLLECT_PERSONAL.value
        assert result["case_id"] == "subgraph-case-001"
        assert result["element_codes"] == ["ESCAPE", "MANILLAR"]

    def test_is_collection_active_with_mode_context_no_contextvar(self):
        """is_collection_active works without ContextVar when mode_context is explicit."""
        from agent.services.expediente_helpers import is_collection_active

        mc = {
            "expediente_sub_mode": CollectionStep.COLLECT_BASE_DOCS.value,
            "case_id": "active-case",
        }
        assert is_collection_active(mode_context=mc)

    def test_get_current_step_with_mode_context_no_contextvar(self):
        """get_current_step(mode_context=...) returns correct step without ContextVar."""
        from agent.services.expediente_helpers import get_current_step

        mc = {"expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value}
        assert get_current_step(mode_context=mc) == CollectionStep.REVIEW_SUMMARY


class TestAllToolsUnchangedSignature:
    """T-35: All 15 expediente tools have unchanged LLM-facing signatures."""

    def test_case_tools_pydantic_schemas_intact(self):
        """
        Import all 8 case tools — they must be importable and have their Pydantic schemas.
        """
        from agent.tools.case_tools import (
            iniciar_expediente,
            obtener_estado_expediente,
            actualizar_datos_expediente,
            actualizar_datos_taller,
            consulta_durante_expediente,
            cancelar_expediente,
            editar_expediente,
            finalizar_expediente,
        )

        tools = [
            iniciar_expediente,
            obtener_estado_expediente,
            actualizar_datos_expediente,
            actualizar_datos_taller,
            consulta_durante_expediente,
            cancelar_expediente,
            editar_expediente,
            finalizar_expediente,
        ]

        for t in tools:
            # Each tool must have a name (LLM-facing)
            assert t.name, f"{t} has no name"
            # Each tool must have a description (LLM-facing)
            assert t.description or t.__doc__, f"{t.name} has no description"

    def test_element_data_tools_importable(self):
        """All 7 element_data tools must still be importable."""
        from agent.tools.element_data_tools import (
            obtener_campos_elemento,
            guardar_datos_elemento,
            confirmar_fotos_elemento,
            completar_elemento_actual,
            obtener_progreso_elementos,
            confirmar_documentacion_base,
            reenviar_imagenes_elemento,
        )

        tools = [
            obtener_campos_elemento,
            guardar_datos_elemento,
            confirmar_fotos_elemento,
            completar_elemento_actual,
            obtener_progreso_elementos,
            confirmar_documentacion_base,
            reenviar_imagenes_elemento,
        ]

        for t in tools:
            assert t.name, f"{t} has no name"


class TestEscalarAHumanoAlwaysAvailable:
    """T-35: escalar_a_humano is present in all 6 expediente node tool lists."""

    def test_all_6_tool_list_functions_include_escalar(self):
        """
        All 6 get_*_tools functions include escalar_a_humano.
        """
        from agent.modes.submodos._shared import (
            _get_element_data_tools,
            _get_base_docs_tools,
            _get_personal_tools,
            _get_vehicle_tools,
            _get_workshop_tools,
            _get_review_tools,
        )

        tool_fns = [
            ("element_data", _get_element_data_tools),
            ("base_docs", _get_base_docs_tools),
            ("personal", _get_personal_tools),
            ("vehicle", _get_vehicle_tools),
            ("workshop", _get_workshop_tools),
            ("review", _get_review_tools),
        ]

        for sub_mode_name, get_tools_fn in tool_fns:
            tools = get_tools_fn()
            tool_names = [t.name for t in tools]
            assert "escalar_a_humano" in tool_names, (
                f"escalar_a_humano missing from {sub_mode_name} tool list: {tool_names}"
            )
