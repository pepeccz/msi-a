"""
MSI Automotive - Process incoming message node.

This node handles incoming user messages and prepares the state
for the conversational agent. Also handles panic button interception
when the agent is disabled.
"""

import logging
from datetime import datetime, UTC
from typing import Any

import uuid

from sqlalchemy import select, and_, update

from agent.state.helpers import add_message
from agent.state.schemas import ConversationState

logger = logging.getLogger(__name__)


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
    is_first: bool,
) -> None:
    """
    Create or update ConversationHistory record in PostgreSQL.

    - First interaction: INSERT new record with message_count=1
    - Subsequent messages: UPDATE message_count += 1

    Args:
        conversation_id: Chatwoot conversation ID
        user_id: User UUID (can be None)
        is_first: True if this is the first message in the conversation
    """
    from database.connection import get_async_session
    from database.models import ConversationHistory

    try:
        async with get_async_session() as session:
            if is_first:
                # Create new ConversationHistory record
                history = ConversationHistory(
                    id=uuid.uuid4(),
                    conversation_id=conversation_id,
                    user_id=uuid.UUID(user_id) if user_id else None,
                    started_at=datetime.now(UTC),
                    message_count=1,
                    metadata_={},
                )
                session.add(history)
                await session.commit()
                logger.info(
                    f"ConversationHistory created | conversation_id={conversation_id}",
                    extra={
                        "event_type": "conversation_history_created",
                        "conversation_id": conversation_id,
                    },
                )
            else:
                # Update message_count for existing record
                stmt = (
                    update(ConversationHistory)
                    .where(ConversationHistory.conversation_id == conversation_id)
                    .values(message_count=ConversationHistory.message_count + 1)
                )
                result = await session.execute(stmt)
                await session.commit()

                # If no record was updated, create one (edge case: checkpoint exists but no DB record)
                if result.rowcount == 0:
                    history = ConversationHistory(
                        id=uuid.uuid4(),
                        conversation_id=conversation_id,
                        user_id=uuid.UUID(user_id) if user_id else None,
                        started_at=datetime.now(UTC),
                        message_count=1,
                        metadata_={},
                    )
                    session.add(history)
                    await session.commit()
                    logger.info(
                        f"ConversationHistory created (fallback) | conversation_id={conversation_id}",
                        extra={
                            "event_type": "conversation_history_created_fallback",
                            "conversation_id": conversation_id,
                        },
                    )

    except Exception as e:
        # Log error but don't fail the main flow
        logger.error(
            f"Error upserting ConversationHistory for conversation_id={conversation_id}: {e}",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )


async def process_incoming_message_node(state: ConversationState) -> dict[str, Any]:
    """
    Process incoming user message and update state.

    This node:
    1. Checks if agent is enabled (panic button)
    2. If disabled: sends auto-response and creates escalation
    3. Adds the user message to conversation history
    4. Detects if this is the first interaction
    5. Updates timestamps

    Args:
        state: Current conversation state

    Returns:
        State updates dict
    """
    from shared.settings_cache import get_cached_setting
    from shared.redis_client import publish_to_channel
    from shared.chatwoot_client import ChatwootClient

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
    # ESCALATION CHECK: Validate atencion_automatica from Chatwoot
    # =========================================================================
    # This is a double protection layer. If a conversation is escalated,
    # atencion_automatica should be False and we should not process messages.
    try:
        conv_id_int = int(conversation_id)
        chatwoot_client = ChatwootClient()

        conversation_data = await chatwoot_client.get_conversation(conv_id_int)
        atencion_automatica = conversation_data.get("custom_attributes", {}).get(
            "atencion_automatica"
        )

        if atencion_automatica is False:
            # Check if this is panic button scenario (agent_enabled = false)
            # In that case, we should still send auto-response, not block silently
            agent_enabled_check = await get_cached_setting("agent_enabled")

            if agent_enabled_check and agent_enabled_check.lower() == "false":
                # Panic button active - continue to panic button flow
                logger.info(
                    f"Conversation {conversation_id} has atencion_automatica=false due to "
                    f"panic button - continuing to auto-response flow",
                    extra={
                        "event_type": "panic_button_escalation_bypass",
                        "conversation_id": conversation_id,
                    },
                )
                # Continue processing - panic button check below will handle it
            else:
                # Normal escalation (manual via tool) - block processing
                logger.info(
                    f"Conversation {conversation_id} has atencion_automatica=false (escalated), "
                    "blocking message processing",
                    extra={
                        "event_type": "message_blocked_escalated",
                        "conversation_id": conversation_id,
                    },
                )

                # Don't respond - user was already notified when escalation was created
                return {
                    "messages": messages,
                    "escalated": True,
                    "last_node": "blocked_escalated",
                    "updated_at": datetime.now(UTC),
                }

    except ValueError:
        logger.warning(
            f"Invalid conversation_id format (not int): {conversation_id}"
        )
    except Exception as chatwoot_error:
        logger.warning(
            f"Could not verify atencion_automatica for conversation {conversation_id}: "
            f"{chatwoot_error}. Continuing with normal processing."
        )
        # Continue processing if verification fails - don't block messages on error

    # =========================================================================
    # PANIC BUTTON: Check if agent is enabled
    # =========================================================================
    agent_enabled = await get_cached_setting("agent_enabled")

    if agent_enabled and agent_enabled.lower() == "false":
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

    # =========================================================================
    # NORMAL FLOW: Process message normally
    # =========================================================================

    # Check if first interaction (no messages yet)
    is_first = len(messages) == 0

    # Add user message to history
    updated_messages = add_message(
        messages=messages,
        role="user",
        content=user_message,
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

    # Persist conversation history to PostgreSQL
    await upsert_conversation_history(
        conversation_id=conversation_id,
        user_id=state.get("user_id"),
        is_first=is_first,
    )

    return updates
