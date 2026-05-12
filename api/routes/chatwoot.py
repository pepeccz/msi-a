"""
MSI Automotive - Chatwoot webhook route handler.

Receives WhatsApp messages from Chatwoot and enqueues them for processing
by the AI agent.

Persistence/publish separation (CAP-09, design D8):
  - ConversationMessage + last_inbound_at are persisted ALWAYS for every inbound.
  - Publishing to the Redis Stream is gated: only when atencion_automatica=True
    AND the conversation's bot_paused_at IS NULL.
  - If DB persistence fails, the handler returns 500 (this is a bug, not normal).
  - If persistence succeeds but the gate blocks publish, 200 is returned with
    status="persisted_no_publish".
"""

import hmac
import json
import logging
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from sqlalchemy import select

from api.models.chatwoot_webhook import (
    ChatwootAttachmentEvent,
    ChatwootMessageEvent,
    ChatwootWebhookPayload,
)
from database.connection import get_async_session
from database.models import ConversationHistory, ConversationMessage, User
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import (
    ATTACHMENT_DOWNLOADS_STREAM,
    INCOMING_STREAM,
    add_to_stream,
    get_redis_client,
    publish_to_channel,
)
from shared.logging_config import sanitize_phone
from shared.text_utils import sanitize_user_input

logger = logging.getLogger(__name__)

router = APIRouter()

IDEMPOTENCY_TTL = 300  # 5 minutes
IDEMPOTENCY_PREFIX = "idempotency:chatwoot:"


async def check_and_set_idempotency(message_id: int) -> bool:
    """
    Check if a message has already been processed (idempotency guard).

    Returns True if the message is a duplicate (already processed).
    Returns False if the message is new and should be processed.
    """
    client = get_redis_client()
    key = f"{IDEMPOTENCY_PREFIX}{message_id}"

    was_set = await client.setnx(key, "1")
    if was_set:
        await client.expire(key, IDEMPOTENCY_TTL)
        return False

    logger.info(f"Duplicate message detected: {message_id}")
    return True


@router.post("/chatwoot/{token}")
async def receive_chatwoot_webhook(
    request: Request,
    token: str,
) -> JSONResponse:
    """
    Receive and process Chatwoot webhook events.

    Authentication: Token in URL path must match CHATWOOT_WEBHOOK_TOKEN.
    Configure in Chatwoot: https://your-domain.com/webhook/chatwoot/{your_secret_token}

    Persistence always runs for every inbound message (message_type=0).
    Publishing to Redis Stream is gated by atencion_automatica AND NOT bot_paused_at.

    Returns:
        JSONResponse 200 always (except 500 on DB failure).

    Raises:
        HTTPException 401: Invalid or missing token.
        HTTPException 400: Invalid payload format.
        JSONResponse 500: DB persistence failure (requires investigation).
    """
    settings = get_settings()

    if not hmac.compare_digest(token, settings.CHATWOOT_WEBHOOK_TOKEN):
        logger.warning(
            f"Invalid Chatwoot webhook token attempted from IP: {request.client.host}"
        )
        raise HTTPException(status_code=401, detail="Invalid token")

    body = await request.body()
    body_str = body.decode("utf-8")
    logger.info(
        "webhook_received",
        extra={"payload_length": len(body_str)},
    )
    logger.debug(
        "webhook_payload_debug",
        extra={
            "payload_length": len(body_str),
            "payload_hint": body_str[:80],
        },
    )

    try:
        payload = ChatwootWebhookPayload.model_validate_json(body)
    except Exception as e:
        logger.error(
            f"Failed to parse webhook payload: {e}",
            exc_info=True,
            extra={"payload_preview": body_str[:80], "payload_length": len(body_str)},
        )
        raise HTTPException(status_code=400, detail=f"Invalid payload format: {str(e)}")

    if payload.event != "message_created":
        logger.debug(f"Ignoring non-message event: {payload.event}")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    if not payload.conversation.messages:
        logger.debug(f"Ignoring conversation {payload.conversation.id} with no messages")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    last_message = payload.conversation.messages[-1]

    if last_message.message_type != 0:
        logger.debug(
            f"Ignoring non-incoming message: message_type={last_message.message_type}"
        )
        return JSONResponse(status_code=200, content={"status": "ignored"})

    if await check_and_set_idempotency(last_message.id):
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    if not payload.sender.phone_number:
        logger.warning(f"Message {last_message.id} has no phone number, ignoring")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # -------------------------------------------------------------------------
    # Step 1: Resolve atencion_automatica=None (first message) BEFORE persisting.
    # The panic_button check must run before we decide what to publish.
    # The actual gate decision (step 4) uses the value AFTER this resolution.
    # -------------------------------------------------------------------------
    atencion_automatica = payload.conversation.custom_attributes.get("atencion_automatica")

    if atencion_automatica is None:
        from shared.settings_cache import get_cached_setting

        agent_enabled = await get_cached_setting("agent_enabled")

        if agent_enabled and agent_enabled.lower() == "false":
            logger.warning(
                f"First message for conversation {payload.conversation.id}: "
                "agent disabled (panic button), setting atencion_automatica=false",
                extra={
                    "event_type": "panic_button_first_message",
                    "conversation_id": str(payload.conversation.id),
                    "customer_phone": sanitize_phone(payload.sender.phone_number),
                },
            )
            try:
                chatwoot_client = ChatwootClient()
                await chatwoot_client.update_conversation_attributes(
                    conversation_id=payload.conversation.id,
                    attributes={"atencion_automatica": False},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to set atencion_automatica=false for conversation "
                    f"{payload.conversation.id}: {e}",
                    exc_info=True,
                )
            # Resolved: treat as False for the gate decision below
            atencion_automatica = False

        else:
            logger.info(
                f"First message for conversation {payload.conversation.id}: "
                "setting atencion_automatica=true",
                extra={
                    "conversation_id": str(payload.conversation.id),
                    "customer_phone": sanitize_phone(payload.sender.phone_number),
                },
            )
            try:
                chatwoot_client = ChatwootClient()
                await chatwoot_client.update_conversation_attributes(
                    conversation_id=payload.conversation.id,
                    attributes={"atencion_automatica": True},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to set atencion_automatica=true for conversation "
                    f"{payload.conversation.id}: {e}",
                    exc_info=True,
                )
            atencion_automatica = True

    # -------------------------------------------------------------------------
    # Step 2: Sanitize message text.
    # -------------------------------------------------------------------------
    message_text = sanitize_user_input(last_message.content or "")

    # -------------------------------------------------------------------------
    # Step 3: Persist User + ConversationHistory + ConversationMessage ALWAYS.
    # Updates last_inbound_at and last_message_at on every inbound.
    # If this step fails → return 500 (persistence failure is a bug).
    # -------------------------------------------------------------------------
    user_id: str | None = None
    conv_history: ConversationHistory | None = None

    try:
        async with get_async_session() as session:
            # --- User: get or create ---
            result = await session.execute(
                select(User).where(User.phone == payload.sender.phone_number)
            )
            existing_user = result.scalar()

            whatsapp_name = payload.sender.name or ""
            name_parts = whatsapp_name.split(" ", 1) if whatsapp_name else []
            first_name = name_parts[0] if name_parts else None
            last_name = name_parts[1] if len(name_parts) > 1 else None

            tipo_chatwoot = payload.conversation.custom_attributes.get("tipo")
            if tipo_chatwoot == "Profesional":
                client_type_from_chatwoot = "professional"
            elif tipo_chatwoot == "Particular":
                client_type_from_chatwoot = "particular"
            else:
                client_type_from_chatwoot = None

            if existing_user:
                user_id = str(existing_user.id)
                user_updated = False

                chatwoot_contact_id = payload.sender.id
                if chatwoot_contact_id and not existing_user.chatwoot_contact_id:
                    existing_user.chatwoot_contact_id = chatwoot_contact_id
                    user_updated = True

                old_whatsapp_name = (
                    existing_user.metadata_.get("whatsapp_name")
                    if existing_user.metadata_
                    else None
                )
                if whatsapp_name and whatsapp_name != old_whatsapp_name:
                    existing_user.first_name = first_name
                    existing_user.last_name = last_name
                    existing_user.metadata_ = {
                        **(existing_user.metadata_ or {}),
                        "whatsapp_name": whatsapp_name,
                    }
                    user_updated = True

                if user_updated:
                    await session.commit()

                logger.debug(
                    f"Existing user found: user_id={user_id} | "
                    f"phone={sanitize_phone(payload.sender.phone_number)}"
                )
            else:
                chatwoot_contact_id = payload.sender.id
                new_user = User(
                    phone=payload.sender.phone_number,
                    first_name=first_name,
                    last_name=last_name,
                    client_type=client_type_from_chatwoot or "particular",
                    chatwoot_contact_id=chatwoot_contact_id,
                    metadata_={"whatsapp_name": whatsapp_name} if whatsapp_name else {},
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                user_id = str(new_user.id)
                logger.info(
                    f"New user created automatically: user_id={user_id} | "
                    f"phone={sanitize_phone(payload.sender.phone_number)} | "
                    f"first_name={first_name} | last_name={last_name} | "
                    f"client_type={new_user.client_type} | "
                    f"chatwoot_contact_id={chatwoot_contact_id}"
                )

            # --- ConversationHistory: get or create + update timestamps ---
            conversation_id_str = str(payload.conversation.id)
            conv_result = await session.execute(
                select(ConversationHistory).where(
                    ConversationHistory.conversation_id == conversation_id_str
                )
            )
            conv_history = conv_result.scalar()

            now = datetime.now(UTC)

            if not conv_history:
                conv_history = ConversationHistory(
                    user_id=user_id,
                    conversation_id=conversation_id_str,
                    started_at=now,
                    message_count=1,
                    last_inbound_at=now,
                    last_message_at=now,
                )
                session.add(conv_history)
                await session.commit()
                await session.refresh(conv_history)
                logger.info(
                    f"New ConversationHistory created: "
                    f"conversation_id={conversation_id_str} | user_id={user_id}"
                )
            else:
                conv_history.last_inbound_at = now
                conv_history.last_message_at = now
                await session.commit()
                logger.debug(
                    f"ConversationHistory updated: conversation_id={conversation_id_str}"
                )

            # --- Filter image-type attachments BEFORE constructing ConversationMessage ---
            # Non-image attachments (PDF, audio, etc.) are silently dropped.
            # This must happen before ConversationMessage so has_images/image_count
            # reflect only image attachments, not all attachment types.
            image_atts = [
                a for a in (last_message.attachments or [])
                if a.file_type == "image"
            ]

            # --- ConversationMessage: always persist inbound ---
            inbound_msg = ConversationMessage(
                conversation_history_id=conv_history.id,
                role="user",
                author_type="user",
                author_user_id=None,
                content=message_text,
                chatwoot_message_id=last_message.id,
                has_images=bool(image_atts),
                image_count=len(image_atts),
            )
            session.add(inbound_msg)
            await session.commit()
            logger.debug(
                "inbound_message_persisted",
                extra={
                    "conversation_id": conversation_id_str,
                    "chatwoot_message_id": last_message.id,
                    "author_type": "user",
                },
            )
            if image_atts:
                await add_to_stream(
                    ATTACHMENT_DOWNLOADS_STREAM,
                    {
                        "conversation_id": str(conv_history.id),
                        "message_id": str(inbound_msg.id),
                        "attachments": [
                            {
                                "url": a.data_url,
                                "name": getattr(a, "file_name", "") or "",
                                "type": "image/jpeg",
                            }
                            for a in image_atts
                        ],
                    },
                )
                logger.info(
                    "attachment_download_enqueued",
                    extra={
                        "conversation_id": conversation_id_str,
                        "message_id": str(inbound_msg.id),
                        "attachment_count": len(image_atts),
                    },
                )

    except Exception as e:
        logger.error(
            "webhook_persistence_failed",
            exc_info=True,
            extra={
                "conversation_id": str(payload.conversation.id),
                "chatwoot_message_id": last_message.id,
                "error": str(e),
            },
        )
        return JSONResponse(
            status_code=500,
            content={"status": "persistence_failed", "detail": "DB error — check logs"},
        )

    # -------------------------------------------------------------------------
    # Step 4: Extract attachments for the event payload (used by agent).
    # -------------------------------------------------------------------------
    attachments: list[ChatwootAttachmentEvent] = []
    if last_message.attachments:
        for att in last_message.attachments:
            attachments.append(
                ChatwootAttachmentEvent(
                    id=att.id,
                    file_type=att.file_type,
                    data_url=att.data_url,
                )
            )
        logger.info(
            f"Webhook received {len(attachments)} attachment(s) | "
            f"conversation_id={payload.conversation.id} | "
            f"message_id={last_message.id} | "
            f"types={[a.file_type for a in attachments]}",
            extra={
                "conversation_id": str(payload.conversation.id),
                "message_id": last_message.id,
                "attachment_count": len(attachments),
                "attachment_types": [a.file_type for a in attachments],
            },
        )

    # -------------------------------------------------------------------------
    # Step 5: Gate — decide whether to publish to Redis Stream.
    # Publish only when: atencion_automatica=True AND bot_paused_at IS NULL.
    # -------------------------------------------------------------------------
    bot_paused = conv_history is not None and conv_history.bot_paused_at is not None

    if atencion_automatica is False or bot_paused:
        gate_reason = "bot_paused" if bot_paused else "atencion_automatica_disabled"
        logger.info(
            "webhook_persisted_skipped_publish",
            extra={
                "conversation_id": str(payload.conversation.id),
                "chatwoot_message_id": last_message.id,
                "gate_reason": gate_reason,
                "atencion_automatica": atencion_automatica,
                "bot_paused": bot_paused,
            },
        )
        return JSONResponse(
            status_code=200,
            content={"status": "persisted_no_publish", "gate_reason": gate_reason},
        )

    # -------------------------------------------------------------------------
    # Step 6: Publish to Redis Stream (bot is active, message should be processed).
    # -------------------------------------------------------------------------
    message_event = ChatwootMessageEvent(
        conversation_id=str(payload.conversation.id),
        customer_phone=payload.sender.phone_number,
        message_text=message_text,
        customer_name=payload.sender.name,
        user_id=user_id,
        chatwoot_message_id=last_message.id,
        chatwoot_message_created_at=last_message.created_at,
        attachments=attachments,
    )

    logger.info(
        f"Parsed message event: conversation_id={message_event.conversation_id}, "
        f"phone={sanitize_phone(message_event.customer_phone)}, name={message_event.customer_name}, "
        f"text='{message_event.message_text[:100]}', attachments={len(attachments)}"
    )

    try:
        if settings.USE_REDIS_STREAMS:
            stream_msg_id = await add_to_stream(
                INCOMING_STREAM,
                message_event.model_dump(),
            )
            logger.info(
                "webhook_processed",
                extra={
                    "conversation_id": str(payload.conversation.id),
                    "chatwoot_message_id": last_message.id,
                    "stream_msg_id": str(stream_msg_id),
                    "customer_phone": sanitize_phone(payload.sender.phone_number),
                },
            )
        else:
            await publish_to_channel(
                "incoming_messages",
                message_event.model_dump(),
            )
            logger.info(
                "webhook_processed_pubsub",
                extra={
                    "conversation_id": str(payload.conversation.id),
                    "customer_phone": sanitize_phone(payload.sender.phone_number),
                },
            )
    except Exception as exc:
        # Persisted to DB but publish to Redis failed. Return 200 so Chatwoot
        # does NOT retry (we already have the message persisted and would
        # duplicate-process on retry). The agent will not see this message
        # until a subsequent inbound triggers reprocessing — accepted trade-off.
        logger.error(
            "webhook_publish_failed",
            extra={
                "conversation_id": str(payload.conversation.id),
                "chatwoot_message_id": last_message.id,
                "error": str(exc),
            },
            exc_info=True,
        )

    return JSONResponse(status_code=200, content={"status": "received"})
