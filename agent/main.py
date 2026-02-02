"""
MSI Automotive - LangGraph Agent Service Entry Point.

Background worker for conversation orchestration using mode-based architecture.
Subscribes to Redis for incoming messages and sends responses via Chatwoot.
"""

import asyncio
import json
import logging
import signal
import time
import uuid as uuid_mod
from datetime import datetime, UTC

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent.graph.conversation_graph import create_compiled_graph
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes
from api.services.chatwoot_image_service import get_chatwoot_image_service
from database.connection import get_async_session
from database.models import User, Case, CaseImage, ConversationHistory
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.text_utils import strip_markdown_for_whatsapp
from shared.redis_client import (
    get_redis_client,
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

# Constants for retry logic
MAX_INIT_RETRIES = 10
INIT_BASE_DELAY = 2.0
MAX_RETRY_DELAY = 30
MAX_CONSECUTIVE_ERRORS = 5

# Image batching constants (recycled from v1)
IMAGE_BATCH_TIMEOUT_SECONDS = 15
IMAGE_BATCH_KEY_PREFIX = "image_batch:"
IMAGE_BATCH_FINAL_PREFIX = "image_batch_final:"
COMPLETION_PHRASES = ["listo", "terminado", "ya está", "ya esta", "hecho", "fin", "ya", "eso es todo", "nada más", "nada mas"]

# Per-conversation locks
_conversation_locks: dict[str, asyncio.Lock] = {}


def get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific conversation."""
    if conversation_id not in _conversation_locks:
        _conversation_locks[conversation_id] = asyncio.Lock()
    return _conversation_locks[conversation_id]


async def wait_for_redis_ready(client, max_wait: int = 60) -> bool:
    """Wait until Redis is available."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            await client.ping()
            return True
        except Exception:
            await asyncio.sleep(1)
    return False


async def initialize_redis_with_retry(
    max_retries: int = MAX_INIT_RETRIES,
    base_delay: float = INIT_BASE_DELAY,
):
    """Initialize Redis connections with exponential backoff."""
    redis_client = get_redis_client()
    
    if not await wait_for_redis_ready(redis_client):
        raise RuntimeError("Redis not available after 60s")
    
    for attempt in range(1, max_retries + 1):
        try:
            await create_consumer_group(INCOMING_STREAM, CONSUMER_GROUP)
            logger.info("Redis consumer group created successfully")
            return redis_client
        except Exception as e:
            delay = min(base_delay * (2 ** (attempt - 1)), MAX_RETRY_DELAY)
            logger.warning(
                f"Redis init attempt {attempt}/{max_retries} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)
            else:
                raise RuntimeError(f"Failed to initialize Redis after {max_retries} attempts") from e


async def save_image_batch(
    redis_client,
    conversation_id: str,
    image_urls: list[str],
) -> None:
    """
    Save received images to database and update batch tracking.
    
    Recycled from v1 for compatibility with image handling flow.
    """
    if not image_urls:
        return

    async with get_async_session() as session:
        # Get case_id for this conversation
        result = await session.execute(
            select(Case.id)
            .join(User, Case.user_id == User.id)
            .where(User.conversation_id == conversation_id)
            .order_by(Case.created_at.desc())
            .limit(1)
        )
        case = result.scalar_one_or_none()
        
        if not case:
            logger.warning(f"No case found for conversation {conversation_id}")
            return
        
        case_id = case
        
        # Determine current element if in COLLECT_ELEMENT_DATA
        # For v2: this would need adaptation based on mode_context
        element_code = None  # TODO: extract from mode_context if needed
        
        # Save images
        for url in image_urls:
            image = CaseImage(
                id=uuid_mod.uuid4(),
                case_id=case_id,
                image_url=url,
                image_type="element" if element_code else "base",
                element_code=element_code,
                description=f"Image for {element_code}" if element_code else "Base documentation",
            )
            session.add(image)
        
        await session.commit()
        logger.info(f"Saved {len(image_urls)} images for case {case_id}")
    
    # Update batch tracking
    batch_key = f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}"
    current_count = await redis_client.get(batch_key)
    new_count = (int(current_count) if current_count else 0) + len(image_urls)
    await redis_client.set(batch_key, str(new_count), ex=300)


async def process_message(
    graph,
    chatwoot: ChatwootClient,
    redis_client,
    message_data: dict,
) -> None:
    """
    Process a single message through the conversation graph.
    
    Adapted for mode-based architecture (no FSM).
    """
    conversation_id = message_data.get("conversation_id")
    if not conversation_id:
        logger.error("Missing conversation_id in message")
        return
    
    # Acquire conversation lock
    lock = get_conversation_lock(conversation_id)
    async with lock:
        try:
            # Extract message content
            user_message = message_data.get("content", "")
            message_type = message_data.get("message_type", "incoming")
            attachments = message_data.get("attachments", [])
            
            # Handle image batching
            if attachments:
                image_urls = [att.get("data_url") for att in attachments if att.get("data_url")]
                if image_urls:
                    await save_image_batch(redis_client, conversation_id, image_urls)
                    logger.info(f"Received {len(image_urls)} images for {conversation_id}")
                    # Don't invoke graph for image-only messages
                    if not user_message.strip():
                        return
            
            # Get user from DB via ConversationHistory
            async with get_async_session() as session:
                result = await session.execute(
                    select(User)
                    .join(ConversationHistory, User.id == ConversationHistory.user_id)
                    .where(ConversationHistory.conversation_id == conversation_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.error(f"User not found for conversation {conversation_id}")
                    return
                
                user_id = str(user.id)
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Usuario"
                client_type = user.client_type or "particular"
                customer_phone = user.phone or ""
            
            # Build config for graph invocation
            config = {
                "configurable": {
                    "thread_id": conversation_id,
                    "checkpoint_ns": "conversation",
                }
            }
            
            # Build initial state
            state_input = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_message": user_message,
                "client_type": client_type,
                "messages": [],  # History loaded from checkpointer
                "current_mode": "START",  # Will be overridden if checkpoint exists
            }
            
            # Invoke graph
            logger.info(
                f"Invoking graph for conversation {conversation_id}",
                extra={"conversation_id": conversation_id, "message_preview": user_message[:60]}
            )
            
            result = await graph.ainvoke(state_input, config=config)
            
            # Extract response
            ai_response = result.get("ai_response", "")
            if not ai_response:
                logger.warning(f"No ai_response from graph for {conversation_id}")
                return
            
            # Strip markdown for WhatsApp
            ai_response_clean = strip_markdown_for_whatsapp(ai_response)
            
            # Send text response
            await chatwoot.send_message(
                customer_phone=customer_phone,
                message=ai_response_clean,
                conversation_id=int(conversation_id),
            )
            logger.info(f"Sent response to {conversation_id}")
            
            # Handle pending images if any
            pending_images = result.get("pending_images")
            if pending_images:
                images = pending_images.get("images", [])
                follow_up = pending_images.get("follow_up_message")
                
                if images:
                    image_service = get_chatwoot_image_service()
                    await image_service.send_images(
                        conversation_id=conversation_id,
                        images=images,
                    )
                    logger.info(f"Sent {len(images)} images to {conversation_id}")
                
                if follow_up:
                    await asyncio.sleep(5.0)  # Gap to prevent overtaking images
                    follow_up_clean = strip_markdown_for_whatsapp(follow_up)
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=follow_up_clean,
                        conversation_id=int(conversation_id),
                    )
        
        except Exception as e:
            logger.error(
                f"Error processing message for {conversation_id}: {e}",
                exc_info=True,
                extra={"conversation_id": conversation_id}
            )
            
            # Send error message to user
            try:
                await chatwoot.send_message(
                    customer_phone=customer_phone,
                    message="Disculpá, hubo un error procesando tu mensaje. Por favor, intentá de nuevo.",
                    conversation_id=int(conversation_id),
                )
            except Exception:
                logger.error(f"Failed to send error message to {conversation_id}")


async def consume_messages(graph, chatwoot: ChatwootClient, redis_client):
    """
    Main message consumer loop.
    
    Reads from Redis Streams and processes messages.
    """
    consumer_name = f"agent-{uuid_mod.uuid4().hex[:8]}"
    logger.info(f"Starting consumer: {consumer_name}")
    
    consecutive_errors = 0
    
    while not shutdown_event.is_set():
        try:
            logger.info(f"[DEBUG] Consumer {consumer_name} reading from stream...")
            messages = await read_from_stream(
                INCOMING_STREAM,
                CONSUMER_GROUP,
                consumer_name,
                block_ms=1000,
            )
            
            if not messages:
                logger.info("[DEBUG] No messages received, continuing...")
                consecutive_errors = 0
                continue
            
            logger.info(f"[DEBUG] Received {len(messages)} messages")
            
            # messages is already [(message_id, message_data), ...]
            for message_id, message_data in messages:
                try:
                    # Parse JSON fields if needed
                    if "attachments" in message_data and isinstance(message_data["attachments"], str):
                        message_data["attachments"] = json.loads(message_data["attachments"])
                    
                    # Process message
                    await process_message(graph, chatwoot, redis_client, message_data)
                    
                    # Acknowledge
                    await acknowledge_message(
                        INCOMING_STREAM,
                        CONSUMER_GROUP,
                        message_id,
                    )
                    
                    consecutive_errors = 0
                    
                except Exception as e:
                    logger.error(f"Error processing message {message_id}: {e}", exc_info=True)
                    
                    # Move to DLQ
                    try:
                        await move_to_dead_letter(
                            INCOMING_STREAM,
                            CONSUMER_GROUP,
                            message_id,
                            message_data,
                            str(e),
                        )
                    except Exception:
                        logger.error(f"Failed to move message {message_id} to DLQ")
                    
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.critical(f"Too many consecutive errors ({consecutive_errors}), pausing...")
                        await asyncio.sleep(30)
                        consecutive_errors = 0
        
        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.critical("Too many consecutive loop errors, pausing...")
                await asyncio.sleep(30)
                consecutive_errors = 0
            else:
                await asyncio.sleep(5)


async def main():
    """Main entry point."""
    settings = get_settings()
    
    logger.info("="*60)
    logger.info("Starting MSI-a Agent (Mode-Based Architecture)")
    logger.info("="*60)
    
    # Initialize Redis
    redis_client = await initialize_redis_with_retry()
    
    # Initialize Chatwoot
    chatwoot = ChatwootClient()
    
    # Initialize graph
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    graph = await create_compiled_graph(checkpointer)
    logger.info("Conversation graph compiled successfully")
    
    # Setup graceful shutdown
    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
    
    # Start consumer
    try:
        await consume_messages(graph, chatwoot, redis_client)
    except Exception as e:
        logger.critical(f"Fatal error in consumer: {e}", exc_info=True)
    finally:
        logger.info("Agent shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
