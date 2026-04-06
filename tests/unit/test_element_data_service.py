"""
Unit tests for agent/services/element_data_service.py

Pure-function tests only: validate_field_value, evaluate_field_condition,
get_element_collection_progress, and the error-response helper.

No database, Redis, LLM, or external I/O — all DB calls are mocked where
needed. Heavy async/integration paths are covered separately in the
integration test suite.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from agent.services.element_data_service import (
    validate_field_value,
    evaluate_field_condition,
    _get_element_collection_progress,
    _get_current_element_code,
    _get_element_phase,
    _is_current_element_photos_done,
    _lcp_length,
    _tool_error_response,
)
from agent.utils.expediente_types import (
    CaseCollectionState,
    CollectionStep,
    ELEMENT_STATUS_PENDING,
    ELEMENT_STATUS_PHOTOS_DONE,
    ELEMENT_STATUS_COMPLETE,
)


# ---------------------------------------------------------------------------
# Fake ElementRequiredField (avoids DB imports in pure tests)
# ---------------------------------------------------------------------------


def _make_field(
    field_key: str = "test_key",
    field_label: str = "Test Field",
    field_type: str = "text",
    is_required: bool = True,
    options: list[str] | None = None,
    validation_rules: dict | None = None,
    condition_field_id: str | None = None,
    condition_operator: str | None = None,
    condition_value: str | None = None,
    field_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
) -> MagicMock:
    field = MagicMock()
    field.field_key = field_key
    field.field_label = field_label
    field.field_type = field_type
    field.is_required = is_required
    field.options = options
    field.validation_rules = validation_rules or {}
    field.condition_field_id = condition_field_id
    field.condition_operator = condition_operator
    field.condition_value = condition_value
    field.id = field_id
    return field


def _make_state(
    element_codes: list[str] | None = None,
    current_idx: int = 0,
    phase: str = "photos",
    element_data_status: dict | None = None,
    sub_mode: str = CollectionStep.COLLECT_ELEMENT_DATA.value,
) -> CaseCollectionState:
    return CaseCollectionState(
        step=sub_mode,
        case_id="case-001",
        category_id="cat-001",
        category_slug="motos-part",
        element_codes=element_codes or ["ESCAPE", "SUBCHASIS"],
        current_element_index=current_idx,
        element_phase=phase,
        element_data_status=element_data_status or {},
        base_docs_received=False,
        base_doc_descriptions=[],
    )


# =============================================================================
# validate_field_value
# =============================================================================


class TestValidateFieldValue:
    def test_required_empty_string_fails(self):
        field = _make_field(is_required=True, field_type="text")
        valid, msg = validate_field_value("", field)
        assert not valid
        assert "obligatorio" in msg

    def test_required_none_fails(self):
        field = _make_field(is_required=True, field_type="text")
        valid, msg = validate_field_value(None, field)
        assert not valid

    def test_optional_empty_passes(self):
        field = _make_field(is_required=False, field_type="text")
        valid, msg = validate_field_value("", field)
        assert valid
        assert msg is None

    def test_optional_none_passes(self):
        field = _make_field(is_required=False, field_type="text")
        valid, msg = validate_field_value(None, field)
        assert valid

    # ── number ──────────────────────────────────────────────────────────────

    def test_number_valid_int(self):
        field = _make_field(field_type="number")
        valid, msg = validate_field_value(42, field)
        assert valid

    def test_number_valid_float_string(self):
        field = _make_field(field_type="number")
        valid, msg = validate_field_value("3.14", field)
        assert valid

    def test_number_with_unit_stripped(self):
        field = _make_field(field_type="number")
        valid, msg = validate_field_value("1230 mm", field)
        assert valid

    def test_number_invalid_string(self):
        field = _make_field(field_type="number")
        valid, msg = validate_field_value("not-a-number", field)
        assert not valid
        assert "número" in msg

    def test_number_below_min(self):
        field = _make_field(
            field_type="number",
            validation_rules={"min_value": 10},
        )
        valid, msg = validate_field_value(5, field)
        assert not valid
        assert "10" in msg

    def test_number_above_max(self):
        field = _make_field(
            field_type="number",
            validation_rules={"max_value": 100},
        )
        valid, msg = validate_field_value(200, field)
        assert not valid

    def test_number_min_max_keys_also_supported(self):
        field = _make_field(
            field_type="number",
            validation_rules={"min": 5, "max": 50},
        )
        valid, _ = validate_field_value(30, field)
        assert valid
        valid2, _ = validate_field_value(3, field)
        assert not valid2

    # ── boolean ─────────────────────────────────────────────────────────────

    def test_boolean_valid_true(self):
        field = _make_field(field_type="boolean")
        for val in ("true", "True", "1", "si", "sí"):
            valid, _ = validate_field_value(val, field)
            assert valid, f"Expected valid for: {val}"

    def test_boolean_valid_false(self):
        field = _make_field(field_type="boolean")
        for val in ("false", "False", "0", "no"):
            valid, _ = validate_field_value(val, field)
            assert valid, f"Expected valid for: {val}"

    def test_boolean_invalid(self):
        field = _make_field(field_type="boolean")
        valid, msg = validate_field_value("maybe", field)
        assert not valid
        assert "Sí o No" in msg

    # ── select ───────────────────────────────────────────────────────────────

    def test_select_valid_option(self):
        field = _make_field(field_type="select", options=["Opción A", "Opción B"])
        valid, _ = validate_field_value("opción a", field)
        assert valid  # case-insensitive

    def test_select_invalid_option(self):
        field = _make_field(field_type="select", options=["Opción A", "Opción B"])
        valid, msg = validate_field_value("Opción C", field)
        assert not valid
        assert "Opciones" in msg

    def test_select_no_options_always_passes(self):
        field = _make_field(field_type="select", options=None)
        valid, _ = validate_field_value("anything", field)
        assert valid

    # ── text ─────────────────────────────────────────────────────────────────

    def test_text_min_length_pass(self):
        field = _make_field(
            field_type="text",
            validation_rules={"min_length": 3},
        )
        valid, _ = validate_field_value("abcde", field)
        assert valid

    def test_text_min_length_fail(self):
        field = _make_field(
            field_type="text",
            validation_rules={"min_length": 5},
        )
        valid, msg = validate_field_value("ab", field)
        assert not valid
        assert "5" in msg

    def test_text_max_length_fail(self):
        field = _make_field(
            field_type="text",
            validation_rules={"max_length": 5},
        )
        valid, msg = validate_field_value("toolongstring", field)
        assert not valid

    def test_text_pattern_pass(self):
        field = _make_field(
            field_type="text",
            validation_rules={"pattern": r"^\d{4}[A-Z]{3}$"},
        )
        valid, _ = validate_field_value("1234ABC", field)
        assert valid

    def test_text_pattern_fail_with_hint(self):
        field = _make_field(
            field_type="text",
            validation_rules={
                "pattern": r"^\d{4}[A-Z]{3}$",
                "pattern_description": "Ej: 1234ABC",
            },
        )
        valid, msg = validate_field_value("bad", field)
        assert not valid
        assert "Ej: 1234ABC" in msg


# =============================================================================
# evaluate_field_condition
# =============================================================================


class TestEvaluateFieldCondition:
    def test_no_condition_always_true(self):
        field = _make_field(condition_field_id=None)
        all_fields = [field]
        assert evaluate_field_condition(field, {}, all_fields) is True

    def test_condition_field_not_found_defaults_true(self):
        field = _make_field(
            field_key="child",
            condition_field_id="non-existent-id",
            condition_operator="equals",
            condition_value="yes",
        )
        all_fields = [field]
        result = evaluate_field_condition(field, {}, all_fields)
        assert result is True

    def test_equals_true(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="equals",
            condition_value="yes",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "yes"}, all_fields) is True

    def test_equals_case_insensitive(self):
        parent = _make_field(
            field_key="tipo",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="sub_tipo",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="equals",
            condition_value="Fijo",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"tipo": "fijo"}, all_fields) is True

    def test_equals_false_when_different_value(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="equals",
            condition_value="yes",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "no"}, all_fields) is False

    def test_equals_false_when_missing(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="equals",
            condition_value="yes",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {}, all_fields) is False

    def test_not_equals_true_when_different(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="not_equals",
            condition_value="no",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "yes"}, all_fields) is True

    def test_not_equals_false_when_same(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="not_equals",
            condition_value="no",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "no"}, all_fields) is False

    def test_exists_true_when_present(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="exists",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "anything"}, all_fields) is True

    def test_exists_false_when_missing(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="exists",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {}, all_fields) is False

    def test_not_exists_true_when_missing(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="not_exists",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {}, all_fields) is True

    def test_not_exists_false_when_present(self):
        parent = _make_field(
            field_key="parent",
            field_id="aaaaaaaa-0000-0000-0000-000000000001",
        )
        child = _make_field(
            field_key="child",
            condition_field_id="aaaaaaaa-0000-0000-0000-000000000001",
            condition_operator="not_exists",
        )
        all_fields = [parent, child]
        assert evaluate_field_condition(child, {"parent": "value"}, all_fields) is False


# =============================================================================
# Progress helpers
# =============================================================================


class TestProgressHelpers:
    def test_get_current_element_code_first(self):
        state = _make_state(element_codes=["ESCAPE", "SUBCHASIS"], current_idx=0)
        assert _get_current_element_code(state) == "ESCAPE"

    def test_get_current_element_code_second(self):
        state = _make_state(element_codes=["ESCAPE", "SUBCHASIS"], current_idx=1)
        assert _get_current_element_code(state) == "SUBCHASIS"

    def test_get_current_element_code_out_of_bounds(self):
        state = _make_state(element_codes=["ESCAPE"], current_idx=5)
        assert _get_current_element_code(state) is None

    def test_get_current_element_code_empty_list(self):
        state = _make_state(element_codes=[])
        assert _get_current_element_code(state) is None

    def test_get_element_phase_default(self):
        state = _make_state(phase="photos")
        assert _get_element_phase(state) == "photos"

    def test_get_element_phase_data(self):
        state = _make_state(phase="data")
        assert _get_element_phase(state) == "data"

    def test_is_photos_done_when_photos_done(self):
        state = _make_state(
            element_codes=["ESCAPE"],
            current_idx=0,
            element_data_status={"ESCAPE": ELEMENT_STATUS_PHOTOS_DONE},
        )
        assert _is_current_element_photos_done(state) is True

    def test_is_photos_done_when_complete(self):
        state = _make_state(
            element_codes=["ESCAPE"],
            current_idx=0,
            element_data_status={"ESCAPE": ELEMENT_STATUS_COMPLETE},
        )
        assert _is_current_element_photos_done(state) is True

    def test_is_photos_done_when_pending(self):
        state = _make_state(
            element_codes=["ESCAPE"],
            current_idx=0,
            element_data_status={"ESCAPE": ELEMENT_STATUS_PENDING},
        )
        assert _is_current_element_photos_done(state) is False

    def test_is_photos_done_no_element(self):
        state = _make_state(element_codes=[])
        assert _is_current_element_photos_done(state) is False


class TestGetElementCollectionProgress:
    def test_empty_elements(self):
        state = _make_state(element_codes=[])
        prog = _get_element_collection_progress(state)
        assert prog["total_elements"] == 0
        assert prog["completed_elements"] == 0
        assert prog["current_element_code"] is None

    def test_partial_completion(self):
        state = _make_state(
            element_codes=["A", "B", "C"],
            current_idx=1,
            element_data_status={
                "A": ELEMENT_STATUS_COMPLETE,
                "B": ELEMENT_STATUS_PHOTOS_DONE,
                "C": ELEMENT_STATUS_PENDING,
            },
        )
        prog = _get_element_collection_progress(state)
        assert prog["total_elements"] == 3
        assert prog["completed_elements"] == 1
        assert prog["current_element_code"] == "B"
        assert prog["current_phase"] == "photos"

    def test_all_complete(self):
        state = _make_state(
            element_codes=["A", "B"],
            current_idx=1,
            element_data_status={
                "A": ELEMENT_STATUS_COMPLETE,
                "B": ELEMENT_STATUS_COMPLETE,
            },
        )
        prog = _get_element_collection_progress(state)
        assert prog["completed_elements"] == 2

    def test_elements_info_structure(self):
        state = _make_state(
            element_codes=["A", "B"],
            current_idx=0,
            element_data_status={"A": ELEMENT_STATUS_COMPLETE},
        )
        prog = _get_element_collection_progress(state)
        elements = prog["elements"]
        assert len(elements) == 2
        a_info = next(e for e in elements if e["code"] == "A")
        b_info = next(e for e in elements if e["code"] == "B")
        assert a_info["status"] == ELEMENT_STATUS_COMPLETE
        assert a_info["is_current"] is True
        assert b_info["is_current"] is False


# =============================================================================
# LCP helper
# =============================================================================


class TestLcpLength:
    def test_identical_strings(self):
        assert _lcp_length("abcde", "abcde") == 5

    def test_no_common_prefix(self):
        assert _lcp_length("abc", "xyz") == 0

    def test_partial_match(self):
        assert _lcp_length("abcdef", "abcxyz") == 3

    def test_empty_string(self):
        assert _lcp_length("", "abc") == 0
        assert _lcp_length("abc", "") == 0


# =============================================================================
# _tool_error_response
# =============================================================================


class TestToolErrorResponse:
    def test_basic_error(self):
        resp = _tool_error_response("Something went wrong")
        assert resp["success"] is False
        assert resp["error"] == "Something went wrong"
        assert resp["message"] == "Something went wrong"
        assert "current_step" not in resp
        assert "guidance" not in resp

    def test_with_step(self):
        resp = _tool_error_response("Error", current_step=CollectionStep.IDLE)
        assert resp["current_step"] == CollectionStep.IDLE.value

    def test_with_step_string(self):
        resp = _tool_error_response("Error", current_step="collect_element_data")
        assert resp["current_step"] == "collect_element_data"

    def test_with_guidance(self):
        resp = _tool_error_response("Error", guidance="Do this instead")
        assert resp["guidance"] == "Do this instead"
