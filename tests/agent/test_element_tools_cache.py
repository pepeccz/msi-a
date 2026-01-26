"""Tests for category ID caching with Redis."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent.tools.element_tools import get_or_fetch_category_id


@pytest.mark.asyncio
class TestCategoryCacheRedis:
    """Test Redis-based category caching."""
    
    async def test_cache_hit_returns_cached_value(self):
        """When cache hits, should return cached value without DB query."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"uuid-123-456"
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug') as mock_db:
                result = await get_or_fetch_category_id("motos-part")
                
                assert result == "uuid-123-456"
                mock_redis.get.assert_called_once_with("category:slug:motos-part")
                mock_db.assert_not_called()  # DB should NOT be queried
    
    async def test_cache_miss_queries_db_and_caches(self):
        """When cache misses, should query DB and cache result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value="uuid-789"):
                result = await get_or_fetch_category_id("motos-part")
                
                assert result == "uuid-789"
                mock_redis.setex.assert_called_once_with(
                    "category:slug:motos-part",
                    300,  # TTL
                    "uuid-789"
                )
    
    async def test_redis_failure_falls_back_to_db(self):
        """When Redis fails, should fall back to DB gracefully."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection failed")
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value="uuid-fallback"):
                result = await get_or_fetch_category_id("motos-part")
                
                assert result == "uuid-fallback"
    
    async def test_cache_write_failure_does_not_break_flow(self):
        """When cache write fails, should still return DB result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("Redis write failed")
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value="uuid-999"):
                result = await get_or_fetch_category_id("motos-part")
                
                assert result == "uuid-999"  # Should still work
    
    async def test_cache_key_format(self):
        """Verify cache key follows expected format."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value="uuid-test"):
                await get_or_fetch_category_id("test-category")
                
                # Verify cache key format
                mock_redis.get.assert_called_with("category:slug:test-category")
    
    async def test_ttl_is_set_correctly(self):
        """Verify TTL is set to 5 minutes (300 seconds)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value="uuid-ttl"):
                await get_or_fetch_category_id("test-category")
                
                # Verify TTL argument
                call_args = mock_redis.setex.call_args
                assert call_args[0][1] == 300  # TTL is second argument
    
    async def test_none_result_is_not_cached(self):
        """When category is not found (None), should not cache the result."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug', return_value=None):
                result = await get_or_fetch_category_id("nonexistent")
                
                assert result is None
                mock_redis.setex.assert_not_called()  # Should NOT cache None
    
    async def test_decoded_utf8_properly(self):
        """Verify bytes from Redis are decoded as UTF-8."""
        mock_redis = AsyncMock()
        # Redis returns bytes
        mock_redis.get.return_value = "uuid-with-ñ".encode('utf-8')
        
        with patch('agent.tools.element_tools.get_redis_client', return_value=mock_redis):
            with patch('agent.tools.element_tools._get_category_id_by_slug') as mock_db:
                result = await get_or_fetch_category_id("test")
                
                assert result == "uuid-with-ñ"
                assert isinstance(result, str)
                mock_db.assert_not_called()
