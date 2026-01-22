"""
MSI Automotive - Chatwoot webhook route handler.

Receives WhatsApp messages from Chatwoot and enqueues them for processing
by the AI agent.
"""

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from sqlalchemy import select

from api.models.chatwoot_webhook import (
    ChatwootAttachmentEvent,
    ChatwootMessageEvent,
    ChatwootWebhookPayload,
)
from database.connection import get_async_session
from database.models import User
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import (
    add_to_stream,
    get_redis_client,
    publish_to_channel,
    INCOMING_STREAM,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Idempotency constants
IDEMPOTENCY_TTL = 300  # 5 minutes
IDEMPOTENCY_PREFIX = "idempotency:chatwoot:"


async def check_and_set_idempotency(message_id: int) -> bool:
    """
    Check if message has already been processed (idempotency check).

    Uses Redis SETNX with TTL to prevent duplicate processing.

    Args:
        message_id: Chatwoot message ID

    Returns:
        True if message is a duplicate (already processed)
        False if message is new (should be processed)
    """
    client = get_redis_client()
    key = f"{IDEMPOTENCY_PREFIX}{message_id}"

    # SETNX returns True if key was set (new message)
    was_set = await client.setnx(key, "1")

    if was_set:
        await client.expire(key, IDEMPOTENCY_TTL)
        return False  # Not a duplicate

    logger.info(f"Duplicate message detected: {message_id}")
    return True  # Is a duplicate


@router.post("/chatwoot/{token}")
async def receive_chatwoot_webhook(
    request: Request,
    token: str,
) -> JSONResponse:
    """
    Receive and process Chatwoot webhook events.

    Authentication: Token in URL path must match CHATWOOT_WEBHOOK_TOKEN.
    Configure in Chatwoot: https://your-domain.com/webhook/chatwoot/{your_secret_token}

    Only processes 'message_created' events with 'incoming' message type.
    Valid messages are enqueued to Redis for the AI agent.

    Args:
        request: FastAPI request object
        token: Secret token from URL path

    Returns:
        JSONResponse with 200 OK status

    Raises:
        HTTPException 401: Invalid or missing token
    """
    settings = get_settings()

    # Validate token using timing-safe comparison
    if not hmac.compare_digest(token, settings.CHATWOOT_WEBHOOK_TOKEN):
        logger.warning(
            f"Invalid Chatwoot webhook token attempted from IP: {request.client.host}"
        )
        raise HTTPException(status_code=401, detail="Invalid token")

    # Read and parse webhook payload
    body = await request.body()
    body_str = body.decode("utf-8")
    logger.info(f"Raw webhook payload: {body_str[:2000]}")
    logger.debug(f"Full webhook payload: {body_str}")

    try:
        payload = ChatwootWebhookPayload.model_validate_json(body)
    except Exception as e:
        logger.error(
            f"Failed to parse webhook payload: {e}",
            exc_info=True,
            extra={"payload_preview": body_str[:1000]},
        )
        raise HTTPException(status_code=400, detail=f"Invalid payload format: {str(e)}")

    # Filter: Only process message_created events
    if payload.event != "message_created":
        logger.debug(f"Ignoring non-message event: {payload.event}")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # Filter: Only process conversations with messages
    if not payload.conversation.messages:
        logger.debug(f"Ignoring conversation {payload.conversation.id} with no messages")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # Get the last (most recent) message
    last_message = payload.conversation.messages[-1]

    # Filter: Only process incoming messages (message_type == 0)
    if last_message.message_type != 0:
        logger.debug(
            f"Ignoring non-incoming message: message_type={last_message.message_type}"
        )
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # Idempotency check
    if await check_and_set_idempotency(last_message.id):
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    # Ensure phone number exists
    if not payload.sender.phone_number:
        logger.warning(f"Message {last_message.id} has no phone number, ignoring")
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # Filter: Check atencion_automatica custom attribute
    atencion_automatica = payload.conversation.custom_attributes.get(
        "atencion_automatica"
    )

    if atencion_automatica is False:
        logger.info(
            f"Ignoring message for conversation {payload.conversation.id}: "
            f"atencion_automatica=false (bot disabled)",
            extra={
                "conversation_id": str(payload.conversation.id),
                "customer_phone": payload.sender.phone_number,
            },
        )
        return JSONResponse(
            status_code=200,
            content={"status": "ignored_auto_attention_disabled"},
        )

    elif atencion_automatica is None:
        # First message - check panic button BEFORE enabling bot
        from shared.settings_cache import get_cached_setting

        agent_enabled = await get_cached_setting("agent_enabled")

        if agent_enabled and agent_enabled.lower() == "false":
            # Panic button active - set atencion_automatica to False
            logger.warning(
                f"First message for conversation {payload.conversation.id}: "
                f"agent disabled (panic button), setting atencion_automatica=false",
                extra={
                    "event_type": "panic_button_first_message",
                    "conversation_id": str(payload.conversation.id),
                    "customer_phone": payload.sender.phone_number,
                },
            )

            try:
                chatwoot_client = ChatwootClient()
                await chatwoot_client.update_conversation_attributes(
                    conversation_id=payload.conversation.id,
                    attributes={"atencion_automatica": False},
                )
                logger.info(
                    f"Set atencion_automatica=false for conversation {payload.conversation.id} (panic button)"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to set atencion_automatica for conversation {payload.conversation.id}: {e}",
                    exc_info=True,
                )

            # Queue message normally - agent will send auto-response

        else:
            # Normal flow - enable bot
            logger.info(
                f"First message for conversation {payload.conversation.id}: "
                f"setting atencion_automatica=true",
                extra={
                    "conversation_id": str(payload.conversation.id),
                    "customer_phone": payload.sender.phone_number,
                },
            )

            try:
                chatwoot_client = ChatwootClient()
                await chatwoot_client.update_conversation_attributes(
                    conversation_id=payload.conversation.id,
                    attributes={"atencion_automatica": True},
                )
                logger.info(
                    f"Successfully enabled bot for conversation {payload.conversation.id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to set atencion_automatica for conversation {payload.conversation.id}: {e}",
                    exc_info=True,
                )

    # Get message text
    message_text = last_message.content or ""

    # Create or get user from database (with bidirectional sync from Chatwoot)
    user_id: str | None = None
    try:
        async with get_async_session() as session:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.phone == payload.sender.phone_number)
            )
            existing_user = result.scalar()

            # Helper: Parse WhatsApp name into first_name/last_name
            whatsapp_name = payload.sender.name or ""
            name_parts = whatsapp_name.split(" ", 1) if whatsapp_name else []
            first_name = name_parts[0] if name_parts else None
            last_name = name_parts[1] if len(name_parts) > 1 else None

            # Helper: Map Chatwoot "tipo" to client_type
            tipo_chatwoot = payload.conversation.custom_attributes.get("tipo")
            if tipo_chatwoot == "Profesional":
                client_type_from_chatwoot = "professional"
            elif tipo_chatwoot == "Particular":
                client_type_from_chatwoot = "particular"
            else:
                client_type_from_chatwoot = None  # No valid tipo in Chatwoot

            if existing_user:
                user_id = str(existing_user.id)
                user_updated = False

                # Sync name if WhatsApp name changed
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
                    logger.info(
                        f"User name updated from WhatsApp: user_id={user_id} | "
                        f"old_name={old_whatsapp_name} -> new_name={whatsapp_name}"
                    )

                # Sync client_type if Chatwoot "tipo" changed
                if (
                    client_type_from_chatwoot
                    and existing_user.client_type != client_type_from_chatwoot
                ):
                    existing_user.client_type = client_type_from_chatwoot
                    user_updated = True
                    logger.info(
                        f"User client_type synced from Chatwoot: user_id={user_id} | "
                        f"tipo={tipo_chatwoot} -> client_type={client_type_from_chatwoot}"
                    )

                if user_updated:
                    await session.commit()

                logger.debug(
                    f"Existing user found: user_id={user_id} | "
                    f"phone={payload.sender.phone_number}"
                )
            else:
                # Create new user automatically with parsed name
                new_user = User(
                    phone=payload.sender.phone_number,
                    first_name=first_name,
                    last_name=last_name,
                    client_type=client_type_from_chatwoot or "particular",
                    metadata_={"whatsapp_name": whatsapp_name} if whatsapp_name else {},
                )
                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)
                user_id = str(new_user.id)
                logger.info(
                    f"New user created automatically: user_id={user_id} | "
                    f"phone={payload.sender.phone_number} | "
                    f"first_name={first_name} | last_name={last_name} | "
                    f"client_type={new_user.client_type}"
                )
    except Exception as e:
        logger.error(
            f"Error creating/fetching user for phone {payload.sender.phone_number}: {e}",
            exc_info=True,
        )
        # Continue without user_id - the agent will handle it

    # Extract attachments from the message (images, files, audio, video)
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

    # Create message event for Redis
    message_event = ChatwootMessageEvent(
        conversation_id=str(payload.conversation.id),
        customer_phone=payload.sender.phone_number,
        message_text=message_text,
        customer_name=payload.sender.name,
        user_id=user_id,
        attachments=attachments,
    )

    logger.info(
        f"Parsed message event: conversation_id={message_event.conversation_id}, "
        f"phone={message_event.customer_phone}, name={message_event.customer_name}, "
        f"text='{message_event.message_text[:100]}', attachments={len(attachments)}"
    )

    # Publish to Redis
    if settings.USE_REDIS_STREAMS:
        stream_msg_id = await add_to_stream(
            INCOMING_STREAM,
            message_event.model_dump(),
        )
        logger.info(
            f"Chatwoot message added to stream: conversation_id={message_event.conversation_id}, "
            f"phone={message_event.customer_phone}, stream_msg_id={stream_msg_id}"
        )
    else:
        await publish_to_channel(
            "incoming_messages",
            message_event.model_dump(),
        )
        logger.info(
            f"Chatwoot message published (pub/sub): conversation_id={message_event.conversation_id}, "
            f"phone={message_event.customer_phone}"
        )

    return JSONResponse(status_code=200, content={"status": "received"})
