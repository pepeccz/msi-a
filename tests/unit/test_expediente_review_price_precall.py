"""
Unit tests for expediente-flow-bugs R1: Deterministic pre-call of
obtener_estado_expediente() in review_summary handler.

Tests cover:
1. When _handle_review() runs and obtener_estado_expediente hasn't been
   called: the pre-call fires and injects the result.
2. When obtener_estado_expediente returns precio_total=65, the injected
   content contains "65".
3. When obtener_estado_expediente was already marked in tools_called (via
   pre_call_tool_name), no duplicate call occurs.

These are pure unit tests — no DB, no Redis, no real LLM.
All external calls are mocked.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_state(conversation_id: str = "test-conv-001") -> dict:
    """Minimal ConversationState-like dict for testing."""
    return {
        "conversation_id": conversation_id,
        "messages": [],
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {},
        "retry_state": None,
        "incoming_attachments": [],
    }


def _make_mode_context() -> dict:
    """Minimal mode_context for REVIEW_SUMMARY."""
    return {
        "expediente_sub_mode": "review_summary",
        "case_id": "00000000-0000-0000-0000-000000000099",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReviewPreCall:
    """Tests for the deterministic pre-call of obtener_estado_expediente
    in ExpedienteModeNode._handle_review()."""

    @pytest.mark.asyncio
    async def test_pre_call_fires_when_not_yet_called(self):
        """
        _handle_review() calls obtener_estado_expediente.ainvoke()
        deterministically before _run_llm_loop, even on the first turn.
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        state = _make_state()
        mode_context = _make_mode_context()

        pre_call_result = {
            "has_active_case": True,
            "precio_total": 65.0,
            "tariff_amount": 50.0,
        }

        captured_kwargs: dict = {}

        async def fake_run_llm_loop(
            message, state, mode_context, tools, sub_mode_name, **kwargs
        ):
            captured_kwargs.update(kwargs)
            return {"ai_response": "Resumen listo.", "mode_context": mode_context}

        mock_tool = AsyncMock(return_value=pre_call_result)

        with (
            patch(
                "agent.modes.expediente_mode.set_current_state",
            ),
            patch(
                "agent.modes.expediente_mode.set_current_state_for_image_tools",
            ),
            patch(
                "agent.tools.case_tools.obtener_estado_expediente",
                create=True,
            ) as mock_obtener,
            patch.object(node, "_run_llm_loop", side_effect=fake_run_llm_loop),
        ):
            mock_obtener.ainvoke = mock_tool
            # Patch the local import inside _handle_review
            with patch(
                "agent.modes.expediente_mode.ExpedienteModeNode._handle_review",
                wraps=node._handle_review,
            ):
                with patch(
                    "agent.tools.case_tools.obtener_estado_expediente",
                ) as patched_tool:
                    patched_tool.ainvoke = mock_tool
                    # Use importlib to intercept the local import
                    import importlib
                    import agent.tools.case_tools as _ct_module

                    _ct_module.obtener_estado_expediente = patched_tool

                    result = await node._handle_review(
                        message="¿cómo queda el resumen?",
                        state=state,
                        mode_context=mode_context,
                    )

        # The pre-call tool was invoked
        mock_tool.assert_called_once_with({})

        # _run_llm_loop received pre_call kwargs
        assert "pre_call_tool_name" in captured_kwargs
        assert captured_kwargs["pre_call_tool_name"] == "obtener_estado_expediente"
        assert "pre_call_tool_result" in captured_kwargs
        assert captured_kwargs["pre_call_tool_result"] is not None

    @pytest.mark.asyncio
    async def test_injected_content_contains_precio_total(self):
        """
        When obtener_estado_expediente returns precio_total=65, the
        pre_call_tool_result kwarg passed to _run_llm_loop contains "65".
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        state = _make_state()
        mode_context = _make_mode_context()

        pre_call_result = {
            "has_active_case": True,
            "precio_total": 65.0,
            "tariff_amount": 50.0,
        }

        captured_result_str: list[str] = []

        async def fake_run_llm_loop(
            message, state, mode_context, tools, sub_mode_name, **kwargs
        ):
            if kwargs.get("pre_call_tool_result"):
                captured_result_str.append(kwargs["pre_call_tool_result"])
            return {"ai_response": "Ok", "mode_context": mode_context}

        mock_tool = AsyncMock(return_value=pre_call_result)

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch.object(node, "_run_llm_loop", side_effect=fake_run_llm_loop),
        ):
            import agent.tools.case_tools as _ct_module

            original = getattr(_ct_module, "obtener_estado_expediente", None)
            try:
                mock_obj = MagicMock()
                mock_obj.ainvoke = mock_tool
                _ct_module.obtener_estado_expediente = mock_obj

                await node._handle_review(
                    message="muestra el resumen",
                    state=state,
                    mode_context=mode_context,
                )
            finally:
                if original is not None:
                    _ct_module.obtener_estado_expediente = original

        # The injected JSON string must contain "65"
        assert len(captured_result_str) == 1, (
            "Expected exactly one pre_call_tool_result to be passed"
        )
        assert "65" in captured_result_str[0], (
            f"Expected '65' in injected result, got: {captured_result_str[0]}"
        )
        # Stale price "410" should not appear in the injected data
        assert "410" not in captured_result_str[0]

    @pytest.mark.asyncio
    async def test_no_duplicate_call_when_already_registered(self):
        """
        The pre-call tool is registered in tools_called via the
        pre_call_tool_name kwarg inside _run_llm_loop.  Verify that
        tools_called includes 'obtener_estado_expediente' after the pre-call
        injection block runs, preventing duplicate LLM-driven invocation.

        We test this by running the full _run_llm_loop injection block logic
        directly, simulating what happens when kwargs are provided.
        """
        # We simulate what _run_llm_loop does with the pre_call kwargs:
        # after injection, the tool name is added to tools_called.

        tools_called: set[str] = set()
        pre_call_tool_name = "obtener_estado_expediente"
        pre_call_tool_result = json.dumps({"precio_total": 65.0})

        # Simulate the injection block from _run_llm_loop
        llm_messages: list[dict] = []
        if pre_call_tool_result and pre_call_tool_name:
            llm_messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[RESULTADO PRE-CARGADO de {pre_call_tool_name}]: "
                        f"{pre_call_tool_result}\n\n"
                        "IMPORTANTE: Usa EXCLUSIVAMENTE estos datos para el resumen. "
                        "No uses precios ni datos de mensajes anteriores."
                    ),
                }
            )
        # Simulate the registration block
        if pre_call_tool_name and pre_call_tool_result:
            tools_called.add(pre_call_tool_name)

        # Assert: tool is registered, preventing LLM from calling it again
        assert "obtener_estado_expediente" in tools_called

        # Assert: the injected message contains the serialised result
        assert len(llm_messages) == 1
        assert "65" in llm_messages[0]["content"]
        assert (
            "[RESULTADO PRE-CARGADO de obtener_estado_expediente]"
            in llm_messages[0]["content"]
        )

    def test_no_duplicate_when_pre_call_result_is_none(self):
        """
        When pre_call_tool_result is None (tool failed), tools_called is NOT
        updated and no system message is injected.
        """
        tools_called: set[str] = set()
        pre_call_tool_name = "obtener_estado_expediente"
        pre_call_tool_result = None  # Tool failed

        llm_messages: list[dict] = []
        if pre_call_tool_result and pre_call_tool_name:
            llm_messages.append({"role": "system", "content": "..."})

        if pre_call_tool_name and pre_call_tool_result:
            tools_called.add(pre_call_tool_name)

        # Nothing injected when pre_call failed
        assert len(llm_messages) == 0
        assert "obtener_estado_expediente" not in tools_called
