"""Persisted upload batch ownership for expediente images."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

import structlog
from sqlalchemy import or_, select

from database.connection import get_async_session
from database.models import CaseImageUploadBatch

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class UploadScope:
    """Canonical expediente upload scope derived from runtime state."""

    case_id: str
    expediente_sub_mode: str
    owner_scope: str
    owner_element_code: str | None
    upload_scope_key: str


@dataclass(frozen=True)
class UploadBatchResolution:
    """Resolved persisted batch for one image or completion event."""

    batch_id: str
    upload_scope_key: str
    owner_element_code: str | None
    owner_scope: str
    status: str
    is_historical: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_message_created_at(message_created_at: int | float | None) -> datetime | None:
    if message_created_at is None:
        return None
    try:
        return datetime.fromtimestamp(float(message_created_at), UTC)
    except (TypeError, ValueError, OSError):
        return None


def build_upload_scope(
    *,
    case_id: str | None,
    expediente_sub_mode: str | None,
    element_code: str | None,
) -> UploadScope | None:
    """Build a canonical upload scope from expediente runtime context."""
    if not case_id or not expediente_sub_mode:
        return None

    if expediente_sub_mode == "collect_element_data" and element_code:
        owner_scope = "element_photo"
        scope_subject = f"element:{element_code}"
    elif expediente_sub_mode == "collect_base_docs":
        owner_scope = "base_documentation"
        scope_subject = "base_docs"
        element_code = None
    else:
        return None

    return UploadScope(
        case_id=case_id,
        expediente_sub_mode=expediente_sub_mode,
        owner_scope=owner_scope,
        owner_element_code=element_code,
        upload_scope_key=(
            f"case:{case_id}:sub_mode:{expediente_sub_mode}:scope:{scope_subject}"
        ),
    )


class CaseImageBatchService:
    """DB-backed lifecycle manager for expediente upload batches."""

    async def resolve_for_snapshot(
        self,
        *,
        assignment_snapshot: dict | None,
        allow_create: bool,
        message_created_at: int | float | None = None,
    ) -> UploadBatchResolution | None:
        if not assignment_snapshot:
            return None

        scope = build_upload_scope(
            case_id=assignment_snapshot.get("case_id"),
            expediente_sub_mode=assignment_snapshot.get("expediente_sub_mode"),
            element_code=assignment_snapshot.get("element_code"),
        )
        if not scope:
            return None

        return await self.resolve_for_scope(
            scope,
            allow_create=allow_create,
            message_created_at=message_created_at,
        )

    async def resolve_for_scope(
        self,
        scope: UploadScope,
        *,
        allow_create: bool,
        message_created_at: int | float | None = None,
    ) -> UploadBatchResolution | None:
        message_dt = _normalize_message_created_at(message_created_at)

        async with get_async_session() as session:
            if message_dt is not None:
                historical = await session.execute(
                    select(CaseImageUploadBatch)
                    .where(CaseImageUploadBatch.case_id == uuid.UUID(scope.case_id))
                    .where(CaseImageUploadBatch.opened_at <= message_dt)
                    .where(
                        or_(
                            CaseImageUploadBatch.finalized_at.is_(None),
                            CaseImageUploadBatch.finalized_at >= message_dt,
                        )
                    )
                    .order_by(CaseImageUploadBatch.opened_at.desc())
                    .limit(1)
                )
                historical_batch = historical.scalar_one_or_none()
                if historical_batch and historical_batch.upload_scope_key != scope.upload_scope_key:
                    return UploadBatchResolution(
                        batch_id=historical_batch.batch_id,
                        upload_scope_key=historical_batch.upload_scope_key,
                        owner_element_code=historical_batch.owner_element_code,
                        owner_scope=historical_batch.owner_scope,
                        status=historical_batch.status,
                        is_historical=True,
                    )

            current = await session.execute(
                select(CaseImageUploadBatch)
                .where(CaseImageUploadBatch.case_id == uuid.UUID(scope.case_id))
                .where(CaseImageUploadBatch.upload_scope_key == scope.upload_scope_key)
                .where(CaseImageUploadBatch.finalized_at.is_(None))
                .order_by(CaseImageUploadBatch.opened_at.desc())
                .limit(1)
            )
            current_batch = current.scalar_one_or_none()
            if current_batch:
                current_batch.last_activity_at = _utc_now()
                await session.commit()
                return UploadBatchResolution(
                    batch_id=current_batch.batch_id,
                    upload_scope_key=current_batch.upload_scope_key,
                    owner_element_code=current_batch.owner_element_code,
                    owner_scope=current_batch.owner_scope,
                    status=current_batch.status,
                )

            if not allow_create:
                return None

            batch = CaseImageUploadBatch(
                batch_id=str(uuid.uuid4()),
                case_id=uuid.UUID(scope.case_id),
                upload_scope_key=scope.upload_scope_key,
                owner_scope=scope.owner_scope,
                owner_element_code=scope.owner_element_code,
                expediente_sub_mode=scope.expediente_sub_mode,
                status="open",
                opened_at=message_dt or _utc_now(),
                last_activity_at=_utc_now(),
            )
            session.add(batch)
            await session.commit()
            return UploadBatchResolution(
                batch_id=batch.batch_id,
                upload_scope_key=batch.upload_scope_key,
                owner_element_code=batch.owner_element_code,
                owner_scope=batch.owner_scope,
                status=batch.status,
            )

    async def open_for_scope(
        self,
        *,
        case_id: str,
        expediente_sub_mode: str,
        element_code: str | None,
        opened_at: datetime | None = None,
    ) -> UploadBatchResolution | None:
        scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode=expediente_sub_mode,
            element_code=element_code,
        )
        if not scope:
            return None
        if opened_at is not None:
            timestamp = int(opened_at.timestamp())
        else:
            timestamp = None
        return await self.resolve_for_scope(
            scope,
            allow_create=True,
            message_created_at=timestamp,
        )

    async def finalize_for_scope(
        self,
        *,
        case_id: str,
        expediente_sub_mode: str,
        element_code: str | None,
        status: str,
    ) -> str | None:
        scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode=expediente_sub_mode,
            element_code=element_code,
        )
        if not scope:
            return None

        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImageUploadBatch)
                .where(CaseImageUploadBatch.case_id == uuid.UUID(case_id))
                .where(CaseImageUploadBatch.upload_scope_key == scope.upload_scope_key)
                .where(CaseImageUploadBatch.finalized_at.is_(None))
                .order_by(CaseImageUploadBatch.opened_at.desc())
                .limit(1)
            )
            batch = result.scalar_one_or_none()
            if not batch:
                return None
            now = _utc_now()
            batch.status = status
            batch.finalized_at = now
            batch.last_activity_at = now
            await session.commit()
            return batch.batch_id

    async def resolve_batch_for_timestamp(
        self,
        *,
        case_id: str,
        message_created_at: int | float,
    ) -> UploadBatchResolution | None:
        """
        Resolve which upload batch owned a specific message timestamp.

        Unlike ``resolve_for_scope``, this method does NOT require a caller-
        supplied scope — it looks up any batch for the case whose open/close
        window contains the given timestamp.  Used exclusively by
        ``reconcile_conversation_images`` so that recovered historical images
        are attributed to the batch that was open *when they were originally
        sent*, rather than to whatever batch is currently active.

        Returns:
            - The matching ``UploadBatchResolution`` (with ``is_historical=True``
              when the batch is already finalized), or
            - ``None`` when no batch window covers the timestamp (caller must
              route to orphan/unmatched batch).
        """
        message_dt = _normalize_message_created_at(message_created_at)
        if message_dt is None:
            return None

        try:
            case_uuid = uuid.UUID(case_id)
        except (ValueError, AttributeError):
            return None

        async with get_async_session() as session:
            # Primary: find a batch whose open-to-finalized window covers the
            # message timestamp (handles finalized historical batches).
            result = await session.execute(
                select(CaseImageUploadBatch)
                .where(CaseImageUploadBatch.case_id == case_uuid)
                .where(CaseImageUploadBatch.opened_at <= message_dt)
                .where(
                    or_(
                        CaseImageUploadBatch.finalized_at.is_(None),
                        CaseImageUploadBatch.finalized_at >= message_dt,
                    )
                )
                .order_by(CaseImageUploadBatch.opened_at.desc())
                .limit(1)
            )
            batch = result.scalar_one_or_none()
            if batch is None:
                return None

            is_historical = batch.finalized_at is not None
            return UploadBatchResolution(
                batch_id=batch.batch_id,
                upload_scope_key=batch.upload_scope_key,
                owner_element_code=batch.owner_element_code,
                owner_scope=batch.owner_scope,
                status=batch.status,
                is_historical=is_historical,
            )

    async def get_or_create_orphan_batch(
        self,
        *,
        case_id: str,
    ) -> UploadBatchResolution:
        """
        Return (or lazily create) a case-level orphan/unmatched batch.

        Images recovered during reconciliation that do not fall within any
        known batch window are assigned to this batch so they are not lost and
        do not contaminate element-scoped counts.

        The orphan batch uses a deterministic ``upload_scope_key`` so it is
        idempotent across reconciliation runs.
        """
        orphan_scope_key = f"case:{case_id}:reconciliation:orphan"

        try:
            case_uuid = uuid.UUID(case_id)
        except (ValueError, AttributeError):
            # Fallback: generate a transient result without DB persistence.
            fallback_batch_id = str(uuid.uuid4())
            return UploadBatchResolution(
                batch_id=fallback_batch_id,
                upload_scope_key=orphan_scope_key,
                owner_element_code=None,
                owner_scope="orphan",
                status="open",
            )

        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImageUploadBatch)
                .where(CaseImageUploadBatch.case_id == case_uuid)
                .where(CaseImageUploadBatch.upload_scope_key == orphan_scope_key)
                .order_by(CaseImageUploadBatch.opened_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return UploadBatchResolution(
                    batch_id=existing.batch_id,
                    upload_scope_key=existing.upload_scope_key,
                    owner_element_code=existing.owner_element_code,
                    owner_scope=existing.owner_scope,
                    status=existing.status,
                    is_historical=existing.finalized_at is not None,
                )

            # Create orphan batch
            now = _utc_now()
            batch = CaseImageUploadBatch(
                batch_id=str(uuid.uuid4()),
                case_id=case_uuid,
                upload_scope_key=orphan_scope_key,
                owner_scope="orphan",
                owner_element_code=None,
                expediente_sub_mode=None,
                status="open",
                opened_at=now,
                last_activity_at=now,
            )
            session.add(batch)
            await session.commit()
            return UploadBatchResolution(
                batch_id=batch.batch_id,
                upload_scope_key=batch.upload_scope_key,
                owner_element_code=batch.owner_element_code,
                owner_scope=batch.owner_scope,
                status=batch.status,
            )

    async def mark_reconciled(self, batch_id: str | None) -> None:
        if not batch_id:
            return

        async with get_async_session() as session:
            result = await session.execute(
                select(CaseImageUploadBatch)
                .where(CaseImageUploadBatch.batch_id == batch_id)
                .limit(1)
            )
            batch = result.scalar_one_or_none()
            if not batch:
                return
            now = _utc_now()
            batch.status = "reconciled" if batch.finalized_at else batch.status
            batch.last_reconciled_at = now
            batch.last_activity_at = now
            await session.commit()


@lru_cache
def get_case_image_batch_service() -> CaseImageBatchService:
    return CaseImageBatchService()
