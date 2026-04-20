"""
T2.1 — get_tool_choice lambda is passed to ModeLoopConfig in PRE_EXPEDIENTE_MODE.

Spec: POST_PRICE LLM Invocation Contract
  WHEN _process_with_tool_loop builds the ModeLoopConfig
  THEN get_tool_choice must be a callable (not None)
  AND the callable must return "required" when all POST_PRICE + CTA 5 conditions hold.

Design D2: get_tool_choice=lambda mc: _should_force_tool_choice(mc)
  wired into ModeLoopConfig(...) constructor in pre_expediente_mode.py:~518.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_price_mode_context() -> dict:
    """Mode context where all POST_PRICE + CTA 5 conditions are satisfied."""
    return {
        "precio_comunicado": True,
        "tarifa_calculada": {"datos": {"price": 450.0}},
        "imagenes_enviadas_codigos": ["T01"],
        "last_cta_emitted": "cta_5",
        "element_codes": ["ESCAPE"],
        "categoria_slug": "motos-part",
    }


def _discovery_mode_context() -> dict:
    """Mode context in DISCOVERY phase — tool_choice must be None."""
    return {
        "precio_comunicado": False,
        "tarifa_calculada": None,
        "imagenes_enviadas_codigos": [],
        "last_cta_emitted": None,
    }


def _minimal_state(mode_context: dict) -> dict:
    """Minimal ConversationState for _process_with_tool_loop calls."""
    return {
        "conversation_id": "test-conv-wiring-01",
        "user_phone": "+34600000001",
        "messages": [],
        "mode_context": mode_context,
        "current_mode": "PRE_EXPEDIENTE_MODE",
        "user_message": "dale",
        "client_type": "particular",
        "is_first_interaction": False,
    }


def _make_loop_result(ai_response: str = "Test response") -> MagicMock:
    """Build a fake loop_result_obj that avoids actual graph compilation."""
    loop_result = MagicMock()
    loop_result.graph = MagicMock()
    loop_result.graph.ainvoke = AsyncMock(return_value={
        "ai_response": ai_response,
        "exit_reason": "response",
        "tools_called": [],
        "pending_state_updates": {},
    })
    loop_result.recursion_limit = 25
    return loop_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetToolChoiceLambdaWired:
    """T2.1 + T2.2 — ModeLoopConfig receives a callable get_tool_choice."""

    @pytest.mark.asyncio
    async def test_get_tool_choice_lambda_passed_to_mode_loop_config(self) -> None:
        """
        T2.1 — GREEN assertion:
        build_mode_tool_loop must receive a ModeLoopConfig with
        get_tool_choice set to a callable.
        """
        captured_configs: list[Any] = []

        def capturing_build(config: Any) -> Any:
            captured_configs.append(config)
            return _make_loop_result()

        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        node = PreExpedienteModeNode()
        state = _minimal_state(_post_price_mode_context())

        with patch(
            "agent.modes.pre_expediente_mode._load_active_draft_quote_into_context",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            side_effect=capturing_build,
        ), patch(
            "agent.modes.pre_expediente_mode.clear_image_tools_state",
        ):
            try:
                await node._process_with_tool_loop("dale", state)
            except Exception:
                pass  # Only care about capturing config

        assert len(captured_configs) == 1, (
            f"Expected build_mode_tool_loop called once, got {len(captured_configs)} times"
        )

        config = captured_configs[0]
        assert hasattr(config, "get_tool_choice"), (
            "ModeLoopConfig missing 'get_tool_choice' attribute"
        )
        assert callable(config.get_tool_choice), (
            f"ModeLoopConfig.get_tool_choice must be callable, got {type(config.get_tool_choice)!r}"
        )

    @pytest.mark.asyncio
    async def test_get_tool_choice_returns_required_for_post_price_cta5(self) -> None:
        """
        T2.2 — Triangulation: the lambda in ModeLoopConfig returns 'required'
        when called with a POST_PRICE + CTA 5 mode context.
        """
        captured_configs: list[Any] = []

        def capturing_build(config: Any) -> Any:
            captured_configs.append(config)
            return _make_loop_result()

        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        node = PreExpedienteModeNode()
        state = _minimal_state(_post_price_mode_context())

        with patch(
            "agent.modes.pre_expediente_mode._load_active_draft_quote_into_context",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "agent.modes.pre_expediente_mode.build_mode_tool_loop",
            side_effect=capturing_build,
        ), patch(
            "agent.modes.pre_expediente_mode.clear_image_tools_state",
        ):
            try:
                await node._process_with_tool_loop("abrilo", state)
            except Exception:
                pass

        assert len(captured_configs) == 1

        config = captured_configs[0]
        # Lambda must return "required" for POST_PRICE + CTA 5 context
        result = config.get_tool_choice(_post_price_mode_context())
        assert result == "required", (
            f"get_tool_choice lambda must return 'required' for POST_PRICE+CTA5 context, "
            f"got {result!r}"
        )

        # Triangulation: returns None for DISCOVERY context
        result_discovery = config.get_tool_choice(_discovery_mode_context())
        assert result_discovery is None, (
            f"get_tool_choice lambda must return None for DISCOVERY context, "
            f"got {result_discovery!r}"
        )
