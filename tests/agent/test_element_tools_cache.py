"""Tests for category ID caching with Redis.

These tests verify get_or_fetch_category_id() caching behavior.
The function lives in agent.services.element_service (moved from element_tools in T2.2a).
Backward-compat import from agent.tools.element_tools is also verified.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.services.element_service import get_or_fetch_category_id


# Helper: build a mock session that returns a category with the given id
def _make_category_mock(category_id: str | None):
    if category_id is None:
        return None
    cat = MagicMock()
    cat.id = category_id
    return cat


@pytest.mark.asyncio
class TestCategoryCacheRedis:
    """Test Redis-based category caching in element_service.get_or_fetch_category_id."""

    async def test_cache_hit_returns_cached_value(self):
        """When cache hits, should return cached value without DB query."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"uuid-123-456"

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session") as mock_session:
                result = await get_or_fetch_category_id("motos-part")

                assert result == "uuid-123-456"
                mock_redis.get.assert_called_once_with("category:slug:motos-part")
                mock_session.assert_not_called()  # DB should NOT be queried

    async def test_cache_miss_queries_db_and_caches(self):
        """When cache misses, should query DB and cache result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss

        mock_cat = MagicMock()
        mock_cat.id = "uuid-789"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cat
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("motos-part")

                assert result == "uuid-789"
                mock_redis.setex.assert_called_once_with("category:slug:motos-part", 300, "uuid-789")

    async def test_redis_failure_falls_back_to_db(self):
        """When Redis fails, should fall back to DB gracefully."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")

        mock_cat = MagicMock()
        mock_cat.id = "uuid-fallback"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cat
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("motos-part")

                assert result == "uuid-fallback"

    async def test_cache_write_failure_does_not_break_flow(self):
        """When cache write fails, should still return DB result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("Redis write failed")

        mock_cat = MagicMock()
        mock_cat.id = "uuid-999"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cat
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("motos-part")

                assert result == "uuid-999"  # Should still work

    async def test_cache_key_format(self):
        """Verify cache key follows expected format."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_cat = MagicMock()
        mock_cat.id = "uuid-test"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cat
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                await get_or_fetch_category_id("test-category")

                mock_redis.get.assert_called_with("category:slug:test-category")

    async def test_ttl_is_set_correctly(self):
        """Verify TTL is set to 5 minutes (300 seconds)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_cat = MagicMock()
        mock_cat.id = "uuid-ttl"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cat
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                await get_or_fetch_category_id("test-category")

                call_args = mock_redis.setex.call_args
                assert call_args[0][1] == 300  # TTL is second positional argument

    async def test_none_result_is_not_cached(self):
        """When category is not found (None), should not cache the result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Not found
        mock_session_instance = AsyncMock()
        mock_session_instance.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("nonexistent")

                assert result is None
                mock_redis.setex.assert_not_called()  # Should NOT cache None

    async def test_decoded_utf8_properly(self):
        """Verify bytes from Redis are decoded as UTF-8."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "uuid-with-ñ".encode("utf-8")

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session") as mock_session:
                result = await get_or_fetch_category_id("test")

                assert result == "uuid-with-ñ"
                assert isinstance(result, str)
                mock_session.assert_not_called()

    async def test_backward_compat_import_from_element_tools(self):
        """Verify get_or_fetch_category_id is still importable from element_tools (re-export)."""
        from agent.tools.element_tools import get_or_fetch_category_id as fn_from_tools
        from agent.services.element_service import get_or_fetch_category_id as fn_from_svc

        # Same function object (re-export, not a copy)
        assert fn_from_tools is fn_from_svc
