"""
Unit tests for agent/modes/expediente_guardrails.py — Phase 5.1

Full unit coverage of:
  - CertaintyEnvelope: construction, to_dict/from_dict round-trip, empty()
  - normalize_tool_payload: all three payload shapes + accumulation
  - evaluate_progression_eligibility: all sub-mode transition rules
  - evaluate_claim_eligibility: all ClaimClass variants
  - evaluate_kickoff_truthfulness: first-destination-turn guard
  - log_guardrail_triggered: smoke tests
  - persist_envelope / load_envelope: mode_context persistence helpers
  - build_prompt_certainty_context: prompt injection field extraction
  - Shadow vs enforced: the module is always enforced (no shadow-only path),
    but the feature flag (EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED) is tested
    at the integration layer (test_expediente_v2_integration.py). Here we test
    the module's pure functions directly.

All tests are pure unit tests — no database, no Redis, no async I/O.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent.modes.expediente_guardrails import (
    CERTAINTY_CONTRACT_VERSION,
    CertaintyEnvelope,
    ClaimClass,
    GuardrailReason,
    build_prompt_certainty_context,
    evaluate_claim_eligibility,
    evaluate_kickoff_truthfulness,
    evaluate_progression_eligibility,
    load_envelope,
    log_guardrail_triggered,
    normalize_tool_payload,
    persist_envelope,
)


# =============================================================================
# Helpers
# =============================================================================


def _empty(sub_mode: str = "collect_element_data") -> CertaintyEnvelope:
    return CertaintyEnvelope.empty(sub_mode=sub_mode)


def _make_success_result(**extra: Any) -> str:
    """Build a JSON-serialised successful tool result."""
    return json.dumps({"success": True, **extra})


def _make_failure_result(**extra: Any) -> str:
    return json.dumps({"success": False, **extra})


def _make_success_dict(**extra: Any) -> dict:
    return {"success": True, **extra}


def _make_failure_dict(**extra: Any) -> dict:
    return {"success": False, **extra}


# =============================================================================
# 1. CertaintyEnvelope — construction and defaults
# =============================================================================


class TestCertaintyEnvelopeConstruction:
    """Contract: all fields default to the most conservative (False/empty) value."""

    def test_empty_defaults_all_false_and_empty(self) -> None:
        env = CertaintyEnvelope.empty("collect_base_docs")
        assert env.sub_mode == "collect_base_docs"
        assert env.photos_confirmed is False
        assert env.docs_confirmed is False
        assert env.images_sent is False
        assert env.case_finalized is False
        assert env.all_elements_complete is False
        assert env.field_saved is False
        assert env.transition_triggered is False
        assert env.transition_target is None
        assert env.is_first_destination_turn is False
        # allowed_transition_claims defaults True (safe default — don't block by default)
        assert env.allowed_transition_claims is True
        assert env.blocked_claim_reason is None
        assert env.kickoff_required is False
        assert env.tools_called == []
        assert env.tools_succeeded == []
        assert env.tools_failed == []
        assert env.source_tool_names == []

    def test_version_is_contract_version(self) -> None:
        env = CertaintyEnvelope.empty()
        assert env.version == CERTAINTY_CONTRACT_VERSION

    def test_created_at_is_iso_string(self) -> None:
        env = CertaintyEnvelope.empty()
        assert isinstance(env.created_at, str)
        # Must be parseable as ISO date
        from datetime import datetime
        datetime.fromisoformat(env.created_at.replace("Z", "+00:00"))

    def test_empty_sub_mode_default(self) -> None:
        env = CertaintyEnvelope.empty()
        assert env.sub_mode == ""

    def test_explicit_construction_all_fields(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            photos_confirmed=True,
            docs_confirmed=True,
            images_sent=True,
            case_finalized=True,
            all_elements_complete=True,
            field_saved=True,
            transition_triggered=True,
            transition_target="completed",
            is_first_destination_turn=True,
            allowed_transition_claims=False,
            blocked_claim_reason="stale step content",
            kickoff_required=True,
            tools_called=["finalizar_expediente"],
            tools_succeeded=["finalizar_expediente"],
            tools_failed=[],
        )
        assert env.sub_mode == "review_summary"
        assert env.photos_confirmed is True
        assert env.docs_confirmed is True
        assert env.images_sent is True
        assert env.case_finalized is True
        assert env.all_elements_complete is True
        assert env.field_saved is True
        assert env.transition_triggered is True
        assert env.transition_target == "completed"
        assert env.is_first_destination_turn is True
        assert env.allowed_transition_claims is False
        assert env.blocked_claim_reason == "stale step content"
        assert env.kickoff_required is True
        assert "finalizar_expediente" in env.tools_called
        assert "finalizar_expediente" in env.tools_succeeded

    def test_two_empty_envelopes_share_no_state(self) -> None:
        env1 = CertaintyEnvelope.empty("collect_personal")
        env2 = CertaintyEnvelope.empty("collect_vehicle")
        env1.tools_called.append("some_tool")
        assert env2.tools_called == []  # Distinct list, not shared


# =============================================================================
# 2. CertaintyEnvelope — to_dict / from_dict round-trip
# =============================================================================


class TestCertaintyEnvelopeSerialisation:
    """to_dict/from_dict must produce a lossless round-trip."""

    def test_to_dict_contains_all_expected_keys(self) -> None:
        env = CertaintyEnvelope.empty("collect_personal")
        d = env.to_dict()
        expected_keys = {
            "version", "sub_mode", "created_at",
            "tools_called", "tools_succeeded", "tools_failed",
            "photos_confirmed", "docs_confirmed", "images_sent",
            "case_finalized", "all_elements_complete", "field_saved",
            "transition_triggered", "transition_target",
            "is_first_destination_turn", "allowed_transition_claims",
            "blocked_claim_reason", "kickoff_required", "source_tool_names",
        }
        assert expected_keys == set(d.keys())

    def test_to_dict_values_are_json_serialisable(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
            photos_confirmed=True,
            docs_confirmed=False,
            tools_called=["guardar_datos_elemento"],
        )
        # Must not raise
        serialised = json.dumps(env.to_dict())
        assert len(serialised) > 0

    def test_from_dict_full_round_trip(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            photos_confirmed=True,
            docs_confirmed=True,
            images_sent=True,
            case_finalized=True,
            all_elements_complete=True,
            field_saved=True,
            transition_triggered=True,
            transition_target="completed",
            is_first_destination_turn=True,
            allowed_transition_claims=False,
            blocked_claim_reason="stale step",
            kickoff_required=True,
            tools_called=["finalizar_expediente"],
            tools_succeeded=["finalizar_expediente"],
        )
        d = env.to_dict()
        restored = CertaintyEnvelope.from_dict(d)

        assert restored.sub_mode == "review_summary"
        assert restored.photos_confirmed is True
        assert restored.docs_confirmed is True
        assert restored.images_sent is True
        assert restored.case_finalized is True
        assert restored.all_elements_complete is True
        assert restored.field_saved is True
        assert restored.transition_triggered is True
        assert restored.transition_target == "completed"
        assert restored.is_first_destination_turn is True
        assert restored.allowed_transition_claims is False
        assert restored.blocked_claim_reason == "stale step"
        assert restored.kickoff_required is True
        assert "finalizar_expediente" in restored.tools_succeeded

    def test_from_dict_with_sparse_dict_uses_safe_defaults(self) -> None:
        """from_dict must not raise on sparse dicts (forward-compat)."""
        restored = CertaintyEnvelope.from_dict({"sub_mode": "collect_vehicle"})
        assert restored.sub_mode == "collect_vehicle"
        assert restored.photos_confirmed is False
        assert restored.docs_confirmed is False
        assert restored.images_sent is False
        assert restored.version == CERTAINTY_CONTRACT_VERSION

    def test_from_dict_empty_dict_uses_all_defaults(self) -> None:
        restored = CertaintyEnvelope.from_dict({})
        assert restored.sub_mode == ""
        assert restored.version == CERTAINTY_CONTRACT_VERSION
        assert restored.tools_called == []

    def test_from_dict_preserves_transition_target_none(self) -> None:
        env = CertaintyEnvelope.empty("collect_element_data")
        d = env.to_dict()
        assert d["transition_target"] is None
        restored = CertaintyEnvelope.from_dict(d)
        assert restored.transition_target is None


# =============================================================================
# 3. normalize_tool_payload — canonical payload shape
# =============================================================================


class TestNormalizeToolPayloadCanonical:
    """Normaliser: canonical _internal_flags + _context_updates payload shape."""

    def test_tracks_called_tool_in_tools_called(self) -> None:
        env = normalize_tool_payload("my_tool", _make_success_result(), "collect_personal")
        assert "my_tool" in env.tools_called
        assert "my_tool" in env.tools_succeeded

    def test_tracks_failed_tool_in_tools_failed(self) -> None:
        env = normalize_tool_payload("my_tool", _make_failure_result(), "collect_personal")
        assert "my_tool" in env.tools_called
        assert "my_tool" in env.tools_failed
        assert "my_tool" not in env.tools_succeeded

    def test_does_not_duplicate_tool_name_on_repeated_calls(self) -> None:
        result = _make_success_result()
        env1 = normalize_tool_payload("tool_a", result, "collect_base_docs")
        env2 = normalize_tool_payload("tool_a", result, "collect_base_docs", existing_envelope=env1)
        assert env2.tools_called.count("tool_a") == 1
        assert env2.tools_succeeded.count("tool_a") == 1

    def test_accepts_dict_payload_instead_of_json_string(self) -> None:
        env = normalize_tool_payload(
            "confirmar_documentacion_base",
            {"success": True},
            "collect_base_docs",
        )
        assert env.docs_confirmed is True

    def test_handles_invalid_json_string_without_raising(self) -> None:
        env = normalize_tool_payload("some_tool", "NOT JSON {{", "collect_personal")
        assert "some_tool" in env.tools_failed  # success=False (missing key)
        assert "some_tool" not in env.tools_succeeded

    def test_handles_non_string_non_dict_payload(self) -> None:
        """Unexpected type must not raise — treated as failure."""
        env = normalize_tool_payload("some_tool", None, "collect_base_docs")  # type: ignore
        assert "some_tool" in env.tools_called

    def test_case_finalized_from_internal_flags(self) -> None:
        result = _make_success_result(_internal_flags={"case_finalized": True})
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is True

    def test_images_sent_from_internal_flags_imagenes_enviadas(self) -> None:
        result = _make_success_result(_internal_flags={"imagenes_enviadas": True})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is True

    def test_transition_from_context_updates_expediente_sub_mode(self) -> None:
        result = json.dumps({
            "success": True,
            "_context_updates": {"expediente_sub_mode": "collect_personal"},
        })
        env = normalize_tool_payload("confirmar_documentacion_base", result, "collect_base_docs")
        assert env.transition_triggered is True
        assert env.transition_target == "collect_personal"


# =============================================================================
# 4. normalize_tool_payload — FSM compat and legacy payload shapes
# =============================================================================


class TestNormalizeToolPayloadLegacy:
    """Normaliser: fsm_state_update.case_collection and flat legacy fields."""

    def test_all_elements_complete_from_flat_field(self) -> None:
        result = _make_success_result(all_elements_complete=True)
        env = normalize_tool_payload("completar_elemento_actual", result, "collect_element_data")
        assert env.all_elements_complete is True

    def test_all_elements_complete_from_context_updates(self) -> None:
        result = json.dumps({
            "success": True,
            "_context_updates": {"all_elements_complete": True},
        })
        env = normalize_tool_payload("completar_elemento_actual", result, "collect_element_data")
        assert env.all_elements_complete is True

    def test_all_elements_complete_from_fsm_state_update_case_collection(self) -> None:
        result = json.dumps({
            "success": True,
            "fsm_state_update": {
                "case_collection": {"all_elements_complete": True}
            },
        })
        env = normalize_tool_payload("completar_elemento_actual", result, "collect_element_data")
        assert env.all_elements_complete is True

    def test_all_elements_complete_from_case_collection_flat(self) -> None:
        result = json.dumps({
            "success": True,
            "case_collection": {"all_elements_complete": True},
        })
        env = normalize_tool_payload("completar_elemento_actual", result, "collect_element_data")
        assert env.all_elements_complete is True

    def test_transition_from_next_step_flat_field(self) -> None:
        result = json.dumps({
            "success": True,
            "next_step": "collect_personal",
        })
        env = normalize_tool_payload("actualizar_datos_expediente", result, "collect_personal")
        assert env.transition_triggered is True
        assert env.transition_target == "collect_personal"


# =============================================================================
# 5. normalize_tool_payload — specific tool-name behaviours
# =============================================================================


class TestNormalizeToolPayloadToolSpecific:
    """Photos, docs, images, field_saved — each requires both tool name and success."""

    def test_photos_confirmed_requires_flag_and_tool_name(self) -> None:
        result = _make_success_result(photos_confirmed=True)
        env = normalize_tool_payload("confirmar_fotos_elemento", result, "collect_element_data")
        assert env.photos_confirmed is True

    def test_photos_confirmed_false_without_flag_in_payload(self) -> None:
        result = _make_success_result()  # No photos_confirmed in payload
        env = normalize_tool_payload("confirmar_fotos_elemento", result, "collect_element_data")
        assert env.photos_confirmed is False

    def test_photos_confirmed_false_for_wrong_tool(self) -> None:
        result = _make_success_result(photos_confirmed=True)
        env = normalize_tool_payload("other_tool", result, "collect_element_data")
        assert env.photos_confirmed is False

    def test_photos_confirmed_false_when_tool_fails(self) -> None:
        result = _make_failure_result(photos_confirmed=True)
        env = normalize_tool_payload("confirmar_fotos_elemento", result, "collect_element_data")
        assert env.photos_confirmed is False

    def test_docs_confirmed_when_confirmar_documentacion_base_succeeds(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("confirmar_documentacion_base", result, "collect_base_docs")
        assert env.docs_confirmed is True

    def test_docs_confirmed_false_when_tool_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("confirmar_documentacion_base", result, "collect_base_docs")
        assert env.docs_confirmed is False

    def test_images_sent_when_status_is_success(self) -> None:
        result = json.dumps({"success": True, "status": "success"})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is True

    def test_images_not_sent_when_status_is_failure(self) -> None:
        result = json.dumps({"success": False, "status": "failure"})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is False

    def test_images_not_sent_when_status_is_empty(self) -> None:
        result = json.dumps({"success": True, "status": ""})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        # status="" is in the exclusion list → not considered "sent"
        assert env.images_sent is False

    def test_case_finalized_from_tool_name_and_success(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is True

    def test_case_finalized_false_when_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is False

    def test_field_saved_when_guardar_datos_elemento_succeeds(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("guardar_datos_elemento", result, "collect_element_data")
        assert env.field_saved is True

    def test_field_saved_false_when_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("guardar_datos_elemento", result, "collect_element_data")
        assert env.field_saved is False


# =============================================================================
# 6. normalize_tool_payload — additive accumulation
# =============================================================================


class TestNormalizeToolPayloadAccumulation:
    """Normaliser is additive: each call merges into the existing envelope."""

    def test_accumulates_across_multiple_tool_calls(self) -> None:
        env1 = normalize_tool_payload(
            "confirmar_fotos_elemento",
            _make_success_result(photos_confirmed=True),
            "collect_element_data",
        )
        env2 = normalize_tool_payload(
            "guardar_datos_elemento",
            _make_success_result(),
            "collect_element_data",
            existing_envelope=env1,
        )
        assert env2.photos_confirmed is True
        assert env2.field_saved is True
        assert "confirmar_fotos_elemento" in env2.tools_succeeded
        assert "guardar_datos_elemento" in env2.tools_succeeded

    def test_earlier_success_preserved_when_later_tool_fails(self) -> None:
        env1 = normalize_tool_payload(
            "confirmar_documentacion_base",
            _make_success_result(),
            "collect_base_docs",
        )
        env2 = normalize_tool_payload(
            "some_other_tool",
            _make_failure_result(),
            "collect_base_docs",
            existing_envelope=env1,
        )
        assert env2.docs_confirmed is True  # Preserved

    def test_created_at_is_preserved_from_existing_envelope(self) -> None:
        env1 = normalize_tool_payload(
            "tool_a", _make_success_result(), "collect_base_docs",
        )
        original_created_at = env1.created_at
        env2 = normalize_tool_payload(
            "tool_b", _make_success_result(), "collect_base_docs",
            existing_envelope=env1,
        )
        assert env2.created_at == original_created_at

    @pytest.mark.parametrize("tool_name,result_factory,expected_flag", [
        ("confirmar_documentacion_base", lambda: _make_success_result(), "docs_confirmed"),
        ("finalizar_expediente", lambda: _make_success_result(), "case_finalized"),
        ("guardar_datos_elemento", lambda: _make_success_result(), "field_saved"),
    ])
    def test_parametrized_tool_sets_expected_flag(
        self, tool_name: str, result_factory: Any, expected_flag: str
    ) -> None:
        result = result_factory()
        env = normalize_tool_payload(tool_name, result, "collect_base_docs")
        assert getattr(env, expected_flag) is True


# =============================================================================
# 7. evaluate_progression_eligibility — all transition pairs
# =============================================================================


class TestEvaluateProgressionEligibility:
    """Transition gate: each sub-mode pair has specific evidence requirements."""

    # collect_element_data → collect_base_docs
    def test_element_to_base_docs_allowed_when_all_elements_complete(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
            all_elements_complete=True,
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_base_docs")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_element_to_base_docs_blocked_when_not_complete(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
            all_elements_complete=False,
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_base_docs")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_NOT_ALLOWED.value

    # collect_base_docs → collect_personal
    def test_base_docs_to_personal_allowed_when_docs_confirmed(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_base_docs",
            docs_confirmed=True,
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_base_docs_to_personal_blocked_when_docs_not_confirmed(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_base_docs",
            docs_confirmed=False,
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is False
        assert reason == GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value

    # collect_personal → collect_vehicle
    def test_personal_to_vehicle_allowed_when_actualizar_datos_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            tools_succeeded=["actualizar_datos_expediente"],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_vehicle")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_personal_to_vehicle_blocked_when_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_vehicle")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value

    def test_personal_to_vehicle_blocked_with_wrong_tool(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            tools_succeeded=["obtener_estado_expediente"],  # Wrong tool
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_vehicle")
        assert allowed is False

    # collect_vehicle → collect_workshop
    def test_vehicle_to_workshop_allowed_when_actualizar_datos_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_vehicle",
            tools_succeeded=["actualizar_datos_expediente"],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_workshop")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_vehicle_to_workshop_blocked_when_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_vehicle",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_workshop")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value

    # collect_workshop → review_summary
    def test_workshop_to_review_allowed_when_taller_tool_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_workshop",
            tools_succeeded=["actualizar_datos_taller"],
        )
        allowed, reason = evaluate_progression_eligibility(env, "review_summary")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_workshop_to_review_blocked_when_taller_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_workshop",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "review_summary")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value

    # review_summary → edit-back (via editar_expediente)
    def test_review_to_edit_allowed_when_editar_expediente_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            tools_succeeded=["editar_expediente"],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_review_to_edit_allowed_when_editar_succeeded_any_target(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            tools_succeeded=["editar_expediente"],
        )
        for target in ("collect_element_data", "collect_base_docs", "collect_personal",
                       "collect_vehicle", "collect_workshop"):
            allowed, _ = evaluate_progression_eligibility(env, target)
            assert allowed is True, f"Expected allowed for target={target}"

    def test_review_to_completed_allowed_when_case_finalized(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            case_finalized=True,
        )
        allowed, reason = evaluate_progression_eligibility(env, "completed")
        assert allowed is True

    def test_review_no_tool_blocked(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_NOT_ALLOWED.value

    # Generic unknown transition — fail-open
    def test_unknown_transition_pair_is_allowed_fail_open(self) -> None:
        env = CertaintyEnvelope(sub_mode="collect_element_data")
        allowed, reason = evaluate_progression_eligibility(env, "some_future_mode")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value

    # Parametrize all blocked transitions with expected reason codes
    @pytest.mark.parametrize("from_mode,to_mode,expected_reason", [
        (
            "collect_element_data", "collect_base_docs",
            GuardrailReason.PROGRESSION_NOT_ALLOWED.value,
        ),
        (
            "collect_base_docs", "collect_personal",
            GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value,
        ),
        (
            "collect_personal", "collect_vehicle",
            GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value,
        ),
        (
            "collect_vehicle", "collect_workshop",
            GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value,
        ),
        (
            "collect_workshop", "review_summary",
            GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value,
        ),
    ])
    def test_parametrized_blocked_transitions(
        self, from_mode: str, to_mode: str, expected_reason: str
    ) -> None:
        """Each transition without required evidence should be blocked with correct reason."""
        env = CertaintyEnvelope(sub_mode=from_mode)
        allowed, reason = evaluate_progression_eligibility(env, to_mode)
        assert allowed is False
        assert reason == expected_reason

    @pytest.mark.parametrize("from_mode,to_mode,setup_kwargs", [
        ("collect_element_data", "collect_base_docs", {"all_elements_complete": True}),
        ("collect_base_docs", "collect_personal", {"docs_confirmed": True}),
        (
            "collect_personal", "collect_vehicle",
            {"tools_succeeded": ["actualizar_datos_expediente"]},
        ),
        (
            "collect_vehicle", "collect_workshop",
            {"tools_succeeded": ["actualizar_datos_expediente"]},
        ),
        (
            "collect_workshop", "review_summary",
            {"tools_succeeded": ["actualizar_datos_taller"]},
        ),
    ])
    def test_parametrized_allowed_transitions(
        self, from_mode: str, to_mode: str, setup_kwargs: dict
    ) -> None:
        """Each transition with required evidence should be allowed."""
        env = CertaintyEnvelope(sub_mode=from_mode, **setup_kwargs)
        allowed, reason = evaluate_progression_eligibility(env, to_mode)
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value


# =============================================================================
# 8. evaluate_claim_eligibility — all ClaimClass values
# =============================================================================


class TestEvaluateClaimEligibility:
    """Claim gate for each ClaimClass variant."""

    # DOCS_RECEIVED
    def test_docs_received_allowed_when_confirmed(self) -> None:
        env = CertaintyEnvelope(docs_confirmed=True)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.DOCS_RECEIVED, "collect_base_docs")
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_docs_received_blocked_when_not_confirmed(self) -> None:
        env = CertaintyEnvelope(docs_confirmed=False)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.DOCS_RECEIVED, "collect_base_docs")
        assert ok is False
        assert reason == GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value

    # IMAGES_SENT
    def test_images_sent_allowed_when_sent(self) -> None:
        env = CertaintyEnvelope(images_sent=True)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.IMAGES_SENT, "collect_element_data")
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_images_sent_blocked_when_not_sent(self) -> None:
        env = CertaintyEnvelope(images_sent=False)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.IMAGES_SENT, "collect_element_data")
        assert ok is False
        assert reason == GuardrailReason.IMAGES_NOT_SENT_BY_TOOL.value

    # CASE_FINALIZED
    def test_case_finalized_allowed_when_finalized(self) -> None:
        env = CertaintyEnvelope(case_finalized=True)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.CASE_FINALIZED, "review_summary")
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_case_finalized_blocked_when_not_finalized(self) -> None:
        env = CertaintyEnvelope(case_finalized=False)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.CASE_FINALIZED, "review_summary")
        assert ok is False
        assert reason == GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value

    # COMPLETION_CLAIM — sub-mode-specific confirming tools
    @pytest.mark.parametrize("sub_mode,required_tool", [
        ("collect_element_data", "completar_elemento_actual"),
        ("collect_element_data", "confirmar_fotos_elemento"),
        ("collect_base_docs", "confirmar_documentacion_base"),
        ("collect_personal", "actualizar_datos_expediente"),
        ("collect_vehicle", "actualizar_datos_expediente"),
        ("collect_workshop", "actualizar_datos_taller"),
        ("review_summary", "finalizar_expediente"),
    ])
    def test_completion_claim_allowed_with_required_tool(
        self, sub_mode: str, required_tool: str
    ) -> None:
        env = CertaintyEnvelope(tools_succeeded=[required_tool])
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.COMPLETION_CLAIM, sub_mode)
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_completion_claim_blocked_when_no_confirming_tool(self) -> None:
        env = CertaintyEnvelope(tools_succeeded=[])
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.COMPLETION_CLAIM, "collect_base_docs"
        )
        assert ok is False
        assert reason == GuardrailReason.COMPLETION_NOT_CONFIRMED_BY_TOOL.value

    def test_completion_claim_allowed_for_unknown_sub_mode(self) -> None:
        """When sub-mode has no required-tools map entry, no restriction applies."""
        env = CertaintyEnvelope(tools_succeeded=[])
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.COMPLETION_CLAIM, "unknown_mode")
        assert ok is True

    # FIELD_CONFIRMED
    def test_field_confirmed_allowed_when_saved(self) -> None:
        env = CertaintyEnvelope(field_saved=True)
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.FIELD_CONFIRMED, "collect_element_data"
        )
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_field_confirmed_blocked_when_not_saved(self) -> None:
        env = CertaintyEnvelope(field_saved=False)
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.FIELD_CONFIRMED, "collect_element_data"
        )
        assert ok is False
        assert reason == GuardrailReason.FIELD_NOT_SAVED_BY_TOOL.value

    # NEXT_STEP_DESCRIPTION — anti-anticipation guard
    def test_next_step_blocked_on_first_destination_turn_with_guard_active(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=False,
        )
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_base_docs"
        )
        assert ok is False
        assert reason == GuardrailReason.ANTICIPATORY_NARRATION.value

    def test_next_step_allowed_when_claims_are_permitted(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=True,  # Guard not blocking
        )
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_base_docs"
        )
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_next_step_allowed_when_not_first_destination_turn(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=False,
            allowed_transition_claims=False,  # Would block if first turn
        )
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_personal"
        )
        assert ok is True

    # Parametrize all ClaimClass blocked cases with reason codes
    @pytest.mark.parametrize("claim_class,env_kwargs,expected_reason", [
        (
            ClaimClass.DOCS_RECEIVED,
            {},
            GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value,
        ),
        (
            ClaimClass.IMAGES_SENT,
            {},
            GuardrailReason.IMAGES_NOT_SENT_BY_TOOL.value,
        ),
        (
            ClaimClass.CASE_FINALIZED,
            {},
            GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value,
        ),
        (
            ClaimClass.FIELD_CONFIRMED,
            {},
            GuardrailReason.FIELD_NOT_SAVED_BY_TOOL.value,
        ),
        (
            ClaimClass.NEXT_STEP_DESCRIPTION,
            {"is_first_destination_turn": True, "allowed_transition_claims": False},
            GuardrailReason.ANTICIPATORY_NARRATION.value,
        ),
    ])
    def test_parametrized_blocked_claim_classes(
        self, claim_class: ClaimClass, env_kwargs: dict, expected_reason: str
    ) -> None:
        env = CertaintyEnvelope(**env_kwargs)
        ok, reason = evaluate_claim_eligibility(env, claim_class, "collect_base_docs")
        assert ok is False
        assert reason == expected_reason

    @pytest.mark.parametrize("claim_class,env_kwargs", [
        (ClaimClass.DOCS_RECEIVED, {"docs_confirmed": True}),
        (ClaimClass.IMAGES_SENT, {"images_sent": True}),
        (ClaimClass.CASE_FINALIZED, {"case_finalized": True}),
        (ClaimClass.FIELD_CONFIRMED, {"field_saved": True}),
        (ClaimClass.COMPLETION_CLAIM, {"tools_succeeded": ["confirmar_documentacion_base"]}),
    ])
    def test_parametrized_allowed_claim_classes(
        self, claim_class: ClaimClass, env_kwargs: dict
    ) -> None:
        env = CertaintyEnvelope(**env_kwargs)
        ok, reason = evaluate_claim_eligibility(env, claim_class, "collect_base_docs")
        assert ok is True
        assert reason == GuardrailReason.ALLOWED.value


# =============================================================================
# 9. evaluate_kickoff_truthfulness
# =============================================================================


class TestEvaluateKickoffTruthfulness:
    """Kickoff truthfulness guard: first-destination-turn stale content check."""

    def test_blocked_on_first_destination_turn_with_allowed_false(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=False,
        )
        is_truthful, reason = evaluate_kickoff_truthfulness(env, "collect_base_docs")
        assert is_truthful is False
        assert reason == GuardrailReason.STALE_STEP_NARRATIVE.value

    def test_allowed_when_first_destination_but_claims_permitted(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=True,
        )
        is_truthful, reason = evaluate_kickoff_truthfulness(env, "collect_base_docs")
        assert is_truthful is True
        assert reason == GuardrailReason.ALLOWED.value

    def test_allowed_when_not_first_destination_turn(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=False,
            allowed_transition_claims=False,  # Does not block when not first turn
        )
        is_truthful, reason = evaluate_kickoff_truthfulness(env, "collect_personal")
        assert is_truthful is True
        assert reason == GuardrailReason.ALLOWED.value

    @pytest.mark.parametrize("sub_mode", [
        "collect_element_data",
        "collect_base_docs",
        "collect_personal",
        "collect_vehicle",
        "collect_workshop",
        "review_summary",
    ])
    def test_parametrized_stale_blocked_for_all_sub_modes(self, sub_mode: str) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=False,
        )
        is_truthful, reason = evaluate_kickoff_truthfulness(env, sub_mode)
        assert is_truthful is False
        assert reason == GuardrailReason.STALE_STEP_NARRATIVE.value


# =============================================================================
# 10. log_guardrail_triggered — smoke tests (no assertion on log output)
# =============================================================================


class TestLogGuardrailTriggered:
    """log_guardrail_triggered must not raise regardless of inputs."""

    def test_does_not_raise_with_minimal_args(self) -> None:
        log_guardrail_triggered(
            reason=GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value,
            sub_mode="collect_base_docs",
            allowed=False,
        )

    def test_does_not_raise_with_all_args(self) -> None:
        log_guardrail_triggered(
            reason=GuardrailReason.ALLOWED.value,
            sub_mode="collect_element_data",
            claim_class=ClaimClass.IMAGES_SENT.value,
            tool_name="enviar_imagenes_ejemplo",
            conversation_id="conv-test-001",
            allowed=True,
            extra={"enforced": False, "rewrite": "none"},
        )

    def test_does_not_raise_for_allowed_outcome(self) -> None:
        log_guardrail_triggered(
            reason=GuardrailReason.ALLOWED.value,
            sub_mode="review_summary",
            allowed=True,
        )

    def test_does_not_raise_for_blocked_outcome(self) -> None:
        log_guardrail_triggered(
            reason=GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value,
            sub_mode="review_summary",
            allowed=False,
        )

    @pytest.mark.parametrize("reason", [r.value for r in GuardrailReason])
    def test_does_not_raise_for_any_reason_code(self, reason: str) -> None:
        log_guardrail_triggered(reason=reason, sub_mode="collect_base_docs", allowed=False)


# =============================================================================
# 11. persist_envelope / load_envelope
# =============================================================================


class TestPersistLoadEnvelope:
    """Mode_context persistence: persist_envelope → load_envelope round-trip."""

    def test_persist_then_load_round_trip(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            docs_confirmed=True,
            case_finalized=False,
            tools_succeeded=["actualizar_datos_expediente"],
        )
        ctx: dict[str, Any] = {}
        persist_envelope(ctx, env)

        assert "certainty_envelope" in ctx
        assert isinstance(ctx["certainty_envelope"], dict)

        loaded = load_envelope(ctx, "collect_personal")
        assert loaded.sub_mode == "collect_personal"
        assert loaded.docs_confirmed is True
        assert loaded.case_finalized is False
        assert "actualizar_datos_expediente" in loaded.tools_succeeded

    def test_load_returns_empty_when_context_has_no_envelope(self) -> None:
        ctx: dict[str, Any] = {}
        loaded = load_envelope(ctx, "collect_vehicle")
        assert loaded.sub_mode == "collect_vehicle"
        assert loaded.docs_confirmed is False
        assert loaded.case_finalized is False

    def test_load_returns_empty_on_corrupt_string_value(self) -> None:
        ctx: dict[str, Any] = {"certainty_envelope": "NOT_A_DICT"}
        loaded = load_envelope(ctx, "collect_base_docs")
        assert loaded.sub_mode == "collect_base_docs"
        assert loaded.docs_confirmed is False

    def test_load_returns_empty_on_none_value(self) -> None:
        ctx: dict[str, Any] = {"certainty_envelope": None}
        loaded = load_envelope(ctx, "collect_workshop")
        assert loaded.sub_mode == "collect_workshop"

    def test_persist_stores_as_dict_not_envelope_object(self) -> None:
        env = CertaintyEnvelope.empty("collect_base_docs")
        ctx: dict[str, Any] = {}
        persist_envelope(ctx, env)
        assert isinstance(ctx["certainty_envelope"], dict)
        assert not isinstance(ctx["certainty_envelope"], CertaintyEnvelope)

    def test_persist_overwrites_previous_envelope(self) -> None:
        env1 = CertaintyEnvelope(sub_mode="collect_personal", docs_confirmed=True)
        env2 = CertaintyEnvelope(sub_mode="collect_vehicle", docs_confirmed=False)
        ctx: dict[str, Any] = {}
        persist_envelope(ctx, env1)
        persist_envelope(ctx, env2)
        loaded = load_envelope(ctx, "collect_vehicle")
        assert loaded.sub_mode == "collect_vehicle"
        assert loaded.docs_confirmed is False


# =============================================================================
# 12. build_prompt_certainty_context
# =============================================================================


class TestBuildPromptCertaintyContext:
    """Prompt injection: only public-safe fields are exposed."""

    def test_returns_expected_keys(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_workshop",
            allowed_transition_claims=False,
            blocked_claim_reason="stale step",
            kickoff_required=True,
        )
        ctx = build_prompt_certainty_context(env)
        assert set(ctx.keys()) == {
            "certainty_sub_mode",
            "certainty_allowed_transition_claims",
            "certainty_blocked_claim_reason",
            "certainty_kickoff_required",
        }

    def test_values_match_envelope_state(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            allowed_transition_claims=True,
            blocked_claim_reason=None,
            kickoff_required=False,
        )
        ctx = build_prompt_certainty_context(env)
        assert ctx["certainty_sub_mode"] == "review_summary"
        assert ctx["certainty_allowed_transition_claims"] is True
        assert ctx["certainty_blocked_claim_reason"] is None
        assert ctx["certainty_kickoff_required"] is False

    def test_does_not_expose_internal_tool_lists(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
            tools_called=["confirmar_fotos_elemento"],
            tools_succeeded=["confirmar_fotos_elemento"],
        )
        ctx = build_prompt_certainty_context(env)
        assert "tools_called" not in ctx
        assert "tools_succeeded" not in ctx
        assert "tools_failed" not in ctx

    def test_does_not_expose_raw_certainty_flags(self) -> None:
        env = CertaintyEnvelope(
            photos_confirmed=True,
            docs_confirmed=True,
            images_sent=True,
            case_finalized=True,
        )
        ctx = build_prompt_certainty_context(env)
        assert "photos_confirmed" not in ctx
        assert "docs_confirmed" not in ctx
        assert "images_sent" not in ctx
        assert "case_finalized" not in ctx

    @pytest.mark.parametrize("sub_mode", [
        "collect_element_data",
        "collect_base_docs",
        "collect_personal",
        "collect_vehicle",
        "collect_workshop",
        "review_summary",
    ])
    def test_sub_mode_passed_through_correctly(self, sub_mode: str) -> None:
        env = CertaintyEnvelope(sub_mode=sub_mode)
        ctx = build_prompt_certainty_context(env)
        assert ctx["certainty_sub_mode"] == sub_mode


# =============================================================================
# 13. GuardrailReason enum — reason code taxonomy completeness
# =============================================================================


class TestGuardrailReasonTaxonomy:
    """Reason codes must be string-serialisable and semantically named."""

    def test_all_reason_codes_are_strings(self) -> None:
        for reason in GuardrailReason:
            assert isinstance(reason.value, str)

    def test_required_progression_reason_codes_present(self) -> None:
        values = {r.value for r in GuardrailReason}
        assert "PROGRESSION_NOT_ALLOWED" in values
        assert "PROGRESSION_TOOL_NOT_CALLED" in values
        assert "PROGRESSION_TOOL_FAILED" in values
        assert "STALE_STEP_NARRATIVE" in values

    def test_required_claim_reason_codes_present(self) -> None:
        values = {r.value for r in GuardrailReason}
        assert "CLAIM_UNSUPPORTED" in values
        assert "DOCS_NOT_CONFIRMED_BY_TOOL" in values
        assert "IMAGES_NOT_SENT_BY_TOOL" in values
        assert "CASE_NOT_FINALIZED_BY_TOOL" in values
        assert "COMPLETION_NOT_CONFIRMED_BY_TOOL" in values
        assert "DELIVERY_UNCONFIRMED" in values
        assert "ANTICIPATORY_NARRATION" in values
        assert "FIELD_NOT_SAVED_BY_TOOL" in values

    def test_neutral_and_pass_codes_present(self) -> None:
        values = {r.value for r in GuardrailReason}
        assert "NOT_APPLICABLE" in values
        assert "ALLOWED" in values
