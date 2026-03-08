"""
MSI Automotive - Image Handling Service (v2).

Ported from v1 and adapted to mode-based architecture.

Provides:
- save_images_silently: Download + validate + save images to DB
- reconcile_conversation_images: Recover images from dropped Chatwoot webhooks
- reconcile_on_completion: Final safety net when user says "listo"
- image_batch_confirmation_worker: Background task to confirm received images
- Redis batch tracking helpers (HSET pattern)
- Helper functions (is_image_attachment, is_completion_message, etc.)
"""

import asyncio
import json
import logging
import time
import uuid as uuid_mod
from typing import Any

from sqlalchemy import func, select

from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE
from api.services.chatwoot_image_service import get_chatwoot_image_service
from database.connection import get_async_session
from database.models import Case, CaseImage
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

IMAGE_BATCH_TIMEOUT_SECONDS = 15
IMAGE_BATCH_KEY_PREFIX = "image_batch:"
IMAGE_BATCH_FINAL_PREFIX = "image_batch_final:"
IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX = "image_assignment_snapshot:"
IMAGE_RECONCILE_INFLIGHT_PREFIX = "image_reconcile_inflight:"
IMAGE_RECONCILE_RECENT_PREFIX = "image_reconcile_recent:"
IMAGE_FINALIZE_LOCK_PREFIX = "finalize_lock:"


def _compute_finalize_lock_ttl() -> int:
    """Compute TTL for finalize_lock Redis key.

    Covers the full reconcile_on_completion window so the
    image_batch_confirmation_worker never sends a stale CTA while
    reconciliation is in progress.

    TTL = PHOTO_COMPLETION_WAIT_SECONDS + PHOTO_COMPLETION_RETRY_WAIT_SECONDS + 5 (buffer).
    """
    s = get_settings()
    return s.PHOTO_COMPLETION_WAIT_SECONDS + s.PHOTO_COMPLETION_RETRY_WAIT_SECONDS + 5


# Cached at import time for use as a constant; get_settings() is lru_cached
# so the call is effectively free after the first invocation.
FINALIZE_LOCK_TTL_SECONDS: int = _compute_finalize_lock_ttl()
# Completion phrases list is superseded by the canonical PHOTO_COMPLETION_INTENT_RE
# regex (imported from agent.utils.validation). Kept as empty list for any
# external callers that reference this name; no longer used internally.
COMPLETION_PHRASES: list[str] = []

# v2 sub-modes that expect images
IMAGE_COLLECTION_SUB_MODES = {
    "collect_element_data",
    "collect_base_docs",
}


# ──────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────

def is_image_attachment(attachment: dict) -> bool:
    """Check if an attachment is an image type."""
    return attachment.get("file_type", "") == "image"


# ──────────────────────────────────────────────────────────────────
# Attachment type classification (TASK-12: MIME-based accept/reject)
# ──────────────────────────────────────────────────────────────────

# Chatwoot file_type values that are always unacceptable for homologation.
# "image" and "file" (PDF/document) are accepted.
# "audio" and "video" are explicitly rejected.
# Unknown values fall through to fail-open (treated as accepted).
_REJECTED_FILE_TYPES: frozenset[str] = frozenset({"audio", "video"})


def is_accepted_attachment(attachment: dict) -> bool:
    """
    Return True if the attachment type is accepted for homologation.

    Accepted:
    - file_type == "image"  → JPEG / PNG / WEBP from WhatsApp
    - file_type == "file"   → PDFs (and other documents; we fail-open here
                               because we cannot distinguish PDF from DOC
                               without a content_type field)

    Rejected:
    - file_type == "audio"  → voice messages, audio files
    - file_type == "video"  → video clips

    Fail-open policy: any unrecognised file_type value is accepted so we
    never silently drop legitimate attachments due to a new Chatwoot type.
    """
    file_type = attachment.get("file_type", "")
    return file_type not in _REJECTED_FILE_TYPES


def is_rejected_attachment(attachment: dict) -> bool:
    """
    Return True if the attachment should be explicitly rejected with a user
    message.  Inverse of is_accepted_attachment, kept as a named helper so
    call-sites are readable.
    """
    return not is_accepted_attachment(attachment)


def is_completion_message(message_text: str | None) -> bool:
    """Check if message text indicates user wants to finish sending images.

    Uses the canonical PHOTO_COMPLETION_INTENT_RE regex from
    agent.utils.validation — same pattern as the expediente_mode guard —
    so both code paths agree on what counts as a completion signal.
    """
    if not message_text:
        return False
    return bool(PHOTO_COMPLETION_INTENT_RE.search(message_text))


def is_in_image_collection_mode(mode_context: dict | None) -> bool:
    """Check if the current mode context expects image uploads (v2 adaptation)."""
    if not mode_context:
        return False
    sub_mode = mode_context.get("expediente_sub_mode", "")
    return sub_mode in IMAGE_COLLECTION_SUB_MODES


def get_current_element_code(mode_context: dict | None) -> str | None:
    """
    Get the current element code from v2 mode_context.

    In COLLECT_ELEMENT_DATA sub-mode, the mode_context tracks which element
    we're currently collecting data for via element_codes + current_element_index.

    IMPORTANT: Returns None (i.e. treat as base doc) when element_phase == "data",
    even if sub-mode is still "collect_element_data".

    Rationale: confirmar_fotos_elemento() transitions element_phase to "data" but
    does NOT immediately flip expediente_sub_mode — that only happens when the LLM
    calls completar_elemento_actual(). Images received in the window between
    confirmar_fotos_elemento() and completar_elemento_actual() are base docs
    (or unrelated), so they must NOT inherit the element_code.
    """
    if not mode_context:
        return None

    sub_mode = mode_context.get("expediente_sub_mode", "")
    if sub_mode != "collect_element_data":
        return None  # Only element-specific images in this sub-mode

    # If photos have already been confirmed for this element (phase switched to "data"),
    # any new incoming images are NOT element photos — treat them as base docs.
    element_phase = mode_context.get("element_phase", "photos")
    if element_phase != "photos":
        return None

    element_codes = mode_context.get("element_codes", [])
    current_idx = mode_context.get("current_element_index", 0)

    if not element_codes or current_idx >= len(element_codes):
        return None
    return element_codes[current_idx]


async def get_case_image_count(case_id: str) -> int:
    """Get the count of existing images for a case."""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(CaseImage.id)).where(
                    CaseImage.case_id == uuid_mod.UUID(case_id)
                )
            )
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"Failed to get image count for case {case_id}: {e}")
        return 0


async def get_mode_context_from_checkpoint(
    checkpointer,
    conversation_id: str,
) -> dict | None:
    """
    Read mode_context from LangGraph checkpoint (v2 adaptation of v1's
    get_fsm_state_from_checkpoint).
    """
    try:
        config = {"configurable": {"thread_id": conversation_id}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)

        if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
            return None

        channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        return channel_values.get("mode_context")

    except Exception as e:
        logger.warning(
            f"Failed to get mode_context from checkpoint: {e}",
            extra={"conversation_id": conversation_id},
        )
        return None


async def get_case_id_from_mode_context(mode_context: dict | None) -> str | None:
    """Extract case_id from v2 mode_context."""
    if not mode_context:
        return None
    return mode_context.get("case_id")


# ──────────────────────────────────────────────────────────────────
# Redis batch tracking (HSET pattern from v1)
# ──────────────────────────────────────────────────────────────────

async def get_batch_info(redis_client, conversation_id: str) -> tuple[int, float]:
    """Get current batch info from Redis. Returns (count, last_update_timestamp)."""
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
    Update the batch counter in Redis (HSET pattern).

    Returns new total count.
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
        if case_id:
            mapping["case_id"] = case_id

        await redis_client.hset(key, mapping=mapping)
        await redis_client.expire(key, 3600)  # 1h auto-cleanup

        logger.debug(
            f"Batch counter updated: {current_count} -> {new_count} | "
            f"conversation_id={conversation_id}"
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
    except Exception as e:
        logger.warning(f"Failed to reset batch counter: {e}")


async def persist_assignment_snapshot(
    redis_client,
    conversation_id: str,
    assignment_snapshot: dict[str, Any] | None,
) -> None:
    """Persist compact assignment context for reuse across retries/reconciliation."""
    if not assignment_snapshot:
        return

    compact = {
        "case_id": assignment_snapshot.get("case_id"),
        "element_code": assignment_snapshot.get("element_code"),
        "in_image_collection_mode": bool(assignment_snapshot.get("in_image_collection_mode")),
        "expediente_sub_mode": assignment_snapshot.get("expediente_sub_mode"),
        "element_phase": assignment_snapshot.get("element_phase"),
    }
    key = f"{IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX}{conversation_id}"
    try:
        await redis_client.set(key, json.dumps(compact), ex=7200)
    except Exception as e:
        logger.warning(f"Failed to persist assignment snapshot: {e}")


async def get_assignment_snapshot(redis_client, conversation_id: str) -> dict[str, Any] | None:
    """Load persisted assignment context for this conversation."""
    key = f"{IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX}{conversation_id}"
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"Failed to load assignment snapshot: {e}")
        return None


# ──────────────────────────────────────────────────────────────────
# Core: save_images_silently
# ──────────────────────────────────────────────────────────────────

async def save_images_silently(
    case_id: str,
    conversation_id: str,
    attachments: list[dict],
    user_phone: str,
    chatwoot_message_id: int | None = None,
    element_code: str | None = None,
    assignment_context: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """
    Save images from attachments to disk and database without sending a response.

    Downloads images via ChatwootImageService (SSRF + security validation),
    stores them to disk, and creates CaseImage records in PostgreSQL.

    Args:
        case_id: UUID of the case to attach images to
        conversation_id: For logging
        attachments: List of attachment dicts from Chatwoot
        user_phone: User's phone number for logging
        chatwoot_message_id: Chatwoot message ID for reconciliation dedup
        element_code: Element code if in COLLECT_ELEMENT_DATA, None for base docs
        assignment_context: Explicit assignment snapshot for deterministic context

    Returns:
        Tuple of (saved_count, failed_count)
    """
    image_service = get_chatwoot_image_service()

    # Prefer explicit assignment context when available.
    # Keep base-doc images with element_code=None when not in element photo phase.
    if assignment_context:
        snap_case_id = assignment_context.get("case_id")
        if snap_case_id:
            case_id = snap_case_id

        if "in_image_collection_mode" in assignment_context and not assignment_context.get(
            "in_image_collection_mode",
        ):
            element_code = None
        elif "element_code" in assignment_context:
            element_code = assignment_context.get("element_code")

    saved_count = 0
    failed_count = 0

    # Filter to only image attachments
    image_attachments = [a for a in attachments if is_image_attachment(a)]
    if not image_attachments:
        return 0, 0

    # Get existing image count for incremental naming
    existing_count = await get_case_image_count(case_id)
    case_short_id = case_id[:8]

    logger.info(
        f"Saving {len(image_attachments)} images silently | "
        f"case_id={case_id} | conversation_id={conversation_id} | "
        f"existing_count={existing_count} | element_code={element_code}",
        extra={
            "conversation_id": conversation_id,
            "case_id": case_id,
            "image_count": len(image_attachments),
            "element_code": element_code,
        },
    )

    for attachment in image_attachments:
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
                element_code=element_code,
            )

            if not download_result:
                failed_count += 1
                logger.error(
                    f"Failed to download image | url={data_url} | case_id={case_id}",
                    extra={"conversation_id": conversation_id, "case_id": case_id},
                )
                continue

            # Save to database
            async with get_async_session() as session:
                case_image = CaseImage(
                    case_id=uuid_mod.UUID(case_id),
                    stored_filename=download_result["stored_filename"],
                    original_filename=download_result.get("original_filename"),
                    mime_type=download_result["mime_type"],
                    file_size=download_result.get("file_size"),
                    display_name=display_name,
                    description="Imagen enviada por usuario via WhatsApp",
                    element_code=element_code,
                    image_type="user_upload",
                    chatwoot_message_id=chatwoot_message_id,
                    is_valid=None,
                )
                session.add(case_image)
                await session.commit()

                # Observability: trace each persisted image insert
                logger.info(
                    "image_insert_persisted",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "stored_filename": download_result["stored_filename"],
                        "display_name": display_name,
                        "element_code": element_code,
                        "chatwoot_message_id": chatwoot_message_id,
                        "source": "save_images_silently",
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


# ──────────────────────────────────────────────────────────────────
# Reconciliation: recover dropped webhooks
# ──────────────────────────────────────────────────────────────────

async def reconcile_conversation_images(
    conversation_id: str,
    case_id: str,
    case_created_at: float | None = None,
    element_code: str | None = None,
) -> tuple[int, int]:
    """
    Reconcile images between Chatwoot and our database.

    Queries Chatwoot API for all image messages, compares with DB by
    chatwoot_message_id, and downloads any missing ones.

    Args:
        conversation_id: Chatwoot conversation ID
        case_id: Case UUID string
        case_created_at: Unix timestamp of case creation (for filtering)
        element_code: Current element code to propagate to reconciled images

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
        return 0, 0

    # Step 2: Get existing chatwoot_message_ids from DB
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
        # Observability: trace dedup skip when no new images found
        logger.info(
            "image_insert_dedup_skipped",
            extra={
                "conversation_id": conversation_id,
                "case_id": case_id,
                "total_chatwoot_msgs": len(messages) if messages else 0,
                "existing_db_count": len(existing_msg_ids),
                "source": "reconcile_conversation_images",
            },
        )
        return 0, 0

    logger.info(
        f"Reconciliation: found {len(missing_messages)} missing | "
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
                    element_code=element_code,
                )

                if not download_result:
                    failed += 1
                    continue

                async with get_async_session() as session:
                    case_image = CaseImage(
                        case_id=uuid_mod.UUID(case_id),
                        stored_filename=download_result["stored_filename"],
                        original_filename=data_url.split("/")[-1] if "/" in data_url else None,
                        mime_type=download_result["mime_type"],
                        file_size=download_result.get("file_size"),
                        display_name=display_name,
                        description="Imagen recuperada por reconciliación",
                        element_code=element_code,
                        image_type="user_upload",
                        chatwoot_message_id=msg_id,
                        is_valid=None,
                    )
                    session.add(case_image)
                    await session.commit()

                reconciled += 1
                # Observability: trace each reconciled image insert
                logger.info(
                    "image_insert_persisted",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "stored_filename": download_result["stored_filename"],
                        "display_name": display_name,
                        "element_code": element_code,
                        "chatwoot_message_id": msg_id,
                        "source": "reconcile_conversation_images",
                    },
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


async def reconcile_on_completion(
    redis_client,
    checkpointer,
    conversation_id: str,
    assignment_snapshot: dict[str, Any] | None = None,
) -> None:
    """
    Run final image reconciliation when user says 'listo'.

    Ensures all images are recovered from Chatwoot before the mode advances.
    Uses confirmed_count from batch confirmation to detect missing images.
    Two-pass reconciliation with increasing delays.
    """
    lock_key = f"{IMAGE_RECONCILE_INFLIGHT_PREFIX}{conversation_id}"
    recent_key = f"{IMAGE_RECONCILE_RECENT_PREFIX}{conversation_id}"
    has_lock = False

    try:
        # Idempotency guard: avoid duplicate reconciliation attempts for
        # repeated completion messages and concurrent retries.
        try:
            recent_marker = await redis_client.get(recent_key)
            if recent_marker:
                logger.info(
                    "completion_reconciliation_skipped_recent",
                    extra={"conversation_id": conversation_id},
                )
                return
            has_lock = bool(await redis_client.set(lock_key, "1", ex=120, nx=True))
            if not has_lock:
                logger.info(
                    "completion_reconciliation_skipped_inflight",
                    extra={"conversation_id": conversation_id},
                )
                return
        except Exception as e:
            logger.warning(f"Completion reconciliation dedupe guard unavailable: {e}")

        # Check if we're in an image collection mode and get case_id
        persisted_snapshot = None
        if assignment_snapshot is None:
            persisted_snapshot = await get_assignment_snapshot(redis_client, conversation_id)

        effective_snapshot = assignment_snapshot or persisted_snapshot

        # Observability: trace which snapshot source was used for reconciliation
        if effective_snapshot:
            snapshot_source = (
                "forwarded" if assignment_snapshot
                else "persisted_redis"
            )
            logger.info(
                "image_assignment_reused_for_reconcile",
                extra={
                    "conversation_id": conversation_id,
                    "snapshot_source": snapshot_source,
                    "case_id": effective_snapshot.get("case_id"),
                    "element_code": effective_snapshot.get("element_code"),
                    "in_image_collection_mode": effective_snapshot.get("in_image_collection_mode"),
                },
            )

        mode_context = None
        if effective_snapshot:
            mode_context = effective_snapshot.get("mode_context")
        if mode_context is None:
            mode_context = await get_mode_context_from_checkpoint(checkpointer, conversation_id)

        in_image_mode = None
        if effective_snapshot and "in_image_collection_mode" in effective_snapshot:
            in_image_mode = bool(effective_snapshot.get("in_image_collection_mode"))
        if in_image_mode is None:
            in_image_mode = is_in_image_collection_mode(mode_context)

        if not in_image_mode:
            return

        case_id = None
        if effective_snapshot:
            case_id = effective_snapshot.get("case_id")
        if not case_id:
            case_id = await get_case_id_from_mode_context(mode_context)
        if not case_id:
            return

        # Extract element_code so reconciled images inherit the context
        if effective_snapshot and "element_code" in effective_snapshot:
            element_code = effective_snapshot.get("element_code")
        else:
            element_code = get_current_element_code(mode_context)

        # Get case_created_at for filtering
        case_created_at = None
        try:
            async with get_async_session() as session:
                case_obj = await session.get(Case, uuid_mod.UUID(case_id))
                if case_obj and case_obj.created_at:
                    case_created_at = case_obj.created_at.timestamp()
        except Exception as e:
            logger.warning(f"Completion reconciliation: could not get case created_at: {e}")

        # Read confirmed count from batch confirmation
        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
        final_data = await redis_client.hgetall(final_key)
        confirmed_total = int(
            final_data.get("total_images", final_data.get(b"total_images", 0))
        )

        current_count = await get_case_image_count(case_id)

        logger.info(
            f"Completion reconciliation starting | conversation_id={conversation_id} | "
            f"current_db_count={current_count} | confirmed_total={confirmed_total}",
            extra={"conversation_id": conversation_id, "case_id": case_id},
        )

        # Brief delay to let Chatwoot finish processing
        await asyncio.sleep(5)

        # First reconciliation pass
        reconciled, failed = await reconcile_conversation_images(
            conversation_id=conversation_id,
            case_id=case_id,
            case_created_at=case_created_at,
            element_code=element_code,
        )

        if reconciled > 0:
            logger.info(
                f"Completion reconciliation pass 1: recovered {reconciled} images",
                extra={"conversation_id": conversation_id},
            )

        # Check if still missing images
        new_count = await get_case_image_count(case_id)
        if confirmed_total > 0 and new_count < confirmed_total:
            logger.info(
                f"Completion reconciliation: still missing images "
                f"(have {new_count}, confirmed {confirmed_total}), retrying after 10s",
                extra={"conversation_id": conversation_id},
            )
            await asyncio.sleep(10)

            # Second reconciliation pass
            retry_reconciled, _ = await reconcile_conversation_images(
                conversation_id=conversation_id,
                case_id=case_id,
                case_created_at=case_created_at,
                element_code=element_code,
            )
            if retry_reconciled > 0:
                logger.info(
                    f"Completion reconciliation pass 2: recovered {retry_reconciled} more",
                    extra={"conversation_id": conversation_id},
                )

        final_count = await get_case_image_count(case_id)
        logger.info(
            f"Completion reconciliation done | final_count={final_count} | "
            f"confirmed_total={confirmed_total}",
            extra={"conversation_id": conversation_id},
        )

        # Cleanup
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
    finally:
        try:
            if has_lock:
                await redis_client.delete(lock_key)
                await redis_client.set(recent_key, "1", ex=25)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# Background worker: image batch confirmation
# ──────────────────────────────────────────────────────────────────

async def image_batch_confirmation_worker(
    shutdown_event: asyncio.Event,
    checkpointer: Any = None,
) -> None:
    """
    Background worker that sends batch confirmation messages after timeout.

    Polls Redis every 3 seconds for idle image batches. When a batch has been
    idle for IMAGE_BATCH_TIMEOUT_SECONDS, it:
    1. Runs reconciliation to catch dropped webhooks
    2. Sends a confirmation message to the user via Chatwoot
    3. Stores confirmed count for reconcile_on_completion

    Args:
        shutdown_event: Event that signals shutdown
        checkpointer: LangGraph checkpointer for reading mode_context
    """
    chatwoot = ChatwootClient()
    check_interval = 3

    logger.info(
        f"Image batch confirmation worker started | "
        f"timeout={IMAGE_BATCH_TIMEOUT_SECONDS}s"
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
                        data = await client.hgetall(key)
                        if not data:
                            continue

                        # Handle both bytes and string keys
                        count = int(data.get(b"count", data.get("count", 0)))
                        failed = int(data.get(b"failed", data.get("failed", 0)))
                        last_update = float(data.get(b"last_update", data.get("last_update", 0)))
                        user_phone = data.get(b"user_phone", data.get("user_phone", b""))
                        if isinstance(user_phone, bytes):
                            user_phone = user_phone.decode("utf-8")

                        # Check if batch is ready for confirmation
                        elapsed = time.time() - last_update
                        if elapsed < IMAGE_BATCH_TIMEOUT_SECONDS:
                            continue

                        # Extract conversation_id from key
                        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                        conversation_id = key_str.replace(IMAGE_BATCH_KEY_PREFIX, "")

                        if count <= 0 and failed <= 0:
                            await client.delete(key)
                            continue

                        logger.info(
                            f"Sending batch confirmation | "
                            f"conversation_id={conversation_id} | count={count}",
                            extra={"conversation_id": conversation_id},
                        )

                        # Prefer persisted assignment snapshot context first,
                        # then batch hash/checkpoint as fallback.
                        assignment_snapshot = await get_assignment_snapshot(client, conversation_id)
                        element_code = None
                        if assignment_snapshot and assignment_snapshot.get("in_image_collection_mode"):
                            element_code = assignment_snapshot.get("element_code")

                        # Get case_id from snapshot, batch hash, or mode_context
                        case_id = assignment_snapshot.get("case_id") if assignment_snapshot else None
                        case_id_raw = data.get(b"case_id", data.get("case_id", b""))
                        if isinstance(case_id_raw, bytes):
                            case_id_raw = case_id_raw.decode("utf-8")
                        if not case_id:
                            case_id = case_id_raw or None

                        if not case_id and checkpointer:
                            mode_context = await get_mode_context_from_checkpoint(
                                checkpointer, conversation_id,
                            )
                            case_id = await get_case_id_from_mode_context(mode_context)

                        # RECONCILIATION before confirming
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
                                element_code=element_code,
                            )

                            if reconciled > 0:
                                count += reconciled
                            if recon_failed > 0:
                                failed += recon_failed

                            # Retry if first pass recovered images (more may appear)
                            if reconciled > 0:
                                logger.info(
                                    f"Reconciliation recovered {reconciled}, "
                                    f"retrying after 15s",
                                    extra={"conversation_id": conversation_id},
                                )
                                await asyncio.sleep(15)
                                retry_reconciled, retry_failed = await reconcile_conversation_images(
                                    conversation_id=conversation_id,
                                    case_id=case_id,
                                    case_created_at=case_created_at,
                                    element_code=element_code,
                                )
                                if retry_reconciled > 0:
                                    count += retry_reconciled
                                if retry_failed > 0:
                                    failed += retry_failed

                        # Get total images from DB after reconciliation
                        total_images = 0
                        if case_id:
                            total_images = await get_case_image_count(case_id)

                        # Check finalize lock: if the main loop already detected "listo"
                        # (set finalize_lock:{conversation_id}), suppress the CTA message
                        # to avoid contradicting the user who already wrote "listo".
                        # Reconciliation above has already run — we only skip the send.
                        finalize_lock_key = f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
                        finalize_locked = False
                        try:
                            finalize_locked = bool(await client.exists(finalize_lock_key))
                        except Exception as lock_err:
                            logger.warning(
                                f"Could not check finalize lock for conversation "
                                f"{conversation_id}: {lock_err}",
                                extra={"conversation_id": conversation_id},
                            )

                        if finalize_locked:
                            logger.info(
                                f"Skipping batch CTA message (finalize lock active) | "
                                f"conversation_id={conversation_id}",
                                extra={"conversation_id": conversation_id},
                            )
                        else:
                            # Build confirmation message
                            if failed > 0 and count == 0:
                                message = (
                                    f"No se pudieron descargar {failed} imagen(es). "
                                    f"Intenta enviarlas de nuevo.\n\n"
                                    f"Cuando hayas enviado todas las fotos, escribe 'listo'."
                                )
                            elif failed > 0:
                                message = (
                                    f"He recibido {count} imagen(es). "
                                    f"{failed} no se pudieron descargar.\n"
                                    f"Total en el expediente: {total_images}.\n\n"
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
                            conv_id_for_chatwoot = None
                            try:
                                conv_id_for_chatwoot = int(conversation_id)
                            except (ValueError, TypeError):
                                pass

                            await chatwoot.send_message(
                                customer_phone=user_phone,
                                message=message,
                                conversation_id=conv_id_for_chatwoot,
                            )

                        # Store confirmed count for reconcile_on_completion
                        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
                        try:
                            await client.hset(final_key, mapping={
                                "confirmed_count": str(count),
                                "total_images": str(total_images),
                                "case_id": case_id or "",
                                "conversation_id": conversation_id,
                            })
                            await client.expire(final_key, 7200)  # 2h TTL
                        except Exception as e:
                            logger.warning(f"Failed to store batch final info: {e}")

                        # Reset batch counter
                        await client.delete(key)

                    except Exception as e:
                        logger.error(
                            f"Error processing batch key {key}: {e}",
                            exc_info=True,
                        )

                if cursor == 0:
                    break

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
