"""
Unit tests for expediente_post_tool_hook and _extract_expediente_context.

TDD: Tests written FIRST (RED), then implementation (GREEN).

Placed in tests/unit/ so that tests/unit/conftest.py stubs for
langgraph.checkpoint.redis are in effect before agent.* imports.

Tasks covered:
  T-01 — Stub signature tests (function exists, returns dict, non-dict → {}, empty state)
  T-03 — All transition paths via _extract_expediente_context
  T-05 — Three-layer merge
  T-07 — Element progress, intro signals, FSM compat
  T-09 — Read-only tool passthrough
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    mode_context: dict | None = None,
    pending_state_updates: dict | None = None,
) -> dict:
    """Build a minimal hook state."""
    return {
        "messages": [HumanMessage(content="Hola")],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-exp-001",
        **({"pending_state_updates": pending_state_updates} if pending_state_updates else {}),
    }


def _make_iniciar_result(success: bool = True, case_id: str = "case-uuid-001") -> dict:
    return {
        "success": success,
        "case_id": case_id,
        "message": "Expediente iniciado",
    }


def _make_completar_result(
    all_elements_complete: bool = False,
    current_element_index: int = 1,
    element_phase: str = "photos",
) -> dict:
    r = {
        "success": True,
        "current_element_index": current_element_index,
        "element_phase": element_phase,
    }
    if all_elements_complete:
        r["all_elements_complete"] = True
    return r


def _make_confirmar_docs_result(
    success: bool = True,
    already_confirmed: bool = False,
    escalated: bool = False,
) -> dict:
    return {
        "success": success,
        "already_confirmed": already_confirmed,
        "escalated": escalated,
    }


def _make_actualizar_datos_result(next_step: str = "collect_vehicle") -> dict:
    return {"success": True, "next_step": next_step}


def _make_actualizar_taller_result(next_step: str = "review_summary") -> dict:
    return {"success": True, "next_step": next_step}


def _make_editar_result(next_step: str = "collect_personal") -> dict:
    return {"success": True, "next_step": next_step}


def _make_finalizar_result(success: bool = True) -> dict:
    return {"success": success}


def _make_cancelar_result(success: bool = True) -> dict:
    return {"success": success}


# ===========================================================================
# GROUP 1 — T-01: Stub signature tests
# ===========================================================================


class TestExpedientePostToolHookSignature:
    """T-01 — expediente_post_tool_hook exists, returns dict, handles edge cases."""

    @pytest.mark.asyncio
    async def test_function_exists_and_returns_dict(self):
        """expediente_post_tool_hook(tool_name, result_dict, state) exists and returns dict."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = await expediente_post_tool_hook("some_tool", {"success": True}, state)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_non_dict_result_returns_empty(self):
        """Non-dict result_dict returns {} without crashing."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = await expediente_post_tool_hook("some_tool", "not a dict", state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_none_result_returns_empty(self):
        """None result_dict returns {} without crashing."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state()
        result = await expediente_post_tool_hook("some_tool", None, state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_state_does_not_crash(self):
        """Empty state dict does not crash."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        result = await expediente_post_tool_hook("some_tool", {"success": True}, {})
        assert isinstance(result, dict)


# ===========================================================================
# GROUP 2 — T-03: Transition paths via _extract_expediente_context
# ===========================================================================


class TestExtractExpedienteContext:
    """T-03 — All transition scenarios for _extract_expediente_context."""

    def test_function_exists(self):
        """_extract_expediente_context is importable from post_tool_hooks."""
        from agent.modes.post_tool_hooks import _extract_expediente_context
        assert callable(_extract_expediente_context)

    def test_iniciar_expediente_success_sets_intro_flag(self):
        """iniciar_expediente success with intro_already_sent flag → intro_already_sent=True."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "case_id": "case-001",
            "_internal_flags": {"intro_already_sent": True},
        }
        updates = _extract_expediente_context("iniciar_expediente", result_dict, {})
        assert updates.get("intro_already_sent") is True

    def test_iniciar_expediente_failure_no_transition(self):
        """iniciar_expediente failure → no expediente_sub_mode set."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {"success": False, "error": "DB error"}
        updates = _extract_expediente_context("iniciar_expediente", result_dict, {})
        assert "expediente_sub_mode" not in updates

    def test_completar_elemento_more_elements_stays_collect(self):
        """completar_elemento_actual with more elements (no all_elements_complete) → stays collect_element_data."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_completar_result(all_elements_complete=False, current_element_index=1)
        updates = _extract_expediente_context("completar_elemento_actual", result_dict, {})
        # No transition should occur
        assert updates.get("expediente_sub_mode") != "collect_base_docs"

    def test_completar_elemento_all_complete_transitions_to_base_docs(self):
        """completar_elemento_actual all_elements_complete=True → expediente_sub_mode=collect_base_docs."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_completar_result(all_elements_complete=True)
        updates = _extract_expediente_context("completar_elemento_actual", result_dict, {})
        assert updates.get("expediente_sub_mode") == "collect_base_docs"

    def test_confirmar_documentacion_base_success_transitions_to_personal(self):
        """confirmar_documentacion_base success → expediente_sub_mode=collect_personal."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_confirmar_docs_result(success=True)
        updates = _extract_expediente_context("confirmar_documentacion_base", result_dict, {})
        assert updates.get("expediente_sub_mode") == "collect_personal"

    def test_confirmar_documentacion_base_already_confirmed_no_transition(self):
        """confirmar_documentacion_base already_confirmed → no transition."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_confirmar_docs_result(success=True, already_confirmed=True)
        updates = _extract_expediente_context("confirmar_documentacion_base", result_dict, {})
        assert updates.get("expediente_sub_mode") != "collect_personal"

    def test_actualizar_datos_expediente_personal_to_vehicle(self):
        """actualizar_datos_expediente next_step=collect_vehicle → expediente_sub_mode=collect_vehicle."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_actualizar_datos_result(next_step="collect_vehicle")
        updates = _extract_expediente_context("actualizar_datos_expediente", result_dict, {})
        assert updates.get("expediente_sub_mode") == "collect_vehicle"

    def test_actualizar_datos_expediente_vehicle_to_workshop(self):
        """actualizar_datos_expediente next_step=collect_workshop → expediente_sub_mode=collect_workshop."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_actualizar_datos_result(next_step="collect_workshop")
        updates = _extract_expediente_context("actualizar_datos_expediente", result_dict, {})
        assert updates.get("expediente_sub_mode") == "collect_workshop"

    def test_actualizar_datos_taller_transitions_to_review(self):
        """actualizar_datos_taller success → expediente_sub_mode=review_summary."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_actualizar_taller_result(next_step="review_summary")
        updates = _extract_expediente_context("actualizar_datos_taller", result_dict, {})
        assert updates.get("expediente_sub_mode") == "review_summary"

    def test_editar_expediente_sets_target_sub_mode(self):
        """editar_expediente with next_step=collect_personal → that sub_mode + editing_from_review."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_editar_result(next_step="collect_personal")
        updates = _extract_expediente_context("editar_expediente", result_dict, {})
        assert updates.get("expediente_sub_mode") == "collect_personal"
        assert updates.get("editing_from_review") is True

    def test_finalizar_expediente_sets_completed(self):
        """finalizar_expediente success → expediente_completed=True."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_finalizar_result(success=True)
        updates = _extract_expediente_context("finalizar_expediente", result_dict, {})
        assert updates.get("expediente_completed") is True
        assert updates.get("_transition_to") == "COMPLETED"

    def test_cancelar_expediente_sets_cancelled(self):
        """cancelar_expediente success → expediente_cancelled=True."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = _make_cancelar_result(success=True)
        updates = _extract_expediente_context("cancelar_expediente", result_dict, {})
        assert updates.get("expediente_cancelled") is True
        assert updates.get("_transition_to") == "PRESUPUESTO_MODE"

    def test_escalar_a_humano_no_transition(self):
        """escalar_a_humano → no mode_context transition."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {"success": True, "message": "Escalating"}
        updates = _extract_expediente_context("escalar_a_humano", result_dict, {})
        assert "expediente_sub_mode" not in updates
        assert "expediente_completed" not in updates
        assert "expediente_cancelled" not in updates

    def test_unknown_tool_returns_empty(self):
        """Unknown tool name → returns {} (no crash, no spurious updates)."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        updates = _extract_expediente_context("unknown_tool_xyz", {"success": True}, {})
        assert isinstance(updates, dict)
        assert "expediente_sub_mode" not in updates


# ===========================================================================
# GROUP 3 — T-05: Three-layer merge
# ===========================================================================


class TestThreeLayerMerge:
    """T-05 — Three-layer merge: Layer 1 survives, L2 wins over L1, L3 wins over L2."""

    @pytest.mark.asyncio
    async def test_layer1_base_context_survives(self):
        """mode_context from state survives in merged output."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state(mode_context={"existing_key": "existing_value"})
        result = await expediente_post_tool_hook(
            "unknown_tool_xyz", {"success": True}, state
        )
        mc = result.get("mode_context", {})
        assert mc.get("existing_key") == "existing_value"

    @pytest.mark.asyncio
    async def test_layer2_extraction_wins_over_layer1(self):
        """Extraction result (Layer 2) overwrites matching Layer 1 keys."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        # State has expediente_sub_mode=collect_personal (L1)
        # Tool result will transition it to collect_vehicle (L2 via _extract)
        state = _make_state(mode_context={"expediente_sub_mode": "collect_personal"})
        result_dict = _make_actualizar_datos_result(next_step="collect_vehicle")
        result = await expediente_post_tool_hook("actualizar_datos_expediente", result_dict, state)
        mc = result.get("mode_context", {})
        # L2 (extraction) sets expediente_sub_mode → collect_vehicle
        assert mc.get("expediente_sub_mode") == "collect_vehicle"

    @pytest.mark.asyncio
    async def test_pending_state_updates_merged_into_layer1(self):
        """pending_state_updates.mode_context is merged into Layer 1 base."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        # L1 has key_a; pending_state_updates.mode_context has key_b
        state = _make_state(
            mode_context={"key_a": "value_a"},
            pending_state_updates={"mode_context": {"key_b": "value_b"}},
        )
        result = await expediente_post_tool_hook(
            "unknown_tool_xyz", {"success": True}, state
        )
        mc = result.get("mode_context", {})
        assert mc.get("key_a") == "value_a", "Layer 1 base key must survive"
        assert mc.get("key_b") == "value_b", "Pending state updates must be merged into L1"

    @pytest.mark.asyncio
    async def test_extraction_exception_does_not_crash_hook(self):
        """Exception in _extract_expediente_context does not crash hook (returns partial result)."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state(mode_context={"existing_key": "existing_value"})
        # Patch _extract_expediente_context to raise
        with patch(
            "agent.modes.post_tool_hooks._extract_expediente_context",
            side_effect=RuntimeError("simulated extraction failure"),
        ):
            result = await expediente_post_tool_hook(
                "some_tool", {"success": True}, state
            )
        # Must not raise, must return a dict
        assert isinstance(result, dict)
        # Layer 1 base should still be present
        mc = result.get("mode_context", {})
        assert mc.get("existing_key") == "existing_value"


# ===========================================================================
# GROUP 4 — T-07: Element progress, intro signals, FSM compat
# ===========================================================================


class TestElementProgressAndFSMCompat:
    """T-07 — Element progress, intro signals, FSM compat unwrapping."""

    def test_confirmar_fotos_elemento_updates_element_phase(self):
        """confirmar_fotos_elemento → element_phase extracted from result."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "element_phase": "data",
            "current_element_index": 0,
        }
        updates = _extract_expediente_context("confirmar_fotos_elemento", result_dict, {})
        assert updates.get("element_phase") == "data"
        assert updates.get("current_element_index") == 0

    def test_completar_elemento_actual_updates_index(self):
        """completar_elemento_actual → current_element_index updated."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "current_element_index": 2,
            "element_phase": "photos",
        }
        updates = _extract_expediente_context("completar_elemento_actual", result_dict, {})
        assert updates.get("current_element_index") == 2

    def test_completar_elemento_clears_field_keys(self):
        """completar_elemento_actual → current_element_field_keys=None, element_data_all_collected=False."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {"success": True, "current_element_index": 1, "element_phase": "photos"}
        updates = _extract_expediente_context("completar_elemento_actual", result_dict, {})
        assert "current_element_field_keys" in updates
        assert updates["current_element_field_keys"] is None
        assert updates.get("element_data_all_collected") is False

    def test_iniciar_expediente_intro_signals(self):
        """iniciar_expediente success with intro data → intro signals extracted."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "case_id": "case-001",
            "expediente_intro_message": "Bienvenido al expediente",
            "expediente_intro_sent": True,
            "_internal_flags": {"intro_already_sent": False},
        }
        updates = _extract_expediente_context("iniciar_expediente", result_dict, {})
        assert updates.get("expediente_intro_message") == "Bienvenido al expediente"
        assert updates.get("expediente_intro_sent") is True

    def test_case_collection_update_unwrapping(self):
        """case_collection_update key is unwrapped into mode_context updates."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "case_collection_update": {
                "case_collection": {
                    "step": "collect_element_data",
                    "current_element_index": 0,
                }
            },
        }
        updates = _extract_expediente_context("iniciar_expediente", result_dict, {})
        assert updates.get("step") == "collect_element_data"
        assert updates.get("current_element_index") == 0

    def test_case_collection_flat_unwrapping(self):
        """case_collection key (flat) is unwrapped into mode_context updates."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "case_collection": {
                "step": "collect_personal",
                "case_id": "case-002",
            },
        }
        updates = _extract_expediente_context("completar_elemento_actual", result_dict, {})
        assert updates.get("step") == "collect_personal"
        assert updates.get("case_id") == "case-002"

    def test_state_update_flat_keys_passthrough(self):
        """_context_updates in result are merged directly into mode_context updates."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "_context_updates": {
                "some_flag": True,
                "custom_key": "custom_value",
            },
        }
        updates = _extract_expediente_context("iniciar_expediente", result_dict, {})
        assert updates.get("some_flag") is True
        assert updates.get("custom_key") == "custom_value"

    def test_confirmar_fotos_extracts_field_keys(self):
        """confirmar_fotos_elemento → current_element_field_keys populated from fields."""
        from agent.modes.post_tool_hooks import _extract_expediente_context

        result_dict = {
            "success": True,
            "element_phase": "data",
            "fields": [
                {"field_key": "altura_mm", "field_label": "Altura", "instruction": "en mm"},
                {"field_key": "peso_kg", "field_label": "Peso", "instruction": "en kg"},
            ],
        }
        updates = _extract_expediente_context("confirmar_fotos_elemento", result_dict, {})
        field_keys = updates.get("current_element_field_keys")
        assert field_keys is not None
        keys = [f["field_key"] for f in field_keys]
        assert "altura_mm" in keys
        assert "peso_kg" in keys


# ===========================================================================
# GROUP 5 — T-09: Read-only tool passthrough
# ===========================================================================


class TestReadOnlyToolPassthrough:
    """T-09 — Read-only tools produce no transitions."""

    @pytest.mark.asyncio
    async def test_escalar_a_humano_no_transition_via_hook(self):
        """escalar_a_humano via hook → no expediente_sub_mode or completion flags."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state(mode_context={"expediente_sub_mode": "collect_personal"})
        result = await expediente_post_tool_hook(
            "escalar_a_humano", {"success": True}, state
        )
        mc = result.get("mode_context", {})
        # sub_mode should remain unchanged from base (no transition forced)
        assert mc.get("expediente_sub_mode") == "collect_personal"
        assert "expediente_completed" not in mc
        assert "expediente_cancelled" not in mc

    @pytest.mark.asyncio
    async def test_obtener_estado_expediente_no_transition(self):
        """obtener_estado_expediente → no transition."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state(mode_context={"expediente_sub_mode": "collect_vehicle"})
        result = await expediente_post_tool_hook(
            "obtener_estado_expediente",
            {"success": True, "current_step": "collect_vehicle"},
            state,
        )
        mc = result.get("mode_context", {})
        assert mc.get("expediente_sub_mode") == "collect_vehicle"

    @pytest.mark.asyncio
    async def test_consulta_durante_expediente_no_transition(self):
        """consulta_durante_expediente → no transition."""
        from agent.modes.post_tool_hooks import expediente_post_tool_hook

        state = _make_state(mode_context={"expediente_sub_mode": "collect_workshop"})
        result = await expediente_post_tool_hook(
            "consulta_durante_expediente",
            {"success": True, "answer": "La homologación tarda 2 semanas"},
            state,
        )
        mc = result.get("mode_context", {})
        assert mc.get("expediente_sub_mode") == "collect_workshop"
