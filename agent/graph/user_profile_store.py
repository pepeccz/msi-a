"""
MSI-a — User Profile Store for cross-thread memory.

Provides a LangGraph Store instance for persisting user profile data
across conversation threads. When a checkpoint TTL expires, the user's
profile (name, client type, past quotes, past expedientes) survives and
is loaded at the start of the next conversation.

Part of WS3: refactor-memory-system.

Current backend: InMemoryStore (development).
Production TODO: Swap to AsyncPostgresStore when langgraph-checkpoint-postgres is installed.
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


def create_user_store() -> BaseStore:
    """
    Create and return a Store instance for user profile persistence.

    Returns InMemoryStore for now. Production will use AsyncPostgresStore.
    """
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
