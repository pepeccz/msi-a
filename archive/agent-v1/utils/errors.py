"""
Centralized Error Handling System for Agent Tools.

This module provides standardized error handling infrastructure including:
- Error categories (user-facing vs system errors)
- Standardized error response format
- Centralized error logging with structured context
- Decorator for consistent error handling in tools

Usage:
    from agent.utils.errors import ErrorCategory, handle_tool_errors
    
    @tool
    @handle_tool_errors(
        error_category=ErrorCategory.DATABASE_ERROR,
        error_code="DB_QUERY_FAILED",
        user_message="Lo siento, hubo un problema técnico."
    )
    async def my_tool():
        # Tool implementation
        ...
"""

import logging
import uuid
from datetime import datetime, UTC
from enum import Enum
from functools import wraps
from typing import Any, TypedDict, Literal


logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for proper handling and logging.
    
    USER-FACING ERRORS (explained to user):
    - VALIDATION_ERROR: Invalid input from user or LLM
    - NOT_FOUND_ERROR: Requested element/category not found
    - FSM_STATE_ERROR: Tool called in wrong FSM phase
    - PERMISSION_ERROR: Operation not allowed in current state
    
    SYSTEM ERRORS (logged internally, generic message to user):
    - DATABASE_ERROR: PostgreSQL/SQLAlchemy errors
    - LLM_ERROR: OpenRouter/Ollama failures
    - REDIS_ERROR: Cache/Streams errors
    - EXTERNAL_API_ERROR: Chatwoot or other external API failures
    - CONFIGURATION_ERROR: Missing or invalid configuration
    - UNEXPECTED_ERROR: Unknown/unhandled exceptions
    """
    # User-facing errors
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND_ERROR = "not_found_error"
    FSM_STATE_ERROR = "fsm_state_error"
    PERMISSION_ERROR = "permission_error"
    
    # System errors
    DATABASE_ERROR = "database_error"
    LLM_ERROR = "llm_error"
    REDIS_ERROR = "redis_error"
    EXTERNAL_API_ERROR = "external_api_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNEXPECTED_ERROR = "unexpected_error"


class ToolErrorResponse(TypedDict):
    """Standardized error response format for all tools.
    
    This format ensures consistency across all tools and provides
    both user-facing messages and LLM guidance.
    """
    success: Literal[False]  # Always False for errors
    error_category: str  # ErrorCategory value
    error_code: str  # Machine-readable error code
    message: str  # User-facing message (Spanish)
    guidance: str | None  # Instructions for LLM on how to proceed
    context: dict[str, Any] | None  # Additional context for debugging
    log_ref: str | None  # Reference ID for log correlation


class ErrorLogger:
    """Centralized error logging with structured context.
    
    Provides consistent error logging with full context including
    conversation_id, tool_name, stack traces, and metrics support.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ErrorLogger")
    
    def _generate_log_ref(self) -> str:
        """Generate unique reference ID for error correlation."""
        return f"err_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def log_error(
        self,
        error: Exception,
        category: ErrorCategory,
        *,
        conversation_id: str | None = None,
        tool_name: str | None = None,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
        exc_info: bool = True,
    ) -> str:
        """Log error with full structured context.
        
        Args:
            error: The exception that occurred
            category: Error category for classification
            conversation_id: Optional conversation identifier
            tool_name: Optional tool name where error occurred
            user_id: Optional user identifier
            context: Additional context data
            exc_info: Whether to include stack trace
            
        Returns:
            log_ref: Unique reference ID for this error instance
        """
        log_ref = self._generate_log_ref()
        
        log_data = {
            "log_ref": log_ref,
            "error_category": category.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "user_id": user_id,
            "context": context or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
        # Log with appropriate level based on category
        if category in [
            ErrorCategory.DATABASE_ERROR,
            ErrorCategory.LLM_ERROR,
            ErrorCategory.UNEXPECTED_ERROR,
        ]:
            self.logger.error(
                f"[{log_ref}] {category.value}: {error}",
                extra=log_data,
                exc_info=exc_info,
            )
        else:
            self.logger.warning(
                f"[{log_ref}] {category.value}: {error}",
                extra=log_data,
                exc_info=exc_info,
            )
        
        return log_ref
    
    def log_tool_error(
        self,
        tool_name: str,
        error: Exception,
        args: dict[str, Any],
        *,
        conversation_id: str | None = None,
        category: ErrorCategory = ErrorCategory.UNEXPECTED_ERROR,
        error_code: str = "TOOL_EXECUTION_ERROR",
        user_message: str = "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?",
    ) -> ToolErrorResponse:
        """Log tool error and return standardized response.
        
        This is the main entry point for tool error handling.
        
        Args:
            tool_name: Name of the tool that failed
            error: The exception that occurred
            args: Tool arguments that were passed
            conversation_id: Optional conversation identifier
            category: Error category
            error_code: Machine-readable error code
            user_message: Message to show to user
            
        Returns:
            Standardized error response dict
        """
        # Build context with tool arguments (sanitized)
        context = {
            "tool_args": {k: v for k, v in args.items() if k not in ["password", "token", "secret"]},
        }
        
        log_ref = self.log_error(
            error=error,
            category=category,
            conversation_id=conversation_id,
            tool_name=tool_name,
            context=context,
            exc_info=True,
        )
        
        # Build guidance based on category
        guidance = self._build_guidance(category, error)
        
        return {
            "success": False,
            "error_category": category.value,
            "error_code": error_code,
            "message": user_message,
            "guidance": guidance,
            "context": context,
            "log_ref": log_ref,
        }
    
    def _build_guidance(self, category: ErrorCategory, error: Exception) -> str | None:
        """Build LLM guidance based on error category."""
        guidance_map = {
            ErrorCategory.VALIDATION_ERROR: "Revisá los parámetros proporcionados y corregí los datos inválidos.",
            ErrorCategory.NOT_FOUND_ERROR: "Verificá que el elemento o categoría solicitada exista. Usá las herramientas de listado para ver opciones disponibles.",
            ErrorCategory.FSM_STATE_ERROR: "Revisá el estado actual de la conversación y usá la herramienta apropiada para esta fase.",
            ErrorCategory.PERMISSION_ERROR: "Esta operación no está permitida en el estado actual. Consultá las reglas de negocio.",
            ErrorCategory.DATABASE_ERROR: "Hubo un problema técnico con la base de datos. Podés intentar nuevamente o escalar a un humano si persiste.",
            ErrorCategory.LLM_ERROR: "Hubo un problema con el servicio de IA. Intentá nuevamente en unos momentos.",
            ErrorCategory.EXTERNAL_API_ERROR: "Hubo un problema con un servicio externo. Intentá nuevamente o verificá el estado del servicio.",
            ErrorCategory.CONFIGURATION_ERROR: "Hay un problema de configuración. Contactá al equipo técnico.",
            ErrorCategory.UNEXPECTED_ERROR: "Hubo un error inesperado. Intentá nuevamente o escalá a un humano si persiste.",
        }
        return guidance_map.get(category)


# Global error logger instance
_error_logger = ErrorLogger()


def get_error_logger() -> ErrorLogger:
    """Get the global error logger instance."""
    return _error_logger


def handle_tool_errors(
    error_category: ErrorCategory = ErrorCategory.UNEXPECTED_ERROR,
    error_code: str = "TOOL_EXECUTION_ERROR",
    user_message: str = "Lo siento, hubo un problema técnico. ¿Puedes intentarlo de nuevo?",
):
    """Decorator for tool functions to provide standardized error handling.
    
    This decorator catches all exceptions from the tool and returns a
    standardized error response. It also logs the error with full context.
    
    Args:
        error_category: Category for error classification
        error_code: Machine-readable error code
        user_message: User-facing error message (Spanish)
        
    Usage:
        @tool
        @handle_tool_errors(
            error_category=ErrorCategory.DATABASE_ERROR,
            error_code="DB_QUERY_FAILED",
            user_message="No se pudo acceder a la base de datos.",
        )
        async def my_tool(param: str) -> dict[str, Any]:
            # If this raises an exception, it will be caught and
            # returned as a standardized error response
            return {"success": True, "data": result}
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> dict[str, Any]:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Get conversation_id from state if available
                conversation_id = None
                try:
                    from agent.state.helpers import get_current_state
                    state = get_current_state()
                    if state:
                        conversation_id = state.get("conversation_id")
                except Exception:
                    pass
                
                # Log and return standardized error
                return _error_logger.log_tool_error(
                    tool_name=func.__name__,
                    error=e,
                    args=kwargs,
                    conversation_id=conversation_id,
                    category=error_category,
                    error_code=error_code,
                    user_message=user_message,
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> dict[str, Any]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                conversation_id = None
                try:
                    from agent.state.helpers import get_current_state
                    state = get_current_state()
                    if state:
                        conversation_id = state.get("conversation_id")
                except Exception:
                    pass
                
                return _error_logger.log_tool_error(
                    tool_name=func.__name__,
                    error=e,
                    args=kwargs,
                    conversation_id=conversation_id,
                    category=error_category,
                    error_code=error_code,
                    user_message=user_message,
                )
        
        # Return appropriate wrapper based on if function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def create_error_response(
    category: ErrorCategory,
    error_code: str,
    message: str,
    guidance: str | None = None,
    context: dict[str, Any] | None = None,
) -> ToolErrorResponse:
    """Create a standardized error response manually.
    
    Use this when you need to create an error response outside of the
    decorator (e.g., for validation errors before the main logic).
    
    Args:
        category: Error category
        error_code: Machine-readable error code
        message: User-facing message
        guidance: Optional LLM guidance
        context: Optional additional context
        
    Returns:
        Standardized error response dict
    """
    logger = get_error_logger()
    log_ref = logger._generate_log_ref()
    
    return {
        "success": False,
        "error_category": category.value,
        "error_code": error_code,
        "message": message,
        "guidance": guidance or logger._build_guidance(category, Exception(message)),
        "context": context or {},
        "log_ref": log_ref,
    }