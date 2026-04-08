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
    transition_mode,
)
from langgraph.types import Overwrite

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_category_not_found_error(error_dict: dict) -> bool:
    """Return True when error_dict signals a category_not_found from element_tools."""
    if not isinstance(error_dict, dict):
        return False
    return (
        error_dict.get("error") == "category_not_found"
        and "available_categories" in error_dict
    )


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
        msg_retry_1="Perdona, no te he entendido bien. ¿Puedes reformular tu pregunta?",
        msg_retry_2=(
            "No te estoy entendiendo bien. ¿Puedes ser más específico sobre "
            "qué quieres saber de homologación?"
        ),
        msg_limit=(
            "Parece que estamos teniendo dificultades. "
            "¿Prefieres hablar con una persona?"
        ),
    ),
    "PRESUPUESTO_MODE": RetryPolicy(
        mode="PRESUPUESTO_MODE",
        max_retries=4,  # Aumentado de 3 a 4 (ahora maneja más tráfico)
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="simplify",
        msg_retry_1="No te he entendido bien. ¿Quieres agregar algo al presupuesto, o tienes dudas?",
        msg_retry_2="¿Quieres que te muestre el presupuesto actual?",
        msg_limit=(
            "Este caso parece complejo. Te voy a conectar con un "
            "especialista que te puede ayudar mejor."
        ),
    ),
    "EXPEDIENTE_MODE": RetryPolicy(
        mode="EXPEDIENTE_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.OFFER_HUMAN_HELP,
        msg_retry_1="No te he entendido bien. ¿Puedes intentarlo de nuevo?",
        msg_retry_2="Parece que hay un problema con el formato. ¿Necesitas ayuda?",
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
            return policy.msg_retry_1 or "¿Puedes repetir eso?"
        return self._progressive_message(count, policy)

    def get_validation_reprompt(
        self,
        retry_state: RetryStateData,
        policy: RetryPolicy,
        error_dict: dict | None = None,
    ) -> str:
        """
        Generate reprompt message for validation errors (Phase 3).
        
        Uses validation context from last error to provide specific guidance.
        Progressive strategy: generic → specific → escalate.
        
        Args:
            retry_state: Current retry state with validation context
            policy: Retry policy for the current mode
            error_dict: Optional error dict from the tool result. When present
                and it signals a category_not_found error (S3), an actionable
                message with the available category slugs is returned immediately.
        
        Returns:
            Reprompt message in Spanish for the LLM
        """
        # S3: Category-not-found — give the LLM an actionable message with available slugs
        if error_dict and _is_category_not_found_error(error_dict):
            available = error_dict.get("available_categories", [])
            slug_used = error_dict.get("categoria_usada", "desconocida")
            if available:
                cats_text = ", ".join(
                    f"{c['slug']} ({c['name']})" for c in available[:6]
                )
                return (
                    f"La categoría '{slug_used}' no existe en el sistema. "
                    f"Categorías disponibles: {cats_text}. "
                    f"Elige la categoría correcta y vuelve a llamar a identificar_y_resolver_elementos(). "
                    f"Si no estás seguro, usa listar_categorias() primero."
                )
            return (
                f"La categoría '{slug_used}' no existe. "
                f"Usa listar_categorias() para ver las categorías disponibles, "
                f"luego elige la correcta y reintenta."
            )

        count = retry_state.get("retry_count", 0)
        context = retry_state.get("last_validation_context", {})
        
        # First retry: generic message
        if count == 1:
            return (
                "Los parámetros que has enviado no son válidos. "
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
                "mode_context": Overwrite({}),  # Actually clears (bypasses merge_dicts)
            }

        if action == FallbackAction.RESET_TO_CONSULTA:
            updates = transition_mode(state, "CONSULTA_MODE")
            updates["ai_response"] = (
                "Parece que nos hemos trabado. Volvamos a empezar. "
                "¿Qué quieres saber sobre homologación?"
            )
            return updates

        if action == FallbackAction.ESCALATE_TO_HUMAN:
            return {
                "ai_response": (
                    "Te voy a conectar con un especialista que te puede "
                    "ayudar mejor. Espera un momento..."
                ),
                "current_mode": "ESCALATION",
                "escalation_triggered": True,
                "escalation_reason": (
                    f"retry_limit_{retry_state.get('retry_count', 0)}"
                ),
                "retry_state": create_empty_retry_state(),
            }

        if action == FallbackAction.OFFER_HUMAN_HELP:
            offer_message = (
                "¿Prefieres que te conecte con una persona para ayudarte? "
                "Responde SÍ si quieres, o cuéntame qué necesitas."
            )

            # EXPEDIENTE_MODE: enrich with field context when available
            if state.get("current_mode") == "EXPEDIENTE_MODE":
                last_ctx = retry_state.get("last_validation_context")
                if isinstance(last_ctx, dict) and last_ctx.get("field_label"):
                    field_label = last_ctx["field_label"]
                    offer_message = (
                        f"Parece que tienes dificultades con el campo '{field_label}'. "
                        "¿Prefieres que te conecte con una persona que te guíe paso a paso? "
                        "Responde SÍ si quieres, o intenta de nuevo."
                    )

            return {
                "ai_response": offer_message,
                "pending_human_decision": True,
                "retry_state": create_empty_retry_state(),
            }

        if action == FallbackAction.SAVE_DRAFT_AND_EXIT:
            updates = transition_mode(state, "CONSULTA_MODE")
            updates["ai_response"] = (
                "He guardado tu progreso como borrador. "
                "Puedes volver cuando quieras. ¿Te puedo ayudar con algo más?"
            )
            updates["draft_quote"] = state.get("mode_context", {}).get("tarifa_calculada")
            return updates

        # Should never reach here
        return {"ai_response": "Ha ocurrido un error. ¿Puedes repetirlo?"}

    # -- Internal helpers ------------------------------------------------

    @staticmethod
    def _progressive_message(count: int, policy: RetryPolicy) -> str:
        if count <= 1:
            return "No te he entendido bien. ¿Puedes ser más específico?"
        return (
            "¿Buscas información general sobre homologaciones, "
            "o quieres un presupuesto para un elemento específico?"
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
                "¿Cuál prefieres?"
            )
        return "¿Prefieres hablar con una persona? Responde: SÍ o NO"

    @staticmethod
    def _mode_welcome(mode: str) -> str:
        return {
            "CONSULTA_MODE": "¿Qué quieres saber sobre homologación?",
            "PRESUPUESTO_MODE": "¿Qué elementos quieres homologar?",
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
