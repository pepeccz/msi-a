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

V2 changes (gated behind EXPEDIENTE_V2_ENABLED):
- Task 2.1: element_code at save time read from DB via ElementStateService
            instead of ContextVar snapshot.
- Task 2.1: Orphan fallback in reconcile_on_completion uses case-level count
            when element-filtered count returns 0.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid as uuid_mod
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from agent.services.case_image_batch_service import (
    UploadBatchResolution,
    get_case_image_batch_service,
)
from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE
from api.services.chatwoot_image_service import DownloadResult, get_chatwoot_image_service
from database.connection import get_async_session
from database.models import Case, CaseImage
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.redis_client import get_redis_client

if TYPE_CHECKING:
    from agent.services.element_state_service import ElementStateService

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

IMAGE_BATCH_TIMEOUT_SECONDS = 15
IMAGE_BATCH_KEY_PREFIX = "image_batch:"
IMAGE_BATCH_FINAL_PREFIX = "image_batch_final:"
IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX = "image_assignment_snapshot:"
IMAGE_BATCH_STATE_PREFIX = "image_batch_state:"
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


def is_document_attachment(attachment: dict) -> bool:
    """Check if an attachment is a document/PDF type (file_type == 'file')."""
    return attachment.get("file_type", "") == "file"


def is_saveable_attachment(attachment: dict) -> bool:
    """Check if an attachment can be saved (image or document/PDF)."""
    return is_image_attachment(attachment) or is_document_attachment(attachment)


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

    Handles the "narrated ahead of state" scenario (Scenario B):
    - element_phase == "photos": normal case, return element N (current).
    - element_phase == "data" AND current element status is "photos_done" AND
      a next element exists: the agent already asked for N+1 photos before calling
      completar_elemento_actual(). Attribute incoming images to element N+1.
    - element_phase == "data" AND current element NOT photos_done: images are
      unrelated / base-doc candidates — return None.

    Rationale: confirmar_fotos_elemento() transitions element_phase to "data" but
    completar_elemento_actual() has not yet been called.  In that window the LLM
    may have already asked for the next element's photos, so images belong to N+1,
    not to the base-doc bucket.
    """
    from agent.utils.expediente_types import ELEMENT_STATUS_PHOTOS_DONE

    if not mode_context:
        return None

    sub_mode = mode_context.get("expediente_sub_mode", "")
    if sub_mode != "collect_element_data":
        return None  # Only element-specific images in this sub-mode

    element_phase = mode_context.get("element_phase", "photos")
    element_codes = mode_context.get("element_codes", [])
    current_idx = mode_context.get("current_element_index", 0)

    if element_phase == "photos":
        # Normal case: element N is still in photo collection — return current element.
        if not element_codes or current_idx >= len(element_codes):
            return None
        return element_codes[current_idx]

    elif element_phase == "data":
        # Element N confirmed (photos_done).  Agent may have already asked for N+1 photos
        # before calling completar_elemento_actual() — check if that's the case.
        element_data_status = mode_context.get("element_data_status", {})
        current_code = (
            element_codes[current_idx]
            if element_codes and current_idx < len(element_codes)
            else None
        )

        if (
            current_code
            and element_data_status.get(current_code) == ELEMENT_STATUS_PHOTOS_DONE
        ):
            # Current element's photos are confirmed.  If there is a next element,
            # the incoming photo batch belongs to it (Scenario B fix).
            next_idx = current_idx + 1
            if next_idx < len(element_codes):
                logger.debug(
                    "get_current_element_code.attributed_to_next_element",
                    extra={
                        "current_element": current_code,
                        "next_element": element_codes[next_idx],
                        "element_phase": element_phase,
                    },
                )
                return element_codes[next_idx]

        # Photos during data phase of N (not yet confirmed), or last element → base docs
        return None

    else:
        return None


async def get_current_element_code_async(
    mode_context: dict | None,
    conversation_id: str | None,
) -> str | None:
    """
    Async version of get_current_element_code() with deterministic Redis marker check.

    T-21: At the top of the 'element_phase == data' branch, check for a
    Redis transition marker set by confirm_element_photos() / guard_photo_completion().
    If found, return its value directly (deterministic). If not found, fall through
    to the existing heuristic (backward compatibility for pre-deploy conversations).

    Key format: element_transition:{conversation_id}:{current_element_code}
    Value: next_element_code  OR  "__none__" (last element)

    Errors from Redis are logged at WARNING and the heuristic fallback runs.
    """
    if not mode_context:
        return None

    sub_mode = mode_context.get("expediente_sub_mode", "")
    if sub_mode != "collect_element_data":
        return None

    element_phase = mode_context.get("element_phase", "photos")
    element_codes = mode_context.get("element_codes", [])
    current_idx = mode_context.get("current_element_index", 0)

    # Fast path for photos phase — no marker check needed
    if element_phase == "photos":
        if not element_codes or current_idx >= len(element_codes):
            return None
        return element_codes[current_idx]

    if element_phase == "data":
        # AC5: Redis marker check BEFORE the heuristic
        current_code = (
            element_codes[current_idx]
            if element_codes and current_idx < len(element_codes)
            else None
        )

        if current_code and conversation_id:
            try:
                redis = get_redis_client()
                marker_key = f"element_transition:{conversation_id}:{current_code}"
                marker_val = await redis.get(marker_key)
                if marker_val is not None:
                    marker_str = (
                        marker_val.decode() if isinstance(marker_val, bytes) else marker_val
                    )
                    if marker_str == "__none__":
                        return None  # Last element — images go to base docs
                    return marker_str  # Next element code (deterministic)
            except Exception as _marker_err:
                logger.warning(
                    "element_transition_marker_read_failed",
                    extra={
                        "conversation_id": conversation_id,
                        "element_code": current_code,
                        "error": str(_marker_err),
                    },
                )
                # Fall through to heuristic

        # Fallback: existing heuristic (backward compat for pre-deploy conversations)
        return get_current_element_code(mode_context)

    return None


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


async def get_scoped_case_image_count(
    case_id: str,
    upload_batch_id: str | None = None,
) -> int:
    """Get image count for a case, optionally scoped to one upload batch."""
    try:
        async with get_async_session() as session:
            query = select(func.count(CaseImage.id)).where(
                CaseImage.case_id == uuid_mod.UUID(case_id)
            )
            if upload_batch_id:
                query = query.where(CaseImage.upload_batch_id == upload_batch_id)
            result = await session.execute(query)
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"Failed to get scoped image count for case {case_id}: {e}")
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


def _get_batch_redis_key(conversation_id: str, scope_key: str | None) -> str:
    """
    Build the Redis key for an image batch counter.

    New format (per-element isolation):
        image_batch:{conversation_id}:{scope_key}

    Legacy format (backward compat, no scope_key):
        image_batch:{conversation_id}

    The scope_key is stored verbatim (not hashed) so it can be
    recovered from the key when needed, while still being unique per
    element/sub-mode combination.
    """
    if scope_key:
        return f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}:{scope_key}"
    return f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}"


def _is_legacy_batch_key(data: dict) -> bool:
    """
    Detect whether a batch hash is in the old format.

    Old format: no ``upload_scope_key`` field in the hash.
    New format: ``upload_scope_key`` field present (may be bytes or str).

    Detection is based on hash field presence, NOT on key name parsing,
    so it works for both old ``image_batch:{conv_id}`` keys and new
    ``image_batch:{conv_id}:{scope}`` keys.
    """
    has_scope = (b"upload_scope_key" in data) or ("upload_scope_key" in data)
    return not has_scope


def _extract_conversation_id_from_batch(key_str: str, data: dict) -> str:
    """
    Extract conversation_id for a batch key.

    Prefers the ``conversation_id`` hash field (stored explicitly by new-format
    writes) to avoid parsing the key name (which now contains a scope suffix).

    Falls back to key-name parsing for legacy keys that have no such field.
    """
    # Prefer explicit hash field
    raw = data.get(b"conversation_id", data.get("conversation_id"))
    if raw:
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    # Legacy fallback: strip prefix and take everything up to the first ":"
    # for old keys like image_batch:{conv_id}
    # (new keys have the scope appended, so we'd get the wrong value — but
    # new keys always have the hash field so this branch won't be reached).
    stripped = key_str.removeprefix(IMAGE_BATCH_KEY_PREFIX)
    return stripped.split(":")[0] if ":" in stripped else stripped


def _build_worker_cta_message(
    count: int,
    failed: int,
    total_images: int,
    element_display_name: str | None,
    is_base_docs: bool,
    is_orphan: bool = False,
    failed_reasons: list[str] | None = None,
) -> str | None:
    """
    Build the CTA message sent by the image_batch_confirmation_worker.

    Returns None for orphan batches (no case_id) — no message sent.
    Returns a Spanish string otherwise.

    Scope labels (in order of precedence):
    1. element_display_name → "para {name}"
    2. is_base_docs=True → "de documentación base"
    3. fallback → "de este bloque"

    When failed_reasons is provided and has ≥2 distinct codes, renders a
    bulleted list with per-reason counts. When all failures share the same
    code, embeds that reason as a flat single line.
    """
    from api.services.chatwoot_image_service import REASON_MESSAGES

    if is_orphan:
        return None

    if element_display_name:
        scope_label = f"para {element_display_name}"
    elif is_base_docs:
        scope_label = "de documentación base"
    else:
        scope_label = "de este bloque"

    listo_cta = "Cuando hayas terminado de enviar archivos, escribe 'listo'."

    if failed > 0:
        # Build reason detail block when reason codes are available
        reason_detail = _build_reason_detail(failed_reasons)

        if count == 0:
            if reason_detail:
                return (
                    f"No se pudieron descargar {failed} archivo(s) {scope_label}:\n"
                    f"{reason_detail}\n\n"
                    f"{listo_cta}"
                )
            return (
                f"No se pudieron descargar {failed} archivo(s) {scope_label}. "
                f"Intenta enviarlos de nuevo.\n\n"
                f"{listo_cta}"
            )
        else:
            if reason_detail:
                return (
                    f"He recibido {count} archivo(s) {scope_label}. No pude procesar {failed}:\n"
                    f"{reason_detail}\n\n"
                    f"{listo_cta}"
                )
            return (
                f"He recibido {count} archivo(s) {scope_label}. "
                f"{failed} no se pudieron descargar.\n"
                f"{listo_cta}"
            )
    elif total_images > count:
        return (
            f"He recibido {count} archivo(s) nuevo(s) {scope_label}.\n\n"
            f"{listo_cta}"
        )
    else:
        return (
            f"He recibido {count} archivo(s) {scope_label}.\n\n"
            f"{listo_cta}"
        )


def _build_reason_detail(failed_reasons: list[str] | None) -> str | None:
    """
    Build the reason detail block for the CTA message.

    Returns:
        None if no reasons available (callers use generic text).
        A single-line string if all failures share one reason code.
        A bulleted multi-line string if ≥2 distinct reason codes.
    """
    from api.services.chatwoot_image_service import REASON_MESSAGES

    if not failed_reasons:
        return None

    distinct_codes = set(failed_reasons)

    if len(distinct_codes) == 1:
        code = next(iter(distinct_codes))
        reason_msg = REASON_MESSAGES.get(code, "")
        return reason_msg if reason_msg else None

    # ≥2 distinct codes → bulleted list with per-code counts
    from collections import Counter
    counts = Counter(failed_reasons)
    lines = []
    for code, n in counts.most_common():
        reason_msg = REASON_MESSAGES.get(code, code)
        lines.append(f"• {reason_msg} ({n})")
    return "\n".join(lines)


async def get_batch_info(
    redis_client,
    conversation_id: str,
    scope_key: str | None = None,
) -> tuple[int, float]:
    """Get current batch info from Redis. Returns (count, last_update_timestamp)."""
    key = _get_batch_redis_key(conversation_id, scope_key)
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
    upload_batch_id: str | None = None,
    upload_scope_key: str | None = None,
    failed_reasons: list[str] | None = None,
) -> int:
    """
    Update the batch counter in Redis (HSET pattern).

    Per-element key isolation: when upload_scope_key is provided the counter
    is stored under ``image_batch:{conversation_id}:{scope_key}`` so concurrent
    element uploads do not overwrite each other.

    The ``conversation_id`` is stored explicitly in the hash so the worker can
    recover it without parsing the key name (backward-compat).

    failed_reasons: list of reason codes for failed downloads; appended to
    any existing reasons already stored in the Redis hash (JSON-encoded).

    Returns new total count.
    """
    key = _get_batch_redis_key(conversation_id, upload_scope_key)
    try:
        data = await redis_client.hgetall(key)
        existing_batch_id = None
        existing_reasons: list[str] = []
        if data:
            existing_batch_id = data.get(
                b"upload_batch_id", data.get("upload_batch_id")
            )
            if isinstance(existing_batch_id, bytes):
                existing_batch_id = existing_batch_id.decode("utf-8")
            # Recover any previously stored failure reasons
            existing_reasons_raw = data.get(b"failed_reasons", data.get("failed_reasons", ""))
            if isinstance(existing_reasons_raw, bytes):
                existing_reasons_raw = existing_reasons_raw.decode("utf-8")
            if existing_reasons_raw:
                try:
                    existing_reasons = json.loads(existing_reasons_raw)
                except (json.JSONDecodeError, TypeError):
                    existing_reasons = []

        if (
            upload_batch_id
            and existing_batch_id
            and existing_batch_id != upload_batch_id
        ):
            current_count = 0
            existing_failed = 0
            existing_reasons = []  # new batch — reset reasons too
        else:
            current_count, _ = await get_batch_info(redis_client, conversation_id, upload_scope_key)
            existing_failed = (
                int(data.get(b"failed", data.get("failed", 0))) if data else 0
            )

        new_count = current_count + additional_count
        all_reasons = existing_reasons + (failed_reasons or [])

        mapping: dict[str, str] = {
            "count": str(new_count),
            "failed": str(existing_failed + failed_count),
            "last_update": str(time.time()),
            "user_phone": user_phone,
            # Store conversation_id in the hash so the worker doesn't need
            # to parse the key name (which now contains the scope suffix).
            "conversation_id": conversation_id,
        }
        if all_reasons:
            mapping["failed_reasons"] = json.dumps(all_reasons)
        if case_id:
            mapping["case_id"] = case_id
        if upload_batch_id:
            mapping["upload_batch_id"] = upload_batch_id
        if upload_scope_key:
            mapping["upload_scope_key"] = upload_scope_key

        await redis_client.hset(key, mapping=mapping)
        await redis_client.expire(key, 3600)  # 1h auto-cleanup

        logger.debug(
            f"Batch counter updated: {current_count} -> {new_count} | "
            f"conversation_id={conversation_id} | scope_key={upload_scope_key}"
        )
        return new_count
    except Exception as e:
        logger.error(f"Failed to update batch counter: {e}")
        return 0


async def reset_batch_counter(
    redis_client,
    conversation_id: str,
    scope_key: str | None = None,
) -> None:
    """Reset/delete the batch counter for a conversation (and optional scope)."""
    key = _get_batch_redis_key(conversation_id, scope_key)
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Failed to reset batch counter: {e}")


async def reset_all_batch_counters(
    redis_client,
    conversation_id: str,
) -> None:
    """Delete ALL batch counter keys for a conversation (legacy + scoped)."""
    # Delete scoped keys via SCAN
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(
            cursor=cursor,
            match=f"{IMAGE_BATCH_KEY_PREFIX}{conversation_id}:*",
            count=100,
        )
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break

    # Delete legacy key explicitly
    legacy_key = _get_batch_redis_key(conversation_id, None)
    await redis_client.delete(legacy_key)

    # Clean related keys
    await redis_client.delete(f"{IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX}{conversation_id}")
    await redis_client.delete(f"{IMAGE_BATCH_STATE_PREFIX}{conversation_id}")

    logger.info("batch_counters_fully_reset | conversation_id=%s", conversation_id)


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
        "in_image_collection_mode": bool(
            assignment_snapshot.get("in_image_collection_mode")
        ),
        "expediente_sub_mode": assignment_snapshot.get("expediente_sub_mode"),
        "element_phase": assignment_snapshot.get("element_phase"),
        "upload_scope_key": assignment_snapshot.get("upload_scope_key"),
        "upload_batch_id": assignment_snapshot.get("upload_batch_id"),
    }
    key = f"{IMAGE_ASSIGNMENT_SNAPSHOT_PREFIX}{conversation_id}"
    try:
        await redis_client.set(key, json.dumps(compact), ex=7200)
    except Exception as e:
        logger.warning(f"Failed to persist assignment snapshot: {e}")


async def get_assignment_snapshot(
    redis_client, conversation_id: str
) -> dict[str, Any] | None:
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


def _build_upload_scope_key(assignment_snapshot: dict[str, Any] | None) -> str | None:
    """Build a deterministic ownership scope for one expediente upload window."""
    if not assignment_snapshot:
        return None

    case_id = assignment_snapshot.get("case_id")
    if not case_id:
        return None

    sub_mode = assignment_snapshot.get("expediente_sub_mode") or "unknown"
    element_code = assignment_snapshot.get("element_code")
    scope_subject = f"element:{element_code}" if element_code else "base_docs"
    return f"case:{case_id}:sub_mode:{sub_mode}:scope:{scope_subject}"


def _get_case_image_description(is_doc: bool, reconciliation: bool) -> str:
    """Return the correct CaseImage.description based on content type and save path.

    Pure helper — no side effects, trivially testable.

    Args:
        is_doc: True when the attachment is a document/PDF
                (file_type == "file" or type == "document").
        reconciliation: True when called from the reconciliation path,
                        False when called from the primary save path.

    Returns:
        The Spanish description string for the CaseImage record.
    """
    if reconciliation:
        return (
            "Documento recuperado por reconciliación"
            if is_doc
            else "Imagen recuperada por reconciliación"
        )
    return (
        "Documento enviado por usuario via WhatsApp"
        if is_doc
        else "Imagen enviada por usuario via WhatsApp"
    )


def _build_attachment_fingerprint(
    chatwoot_message_id: int | None,
    attachment: dict[str, Any],
) -> str:
    """Build a stable attachment-level fingerprint for deduplication.

    Uses Chatwoot's stable attachment ``id`` instead of ``data_url`` because
    Active Storage signed URLs change between webhook delivery and API
    query, producing different fingerprints for the same physical image.
    """
    basis = "|".join(
        [
            str(chatwoot_message_id or ""),
            str(attachment.get("id") or ""),
            str(attachment.get("file_size") or ""),
            str(attachment.get("filename") or attachment.get("file_name") or ""),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


async def assign_upload_batch(
    redis_client,
    conversation_id: str,
    assignment_snapshot: dict[str, Any] | None,
    *,
    allow_create: bool,
    message_created_at: int | float | None = None,
) -> dict[str, Any] | None:
    """Reuse or create the persisted upload batch for the current scope."""
    if not assignment_snapshot:
        return assignment_snapshot

    scope_key = _build_upload_scope_key(assignment_snapshot)
    assignment_snapshot["upload_scope_key"] = scope_key
    if not scope_key:
        return assignment_snapshot

    batch_service = get_case_image_batch_service()
    try:
        resolution = await batch_service.resolve_for_snapshot(
            assignment_snapshot=assignment_snapshot,
            allow_create=allow_create,
            message_created_at=message_created_at,
            is_live_ingest=True,
        )
    except Exception as e:
        logger.warning(f"Failed to resolve upload batch from DB: {e}")
        resolution = None

    if resolution:
        assignment_snapshot["upload_batch_id"] = resolution.batch_id
        assignment_snapshot["upload_scope_key"] = resolution.upload_scope_key
        assignment_snapshot["resolved_element_code"] = resolution.owner_element_code
        assignment_snapshot["resolved_owner_scope"] = resolution.owner_scope
        assignment_snapshot["resolved_batch_is_historical"] = resolution.is_historical

        # REQ-PERSIST-1 (SHOULD): Detect element_code drift between the
        # ingest-time snapshot and the batch the DB resolved to.
        # This can happen when the element advances while images are in-flight.
        # We warn but do NOT block or discard — the resolved batch already
        # applied the cross-scope guard in resolve_for_scope().
        _snapshot_element_code = assignment_snapshot.get("element_code")
        _resolved_element_code = resolution.owner_element_code
        if _resolved_element_code != _snapshot_element_code:
            logger.warning(
                "image_element_code_drift_detected",
                extra={
                    "conversation_id": conversation_id,
                    "case_id": assignment_snapshot.get("case_id"),
                    "message_id": None,
                    "snapshot_element_code": _snapshot_element_code,
                    "resolved_element_code": _resolved_element_code,
                },
            )

    redis_key = f"{IMAGE_BATCH_STATE_PREFIX}{conversation_id}"
    try:
        raw = await redis_client.get(redis_key)
        existing: dict[str, Any] | None = None
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                existing = parsed

        if resolution and resolution.is_historical:
            return assignment_snapshot

        if (
            (not resolution)
            and existing
            and existing.get("upload_scope_key")
            == assignment_snapshot.get("upload_scope_key")
        ):
            assignment_snapshot["upload_batch_id"] = existing.get("upload_batch_id")
            return assignment_snapshot

        if not allow_create:
            if existing:
                assignment_snapshot["upload_batch_id"] = existing.get("upload_batch_id")
            return assignment_snapshot

        batch_id = assignment_snapshot.get("upload_batch_id") or str(uuid_mod.uuid4())
        assignment_snapshot["upload_batch_id"] = batch_id
        await redis_client.set(
            redis_key,
            json.dumps(
                {
                    "upload_batch_id": batch_id,
                    "upload_scope_key": assignment_snapshot.get("upload_scope_key")
                    or scope_key,
                    "case_id": assignment_snapshot.get("case_id"),
                    "element_code": assignment_snapshot.get("element_code"),
                }
            ),
            ex=7200,
        )
    except Exception as e:
        logger.warning(f"Failed to assign upload batch: {e}")

    return assignment_snapshot


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
) -> tuple[int, int, list[str]]:
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
        Tuple of (saved_count, failed_count, failed_reasons) where failed_reasons
        is a list of reason codes (strings) for each failed download.
    """
    image_service = get_chatwoot_image_service()
    settings = get_settings()

    # Prefer explicit assignment context when available.
    # Keep base-doc images with element_code=None when not in element photo phase.
    if assignment_context:
        snap_case_id = assignment_context.get("case_id")
        if snap_case_id:
            case_id = snap_case_id

        if (
            "in_image_collection_mode" in assignment_context
            and not assignment_context.get(
                "in_image_collection_mode",
            )
        ):
            element_code = None
        elif "element_code" in assignment_context:
            element_code = assignment_context.get("element_code")

    # Override element_code from DB (REQ-IMG-1): ignore the ContextVar/snapshot-derived
    # element_code and instead query the DB for the first non-completed element.
    # This prevents stale assignment when the snapshot drifts from DB reality.
    if case_id:
        try:
            from agent.services.element_state_service import get_element_state_service

            _element_state_svc: ElementStateService = get_element_state_service()
            # element_codes come from assignment_context (mode_context carries them)
            _element_codes: list[str] = []
            if assignment_context:
                _mode_ctx = assignment_context.get("mode_context") or {}
                _element_codes = _mode_ctx.get("element_codes", [])
                # Also check in_image_collection_mode: only assign element_code when in
                # the element photo collection sub-mode (not base_docs).
                _in_element_sub_mode = (
                    assignment_context.get("expediente_sub_mode")
                    == "collect_element_data"
                    and assignment_context.get("element_phase", "photos") == "photos"
                )
            else:
                _in_element_sub_mode = False

            if _in_element_sub_mode and _element_codes:
                _db_element_code = await _element_state_svc.get_current_element(
                    case_id, _element_codes
                )
                # Only override when DB returns a valid code.
                # If None (all complete), fall through to existing element_code.
                if _db_element_code is not None:
                    # Guard: verify the candidate element has not already finalized
                    # its photo batch. Late-arriving images must NOT be attributed
                    # to a finalized element (photos_completed_at IS NOT NULL).
                    from agent.services.element_state_service import ElementState

                    _ced_check: (
                        ElementState | None
                    ) = await _element_state_svc.get_element_state(
                        case_id, _db_element_code
                    )
                    if (
                        _ced_check is not None
                        and _ced_check.photos_completed_at is not None
                    ):
                        # Element already finalized — reject attribution
                        logger.warning(
                            "image_handling.v2_element_already_finalized",
                            extra={
                                "conversation_id": conversation_id,
                                "case_id": case_id,
                                "resolved_element_code": _db_element_code,
                                "photos_completed_at": str(
                                    _ced_check.photos_completed_at
                                ),
                            },
                        )
                        element_code = None
                    else:
                        # Element still active (or state not found) — proceed normally
                        if _db_element_code != element_code:
                            logger.info(
                                "image_handling.v2_element_code_override",
                                extra={
                                    "conversation_id": conversation_id,
                                    "case_id": case_id,
                                    "snapshot_element_code": element_code,
                                    "db_element_code": _db_element_code,
                                },
                            )
                        element_code = _db_element_code
                # If not in element sub-mode, keep element_code=None (base docs)
            elif not _in_element_sub_mode:
                element_code = None

        except Exception as _v2_err:
            logger.warning(
                "image_handling.v2_element_code_lookup_failed",
                extra={
                    "conversation_id": conversation_id,
                    "case_id": case_id,
                    "error": str(_v2_err),
                    "fallback": "using_snapshot_element_code",
                },
            )
            # Graceful fallback: keep element_code from snapshot

    saved_count = 0
    failed_count = 0
    failed_reasons: list[str] = []
    upload_batch_id = (
        assignment_context.get("upload_batch_id") if assignment_context else None
    )
    upload_scope_key = (
        assignment_context.get("upload_scope_key") if assignment_context else None
    )
    resolved_element_code = (
        assignment_context.get("resolved_element_code") if assignment_context else None
    )
    if resolved_element_code is not None:
        element_code = resolved_element_code

    # Filter to saveable attachments (images + documents/PDFs)
    saveable = [a for a in attachments if is_saveable_attachment(a)]
    if not saveable:
        return 0, 0, []

    # Get existing image count for incremental naming
    existing_count = await get_case_image_count(case_id)
    case_short_id = case_id[:8]

    logger.info(
        f"Saving {len(saveable)} attachments silently | "
        f"case_id={case_id} | conversation_id={conversation_id} | "
        f"existing_count={existing_count} | element_code={element_code}",
        extra={
            "conversation_id": conversation_id,
            "case_id": case_id,
            "attachment_count": len(saveable),
            "element_code": element_code,
        },
    )

    for attachment in saveable:
        data_url = attachment.get("data_url")
        if not data_url:
            logger.warning(f"Attachment missing data_url: {attachment}")
            failed_count += 1
            continue

        attachment_fingerprint = _build_attachment_fingerprint(
            chatwoot_message_id, attachment
        )

        try:
            # Polymorphic naming: use 'doc' for document/PDF attachments, 'image' for photos
            _is_doc = attachment.get("file_type") == "file" or attachment.get("type") == "document"
            _slot = "doc" if _is_doc else "image"
            display_name = (
                f"case_{case_short_id}_{_slot}_{existing_count + saved_count + 1}"
            )
            download_result = await image_service.download_image(
                data_url=data_url,
                display_name=display_name,
                element_code=element_code,
            )

            if not download_result.success:
                failed_count += 1
                logger.error(
                    f"Failed to download image | url={data_url} | case_id={case_id} "
                    f"| reason={download_result.reason_code}",
                    extra={"conversation_id": conversation_id, "case_id": case_id},
                )
                if download_result.reason_code:
                    failed_reasons.append(download_result.reason_code)
                continue

            # Save to database
            image_data = download_result.data  # dict guaranteed when success=True
            async with get_async_session() as session:
                existing_image = await session.execute(
                    select(CaseImage.id)
                    .where(CaseImage.case_id == uuid_mod.UUID(case_id))
                    .where(CaseImage.attachment_fingerprint == attachment_fingerprint)
                )
                if existing_image.scalar_one_or_none() is not None:
                    logger.info(
                        "image_insert_dedup_skipped",
                        extra={
                            "conversation_id": conversation_id,
                            "case_id": case_id,
                            "attachment_fingerprint": attachment_fingerprint,
                            "source": "save_images_silently",
                        },
                    )
                    continue

                case_image = CaseImage(
                    case_id=uuid_mod.UUID(case_id),
                    stored_filename=image_data["stored_filename"],
                    original_filename=image_data.get("original_filename"),
                    mime_type=image_data["mime_type"],
                    file_size=image_data.get("file_size"),
                    display_name=display_name,
                    description=_get_case_image_description(_is_doc, reconciliation=False),
                    element_code=element_code,
                    image_type="user_upload",
                    chatwoot_message_id=chatwoot_message_id,
                    attachment_fingerprint=attachment_fingerprint,
                    upload_scope_key=upload_scope_key,
                    upload_batch_id=upload_batch_id,
                    is_valid=None,
                )
                session.add(case_image)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    logger.info(
                        "image_insert_dedup_skipped",
                        extra={
                            "conversation_id": conversation_id,
                            "case_id": case_id,
                            "attachment_fingerprint": attachment_fingerprint,
                            "source": "save_images_silently_integrity",
                        },
                    )
                    continue

                # Observability: trace each persisted image insert
                logger.info(
                    "image_insert_persisted",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "stored_filename": image_data["stored_filename"],
                        "display_name": display_name,
                        "element_code": element_code,
                        "upload_batch_id": upload_batch_id,
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

    return saved_count, failed_count, failed_reasons


# ──────────────────────────────────────────────────────────────────
# Reconciliation: recover dropped webhooks
# ──────────────────────────────────────────────────────────────────


async def reconcile_conversation_images(
    conversation_id: str,
    case_id: str,
    case_created_at: float | None = None,
    element_code: str | None = None,
    upload_batch_id: str | None = None,
    upload_scope_key: str | None = None,
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

    # Step 2: Get existing attachment fingerprints from DB
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImage.attachment_fingerprint)
                .where(CaseImage.case_id == uuid_mod.UUID(case_id))
                .where(CaseImage.attachment_fingerprint.isnot(None))
            )
            existing_fingerprints = {row[0] for row in result.fetchall() if row[0]}
    except Exception as e:
        logger.error(f"Reconciliation: failed to query DB: {e}", exc_info=True)
        return 0, 0

    logger.info(
        f"Reconciliation: scanning {len(messages)} message(s) | "
        f"conversation_id={conversation_id} | case_id={case_id}"
    )

    # Step 4: Download and save missing images
    image_service = get_chatwoot_image_service()
    existing_count = await get_case_image_count(case_id)
    case_short_id = case_id[:8]

    # Lazily resolved orphan batch (shared across all unmatched images in this run).
    _orphan_batch_resolution: UploadBatchResolution | None = None

    # Defence-in-depth: pre-load chatwoot_message_ids already saved for this
    # case so we can skip entire messages without re-computing fingerprints.
    _existing_msg_ids: set[int] = set()
    try:
        async with get_async_session() as session:
            _msg_id_result = await session.execute(
                select(CaseImage.chatwoot_message_id)
                .where(CaseImage.case_id == uuid_mod.UUID(case_id))
                .where(CaseImage.chatwoot_message_id.isnot(None))
            )
            _existing_msg_ids = {
                row[0] for row in _msg_id_result.fetchall() if row[0] is not None
            }
    except Exception as _mid_err:
        logger.warning(
            f"Reconciliation: failed to pre-load chatwoot_message_ids: {_mid_err}"
        )

    for msg in messages:
        msg_id = msg.get("id")
        msg_created_at = msg.get("created_at")  # Unix timestamp from Chatwoot
        attachments = msg.get("attachments", [])

        # Defence-in-depth: if ALL images from this message were already
        # saved by the webhook ingest path, skip the entire message.
        if msg_id is not None and msg_id in _existing_msg_ids:
            logger.info(
                f"Reconciliation: skipping message {msg_id} — already saved by webhook",
                extra={
                    "conversation_id": conversation_id,
                    "case_id": case_id,
                    "chatwoot_message_id": msg_id,
                    "source": "reconcile_dedup_by_msg_id",
                },
            )
            continue

        for attachment in attachments:
            if not is_saveable_attachment(attachment):
                continue

            attachment_fingerprint = _build_attachment_fingerprint(msg_id, attachment)
            if attachment_fingerprint in existing_fingerprints:
                # Idempotent: already persisted — skip silently.
                continue

            data_url = attachment.get("data_url")
            if not data_url:
                failed += 1
                continue

            try:
                # ── Timestamp-based batch resolution (the fix) ──────────────
                # Each recovered image is assigned to the batch that was open
                # at the time the Chatwoot message was *originally* sent.
                # We NEVER inherit the caller's current active batch/element.
                resolved_batch_id: str | None = None
                resolved_element_code: str | None = None
                resolved_scope_key: str | None = None

                batch_svc = get_case_image_batch_service()

                if msg_created_at is not None:
                    ts_resolution = await batch_svc.resolve_batch_for_timestamp(
                        case_id=case_id,
                        message_created_at=msg_created_at,
                    )
                else:
                    ts_resolution = None

                if ts_resolution is not None:
                    resolved_batch_id = ts_resolution.batch_id
                    resolved_element_code = ts_resolution.owner_element_code
                    resolved_scope_key = ts_resolution.upload_scope_key
                else:
                    # No batch window covers this message timestamp → route to
                    # orphan/unmatched batch so the image is not lost and does
                    # not contaminate any element-scoped count.
                    if _orphan_batch_resolution is None:
                        _orphan_batch_resolution = (
                            await batch_svc.get_or_create_orphan_batch(
                                case_id=case_id,
                            )
                        )
                    resolved_batch_id = _orphan_batch_resolution.batch_id
                    resolved_element_code = None  # orphan has no element
                    resolved_scope_key = _orphan_batch_resolution.upload_scope_key

                    logger.warning(
                        "reconcile_image_no_batch_window",
                        extra={
                            "conversation_id": conversation_id,
                            "case_id": case_id,
                            "msg_id": msg_id,
                            "msg_created_at": msg_created_at,
                            "orphan_batch_id": resolved_batch_id,
                            "source": "reconcile_conversation_images",
                        },
                    )
                # ─────────────────────────────────────────────────────────────

                # Polymorphic naming: use 'doc' for document/PDF, 'image' for photos
                _is_doc_recon = attachment.get("file_type") == "file" or attachment.get("type") == "document"
                _slot_recon = "doc" if _is_doc_recon else "image"
                display_name = (
                    f"case_{case_short_id}_{_slot_recon}_{existing_count + reconciled + 1}"
                )
                download_result = await image_service.download_image(
                    data_url=data_url,
                    display_name=display_name,
                    element_code=resolved_element_code,
                )

                if not download_result.success:
                    failed += 1
                    continue

                recon_data = download_result.data  # dict guaranteed when success=True
                async with get_async_session() as session:
                    case_image = CaseImage(
                        case_id=uuid_mod.UUID(case_id),
                        stored_filename=recon_data["stored_filename"],
                        original_filename=data_url.split("/")[-1]
                        if "/" in data_url
                        else None,
                        mime_type=recon_data["mime_type"],
                        file_size=recon_data.get("file_size"),
                        display_name=display_name,
                        description=_get_case_image_description(_is_doc_recon, reconciliation=True),
                        element_code=resolved_element_code,  # per-timestamp resolved
                        image_type="user_upload",
                        chatwoot_message_id=msg_id,
                        attachment_fingerprint=attachment_fingerprint,
                        upload_scope_key=resolved_scope_key,  # per-timestamp resolved
                        upload_batch_id=resolved_batch_id,  # per-timestamp resolved
                        is_valid=None,
                    )
                    session.add(case_image)
                    try:
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        continue

                reconciled += 1
                existing_fingerprints.add(attachment_fingerprint)
                # Observability: trace each reconciled image insert
                logger.info(
                    "image_insert_persisted",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "stored_filename": recon_data["stored_filename"],
                        "display_name": display_name,
                        "element_code": resolved_element_code,
                        "upload_batch_id": resolved_batch_id,
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
            persisted_snapshot = await get_assignment_snapshot(
                redis_client, conversation_id
            )

        effective_snapshot = assignment_snapshot or persisted_snapshot

        # Observability: trace which snapshot source was used for reconciliation
        if effective_snapshot:
            snapshot_source = "forwarded" if assignment_snapshot else "persisted_redis"
            logger.info(
                "image_assignment_reused_for_reconcile",
                extra={
                    "conversation_id": conversation_id,
                    "snapshot_source": snapshot_source,
                    "case_id": effective_snapshot.get("case_id"),
                    "element_code": effective_snapshot.get("element_code"),
                    "in_image_collection_mode": effective_snapshot.get(
                        "in_image_collection_mode"
                    ),
                },
            )

        mode_context = None
        if effective_snapshot:
            mode_context = effective_snapshot.get("mode_context")
        if mode_context is None:
            mode_context = await get_mode_context_from_checkpoint(
                checkpointer, conversation_id
            )

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
        upload_batch_id = (
            effective_snapshot.get("upload_batch_id") if effective_snapshot else None
        )
        upload_scope_key = (
            effective_snapshot.get("upload_scope_key") if effective_snapshot else None
        )

        # ── V2: Orphan reassignment guard (REQ-IMG-4) ─────────────────────
        # If EXPEDIENTE_V2_ENABLED and element_code is set, verify that there
        # are actually element-filtered images in DB.  When count=0 but the
        # case-level count>0 it means images were saved with element_code=None
        # (orphan).  Log a warning and continue — reconcile_conversation_images
        # will re-save missing images from Chatwoot with the correct code.
        _reconcile_settings = get_settings()
        if _reconcile_settings.EXPEDIENTE_V2_ENABLED and element_code:
            try:
                from agent.services.element_state_service import (
                    get_element_state_service as _get_ess,
                )

                _ess = _get_ess()
                _element_filtered_count = await _ess.get_element_photo_count(
                    case_id, element_code
                )
                if _element_filtered_count == 0:
                    # Check case-level count (element_code=None includes all images)
                    _case_level_count = await get_case_image_count(case_id)
                    if _case_level_count > 0:
                        logger.warning(
                            "image_handling.orphan_images_detected",
                            extra={
                                "conversation_id": conversation_id,
                                "case_id": case_id,
                                "element_code": element_code,
                                "element_filtered_count": _element_filtered_count,
                                "case_level_count": _case_level_count,
                                "action": "reconcile_will_reassign_from_chatwoot",
                            },
                        )
            except Exception as _orphan_err:
                logger.warning(
                    "image_handling.orphan_check_failed",
                    extra={
                        "conversation_id": conversation_id,
                        "case_id": case_id,
                        "error": str(_orphan_err),
                    },
                )

        # Get case_created_at for filtering
        case_created_at = None
        try:
            async with get_async_session() as session:
                case_obj = await session.get(Case, uuid_mod.UUID(case_id))
                if case_obj and case_obj.created_at:
                    case_created_at = case_obj.created_at.timestamp()
        except Exception as e:
            logger.warning(
                f"Completion reconciliation: could not get case created_at: {e}"
            )

        # Read confirmed count from batch confirmation
        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
        final_data = await redis_client.hgetall(final_key)
        final_batch_id = final_data.get(
            "upload_batch_id", final_data.get(b"upload_batch_id", b"")
        )
        if isinstance(final_batch_id, bytes):
            final_batch_id = final_batch_id.decode("utf-8")
        confirmed_total = 0
        if (
            not upload_batch_id
            or not final_batch_id
            or final_batch_id == upload_batch_id
        ):
            confirmed_total = int(
                final_data.get("confirmed_count", final_data.get(b"confirmed_count", 0))
            )

        current_count = await get_scoped_case_image_count(case_id, upload_batch_id)

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
            upload_batch_id=upload_batch_id,
            upload_scope_key=upload_scope_key,
        )

        if reconciled > 0:
            logger.info(
                f"Completion reconciliation pass 1: recovered {reconciled} images",
                extra={"conversation_id": conversation_id},
            )

        # Check if still missing images
        new_count = await get_scoped_case_image_count(case_id, upload_batch_id)
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
                upload_batch_id=upload_batch_id,
                upload_scope_key=upload_scope_key,
            )
            if retry_reconciled > 0:
                logger.info(
                    f"Completion reconciliation pass 2: recovered {retry_reconciled} more",
                    extra={"conversation_id": conversation_id},
                )

        final_count = await get_scoped_case_image_count(case_id, upload_batch_id)
        await get_case_image_batch_service().mark_reconciled(upload_batch_id)
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
                        last_update = float(
                            data.get(b"last_update", data.get("last_update", 0))
                        )
                        user_phone = data.get(
                            b"user_phone", data.get("user_phone", b"")
                        )
                        if isinstance(user_phone, bytes):
                            user_phone = user_phone.decode("utf-8")
                        # Read failed_reasons from the batch hash (JSON-encoded list)
                        _batch_failed_reasons: list[str] = []
                        _raw_reasons = data.get(b"failed_reasons", data.get("failed_reasons", ""))
                        if isinstance(_raw_reasons, bytes):
                            _raw_reasons = _raw_reasons.decode("utf-8")
                        if _raw_reasons:
                            try:
                                _batch_failed_reasons = json.loads(_raw_reasons)
                            except (json.JSONDecodeError, TypeError):
                                _batch_failed_reasons = []

                        # Check if batch is ready for confirmation
                        elapsed = time.time() - last_update
                        if elapsed < IMAGE_BATCH_TIMEOUT_SECONDS:
                            continue

                        # Extract conversation_id from key.
                        # New-format keys store conversation_id in the hash to avoid
                        # key-name parsing (key now has scope suffix).
                        # Legacy keys fall back to key-name parsing.
                        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                        conversation_id = _extract_conversation_id_from_batch(key_str, data)

                        # Detect legacy vs new format for logging
                        _is_legacy = _is_legacy_batch_key(data)
                        if _is_legacy:
                            logger.debug(
                                "processing_legacy_batch_key",
                                extra={
                                    "key": key_str,
                                    "conversation_id": conversation_id,
                                },
                            )

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
                        assignment_snapshot = await get_assignment_snapshot(
                            client, conversation_id
                        )
                        element_code = None
                        if assignment_snapshot and assignment_snapshot.get(
                            "in_image_collection_mode"
                        ):
                            element_code = assignment_snapshot.get("element_code")
                        upload_batch_id = None
                        upload_scope_key = None
                        if assignment_snapshot:
                            upload_batch_id = assignment_snapshot.get("upload_batch_id")
                            upload_scope_key = assignment_snapshot.get(
                                "upload_scope_key"
                            )

                        # Get case_id from snapshot, batch hash, or mode_context
                        case_id = (
                            assignment_snapshot.get("case_id")
                            if assignment_snapshot
                            else None
                        )
                        case_id_raw = data.get(b"case_id", data.get("case_id", b""))
                        if isinstance(case_id_raw, bytes):
                            case_id_raw = case_id_raw.decode("utf-8")
                        if not case_id:
                            case_id = case_id_raw or None
                        if not upload_batch_id:
                            batch_id_raw = data.get(
                                b"upload_batch_id", data.get("upload_batch_id", b"")
                            )
                            if isinstance(batch_id_raw, bytes):
                                batch_id_raw = batch_id_raw.decode("utf-8")
                            upload_batch_id = batch_id_raw or None
                        if not upload_scope_key:
                            scope_raw = data.get(
                                b"upload_scope_key", data.get("upload_scope_key", b"")
                            )
                            if isinstance(scope_raw, bytes):
                                scope_raw = scope_raw.decode("utf-8")
                            upload_scope_key = scope_raw or None

                        if not case_id and checkpointer:
                            mode_context = await get_mode_context_from_checkpoint(
                                checkpointer,
                                conversation_id,
                            )
                            case_id = await get_case_id_from_mode_context(mode_context)

                        # RECONCILIATION before confirming
                        if case_id:
                            case_created_at = None
                            try:
                                async with get_async_session() as session:
                                    case_obj = await session.get(
                                        Case, uuid_mod.UUID(case_id)
                                    )
                                    if case_obj and case_obj.created_at:
                                        case_created_at = (
                                            case_obj.created_at.timestamp()
                                        )
                            except Exception as e:
                                logger.warning(f"Could not get case created_at: {e}")

                            (
                                reconciled,
                                recon_failed,
                            ) = await reconcile_conversation_images(
                                conversation_id=conversation_id,
                                case_id=case_id,
                                case_created_at=case_created_at,
                                element_code=element_code,
                                upload_batch_id=upload_batch_id,
                                upload_scope_key=upload_scope_key,
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
                                (
                                    retry_reconciled,
                                    retry_failed,
                                ) = await reconcile_conversation_images(
                                    conversation_id=conversation_id,
                                    case_id=case_id,
                                    case_created_at=case_created_at,
                                    element_code=element_code,
                                    upload_batch_id=upload_batch_id,
                                    upload_scope_key=upload_scope_key,
                                )
                                if retry_reconciled > 0:
                                    count += retry_reconciled
                                if retry_failed > 0:
                                    failed += retry_failed

                        # Get total images from DB after reconciliation
                        total_images = 0
                        if case_id:
                            total_images = await get_scoped_case_image_count(
                                case_id,
                                upload_batch_id,
                            )

                        # Check finalize lock: if the main loop already detected "listo"
                        # (set finalize_lock:{conversation_id}[:{element_code}]), suppress
                        # the CTA message to avoid contradicting the user who already wrote
                        # "listo". Lock is scoped by element_code so ELEMENT_1's lock
                        # never blocks ELEMENT_2's CTA.
                        finalize_lock_key = (
                            f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
                            f":{element_code}"
                            if element_code
                            else f"{IMAGE_FINALIZE_LOCK_PREFIX}{conversation_id}"
                        )
                        finalize_locked = False
                        try:
                            finalize_locked = bool(
                                await client.exists(finalize_lock_key)
                            )
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
                            # Resolve element display name from assignment snapshot.
                            # This enriches the CTA with the element's human-readable name.
                            _element_display_name: str | None = None
                            _is_base_docs = False
                            if assignment_snapshot:
                                _element_display_name = assignment_snapshot.get(
                                    "element_display_name"
                                )
                                _sub_mode = assignment_snapshot.get("expediente_sub_mode", "")
                                _is_base_docs = _sub_mode == "collect_base_docs"

                            # Build scope-aware CTA message
                            message = _build_worker_cta_message(
                                count=count,
                                failed=failed,
                                total_images=total_images,
                                element_display_name=_element_display_name,
                                is_base_docs=_is_base_docs,
                                is_orphan=not bool(case_id),
                                failed_reasons=_batch_failed_reasons or None,
                            )

                            if message:
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
                            else:
                                logger.info(
                                    "worker_cta_suppressed_orphan_batch",
                                    extra={"conversation_id": conversation_id},
                                )

                        # Store confirmed count for reconcile_on_completion
                        final_key = f"{IMAGE_BATCH_FINAL_PREFIX}{conversation_id}"
                        try:
                            await client.hset(
                                final_key,
                                mapping={
                                    "confirmed_count": str(count),
                                    "total_images": str(total_images),
                                    "case_id": case_id or "",
                                    "conversation_id": conversation_id,
                                    "upload_batch_id": upload_batch_id or "",
                                    "upload_scope_key": upload_scope_key or "",
                                },
                            )
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
