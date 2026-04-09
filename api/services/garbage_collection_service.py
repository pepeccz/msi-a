"""
MSI Automotive - Garbage Collection Service.

Deletes stale ConversationHistory records (and their cascade messages) older
than *retention_days*, and removes orphaned case-image directories whose
corresponding Case no longer exists in the database.

Design rules:
- NEVER raises — all errors are logged and partial results are returned.
- All deletes are guarded by *dry_run=True* by default.
- Uses structlog for all output.
"""

__all__ = ["GCResult", "run_gc"]

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Case, ConversationHistory, ConversationMessage
from shared.config import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class GCResult:
    """Outcome of a single garbage-collection run."""

    conversations_deleted: int = 0
    messages_deleted: int = 0
    images_deleted: int = 0
    dry_run: bool = True
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


async def run_gc(
    session: AsyncSession,
    retention_days: int = 90,
    dry_run: bool = True,
) -> GCResult:
    """
    Run garbage collection for old conversation records and orphaned images.

    Args:
        session:        SQLAlchemy async session (caller owns commit/rollback).
        retention_days: Delete ConversationHistory records whose *started_at*
                        is older than this many days.
        dry_run:        When True, only counts — no records are deleted.

    Returns:
        GCResult with counts and timing.
    """
    started = time.monotonic()
    result = GCResult(dry_run=dry_run)

    log = logger.bind(retention_days=retention_days, dry_run=dry_run)
    log.info("gc.run_start")

    # ------------------------------------------------------------------
    # 1. Old ConversationHistory records
    # ------------------------------------------------------------------
    try:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        # Gather IDs of conversations to delete
        stmt = select(ConversationHistory.id).where(
            ConversationHistory.started_at < cutoff
        )
        rows = await session.execute(stmt)
        conv_ids: list[uuid.UUID] = [r[0] for r in rows]

        if conv_ids:
            # Count associated messages first
            msg_count_result = await session.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.conversation_history_id.in_(conv_ids)
                )
            )
            result.messages_deleted = int(msg_count_result or 0)
            result.conversations_deleted = len(conv_ids)

            if not dry_run:
                await session.execute(
                    delete(ConversationHistory).where(
                        ConversationHistory.id.in_(conv_ids)
                    )
                )
                await session.commit()
                log.info(
                    "gc.conversations_deleted",
                    count=result.conversations_deleted,
                    messages=result.messages_deleted,
                )
            else:
                log.info(
                    "gc.dry_run_would_delete",
                    conversations=result.conversations_deleted,
                    messages=result.messages_deleted,
                )
        else:
            log.info("gc.no_old_conversations")

    except Exception as exc:  # noqa: BLE001
        msg = f"gc.conversations error: {exc}"
        result.errors.append(msg)
        log.error("gc.conversations_error", error=str(exc))

    # ------------------------------------------------------------------
    # 2. Orphaned case-image directories
    # ------------------------------------------------------------------
    try:
        settings = get_settings()
        case_images_dir = Path(settings.CASE_IMAGES_DIR)

        if not case_images_dir.exists():
            log.info("gc.case_images_dir_missing", path=str(case_images_dir))
        else:
            # Fetch all existing case IDs from DB
            existing_ids_result = await session.execute(select(Case.id))
            existing_case_ids: set[str] = {
                str(r[0]) for r in existing_ids_result
            }

            for subdir in case_images_dir.iterdir():
                if not subdir.is_dir():
                    continue

                dir_name = subdir.name

                if dir_name not in existing_case_ids:
                    # Orphaned directory
                    file_count = sum(1 for f in subdir.rglob("*") if f.is_file())
                    result.images_deleted += file_count

                    if not dry_run:
                        import shutil

                        try:
                            shutil.rmtree(subdir)
                            log.info(
                                "gc.orphaned_dir_deleted",
                                path=str(subdir),
                                files=file_count,
                            )
                        except Exception as rm_exc:  # noqa: BLE001
                            msg = f"gc.rmtree error for {subdir}: {rm_exc}"
                            result.errors.append(msg)
                            log.error(
                                "gc.rmtree_error",
                                path=str(subdir),
                                error=str(rm_exc),
                            )
                    else:
                        log.info(
                            "gc.dry_run_would_delete_dir",
                            path=str(subdir),
                            files=file_count,
                        )

    except Exception as exc:  # noqa: BLE001
        msg = f"gc.images error: {exc}"
        result.errors.append(msg)
        log.error("gc.images_error", error=str(exc))

    result.duration_seconds = round(time.monotonic() - started, 3)
    log.info(
        "gc.run_complete",
        conversations_deleted=result.conversations_deleted,
        messages_deleted=result.messages_deleted,
        images_deleted=result.images_deleted,
        duration_seconds=result.duration_seconds,
        errors=len(result.errors),
    )
    return result
