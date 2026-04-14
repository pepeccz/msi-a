"""
MSI Automotive - LangGraph Agent Service Entry Point.

Background worker for conversation orchestration using mode-based architecture.
Subscribes to Redis for incoming messages and sends responses via Chatwoot.
"""

import asyncio
import hashlib
import json
import logging
import signal
import time
import uuid as uuid_mod
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select

from agent.graph.conversation_graph import create_compiled_graph, _RECURSION_LIMIT
from agent.graph.user_profile_store import create_user_store
from agent.state.checkpointer import (
    get_redis_checkpointer,
    get_initialized_checkpointer,
    initialize_redis_indexes,
)
from agent.state.mutation_config import build_state_mutation_config
from agent.services.case_helpers import update_case_last_activity
from agent.services.case_lifecycle_worker import case_lifecycle_worker
from agent.services.image_handling import (
    is_completion_message,
    is_in_image_collection_mode,
    get_current_element_code,
    get_current_element_code_async,
    get_mode_context_from_checkpoint,
    get_case_id_from_mode_context,
    persist_assignment_snapshot,
    assign_upload_batch,
    get_assignment_snapshot,
    save_images_silently,
    update_batch_counter,
    reset_batch_counter,
    reset_all_batch_counters,
    reconcile_on_completion,
    image_batch_confirmation_worker,
    is_image_attachment,
    is_accepted_attachment,
    is_rejected_attachment,
    IMAGE_FINALIZE_LOCK_PREFIX,
    FINALIZE_LOCK_TTL_SECONDS,
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
from shared.redis_keys import RedisKeys, RedisKeyTTL

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

# Image delivery retry constants
IMAGE_DELIVERY_MAX_RETRIES = 2  # Max retry rounds for failed image subset
IMAGE_DELIVERY_RETRY_DELAY = 3.0  # Seconds between retry rounds

# Per-conversation locks
_conversation_locks: dict[str, asyncio.Lock] = {}


def get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific conversation."""
    if conversation_id not in _conversation_locks:
        _conversation_locks[conversation_id] = asyncio.Lock()
    return _conversation_locks[conversation_id]


def _resolve_image_delivery_contract(
    pending_images: dict[str, object] | None,
    conversation_id: str,
) -> dict[str, object]:
    """Return a normalized delivery contract for observability."""
    contract = pending_images.get("delivery_contract", {}) if pending_images else {}
    if not isinstance(contract, dict):
        contract = {}

    return {
        "delivery_contract_version": contract.get("version", "v1"),
        "delivery_request_id": contract.get("delivery_request_id")
        or uuid_mod.uuid4().hex,
        "delivery_scope": contract.get("delivery_scope", "presupuesto"),
        "delivery_source_tool": contract.get(
            "delivery_source_tool", "enviar_imagenes_ejemplo"
        ),
        "delivery_intent_created_at": contract.get("delivery_intent_created_at"),
        "delivery_conversation_id": contract.get("delivery_conversation_id")
        or str(conversation_id),
        "delivery_requested_count": int(
            contract.get("delivery_requested_count", 0) or 0
        ),
        "delivery_has_follow_up": bool(contract.get("delivery_has_follow_up", False)),
        "delivery_category": contract.get("delivery_category"),
        "delivery_element_code": contract.get("delivery_element_code"),
    }


def _classify_image_delivery_outcome(attempted_count: int, sent_count: int) -> str:
    """Classify delivery outcome after a transport attempt."""
    if attempted_count <= 0:
        return "failure"
    if sent_count == attempted_count:
        return "full_success"
    if sent_count > 0:
        return "partial_success"
    return "failure"


def _build_image_delivery_outcome_state(
    *,
    delivery_contract: dict[str, object],
    attempted_count: int,
    sent_count: int,
    transport_error: str | None,
) -> dict[str, object]:
    """Build explicit outcome state payload persisted in mode_context."""
    failed_count = max(attempted_count - sent_count, 0)
    outcome = _classify_image_delivery_outcome(attempted_count, sent_count)
    requested_raw = delivery_contract.get("delivery_requested_count", attempted_count)
    if isinstance(requested_raw, (int, float, str)):
        try:
            requested_count = int(requested_raw)
        except (TypeError, ValueError):
            requested_count = attempted_count
    else:
        requested_count = attempted_count

    return {
        "status": outcome,
        "request_id": delivery_contract.get("delivery_request_id"),
        "scope": delivery_contract.get("delivery_scope"),
        "requested_count": requested_count,
        "attempted_count": attempted_count,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "transport_error": transport_error,
        "updated_at": datetime.now(UTC).isoformat(),
    }


_EXPEDIENTE_DELIVERY_SCOPES: frozenset[str] = frozenset(
    {
        "documentacion_base",
        "expediente",
        "collect_element_data",
        "collect_base_docs",
    }
)
"""Delivery scopes that originate from EXPEDIENTE_MODE sub-modes.

These scopes require additional outcome persistence so that the certainty
guardrail system (CertaintyEnvelope) can observe the real transport result
on subsequent turns.
"""


async def _persist_image_delivery_outcome(
    *,
    graph,
    config: dict[str, Any],
    delivery_contract: dict[str, object],
    attempted_count: int,
    sent_count: int,
    transport_error: str | None,
) -> None:
    """Persist transport-level image delivery outcome to mode_context.

    Task 2.4 extension:
    - ``presupuesto`` scope: original behaviour (unchanged).
    - expediente scopes: additionally persist ``image_delivery_result`` so
      the certainty envelope system can read the real outcome on the next turn.
    """
    scope = str(delivery_contract.get("delivery_scope", ""))

    outcome_state = _build_image_delivery_outcome_state(
        delivery_contract=delivery_contract,
        attempted_count=attempted_count,
        sent_count=sent_count,
        transport_error=transport_error,
    )

    if scope == "presupuesto":
        # Original behaviour — unchanged
        await graph.aupdate_state(
            build_state_mutation_config(config),
            {
                "mode_context": {
                    "imagenes_enviadas": sent_count > 0,
                    "imagenes_envio_intent_creado": False,
                    "imagenes_delivery_request_id": outcome_state.get("request_id"),
                    "imagenes_delivery_outcome": outcome_state,
                }
            },
        )
        return

    if scope in _EXPEDIENTE_DELIVERY_SCOPES:
        # Expediente-scoped delivery: persist real outcome so guardrails can gate
        # "images sent" claims on the next turn.
        await graph.aupdate_state(
            build_state_mutation_config(config),
            {
                "mode_context": {
                    # Canonical outcome field read by CertaintyEnvelope normaliser
                    "image_delivery_result": outcome_state,
                    # Legacy flag kept for backward-compat (other code reads this)
                    "imagenes_enviadas": sent_count > 0,
                    "imagenes_delivery_request_id": outcome_state.get("request_id"),
                    "imagenes_delivery_outcome": outcome_state,
                }
            },
        )
        return

    # Unknown scope — no persistence needed
    logger.debug(
        "image_delivery_outcome_scope_not_persisted",
        extra={
            "delivery_scope": scope,
            "delivery_outcome": outcome_state.get("status"),
        },
    )


def _image_url_hash(url: str) -> str:
    """Compute a short deterministic hash for image-level dedup."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


async def _check_request_idempotency(
    redis_client,
    conversation_id: str,
    request_id: str,
) -> bool:
    """Check if a delivery request has already been processed.

    Returns True if the request is a duplicate (already sent).
    """
    key = RedisKeys.image_delivery_request(conversation_id, request_id)
    existing = await redis_client.get(key)
    return existing is not None


async def _mark_request_processed(
    redis_client,
    conversation_id: str,
    request_id: str,
) -> None:
    """Mark a delivery request as processed with TTL."""
    key = RedisKeys.image_delivery_request(conversation_id, request_id)
    await redis_client.set(key, "1", ex=RedisKeyTTL.IMAGE_DELIVERY_REQUEST)


async def _check_image_already_sent(
    redis_client,
    conversation_id: str,
    delivery_request_id: str,
    image_url: str,
) -> bool:
    """Check if a specific image has already been sent within this delivery request."""
    image_hash = _image_url_hash(image_url)
    key = RedisKeys.image_delivery_image(
        conversation_id, delivery_request_id, image_hash
    )
    existing = await redis_client.get(key)
    return existing is not None


async def _mark_image_sent(
    redis_client,
    conversation_id: str,
    delivery_request_id: str,
    image_url: str,
) -> None:
    """Mark an individual image as sent within this delivery request (TTL = 30s)."""
    image_hash = _image_url_hash(image_url)
    key = RedisKeys.image_delivery_image(
        conversation_id, delivery_request_id, image_hash
    )
    await redis_client.set(key, "1", ex=RedisKeyTTL.IMAGE_DELIVERY_IMAGE)


async def _store_delivery_outcome_audit(
    redis_client,
    conversation_id: str,
    request_id: str,
    outcome_data: dict[str, Any],
) -> None:
    """Store the delivery outcome as JSON for auditing/debugging."""
    key = RedisKeys.image_delivery_outcome(conversation_id, request_id)
    await redis_client.set(
        key,
        json.dumps(outcome_data, default=str),
        ex=RedisKeyTTL.IMAGE_DELIVERY_OUTCOME,
    )


def build_image_delivery_fallback_message(
    outcome: str,
    *,
    sent_count: int = 0,
    failed_count: int = 0,
    total_requested: int = 0,
) -> str | None:
    """Build a user-facing fallback message in Spanish based on delivery outcome.

    Returns:
        A Spanish message string for ``partial_success`` and ``failure`` outcomes.
        ``None`` for ``full_success`` (no special message needed).
    """
    if outcome == "full_success":
        return None

    if outcome == "partial_success":
        # Inform the user that some images could not be sent
        return (
            f"He podido enviarte {sent_count} de {total_requested} "
            f"imagen{'es' if total_requested != 1 else ''} de ejemplo. "
            f"{'Las' if failed_count > 1 else 'La'} "
            f"{'restantes no se han' if failed_count > 1 else 'restante no se ha'} "
            f"podido enviar en este momento. "
            "Si necesitas verlas, dímelo y lo intento de nuevo."
        )

    # outcome == "failure"
    return (
        "No he podido enviarte las imágenes de ejemplo en este momento. "
        "Si necesitas verlas, dímelo y lo intento de nuevo, "
        "o puedo explicarte la documentación necesaria por texto."
    )


async def _send_images_with_idempotency_and_retry(
    *,
    chatwoot: ChatwootClient,
    redis_client,
    chatwoot_conv_id: int,
    conversation_id: str,
    image_urls: list[str],
    image_captions: list[str | None],
    delivery_contract: dict[str, object],
) -> tuple[int, str | None]:
    """Send images with per-image idempotency dedup and bounded retry.

    Returns:
        (sent_count, transport_error) — total successfully sent, last error or None.
    """
    request_id = str(delivery_contract.get("delivery_request_id", ""))

    # Request-level idempotency check
    if request_id:
        is_duplicate = await _check_request_idempotency(
            redis_client,
            conversation_id,
            request_id,
        )
        if is_duplicate:
            logger.info(
                "image_delivery_request_dedup_skip",
                extra={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "reason": "request_already_processed",
                },
            )
            return (len(image_urls), None)  # Treat as already sent

    total = len(image_urls)
    sent_set: set[int] = set()  # indexes ACTUALLY sent via Chatwoot this request
    dedup_set: set[int] = set()  # indexes skipped because already sent previously
    last_error: str | None = None

    for attempt in range(1 + IMAGE_DELIVERY_MAX_RETRIES):
        # Build the subset of images to send this round (exclude both sent and dedup-skipped)
        pending_indexes = [
            i for i in range(total) if i not in sent_set and i not in dedup_set
        ]
        if not pending_indexes:
            break  # All done

        if attempt > 0:
            logger.info(
                "image_delivery_retry_round",
                extra={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "retry_attempt": attempt,
                    "pending_count": len(pending_indexes),
                },
            )
            await asyncio.sleep(IMAGE_DELIVERY_RETRY_DELAY)

        for idx in pending_indexes:
            url = image_urls[idx]

            # Per-image idempotency check (scoped to this delivery_request_id)
            already_sent = await _check_image_already_sent(
                redis_client,
                conversation_id,
                request_id,
                url,
            )
            if already_sent:
                logger.info(
                    "image_delivery_image_dedup_skip",
                    extra={
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                        "image_index": idx,
                        "image_url_hash": _image_url_hash(url),
                    },
                )
                dedup_set.add(idx)
                continue

            # Determine caption for this image
            caption = image_captions[idx] if idx < len(image_captions) else None

            try:
                success = await chatwoot.send_image(
                    conversation_id=chatwoot_conv_id,
                    image_url=url,
                    caption=caption,
                )
                if success:
                    sent_set.add(idx)
                    await _mark_image_sent(
                        redis_client, conversation_id, request_id, url
                    )
                    logger.info(
                        "image_delivery_image_sent",
                        extra={
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "image_index": idx,
                            "attempt": attempt,
                        },
                    )
                else:
                    last_error = f"send_image returned False for index {idx}"
                    logger.warning(
                        "image_delivery_image_failed",
                        extra={
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "image_index": idx,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "image_delivery_image_exception",
                    extra={
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                        "image_index": idx,
                        "attempt": attempt,
                        "error": last_error,
                    },
                    exc_info=True,
                )

            # Delay between images within a batch (matching existing pattern)
            if total > 1 and idx < pending_indexes[-1]:
                delay = getattr(chatwoot, "image_send_delay_seconds", 1.5)
                logger.info(
                    "inter_image_delay",
                    extra={
                        "conversation_id": conversation_id,
                        "delay_seconds": delay,
                        "image_index": idx,
                        "total_images": total,
                    },
                )
                if delay > 0:
                    await asyncio.sleep(delay)

        # If all images accounted for (sent or dedup-skipped), no need for another retry round
        if len(sent_set) + len(dedup_set) >= total:
            break

    sent_count = len(sent_set)

    # Log dedup summary for observability
    if dedup_set:
        logger.info(
            "image_delivery_dedup_summary",
            extra={
                "conversation_id": conversation_id,
                "request_id": request_id,
                "dedup_skipped_count": len(dedup_set),
                "actually_sent_count": sent_count,
                "total_requested": total,
            },
        )

    # Mark request as processed and store audit outcome
    if request_id:
        await _mark_request_processed(redis_client, conversation_id, request_id)
        await _store_delivery_outcome_audit(
            redis_client,
            conversation_id,
            request_id,
            {
                "outcome": _classify_image_delivery_outcome(total, sent_count),
                "attempted": total,
                "sent": sent_count,
                "dedup_skipped": len(dedup_set),
                "failed": total - sent_count - len(dedup_set),
                "retries_used": min(
                    IMAGE_DELIVERY_MAX_RETRIES,
                    max(0, IMAGE_DELIVERY_MAX_RETRIES if sent_count < total else 0),
                ),
                "last_error": last_error,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )

    return (sent_count, last_error)


async def _safe_reconcile(
    redis_client,
    checkpointer,
    conversation_id: str,
    assignment_snapshot: dict | None = None,
) -> None:
    """Run reconciliation in background without blocking the response.

    This is a fire-and-forget wrapper around reconcile_on_completion() so
    the 5-15s sleep inside reconciliation doesn't delay the agent response.
    """
    try:
        await reconcile_on_completion(
            redis_client,
            checkpointer,
            conversation_id,
            assignment_snapshot=assignment_snapshot,
        )
    except Exception as e:
        logger.error(
            "background_reconciliation_failed",
            extra={
                "conversation_id": conversation_id,
                "error": str(e),
            },
            exc_info=True,
        )


async def _build_image_assignment_snapshot(
    *,
    checkpointer,
    conversation_id: str,
    customer_phone: str,
) -> dict:
    """Build a single assignment snapshot for this ingest event.

    The snapshot is captured once and reused by both the immediate save path
    and the deferred reconciliation path to avoid attribution drift.
    """
    mode_context = await get_mode_context_from_checkpoint(checkpointer, conversation_id)
    in_image_collection_mode = is_in_image_collection_mode(mode_context)
    case_id = await get_case_id_from_mode_context(mode_context)
    if not case_id:
        case_id = await get_case_id_for_conversation(conversation_id, customer_phone)

    # T-21: Use async version that checks Redis marker for deterministic attribution.
    # Falls back to the sync heuristic when no marker is present.
    element_code = (
        await get_current_element_code_async(mode_context, conversation_id)
        if in_image_collection_mode
        else None
    )

    # Resolve element display name for enriched CTA messages in the worker.
    # Read from element_display_names dict in mode_context (populated by expediente flow).
    element_display_name: str | None = None
    if element_code and mode_context:
        display_names: dict = (mode_context or {}).get("element_display_names") or {}
        element_display_name = display_names.get(element_code)

    return {
        "mode_context": mode_context,
        "expediente_sub_mode": (mode_context or {}).get("expediente_sub_mode"),
        "element_phase": (mode_context or {}).get("element_phase"),
        "in_image_collection_mode": in_image_collection_mode,
        "case_id": case_id,
        "element_code": element_code,
        "element_display_name": element_display_name,
    }


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
                raise RuntimeError(
                    f"Failed to initialize Redis after {max_retries} attempts"
                ) from e


async def get_case_id_for_conversation(
    conversation_id: str, customer_phone: str
) -> str | None:
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
    # Pre-initialize so the except block always has a bound value even if
    # an exception is raised before the proper assignment below.
    customer_phone: str = ""
    async with lock:
        try:
            # Extract message content (API sends "message_text", not "content")
            user_message = message_data.get("message_text", "") or message_data.get(
                "content", ""
            )
            message_type = message_data.get("message_type", "incoming")
            attachments = message_data.get("attachments", [])

            # Extract customer phone from message
            customer_phone = message_data.get("customer_phone", "")
            if not customer_phone:
                logger.error(
                    f"Missing customer_phone in message for conversation {conversation_id}"
                )
                return

            # ── Escalation guard (must run first, before any attachment processing) ─
            # If the conversation is already escalated to a human agent, silently
            # discard the message — the bot must not interfere at all.
            # We check the checkpoint here (early) so that FIX-2/FIX-3 (image/PDF
            # acknowledgments) are also suppressed for escalated conversations.
            _escalation_config = {
                "configurable": {
                    "thread_id": conversation_id,
                    "checkpoint_ns": "conversation",
                }
            }
            try:
                _early_state = await graph.aget_state(_escalation_config)
                if (
                    _early_state
                    and _early_state.values
                    and _early_state.values.get("current_mode") == "ESCALATION"
                ):
                    logger.info(
                        "graph_invocation_skipped_escalated",
                        extra={"conversation_id": conversation_id},
                    )
                    return
            except Exception as _early_state_err:
                # First message (no checkpoint) or transient error — safe to proceed.
                logger.debug(
                    "escalation_check_skipped",
                    extra={
                        "conversation_id": conversation_id,
                        "error": str(_early_state_err),
                    },
                )

            # ── Attachment type validation (TASK-12: MIME-based accept/reject) ────
            # Accept: images (JPEG/PNG/WEBP via file_type="image") and documents
            # (PDF/other via file_type="file" — fail-open, can't distinguish without
            # content_type). Reject: audio and video with a clear user message.
            # Send ONE rejection message even if multiple invalid attachments arrive.
            if attachments:
                rejected_attachments = [
                    a for a in attachments if is_rejected_attachment(a)
                ]
                if rejected_attachments:
                    rejected_types = [
                        a.get("file_type", "unknown") for a in rejected_attachments
                    ]
                    logger.info(
                        "attachment_type_rejected",
                        extra={
                            "conversation_id": conversation_id,
                            "rejected_count": len(rejected_attachments),
                            "rejected_types": rejected_types,
                            "total_attachments": len(attachments),
                        },
                    )
                    # Send rejection message — non-fatal, fire-and-forget
                    try:
                        conv_id_for_rejection: int | None = None
                        try:
                            conv_id_for_rejection = int(conversation_id)
                        except (ValueError, TypeError):
                            pass
                        rejection_message = (
                            "Solo puedo aceptar imágenes (JPEG, PNG o WEBP) o documentos PDF. "
                            "Por favor, envía las fotos como imagen de WhatsApp (no como documento adjunto) "
                            "y los documentos adicionales como PDF."
                        )
                        await chatwoot.send_message(
                            customer_phone=customer_phone,
                            message=rejection_message,
                            conversation_id=conv_id_for_rejection,
                        )
                        logger.info(
                            "attachment_rejection_message_sent",
                            extra={
                                "conversation_id": conversation_id,
                                "rejected_types": rejected_types,
                            },
                        )
                    except Exception as rejection_err:
                        # Non-fatal: log and continue processing
                        logger.warning(
                            "attachment_rejection_message_failed",
                            extra={
                                "conversation_id": conversation_id,
                                "error": str(rejection_err),
                            },
                        )
                    # If ALL attachments are rejected and there is no text, skip processing
                    accepted_attachments = [
                        a for a in attachments if is_accepted_attachment(a)
                    ]
                    if not accepted_attachments and not user_message.strip():
                        logger.info(
                            "attachment_only_message_skipped_all_rejected",
                            extra={"conversation_id": conversation_id},
                        )
                        return
                    # Replace attachments with only the accepted ones for downstream processing
                    attachments = [a for a in attachments if is_accepted_attachment(a)]

            # Handle image attachments
            image_attachments = (
                [a for a in attachments if is_image_attachment(a)]
                if attachments
                else []
            )
            checkpointer = None
            assignment_snapshot = None
            if image_attachments or (
                user_message and is_completion_message(user_message)
            ):
                checkpointer = (
                    get_initialized_checkpointer() or get_redis_checkpointer()
                )
                # Cache-first: reuse persisted snapshot to keep all images in the same batch
                cached_snapshot = await get_assignment_snapshot(redis_client, conversation_id)
                if cached_snapshot and cached_snapshot.get("upload_scope_key"):
                    assignment_snapshot = cached_snapshot
                    logger.info("image_assignment_snapshot_reused", conversation_id=conversation_id)
                else:
                    assignment_snapshot = await _build_image_assignment_snapshot(
                        checkpointer=checkpointer,
                        conversation_id=conversation_id,
                        customer_phone=customer_phone,
                    )
                message_created_at = message_data.get("chatwoot_message_created_at")
                assignment_snapshot = await assign_upload_batch(
                    redis_client,
                    conversation_id,
                    assignment_snapshot,
                    allow_create=bool(image_attachments),
                    message_created_at=message_created_at,
                )
                assignment_snapshot = assignment_snapshot or {}
                # Observability: trace ingest-time assignment resolution
                logger.info(
                    "image_assignment_resolved",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": assignment_snapshot.get("case_id"),
                        "element_code": assignment_snapshot.get("element_code"),
                        "in_image_collection_mode": assignment_snapshot.get(
                            "in_image_collection_mode"
                        ),
                        "expediente_sub_mode": assignment_snapshot.get(
                            "expediente_sub_mode"
                        ),
                        "upload_batch_id": assignment_snapshot.get("upload_batch_id"),
                        "resolved_element_code": assignment_snapshot.get(
                            "resolved_element_code"
                        ),
                        "resolved_batch_is_historical": assignment_snapshot.get(
                            "resolved_batch_is_historical"
                        ),
                        "has_images": bool(image_attachments),
                        "is_completion": bool(
                            user_message and is_completion_message(user_message)
                        ),
                    },
                )
                if not assignment_snapshot.get("resolved_batch_is_historical"):
                    await persist_assignment_snapshot(
                        redis_client,
                        conversation_id,
                        assignment_snapshot,
                    )

            if image_attachments:
                case_id = (
                    assignment_snapshot.get("case_id") if assignment_snapshot else None
                )
                in_image_mode = bool(
                    assignment_snapshot
                    and assignment_snapshot.get("in_image_collection_mode")
                )

                if case_id and in_image_mode:
                    # In image collection mode — save silently with full validation
                    chatwoot_msg_id_for_image = message_data.get("chatwoot_message_id")
                    try:
                        img_msg_id = (
                            int(chatwoot_msg_id_for_image)
                            if chatwoot_msg_id_for_image
                            else None
                        )
                    except (ValueError, TypeError):
                        img_msg_id = None

                    saved, failed = await save_images_silently(
                        case_id=case_id,
                        conversation_id=conversation_id,
                        attachments=image_attachments,
                        user_phone=customer_phone,
                        chatwoot_message_id=img_msg_id,
                        assignment_context=assignment_snapshot,
                    )

                    # Update batch counter for confirmation worker
                    if not assignment_snapshot.get("resolved_batch_is_historical"):
                        await update_batch_counter(
                            redis_client,
                            conversation_id,
                            additional_count=saved,
                            user_phone=customer_phone,
                            failed_count=failed,
                            case_id=case_id,
                            upload_batch_id=assignment_snapshot.get("upload_batch_id"),
                            upload_scope_key=assignment_snapshot.get(
                                "upload_scope_key"
                            ),
                        )

                    logger.info(
                        f"Images saved silently | saved={saved} | failed={failed} | "
                        f"conversation_id={conversation_id}",
                    )

                    # Check if this is also a completion message ("listo" + images)
                    if user_message.strip() and is_completion_message(user_message):
                        await reset_all_batch_counters(redis_client, conversation_id)
                        # Fall through to graph processing with the text
                    elif not user_message.strip():
                        # Image-only message — don't invoke graph
                        return
                else:
                    # Not in image collection mode — images won't be processed by graph
                    logger.info(
                        "images_received_outside_collection_mode",
                        extra={
                            "conversation_id": conversation_id,
                            "image_count": len(image_attachments),
                            "has_text": bool(user_message.strip()),
                        },
                    )
                    # FIX-2: If image-only (no text), send brief feedback and return
                    if not user_message.strip():
                        try:
                            _img_conv_id = int(conversation_id)
                        except (ValueError, TypeError):
                            _img_conv_id = None
                        await chatwoot.send_message(
                            customer_phone=customer_phone,
                            message=(
                                "Recibí tu(s) foto(s). Cuando iniciemos el proceso de "
                                "documentación del expediente, te las pediré en cada paso. "
                                "Si tienes alguna pregunta, escríbeme."
                            ),
                            conversation_id=_img_conv_id,
                        )
                        return
                    # If there's also text, fall through to graph invocation

            # ── FIX-3: PDF/document acknowledgment ─────────────────────
            # PDFs pass is_accepted_attachment (file_type="file") but are NOT images.
            # Acknowledge once so the user isn't left wondering.
            # assignment_snapshot is now populated (or None if no images/completion).
            # PDF-only message → assignment_snapshot is None → guard passes → ack sent.
            # PDF + images in collection mode → assignment_snapshot set → guard blocks ack.
            _file_attachments = [
                a for a in (attachments or []) if a.get("file_type") == "file"
            ]
            if _file_attachments and not (
                assignment_snapshot
                and assignment_snapshot.get("in_image_collection_mode")
            ):
                try:
                    _pdf_conv_id = int(conversation_id)
                except (ValueError, TypeError):
                    _pdf_conv_id = None
                try:
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=(
                            "Recibí tu documento. Cuando necesite documentación de "
                            "tu parte, te indicaré exactamente qué adjuntar y en qué formato."
                        ),
                        conversation_id=_pdf_conv_id,
                    )
                except Exception as _pdf_ack_err:
                    logger.warning(
                        "pdf_acknowledgment_send_failed",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(_pdf_ack_err),
                        },
                    )
                # Do NOT return — fall through to graph (text may accompany the PDF)

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
                user_name = (
                    f"{user.first_name or ''} {user.last_name or ''}".strip()
                    or "Usuario"
                )
                client_type = user.client_type or "particular"

            # ── Lifecycle: track last user activity ──────────────────
            # Updates last_activity_at + clears reminder_sent_at for the user's
            # active expediente case (if any). Runs in background to avoid
            # blocking message processing — the DB UPDATE is a no-op when no
            # active case exists (WHERE status IN ACTIVE_STATUSES).
            asyncio.create_task(update_case_last_activity(user_id))

            # ── Persist user message (fire-and-forget) ──────────────
            chatwoot_msg_id = message_data.get("chatwoot_message_id")
            try:
                chatwoot_msg_id_int = int(chatwoot_msg_id) if chatwoot_msg_id else None
            except (ValueError, TypeError):
                chatwoot_msg_id_int = None

            has_images = bool(attachments)
            image_count = (
                len([a for a in attachments if a.get("data_url")]) if attachments else 0
            )

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
                await reset_all_batch_counters(redis_client, conversation_id)
                logger.info(
                    "batch_counter_reset_on_completion",
                    extra={
                        "conversation_id": conversation_id,
                        "user_message": user_message,
                    },
                )

                # Scope the lock by element_code so a lock from ELEMENT_1 can never
                # block CTA messages for ELEMENT_2 in a multi-element expedition.
                # TTL is a safety net for process crashes; the finally block below
                # always deletes it explicitly on clean completion.
                _lock_element_code = (assignment_snapshot or {}).get(
                    "element_code"
                ) or ""
                finalize_lock_key = (
                    f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
                    f":{_lock_element_code}"
                    if _lock_element_code
                    else f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
                )
                try:
                    await redis_client.set(
                        finalize_lock_key,
                        "1",
                        ex=FINALIZE_LOCK_TTL_SECONDS,
                        nx=True,
                    )
                    logger.info(
                        "finalize_lock_set",
                        extra={
                            "conversation_id": conversation_id,
                            "ttl": FINALIZE_LOCK_TTL_SECONDS,
                            "key": finalize_lock_key,
                        },
                    )
                except Exception as lock_err:
                    logger.warning(
                        "finalize_lock_set_failed",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(lock_err),
                        },
                    )

                # Reconciliation MUST complete before the graph is invoked so images
                # are in DB when the LLM calls confirmar_fotos_elemento().
                # 20s timeout prevents stalling the turn if Chatwoot is slow.
                # The finally block always releases the lock — TTL is only a fallback
                # for hard process crashes.
                if checkpointer is None:
                    checkpointer = (
                        get_initialized_checkpointer() or get_redis_checkpointer()
                    )

                try:
                    logger.info(
                        "reconcile_on_completion_await_start",
                        extra={"conversation_id": conversation_id},
                    )
                    await asyncio.wait_for(
                        reconcile_on_completion(
                            redis_client,
                            checkpointer,
                            conversation_id,
                            assignment_snapshot=assignment_snapshot,
                        ),
                        timeout=20.0,
                    )
                    logger.info(
                        "reconcile_on_completion_await_done",
                        extra={"conversation_id": conversation_id},
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "reconcile_on_completion_timeout",
                        extra={
                            "conversation_id": conversation_id,
                            "timeout_seconds": 20.0,
                            "action": "continuing_without_full_reconcile",
                        },
                    )
                except Exception as _recon_err:
                    logger.error(
                        "reconcile_on_completion_error",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(_recon_err),
                        },
                        exc_info=True,
                    )
                finally:
                    # Always release the lock. TTL=21s is the only fallback for
                    # process crashes between SET and here.
                    try:
                        await redis_client.delete(finalize_lock_key)
                    except Exception as _del_err:
                        logger.warning(
                            "finalize_lock_delete_failed",
                            extra={
                                "conversation_id": conversation_id,
                                "key": finalize_lock_key,
                                "error": str(_del_err),
                            },
                        )

            # Build config for graph invocation
            config = {
                "configurable": {
                    "thread_id": conversation_id,
                    "checkpoint_ns": "conversation",
                }
            }

            # ── T2.7b: Startup checkpoint diagnostic (REQ-P2-3) ──────────
            # Before invoking the graph, check whether a checkpoint exists for
            # this conversation. This diagnostic helps detect "checkpoint lost
            # on restart" scenarios (Bug #9 from AD-6).
            #
            # If a checkpoint exists → log checkpoint_found_on_restart with mode
            # If no checkpoint → this is a fresh conversation (normal)
            # If checkpoint expected but missing → log checkpoint_lost_on_restart
            #
            # We use aget_state() — same call as the escalation guard above.
            # This is a best-effort diagnostic; any exception is swallowed.
            try:
                _checkpoint_state = await graph.aget_state(config)
                _checkpoint_mode = None
                if _checkpoint_state and _checkpoint_state.values:
                    _checkpoint_mode = _checkpoint_state.values.get("current_mode")

                if _checkpoint_mode and _checkpoint_mode != "START":
                    # Existing non-START checkpoint found — verify it will be restored
                    logger.info(
                        "checkpoint_found_on_restart",
                        extra={
                            "conversation_id": conversation_id,
                            "current_mode": _checkpoint_mode,
                            "checkpoint_present": True,
                        },
                    )
                # No else: fresh conversations (no checkpoint) are normal — don't log noise
            except Exception as _diag_err:
                # Diagnostic failure must never block message processing
                logger.debug(
                    "checkpoint_diagnostic_error",
                    extra={
                        "conversation_id": conversation_id,
                        "error": str(_diag_err),
                    },
                )

            # Build initial state
            # Note: Only pass transient fields. Persistent fields like current_mode
            # will be restored from checkpoint (if exists) or initialized by router.
            state_input = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "user_name": user_name,
                "user_message": user_message,
                "client_type": client_type,
                "user_phone": customer_phone,  # Already known from WhatsApp/Chatwoot
                "messages": [],  # History loaded from checkpointer
                "incoming_attachments": [
                    {"type": "image", "data_url": a.get("data_url", "")}
                    for a in (attachments or [])
                    if a.get("data_url")
                ],
                # NOTE: mode_context is NOT passed here - LangGraph loads it from checkpoint
            }

            logger.info(
                f"Invoking graph for conversation {conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "message_preview": (user_message or "")[:60],
                },
            )

            _graph_timeout = float(get_settings().AGENT_GRAPH_TIMEOUT_SECONDS)

            try:
                result = await asyncio.wait_for(
                    graph.ainvoke(
                        state_input,
                        config={**config, "recursion_limit": _RECURSION_LIMIT},
                    ),
                    timeout=_graph_timeout,
                )
            except asyncio.TimeoutError:
                logger.critical(
                    "graph_invoke_timeout",
                    extra={
                        "conversation_id": conversation_id,
                        "timeout_seconds": _graph_timeout,
                    },
                )
                result = {
                    "ai_response": (
                        "Disculpa, he tenido un problema procesando tu mensaje. "
                        "¿Puedes repetirlo? Si el problema persiste, escribe 'hablar con humano'."
                    )
                }

            # ── T2.7b: Checkpoint lost on restart detection (REQ-P2-3) ──
            # If the diagnostic found a non-START checkpoint but the result
            # is now START, the checkpoint was lost during this invocation.
            # This is the Bug #9 scenario from AD-6.
            try:
                _result_mode = (
                    result.get("current_mode") if isinstance(result, dict) else None
                )
                if (
                    _checkpoint_mode
                    and _checkpoint_mode not in (None, "START", "")
                    and _result_mode in (None, "START", "")
                ):
                    logger.warning(
                        "checkpoint_lost_on_restart",
                        extra={
                            "conversation_id": conversation_id,
                            "expected_mode": _checkpoint_mode,
                            "actual_mode": _result_mode,
                            "action": "conversation_reset_to_start",
                        },
                    )
            except Exception as _lost_check_err:
                logger.debug(
                    "checkpoint_lost_check_error",
                    extra={
                        "conversation_id": conversation_id,
                        "error": str(_lost_check_err),
                    },
                )

            # Extract response
            ai_response = result.get("ai_response", "")
            if not ai_response:
                logger.error(
                    "empty_ai_response_final_safety_net",
                    extra={"conversation_id": conversation_id},
                )
                ai_response = (
                    "Disculpa, he tenido un problema procesando tu mensaje. "
                    "¿Puedes repetir tu consulta?"
                )

            # EU AI Act: guarantee AI identification on first interaction
            # (legal requirement — must not depend on LLM behavior)
            if result.get("is_first_interaction") and ai_response:
                _AI_GREETING = (
                    "¡Hola! Soy el asistente con IA de MSI Automotive.\n\n"
                )
                if "asistente con IA" not in ai_response:
                    ai_response = _AI_GREETING + ai_response

            # Strip markdown for WhatsApp
            ai_response_clean = strip_markdown_for_whatsapp(ai_response)

            # Try to convert conversation_id to int (required by Chatwoot)
            try:
                chatwoot_conv_id = int(conversation_id)
            except (ValueError, TypeError):
                logger.warning(
                    f"conversation_id '{conversation_id}' is not numeric, using None for Chatwoot"
                )
                chatwoot_conv_id = None

            # ── Determine send order: images first if pending ────────
            # When enviar_imagenes_ejemplo enqueues images, the LLM produces
            # an ai_response AFTER calling the tool (e.g. "Te envío las fotos…").
            # That text would arrive BEFORE the images if sent normally.
            # Fix: when there are pending images, send images first and degrade
            # ai_response to a follow_up that is sent AFTER all images.
            pending_images = result.get("pending_images")

            if pending_images and pending_images.get("images"):
                # ── Images-first path ───────────────────────────────
                images = pending_images.get("images", [])
                delivery_contract = _resolve_image_delivery_contract(
                    pending_images,
                    conversation_id,
                )
                delivery_started_at = time.monotonic()
                # Post-image message strategy:
                # - presupuesto / elemento: only send ai_response (LLM writes the CTA in its response).
                #   Using both tool follow_up + ai_response would produce duplicate CTA messages.
                # - documentacion_base: the tool auto-generates a follow_up_message in code (NOT the LLM)
                #   listing docs that have no example image configured. This info must be sent as an
                #   extra message BEFORE ai_response so the user sees the complete docs list.
                tool_follow_up = pending_images.get("follow_up_message")
                delivery_scope = delivery_contract.get("delivery_scope", "presupuesto")

                post_image_message = ai_response_clean
                pre_image_message = None
                # Extra message inserted between images and ai_response (documentacion_base only)
                docs_extra_message = (
                    tool_follow_up if delivery_scope == "documentacion_base" else None
                )

                # Send pre-image text (only if distinct from post-image)
                if pre_image_message:
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=pre_image_message,
                        conversation_id=chatwoot_conv_id,
                    )
                    await save_assistant_message(
                        conversation_id=conversation_id,
                        content=pre_image_message,
                    )
                    logger.info(f"Sent pre-image text to {conversation_id}")

                # Send images with idempotency + bounded retry
                image_urls: list[str] = []
                image_captions: list[str | None] = []
                sent_count = 0
                transport_error: str | None = None

                if chatwoot_conv_id:
                    for img in images:
                        if isinstance(img, dict):
                            url = img.get("url", "")
                            if url:
                                image_urls.append(url)
                                descripcion = img.get("descripcion", "").strip()
                                image_captions.append(
                                    descripcion if descripcion else None
                                )
                        elif isinstance(img, str):
                            image_urls.append(img)
                            image_captions.append(None)

                    attempted_count = len(image_urls)
                    logger.info(
                        "image_delivery_attempt",
                        extra={
                            **delivery_contract,
                            "conversation_id": conversation_id,
                            "chatwoot_conversation_id": chatwoot_conv_id,
                            "delivery_attempted_count": attempted_count,
                        },
                    )

                    if image_urls:
                        (
                            sent_count,
                            transport_error,
                        ) = await _send_images_with_idempotency_and_retry(
                            chatwoot=chatwoot,
                            redis_client=redis_client,
                            chatwoot_conv_id=chatwoot_conv_id,
                            conversation_id=conversation_id,
                            image_urls=image_urls,
                            image_captions=image_captions,
                            delivery_contract=delivery_contract,
                        )

                        outcome = _classify_image_delivery_outcome(
                            attempted_count, sent_count
                        )
                        failed_count = max(attempted_count - sent_count, 0)
                        logger.info(
                            "image_delivery_result",
                            extra={
                                **delivery_contract,
                                "conversation_id": conversation_id,
                                "chatwoot_conversation_id": chatwoot_conv_id,
                                "delivery_attempted_count": attempted_count,
                                "delivery_sent_count": sent_count,
                                "delivery_failed_count": failed_count,
                                "delivery_outcome": outcome,
                                "delivery_transport_error": transport_error,
                            },
                        )
                        logger.info(
                            f"Sent {sent_count}/{len(image_urls)} images to {chatwoot_conv_id}"
                        )
                    else:
                        logger.warning(
                            f"No valid image URLs extracted from {len(images)} image entries"
                        )
                else:
                    logger.info(
                        "image_delivery_attempt",
                        extra={
                            **delivery_contract,
                            "conversation_id": conversation_id,
                            "chatwoot_conversation_id": None,
                            "delivery_attempted_count": 0,
                        },
                    )
                    logger.info(
                        "image_delivery_result",
                        extra={
                            **delivery_contract,
                            "conversation_id": conversation_id,
                            "chatwoot_conversation_id": None,
                            "delivery_attempted_count": 0,
                            "delivery_sent_count": 0,
                            "delivery_failed_count": delivery_contract.get(
                                "delivery_requested_count", 0
                            ),
                            "delivery_outcome": "failure",
                            "delivery_transport_error": "invalid_chatwoot_conversation_id",
                        },
                    )
                    logger.warning(
                        f"Cannot send images: conversation_id '{conversation_id}' is not numeric"
                    )

                # ── Compute final outcome for post-image messaging ───────
                attempted_total = len(image_urls)
                failed_total = max(attempted_total - sent_count, 0)
                final_outcome = _classify_image_delivery_outcome(
                    attempted_total, sent_count
                )

                # ── Task 5.1: User-facing fallback message by outcome ────
                # For partial_success / failure, prepend a Spanish-language
                # message informing the user honestly about what happened.
                fallback_msg = build_image_delivery_fallback_message(
                    final_outcome,
                    sent_count=sent_count,
                    failed_count=failed_total,
                    total_requested=attempted_total,
                )
                if fallback_msg and chatwoot_conv_id:
                    # Send the fallback BEFORE the post-image follow-up text.
                    # Use a proportional delay based on images actually sent so the
                    # fallback message arrives after WhatsApp has processed them.
                    sleep_seconds_fallback = 2.0 + sent_count * 2.0
                    logger.info(
                        "image_delivery_fallback_delay",
                        extra={
                            "conversation_id": conversation_id,
                            "delay_seconds": sleep_seconds_fallback,
                            "sent_count": sent_count,
                        },
                    )
                    await asyncio.sleep(sleep_seconds_fallback)
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=fallback_msg,
                        conversation_id=chatwoot_conv_id,
                    )
                    await save_assistant_message(
                        conversation_id=conversation_id,
                        content=fallback_msg,
                    )
                    logger.info(
                        "image_delivery_fallback_sent",
                        extra={
                            "conversation_id": conversation_id,
                            "delivery_outcome": final_outcome,
                            "fallback_message_length": len(fallback_msg),
                        },
                    )

                # Send post-image text after a delay proportional to the number of
                # images sent. Each image requires download + upload to Chatwoot +
                # WhatsApp Business API processing before it lands on the device.
                # A flat delay was insufficient for 3+ images — using 3s base + 2.5s
                # per image gives ~10.5s for 3 images, enough for typical conditions.
                # Skip post-image message on total failure to avoid claiming images
                # were sent when none were delivered.

                # For documentacion_base: send tool-generated docs list BEFORE ai_response.
                # This extra message lists docs with no example image configured — it is
                # auto-generated by the tool in code (not by the LLM) so it must be
                # preserved. A short extra delay separates it visually from ai_response.
                if (
                    docs_extra_message
                    and final_outcome != "failure"
                    and chatwoot_conv_id
                ):
                    sleep_seconds_docs = 3.0 + len(image_urls) * 2.5
                    await asyncio.sleep(sleep_seconds_docs)
                    docs_extra_clean = strip_markdown_for_whatsapp(docs_extra_message)
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=docs_extra_clean,
                        conversation_id=chatwoot_conv_id,
                    )
                    await save_assistant_message(
                        conversation_id=conversation_id,
                        content=docs_extra_clean,
                    )
                    logger.info(
                        "docs_extra_message_sent",
                        extra={
                            "conversation_id": conversation_id,
                            "delivery_scope": delivery_scope,
                            "message_length": len(docs_extra_clean),
                        },
                    )

                # ── Task 2.4: Tighten post-image narration for expediente scopes ──
                # When guardrails are enabled and the delivery scope is expediente,
                # the LLM-generated post-image narration must reflect the actual
                # transport outcome rather than unconditionally claiming success.
                #
                # Rules:
                #   full_success + any scope        → send as-is (original behaviour)
                #   partial_success + non-expediente → send as-is (original behaviour)
                #   partial_success + expediente + guardrails ON → replace with honest partial msg
                #   failure + any scope              → always suppress (existing behaviour)
                _settings_main = get_settings()
                _is_expediente_scope = delivery_scope in _EXPEDIENTE_DELIVERY_SCOPES
                _guardrails_on = _settings_main.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED

                if (
                    post_image_message
                    and final_outcome == "partial_success"
                    and _is_expediente_scope
                    and _guardrails_on
                ):
                    # Replace LLM narration with a bounded honest acknowledgement.
                    # We do NOT suppress entirely (images were sent), but we strip
                    # any claim that all images arrived successfully.
                    _honest_partial = (
                        f"Se han enviado {sent_count} de {attempted_total} imágenes. "
                        "Comprueba que las hayas recibido correctamente."
                    )
                    logger.info(
                        "expediente_delivery_narration_adjusted",
                        extra={
                            "conversation_id": conversation_id,
                            "delivery_scope": delivery_scope,
                            "delivery_outcome": final_outcome,
                            "original_length": len(post_image_message),
                            "replacement_length": len(_honest_partial),
                            # Task 3.4: Required fields for certainty guardrail observability
                            "narration_downgraded": True,
                            "sent_count": sent_count,
                            "total_count": attempted_total,
                        },
                    )
                    post_image_message = _honest_partial

                if post_image_message and final_outcome != "failure":
                    sleep_seconds = 3.0 + len(image_urls) * 2.5
                    logger.info(
                        "post_image_text_delay",
                        extra={
                            "conversation_id": conversation_id,
                            "delay_seconds": sleep_seconds,
                            "image_count": len(image_urls),
                        },
                    )
                    await asyncio.sleep(sleep_seconds)
                    post_clean = strip_markdown_for_whatsapp(post_image_message)
                    await chatwoot.send_message(
                        customer_phone=customer_phone,
                        message=post_clean,
                        conversation_id=chatwoot_conv_id,
                    )
                    await save_assistant_message(
                        conversation_id=conversation_id,
                        content=post_clean,
                        has_images=True,
                        image_count=len(images),
                    )
                    logger.info(f"Sent post-image message to {conversation_id}")
                elif post_image_message and final_outcome == "failure":
                    logger.info(
                        "image_delivery_post_message_suppressed",
                        extra={
                            "conversation_id": conversation_id,
                            "reason": "total_failure_no_images_sent",
                        },
                    )

                logger.info(
                    "image_delivery_final",
                    extra={
                        **delivery_contract,
                        "conversation_id": conversation_id,
                        "chatwoot_conversation_id": chatwoot_conv_id,
                        "delivery_attempted_count": attempted_total,
                        "delivery_sent_count": sent_count,
                        "delivery_failed_count": failed_total,
                        "delivery_outcome": final_outcome,
                        "delivery_duration_ms": round(
                            (time.monotonic() - delivery_started_at) * 1000, 2
                        ),
                        "delivery_post_message_sent": bool(post_image_message)
                        and final_outcome != "failure",
                        "delivery_fallback_sent": bool(fallback_msg),
                    },
                )
                try:
                    await _persist_image_delivery_outcome(
                        graph=graph,
                        config=config,
                        delivery_contract=delivery_contract,
                        attempted_count=attempted_total,
                        sent_count=sent_count,
                        transport_error=transport_error,
                    )
                except Exception as persist_error:
                    logger.error(
                        "image_delivery_outcome_persist_failed",
                        extra={
                            **delivery_contract,
                            "conversation_id": conversation_id,
                            "error": str(persist_error),
                        },
                        exc_info=True,
                    )

            else:
                # ── Normal path: no pending images ───────────────────
                await chatwoot.send_message(
                    customer_phone=customer_phone,
                    message=ai_response_clean,
                    conversation_id=chatwoot_conv_id,
                )
                logger.info(f"Sent response to {conversation_id}")

                # ── Persist assistant message (fire-and-forget) ──────
                await save_assistant_message(
                    conversation_id=conversation_id,
                    content=ai_response_clean,
                )

                # Edge case: pending_images exists but no actual image list.
                # ai_response was already sent above as the normal message.
                # tool_follow_up is not sent here: for presupuesto/elemento the CTA is
                # already in ai_response; for documentacion_base there are no images to
                # follow up on so the LLM's ai_response handles the whole turn.

        except Exception as e:
            logger.error(
                f"Error processing message for {conversation_id}: {e}",
                exc_info=True,
                extra={"conversation_id": conversation_id},
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
                    if "attachments" in message_data and isinstance(
                        message_data["attachments"], str
                    ):
                        message_data["attachments"] = json.loads(
                            message_data["attachments"]
                        )

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
                    logger.error(
                        f"Error processing message {message_id}: {e}", exc_info=True
                    )

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
                        logger.critical(
                            f"Too many consecutive errors ({consecutive_errors}), pausing..."
                        )
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

    logger.info("=" * 60)
    logger.info("Starting MSI-a Agent (Mode-Based Architecture)")
    logger.info("=" * 60)

    # Initialize Redis
    redis_client = await initialize_redis_with_retry()

    # Initialize Chatwoot
    chatwoot = ChatwootClient()

    # Initialize graph
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    user_store = await create_user_store()
    graph = await create_compiled_graph(checkpointer, store=user_store)
    logger.info("Conversation graph compiled successfully (with user profile store)")

    # Setup graceful shutdown
    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

    # Start background tasks
    batch_task = asyncio.create_task(
        image_batch_confirmation_worker(shutdown_event, checkpointer)
    )
    logger.info("Image batch confirmation worker started")

    lifecycle_task = asyncio.create_task(
        case_lifecycle_worker(shutdown_event, chatwoot)
    )
    logger.info("Case lifecycle worker started")

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
        for task in [batch_task, lifecycle_task, cache_sub_task]:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Agent shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
