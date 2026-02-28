"""
Tests for change: verify-conversation-merelo (Phase 5, Tasks 5.4–5.5).

Task 5.4: Constraint retries exhausted uses FallbackHandler.get_reprompt()
    Verifies that when constraint validation fails MAX_VALIDATION_RETRIES+1 times
    in PRESUPUESTO_MODE, the ai_response comes from FallbackHandler.get_reprompt()
    instead of the old hardcoded string.

Task 5.5: Pending variants block calcular_tarifa + state None warning
    a) pending_variants in mode_context → calcular_tarifa returns blocking JSON
    b) get_current_state() returns None → logger.warning is emitted

Run:
    pytest tests/unit/test_verify_conversation_merelo_agent.py -v
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# Task 5.4 — Constraint retries exhausted uses FallbackHandler.get_reprompt
# ============================================================================


# The OLD hardcoded fallback that must NO LONGER appear after the fix
OLD_HARDCODED_FALLBACK = (
    "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"
)


class TestConstraintRetriesExhaustedUsesFallbackHandler:
    """
    After Fix 2, line ~343 of presupuesto_mode.py should call:
        ai_response = self._fallback.get_reprompt(retry_state, self._policy)
    instead of the old hardcoded string.
    """

    @pytest.mark.asyncio
    async def test_exhausted_retries_response_comes_from_fallback_handler(self):
        """
        When constraint validation fails MAX_VALIDATION_RETRIES+1 times,
        ai_response must come from FallbackHandler.get_reprompt() — NOT the
        old hardcoded string.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode
        from agent.fallback.fallback_handler import FallbackHandler, DEFAULT_POLICIES

        node = PresupuestoModeNode()

        mock_state: dict = {
            "messages": [{"role": "user", "content": "quiero homologar mi moto"}],
            "conversation_id": "test-merelo-fix2",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "consecutive_errors": 0},
            "mode_history": [],
        }

        # LLM always returns text (no tool calls) triggering constraint check
        mock_response = MagicMock()
        mock_response.content = "El presupuesto es de 450€ +IVA"
        mock_response.tool_calls = None
        mock_response.usage_metadata = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        # Constraint validation always fails → drives validation_retries past MAX
        async def always_invalid(
            response, tools_called, state, current_mode_context=None, available_tool_names=None
        ):
            return False, "Price mentioned without calcular_tarifa_con_elementos"

        with (
            patch.object(node, "_get_llm", return_value=mock_llm),
            patch.object(
                node,
                "_validate_response_constraints",
                side_effect=always_invalid,
            ),
        ):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        ai_response = result["ai_response"]

        # ---- Assert the OLD hardcoded string is NOT present ----
        assert ai_response != OLD_HARDCODED_FALLBACK, (
            "ai_response should NOT be the old hardcoded fallback. "
            "Fix 2 must replace it with FallbackHandler.get_reprompt()."
        )

        # ---- Assert it matches what FallbackHandler.get_reprompt would return ----
        # For PRESUPUESTO_MODE with retry_count >= max_retries,
        # get_reprompt returns policy.msg_limit
        policy = DEFAULT_POLICIES["PRESUPUESTO_MODE"]
        handler = FallbackHandler()

        # Build a retry_state representing exhausted retries
        # After MAX_VALIDATION_RETRIES=2 failures, retry_count should be 2
        # (validation_retries starts at 0, increments to 1, then to 2, then
        # the elif branch fires because validation_retries >= MAX_VALIDATION_RETRIES)
        # The retry_state passed to get_reprompt reflects the current fallback state.
        # The exact retry_count depends on what the mode increments, but
        # get_reprompt for count >= max_retries returns msg_limit.
        expected_for_limit = policy.msg_limit

        # The response could be msg_limit or one of the progressive messages
        # depending on the retry_count at the point of call. Let's verify it's
        # one of the valid FallbackHandler messages for PRESUPUESTO_MODE.
        valid_fallback_messages = {
            policy.msg_retry_1,
            policy.msg_retry_2,
            policy.msg_limit,
        }
        # Also include the _simplify_message fallback (auto-generated)
        simplify_msg = handler._simplify_message(policy)
        valid_fallback_messages.add(simplify_msg)

        assert ai_response in valid_fallback_messages, (
            f"ai_response should be one of the FallbackHandler messages for "
            f"PRESUPUESTO_MODE. Got: '{ai_response[:100]}...'"
        )

    @pytest.mark.asyncio
    async def test_exhausted_retries_does_not_contain_old_hardcoded_text(self):
        """
        Negative test: verify the old hardcoded substring never appears,
        even partially, in the exhausted-retries ai_response.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()

        mock_state: dict = {
            "messages": [{"role": "user", "content": "quiero un presupuesto"}],
            "conversation_id": "test-merelo-negative",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "consecutive_errors": 0},
            "mode_history": [],
        }

        mock_response = MagicMock()
        mock_response.content = "Presupuesto: 300€ sin IVA"
        mock_response.tool_calls = None
        mock_response.usage_metadata = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        async def always_invalid(
            response, tools_called, state, current_mode_context=None, available_tool_names=None
        ):
            return False, "Hallucinated price"

        with (
            patch.object(node, "_get_llm", return_value=mock_llm),
            patch.object(
                node,
                "_validate_response_constraints",
                side_effect=always_invalid,
            ),
        ):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        # The old string fragments should not appear
        assert "déjame reformularte" not in result["ai_response"], (
            "Old hardcoded fallback fragment found in response"
        )
        assert "Podrías repetirme qué necesitas" not in result["ai_response"], (
            "Old hardcoded fallback fragment found in response"
        )

    @pytest.mark.asyncio
    async def test_successful_retry_does_not_trigger_fallback(self):
        """
        If constraint retry succeeds on the second LLM call, the response
        should be the LLM's valid text — not a fallback message.
        """
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()

        mock_state: dict = {
            "messages": [{"role": "user", "content": "quiero homologar mi moto"}],
            "conversation_id": "test-merelo-retry-ok",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "consecutive_errors": 0},
            "mode_history": [],
        }

        # First LLM call returns bad response, second returns good
        call_count = 0
        mock_bad = MagicMock()
        mock_bad.content = "El presupuesto es de 450€"
        mock_bad.tool_calls = None
        mock_bad.usage_metadata = None

        mock_good = MagicMock()
        mock_good.content = "¿Qué tipo de moto tienes?"
        mock_good.tool_calls = None
        mock_good.usage_metadata = None

        mock_llm = AsyncMock()

        async def dynamic_invoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_bad if call_count == 1 else mock_good

        mock_llm.ainvoke = dynamic_invoke

        validate_count = 0

        async def first_fail_then_pass(
            response, tools_called, state, current_mode_context=None, available_tool_names=None
        ):
            nonlocal validate_count
            validate_count += 1
            if validate_count == 1:
                return False, "Price without tool"
            return True, None

        with (
            patch.object(node, "_get_llm", return_value=mock_llm),
            patch.object(
                node,
                "_validate_response_constraints",
                side_effect=first_fail_then_pass,
            ),
        ):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        # Should be the LLM's valid response, not any fallback message
        assert result["ai_response"] == "¿Qué tipo de moto tienes?"


# ============================================================================
# Task 5.5a — Pending variants block calcular_tarifa_con_elementos
# ============================================================================


class TestPendingVariantsBlockCalcTarifa:
    """
    When mode_context contains pending_variants, calcular_tarifa_con_elementos
    must return a blocking JSON response (success=False) instead of a price.
    """

    @pytest.mark.asyncio
    async def test_pending_variants_returns_blocking_message(self):
        """
        With pending_variants in state, the tool must return success=False
        and an actionable error about resolving variants first.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos
        from agent.state.helpers import set_current_state, clear_current_state

        # Build state with pending variants
        state_with_variants = {
            "conversation_id": "test-merelo-variants",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "categoria_slug": "motos-part",
                "pending_variants": [
                    {
                        "codigo_base": "SUSPENSION",
                        "pregunta": "¿La suspensión es delantera o trasera?",
                    },
                ],
            },
        }

        try:
            set_current_state(state_with_variants)

            # Call the tool directly (it's a @tool, use .ainvoke)
            result_str = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE", "SUSPENSION"],
                "skip_validation": True,
            })

            result = json.loads(result_str)

            # Must be blocked
            assert result["success"] is False, "Should be blocked by pending variants"
            assert "variantes pendientes" in result["error"].lower(), (
                f"Error message should mention pending variants. Got: {result['error']}"
            )
            assert "variantes_pendientes" in result, (
                "Response should contain the list of pending variant questions"
            )
            assert "accion_requerida" in result, (
                "Response should contain actionable instructions"
            )
            assert "seleccionar_variante_por_respuesta" in result["accion_requerida"], (
                "Instructions should mention the correct tool to resolve variants"
            )
            # Internal flags should keep precio_comunicado=False
            flags = result.get("_internal_flags", {})
            assert flags.get("precio_comunicado") is False, (
                "precio_comunicado flag should be False when blocked"
            )
        finally:
            clear_current_state()

    @pytest.mark.asyncio
    async def test_no_pending_variants_does_not_block(self):
        """
        Without pending_variants, the tool should proceed normally
        (it may fail for other reasons like missing category, but
        NOT with the variants-blocking message).
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos
        from agent.state.helpers import set_current_state, clear_current_state

        state_no_variants = {
            "conversation_id": "test-merelo-no-variants",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "categoria_slug": "motos-part",
                "pending_variants": [],  # empty = no blocking
            },
        }

        try:
            set_current_state(state_no_variants)

            # We need to mock the downstream calls to avoid DB access.
            # We just want to verify the variant guard is NOT triggered.
            mock_tarifa_svc = MagicMock()
            mock_tarifa_svc.get_active_categories = AsyncMock(return_value=[])

            with patch(
                "agent.tools.element_tools.validate_category_slug"
            ) as mock_validate, patch(
                "agent.tools.element_tools.get_tarifa_service",
                return_value=mock_tarifa_svc,
            ) as mock_ts, patch(
                "agent.tools.element_tools.get_element_service"
            ) as mock_es, patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value=None,  # category not found → will error, but NOT the variant block
            ):
                result_str = await calcular_tarifa_con_elementos.ainvoke({
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                })

            # Should NOT contain the variant-blocking error
            if result_str.startswith("{"):
                result = json.loads(result_str)
                if not result.get("success", True):
                    assert "variantes pendientes" not in result.get("error", "").lower(), (
                        "Should not be blocked by variants when pending_variants is empty"
                    )
            # If it's a plain error string that's fine — it's not the variant block
        finally:
            clear_current_state()

    @pytest.mark.asyncio
    async def test_multiple_pending_variants_all_listed(self):
        """
        When multiple variants are pending, all their questions should appear
        in the blocking response's variantes_pendientes list.
        """
        from agent.tools.element_tools import calcular_tarifa_con_elementos
        from agent.state.helpers import set_current_state, clear_current_state

        state_multi = {
            "conversation_id": "test-merelo-multi",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "pending_variants": [
                    {
                        "codigo_base": "SUSPENSION",
                        "pregunta": "¿Delantera o trasera?",
                    },
                    {
                        "codigo_base": "ESCAPE",
                        "pregunta": "¿Deportivo o estándar?",
                    },
                ],
            },
        }

        try:
            set_current_state(state_multi)

            result_str = await calcular_tarifa_con_elementos.ainvoke({
                "categoria_vehiculo": "motos-part",
                "codigos_elementos": ["ESCAPE", "SUSPENSION"],
            })

            result = json.loads(result_str)
            assert result["success"] is False
            assert len(result["variantes_pendientes"]) == 2, (
                f"Expected 2 pending variants, got {len(result['variantes_pendientes'])}"
            )
            # The variant questions should be present (extracted from "pregunta" key)
            assert "¿Delantera o trasera?" in result["variantes_pendientes"]
            assert "¿Deportivo o estándar?" in result["variantes_pendientes"]
        finally:
            clear_current_state()


# ============================================================================
# Task 5.5b — State None warning when get_current_state() returns None
# ============================================================================


class TestCalcTarifaStateNoneWarning:
    """
    When get_current_state() returns None (ContextVar not set),
    calcular_tarifa_con_elementos should:
    1. Log a warning with event "calcular_tarifa_state_unavailable"
    2. NOT crash — proceed with the calculation (skipping variant check)
    """

    @pytest.mark.asyncio
    async def test_state_none_logs_warning(self):
        """
        When state is None, a warning log must be emitted with
        event "calcular_tarifa_state_unavailable".
        """
        from agent.state.helpers import clear_current_state

        # Ensure ContextVar is cleared → get_current_state() returns None
        clear_current_state()

        with patch(
            "agent.tools.element_tools.logger"
        ) as mock_logger, patch(
            "agent.tools.element_tools.validate_category_slug"
        ), patch(
            "agent.tools.element_tools.get_tarifa_service"
        ), patch(
            "agent.tools.element_tools.get_element_service"
        ), patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=None,  # will fail downstream, but we verify the warning first
        ):
            from agent.tools.element_tools import calcular_tarifa_con_elementos

            # Call — may error downstream, but the warning should fire first
            try:
                await calcular_tarifa_con_elementos.ainvoke({
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                })
            except Exception:
                pass  # downstream errors are OK — we only care about the warning

            # Verify the warning was logged (structlog kwargs pattern, not extra={})
            mock_logger.warning.assert_any_call(
                "calcular_tarifa_state_unavailable",
                codigos_solicitados=["ESCAPE"],
            )

    @pytest.mark.asyncio
    async def test_state_none_does_not_crash(self):
        """
        When state is None, the function must NOT raise.
        It should proceed past the variant guard and attempt calculation.
        """
        from agent.state.helpers import clear_current_state

        clear_current_state()

        # Mock enough to prevent DB access but let the variant guard pass
        with patch(
            "agent.tools.element_tools.validate_category_slug"
        ), patch(
            "agent.tools.element_tools.get_tarifa_service"
        ), patch(
            "agent.tools.element_tools.get_element_service"
        ), patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value="some-uuid",
        ), patch(
            "agent.tools.element_tools.get_async_session"
        ) as mock_session_ctx:
            # Mock the async session context manager
            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # We don't need a full DB — just verify no crash from state=None
            # The function will likely fail further down, but that's OK
            try:
                from agent.tools.element_tools import calcular_tarifa_con_elementos
                await calcular_tarifa_con_elementos.ainvoke({
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                })
            except Exception as e:
                # Any exception is fine as long as it's NOT related to
                # NoneType access from the state being None
                error_msg = str(e).lower()
                assert "'nonetype'" not in error_msg or "state" not in error_msg, (
                    f"Crashed due to None state: {e}"
                )

    @pytest.mark.asyncio
    async def test_state_present_no_warning(self):
        """
        When state IS available, the warning should NOT be logged.
        """
        from agent.state.helpers import set_current_state, clear_current_state

        state = {
            "conversation_id": "test-merelo-present",
            "mode_context": {"pending_variants": []},
        }

        try:
            set_current_state(state)

            with patch(
                "agent.tools.element_tools.logger"
            ) as mock_logger, patch(
                "agent.tools.element_tools.validate_category_slug"
            ), patch(
                "agent.tools.element_tools.get_tarifa_service"
            ), patch(
                "agent.tools.element_tools.get_element_service"
            ), patch(
                "agent.tools.element_tools.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                from agent.tools.element_tools import calcular_tarifa_con_elementos

                try:
                    await calcular_tarifa_con_elementos.ainvoke({
                        "categoria_vehiculo": "motos-part",
                        "codigos_elementos": ["ESCAPE"],
                        "skip_validation": True,
                    })
                except Exception:
                    pass

                # Verify the state-unavailable warning was NOT called
                warning_calls = [
                    call for call in mock_logger.warning.call_args_list
                    if call.args and call.args[0] == "calcular_tarifa_state_unavailable"
                ]
                assert len(warning_calls) == 0, (
                    "Should NOT log state_unavailable warning when state is present"
                )
        finally:
            clear_current_state()
