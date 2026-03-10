"""
Intent Classifier Service — EXPEDIENTE_MODE v2.

Classifies user messages into 9 intent categories using LLM-based classification
(qwen2.5:3b via LLMRouter, TaskType.CLASSIFICATION → Tier 1 / LOCAL_FAST).

This service replaces the regex-based PHOTO_COMPLETION_INTENT_RE pattern in
agent/utils/validation.py for the EXPEDIENTE element-collection sub-flow.

Feature flag: only used when EXPEDIENTE_V2_ENABLED=True.

Design decisions:
- LLM-first: qwen2.5:3b classifies intent via structured JSON response.
- Timeout: 3-second hard timeout via asyncio.wait_for; falls back to keyword
  detection on timeout or LLM failure.
- Keyword fallback is MINIMAL and conservative (5 rules, prefer UNCLEAR over
  guessing wrong).
- Never raises to caller — always returns a valid IntentResult.
- Singleton via module-level instance + get_intent_classifier().
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any

import structlog

from shared.config import get_settings
from shared.llm_router import TaskType, get_llm_router

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Intent enum
# ---------------------------------------------------------------------------


class UserIntent(str, Enum):
    """Exhaustive intent categories for user messages during element collection."""

    COMPLETION_SIGNAL = "completion_signal"
    """User signals they are done: 'listo', 'ya está', 'hecho', 'enviado', 'ahí van'."""

    PHOTO_SENT = "photo_sent"
    """User sent photo(s) without meaningful text, or short confirmation like 'ahí van'."""

    DATA_RESPONSE = "data_response"
    """User is answering a data question: brand, model, serial, technical spec."""

    QUESTION = "question"
    """User is asking something: '¿qué fotos necesito?', '¿es obligatorio?'"""

    REJECTION = "rejection"
    """User declines or says they don't have something: 'no tengo', 'no es necesario'."""

    CORRECTION = "correction"
    """User corrects a previous answer: 'perdona, la marca es otra', 'me equivoqué'."""

    OFF_TOPIC = "off_topic"
    """User asks about something unrelated to the current collection step."""

    UNCLEAR = "unclear"
    """Ambiguous message that cannot be reliably classified; trigger clarification."""

    EMPTY = "empty"
    """Empty, whitespace-only, or single punctuation message."""


# ---------------------------------------------------------------------------
# Context and result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ClassificationContext:
    """
    Contextual information provided to the classifier for context-aware
    intent resolution.

    The same message ('listo') can mean different things:
    - During photo collection → COMPLETION_SIGNAL (photos are done)
    - During data collection → DATA_RESPONSE or UNCLEAR (answering a field?)
    """

    current_phase: str
    """Phase of collection: 'photos' | 'data' | 'completed'."""

    current_element_name: str
    """Human-readable element name being collected (e.g., 'Escape de escape')."""

    pending_fields: list[str] = field(default_factory=list)
    """List of field labels still pending collection."""

    last_agent_message: str | None = None
    """Last message sent by the agent (for context)."""


@dataclass
class IntentResult:
    """
    Result of classifying a user message.

    Always returned even on failure (falls back to UNCLEAR).
    """

    intent: UserIntent
    """Classified intent."""

    confidence: float
    """Confidence score [0.0, 1.0]. Below 0.6 means UNCLEAR was returned."""

    reasoning: str | None = None
    """LLM reasoning for logging/debugging purposes."""

    fallback_used: bool = False
    """True if LLM call failed or timed out and keyword fallback was used."""


# ---------------------------------------------------------------------------
# Classification prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an intent classifier for a vehicle homologation data collection system.
Classify the user message into exactly ONE of these 9 intents.

INTENTS:
- completion_signal: User signals they finished (e.g. "listo", "ya está", "hecho", "enviadas", "ahí van", "terminado")
- photo_sent: User sent photos with no/minimal text, or short phrases like "ahí van las fotos"
- data_response: User is answering a data question (brand, model, serial number, technical specs, measurements)
- question: User asks a question (contains '?' or interrogative phrasing)
- rejection: User refuses or says they don't have something ("no tengo", "no es necesario", "no aplica")
- correction: User corrects a previous answer ("perdona", "me equivoqué", "en realidad es", "es otra")
- off_topic: User asks about something unrelated to current collection (pricing, other elements, general questions)
- unclear: Cannot be reliably classified; message is ambiguous
- empty: Message is empty, whitespace only, or single punctuation

CONTEXT PROVIDED:
- Current phase: {current_phase} (photos = collecting photos, data = collecting technical data)
- Current element: {current_element_name}
- Pending fields: {pending_fields}
- Last agent message: {last_agent_message}

RULES:
1. If has_images=true AND message is short or empty → prefer photo_sent over completion_signal
2. If current_phase='photos' AND message matches completion words → completion_signal
3. If current_phase='data' AND message looks like a value/answer → data_response
4. If confidence < 0.6 → use unclear
5. Respond ONLY with valid JSON, no markdown, no code blocks

RESPONSE FORMAT:
{{"intent": "<one of the 9 values above>", "confidence": <0.0-1.0>, "reasoning": "<brief english explanation>"}}"""

_USER_PROMPT_TEMPLATE = """Message: "{message}"
Has images attached: {has_images}"""

# Confidence threshold below which we force UNCLEAR
_MIN_CONFIDENCE = 0.6

# Hard timeout for LLM call in seconds (REQ-INTENT-5: P95 < 500ms; we give 3s
# to stay well under in nominal conditions while providing a safety net)
_LLM_TIMEOUT_SECONDS = 3.0


# ---------------------------------------------------------------------------
# Keyword fallback (minimal — only for LLM failure path, REQ-INTENT-4)
# ---------------------------------------------------------------------------

_COMPLETION_KEYWORDS = frozenset({
    "listo", "lista", "listos", "listas",
    "hecho", "hecha", "hechos", "hechas",
    "terminado", "terminada",
    "enviado", "enviada", "enviados", "enviadas",
    "mandado", "mandada", "mandados", "mandadas",
    "ya",
    "done",
})

_COMPLETION_PHRASES = (
    "ahí van",
    "ahí va",
    "ya están",
    "ya está",
    "ya te las",
    "ya las",
    "eso es todo",
    "nada más",
    "nada mas",
)


def _keyword_fallback(message: str, has_images: bool) -> IntentResult:
    """
    Conservative keyword-based fallback.

    Only used when the LLM call fails or times out.
    Prefers UNCLEAR over guessing wrong — 5 rules, nothing more.
    """
    stripped = message.strip()

    # Rule 1: Empty / whitespace
    if not stripped or stripped in (".", ",", "!", "?", "-", "_"):
        return IntentResult(
            intent=UserIntent.EMPTY,
            confidence=1.0,
            reasoning="Empty or single punctuation message",
            fallback_used=True,
        )

    # Rule 2: Has images + short/no meaningful text → PHOTO_SENT
    if has_images and len(stripped) <= 25:
        return IntentResult(
            intent=UserIntent.PHOTO_SENT,
            confidence=0.8,
            reasoning="Images attached with minimal text",
            fallback_used=True,
        )

    lower = stripped.lower()

    # Rule 3: Contains '?' → likely QUESTION
    if "?" in lower:
        return IntentResult(
            intent=UserIntent.QUESTION,
            confidence=0.75,
            reasoning="Message contains question mark",
            fallback_used=True,
        )

    # Rule 4: Completion keywords / phrases → COMPLETION_SIGNAL
    words = set(lower.split())
    if words & _COMPLETION_KEYWORDS or any(phrase in lower for phrase in _COMPLETION_PHRASES):
        return IntentResult(
            intent=UserIntent.COMPLETION_SIGNAL,
            confidence=0.7,
            reasoning="Keyword match: completion signal detected",
            fallback_used=True,
        )

    # Rule 5: Everything else → UNCLEAR (safe fallback, triggers clarification)
    return IntentResult(
        intent=UserIntent.UNCLEAR,
        confidence=0.5,
        reasoning="No keyword match; defaulting to unclear",
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------


class IntentClassifier:
    """
    LLM-driven intent classifier for EXPEDIENTE element-collection flow.

    Uses qwen2.5:3b (TaskType.CLASSIFICATION → LOCAL_FAST tier) with a
    3-second timeout. Falls back to conservative keyword detection if the
    LLM fails or times out.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._router = get_llm_router()

    async def classify(
        self,
        message: str,
        context: ClassificationContext,
        has_images: bool = False,
    ) -> IntentResult:
        """
        Classify a user message into one of 9 intent categories.

        Args:
            message: Raw user message text (may be empty if only images).
            context: Classification context (phase, element, pending fields).
            has_images: True if the message payload contains image attachments.

        Returns:
            IntentResult with intent, confidence, reasoning, and fallback_used flag.
            Never raises — returns UNCLEAR on any unexpected failure.
        """
        # Fast path: empty message
        stripped = message.strip()
        if not stripped:
            if has_images:
                return IntentResult(
                    intent=UserIntent.PHOTO_SENT,
                    confidence=1.0,
                    reasoning="No text, images attached",
                    fallback_used=False,
                )
            return IntentResult(
                intent=UserIntent.EMPTY,
                confidence=1.0,
                reasoning="Empty message, no images",
                fallback_used=False,
            )

        # Attempt LLM classification with timeout
        try:
            result = await asyncio.wait_for(
                self._classify_with_llm(stripped, context, has_images),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            logger.info(
                "intent_classified",
                intent=result.intent.value,
                confidence=result.confidence,
                fallback_used=result.fallback_used,
                phase=context.current_phase,
                element=context.current_element_name,
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "intent_classifier_timeout",
                timeout_seconds=_LLM_TIMEOUT_SECONDS,
                message_preview=stripped[:50],
            )
            return _keyword_fallback(stripped, has_images)

        except Exception as exc:
            logger.error(
                "intent_classifier_error",
                error=str(exc),
                error_type=type(exc).__name__,
                message_preview=stripped[:50],
            )
            return _keyword_fallback(stripped, has_images)

    async def _classify_with_llm(
        self,
        message: str,
        context: ClassificationContext,
        has_images: bool,
    ) -> IntentResult:
        """
        Internal: run LLM classification and parse the JSON response.

        Returns UNCLEAR (fallback_used=False) on parse errors or low confidence.
        Returns keyword fallback (fallback_used=True) only when LLM response is
        completely unusable.
        """
        # Build system prompt with context interpolated
        pending_fields_str = (
            ", ".join(context.pending_fields) if context.pending_fields else "ninguno"
        )
        last_agent_msg = context.last_agent_message or "N/A"

        system_prompt = _SYSTEM_PROMPT.format(
            current_phase=context.current_phase,
            current_element_name=context.current_element_name,
            pending_fields=pending_fields_str,
            last_agent_message=last_agent_msg[:200],  # Truncate for token budget
        )

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            message=message,
            has_images=str(has_images).lower(),
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        llm_response = await self._router.invoke(
            task_type=TaskType.CLASSIFICATION,
            messages=messages,
            temperature=0.1,   # Low temperature for deterministic classification
            max_tokens=150,    # Short response: JSON with intent + confidence + reasoning
        )

        if not llm_response.success or not llm_response.content:
            logger.warning(
                "intent_classifier_llm_failure",
                error=llm_response.error,
                model=llm_response.model,
            )
            return _keyword_fallback(message, has_images)

        return self._parse_llm_response(llm_response.content, message, has_images)

    def _parse_llm_response(
        self,
        raw: str,
        original_message: str,
        has_images: bool,
    ) -> IntentResult:
        """
        Parse and validate the LLM JSON response.

        Handles:
        - Malformed JSON (strip markdown fences, try again)
        - Unknown intent values (map to UNCLEAR)
        - Missing fields (use safe defaults)
        - Low confidence (force UNCLEAR)

        Never raises.
        """
        content = raw.strip()

        # Strip markdown code fences if present (some models wrap in ```json ... ```)
        if content.startswith("```"):
            lines = content.splitlines()
            # Drop first and last fence lines
            inner = [ln for ln in lines if not ln.startswith("```")]
            content = "\n".join(inner).strip()

        try:
            data: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON substring
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                except json.JSONDecodeError:
                    logger.warning(
                        "intent_classifier_json_parse_failure",
                        raw_preview=raw[:100],
                    )
                    return _keyword_fallback(original_message, has_images)
            else:
                logger.warning(
                    "intent_classifier_no_json_found",
                    raw_preview=raw[:100],
                )
                return _keyword_fallback(original_message, has_images)

        # Extract and validate fields
        raw_intent = data.get("intent", "")
        confidence = float(data.get("confidence", 0.0))
        reasoning = data.get("reasoning")

        # Map to enum (unknown value → UNCLEAR)
        try:
            intent = UserIntent(raw_intent)
        except ValueError:
            logger.warning(
                "intent_classifier_unknown_intent",
                raw_intent=raw_intent,
            )
            intent = UserIntent.UNCLEAR

        # Enforce minimum confidence threshold (REQ-INTENT-5 related: low-confidence
        # classifications trigger clarification, which is safer than a wrong action)
        if confidence < _MIN_CONFIDENCE:
            logger.debug(
                "intent_classifier_low_confidence",
                intent=intent.value,
                confidence=confidence,
                forced_to="unclear",
            )
            return IntentResult(
                intent=UserIntent.UNCLEAR,
                confidence=confidence,
                reasoning=f"Low confidence ({confidence:.2f}) on '{intent.value}'; forced to unclear",
                fallback_used=False,
            )

        return IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            fallback_used=False,
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_classifier_instance: IntentClassifier | None = None


@lru_cache(maxsize=1)
def _get_classifier_singleton() -> IntentClassifier:
    """
    Return a cached IntentClassifier instance.

    Uses lru_cache so import-time creation is deferred and settings are
    already loaded when first accessed.
    """
    return IntentClassifier()


def get_intent_classifier() -> IntentClassifier:
    """
    Get the singleton IntentClassifier instance.

    Thread-safe via Python's GIL; lru_cache ensures single instantiation.
    Gated at the call-site by EXPEDIENTE_V2_ENABLED — this function itself
    does not enforce the flag, so callers must check:

        if get_settings().EXPEDIENTE_V2_ENABLED:
            result = await get_intent_classifier().classify(...)
    """
    return _get_classifier_singleton()
