"""
Unit tests for ChatwootClient.list_whatsapp_templates (T07).

TDD cycle: RED → GREEN → REFACTOR

Covers:
  T07.1 - cache miss → fetch + cache
  T07.2 - cache hit → no fetch
  T07.3 - cache invalidation → fetch again
  T07.4 - response mapping (Chatwoot raw → uniform schema)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_template(
    *,
    name: str = "bienvenida",
    language: str = "es",
    status: str = "approved",
    category: str = "UTILITY",
    components: list[dict] | None = None,
) -> dict:
    """Raw Chatwoot API template shape (snake_case)."""
    return {
        "name": name,
        "language": language,
        "status": status,
        "category": category,
        "components": components or [
            {"type": "BODY", "text": "Hola {{1}}, ¿en qué podemos ayudarte?"},
        ],
    }


def _make_chatwoot_response(templates: list[dict]) -> dict:
    """Wrap templates in Chatwoot list response envelope."""
    return {"message_templates": templates}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)       # cache miss by default
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def chatwoot_client(mock_redis: AsyncMock):
    """ChatwootClient with Redis injected and HTTP patched."""
    with (
        patch("shared.chatwoot_client.get_settings") as mock_settings,
        patch("shared.chatwoot_client.get_error_logger") as mock_error_logger,
    ):
        mock_settings.return_value = MagicMock(
            CHATWOOT_API_URL="https://chatwoot.test",
            CHATWOOT_API_TOKEN="test-token",
            CHATWOOT_PLATFORM_TOKEN="plat-token",
            CHATWOOT_ACCOUNT_ID=1,
            CHATWOOT_INBOX_ID=42,
            CHATWOOT_IMAGE_SEND_DELAY_SECONDS=0,
        )
        mock_error_logger.return_value = MagicMock()

        from shared.chatwoot_client import ChatwootClient

        client = ChatwootClient()
        client._redis = mock_redis
        return client


# ---------------------------------------------------------------------------
# T07.1 — cache miss → fetch + cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_templates_cache_miss_fetches_and_caches(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """On cache miss the method fetches from Chatwoot and stores result in Redis."""
    raw_templates = [
        _make_raw_template(name="bienvenida", status="approved"),
        _make_raw_template(name="recordatorio", status="approved"),
    ]
    api_response = _make_chatwoot_response(raw_templates)

    mock_redis.get.return_value = None  # cache miss

    with patch("httpx.AsyncClient") as mock_http_cls:
        mock_http = AsyncMock()
        mock_http_cls.return_value.__aenter__.return_value = mock_http

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await chatwoot_client.list_whatsapp_templates(inbox_id=42)

    assert len(result) == 2
    assert result[0]["name"] == "bienvenida"
    assert result[1]["name"] == "recordatorio"

    # Redis setex should have been called to cache the result
    mock_redis.setex.assert_awaited_once()
    call_args = mock_redis.setex.call_args
    cache_key = call_args[0][0]
    assert "42" in cache_key
    ttl = call_args[0][1]
    assert ttl == 3600  # default 1h


# ---------------------------------------------------------------------------
# T07.2 — cache hit → no HTTP fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_templates_cache_hit_skips_fetch(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """On cache hit the method returns cached data without calling Chatwoot API."""
    cached_templates = [
        {"name": "bienvenida", "language": "es", "category": "UTILITY", "components": []},
    ]
    mock_redis.get.return_value = json.dumps(cached_templates).encode()

    with patch("httpx.AsyncClient") as mock_http_cls:
        mock_http = AsyncMock()
        mock_http_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get = AsyncMock()

        result = await chatwoot_client.list_whatsapp_templates(inbox_id=42)

    assert len(result) == 1
    assert result[0]["name"] == "bienvenida"

    # HTTP must NOT have been called
    mock_http.get.assert_not_called()
    # setex must NOT have been called (no new cache write)
    mock_redis.setex.assert_not_awaited()


# ---------------------------------------------------------------------------
# T07.3 — cache invalidation → next call fetches again
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalidate_templates_cache_deletes_key(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """invalidate_templates_cache deletes the Redis key for that inbox."""
    await chatwoot_client.invalidate_templates_cache(inbox_id=42)

    mock_redis.delete.assert_awaited_once()
    deleted_key: str = mock_redis.delete.call_args[0][0]
    assert "42" in deleted_key


@pytest.mark.asyncio
async def test_list_templates_after_invalidation_fetches(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """After invalidation, cache miss leads to new HTTP fetch."""
    # Simulate: Redis returns None (simulating post-invalidation state)
    mock_redis.get.return_value = None

    raw_templates = [_make_raw_template(name="nueva")]
    api_response = _make_chatwoot_response(raw_templates)

    with patch("httpx.AsyncClient") as mock_http_cls:
        mock_http = AsyncMock()
        mock_http_cls.return_value.__aenter__.return_value = mock_http

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await chatwoot_client.list_whatsapp_templates(inbox_id=42)

    assert len(result) == 1
    assert result[0]["name"] == "nueva"
    mock_http.get.assert_awaited_once()


# ---------------------------------------------------------------------------
# T07.4 — response mapping (raw → uniform schema)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_templates_maps_to_uniform_schema(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """Each template in the result has the uniform schema: name, language, category, components."""
    raw = _make_raw_template(
        name="oferta_especial",
        language="es_ES",
        status="approved",
        category="MARKETING",
        components=[
            {"type": "HEADER", "text": "Oferta especial"},
            {"type": "BODY", "text": "Estimado {{1}}, tenemos una oferta..."},
        ],
    )
    mock_redis.get.return_value = None

    with patch("httpx.AsyncClient") as mock_http_cls:
        mock_http = AsyncMock()
        mock_http_cls.return_value.__aenter__.return_value = mock_http

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_chatwoot_response([raw])
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await chatwoot_client.list_whatsapp_templates(inbox_id=42)

    assert len(result) == 1
    t = result[0]
    assert t["name"] == "oferta_especial"
    assert t["language"] == "es_ES"
    assert t["category"] == "MARKETING"
    assert isinstance(t["components"], list)
    assert len(t["components"]) == 2
    # Uniform schema: no extra raw fields that aren't part of the contract
    assert "name" in t
    assert "language" in t
    assert "category" in t
    assert "components" in t


@pytest.mark.asyncio
async def test_list_templates_use_cache_false_bypasses_cache(
    chatwoot_client, mock_redis: AsyncMock
) -> None:
    """use_cache=False always fetches from Chatwoot even if cache is warm."""
    # Cache is warm
    cached = [{"name": "viejo", "language": "es", "category": "UTILITY", "components": []}]
    mock_redis.get.return_value = json.dumps(cached).encode()

    fresh = [_make_raw_template(name="nuevo")]

    with patch("httpx.AsyncClient") as mock_http_cls:
        mock_http = AsyncMock()
        mock_http_cls.return_value.__aenter__.return_value = mock_http

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_chatwoot_response(fresh)
        mock_response.raise_for_status = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await chatwoot_client.list_whatsapp_templates(inbox_id=42, use_cache=False)

    assert result[0]["name"] == "nuevo"
    mock_http.get.assert_awaited_once()
