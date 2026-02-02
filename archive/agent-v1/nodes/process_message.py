"""
MSI Automotive - Process incoming message node.

This node handles incoming user messages and prepares the state
for the conversational agent. Also handles panic button interception
when the agent is disabled.

Performance optimizations (2026-01):
- Removed redundant Chatwoot atencion_automatica check (already done in webhook)
- Parallelized independent I/O operations with asyncio.gather()
- Optimized upsert_conversation_history with ON CONFLICT DO UPDATE
"""

import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select, and_

from agent.state.helpers import add_message
from agent.state.schemas import ConversationState

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


async def create_escalation_if_needed(conversation_id: str, state: ConversationState) -> None:
    """
    Create an escalation if one doesn't already exist for this conversation.

    Only creates ONE escalation per conversation with source='agent_disabled'.
    Also updates Chatwoot to disable bot processing and notifies the user.

    Args:
        conversation_id: Chatwoot conversation ID
        state: Current conversation state
    """
    from database.connection import get_async_session
    from database.models import Escalation
    from shared.chatwoot_client import ChatwootClient

    try:
        async with get_async_session() as session:
            # Check if escalation already exists for this conversation
            result = await session.execute(
                select(Escalation)
                .where(
                    and_(
                        Escalation.conversation_id == conversation_id,
                        Escalation.source == "agent_disabled",
                        Escalation.status.in_(["pending", "in_progress"])
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.debug(
                    f"Escalation already exists for conversation_id={conversation_id}",
                    extra={"conversation_id": conversation_id},
                )
                return

            # Create new escalation
            escalation = Escalation(
                conversation_id=conversation_id,
                reason="Agente desactivado - Requiere atención humana",
                source="agent_disabled",
                status="pending",
                metadata_={"user_phone": state.get("user_phone")},
            )
            session.add(escalation)
            await session.commit()
            await session.refresh(escalation)

            logger.info(
                f"Escalation created | conversation_id={conversation_id}",
                extra={
                    "event_type": "escalation_created",
                    "conversation_id": conversation_id,
                    "source": "agent_disabled",
                },
            )

            # =================================================================
            # UPDATE CHATWOOT: Disable bot and notify user
            # =================================================================
            try:
                conv_id_int = int(conversation_id)
                chatwoot_client = ChatwootClient()

                # Step 1: Disable atencion_automatica to prevent further bot processing
                await chatwoot_client.update_conversation_attributes(
                    conversation_id=conv_id_int,
                    attributes={"atencion_automatica": False},
                )

                # Step 2: Send notification message to user
                escalation_message = (
                    "Tu consulta ha sido escalada a un agente humano que te "
                    "atenderá lo antes posible. Gracias por tu paciencia."
                )
                await chatwoot_client.send_message(
                    customer_phone=state.get("user_phone", ""),
                    message=escalation_message,
                    conversation_id=conv_id_int,
                )

                # Step 3: Add "escalado" label (best-effort)
                try:
                    await chatwoot_client.add_labels(
                        conversation_id=conv_id_int,
                        labels=["escalado"],
                    )
                except Exception as label_error:
                    logger.warning(
                        f"Could not add label to conversation {conv_id_int}: {label_error}"
                    )

                # Step 4: Add private note with context (best-effort)
                try:
                    note = (
                        f"ESCALACION POR PANIC BUTTON\n"
                        f"---\n"
                        f"El agente ha sido desactivado globalmente.\n"
                        f"Usuario: {state.get('user_phone')}\n"
                        f"Escalation ID: {escalation.id}\n"
                        f"Timestamp: {datetime.now(UTC).isoformat()}\n"
                    )
                    await chatwoot_client.add_private_note(
                        conversation_id=conv_id_int,
                        note=note,
                    )
                except Exception as note_error:
                    logger.warning(
                        f"Could not add note to conversation {conv_id_int}: {note_error}"
                    )

                logger.info(
                    f"Chatwoot updated for escalation | conversation_id={conversation_id}",
                    extra={
                        "event_type": "escalation_chatwoot_updated",
                        "conversation_id": conversation_id,
                        "atencion_automatica": False,
                    },
                )

            except ValueError:
                logger.error(
                    f"Invalid conversation_id format: {conversation_id} (must be int)"
                )
            except Exception as chatwoot_error:
                logger.error(
                    f"Failed to update Chatwoot for conversation {conversation_id}: "
                    f"{chatwoot_error}",
                    extra={"conversation_id": conversation_id, "error": str(chatwoot_error)},
                )

    except Exception as e:
        logger.error(
            f"Error creating escalation for conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )


async def upsert_conversation_history(
    conversation_id: str,
    user_id: str | None,
) -> None:
    """
    Create or update ConversationHistory record in PostgreSQL using atomic upsert.

    Uses PostgreSQL ON CONFLICT DO UPDATE for atomic operation:
    - Single round-trip to database
    - No race conditions
    - Guaranteed consistency

    Requires unique constraint on conversation_id (migration 032).

    Args:
        conversation_id: Chatwoot conversation ID
        user_id: User UUID (can be None)
    """
    from sqlalchemy.dialects.postgresql import insert
    from database.connection import get_async_session
    from database.models import ConversationHistory

    try:
        async with get_async_session() as session:
            # Atomic upsert using ON CONFLICT DO UPDATE
            stmt = insert(ConversationHistory).values(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                user_id=uuid.UUID(user_id) if user_id else None,
                started_at=datetime.now(UTC),
                message_count=1,
                metadata_={},
            ).on_conflict_do_update(
                constraint="uq_conversation_history_conversation_id",
                set_={"message_count": ConversationHistory.message_count + 1},
            )
            await session.execute(stmt)
            await session.commit()

    except Exception as e:
        # Log error but don't fail the main flow
        logger.error(
            f"Error upserting ConversationHistory for conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )


async def handle_panic_button(
    conversation_id: str,
    state: ConversationState,
    messages: list,
) -> dict[str, Any]:
    """
    Handle panic button scenario when agent is globally disabled.

    Sends auto-response message and creates escalation.

    Args:
        conversation_id: Chatwoot conversation ID
        state: Current conversation state
        messages: Current message list

    Returns:
        State updates dict for panic button response
    """
    from shared.settings_cache import get_cached_setting
    from shared.redis_client import publish_to_channel

    logger.warning(
        f"Agent disabled - auto-responding | conversation_id={conversation_id}",
        extra={
            "event_type": "agent_disabled",
            "conversation_id": conversation_id,
        },
    )

    # Get the auto-response message
    disabled_message = await get_cached_setting("agent_disabled_message")
    if not disabled_message:
        disabled_message = (
            "Disculpa las molestias. Nuestro asistente automático está "
            "temporalmente deshabilitado. Un agente humano te atenderá lo antes posible."
        )

    # Publish auto-response
    await publish_to_channel(
        "outgoing_messages",
        {
            "conversation_id": conversation_id,
            "customer_phone": state.get("user_phone"),
            "message": disabled_message,
        },
    )

    # Create escalation (only one per conversation)
    await create_escalation_if_needed(conversation_id, state)

    # Return early - skip conversational agent
    return {
        "messages": messages,  # Don't add user message
        "agent_disabled": True,
        "pending_images": [],  # Clear images from previous invocations
        "last_node": "agent_disabled_response",
        "updated_at": datetime.now(UTC),
    }


# =============================================================================
# MAIN NODE FUNCTION
# =============================================================================


async def process_incoming_message_node(state: ConversationState) -> dict[str, Any]:
    """
    Process incoming user message and update state.

    This node:
    1. Checks if agent is enabled (panic button) - parallelized with DB upsert
    2. If disabled: sends auto-response and creates escalation
    3. Adds the user message to conversation history
    4. Detects if this is the first interaction
    5. Updates timestamps

    Performance notes:
    - Chatwoot atencion_automatica check removed (already done in webhook)
    - Panic button check and DB upsert run in parallel
    - Upsert uses ON CONFLICT for single round-trip

    Args:
        state: Current conversation state

    Returns:
        State updates dict
    """
    from shared.settings_cache import get_cached_setting

    conversation_id = state.get("conversation_id", "unknown")
    user_message = state.get("user_message", "")
    messages = state.get("messages", [])
    total_count = state.get("total_message_count", 0)

    logger.info(
        f"Processing incoming message | conversation_id={conversation_id}",
        extra={
            "conversation_id": conversation_id,
            "message_length": len(user_message) if user_message else 0,
        },
    )

    # =========================================================================
    # PARALLEL I/O: Check panic button + Upsert conversation history + Save message
    # =========================================================================
    # These operations are independent and can run concurrently
    from api.services.message_persistence_service import save_user_message
    
    # Extract attachment info for message persistence
    incoming_attachments = state.get("incoming_attachments", [])
    has_images = any(att.get("file_type") == "image" for att in incoming_attachments)
    image_count = sum(1 for att in incoming_attachments if att.get("file_type") == "image")
    
    # Extract chatwoot_message_id if available (for correlation)
    # Note: This would need to be passed through the state if available from webhook
    chatwoot_message_id = state.get("chatwoot_message_id")
    
    agent_enabled, _, _ = await asyncio.gather(
        get_cached_setting("agent_enabled"),
        upsert_conversation_history(
            conversation_id=conversation_id,
            user_id=state.get("user_id"),
        ),
        save_user_message(
            conversation_id=conversation_id,
            content=user_message or "",
            chatwoot_message_id=chatwoot_message_id,
            has_images=has_images,
            image_count=image_count,
            user_id=state.get("user_id"),
        ),
    )

    # =========================================================================
    # PANIC BUTTON: Check if agent is enabled
    # =========================================================================
    if agent_enabled and agent_enabled.lower() == "false":
        return await handle_panic_button(conversation_id, state, messages)

    # =========================================================================
    # NORMAL FLOW: Process message normally
    # =========================================================================

    # Check if first interaction (no messages yet)
    is_first = len(messages) == 0

    # Add user message to history
    updated_messages = add_message(
        messages=messages,
        role="user",
        content=user_message or "",
    )

    # Prepare state updates
    updates: dict[str, Any] = {
        "messages": updated_messages,
        "total_message_count": total_count + 1,
        "is_first_interaction": is_first,
        "agent_disabled": False,  # Clear stale flag from checkpoint
        "pending_images": [],  # Clear images from previous invocations to prevent duplicates
        "updated_at": datetime.now(UTC),
        "last_node": "process_incoming_message",
    }

    # Set initial state if first interaction
    if is_first:
        updates["current_state"] = "greeting"
        updates["created_at"] = datetime.now(UTC)
        logger.info(
            f"First interaction detected | conversation_id={conversation_id}",
            extra={"conversation_id": conversation_id},
        )

    return updates
