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
import time
import uuid as uuid_mod
from datetime import datetime, UTC

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent.graphs.conversation_flow import create_conversation_graph
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes
from agent.fsm.case_collection import CollectionStep, get_case_fsm_state
from api.services.chatwoot_image_service import get_chatwoot_image_service
from database.connection import get_async_session
from database.models import User, Case, CaseImage
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.text_utils import strip_markdown_for_whatsapp
from shared.redis_client import (
    get_redis_client,
    publish_to_channel,
    create_consumer_group,
    read_from_stream,
    acknowledge_message,
    move_to_dead_letter,
    RedisServiceError,
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

# Image batching constants
IMAGE_BATCH_TIMEOUT_SECONDS = 60  # Wait this long after last image before confirming
IMAGE_BATCH_KEY_PREFIX = "image_batch:"  # Redis key prefix for batch tracking
IMAGE_BATCH_FINAL_PREFIX = "image_batch_final:"  # Stores confirmed count for "listo" reconciliation
COMPLETION_PHRASES = ["listo", "terminado", "ya está", "ya esta", "hecho", "fin", "ya", "eso es todo", "nada más", "nada mas"]

# Per-conversation locks to prevent race conditions during graph invocations
_conversation_locks: dict[str, asyncio.Lock] = {}


def get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific conversation."""
    if conversation_id not in _conversation_locks:
        _conversation_locks[conversation_id] = asyncio.Lock()
    return _conversation_locks[conversation_id]


async def wait_for_redis_ready(client, max_wait: int = 60) -> bool:
    """
    Espera hasta que Redis esté disponible.

    Args:
        client: Cliente Redis
        max_wait: Tiempo máximo de espera en segundos

    Returns:
        True si Redis está disponible, False si se agotó el tiempo
    """
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
    """
    Inicializa conexiones Redis con reintentos y backoff exponencial.

    Args:
        max_retries: Número máximo de reintentos
        base_delay: Delay base para backoff exponencial

    Returns:
        Tuple (client, checkpointer) si tiene éxito

    Raises:
        Exception si se agotan los reintentos
    """
    for attempt in range(max_retries):
        try:
            client = get_redis_client()
            await client.ping()  # Verificar conexión
            logger.info("Redis connection verified")

            checkpointer = get_redis_checkpointer()
            await initialize_redis_indexes(checkpointer)
            logger.info("Redis checkpointer initialized successfully")

            return client, checkpointer

        except Exception as e:
            delay = min(60, base_delay * (2 ** attempt))
            logger.warning(
                f"Redis init failed (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.error("Max retries reached for Redis initialization. Exiting.")
                raise


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


# =============================================================================
# IMAGE BATCHING HELPERS
# =============================================================================


async def get_fsm_state_from_checkpoint(
    checkpointer,
    conversation_id: str,
) -> dict | None:
    """
    Read FSM state from LangGraph checkpoint.

    Args:
        checkpointer: AsyncRedisSaver instance
        conversation_id: The thread_id to look up

    Returns:
        The fsm_state dict if found, None otherwise
    """
    try:
        config = {"configurable": {"thread_id": conversation_id}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
            return None

        # Extract channel_values from checkpoint
        channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        return channel_values.get("fsm_state")

    except Exception as e:
        logger.warning(
            f"Failed to get FSM state from checkpoint: {e}",
            extra={"conversation_id": conversation_id},
        )
        return None


def is_in_collect_images_step(fsm_state: dict | None) -> bool:
    """Check if the FSM is currently in the COLLECT_IMAGES step."""
    if not fsm_state:
        return False

    case_fsm = get_case_fsm_state(fsm_state)
    step = case_fsm.get("step")
    return step == CollectionStep.COLLECT_IMAGES.value


def is_image_attachment(attachment: dict) -> bool:
    """Check if an attachment is an image type."""
    file_type = attachment.get("file_type", "")
    return file_type == "image"


def is_completion_message(message_text: str | None) -> bool:
    """
    Check if message text indicates user wants to finish sending images.

    Args:
        message_text: The user's message text

    Returns:
        True if message contains a completion phrase
    """
    if not message_text:
        return False

    text_lower = message_text.lower().strip()

    # Exact match or starts with completion phrase
    for phrase in COMPLETION_PHRASES:
        if text_lower == phrase or text_lower.startswith(phrase + " "):
            return True

    return False


async def get_case_image_count(case_id: str) -> int:
    """
    Get the count of existing images for a case.

    Args:
        case_id: UUID of the case

    Returns:
        Number of images already saved for this case
    """
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(CaseImage.id)).where(CaseImage.case_id == case_id)
            )
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"Failed to get image count for case {case_id}: {e}")
        return 0


async def save_images_silently(
    case_id: str,
    conversation_id: str,
    attachments: list[dict],
    user_phone: str,
    chatwoot_message_id: int | None = None,
) -> tuple[int, int]:
    """
    Save images from attachments to disk and database without sending a response.

    Args:
        case_id: UUID of the case to attach images to
        conversation_id: For logging
        attachments: List of attachment dicts from Chatwoot
        user_phone: User's phone number for logging
        chatwoot_message_id: Chatwoot message ID for reconciliation dedup

    Returns:
        Tuple of (saved_count, failed_count)
    """
    image_service = get_chatwoot_image_service()
    saved_count = 0
    failed_count = 0

    # Filter to only image attachments
    image_attachments = [a for a in attachments if is_image_attachment(a)]

    if not image_attachments:
        return 0, 0

    # Get existing image count for incremental naming
    existing_count = await get_case_image_count(case_id)

    logger.info(
        f"Saving {len(image_attachments)} images silently | "
        f"case_id={case_id} | conversation_id={conversation_id} | "
        f"existing_count={existing_count} | chatwoot_msg_id={chatwoot_message_id}",
        extra={
            "conversation_id": conversation_id,
            "case_id": case_id,
            "image_count": len(image_attachments),
            "existing_count": existing_count,
        },
    )

    # Use case short ID for naming: case_4df65b1a_image_1
    case_short_id = case_id[:8]

    for i, attachment in enumerate(image_attachments):
        data_url = attachment.get("data_url")
        if not data_url:
            logger.warning(f"Attachment missing data_url: {attachment}")
            failed_count += 1
            continue

        try:
            display_name = f"case_{case_short_id}_image_{existing_count + saved_count + 1}"
            download_result = await image_service.download_image(
                data_url=data_url,
                display_name=display_name,
                element_code=None,
            )

            if not download_result:
                failed_count += 1
                logger.error(
                    f"Failed to download image | url={data_url} | case_id={case_id}",
                    extra={"conversation_id": conversation_id, "case_id": case_id, "url": data_url},
                )
                continue

            # Save to database
            async with get_async_session() as session:
                case_image = CaseImage(
                    case_id=case_id,
                    stored_filename=download_result["stored_filename"],
                    original_filename=download_result.get("original_filename"),
                    mime_type=download_result["mime_type"],
                    file_size=download_result.get("file_size"),
                    display_name=display_name,
                    description="Imagen enviada por usuario via WhatsApp",
                    element_code=None,
                    image_type="user_upload",
                    chatwoot_message_id=chatwoot_message_id,
                    is_valid=None,
                )
                session.add(case_image)
                await session.commit()

                logger.info(
                    f"Image saved to database | "
                    f"case_id={case_id} | display_name={display_name} | "
                    f"filename={download_result['stored_filename']}",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "stored_filename": download_result["stored_filename"],
                    },
                )
                saved_count += 1

        except Exception as e:
            failed_count += 1
            logger.error(
                f"Error saving image: {e}",
                extra={"conversation_id": conversation_id, "case_id": case_id},
                exc_info=True,
            )

    return saved_count, failed_count


async def reconcile_conversation_images(
    conversation_id: str,
    case_id: str,
    case_created_at: float | None = None,
) -> tuple[int, int]:
    """
    Reconcile images between Chatwoot and our database.

    Queries Chatwoot API for all image messages in the conversation,
    compares with what we have in DB by chatwoot_message_id, and
    downloads any missing ones. This catches images whose webhooks
    were dropped by Chatwoot.

    Args:
        conversation_id: Chatwoot conversation ID
        case_id: Case UUID string
        case_created_at: Unix timestamp of case creation (for filtering)

    Returns:
        Tuple of (reconciled_count, failed_count)
    """
    chatwoot = ChatwootClient()
    reconciled = 0
    failed = 0

    try:
        conv_id = int(conversation_id)
    except (ValueError, TypeError):
        logger.warning(f"Cannot reconcile: invalid conversation_id={conversation_id}")
        return 0, 0

    # Step 1: Get all image messages from Chatwoot
    try:
        messages = await chatwoot.get_conversation_messages(
            conversation_id=conv_id,
            after=int(case_created_at) if case_created_at else None,
        )
    except Exception as e:
        logger.error(
            f"Reconciliation: failed to fetch Chatwoot messages | "
            f"conversation_id={conversation_id}: {e}",
            exc_info=True,
        )
        return 0, 0

    if not messages:
        logger.debug(f"Reconciliation: no image messages from Chatwoot | conversation_id={conversation_id}")
        return 0, 0

    # Step 2: Get existing chatwoot_message_ids from DB for this case
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImage.chatwoot_message_id)
                .where(CaseImage.case_id == uuid_mod.UUID(case_id))
                .where(CaseImage.chatwoot_message_id.isnot(None))
            )
            existing_msg_ids = {row[0] for row in result.fetchall()}
    except Exception as e:
        logger.error(f"Reconciliation: failed to query DB: {e}", exc_info=True)
        return 0, 0

    # Step 3: Find messages not in our DB
    missing_messages = [
        msg for msg in messages
        if msg.get("id") not in existing_msg_ids
    ]

    if not missing_messages:
        logger.info(
            f"Reconciliation: all images accounted for | "
            f"conversation_id={conversation_id} | chatwoot_msgs={len(messages)} | db_msgs={len(existing_msg_ids)}"
        )
        return 0, 0

    logger.info(
        f"Reconciliation: found {len(missing_messages)} missing image messages | "
        f"conversation_id={conversation_id} | case_id={case_id}"
    )

    # Step 4: Download and save missing images
    image_service = get_chatwoot_image_service()
    existing_count = await get_case_image_count(case_id)
    case_short_id = case_id[:8]

    for msg in missing_messages:
        msg_id = msg.get("id")
        attachments = msg.get("attachments", [])

        for attachment in attachments:
            if attachment.get("file_type") != "image":
                continue

            data_url = attachment.get("data_url")
            if not data_url:
                failed += 1
                continue

            try:
                display_name = f"case_{case_short_id}_image_{existing_count + reconciled + 1}"
                download_result = await image_service.download_image(
                    data_url=data_url,
                    display_name=display_name,
                    element_code=None,
                )

                if not download_result:
                    failed += 1
                    logger.warning(
                        f"Reconciliation: download failed | msg_id={msg_id} | url={data_url}"
                    )
                    continue

                # Save to database
                async with get_async_session() as session:
                    case_image = CaseImage(
                        case_id=uuid_mod.UUID(case_id),
                        stored_filename=download_result["stored_filename"],
                        original_filename=data_url.split("/")[-1] if "/" in data_url else None,
                        mime_type=download_result["mime_type"],
                        file_size=download_result.get("file_size"),
                        display_name=display_name,
                        description="Imagen recuperada por reconciliación",
                        element_code=None,
                        image_type="user_upload",
                        chatwoot_message_id=msg_id,
                        is_valid=None,
                    )
                    session.add(case_image)
                    await session.commit()

                reconciled += 1
                logger.info(
                    f"Reconciliation: image recovered | msg_id={msg_id} | "
                    f"display_name={display_name} | case_id={case_id}"
                )

            except Exception as e:
                failed += 1
                logger.error(
                    f"Reconciliation: error saving image from msg {msg_id}: {e}",
                    exc_info=True,
                )

    if reconciled > 0 or failed > 0:
        logger.info(
            f"Reconciliation complete | conversation_id={conversation_id} | "
            f"recovered={reconciled} | failed={failed}"
        )

    return reconciled, failed


async def get_batch_info(redis_client, conversation_id: str) -> tuple[int, float]:
    """
    Get current batch info from Redis.

    Returns:
        Tuple of (count, last_update_timestamp)
    """
    key = f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}"
    try:
        data = await redis_client.hgetall(key)
        if not data:
            return 0, 0.0

        count = int(data.get(b"count", data.get("count", 0)))
        last_update = float(data.get(b"last_update", data.get("last_update", 0)))
        return count, last_update
    except Exception as e:
        logger.warning(f"Failed to get batch info: {e}")
        return 0, 0.0


async def update_batch_counter(
    redis_client,
    conversation_id: str,
    additional_count: int,
    user_phone: str,
    failed_count: int = 0,
    case_id: str | None = None,
) -> int:
    """
    Update the batch counter in Redis.

    Args:
        redis_client: Redis client
        conversation_id: Conversation ID
        additional_count: Number of images successfully saved
        user_phone: User's phone number (stored for confirmation worker)
        failed_count: Number of images that failed to download
        case_id: Case UUID string (stored for reconciliation in worker)

    Returns:
        New total count
    """
    key = f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}"
    try:
        current_count, _ = await get_batch_info(redis_client, conversation_id)
        new_count = current_count + additional_count

        # Get existing failed count
        data = await redis_client.hgetall(key)
        existing_failed = int(data.get(b"failed", data.get("failed", 0))) if data else 0

        mapping: dict[str, str] = {
            "count": str(new_count),
            "failed": str(existing_failed + failed_count),
            "last_update": str(time.time()),
            "user_phone": user_phone,
        }
        # Store case_id if provided (for reconciliation without FSM lookup)
        if case_id:
            mapping["case_id"] = case_id

        await redis_client.hset(key, mapping=mapping)
        # Set TTL of 1 hour to auto-cleanup stale batches
        await redis_client.expire(key, 3600)

        logger.debug(
            f"Batch counter updated: {current_count} -> {new_count} (failed: {existing_failed + failed_count}) | "
            f"conversation_id={conversation_id}",
        )
        return new_count
    except Exception as e:
        logger.error(f"Failed to update batch counter: {e}")
        return 0


async def reset_batch_counter(redis_client, conversation_id: str) -> None:
    """Reset/delete the batch counter for a conversation."""
    key = f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}"
    try:
        await redis_client.delete(key)
        logger.debug(f"Batch counter reset | conversation_id={conversation_id}")
    except Exception as e:
        logger.warning(f"Failed to reset batch counter: {e}")


async def get_total_case_images(case_id: str) -> int:
    """Get total number of images for a case from database."""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImage).where(CaseImage.case_id == case_id)
            )
            images = result.scalars().all()
            return len(images)
    except Exception as e:
        logger.warning(f"Failed to get case image count: {e}")
        return 0


async def reconcile_on_completion(
    redis_client,
    checkpointer,
    conversation_id: str,
) -> None:
    """
    Run final image reconciliation when user says 'listo'.

    This ensures all images are recovered from Chatwoot before the FSM advances.
    Addresses the root cause where Chatwoot processes images asynchronously and
    some may not be available via API during the batch confirmation reconciliation.

    Uses the confirmed_count (from batch confirmation) to detect if images are
    still missing and retries with increasing delays.

    Args:
        redis_client: Redis client instance
        checkpointer: AsyncRedisSaver for reading FSM state
        conversation_id: Chatwoot conversation ID
    """
    try:
        # Check if we're in COLLECT_IMAGES phase and get case_id
        fsm_state = await get_fsm_state_from_checkpoint(checkpointer, conversation_id)
        if not is_in_collect_images_step(fsm_state):
            return

        case_fsm = get_case_fsm_state(fsm_state) if fsm_state else {}
        case_id = case_fsm.get("case_id")
        if not case_id:
            return

        # Get case_created_at for filtering
        case_created_at = None
        try:
            async with get_async_session() as session:
                case_obj = await session.get(Case, uuid_mod.UUID(case_id))
                if case_obj and case_obj.created_at:
                    case_created_at = case_obj.created_at.timestamp()
        except Exception as e:
            logger.warning(f"Completion reconciliation: could not get case created_at: {e}")

        # Read the confirmed count from batch confirmation (Fix 3)
        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
        final_data = await redis_client.hgetall(final_key)
        confirmed_total = int(final_data.get("total_images", final_data.get(b"total_images", 0)))

        # Get current image count in DB
        current_count = await get_case_image_count(case_id)

        logger.info(
            f"Completion reconciliation starting | conversation_id={conversation_id} | "
            f"current_db_count={current_count} | confirmed_total={confirmed_total} | "
            f"case_id={case_id}",
            extra={"conversation_id": conversation_id, "case_id": case_id},
        )

        # Brief delay to let Chatwoot finish processing
        await asyncio.sleep(5)

        # First reconciliation pass
        reconciled, failed = await reconcile_conversation_images(
            conversation_id=conversation_id,
            case_id=case_id,
            case_created_at=case_created_at,
        )

        if reconciled > 0:
            logger.info(
                f"Completion reconciliation pass 1: recovered {reconciled} images | "
                f"conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )

        # Check if we still have fewer images than confirmed
        new_count = await get_case_image_count(case_id)
        if confirmed_total > 0 and new_count < confirmed_total:
            logger.info(
                f"Completion reconciliation: still missing images "
                f"(have {new_count}, confirmed {confirmed_total}), "
                f"retrying after 10s | conversation_id={conversation_id}",
                extra={"conversation_id": conversation_id},
            )
            await asyncio.sleep(10)

            # Second reconciliation pass
            retry_reconciled, retry_failed = await reconcile_conversation_images(
                conversation_id=conversation_id,
                case_id=case_id,
                case_created_at=case_created_at,
            )
            if retry_reconciled > 0:
                logger.info(
                    f"Completion reconciliation pass 2: recovered {retry_reconciled} more | "
                    f"conversation_id={conversation_id}",
                    extra={"conversation_id": conversation_id},
                )

        # Final count
        final_count = await get_case_image_count(case_id)
        logger.info(
            f"Completion reconciliation done | conversation_id={conversation_id} | "
            f"final_count={final_count} | confirmed_total={confirmed_total}",
            extra={"conversation_id": conversation_id, "final_count": final_count},
        )

        # Cleanup final key
        try:
            await redis_client.delete(final_key)
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Error in completion reconciliation: {e}",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )


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
    settings = get_settings()

    logger.info("Initializing Redis with retry logic...")

    # Initialize Redis with retry and backoff
    client, checkpointer = await initialize_redis_with_retry()

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
        attachments: list[dict] | None = None,
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
            attachments: Optional list of attachments from Chatwoot
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
            "incoming_attachments": attachments or [],
            "updated_at": datetime.now(UTC),
        }

        # Log if there are attachments
        if attachments:
            logger.info(
                f"Message has {len(attachments)} attachment(s) | "
                f"conversation_id={conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "attachment_count": len(attachments),
                    "attachment_types": [a.get("file_type") for a in attachments],
                },
            )

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
            outgoing_payload["pending_images"] = pending_images
            # Count actual images (handle both dict and list formats)
            if isinstance(pending_images, dict):
                actual_image_count = len(pending_images.get("images", []))
            else:
                actual_image_count = len(pending_images)
            logger.info(
                f"Including {actual_image_count} images in outgoing message | "
                f"conversation_id={conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "image_count": actual_image_count,
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

        # Counter for consecutive errors (for exponential backoff)
        consecutive_errors = 0

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

                    # Reset error counter on successful read
                    if consecutive_errors > 0:
                        logger.info(
                            f"Redis connection recovered after {consecutive_errors} errors"
                        )
                        consecutive_errors = 0

                    # =============================================================
                    # IMAGES-FIRST PROCESSING: Separate image from text messages
                    # to prevent race conditions where graph invocations change
                    # FSM state before all images are saved.
                    # =============================================================
                    
                    # Step 1: Parse all messages and categorize
                    image_msgs = []  # Messages with images to save silently
                    text_msgs = []   # Messages to process through the graph
                    
                    for stream_msg_id, data in messages:
                        try:
                            conversation_id = data.get("conversation_id")
                            user_phone = data.get("customer_phone")
                            message_text = data.get("message_text")
                            user_name = data.get("customer_name")
                            user_id = data.get("user_id")
                            raw_attachments = data.get("attachments", [])
                            if isinstance(raw_attachments, str):
                                try:
                                    raw_attachments = json.loads(raw_attachments)
                                except json.JSONDecodeError:
                                    raw_attachments = []
                            attachments = raw_attachments if isinstance(raw_attachments, list) else []

                            # Extract chatwoot_message_id for reconciliation
                            raw_msg_id = data.get("chatwoot_message_id")
                            chatwoot_message_id = int(raw_msg_id) if raw_msg_id else None

                            parsed = {
                                "stream_msg_id": stream_msg_id,
                                "data": data,
                                "conversation_id": conversation_id,
                                "user_phone": user_phone,
                                "message_text": message_text,
                                "user_name": user_name,
                                "user_id": user_id,
                                "attachments": attachments,
                                "chatwoot_message_id": chatwoot_message_id,
                            }

                            has_images = any(is_image_attachment(a) for a in attachments)
                            if has_images and conversation_id:
                                image_msgs.append(parsed)
                            else:
                                text_msgs.append(parsed)

                        except Exception as e:
                            logger.error(f"Error parsing stream message {stream_msg_id}: {e}")
                            try:
                                await move_to_dead_letter(
                                    INCOMING_STREAM, CONSUMER_GROUP, stream_msg_id, data, str(e)
                                )
                            except Exception:
                                pass

                    # Step 2: Process ALL image messages FIRST (no graph invocation)
                    for msg in image_msgs:
                        try:
                            conversation_id = msg["conversation_id"]
                            stream_msg_id = msg["stream_msg_id"]
                            attachments = msg["attachments"]
                            message_text = msg["message_text"]
                            user_phone = msg["user_phone"]
                            chatwoot_msg_id = msg.get("chatwoot_message_id")

                            logger.info(
                                f"Processing image message | conversation_id={conversation_id} | "
                                f"attachments={len(attachments)} | chatwoot_msg_id={chatwoot_msg_id}",
                                extra={"conversation_id": conversation_id},
                            )

                            # Check if in COLLECT_IMAGES phase
                            fsm_state = await get_fsm_state_from_checkpoint(
                                checkpointer, conversation_id
                            )

                            if is_in_collect_images_step(fsm_state):
                                case_fsm = get_case_fsm_state(fsm_state) if fsm_state else {}
                                case_id = case_fsm.get("case_id")

                                if case_id:
                                    saved_count, failed_count = await save_images_silently(
                                        case_id=case_id,
                                        conversation_id=conversation_id,
                                        attachments=attachments,
                                        user_phone=user_phone or "",
                                        chatwoot_message_id=chatwoot_msg_id,
                                    )

                                    if saved_count > 0 or failed_count > 0:
                                        await update_batch_counter(
                                            client, conversation_id,
                                            saved_count, user_phone or "",
                                            failed_count=failed_count,
                                            case_id=case_id,
                                        )

                                    if failed_count > 0:
                                        logger.warning(
                                            f"Image download failures | saved={saved_count} "
                                            f"failed={failed_count} | conversation_id={conversation_id}",
                                            extra={"conversation_id": conversation_id},
                                        )

                                    # If user also sent completion text with the image
                                    if is_completion_message(message_text):
                                        await reset_batch_counter(client, conversation_id)
                                        # Move to text processing for graph invocation
                                        text_msgs.append(msg)
                                    else:
                                        # ACK and done - no graph needed
                                        if stream_msg_id and settings.USE_REDIS_STREAMS:
                                            try:
                                                await acknowledge_message(
                                                    INCOMING_STREAM, CONSUMER_GROUP, stream_msg_id
                                                )
                                            except Exception as ack_error:
                                                logger.warning(f"Failed to ACK: {ack_error}")
                                    continue
                                else:
                                    logger.warning(
                                        f"In COLLECT_IMAGES but no case_id | conversation_id={conversation_id}"
                                    )

                            # Not in COLLECT_IMAGES or no case_id: process as text
                            text_msgs.append(msg)

                        except Exception as e:
                            logger.error(f"Error processing image message: {e}", exc_info=True)
                            try:
                                await move_to_dead_letter(
                                    INCOMING_STREAM, CONSUMER_GROUP,
                                    msg["stream_msg_id"], msg["data"], str(e)
                                )
                            except Exception:
                                pass

                    # Step 3: Process text messages WITH per-conversation lock
                    for msg in text_msgs:
                        stream_msg_id = msg["stream_msg_id"]
                        data = msg["data"]
                        try:
                            conversation_id = msg["conversation_id"]

                            # Fix 1: Run final reconciliation when user says "listo"
                            # before invoking the graph (ensures all images are recovered)
                            if conversation_id and is_completion_message(msg.get("message_text")):
                                await reconcile_on_completion(
                                    redis_client=client,
                                    checkpointer=checkpointer,
                                    conversation_id=conversation_id,
                                )

                            lock = get_conversation_lock(conversation_id) if conversation_id else None

                            if lock:
                                async with lock:
                                    await process_message(
                                        conversation_id=conversation_id,
                                        user_phone=msg["user_phone"],
                                        message_text=msg["message_text"],
                                        user_name=msg["user_name"],
                                        user_id=msg["user_id"],
                                        stream_msg_id=stream_msg_id,
                                        attachments=msg["attachments"],
                                    )
                            else:
                                await process_message(
                                    conversation_id=conversation_id,
                                    user_phone=msg["user_phone"],
                                    message_text=msg["message_text"],
                                    user_name=msg["user_name"],
                                    user_id=msg["user_id"],
                                    stream_msg_id=stream_msg_id,
                                    attachments=msg["attachments"],
                                )

                        except Exception as e:
                            logger.error(
                                f"Error processing stream message {stream_msg_id}: {e}",
                                exc_info=True,
                            )
                            try:
                                await move_to_dead_letter(
                                    INCOMING_STREAM, CONSUMER_GROUP, stream_msg_id, data, str(e)
                                )
                            except Exception as dlq_error:
                                logger.error(f"Failed to move to DLQ: {dlq_error}")
                            continue

                except asyncio.CancelledError:
                    raise
                except (RedisServiceError, Exception) as e:
                    consecutive_errors += 1
                    # Exponential backoff: 2^n seconds, max 30 seconds
                    retry_delay = min(
                        MAX_RETRY_DELAY,
                        INIT_BASE_DELAY ** min(consecutive_errors, MAX_CONSECUTIVE_ERRORS)
                    )

                    logger.error(
                        f"Error reading from stream (attempt {consecutive_errors}): {e}",
                        exc_info=True,
                    )
                    logger.warning(f"Retrying in {retry_delay:.1f}s...")

                    # If many consecutive errors, wait for Redis to be ready
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.warning(
                            f"Too many consecutive errors ({consecutive_errors}), "
                            "checking Redis availability..."
                        )
                        redis_ready = await wait_for_redis_ready(client, max_wait=60)
                        if not redis_ready:
                            logger.error("Redis not available after 60s wait")
                        else:
                            logger.info("Redis is available again")

                    await asyncio.sleep(retry_delay)

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
                    user_phone = data.get("customer_phone")
                    message_text = data.get("message_text")
                    user_name = data.get("customer_name")
                    user_id = data.get("user_id")
                    raw_cw_msg_id = data.get("chatwoot_message_id")
                    chatwoot_msg_id = int(raw_cw_msg_id) if raw_cw_msg_id else None
                    attachments = data.get("attachments", [])

                    logger.info(
                        f"Message received: conversation_id={conversation_id}, "
                        f"phone={user_phone}, user_id={user_id}, attachments={len(attachments)}",
                        extra={
                            "conversation_id": conversation_id,
                            "user_phone": user_phone,
                            "user_id": user_id,
                            "attachment_count": len(attachments),
                        },
                    )

                    # =============================================================
                    # IMAGE BATCHING: Intercept images during COLLECT_IMAGES phase
                    # =============================================================
                    has_images = any(is_image_attachment(a) for a in attachments)

                    if has_images and conversation_id:
                        # Check if we're in COLLECT_IMAGES phase
                        fsm_state = await get_fsm_state_from_checkpoint(
                            checkpointer, conversation_id
                        )

                        if is_in_collect_images_step(fsm_state):
                            # Get case_id from FSM state
                            case_fsm = get_case_fsm_state(fsm_state) if fsm_state else {}
                            case_id = case_fsm.get("case_id")

                            if case_id:
                                # Save images silently (no response to user)
                                saved_count, failed_count = await save_images_silently(
                                    case_id=case_id,
                                    conversation_id=conversation_id,
                                    attachments=attachments,
                                    user_phone=user_phone or "",
                                    chatwoot_message_id=chatwoot_msg_id,
                                )

                                if saved_count > 0 or failed_count > 0:
                                    # Update batch counter
                                    await update_batch_counter(
                                        client,
                                        conversation_id,
                                        saved_count,
                                        user_phone or "",
                                        failed_count=failed_count,
                                        case_id=case_id,
                                    )

                                if failed_count > 0:
                                    logger.warning(
                                        f"Image download failures (pub/sub) | "
                                        f"saved={saved_count} failed={failed_count} | "
                                        f"conversation_id={conversation_id}",
                                        extra={"conversation_id": conversation_id},
                                    )

                                # Check if user wants to proceed
                                if is_completion_message(message_text):
                                    logger.info(
                                        f"Completion message detected (pub/sub), proceeding | "
                                        f"conversation_id={conversation_id}",
                                        extra={"conversation_id": conversation_id},
                                    )
                                    # Reset batch counter before proceeding
                                    await reset_batch_counter(client, conversation_id)
                                    # Continue to process_message to advance FSM
                                else:
                                    # Skip graph invocation for silent image saves
                                    logger.info(
                                        f"Images saved silently (pub/sub) | "
                                        f"saved={saved_count} failed={failed_count} | "
                                        f"conversation_id={conversation_id}",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "saved_count": saved_count,
                                        },
                                    )
                                    continue  # Skip to next message

                    # Fix 1: Run final reconciliation when user says "listo" (pub/sub)
                    if conversation_id and is_completion_message(message_text):
                        await reconcile_on_completion(
                            redis_client=client,
                            checkpointer=checkpointer,
                            conversation_id=conversation_id,
                        )

                    # Process the message normally
                    await process_message(
                        conversation_id=conversation_id,
                        user_phone=user_phone,
                        message_text=message_text,
                        user_name=user_name,
                        user_id=user_id,
                        attachments=attachments,
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

    Includes retry logic with exponential backoff for Redis connection failures.

    Message format (outgoing_messages):
        {
            "conversation_id": "wa-msg-123",
            "customer_phone": "+34612345678",
            "message": "AI response text",
            "pending_images": {"images": [...], "follow_up_message": "..."}
        }
    """
    chatwoot = ChatwootClient()
    consecutive_errors = 0
    pubsub = None

    logger.info("Starting outgoing_messages subscriber with retry logic...")

    while not shutdown_event.is_set():
        try:
            # Get fresh Redis client for each reconnection attempt
            client = get_redis_client()

            # Create new pubsub connection
            pubsub = client.pubsub()
            await pubsub.subscribe("outgoing_messages")

            logger.info("Subscribed to 'outgoing_messages' channel")

            # Reset error counter on successful connection
            if consecutive_errors > 0:
                logger.info(f"Outgoing subscriber recovered after {consecutive_errors} errors")
                consecutive_errors = 0

            # Inner loop for messages
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    customer_phone = data.get("customer_phone")
                    message_text = data.get("message")
                    conversation_id = data.get("conversation_id")

                    # Handle both old format (list) and new format (dict with images/follow_up)
                    pending_images = data.get("pending_images", data.get("images", []))
                    images = []
                    follow_up_message = None

                    if isinstance(pending_images, dict):
                        images = pending_images.get("images", [])
                        follow_up_message = pending_images.get("follow_up_message")
                    elif isinstance(pending_images, list):
                        images = pending_images

                    # Strip markdown for WhatsApp compatibility
                    message_text = strip_markdown_for_whatsapp(message_text)

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
                                # Accept both "base" and "base_documentation" for backward compatibility
                                if tipo in ("base", "base_documentation"):
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
                            tipo = img_data.get("tipo", "base")

                            if not url:
                                continue

                            logger.debug(
                                f"Processing image | tipo={tipo}, url={url}",
                                extra={"tipo": tipo, "url": url, "conversation_id": conversation_id}
                            )

                            absolute_url = make_absolute_url(url)
                            if not absolute_url:
                                logger.warning(
                                    f"Failed to make absolute URL | url={url}",
                                    extra={"url": url, "conversation_id": conversation_id}
                                )
                                continue

                            try:
                                success = await chatwoot.send_image(
                                    conversation_id=int(conversation_id),
                                    image_url=absolute_url,
                                    caption=descripcion,
                                )
                                if success:
                                    logger.info(
                                        f"Image sent successfully | tipo={tipo}, url={absolute_url}",
                                        extra={"tipo": tipo, "url": absolute_url}
                                    )
                                    sent_count += 1
                                else:
                                    logger.warning(
                                        f"Failed to send image | tipo={tipo}, url={absolute_url}",
                                        extra={"tipo": tipo, "url": absolute_url}
                                    )

                                # Delay between images (1.5s for WhatsApp ordering)
                                if base_images.index(img_data) < len(base_images) - 1:
                                    await asyncio.sleep(1.5)
                            except Exception as e:
                                logger.error(
                                    f"Failed to send base image: {e}",
                                    extra={"conversation_id": conversation_id},
                                )

                        # Delay between base and element groups for WhatsApp ordering
                        if base_images and elemento_images:
                            await asyncio.sleep(1.5)

                        # Send element-specific images after (each with its own description)
                        for img_data in elemento_images:
                            url = img_data.get("url")
                            descripcion = img_data.get("descripcion", "")
                            tipo = img_data.get("tipo", "elemento")

                            if not url:
                                continue

                            logger.debug(
                                f"Processing image | tipo={tipo}, url={url}",
                                extra={"tipo": tipo, "url": url, "conversation_id": conversation_id}
                            )

                            absolute_url = make_absolute_url(url)
                            if not absolute_url:
                                logger.warning(
                                    f"Failed to make absolute URL | url={url}",
                                    extra={"url": url, "conversation_id": conversation_id}
                                )
                                continue

                            try:
                                success = await chatwoot.send_image(
                                    conversation_id=int(conversation_id),
                                    image_url=absolute_url,
                                    caption=descripcion,
                                )
                                if success:
                                    logger.info(
                                        f"Image sent successfully | tipo={tipo}, url={absolute_url}",
                                        extra={"tipo": tipo, "url": absolute_url}
                                    )
                                    sent_count += 1
                                else:
                                    logger.warning(
                                        f"Failed to send image | tipo={tipo}, url={absolute_url}",
                                        extra={"tipo": tipo, "url": absolute_url}
                                    )

                                # Delay between images (1.5s for WhatsApp ordering)
                                if elemento_images.index(img_data) < len(elemento_images) - 1:
                                    await asyncio.sleep(1.5)
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

                        # Send follow_up message after all images (1.5s delay for ordering)
                        if follow_up_message and sent_count > 0:
                            await asyncio.sleep(1.5)
                            success = await chatwoot.send_message(
                                customer_phone=customer_phone,
                                message=follow_up_message,
                                conversation_id=conversation_id,
                            )
                            if success:
                                logger.info(
                                    f"Follow-up message sent | conversation_id={conversation_id}",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "follow_up_message": follow_up_message[:50] + "..." if len(follow_up_message) > 50 else follow_up_message,
                                    },
                                )
                            else:
                                logger.warning(
                                    f"Failed to send follow-up message | conversation_id={conversation_id}",
                                    extra={"conversation_id": conversation_id},
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
            if pubsub:
                try:
                    await pubsub.unsubscribe("outgoing_messages")
                    await pubsub.close()
                except Exception:
                    pass
            raise

        except Exception as e:
            # Connection error - apply exponential backoff and retry
            consecutive_errors += 1
            retry_delay = min(
                MAX_RETRY_DELAY,
                INIT_BASE_DELAY ** min(consecutive_errors, MAX_CONSECUTIVE_ERRORS)
            )

            logger.error(
                f"Outgoing subscriber error (attempt {consecutive_errors}): {e}",
                exc_info=consecutive_errors == 1,  # Full traceback only on first error
            )
            logger.warning(f"Outgoing subscriber retrying in {retry_delay:.1f}s...")

            # Cleanup old pubsub connection
            if pubsub:
                try:
                    await pubsub.unsubscribe("outgoing_messages")
                    await pubsub.close()
                except Exception:
                    pass
                pubsub = None

            # If many consecutive errors, wait for Redis to be ready
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.warning(
                    f"Outgoing subscriber: too many errors ({consecutive_errors}), "
                    "checking Redis availability..."
                )
                client = get_redis_client()
                redis_ready = await wait_for_redis_ready(client, max_wait=60)
                if not redis_ready:
                    logger.error("Redis not available after 60s wait")
                else:
                    logger.info("Redis is available again, reconnecting outgoing subscriber")

            await asyncio.sleep(retry_delay)

    # Cleanup on exit
    logger.info("Outgoing message subscriber stopped")


async def image_batch_confirmation_worker():
    """
    Background worker that sends batch confirmation messages after timeout.

    This worker periodically checks Redis for image batches that have been
    idle for IMAGE_BATCH_TIMEOUT_SECONDS and sends a confirmation message
    to the user.

    The confirmation tells the user how many images were received and
    prompts them to say "listo" when done.
    """
    chatwoot = ChatwootClient()
    check_interval = 3  # Check every 3 seconds

    logger.info(
        f"Image batch confirmation worker started | "
        f"timeout={IMAGE_BATCH_TIMEOUT_SECONDS}s | check_interval={check_interval}s"
    )

    while not shutdown_event.is_set():
        try:
            client = get_redis_client()

            # Scan for all batch keys
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor,
                    match=f"{IMAGE_BATCH_KEY_PREFIX}*",
                    count=100,
                )

                for key in keys:
                    try:
                        # Get batch data
                        data = await client.hgetall(key)
                        if not data:
                            continue

                        # Handle both bytes and string keys (depends on Redis client config)
                        count = int(data.get(b"count", data.get("count", 0)))
                        failed = int(data.get(b"failed", data.get("failed", 0)))
                        last_update = float(data.get(b"last_update", data.get("last_update", 0)))
                        user_phone = (
                            data.get(b"user_phone", data.get("user_phone", b""))
                        )
                        if isinstance(user_phone, bytes):
                            user_phone = user_phone.decode("utf-8")

                        # Check if batch is ready for confirmation
                        elapsed = time.time() - last_update
                        if elapsed < IMAGE_BATCH_TIMEOUT_SECONDS:
                            continue  # Still waiting for more images

                        # Extract conversation_id from key
                        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                        conversation_id = key_str.replace(IMAGE_BATCH_KEY_PREFIX, "")

                        if count <= 0 and failed <= 0:
                            # No images at all, just clean up
                            await client.delete(key)
                            continue

                        logger.info(
                            f"Sending batch confirmation | "
                            f"conversation_id={conversation_id} | count={count} | failed={failed}",
                            extra={
                                "conversation_id": conversation_id,
                                "batch_count": count,
                                "batch_failed": failed,
                            },
                        )

                        # Get case_id: first try from batch hash, fallback to FSM state
                        case_id_raw = data.get(b"case_id", data.get("case_id", b""))
                        if isinstance(case_id_raw, bytes):
                            case_id_raw = case_id_raw.decode("utf-8")
                        case_id = case_id_raw or None

                        if not case_id:
                            # Fallback: get from FSM state
                            checkpointer = get_redis_checkpointer()
                            fsm_state = await get_fsm_state_from_checkpoint(
                                checkpointer, conversation_id
                            )
                            case_fsm = get_case_fsm_state(fsm_state) if fsm_state else {}
                            case_id = case_fsm.get("case_id")

                        # RECONCILIATION: Before confirming, check Chatwoot
                        # for any images whose webhooks were dropped
                        if case_id:
                            case_created_at = None
                            try:
                                async with get_async_session() as session:
                                    case_obj = await session.get(Case, uuid_mod.UUID(case_id))
                                    if case_obj and case_obj.created_at:
                                        case_created_at = case_obj.created_at.timestamp()
                            except Exception as e:
                                logger.warning(f"Could not get case created_at: {e}")

                            reconciled, recon_failed = await reconcile_conversation_images(
                                conversation_id=conversation_id,
                                case_id=case_id,
                                case_created_at=case_created_at,
                            )

                            if reconciled > 0:
                                count += reconciled
                            if recon_failed > 0:
                                failed += recon_failed

                            # Retry reconciliation if first pass recovered images
                            # (indicates Chatwoot is still processing, more may appear)
                            if reconciled > 0:
                                logger.info(
                                    f"Reconciliation recovered {reconciled} images, "
                                    f"retrying after 15s to catch remaining | "
                                    f"conversation_id={conversation_id}",
                                    extra={"conversation_id": conversation_id},
                                )
                                await asyncio.sleep(15)
                                retry_reconciled, retry_failed = await reconcile_conversation_images(
                                    conversation_id=conversation_id,
                                    case_id=case_id,
                                    case_created_at=case_created_at,
                                )
                                if retry_reconciled > 0:
                                    count += retry_reconciled
                                    logger.info(
                                        f"Reconciliation retry recovered {retry_reconciled} more | "
                                        f"conversation_id={conversation_id}",
                                        extra={"conversation_id": conversation_id},
                                    )
                                if retry_failed > 0:
                                    failed += retry_failed

                        # Get total images from DB (after reconciliation)
                        total_images = 0
                        if case_id:
                            total_images = await get_total_case_images(case_id)

                        # Build confirmation message
                        if failed > 0 and count == 0:
                            # All images failed
                            message = (
                                f"No se pudieron descargar {failed} imagen(es). "
                                f"Intenta enviarlas de nuevo.\n\n"
                                f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                            )
                        elif failed > 0:
                            if total_images > count:
                                message = (
                                    f"He recibido {count} imagen(es) nueva(s). "
                                    f"{failed} no se pudieron descargar, intenta enviarlas de nuevo.\n"
                                    f"Total en el expediente: {total_images}.\n\n"
                                    f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                                )
                            else:
                                message = (
                                    f"He recibido {count} imagen(es). "
                                    f"{failed} no se pudieron descargar, intenta enviarlas de nuevo.\n\n"
                                    f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                                )
                        elif total_images > count:
                            message = (
                                f"He recibido {count} imagen(es) nueva(s). "
                                f"Total en el expediente: {total_images}.\n\n"
                                f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                            )
                        else:
                            message = (
                                f"He recibido {count} imagen(es).\n\n"
                                f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                            )

                        # Send confirmation via Chatwoot
                        # Convert conversation_id to int if it's numeric
                        conv_id_for_chatwoot = None
                        try:
                            conv_id_for_chatwoot = int(conversation_id)
                        except (ValueError, TypeError):
                            pass

                        success = await chatwoot.send_message(
                            customer_phone=user_phone,
                            message=message,
                            conversation_id=conv_id_for_chatwoot,
                        )

                        if success:
                            logger.info(
                                f"Batch confirmation sent | conversation_id={conversation_id}",
                                extra={"conversation_id": conversation_id},
                            )
                        else:
                            logger.warning(
                                f"Failed to send batch confirmation | "
                                f"conversation_id={conversation_id}",
                                extra={"conversation_id": conversation_id},
                            )

                        # Store confirmed count for "listo" reconciliation (Fix 3)
                        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
                        try:
                            await client.hset(final_key, mapping={
                                "confirmed_count": str(count),
                                "total_images": str(total_images),
                                "case_id": case_id or "",
                                "conversation_id": conversation_id,
                            })
                            await client.expire(final_key, 7200)  # 2h TTL
                            logger.debug(
                                f"Stored batch final info | conversation_id={conversation_id} | "
                                f"confirmed_count={count} | total_images={total_images}",
                            )
                        except Exception as e:
                            logger.warning(f"Failed to store batch final info: {e}")

                        # Reset the batch counter
                        await client.delete(key)

                    except Exception as e:
                        logger.error(
                            f"Error processing batch key {key}: {e}",
                            exc_info=True,
                        )

                if cursor == 0:
                    break  # Scan complete

            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Image batch confirmation worker cancelled")
            raise

        except Exception as e:
            logger.error(
                f"Error in image batch confirmation worker: {e}",
                exc_info=True,
            )
            await asyncio.sleep(check_interval)

    logger.info("Image batch confirmation worker stopped")


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

    # Start all workers concurrently with supervisor
    workers = {
        "incoming": asyncio.create_task(subscribe_to_incoming_messages()),
        "outgoing": asyncio.create_task(subscribe_to_outgoing_messages()),
        "image_batch": asyncio.create_task(image_batch_confirmation_worker()),
    }

    async def supervisor():
        """Monitor workers and restart them if they die unexpectedly."""
        while not shutdown_event.is_set():
            for name, task in list(workers.items()):
                if task.done():
                    try:
                        # Check if it raised an exception
                        exc = task.exception()
                        if exc:
                            logger.error(
                                f"Worker '{name}' died with exception: {exc}. Restarting...",
                                exc_info=exc,
                            )
                        else:
                            logger.warning(f"Worker '{name}' exited unexpectedly. Restarting...")
                    except asyncio.CancelledError:
                        # Task was cancelled - don't restart
                        logger.info(f"Worker '{name}' was cancelled")
                        continue

                    # Restart the worker
                    if name == "incoming":
                        workers[name] = asyncio.create_task(subscribe_to_incoming_messages())
                    elif name == "outgoing":
                        workers[name] = asyncio.create_task(subscribe_to_outgoing_messages())
                    elif name == "image_batch":
                        workers[name] = asyncio.create_task(image_batch_confirmation_worker())
                    logger.info(f"Worker '{name}' restarted")

            await asyncio.sleep(5)  # Check every 5 seconds

    supervisor_task = asyncio.create_task(supervisor())

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Main loop cancelled")
    finally:
        logger.info("Shutting down agent service...")
        supervisor_task.cancel()
        for name, task in workers.items():
            task.cancel()
        try:
            await asyncio.gather(
                supervisor_task,
                *workers.values(),
                return_exceptions=True
            )
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
