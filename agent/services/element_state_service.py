"""
MSI Automotive - Element State Service (EXPEDIENTE_MODE v2).

Single source of truth for reading/writing per-element collection state
during EXPEDIENTE_MODE. Backed exclusively by CaseElementData and CaseImage
DB records — no ContextVar or mode_context ephemeral dict usage.

Design principles:
- AI DATA-GIVEN: all field definitions come from ElementRequiredField DB
- LLM-DRIVEN: service returns structured context; LLM decides the flow
- NO HARDCODING: element codes, field keys, and ordering come from the DB
- REESCALABLE: adding elements/fields in DB automatically works here
- Feature flag: all v2 logic gated behind EXPEDIENTE_V2_ENABLED

Feature flag:
    This module is always importable but raises FeatureFlagDisabledError
    if EXPEDIENTE_V2_ENABLED=False is detected at call time.  Callers
    (expediente_mode.py) are expected to check the flag before calling.

Spec domain: agent/element-state-management
Relevant requirements:
    REQ-STATE-1  CaseElementData is single source of truth
    REQ-STATE-2  Transitions driven by DB completeness
    REQ-STATE-3  No ContextVar usage
    REQ-STATE-4  Service generates CollectionContext for prompt injection
    REQ-STATE-5  Element ordering from DB (not hardcoded)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from functools import lru_cache
from typing import Any, Literal

import structlog
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import (
    CaseElementData,
    CaseImage,
    Element,
    ElementRequiredField,
    Warning,
)
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ElementPhase = Literal["photos", "data", "completed"]
ElementStatusStr = Literal["pending_photos", "pending_data", "completed"]


# ---------------------------------------------------------------------------
# Data classes for structured context (REQ-STATE-4)
# ---------------------------------------------------------------------------


@dataclass
class FieldContext:
    """Structured info about a single required field."""

    field_key: str
    field_label: str
    field_type: str
    is_required: bool
    current_value: Any | None = None
    is_collected: bool = False
    options: list[str] | None = None
    example_value: str | None = None
    llm_instruction: str | None = None
    validation_rules: dict[str, Any] | None = None
    has_condition: bool = False
    condition_depends_on: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for JSON injection."""
        out: dict[str, Any] = {
            "field_key": self.field_key,
            "field_label": self.field_label,
            "field_type": self.field_type,
            "is_required": self.is_required,
            "current_value": self.current_value,
            "is_collected": self.is_collected,
        }
        if self.options:
            out["options"] = self.options
        if self.example_value:
            out["example"] = self.example_value
        if self.llm_instruction:
            out["instruction"] = self.llm_instruction
        if self.validation_rules:
            out["validation"] = self.validation_rules
        if self.has_condition and self.condition_depends_on:
            out["condition"] = {"depends_on": self.condition_depends_on}
        return out


@dataclass
class ElementState:
    """
    Current state of a single element's data collection.

    Derived exclusively from DB records (CaseElementData + CaseImage).
    """

    element_code: str
    display_name: str
    db_status: ElementStatusStr  # raw DB status field
    phase: ElementPhase  # derived: "photos" | "data" | "completed"
    photos_required: bool  # element has images to send (example images)
    photos_confirmed_count: int  # CaseImage rows for this element
    field_values: dict[str, Any]  # CaseElementData.field_values
    all_fields: list[FieldContext]  # all applicable required fields
    pending_fields: list[FieldContext]  # fields not yet collected
    warnings: list[dict[str, Any]]  # element warnings from DB
    photos_completed_at: datetime | None = (
        None  # when photos were confirmed (None = not yet confirmed)
    )

    @property
    def is_completed(self) -> bool:
        return self.db_status == "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.element_code,
            "display_name": self.display_name,
            "phase": self.phase,
            "db_status": self.db_status,
            "photos_required": self.photos_required,
            "photos_confirmed_count": self.photos_confirmed_count,
            "pending_fields": [f.to_dict() for f in self.pending_fields],
            "collected_fields": self.field_values,
            "warnings": self.warnings,
            "is_completed": self.is_completed,
        }


@dataclass
class CollectionContext:
    """
    Structured context injected into the system prompt.

    REQ-STATE-4: The service generates this; the LLM decides the flow.
    """

    current_element: dict[str, Any] | None
    all_elements: list[dict[str, Any]]
    progress: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_element": self.current_element,
            "all_elements": self.all_elements,
            "progress": self.progress,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """Coerce str or UUID to UUID, robust for both types."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _evaluate_field_condition(
    field: ElementRequiredField,
    collected_values: dict[str, Any],
    all_fields: list[ElementRequiredField],
) -> bool:
    """
    Return True if the field should be shown given the current collected_values.

    Respects condition_field_id / condition_operator / condition_value.
    If no condition is set, always returns True.
    Unknown operators default to True (show by default).
    """
    if not field.condition_field_id:
        return True

    # Find the condition anchor field
    condition_field = next(
        (f for f in all_fields if str(f.id) == str(field.condition_field_id)),
        None,
    )
    if not condition_field:
        logger.warning(
            "element_state_service.condition_field_not_found",
            field_key=field.field_key,
            condition_field_id=str(field.condition_field_id),
        )
        return True  # Show by default when anchor not found

    condition_value = collected_values.get(condition_field.field_key)
    operator = field.condition_operator or "equals"
    expected = field.condition_value

    if operator == "equals":
        if condition_value is None:
            return False
        return str(condition_value).lower() == str(expected).lower()
    elif operator == "not_equals":
        if condition_value is None:
            return True
        return str(condition_value).lower() != str(expected).lower()
    elif operator == "exists":
        return condition_value is not None and condition_value != ""
    elif operator == "not_exists":
        return condition_value is None or condition_value == ""

    return True  # Unknown operator — show by default


def _build_field_contexts(
    db_fields: list[ElementRequiredField],
    collected_values: dict[str, Any],
) -> tuple[list[FieldContext], list[FieldContext]]:
    """
    Build (all_applicable_fields, pending_fields) tuples.

    - all_applicable_fields: all fields that pass condition evaluation
    - pending_fields: subset where value not yet collected

    Ordering: respects ElementRequiredField.sort_order (REQ-STATE-5).
    """
    sorted_fields = sorted(db_fields, key=lambda f: f.sort_order)
    all_applicable: list[FieldContext] = []
    pending: list[FieldContext] = []

    for db_field in sorted_fields:
        # Skip inactive fields
        if not db_field.is_active:
            continue

        # Evaluate conditional display
        if not _evaluate_field_condition(db_field, collected_values, sorted_fields):
            continue

        # Find condition anchor field_key (for FieldContext)
        condition_depends_on: str | None = None
        if db_field.condition_field_id:
            anchor = next(
                (
                    f
                    for f in sorted_fields
                    if str(f.id) == str(db_field.condition_field_id)
                ),
                None,
            )
            if anchor:
                condition_depends_on = anchor.field_key

        ctx = FieldContext(
            field_key=db_field.field_key,
            field_label=db_field.field_label,
            field_type=db_field.field_type,
            is_required=db_field.is_required,
            current_value=collected_values.get(db_field.field_key),
            is_collected=db_field.field_key in collected_values,
            options=db_field.options,
            example_value=db_field.example_value,
            llm_instruction=db_field.llm_instruction,
            validation_rules=db_field.validation_rules,
            has_condition=bool(db_field.condition_field_id),
            condition_depends_on=condition_depends_on,
        )
        all_applicable.append(ctx)

        if not ctx.is_collected:
            pending.append(ctx)

    return all_applicable, pending


def _derive_phase(
    db_status: ElementStatusStr,
    db_fields: list[ElementRequiredField],
    collected_values: dict[str, Any],
) -> ElementPhase:
    """
    Derive the human-facing phase from DB state.

    - completed   → "completed"
    - pending_photos → "photos"
    - pending_data  → "data" (could also be "photos" if no fields)
    """
    if db_status == "completed":
        return "completed"
    if db_status == "pending_photos":
        return "photos"
    # pending_data
    # If there are no applicable required fields, treat as effectively completed
    # (the DB status update may be slightly behind)
    _, pending = _build_field_contexts(db_fields, collected_values)
    required_pending = [f for f in pending if f.is_required]
    if not required_pending:
        return "data"  # All required fields done, just not yet marked completed in DB
    return "data"


# ---------------------------------------------------------------------------
# ElementStateService
# ---------------------------------------------------------------------------


class ElementStateService:
    """
    EXPEDIENTE_MODE v2 element state service.

    All state comes from CaseElementData and CaseImage DB records.
    No ContextVar, no fsm_state, no mode_context reads.

    Feature-flagged: raises RuntimeError if called when
    EXPEDIENTE_V2_ENABLED is False (callers must check first).
    """

    # ------------------------------------------------------------------
    # Feature flag guard
    # ------------------------------------------------------------------

    def _require_v2_enabled(self) -> None:
        """Raise RuntimeError if the element state service feature flag is off.

        Agent Architecture Refactor T1.2b (AD-2): Guard now checks
        USE_ELEMENT_STATE_SERVICE instead of EXPEDIENTE_V2_ENABLED so that
        useful element state tracking can be enabled independently of the
        harmful EXPEDIENTE_TOOL_MATRIX (which is gated behind EXPEDIENTE_V2_ENABLED).
        """
        settings = get_settings()
        if not settings.USE_ELEMENT_STATE_SERVICE:
            raise RuntimeError(
                "ElementStateService requires USE_ELEMENT_STATE_SERVICE=True. "
                "Check the feature flag before calling."
            )

    # ------------------------------------------------------------------
    # Core read methods
    # ------------------------------------------------------------------

    async def get_element_state(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
        category_id: str | uuid.UUID | None = None,
    ) -> ElementState | None:
        """
        Load the full state for one element from the DB.

        Returns None if the element is not found in the DB (Element table).
        Creates CaseElementData automatically if it doesn't exist yet.

        Args:
            case_id: Case UUID (str or UUID)
            element_code: Element code (e.g. "ESCAPE")
            category_id: Optional category UUID for element lookup.  When
                omitted, the element name defaults to the element_code.

        Returns:
            ElementState or None
        """
        self._require_v2_enabled()

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                # ----- Load CaseElementData (create if missing) -----
                ced_result = await session.execute(
                    select(CaseElementData)
                    .where(CaseElementData.case_id == case_uuid)
                    .where(CaseElementData.element_code == element_code)
                )
                ced: CaseElementData | None = ced_result.scalar_one_or_none()

                if ced is None:
                    # Create fresh record
                    ced = CaseElementData(
                        case_id=case_uuid,
                        element_code=element_code,
                        status="pending_photos",
                        field_values={},
                    )
                    session.add(ced)
                    await session.commit()
                    await session.refresh(ced)
                    logger.info(
                        "element_state_service.ced_created",
                        case_id=str(case_uuid),
                        element_code=element_code,
                    )

                collected_values: dict[str, Any] = ced.field_values or {}
                db_status: ElementStatusStr = ced.status  # type: ignore[assignment]

                # ----- Load Element + required fields -----
                element_query = (
                    select(Element)
                    .where(Element.code == element_code)
                    .where(Element.is_active == True)  # noqa: E712
                    .options(
                        selectinload(Element.required_fields),
                    )
                )
                if category_id is not None:
                    element_query = element_query.where(
                        Element.category_id == _to_uuid(category_id)
                    )

                elem_result = await session.execute(element_query)
                element: Element | None = elem_result.scalar_one_or_none()

                display_name = element.name if element else element_code
                db_fields: list[ElementRequiredField] = (
                    element.required_fields if element else []
                )

                # ----- Load element warnings -----
                warnings_data: list[dict[str, Any]] = []
                if element:
                    warn_result = await session.execute(
                        select(Warning)
                        .where(Warning.element_id == element.id)
                        .where(Warning.is_active == True)  # noqa: E712
                    )
                    for w in warn_result.scalars().all():
                        warnings_data.append(
                            {
                                "code": w.code,
                                "message": w.message,
                                "severity": w.severity,
                            }
                        )

                # ----- Count element photos -----
                photo_count_result = await session.execute(
                    select(func.count(CaseImage.id))
                    .where(CaseImage.case_id == case_uuid)
                    .where(CaseImage.element_code == element_code)
                )
                photos_count: int = photo_count_result.scalar() or 0

                # ----- Build FieldContext lists -----
                all_fields, pending_fields = _build_field_contexts(
                    db_fields, collected_values
                )

                # ----- Derive phase -----
                phase = _derive_phase(db_status, db_fields, collected_values)

                # photos_required: True if element has example images (admin sets them),
                # which signals the agent to request them from the user.
                # We use whether the element has images in the element_images table
                # OR simply always require photos for elements (configurable in DB).
                # For now: photos_required = True when status starts at pending_photos
                # (i.e., always require photos unless explicitly skipped).
                photos_required = db_status in ("pending_photos",) or phase == "photos"

                return ElementState(
                    element_code=element_code,
                    display_name=display_name,
                    db_status=db_status,
                    phase=phase,
                    photos_required=photos_required,
                    photos_confirmed_count=photos_count,
                    field_values=collected_values,
                    all_fields=all_fields,
                    pending_fields=pending_fields,
                    warnings=warnings_data,
                    photos_completed_at=ced.photos_completed_at,
                )

        except Exception as exc:
            logger.error(
                "element_state_service.get_element_state_error",
                case_id=str(case_id),
                element_code=element_code,
                error=str(exc),
                exc_info=True,
            )
            return None

    async def get_collection_context(
        self,
        case_id: str | uuid.UUID,
        element_codes: list[str],
        category_id: str | uuid.UUID | None = None,
    ) -> CollectionContext:
        """
        Build a CollectionContext for prompt injection.

        REQ-STATE-4: structured dict used to populate the system prompt
        with the current element's phase, pending fields, progress, etc.

        Args:
            case_id: Case UUID
            element_codes: Ordered list of element codes (REQ-STATE-5)
            category_id: Optional category UUID for element name lookup

        Returns:
            CollectionContext (never raises — returns empty context on error)
        """
        self._require_v2_enabled()

        all_elements_summary: list[dict[str, Any]] = []
        current_element_dict: dict[str, Any] | None = None
        completed_count = 0

        for code in element_codes:
            state = await self.get_element_state(case_id, code, category_id)
            if state is None:
                # Fallback: treat as unknown
                all_elements_summary.append(
                    {
                        "code": code,
                        "display_name": code,
                        "status": "unknown",
                    }
                )
                continue

            status_label = (
                "completed"
                if state.is_completed
                else ("in_progress" if state.phase != "photos" else "pending")
            )
            all_elements_summary.append(
                {
                    "code": code,
                    "display_name": state.display_name,
                    "status": status_label,
                }
            )

            if state.is_completed:
                completed_count += 1

            # current = first non-completed element
            if current_element_dict is None and not state.is_completed:
                current_element_dict = state.to_dict()

        progress = {
            "completed": completed_count,
            "total": len(element_codes),
        }

        return CollectionContext(
            current_element=current_element_dict,
            all_elements=all_elements_summary,
            progress=progress,
        )

    async def get_current_element(
        self,
        case_id: str | uuid.UUID,
        element_codes: list[str],
    ) -> str | None:
        """
        Return the first element_code that is NOT completed.

        REQ-STATE-5: ordering follows element_codes list order (from DB/mode_context).

        Returns None if all elements are complete.
        """
        self._require_v2_enabled()

        for code in element_codes:
            state = await self.get_element_state(case_id, code)
            if state is not None and not state.is_completed:
                return code
        return None

    async def is_all_elements_complete(
        self,
        case_id: str | uuid.UUID,
        element_codes: list[str],
    ) -> bool:
        """
        Check if every element in element_codes is in 'completed' status.

        Returns True if element_codes is empty (vacuously complete).
        """
        self._require_v2_enabled()

        if not element_codes:
            return True

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(CaseElementData)
                    .where(CaseElementData.case_id == case_uuid)
                    .where(CaseElementData.element_code.in_(element_codes))
                )
                records = {r.element_code: r for r in result.scalars().all()}

            for code in element_codes:
                record = records.get(code)
                if record is None or record.status != "completed":
                    return False

            return True

        except Exception as exc:
            logger.error(
                "element_state_service.is_all_elements_complete_error",
                case_id=str(case_id),
                error=str(exc),
                exc_info=True,
            )
            return False  # Safe fallback: treat as incomplete

    async def get_pending_fields(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
        category_id: str | uuid.UUID | None = None,
    ) -> list[FieldContext]:
        """
        Return FieldContext list of fields not yet collected for element_code.

        Respects conditional field logic (REQ-STATE-2) and sort_order (REQ-STATE-5).
        Returns empty list on error (graceful fallback).
        """
        self._require_v2_enabled()

        state = await self.get_element_state(case_id, element_code, category_id)
        if state is None:
            return []
        return state.pending_fields

    async def get_element_photo_count(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
    ) -> int:
        """
        Return number of CaseImage rows associated with this case+element.

        Returns 0 on error (graceful fallback).
        """
        self._require_v2_enabled()

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(func.count(CaseImage.id))
                    .where(CaseImage.case_id == case_uuid)
                    .where(CaseImage.element_code == element_code)
                )
                return result.scalar() or 0

        except Exception as exc:
            logger.error(
                "element_state_service.get_photo_count_error",
                case_id=str(case_id),
                element_code=element_code,
                error=str(exc),
                exc_info=True,
            )
            return 0

    # ------------------------------------------------------------------
    # Write / mutation methods
    # ------------------------------------------------------------------

    async def record_photos_confirmed(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
        photo_count: int,
    ) -> None:
        """
        Advance element status from pending_photos → pending_data (or completed).

        If the element has no required fields, it goes directly to 'completed'.
        Uses photos_completed_at timestamp.

        Args:
            case_id: Case UUID
            element_code: Element code
            photo_count: Number of photos received (informational, stored context)
        """
        self._require_v2_enabled()

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                # Load CaseElementData
                ced_result = await session.execute(
                    select(CaseElementData)
                    .where(CaseElementData.case_id == case_uuid)
                    .where(CaseElementData.element_code == element_code)
                )
                ced: CaseElementData | None = ced_result.scalar_one_or_none()

                if ced is None:
                    # Create with photos already confirmed
                    ced = CaseElementData(
                        case_id=case_uuid,
                        element_code=element_code,
                        status="pending_photos",
                        field_values={},
                    )
                    session.add(ced)
                    await session.flush()

                if ced.status == "completed":
                    # Idempotent: already completed, nothing to do
                    logger.info(
                        "element_state_service.record_photos_confirmed_idempotent",
                        case_id=str(case_uuid),
                        element_code=element_code,
                    )
                    return

                # Check if element has required fields to determine next status
                # We look up Element to check required_fields
                elem_result = await session.execute(
                    select(Element)
                    .where(Element.code == element_code)
                    .where(Element.is_active == True)  # noqa: E712
                    .options(selectinload(Element.required_fields))
                )
                element = elem_result.scalar_one_or_none()
                has_required_fields = bool(element and element.required_fields)

                new_status: ElementStatusStr = (
                    "pending_data" if has_required_fields else "completed"
                )

                ced.status = new_status
                ced.photos_completed_at = datetime.now(UTC)
                ced.updated_at = datetime.now(UTC)

                await session.commit()

                logger.info(
                    "element_state_service.photos_confirmed",
                    case_id=str(case_uuid),
                    element_code=element_code,
                    photo_count=photo_count,
                    new_status=new_status,
                    has_required_fields=has_required_fields,
                )

        except Exception as exc:
            logger.error(
                "element_state_service.record_photos_confirmed_error",
                case_id=str(case_id),
                element_code=element_code,
                error=str(exc),
                exc_info=True,
            )
            # Graceful fallback: do not raise to caller

    async def record_field_value(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
        field_key: str,
        value: Any,
    ) -> None:
        """
        Persist a single field value for an element.

        Merges into the existing field_values JSONB dict (upsert semantics).
        Does NOT validate the value — callers should validate before calling.

        Args:
            case_id: Case UUID
            element_code: Element code
            field_key: Field key (from ElementRequiredField.field_key)
            value: Field value to store
        """
        self._require_v2_enabled()

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                ced_result = await session.execute(
                    select(CaseElementData)
                    .where(CaseElementData.case_id == case_uuid)
                    .where(CaseElementData.element_code == element_code)
                )
                ced: CaseElementData | None = ced_result.scalar_one_or_none()

                if ced is None:
                    ced = CaseElementData(
                        case_id=case_uuid,
                        element_code=element_code,
                        status="pending_data",
                        field_values={},
                    )
                    session.add(ced)
                    await session.flush()

                # Merge value into JSONB dict
                current_values = dict(ced.field_values or {})
                current_values[field_key] = value
                ced.field_values = current_values
                ced.updated_at = datetime.now(UTC)

                await session.commit()

                logger.info(
                    "element_state_service.field_value_recorded",
                    case_id=str(case_uuid),
                    element_code=element_code,
                    field_key=field_key,
                )

        except Exception as exc:
            logger.error(
                "element_state_service.record_field_value_error",
                case_id=str(case_id),
                element_code=element_code,
                field_key=field_key,
                error=str(exc),
                exc_info=True,
            )
            # Graceful fallback: do not raise to caller

    async def mark_element_complete(
        self,
        case_id: str | uuid.UUID,
        element_code: str,
    ) -> None:
        """
        Set CaseElementData.status = 'completed' and stamp data_completed_at.

        Idempotent: safe to call multiple times.

        Args:
            case_id: Case UUID
            element_code: Element code
        """
        self._require_v2_enabled()

        case_uuid = _to_uuid(case_id)

        try:
            async with get_async_session() as session:
                ced_result = await session.execute(
                    select(CaseElementData)
                    .where(CaseElementData.case_id == case_uuid)
                    .where(CaseElementData.element_code == element_code)
                )
                ced: CaseElementData | None = ced_result.scalar_one_or_none()

                if ced is None:
                    logger.warning(
                        "element_state_service.mark_complete_no_record",
                        case_id=str(case_uuid),
                        element_code=element_code,
                    )
                    return

                if ced.status == "completed":
                    # Already complete — idempotent
                    return

                ced.status = "completed"
                ced.data_completed_at = datetime.now(UTC)
                ced.updated_at = datetime.now(UTC)

                await session.commit()

                logger.info(
                    "element_state_service.element_marked_complete",
                    case_id=str(case_uuid),
                    element_code=element_code,
                )

        except Exception as exc:
            logger.error(
                "element_state_service.mark_element_complete_error",
                case_id=str(case_id),
                element_code=element_code,
                error=str(exc),
                exc_info=True,
            )
            # Graceful fallback: do not raise to caller

    async def advance_to_next_element(
        self,
        case_id: str | uuid.UUID,
        element_codes: list[str],
    ) -> str | None:
        """
        Return the next non-completed element after marking the current one done.

        Equivalent to get_current_element() — it finds the first non-completed
        element in element_codes.  Callers should call mark_element_complete()
        before calling this to advance correctly.

        Args:
            case_id: Case UUID
            element_codes: Ordered list of element codes

        Returns:
            Next element code, or None if all complete
        """
        self._require_v2_enabled()

        return await self.get_current_element(case_id, element_codes)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_element_state_service() -> ElementStateService:
    """
    Return the singleton ElementStateService instance.

    Uses lru_cache so the same object is reused across calls.
    Thread-safe for Python's GIL-protected lru_cache.
    """
    return ElementStateService()
