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

from sqlalchemy import select

from agent.graph.conversation_graph import create_compiled_graph
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes
from agent.services.image_handling import (
    is_completion_message,
    is_in_image_collection_mode,
    get_current_element_code,
    get_mode_context_from_checkpoint,
    get_case_id_from_mode_context,
    save_images_silently,
    update_batch_counter,
    reset_batch_counter,
    reconcile_on_completion,
    image_batch_confirmation_worker,
    is_image_attachment,
)
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
from api.services.message_persistence_service import (
    save_user_message,
    save_assistant_message,
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

# Per-conversation locks
_conversation_locks: dict[str, asyncio.Lock] = {}


def get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific conversation."""
    if conversation_id not in _conversation_locks:
        _conversation_locks[conversation_id] = asyncio.Lock()
    return _conversation_locks[conversation_id]


async def _safe_reconcile(redis_client, checkpointer, conversation_id: str) -> None:
    """Run reconciliation in background without blocking the response.

    This is a fire-and-forget wrapper around reconcile_on_completion() so
    the 5-15s sleep inside reconciliation doesn't delay the agent response.
    """
    try:
        await reconcile_on_completion(redis_client, checkpointer, conversation_id)
    except Exception as e:
        logger.error(
            "background_reconciliation_failed",
            extra={
                "conversation_id": conversation_id,
                "error": str(e),
            },
            exc_info=True,
        )


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


async def get_case_id_for_conversation(conversation_id: str, customer_phone: str) -> str | None:
    """Get the latest case_id for a conversation by looking up user + case."""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(Case.id)
                .join(User, Case.user_id == User.id)
                .where(User.phone == customer_phone)
                .order_by(Case.created_at.desc())
                .limit(1)
            )
            case_id = result.scalar_one_or_none()
            return str(case_id) if case_id else None
    except Exception as e:
        logger.warning(f"Failed to get case_id for conversation {conversation_id}: {e}")
        return None


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
            # Extract message content (API sends "message_text", not "content")
            user_message = message_data.get("message_text", "") or message_data.get("content", "")
            message_type = message_data.get("message_type", "incoming")
            attachments = message_data.get("attachments", [])
            
            # Extract customer phone from message
            customer_phone = message_data.get("customer_phone", "")
            if not customer_phone:
                logger.error(f"Missing customer_phone in message for conversation {conversation_id}")
                return
            
            # Handle image attachments
            image_attachments = [a for a in attachments if is_image_attachment(a)] if attachments else []
            if image_attachments:
                # Get checkpointer for mode_context lookup
                checkpointer = get_redis_checkpointer()
                mode_context = await get_mode_context_from_checkpoint(
                    checkpointer, conversation_id,
                )
                
                # Try to find case_id + element_code for proper save
                case_id = await get_case_id_from_mode_context(mode_context)
                if not case_id:
                    case_id = await get_case_id_for_conversation(
                        conversation_id, customer_phone,
                    )
                
                if case_id and is_in_image_collection_mode(mode_context):
                    # In image collection mode — save silently with full validation
                    element_code = get_current_element_code(mode_context)
                    chatwoot_msg_id_for_image = message_data.get("chatwoot_message_id")
                    try:
                        img_msg_id = int(chatwoot_msg_id_for_image) if chatwoot_msg_id_for_image else None
                    except (ValueError, TypeError):
                        img_msg_id = None
                    
                    saved, failed = await save_images_silently(
                        case_id=case_id,
                        conversation_id=conversation_id,
                        attachments=image_attachments,
                        user_phone=customer_phone,
                        chatwoot_message_id=img_msg_id,
                        element_code=element_code,
                    )
                    
                    # Update batch counter for confirmation worker
                    await update_batch_counter(
                        redis_client,
                        conversation_id,
                        additional_count=saved,
                        user_phone=customer_phone,
                        failed_count=failed,
                        case_id=case_id,
                    )
                    
                    logger.info(
                        f"Images saved silently | saved={saved} | failed={failed} | "
                        f"conversation_id={conversation_id}",
                    )
                    
                    # Check if this is also a completion message ("listo" + images)
                    if user_message.strip() and is_completion_message(user_message):
                        await reset_batch_counter(redis_client, conversation_id)
                        # Fall through to graph processing with the text
                    elif not user_message.strip():
                        # Image-only message — don't invoke graph
                        return
                else:
                    # Not in image collection mode — let graph handle it
                    logger.info(
                        f"Images received outside collection mode | "
                        f"conversation_id={conversation_id}",
                    )
            
            # Get user from DB by phone number (not by conversation_id)
            async with get_async_session() as session:
                result = await session.execute(
                    select(User).where(User.phone == customer_phone)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.error(
                        f"User not found for phone {customer_phone} (conversation {conversation_id})"
                    )
                    return
                
                user_id = str(user.id)
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Usuario"
                client_type = user.client_type or "particular"
            
            # ── Persist user message (fire-and-forget) ──────────────
            chatwoot_msg_id = message_data.get("chatwoot_message_id")
            try:
                chatwoot_msg_id_int = int(chatwoot_msg_id) if chatwoot_msg_id else None
            except (ValueError, TypeError):
                chatwoot_msg_id_int = None
            
            has_images = bool(attachments)
            image_count = len([a for a in attachments if a.get("data_url")]) if attachments else 0
            
            await save_user_message(
                conversation_id=conversation_id,
                content=user_message or "[imagen]",
                chatwoot_message_id=chatwoot_msg_id_int,
                has_images=has_images,
                image_count=image_count,
                user_id=user_id,
            )
            
            # ── Completion detection + reconciliation ─────────────────
            if user_message and is_completion_message(user_message):
                # Reset batch counter FIRST to prevent worker from sending stale confirmation
                await reset_batch_counter(redis_client, conversation_id)
                logger.info(
                    "batch_counter_reset_on_completion",
                    extra={
                        "conversation_id": conversation_id,
                        "user_message": user_message,
                    },
                )
                # Run reconciliation in background — don't block the response
                # (reconcile_on_completion contains 5-15s of asyncio.sleep)
                checkpointer = get_redis_checkpointer()
                asyncio.create_task(
                    _safe_reconcile(redis_client, checkpointer, conversation_id)
                )
            
            # Build config for graph invocation
            config = {
                "configurable": {
                    "thread_id": conversation_id,
                    "checkpoint_ns": "conversation",
                }
            }
            
            # Build initial state
            # Note: Only pass transient fields. Persistent fields like current_mode
            # will be restored from checkpoint (if exists) or initialized by router.
            state_input = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_message": user_message,
                "client_type": client_type,
                "messages": [],  # History loaded from checkpointer
                "incoming_attachments": [
                    {"type": "image", "data_url": a.get("data_url", "")}
                    for a in (attachments or [])
                    if a.get("data_url")
                ],
                # NOTE: mode_context is NOT passed here - LangGraph loads it from checkpoint
            }
            
            # Invoke graph (with mode chaining support)
            MAX_CHAIN_DEPTH = 2
            chain_depth = 0

            logger.info(
                f"Invoking graph for conversation {conversation_id}",
                extra={"conversation_id": conversation_id, "message_preview": (user_message or "")[:60]}
            )
            
            result = await graph.ainvoke(state_input, config=config)

            # ── Mode chaining loop ──────────────────────────────────────
            # When a tool signals _chain_next_mode, suppress the transition
            # message and re-invoke the graph so the next mode executes
            # in the same turn (zero-friction UX).
            while result.get("_chain_next_mode") and chain_depth < MAX_CHAIN_DEPTH:
                chain_depth += 1
                suppressed_msg = result.get("ai_response", "")
                target_mode = result.get("current_mode", "?")

                logger.info(
                    "mode_chain_continuation",
                    extra={
                        "conversation_id": conversation_id,
                        "chain_depth": chain_depth,
                        "target_mode": target_mode,
                        "suppressed_message": suppressed_msg[:80] if suppressed_msg else "",
                    }
                )

                # Build synthetic state_input for the chained invocation.
                # _is_chained_turn tells preprocess to skip counter increments.
                # The synthetic user_message gives EXPEDIENTE_MODE context to start.
                chain_state_input = {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "user_message": "Vamos, empezamos con el expediente.",
                    "client_type": client_type,
                    "messages": [],
                    "_is_chained_turn": True,
                }

                result = await graph.ainvoke(chain_state_input, config=config)
            
            # Extract response
            ai_response = result.get("ai_response", "")
            if not ai_response:
                logger.error(
                    "empty_ai_response_final_safety_net",
                    extra={"conversation_id": conversation_id}
                )
                ai_response = (
                    "Disculpa, he tenido un problema procesando tu mensaje. "
                    "¿Puedes repetir tu consulta?"
                )
            
            # Strip markdown for WhatsApp
            ai_response_clean = strip_markdown_for_whatsapp(ai_response)
            
            # Send text response
            # Try to convert conversation_id to int (required by Chatwoot)
            # If it's a test string, use None to let Chatwoot create a new conversation
            try:
                chatwoot_conv_id = int(conversation_id)
            except (ValueError, TypeError):
                logger.warning(f"conversation_id '{conversation_id}' is not numeric, using None for Chatwoot")
                chatwoot_conv_id = None
            
            await chatwoot.send_message(
                customer_phone=customer_phone,
                message=ai_response_clean,
                conversation_id=chatwoot_conv_id,
            )
            logger.info(f"Sent response to {conversation_id}")
            
            # ── Persist assistant message (fire-and-forget) ──────────
            await save_assistant_message(
                conversation_id=conversation_id,
                content=ai_response_clean,
            )
            
            # Handle pending images if any
            pending_images = result.get("pending_images")
            if pending_images:
                images = pending_images.get("images", [])
                follow_up = pending_images.get("follow_up_message")
                
                if images:
                    # Send images via ChatwootClient (not ChatwootImageService which is for downloads)
                    if chatwoot_conv_id:
                        # Extract URLs and captions from image dicts (images can be dicts with metadata or plain strings)
                        image_urls = []
                        image_captions = []
                        
                        for img in images:
                            if isinstance(img, dict):
                                # Image dict has 'url' field (e.g., {'url': '/images/xxx.png', 'tipo': 'base', ...})
                                url = img.get("url", "")
                                if url:
                                    image_urls.append(url)
                                    
                                    # Extract caption for THIS image
                                    # The 'descripcion' field already has priority: description > title
                                    # (set in agent/tools/image_tools.py line 386)
                                    descripcion = img.get("descripcion", "").strip()
                                    image_captions.append(descripcion if descripcion else None)
                            elif isinstance(img, str):
                                # Plain string URL (no caption)
                                image_urls.append(img)
                                image_captions.append(None)
                        
                        if image_urls:
                            sent_count = await chatwoot.send_images(
                                conversation_id=chatwoot_conv_id,
                                image_urls=image_urls,
                                captions=image_captions,
                            )
                            logger.info(f"Sent {sent_count}/{len(image_urls)} images to conversation {chatwoot_conv_id}")
                        else:
                            logger.warning(f"No valid image URLs extracted from {len(images)} image entries")
                    else:
                        logger.warning(f"Cannot send images: conversation_id '{conversation_id}' is not numeric")
                
                if follow_up:
                    # Deduplicate: skip follow_up if ai_response already contains
                    # similar question content (prevents double-asking the user)
                    ai_lower = ai_response_clean.lower()
                    fu_lower = follow_up.lower()
                    overlap_keywords = ["expediente", "opción", "opcion", "gestionar"]
                    has_overlap = any(kw in ai_lower and kw in fu_lower for kw in overlap_keywords)
                    if has_overlap and "?" in ai_lower:
                        logger.info(
                            "follow_up_suppressed: ai_response already contains similar question",
                            extra={
                                "conversation_id": conversation_id,
                                "follow_up_preview": follow_up[:80],
                            },
                        )
                    else:
                        await asyncio.sleep(5.0)  # Gap to prevent overtaking images
                        follow_up_clean = strip_markdown_for_whatsapp(follow_up)
                        await chatwoot.send_message(
                            customer_phone=customer_phone,
                            message=follow_up_clean,
                            conversation_id=int(conversation_id),
                        )
                        
                        # Persist follow-up message
                        await save_assistant_message(
                            conversation_id=conversation_id,
                            content=follow_up_clean,
                            has_images=bool(images),
                            image_count=len(images),
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
                    message="Disculpa, ha habido un error procesando tu mensaje. Por favor, intenta de nuevo.",
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
            messages = await read_from_stream(
                INCOMING_STREAM,
                CONSUMER_GROUP,
                consumer_name,
                block_ms=1000,
            )
            
            if not messages:
                consecutive_errors = 0
                continue
            
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
    
    # Start background tasks
    from agent.services.llm_metrics_persistence import metrics_flush_loop
    metrics_task = asyncio.create_task(metrics_flush_loop(shutdown_event))
    logger.info("LLM metrics flush background task started")
    
    batch_task = asyncio.create_task(
        image_batch_confirmation_worker(shutdown_event, checkpointer)
    )
    logger.info("Image batch confirmation worker started")
    
    from agent.services.cache_subscriber import cache_invalidation_listener
    cache_sub_task = asyncio.create_task(cache_invalidation_listener(shutdown_event))
    logger.info("Cache invalidation subscriber started")
    
    # Start consumer
    try:
        await consume_messages(graph, chatwoot, redis_client)
    except Exception as e:
        logger.critical(f"Fatal error in consumer: {e}", exc_info=True)
    finally:
        # Cancel background tasks
        for task in [metrics_task, batch_task, cache_sub_task]:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Agent shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
