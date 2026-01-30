"""
Shared Tool Utilities for Agent Tools.

This module provides common helper functions used across multiple tool files
to reduce code duplication and ensure consistency.

Functions:
    - tool_error_response: Create standardized error responses
    - validate_category_slug: Validate category identifier format
    - sanitize_user_input: Clean user input to prevent injection
"""

import logging
import re
from typing import Any

from agent.utils.errors import ErrorCategory, create_error_response

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
            guidance="Verificá que el slug de categoría sea correcto.",
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


def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input to prevent injection attacks.
    
    This function:
    - Strips leading/trailing whitespace
    - Removes control characters
    - Limits length
    - Prevents common injection patterns
    
    Args:
        text: Raw user input
        max_length: Maximum allowed length (default 1000)
        
    Returns:
        Sanitized text
        
    Example:
        >>> sanitize_user_input("  Hello\\x00World  ")
        "HelloWorld"
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Remove control characters (except newlines and tabs)
    text = ''.join(
        char for char in text 
        if ord(char) >= 32 or char in '\n\t'
    )
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning(
            f"User input truncated to {max_length} characters",
            extra={"original_length": len(text) + 1},
        )
    
    # Prevent null byte injection
    text = text.replace('\x00', '')
    
    return text


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