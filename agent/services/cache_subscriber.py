"""
Redis Pub/Sub subscriber for cross-container cache invalidation.

Listens on ``msia:cache:invalidate:*`` channels so the agent process
can react instantly when the API container modifies cached data
(e.g. response constraints edited via admin panel).

Without this, constraint cache changes take up to 5 minutes to
propagate (the in-memory cache TTL).
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Channel patterns to subscribe to
CONSTRAINT_CHANNEL = "msia:cache:invalidate:constraints"


async def cache_invalidation_listener(shutdown_event: asyncio.Event) -> None:
    """Background task that subscribes to Redis Pub/Sub invalidation channels.

    Runs until *shutdown_event* is set.  On any transient Redis error the
    loop backs off exponentially (1 → 2 → 4 … 30 s) and retries, so a
    brief Redis hiccup doesn't kill the subscriber permanently.

    Args:
        shutdown_event: ``asyncio.Event`` signalled on agent shutdown.
    """
    backoff = 1

    while not shutdown_event.is_set():
        pubsub = None
        try:
            client = get_redis_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(CONSTRAINT_CHANNEL)
            logger.info(
                "Cache invalidation subscriber started",
                extra={"channel": CONSTRAINT_CHANNEL},
            )
            backoff = 1  # reset on successful connect

            while not shutdown_event.is_set():
                # get_message with a short timeout so we can check shutdown_event
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is not None:
                    await _handle_message(message)

        except asyncio.CancelledError:
            logger.info("Cache invalidation subscriber cancelled")
            break

        except Exception as e:
            logger.warning(
                f"Cache invalidation subscriber error, retrying in {backoff}s: {e}"
            )
            # Wait with shutdown check
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=backoff,
                )
                # If we reach here, shutdown was signalled during backoff
                break
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30)

        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(CONSTRAINT_CHANNEL)
                    await pubsub.close()
                except Exception:
                    pass

    logger.info("Cache invalidation subscriber stopped")


async def _handle_message(message: dict) -> None:
    """Dispatch a single Pub/Sub message to the right cache invalidator."""
    channel = message.get("channel")
    if isinstance(channel, bytes):
        channel = channel.decode()

    data_raw = message.get("data")
    if isinstance(data_raw, bytes):
        data_raw = data_raw.decode()

    try:
        data = json.loads(data_raw) if data_raw else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    logger.info(
        f"Cache invalidation received on '{channel}'",
        extra={"channel": channel, "data": data},
    )

    if channel == CONSTRAINT_CHANNEL:
        _invalidate_constraints(data)
    else:
        logger.debug(f"Unhandled invalidation channel: {channel}")


def _invalidate_constraints(data: dict) -> None:
    """Call the constraint service's cache invalidator."""
    from agent.services.constraint_service import invalidate_cache

    action = data.get("action", "invalidate_all")
    category_slug = data.get("category_slug")

    if action == "invalidate_all":
        invalidate_cache()
    elif action == "invalidate_category" and category_slug:
        invalidate_cache(category_slug=category_slug)
    else:
        # Unknown action — invalidate everything to be safe
        invalidate_cache()
