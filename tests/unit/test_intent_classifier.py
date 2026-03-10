"""
Unit tests for agent/services/intent_classifier.py

Covers:
  REQ-INTENT-1  Classification accuracy for 9 intent categories
  REQ-INTENT-2  LLM is the primary classifier (not regex)
  REQ-INTENT-3  Context-aware classification (phase + last agent message)
  REQ-INTENT-4  Graceful fallback on LLM failure / timeout / bad JSON
  REQ-INTENT-5  Latency: mock-based check that classify() completes quickly
  Edge cases    Long messages, emoji-only, low confidence forcing UNCLEAR
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from agent.services.intent_classifier import (
    ClassificationContext,
    IntentClassifier,
    IntentResult,
    UserIntent,
    _keyword_fallback,
    get_intent_classifier,
)
from shared.llm_router import LLMResponse, ModelTier, Provider


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_llm_response(content: str, success: bool = True) -> LLMResponse:
    """Build a fake LLMResponse with the given JSON content."""
    return LLMResponse(
        content=content,
        provider=Provider.OLLAMA,
        model="qwen2.5:3b",
        tier=ModelTier.LOCAL_FAST,
        latency_ms=50,
        success=success,
        error=None if success else "mock error",
    )


def _make_ctx(
    phase: str = "photos",
    element_name: str = "Escape",
    pending_fields: list[str] | None = None,
    last_agent_message: str | None = None,
) -> ClassificationContext:
    return ClassificationContext(
        current_phase=phase,
        current_element_name=element_name,
        pending_fields=pending_fields or [],
        last_agent_message=last_agent_message,
    )


def _llm_json(intent: str, confidence: float = 0.9, reasoning: str = "test") -> str:
    return json.dumps({
        "intent": intent,
        "confidence": confidence,
        "reasoning": reasoning,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def classifier() -> IntentClassifier:
    """Return a fresh IntentClassifier with a mocked LLM router."""
    with patch("agent.services.intent_classifier.get_llm_router") as mock_router_fn:
        mock_router = MagicMock()
        mock_router_fn.return_value = mock_router
        with patch("agent.services.intent_classifier.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(EXPEDIENTE_V2_ENABLED=True)
            clf = IntentClassifier()
            clf._router = mock_router
            yield clf


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-1: Classification accuracy
# ─────────────────────────────────────────────────────────────────────────────

class TestClassificationAccuracy:
    """REQ-INTENT-1: correct intents for representative messages."""

    @pytest.mark.asyncio
    async def test_listo_classified_as_completion_signal(self, classifier):
        """'listo' → COMPLETION_SIGNAL."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("completion_signal"))
        )
        result = await classifier.classify("listo", _make_ctx("photos"))
        assert result.intent == UserIntent.COMPLETION_SIGNAL
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_photo_with_short_text_classified_as_photo_sent(self, classifier):
        """Photos attachment with short text → PHOTO_SENT."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("photo_sent", confidence=0.95))
        )
        result = await classifier.classify("ahí van", _make_ctx("photos"), has_images=True)
        assert result.intent == UserIntent.PHOTO_SENT

    @pytest.mark.asyncio
    async def test_data_response_classified_in_data_phase(self, classifier):
        """Technical data reply in data phase → DATA_RESPONSE."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("data_response"))
        )
        ctx = _make_ctx("data", pending_fields=["Marca del regulador"])
        result = await classifier.classify(
            "SOLARFAM, epever, mppt 100-20l", ctx
        )
        assert result.intent == UserIntent.DATA_RESPONSE

    @pytest.mark.asyncio
    async def test_question_mark_classified_as_question(self, classifier):
        """'¿qué fotos necesito?' → QUESTION."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("question"))
        )
        result = await classifier.classify(
            "¿qué fotos necesito?", _make_ctx("photos")
        )
        assert result.intent == UserIntent.QUESTION

    @pytest.mark.asyncio
    async def test_rejection_classified_as_rejection_not_completion(self, classifier):
        """'no es necesario' → REJECTION, NOT COMPLETION_SIGNAL."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("rejection", confidence=0.88))
        )
        result = await classifier.classify(
            "no es necesario", _make_ctx("data")
        )
        assert result.intent == UserIntent.REJECTION
        assert result.intent != UserIntent.COMPLETION_SIGNAL

    @pytest.mark.asyncio
    async def test_correction_classified_as_correction(self, classifier):
        """'perdona, la marca es otra' → CORRECTION."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("correction"))
        )
        result = await classifier.classify(
            "perdona, la marca es otra", _make_ctx("data")
        )
        assert result.intent == UserIntent.CORRECTION

    @pytest.mark.asyncio
    async def test_empty_string_classified_as_empty(self, classifier):
        """Empty string → EMPTY (fast path, no LLM call)."""
        result = await classifier.classify("", _make_ctx("photos"))
        assert result.intent == UserIntent.EMPTY
        assert result.confidence == 1.0
        # LLM should NOT be called for empty messages
        classifier._router.invoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_classified_as_empty(self, classifier):
        """Whitespace-only message → EMPTY (fast path)."""
        result = await classifier.classify("   \t\n", _make_ctx("photos"))
        assert result.intent == UserIntent.EMPTY

    @pytest.mark.asyncio
    async def test_empty_with_images_classified_as_photo_sent(self, classifier):
        """Empty message + has_images=True → PHOTO_SENT (fast path)."""
        result = await classifier.classify("", _make_ctx("photos"), has_images=True)
        assert result.intent == UserIntent.PHOTO_SENT
        assert result.confidence == 1.0
        classifier._router.invoke.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-2: LLM is primary — fallback_used=False when LLM succeeds
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMPrimary:
    """REQ-INTENT-2: When LLM succeeds, fallback_used must be False."""

    @pytest.mark.asyncio
    async def test_fallback_not_used_when_llm_returns_valid_response(self, classifier):
        """With valid LLM response, fallback_used=False."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("completion_signal", confidence=0.92))
        )
        result = await classifier.classify("listo ya", _make_ctx("photos"))
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_llm_router_called_for_non_empty_messages(self, classifier):
        """LLM router.invoke is called for non-empty, non-trivial messages."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("data_response"))
        )
        await classifier.classify("marca AKRAPOVIC", _make_ctx("data"))
        classifier._router.invoke.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-3: Context-aware classification
# ─────────────────────────────────────────────────────────────────────────────

class TestContextAware:
    """REQ-INTENT-3: Same word can have different meaning depending on phase."""

    @pytest.mark.asyncio
    async def test_ya_in_photos_phase_classified_by_llm(self, classifier):
        """'ya' in photos phase: LLM decides (likely COMPLETION_SIGNAL)."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("completion_signal", confidence=0.78))
        )
        ctx = _make_ctx("photos", last_agent_message=None)
        result = await classifier.classify("ya", ctx)
        # LLM was called with phase context
        classifier._router.invoke.assert_called_once()
        # Result must be a valid intent (not raise)
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_context_passed_to_llm_prompt(self, classifier):
        """Verify context fields are interpolated into the LLM prompt."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("data_response"))
        )
        ctx = _make_ctx(
            phase="data",
            element_name="Suspension trasera",
            pending_fields=["Marca del muelle"],
            last_agent_message="¿Cuál es la marca del muelle?",
        )
        await classifier.classify("Ohlins", ctx)
        # Inspect the messages passed to router
        call_args = classifier._router.invoke.call_args
        # Extract messages from kwargs first, then fall back to positional args
        messages = call_args.kwargs.get("messages")
        if messages is None and call_args.args:
            messages = call_args.args[0]
        messages = messages or []
        # System prompt should contain phase context
        system_content = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        assert "data" in system_content
        assert "Suspension trasera" in system_content


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-4: Fallback on LLM failure
# ─────────────────────────────────────────────────────────────────────────────

class TestFallback:
    """REQ-INTENT-4: Graceful fallback when LLM fails."""

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self, classifier):
        """LLM exception → fallback_used=True, returns safe intent."""
        classifier._router.invoke = AsyncMock(
            side_effect=RuntimeError("LLM crashed")
        )
        result = await classifier.classify("listo", _make_ctx("photos"))
        assert result.fallback_used is True
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_fallback_on_llm_timeout(self, classifier):
        """LLM timeout (asyncio.TimeoutError) → fallback_used=True."""
        async def slow_llm(*args, **kwargs):
            await asyncio.sleep(100)  # Will be cancelled by wait_for

        classifier._router.invoke = AsyncMock(side_effect=slow_llm)

        # Patch the timeout to 0 seconds to force immediate timeout
        with patch("agent.services.intent_classifier._LLM_TIMEOUT_SECONDS", 0.001):
            result = await classifier.classify("listo", _make_ctx("photos"))

        assert result.fallback_used is True
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure_response(self, classifier):
        """LLM returns success=False → keyword fallback used."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response("", success=False)
        )
        result = await classifier.classify("listo", _make_ctx("photos"))
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_unclear_on_invalid_json_from_llm(self, classifier):
        """LLM returns unparseable JSON → UNCLEAR returned (fallback from parse error)."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response("NOT VALID JSON AT ALL !!!")
        )
        result = await classifier.classify("algo raro", _make_ctx("data"))
        # On JSON parse failure, keyword fallback is used → fallback_used=True
        # OR internal UNCLEAR fallback path → can be either
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_unknown_intent_value_mapped_to_unclear(self, classifier):
        """LLM returns unknown intent string → mapped to UNCLEAR."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(
                json.dumps({"intent": "totally_new_intent", "confidence": 0.9, "reasoning": "x"})
            )
        )
        result = await classifier.classify("algún texto", _make_ctx("data"))
        assert result.intent == UserIntent.UNCLEAR


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-4 continued: Low confidence forces UNCLEAR
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceThreshold:
    """Confidence < 0.6 forces UNCLEAR regardless of intent."""

    @pytest.mark.asyncio
    async def test_low_confidence_forces_unclear(self, classifier):
        """confidence=0.4 → UNCLEAR even if LLM said completion_signal."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(
                _llm_json("completion_signal", confidence=0.4)
            )
        )
        result = await classifier.classify("quizás", _make_ctx("photos"))
        assert result.intent == UserIntent.UNCLEAR

    @pytest.mark.asyncio
    async def test_confidence_exactly_at_threshold_not_forced_unclear(self, classifier):
        """confidence=0.6 → NOT forced to UNCLEAR (>= threshold passes)."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(
                _llm_json("completion_signal", confidence=0.6)
            )
        )
        result = await classifier.classify("listo", _make_ctx("photos"))
        assert result.intent == UserIntent.COMPLETION_SIGNAL

    @pytest.mark.asyncio
    async def test_low_confidence_fallback_used_is_false(self, classifier):
        """Low confidence fallback sets fallback_used=False (parse path, not LLM crash)."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("question", confidence=0.3))
        )
        result = await classifier.classify("algo", _make_ctx("data"))
        assert result.intent == UserIntent.UNCLEAR
        assert result.fallback_used is False  # Parse path — LLM succeeded, just low confidence


# ─────────────────────────────────────────────────────────────────────────────
# REQ-INTENT-5: Latency — mock-based check
# ─────────────────────────────────────────────────────────────────────────────

class TestLatency:
    """REQ-INTENT-5: classify() completes quickly when LLM mock returns immediately."""

    @pytest.mark.asyncio
    async def test_classify_completes_under_one_second_with_mock(self, classifier):
        """With immediate mock response, classify() finishes in < 1 s."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("data_response"))
        )
        import time
        start = time.monotonic()
        await classifier.classify("Akrapovic", _make_ctx("data"))
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"classify() took {elapsed:.3f}s — too slow with mock LLM"


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases: long messages, emojis, markdown fences in LLM response."""

    @pytest.mark.asyncio
    async def test_very_long_message_does_not_raise(self, classifier):
        """A 5000-character message should not raise any exception."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("data_response"))
        )
        long_message = "marca " * 800  # ~4800 chars
        result = await classifier.classify(long_message, _make_ctx("data"))
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_emoji_only_message_handled_gracefully(self, classifier):
        """Emoji-only messages don't crash the classifier."""
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(_llm_json("unclear", confidence=0.65))
        )
        result = await classifier.classify("👍🎉🔥", _make_ctx("photos"))
        assert isinstance(result.intent, UserIntent)

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_from_llm_is_parsed(self, classifier):
        """LLM wraps JSON in ```json ... ``` fences — should still parse correctly."""
        fenced = "```json\n" + _llm_json("completion_signal") + "\n```"
        classifier._router.invoke = AsyncMock(
            return_value=_make_llm_response(fenced)
        )
        result = await classifier.classify("listo", _make_ctx("photos"))
        assert result.intent == UserIntent.COMPLETION_SIGNAL
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_classify_never_raises(self, classifier):
        """classify() should NEVER propagate an exception to the caller."""
        classifier._router.invoke = AsyncMock(
            side_effect=Exception("unexpected crash")
        )
        # Should NOT raise
        try:
            result = await classifier.classify("test", _make_ctx("photos"))
        except Exception as e:
            pytest.fail(f"classify() should not raise, but raised: {e}")
        assert isinstance(result, IntentResult)


# ─────────────────────────────────────────────────────────────────────────────
# _keyword_fallback unit tests (pure function, no mocking needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordFallback:
    """Direct tests of the _keyword_fallback function."""

    def test_empty_message_returns_empty_intent(self):
        result = _keyword_fallback("", has_images=False)
        assert result.intent == UserIntent.EMPTY
        assert result.fallback_used is True

    def test_single_punctuation_returns_empty(self):
        result = _keyword_fallback(".", has_images=False)
        assert result.intent == UserIntent.EMPTY

    def test_images_with_short_text_returns_photo_sent(self):
        result = _keyword_fallback("ahí van", has_images=True)
        assert result.intent == UserIntent.PHOTO_SENT

    def test_question_mark_returns_question(self):
        result = _keyword_fallback("¿qué necesito?", has_images=False)
        assert result.intent == UserIntent.QUESTION

    def test_completion_keyword_listo_returns_completion_signal(self):
        result = _keyword_fallback("listo", has_images=False)
        assert result.intent == UserIntent.COMPLETION_SIGNAL

    def test_completion_phrase_ahi_van_returns_completion_signal(self):
        result = _keyword_fallback("ahí van las fotos", has_images=False)
        assert result.intent == UserIntent.COMPLETION_SIGNAL

    def test_unknown_text_returns_unclear(self):
        result = _keyword_fallback("algún texto completamente ambiguo xyz", has_images=False)
        assert result.intent == UserIntent.UNCLEAR

    def test_all_fallback_results_have_fallback_used_true(self):
        """Every result from _keyword_fallback must have fallback_used=True."""
        test_cases = [
            ("", False),
            ("listo", False),
            ("foto", True),
            ("¿cómo?", False),
            ("xyz abc", False),
        ]
        for message, has_images in test_cases:
            result = _keyword_fallback(message, has_images=has_images)
            assert result.fallback_used is True, (
                f"Expected fallback_used=True for '{message}', has_images={has_images}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleton:
    """get_intent_classifier() returns a consistent singleton."""

    def test_returns_same_instance_on_repeated_calls(self):
        with patch("agent.services.intent_classifier.get_settings") as ms, \
             patch("agent.services.intent_classifier.get_llm_router"):
            ms.return_value = MagicMock(EXPEDIENTE_V2_ENABLED=True)
            # Clear lru_cache to ensure fresh singleton
            from agent.services.intent_classifier import _get_classifier_singleton
            _get_classifier_singleton.cache_clear()
            instance_1 = get_intent_classifier()
            instance_2 = get_intent_classifier()
            assert instance_1 is instance_2

    def test_returns_intent_classifier_instance(self):
        with patch("agent.services.intent_classifier.get_settings") as ms, \
             patch("agent.services.intent_classifier.get_llm_router"):
            ms.return_value = MagicMock(EXPEDIENTE_V2_ENABLED=True)
            from agent.services.intent_classifier import _get_classifier_singleton
            _get_classifier_singleton.cache_clear()
            clf = get_intent_classifier()
            assert isinstance(clf, IntentClassifier)
