"""
Constraint System Refactor — Phase 2 Tests.

Tests for hybrid validation: regex pre-filter + LLM Tier 1 confirmation.

Components tested:
- validate_with_llm(): LLM Tier 1 confirmation of regex matches
- validate_response_hybrid(): Full hybrid pipeline (regex + LLM)
- _validate_response_constraints() integration with hybrid path

These tests are PURE UNIT TESTS — no DB, no Redis, no real LLM, no network.
All external dependencies are mocked.
"""

import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from agent.services.constraint_service import (
    _should_skip_constraint,
    validate_response,
    validate_response_hybrid,
    validate_with_llm,
)


# ============================================================================
# Helpers: Mock LLMResponse
# ============================================================================

@dataclass
class MockLLMResponse:
    """Minimal mock of shared.llm_router.LLMResponse."""
    content: str
    success: bool = True
    error: str | None = None
    latency_ms: int = 150
    model: str = "qwen2.5:3b"


def _make_settings(**overrides):
    """Create a mock Settings object with defaults for constraint validation."""
    settings = MagicMock()
    settings.USE_LLM_CONSTRAINT_VALIDATION = overrides.get("USE_LLM_CONSTRAINT_VALIDATION", True)
    settings.USE_HYBRID_LLM = overrides.get("USE_HYBRID_LLM", True)
    settings.CONSTRAINT_VALIDATION_MODEL = overrides.get("CONSTRAINT_VALIDATION_MODEL", "qwen2.5:3b")
    return settings


# Standard test constraints (same patterns as production DB seed)
PRICE_CONSTRAINT = {
    "constraint_type": "price_requires_tool",
    "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
    "required_tool": "calcular_tarifa_con_elementos",
    "error_injection": "Debes calcular el precio con la herramienta.",
    "priority": 100,
}

IMAGES_CONSTRAINT = {
    "constraint_type": "images_narration_blocked",
    "detection_pattern": r"\[.*[Ll]lamando.*herramienta|imagenes.*se.*enviaran",
    "required_tool": "enviar_imagenes_ejemplo",
    "error_injection": "Las imágenes deben enviarse con la herramienta.",
    "priority": 95,
}

DOCS_CONSTRAINT = {
    "constraint_type": "docs_from_tool_only",
    "detection_pattern": r"certificado.*(resistencia|anclaje|instalacion)",
    "required_tool": "calcular_tarifa_con_elementos|obtener_documentacion_elemento",
    "error_injection": "La documentación debe obtenerse con herramientas.",
    "priority": 80,
}


# ============================================================================
# Phase 2A: validate_with_llm() unit tests
# ============================================================================

class TestValidateWithLlm:
    """Test the LLM confirmation function in isolation."""

    @pytest.mark.asyncio
    async def test_llm_says_valid_returns_true(self):
        """LLM confirms response is valid (false positive) → returns True."""
        mock_response = MockLLMResponse(content='{"valid": true}')
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "El presupuesto es de 410€ +IVA.",
                {"calcular_tarifa_con_elementos"},
                "price_requires_tool",
            )
            assert result is True  # False positive → discard regex match

    @pytest.mark.asyncio
    async def test_llm_says_invalid_returns_false(self):
        """LLM confirms violation is real → returns False."""
        mock_response = MockLLMResponse(
            content='{"valid": false, "reason": "Price mentioned without tool"}'
        )
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "Te va a costar 500€ +IVA.",
                set(),
                "price_requires_tool",
            )
            assert result is False  # Real violation

    @pytest.mark.asyncio
    async def test_llm_returns_markdown_wrapped_json(self):
        """LLM wraps JSON in ```json``` markdown → should still parse."""
        mock_response = MockLLMResponse(
            content='```json\n{"valid": true}\n```'
        )
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "El precio es 410€.",
                {"calcular_tarifa_con_elementos"},
                "price_requires_tool",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_llm_returns_malformed_json_returns_none(self):
        """LLM returns garbage → returns None (fall back to regex)."""
        mock_response = MockLLMResponse(content="I think it's valid")
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "500€",
                set(),
                "price_requires_tool",
            )
            assert result is None  # Fallback to regex

    @pytest.mark.asyncio
    async def test_llm_invoke_fails_returns_none(self):
        """LLM router raises exception → returns None (fall back to regex)."""
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(side_effect=Exception("Ollama connection refused"))

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "500€",
                set(),
                "price_requires_tool",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_response_not_success_returns_none(self):
        """LLM responds with success=False → returns None."""
        mock_response = MockLLMResponse(content="", success=False, error="Model not loaded")
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            result = await validate_with_llm(
                "500€",
                set(),
                "price_requires_tool",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_feature_flag_disabled_returns_none(self):
        """USE_LLM_CONSTRAINT_VALIDATION=False → returns None immediately."""
        with patch(
            "shared.config.get_settings",
            return_value=_make_settings(USE_LLM_CONSTRAINT_VALIDATION=False),
        ):
            result = await validate_with_llm(
                "500€",
                set(),
                "price_requires_tool",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_hybrid_llm_disabled_returns_none(self):
        """USE_HYBRID_LLM=False → returns None immediately."""
        with patch(
            "shared.config.get_settings",
            return_value=_make_settings(USE_HYBRID_LLM=False),
        ):
            result = await validate_with_llm(
                "500€",
                set(),
                "price_requires_tool",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_params(self):
        """Verify LLM is called with TaskType.CONSTRAINT_VALIDATION and disable_fallback."""
        mock_response = MockLLMResponse(content='{"valid": true}')
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            from shared.llm_router import TaskType
            await validate_with_llm(
                "El presupuesto es de 410€.",
                {"calcular_tarifa_con_elementos"},
                "price_requires_tool",
            )

            # Verify invoke was called correctly
            mock_router.invoke.assert_called_once()
            call_kwargs = mock_router.invoke.call_args
            assert call_kwargs.kwargs["task_type"] == TaskType.CONSTRAINT_VALIDATION
            assert call_kwargs.kwargs["temperature"] == 0.0
            assert call_kwargs.kwargs["max_tokens"] == 100
            assert call_kwargs.kwargs["disable_fallback"] is True

    @pytest.mark.asyncio
    async def test_response_text_truncated_to_300_chars(self):
        """Response text should be truncated to 300 chars in the prompt."""
        long_response = "A" * 500  # 500 chars
        mock_response = MockLLMResponse(content='{"valid": true}')
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            await validate_with_llm(long_response, set(), "price_requires_tool")

            # Check that the prompt contains only first 300 chars
            call_kwargs = mock_router.invoke.call_args
            prompt_content = call_kwargs.kwargs["messages"][0]["content"]
            assert "A" * 300 in prompt_content
            assert "A" * 301 not in prompt_content

    @pytest.mark.asyncio
    async def test_tools_called_formatted_in_prompt(self):
        """Tools called should appear comma-separated in the prompt."""
        mock_response = MockLLMResponse(content='{"valid": true}')
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            await validate_with_llm(
                "410€",
                {"calcular_tarifa_con_elementos", "enviar_imagenes_ejemplo"},
                "price_requires_tool",
            )

            call_kwargs = mock_router.invoke.call_args
            prompt = call_kwargs.kwargs["messages"][0]["content"]
            # Both tools should appear (order may vary due to set)
            assert "calcular_tarifa_con_elementos" in prompt
            assert "enviar_imagenes_ejemplo" in prompt

    @pytest.mark.asyncio
    async def test_empty_tools_shows_none_in_prompt(self):
        """Empty tools set should show 'none' in prompt."""
        mock_response = MockLLMResponse(content='{"valid": true}')
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch("shared.config.get_settings", return_value=_make_settings()), \
             patch("shared.llm_router.get_llm_router", return_value=mock_router):
            await validate_with_llm("410€", set(), "price_requires_tool")

            call_kwargs = mock_router.invoke.call_args
            prompt = call_kwargs.kwargs["messages"][0]["content"]
            assert "TOOLS CALLED THIS TURN: none" in prompt


# ============================================================================
# Phase 2B: validate_response_hybrid() unit tests
# ============================================================================

class TestValidateResponseHybrid:
    """Test the full hybrid validation pipeline."""

    @pytest.mark.asyncio
    async def test_no_regex_match_returns_valid_no_llm_call(self):
        """When regex doesn't match, LLM is NOT called → returns valid."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                "Hola, ¿en qué puedo ayudarte?",  # No price mention
                set(),
                [PRICE_CONSTRAINT],
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()  # LLM should NOT be invoked

    @pytest.mark.asyncio
    async def test_regex_matches_tool_called_returns_valid_no_llm_call(self):
        """Regex matches BUT required tool was called → valid, no LLM needed."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            is_valid, error = await validate_response_hybrid(
                "El presupuesto es de 410€ +IVA.",
                {"calcular_tarifa_con_elementos"},
                [PRICE_CONSTRAINT],
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_regex_only_constraint_fires_without_llm(self):
        """price_requires_tool is regex-only: fires immediately, LLM never called."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=True,  # Would be false positive — but never reached
        ) as mock_llm:
            is_valid, error = await validate_response_hybrid(
                "El presupuesto es de 410€ +IVA.",  # Regex matches
                set(),  # No tool called
                [PRICE_CONSTRAINT],
            )
            assert is_valid is False  # Regex-only: fires without LLM
            assert error == PRICE_CONSTRAINT["error_injection"]
            mock_llm.assert_not_called()  # LLM must NOT be consulted

    @pytest.mark.asyncio
    async def test_regex_matches_llm_confirms_violation_returns_invalid(self):
        """Regex matches, tool NOT called, LLM says 'invalid' → constraint fires."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=False,  # Real violation
        ):
            is_valid, error = await validate_response_hybrid(
                "Te va a costar 500€ +IVA, confía en mí.",  # Regex matches
                set(),  # No tool called
                [PRICE_CONSTRAINT],
            )
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]

    @pytest.mark.asyncio
    async def test_regex_matches_llm_unavailable_falls_back_to_regex(self):
        """Regex matches, LLM returns None (unavailable) → regex decides (violation)."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=None,  # LLM unavailable
        ):
            is_valid, error = await validate_response_hybrid(
                "Te va a costar 500€ +IVA.",
                set(),
                [PRICE_CONSTRAINT],
            )
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]

    @pytest.mark.asyncio
    async def test_empty_constraints_returns_valid(self):
        """No constraints → always valid."""
        is_valid, error = await validate_response_hybrid("anything", set(), [])
        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_empty_response_returns_valid(self):
        """Empty response text → always valid."""
        is_valid, error = await validate_response_hybrid("", set(), [PRICE_CONSTRAINT])
        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_constraint_skipped_by_context_no_llm_call(self):
        """Constraint skipped by fsm_state → no regex, no LLM."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            fsm_state = {"tarifa_calculada": {"datos": {"price": 410.0}}}
            is_valid, error = await validate_response_hybrid(
                "El presupuesto es de 410€ +IVA.",
                set(),
                [PRICE_CONSTRAINT],
                fsm_state=fsm_state,
            )
            assert is_valid is True
            assert error is None
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_constraints_regex_only_fires_first_no_llm(self):
        """Regex-only constraint (price) fires immediately; LLM never called."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            is_valid, error = await validate_response_hybrid(
                "Te va a costar 500€ +IVA. Las imagenes se enviaran pronto.",
                set(),
                [PRICE_CONSTRAINT, IMAGES_CONSTRAINT],
            )
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]
            mock_llm.assert_not_called()  # Regex-only: zero LLM calls

    @pytest.mark.asyncio
    async def test_regex_only_constraint_preempts_later_llm_constraints(self):
        """Regex-only (price) fires before LLM-validated constraints are reached."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            # Both constraints regex-match, but price (regex-only) fires first
            is_valid, error = await validate_response_hybrid(
                "Son 410€ +IVA. Las imagenes se enviaran ahora.",
                set(),
                [PRICE_CONSTRAINT, IMAGES_CONSTRAINT],
            )
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]
            mock_llm.assert_not_called()  # Never reached images LLM check

    @pytest.mark.asyncio
    async def test_all_llm_constraints_false_positive_returns_valid(self):
        """Non-regex-only constraints that are all LLM false positives → valid."""
        with patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=True,  # Always false positive
        ):
            # Only use non-regex-only constraints (images, docs)
            is_valid, error = await validate_response_hybrid(
                "Las imagenes se enviaran ahora. El certificado de resistencia incluido.",
                set(),
                [IMAGES_CONSTRAINT, DOCS_CONSTRAINT],
            )
            assert is_valid is True
            assert error is None

    @pytest.mark.asyncio
    async def test_pipe_separated_tools_any_match_passes(self):
        """Constraint with pipe-separated tools: ANY matching tool passes."""
        with patch("agent.services.constraint_service.validate_with_llm") as mock_llm:
            # docs_from_tool_only accepts either tool
            is_valid, error = await validate_response_hybrid(
                "El certificado de resistencia incluido.",
                {"obtener_documentacion_elemento"},  # One of the accepted tools
                [DOCS_CONSTRAINT],
            )
            assert is_valid is True
            mock_llm.assert_not_called()  # Tool was called, no LLM needed

    @pytest.mark.asyncio
    async def test_invalid_regex_skipped_gracefully(self):
        """Constraint with invalid regex → skipped, no crash."""
        bad_constraint = {
            "constraint_type": "broken_regex",
            "detection_pattern": r"[invalid(regex",  # Invalid regex
            "required_tool": "some_tool",
            "error_injection": "This should never fire.",
            "priority": 50,
        }

        is_valid, error = await validate_response_hybrid(
            "Any response text",
            set(),
            [bad_constraint],
        )
        assert is_valid is True
        assert error is None


# ============================================================================
# Phase 2B: Backward compatibility — validate_response (sync) still works
# ============================================================================

class TestSyncValidateResponseStillWorks:
    """Ensure the original sync validate_response() is unchanged and working."""

    def test_sync_validate_response_detects_violation(self):
        """Original sync function still catches violations."""
        is_valid, error = validate_response(
            "El precio es 500€ +IVA.",
            set(),
            [PRICE_CONSTRAINT],
        )
        assert is_valid is False
        assert error == PRICE_CONSTRAINT["error_injection"]

    def test_sync_validate_response_passes_with_tool(self):
        """Original sync function still passes when tool was called."""
        is_valid, error = validate_response(
            "El precio es 410€ +IVA.",
            {"calcular_tarifa_con_elementos"},
            [PRICE_CONSTRAINT],
        )
        assert is_valid is True

    def test_sync_validate_response_uses_fsm_state(self):
        """Original sync function still uses fsm_state for skip logic."""
        is_valid, error = validate_response(
            "El precio es 410€ +IVA.",
            set(),
            [PRICE_CONSTRAINT],
            fsm_state={"tarifa_calculada": {"datos": {"price": 410.0}}},
        )
        assert is_valid is True  # Skipped by context


# ============================================================================
# Phase 2C: Integration — _validate_response_constraints with hybrid path
# ============================================================================

class TestValidateResponseConstraintsHybrid:
    """Test base_mode._validate_response_constraints() calls hybrid validation."""

    @pytest.mark.asyncio
    async def test_hybrid_validation_called_in_base_mode(self):
        """
        _validate_response_constraints should call validate_response_hybrid,
        NOT the sync validate_response.
        """
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {"conversation_id": "test", "mode_context": {}}

        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            return_value=[PRICE_CONSTRAINT],
        ), patch(
            "agent.services.constraint_service.validate_response_hybrid",
            new_callable=AsyncMock,
            return_value=(True, None),
        ) as mock_hybrid:
            is_valid, error = await mode._validate_response_constraints(
                "410€", ["calcular_tarifa_con_elementos"], state,
            )
            assert is_valid is True
            mock_hybrid.assert_called_once()

    @pytest.mark.asyncio
    async def test_current_mode_context_passed_to_hybrid(self):
        """
        When current_mode_context is provided, it should be passed as fsm_state
        to validate_response_hybrid.
        """
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {
            "conversation_id": "test",
            "mode_context": {"old_key": "stale"},  # Stale state
        }
        current_ctx = {"tarifa_calculada": {"datos": {"price": 410.0}}}

        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            return_value=[PRICE_CONSTRAINT],
        ), patch(
            "agent.services.constraint_service.validate_response_hybrid",
            new_callable=AsyncMock,
            return_value=(True, None),
        ) as mock_hybrid:
            await mode._validate_response_constraints(
                "410€", [], state, current_mode_context=current_ctx,
            )

            # Verify fsm_state is current_ctx (not stale state)
            call_args = mock_hybrid.call_args
            assert call_args.kwargs["fsm_state"] == current_ctx

    @pytest.mark.asyncio
    async def test_no_constraints_returns_valid(self):
        """When no constraints loaded, return valid immediately."""
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {"conversation_id": "test", "mode_context": {}}

        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            return_value=[],
        ):
            is_valid, error = await mode._validate_response_constraints(
                "500€", [], state,
            )
            assert is_valid is True

    @pytest.mark.asyncio
    async def test_constraint_loading_crash_fails_open(self):
        """If constraint loading crashes, fail open (return valid)."""
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {"conversation_id": "test", "mode_context": {}}

        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection failed"),
        ):
            is_valid, error = await mode._validate_response_constraints(
                "500€", [], state,
            )
            assert is_valid is True  # Fail open

    @pytest.mark.asyncio
    async def test_end_to_end_regex_only_constraint_fires_without_llm(self):
        """
        End-to-end: regex-only constraint (price) fires immediately, no LLM.
        This tests the FULL pipeline through base_mode integration.
        """
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {"conversation_id": "test", "mode_context": {}}

        # Mock: constraints loaded from DB
        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            return_value=[PRICE_CONSTRAINT],
        ), patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            is_valid, error = await mode._validate_response_constraints(
                "Tu presupuesto es de 410€ +IVA.",  # Regex WILL match
                [],  # No tools called this turn
                state,
            )
            # price_requires_tool is regex-only: fires immediately
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]
            mock_llm.assert_not_called()  # LLM never consulted

    @pytest.mark.asyncio
    async def test_end_to_end_hybrid_real_violation_fires(self):
        """
        End-to-end: regex matches, LLM confirms violation → constraint fires.
        """
        from agent.modes.base_mode import BaseModeNode

        class TestMode(BaseModeNode):
            async def _process_message(self, message, state):
                return {"ai_response": "test"}
            def get_tools(self):
                return []

        mode = TestMode("TEST_MODE")
        state = {"conversation_id": "test", "mode_context": {}}

        with patch(
            "agent.services.constraint_service.get_constraints_for_category",
            new_callable=AsyncMock,
            return_value=[PRICE_CONSTRAINT],
        ), patch(
            "agent.services.constraint_service.validate_with_llm",
            new_callable=AsyncMock,
            return_value=False,  # LLM says: real violation
        ):
            is_valid, error = await mode._validate_response_constraints(
                "Creo que te costará unos 500€ +IVA.",
                [],
                state,
            )
            assert is_valid is False
            assert error == PRICE_CONSTRAINT["error_injection"]
