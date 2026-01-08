"""
MSI Automotive - LangGraph Agent Service Entry Point.

Background worker for conversation orchestration.
Subscribes to Redis for incoming messages and sends responses via Chatwoot.
"""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, UTC

from sqlalchemy import select

from agent.graphs.conversation_flow import create_conversation_graph
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes
from database.connection import get_async_session
from database.models import User
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.redis_client import (
    get_redis_client,
    publish_to_channel,
    create_consumer_group,
    read_from_stream,
    acknowledge_message,
    move_to_dead_letter,
    INCOMING_STREAM,
    CONSUMER_GROUP,
)

# Configure structured JSON logging
configure_logging()
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


def make_absolute_url(url: str | None) -> str | None:
    """
    Convert relative URL to absolute URL using API_BASE_URL.

    Chatwoot requires absolute URLs to download images. This function
    converts relative URLs (e.g., /images/filename.png) to absolute URLs
    (e.g., https://domain.com/images/filename.png).

    Args:
        url: Relative or absolute URL

    Returns:
        Absolute URL or None if input is None/empty
    """
    if not url:
        return None

    # Already absolute
    if url.startswith("http://") or url.startswith("https://"):
        return url

    # Make absolute using API_BASE_URL
    settings = get_settings()
    base_url = settings.API_BASE_URL.rstrip("/")
    url = url.lstrip("/")

    return f"{base_url}/{url}"


async def get_user_by_phone(phone: str) -> User | None:
    """
    Fetch user from database by phone number.

    Args:
        phone: User phone in E.164 format (e.g., +34612345678)

    Returns:
        User object if found, None otherwise
    """
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.phone == phone)
            )
            return result.scalar()
    except Exception as e:
        logger.warning(f"Failed to fetch user by phone {phone}: {e}")
        return None


async def subscribe_to_incoming_messages():
    """
    Subscribe to incoming_messages Redis channel and process with LangGraph.

    This worker listens for messages published by the FastAPI webhook receiver
    and processes them through the conversation StateGraph.

    Message format (incoming_messages):
        {
            "conversation_id": "wa-msg-123",
            "customer_phone": "+34612345678",
            "message_text": "Hola, quiero homologar un gancho de remolque"
        }

    Message format (outgoing_messages):
        {
            "conversation_id": "wa-msg-123",
            "customer_phone": "+34612345678",
            "message": "AI response text"
        }
    """
    client = get_redis_client()
    settings = get_settings()

    logger.info("Initializing Redis checkpointer...")

    # Create checkpointer for conversation state persistence
    checkpointer = get_redis_checkpointer()

    # Initialize Redis indexes for LangGraph
    try:
        await initialize_redis_indexes(checkpointer)
        logger.info("Redis checkpointer initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis indexes: {e}")
        raise

    # Create conversation graph
    graph = create_conversation_graph(checkpointer=checkpointer)
    logger.info("Conversation graph created successfully")

    async def process_message(
        conversation_id: str,
        user_phone: str,
        message_text: str,
        user_name: str | None = None,
        user_id: str | None = None,
        stream_msg_id: str | None = None,
    ) -> None:
        """
        Process a single incoming message through the LangGraph.

        Args:
            conversation_id: The conversation thread ID
            user_phone: User's phone number
            message_text: The message content
            user_name: Optional user name from WhatsApp
            user_id: Optional user ID (created by webhook)
            stream_msg_id: Optional Redis stream message ID for acknowledgment
        """
        logger.info(
            f"Processing message | conversation_id={conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "user_phone": user_phone,
                "message_length": len(message_text) if message_text else 0,
            },
        )

        # Get user info - use provided user_id or lookup by phone
        client_type = "particular"
        if user_id:
            # User was already created/fetched by webhook
            user = await get_user_by_phone(user_phone)
            if user:
                client_type = user.client_type
            logger.info(
                f"User found | user_id={user_id} | client_type={client_type}",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "client_type": client_type,
                },
            )
        else:
            # Fallback: lookup user by phone (shouldn't happen with new webhook)
            user = await get_user_by_phone(user_phone)
            if user:
                user_id = str(user.id)
                client_type = user.client_type
                logger.info(
                    f"User found by phone | user_id={user_id} | client_type={client_type}",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "client_type": client_type,
                    },
                )

        # Create initial ConversationState
        state = {
            "conversation_id": conversation_id,
            "user_phone": user_phone,
            "user_name": user_name,
            "user_id": user_id,
            "client_type": client_type,
            "user_message": message_text,
            "updated_at": datetime.now(UTC),
        }

        # Invoke graph with checkpointing
        config = {"configurable": {"thread_id": conversation_id}}
        logger.info(
            f"Invoking graph for thread_id={conversation_id}",
            extra={"conversation_id": conversation_id},
        )

        try:
            result = await graph.ainvoke(state, config=config)

            logger.debug(
                f"Checkpoint persisted | conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )

        except Exception as graph_error:
            logger.error(
                f"Graph invocation failed for conversation_id={conversation_id}: {graph_error}",
                extra={
                    "conversation_id": conversation_id,
                    "error_type": type(graph_error).__name__,
                },
                exc_info=True,
            )

            # Send fallback error message to user
            fallback_message = (
                "Lo siento, tuve un problema técnico. "
                "¿Puedes intentarlo de nuevo?"
            )
            await publish_to_channel(
                "outgoing_messages",
                {
                    "conversation_id": conversation_id,
                    "customer_phone": user_phone,  # Keep as customer_phone for outgoing compatibility
                    "message": fallback_message,
                },
            )
            logger.info(f"Sent fallback message for conversation_id={conversation_id}")

            # Still ACK the message to avoid reprocessing
            if stream_msg_id and settings.USE_REDIS_STREAMS:
                try:
                    await acknowledge_message(
                        INCOMING_STREAM, CONSUMER_GROUP, stream_msg_id
                    )
                except Exception as ack_error:
                    logger.warning(f"Failed to ACK message {stream_msg_id}: {ack_error}")
            return

        # Extract AI response from result state
        last_message = result.get("messages", [])[-1] if result.get("messages") else None

        if not last_message:
            logger.warning(
                f"No messages in result for conversation_id={conversation_id}"
            )
            return

        # Handle both dict and Message object formats
        if isinstance(last_message, dict):
            content = last_message.get("content", "")
        else:
            content = getattr(last_message, "content", "")

        # Extract text from content (handle both string and list of blocks)
        if isinstance(content, str):
            ai_message = content
        elif isinstance(content, list):
            text_blocks = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            ai_message = " ".join(text_blocks).strip()
        else:
            ai_message = str(content)

        logger.info(
            f"Graph completed for conversation_id={conversation_id}",
            extra={
                "conversation_id": conversation_id,
                "ai_message_preview": ai_message[:50] if ai_message else "",
            },
        )

        # Prepare outgoing message payload
        outgoing_payload = {
            "conversation_id": conversation_id,
            "customer_phone": user_phone,  # Keep as customer_phone for outgoing compatibility
            "message": ai_message,
        }

        # Check for pending images from tool calls (documentation images)
        pending_images = result.get("pending_images", [])
        if pending_images:
            outgoing_payload["images"] = pending_images
            logger.info(
                f"Including {len(pending_images)} images in outgoing message | "
                f"conversation_id={conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "image_count": len(pending_images),
                },
            )

        # Publish to outgoing_messages channel
        await publish_to_channel("outgoing_messages", outgoing_payload)

        logger.info(
            f"Message published to outgoing_messages: conversation_id={conversation_id}",
            extra={"conversation_id": conversation_id},
        )

        # Check if escalation was triggered
        if result.get("escalation_triggered"):
            escalation_reason = result.get("escalation_reason", "unknown")
            escalation_id = result.get("escalation_id")
            logger.warning(
                f"ESCALATION TRIGGERED | conversation_id={conversation_id} | "
                f"reason={escalation_reason} | escalation_id={escalation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "escalation_reason": escalation_reason,
                    "escalation_id": escalation_id,
                    "event_type": "escalation",
                },
            )

            # Publish escalation event for monitoring/notifications
            try:
                await publish_to_channel(
                    "escalation_events",
                    {
                        "conversation_id": conversation_id,
                        "user_phone": user_phone,
                        "reason": escalation_reason,
                        "escalation_id": escalation_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            except Exception as pub_error:
                logger.warning(
                    f"Failed to publish escalation event: {pub_error}",
                    extra={"conversation_id": conversation_id},
                )

        # ACK stream message after successful processing
        if stream_msg_id and settings.USE_REDIS_STREAMS:
            try:
                await acknowledge_message(
                    INCOMING_STREAM, CONSUMER_GROUP, stream_msg_id
                )
                logger.debug(
                    f"ACK stream message {stream_msg_id} | conversation_id={conversation_id}"
                )
            except Exception as ack_error:
                logger.warning(
                    f"Failed to ACK message {stream_msg_id}: {ack_error}",
                    extra={"conversation_id": conversation_id},
                )

    # ========================================================================
    # MESSAGE SUBSCRIPTION (Redis Streams or Pub/Sub based on config)
    # ========================================================================

    if settings.USE_REDIS_STREAMS:
        # ====================================================================
        # REDIS STREAMS MODE: Persistent with acknowledgment
        # ====================================================================
        consumer_name = f"agent-{os.getpid()}"

        logger.info(
            f"Initializing Redis Streams consumer | stream={INCOMING_STREAM} | "
            f"group={CONSUMER_GROUP} | consumer={consumer_name}"
        )

        # Create consumer group if it doesn't exist
        await create_consumer_group(INCOMING_STREAM, CONSUMER_GROUP)

        logger.info(
            f"Redis Streams consumer ready | stream={INCOMING_STREAM} | "
            f"consumer={consumer_name}"
        )

        try:
            while not shutdown_event.is_set():
                try:
                    # Read messages from stream (blocks for 5 seconds if no messages)
                    messages = await read_from_stream(
                        INCOMING_STREAM,
                        CONSUMER_GROUP,
                        consumer_name,
                        count=10,
                        block_ms=5000,
                    )

                    for stream_msg_id, data in messages:
                        try:
                            conversation_id = data.get("conversation_id")
                            user_phone = data.get("customer_phone")  # Keep reading as customer_phone for compatibility
                            message_text = data.get("message_text")
                            user_name = data.get("customer_name")  # Keep reading as customer_name for compatibility
                            user_id = data.get("user_id")  # New field from webhook

                            logger.info(
                                f"Stream message received: conversation_id={conversation_id}, "
                                f"phone={user_phone}, user_id={user_id}, stream_msg_id={stream_msg_id}",
                                extra={
                                    "conversation_id": conversation_id,
                                    "user_phone": user_phone,
                                    "user_id": user_id,
                                    "stream_msg_id": stream_msg_id,
                                },
                            )

                            # Process the message
                            await process_message(
                                conversation_id=conversation_id,
                                user_phone=user_phone,
                                message_text=message_text,
                                user_name=user_name,
                                user_id=user_id,
                                stream_msg_id=stream_msg_id,
                            )

                        except Exception as e:
                            logger.error(
                                f"Error processing stream message {stream_msg_id}: {e}",
                                exc_info=True,
                            )
                            # Move to dead letter queue for later inspection
                            try:
                                await move_to_dead_letter(
                                    INCOMING_STREAM,
                                    CONSUMER_GROUP,
                                    stream_msg_id,
                                    data,
                                    str(e),
                                )
                            except Exception as dlq_error:
                                logger.error(f"Failed to move to DLQ: {dlq_error}")
                            continue

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error reading from stream: {e}", exc_info=True)
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Stream consumer cancelled")
            raise

        except Exception as e:
            logger.error(f"Fatal error in stream consumer: {e}", exc_info=True)
            raise

    else:
        # ====================================================================
        # LEGACY PUB/SUB MODE: Fire-and-forget (backward compatibility)
        # ====================================================================
        logger.info("Subscribing to 'incoming_messages' channel (pub/sub mode)...")

        pubsub = client.pubsub()
        await pubsub.subscribe("incoming_messages")

        logger.info("Subscribed to 'incoming_messages' channel")

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    conversation_id = data.get("conversation_id")
                    user_phone = data.get("customer_phone")  # Keep reading as customer_phone for compatibility
                    message_text = data.get("message_text")
                    user_name = data.get("customer_name")  # Keep reading as customer_name for compatibility
                    user_id = data.get("user_id")  # New field from webhook

                    logger.info(
                        f"Message received: conversation_id={conversation_id}, "
                        f"phone={user_phone}, user_id={user_id}",
                        extra={
                            "conversation_id": conversation_id,
                            "user_phone": user_phone,
                            "user_id": user_id,
                        },
                    )

                    # Process the message
                    await process_message(
                        conversation_id=conversation_id,
                        user_phone=user_phone,
                        message_text=message_text,
                        user_name=user_name,
                        user_id=user_id,
                    )

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in message: {e}")
                    continue

                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}",
                        exc_info=True,
                    )
                    continue

        except asyncio.CancelledError:
            logger.info("Incoming message subscriber cancelled")
            await pubsub.unsubscribe("incoming_messages")
            await pubsub.close()
            raise

        except Exception as e:
            logger.error(f"Fatal error in incoming message subscriber: {e}", exc_info=True)
            raise


async def subscribe_to_outgoing_messages():
    """
    Subscribe to outgoing_messages Redis channel and send via Chatwoot.

    This worker listens for messages published by the conversation graph,
    and sends them to customers via the Chatwoot API.

    Message format (outgoing_messages):
        {
            "conversation_id": "wa-msg-123",
            "customer_phone": "+34612345678",
            "message": "AI response text"
        }
    """
    client = get_redis_client()
    chatwoot = ChatwootClient()

    logger.info("Subscribing to 'outgoing_messages' channel...")

    pubsub = client.pubsub()
    await pubsub.subscribe("outgoing_messages")

    logger.info("Subscribed to 'outgoing_messages' channel")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                customer_phone = data.get("customer_phone")
                message_text = data.get("message")
                conversation_id = data.get("conversation_id")
                images = data.get("images", [])

                logger.info(
                    f"Outgoing message received: conversation_id={conversation_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "customer_phone": customer_phone,
                        "has_images": len(images) > 0,
                    },
                )

                # Send text message via Chatwoot
                success = await chatwoot.send_message(
                    customer_phone=customer_phone,
                    message=message_text,
                    conversation_id=conversation_id,
                )

                if success:
                    logger.info(
                        f"Message sent to {customer_phone}: success=True",
                        extra={
                            "conversation_id": conversation_id,
                            "customer_phone": customer_phone,
                        },
                    )
                else:
                    logger.error(
                        f"Message sent to {customer_phone}: success=False",
                        extra={
                            "conversation_id": conversation_id,
                            "customer_phone": customer_phone,
                        },
                    )

                # Send images if present (each with its own caption)
                if images and conversation_id:
                    # Separate images by type (keep full metadata)
                    base_images: list[dict] = []
                    elemento_images: list[dict] = []

                    for img in images:
                        if isinstance(img, str):
                            # Old format: just URL, treat as general/elemento
                            elemento_images.append({
                                "url": img,
                                "tipo": "elemento",
                                "descripcion": "Documentación específica",
                            })
                        elif isinstance(img, dict):
                            # New format: keep full metadata
                            tipo = img.get("tipo", "general")
                            if tipo == "base":
                                base_images.append(img)
                            else:
                                elemento_images.append(img)

                    total_images = len(base_images) + len(elemento_images)
                    logger.info(
                        f"Sending {total_images} images to conversation "
                        f"{conversation_id} (base: {len(base_images)}, "
                        f"elementos: {len(elemento_images)})",
                        extra={
                            "conversation_id": conversation_id,
                            "base_images": len(base_images),
                            "elemento_images": len(elemento_images),
                        },
                    )

                    sent_count = 0

                    # Send base documentation images first (each with its own description)
                    for img_data in base_images:
                        url = img_data.get("url")
                        descripcion = img_data.get("descripcion", "")

                        if not url:
                            continue

                        absolute_url = make_absolute_url(url)
                        if not absolute_url:
                            continue

                        try:
                            success = await chatwoot.send_image(
                                conversation_id=int(conversation_id),
                                image_url=absolute_url,
                                caption=descripcion,
                            )
                            if success:
                                sent_count += 1

                            # Small delay between images
                            if base_images.index(img_data) < len(base_images) - 1:
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.error(
                                f"Failed to send base image: {e}",
                                extra={"conversation_id": conversation_id},
                            )

                    # Send element-specific images after (each with its own description)
                    for img_data in elemento_images:
                        url = img_data.get("url")
                        descripcion = img_data.get("descripcion", "")

                        if not url:
                            continue

                        absolute_url = make_absolute_url(url)
                        if not absolute_url:
                            continue

                        try:
                            success = await chatwoot.send_image(
                                conversation_id=int(conversation_id),
                                image_url=absolute_url,
                                caption=descripcion,
                            )
                            if success:
                                sent_count += 1

                            # Small delay between images
                            if elemento_images.index(img_data) < len(elemento_images) - 1:
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.error(
                                f"Failed to send elemento image: {e}",
                                extra={"conversation_id": conversation_id},
                            )

                    logger.info(
                        f"Images sent to conversation {conversation_id}: "
                        f"{sent_count}/{total_images}",
                        extra={
                            "conversation_id": conversation_id,
                            "sent_count": sent_count,
                            "total_images": total_images,
                        },
                    )

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in outgoing message: {e}")
                continue

            except Exception as e:
                logger.error(
                    f"Error sending outgoing message: {e}",
                    exc_info=True,
                )
                continue

    except asyncio.CancelledError:
        logger.info("Outgoing message subscriber cancelled")
        await pubsub.unsubscribe("outgoing_messages")
        await pubsub.close()
        raise

    except Exception as e:
        logger.error(f"Fatal error in outgoing message subscriber: {e}", exc_info=True)
        raise


async def main():
    """Agent worker main entry point."""
    logger.info("MSI-a Agent service started")

    loop = asyncio.get_running_loop()

    def handle_shutdown_signal():
        """Handle shutdown signals gracefully in async context."""
        logger.info("Received shutdown signal, initiating graceful shutdown...")
        shutdown_event.set()

    # Register signal handlers (Unix only)
    try:
        loop.add_signal_handler(signal.SIGTERM, handle_shutdown_signal)
        loop.add_signal_handler(signal.SIGINT, handle_shutdown_signal)
        logger.info("Signal handlers registered")
    except NotImplementedError:
        logger.warning("Signal handlers not supported on this platform")

    # Start both workers concurrently
    incoming_task = asyncio.create_task(subscribe_to_incoming_messages())
    outgoing_task = asyncio.create_task(subscribe_to_outgoing_messages())

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Main loop cancelled")
    finally:
        logger.info("Shutting down agent service...")
        incoming_task.cancel()
        outgoing_task.cancel()
        try:
            await asyncio.gather(incoming_task, outgoing_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        logger.info("Agent service stopped")


if __name__ == "__main__":
    logger.info("Starting MSI-a Agent Service")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Agent service exited")
