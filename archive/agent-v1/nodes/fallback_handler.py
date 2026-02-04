"""
Fallback Handler for MSI-a v2.0 Architecture

Each mode defines its own retry policy and fallback behavior.
The fallback handler is called when retry_count >= max_retries.

Key Design Decisions:
1. Per-mode retry policies (not global)
2. Each mode decides: reset, escalate, or custom action
3. Retry count resets when changing modes
4. Fallback is a node in the graph, not a wrapper
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class FallbackAction(str, Enum):
    """Actions available when retry limit is reached."""
    RESET_TO_MODE_START = "reset_to_mode_start"  # Reset within same mode
    RESET_TO_CONSULTA = "reset_to_consulta"      # Go back to CONSULTA_MODE
    ESCALATE_TO_HUMAN = "escalate_to_human"      # Transfer to human agent
    OFFER_HUMAN_HELP = "offer_human_help"        # Ask if they want human
    SAVE_DRAFT_AND_EXIT = "save_draft_and_exit"  # Save progress, end conversation


class RetryErrorType(str, Enum):
    """Types of errors that trigger retry counting."""
    INTENT_NOT_UNDERSTOOD = "intent_not_understood"
    TOOL_CALL_FAILED = "tool_call_failed"
    VALIDATION_ERROR = "validation_error"
    LLM_PARSE_ERROR = "llm_parse_error"
    USER_CONFUSION = "user_confusion"  # Detected via sentiment/keywords


@dataclass
class RetryPolicy:
    """
    Retry policy for a specific conversation mode.
    
    Each mode defines:
    - max_retries: How many attempts before fallback
    - action_on_limit: What to do when limit reached
    - reprompt_strategy: How to reprompt on each retry
    - reset_on_success: Whether to reset counter on successful interaction
    """
    mode: str
    max_retries: int = 3
    action_on_limit: FallbackAction = FallbackAction.ESCALATE_TO_HUMAN
    reprompt_strategy: str = "progressive_clarity"  # progressive_clarity | same_message | simplify
    reset_on_success: bool = True  # Reset counter when user responds successfully
    error_types_to_track: list = field(default_factory=lambda: [
        RetryErrorType.INTENT_NOT_UNDERSTOOD,
        RetryErrorType.TOOL_CALL_FAILED,
        RetryErrorType.VALIDATION_ERROR,
    ])
    
    # Custom message overrides (optional)
    first_retry_message: Optional[str] = None
    second_retry_message: Optional[str] = None
    limit_reached_message: Optional[str] = None


# Default policies for each v2.0 mode
DEFAULT_RETRY_POLICIES: Dict[str, RetryPolicy] = {
    "CONSULTA_MODE": RetryPolicy(
        mode="CONSULTA_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.OFFER_HUMAN_HELP,
        reprompt_strategy="progressive_clarity",
        first_retry_message="Perdón, no entendí bien. ¿Podés reformular tu pregunta?",
        second_retry_message="No estoy entendiendo bien. ¿Podés ser más específico sobre qué Quieres saber de homologación?",
        limit_reached_message="Parece que estamos teniendo dificultades para comunicarnos. ¿Preferís hablar con una persona?",
    ),
    
    "VIABILIDAD_MODE": RetryPolicy(
        mode="VIABILIDAD_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        reprompt_strategy="progressive_clarity",
        first_retry_message="No capté bien qué Quieres evaluar. ¿Podés decirme el elemento y el vehículo?",
        second_retry_message="Necesito saber específicamente: ¿qué elemento Quieres homologar y en qué vehículo?",
        limit_reached_message="Este caso parece complejo. Te voy a conectar con un especialista que te puede ayudar mejor.",
    ),
    
    "PRESUPUESTO_MODE": RetryPolicy(
        mode="PRESUPUESTO_MODE",
        max_retries=5,  # More tolerant - user exploring options
        action_on_limit=FallbackAction.RESET_TO_VIABILIDAD,
        reprompt_strategy="simplify",
        first_retry_message="No entendí bien. ¿Quieres agregar algo al presupuesto, o tenés dudas?",
        second_retry_message="¿Quieres que volvamos a evaluar la viabilidad primero?",
        limit_reached_message="Parece que hay confusión. Volvamos a evaluar qué Quieres homologar.",
    ),
    
    "EVALUACION_GATEWAY": RetryPolicy(
        mode="EVALUACION_GATEWAY",
        max_retries=2,  # Binary decision - should be clear
        action_on_limit=FallbackAction.RESET_TO_PRESUPUESTO,
        reprompt_strategy="same_message",
        first_retry_message="Necesito que me respondas sí o no: ¿Quieres iniciar el expediente?",
        limit_reached_message="Te devuelvo al presupuesto para que lo revises con calma.",
    ),
    
    "EXPEDIENTE_MODE": RetryPolicy(
        mode="EXPEDIENTE_MODE",
        max_retries=3,
        action_on_limit=FallbackAction.OFFER_HUMAN_HELP,
        reprompt_strategy="progressive_clarity",
        first_retry_message="No entendí bien lo que me pasaste. ¿Podés intentar de nuevo?",
        second_retry_message="Parece que hay un problema con el formato. ¿Necesitás ayuda?",
        limit_reached_message="¿Quieres que te conecte con alguien que te guíe paso a paso?",
    ),
}


@dataclass
class RetryState:
    """Tracks retry state for current mode."""
    retry_count: int = 0
    last_error_type: Optional[RetryErrorType] = None
    last_error_message: Optional[str] = None
    first_error_timestamp: Optional[datetime] = None
    last_retry_timestamp: Optional[datetime] = None
    consecutive_errors: int = 0  # Track consecutive vs total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "retry_count": self.retry_count,
            "last_error_type": self.last_error_type.value if self.last_error_type else None,
            "last_error_message": self.last_error_message,
            "first_error_timestamp": self.first_error_timestamp.isoformat() if self.first_error_timestamp else None,
            "last_retry_timestamp": self.last_retry_timestamp.isoformat() if self.last_retry_timestamp else None,
            "consecutive_errors": self.consecutive_errors,
        }


class FallbackHandler:
    """
    Centralized fallback handler for v2.0 architecture.
    
    Usage in mode nodes:
    1. Check if current interaction is an error
    2. Call record_error() to increment counter
    3. If should_fallback() returns True, execute fallback action
    4. Otherwise, get reprompt message and continue
    """
    
    def __init__(self, policies: Optional[Dict[str, RetryPolicy]] = None):
        self.policies = policies or DEFAULT_RETRY_POLICIES
        self.logger = logger.bind(component="fallback_handler")
    
    def get_policy(self, mode: str) -> RetryPolicy:
        """Get retry policy for a mode."""
        return self.policies.get(mode, DEFAULT_RETRY_POLICIES["CONSULTA_MODE"])
    
    def record_error(
        self,
        retry_state: RetryState,
        error_type: RetryErrorType,
        error_message: str,
        policy: RetryPolicy,
    ) -> RetryState:
        """
        Record an error and update retry state.
        
        Returns updated RetryState (mutates input).
        """
        now = datetime.now()
        
        if retry_state.first_error_timestamp is None:
            retry_state.first_error_timestamp = now
            
        retry_state.retry_count += 1
        retry_state.consecutive_errors += 1
        retry_state.last_error_type = error_type
        retry_state.last_error_message = error_message
        retry_state.last_retry_timestamp = now
        
        self.logger.info(
            "error_recorded",
            error_type=error_type.value,
            retry_count=retry_state.retry_count,
            max_retries=policy.max_retries,
            mode=policy.mode,
        )
        
        return retry_state
    
    def record_success(self, retry_state: RetryState, policy: RetryPolicy) -> RetryState:
        """
        Record successful interaction - resets consecutive counter if configured.
        
        Returns updated RetryState.
        """
        if policy.reset_on_success:
            if retry_state.consecutive_errors > 0:
                self.logger.info(
                    "retry_counter_reset",
                    mode=policy.mode,
                    previous_consecutive_errors=retry_state.consecutive_errors,
                )
            retry_state.consecutive_errors = 0
            # Note: we keep total retry_count for analytics, just reset consecutive
            
        return retry_state
    
    def should_fallback(self, retry_state: RetryState, policy: RetryPolicy) -> bool:
        """Check if we should trigger fallback action."""
        return retry_state.retry_count >= policy.max_retries
    
    def get_reprompt_message(
        self,
        retry_state: RetryState,
        policy: RetryPolicy,
        default_message: Optional[str] = None,
    ) -> str:
        """
        Get the appropriate reprompt message based on retry count.
        
        Returns message to send to user on this retry.
        """
        count = retry_state.retry_count
        
        # Check for custom messages first
        if count == 1 and policy.first_retry_message:
            return policy.first_retry_message
        elif count == 2 and policy.second_retry_message:
            return policy.second_retry_message
        elif count >= policy.max_retries and policy.limit_reached_message:
            return policy.limit_reached_message
        
        # Generate based on strategy
        if policy.reprompt_strategy == "same_message":
            return default_message or "¿Podés repetir eso?"
            
        elif policy.reprompt_strategy == "simplify":
            return self._generate_simplified_message(retry_state, policy)
            
        elif policy.reprompt_strategy == "progressive_clarity":
            return self._generate_progressive_message(retry_state, policy, default_message)
        
        return default_message or "No entendí, ¿podés repetir?"
    
    def _generate_progressive_message(
        self,
        retry_state: RetryState,
        policy: RetryPolicy,
        default_message: Optional[str],
    ) -> str:
        """Generate progressively clearer message based on retry count."""
        count = retry_state.retry_count
        
        if count == 1:
            return "No entendí bien. ¿Podés ser más específico?"
        elif count == 2:
            if policy.mode == "CONSULTA_MODE":
                return "¿Buscás información general, evaluar si algo se puede homologar, o un presupuesto?"
            elif policy.mode == "VIABILIDAD_MODE":
                return "Para ayudarte, necesito que me digas: ¿qué elemento Quieres homologar y en qué vehículo?"
            elif policy.mode == "PRESUPUESTO_MODE":
                return "¿Quieres que te muestre el presupuesto actual, o preferís que vuelva a explicar los elementos?"
            else:
                return "Parece que no me estoy explicando bien. ¿Qué necesitás en este momento?"
        else:
            return policy.limit_reached_message or "Voy a intentar de otra forma..."
    
    def _generate_simplified_message(
        self,
        retry_state: RetryState,
        policy: RetryPolicy,
    ) -> str:
        """Generate simplified/options-based message."""
        if policy.mode == "PRESUPUESTO_MODE":
            return (
                "Te resumo las opciones:\n"
                "1. Ver presupuesto actual\n"
                "2. Agregar/quitar elementos\n" 
                "3. Volver a evaluar viabilidad\n"
                "4. Hablar con una persona\n\n"
                "¿Cuál preferís?"
            )
        elif policy.mode == "EVALUACION_GATEWAY":
            return "¿Confirmás iniciar el expediente? Respondé: SÍ o NO"
        else:
            return "¿Preferís hablar con una persona? Respondé: SÍ o NO"
    
    async def execute_fallback_action(
        self,
        action: FallbackAction,
        conversation_context: Dict[str, Any],
        retry_state: RetryState,
    ) -> Dict[str, Any]:
        """
        Execute the fallback action when retry limit is reached.
        
        Returns dict with:
        - action: FallbackAction executed
        - message: Message to send to user
        - new_mode: Mode to transition to (if any)
        - context_updates: Updates to conversation context
        - escalate: Whether to escalate to human
        """
        self.logger.warning(
            "fallback_action_triggered",
            action=action.value,
            mode=conversation_context.get("current_mode"),
            retry_count=retry_state.retry_count,
        )
        
        result = {
            "action": action.value,
            "message": "",
            "new_mode": None,
            "context_updates": {},
            "escalate": False,
        }
        
        if action == FallbackAction.RESET_TO_MODE_START:
            # Reset retry state, stay in same mode
            result["message"] = "Empecemos de nuevo desde el principio. " + self._get_mode_welcome_message(
                conversation_context.get("current_mode", "CONSULTA_MODE")
            )
            result["context_updates"] = {
                "retry_state": RetryState(),  # Fresh state
                "mode_context": {},  # Reset mode-specific context
            }
            
        elif action == FallbackAction.RESET_TO_CONSULTA:
            result["new_mode"] = "CONSULTA_MODE"
            result["message"] = (
                "Parece que nos trabamos. Volvamos a empezar de forma más simple. "
                "¿Qué Quieres saber sobre homologación?"
            )
            result["context_updates"] = {
                "retry_state": RetryState(),
                "preserved_quote": conversation_context.get("current_quote"),  # Save if exists
            }
            
        elif action == FallbackAction.ESCALATE_TO_HUMAN:
            result["escalate"] = True
            result["message"] = (
                "Te voy a conectar con un especialista que te puede ayudar mejor. "
                "Aguardá un momento..."
            )
            result["context_updates"] = {
                "escalation_reason": f"retry_limit_exceeded_{retry_state.retry_count}_attempts",
                "escalation_context": self._build_escalation_context(conversation_context, retry_state),
            }
            
        elif action == FallbackAction.OFFER_HUMAN_HELP:
            # Special case: offer human but don't force it
            result["message"] = (
                "¿Preferís que te conecte con una persona para ayudarte? "
                "Respondé SÍ si Quieres, o contame qué necesitás y sigo intentando ayudarte."
            )
            result["context_updates"] = {
                "human_offered": True,
                "pending_human_decision": True,
            }
            
        elif action == FallbackAction.SAVE_DRAFT_AND_EXIT:
            result["new_mode"] = "CONSULTA_MODE"
            result["message"] = (
                "Guardé tu progreso como borrador. Podés volver cuando quieras. "
                "¿Te puedo ayudar con algo más?"
            )
            result["context_updates"] = {
                "draft_saved": True,
                "draft_timestamp": datetime.now().isoformat(),
                "retry_state": RetryState(),
            }
        
        return result
    
    def _get_mode_welcome_message(self, mode: str) -> str:
        """Get welcome message for a mode."""
        messages = {
            "CONSULTA_MODE": "¿Qué Quieres saber sobre homologación?",
            "VIABILIDAD_MODE": "¿Qué elemento Quieres evaluar y en qué vehículo?",
            "PRESUPUESTO_MODE": "¿Qué elementos Quieres homologar?",
            "EXPEDIENTE_MODE": "¿Con qué dato empezamos?",
        }
        return messages.get(mode, "¿En qué te puedo ayudar?")
    
    def _build_escalation_context(
        self,
        conversation_context: Dict[str, Any],
        retry_state: RetryState,
    ) -> Dict[str, Any]:
        """Build context for human escalation."""
        return {
            "mode": conversation_context.get("current_mode"),
            "retry_count": retry_state.retry_count,
            "error_history": [
                {
                    "type": retry_state.last_error_type.value if retry_state.last_error_type else None,
                    "message": retry_state.last_error_message,
                }
            ],
            "user_context": {
                k: v for k, v in conversation_context.items()
                if k not in ["messages", "full_history"]  # Exclude heavy data
            },
        }


# Singleton instance
_fallback_handler: Optional[FallbackHandler] = None


def get_fallback_handler() -> FallbackHandler:
    """Get singleton fallback handler instance."""
    global _fallback_handler
    if _fallback_handler is None:
        _fallback_handler = FallbackHandler()
    return _fallback_handler


def reset_fallback_handler():
    """Reset singleton (useful for testing)."""
    global _fallback_handler
    _fallback_handler = None
