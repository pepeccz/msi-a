"""
Mode Node Template for v2.0 - Shows Fallback Handler Integration

This is a template showing how each mode node should implement fallback handling.
Each real mode node (consulta_mode.py, viabilidad_mode.py, etc.) follows this pattern.
"""

from typing import Dict, Any, TypedDict, Optional
import structlog
from agent.nodes.fallback_handler import (
    get_fallback_handler,
    RetryState,
    RetryPolicy,
    RetryErrorType,
    FallbackAction,
)

logger = structlog.get_logger(__name__)


class ModeNodeResult(TypedDict):
    """Standard result from any mode node."""
    response: str
    mode: str  # Current or new mode
    context_updates: Dict[str, Any]
    should_transition: bool
    transition_target: Optional[str]
    escalate: bool


class BaseModeNode:
    """
    Base class for all v2.0 mode nodes.
    
    Implements fallback handling pattern:
    1. Initialize/get retry state
    2. Process user input
    3. If error: record_error() + check should_fallback()
    4. If should_fallback: execute_fallback_action()
    5. If success: record_success() to reset consecutive counter
    """
    
    def __init__(self, mode_name: str):
        self.mode_name = mode_name
        self.fallback_handler = get_fallback_handler()
        self.policy = self.fallback_handler.get_policy(mode_name)
        self.logger = logger.bind(mode=mode_name)
    
    async def process(
        self,
        user_message: str,
        conversation_context: Dict[str, Any],
        history: list,
    ) -> ModeNodeResult:
        """
        Main entry point for mode processing.
        
        Override this in concrete mode implementations.
        This template shows the fallback integration pattern.
        """
        # 1. Get or initialize retry state for this mode
        retry_state = self._get_retry_state(conversation_context)
        
        try:
            # 2. Attempt to process the message
            result = await self._process_message(
                user_message, conversation_context, history
            )
            
            # 3. If successful, record success (resets consecutive counter)
            if result.get("success", True):
                updated_retry = self.fallback_handler.record_success(retry_state, self.policy)
                result["context_updates"]["retry_state"] = updated_retry.to_dict()
                
            return result
            
        except Exception as e:
            # 4. Handle error with fallback logic
            return await self._handle_error(
                error=e,
                error_type=self._classify_error(e),
                retry_state=retry_state,
                conversation_context=conversation_context,
            )
    
    async def _process_message(
        self,
        user_message: str,
        context: Dict[str, Any],
        history: list,
    ) -> ModeNodeResult:
        """
        Override this in concrete implementations.
        
        This is where the actual mode logic goes (tool calls, LLM, etc.)
        """
        raise NotImplementedError("Subclasses must implement _process_message")
    
    async def _handle_error(
        self,
        error: Exception,
        error_type: RetryErrorType,
        retry_state: RetryState,
        conversation_context: Dict[str, Any],
    ) -> ModeNodeResult:
        """
        Handle error with fallback logic.
        
        This method is the same across all modes - the policy decides the behavior.
        """
        error_message = str(error)
        
        # Record the error
        updated_retry = self.fallback_handler.record_error(
            retry_state=retry_state,
            error_type=error_type,
            error_message=error_message,
            policy=self.policy,
        )
        
        # Check if we should trigger fallback
        if self.fallback_handler.should_fallback(updated_retry, self.policy):
            # Execute fallback action
            fallback_result = await self.fallback_handler.execute_fallback_action(
                action=self.policy.action_on_limit,
                conversation_context=conversation_context,
                retry_state=updated_retry,
            )
            
            self.logger.warning(
                "fallback_triggered",
                action=fallback_result["action"],
                retry_count=updated_retry.retry_count,
            )
            
            return ModeNodeResult(
                response=fallback_result["message"],
                mode=fallback_result.get("new_mode") or self.mode_name,
                context_updates={
                    **fallback_result["context_updates"],
                    "retry_state": RetryState().to_dict(),  # Reset for new mode
                },
                should_transition=fallback_result.get("new_mode") is not None,
                transition_target=fallback_result.get("new_mode"),
                escalate=fallback_result["escalate"],
            )
        
        else:
            # Get reprompt message and continue in same mode
            reprompt = self.fallback_handler.get_reprompt_message(
                retry_state=updated_retry,
                policy=self.policy,
                default_message="No entendí bien. ¿Podés repetir?",
            )
            
            return ModeNodeResult(
                response=reprompt,
                mode=self.mode_name,
                context_updates={
                    "retry_state": updated_retry.to_dict(),
                    "last_error": error_message,
                },
                should_transition=False,
                transition_target=None,
                escalate=False,
            )
    
    def _get_retry_state(self, context: Dict[str, Any]) -> RetryState:
        """Get or initialize retry state from context."""
        retry_data = context.get("retry_state", {})
        
        if not retry_data:
            return RetryState()
        
        return RetryState(
            retry_count=retry_data.get("retry_count", 0),
            last_error_type=RetryErrorType(retry_data["last_error_type"]) if retry_data.get("last_error_type") else None,
            last_error_message=retry_data.get("last_error_message"),
            consecutive_errors=retry_data.get("consecutive_errors", 0),
        )
    
    def _classify_error(self, error: Exception) -> RetryErrorType:
        """Classify error type for retry tracking."""
        error_msg = str(error).lower()
        error_type = type(error).__name__.lower()
        
        if "tool" in error_type or "invocation" in error_msg:
            return RetryErrorType.TOOL_CALL_FAILED
        elif "validation" in error_type or "invalid" in error_msg:
            return RetryErrorType.VALIDATION_ERROR
        elif "parse" in error_type or "json" in error_msg:
            return RetryErrorType.LLM_PARSE_ERROR
        elif "understand" in error_msg or "intent" in error_msg:
            return RetryErrorType.INTENT_NOT_UNDERSTOOD
        else:
            return RetryErrorType.USER_CONFUSION


# =============================================================================
# EXAMPLE: CONSULTA_MODE Implementation
# =============================================================================

class ConsultaModeNode(BaseModeNode):
    """
    CONSULTA_MODE implementation with fallback handling.
    
    This shows a real implementation of the base pattern.
    """
    
    def __init__(self):
        super().__init__("CONSULTA_MODE")
        self.available_tools = [
            "responder_consulta_general",
            "explicar_proceso_homologacion",
            "listar_categorias",
            "listar_elementos_generales",
            "escalar_a_humano",
        ]
    
    async def _process_message(
        self,
        user_message: str,
        context: Dict[str, Any],
        history: list,
    ) -> ModeNodeResult:
        """
        Process message in CONSULTA_MODE.
        
        Returns result with success=True if processed correctly.
        Raises exception if something goes wrong (triggers fallback).
        """
        try:
            # 1. Check for mode transition intent
            transition = self._check_transition_intent(user_message)
            if transition:
                return ModeNodeResult(
                    response=transition["message"],
                    mode=transition["target_mode"],
                    context_updates={
                        "previous_mode": "CONSULTA_MODE",
                        "retry_state": RetryState().to_dict(),  # Reset for new mode
                    },
                    should_transition=True,
                    transition_target=transition["target_mode"],
                    escalate=False,
                )
            
            # 2. Process with available tools
            tool_result = await self._call_consulta_tools(user_message, context)
            
            # 3. Return successful result
            return ModeNodeResult(
                response=tool_result["response"],
                mode="CONSULTA_MODE",
                context_updates={
                    "consulta_history": context.get("consulta_history", []) + [{
                        "question": user_message,
                        "response": tool_result["response"],
                    }],
                    "success": True,  # Signals that retry counter should reset
                },
                should_transition=False,
                transition_target=None,
                escalate=False,
            )
            
        except Exception as e:
            # Let parent class handle with fallback logic
            raise e
    
    def _check_transition_intent(self, message: str) -> Optional[Dict[str, str]]:
        """Check if user wants to transition to another mode."""
        message_lower = message.lower()
        
        # VIABILIDAD_MODE triggers
        viabilidad_keywords = ["se puede", "es posible", "está permitido", "puedo homologar"]
        if any(kw in message_lower for kw in viabilidad_keywords):
            return {
                "target_mode": "VIABILIDAD_MODE",
                "message": "Déjame evaluar eso para vos...",
            }
        
        # PRESUPUESTO_MODE triggers
        presupuesto_keywords = ["cuánto cuesta", "precio de", "presupuesto para"]
        if any(kw in message_lower for kw in presupuesto_keywords):
            return {
                "target_mode": "PRESUPUESTO_MODE",
                "message": "Voy a calcular un presupuesto para vos...",
            }
        
        return None
    
    async def _call_consulta_tools(
        self,
        message: str,
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Call appropriate tools for consultation."""
        # This would call actual tools (RAG, etc.)
        # For template, return mock response
        return {
            "response": f"[CONSULTA_MODE] Respuesta a: {message}",
        }


# =============================================================================
# EXAMPLE: PRESUPUESTO_MODE Implementation (with more complex fallback)
# =============================================================================

class PresupuestoModeNode(BaseModeNode):
    """
    PRESUPUESTO_MODE with higher retry tolerance and different fallback action.
    
    Note: Uses 5 retries (from policy) and resets to VIABILIDAD on limit.
    """
    
    def __init__(self):
        super().__init__("PRESUPUESTO_MODE")
    
    async def _process_message(
        self,
        user_message: str,
        context: Dict[str, Any],
        history: list,
    ) -> ModeNodeResult:
        """Process message in PRESUPUESTO_MODE."""
        try:
            # Check for element modifications (loops within mode)
            if self._is_element_modification(user_message):
                result = await self._handle_element_modification(user_message, context)
                return ModeNodeResult(
                    response=result["message"],
                    mode="PRESUPUESTO_MODE",  # Stay in mode
                    context_updates={
                        "current_quote": result["updated_quote"],
                        "success": True,
                    },
                    should_transition=False,
                    transition_target=None,
                    escalate=False,
                )
            
            # Check for acceptance
            if self._is_acceptance(user_message):
                return ModeNodeResult(
                    response="Perfecto, procedamos...",
                    mode="EVALUACION_GATEWAY",
                    context_updates={
                        "quote_accepted": True,
                        "retry_state": RetryState().to_dict(),
                    },
                    should_transition=True,
                    transition_target="EVALUACION_GATEWAY",
                    escalate=False,
                )
            
            # Default: explain current quote
            return ModeNodeResult(
                response=self._format_quote(context.get("current_quote")),
                mode="PRESUPUESTO_MODE",
                context_updates={"success": True},
                should_transition=False,
                transition_target=None,
                escalate=False,
            )
            
        except Exception as e:
            raise e
    
    def _is_element_modification(self, message: str) -> bool:
        """Check if user wants to add/remove elements."""
        keywords = ["también", "agregar", "sacar", "quitar", "eliminar", "además"]
        return any(kw in message.lower() for kw in keywords)
    
    def _is_acceptance(self, message: str) -> bool:
        """Check if user accepts the quote."""
        accept_keywords = ["sí", "si", "ok", "perfecto", "adelante", "confirmo"]
        return any(kw in message.lower() for kw in accept_keywords)
    
    async def _handle_element_modification(
        self,
        message: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle adding/removing elements from quote."""
        # Would call actual element tools
        return {
            "message": "Actualizando presupuesto...",
            "updated_quote": context.get("current_quote", {}),
        }
    
    def _format_quote(self, quote: Optional[Dict]) -> str:
        """Format current quote for display."""
        if not quote:
            return "No hay presupuesto activo. ¿Qué elementos Quieres cotizar?"
        return f"Presupuesto actual: {quote}"


# =============================================================================
# Usage Example in Graph
# =============================================================================

"""
In conversation.py graph definition:

from agent.nodes.mode_nodes import ConsultaModeNode, PresupuestoModeNode, ...

# Initialize nodes
consulta_node = ConsultaModeNode()
presupuesto_node = PresupuestoModeNode()

# In graph edges:
async def route_from_consulta(state: ConversationState):
    result = await consulta_node.process(
        user_message=state["user_message"],
        conversation_context=state["context"],
        history=state["messages"],
    )
    
    if result["escalate"]:
        return "ESCALATE"
    elif result["should_transition"]:
        return result["transition_target"]
    else:
        # Update state with result
        state["response"] = result["response"]
        state["context"] = {**state["context"], **result["context_updates"]}
        return "CONSULTA_MODE"  # Stay in mode

# The fallback logic is handled INSIDE each node
# No need for external fallback routing - the node decides
"""
