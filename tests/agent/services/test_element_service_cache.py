"""Tests for ElementService.get_element_by_code() Redis caching.

Covers:
- Cache miss → DB hit → result cached
- Cache hit → DB not queried
- Null sentinel hit → returns None without DB query
- Redis error → graceful fallback to DB
- DB miss → null sentinel cached

Run with: pytest tests/agent/services/test_element_service_cache.py -v
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agent.services.element_service import ElementService

FAKE_CATEGORY_ID = str(uuid4())
FAKE_ELEMENT_CODE = "BOLA_REMOLQUE"
EXPECTED_CACHE_KEY = f"elements:code:{FAKE_ELEMENT_CODE}:{FAKE_CATEGORY_ID}"
CACHE_TTL = 300  # Must match agent/services/element_service.py CACHE_TTL


def _make_fake_element(**overrides):
    """Create a mock SQLAlchemy Element with default attributes."""
    elem = MagicMock()
    elem.id = overrides.get("id", uuid4())
    elem.code = overrides.get("code", FAKE_ELEMENT_CODE)
    elem.name = overrides.get("name", "Bola de remolque")
    elem.description = overrides.get("description", "Desc")
    elem.keywords = overrides.get("keywords", ["bola", "remolque"])
    elem.question_hint = overrides.get("question_hint", "¿Qué tipo?")
    elem.multi_select_keywords = overrides.get("multi_select_keywords", [])
    elem.is_active = overrides.get("is_active", True)
    return elem


def _element_to_dict(elem):
    """Convert a mock element to the expected dict output."""
    return {
        "id": str(elem.id),
        "code": elem.code,
        "name": elem.name,
        "description": elem.description or "",
        "keywords": elem.keywords or [],
        "question_hint": elem.question_hint,
        "multi_select_keywords": elem.multi_select_keywords or [],
        "is_active": elem.is_active,
    }


def _make_service(mock_redis: AsyncMock) -> ElementService:
    """Create an ElementService with a mocked Redis client."""
    with patch("shared.redis_client.get_redis_client", return_value=mock_redis):
        service = ElementService()
    # Also directly set redis in case the import path differs
    service.redis = mock_redis
    return service


@pytest.mark.asyncio
class TestGetElementByCodeCache:
    """Test Redis caching in ElementService.get_element_by_code()."""

    async def test_cache_miss_db_hit_caches_result(self):
        """Cache miss → DB returns element → result is cached via setex."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss

        fake_elem = _make_fake_element()
        expected_dict = _element_to_dict(fake_elem)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_elem

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session",
            return_value=mock_session_ctx,
        ):
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result == expected_dict
        mock_redis.get.assert_called_once_with(EXPECTED_CACHE_KEY)
        mock_redis.setex.assert_called_once_with(
            EXPECTED_CACHE_KEY, CACHE_TTL, json.dumps(expected_dict)
        )

    async def test_cache_hit_returns_cached_no_db(self):
        """Cache hit → returns cached JSON, DB is NOT queried."""
        mock_redis = AsyncMock()
        cached_data = {
            "id": str(uuid4()),
            "code": FAKE_ELEMENT_CODE,
            "name": "Bola de remolque",
            "description": "Desc",
            "keywords": ["bola"],
            "question_hint": "¿Qué tipo?",
            "multi_select_keywords": [],
            "is_active": True,
        }
        mock_redis.get.return_value = json.dumps(cached_data).encode("utf-8")

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session"
        ) as mock_session_factory:
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result == cached_data
        mock_redis.get.assert_called_once_with(EXPECTED_CACHE_KEY)
        mock_session_factory.assert_not_called()  # DB never queried

    async def test_null_sentinel_returns_none_no_db(self):
        """Null sentinel b'null' in cache → returns None, DB is NOT queried."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"null"

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session"
        ) as mock_session_factory:
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result is None
        mock_redis.get.assert_called_once_with(EXPECTED_CACHE_KEY)
        mock_session_factory.assert_not_called()

    async def test_null_sentinel_string_variant(self):
        """Null sentinel as str 'null' (not bytes) also returns None."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "null"

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session"
        ) as mock_session_factory:
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result is None
        mock_session_factory.assert_not_called()

    async def test_redis_error_falls_back_to_db(self):
        """Redis.get raises exception → DB is queried and result returned."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection lost")

        fake_elem = _make_fake_element()
        expected_dict = _element_to_dict(fake_elem)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_elem

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session",
            return_value=mock_session_ctx,
        ):
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result == expected_dict
        # DB was queried despite Redis failure
        mock_session.execute.assert_called_once()

    async def test_db_miss_caches_null_sentinel(self):
        """Cache miss + DB miss → caches 'null' sentinel to prevent repeated misses."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # DB miss

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None

        service = _make_service(mock_redis)

        with patch(
            "agent.services.element_service.get_async_session",
            return_value=mock_session_ctx,
        ):
            result = await service.get_element_by_code(
                FAKE_ELEMENT_CODE, FAKE_CATEGORY_ID
            )

        assert result is None
        mock_redis.setex.assert_called_once_with(
            EXPECTED_CACHE_KEY, CACHE_TTL, "null"
        )
