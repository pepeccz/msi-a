"""
Settings cache module - Cached access to SystemSettings via Redis.

Provides caching layer for system settings to avoid database queries
on every agent message. Cache TTL is 5 seconds with manual invalidation
when settings are updated via API.
"""

__all__ = [
    "get_cached_setting",
    "get_cached_settings",
    "invalidate_setting_cache",
    "invalidate_all_settings",
]

import logging
from typing import Any

from sqlalchemy import select

from database.connection import get_async_session
from database.models import SystemSetting
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cache configuration
SETTINGS_CACHE_PREFIX = "system_setting:"
SETTINGS_CACHE_TTL = 5  # 5 seconds TTL


async def get_cached_setting(key: str) -> str | None:
    """
    Get a system setting value with Redis caching.

    First tries to get from Redis cache. If cache miss, queries PostgreSQL
    and caches the result with 5 second TTL.

    Args:
        key: The setting key (e.g., 'agent_enabled')

    Returns:
        The setting value as string, or None if not found
    """
    redis_client = get_redis_client()
    cache_key = f"{SETTINGS_CACHE_PREFIX}{key}"

    try:
        # Try to get from cache
        cached_value = await redis_client.get(cache_key)

        if cached_value is not None:
            logger.debug(f"Cache hit for setting '{key}': {cached_value}")
            return cached_value

        # Cache miss - query database
        logger.debug(f"Cache miss for setting '{key}', querying database")

        async with get_async_session() as session:
            result = await session.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            setting = result.scalar_one_or_none()

            if setting is None:
                logger.warning(f"Setting '{key}' not found in database")
                return None

            # Cache the value
            await redis_client.setex(cache_key, SETTINGS_CACHE_TTL, setting.value)

            logger.debug(f"Cached setting '{key}' with value '{setting.value}' (TTL={SETTINGS_CACHE_TTL}s)")
            return setting.value

    except Exception as e:
        logger.error(f"Error getting cached setting '{key}': {e}")
        # On error, try to get directly from database without caching
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(SystemSetting).where(SystemSetting.key == key)
                )
                setting = result.scalar_one_or_none()
                return setting.value if setting else None
        except Exception as db_error:
            logger.error(f"Database fallback also failed for '{key}': {db_error}")
            return None


async def invalidate_setting_cache(key: str) -> bool:
    """
    Invalidate the cache for a specific setting.

    Should be called when a setting is updated via API to ensure
    immediate propagation of the change.

    Args:
        key: The setting key to invalidate

    Returns:
        True if key was deleted, False otherwise
    """
    redis_client = get_redis_client()
    cache_key = f"{SETTINGS_CACHE_PREFIX}{key}"

    try:
        deleted = await redis_client.delete(cache_key)

        if deleted:
            logger.info(f"Invalidated cache for setting '{key}'")
        else:
            logger.debug(f"Cache key '{cache_key}' was not present (nothing to invalidate)")

        return bool(deleted)

    except Exception as e:
        logger.error(f"Error invalidating cache for setting '{key}': {e}")
        return False


async def get_cached_settings(keys: list[str]) -> dict[str, str | None]:
    """
    Get multiple settings values with caching (convenience method).

    Args:
        keys: List of setting keys to retrieve

    Returns:
        Dictionary mapping keys to their values (None if not found)
    """
    result: dict[str, str | None] = {}

    for key in keys:
        result[key] = await get_cached_setting(key)

    return result


async def invalidate_all_settings() -> int:
    """
    Invalidate all cached settings.

    Useful when doing bulk updates or during system reset.

    Returns:
        Number of keys deleted
    """
    redis_client = get_redis_client()

    try:
        # Find all setting cache keys
        pattern = f"{SETTINGS_CACHE_PREFIX}*"
        keys = []

        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key)

        if not keys:
            logger.debug("No cached settings to invalidate")
            return 0

        # Delete all found keys
        deleted = await redis_client.delete(*keys)
        logger.info(f"Invalidated {deleted} cached settings")

        return deleted

    except Exception as e:
        logger.error(f"Error invalidating all settings cache: {e}")
        return 0
