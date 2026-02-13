"""
Phase 4 Tests: Constraint system hardening.

Tests:
1. Retry exhaustion safety net — safe fallback message (4A)
2. Unified injection role — system + IMPORTANT in all modes (4B)
3. variant_requires_tool reactivation (4C) — verified via SQL + Pub/Sub live test
4. Cross-phase regression tests — full pipeline from regex → LLM → retry → exhaustion
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# Safe fallback message used when constraint retries are exhausted
SAFE_FALLBACK = "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"


# ============================================================================
# 1. RETRY EXHAUSTION SAFETY NET TESTS (Phase 4A)
# ============================================================================


class TestRetryExhaustionPresupuesto:
    """Presupuesto mode: when constraint retries exhausted, use safe fallback."""

    @pytest.mark.asyncio
    async def test_exhausted_retries_produce_safe_response(self):
        """After MAX_VALIDATION_RETRIES, ai_response should be the safe fallback."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()

        # Build a state that will trigger constraint violation
        mock_state = {
            "messages": [{"role": "user", "content": "quiero homologar mi moto"}],
            "conversation_id": "test-conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        # Mock LLM to always return a response that triggers constraint violation
        mock_response = MagicMock()
        mock_response.content = "El presupuesto es de 450€ +IVA"  # Mentions price without tool
        mock_response.tool_calls = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        # Mock _validate_response_constraints to always return invalid
        async def always_invalid(response, tools_called, state, current_mode_context=None):
            return False, "Price mentioned without calcular_tarifa_con_elementos"

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=always_invalid):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert result["ai_response"] == SAFE_FALLBACK

    @pytest.mark.asyncio
    async def test_successful_retry_does_not_trigger_safety_net(self):
        """If retry succeeds (LLM fixes response), safety net should NOT activate."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()

        mock_state = {
            "messages": [{"role": "user", "content": "quiero homologar mi moto"}],
            "conversation_id": "test-conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        # First response fails, second succeeds
        call_count = 0
        mock_response_bad = MagicMock()
        mock_response_bad.content = "El presupuesto es de 450€"
        mock_response_bad.tool_calls = None

        mock_response_good = MagicMock()
        mock_response_good.content = "¿Qué tipo de moto tienes?"
        mock_response_good.tool_calls = None

        mock_llm = AsyncMock()

        async def dynamic_invoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_bad
            return mock_response_good

        mock_llm.ainvoke = dynamic_invoke

        validate_call_count = 0

        async def first_fail_then_pass(response, tools_called, state, current_mode_context=None):
            nonlocal validate_call_count
            validate_call_count += 1
            if validate_call_count == 1:
                return False, "Price without tool"
            return True, None

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=first_fail_then_pass):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        # Should get the good response, not the safety net
        assert result["ai_response"] == "¿Qué tipo de moto tienes?"
        assert result["ai_response"] != SAFE_FALLBACK


class TestRetryExhaustionConsulta:
    """Consulta mode: when constraint retries exhausted, use safe fallback."""

    @pytest.mark.asyncio
    async def test_exhausted_retries_produce_safe_response(self):
        """After MAX_VALIDATION_RETRIES, ai_response should be the safe fallback."""
        from agent.modes.consulta_mode import ConsultaModeNode

        node = ConsultaModeNode()

        mock_state = {
            "messages": [{"role": "user", "content": "qué documentos necesito"}],
            "conversation_id": "test-conv-123",
            "current_mode": "CONSULTA_MODE",
            "mode_context": {},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        mock_response = MagicMock()
        mock_response.content = "Necesitas certificado de resistencia y anclaje"
        mock_response.tool_calls = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        async def always_invalid(response, tools_called, state, current_mode_context=None):
            return False, "Docs mentioned without tool"

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=always_invalid):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert result["ai_response"] == SAFE_FALLBACK


class TestRetryExhaustionExpediente:
    """Expediente mode: when constraint retries exhausted, use safe fallback."""

    @pytest.mark.asyncio
    async def test_exhausted_retries_produce_safe_response(self):
        """After MAX_VALIDATION_RETRIES, ai_response should be the safe fallback."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()

        mock_state = {
            "messages": [{"role": "user", "content": "quiero abrir expediente"}],
            "conversation_id": "test-conv-123",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "categoria_slug": "motos-part",
                "expediente_sub_mode": "collect_personal",
                "case_id": "case-123",
            },
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        mock_response = MagicMock()
        mock_response.content = "El presupuesto es de 450€"
        mock_response.tool_calls = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        async def always_invalid(response, tools_called, state, current_mode_context=None):
            return False, "Price without tool"

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=always_invalid):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert result["ai_response"] == SAFE_FALLBACK


# ============================================================================
# 2. UNIFIED INJECTION ROLE TESTS (Phase 4B)
# ============================================================================


class TestUnifiedInjectionRole:
    """All modes should inject constraint errors as role=system with IMPORTANT."""

    @pytest.mark.asyncio
    async def test_presupuesto_injects_as_system(self):
        """Presupuesto mode should use role=system for constraint injection."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()
        injected_messages = []

        mock_state = {
            "messages": [{"role": "user", "content": "quiero homologar"}],
            "conversation_id": "test-conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        call_count = 0
        mock_response_bad = MagicMock()
        mock_response_bad.content = "450€ +IVA"
        mock_response_bad.tool_calls = None

        mock_response_good = MagicMock()
        mock_response_good.content = "¿Qué moto tienes?"
        mock_response_good.tool_calls = None

        mock_llm = AsyncMock()

        async def capture_invoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            # Capture injected messages (looking for system constraint messages)
            for msg in messages:
                if isinstance(msg, dict) and "CONSTRAINT VALIDATION ERROR" in msg.get("content", ""):
                    injected_messages.append(msg)
            if call_count == 1:
                return mock_response_bad
            return mock_response_good

        mock_llm.ainvoke = capture_invoke

        validate_count = 0

        async def first_fail(response, tools_called, state, current_mode_context=None):
            nonlocal validate_count
            validate_count += 1
            if validate_count == 1:
                return False, "Test error injection"
            return True, None

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=first_fail):
            await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert len(injected_messages) == 1
        assert injected_messages[0]["role"] == "system"
        assert "IMPORTANT" in injected_messages[0]["content"]
        assert "MUST call the required tools" in injected_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_consulta_injects_as_system(self):
        """Consulta mode should use role=system (was 'user' before Phase 4B)."""
        from agent.modes.consulta_mode import ConsultaModeNode

        node = ConsultaModeNode()
        injected_messages = []

        mock_state = {
            "messages": [{"role": "user", "content": "qué necesito"}],
            "conversation_id": "test-conv-123",
            "current_mode": "CONSULTA_MODE",
            "mode_context": {},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        call_count = 0
        mock_response_bad = MagicMock()
        mock_response_bad.content = "Certificado resistencia"
        mock_response_bad.tool_calls = None

        mock_response_good = MagicMock()
        mock_response_good.content = "Déjame consultar..."
        mock_response_good.tool_calls = None

        mock_llm = AsyncMock()

        async def capture_invoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            for msg in messages:
                if isinstance(msg, dict) and "CONSTRAINT VALIDATION ERROR" in msg.get("content", ""):
                    injected_messages.append(msg)
            if call_count == 1:
                return mock_response_bad
            return mock_response_good

        mock_llm.ainvoke = capture_invoke

        validate_count = 0

        async def first_fail(response, tools_called, state, current_mode_context=None):
            nonlocal validate_count
            validate_count += 1
            if validate_count == 1:
                return False, "Test error"
            return True, None

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=first_fail):
            await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert len(injected_messages) == 1
        assert injected_messages[0]["role"] == "system"
        assert "IMPORTANT" in injected_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_expediente_injects_as_system(self):
        """Expediente mode should use role=system (was 'user' before Phase 4B)."""
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        injected_messages = []

        mock_state = {
            "messages": [{"role": "user", "content": "mis datos"}],
            "conversation_id": "test-conv-123",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "categoria_slug": "motos-part",
                "expediente_sub_mode": "collect_personal",
                "case_id": "case-123",
            },
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        call_count = 0
        mock_response_bad = MagicMock()
        mock_response_bad.content = "450€"
        mock_response_bad.tool_calls = None

        mock_response_good = MagicMock()
        mock_response_good.content = "Necesito tu nombre completo"
        mock_response_good.tool_calls = None

        mock_llm = AsyncMock()

        async def capture_invoke(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            for msg in messages:
                if isinstance(msg, dict) and "CONSTRAINT VALIDATION ERROR" in msg.get("content", ""):
                    injected_messages.append(msg)
            if call_count == 1:
                return mock_response_bad
            return mock_response_good

        mock_llm.ainvoke = capture_invoke

        validate_count = 0

        async def first_fail(response, tools_called, state, current_mode_context=None):
            nonlocal validate_count
            validate_count += 1
            if validate_count == 1:
                return False, "Test error"
            return True, None

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=first_fail):
            await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert len(injected_messages) == 1
        assert injected_messages[0]["role"] == "system"
        assert "IMPORTANT" in injected_messages[0]["content"]


# ============================================================================
# 3. CROSS-PHASE REGRESSION: Constraint retry + exhaustion + safe fallback
# ============================================================================


class TestConstraintRetrySequence:
    """Verify the full retry → exhaustion → safe fallback sequence."""

    @pytest.mark.asyncio
    async def test_retry_count_matches_max(self):
        """Should retry exactly MAX_VALIDATION_RETRIES times before safety net."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()
        validate_calls = 0

        mock_state = {
            "messages": [{"role": "user", "content": "homologar moto"}],
            "conversation_id": "test-conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        mock_response = MagicMock()
        mock_response.content = "450€ sin herramienta"
        mock_response.tool_calls = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        async def count_validates(response, tools_called, state, current_mode_context=None):
            nonlocal validate_calls
            validate_calls += 1
            return False, "Always fails"

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=count_validates):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        # MAX_VALIDATION_RETRIES = 2, so exactly 2 validation calls
        assert validate_calls == 2
        assert result["ai_response"] == SAFE_FALLBACK

    @pytest.mark.asyncio
    async def test_safe_fallback_message_is_spanish(self):
        """Safety net message must be in Spanish (user-facing)."""
        assert "Disculpa" in SAFE_FALLBACK
        assert "reformularte" in SAFE_FALLBACK

    @pytest.mark.asyncio
    async def test_valid_first_attempt_no_retry(self):
        """If first validation passes, no retry should occur."""
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        node = PresupuestoModeNode()

        mock_state = {
            "messages": [{"role": "user", "content": "homologar"}],
            "conversation_id": "test-conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {"categoria_slug": "motos-part"},
            "mode_message_count": 1,
            "retry_state": {"retry_count": 0, "last_error": None},
            "mode_history": [],
        }

        mock_response = MagicMock()
        mock_response.content = "¿Qué tipo de moto tienes?"
        mock_response.tool_calls = None

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        async def always_valid(response, tools_called, state, current_mode_context=None):
            return True, None

        with patch.object(node, "_get_llm", return_value=mock_llm), \
             patch.object(node, "_validate_response_constraints", side_effect=always_valid):
            result = await node._process_message(
                mock_state["messages"][-1]["content"],
                mock_state,
            )

        assert result["ai_response"] == "¿Qué tipo de moto tienes?"
