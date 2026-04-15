"""
MSI-a - Intent Router.

Classifies user messages into intents and suggests the appropriate mode.

Uses the local LLM (qwen2.5:3b via Hybrid LLM Router) for fast classification.
Falls back to keyword matching when LLM is unavailable.

Confidence threshold: 0.75
- >= 0.75 → route to suggested mode directly
- <  0.75 → route to PRE_EXPEDIENTE_MODE with clarification question
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
    PRESUPUESTO_DIRECTO = "presupuesto_directo"
    INICIAR_EXPEDIENTE = "iniciar_expediente"
    ESCALAR = "escalar"
    CONFIRMACION = "confirmacion"
    RECHAZO = "rechazo"
    CANCELAR = "cancelar"
    VER_IMAGENES = "ver_imagenes"  # ✅ NUEVO
    ABRIR_EXPEDIENTE = "abrir_expediente"  # ✅ NUEVO
    MODIFICAR_ELEMENTOS = "modificar_elementos"
    AMBIGUO = "ambiguo"


# Intent → default mode mapping
INTENT_TO_MODE: dict[UserIntent, str] = {
    UserIntent.CONSULTA_GENERAL: "PRE_EXPEDIENTE_MODE",
    UserIntent.PRESUPUESTO_DIRECTO: "PRE_EXPEDIENTE_MODE",
    UserIntent.INICIAR_EXPEDIENTE: "EXPEDIENTE_MODE",
    UserIntent.ESCALAR: "ESCALATION",
    UserIntent.CONFIRMACION: "",  # Context-dependent
    UserIntent.RECHAZO: "",  # Context-dependent
    UserIntent.CANCELAR: "",  # Reset handled in router node of conversation_graph.py
    UserIntent.VER_IMAGENES: "",  # Context-dependent (handled in PRE_EXPEDIENTE_MODE)
    UserIntent.ABRIR_EXPEDIENTE: "EXPEDIENTE_MODE",
    UserIntent.MODIFICAR_ELEMENTOS: "PRE_EXPEDIENTE_MODE",
    UserIntent.AMBIGUO: "PRE_EXPEDIENTE_MODE",
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
    # Presupuesto / Viabilidad (fusionados - TODO va a PRESUPUESTO ahora)
    # "Quiero homologar X" → PRESUPUESTO (precio inmediato)
    (
        re.compile(
            r"\b(quiero|necesito|tengo que|voy a|debo)\s+(homologar|legalizar)\b", re.I
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.90,
    ),
    # "Quiero modificar/cambiar X" → PRESUPUESTO
    (
        re.compile(
            r"\b(quiero|necesito|tengo que|voy a|debo)\s+(modificar|cambiar|instalar|poner|montar)\s+\w+",
            re.I,
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.85,
    ),
    # "Tengo una modificación en X" → PRESUPUESTO
    (
        re.compile(
            r"\b(tengo|hice|instalé|monté|puse)\s+.*(modificación|cambio|instalación)\s+(en|de|al)\b",
            re.I,
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.85,
    ),
    # "Modificar/cambiar el/la X" → PRESUPUESTO
    (
        re.compile(
            r"\b(modificar|cambiar|instalar|montar)\s+(el|la|los|las|un|una)\s+\w+",
            re.I,
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.80,
    ),
    # "Se puede homologar X" → PRESUPUESTO (ya no es solo "viabilidad")
    (
        re.compile(
            r"\b(se puede|es posible|está permitido|puedo homologar|es legal)\b", re.I
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.85,
    ),
    # Precio explícito → PRESUPUESTO
    (
        re.compile(
            r"\b(cuánto (cuesta|sale|vale)|precio|presupuesto|cotizar|cotización|tarifa)\b",
            re.I,
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.90,
    ),
    # Expediente
    (
        re.compile(r"\b(iniciar|empezar|abrir)\s*(expediente|caso|trámite)\b", re.I),
        UserIntent.INICIAR_EXPEDIENTE,
        0.90,
    ),
    # Escalación
    (
        re.compile(r"\b(persona|humano|agente|hablar con alguien|atención)\b", re.I),
        UserIntent.ESCALAR,
        0.95,
    ),
    # Confirmación
    (
        re.compile(
            r"^\s*(sí|si|ok|dale|vale|adelante|perfecto|claro|confirmo|venga)\s*[.!?]?\s*$",
            re.I,
        ),
        UserIntent.CONFIRMACION,
        0.90,
    ),
    # VER_IMAGENES: Ultra-short responses for "Option A"
    (
        re.compile(r"^\s*([Aa]|opci[oó]n\s*[Aa]|la\s*[Aa])\s*[.!?]?\s*$", re.I),
        UserIntent.VER_IMAGENES,
        0.95,
    ),
    # VER_IMAGENES: Natural language variants
    (
        re.compile(
            r"\b(ver|mostrar|enviar|quiero|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b",
            re.I,
        ),
        UserIntent.VER_IMAGENES,
        0.90,
    ),
    (
        re.compile(
            r"\b(s[ií],?\s*)?(mostr[aá]|env[ií]a|manda)\s+(las\s+)?(fotos?|im[aá]genes?)\b",
            re.I,
        ),
        UserIntent.VER_IMAGENES,
        0.90,
    ),
    # VER_IMAGENES: Imperativos con pronombres enclíticos (mostrame, enviame, etc.)
    (
        re.compile(
            r"\b(mostr[aá]me|env[ií]ame|mandame|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b",
            re.I,
        ),
        UserIntent.VER_IMAGENES,
        0.90,
    ),
    # ABRIR_EXPEDIENTE: Ultra-short responses for "Option B"
    (
        re.compile(r"^\s*([Bb]|opci[oó]n\s*[Bb]|la\s*[Bb])\s*[.!?]?\s*$", re.I),
        UserIntent.ABRIR_EXPEDIENTE,
        0.95,
    ),
    # Cancelar (reset conversation)
    (
        re.compile(
            r"\b(cancelar|cancela(r)?\s+todo|empezar\s+de\s+nuevo|reiniciar"
            r"|volver\s+al\s+inicio|olv[ií]da(lo|te)|borr[oó]n\s+y\s+cuenta\s+nueva)\b",
            re.I,
        ),
        UserIntent.CANCELAR,
        0.90,
    ),
    # Rechazo
    (
        re.compile(
            r"^\s*(no|nop|nope|mejor no|todavía no|ahora no)\s*[.!?]?\s*$", re.I
        ),
        UserIntent.RECHAZO,
        0.90,
    ),
    # Modificar elementos
    (
        re.compile(r"\b(también|agregar|añadir|sacar|quitar|eliminar|además)\b", re.I),
        UserIntent.MODIFICAR_ELEMENTOS,
        0.80,
    ),
    # Documentation query about a specific element → PRESUPUESTO (needs element tools)
    # e.g. "¿Qué documentación necesito para homologar mi placa solar?"
    # Must come BEFORE the broad CONSULTA_GENERAL catch (higher confidence wins)
    (
        re.compile(
            r"\b(qu[eé]\s+documentaci[oó]n|qu[eé]\s+documentos?|qu[eé]\s+fotos?|qu[eé]\s+requisitos?)"
            r"\s+(necesito|hay que|se requiere[n]?|hace\s+falta)\b",
            re.I,
        ),
        UserIntent.PRESUPUESTO_DIRECTO,
        0.85,
    ),
    # Consulta general (broad catch)
    (
        re.compile(
            r"\b(qué es|cómo funciona|para qué|qué necesito|cuánto tarda|es obligatorio)\b",
            re.I,
        ),
        UserIntent.CONSULTA_GENERAL,
        0.80,
    ),
]


# ---------------------------------------------------------------------------
# LLM classification prompt
# ---------------------------------------------------------------------------

CLASSIFICATION_SYSTEM_PROMPT = """\
Eres un clasificador de intenciones para un servicio de homologación de vehículos.

Clasifica el mensaje del usuario en UNA de estas categorías:
- CONSULTA_GENERAL: Preguntas informativas generales ("¿Qué es?", "¿Cómo funciona?", "¿Cuánto tarda?")
- PRESUPUESTO_DIRECTO: Quiere saber precio de homologación (pregunta viabilidad O pide precio O pregunta documentación de un elemento concreto)
  ("¿Se puede homologar escape?", "Quiero homologar suspensión", "¿Cuánto cuesta?", 
   "Precio de...", "Tengo un escape y...", "Necesito homologar X",
   "¿Qué documentación necesito para homologar X?", "¿Qué fotos/requisitos necesito para X?")
  
  IMPORTANTE: NO hay diferencia entre preguntar viabilidad, pedir precio, o preguntar documentación de un elemento.
  TODOS van a PRESUPUESTO_DIRECTO que calcula precio y documentación inmediatamente.
  Si el usuario pregunta qué documentación necesita para un elemento específico → PRESUPUESTO_DIRECTO.

- INICIAR_EXPEDIENTE: Quiere empezar el TRAMITE FORMAL con presupuesto ya calculado
  ("Iniciar expediente", "Empezar el trámite", "Abrir el caso", "Quiero arrancar")
  [SOLO si ya habló de precio antes]
- ESCALAR: Quiere hablar con humano ("Persona", "Agente", "Humano")
- CONFIRMACION: Respuesta afirmativa simple ("Sí", "ok", "dale")
- RECHAZO: Respuesta negativa simple ("No", "mejor no")
- CANCELAR: Quiere cancelar la conversación y empezar de nuevo ("cancelar", "cancela todo", "empezar de nuevo", "reiniciar", "volver al inicio", "olvídalo")
- VER_IMAGENES: Quiere ver fotos de ejemplo ("A", "Opción A", "ver fotos", "muestra las imágenes")
- ABRIR_EXPEDIENTE: Quiere abrir expediente directamente ("B", "Opción B", "abrir expediente")
- MODIFICAR_ELEMENTOS: Quiere agregar/quitar elementos ("también quiero", "quita el...")
- AMBIGUO: No claro

Usa el CONTEXTO RECIENTE (si existe) para desambiguar respuestas cortas como "sí", "A", "B".

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
        mode_context: dict[str, Any] | None = None,
    ) -> IntentResult:
        """
        Classify the user's intent.

        Args:
            message: Raw user message text.
            current_mode: Current conversation mode (for context).
            history: Recent conversation history (optional, last 6 messages).
            mode_context: Extracted context hints for keyword validation (optional).
                Expected keys: precio_comunicado, tarifa_calculada.

        Returns:
            IntentResult with intent, confidence, and suggested mode.
        """
        # 1. Try keyword matching (fast path)
        keyword_result = self._classify_keywords(message)
        if keyword_result and keyword_result.confidence >= CONFIDENCE_THRESHOLD:
            # Validate against mode context if provided (Phase 2)
            if mode_context is not None:
                adjusted = self._validate_keyword_with_context(
                    keyword_result.intent,
                    keyword_result.confidence,
                    mode_context,
                )
                if adjusted < CONFIDENCE_THRESHOLD:
                    logger.info(
                        "keyword_downgraded_by_context",
                        intent=keyword_result.intent.value,
                        original_confidence=keyword_result.confidence,
                        adjusted_confidence=adjusted,
                        context_hints=mode_context,
                    )
                    # Fall through to LLM path — don't return here
                    keyword_result = IntentResult(
                        intent=keyword_result.intent,
                        confidence=adjusted,
                        suggested_mode=keyword_result.suggested_mode,
                    )
                else:
                    logger.debug(
                        "intent_classified_keywords",
                        intent=keyword_result.intent.value,
                        confidence=keyword_result.confidence,
                    )
                    return keyword_result
            else:
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
            suggested_mode="PRE_EXPEDIENTE_MODE",
            clarification_question=(
                "¿Buscas información general, evaluar si algo se puede "
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
                    mode = INTENT_TO_MODE.get(intent, "PRE_EXPEDIENTE_MODE")
                    best_match = IntentResult(
                        intent=intent,
                        confidence=confidence,
                        suggested_mode=mode,
                    )

        return best_match

    # -- Context-aware keyword validation --------------------------------

    def _validate_keyword_with_context(
        self,
        intent: UserIntent,
        confidence: float,
        context_hints: dict[str, Any] | None,
    ) -> float:
        """
        Downgrade keyword confidence if mode_context contradicts the match.

        Only applies to ambiguous intents that depend on conversation state:
        - CONFIRMACION: valid only when there is something to confirm

        Note: VER_IMAGENES and ABRIR_EXPEDIENTE (A/B option keywords) are no longer
        downgraded here. The `waiting_for_image_choice` flag was never set to True
        by any code path, causing permanent suppression of these valid intents.
        The dead downgrade blocks were removed per Spec 4 / AD-2.

        Returns original confidence if consistent, or 0.50 (below CONFIDENCE_THRESHOLD)
        if contradicted. Never makes external calls — only dict lookups.
        """
        if not context_hints:
            return confidence  # No context → trust keyword as-is

        DOWNGRADE = 0.50  # Below CONFIDENCE_THRESHOLD (0.75) → falls to LLM

        if intent == UserIntent.CONFIRMACION:
            # "sí" as confirmation only valid if there's something to confirm
            # (tarifa calculated = presupuesto flow active, or price already communicated)
            if not context_hints.get("precio_comunicado") and not context_hints.get(
                "tarifa_calculada"
            ):
                return DOWNGRADE

        return confidence  # Context consistent → keep original confidence

    # -- History formatting ----------------------------------------------

    @staticmethod
    def _format_history_context(
        history: list[dict[str, Any]],
        max_chars: int = 500,
    ) -> str:
        """
        Format recent history as compact context block for classification prompt.

        Skips tool messages (noise for classification). Prefixes with U:/A:.
        Truncates each message to 120 chars, hard-caps total at max_chars.

        Returns empty string for empty/None history (no regression when unused).
        """
        if not history:
            return ""

        lines: list[str] = []
        for msg in history:
            # Duck-type: BaseMessage uses .type/.content, dicts use ["role"]/["content"]
            msg_type = getattr(msg, "type", None)
            if msg_type is not None:
                role = {"human": "user", "ai": "assistant"}.get(msg_type, msg_type)
                content = str(getattr(msg, "content", ""))
            else:
                role = msg.get("role", "")
                content = msg.get("content", "")
            if role == "tool":
                continue  # Skip tool results — noise for classification
            prefix = "U" if role == "user" else "A"
            # Strip security tags from user messages
            clean = (
                content.replace("<USER_MESSAGE>", "")
                .replace("</USER_MESSAGE>", "")
                .strip()
            )
            # Take first 120 chars per message to avoid one long message dominating
            lines.append(f"{prefix}: {clean[:120]}")

        block = "\n".join(lines)
        # Hard cap at max_chars
        if len(block) > max_chars:
            block = block[:max_chars] + "..."
        return block

    # -- LLM classification ----------------------------------------------

    async def _classify_llm(
        self,
        message: str,
        current_mode: str,
        history: list[dict[str, Any]],
    ) -> IntentResult | None:
        """Classify using local LLM (qwen2.5:3b).

        When history is non-empty, injects a CONTEXTO RECIENTE block (≤500 chars)
        between MODO ACTUAL and MENSAJE to help the LLM disambiguate short replies.
        Empty history → prompt identical to current behavior (no regression).
        """
        try:
            if self._llm_router is None:
                self._llm_router = get_llm_router()

            context_block = self._format_history_context(history)
            parts = [f"MODO ACTUAL: {current_mode}"]
            if context_block:
                parts.append(f"CONTEXTO RECIENTE:\n{context_block}")
            parts.append(f"MENSAJE: {message}")
            user_prompt = "\n".join(parts)

            response = await self._llm_router.invoke(
                task_type=TaskType.CLASSIFICATION,
                messages=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            return self._parse_llm_response(response.content)

        except Exception as e:
            logger.warning("intent_llm_classification_failed", error=str(e))
            return None

    def _parse_llm_response(self, response: str | Any) -> IntentResult | None:
        """Parse JSON response from LLM."""
        try:
            # Ensure response is a string
            if not isinstance(response, str):
                # Handle LLMResponse objects
                if hasattr(response, "content"):
                    response_str = str(response.content)
                elif hasattr(response, "text"):
                    response_str = str(response.text)
                else:
                    # Last resort: stringify
                    response_str = str(response)
                    logger.warning(
                        "intent_llm_response_type_unexpected",
                        response_type=type(response).__name__,
                    )
            else:
                response_str = response

            # Clean response (remove markdown fences if present)
            clean = response_str.strip()
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
            mode = INTENT_TO_MODE.get(intent, "PRE_EXPEDIENTE_MODE")

            clarification = None
            if confidence < CONFIDENCE_THRESHOLD:
                clarification = (
                    "¿Buscas información general, evaluar si algo se puede "
                    "homologar, o un presupuesto específico?"
                )
                mode = "PRE_EXPEDIENTE_MODE"

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
