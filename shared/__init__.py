"""
MSI Automotive - Shared module.

This module contains shared utilities, configuration, and clients
used across the application.
"""

from shared.chatwoot_client import ChatwootClient
from shared.config import Settings, get_settings
from shared.image_security import ImageSecurityError, validate_image_full
from shared.llm_router import LLMRouter, ModelTier, TaskType, get_llm_router
from shared.logging_config import configure_logging
from shared.redis_client import get_redis_client
from shared.redis_keys import RedisKeys
from shared.errors import (
    ErrorCategory,
    APIErrorResponse,
    ErrorLogger,
    get_error_logger,
    map_status_to_category,
    translate_to_spanish,
)
from shared.fastapi_errors import register_error_handlers

__all__ = [
    # Core utilities
    "Settings",
    "get_settings",
    "configure_logging",
    # Redis
    "get_redis_client",
    "RedisKeys",
    # Clients
    "ChatwootClient",
    # LLM routing
    "LLMRouter",
    "get_llm_router",
    "TaskType",
    "ModelTier",
    # Image security
    "validate_image_full",
    "ImageSecurityError",
    # Error handling
    "ErrorCategory",
    "APIErrorResponse",
    "ErrorLogger",
    "get_error_logger",
    "map_status_to_category",
    "translate_to_spanish",
    "register_error_handlers",
]
