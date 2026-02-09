"""
MSI-a - Fallback Handler.

Centralised error recovery for all conversation modes.

Design: "The node decides" - each mode has its own retry policy,
but the handler logic is shared.

Key decisions:
- retry_count is per-mode (resets on mode change via transition_mode)
- consecutive_errors resets on any successful interaction
- action_on_limit is mode-specific (escalate, reset, offer help)
- Reprompt messages are progressive (1st gentle, 2nd clearer, 3rd limit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any

import structlog

from agent.state.conversation_state import (
    ConversationState,
    RetryStateData,
    create_empty_retry_state,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FallbackAction(str, Enum):
    """Actions available when retry limit is reached."""

    RESET_TO_MODE_START = "reset_to_mode_start"
    RESET_TO_CONSULTA = "reset_to_consulta"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    OFFER_HUMAN_HELP = "offer_human_help"
    SAVE_DRAFT_AND_EXIT = "save_draft_and_exit"


class RetryErrorType(str, Enum):
    """Types of errors that trigger retry counting."""

    INTENT_NOT_UNDERSTOOD = "intent_not_understood"
    TOOL_CALL_FAILED = "tool_call_failed"
    VALIDATION_ERROR = "validation_error"
    LLM_PARSE_ERROR = "llm_parse_error"
    USER_CONFUSION = "user_confusion"


# ---------------------------------------------------------------------------
# Retry policies per mode
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """
    Immutable retry policy for a conversation mode.

    Each mode defines how many errors it tolerates and what to do when
    the limit is reached.
    """

    mode: str
    max_retries: int = 3
    action_on_limit: FallbackAction = FallbackAction.ESCALATE_TO_HUMAN
    reprompt_strategy: str = "progressive"  # "progressive" | "simplify" | "same"
    reset_on_success: bool = True

    # Custom messages (None = auto-generate)
    msg_retry_1: str | None = None
    msg_retry_2: str | None = None
    msg_limit: str | None = None


DEFAULT_POLICIES: dict[str, RetryPolicy] = {
    "CONSULTA_MODE": RetryPolicy(
        mode="CONSULTA_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.OFFER_HUMAN_HELP,
        msg_retry_1="Perdón, no entendí bien. ¿Podés reformular tu pregunta?",
        msg_retry_2=(
            "No estoy entendiendo bien. ¿Podés ser más específico sobre "
            "qué Quieres saber de homologación?"
        ),
        msg_limit=(
            "Parece que estamos teniendo dificultades. "
            "¿Preferís hablar con una persona?"
        ),
    ),
    "PRESUPUESTO_MODE": RetryPolicy(
        mode="PRESUPUESTO_MODE",
        max_retries=4,  # Aumentado de 3 a 4 (ahora maneja más tráfico)
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="simplify",
        msg_retry_1="No entendí bien. ¿Quieres agregar algo al presupuesto, o tenés dudas?",
        msg_retry_2="¿Quieres que te muestre el presupuesto actual?",
        msg_limit=(
            "Este caso parece complejo. Te voy a conectar con un "
            "especialista que te puede ayudar mejor."
        ),
    ),
    "EVALUACION_GATEWAY": RetryPolicy(
        mode="EVALUACION_GATEWAY",
        max_retries=2,
        action_on_limit=FallbackAction.RESET_TO_MODE_START,
        reprompt_strategy="same",
        msg_retry_1="Necesito que me respondas sí o no: ¿Quieres iniciar el expediente?",
        msg_limit="Te devuelvo al presupuesto para que lo revises con calma.",
    ),
    "EXPEDIENTE_MODE": RetryPolicy(
        mode="EXPEDIENTE_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.OFFER_HUMAN_HELP,
        msg_retry_1="No entendí bien lo que me pasaste. ¿Podés intentar de nuevo?",
        msg_retry_2="Parece que hay un problema con el formato. ¿Necesitás ayuda?",
        msg_limit="¿Quieres que te conecte con alguien que te guíe paso a paso?",
    ),
}


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class FallbackHandler:
    """
    Stateless fallback handler.

    All mutable state lives in ``RetryStateData`` inside the conversation
    state; this class only provides pure functions to read/update it.
    """

    def __init__(self, policies: dict[str, RetryPolicy] | None = None) -> None:
        self.policies = policies or DEFAULT_POLICIES

    # -- Policy lookup ---------------------------------------------------

    def get_policy(self, mode: str) -> RetryPolicy:
        """Return the retry policy for *mode*, defaulting to CONSULTA."""
        return self.policies.get(mode, DEFAULT_POLICIES["CONSULTA_MODE"])

    # -- Record events ---------------------------------------------------

    def record_error(
        self,
        retry_state: RetryStateData,
        error_type: RetryErrorType,
        error_message: str,
    ) -> RetryStateData:
        """Increment counters after an error. Returns **new** dict."""
        now = datetime.now(UTC).isoformat()
        return RetryStateData(
            retry_count=retry_state.get("retry_count", 0) + 1,
            consecutive_errors=retry_state.get("consecutive_errors", 0) + 1,
            last_error_type=error_type.value,
            last_error_message=error_message,
            first_error_at=retry_state.get("first_error_at") or now,
            last_retry_at=now,
        )

    def record_validation_error(
        self,
        retry_state: RetryStateData,
        tool_name: str,
        validation_errors: list[str],
        validation_layer: str,
    ) -> RetryStateData:
        """
        Record a validation error with context (Phase 3).
        
        This is a specialized version of record_error() that includes
        validation-specific metadata for better reprompting.
        
        Args:
            retry_state: Current retry state
            tool_name: Name of the tool that failed validation
            validation_errors: List of validation error messages
            validation_layer: Which layer failed ("syntax", "state", "semantic")
        
        Returns:
            New retry state with incremented counters and validation context
        """
        now = datetime.now(UTC).isoformat()
        
        error_message = (
            f"Validation failed in {validation_layer} layer for {tool_name}: "
            f"{'; '.join(validation_errors)}"
        )
        
        return RetryStateData(
            retry_count=retry_state.get("retry_count", 0) + 1,
            consecutive_errors=retry_state.get("consecutive_errors", 0) + 1,
            last_error_type=RetryErrorType.VALIDATION_ERROR.value,
            last_error_message=error_message,
            first_error_at=retry_state.get("first_error_at") or now,
            last_retry_at=now,
            last_validation_context={
                "tool_name": tool_name,
                "errors": validation_errors,
                "layer": validation_layer,
            },
        )

    def record_success(
        self,
        retry_state: RetryStateData,
        policy: RetryPolicy,
    ) -> RetryStateData:
        """Reset consecutive counter after a successful turn."""
        if policy.reset_on_success and retry_state.get("consecutive_errors", 0) > 0:
            return RetryStateData(
                retry_count=retry_state.get("retry_count", 0),
                consecutive_errors=0,
                last_error_type=retry_state.get("last_error_type"),
                last_error_message=retry_state.get("last_error_message"),
                first_error_at=retry_state.get("first_error_at"),
                last_retry_at=retry_state.get("last_retry_at"),
                last_validation_context=retry_state.get("last_validation_context"),
            )
        return retry_state

    # -- Decision helpers ------------------------------------------------

    def should_fallback(
        self,
        retry_state: RetryStateData,
        policy: RetryPolicy,
    ) -> bool:
        """True when the retry limit has been reached."""
        return retry_state.get("retry_count", 0) >= policy.max_retries

    def get_reprompt(
        self,
        retry_state: RetryStateData,
        policy: RetryPolicy,
    ) -> str:
        """Return the appropriate reprompt message for the current retry."""
        count = retry_state.get("retry_count", 0)

        if count == 1 and policy.msg_retry_1:
            return policy.msg_retry_1
        if count == 2 and policy.msg_retry_2:
            return policy.msg_retry_2
        if count >= policy.max_retries and policy.msg_limit:
            return policy.msg_limit

        # Auto-generated fallback
        if policy.reprompt_strategy == "simplify":
            return self._simplify_message(policy)
        if policy.reprompt_strategy == "same":
            return policy.msg_retry_1 or "¿Podés repetir eso?"
        return self._progressive_message(count, policy)

    def get_validation_reprompt(
        self,
        retry_state: RetryStateData,
        policy: RetryPolicy,
    ) -> str:
        """
        Generate reprompt message for validation errors (Phase 3).
        
        Uses validation context from last error to provide specific guidance.
        Progressive strategy: generic → specific → escalate.
        
        Args:
            retry_state: Current retry state with validation context
            policy: Retry policy for the current mode
        
        Returns:
            Reprompt message in Spanish for the LLM
        """
        count = retry_state.get("retry_count", 0)
        context = retry_state.get("last_validation_context", {})
        
        # First retry: generic message
        if count == 1:
            return (
                "Los parámetros que enviaste no son válidos. "
                "Por favor, revisa e intenta de nuevo."
            )
        
        # Second retry: specific message with error details
        if count == 2 and context:
            tool = context.get("tool_name", "la herramienta")
            errors = context.get("errors", [])
            
            if errors:
                error_list = "\n".join(f"- {err}" for err in errors)
                return (
                    f"Hay un problema con los parámetros de {tool}:\n"
                    f"{error_list}\n\n"
                    "Por favor, corrige estos errores."
                )
        
        # Third+ retry: escalate
        if count >= policy.max_retries:
            return (
                "No pude procesar la solicitud después de varios intentos. "
                "Te voy a conectar con un humano que te puede ayudar mejor."
            )
        
        # Fallback (shouldn't reach here normally)
        return "Por favor, intenta de nuevo con parámetros correctos."

    # -- Execute fallback action -----------------------------------------

    def execute_fallback(
        self,
        policy: RetryPolicy,
        state: ConversationState,
        retry_state: RetryStateData,
    ) -> dict[str, Any]:
        """
        Build a state-update dict for the fallback action.

        Returns a dict ready to be merged into the graph state.
        Keys: ai_response, current_mode (optional), escalation_triggered, etc.
        """
        action = policy.action_on_limit

        logger.warning(
            "fallback_triggered",
            action=action.value,
            mode=state.get("current_mode"),
            retry_count=retry_state.get("retry_count"),
        )

        if action == FallbackAction.RESET_TO_MODE_START:
            return {
                "ai_response": (
                    "Empecemos de nuevo. "
                    + self._mode_welcome(state.get("current_mode", "CONSULTA_MODE"))
                ),
                "retry_state": create_empty_retry_state(),
                "mode_context": {},  # Clear current mode context
            }

        if action == FallbackAction.RESET_TO_CONSULTA:
            return {
                "ai_response": (
                    "Parece que nos trabamos. Volvamos a empezar. "
                    "¿Qué Quieres saber sobre homologación?"
                ),
                "current_mode": "CONSULTA_MODE",
                "previous_mode": state.get("current_mode"),
                "retry_state": create_empty_retry_state(),
                "mode_context": {},
            }

        if action == FallbackAction.ESCALATE_TO_HUMAN:
            return {
                "ai_response": (
                    "Te voy a conectar con un especialista que te puede "
                    "ayudar mejor. Aguardá un momento..."
                ),
                "current_mode": "ESCALATION",
                "escalation_triggered": True,
                "escalation_reason": (
                    f"retry_limit_{retry_state.get('retry_count', 0)}"
                ),
                "retry_state": create_empty_retry_state(),
            }

        if action == FallbackAction.OFFER_HUMAN_HELP:
            return {
                "ai_response": (
                    "¿Preferís que te conecte con una persona para ayudarte? "
                    "Respondé SÍ si Quieres, o contame qué necesitás."
                ),
                "pending_human_decision": True,
                "retry_state": create_empty_retry_state(),
            }

        if action == FallbackAction.SAVE_DRAFT_AND_EXIT:
            return {
                "ai_response": (
                    "Guardé tu progreso como borrador. "
                    "Podés volver cuando quieras. ¿Te puedo ayudar con algo más?"
                ),
                "current_mode": "CONSULTA_MODE",
                "draft_quote": state.get("mode_context", {}).get("tarifa_calculada"),
                "retry_state": create_empty_retry_state(),
                "mode_context": {},
            }

        # Should never reach here
        return {"ai_response": "Ha ocurrido un error. ¿Podés repetir?"}

    # -- Internal helpers ------------------------------------------------

    @staticmethod
    def _progressive_message(count: int, policy: RetryPolicy) -> str:
        if count <= 1:
            return "No entendí bien. ¿Podés ser más específico?"
        return (
            "¿Buscás información general sobre homologaciones, "
            "o querés un presupuesto para un elemento específico?"
        )

    @staticmethod
    def _simplify_message(policy: RetryPolicy) -> str:
        if policy.mode == "PRESUPUESTO_MODE":
            return (
                "Te resumo las opciones:\n"
                "1. Ver presupuesto actual\n"
                "2. Agregar/quitar elementos\n"
                "3. Ver fotos de ejemplo\n"
                "4. Abrir expediente\n"
                "5. Hablar con una persona\n\n"
                "¿Cuál preferís?"
            )
        return "¿Preferís hablar con una persona? Respondé: SÍ o NO"

    @staticmethod
    def _mode_welcome(mode: str) -> str:
        return {
            "CONSULTA_MODE": "¿Qué Quieres saber sobre homologación?",
            "PRESUPUESTO_MODE": "¿Qué elementos Quieres homologar?",
            "EXPEDIENTE_MODE": "¿Con qué dato empezamos?",
        }.get(mode, "¿En qué te puedo ayudar?")

    # -- Error classification --------------------------------------------

    @staticmethod
    def classify_error(error: Exception) -> RetryErrorType:
        """Heuristic classification of an exception."""
        msg = str(error).lower()
        name = type(error).__name__.lower()

        if "tool" in name or "invocation" in msg:
            return RetryErrorType.TOOL_CALL_FAILED
        if "validation" in name or "invalid" in msg:
            return RetryErrorType.VALIDATION_ERROR
        if "parse" in name or "json" in msg:
            return RetryErrorType.LLM_PARSE_ERROR
        if "understand" in msg or "intent" in msg:
            return RetryErrorType.INTENT_NOT_UNDERSTOOD
        return RetryErrorType.USER_CONFUSION


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_handler: FallbackHandler | None = None


def get_fallback_handler() -> FallbackHandler:
    global _handler
    if _handler is None:
        _handler = FallbackHandler()
    return _handler
