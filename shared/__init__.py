"""
MSI Automotive - Shared module.

This module contains shared utilities, configuration, and clients
used across the application.
"""

from shared.config import Settings, get_settings
from shared.logging_config import configure_logging
from shared.redis_client import get_redis_client

__all__ = [
    "Settings",
    "get_settings",
    "configure_logging",
    "get_redis_client",
]
