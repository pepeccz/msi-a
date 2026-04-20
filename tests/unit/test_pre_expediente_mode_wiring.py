"""
T2.1 — ModeLoopConfig wiring test.

Spec coverage: get_tool_choice lambda MUST be passed to ModeLoopConfig.
Design reference: D2 — Lambda wired via get_tool_choice= kwarg.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestGetToolChoiceLambdaPassed:
    """
    Assert that PreExpedienteModeNode wires get_tool_choice into ModeLoopConfig.
    """

    async def test_get_tool_choice_lambda_passed(self):
        """
        T2.1 RED: ModeLoopConfig must be constructed with a callable get_tool_choice.

        Strategy: Patch ModeLoopConfig at the point of use in pre_expediente_mode
        and capture the kwargs it was called with.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        captured_kwargs: dict = {}

        # We'll capture the ModeLoopConfig constructor kwargs
        original_config_cls = None

        def _capture_config(*args, **kwargs):
            captured_kwargs.update(kwargs)
            # Return a real-enough mock so build_mode_tool_loop doesn't fail
            mock_cfg = MagicMock()
            mock_cfg.mode_name = kwargs.get("mode_name", "PRE_EXPEDIENTE_MODE")
            mock_cfg.get_tools = kwargs.get("get_tools")
            mock_cfg.get_system_prompt = kwargs.get("get_system_prompt")
            mock_cfg.post_tool_hook = kwargs.get("post_tool_hook")
            mock_cfg.max_iterations = kwargs.get("max_iterations", 10)
            mock_cfg.max_tokens = kwargs.get("max_tokens", 1500)
            mock_cfg.get_tool_choice = kwargs.get("get_tool_choice")
            return mock_cfg

        # Build a minimal state
        state = {
            "conversation_id": "test-wiring-001",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {"datos": {"price": 100}},
                "imagenes_enviadas_codigos": ["T01"],
                "last_cta_emitted": "cta_5",
            },
            "messages": [],
            "client_type": "particular",
            "is_first_interaction": False,
        }

        # Fake loop result so ainvoke doesn't need real services
        fake_loop_result = {
            "ai_response": "¿Abrimos expediente o tienes alguna duda?",
            "exit_reason": "response",
            "tools_called": [],
            "pending_state_updates": {},
        }

        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value=fake_loop_result)

        fake_loop_obj = MagicMock()
        fake_loop_obj.graph = fake_graph
        fake_loop_obj.recursion_limit = 25

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig", side_effect=_capture_config),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=fake_loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
            patch("agent.modes.pre_expediente_mode._deactivate_draft_quote", new_callable=AsyncMock, create=True),
        ):
            node = PreExpedienteModeNode()
            await node._process_with_tool_loop("dale", state)

        assert "get_tool_choice" in captured_kwargs, (
            "ModeLoopConfig was NOT called with get_tool_choice kwarg. "
            "Wire _should_force_tool_choice into ModeLoopConfig in pre_expediente_mode.py."
        )

        get_tc = captured_kwargs["get_tool_choice"]
        assert callable(get_tc), (
            f"get_tool_choice must be a callable, got {type(get_tc)}"
        )

    async def test_get_tool_choice_returns_required_when_all_conditions_met(self):
        """
        Triangulation: the passed lambda must return "required" when all 4 conditions hold.
        Tests that the lambda correctly delegates to _should_force_tool_choice.
        """
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        captured_kwargs: dict = {}

        def _capture_config(*args, **kwargs):
            captured_kwargs.update(kwargs)
            mock_cfg = MagicMock()
            mock_cfg.get_tool_choice = kwargs.get("get_tool_choice")
            return mock_cfg

        state = {
            "conversation_id": "test-wiring-002",
            "mode_context": {},
            "messages": [],
            "client_type": "particular",
            "is_first_interaction": False,
        }

        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value={
            "ai_response": "",
            "exit_reason": "response",
            "tools_called": [],
            "pending_state_updates": {},
        })
        fake_loop_obj = MagicMock()
        fake_loop_obj.graph = fake_graph
        fake_loop_obj.recursion_limit = 25

        with (
            patch("agent.modes.pre_expediente_mode.ModeLoopConfig", side_effect=_capture_config),
            patch("agent.modes.pre_expediente_mode.build_mode_tool_loop", return_value=fake_loop_obj),
            patch("agent.modes.pre_expediente_mode._load_active_draft_quote_into_context", new_callable=AsyncMock),
            patch("agent.modes.pre_expediente_mode.clear_image_tools_state"),
        ):
            node = PreExpedienteModeNode()
            await node._process_with_tool_loop("dale", state)

        get_tc = captured_kwargs.get("get_tool_choice")
        assert get_tc is not None

        # Test it returns "required" with the right conditions
        all_true_mc = {
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],
            "last_cta_emitted": "cta_5",
        }
        result = get_tc(all_true_mc)
        assert result == "required", (
            f"Lambda should return 'required' for all-true mc, got {result!r}"
        )

        # And None when last_cta_emitted is absent
        partial_mc = {
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 100}},
            "imagenes_enviadas_codigos": ["T01"],
        }
        result_none = get_tc(partial_mc)
        assert result_none is None, (
            f"Lambda should return None without last_cta_emitted, got {result_none!r}"
        )
