"""
MSI Automotive - Element Data Service.

Business logic extracted from element_data_tools.py (Wave 3, Part 1).
Each public method corresponds to one tool; tools become thin wrappers
that delegate here.

Responsibilities:
- DB access for elements and required fields
- Field validation (type checking, range, conditionals)
- Photo-count queries (element and base-docs)
- State update assembly (case_collection_update / _state_update)
- Smart Collection Mode integration

Does NOT:
- Import from agent/tools/  (service must be tool-independent)
- Call get_current_state() directly (callers extract from state first)
- Hold mutable module-level state (idempotency keys belong in the tool layer)
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, UTC
from functools import lru_cache
from typing import Any

import structlog

from agent.services.expediente_helpers import (
    build_case_update,
    set_collection_step,
)
from agent.utils.expediente_types import (
    CaseCollectionState,
    CollectionStep,
    ELEMENT_STATUS_PENDING,
    ELEMENT_STATUS_PHOTOS_DONE,
    ELEMENT_STATUS_COMPLETE,
)
from agent.utils.text_utils import normalize_field_key as _normalize_field_key
from database.connection import get_async_session
from database.models import Case, CaseElementData, Element, ElementRequiredField

logger = structlog.get_logger(__name__)


# =============================================================================
# DB helpers (private)
# =============================================================================


async def _get_element_by_code(
    element_code: str,
    category_id: str,
    load_images: bool = False,
) -> Element | None:
    """Get element by code and category."""
    try:
        async with get_async_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            query = (
                select(Element)
                .where(
                    Element.code == element_code,
                    Element.category_id == uuid.UUID(category_id),
                    Element.is_active == True,  # noqa: E712
                )
            )
            if load_images:
                query = query.options(selectinload(Element.images))

            result = await session.execute(query)
            element = result.scalar_one_or_none()

            if element and load_images:
                _ = element.images  # trigger load while session is active

            return element
    except Exception as e:
        logger.error(
            "element_data_service.get_element_by_code_error",
            error=str(e),
            element_code=element_code,
            category_id=category_id,
            exc_info=True,
        )
        return None


async def _get_required_fields_for_element(
    element_id: str,
) -> list[ElementRequiredField]:
    """Get all active required fields for an element, ordered by sort_order."""
    try:
        async with get_async_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ElementRequiredField)
                .where(ElementRequiredField.element_id == uuid.UUID(element_id))
                .where(ElementRequiredField.is_active == True)  # noqa: E712
                .order_by(ElementRequiredField.sort_order)
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(
            "element_data_service.get_required_fields_error",
            error=str(e),
            element_id=element_id,
            exc_info=True,
        )
        return []


async def _get_or_create_case_element_data(
    case_id: str,
    element_code: str,
) -> CaseElementData | None:
    """Get or create CaseElementData record using INSERT … ON CONFLICT DO NOTHING."""
    try:
        async with get_async_session() as session:
            from sqlalchemy import select
            from sqlalchemy.dialects.postgresql import insert

            insert_stmt = (
                insert(CaseElementData)
                .values(
                    case_id=uuid.UUID(case_id),
                    element_code=element_code,
                    status="pending_photos",
                    field_values={},
                )
                .on_conflict_do_nothing(
                    index_elements=["case_id", "element_code"]
                )
            )
            await session.execute(insert_stmt)
            await session.commit()

            result = await session.execute(
                select(CaseElementData)
                .where(CaseElementData.case_id == uuid.UUID(case_id))
                .where(CaseElementData.element_code == element_code)
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error(
            "element_data_service.get_or_create_case_element_data_error",
            error=str(e),
            case_id=case_id,
            exc_info=True,
        )
        return None


async def _update_case_element_data(
    case_id: str,
    element_code: str,
    updates: dict[str, Any],
) -> CaseElementData | None:
    """Update CaseElementData record."""
    try:
        async with get_async_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(CaseElementData)
                .where(CaseElementData.case_id == uuid.UUID(case_id))
                .where(CaseElementData.element_code == element_code)
            )
            record = result.scalar_one_or_none()
            if record:
                for key, value in updates.items():
                    setattr(record, key, value)
                record.updated_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(record)
            return record
    except Exception as e:
        logger.error(
            "element_data_service.update_case_element_data_error",
            error=str(e),
            case_id=case_id,
            element_code=element_code,
            updates=list(updates.keys()),
            exc_info=True,
        )
        return None


async def _get_element_image_count(
    case_id: str,
    element_code: str,
    upload_batch_id: str | None = None,
) -> int:
    """Count images for a specific element within a case."""
    try:
        from sqlalchemy import func, select
        from database.models import CaseImage

        async with get_async_session() as session:
            scoped_query = (
                select(func.count())
                .select_from(CaseImage)
                .where(
                    CaseImage.case_id == uuid.UUID(case_id),
                    CaseImage.element_code == element_code,
                )
            )
            if upload_batch_id:
                scoped_query = scoped_query.where(
                    CaseImage.upload_batch_id == upload_batch_id
                )
            scoped_result = await session.execute(scoped_query)
            scoped_count = scoped_result.scalar() or 0

            if scoped_count == 0 and upload_batch_id:
                unscoped_query = (
                    select(func.count())
                    .select_from(CaseImage)
                    .where(
                        CaseImage.case_id == uuid.UUID(case_id),
                        CaseImage.element_code == element_code,
                    )
                )
                unscoped_result = await session.execute(unscoped_query)
                unscoped_count = unscoped_result.scalar() or 0
                if unscoped_count > 0:
                    logger.warning(
                        "element_data_service.element_image_batch_scope_mismatch",
                        case_id=case_id,
                        element_code=element_code,
                        upload_batch_id=upload_batch_id,
                        scoped_count=scoped_count,
                        unscoped_count=unscoped_count,
                    )
                    return unscoped_count

            return scoped_count
    except Exception as e:
        logger.warning(
            "element_data_service.get_element_image_count_failed",
            error=str(e),
            case_id=case_id,
        )
        return 0


async def _get_case_image_count(
    case_id: str,
    upload_batch_id: str | None = None,
) -> int:
    """Count base documentation images (element_code IS NULL) for a case."""
    try:
        from sqlalchemy import func, select
        from database.models import CaseImage

        async with get_async_session() as session:
            scoped_query = (
                select(func.count())
                .select_from(CaseImage)
                .where(
                    CaseImage.case_id == uuid.UUID(case_id),
                    CaseImage.element_code.is_(None),
                )
            )
            if upload_batch_id:
                scoped_query = scoped_query.where(
                    CaseImage.upload_batch_id == upload_batch_id
                )
            scoped_result = await session.execute(scoped_query)
            scoped_count = scoped_result.scalar() or 0

            if scoped_count == 0 and upload_batch_id:
                unscoped_query = (
                    select(func.count())
                    .select_from(CaseImage)
                    .where(
                        CaseImage.case_id == uuid.UUID(case_id),
                        CaseImage.element_code.is_(None),
                    )
                )
                unscoped_result = await session.execute(unscoped_query)
                unscoped_count = unscoped_result.scalar() or 0
                if unscoped_count > 0:
                    logger.warning(
                        "element_data_service.base_docs_batch_scope_mismatch",
                        case_id=case_id,
                        upload_batch_id=upload_batch_id,
                        scoped_count=scoped_count,
                        unscoped_count=unscoped_count,
                    )
                    return unscoped_count

            return scoped_count
    except Exception as e:
        logger.warning(
            "element_data_service.get_case_image_count_failed",
            error=str(e),
            case_id=case_id,
        )
        return 0


def _get_base_docs_settings():
    """Return settings object — extracted for test patching."""
    from shared.config import get_settings

    return get_settings()


async def _get_base_docs_min_required(
    case_id: str,
    category_id: str | None,
    base_doc_descriptions: list[str],
) -> int:
    """Derive minimum required base doc images from DB + floor setting.

    Formula: max(db_count, len(base_doc_descriptions), BASE_DOCS_MIN_REQUIRED_FLOOR)

    On DB failure: non-fatal. Falls back to max(len(descriptions), floor).
    Never returns a value below BASE_DOCS_MIN_REQUIRED_FLOOR.
    """
    settings = _get_base_docs_settings()
    floor = settings.BASE_DOCS_MIN_REQUIRED_FLOOR

    db_count = 0
    if category_id:
        try:
            from sqlalchemy import func, select
            from database.models import BaseDocumentation

            async with get_async_session() as session:
                result = await session.execute(
                    select(func.count(BaseDocumentation.id)).where(
                        BaseDocumentation.category_id == uuid.UUID(category_id),
                    )
                )
                db_count = result.scalar_one_or_none() or 0
        except Exception as e:
            logger.warning(
                "base_docs_min_required_fallback",
                case_id=case_id,
                category_id=category_id,
                error=str(e),
            )

    return max(db_count, len(base_doc_descriptions), floor)


# =============================================================================
# Pure helpers (private — no I/O)
# =============================================================================


def _get_current_element_code(case_state: CaseCollectionState) -> str | None:
    codes = case_state.get("element_codes", [])
    idx = case_state.get("current_element_index", 0)
    return codes[idx] if codes and idx < len(codes) else None


def _get_element_phase(case_state: CaseCollectionState) -> str:
    return case_state.get("element_phase", "photos")


def _is_current_element_photos_done(case_state: CaseCollectionState) -> bool:
    element_code = _get_current_element_code(case_state)
    if not element_code:
        return False
    status = case_state.get("element_data_status", {}).get(
        element_code, ELEMENT_STATUS_PENDING
    )
    return status in (ELEMENT_STATUS_PHOTOS_DONE, ELEMENT_STATUS_COMPLETE)


def _get_element_collection_progress(case_state: CaseCollectionState) -> dict[str, Any]:
    element_codes = case_state.get("element_codes", [])
    element_status = case_state.get("element_data_status", {})
    current_idx = case_state.get("current_element_index", 0)
    phase = case_state.get("element_phase", "photos")
    completed = sum(
        1
        for code in element_codes
        if element_status.get(code) == ELEMENT_STATUS_COMPLETE
    )
    current_code = (
        element_codes[current_idx] if current_idx < len(element_codes) else None
    )
    elements_info = [
        {
            "code": code,
            "status": element_status.get(code, ELEMENT_STATUS_PENDING),
            "is_current": code == current_code,
        }
        for code in element_codes
    ]
    return {
        "total_elements": len(element_codes),
        "completed_elements": completed,
        "current_element_index": current_idx,
        "current_element_code": current_code,
        "current_phase": phase,
        "elements": elements_info,
    }


def _lcp_length(a: str, b: str) -> int:
    """Return length of longest common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def validate_field_value(
    value: Any,
    field: ElementRequiredField,
) -> tuple[bool, str | None]:
    """
    Validate a field value against its type and validation rules.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if field.is_required and (value is None or value == ""):
        return False, f"El campo '{field.field_label}' es obligatorio"

    if value is None or value == "":
        return True, None

    if field.field_type == "number":
        try:
            clean_value = str(value).strip()
            clean_value = re.sub(
                r"\s*(mm|cm|m|kg|g|cc|cv|hp|kw|€|euros?)\s*$",
                "",
                clean_value,
                flags=re.IGNORECASE,
            )
            clean_value = clean_value.strip()
            num_val = float(clean_value)
            rules = field.validation_rules or {}
            min_val = rules.get("min") if "min" in rules else rules.get("min_value")
            max_val = rules.get("max") if "max" in rules else rules.get("max_value")
            if min_val is not None and num_val < min_val:
                return False, f"El valor debe ser mayor o igual a {min_val}"
            if max_val is not None and num_val > max_val:
                return False, f"El valor debe ser menor o igual a {max_val}"
        except (ValueError, TypeError):
            return False, f"'{value}' no es un número válido"

    elif field.field_type == "boolean":
        if str(value).lower() not in ("true", "false", "sí", "si", "no", "1", "0"):
            return False, "El valor debe ser Sí o No"

    elif field.field_type == "select":
        if field.options:
            options_lower = {o.lower(): o for o in field.options}
            if str(value).lower() not in options_lower:
                return False, f"Valor no válido. Opciones: {', '.join(field.options)}"

    elif field.field_type == "text":
        rules = field.validation_rules or {}
        if "min_length" in rules and len(str(value)) < rules["min_length"]:
            return False, f"El texto debe tener al menos {rules['min_length']} caracteres"
        if "max_length" in rules and len(str(value)) > rules["max_length"]:
            return False, f"El texto debe tener como máximo {rules['max_length']} caracteres"
        if "pattern" in rules:
            if not re.match(rules["pattern"], str(value)):
                pattern_hint = rules.get("pattern_description") or rules.get("example")
                if pattern_hint:
                    return False, f"El formato no es válido. Ejemplo esperado: {pattern_hint}"
                return False, f"El formato no es válido (patrón requerido: {rules['pattern']})"

    return True, None


def evaluate_field_condition(
    field: ElementRequiredField,
    collected_values: dict[str, Any],
    all_fields: list[ElementRequiredField],
) -> bool:
    """Evaluate if a conditional field should be shown."""
    if not field.condition_field_id:
        return True

    condition_field = next(
        (f for f in all_fields if str(f.id) == str(field.condition_field_id)),
        None,
    )
    if not condition_field:
        logger.warning(
            "element_data_service.conditional_field_missing_reference",
            field_key=field.field_key,
            field_id=str(field.id),
            condition_field_id=str(field.condition_field_id),
        )
        return True

    condition_value = collected_values.get(condition_field.field_key)
    operator = field.condition_operator or "equals"
    expected = field.condition_value

    if operator == "equals":
        return (
            str(condition_value).lower() == str(expected).lower()
            if condition_value
            else False
        )
    elif operator == "not_equals":
        return (
            str(condition_value).lower() != str(expected).lower()
            if condition_value
            else True
        )
    elif operator == "exists":
        return condition_value is not None and condition_value != ""
    elif operator == "not_exists":
        return condition_value is None or condition_value == ""

    return True


def _increment_field_retry_count(
    mode_context: dict[str, Any],
    field_key: str,
) -> dict[str, Any]:
    """
    Increment the retry count for a specific field in mode_context.

    Returns the updated _field_retry_counts dict (not a full mode_context).
    Does NOT mutate mode_context — callers include the result in _internal_flags.
    """
    current_counts: dict[str, int] = dict(
        mode_context.get("_field_retry_counts") or {}
    )
    current_counts[field_key] = current_counts.get(field_key, 0) + 1
    return current_counts


def _reset_field_retry_counts() -> dict[str, Any]:
    """Return an empty _field_retry_counts dict (used on completar_elemento_actual)."""
    return {}


def _tool_error_response(
    error: str,
    current_step: CollectionStep | str | None = None,
    guidance: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "success": False,
        "error": error,
        "message": error,
    }
    if current_step:
        step_val = (
            current_step.value
            if isinstance(current_step, CollectionStep)
            else current_step
        )
        response["current_step"] = step_val
    if guidance:
        response["guidance"] = guidance
    return response


# =============================================================================
# Public service API
# =============================================================================


async def get_element_fields(
    element_code: str | None,
    case_id: str,
    category_id: str,
    element_codes: list[str],
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Return required fields for the current or specified element.

    V2 path (ElementStateService) is tried first; falls back to V1 FSM path.
    """
    # ── V2 PATH ───────────────────────────────────────────────────────────────
    try:
        from agent.services.element_state_service import (
            get_element_state_service as _get_ess_v2,
        )
        from agent.services.collection_mode import (
            CollectionMode as _CM,
            FieldInfo as _FieldInfo,
            determine_collection_mode as _determine_mode,
        )

        # Extract adaptive params from mode_context (V2 path only)
        _turn_count: int = mode_context.get("mode_message_count") or 0
        _client_type: str | None = mode_context.get("client_type")
        _retry_state: dict = mode_context.get("retry_state") or {}
        _consecutive_errors: int = (
            _retry_state.get("consecutive_errors", 0)
            if isinstance(_retry_state, dict)
            else 0
        )

        ess_v2 = _get_ess_v2()

        if element_code:
            el_state = await ess_v2.get_element_state(case_id, element_code, category_id)
            if el_state is None:
                return _tool_error_response(f"Elemento '{element_code}' no encontrado (V2)")
            pending_fields = [f.to_dict() for f in el_state.pending_fields]

            # Compute recommended_collection_mode with adaptive params
            _element_complexity = len(el_state.all_fields)
            _field_infos = [_FieldInfo.from_db_field(f) for f in el_state.pending_fields]
            _rec_mode: _CM = _determine_mode(
                _field_infos,
                turn_count=_turn_count,
                client_type=_client_type,
                consecutive_errors=_consecutive_errors,
                element_complexity=_element_complexity,
            )
            _v2_ctx = el_state.to_dict()
            _v2_ctx["recommended_collection_mode"] = _rec_mode.value

            return {
                "success": True,
                "v2": True,
                "element_code": element_code,
                "element_name": el_state.display_name,
                "phase": el_state.phase,
                "photos_required": el_state.photos_required,
                "photos_confirmed_count": el_state.photos_confirmed_count,
                "fields": pending_fields,
                "total_fields": len(el_state.all_fields),
                "total_required": sum(1 for f in el_state.all_fields if f.is_required),
                "collected_required": sum(
                    1 for f in el_state.all_fields if f.is_required and f.is_collected
                ),
                "all_required_collected": not any(
                    f for f in el_state.pending_fields if f.is_required
                ),
                "warnings": el_state.warnings,
                "message": (
                    f"Elemento {element_code} — fase '{el_state.phase}'. "
                    f"{len(pending_fields)} campo(s) pendiente(s)."
                ),
                "v2_collection_context": _v2_ctx,
            }

        # No element_code → full CollectionContext
        collection_ctx = await ess_v2.get_collection_context(
            case_id, element_codes, category_id
        )
        ctx_dict = collection_ctx.to_dict()
        current = ctx_dict.get("current_element") or {}
        pending_fields_current = current.get("pending_fields", [])

        # Compute recommended_collection_mode for current element
        _all_fields_current = current.get("all_fields") or current.get("pending_fields", [])
        _element_complexity_ctx = len(_all_fields_current)
        _pf_infos = [
            _FieldInfo(
                field_key=f.get("field_key", ""),
                field_label=f.get("field_label", ""),
                field_type=f.get("field_type", "text"),
                is_required=f.get("is_required", True),
                has_condition=bool(f.get("condition_field_key")),
                condition_field_key=f.get("condition_field_key"),
            )
            for f in pending_fields_current
            if isinstance(f, dict)
        ]
        _rec_mode_ctx: _CM = _determine_mode(
            _pf_infos,
            turn_count=_turn_count,
            client_type=_client_type,
            consecutive_errors=_consecutive_errors,
            element_complexity=_element_complexity_ctx,
        )
        ctx_dict["recommended_collection_mode"] = _rec_mode_ctx.value

        return {
            "success": True,
            "v2": True,
            "element_code": current.get("code"),
            "element_name": current.get("display_name"),
            "phase": current.get("phase"),
            "fields": pending_fields_current,
            "all_required_collected": not any(
                f for f in pending_fields_current if f.get("is_required")
            ),
            "progress": ctx_dict.get("progress", {}),
            "all_elements": ctx_dict.get("all_elements", []),
            "message": (
                f"Contexto de recolección disponible. "
                f"Elemento actual: {current.get('display_name', current.get('code', '?'))}. "
                f"{len(pending_fields_current)} campo(s) pendiente(s) de recoger."
            ),
            "v2_collection_context": ctx_dict,
        }

    except Exception as _v2_err:
        logger.error(
            "element_data_service.get_element_fields_v2_error",
            error=str(_v2_err),
            exc_info=True,
        )
        logger.warning(
            "element_data_service.get_element_fields_v2_fallback",
            reason="exception in V2 path, falling back to V1",
        )

    # ── V1 PATH ───────────────────────────────────────────────────────────────
    from agent.utils.expediente_types import CollectionStep as _CS

    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", _CS.IDLE.value),
        case_id=case_id,
        category_id=category_id,
        element_codes=element_codes,
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )

    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))

    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
    collected_values = case_element.field_values or {}

    fields_info = []
    for field in fields:
        if not evaluate_field_condition(field, collected_values, fields):
            continue
        field_info: dict[str, Any] = {
            "field_key": field.field_key,
            "field_label": field.field_label,
            "field_type": field.field_type,
            "is_required": field.is_required,
            "current_value": collected_values.get(field.field_key),
            "is_collected": field.field_key in collected_values,
        }
        if field.options:
            field_info["options"] = field.options
        if field.example_value:
            field_info["example"] = field.example_value
        if field.llm_instruction:
            field_info["instruction"] = field.llm_instruction
        if field.validation_rules:
            field_info["validation"] = field.validation_rules
        fields_info.append(field_info)

    total_required = sum(1 for f in fields_info if f["is_required"])
    collected_required = sum(
        1 for f in fields_info if f["is_required"] and f["is_collected"]
    )

    return {
        "success": True,
        "element_code": element_code,
        "element_name": element.name,
        "fields": fields_info,
        "total_fields": len(fields_info),
        "total_required": total_required,
        "collected_required": collected_required,
        "all_required_collected": collected_required >= total_required,
        "message": (
            f"Elemento {element_code} tiene {len(fields_info)} campos de datos. "
            f"{collected_required}/{total_required} campos obligatorios completados."
        ),
    }


async def save_element_data(
    datos: dict[str, Any],
    element_code: str | None,
    case_id: str,
    category_id: str,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate and persist technical field data for one element.

    Handles field-key normalisation (accents, fuzzy matching, LCP tie-break),
    idempotency guards, and smart collection mode for the response.
    """
    from shared.config import get_settings

    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=case_id,
        category_id=category_id,
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )

    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    phase = _get_element_phase(case_state)
    if phase != "data":
        available_fields_hint = ""
        if element_code and category_id:
            try:
                hint_element = await _get_element_by_code(element_code, category_id)
                if hint_element:
                    hint_fields = await _get_required_fields_for_element(str(hint_element.id))
                    if hint_fields:
                        field_keys = [
                            f"{f.field_key} ({f.field_label})" for f in hint_fields
                        ]
                        available_fields_hint = (
                            f"\n\nCampos que necesitarás después: {', '.join(field_keys)}"
                        )
            except Exception:
                pass
        return _tool_error_response(
            f"Estamos en fase '{phase}', no 'data'. "
            "Primero confirma las fotos con confirmar_fotos_elemento()."
            f"{available_fields_hint}",
            guidance="confirmar_fotos_primero",
        )

    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))
    fields_by_key = {f.field_key: f for f in fields}
    fields_by_normalized_key = {_normalize_field_key(f.field_key): f for f in fields}

    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
    current_values = case_element.field_values.copy() if case_element.field_values else {}

    # Empty datos guard
    if not datos:
        pending = [
            {
                "field_key": f.field_key,
                "field_label": f.field_label,
                "field_type": f.field_type,
            }
            for f in fields
            if evaluate_field_condition(f, current_values, fields)
            and f.field_key not in current_values
        ]
        example = {f["field_key"]: f"<{f['field_type']}>" for f in pending[:3]}
        return {
            "success": False,
            "element_code": element_code,
            "error": "No se proporcionaron datos. Usa los field_key indicados abajo.",
            "message": (
                "Necesito los datos técnicos del elemento. "
                "Llama guardar_datos_elemento(datos={field_key: valor, ...}) "
                "con los siguientes campos:"
            ),
            "pending_fields": pending,
            "example": example,
        }

    # Validate and save each field
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    idempotent_count = 0

    for field_key, value in datos.items():
        field = fields_by_key.get(field_key)
        actual_field_key = field_key

        if not field:
            normalized_key = _normalize_field_key(field_key)
            field = fields_by_normalized_key.get(normalized_key)
            if field:
                actual_field_key = field.field_key
                logger.info(
                    "element_data_service.field_key_normalized",
                    field_key_original=field_key,
                    field_key_actual=actual_field_key,
                    element_code=element_code,
                )

        if not field:
            normalized_input = _normalize_field_key(field_key)
            candidates: list[tuple[str, ElementRequiredField]] = []
            for norm_key, f_candidate in fields_by_normalized_key.items():
                if normalized_input in norm_key or norm_key in normalized_input:
                    candidates.append((norm_key, f_candidate))

            if len(candidates) == 1:
                field = candidates[0][1]
                actual_field_key = field.field_key
                logger.info(
                    "element_data_service.field_key_fuzzy_matched",
                    field_key_input=field_key,
                    field_key_actual=actual_field_key,
                    element_code=element_code,
                )
            elif len(candidates) > 1:
                candidate_keys = [c[1].field_key for c in candidates]
                lcp_scores = [
                    _lcp_length(normalized_input, _normalize_field_key(ck))
                    for ck in candidate_keys
                ]
                best_lcp = max(lcp_scores)
                best_idx = lcp_scores.index(best_lcp)
                lcp_selected_key = candidate_keys[best_idx]
                lcp_selected_field = candidates[best_idx][1]

                logger.warning(
                    "element_data_service.field_mapping_ambiguous",
                    field_input=field_key,
                    candidates=candidate_keys,
                    selected=lcp_selected_key,
                    strict_mode=get_settings().EXPEDIENTE_STRICT_FIELD_MAPPING,
                    element_code=element_code,
                )

                if get_settings().EXPEDIENTE_STRICT_FIELD_MAPPING:
                    candidate_labels = [c[1].field_label for c in candidates]
                    results.append(
                        {
                            "field_key": field_key,
                            "status": "ambiguous",
                            "message": (
                                f"No he podido identificar exactamente a qué campo corresponde ese dato. "
                                f"¿Puedes indicar si es {', '.join(candidate_labels)}?"
                            ),
                            "candidates": candidate_keys,
                        }
                    )
                    continue

                field = lcp_selected_field
                actual_field_key = field.field_key

        if not field:
            valid_keys = [f.field_key for f in fields]
            results.append(
                {
                    "field_key": field_key,
                    "status": "ignored",
                    "message": f"Campo '{field_key}' no existe. Campos válidos: {', '.join(valid_keys)}",
                    "valid_field_keys": valid_keys,
                }
            )
            continue

        if not evaluate_field_condition(field, current_values, fields):
            results.append(
                {
                    "field_key": field_key,
                    "status": "skipped",
                    "message": f"Campo '{field_key}' no aplica según las condiciones",
                }
            )
            continue

        existing_value = current_values.get(actual_field_key)
        if existing_value == value:
            idempotent_count += 1
            results.append(
                {
                    "field_key": actual_field_key,
                    "status": "already_saved",
                    "value": value,
                    "message": f"Campo '{field.field_label}' ya tiene este valor",
                }
            )
            logger.info(
                "element_data_service.field_idempotent",
                element_code=element_code,
                field_key=actual_field_key,
            )
            continue

        is_valid, error_msg = validate_field_value(value, field)
        if not is_valid:
            errors.append(f"{field.field_label}: {error_msg}")
            results.append({"field_key": actual_field_key, "status": "error", "message": error_msg})
        else:
            current_values[actual_field_key] = value
            results.append({"field_key": actual_field_key, "status": "saved", "value": value})

    # Persist to DB
    await _update_case_element_data(case_id, element_code, {"field_values": current_values})

    # V2: Mirror each saved value into ElementStateService
    try:
        from agent.services.element_state_service import get_element_state_service

        _ess_v2 = get_element_state_service()
        for _fk, _fv in current_values.items():
            await _ess_v2.record_field_value(case_id, element_code, _fk, _fv)
    except Exception as _ess_err:
        logger.warning(
            "element_data_service.v2_record_field_failed",
            element_code=element_code,
            error=str(_ess_err),
        )

    # Check completeness
    all_required_collected = True
    missing_fields: list[str] = []
    for field in fields:
        if not evaluate_field_condition(field, current_values, fields):
            continue
        if field.is_required and field.field_key not in current_values:
            all_required_collected = False
            missing_fields.append(field.field_label)

    from agent.services.collection_mode import (
        CollectionMode,
        FieldInfo,
        determine_collection_mode,
        get_fields_for_mode,
        format_batch_prompt,
    )

    ignored_fields = [r["field_key"] for r in results if r["status"] in ("ignored", "ambiguous")]

    response: dict[str, Any] = {
        "success": len(errors) == 0,
        "element_code": element_code,
        "results": results,
        "saved_count": sum(1 for r in results if r["status"] == "saved"),
        "error_count": len(errors),
        "all_required_collected": all_required_collected,
    }

    if ignored_fields:
        valid_field_keys = [f.field_key for f in fields]
        response["error"] = f"CAMPOS INCORRECTOS: {', '.join(ignored_fields)}"
        response["message"] = (
            f"❌ ERROR CRÍTICO: Los campos {', '.join(ignored_fields)} NO EXISTEN para el elemento {element_code}.\n\n"
            f"DEBES usar EXACTAMENTE estos field_key:\n"
            f"{', '.join(valid_field_keys)}\n\n"
            f"Vuelve a llamar guardar_datos_elemento() con los field_key correctos.\n"
            f"Usa obtener_campos_elemento() si necesitas ver las instrucciones completas."
        )
        response["success"] = False
        logger.warning(
            "element_data_service.ignored_fields",
            ignored_fields=ignored_fields,
            element_code=element_code,
            valid=valid_field_keys,
        )
        return response

    if errors:
        from agent.services.collection_mode import create_error_recovery_response

        # Accumulate updated retry counts (immutable: start from mode_context, build up)
        updated_counts: dict[str, int] = dict(
            mode_context.get("_field_retry_counts") or {}
        )
        erroring_fields_results = [r for r in results if r["status"] == "error"]

        # Build per-field error recovery and accumulate retry counts
        erroring_field_keys = [r["field_key"] for r in erroring_fields_results]

        # Increment counts for all erroring fields
        for fk in erroring_field_keys:
            updated_counts[fk] = updated_counts.get(fk, 0) + 1

        # Build structured recovery for the first erroring field
        # (the LLM reads this to ask the user for the corrected value)
        first_error_result = erroring_fields_results[0] if erroring_fields_results else {}
        first_field_key = first_error_result.get("field_key", "")
        first_field_obj = fields_by_key.get(first_field_key) or fields_by_normalized_key.get(
            _normalize_field_key(first_field_key)
        )

        recovery = create_error_recovery_response(
            error_code="VALIDATION_ERROR",
            error_message=first_error_result.get("message") or errors[0],
            field_key=first_field_key,
            validation_hint=first_error_result.get("message") or errors[0],
            example_value=first_field_obj.example_value if first_field_obj else None,
            field_retry_count=updated_counts.get(first_field_key, 1),
            is_required=first_field_obj.is_required if first_field_obj else True,
        )

        response["errors"] = errors
        response["recovery"] = {
            **recovery.get("recovery", {}),
            "fields_with_errors": erroring_field_keys,
        }
        response["message"] = f"Errores en {len(errors)} campos. Verifica: {'; '.join(errors)}"
        response["_internal_flags"] = {"_field_retry_counts": updated_counts}

    elif missing_fields:
        # Extract adaptive params from mode_context for determine_collection_mode
        _turn_count: int = mode_context.get("mode_message_count") or 0
        _client_type: str | None = mode_context.get("client_type")
        _retry_state: dict = mode_context.get("retry_state") or {}
        _consecutive_errors: int = (
            _retry_state.get("consecutive_errors", 0)
            if isinstance(_retry_state, dict)
            else 0
        )

        pending_fields: list[FieldInfo] = []
        for field in fields:
            if not evaluate_field_condition(field, current_values, fields):
                continue
            if field.is_required and field.field_key not in current_values:
                pending_fields.append(FieldInfo.from_db_field(field))

        if pending_fields:
            _element_complexity = len(fields)
            collection_mode = determine_collection_mode(
                pending_fields,
                current_values,
                turn_count=_turn_count,
                client_type=_client_type,
                consecutive_errors=_consecutive_errors,
                element_complexity=_element_complexity,
            )
            fields_structure = get_fields_for_mode(collection_mode, pending_fields, current_values)
            response["collection_mode"] = collection_mode.value
            response["missing_fields"] = missing_fields
            response.update(fields_structure)

            if collection_mode == CollectionMode.SEQUENTIAL:
                current_field = fields_structure.get("current_field", {})
                instruction = current_field.get("instruction", "")
                fk = current_field.get("field_key", "")
                fl = current_field.get("field_label", "")
                options = current_field.get("options")
                example = current_field.get("example")
                options_text = f" (opciones: {', '.join(options)})" if options else ""
                example_text = f" (ej: {example})" if example else ""
                response["message"] = (
                    f"✅ Datos guardados.\n\n"
                    f"📋 SIGUIENTE CAMPO:\n"
                    f"• Nombre: {fl}\n"
                    f"• Field key: '{fk}'\n"
                    f"• Guía interna (reformula en lenguaje sencillo): {instruction}{options_text}{example_text}\n\n"
                    f"⚠️ Al guardar, usa field_key='{fk}'"
                )
            else:
                batch_fields = fields_structure.get("fields", [])
                if batch_fields:
                    field_items = [
                        f"{f['field_label']} (field_key={f['field_key']})"
                        for f in batch_fields
                    ]
                    response["message"] = f"Datos guardados. Aun faltan: {', '.join(field_items)}"
                else:
                    response["message"] = f"Datos guardados. Faltan: {', '.join(missing_fields)}"
        else:
            response["message"] = f"Datos guardados. Faltan: {', '.join(missing_fields)}"
    else:
        response["message"] = "Todos los datos del elemento han sido guardados correctamente."
        response["action"] = "ELEMENT_DATA_COMPLETE"

    # V2: Enrich with DB-authoritative pending_fields when all required collected
    if response.get("all_required_collected"):
        try:
            from agent.services.element_state_service import get_element_state_service

            _ess_resp = get_element_state_service()
            _remaining = await _ess_resp.get_pending_fields(case_id, element_code)
            response["pending_fields"] = [
                {"field_key": f.field_key, "field_label": f.field_label}
                for f in _remaining
            ]
        except Exception as _ess_resp_err:
            logger.debug(
                "element_data_service.v2_pending_fields_failed",
                element_code=element_code,
                error=str(_ess_resp_err),
            )

    return response


# =============================================================================
# Two-Phase Poller (shared by element photos + base docs confirmation)
# =============================================================================


from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class TwoPhasePollingResult:
    """Result of a two-phase image count poll."""

    count: int
    phase_reached: int  # 0=no poll needed, 1=after phase1, 2=after phase2
    feedback_sent: bool


def _get_two_phase_settings():
    """Return settings object — extracted for test patching."""
    from shared.config import get_settings

    return get_settings()


def _get_chatwoot_client():
    """Return ChatwootClient — extracted for test patching."""
    from shared.chatwoot_client import ChatwootClient

    return ChatwootClient()


async def _send_poller_feedback(
    *,
    message: str,
    conversation_id: str | None,
    user_phone: str,
) -> bool:
    """Send processing feedback message to user via Chatwoot.

    Non-fatal: any exception is swallowed and False is returned.
    """
    try:
        chatwoot = _get_chatwoot_client()
        conv_id_int = int(conversation_id) if conversation_id else None
        await chatwoot.send_message(
            customer_phone=user_phone,
            message=message,
            conversation_id=conv_id_int,
        )
        return True
    except Exception as _feed_err:
        logger.debug(
            "element_data_service.poller_feedback_failed",
            error=str(_feed_err),
        )
        return False


class TwoPhasePoller:
    """Reusable two-phase polling for image count verification.

    The poller is invoked ONLY when the caller has already determined that the
    current count is below min_required. It sends a "processing" feedback
    message, waits for phase-1, rechecks, then optionally waits for phase-2.

    Usage::

        poller = TwoPhasePoller(
            count_fn=lambda: _get_element_image_count(case_id, element_code, batch_id),
            feedback_message="Procesando tus imágenes, un momento... ⏳",
            conversation_id=conversation_id,
            user_phone=mode_context.get("user_phone", ""),
        )
        result = await poller.poll(min_required=1)
        if result.count >= min_required:
            # advance
    """

    def __init__(
        self,
        *,
        count_fn: Callable[[], Awaitable[int]],
        feedback_message: str,
        conversation_id: str | None,
        user_phone: str,
    ) -> None:
        self._count_fn = count_fn
        self._feedback_message = feedback_message
        self._conversation_id = conversation_id
        self._user_phone = user_phone

    async def poll(self, min_required: int = 1) -> TwoPhasePollingResult:
        """Execute two-phase polling. Returns final count and metadata.

        Fast-path (phase_reached=0): if count_fn already meets the threshold on
        the very first call (before any sleep or feedback), return immediately.
        This handles the case where the caller invokes poll() without a prior
        count check.

        Phase 1: send feedback, sleep, recheck.
        Phase 2: sleep again, recheck.
        """
        settings = _get_two_phase_settings()
        phase1_wait = settings.PHOTO_COMPLETION_WAIT_SECONDS
        phase2_wait = settings.PHOTO_COMPLETION_RETRY_WAIT_SECONDS

        # Fast-path: check count before sending feedback or sleeping
        initial_count = await self._count_fn()
        if initial_count >= min_required:
            return TwoPhasePollingResult(
                count=initial_count, phase_reached=0, feedback_sent=False
            )

        # Send processing feedback via Chatwoot (non-fatal)
        feedback_sent = await _send_poller_feedback(
            message=self._feedback_message,
            conversation_id=self._conversation_id,
            user_phone=self._user_phone,
        )

        # Phase 1: wait then recheck
        await asyncio.sleep(phase1_wait)
        count = await self._count_fn()
        if count >= min_required:
            return TwoPhasePollingResult(
                count=count, phase_reached=1, feedback_sent=feedback_sent
            )

        # Phase 2: wait then recheck
        await asyncio.sleep(phase2_wait)
        count = await self._count_fn()
        return TwoPhasePollingResult(
            count=count, phase_reached=2, feedback_sent=feedback_sent
        )


# =============================================================================
# Redis transition marker helpers (T-20)
# =============================================================================

_ELEMENT_TRANSITION_MARKER_PREFIX = "element_transition"
_ELEMENT_TRANSITION_MARKER_TTL = 60  # seconds


async def _set_element_transition_marker(
    conversation_id: str,
    element_code: str,
    next_element_code: str | None,
) -> None:
    """
    Set a Redis marker that deterministically attributes incoming photos to the
    next element code after confirmar_fotos_elemento() transitions element_phase.

    Key:   element_transition:{conversation_id}:{element_code}
    Value: next_element_code  OR  "__none__" when element_code is the last one
    TTL:   60 seconds
    NX:    SET NX — idempotent; second call does NOT reset the TTL

    Errors are swallowed (non-fatal) — the heuristic fallback covers this.
    """
    from shared.redis_client import get_redis_client

    marker_key = f"{_ELEMENT_TRANSITION_MARKER_PREFIX}:{conversation_id}:{element_code}"
    marker_value = next_element_code if next_element_code else "__none__"

    try:
        redis = get_redis_client()
        await redis.set(marker_key, marker_value, ex=_ELEMENT_TRANSITION_MARKER_TTL, nx=True)
    except Exception as _marker_err:
        logger.warning(
            "element_transition_marker_write_failed",
            conversation_id=conversation_id,
            element_code=element_code,
            error=str(_marker_err),
        )


async def _delete_element_transition_marker(
    conversation_id: str,
    element_code: str,
) -> None:
    """
    Delete the Redis transition marker for a completed element.
    Called from complete_current_element() after advancing the index.
    Errors are swallowed (non-fatal).
    """
    from shared.redis_client import get_redis_client

    marker_key = f"{_ELEMENT_TRANSITION_MARKER_PREFIX}:{conversation_id}:{element_code}"

    try:
        redis = get_redis_client()
        await redis.delete(marker_key)
    except Exception as _del_err:
        logger.warning(
            "element_transition_marker_delete_failed",
            conversation_id=conversation_id,
            element_code=element_code,
            error=str(_del_err),
        )


async def confirm_element_photos(
    case_id: str,
    category_id: str,
    mode_context: dict[str, Any],
    usuario_confirma: bool | None,
    conversation_id: str | None,
    active_batch_id: str | None,
    idempotency_key: str,
    already_confirmed_this_turn: bool,
) -> dict[str, Any]:
    """
    Confirm photos received for the current element.

    The tool layer is responsible for:
    - providing the idempotency key and whether it was already confirmed
    - registering the key in the module-level set after this method returns

    This method focuses on the business logic only.
    """
    from agent.services.case_image_batch_service import get_case_image_batch_service

    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=case_id,
        category_id=category_id,
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )
    fsm_state = mode_context.get("fsm_state")

    element_code = _get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    phase = _get_element_phase(case_state)

    # Idempotency: photos already confirmed in a prior turn
    if phase == "data" and _is_current_element_photos_done(case_state):
        return {
            "success": True,
            "photos_confirmed": True,
            "already_confirmed": True,
            "element_code": element_code,
            "message": f"Las fotos de {element_code} ya fueron confirmadas. Continuamos con los datos técnicos.",
            "_state_update": {
                "fotos_elemento_registered": True,
                "can_narrate_next_element": False,
                "all_elements_complete": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    if phase != "photos":
        return _tool_error_response(
            f"Fase incorrecta: {phase}. No se puede confirmar fotos desde esta fase."
        )

    # Idempotency: already confirmed this turn
    if already_confirmed_this_turn:
        _idemp_element = await _get_element_by_code(element_code, category_id)
        _idemp_fields: list[ElementRequiredField] = []
        if _idemp_element:
            _idemp_fields = await _get_required_fields_for_element(str(_idemp_element.id))
        _idemp_has_fields = bool(_idemp_fields)
        _idemp_phase = "data" if _idemp_has_fields else "photos"

        logger.info(
            "element_data_service.confirm_photos_idempotent_v2",
            case_id=case_id,
            element_code=element_code,
        )

        _idemp_response: dict[str, Any] = {
            "success": True,
            "photos_confirmed": True,
            "idempotent": True,
            "element_code": element_code,
            "element_phase": _idemp_phase,
            "has_required_fields": _idemp_has_fields,
            "current_element_index": case_state.get("current_element_index", 0),
            "message": f"Las fotos de {element_code} ya fueron confirmadas en este turno.",
            "_state_update": {
                "fotos_elemento_registered": True,
                "can_narrate_next_element": False,
                "all_elements_complete": False,
                "delivery_outcome_status": "not_requested",
            },
        }

        if _idemp_has_fields:
            from agent.services.collection_mode import (
                CollectionMode,
                FieldInfo,
                determine_collection_mode,
                get_fields_for_mode,
            )

            _idemp_field_infos = [FieldInfo.from_db_field(f) for f in _idemp_fields]
            _idemp_coll_mode = determine_collection_mode(_idemp_field_infos)
            _idemp_fields_structure = get_fields_for_mode(_idemp_coll_mode, _idemp_field_infos)
            _idemp_response["total_fields"] = len(_idemp_fields)
            _idemp_response["collection_mode"] = _idemp_coll_mode.value
            _idemp_response.update(_idemp_fields_structure)

        return _idemp_response

    # Defense: reject premature LLM calls
    element_image_count = await _get_element_image_count(
        case_id, element_code, active_batch_id
    )

    _el_states: dict = mode_context.get("element_states") or {}
    _el_entry = _el_states.get(element_code)
    if (
        element_image_count == 0
        and isinstance(_el_entry, dict)
        and _el_entry.get("state") == "awaiting_photos"
    ):
        logger.warning(
            "element_data_service.confirm_photos_rejected_awaiting",
            case_id=case_id,
            element_code=element_code,
        )
        return {
            "success": False,
            "rejected": True,
            "element_code": element_code,
            "message": (
                f"El elemento {element_code} aún no tiene fotos. "
                "Esperá a que el usuario envíe las fotos y diga 'listo' antes de confirmar."
            ),
        }

    # Two-phase polling when user confirms but count is 0
    if element_image_count == 0:
        if usuario_confirma is True:
            _user_phone: str = mode_context.get("user_phone", "")
            poller = TwoPhasePoller(
                count_fn=lambda: _get_element_image_count(
                    case_id, element_code, active_batch_id
                ),
                feedback_message="Procesando tus imágenes, un momento... ⏳",
                conversation_id=conversation_id,
                user_phone=_user_phone,
            )
            poll_result = await poller.poll(min_required=1)
            element_image_count = poll_result.count

            # T-18: Reconcile-on-demand — only when BOTH phases failed.
            # Attempts to recover images missed by dropped Chatwoot webhooks.
            # Non-fatal: a timeout or error here must not block the user.
            if element_image_count == 0:
                try:
                    from agent.services.image_handling import (
                        reconcile_conversation_images,
                    )

                    _case_id_for_reconcile = case_id
                    _conv_id_for_reconcile = conversation_id

                    logger.info(
                        "reconcile_on_demand_triggered",
                        case_id=_case_id_for_reconcile,
                        element_code=element_code,
                        conversation_id=_conv_id_for_reconcile,
                    )

                    _reconciled, _ = await asyncio.wait_for(
                        reconcile_conversation_images(
                            conversation_id=_conv_id_for_reconcile or "",
                            case_id=_case_id_for_reconcile,
                            element_code=element_code,
                        ),
                        timeout=20,
                    )
                    if _reconciled > 0:
                        element_image_count = await _get_element_image_count(
                            case_id, element_code, active_batch_id
                        )
                        logger.info(
                            "reconcile_on_demand_recovered",
                            case_id=case_id,
                            element_code=element_code,
                            reconciled=_reconciled,
                            new_count=element_image_count,
                        )
                except asyncio.TimeoutError as _reconcile_timeout:
                    logger.error(
                        "reconcile_on_demand_timeout",
                        case_id=case_id,
                        element_code=element_code,
                        error=str(_reconcile_timeout),
                    )
                except Exception as _reconcile_err:
                    logger.error(
                        "reconcile_on_demand_failed",
                        case_id=case_id,
                        element_code=element_code,
                        error=str(_reconcile_err),
                    )

            if element_image_count == 0:
                return {
                    "success": False,
                    "received": False,
                    "needs_photos": True,
                    "element_code": element_code,
                    "message": (
                        f"No he podido recuperar las fotos de {element_code}. "
                        "¿Puedes reenviarlas? "
                        "Asegurate de enviarlas como imagen de WhatsApp, no como documento adjunto."
                    ),
                }
        else:
            return {
                "success": False,
                "needs_confirmation": True,
                "element_code": element_code,
                "images_received": 0,
                "message": (
                    f"No he recibido fotos para {element_code} todavía. "
                    "¿Has enviado ya las fotos de este elemento?\n\n"
                    "Envía las fotos y escribe 'listo' cuando termines."
                ),
                "guidance": (
                    "Si el usuario confirma que sí ha enviado las fotos, "
                    "llama de nuevo a confirmar_fotos_elemento(usuario_confirma=True). "
                    "Si dice que no, pídele que las envíe."
                ),
            }

    # Images confirmed — fetch element and fields
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))

    await _update_case_element_data(
        case_id,
        element_code,
        {
            "status": "pending_data" if fields else "completed",
            "photos_completed_at": datetime.now(UTC),
        },
    )

    # Finalize batch
    batch_service = get_case_image_batch_service()
    await batch_service.finalize_for_scope(
        case_id=case_id,
        expediente_sub_mode="collect_element_data",
        element_code=element_code,
        status="confirmed",
    )

    # T-20: Set Redis transition marker after successful finalization.
    # This marker is read by get_current_element_code_async() to deterministically
    # attribute incoming photos to the next element (instead of fragile heuristic).
    # SET NX ensures idempotency; TTL=60s prevents stale markers.
    if conversation_id:
        _element_codes_for_marker = case_state.get("element_codes", [])
        _current_idx_for_marker = case_state.get("current_element_index", 0)
        _next_for_marker: str | None = None
        if (
            _element_codes_for_marker
            and _current_idx_for_marker + 1 < len(_element_codes_for_marker)
        ):
            _next_for_marker = _element_codes_for_marker[_current_idx_for_marker + 1]
        await _set_element_transition_marker(
            conversation_id=conversation_id,
            element_code=element_code,
            next_element_code=_next_for_marker,
        )

    element_data_status = case_state.get("element_data_status", {}).copy()

    if fields:
        element_data_status[element_code] = ELEMENT_STATUS_PHOTOS_DONE
        new_fsm_state = build_case_update(
            fsm_state,
            {
                "element_phase": "data",
                "element_data_status": element_data_status,
            },
        )

        from agent.services.collection_mode import (
            CollectionMode,
            FieldInfo,
            determine_collection_mode,
            get_fields_for_mode,
            format_batch_prompt,
        )

        field_infos = [FieldInfo.from_db_field(f) for f in fields]
        collection_mode = determine_collection_mode(field_infos)
        fields_structure = get_fields_for_mode(collection_mode, field_infos)

        response: dict[str, Any] = {
            "success": True,
            "element_code": element_code,
            "element_name": element.name,
            "photos_confirmed": True,
            "has_required_fields": True,
            "total_fields": len(fields),
            "next_phase": "data",
            "collection_mode": collection_mode.value,
            "case_collection_update": new_fsm_state,
            "element_phase": "data",
            "current_element_index": case_state.get("current_element_index", 0),
            "_state_update": {
                "fotos_elemento_registered": True,
                "can_narrate_next_element": False,
                "all_elements_complete": False,
                "delivery_outcome_status": "not_requested",
            },
        }
        response.update(fields_structure)

        if collection_mode == CollectionMode.SEQUENTIAL:
            current_field = fields_structure.get("current_field", {})
            instruction = current_field.get("instruction", "")
            fk = current_field.get("field_key", "")
            fl = current_field.get("field_label", "")
            options = current_field.get("options")
            example = current_field.get("example")
            options_text = f" (opciones: {', '.join(options)})" if options else ""
            example_text = f" (ej: {example})" if example else ""
            response["message"] = (
                f"Fotos de {element.name} confirmadas. Ahora necesito algunos datos.\n\n"
                f"📋 CAMPO A RECOGER:\n"
                f"• Nombre: {fl}\n"
                f"• Field key a usar: '{fk}'\n"
                f"• Guía interna (reformula en lenguaje sencillo): {instruction}{options_text}{example_text}\n\n"
                f"⚠️ IMPORTANTE: Al guardar con guardar_datos_elemento(), USA EXACTAMENTE el field_key '{fk}'"
            )
        else:
            batch_fields = fields_structure.get("fields", [])
            batch_prompt = format_batch_prompt(batch_fields, element.name)
            response["message"] = (
                f"Fotos de {element.name} confirmadas. "
                f"Ahora necesito algunos datos.\n\n{batch_prompt}\n\n"
                f"El usuario puede responder todo junto o uno por uno."
            )

        return response

    else:
        # No required fields — mark element as complete
        element_data_status[element_code] = ELEMENT_STATUS_COMPLETE
        element_codes = case_state.get("element_codes", [])
        all_done = all(
            element_data_status.get(code) == ELEMENT_STATUS_COMPLETE
            for code in element_codes
        )

        if all_done:
            new_fsm_state = set_collection_step(fsm_state, CollectionStep.COLLECT_BASE_DOCS)
            new_fsm_state = build_case_update(
                new_fsm_state, {"element_data_status": element_data_status}
            )
            return {
                "success": True,
                "element_code": element_code,
                "photos_confirmed": True,
                "has_required_fields": False,
                "element_complete": True,
                "all_elements_complete": True,
                "next_step": "COLLECT_BASE_DOCS",
                "case_collection_update": new_fsm_state,
                "current_element_index": case_state.get("current_element_index", 0),
                "message": (
                    f"Fotos de {element.name} recibidas ✅\n\n"
                    "Este elemento NO tiene datos técnicos adicionales que recoger. "
                    "NO pidas marca, modelo, medidas ni ningún otro dato técnico al usuario.\n\n"
                    "Todos los elementos están completos."
                ),
                "_state_update": {
                    "fotos_elemento_registered": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": True,
                    "delivery_outcome_status": "not_requested",
                },
            }
        else:
            current_idx = case_state.get("current_element_index", 0)
            next_idx = current_idx + 1
            next_element = (
                element_codes[next_idx] if next_idx < len(element_codes) else None
            )
            new_fsm_state = build_case_update(
                fsm_state,
                {
                    "current_element_index": next_idx,
                    "element_phase": "photos",
                    "element_data_status": element_data_status,
                },
            )
            return {
                "success": True,
                "element_code": element_code,
                "photos_confirmed": True,
                "has_required_fields": False,
                "element_complete": True,
                "all_elements_complete": False,
                "next_element": next_element,
                "case_collection_update": new_fsm_state,
                "element_phase": "photos",
                "current_element_index": next_idx,
                "message": (
                    f"Fotos de {element.name} recibidas ✅\n\n"
                    "Este elemento NO tiene datos técnicos adicionales que recoger. "
                    "NO pidas marca, modelo, medidas ni ningún otro dato técnico al usuario.\n\n"
                    "Pasamos al siguiente elemento."
                ),
                "_state_update": {
                    "fotos_elemento_registered": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": False,
                    "delivery_outcome_status": "not_requested",
                },
            }


async def complete_current_element(
    case_id: str,
    category_id: str,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """Mark the current element as complete and advance to the next one."""
    from agent.services.case_image_batch_service import get_case_image_batch_service

    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=case_id,
        category_id=category_id,
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )
    fsm_state = mode_context.get("fsm_state")

    element_code = _get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    element_data_status = case_state.get("element_data_status", {})

    # Idempotency guard
    if element_data_status.get(element_code) == ELEMENT_STATUS_COMPLETE:
        logger.info(
            "element_data_service.complete_element_idempotent",
            element_code=element_code,
        )
        element_codes = case_state.get("element_codes", [])
        current_idx = case_state.get("current_element_index", 0)

        if current_idx + 1 < len(element_codes):
            next_code = element_codes[current_idx + 1]
            return {
                "success": True,
                "element_code": element_code,
                "element_complete": True,
                "already_completed": True,
                "all_elements_complete": False,
                "next_element_code": next_code,
                "message": f"Elemento {element_code} ya está completado. Siguiente: {next_code}.",
                "_state_update": {
                    "elemento_completed": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": False,
                },
            }
        else:
            return {
                "success": True,
                "element_code": element_code,
                "element_complete": True,
                "already_completed": True,
                "all_elements_complete": True,
                "message": f"Elemento {element_code} ya está completado. Todos los elementos listos.",
                "_state_update": {
                    "elemento_completed": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": True,
                },
            }

    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))
    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
    collected_values = case_element.field_values or {}

    missing_required: list[str] = []
    missing_field_keys: list[str] = []
    for field in fields:
        if not evaluate_field_condition(field, collected_values, fields):
            continue
        if field.is_required and field.field_key not in collected_values:
            missing_required.append(field.field_label)
            missing_field_keys.append(field.field_key)

    if missing_required:
        fields_detail = [
            f"{label} (field_key={key})"
            for label, key in zip(missing_required, missing_field_keys)
        ]
        return _tool_error_response(
            f"Faltan campos obligatorios: {', '.join(fields_detail)}. "
            "Recógelos antes de completar el elemento usando los field_keys indicados."
        )

    await _update_case_element_data(
        case_id,
        element_code,
        {"status": "completed", "data_completed_at": datetime.now(UTC)},
    )

    # T-20: Delete the Redis transition marker now that the element index is
    # being advanced. The marker served its purpose (deterministic attribution
    # of photos to the next element). Explicit cleanup prevents stale reads.
    _conv_id_for_delete = mode_context.get("conversation_id")
    if _conv_id_for_delete:
        await _delete_element_transition_marker(
            conversation_id=_conv_id_for_delete,
            element_code=element_code,
        )

    # V2: mark complete in ElementStateService
    _v2_all_done: bool | None = None
    _v2_next_element_code: str | None = None
    _v2_next_element_index: int | None = None
    try:
        from agent.services.element_state_service import get_element_state_service

        _ess = get_element_state_service()
        await _ess.mark_element_complete(case_id, element_code)
        _element_codes_v2 = case_state.get("element_codes", [])
        _v2_next_code = await _ess.advance_to_next_element(case_id, _element_codes_v2)
        _v2_next_element_code = _v2_next_code
        _v2_all_done = _v2_next_code is None
        if _v2_next_code and _v2_next_code in _element_codes_v2:
            _v2_next_element_index = _element_codes_v2.index(_v2_next_code)
    except Exception as _ess_err:
        logger.warning(
            "element_data_service.complete_element_v2_failed",
            element_code=element_code,
            error=str(_ess_err),
        )

    element_data_status = case_state.get("element_data_status", {}).copy()
    element_data_status[element_code] = ELEMENT_STATUS_COMPLETE
    element_codes = case_state.get("element_codes", [])

    all_done: bool
    if _v2_all_done is not None:
        all_done = _v2_all_done
    else:
        all_done = all(
            element_data_status.get(code) == ELEMENT_STATUS_COMPLETE
            for code in element_codes
        )

    # Finalize current element batch
    batch_service = get_case_image_batch_service()
    try:
        finalized_batch_id = await batch_service.finalize_for_scope(
            case_id=case_id,
            expediente_sub_mode="collect_element_data",
            element_code=element_code,
            status="completed",
        )
        logger.info(
            "element_data_service.complete_element_batch_finalized",
            case_id=case_id,
            element_code=element_code,
            finalized_batch_id=finalized_batch_id,
        )
    except Exception as _fin_err:
        logger.warning(
            "element_data_service.complete_element_batch_finalize_failed",
            case_id=case_id,
            element_code=element_code,
            error=str(_fin_err),
        )

    if all_done:
        # Open base-docs batch
        try:
            await batch_service.open_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                opened_at=datetime.now(UTC),
            )
        except Exception:
            pass

        new_fsm_state = set_collection_step(fsm_state, CollectionStep.COLLECT_BASE_DOCS)
        new_fsm_state = build_case_update(
            new_fsm_state, {"element_data_status": element_data_status}
        )
        return {
            "success": True,
            "element_code": element_code,
            "element_complete": True,
            "all_elements_complete": True,
            "next_step": "COLLECT_BASE_DOCS",
            "case_collection_update": new_fsm_state,
            "current_element_index": case_state.get("current_element_index", 0),
            "message": "Todos los elementos registrados correctamente.",
            "_state_update": {
                "elemento_completed": True,
                "can_narrate_next_element": True,
                "all_elements_complete": True,
            },
        }
    else:
        current_idx = case_state.get("current_element_index", 0)
        if _v2_next_element_index is not None:
            next_idx = _v2_next_element_index
        else:
            next_idx = current_idx + 1
        next_element = (
            _v2_next_element_code
            if _v2_next_element_code is not None
            else (element_codes[next_idx] if next_idx < len(element_codes) else None)
        )

        new_fsm_state = build_case_update(
            fsm_state,
            {
                "current_element_index": next_idx,
                "element_phase": "photos",
                "element_data_status": element_data_status,
            },
        )

        next_element_obj = None
        if next_element:
            next_element_obj = await _get_element_by_code(next_element, category_id)

        # Open next-element batch
        if next_element:
            try:
                await batch_service.open_for_scope(
                    case_id=case_id,
                    expediente_sub_mode="collect_element_data",
                    element_code=next_element,
                    opened_at=datetime.now(UTC),
                )
            except Exception:
                pass

        return {
            "success": True,
            "element_code": element_code,
            "element_complete": True,
            "all_elements_complete": False,
            "next_element_code": next_element,
            "next_element_name": next_element_obj.name if next_element_obj else None,
            "progress": {
                "completed": sum(
                    1 for s in element_data_status.values()
                    if s == ELEMENT_STATUS_COMPLETE
                ),
                "total": len(element_codes),
            },
            "case_collection_update": new_fsm_state,
            "element_phase": "photos",
            "current_element_index": next_idx,
            "message": f"{element.name} completado ✅",
            "_state_update": {
                "elemento_completed": True,
                "can_narrate_next_element": True,
                "all_elements_complete": False,
            },
        }


async def get_element_progress(
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """Return a progress summary for all elements in the current collection."""
    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=mode_context.get("case_id"),
        category_id=mode_context.get("category_id"),
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )
    progress = _get_element_collection_progress(case_state)
    return {
        "success": True,
        **progress,
        "message": (
            f"Progreso: {progress['completed_elements']}/{progress['total_elements']} "
            f"elementos completados. "
            f"Elemento actual: {progress['current_element_code']} ({progress['current_phase']})."
        ),
    }


async def perform_escalation(
    conversation_id: str,
    reason: str,
    source: str = "auto",
    is_technical_error: bool = False,
) -> None:
    """Thin wrapper around escalation_service.perform_escalation — patchable at module level."""
    from agent.services.escalation_service import perform_escalation as _perform_escalation

    await _perform_escalation(
        conversation_id=conversation_id,
        reason=reason,
        source=source,
        is_technical_error=is_technical_error,
    )


async def confirm_base_documentation(
    usuario_confirma: bool | None,
    case_id: str,
    conversation_id: str | None,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """Confirm that base vehicle documentation has been received."""
    from agent.services.case_image_batch_service import (
        build_upload_scope,
        get_case_image_batch_service,
    )

    fsm_state = mode_context.get("fsm_state")
    current_step_val = mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value)
    try:
        current_step = CollectionStep(current_step_val)
    except ValueError:
        current_step = CollectionStep.IDLE

    # Already past this step — idempotent
    past_steps = [
        CollectionStep.COLLECT_PERSONAL,
        CollectionStep.COLLECT_VEHICLE,
        CollectionStep.COLLECT_WORKSHOP,
        CollectionStep.REVIEW_SUMMARY,
        CollectionStep.COMPLETED,
    ]
    if current_step in past_steps:
        logger.info(
            "element_data_service.confirm_base_docs_idempotent",
            current_step=current_step.value,
        )
        return {
            "success": True,
            "base_docs_confirmed": True,
            "already_confirmed": True,
            "message": "La documentación base ya fue confirmada. Continuamos con el expediente.",
            "_state_update": {
                "base_docs_registered": True,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    if current_step != CollectionStep.COLLECT_BASE_DOCS:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_BASE_DOCS. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    base_doc_descriptions = mode_context.get("base_doc_descriptions") or []
    category_id = mode_context.get("category_id")

    # Authoritative minimum: DB count + floor setting (replaces old max(len, 2))
    min_required_images = await _get_base_docs_min_required(
        case_id=case_id,
        category_id=category_id,
        base_doc_descriptions=base_doc_descriptions,
    )

    # Resolve batch scope
    batch_service = get_case_image_batch_service()
    active_base_batch_id: str | None = None
    try:
        active_scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode="collect_base_docs",
            element_code=None,
        )
        active_batch = (
            await batch_service.resolve_for_scope(active_scope, allow_create=False)
            if active_scope
            else None
        )
        active_base_batch_id = active_batch.batch_id if active_batch else None
    except Exception:
        pass

    image_count = await _get_case_image_count(case_id, active_base_batch_id)

    logger.info(
        "element_data_service.confirm_base_docs_called",
        case_id=case_id,
        image_count=image_count,
        min_required=min_required_images,
        usuario_confirma=usuario_confirma,
    )

    async def _advance_to_personal(confirmed_count: int) -> dict[str, Any]:
        try:
            await batch_service.finalize_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                status="confirmed",
            )
        except Exception:
            pass
        new_fsm = build_case_update(fsm_state, {"base_docs_received": True})
        new_fsm = set_collection_step(new_fsm, CollectionStep.COLLECT_PERSONAL)
        return {
            "success": True,
            "base_docs_confirmed": True,
            "images_received": confirmed_count,
            "next_step": "COLLECT_PERSONAL",
            "case_collection_update": new_fsm,
            "base_docs_received": True,
            "message": "Documentación base recibida y registrada correctamente.",
            "_state_update": {
                "base_docs_registered": True,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    # Fast path: already enough images
    if image_count >= min_required_images:
        return await _advance_to_personal(image_count)

    if usuario_confirma is True:
        # Two-phase polling: send feedback, wait phase1, recheck, wait phase2, recheck
        poller = TwoPhasePoller(
            count_fn=lambda: _get_case_image_count(case_id, active_base_batch_id),
            feedback_message="Procesando tus documentos, un momento... ⏳",
            conversation_id=conversation_id,
            user_phone=mode_context.get("user_phone", ""),
        )
        poll_result = await poller.poll(min_required=min_required_images)
        final_count = poll_result.count

        logger.info(
            "element_data_service.confirm_base_docs_poll_result",
            case_id=case_id,
            final_count=final_count,
            phase_reached=poll_result.phase_reached,
            min_required=min_required_images,
        )

        if final_count >= min_required_images:
            return await _advance_to_personal(final_count)

        # Both phases exhausted — escalate silently
        if conversation_id:
            try:
                await perform_escalation(
                    conversation_id=conversation_id,
                    reason=(
                        f"El usuario indica que ha enviado imágenes (case_id={case_id}) "
                        "pero el sistema no las ha recibido tras espera de dos fases. "
                        "Posible problema técnico de Chatwoot/WhatsApp."
                    ),
                    source="auto",
                    is_technical_error=True,
                )
            except Exception as _esc_err:
                logger.error(
                    "element_data_service.image_receipt_escalation_failed",
                    case_id=case_id,
                    error=str(_esc_err),
                )

        try:
            await batch_service.finalize_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                status="confirmed",
            )
        except Exception:
            pass

        return {
            "success": False,
            "escalated": True,
            "images_received": final_count,
            "current_step": "collect_base_docs",
            "message": (
                "He registrado una incidencia con la recepción de documentos. "
                "Un agente humano revisará el caso. Mientras tanto, puedes "
                "intentar reenviar los documentos."
            ),
            "_state_update": {
                "base_docs_registered": False,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    # Not enough images, user hasn't confirmed yet
    expected_docs = base_doc_descriptions or ["los documentos requeridos"]
    missing_docs_lines = "\n".join(f"• {doc}" for doc in expected_docs)
    return {
        "success": False,
        "needs_confirmation": True,
        "images_received": image_count,
        "current_step": current_step.value,
        "message": (
            "¿Has enviado ya la documentación base?\n\n"
            f"Necesito estos documentos para continuar:\n{missing_docs_lines}\n\n"
        ),
        "guidance": (
            "Si el usuario confirma que sí ha enviado los documentos, "
            "llama de nuevo a confirmar_documentacion_base(usuario_confirma=True). "
            "Si dice que no, pídele que los envíe."
        ),
    }


async def resend_element_images(
    element_code: str | None,
    case_id: str,
    category_id: str,
    mode_context: dict[str, Any],
    conversation_id: str,
) -> dict[str, Any]:
    """Return element images so the tool wrapper can forward them to the user."""
    case_state = CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=case_id,
        category_id=category_id,
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        category_slug=mode_context.get("category_slug"),
    )

    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    element_basic = await _get_element_by_code(element_code, category_id, load_images=False)
    if not element_basic:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    from agent.services.element_service import get_element_service

    element_service = get_element_service()
    element_details = await element_service.get_element_with_images(str(element_basic.id))

    if not element_details:
        return _tool_error_response(
            f"No se pudieron obtener detalles del elemento '{element_code}'"
        )

    example_images = []
    for img in element_details.get("images", []):
        if img.get("status") == "active":
            example_images.append(
                {
                    "url": img["image_url"],
                    "tipo": "elemento",
                    "elemento": element_details["name"],
                    "descripcion": img.get("description") or "",
                    "display_order": img.get("sort_order", 0),
                    "status": "active",
                }
            )

    example_images.sort(key=lambda x: x.get("display_order", 0))

    logger.info(
        "element_data_service.resend_element_images",
        image_count=len(example_images),
        element_code=element_code,
        conversation_id=conversation_id,
    )

    element_name = element_details["name"]
    element_description = element_details.get("description")

    return {
        "success": True,
        "element_code": element_code,
        "element_name": element_name,
        "example_images": example_images,
        "description": element_description,
        "should_send_images": len(example_images) > 0,
        "message": (
            f"Aquí tienes las imágenes de ejemplo para {element_name}. "
            "Envíame fotos similares de tu vehículo."
        )
        if example_images
        else (
            f"No hay imágenes de ejemplo configuradas para {element_name}. "
            "Envíame fotos del elemento instalado en tu vehículo."
        ),
        "_pending_images": {"images": example_images} if example_images else None,
    }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_element_data_service() -> "ElementDataService":
    """Return a singleton ElementDataService instance (for DI)."""
    return ElementDataService()


class ElementDataService:
    """
    Thin class wrapper exposing the module-level functions as methods.

    Useful for dependency injection and mocking in tests.
    All heavy lifting is done by the module-level async functions above.
    """

    async def get_element_fields(self, *args, **kwargs):  # type: ignore[override]
        return await get_element_fields(*args, **kwargs)

    async def save_element_data(self, *args, **kwargs):  # type: ignore[override]
        return await save_element_data(*args, **kwargs)

    async def confirm_element_photos(self, *args, **kwargs):  # type: ignore[override]
        return await confirm_element_photos(*args, **kwargs)

    async def complete_current_element(self, *args, **kwargs):  # type: ignore[override]
        return await complete_current_element(*args, **kwargs)

    async def get_element_progress(self, *args, **kwargs):  # type: ignore[override]
        return await get_element_progress(*args, **kwargs)

    async def confirm_base_documentation(self, *args, **kwargs):  # type: ignore[override]
        return await confirm_base_documentation(*args, **kwargs)

    async def resend_element_images(self, *args, **kwargs):  # type: ignore[override]
        return await resend_element_images(*args, **kwargs)

    # Expose pure helpers for test access
    validate_field_value = staticmethod(validate_field_value)
    evaluate_field_condition = staticmethod(evaluate_field_condition)
    get_element_collection_progress = staticmethod(_get_element_collection_progress)
