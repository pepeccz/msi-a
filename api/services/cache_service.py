"""
Centralized cache invalidation service.

Provides consistent cache invalidation patterns across all API routes,
reducing code duplication and ensuring all related cache keys are cleared.
"""

import logging
from typing import Literal

from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class CacheService:
    """Centralized cache invalidation service."""

    def __init__(self):
        self.redis = get_redis_client()

    async def invalidate_element_cache(
        self,
        element_id: str | None = None,
        category_id: str | None = None,
    ) -> int:
        """
        Invalidate element-related cache keys.

        Args:
            element_id: Optional element UUID to invalidate specific element details
            category_id: Optional category UUID to invalidate category listings

        Returns:
            Number of cache keys deleted
        """
        deleted = 0
        patterns = []

        # Element detail cache (inherited and non-inherited)
        if element_id:
            patterns.extend([
                f"element:details:{element_id}:inherited=True",
                f"element:details:{element_id}:inherited=False",
            ])

        # Category listing cache (active elements)
        if category_id:
            patterns.extend([
                f"elements:category:{category_id}:active=True",
                f"elements:base:category:{category_id}:active=True",
            ])

        # Delete all patterns
        for pattern in patterns:
            try:
                result = await self.redis.delete(pattern)
                deleted += result
            except Exception as e:
                logger.warning(f"Failed to delete cache key '{pattern}': {e}")

        if deleted > 0:
            logger.debug(f"Invalidated {deleted} element cache keys")

        return deleted

    async def invalidate_element_children_cache(self, parent_id: str) -> int:
        """
        Invalidate cache for all children of a parent element.

        Args:
            parent_id: Parent element UUID

        Returns:
            Number of cache keys deleted
        """
        # NOTE: This requires querying DB to get child IDs
        # Implementation left to caller to avoid circular dependency
        # This is a placeholder for future enhancement
        logger.debug(f"Element children cache invalidation requested for parent {parent_id}")
        return 0

    async def invalidate_tier_elements_cache(self, tier_id: str) -> int:
        """
        Invalidate tier element inclusion cache.

        Args:
            tier_id: Tier UUID

        Returns:
            Number of cache keys deleted
        """
        deleted = 0
        pattern = f"tier_elements:{tier_id}"

        try:
            result = await self.redis.delete(pattern)
            deleted += result
            if result > 0:
                logger.debug(f"Invalidated tier elements cache: {pattern}")
        except Exception as e:
            logger.warning(f"Failed to delete tier elements cache '{pattern}': {e}")

        return deleted

    async def invalidate_tariff_cache(
        self,
        category_slug: str | None = None,
        client_type: Literal["particular", "professional"] | None = None,
    ) -> int:
        """
        Invalidate tariff-related cache keys.

        Args:
            category_slug: Optional category slug to invalidate specific tariff
            client_type: Optional client type to invalidate supported categories

        Returns:
            Number of cache keys deleted
        """
        deleted = 0
        patterns = []

        # Specific tariff cache
        if category_slug:
            patterns.extend([
                f"tariffs:{category_slug}",
                f"prompt:calculator:{category_slug}",
            ])

        # Supported categories cache
        if client_type:
            patterns.append(f"tariffs:supported:{client_type}")
        else:
            # Invalidate both if not specified
            patterns.extend([
                "tariffs:supported:particular",
                "tariffs:supported:professional",
            ])

        # Category listings cache
        patterns.extend([
            "tariffs:categories:all",
            "tariffs:categories:particular",
            "tariffs:categories:professional",
        ])

        # Delete all patterns
        for pattern in patterns:
            try:
                result = await self.redis.delete(pattern)
                deleted += result
            except Exception as e:
                logger.warning(f"Failed to delete tariff cache key '{pattern}': {e}")

        if deleted > 0:
            logger.debug(f"Invalidated {deleted} tariff cache keys")

        return deleted

    async def invalidate_all_element_caches(self) -> int:
        """
        Invalidate ALL element-related caches (use sparingly).

        Returns:
            Number of cache keys deleted
        """
        deleted = 0
        patterns = [
            "elements:*",
            "element:*",
            "tier_elements:*",
        ]

        for pattern in patterns:
            cursor = 0
            while True:
                try:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        result = await self.redis.delete(*keys)
                        deleted += result
                    if cursor == 0:
                        break
                except Exception as e:
                    logger.warning(f"Failed to scan/delete pattern '{pattern}': {e}")
                    break

        if deleted > 0:
            logger.info(f"Invalidated ALL element caches: {deleted} keys deleted")

        return deleted

    async def invalidate_all_tariff_caches(self) -> int:
        """
        Invalidate ALL tariff-related caches (use sparingly).

        Returns:
            Number of cache keys deleted
        """
        deleted = 0
        patterns = [
            "tariffs:*",
            "prompt:calculator:*",
        ]

        for pattern in patterns:
            cursor = 0
            while True:
                try:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        result = await self.redis.delete(*keys)
                        deleted += result
                    if cursor == 0:
                        break
                except Exception as e:
                    logger.warning(f"Failed to scan/delete pattern '{pattern}': {e}")
                    break

        if deleted > 0:
            logger.info(f"Invalidated ALL tariff caches: {deleted} keys deleted")

        return deleted


# Singleton instance
_cache_service: CacheService | None = None


def get_cache_service() -> CacheService:
    """
    Get the singleton CacheService instance.

    Returns:
        CacheService instance
    """
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
