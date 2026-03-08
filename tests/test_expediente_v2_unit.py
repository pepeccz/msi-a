"""Unit tests for expediente-flow-redesign TASK-14 contracts."""

from __future__ import annotations

import hashlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

from agent.modes.expediente_mode import (
    _check_anti_repetition,
    _inject_step_prefix,
    _is_tool_blocked,
    _store_turn_hash,
)
from agent.services.image_handling import (
    IMAGE_FINALIZE_LOCK_PREFIX,
    _compute_finalize_lock_ttl,
    is_accepted_attachment,
)
from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE


@pytest.mark.parametrize(
    "message",
    [
        "listo",
        "Listo",
        "LISTO",
        "ya te las envie",
        "enviadas",
        "ya las mande",
        "ahi van",
        "ya estan",
        "listas ya",
        "listas",
    ],
)
def test_photo_completion_intent_regex_positive_cases(message: str) -> None:
    assert PHOTO_COMPLETION_INTENT_RE.search(message) is not None


@pytest.mark.parametrize(
    "message",
    [
        "las voy a enviar",
        "te las mando luego",
        "manana las mando",
        "ahora las mando",
        "voy a enviartelas",
    ],
)
def test_photo_completion_intent_regex_negative_cases(message: str) -> None:
    assert PHOTO_COMPLETION_INTENT_RE.search(message) is None


@pytest.mark.parametrize(
    ("attachment", "expected"),
    [
        ({"file_type": "image"}, True),
        ({"file_type": "file"}, True),
        ({"file_type": "audio"}, False),
        ({"file_type": "video"}, False),
        ({"file_type": "unknown-new-type"}, True),
        ({}, True),
    ],
)
def test_attachment_acceptance_matrix(attachment: dict, expected: bool) -> None:
    assert is_accepted_attachment(attachment) is expected


def test_finalize_lock_key_and_ttl_contracts() -> None:
    conversation_id = "conv-123"
    key = f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
    assert key == "finalize_lock:conv-123"

    with patch(
        "agent.services.image_handling.get_settings",
        return_value=SimpleNamespace(
            PHOTO_COMPLETION_WAIT_SECONDS=7,
            PHOTO_COMPLETION_RETRY_WAIT_SECONDS=11,
        ),
    ):
        ttl = _compute_finalize_lock_ttl()

    assert ttl == 23


def test_tool_matrix_blocks_guardar_datos_en_photos_phase() -> None:
    assert _is_tool_blocked("guardar_datos_elemento", "collect_element_data", "photos") is True


def test_tool_matrix_blocks_confirmar_fotos_en_data_phase() -> None:
    assert _is_tool_blocked("confirmar_fotos_elemento", "collect_element_data", "data") is True


def test_tool_matrix_never_blocks_escalar_a_humano() -> None:
    assert _is_tool_blocked("escalar_a_humano", "review_summary", None) is False


def test_tool_matrix_unknown_submode_is_fail_open() -> None:
    assert _is_tool_blocked("guardar_datos_elemento", "unknown_sub_mode", None) is False


def test_anti_repetition_first_message_has_no_prefix() -> None:
    mode_context: dict[str, list[str]] = {}
    message = "Necesito las fotos del elemento."
    assert _check_anti_repetition(message, mode_context) == message


def test_anti_repetition_repeated_message_gets_prefix() -> None:
    mode_context: dict[str, list[str]] = {}
    message = "Necesito las fotos del elemento."
    _store_turn_hash(message, mode_context)

    assert _check_anti_repetition(message, mode_context).startswith("Para recordarte: ")


def test_anti_repetition_hash_fifo_cap_two() -> None:
    mode_context: dict[str, list[str]] = {}
    m1 = "mensaje-1"
    m2 = "mensaje-2"
    m3 = "mensaje-3"
    _store_turn_hash(m1, mode_context)
    _store_turn_hash(m2, mode_context)
    _store_turn_hash(m3, mode_context)

    hashes = mode_context.get("_last_agent_turns")
    assert hashes is not None
    assert len(hashes) == 2
    assert hashlib.md5(m1.encode()).hexdigest() not in hashes
    assert hashlib.md5(m2.encode()).hexdigest() in hashes
    assert hashlib.md5(m3.encode()).hexdigest() in hashes


@pytest.mark.parametrize(
    ("sub_mode", "expected_prefix"),
    [
        ("collect_element_data", "📍 Paso 1/6 — Documentación de elementos"),
        ("collect_base_docs", "📍 Paso 2/6 — Documentación base"),
        ("collect_personal", "📍 Paso 3/6 — Datos personales"),
        ("collect_vehicle", "📍 Paso 4/6 — Datos del vehículo"),
        ("collect_workshop", "📍 Paso 5/6 — Certificado del taller"),
        ("review_summary", "📍 Paso 6/6 — Revisión final"),
    ],
)
def test_prefix_injection_maps_all_six_submodes(sub_mode: str, expected_prefix: str) -> None:
    result = _inject_step_prefix("Mensaje base", sub_mode)
    assert result.startswith(expected_prefix)


def test_prefix_injection_is_idempotent() -> None:
    prefixed = "📍 Paso 1/6 — Documentación de elementos\n\nMensaje base"
    assert _inject_step_prefix(prefixed, "collect_element_data") == prefixed


def test_prefix_injection_unknown_submode_is_unchanged() -> None:
    message = "Mensaje base"
    assert _inject_step_prefix(message, "not-registered") == message


# ===========================================================================
# Phase 5.5 — Certainty guardrails feature-flag contract tests
# ===========================================================================

from agent.modes.expediente_guardrails import (
    CertaintyEnvelope,
    ClaimClass,
    GuardrailReason,
    evaluate_claim_eligibility,
    evaluate_progression_eligibility,
    normalize_tool_payload,
)


class TestCertaintyFlagDefaultOff:
    """
    EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED defaults to False.
    When the flag is off, the guardrail evaluators must still work correctly
    (they are pure functions — the flag only controls whether the CALLER uses them).
    """

    def test_flag_default_is_false(self) -> None:
        """Feature flag must default to False for safe rollout."""
        from shared.config import get_settings
        settings = get_settings()
        assert settings.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED is False

    def test_empty_envelope_progression_to_personal_blocked(self) -> None:
        """
        An empty envelope starting at collect_base_docs must block progression
        to collect_personal (docs_confirmed not set).
        """
        envelope = CertaintyEnvelope.empty(sub_mode="collect_base_docs")
        allowed, reason = evaluate_progression_eligibility(
            envelope, sub_mode="collect_personal"
        )
        assert allowed is False
        assert reason  # must provide a reason code

    def test_empty_envelope_claim_blocked_regardless_of_flag(self) -> None:
        """
        An empty envelope must block COMPLETION_CLAIM for any sub-mode.
        The caller decides whether to enforce based on the feature flag.
        """
        envelope = CertaintyEnvelope.empty(sub_mode="collect_personal")
        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.COMPLETION_CLAIM, "collect_personal"
        )
        assert ok is False

    @pytest.mark.parametrize("sub_mode,target_sub_mode", [
        ("collect_element_data", "collect_base_docs"),
        ("collect_base_docs", "collect_personal"),
        ("collect_personal", "collect_vehicle"),
        ("collect_vehicle", "collect_workshop"),
        ("collect_workshop", "review_summary"),
    ])
    def test_empty_envelope_blocks_progression(
        self, sub_mode: str, target_sub_mode: str
    ) -> None:
        """An empty envelope blocks progression for the 5 canonical transitions."""
        envelope = CertaintyEnvelope.empty(sub_mode=sub_mode)
        allowed, _ = evaluate_progression_eligibility(
            envelope, sub_mode=target_sub_mode
        )
        assert allowed is False, (
            f"Empty envelope must block progression from {sub_mode!r} → {target_sub_mode!r}"
        )


class TestCertaintyEnvelopeEvidenceUnlocksClaim:
    """
    When the correct tool evidence is present in the envelope, evaluators must allow.
    This ensures the guardrails are not over-blocking when evidence IS available.
    """

    def test_confirmed_data_tool_unlocks_completion_claim_for_personal(self) -> None:
        """
        When actualizar_datos_expediente succeeds in collect_personal,
        COMPLETION_CLAIM must be allowed.
        """
        envelope = normalize_tool_payload(
            tool_name="actualizar_datos_expediente",
            raw_result={
                "success": True,
                "_internal_flags": {
                    "confirmed_fields": ["nombre", "apellido", "email"],
                },
            },
            current_sub_mode="collect_personal",
        )
        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.COMPLETION_CLAIM, "collect_personal"
        )
        assert ok is True, (
            f"COMPLETION_CLAIM must be allowed after actualizar_datos_expediente success; "
            f"reason: {reason}"
        )

    def test_finalizacion_tool_unlocks_case_finalized_claim(self) -> None:
        """
        When finalizar_expediente succeeds, CASE_FINALIZED must be allowed.
        """
        envelope = normalize_tool_payload(
            tool_name="finalizar_expediente",
            raw_result={
                "success": True,
                "_internal_flags": {
                    "case_finalized": True,
                },
            },
            current_sub_mode="review_summary",
        )
        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.CASE_FINALIZED, "review_summary"
        )
        assert ok is True, (
            f"CASE_FINALIZED claim must be allowed after finalizar_expediente success; "
            f"reason: {reason}"
        )

    def test_fotos_tool_unlocks_completion_claim_for_element_data(self) -> None:
        """confirmar_fotos_elemento success must unlock COMPLETION_CLAIM in collect_element_data."""
        envelope = normalize_tool_payload(
            tool_name="confirmar_fotos_elemento",
            raw_result={
                "success": True,
                "_internal_flags": {"photos_confirmed": True},
            },
            current_sub_mode="collect_element_data",
        )
        ok, reason = evaluate_claim_eligibility(
            envelope, ClaimClass.COMPLETION_CLAIM, "collect_element_data"
        )
        assert ok is True, f"reason: {reason}"


class TestGuardrailReasonTaxonomy:
    """
    GuardrailReason values must be stable strings (used in logs and metrics).
    Any rename would break log-based alerting.
    """

    def test_progression_not_allowed_reason_exists(self) -> None:
        assert isinstance(GuardrailReason.PROGRESSION_NOT_ALLOWED, GuardrailReason)

    def test_allowed_reason_exists(self) -> None:
        assert isinstance(GuardrailReason.ALLOWED, GuardrailReason)

    def test_all_reasons_are_strings(self) -> None:
        for reason in GuardrailReason:
            assert isinstance(reason.value, str), (
                f"GuardrailReason.{reason.name}.value must be str, got {type(reason.value)}"
            )

    @pytest.mark.parametrize("claim_class", list(ClaimClass))
    def test_all_claim_classes_are_strings(self, claim_class: ClaimClass) -> None:
        assert isinstance(claim_class.value, str)

    def test_key_reason_codes_match_expected_values(self) -> None:
        """Regression guard: reason code strings must not change (used in logs/metrics)."""
        assert GuardrailReason.PROGRESSION_NOT_ALLOWED.value == "PROGRESSION_NOT_ALLOWED"
        assert GuardrailReason.ALLOWED.value == "ALLOWED"
        assert GuardrailReason.CLAIM_UNSUPPORTED.value == "CLAIM_UNSUPPORTED"
        assert GuardrailReason.CASE_NOT_FINALIZED_BY_TOOL.value == "CASE_NOT_FINALIZED_BY_TOOL"
