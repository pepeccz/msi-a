"""
Phase 3 Tests: Redis Pub/Sub cache invalidation.

Tests the cross-container cache invalidation mechanism where:
- API publishes to ``msia:cache:invalidate:constraints`` on CRUD operations
- Agent subscribes and calls ``invalidate_cache()`` on receipt

Test groups:
1. Publisher tests (_invalidate_constraint_cache in api/routes/constraints.py)
2. Subscriber message handler tests (_handle_message, _invalidate_constraints)
3. Subscriber lifecycle tests (cache_invalidation_listener)
4. Dispatch logic tests (_invalidate_constraints)
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# 1. PUBLISHER TESTS (API side)
# ============================================================================


class TestConstraintCachePublisher:
    """Tests for _invalidate_constraint_cache() in api/routes/constraints.py."""

    @pytest.mark.asyncio
    async def test_publish_invalidation_message(self):
        """Should publish invalidate_all to Redis Pub/Sub channel."""
        # publish_to_channel is imported INSIDE _invalidate_constraint_cache,
        # so we must patch at source: shared.redis_client.publish_to_channel
        with patch(
            "shared.redis_client.publish_to_channel",
            new_callable=AsyncMock,
        ) as mock_publish:
            from api.routes.constraints import _invalidate_constraint_cache

            await _invalidate_constraint_cache()

            mock_publish.assert_called_once_with(
                "msia:cache:invalidate:constraints",
                {"action": "invalidate_all"},
            )

    @pytest.mark.asyncio
    async def test_publish_failure_is_non_fatal(self):
        """If Redis publish fails, should log warning but not raise."""
        with patch(
            "shared.redis_client.publish_to_channel",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            from api.routes.constraints import _invalidate_constraint_cache

            # Should NOT raise
            await _invalidate_constraint_cache()


# ============================================================================
# 2. SUBSCRIBER MESSAGE HANDLER TESTS (Agent side)
# ============================================================================


class TestHandleMessage:
    """Tests for _handle_message() in cache_subscriber.py."""

    @pytest.mark.asyncio
    async def test_handle_constraint_invalidation_all(self):
        """Should call invalidate_cache() with no args for invalidate_all."""
        # invalidate_cache is imported INSIDE _invalidate_constraints,
        # so we must patch at source: agent.services.constraint_service.invalidate_cache
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:constraints",
                "data": json.dumps({"action": "invalidate_all"}).encode(),
            })

            mock_invalidate.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_constraint_invalidation_category(self):
        """Should call invalidate_cache(category_slug=...) for category action."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:constraints",
                "data": json.dumps({
                    "action": "invalidate_category",
                    "category_slug": "motos-part",
                }).encode(),
            })

            mock_invalidate.assert_called_once_with(category_slug="motos-part")

    @pytest.mark.asyncio
    async def test_handle_unknown_action_invalidates_all(self):
        """Unknown actions should invalidate everything (safe fallback)."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:constraints",
                "data": json.dumps({"action": "unknown_action"}).encode(),
            })

            mock_invalidate.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_string_channel(self):
        """Channel can be string (not bytes) depending on Redis config."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": "msia:cache:invalidate:constraints",
                "data": json.dumps({"action": "invalidate_all"}).encode(),
            })

            mock_invalidate.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_malformed_json_data(self):
        """Malformed JSON data should not crash — invalidate all as fallback."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:constraints",
                "data": b"not-json",
            })

            # Empty data → action="" → falls to else → invalidate_cache()
            mock_invalidate.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_empty_data(self):
        """Empty data should still trigger invalidation."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:constraints",
                "data": None,
            })

            mock_invalidate.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handle_unknown_channel_ignored(self):
        """Messages on unknown channels should be silently ignored."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock_invalidate:
            from agent.services.cache_subscriber import _handle_message

            await _handle_message({
                "channel": b"msia:cache:invalidate:other_thing",
                "data": json.dumps({"action": "invalidate_all"}).encode(),
            })

            mock_invalidate.assert_not_called()


# ============================================================================
# 3. SUBSCRIBER LIFECYCLE TESTS
# ============================================================================


class TestCacheInvalidationListener:
    """Tests for the cache_invalidation_listener() background task."""

    @pytest.mark.asyncio
    async def test_listener_stops_on_shutdown_event(self):
        """Listener should stop cleanly when shutdown_event is set."""
        shutdown = asyncio.Event()

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        call_count = 0

        async def fake_get_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                shutdown.set()
            return None

        mock_pubsub.get_message = fake_get_message

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub

        with patch(
            "agent.services.cache_subscriber.get_redis_client",
            return_value=mock_client,
        ):
            from agent.services.cache_subscriber import cache_invalidation_listener

            await asyncio.wait_for(
                cache_invalidation_listener(shutdown),
                timeout=5.0,
            )

        mock_pubsub.subscribe.assert_called_once()
        mock_pubsub.unsubscribe.assert_called()

    @pytest.mark.asyncio
    async def test_listener_processes_message(self):
        """Listener should dispatch received messages to handler."""
        shutdown = asyncio.Event()

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        message_sent = False

        async def fake_get_message(**kwargs):
            nonlocal message_sent
            if not message_sent:
                message_sent = True
                return {
                    "type": "message",
                    "channel": b"msia:cache:invalidate:constraints",
                    "data": json.dumps({"action": "invalidate_all"}).encode(),
                }
            shutdown.set()
            return None

        mock_pubsub.get_message = fake_get_message

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub

        with patch(
            "agent.services.cache_subscriber.get_redis_client",
            return_value=mock_client,
        ), patch(
            "agent.services.cache_subscriber._handle_message",
            new_callable=AsyncMock,
        ) as mock_handler:
            from agent.services.cache_subscriber import cache_invalidation_listener

            await asyncio.wait_for(
                cache_invalidation_listener(shutdown),
                timeout=5.0,
            )

            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_listener_retries_on_redis_error(self):
        """On Redis error, should retry with backoff (not crash)."""
        shutdown = asyncio.Event()
        attempt = 0

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)

        mock_client = MagicMock()

        def create_pubsub():
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ConnectionError("Redis down")
            # Second attempt succeeds, then shutdown
            async def stop_after_one(**kwargs):
                shutdown.set()
                return None
            mock_pubsub.get_message = stop_after_one
            return mock_pubsub

        mock_client.pubsub = create_pubsub

        with patch(
            "agent.services.cache_subscriber.get_redis_client",
            return_value=mock_client,
        ):
            from agent.services.cache_subscriber import cache_invalidation_listener

            await asyncio.wait_for(
                cache_invalidation_listener(shutdown),
                timeout=10.0,
            )

        assert attempt >= 2, f"Expected retry, only got {attempt} attempts"


# ============================================================================
# 4. DISPATCH LOGIC TESTS (_invalidate_constraints)
# ============================================================================


class TestInvalidateConstraintsDispatch:
    """Tests for _invalidate_constraints() dispatch logic."""

    def test_invalidate_all(self):
        """action=invalidate_all should call invalidate_cache() with no args."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock:
            from agent.services.cache_subscriber import _invalidate_constraints

            _invalidate_constraints({"action": "invalidate_all"})
            mock.assert_called_once_with()

    def test_invalidate_category(self):
        """action=invalidate_category should pass category_slug."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock:
            from agent.services.cache_subscriber import _invalidate_constraints

            _invalidate_constraints({
                "action": "invalidate_category",
                "category_slug": "coches-part",
            })
            mock.assert_called_once_with(category_slug="coches-part")

    def test_invalidate_category_without_slug_falls_back(self):
        """invalidate_category without slug should fallback to invalidate_all."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock:
            from agent.services.cache_subscriber import _invalidate_constraints

            _invalidate_constraints({"action": "invalidate_category"})
            mock.assert_called_once_with()

    def test_empty_data_invalidates_all(self):
        """Empty dict should invalidate all as safe default."""
        with patch(
            "agent.services.constraint_service.invalidate_cache"
        ) as mock:
            from agent.services.cache_subscriber import _invalidate_constraints

            _invalidate_constraints({})
            mock.assert_called_once_with()
