"""
Tests for variant_interpretation_service.py — Task 4.1.

Covers:
- validate_and_apply_allocations() deterministic validation logic
- interpret_variant_allocations() with mocked LLMRouter
- Edge cases: over-allocation, invalid codes, duplicate codes, dry_run

All tests run without external services (DB, Redis, LLM are mocked).
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from agent.services.variant_interpretation_service import (
    VariantAllocation,
    VariantInterpretationResult,
    interpret_variant_allocations,
    validate_and_apply_allocations,
    _parse_llm_response,
    _fuzzy_match_option,
)
from agent.state.conversation_state import PendingVariantGroup, VariantResolution
from shared.llm_router import LLMResponse, ModelTier, Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pending(
    codigo_base: str = "PLACA_SOLAR",
    opciones: list[str] | None = None,
    cantidad_total: int = 3,
    cantidad_resuelta: int = 0,
    resoluciones: list[VariantResolution] | None = None,
) -> PendingVariantGroup:
    """Build a PendingVariantGroup for testing."""
    if opciones is None:
        opciones = ["Con regulador propio", "Regulador existente del vehículo"]
    if resoluciones is None:
        resoluciones = []

    return PendingVariantGroup(
        pending_id=f"{codigo_base}_0",
        codigo_base=codigo_base,
        pregunta="¿La placa solar incluye su propio regulador o usa el del vehículo?",
        opciones=opciones,
        cantidad_total=cantidad_total,
        cantidad_resuelta=cantidad_resuelta,
        cantidad_pendiente=cantidad_total - cantidad_resuelta,
        resoluciones=resoluciones,
        status="pending" if cantidad_resuelta == 0 else "partial",
    )


def _make_allocation(
    variant_code: str,
    quantity: int,
    confidence: float = 0.9,
) -> VariantAllocation:
    """Build a VariantAllocation for testing."""
    return VariantAllocation(
        variant_code=variant_code,
        quantity=quantity,
        confidence=confidence,
    )


def _make_llm_response(
    content: str,
    success: bool = True,
    tier: ModelTier = ModelTier.LOCAL_FAST,
) -> LLMResponse:
    """Build a mock LLMResponse."""
    return LLMResponse(
        content=content,
        provider=Provider.OLLAMA,
        model="qwen2.5:3b",
        tier=tier,
        latency_ms=100,
        input_tokens=50,
        output_tokens=30,
        success=success,
        error=None if success else "mock error",
    )


# ===========================================================================
# Test class: validate_and_apply_allocations (deterministic)
# ===========================================================================


@pytest.mark.asyncio
class TestValidateAndApplyAllocations:
    """Tests for deterministic validation and application of allocations."""

    async def test_validate_valid_full_allocation(self):
        """3 units, allocations sum to 3, all variant codes valid → success."""
        pending = _make_pending(cantidad_total=3)
        allocations = [
            _make_allocation("Con regulador propio", 2),
            _make_allocation("Regulador existente del vehículo", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert errors == [], f"Expected no errors, got {errors}"
        assert updated.get("cantidad_resuelta") == 3
        assert updated.get("cantidad_pendiente") == 0
        assert updated.get("status") == "resolved"
        assert len(updated.get("resoluciones", [])) == 2

    async def test_validate_partial_allocation(self):
        """3 units, allocations sum to 2 → validation error (sum mismatch)."""
        pending = _make_pending(cantidad_total=3)
        allocations = [
            _make_allocation("Con regulador propio", 1),
            _make_allocation("Regulador existente del vehículo", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert len(errors) > 0, "Expected validation errors for partial allocation"
        assert any("Sum of quantities (2) != cantidad_pendiente (3)" in e for e in errors)
        # State should NOT be modified on error
        assert updated.get("cantidad_resuelta", 0) == 0

    async def test_validate_invalid_option(self):
        """Allocation with non-existent variant code → error."""
        pending = _make_pending(cantidad_total=2)
        allocations = [
            _make_allocation("Opción que no existe", 1),
            _make_allocation("Con regulador propio", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert len(errors) > 0, "Expected validation error for invalid option"
        assert any("does not match any option" in e for e in errors)

    async def test_validate_over_allocation(self):
        """Allocations sum > remaining → error."""
        pending = _make_pending(cantidad_total=3)
        allocations = [
            _make_allocation("Con regulador propio", 3),
            _make_allocation("Regulador existente del vehículo", 2),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert len(errors) > 0, "Expected validation error for over-allocation"
        assert any("Sum of quantities (5) != cantidad_pendiente (3)" in e for e in errors)

    async def test_validate_applies_correctly(self):
        """After valid apply, cantidad_resuelta increments, status changes."""
        pending = _make_pending(cantidad_total=3, cantidad_resuelta=0)
        allocations = [
            _make_allocation("Con regulador propio", 2),
            _make_allocation("Regulador existente del vehículo", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert errors == []
        assert updated["cantidad_resuelta"] == 3
        assert updated["cantidad_pendiente"] == 0
        assert updated["status"] == "resolved"
        assert updated["pending_id"] == "PLACA_SOLAR_0"
        assert updated["codigo_base"] == "PLACA_SOLAR"

        # Verify resoluciones content
        resoluciones = updated["resoluciones"]
        assert len(resoluciones) == 2
        assert resoluciones[0]["variant_code"] == "Con regulador propio"
        assert resoluciones[0]["quantity"] == 2
        assert resoluciones[0]["source"] == "user_explicit"
        assert resoluciones[1]["variant_code"] == "Regulador existente del vehículo"
        assert resoluciones[1]["quantity"] == 1

    async def test_dry_run_does_not_modify(self):
        """dry_run=True validates but doesn't change pending state."""
        pending = _make_pending(cantidad_total=3)
        allocations = [
            _make_allocation("Con regulador propio", 2),
            _make_allocation("Regulador existente del vehículo", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=True,
        )

        assert errors == [], f"Expected no errors for valid dry_run, got {errors}"
        # On dry_run, the ORIGINAL pending is returned unmodified
        assert updated.get("cantidad_resuelta", 0) == 0
        assert updated.get("cantidad_pendiente", 3) == 3
        assert updated.get("status", "pending") == "pending"
        assert updated.get("resoluciones", []) == []

    async def test_validate_empty_allocations(self):
        """No allocations provided → error."""
        pending = _make_pending(cantidad_total=3)

        updated, errors = validate_and_apply_allocations(
            pending, [], dry_run=False,
        )

        assert len(errors) > 0
        assert any("No allocations provided" in e for e in errors)

    async def test_validate_duplicate_variant_codes(self):
        """Duplicate variant_codes in allocations → error."""
        pending = _make_pending(cantidad_total=3)
        allocations = [
            _make_allocation("Con regulador propio", 2),
            _make_allocation("con regulador propio", 1),  # duplicate (case-insensitive)
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert len(errors) > 0
        assert any("Duplicate" in e for e in errors)

    async def test_validate_partial_status_after_prior_resolution(self):
        """Pre-existing resolutions + new allocation → partial or resolved."""
        pending = _make_pending(
            cantidad_total=3,
            cantidad_resuelta=1,
            resoluciones=[
                VariantResolution(
                    variant_code="Con regulador propio",
                    quantity=1,
                    confidence=0.9,
                    source="user_explicit",
                ),
            ],
        )
        # cantidad_pendiente should be 2
        assert pending["cantidad_pendiente"] == 2

        allocations = [
            _make_allocation("Regulador existente del vehículo", 2),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=False,
        )

        assert errors == []
        assert updated["cantidad_resuelta"] == 3
        assert updated["status"] == "resolved"
        assert len(updated["resoluciones"]) == 2  # 1 prior + 1 new

    async def test_fuzzy_match_accent_insensitive(self):
        """Fuzzy matching handles accented characters."""
        pending = _make_pending(
            opciones=["Suspensión delantera", "Suspensión trasera"],
            cantidad_total=2,
        )
        allocations = [
            _make_allocation("Suspension delantera", 1),  # no accent
            _make_allocation("suspensión trasera", 1),  # lowercase + accent
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=True,
        )

        assert errors == [], f"Expected no errors with fuzzy matching, got {errors}"

    async def test_fuzzy_match_substring(self):
        """Fuzzy matching allows substring containment."""
        pending = _make_pending(
            opciones=["Suspensión delantera", "Suspensión trasera"],
            cantidad_total=2,
        )
        allocations = [
            _make_allocation("delantera", 1),
            _make_allocation("trasera", 1),
        ]

        updated, errors = validate_and_apply_allocations(
            pending, allocations, dry_run=True,
        )

        assert errors == [], f"Expected no errors with substring matching, got {errors}"


# ===========================================================================
# Test class: interpret_variant_allocations (mocked LLM)
# ===========================================================================


@pytest.mark.asyncio
class TestInterpretVariantAllocations:
    """Tests for LLM-based variant interpretation with mocked router."""

    async def test_interpret_with_mocked_llm(self):
        """Mock LLMRouter to return valid JSON, verify parsing works."""
        pending = _make_pending(cantidad_total=3)

        llm_json = json.dumps({
            "allocations": [
                {"variant_code": "Con regulador propio", "quantity": 2, "confidence": 0.9},
                {"variant_code": "Regulador existente del vehículo", "quantity": 1, "confidence": 0.85},
            ],
            "needs_clarification": False,
            "clarification_reason": None,
        })

        mock_response = _make_llm_response(llm_json, success=True)
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch(
            "agent.services.variant_interpretation_service.get_llm_router",
            return_value=mock_router,
        ):
            result = await interpret_variant_allocations(
                user_message="2 con regulador propio y 1 existente",
                pending_variant=pending,
            )

        assert not result.needs_clarification
        assert len(result.allocations) == 2
        assert result.allocations[0].variant_code == "Con regulador propio"
        assert result.allocations[0].quantity == 2
        assert result.allocations[1].variant_code == "Regulador existente del vehículo"
        assert result.allocations[1].quantity == 1

    async def test_interpret_local_low_confidence_escalates_to_cloud(self):
        """When local LLM returns low confidence, escalates to cloud."""
        pending = _make_pending(cantidad_total=2)

        # Local returns low confidence
        local_json = json.dumps({
            "allocations": [
                {"variant_code": "Con regulador propio", "quantity": 1, "confidence": 0.3},
                {"variant_code": "Regulador existente del vehículo", "quantity": 1, "confidence": 0.3},
            ],
            "needs_clarification": False,
        })

        # Cloud returns high confidence
        cloud_json = json.dumps({
            "allocations": [
                {"variant_code": "Con regulador propio", "quantity": 1, "confidence": 0.95},
                {"variant_code": "Regulador existente del vehículo", "quantity": 1, "confidence": 0.95},
            ],
            "needs_clarification": False,
        })

        local_response = _make_llm_response(local_json, tier=ModelTier.LOCAL_FAST)
        cloud_response = _make_llm_response(cloud_json, tier=ModelTier.CLOUD_STANDARD)

        call_count = 0

        async def mock_invoke(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return local_response  # First call: local
            return cloud_response  # Second call: cloud

        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(side_effect=mock_invoke)

        with patch(
            "agent.services.variant_interpretation_service.get_llm_router",
            return_value=mock_router,
        ):
            result = await interpret_variant_allocations(
                user_message="1 propio y 1 existente",
                pending_variant=pending,
            )

        # Cloud result should be used (higher confidence)
        assert not result.needs_clarification
        assert len(result.allocations) == 2
        assert call_count == 2, "Should have called LLM twice (local + cloud)"

    async def test_interpret_both_fail_returns_clarification(self):
        """When both local and cloud fail, returns needs_clarification."""
        pending = _make_pending(cantidad_total=2)

        failed_response = _make_llm_response("", success=False)

        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=failed_response)

        with patch(
            "agent.services.variant_interpretation_service.get_llm_router",
            return_value=mock_router,
        ):
            result = await interpret_variant_allocations(
                user_message="algo raro",
                pending_variant=pending,
            )

        assert result.needs_clarification is True
        assert result.clarification_reason is not None

    async def test_interpret_llm_returns_needs_clarification(self):
        """When LLM explicitly says it needs clarification."""
        pending = _make_pending(cantidad_total=2)

        llm_json = json.dumps({
            "allocations": [],
            "needs_clarification": True,
            "clarification_reason": "La respuesta es ambigua.",
        })

        # Local returns clarification, cloud also returns clarification
        mock_response = _make_llm_response(llm_json)
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch(
            "agent.services.variant_interpretation_service.get_llm_router",
            return_value=mock_router,
        ):
            result = await interpret_variant_allocations(
                user_message="no sé",
                pending_variant=pending,
            )

        assert result.needs_clarification is True
        assert "ambigua" in (result.clarification_reason or "")

    async def test_interpret_with_conversation_context(self):
        """Conversation context is included in the prompt."""
        pending = _make_pending(cantidad_total=2)

        llm_json = json.dumps({
            "allocations": [
                {"variant_code": "Con regulador propio", "quantity": 1, "confidence": 0.9},
                {"variant_code": "Regulador existente del vehículo", "quantity": 1, "confidence": 0.9},
            ],
            "needs_clarification": False,
        })

        mock_response = _make_llm_response(llm_json)
        mock_router = AsyncMock()
        mock_router.invoke = AsyncMock(return_value=mock_response)

        with patch(
            "agent.services.variant_interpretation_service.get_llm_router",
            return_value=mock_router,
        ):
            result = await interpret_variant_allocations(
                user_message="1 y 1",
                pending_variant=pending,
                conversation_context="El usuario tiene 2 placas solares en una autocaravana",
            )

        assert not result.needs_clarification
        # Verify that the prompt was built with context (via the invoke call)
        call_args = mock_router.invoke.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        prompt_text = messages[0]["content"] if messages else ""
        assert "CONTEXTO DE LA CONVERSACIÓN" in prompt_text


# ===========================================================================
# Test class: _parse_llm_response (internal helper)
# ===========================================================================


class TestParseLlmResponse:
    """Tests for LLM response parsing edge cases."""

    def test_parse_markdown_fences(self):
        """Handle LLM wrapping JSON in markdown code fences."""
        content = """```json
{"allocations": [{"variant_code": "delantera", "quantity": 1, "confidence": 0.9}], "needs_clarification": false}
```"""
        pending = _make_pending(cantidad_total=1)
        response = _make_llm_response(content)

        result = _parse_llm_response(response, pending)

        assert result is not None
        assert not result.needs_clarification
        assert len(result.allocations) == 1

    def test_parse_trailing_comma(self):
        """Handle LLM adding trailing commas (common mistake)."""
        content = '{"allocations": [{"variant_code": "delantera", "quantity": 1, "confidence": 0.9,},], "needs_clarification": false,}'
        pending = _make_pending(cantidad_total=1)
        response = _make_llm_response(content)

        result = _parse_llm_response(response, pending)

        assert result is not None
        assert len(result.allocations) == 1

    def test_parse_invalid_json(self):
        """Completely invalid JSON returns None."""
        content = "this is not json at all"
        pending = _make_pending(cantidad_total=1)
        response = _make_llm_response(content)

        result = _parse_llm_response(response, pending)

        assert result is None

    def test_parse_needs_clarification_response(self):
        """LLM returns needs_clarification structure."""
        content = json.dumps({
            "allocations": [],
            "needs_clarification": True,
            "clarification_reason": "No puedo determinar la opción.",
        })
        pending = _make_pending(cantidad_total=1)
        response = _make_llm_response(content)

        result = _parse_llm_response(response, pending)

        assert result is not None
        assert result.needs_clarification is True
        assert "No puedo" in (result.clarification_reason or "")


# ===========================================================================
# Test class: _fuzzy_match_option (internal helper)
# ===========================================================================


class TestFuzzyMatchOption:
    """Tests for option fuzzy matching."""

    def test_exact_match(self):
        """Exact match (case-insensitive) works."""
        result = _fuzzy_match_option(
            "Suspensión delantera",
            ["Suspensión delantera", "Suspensión trasera"],
        )
        assert result == "Suspensión delantera"

    def test_case_insensitive_match(self):
        """Case-insensitive exact match."""
        result = _fuzzy_match_option(
            "SUSPENSIÓN DELANTERA",
            ["Suspensión delantera", "Suspensión trasera"],
        )
        assert result == "Suspensión delantera"

    def test_accent_insensitive_match(self):
        """Accent-stripped matching."""
        result = _fuzzy_match_option(
            "Suspension delantera",  # no accent
            ["Suspensión delantera", "Suspensión trasera"],
        )
        assert result == "Suspensión delantera"

    def test_substring_match(self):
        """Substring containment in either direction."""
        result = _fuzzy_match_option(
            "delantera",
            ["Suspensión delantera", "Suspensión trasera"],
        )
        assert result == "Suspensión delantera"

    def test_no_match(self):
        """No match returns None."""
        result = _fuzzy_match_option(
            "lateral",
            ["Suspensión delantera", "Suspensión trasera"],
        )
        assert result is None

    def test_empty_options(self):
        """Empty options list returns None."""
        result = _fuzzy_match_option("anything", [])
        assert result is None
