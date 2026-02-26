"""
Shared Tool Utilities for Agent Tools.

This module provides common helper functions used across multiple tool files
to reduce code duplication and ensure consistency.

Functions:
    - tool_error_response: Create standardized error responses
    - validate_category_slug: Validate category identifier format
    - sanitize_user_input: Clean user input to prevent injection (delegates to shared/)
"""

import logging
import re
from typing import Any

from agent.utils.errors import ErrorCategory, create_error_response

# Re-export sanitize_user_input from shared/ so existing imports keep working.
# The canonical implementation lives in shared/text_utils.py (correct layer).
from shared.text_utils import sanitize_user_input as sanitize_user_input  # noqa: F401

logger = logging.getLogger(__name__)


def tool_error_response(
    message: str,
    error_category: ErrorCategory = ErrorCategory.UNEXPECTED_ERROR,
    error_code: str = "TOOL_ERROR",
    guidance: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a standardized error response for tools.
    
    This is a convenience wrapper around create_error_response that adds
    the 'success': False field expected by tool consumers.
    
    Args:
        message: User-facing error message (Spanish)
        error_category: Error classification
        error_code: Machine-readable error code
        guidance: Optional LLM guidance
        context: Optional additional context
        
    Returns:
        Standardized error response dict with success=False
        
    Example:
        return tool_error_response(
            message="No se encontró la categoría solicitada.",
            error_category=ErrorCategory.NOT_FOUND_ERROR,
            error_code="CATEGORY_NOT_FOUND",
            guidance="Verifica que el slug de categoría sea correcto.",
            context={"requested_category": slug},
        )
    """
    response = create_error_response(
        category=error_category,
        error_code=error_code,
        message=message,
        guidance=guidance,
        context=context,
    )
    
    # Ensure success field is present for backward compatibility
    response["success"] = False
    
    return response


def validate_category_slug(slug: str) -> str:
    """Validate category slug format.
    
    Validates that the slug:
    - Contains only lowercase letters, numbers, and hyphens
    - Does not start or end with a hyphen
    - Has reasonable length (3-50 characters)
    
    Args:
        slug: Category slug to validate
        
    Returns:
        The validated slug (unchanged)
        
    Raises:
        ValueError: If slug format is invalid
        
    Example:
        >>> validate_category_slug("motos-part")
        "motos-part"
        >>> validate_category_slug("Invalid_Slug")
        ValueError: Invalid category slug format: Invalid_Slug
    """
    if not slug:
        raise ValueError("Category slug cannot be empty")
    
    if len(slug) < 3 or len(slug) > 50:
        raise ValueError(f"Category slug must be 3-50 characters, got {len(slug)}")
    
    # Allow lowercase letters, numbers, and hyphens only
    if not re.match(r'^[a-z0-9-]+$', slug):
        raise ValueError(
            f"Invalid category slug format: {slug}. "
            "Only lowercase letters, numbers, and hyphens allowed."
        )
    
    # Prevent leading/trailing hyphens
    if slug.startswith('-') or slug.endswith('-'):
        raise ValueError(
            f"Invalid category slug: {slug}. "
            "Cannot start or end with hyphen."
        )
    
    # Prevent consecutive hyphens
    if '--' in slug:
        raise ValueError(
            f"Invalid category slug: {slug}. "
            "Cannot contain consecutive hyphens."
        )
    
    return slug


# sanitize_user_input is imported from shared/text_utils at the top of this file.
# The implementation now lives in shared/ (correct architectural layer) so both
# api/ and agent/ can use it without cross-layer dependencies.


def truncate_for_llm(text: str, max_chars: int = 500) -> str:
    """Truncate text to fit within LLM context limits.
    
    Used when including error messages or long text in LLM prompts.
    Adds "[truncated]" suffix when truncation occurs.
    
    Args:
        text: Original text
        max_chars: Maximum characters allowed
        
    Returns:
        Truncated text if needed
    """
    if not text or len(text) <= max_chars:
        return text
    
    # Reserve space for truncation indicator
    available = max_chars - 13  # len(" [truncated]")
    return text[:available] + " [truncated]"


def format_field_list(fields: list[dict[str, Any]]) -> str:
    """Format a list of fields for LLM consumption.
    
    Creates a human-readable list of field names and types
    suitable for inclusion in LLM prompts.
    
    Args:
        fields: List of field dictionaries with 'name', 'type', 'required' keys
        
    Returns:
        Formatted string
    """
    if not fields:
        return "No hay campos disponibles."
    
    lines = []
    for field in fields:
        name = field.get("name", "unknown")
        field_type = field.get("type", "text")
        required = field.get("required", False)
        
        req_marker = " (obligatorio)" if required else " (opcional)"
        lines.append(f"- {name}: {field_type}{req_marker}")
    
    return "\n".join(lines)


def parse_confirmation_message(message: str) -> bool:
    """Parse user message to detect confirmation intent.
    
    Detects common affirmative responses in Spanish:
    - "sí", "si", "dale", "adelante", "ok", "vale", "bueno", etc.
    
    Args:
        message: User message text
        
    Returns:
        True if message appears to be confirmation
        
    Example:
        >>> parse_confirmation_message("dale, adelante")
        True
        >>> parse_confirmation_message("no estoy seguro")
        False
    """
    if not message:
        return False
    
    # Normalize: lowercase, remove punctuation
    normalized = message.lower().strip()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    
    # Confirmation keywords in Spanish
    confirm_words = {
        'si', 'sí', 'dale', 'adelante', 'ok', 'okay', 'vale', 'va',
        'bueno', 'bien', 'perfecto', 'correcto', 'exacto', 'claro',
        'por', 'supuesto', 'confirmo', 'confirmado', 'yes', 'ya',
    }
    
    # Split into words and check
    words = normalized.split()
    return any(word in confirm_words for word in words)


def safe_json_dumps(obj: Any, max_length: int = 2000) -> str:
    """Safely convert object to JSON string with length limit.
    
    Args:
        obj: Object to serialize
        max_length: Maximum string length
        
    Returns:
        JSON string or error message if serialization fails
    """
    try:
        import json
        result = json.dumps(obj, ensure_ascii=False, default=str)
        if len(result) > max_length:
            return result[:max_length] + "... [truncated]"
        return result
    except Exception as e:
        logger.error(f"JSON serialization failed: {e}")
        return f"<serialization error: {str(e)}>"


def structured_validation_error(
    tool_name: str,
    validation_errors: list[str],
    validation_layer: str,  # Phase 3: which layer failed
    provided_params: list[str],
    required_params: list[str],
    suggestion: str,
) -> dict[str, Any]:
    """
    Generate structured validation error for LLM retry (Phase 3).

    Provides enough context for LLM to fix parameters and retry
    the tool call with correct arguments.

    Args:
        tool_name: Name of the tool that failed validation
        validation_errors: List of validation error messages
        validation_layer: Which validation layer failed ("syntax", "state", "semantic")
        provided_params: List of parameter names provided by LLM
        required_params: List of required parameter names
        suggestion: Helpful suggestion on how to fix the error

    Returns:
        Dict with structured error information for LLM

    Example:
        return structured_validation_error(
            tool_name="iniciar_expediente",
            validation_errors=["Missing required parameter: categoria_slug"],
            validation_layer="syntax",
            provided_params=["user_input"],
            required_params=["categoria_slug", "tarifa_calculada", "tier_id"],
            suggestion="Please provide categoria_slug from mode_context",
        )
    """
    return {
        "success": False,
        "error": "Invalid tool parameters",
        "error_type": "parameter_validation",
        "validation_layer": validation_layer,  # Phase 3: include layer
        "tool_name": tool_name,
        "validation_errors": validation_errors,
        "provided_params": provided_params,
        "required_params": required_params,
        "suggestion": suggestion,
        "can_retry": True,  # Signal to LLM that retry is expected
    }