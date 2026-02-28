"""Tests for _extract_context_from_tool in ExpedienteModeNode.

Validates that the static method correctly:
1. Unwraps fsm_state_update.case_collection (v1 tool compat)
2. Falls back to direct case_collection
3. Reads _context_updates contract (new tools)
4. Detects sub-mode transitions by next_step (not seccion)
5. Handles editar_expediente routing back to sub-modes
6. Extracts element progress fields at root level
"""

import json
import pytest

from agent.modes.expediente_mode import ExpedienteModeNode


class TestExtractContextFromTool:
    """Test that _extract_context_from_tool properly extracts state updates."""

    @pytest.fixture
    def extract(self):
        """Get the extract function (static method)."""
        return ExpedienteModeNode._extract_context_from_tool

    # ------------------------------------------------------------------
    # FSM state update unwrapping
    # ------------------------------------------------------------------

    def test_fsm_state_update_unwrapped(self, extract):
        """fsm_state_update.case_collection is properly unwrapped."""
        data = {
            "success": True,
            "fsm_state_update": {
                "case_collection": {
                    "element_phase": "data",
                    "element_data_status": {"SUBCHASIS": "photos_done"},
                }
            },
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("element_phase") == "data"
        assert "element_data_status" in updates

    def test_direct_case_collection_still_works(self, extract):
        """Direct case_collection (without fsm_state_update wrapper) still works."""
        data = {
            "success": True,
            "case_collection": {
                "element_phase": "data",
            },
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("element_phase") == "data"

    def test_fsm_state_update_preferred_over_case_collection(self, extract):
        """fsm_state_update takes precedence (elif means case_collection is fallback)."""
        data = {
            "success": True,
            "fsm_state_update": {
                "case_collection": {"element_phase": "data"}
            },
            "case_collection": {"element_phase": "photos"},
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("element_phase") == "data"

    def test_fsm_state_update_empty_case_collection_blocks_fallback(self, extract):
        """Empty case_collection in fsm_state_update blocks the elif fallback.

        When fsm_state_update exists (even with empty case_collection),
        the elif branch for direct case_collection never fires. This is
        correct behavior — fsm_state_update takes precedence.
        The only way to get element_phase here is if it's at the root level
        AND the tool is in the element tracking list.
        """
        data = {
            "success": True,
            "fsm_state_update": {
                "case_collection": {}  # Empty — won't merge anything
            },
            "case_collection": {"element_phase": "data"},  # Never reached (elif)
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        # Neither fsm_state_update (empty) nor case_collection (blocked by elif) provides data.
        # Root-level element_phase is NOT in this data, so no extraction happens.
        assert "element_phase" not in updates

    # ------------------------------------------------------------------
    # _context_updates contract
    # ------------------------------------------------------------------

    def test_context_updates_contract(self, extract):
        """_context_updates contract is properly read."""
        data = {
            "success": True,
            "_context_updates": {
                "expediente_sub_mode": "collect_base_docs",
                "custom_field": True,
            },
        }
        updates = extract("some_new_tool", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_base_docs"
        assert updates.get("custom_field") is True

    def test_context_updates_non_dict_ignored(self, extract):
        """Non-dict _context_updates is ignored."""
        data = {
            "success": True,
            "_context_updates": "not_a_dict",
        }
        updates = extract("some_tool", {}, json.dumps(data), {})
        assert "not_a_dict" not in updates.values()

    # ------------------------------------------------------------------
    # actualizar_datos_expediente transitions by next_step
    # ------------------------------------------------------------------

    def test_actualizar_datos_by_next_step_personal_to_vehicle(self, extract):
        """actualizar_datos_expediente transitions to COLLECT_VEHICLE by next_step."""
        data = {"success": True, "next_step": "collect_vehicle"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_vehicle"

    def test_actualizar_datos_by_next_step_vehicle_to_workshop(self, extract):
        """actualizar_datos_expediente transitions to COLLECT_WORKSHOP by next_step."""
        data = {"success": True, "next_step": "collect_workshop"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_workshop"

    def test_actualizar_datos_no_transition_on_failure(self, extract):
        """No transition when actualizar_datos_expediente fails."""
        data = {"success": False, "next_step": "collect_vehicle"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    def test_actualizar_datos_no_transition_without_next_step(self, extract):
        """No transition when next_step is absent (partial update)."""
        data = {"success": True, "message": "Datos guardados parcialmente"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    def test_actualizar_datos_tracks_just_transitioned_from(self, extract):
        """actualizar_datos sets just_transitioned_from correctly."""
        data = {"success": True, "next_step": "collect_vehicle"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert updates.get("just_transitioned_from") == "collect_personal"
        assert updates.get("expediente_transition_marker", {}).get("to_sub_mode") == "collect_vehicle"

        data = {"success": True, "next_step": "collect_workshop"}
        updates = extract("actualizar_datos_expediente", {}, json.dumps(data), {})
        assert updates.get("just_transitioned_from") == "collect_vehicle"
        assert updates.get("expediente_transition_marker", {}).get("to_sub_mode") == "collect_workshop"

    # ------------------------------------------------------------------
    # editar_expediente transitions
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "next_step,expected_sub_mode",
        [
            ("collect_personal", "collect_personal"),
            ("collect_vehicle", "collect_vehicle"),
            ("collect_workshop", "collect_workshop"),
            ("collect_base_docs", "collect_base_docs"),
            ("collect_element_data", "collect_element_data"),
        ],
    )
    def test_editar_expediente_transitions(self, extract, next_step, expected_sub_mode):
        """editar_expediente transitions to correct sub-mode."""
        data = {"success": True, "next_step": next_step}
        updates = extract("editar_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == expected_sub_mode
        assert updates.get("editing_from_review") is True

    def test_editar_expediente_no_transition_on_failure(self, extract):
        """editar_expediente does nothing on failure."""
        data = {"success": False, "next_step": "collect_personal"}
        updates = extract("editar_expediente", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates
        assert "editing_from_review" not in updates

    def test_editar_expediente_unknown_next_step_ignored(self, extract):
        """editar_expediente ignores unknown next_step values."""
        data = {"success": True, "next_step": "nonexistent_step"}
        updates = extract("editar_expediente", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    # ------------------------------------------------------------------
    # completar_elemento_actual transitions
    # ------------------------------------------------------------------

    def test_completar_elemento_all_done(self, extract):
        """completar_elemento_actual with all_elements_complete transitions."""
        data = {"success": True, "all_elements_complete": True}
        updates = extract("completar_elemento_actual", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_base_docs"
        marker = updates.get("expediente_transition_marker")
        assert marker and marker.get("from_sub_mode") == "collect_element_data"
        assert marker.get("to_sub_mode") == "collect_base_docs"

    def test_completar_elemento_not_all_done(self, extract):
        """completar_elemento_actual without all_elements_complete stays."""
        data = {"success": True, "all_elements_complete": False}
        updates = extract("completar_elemento_actual", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    # ------------------------------------------------------------------
    # confirmar_documentacion_base transitions
    # ------------------------------------------------------------------

    def test_confirmar_docs_base_transitions(self, extract):
        """confirmar_documentacion_base transitions to COLLECT_PERSONAL."""
        data = {"success": True}
        updates = extract("confirmar_documentacion_base", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "collect_personal"
        assert updates.get("expediente_transition_marker", {}).get("from_sub_mode") == "collect_base_docs"

    def test_confirmar_docs_base_no_transition_on_failure(self, extract):
        """confirmar_documentacion_base does nothing on failure."""
        data = {"success": False}
        updates = extract("confirmar_documentacion_base", {}, json.dumps(data), {})
        assert "expediente_sub_mode" not in updates

    # ------------------------------------------------------------------
    # actualizar_datos_taller transitions
    # ------------------------------------------------------------------

    def test_actualizar_taller_transitions_to_review(self, extract):
        """actualizar_datos_taller transitions to REVIEW_SUMMARY."""
        data = {"success": True}
        updates = extract("actualizar_datos_taller", {}, json.dumps(data), {})
        assert updates.get("expediente_sub_mode") == "review_summary"
        assert updates.get("expediente_transition_marker", {}).get("to_sub_mode") == "review_summary"

    # ------------------------------------------------------------------
    # finalizar/cancelar expediente transitions
    # ------------------------------------------------------------------

    def test_finalizar_expediente_marks_completed(self, extract):
        """finalizar_expediente marks completed and triggers transition."""
        data = {"success": True}
        updates = extract("finalizar_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_completed") is True
        assert updates.get("_transition_to") == "COMPLETED"

    def test_cancelar_expediente_transitions_to_presupuesto(self, extract):
        """cancelar_expediente transitions back to PRESUPUESTO_MODE."""
        data = {"success": True}
        updates = extract("cancelar_expediente", {}, json.dumps(data), {})
        assert updates.get("expediente_cancelled") is True
        assert updates.get("_transition_to") == "PRESUPUESTO_MODE"

    # ------------------------------------------------------------------
    # Element progress tracking
    # ------------------------------------------------------------------

    def test_root_level_element_phase_extracted(self, extract):
        """element_phase at root level is extracted by direct extractor."""
        data = {
            "success": True,
            "element_phase": "data",
            "current_element_index": 2,
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        assert updates.get("element_phase") == "data"
        assert updates.get("current_element_index") == 2

    def test_guardar_datos_elemento_tracks_progress(self, extract):
        """guardar_datos_elemento extracts element progress fields."""
        data = {
            "success": True,
            "current_element_index": 1,
            "element_phase": "photos",
        }
        updates = extract("guardar_datos_elemento", {}, json.dumps(data), {})
        assert updates.get("current_element_index") == 1
        assert updates.get("element_phase") == "photos"

    def test_completar_elemento_tracks_index(self, extract):
        """completar_elemento_actual extracts current_element_index."""
        data = {
            "success": True,
            "all_elements_complete": False,
            "current_element_index": 3,
        }
        updates = extract("completar_elemento_actual", {}, json.dumps(data), {})
        assert updates.get("current_element_index") == 3

    # ------------------------------------------------------------------
    # Robustness / Edge cases
    # ------------------------------------------------------------------

    def test_non_json_result_returns_empty(self, extract):
        """Non-JSON result string returns empty updates."""
        updates = extract("some_tool", {}, "not valid json", {})
        assert updates == {}

    def test_non_dict_result_returns_empty(self, extract):
        """Non-dict JSON result returns empty updates."""
        updates = extract("some_tool", {}, json.dumps([1, 2, 3]), {})
        assert updates == {}

    def test_none_result_returns_empty(self, extract):
        """None result returns empty updates (TypeError on json.loads)."""
        updates = extract("some_tool", {}, None, {})
        assert updates == {}

    def test_empty_dict_result_returns_empty(self, extract):
        """Empty dict result returns empty updates."""
        updates = extract("some_tool", {}, json.dumps({}), {})
        assert updates == {}

    def test_unknown_tool_returns_empty(self, extract):
        """Unknown tool with no matching extractor returns empty."""
        data = {"success": True, "some_field": "value"}
        updates = extract("totally_unknown_tool", {}, json.dumps(data), {})
        assert updates == {}

    def test_result_as_dict_instead_of_string(self, extract):
        """When result is already a dict (not JSON string), it still works."""
        data = {
            "success": True,
            "element_phase": "data",
            "current_element_index": 1,
        }
        # Pass dict directly instead of JSON string
        updates = extract("confirmar_fotos_elemento", {}, data, {})
        assert updates.get("element_phase") == "data"
        assert updates.get("current_element_index") == 1

    # ------------------------------------------------------------------
    # Combined: fsm_state_update + element tracking
    # ------------------------------------------------------------------

    def test_fsm_update_and_element_tracking_combined(self, extract):
        """Both fsm_state_update and root-level element fields are extracted."""
        data = {
            "success": True,
            "element_phase": "data",
            "current_element_index": 2,
            "fsm_state_update": {
                "case_collection": {
                    "element_data_status": {"ESC": "photos_done", "SUB": "pending"},
                }
            },
        }
        updates = extract("confirmar_fotos_elemento", {}, json.dumps(data), {})
        # Root-level fields
        assert updates.get("element_phase") == "data"
        assert updates.get("current_element_index") == 2
        # FSM update unwrapped
        assert updates.get("element_data_status") == {"ESC": "photos_done", "SUB": "pending"}

    def test_context_updates_and_transition_combined(self, extract):
        """_context_updates combined with tool-specific transition logic."""
        data = {
            "success": True,
            "all_elements_complete": True,
            "_context_updates": {
                "some_extra_flag": True,
            },
        }
        updates = extract("completar_elemento_actual", {}, json.dumps(data), {})
        # From _context_updates contract
        assert updates.get("some_extra_flag") is True
        # From completar_elemento_actual handler
        assert updates.get("expediente_sub_mode") == "collect_base_docs"
