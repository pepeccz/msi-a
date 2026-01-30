"""
Unified Error Handling System for API and Shared Components.

This module provides standardized error handling infrastructure for FastAPI
including error categories, Pydantic response models, HTTP status code mapping,
and centralized error logging with structured context.

Usage:
    from shared.errors import ErrorCategory, APIErrorResponse, ErrorLogger
    
    logger = ErrorLogger()
    log_ref = logger.log_error(
        error=exc,
        category=ErrorCategory.DATABASE_ERROR,
        context={"endpoint": "/api/tariffs"}
    )
"""

import logging
import uuid
from datetime import datetime, UTC
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of errors for proper handling and logging.
    
    USER-FACING ERRORS (explained to user):
    - VALIDATION_ERROR: Invalid input from user
    - NOT_FOUND_ERROR: Requested resource not found
    - PERMISSION_ERROR: Operation not allowed for current user/role
    
    SYSTEM ERRORS (logged internally, generic message to user):
    - DATABASE_ERROR: PostgreSQL/SQLAlchemy errors
    - EXTERNAL_API_ERROR: Chatwoot or other external API failures
    - CONFIGURATION_ERROR: Missing or invalid configuration
    - UNEXPECTED_ERROR: Unknown/unhandled exceptions
    """
    # User-facing errors
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND_ERROR = "not_found_error"
    PERMISSION_ERROR = "permission_error"
    
    # System errors
    DATABASE_ERROR = "database_error"
    EXTERNAL_API_ERROR = "external_api_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNEXPECTED_ERROR = "unexpected_error"


class APIErrorResponse(BaseModel):
    """Standardized error response format for API endpoints.
    
    This format ensures consistency across all API endpoints and provides
    both user-facing messages and optional context for debugging.
    """
    success: bool = Field(default=False, description="Always False for errors")
    error_category: ErrorCategory = Field(description="Error category for classification")
    error_code: str = Field(description="Machine-readable error code")
    message: str = Field(description="User-facing message (Spanish)")
    guidance: str | None = Field(default=None, description="Optional guidance for resolution")
    log_ref: str | None = Field(default=None, description="Reference ID for log correlation")
    context: dict[str, Any] | None = Field(default=None, description="Additional context for debugging")


class ErrorLogger:
    """Centralized error logging with structured context.
    
    Provides consistent error logging with full context including
    endpoint path, request method, user info, stack traces, and more.
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
        endpoint: str | None = None,
        method: str | None = None,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
        exc_info: bool = True,
    ) -> str:
        """Log error with full structured context.
        
        Args:
            error: The exception that occurred
            category: Error category for classification
            endpoint: Optional endpoint path where error occurred
            method: Optional HTTP method (GET, POST, etc.)
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
            "endpoint": endpoint,
            "method": method,
            "user_id": user_id,
            "context": context or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
        # Log with appropriate level based on category
        if category in [
            ErrorCategory.DATABASE_ERROR,
            ErrorCategory.EXTERNAL_API_ERROR,
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
    
    def _build_guidance(self, category: ErrorCategory) -> str | None:
        """Build user guidance based on error category."""
        guidance_map = {
            ErrorCategory.VALIDATION_ERROR: "Verifique los datos proporcionados y corrija los errores.",
            ErrorCategory.NOT_FOUND_ERROR: "Verifique que el recurso solicitado existe.",
            ErrorCategory.PERMISSION_ERROR: "No tiene permisos para realizar esta operación. Contacte al administrador si necesita acceso.",
            ErrorCategory.DATABASE_ERROR: "Hubo un problema técnico con la base de datos. Por favor, intente nuevamente en unos momentos.",
            ErrorCategory.EXTERNAL_API_ERROR: "Hubo un problema con un servicio externo. Por favor, intente nuevamente en unos momentos.",
            ErrorCategory.CONFIGURATION_ERROR: "Hay un problema de configuración. Por favor, contacte al equipo técnico.",
            ErrorCategory.UNEXPECTED_ERROR: "Hubo un error inesperado. Por favor, intente nuevamente o contacte al soporte técnico.",
        }
        return guidance_map.get(category)


# Global error logger instance
_error_logger = ErrorLogger()


def get_error_logger() -> ErrorLogger:
    """Get the global error logger instance."""
    return _error_logger


# HTTP status code to ErrorCategory mapping
STATUS_TO_CATEGORY: dict[int, ErrorCategory] = {
    400: ErrorCategory.VALIDATION_ERROR,
    401: ErrorCategory.PERMISSION_ERROR,
    403: ErrorCategory.PERMISSION_ERROR,
    404: ErrorCategory.NOT_FOUND_ERROR,
    409: ErrorCategory.VALIDATION_ERROR,
    422: ErrorCategory.VALIDATION_ERROR,
    500: ErrorCategory.UNEXPECTED_ERROR,
    502: ErrorCategory.EXTERNAL_API_ERROR,
    503: ErrorCategory.EXTERNAL_API_ERROR,
    504: ErrorCategory.EXTERNAL_API_ERROR,
}


def map_status_to_category(status_code: int) -> ErrorCategory:
    """Map HTTP status code to ErrorCategory.
    
    Args:
        status_code: HTTP status code
        
    Returns:
        Corresponding ErrorCategory
    """
    return STATUS_TO_CATEGORY.get(status_code, ErrorCategory.UNEXPECTED_ERROR)


# Spanish translations for common error messages
TRANSLATIONS: dict[str, str] = {
    # Authentication & Authorization
    "Unauthorized": "No autorizado. Por favor, inicie sesión.",
    "Forbidden": "Acceso prohibido. No tiene permisos para esta operación.",
    "Invalid credentials": "Credenciales inválidas. Verifique su usuario y contraseña.",
    "Token expired": "Su sesión ha expirado. Por favor, inicie sesión nuevamente.",
    "Invalid token": "Token de autenticación inválido. Por favor, inicie sesión nuevamente.",
    
    # Validation
    "Validation error": "Error de validación. Verifique los datos proporcionados.",
    "Invalid input": "Entrada inválida. Verifique los datos proporcionados.",
    "Missing required field": "Falta un campo requerido.",
    "Invalid format": "Formato inválido.",
    
    # Not Found
    "Not found": "Recurso no encontrado.",
    "Not Found": "Recurso no encontrado.",
    "Resource not found": "Recurso no encontrado.",
    
    # Database
    "Database error": "Error de base de datos. Intente nuevamente.",
    "Connection error": "Error de conexión. Intente nuevamente.",
    
    # External API
    "External API error": "Error de servicio externo. Intente nuevamente.",
    "Service unavailable": "Servicio no disponible temporalmente. Intente nuevamente más tarde.",
    
    # Configuration
    "Configuration error": "Error de configuración del sistema. Contacte al administrador.",
    
    # Generic
    "Internal server error": "Error interno del servidor. Intente nuevamente.",
    "Unexpected error": "Error inesperado. Intente nuevamente.",
}


def translate_to_spanish(message: str) -> str:
    """Translate common English error messages to Spanish.
    
    Args:
        message: Error message in English
        
    Returns:
        Translated message in Spanish (or original if no translation found)
    """
    # Direct match
    if message in TRANSLATIONS:
        return TRANSLATIONS[message]
    
    # Case-insensitive partial match
    message_lower = message.lower()
    for eng, spa in TRANSLATIONS.items():
        if eng.lower() in message_lower:
            return spa
    
    # No translation found, return original
    return message
