"""
Unit tests for AC-12 — Guard telemetry standardization.

Spec R12: Every guard firing MUST emit a structured log event with ALL of:
guard_name, reason, scope, precio_comunicado, reprice_allowed_this_turn,
original_len, final_len, stripped_paragraph_count.

Tests use structlog test captures via structlog.testing.capture_logs().
"""
from __future__ import annotations

import pytest
import structlog.testing


def _mc_post_price(**overrides) -> dict:
    mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
    mc.update(overrides)
    return mc


class TestR5GuardEmitsAllFields:
    """AC-12.1: guard_no_reprice_post_price must emit all 8 required fields."""

    def test_r5_guard_emits_all_8_fields(self):
        from agent.modes.pre_expediente_mode import guard_no_reprice_post_price
        import structlog

        # Use a real structlog bound logger that capture_logs intercepts
        logger = structlog.get_logger()

        # Text that will trigger R-5 (has currency paragraph)
        text = "El presupuesto es de 410€ +IVA.\n\n¿Abrimos expediente o tienes alguna duda?"
        mc = _mc_post_price()

        with structlog.testing.capture_logs() as cap:
            guard_no_reprice_post_price(
                text=text,
                mc=mc,
                node_logger=logger,
                conversation_id="test-conv",
            )

        # Guard must have fired and emitted at least one log event
        fired = [e for e in cap if e.get("guard_name") == "no_reprice_post_price"]
        assert len(fired) >= 1, f"Expected at least one guard_fired log. Got: {cap}"

        event = fired[0]
        # All 8 required fields must be present
        required_fields = {
            "guard_name", "reason", "scope", "precio_comunicado",
            "reprice_allowed_this_turn", "original_len", "final_len",
            "stripped_paragraph_count",
        }
        # Check via mc_keys (current shape) or direct keys (new shape)
        # The test accepts EITHER the mc_keys dict containing the fields OR
        # the fields at the top level — the implementation chooses the shape.
        all_keys: set[str] = set(event.keys())
        mc_keys_dict: dict = event.get("mode_context_snapshot") or {}
        all_available = all_keys | set(mc_keys_dict.keys())

        missing = required_fields - all_available
        assert not missing, (
            f"Missing required telemetry fields: {missing}. Event: {event}"
        )


class TestConvGuardEmitsAllFields:
    """AC-12.1: guard_no_reprice_without_tool must emit all 8 required fields."""

    def test_conv_guard_emits_all_8_fields(self):
        from agent.modes.pre_expediente_mode import guard_no_reprice_without_tool
        import structlog

        logger = structlog.get_logger()

        # ≥2 signals to trigger the guard
        text = "Son 410€.\n\n⚠️ Requiere certificación."
        mc = _mc_post_price()

        with structlog.testing.capture_logs() as cap:
            guard_no_reprice_without_tool(
                text=text,
                mc=mc,
                tools_called_this_turn=[],
                node_logger=logger,
                conversation_id="test-conv",
            )

        fired = [e for e in cap if e.get("guard_name") == "no_reprice_without_tool"]
        assert len(fired) >= 1, f"Expected at least one guard_fired log. Got: {cap}"

        event = fired[0]
        required_fields = {
            "guard_name", "reason", "scope", "precio_comunicado",
            "reprice_allowed_this_turn", "original_len", "final_len",
            "stripped_paragraph_count",
        }
        all_keys: set[str] = set(event.keys())
        mc_keys_dict: dict = event.get("mode_context_snapshot") or {}
        all_available = all_keys | set(mc_keys_dict.keys())

        missing = required_fields - all_available
        assert not missing, (
            f"Missing required telemetry fields: {missing}. Event: {event}"
        )


class TestGuardTelemetryNeverRaises:
    """AC-12.1 safety: passing node_logger=None must not raise any exception."""

    def test_r5_guard_no_exception_with_none_logger(self):
        from agent.modes.pre_expediente_mode import guard_no_reprice_post_price

        text = "El presupuesto es de 410€ +IVA.\n\n¿Abrimos expediente?"
        # Must not raise
        result = guard_no_reprice_post_price(
            text=text, mc=_mc_post_price(), node_logger=None, conversation_id=""
        )
        assert isinstance(result, str)

    def test_conv_guard_no_exception_with_none_logger(self):
        from agent.modes.pre_expediente_mode import guard_no_reprice_without_tool

        text = "Son 410€.\n\n⚠️ Advertencia."
        result = guard_no_reprice_without_tool(
            text=text,
            mc=_mc_post_price(),
            tools_called_this_turn=[],
            node_logger=None,
            conversation_id="",
        )
        assert isinstance(result, str)
