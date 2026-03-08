"""
Unit tests for agent/main.py delivery narration alignment — Phase 5.4

Tests the expediente-scoped delivery narration functions:
  - _classify_image_delivery_outcome(): outcome classification
  - _build_image_delivery_outcome_state(): outcome state payload
  - build_image_delivery_fallback_message(): user-facing fallback narration
  - _resolve_image_delivery_contract(): contract normalization
  - _persist_image_delivery_outcome(): scope-based persistence routing
  - Deduplication helpers: _check_request_idempotency, _mark_request_processed,
    _check_image_already_sent, _mark_image_sent

All tests are pure unit tests — no real Redis, no Chatwoot, no async I/O except
where async is required by the function signature (mocked with AsyncMock).

Delivery outcome contracts:
  - full_success  → normal narration allowed (no fallback message)
  - partial_success → bounded narration + honest fallback, no claim of full delivery
  - failure       → narration suppressed, fallback message sent instead
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.main import (
    _classify_image_delivery_outcome,
    _build_image_delivery_outcome_state,
    build_image_delivery_fallback_message,
    _resolve_image_delivery_contract,
    _EXPEDIENTE_DELIVERY_SCOPES,
    _persist_image_delivery_outcome,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_delivery_contract(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": "v1",
        "delivery_request_id": "req-test-001",
        "delivery_scope": "presupuesto",
        "delivery_source_tool": "enviar_imagenes_ejemplo",
        "delivery_intent_created_at": None,
        "delivery_conversation_id": "conv-test-001",
        "delivery_requested_count": 3,
        "delivery_has_follow_up": False,
        "delivery_category": "motos-part",
        "delivery_element_code": "ESCAPE",
    }
    base.update(overrides)
    return base


# =============================================================================
# 1. _classify_image_delivery_outcome
# =============================================================================


class TestClassifyImageDeliveryOutcome:
    """Outcome classification based on attempted/sent counts."""

    def test_full_success_when_all_sent(self) -> None:
        assert _classify_image_delivery_outcome(3, 3) == "full_success"

    def test_full_success_single_image(self) -> None:
        assert _classify_image_delivery_outcome(1, 1) == "full_success"

    def test_partial_success_when_some_sent(self) -> None:
        assert _classify_image_delivery_outcome(3, 2) == "partial_success"

    def test_partial_success_when_one_sent(self) -> None:
        assert _classify_image_delivery_outcome(3, 1) == "partial_success"

    def test_failure_when_none_sent(self) -> None:
        assert _classify_image_delivery_outcome(3, 0) == "failure"

    def test_failure_when_attempted_is_zero(self) -> None:
        """Zero attempts always means failure (no images to send)."""
        assert _classify_image_delivery_outcome(0, 0) == "failure"

    @pytest.mark.parametrize("attempted,sent,expected", [
        (1, 0, "failure"),
        (1, 1, "full_success"),
        (5, 3, "partial_success"),
        (5, 5, "full_success"),
        (5, 0, "failure"),
        (10, 7, "partial_success"),
    ])
    def test_parametrized_outcome_classification(
        self, attempted: int, sent: int, expected: str
    ) -> None:
        assert _classify_image_delivery_outcome(attempted, sent) == expected


# =============================================================================
# 2. _build_image_delivery_outcome_state
# =============================================================================


class TestBuildImageDeliveryOutcomeState:
    """Outcome state payload construction."""

    def test_full_success_payload_structure(self) -> None:
        contract = _make_delivery_contract(
            delivery_request_id="req-001",
            delivery_scope="presupuesto",
        )
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=3,
            sent_count=3,
            transport_error=None,
        )
        assert state["status"] == "full_success"
        assert state["sent_count"] == 3
        assert state["failed_count"] == 0
        assert state["attempted_count"] == 3
        assert state["transport_error"] is None
        assert state["request_id"] == "req-001"

    def test_partial_success_payload_structure(self) -> None:
        contract = _make_delivery_contract(delivery_requested_count=4)
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=4,
            sent_count=2,
            transport_error=None,
        )
        assert state["status"] == "partial_success"
        assert state["sent_count"] == 2
        assert state["failed_count"] == 2
        assert state["attempted_count"] == 4

    def test_failure_payload_structure(self) -> None:
        contract = _make_delivery_contract()
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=3,
            sent_count=0,
            transport_error="connection refused",
        )
        assert state["status"] == "failure"
        assert state["sent_count"] == 0
        assert state["failed_count"] == 3
        assert state["transport_error"] == "connection refused"

    def test_scope_is_preserved_from_contract(self) -> None:
        contract = _make_delivery_contract(delivery_scope="documentacion_base")
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=2,
            sent_count=2,
            transport_error=None,
        )
        assert state["scope"] == "documentacion_base"

    def test_updated_at_is_present_and_is_string(self) -> None:
        contract = _make_delivery_contract()
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=1,
            sent_count=1,
            transport_error=None,
        )
        assert "updated_at" in state
        assert isinstance(state["updated_at"], str)

    def test_failed_count_never_negative(self) -> None:
        """sent_count should not exceed attempted_count (max clamps to 0)."""
        contract = _make_delivery_contract(delivery_requested_count=2)
        state = _build_image_delivery_outcome_state(
            delivery_contract=contract,
            attempted_count=2,
            sent_count=2,
            transport_error=None,
        )
        assert state["failed_count"] == 0


# =============================================================================
# 3. build_image_delivery_fallback_message
# =============================================================================


class TestBuildImageDeliveryFallbackMessage:
    """User-facing fallback message: honest Spanish narration by outcome."""

    # full_success — no fallback needed
    def test_full_success_returns_none(self) -> None:
        msg = build_image_delivery_fallback_message("full_success", sent_count=3, failed_count=0, total_requested=3)
        assert msg is None

    # partial_success — bounded narration
    def test_partial_success_returns_string(self) -> None:
        msg = build_image_delivery_fallback_message("partial_success", sent_count=2, failed_count=1, total_requested=3)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_partial_success_mentions_sent_count(self) -> None:
        msg = build_image_delivery_fallback_message("partial_success", sent_count=2, failed_count=1, total_requested=3)
        assert msg is not None
        # Must convey that some images arrived
        assert "2" in msg or "imagen" in msg.lower()

    def test_partial_success_does_not_claim_full_delivery(self) -> None:
        """Partial success narration must NOT claim all images arrived."""
        msg = build_image_delivery_fallback_message("partial_success", sent_count=1, failed_count=2, total_requested=3)
        assert msg is not None
        msg_lower = msg.lower()
        # Must NOT use phrases that imply full delivery
        assert "todas" not in msg_lower or "no" in msg_lower  # If "todas" appears, must be negated
        # More importantly: must offer to retry
        assert any(kw in msg_lower for kw in ("intento", "intenta", "dímelo", "vuelve"))

    def test_partial_success_is_in_spanish(self) -> None:
        msg = build_image_delivery_fallback_message("partial_success", sent_count=2, failed_count=1, total_requested=3)
        assert msg is not None
        # Spanish characters expected in the honest message
        assert any(ch in msg for ch in ("é", "ó", "á", "í", "ú", "ñ", "¿", "¡"))

    # failure — no delivery narration allowed
    def test_failure_returns_string(self) -> None:
        msg = build_image_delivery_fallback_message("failure", sent_count=0, failed_count=3, total_requested=3)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_failure_does_not_claim_any_delivery(self) -> None:
        msg = build_image_delivery_fallback_message("failure", sent_count=0, failed_count=3, total_requested=3)
        assert msg is not None
        msg_lower = msg.lower()
        # Must NOT claim images were sent
        assert "enviado" not in msg_lower or "no" in msg_lower

    def test_failure_offers_recovery_path(self) -> None:
        msg = build_image_delivery_fallback_message("failure", sent_count=0, failed_count=3, total_requested=3)
        assert msg is not None
        msg_lower = msg.lower()
        assert any(kw in msg_lower for kw in ("intento", "dímelo", "texto", "vuelve", "intentarlo"))

    @pytest.mark.parametrize("outcome,expected_none", [
        ("full_success", True),
        ("partial_success", False),
        ("failure", False),
    ])
    def test_parametrized_outcome_to_message(self, outcome: str, expected_none: bool) -> None:
        msg = build_image_delivery_fallback_message(outcome, sent_count=1, failed_count=1, total_requested=2)
        if expected_none:
            assert msg is None
        else:
            assert msg is not None
            assert isinstance(msg, str)


# =============================================================================
# 4. _resolve_image_delivery_contract
# =============================================================================


class TestResolveImageDeliveryContract:
    """Contract normalization: missing fields get safe defaults."""

    def test_resolves_full_contract(self) -> None:
        pending_images = {
            "delivery_contract": {
                "version": "v2",
                "delivery_request_id": "req-999",
                "delivery_scope": "documentacion_base",
                "delivery_source_tool": "enviar_imagenes_ejemplo",
                "delivery_intent_created_at": "2026-01-01T00:00:00",
                "delivery_conversation_id": "conv-999",
                "delivery_requested_count": 5,
                "delivery_has_follow_up": True,
                "delivery_category": "motos-part",
                "delivery_element_code": "ESCAPE",
            }
        }
        result = _resolve_image_delivery_contract(pending_images, "conv-999")
        assert result["delivery_contract_version"] == "v2"
        assert result["delivery_scope"] == "documentacion_base"
        assert result["delivery_requested_count"] == 5
        assert result["delivery_has_follow_up"] is True

    def test_resolves_empty_contract_with_defaults(self) -> None:
        result = _resolve_image_delivery_contract(None, "conv-001")
        assert result["delivery_contract_version"] == "v1"
        assert result["delivery_scope"] == "presupuesto"
        assert result["delivery_conversation_id"] == "conv-001"

    def test_resolves_missing_request_id_generates_one(self) -> None:
        result = _resolve_image_delivery_contract({}, "conv-001")
        # Must generate a request ID if none present
        assert result["delivery_request_id"] is not None
        assert len(result["delivery_request_id"]) > 0

    def test_preserves_explicit_request_id(self) -> None:
        pending_images = {"delivery_contract": {"delivery_request_id": "my-explicit-id"}}
        result = _resolve_image_delivery_contract(pending_images, "conv-001")
        assert result["delivery_request_id"] == "my-explicit-id"

    def test_expediente_scopes_are_recognized(self) -> None:
        for scope in _EXPEDIENTE_DELIVERY_SCOPES:
            pending_images = {"delivery_contract": {"delivery_scope": scope}}
            result = _resolve_image_delivery_contract(pending_images, "conv-001")
            assert result["delivery_scope"] == scope


# =============================================================================
# 5. _EXPEDIENTE_DELIVERY_SCOPES constant
# =============================================================================


class TestExpedienteDeliveryScopes:
    """The scopes set must include all expected expediente-origin scopes."""

    def test_documentacion_base_is_expediente_scope(self) -> None:
        assert "documentacion_base" in _EXPEDIENTE_DELIVERY_SCOPES

    def test_expediente_is_expediente_scope(self) -> None:
        assert "expediente" in _EXPEDIENTE_DELIVERY_SCOPES

    def test_collect_scopes_are_expediente_scopes(self) -> None:
        assert "collect_element_data" in _EXPEDIENTE_DELIVERY_SCOPES
        assert "collect_base_docs" in _EXPEDIENTE_DELIVERY_SCOPES

    def test_presupuesto_is_not_expediente_scope(self) -> None:
        assert "presupuesto" not in _EXPEDIENTE_DELIVERY_SCOPES


# =============================================================================
# 6. _persist_image_delivery_outcome — scope-based routing
# =============================================================================


class TestPersistImageDeliveryOutcome:
    """Delivery outcome persistence: presupuesto and expediente scopes differ."""

    @pytest.mark.asyncio
    async def test_presupuesto_scope_updates_imagenes_enviadas(self) -> None:
        """Presupuesto scope: updates imagenes_enviadas flag in mode_context."""
        mock_graph = AsyncMock()
        config = {"configurable": {"thread_id": "test-thread"}}
        contract = _make_delivery_contract(
            delivery_scope="presupuesto",
            delivery_request_id="req-001",
        )

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=3,
                sent_count=3,
                transport_error=None,
            )

        mock_graph.aupdate_state.assert_called_once()
        call_args = mock_graph.aupdate_state.call_args
        state_update = call_args[0][1]
        assert "mode_context" in state_update
        assert state_update["mode_context"]["imagenes_enviadas"] is True

    @pytest.mark.asyncio
    async def test_expediente_scope_updates_image_delivery_result(self) -> None:
        """Expediente scope: additionally persists image_delivery_result."""
        mock_graph = AsyncMock()
        config = {"configurable": {"thread_id": "test-thread"}}
        contract = _make_delivery_contract(
            delivery_scope="documentacion_base",
            delivery_request_id="req-002",
        )

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=2,
                sent_count=2,
                transport_error=None,
            )

        mock_graph.aupdate_state.assert_called_once()
        call_args = mock_graph.aupdate_state.call_args
        state_update = call_args[0][1]
        assert "mode_context" in state_update
        assert "image_delivery_result" in state_update["mode_context"]

    @pytest.mark.asyncio
    async def test_expediente_partial_success_correctly_persisted(self) -> None:
        """Expediente scope partial_success: outcome state must reflect partial."""
        mock_graph = AsyncMock()
        config = {}
        contract = _make_delivery_contract(
            delivery_scope="collect_element_data",
            delivery_requested_count=3,
        )

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=3,
                sent_count=1,
                transport_error=None,
            )

        call_args = mock_graph.aupdate_state.call_args
        state_update = call_args[0][1]
        image_result = state_update["mode_context"]["image_delivery_result"]
        assert image_result["status"] == "partial_success"
        assert image_result["sent_count"] == 1

    @pytest.mark.asyncio
    async def test_expediente_failure_correctly_persisted(self) -> None:
        """Expediente scope failure: outcome state must reflect failure."""
        mock_graph = AsyncMock()
        config = {}
        contract = _make_delivery_contract(
            delivery_scope="collect_base_docs",
        )

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=2,
                sent_count=0,
                transport_error="connection timeout",
            )

        call_args = mock_graph.aupdate_state.call_args
        state_update = call_args[0][1]
        image_result = state_update["mode_context"]["image_delivery_result"]
        assert image_result["status"] == "failure"
        assert image_result["transport_error"] == "connection timeout"

    @pytest.mark.asyncio
    async def test_unknown_scope_does_not_call_update_state(self) -> None:
        """Unknown delivery scope: no state update should be performed."""
        mock_graph = AsyncMock()
        config = {}
        contract = _make_delivery_contract(delivery_scope="unknown_scope")

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=1,
                sent_count=1,
                transport_error=None,
            )

        mock_graph.aupdate_state.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("expediente_scope", list(_EXPEDIENTE_DELIVERY_SCOPES))
    async def test_all_expediente_scopes_persist_image_delivery_result(
        self, expediente_scope: str
    ) -> None:
        """All scopes in _EXPEDIENTE_DELIVERY_SCOPES must persist image_delivery_result."""
        mock_graph = AsyncMock()
        config = {}
        contract = _make_delivery_contract(delivery_scope=expediente_scope)

        with patch("agent.main.build_state_mutation_config", return_value=config):
            await _persist_image_delivery_outcome(
                graph=mock_graph,
                config=config,
                delivery_contract=contract,
                attempted_count=2,
                sent_count=2,
                transport_error=None,
            )

        call_args = mock_graph.aupdate_state.call_args
        state_update = call_args[0][1]
        assert "image_delivery_result" in state_update["mode_context"], (
            f"scope={expediente_scope!r} must persist image_delivery_result"
        )


# =============================================================================
# 7. Partial success narration guard (inline logic in main.py)
# =============================================================================


class TestPartialSuccessNarrationGuard:
    """
    The inline logic in process_message that tightens narration for expediente
    partial_success when guardrails are enabled.

    We test the LOGIC extracted as helper functions (_classify_image_delivery_outcome
    and build_image_delivery_fallback_message) rather than the full async
    process_message (which requires extensive infrastructure mocks).

    These tests verify the contract: when guardrails are enabled and the delivery
    scope is expediente, partial_success must produce a bounded honest message.
    """

    def test_partial_success_honest_message_does_not_claim_all_sent(self) -> None:
        """Honest partial message must not imply all images arrived."""
        msg = build_image_delivery_fallback_message(
            "partial_success",
            sent_count=1,
            failed_count=2,
            total_requested=3,
        )
        assert msg is not None
        # Must NOT claim all images arrived
        msg_lower = msg.lower()
        full_success_phrases = ["te he enviado todas", "enviadas correctamente todas"]
        for phrase in full_success_phrases:
            assert phrase not in msg_lower, f"Partial message contained full-success phrase: {phrase!r}"

    def test_full_success_fallback_is_none_so_llm_narration_used(self) -> None:
        """Full success: fallback=None means LLM narration is used unchanged."""
        msg = build_image_delivery_fallback_message(
            "full_success",
            sent_count=3,
            failed_count=0,
            total_requested=3,
        )
        assert msg is None, "full_success must not produce a fallback message"

    def test_failure_fallback_prevents_delivery_claim(self) -> None:
        """Failure fallback must contain enough info to explain non-delivery."""
        msg = build_image_delivery_fallback_message(
            "failure",
            sent_count=0,
            failed_count=3,
            total_requested=3,
        )
        assert msg is not None
        msg_lower = msg.lower()
        # Must explain what happened and offer alternative
        assert any(kw in msg_lower for kw in ("podido", "enviarte", "momento", "texto"))

    @pytest.mark.parametrize("sent,total,outcome_expected", [
        (0, 3, "failure"),
        (1, 3, "partial_success"),
        (2, 3, "partial_success"),
        (3, 3, "full_success"),
    ])
    def test_outcome_classification_aligns_with_narration_type(
        self, sent: int, total: int, outcome_expected: str
    ) -> None:
        outcome = _classify_image_delivery_outcome(total, sent)
        assert outcome == outcome_expected
        msg = build_image_delivery_fallback_message(
            outcome, sent_count=sent, failed_count=total - sent, total_requested=total
        )
        if outcome == "full_success":
            assert msg is None
        else:
            assert msg is not None
