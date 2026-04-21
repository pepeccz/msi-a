"""
Regression smoke test for PRE_EXPEDIENTE_MODE error handling (Ola 6, Task 6.3).

Verifies that the extraction of ``is_transient_error`` and ``perform_fallback_escalation``
into shared modules (Ola 0) did NOT break the PRE_EXPEDIENTE_MODE error handling.

Specifically:
- ``BaseModeNode._perform_immediate_escalation`` must still delegate to
  ``perform_fallback_escalation`` and return a dict with the expected keys.
- The shared ``is_transient_error`` re-export in ``base_mode.py`` works correctly.

Design: these are unit tests on the shared helpers — they confirm that the
delegation wiring added in Ola 0 is intact and the original callers still work.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.state.conversation_state import RetryStateData, create_empty_retry_state


# ---------------------------------------------------------------------------
# Task 6.3 — Smoke: PRE_EXPEDIENTE error path delegates unchanged
# ---------------------------------------------------------------------------

class TestPreExpedienteErrorPathUnchanged:
    """
    S6.3: ensure the Ola 0 extraction did NOT break PRE_EXPEDIENTE_MODE's
    immediate-escalation path.

    ``_perform_immediate_escalation`` delegates to ``perform_fallback_escalation``
    and merges result.  We verify:
    1. The shared helper is called with correct args.
    2. The result dict includes ``current_mode="ESCALATION"``.
    3. The ``is_transient_error`` re-export in base_mode still classifies correctly.
    """

    @pytest.mark.asyncio
    async def test_perform_immediate_escalation_delegates_to_shared_helper(self):
        """
        _perform_immediate_escalation must call perform_fallback_escalation and
        merge the escalation result into the fallback_result dict.
        """
        # We need a concrete subclass of BaseModeNode to call its method.
        # Import BaseModeNode — it's in a module that the conftest stubs do NOT block.
        from agent.modes.base_mode import BaseModeNode

        # Minimal concrete subclass — we only need the method under test
        class _StubMode(BaseModeNode):
            async def _process_message(self, state):
                return {}

            def get_tools(self, state):
                return []

        stub_mode = _StubMode("PRE_EXPEDIENTE_MODE")

        escalation_result = {
            "ai_response": "Te voy a conectar con un especialista.",
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "retry_state": create_empty_retry_state(),
        }

        mock_perform = AsyncMock(return_value=escalation_result)

        # Minimal state dict (ConversationState-shaped)
        state = {
            "conversation_id": "conv-regression-001",
            "user_id": "user-001",
            "user_phone": "+34600000001",
            "retry_state": RetryStateData(retry_count=4, consecutive_errors=4),
            "current_mode": "PRE_EXPEDIENTE_MODE",
        }

        fallback_result = {
            "action": "ESCALATE_TO_HUMAN",
            "escalation_reason": "pre_expediente_fallback",
        }

        with patch(
            "agent.services.fallback_escalation.perform_escalation",
            new=mock_perform,
        ):
            result = await stub_mode._perform_immediate_escalation(fallback_result, state)  # type: ignore[arg-type]

        # 1. The shared perform_escalation was called
        mock_perform.assert_awaited_once()

        # 2. call args include conversation_id
        call_kwargs = mock_perform.call_args.kwargs
        assert call_kwargs["conversation_id"] == "conv-regression-001"

        # 3. result merged into fallback_result
        assert result.get("current_mode") == "ESCALATION", (
            f"current_mode must be ESCALATION, got {result.get('current_mode')!r}"
        )
        assert result.get("escalation_triggered") is True

    def test_is_transient_error_reexport_classifies_httpx_timeout(self):
        """
        Ola 0 re-exported is_transient_error via base_mode.  Verify it still works
        for the PRE_EXPEDIENTE callers (BaseModeNode internal usage).
        """
        import httpx
        from agent.modes.base_mode import _is_transient_error  # re-exported name

        assert _is_transient_error(httpx.TimeoutException("timeout")) is True
        assert _is_transient_error(httpx.ConnectError("connect")) is True

    def test_is_transient_error_reexport_classifies_value_error_as_business(self):
        """
        ValueError (business/validation error) must return False from is_transient_error.
        Triangulation: confirms non-transient classification is also correct.
        """
        from agent.modes.base_mode import _is_transient_error  # re-exported name

        assert _is_transient_error(ValueError("bad user input")) is False
        assert _is_transient_error(RuntimeError("unexpected state")) is False

    @pytest.mark.asyncio
    async def test_perform_fallback_escalation_returns_canonical_keys(self):
        """
        Smoke: shared ``perform_fallback_escalation`` returns all canonical keys
        even when ``perform_escalation`` succeeds (Ola 0 regression check).
        """
        from agent.services.fallback_escalation import perform_fallback_escalation

        mock_perform = AsyncMock(return_value={"message": "Especialista en camino."})

        with patch(
            "agent.services.fallback_escalation.perform_escalation",
            new=mock_perform,
        ):
            result = await perform_fallback_escalation(
                conversation_id="conv-smoke",
                user_id="user-001",
                user_phone="+34600000001",
                reason="pre_expediente_fallback",
            )

        # All canonical keys must be present
        assert "ai_response" in result, "ai_response must be in canonical result"
        assert "current_mode" in result, "current_mode must be in canonical result"
        assert "escalation_triggered" in result, "escalation_triggered must be in canonical result"
        assert "retry_state" in result, "retry_state must be in canonical result"

        # current_mode must always be ESCALATION
        assert result["current_mode"] == "ESCALATION"

        # ai_response must use the message from perform_escalation when provided
        assert result["ai_response"] == "Especialista en camino.", (
            "ai_response must use the message from perform_escalation result"
        )


# ---------------------------------------------------------------------------
# F3 — Deterministic safety-net render
# Spec: sdd/fix-pricing-gate-self-heal-loop/spec — "Deterministic Safety-Net
# Render"
# ---------------------------------------------------------------------------

_TARIFA_FOR_SAFETY_NET = {
    "datos": {
        "tier_name": "Moto - 2 elementos",
        "price": 410.0,
        "elements": ["Subchasis", "Asideros"],
        "warnings": [],
    }
}


class TestSafetyNetTariffRender:
    """When `_process_message` returns empty `ai_response` AND `mode_context`
    contains `tarifa_calculada`, the safety net MUST render a deterministic
    tariff summary instead of the generic error template.
    """

    @pytest.mark.asyncio
    async def test_empty_response_with_tarifa_renders_deterministic_summary(self):
        from agent.modes.base_mode import BaseModeNode

        class _StubMode(BaseModeNode):
            async def _process_message(self, message, state):  # type: ignore[override]
                return {
                    "ai_response": "",
                    "mode_context": {"tarifa_calculada": _TARIFA_FOR_SAFETY_NET},
                }

            def get_tools(self, state):
                return []

        stub = _StubMode("PRE_EXPEDIENTE_MODE")
        state = {
            "conversation_id": "conv-f3-render",
            "retry_state": create_empty_retry_state(),
            "current_mode": "PRE_EXPEDIENTE_MODE",
            "user_phone": "+34600000099",
        }
        state["user_message"] = "irrelevant message"
        result = await stub.process(state)  # type: ignore[arg-type]
        out = result["ai_response"]
        assert "410" in out, "rendered output MUST contain the tariff price literal"
        assert "€" in out
        assert "IVA" in out
        assert "Disculpa, he tenido un problema" not in out, (
            "generic error template MUST NOT be used when tariff exists"
        )

    @pytest.mark.asyncio
    async def test_empty_response_without_tarifa_uses_generic_template(self):
        from agent.modes.base_mode import BaseModeNode

        class _StubMode(BaseModeNode):
            async def _process_message(self, message, state):  # type: ignore[override]
                return {"ai_response": "", "mode_context": {}}

            def get_tools(self, state):
                return []

        stub = _StubMode("PRE_EXPEDIENTE_MODE")
        state = {
            "conversation_id": "conv-f3-no-tarifa",
            "retry_state": create_empty_retry_state(),
            "current_mode": "PRE_EXPEDIENTE_MODE",
            "user_phone": "+34600000098",
        }
        state["user_message"] = "irrelevant message"
        result = await stub.process(state)  # type: ignore[arg-type]
        assert "Disculpa, he tenido un problema" in result["ai_response"]

    @pytest.mark.asyncio
    async def test_non_empty_response_passes_through_unchanged(self):
        from agent.modes.base_mode import BaseModeNode

        class _StubMode(BaseModeNode):
            async def _process_message(self, message, state):  # type: ignore[override]
                return {
                    "ai_response": "Mensaje del LLM intacto.",
                    "mode_context": {"tarifa_calculada": _TARIFA_FOR_SAFETY_NET},
                }

            def get_tools(self, state):
                return []

        stub = _StubMode("PRE_EXPEDIENTE_MODE")
        state = {
            "conversation_id": "conv-f3-passthrough",
            "retry_state": create_empty_retry_state(),
            "current_mode": "PRE_EXPEDIENTE_MODE",
            "user_phone": "+34600000097",
        }
        state["user_message"] = "irrelevant message"
        result = await stub.process(state)  # type: ignore[arg-type]
        assert result["ai_response"] == "Mensaje del LLM intacto."
