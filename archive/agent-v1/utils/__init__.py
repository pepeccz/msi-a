"""Utility functions for the agent."""

from agent.utils.errors import (
    ErrorCategory,
    ErrorLogger,
    ToolErrorResponse,
    create_error_response,
    get_error_logger,
    handle_tool_errors,
)
from agent.utils.text_utils import (
    fuzzy_match,
    fuzzy_match_with_scores,
    normalize_field_key,
    normalize_text,
)
from agent.utils.tool_helpers import (
    format_field_list,
    parse_confirmation_message,
    safe_json_dumps,
    sanitize_user_input,
    tool_error_response,
    truncate_for_llm,
    validate_category_slug,
)
from agent.utils.validation import validate_category_slug as validate_slug

__all__ = [
    # Error handling
    "ErrorCategory",
    "ErrorLogger",
    "ToolErrorResponse",
    "create_error_response",
    "get_error_logger",
    "handle_tool_errors",
    # Text utilities
    "normalize_text",
    "normalize_field_key",
    "fuzzy_match",
    "fuzzy_match_with_scores",
    # Tool helpers
    "format_field_list",
    "parse_confirmation_message",
    "safe_json_dumps",
    "sanitize_user_input",
    "tool_error_response",
    "truncate_for_llm",
    "validate_category_slug",
    "validate_slug",
]
