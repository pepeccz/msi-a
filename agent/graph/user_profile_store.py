"""
MSI-a — User Profile Store for cross-thread memory.

Provides a LangGraph Store instance for persisting user profile data
across conversation threads. When a checkpoint TTL expires, the user's
profile (name, client type, past quotes, past expedientes) survives and
is loaded at the start of the next conversation.

Part of WS3: refactor-memory-system.

Backend: AsyncPostgresStore (production) with InMemoryStore fallback (dev).
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

import structlog
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

logger = structlog.get_logger(__name__)

# Namespace constants
NS_USERS = "users"
PROFILE_KEY = "profile"

# Try to import AsyncPostgresStore — available in Docker (libpq installed),
# falls back to InMemoryStore in local dev where libpq is not present.
_AsyncPostgresStore = None
try:
    from langgraph.store.postgres import AsyncPostgresStore as _AsyncPostgresStore  # type: ignore[assignment]
except ImportError:
    pass


async def create_user_store() -> BaseStore:
    """
    Create and return a Store instance for user profile persistence.

    Uses AsyncPostgresStore when available (production/Docker), falls back
    to InMemoryStore for local development. The PostgreSQL store uses the
    same DATABASE_URL as the rest of the application — converted from
    asyncpg to psycopg format for compatibility.

    NOTE: AsyncPostgresStore.from_conn_string() returns an async context
    manager. We enter it and keep the reference alive — the store stays
    open for the lifetime of the process (agent runs until shutdown).
    """
    if _AsyncPostgresStore is not None:
        try:
            from shared.config import get_settings

            settings = get_settings()
            # Convert asyncpg URL to psycopg format:
            # postgresql+asyncpg://user:pass@host/db → postgresql://user:pass@host/db
            conn_string = settings.DATABASE_URL.replace("+asyncpg", "")
            # Use a connection pool instead of a single raw connection.
            # The pool auto-detects broken connections and replaces them,
            # surviving PostgreSQL restarts and Docker networking events.
            ctx = _AsyncPostgresStore.from_conn_string(
                conn_string,
                pool_config={"min_size": 1, "max_size": 3},
            )
            store = await ctx.__aenter__()
            # setup() creates the `store` table if it doesn't exist
            await store.setup()
            logger.info("user_profile_store_created", backend="AsyncPostgresStore")
            return store
        except Exception:
            logger.warning(
                "postgres_store_init_failed_falling_back_to_memory",
                exc_info=True,
            )

    store = InMemoryStore()
    logger.info("user_profile_store_created", backend="InMemoryStore")
    return store


async def load_user_profile(
    store: BaseStore,
    user_phone: str,
) -> dict[str, Any] | None:
    """
    Load a user profile from the Store.

    Args:
        store: LangGraph Store instance.
        user_phone: User phone number (E.164 format), used as namespace key.

    Returns:
        Profile dict or None if no profile exists.
    """
    if not store or not user_phone:
        return None

    try:
        item = await store.aget((NS_USERS, user_phone), PROFILE_KEY)
        if item:
            logger.debug(
                "user_profile_loaded",
                user_phone=user_phone,
                profile_keys=list(item.value.keys()),
            )
            return item.value
    except Exception:
        logger.warning("user_profile_load_failed", user_phone=user_phone, exc_info=True)

    return None


async def save_user_profile(
    store: BaseStore,
    user_phone: str,
    state: dict[str, Any],
) -> None:
    """
    Upsert user profile data to the Store.

    Extracts relevant persistent data from the conversation state and
    saves it to the Store under the user's phone namespace. Merges with
    existing profile data (doesn't overwrite).

    Args:
        store: LangGraph Store instance.
        user_phone: User phone number (E.164 format).
        state: Current ConversationState dict.
    """
    if not store or not user_phone:
        return

    try:
        # Load existing profile to merge
        existing = await load_user_profile(store, user_phone)
        profile = existing or {}

        now = datetime.now(UTC).isoformat()

        # Update identity fields
        user_name = state.get("user_name")
        if user_name:
            profile["user_name"] = user_name

        client_type = state.get("client_type")
        if client_type:
            profile["client_type"] = client_type

        user_id = state.get("user_id")
        if user_id:
            profile["user_id"] = user_id

        # Track quote history (last 5)
        mc = state.get("mode_context") or {}
        tarifa = mc.get("tarifa_calculada")
        if tarifa and mc.get("precio_comunicado"):
            quotes = profile.get("past_quotes", [])
            datos = tarifa.get("datos", tarifa)
            quote_entry = {
                "price": datos.get("price") or datos.get("precio"),
                "elements": mc.get("element_codes", []),
                "date": now,
            }
            # Avoid duplicate (same elements same price)
            if not quotes or quotes[-1].get("elements") != quote_entry["elements"]:
                quotes.append(quote_entry)
                profile["past_quotes"] = quotes[-5:]  # Keep last 5

        # Track expediente history (last 3)
        case_id = mc.get("case_id")
        if case_id:
            expedientes = profile.get("past_expedientes", [])
            if not any(e.get("case_id") == case_id for e in expedientes):
                expedientes.append({
                    "case_id": case_id,
                    "elements": mc.get("element_codes", []),
                    "date": now,
                })
                profile["past_expedientes"] = expedientes[-3:]  # Keep last 3

        # Timestamps
        if "first_seen" not in profile:
            profile["first_seen"] = now
        profile["last_seen"] = now

        await store.aput((NS_USERS, user_phone), PROFILE_KEY, profile)

        logger.debug(
            "user_profile_saved",
            user_phone=user_phone,
            profile_keys=list(profile.keys()),
        )

    except Exception:
        # Fire-and-forget: never block the conversation
        logger.warning("user_profile_save_failed", user_phone=user_phone, exc_info=True)
