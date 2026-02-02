"""
MSI-a - Intent Router.

Classifies user messages into intents and suggests the appropriate mode.

Uses the local LLM (qwen2.5:3b via Hybrid LLM Router) for fast classification.
Falls back to keyword matching when LLM is unavailable.

Confidence threshold: 0.75
- >= 0.75 → route to suggested mode directly
- <  0.75 → route to CONSULTA_MODE with clarification question
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from shared.llm_router import TaskType, get_llm_router

logger = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

class UserIntent(str, Enum):
    """Possible user intents."""

    CONSULTA_GENERAL = "consulta_general"
    EVALUAR_VIABILIDAD = "evaluar_viabilidad"
    PRESUPUESTO_DIRECTO = "presupuesto_directo"
    INICIAR_EXPEDIENTE = "iniciar_expediente"
    ESCALAR = "escalar"
    CONFIRMACION = "confirmacion"
    RECHAZO = "rechazo"
    MODIFICAR_ELEMENTOS = "modificar_elementos"
    AMBIGUO = "ambiguo"


# Intent → default mode mapping
INTENT_TO_MODE: dict[UserIntent, str] = {
    UserIntent.CONSULTA_GENERAL: "CONSULTA_MODE",
    UserIntent.EVALUAR_VIABILIDAD: "VIABILIDAD_MODE",
    UserIntent.PRESUPUESTO_DIRECTO: "PRESUPUESTO_MODE",
    UserIntent.INICIAR_EXPEDIENTE: "EVALUACION_GATEWAY",
    UserIntent.ESCALAR: "ESCALATION",
    UserIntent.CONFIRMACION: "",   # Context-dependent
    UserIntent.RECHAZO: "",        # Context-dependent
    UserIntent.MODIFICAR_ELEMENTOS: "PRESUPUESTO_MODE",
    UserIntent.AMBIGUO: "CONSULTA_MODE",
}


@dataclass
class IntentResult:
    """Result of intent classification."""

    intent: UserIntent
    confidence: float
    suggested_mode: str
    entities: dict[str, Any] = field(default_factory=dict)
    clarification_question: str | None = None


# ---------------------------------------------------------------------------
# Keyword patterns (fast fallback, no LLM needed)
# ---------------------------------------------------------------------------

_KEYWORD_PATTERNS: list[tuple[re.Pattern[str], UserIntent, float]] = [
    # Viabilidad
    (re.compile(r"\b(se puede|es posible|está permitido|puedo homologar|es legal)\b", re.I),
     UserIntent.EVALUAR_VIABILIDAD, 0.85),

    # Presupuesto
    (re.compile(r"\b(cuánto (cuesta|sale|vale)|precio|presupuesto|cotizar|cotización)\b", re.I),
     UserIntent.PRESUPUESTO_DIRECTO, 0.85),

    # Expediente
    (re.compile(r"\b(iniciar|empezar|abrir)\s*(expediente|caso|trámite)\b", re.I),
     UserIntent.INICIAR_EXPEDIENTE, 0.90),

    # Escalación
    (re.compile(r"\b(persona|humano|agente|hablar con alguien|atención)\b", re.I),
     UserIntent.ESCALAR, 0.95),

    # Confirmación
    (re.compile(r"^\s*(sí|si|ok|dale|vale|adelante|perfecto|claro|confirmo|venga)\s*[.!?]?\s*$", re.I),
     UserIntent.CONFIRMACION, 0.90),

    # Rechazo
    (re.compile(r"^\s*(no|nop|nope|mejor no|todavía no|ahora no|cancelar)\s*[.!?]?\s*$", re.I),
     UserIntent.RECHAZO, 0.90),

    # Modificar elementos
    (re.compile(r"\b(también|agregar|añadir|sacar|quitar|eliminar|además)\b", re.I),
     UserIntent.MODIFICAR_ELEMENTOS, 0.80),

    # Consulta general (broad catch)
    (re.compile(r"\b(qué es|cómo funciona|para qué|qué necesito|cuánto tarda|es obligatorio)\b", re.I),
     UserIntent.CONSULTA_GENERAL, 0.80),
]


# ---------------------------------------------------------------------------
# LLM classification prompt
# ---------------------------------------------------------------------------

CLASSIFICATION_SYSTEM_PROMPT = """\
Eres un clasificador de intenciones para un servicio de homologación de vehículos.

Clasifica el mensaje del usuario en UNA de estas categorías:
- CONSULTA_GENERAL: Preguntas informativas ("¿Qué es?", "¿Cómo funciona?", "¿Cuánto tarda?")
- EVALUAR_VIABILIDAD: Pregunta si algo se puede homologar ("¿Se puede?", "¿Es posible?", "¿Es legal?")
- PRESUPUESTO_DIRECTO: Solicitud de precio ("¿Cuánto cuesta?", "Precio de...", "Presupuesto para...")
- INICIAR_EXPEDIENTE: Quiere empezar formalmente ("Quiero empezar", "Iniciar expediente")
- ESCALAR: Quiere hablar con humano ("Persona", "Agente", "Humano")
- CONFIRMACION: Respuesta afirmativa simple ("Sí", "ok", "dale")
- RECHAZO: Respuesta negativa simple ("No", "mejor no")
- MODIFICAR_ELEMENTOS: Quiere agregar/quitar elementos ("también quiero", "sacá el...")
- AMBIGUO: No claro

Responde SOLO con JSON, sin markdown:
{"intent": "...", "confidence": 0.85, "entities": {"elemento": "...", "vehiculo": "..."}}
"""


# ---------------------------------------------------------------------------
# Router class
# ---------------------------------------------------------------------------

class IntentRouter:
    """
    Classify user messages and suggest conversation modes.

    Strategy:
    1. Try keyword matching first (instant, no LLM cost).
    2. If no strong match, use LLM classification (qwen2.5:3b local).
    3. If LLM fails, return AMBIGUO with low confidence.
    """

    def __init__(self) -> None:
        self._llm_router = None  # Lazy init

    async def classify(
        self,
        message: str,
        current_mode: str = "START",
        history: list[dict[str, Any]] | None = None,
    ) -> IntentResult:
        """
        Classify the user's intent.

        Args:
            message: Raw user message text.
            current_mode: Current conversation mode (for context).
            history: Recent conversation history (optional).

        Returns:
            IntentResult with intent, confidence, and suggested mode.
        """
        # 1. Try keyword matching (fast path)
        keyword_result = self._classify_keywords(message)
        if keyword_result and keyword_result.confidence >= CONFIDENCE_THRESHOLD:
            logger.debug(
                "intent_classified_keywords",
                intent=keyword_result.intent.value,
                confidence=keyword_result.confidence,
            )
            return keyword_result

        # 2. Try LLM classification
        llm_result = await self._classify_llm(message, current_mode, history or [])
        if llm_result:
            logger.info(
                "intent_classified_llm",
                intent=llm_result.intent.value,
                confidence=llm_result.confidence,
            )
            return llm_result

        # 3. Fallback: use keyword result if available, or AMBIGUO
        if keyword_result:
            return keyword_result

        return IntentResult(
            intent=UserIntent.AMBIGUO,
            confidence=0.3,
            suggested_mode="CONSULTA_MODE",
            clarification_question=(
                "¿Buscás información general, evaluar si algo se puede "
                "homologar, o un presupuesto específico?"
            ),
        )

    # -- Keyword matching ------------------------------------------------

    def _classify_keywords(self, message: str) -> IntentResult | None:
        """Fast keyword-based classification."""
        best_match: IntentResult | None = None
        best_confidence = 0.0

        for pattern, intent, confidence in _KEYWORD_PATTERNS:
            if pattern.search(message):
                if confidence > best_confidence:
                    best_confidence = confidence
                    mode = INTENT_TO_MODE.get(intent, "CONSULTA_MODE")
                    best_match = IntentResult(
                        intent=intent,
                        confidence=confidence,
                        suggested_mode=mode,
                    )

        return best_match

    # -- LLM classification ----------------------------------------------

    async def _classify_llm(
        self,
        message: str,
        current_mode: str,
        history: list[dict[str, Any]],
    ) -> IntentResult | None:
        """Classify using local LLM (qwen2.5:3b)."""
        try:
            if self._llm_router is None:
                self._llm_router = get_llm_router()

            user_prompt = (
                f"MODO ACTUAL: {current_mode}\n"
                f"MENSAJE: {message}"
            )

            response = await self._llm_router.invoke(
                task_type=TaskType.CLASSIFICATION,
                messages=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            return self._parse_llm_response(response)

        except Exception as e:
            logger.warning("intent_llm_classification_failed", error=str(e))
            return None

    def _parse_llm_response(self, response: str) -> IntentResult | None:
        """Parse JSON response from LLM."""
        try:
            # Clean response (remove markdown fences if present)
            clean = response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"```\w*\n?", "", clean).strip()

            data = json.loads(clean)

            intent_str = data.get("intent", "AMBIGUO").upper()

            # Map string to enum
            try:
                intent = UserIntent(intent_str.lower())
            except ValueError:
                intent = UserIntent.AMBIGUO

            confidence = float(data.get("confidence", 0.5))
            entities = data.get("entities", {})
            mode = INTENT_TO_MODE.get(intent, "CONSULTA_MODE")

            clarification = None
            if confidence < CONFIDENCE_THRESHOLD:
                clarification = (
                    "¿Buscás información general, evaluar si algo se puede "
                    "homologar, o un presupuesto específico?"
                )
                mode = "CONSULTA_MODE"

            return IntentResult(
                intent=intent,
                confidence=confidence,
                suggested_mode=mode,
                entities=entities,
                clarification_question=clarification,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("intent_llm_parse_failed", error=str(e))
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: IntentRouter | None = None


def get_intent_router() -> IntentRouter:
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router
