"""
Tests for agent/modes/expediente_guardrails.py — Phase 5 verification.

Covers:
  - CertaintyEnvelope: construction, to_dict/from_dict round-trip, empty()
  - normalize_tool_payload: canonical, fsm-compat, and legacy payload shapes
  - evaluate_progression_eligibility: all transition rules
  - evaluate_claim_eligibility: all ClaimClass variants
  - evaluate_kickoff_truthfulness: first-destination-turn guard
  - log_guardrail_triggered: smoke test (no assertion on log output)
  - persist_envelope / load_envelope: mode_context persistence helpers
  - build_prompt_certainty_context: field extraction for prompt injection

All tests are pure unit tests — no database, no Redis, no async.
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


# =============================================================================
# CertaintyEnvelope
# =============================================================================


class TestCertaintyEnvelope:
    """Constructor, serialisation, and empty() factory."""

    def test_empty_defaults_all_false(self) -> None:
        env = CertaintyEnvelope.empty("collect_base_docs")
        assert env.sub_mode == "collect_base_docs"
        assert env.photos_confirmed is False
        assert env.docs_confirmed is False
        assert env.images_sent is False
        assert env.case_finalized is False
        assert env.all_elements_complete is False
        assert env.field_saved is False
        assert env.transition_triggered is False
        assert env.allowed_transition_claims is True  # safe default
        assert env.kickoff_required is False
        assert env.tools_called == []
        assert env.tools_succeeded == []
        assert env.tools_failed == []
        assert env.version == CERTAINTY_CONTRACT_VERSION

    def test_to_dict_contains_all_fields(self) -> None:
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

    def test_from_dict_round_trip(self) -> None:
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

    def test_from_dict_with_missing_keys_uses_defaults(self) -> None:
        """from_dict must not raise on sparse dicts (forward-compat)."""
        restored = CertaintyEnvelope.from_dict({"sub_mode": "collect_vehicle"})
        assert restored.sub_mode == "collect_vehicle"
        assert restored.photos_confirmed is False
        assert restored.version == CERTAINTY_CONTRACT_VERSION


# =============================================================================
# normalize_tool_payload
# =============================================================================


class TestNormalizeToolPayload:
    """Normaliser merges heterogeneous payloads into the envelope."""

    # -------------------------------------------------------------------------
    # Tool call tracking
    # -------------------------------------------------------------------------

    def test_tracks_called_tool_name(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("my_tool", result, "collect_personal")
        assert "my_tool" in env.tools_called
        assert "my_tool" in env.tools_succeeded

    def test_tracks_failed_tool_name(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("my_tool", result, "collect_personal")
        assert "my_tool" in env.tools_called
        assert "my_tool" in env.tools_failed
        assert "my_tool" not in env.tools_succeeded

    def test_does_not_duplicate_tool_name(self) -> None:
        """Calling normalise twice with same tool should not duplicate entries."""
        result = _make_success_result()
        env1 = normalize_tool_payload("tool_a", result, "collect_base_docs")
        env2 = normalize_tool_payload("tool_a", result, "collect_base_docs", existing_envelope=env1)
        assert env2.tools_called.count("tool_a") == 1
        assert env2.tools_succeeded.count("tool_a") == 1

    # -------------------------------------------------------------------------
    # String vs dict input
    # -------------------------------------------------------------------------

    def test_accepts_dict_payload(self) -> None:
        env = normalize_tool_payload(
            "confirmar_documentacion_base",
            {"success": True},
            "collect_base_docs",
        )
        assert env.docs_confirmed is True

    def test_handles_invalid_json_string(self) -> None:
        """Non-JSON string must not raise."""
        env = normalize_tool_payload("some_tool", "NOT JSON {{", "collect_personal")
        assert "some_tool" in env.tools_failed  # success=False (missing key)

    # -------------------------------------------------------------------------
    # Canonical _internal_flags layer
    # -------------------------------------------------------------------------

    def test_case_finalized_from_internal_flags(self) -> None:
        result = _make_success_result(
            _internal_flags={"case_finalized": True}
        )
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is True

    def test_images_sent_from_internal_flags(self) -> None:
        result = _make_success_result(
            _internal_flags={"imagenes_enviadas": True}
        )
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is True

    # -------------------------------------------------------------------------
    # Photos confirmed
    # -------------------------------------------------------------------------

    def test_photos_confirmed_requires_flag_and_tool_name(self) -> None:
        """photos_confirmed requires BOTH the right tool_name AND the flag."""
        result = _make_success_result(photos_confirmed=True)
        env = normalize_tool_payload("confirmar_fotos_elemento", result, "collect_element_data")
        assert env.photos_confirmed is True

    def test_photos_confirmed_false_without_flag(self) -> None:
        """Even with success, photos_confirmed must not be set if flag is missing."""
        result = _make_success_result()  # No photos_confirmed in payload
        env = normalize_tool_payload("confirmar_fotos_elemento", result, "collect_element_data")
        assert env.photos_confirmed is False

    def test_photos_confirmed_false_wrong_tool(self) -> None:
        result = _make_success_result(photos_confirmed=True)
        env = normalize_tool_payload("other_tool", result, "collect_element_data")
        assert env.photos_confirmed is False

    # -------------------------------------------------------------------------
    # Docs confirmed
    # -------------------------------------------------------------------------

    def test_docs_confirmed_when_confirmar_documentacion_base_succeeds(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("confirmar_documentacion_base", result, "collect_base_docs")
        assert env.docs_confirmed is True

    def test_docs_confirmed_false_when_tool_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("confirmar_documentacion_base", result, "collect_base_docs")
        assert env.docs_confirmed is False

    # -------------------------------------------------------------------------
    # Images sent via enviar_imagenes_ejemplo
    # -------------------------------------------------------------------------

    def test_images_sent_when_status_is_success(self) -> None:
        result = json.dumps({"success": True, "status": "success"})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is True

    def test_images_not_sent_when_status_is_failure(self) -> None:
        result = json.dumps({"success": False, "status": "failure"})
        env = normalize_tool_payload("enviar_imagenes_ejemplo", result, "collect_element_data")
        assert env.images_sent is False

    # -------------------------------------------------------------------------
    # Case finalised
    # -------------------------------------------------------------------------

    def test_case_finalized_from_tool_name_and_success(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is True

    def test_case_finalized_false_when_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("finalizar_expediente", result, "review_summary")
        assert env.case_finalized is False

    # -------------------------------------------------------------------------
    # All elements complete (legacy + context updates)
    # -------------------------------------------------------------------------

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

    def test_all_elements_complete_from_fsm_state_update(self) -> None:
        result = json.dumps({
            "success": True,
            "fsm_state_update": {
                "case_collection": {"all_elements_complete": True}
            },
        })
        env = normalize_tool_payload("completar_elemento_actual", result, "collect_element_data")
        assert env.all_elements_complete is True

    # -------------------------------------------------------------------------
    # Field saved
    # -------------------------------------------------------------------------

    def test_field_saved_when_guardar_datos_elemento_succeeds(self) -> None:
        result = _make_success_result()
        env = normalize_tool_payload("guardar_datos_elemento", result, "collect_element_data")
        assert env.field_saved is True

    def test_field_saved_false_when_fails(self) -> None:
        result = _make_failure_result()
        env = normalize_tool_payload("guardar_datos_elemento", result, "collect_element_data")
        assert env.field_saved is False

    # -------------------------------------------------------------------------
    # Additive accumulation across multiple tools
    # -------------------------------------------------------------------------

    def test_accumulates_across_multiple_calls(self) -> None:
        """Normalise multiple tools in sequence — envelope is additive."""
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

    def test_existing_envelope_preserved_when_new_tool_fails(self) -> None:
        """A subsequent tool failure must not reset earlier successes."""
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
        assert env2.docs_confirmed is True  # Still confirmed from first call


# =============================================================================
# evaluate_progression_eligibility
# =============================================================================


class TestEvaluateProgressionEligibility:
    """Transition gate rules for each sub-mode pair."""

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

    def test_base_docs_to_personal_blocked_when_docs_not_confirmed(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_base_docs",
            docs_confirmed=False,
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is False
        assert reason == GuardrailReason.DOCS_NOT_CONFIRMED_BY_TOOL.value

    # collect_personal → collect_vehicle
    def test_personal_to_vehicle_allowed_when_tool_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            tools_succeeded=["actualizar_datos_expediente"],
        )
        allowed, _ = evaluate_progression_eligibility(env, "collect_vehicle")
        assert allowed is True

    def test_personal_to_vehicle_blocked_when_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_vehicle")
        assert allowed is False
        assert reason == GuardrailReason.PROGRESSION_TOOL_NOT_CALLED.value

    # collect_vehicle → collect_workshop
    def test_vehicle_to_workshop_allowed_when_tool_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_vehicle",
            tools_succeeded=["actualizar_datos_expediente"],
        )
        allowed, _ = evaluate_progression_eligibility(env, "collect_workshop")
        assert allowed is True

    def test_vehicle_to_workshop_blocked_when_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_vehicle",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "collect_workshop")
        assert allowed is False

    # collect_workshop → review_summary
    def test_workshop_to_review_allowed_when_taller_tool_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_workshop",
            tools_succeeded=["actualizar_datos_taller"],
        )
        allowed, _ = evaluate_progression_eligibility(env, "review_summary")
        assert allowed is True

    def test_workshop_to_review_blocked_when_taller_tool_not_called(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_workshop",
            tools_succeeded=[],
        )
        allowed, reason = evaluate_progression_eligibility(env, "review_summary")
        assert allowed is False

    # review_summary → edit (via editar_expediente)
    def test_review_to_edit_allowed_when_editar_expediente_succeeded(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="review_summary",
            tools_succeeded=["editar_expediente"],
        )
        allowed, _ = evaluate_progression_eligibility(env, "collect_personal")
        assert allowed is True

    # Generic unknown transition — fail-open
    def test_unknown_transition_pair_is_allowed(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
        )
        # Unknown target — not covered by specific rules
        allowed, reason = evaluate_progression_eligibility(env, "some_future_mode")
        assert allowed is True
        assert reason == GuardrailReason.ALLOWED.value


# =============================================================================
# evaluate_claim_eligibility
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
        ok, _ = evaluate_claim_eligibility(env, ClaimClass.IMAGES_SENT, "collect_element_data")
        assert ok is True

    def test_images_sent_blocked_when_not_sent(self) -> None:
        env = CertaintyEnvelope(images_sent=False)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.IMAGES_SENT, "collect_element_data")
        assert ok is False
        assert reason == GuardrailReason.IMAGES_NOT_SENT_BY_TOOL.value

    # CASE_FINALIZED
    def test_case_finalized_allowed_when_finalized(self) -> None:
        env = CertaintyEnvelope(case_finalized=True)
        ok, _ = evaluate_claim_eligibility(env, ClaimClass.CASE_FINALIZED, "review_summary")
        assert ok is True

    def test_case_finalized_blocked_when_not_finalized(self) -> None:
        env = CertaintyEnvelope(case_finalized=False)
        ok, reason = evaluate_claim_eligibility(env, ClaimClass.CASE_FINALIZED, "review_summary")
        assert ok is False
        assert reason == GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value

    # COMPLETION_CLAIM — sub-mode specific tools
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
        ok, _ = evaluate_claim_eligibility(env, ClaimClass.COMPLETION_CLAIM, sub_mode)
        assert ok is True

    def test_completion_claim_blocked_when_no_confirming_tool(self) -> None:
        env = CertaintyEnvelope(tools_succeeded=[])
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.COMPLETION_CLAIM, "collect_base_docs"
        )
        assert ok is False
        assert reason == GuardrailReason.COMPLETION_NOT_CONFIRMED_BY_TOOL.value

    def test_completion_claim_allowed_for_unknown_sub_mode(self) -> None:
        """When sub-mode is not in the required-tools map, no restriction applies."""
        env = CertaintyEnvelope(tools_succeeded=[])
        ok, _ = evaluate_claim_eligibility(env, ClaimClass.COMPLETION_CLAIM, "unknown_mode")
        assert ok is True

    # FIELD_CONFIRMED
    def test_field_confirmed_allowed_when_saved(self) -> None:
        env = CertaintyEnvelope(field_saved=True)
        ok, _ = evaluate_claim_eligibility(env, ClaimClass.FIELD_CONFIRMED, "collect_element_data")
        assert ok is True

    def test_field_confirmed_blocked_when_not_saved(self) -> None:
        env = CertaintyEnvelope(field_saved=False)
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.FIELD_CONFIRMED, "collect_element_data"
        )
        assert ok is False
        assert reason == GuardrailReason.FIELD_NOT_SAVED_BY_TOOL.value

    # NEXT_STEP_DESCRIPTION
    def test_next_step_blocked_on_first_destination_turn_with_guard(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=False,
        )
        ok, reason = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_base_docs"
        )
        assert ok is False
        assert reason == GuardrailReason.ANTICIPATORY_NARRATION.value

    def test_next_step_allowed_when_claims_are_allowed(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=True,
        )
        ok, _ = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_base_docs"
        )
        assert ok is True

    def test_next_step_allowed_when_not_first_destination_turn(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=False,
            allowed_transition_claims=False,  # Would block if first turn
        )
        ok, _ = evaluate_claim_eligibility(
            env, ClaimClass.NEXT_STEP_DESCRIPTION, "collect_base_docs"
        )
        assert ok is True


# =============================================================================
# evaluate_kickoff_truthfulness
# =============================================================================


class TestEvaluateKickoffTruthfulness:
    def test_blocked_on_first_destination_turn_with_stale_allowed_false(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=False,
        )
        is_truthful, reason = evaluate_kickoff_truthfulness(env, "collect_base_docs")
        assert is_truthful is False
        assert reason == GuardrailReason.STALE_STEP_NARRATIVE.value

    def test_allowed_when_first_destination_but_claims_ok(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=True,
            allowed_transition_claims=True,
        )
        is_truthful, _ = evaluate_kickoff_truthfulness(env, "collect_base_docs")
        assert is_truthful is True

    def test_allowed_when_not_first_destination(self) -> None:
        env = CertaintyEnvelope(
            is_first_destination_turn=False,
            allowed_transition_claims=False,
        )
        is_truthful, _ = evaluate_kickoff_truthfulness(env, "collect_personal")
        assert is_truthful is True


# =============================================================================
# persist_envelope / load_envelope
# =============================================================================


class TestPersistLoadEnvelope:
    def test_persist_then_load_round_trip(self) -> None:
        env = CertaintyEnvelope(
            sub_mode="collect_personal",
            docs_confirmed=True,
            case_finalized=False,
            tools_succeeded=["actualizar_datos_expediente"],
        )
        ctx: dict[str, Any] = {}
        persist_envelope(ctx, env)

        # Must be stored as a dict under 'certainty_envelope'
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

    def test_load_returns_empty_on_corrupt_envelope(self) -> None:
        """Corrupt envelope must not raise — return empty instead."""
        ctx: dict[str, Any] = {"certainty_envelope": "NOT_A_DICT"}
        loaded = load_envelope(ctx, "collect_base_docs")
        assert loaded.sub_mode == "collect_base_docs"
        assert loaded.docs_confirmed is False


# =============================================================================
# build_prompt_certainty_context
# =============================================================================


class TestBuildPromptCertaintyContext:
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

    def test_does_not_expose_internal_flags(self) -> None:
        """Prompt context must not expose raw tools_called / tools_succeeded."""
        env = CertaintyEnvelope(
            sub_mode="collect_element_data",
            tools_called=["confirmar_fotos_elemento"],
            tools_succeeded=["confirmar_fotos_elemento"],
        )
        ctx = build_prompt_certainty_context(env)
        assert "tools_called" not in ctx
        assert "tools_succeeded" not in ctx


# =============================================================================
# log_guardrail_triggered — smoke test (no assertion on log output)
# =============================================================================


class TestLogGuardrailTriggered:
    def test_does_not_raise_with_minimal_args(self) -> None:
        """Function must not raise regardless of inputs."""
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
