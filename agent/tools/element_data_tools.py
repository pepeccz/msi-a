"""
MSI Automotive - Element Data Collection Tools for LangGraph Agent.

Tools for collecting element-specific photos and required field data
during case creation. Implements the element-by-element collection flow.

Flow per element:
1. Show example images for the element
2. User sends photos (can be batched)
3. User says "listo" -> confirmar_fotos_elemento()
4. Ask required data fields (one by one or multiple)
5. Validate and save with guardar_datos_elemento()
6. Move to next element with siguiente_elemento()

# TODO(hardening): migrate to canonical _internal_flags contract
# All tools in this module use the legacy ``fsm_state_update`` pattern to
# signal state changes.  They should be migrated to return canonical
# ``_internal_flags`` and/or ``_context_updates`` dicts so that
# ``base_mode._audit_tool_result_contract()`` can track them and
# ``mode_context_keys`` validation fully covers their output.
"""

import asyncio
import structlog
import uuid
from datetime import datetime, UTC
from typing import Any

from langchain_core.tools import tool

from agent.utils.expediente_types import (
    CaseFSMState,
    CollectionStep,
    ELEMENT_STATUS_PENDING,
    ELEMENT_STATUS_PHOTOS_DONE,
    ELEMENT_STATUS_COMPLETE,
)
from agent.state.helpers import get_current_state
from agent.utils.errors import ErrorCategory
from agent.utils.tool_helpers import tool_error_response
from agent.services.case_image_batch_service import (
    build_upload_scope,
    get_case_image_batch_service,
)
from database.connection import get_async_session
from database.models import Case, CaseElementData, Element, ElementRequiredField

logger = structlog.get_logger(__name__)

from shared.config import get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Turn-level idempotency guard for confirmar_fotos_elemento (REQ-IMG-3).
#
# Key format: "{case_id}:{element_code}"
# The set lives at module scope and resets between Python process restarts.
# Within a single agent process turn, this prevents the LLM from calling
# confirmar_fotos_elemento() twice and double-advancing the element phase.
#
# This is intentionally NOT Redis-backed: the guard is per-turn (in-memory)
# and process restarts are a natural boundary.  Redis would add latency for
# a problem that only manifests within a single graph execution turn.
# ─────────────────────────────────────────────────────────────────────────────
_photos_confirmed_this_turn: set[str] = set()


# =============================================================================
# Module-level helpers replacing fsm_compat wrappers
# =============================================================================


def _get_mode_context() -> CaseFSMState:
    """Read expediente state from current mode_context (replaces get_case_fsm_state)."""
    state = get_current_state()
    if not state:
        return CaseFSMState(
            step=CollectionStep.IDLE.value,
            case_id=None,
            element_codes=[],
            current_element_index=0,
            element_phase="photos",
            element_data_status={},
            category_id=None,
            category_slug=None,
            base_docs_received=False,
            base_doc_descriptions=[],
        )
    mode_context = state.get("mode_context", {})
    if state.get("current_mode") != "EXPEDIENTE_MODE":
        return CaseFSMState(
            step=CollectionStep.IDLE.value,
            case_id=None,
            element_codes=[],
            current_element_index=0,
            element_phase="photos",
            element_data_status={},
            category_id=None,
            category_slug=None,
            base_docs_received=False,
            base_doc_descriptions=[],
        )
    return CaseFSMState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=mode_context.get("case_id"),
        category_slug=mode_context.get("category_slug"),
        category_id=mode_context.get("category_id"),
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
    )


def _get_current_step_from_context() -> CollectionStep:
    """Get current collection step from mode_context (replaces get_current_step)."""
    mc = _get_mode_context()
    step_val = mc.get("step", CollectionStep.IDLE.value)
    try:
        return CollectionStep(step_val)
    except ValueError:
        return CollectionStep.IDLE


def _update_fsm_state(
    fsm_state: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Update case collection FSM state with MERGE semantics (ADR-006).

    Chained calls accumulate updates instead of overwriting.

    Returns:
        Dict with "case_collection" key containing merged updates.
    """
    existing: dict[str, Any] = {}
    if isinstance(fsm_state, dict) and "case_collection" in fsm_state:
        existing = dict(fsm_state["case_collection"])
    existing.update(updates)
    return {"case_collection": existing}


def _transition_to_step(
    fsm_state: dict[str, Any] | None,
    target_step: CollectionStep,
) -> dict[str, Any]:
    """Transition to a new FSM step (replaces transition_to)."""
    return _update_fsm_state(fsm_state, {"step": target_step.value})


def _get_current_element_code(case_state: CaseFSMState) -> str | None:
    """Get the current element code being collected."""
    codes = case_state.get("element_codes", [])
    idx = case_state.get("current_element_index", 0)
    return codes[idx] if codes and idx < len(codes) else None


def _get_element_phase(case_state: CaseFSMState) -> str:
    """Get the current phase for element collection: 'photos' or 'data'."""
    return case_state.get("element_phase", "photos")


def _is_current_element_photos_done(case_state: CaseFSMState) -> bool:
    """Check if photos are done for the current element."""
    element_code = _get_current_element_code(case_state)
    if not element_code:
        return False
    status = case_state.get("element_data_status", {}).get(
        element_code, ELEMENT_STATUS_PENDING
    )
    return status in (ELEMENT_STATUS_PHOTOS_DONE, ELEMENT_STATUS_COMPLETE)


def _get_element_collection_progress(case_state: CaseFSMState) -> dict[str, Any]:
    """Get a summary of element collection progress."""
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


# =============================================================================
# Helper Functions
# =============================================================================

from agent.utils.text_utils import normalize_field_key as _normalize_field_key


def _lcp_length(a: str, b: str) -> int:
    """Return length of longest common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


async def _get_element_by_code(
    element_code: str, category_id: str, load_images: bool = False
) -> Element | None:
    """
    Get element by code and category.

    Args:
        element_code: Element code
        category_id: Category UUID
        load_images: If True, eagerly load element.images relationship
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            query = select(Element).where(
                Element.code == element_code,
                Element.category_id == uuid.UUID(category_id),
                Element.is_active == True,  # noqa: E712
            )

            # Eagerly load images if requested to avoid DetachedInstanceError
            if load_images:
                query = query.options(selectinload(Element.images))

            result = await session.execute(query)
            element = result.scalar_one_or_none()

            # Ensure the object is fully loaded before session closes
            if element and load_images:
                # Access images to trigger loading while session is active
                _ = element.images

            return element
    except Exception as e:
        logger.error(
            "database_error_get_element_by_code",
            error=str(e),
            element_code=element_code,
            category_id=category_id,
            load_images=load_images,
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
            "database_error_get_required_fields",
            error=str(e),
            element_id=element_id,
            exc_info=True,
        )
        return []


async def _get_or_create_case_element_data(
    case_id: str,
    element_code: str,
) -> CaseElementData | None:
    """Get or create CaseElementData record for a case-element pair.

    Uses INSERT ... ON CONFLICT DO NOTHING pattern to avoid race conditions
    when multiple concurrent requests try to create the same record.
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import select
            from sqlalchemy.dialects.postgresql import insert

            # Try to insert first (atomic operation with conflict handling)
            insert_stmt = (
                insert(CaseElementData)
                .values(
                    case_id=uuid.UUID(case_id),
                    element_code=element_code,
                    status="pending_photos",
                    field_values={},
                )
                .on_conflict_do_nothing(
                    index_elements=["case_id", "element_code"]  # Unique constraint
                )
            )

            await session.execute(insert_stmt)
            await session.commit()

            # Now fetch the record (either newly inserted or existing)
            result = await session.execute(
                select(CaseElementData)
                .where(CaseElementData.case_id == uuid.UUID(case_id))
                .where(CaseElementData.element_code == element_code)
            )
            record = result.scalar_one_or_none()

            return record
    except Exception as e:
        logger.error(
            "database_error_get_or_create_case_element_data",
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
            "database_error_update_case_element_data",
            error=str(e),
            case_id=case_id,
            element_code=element_code,
            updates=list(updates.keys()),
            exc_info=True,
        )
        return None


def _validate_field_value(
    value: Any,
    field: ElementRequiredField,
) -> tuple[bool, str | None]:
    """
    Validate a field value against its type and validation rules.

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Required check
    if field.is_required and (value is None or value == ""):
        return False, f"El campo '{field.field_label}' es obligatorio"

    # Skip validation if empty and not required
    if value is None or value == "":
        return True, None

    # Type validation
    if field.field_type == "number":
        try:
            # Strip common units before converting (LLM sometimes passes "1230 mm" instead of "1230")
            import re

            clean_value = str(value).strip()
            # Remove common units: mm, cm, m, kg, g, cc, cv, hp, kw, €, euros, etc.
            clean_value = re.sub(
                r"\s*(mm|cm|m|kg|g|cc|cv|hp|kw|€|euros?)\s*$",
                "",
                clean_value,
                flags=re.IGNORECASE,
            )
            clean_value = clean_value.strip()

            num_val = float(clean_value)
            rules = field.validation_rules or {}
            # Support both "min"/"max" and "min_value"/"max_value" keys (DB uses latter)
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
            # Case-insensitive matching for select options
            options_lower = {o.lower(): o for o in field.options}
            value_lower = str(value).lower()
            if value_lower not in options_lower:
                return False, f"Valor no válido. Opciones: {', '.join(field.options)}"

    elif field.field_type == "text":
        rules = field.validation_rules or {}
        if "min_length" in rules and len(str(value)) < rules["min_length"]:
            return (
                False,
                f"El texto debe tener al menos {rules['min_length']} caracteres",
            )
        if "max_length" in rules and len(str(value)) > rules["max_length"]:
            return (
                False,
                f"El texto debe tener como máximo {rules['max_length']} caracteres",
            )
        if "pattern" in rules:
            import re

            if not re.match(rules["pattern"], str(value)):
                # Include pattern description or example if available
                pattern_hint = rules.get("pattern_description") or rules.get("example")
                if pattern_hint:
                    return (
                        False,
                        f"El formato no es válido. Ejemplo esperado: {pattern_hint}",
                    )
                return (
                    False,
                    f"El formato no es válido (patrón requerido: {rules['pattern']})",
                )

    return True, None


def _evaluate_field_condition(
    field: ElementRequiredField,
    collected_values: dict[str, Any],
    all_fields: list[ElementRequiredField],
) -> bool:
    """
    Evaluate if a conditional field should be shown.

    Returns:
        True if field should be shown, False otherwise
    """
    if not field.condition_field_id:
        return True  # No condition, always show

    # Find the condition field
    condition_field = next(
        (f for f in all_fields if str(f.id) == str(field.condition_field_id)),
        None,
    )
    if not condition_field:
        # Log this unexpected situation - condition_field_id references a non-existent field
        logger.warning(
            "conditional_field_missing_reference",
            field_key=field.field_key,
            field_id=str(field.id),
            condition_field_id=str(field.condition_field_id),
            available_field_ids=[str(f.id) for f in all_fields],
        )
        return True  # Condition field not found, show by default

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


def _tool_error_response(
    error: str,
    current_step: CollectionStep | str | None = None,
    guidance: str | None = None,
) -> dict[str, Any]:
    """
    Create a standardized error response for tools.

    DEPRECATED: Use tool_error_response() from agent.utils.tool_helpers instead.
    This wrapper is maintained for backward compatibility during migration.

    Args:
        error: Error description
        current_step: Current FSM step (for context)
        guidance: What the LLM should do instead

    Returns:
        Dict with success=False, error, message, and optional fields
    """
    response = {
        "success": False,
        "error": error,
        "message": error,  # For LLM injection
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
# Element Data Collection Tools
# =============================================================================


@tool
async def obtener_campos_elemento(element_code: str | None = None) -> dict[str, Any]:
    """
    Obtener los campos requeridos para el elemento actual o especificado.

    Usa esta herramienta para saber qué datos técnicos necesitas recoger
    del usuario para un elemento específico.

    Args:
        element_code: Código del elemento (opcional, usa el actual si no se especifica)

    Returns:
        Lista de campos requeridos con sus tipos, etiquetas e instrucciones.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    # ── V2 PATH ───────────────────────────────────────────────────────────
    # When EXPEDIENTE_V2_ENABLED, bypass the FSM step check and use
    # ElementStateService as the authoritative source for element state.
    # Returns a CollectionContext with pending fields, progress, and warnings
    # so the LLM can decide the collection strategy without guessing.
    if get_settings().EXPEDIENTE_V2_ENABLED:
        try:
            from agent.services.element_state_service import (
                get_element_state_service as _get_ess_v2,
            )

            mode_context: dict[str, Any] = state.get("mode_context") or {}
            case_id_v2: str | None = mode_context.get("case_id")
            category_id_v2: str | None = mode_context.get("category_id")
            element_codes_v2: list[str] = mode_context.get("element_codes") or []

            if not case_id_v2:
                return _tool_error_response("No hay expediente activo (V2)")

            ess_v2 = _get_ess_v2()

            # If caller passed a specific element_code, return its state only.
            # Otherwise, return the full CollectionContext (all elements + current).
            if element_code:
                el_state = await ess_v2.get_element_state(
                    case_id_v2, element_code, category_id_v2
                )
                if el_state is None:
                    return _tool_error_response(
                        f"Elemento '{element_code}' no encontrado (V2)"
                    )
                pending_fields = [f.to_dict() for f in el_state.pending_fields]
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
                    "total_required": sum(
                        1 for f in el_state.all_fields if f.is_required
                    ),
                    "collected_required": sum(
                        1
                        for f in el_state.all_fields
                        if f.is_required and f.is_collected
                    ),
                    "all_required_collected": not any(
                        f for f in el_state.pending_fields if f.is_required
                    ),
                    "warnings": el_state.warnings,
                    "message": (
                        f"Elemento {element_code} — fase '{el_state.phase}'. "
                        f"{len(pending_fields)} campo(s) pendiente(s)."
                    ),
                    # Store v2_collection_context for the mode to inject into the prompt
                    "v2_collection_context": el_state.to_dict(),
                }

            # No element_code specified → return full CollectionContext
            collection_ctx = await ess_v2.get_collection_context(
                case_id_v2, element_codes_v2, category_id_v2
            )
            ctx_dict = collection_ctx.to_dict()
            current = ctx_dict.get("current_element") or {}
            pending_fields_current = current.get("pending_fields", [])
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
                # Store v2_collection_context for the mode to inject into the prompt
                "v2_collection_context": ctx_dict,
            }

        except Exception as _v2_err:
            logger.error(
                "obtener_campos_elemento_v2_error",
                error=str(_v2_err),
                exc_info=True,
            )
            # Non-fatal: fall through to V1 path
            logger.warning(
                "obtener_campos_elemento_v2_fallback",
                reason="exception in V2 path, falling back to V1",
            )

    # ── V1 PATH (legacy FSM) ──────────────────────────────────────────────
    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()
    current_step = _get_current_step_from_context()

    # Validate we're in the right step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    category_id = case_state.get("category_id")
    if not category_id:
        return _tool_error_response("No hay categoría definida en el expediente")

    case_id = case_state.get("case_id")
    if not case_id:
        return _tool_error_response("No hay expediente activo")

    # Get element
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    # Get required fields
    fields = await _get_required_fields_for_element(str(element.id))

    # Get already collected values
    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response(
            "Error al acceder a los datos del elemento. Intenta de nuevo."
        )
    collected_values = case_element.field_values or {}

    # Build response with fields that should be shown
    fields_info = []
    for field in fields:
        # Check if field should be shown based on conditions
        if not _evaluate_field_condition(field, collected_values, fields):
            continue

        field_info = {
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

    # Calculate progress
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


@tool
async def guardar_datos_elemento(
    datos: dict[str, Any],
    element_code: str | None = None,
) -> dict[str, Any]:
    """
    Guardar datos técnicos para el elemento actual.

    Extrae los valores del mensaje del usuario y guárdalos aquí.
    Puedes guardar múltiples campos a la vez.

    Args:
        datos: Diccionario con los valores de los campos {field_key: value}
        element_code: Código del elemento (opcional, usa el actual si no se especifica)

    Returns:
        Resultado de la validación y guardado de cada campo.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()
    current_step = _get_current_step_from_context()

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Validate phase (should be in "data" phase)
    phase = _get_element_phase(case_state)
    if phase != "data":
        return _tool_error_response(
            f"Estamos en fase '{phase}', no 'data'. "
            "Primero confirma las fotos con confirmar_fotos_elemento().",
            guidance="confirmar_fotos_primero",
        )

    category_id = case_state.get("category_id")
    case_id = case_state.get("case_id")

    if not category_id or not case_id:
        return _tool_error_response("Expediente no configurado correctamente")

    # Get element and fields
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))
    fields_by_key = {f.field_key: f for f in fields}
    # Also create a normalized lookup for fuzzy matching (ñ->n, accents removed)
    fields_by_normalized_key = {_normalize_field_key(f.field_key): f for f in fields}

    # Get current data
    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response(
            "Error al acceder a los datos del elemento. Intenta de nuevo."
        )
    current_values = (
        case_element.field_values.copy() if case_element.field_values else {}
    )

    # Validate and save each field
    results = []
    errors = []
    idempotent_count = 0  # Track fields with unchanged values

    for field_key, value in datos.items():
        # Try exact match first, then normalized match
        field = fields_by_key.get(field_key)
        actual_field_key = field_key  # Key to use for storage

        if not field:
            # Try normalized matching (handles ñ->n, accents, etc.)
            normalized_key = _normalize_field_key(field_key)
            field = fields_by_normalized_key.get(normalized_key)
            if field:
                # Use the actual DB field key for storage
                actual_field_key = field.field_key
                logger.info(
                    "field_key_normalized",
                    field_key_original=field_key,
                    field_key_actual=actual_field_key,
                    element_code=element_code,
                )

        if not field:
            # Fuzzy fallback: substring/contains matching.
            # Handles LLM abbreviations like "modificacion" → "descripcion_modificacion"
            # or "longitud_total" → "nueva_longitud_total".
            normalized_input = _normalize_field_key(field_key)
            candidates: list[tuple[str, ElementRequiredField]] = []
            for norm_key, f_candidate in fields_by_normalized_key.items():
                # Check if input is a substring of a DB key or vice versa
                if normalized_input in norm_key or norm_key in normalized_input:
                    candidates.append((norm_key, f_candidate))

            if len(candidates) == 1:
                # Unambiguous match — use it
                field = candidates[0][1]
                actual_field_key = field.field_key
                logger.info(
                    "Field key fuzzy-matched (substring): '%s' -> '%s'",
                    field_key,
                    actual_field_key,
                    element_code=element_code,
                )
            elif len(candidates) > 1:
                # Ambiguous — multiple substring matches.
                candidate_keys = [c[1].field_key for c in candidates]
                normalized_input = _normalize_field_key(field_key)

                # Apply LCP tie-break: select candidate whose normalized key shares
                # the longest common prefix with the normalized input.
                lcp_scores = [
                    _lcp_length(normalized_input, _normalize_field_key(ck))
                    for ck in candidate_keys
                ]
                best_lcp = max(lcp_scores)
                best_idx = lcp_scores.index(
                    best_lcp
                )  # First index on tie → preserves old behavior
                lcp_selected_key = candidate_keys[best_idx]
                lcp_selected_field = candidates[best_idx][1]

                # Shadow log — fires regardless of strict_mode flag
                logger.warning(
                    "expediente_field_mapping_ambiguous",
                    field_input=field_key,
                    candidates=candidate_keys,
                    selected=lcp_selected_key,
                    strict_mode=get_settings().EXPEDIENTE_STRICT_FIELD_MAPPING,
                    element_code=element_code,
                )

                # Strict mode: block auto-assignment and ask LLM to disambiguate
                if get_settings().EXPEDIENTE_STRICT_FIELD_MAPPING:
                    # Build human-readable label list for the clarification message
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

                # Soft mode (default): use LCP tie-break selection
                field = lcp_selected_field
                actual_field_key = field.field_key
                logger.info(
                    "Field key fuzzy-matched (substring, LCP tie-break): '%s' -> '%s'",
                    field_key,
                    actual_field_key,
                    element_code=element_code,
                )

        if not field:
            results.append(
                {
                    "field_key": field_key,
                    "status": "ignored",
                    "message": f"Campo '{field_key}' no existe para este elemento",
                }
            )
            continue

        # Check condition
        if not _evaluate_field_condition(field, current_values, fields):
            results.append(
                {
                    "field_key": field_key,
                    "status": "skipped",
                    "message": f"Campo '{field_key}' no aplica según las condiciones",
                }
            )
            continue

        # Idempotency guard: Check if field already has this exact value
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
                "guardar_datos_elemento_idempotent_field",
                    element_code=element_code,
                    field_key=actual_field_key,
                element_code=element_code,
                field_key=actual_field_key,
                idempotent=True,
            )
            continue  # Skip validation and DB write

        # Validate
        is_valid, error_msg = _validate_field_value(value, field)
        if not is_valid:
            errors.append(f"{field.field_label}: {error_msg}")
            results.append(
                {
                    "field_key": actual_field_key,
                    "status": "error",
                    "message": error_msg,
                }
            )
        else:
            # Use the actual DB field key for storage
            current_values[actual_field_key] = value
            results.append(
                {
                    "field_key": actual_field_key,
                    "status": "saved",
                    "value": value,
                }
            )

    # Save to database
    await _update_case_element_data(
        case_id,
        element_code,
        {"field_values": current_values},
    )

    # V2: Mirror each saved field value into ElementStateService for DB-authoritative tracking.
    # This runs in addition to the existing dict/FSM path so V1 tools remain unaffected.
    if get_settings().EXPEDIENTE_V2_ENABLED:
        try:
            from agent.services.element_state_service import get_element_state_service

            _ess_v2 = get_element_state_service()
            for _field_key_v2, _field_val_v2 in current_values.items():
                await _ess_v2.record_field_value(
                    case_id, element_code, _field_key_v2, _field_val_v2
                )
        except Exception as _ess_err:
            logger.warning(
                "guardar_datos_elemento_v2_record_field_failed",
                element_code=element_code,
                error=str(_ess_err),
            )
            # Non-fatal: continue with V1 path

    # Check if all required fields are collected
    all_required_collected = True
    missing_fields = []
    for field in fields:
        if not _evaluate_field_condition(field, current_values, fields):
            continue
        if field.is_required and field.field_key not in current_values:
            all_required_collected = False
            missing_fields.append(field.field_label)

    # Use Smart Collection Mode for remaining fields
    from agent.services.collection_mode import (
        CollectionMode,
        FieldInfo,
        determine_collection_mode,
        get_fields_for_mode,
        format_batch_prompt,
        create_error_recovery_response,
    )

    # Collect ignored and ambiguous fields to warn about them prominently
    ignored_fields = [
        r["field_key"] for r in results if r["status"] in ("ignored", "ambiguous")
    ]

    response = {
        "success": len(errors) == 0,
        "element_code": element_code,
        "results": results,
        "saved_count": sum(1 for r in results if r["status"] == "saved"),
        "error_count": len(errors),
        "all_required_collected": all_required_collected,
    }

    # Add CRITICAL error message for ignored fields (not just a warning)
    if ignored_fields:
        valid_field_keys = [f.field_key for f in fields]
        # Make this CRITICAL and imperative so LLM doesn't ignore it
        response["error"] = f"CAMPOS INCORRECTOS: {', '.join(ignored_fields)}"
        response["message"] = (
            f"❌ ERROR CRÍTICO: Los campos {', '.join(ignored_fields)} NO EXISTEN para el elemento {element_code}.\n\n"
            f"DEBES usar EXACTAMENTE estos field_key:\n"
            f"{', '.join(valid_field_keys)}\n\n"
            f"Vuelve a llamar guardar_datos_elemento() con los field_key correctos.\n"
            f"Usa obtener_campos_elemento() si necesitas ver las instrucciones completas."
        )
        # Override success to False when there are ignored fields
        response["success"] = False
        logger.warning(
            "guardar_datos_elemento_ignored_fields",
            ignored_fields=ignored_fields,
            element_code=element_code,
            ignored=ignored_fields,
            valid=valid_field_keys,
        )
        # EARLY RETURN - Don't process further logic if fields were ignored
        return response

    if errors:
        # Build structured error response with recovery guidance
        first_error = results[0] if results else {}
        field_key = first_error.get("field_key")
        field = fields_by_key.get(field_key) if field_key else None

        response["errors"] = errors
        response["recovery"] = {
            "action": "RE_ASK",
            "fields_with_errors": [
                r["field_key"] for r in results if r["status"] == "error"
            ],
            "prompt_suggestion": f"Hubo un problema con algunos datos. {'; '.join(errors)}. Por favor, verifica y vuelve a proporcionar los valores correctos.",
        }
        response["message"] = (
            f"Errores en {len(errors)} campos. Verifica: {'; '.join(errors)}"
        )

    elif missing_fields:
        # Convert remaining fields to FieldInfo for smart mode
        pending_fields = []
        for field in fields:
            if not _evaluate_field_condition(field, current_values, fields):
                continue
            if field.is_required and field.field_key not in current_values:
                pending_fields.append(FieldInfo.from_db_field(field))

        if pending_fields:
            # Re-evaluate collection mode with remaining fields
            collection_mode = determine_collection_mode(pending_fields, current_values)
            fields_structure = get_fields_for_mode(
                collection_mode, pending_fields, current_values
            )

            response["collection_mode"] = collection_mode.value
            response["missing_fields"] = missing_fields
            response.update(fields_structure)

            # Generate message based on mode
            if collection_mode == CollectionMode.SEQUENTIAL:
                current_field = fields_structure.get("current_field", {})
                instruction = current_field.get("instruction", "")
                field_key = current_field.get("field_key", "")
                field_label = current_field.get("field_label", "")
                options = current_field.get("options")
                example = current_field.get("example")

                options_text = f" (opciones: {', '.join(options)})" if options else ""
                example_text = f" (ej: {example})" if example else ""

                # Make field_key explicit in the message
                response["message"] = (
                    f"✅ Datos guardados.\n\n"
                    f"📋 SIGUIENTE CAMPO:\n"
                    f"• Nombre: {field_label}\n"
                    f"• Field key: '{field_key}'\n"
                    f"• Pregunta: {instruction}{options_text}{example_text}\n\n"
                    f"⚠️ Al guardar, usa field_key='{field_key}'"
                )
            else:
                # BATCH or HYBRID
                batch_fields = fields_structure.get("fields", [])
                if batch_fields:
                    # Include field_keys for batch fields
                    field_items = [
                        f"{f['field_label']} (field_key={f['field_key']})"
                        for f in batch_fields
                    ]
                    response["message"] = (
                        f"Datos guardados. Aun faltan: {', '.join(field_items)}"
                    )
                else:
                    response["message"] = (
                        f"Datos guardados. Faltan: {', '.join(missing_fields)}"
                    )
        else:
            response["message"] = (
                f"Datos guardados. Faltan: {', '.join(missing_fields)}"
            )
    else:
        response["message"] = (
            "Todos los datos del elemento han sido guardados correctamente."
        )
        response["action"] = "ELEMENT_DATA_COMPLETE"

    # V2: Enrich response with pending_fields from DB when all required fields are collected.
    # This gives the mode node DB-authoritative signal that data collection is truly done.
    if get_settings().EXPEDIENTE_V2_ENABLED and response.get("all_required_collected"):
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
                "guardar_datos_elemento_v2_pending_fields_failed",
                element_code=element_code,
                error=str(_ess_resp_err),
            )
            # Non-fatal — response.pending_fields simply absent

    return response


@tool
async def confirmar_fotos_elemento(
    usuario_confirma: bool | None = None,
) -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado todas las fotos del elemento actual.

    Usa esta herramienta cuando el usuario diga "listo" o similar
    después de enviar las fotos de un elemento.

    Después de confirmar, automáticamente pasamos a recoger los datos
    técnicos del elemento (si tiene campos requeridos).

    Args:
        usuario_confirma: True si el usuario confirma explícitamente que ya envió
                         las fotos. Solo usa este parámetro si preguntaste al
                         usuario y respondió afirmativamente.

    Returns:
        Estado actualizado y próximo paso.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()
    current_step = _get_current_step_from_context()

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get current element
    element_code = _get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Validate phase (should be in "photos" phase)
    phase = _get_element_phase(case_state)
    if phase != "photos":
        # Idempotency guard: Check if this is a repeat call (photos already confirmed)
        if phase == "data" and _is_current_element_photos_done(case_state):
            logger.info(
                "confirmar_fotos_elemento_idempotent",
            element_code=element_code,
                element_code=element_code,
                idempotent=True,
                phase=phase,
            )
            # Idempotent call — photos were already confirmed in a prior turn.
            # all_elements_complete is unknown at this point (idempotent path),
            # so we conservatively set it to False and can_narrate_next_element to False.
            return {
                "success": True,
                "photos_confirmed": True,
                "already_confirmed": True,
                "element_code": element_code,
                "message": f"Las fotos de {element_code} ya fueron confirmadas. Continuamos con los datos técnicos.",
                "fsm_state_update": fsm_state,  # Return current state unchanged
                "_internal_flags": {
                    "fotos_elemento_registered": True,
                    "can_narrate_next_element": False,
                    "all_elements_complete": False,
                    "delivery_outcome_status": "not_requested",
                },
            }
        # Different error for truly wrong phase
        return _tool_error_response(
            f"Fase incorrecta: {phase}. No se puede confirmar fotos desde esta fase."
        )

    category_id = case_state.get("category_id")
    case_id = case_state.get("case_id")
    conversation_id = state.get("conversation_id")
    batch_service = get_case_image_batch_service()
    active_batch_id: str | None = None

    if not category_id or not case_id:
        return _tool_error_response("Expediente no configurado correctamente")

    # ── V2: Turn-level idempotency guard (REQ-IMG-3) ──────────────────────
    # If this turn already confirmed photos for this element, return early.
    # Prevents the LLM from calling this tool twice and double-advancing state.
    _idempotency_key = f"{case_id}:{element_code}"
    _settings = get_settings()
    if (
        _settings.EXPEDIENTE_V2_ENABLED
        and _idempotency_key in _photos_confirmed_this_turn
    ):
        # Look up element and required fields so the idempotent return
        # carries the same phase/field context as the original call.
        # Without this the LLM loses track of element_phase and field_keys.
        _idemp_element = await _get_element_by_code(element_code, category_id)
        _idemp_fields: list = []
        if _idemp_element:
            _idemp_fields = await _get_required_fields_for_element(
                str(_idemp_element.id)
            )
        _idemp_has_fields = bool(_idemp_fields)
        _idemp_phase = "data" if _idemp_has_fields else "photos"

        logger.info(
            "confirmar_fotos_elemento.idempotent_v2",
            case_id=case_id,
            element_code=element_code,
            idempotency_key=_idempotency_key,
            action="returning_early_same_turn",
            has_required_fields=_idemp_has_fields,
            element_phase=_idemp_phase,
        )

        _idemp_response: dict = {
            "success": True,
            "photos_confirmed": True,
            "idempotent": True,
            "element_code": element_code,
            "element_phase": _idemp_phase,
            "has_required_fields": _idemp_has_fields,
            "current_element_index": case_state.get("current_element_index", 0),
            "message": f"Las fotos de {element_code} ya fueron confirmadas en este turno.",
            "_internal_flags": {
                "fotos_elemento_registered": True,
                "can_narrate_next_element": False,
                "all_elements_complete": False,
                "delivery_outcome_status": "not_requested",
            },
        }

        # If element has required fields, include field_keys so the LLM
        # can continue data collection without losing context.
        if _idemp_has_fields:
            from agent.services.collection_mode import (
                CollectionMode,
                FieldInfo,
                determine_collection_mode,
                get_fields_for_mode,
            )

            _idemp_field_infos = [FieldInfo.from_db_field(f) for f in _idemp_fields]
            _idemp_coll_mode = determine_collection_mode(_idemp_field_infos)
            _idemp_fields_structure = get_fields_for_mode(
                _idemp_coll_mode, _idemp_field_infos
            )
            _idemp_response["total_fields"] = len(_idemp_fields)
            _idemp_response["collection_mode"] = _idemp_coll_mode.value
            _idemp_response.update(_idemp_fields_structure)

        return _idemp_response

    # ── V2: Use ElementStateService for photo count (REQ-IMG-5) ──────────
    # In V2 mode, use the canonical DB-backed count from ElementStateService
    # instead of the legacy _get_element_image_count() helper.
    if _settings.EXPEDIENTE_V2_ENABLED:
        active_scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode="collect_element_data",
            element_code=element_code,
        )
        active_batch = (
            await batch_service.resolve_for_scope(active_scope, allow_create=False)
            if active_scope
            else None
        )
        active_batch_id = active_batch.batch_id if active_batch else None
        try:
            from agent.services.element_state_service import (
                get_element_state_service as _get_ess,
            )

            _ess = _get_ess()
            element_image_count = await _get_element_image_count(
                case_id,
                element_code,
                upload_batch_id=active_batch_id,
            )
        except Exception as _ess_err:
            logger.warning(
                "confirmar_fotos_elemento.v2_photo_count_fallback",
                case_id=case_id,
                element_code=element_code,
                error=str(_ess_err),
                fallback="_get_element_image_count",
            )
            element_image_count = await _get_element_image_count(
                case_id, element_code, active_batch_id
            )
    else:
        element_image_count = await _get_element_image_count(case_id, element_code)

    logger.info(
        "confirmar_fotos_elemento called",
        case_id=case_id,
        element_code=element_code,
        element_image_count=element_image_count,
        usuario_confirma=usuario_confirma,
        v2_enabled=_settings.EXPEDIENTE_V2_ENABLED,
    )

    if element_image_count == 0:
        if usuario_confirma is True:
            # Two-phase blocking poll: WhatsApp image delivery typically takes 5-15s
            # so a single short wait is insufficient. We do:
            #   Phase 1 — wait PHOTO_COMPLETION_WAIT_SECONDS, then check.
            #   Phase 2 — if still 0, wait PHOTO_COMPLETION_RETRY_WAIT_SECONDS, then check once more.
            # Total maximum wait = phase_1 + phase_2 (configurable via env vars).
            from shared.config import get_settings as _get_settings

            _settings = _get_settings()
            phase1_wait = _settings.PHOTO_COMPLETION_WAIT_SECONDS
            phase2_wait = _settings.PHOTO_COMPLETION_RETRY_WAIT_SECONDS

            # Send immediate "processing" feedback before polling begins.
            # "Fire and continue" — non-fatal if Chatwoot send fails.
            try:
                from shared.chatwoot_client import ChatwootClient as _ChatwootClient

                _chatwoot = _ChatwootClient()
                _user_phone = state.get("user_phone", "")
                _conv_id_int: int | None = None
                if conversation_id is not None:
                    try:
                        _conv_id_int = int(conversation_id)
                    except (ValueError, TypeError):
                        _conv_id_int = None
                await _chatwoot.send_message(
                    customer_phone=_user_phone,
                    message="Procesando tus imágenes, un momento... ⏳",
                    conversation_id=_conv_id_int,
                )
                logger.info(
                    "confirmar_fotos_elemento: sent processing feedback message",
                    case_id=case_id,
                    element_code=element_code,
                    conversation_id=conversation_id,
                )
            except Exception as _feedback_err:
                # Non-fatal: polling continues regardless
                logger.warning(
                    "confirmar_fotos_elemento: failed to send processing feedback message",
                    case_id=case_id,
                    element_code=element_code,
                    conversation_id=conversation_id,
                    error=str(_feedback_err),
                )

            # — Phase 1 —
            await asyncio.sleep(phase1_wait)
            element_image_count = await _get_element_image_count(
                case_id, element_code, active_batch_id
            )
            logger.info(
                "confirmar_fotos_elemento: re-checked image count after phase-1 wait",
                case_id=case_id,
                element_code=element_code,
                phase1_wait_seconds=phase1_wait,
                element_image_count_after_phase1=element_image_count,
            )

            if element_image_count == 0:
                # — Phase 2 (single retry) —
                await asyncio.sleep(phase2_wait)
                element_image_count = await _get_element_image_count(
                    case_id, element_code, active_batch_id
                )
                logger.info(
                    "confirmar_fotos_elemento: re-checked image count after phase-2 retry wait",
                    case_id=case_id,
                    element_code=element_code,
                    phase2_wait_seconds=phase2_wait,
                    element_image_count_after_phase2=element_image_count,
                )

            if element_image_count == 0:
                # Still no images after both phases — do NOT advance phase
                return {
                    "success": False,
                    "received": False,
                    "needs_photos": True,
                    "message": (
                        "No he podido recuperar tus fotos, ¿puedes reenviarlas? "
                        "Asegúrate de enviarlas como imagen de WhatsApp, no como documento adjunto."
                    ),
                }
            # Images arrived during one of the wait phases — fall through to normal processing below
        else:
            # No photos received and user hasn't confirmed — ask again
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
                # Failure paths: no _internal_flags as registration did not succeed
            }

    # Get element to check if it has required fields
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    fields = await _get_required_fields_for_element(str(element.id))

    # Update case element data - mark photos as done
    await _update_case_element_data(
        case_id,
        element_code,
        {
            "status": "pending_data" if fields else "completed",
            "photos_completed_at": datetime.now(UTC),
        },
    )

    # ── V2: Register turn-level idempotency key (REQ-IMG-3) ───────────────
    # Photos are now confirmed — register so subsequent calls in this turn
    # are no-ops.  Key is "{case_id}:{element_code}".
    if _settings.EXPEDIENTE_V2_ENABLED:
        _photos_confirmed_this_turn.add(_idempotency_key)
        await batch_service.finalize_for_scope(
            case_id=case_id,
            expediente_sub_mode="collect_element_data",
            element_code=element_code,
            status="confirmed",
        )
        logger.info(
            "confirmar_fotos_elemento.idempotency_key_registered",
            case_id=case_id,
            element_code=element_code,
            idempotency_key=_idempotency_key,
        )

    # Update FSM state
    element_data_status = case_state.get("element_data_status", {}).copy()

    if fields:
        # Has required fields - switch to data phase
        element_data_status[element_code] = ELEMENT_STATUS_PHOTOS_DONE
        new_fsm_state = _update_fsm_state(
            fsm_state,
            {
                "element_phase": "data",
                "element_data_status": element_data_status,
            },
        )

        # Use Smart Collection Mode to determine how to ask for fields
        from agent.services.collection_mode import (
            CollectionMode,
            FieldInfo,
            determine_collection_mode,
            get_fields_for_mode,
            format_batch_prompt,
        )

        # Convert DB fields to FieldInfo objects
        field_infos = [FieldInfo.from_db_field(f) for f in fields]

        # Determine collection mode
        collection_mode = determine_collection_mode(field_infos)

        # Get fields structure based on mode
        fields_structure = get_fields_for_mode(collection_mode, field_infos)

        # Build response based on collection mode
        response = {
            "success": True,
            "element_code": element_code,
            "element_name": element.name,
            "photos_confirmed": True,
            "has_required_fields": True,
            "total_fields": len(fields),
            "next_phase": "data",
            "collection_mode": collection_mode.value,
            "fsm_state_update": new_fsm_state,
            # Defense-in-depth: root-level fields for direct extractors
            "element_phase": "data",
            "current_element_index": case_state.get("current_element_index", 0),
            # Phase 2 canonical certainty flags.
            # Photos are confirmed but element is NOT yet complete (data collection pending).
            # can_narrate_next_element is False because data collection for THIS element
            # is still in progress — the LLM must collect field data first.
            "_internal_flags": {
                "fotos_elemento_registered": True,
                "can_narrate_next_element": False,
                "all_elements_complete": False,
                "delivery_outcome_status": "not_requested",
            },
        }

        # Add mode-specific data
        response.update(fields_structure)

        # Generate appropriate message based on mode
        if collection_mode == CollectionMode.SEQUENTIAL:
            # Single field to ask
            current_field = fields_structure.get("current_field", {})
            instruction = current_field.get("instruction", "")
            field_key = current_field.get("field_key", "")
            field_label = current_field.get("field_label", "")
            options = current_field.get("options")
            example = current_field.get("example")

            options_text = f" (opciones: {', '.join(options)})" if options else ""
            example_text = f" (ej: {example})" if example else ""

            # Make field_key VERY explicit at the start, not just at the end
            response["message"] = (
                f"Fotos de {element.name} confirmadas. Ahora necesito algunos datos.\n\n"
                f"📋 CAMPO A RECOGER:\n"
                f"• Nombre: {field_label}\n"
                f"• Field key a usar: '{field_key}'\n"
                f"• Pregunta al usuario: {instruction}{options_text}{example_text}\n\n"
                f"⚠️ IMPORTANTE: Al guardar con guardar_datos_elemento(), USA EXACTAMENTE el field_key '{field_key}'"
            )
        else:
            # BATCH or HYBRID - multiple fields
            batch_fields = fields_structure.get("fields", [])
            batch_prompt = format_batch_prompt(batch_fields, element.name)

            response["message"] = (
                f"Fotos de {element.name} confirmadas. "
                f"Ahora necesito algunos datos.\n\n{batch_prompt}\n\n"
                f"El usuario puede responder todo junto o uno por uno."
            )

        return response
    else:
        # No required fields - mark element as complete
        element_data_status[element_code] = ELEMENT_STATUS_COMPLETE

        # Check if all elements are done
        element_codes = case_state.get("element_codes", [])
        all_done = all(
            element_data_status.get(code) == ELEMENT_STATUS_COMPLETE
            for code in element_codes
        )

        if all_done:
            # All elements complete - transition to COLLECT_BASE_DOCS
            new_fsm_state = _transition_to_step(
                fsm_state, CollectionStep.COLLECT_BASE_DOCS
            )
            new_fsm_state = _update_fsm_state(
                new_fsm_state,
                {"element_data_status": element_data_status},
            )
            return {
                "success": True,
                "element_code": element_code,
                "photos_confirmed": True,
                "has_required_fields": False,
                "element_complete": True,
                "all_elements_complete": True,
                "next_step": "COLLECT_BASE_DOCS",
                "fsm_state_update": new_fsm_state,
                # Defense-in-depth: root-level fields for direct extractors
                "current_element_index": case_state.get("current_element_index", 0),
                # Anti-hallucination: explicitly tell LLM this element has NO data fields.
                # Without this, the LLM may hallucinate and ask the user for technical data.
                "message": (
                    f"Fotos de {element.name} recibidas ✅\n\n"
                    "Este elemento NO tiene datos técnicos adicionales que recoger. "
                    "NO pidas marca, modelo, medidas ni ningún otro dato técnico al usuario.\n\n"
                    "Todos los elementos están completos."
                ),
                # Phase 2 canonical certainty flags.
                # This element had no required fields, so photos = complete for this element.
                # All elements are done → can narrate transition to base docs.
                "_internal_flags": {
                    "fotos_elemento_registered": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": True,
                    "delivery_outcome_status": "not_requested",
                },
            }
        else:
            # More elements to process
            current_idx = case_state.get("current_element_index", 0)
            next_idx = current_idx + 1
            next_element = (
                element_codes[next_idx] if next_idx < len(element_codes) else None
            )

            new_fsm_state = _update_fsm_state(
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
                "fsm_state_update": new_fsm_state,
                # Defense-in-depth: root-level fields for direct extractors
                "element_phase": "photos",
                "current_element_index": next_idx,
                # Anti-hallucination: explicitly tell LLM this element has NO data fields.
                # Without this, the LLM may hallucinate and ask the user for technical data.
                "message": (
                    f"Fotos de {element.name} recibidas ✅\n\n"
                    "Este elemento NO tiene datos técnicos adicionales que recoger. "
                    "NO pidas marca, modelo, medidas ni ningún otro dato técnico al usuario.\n\n"
                    "Pasamos al siguiente elemento."
                ),
                # Phase 2 canonical certainty flags.
                # This element is complete (no required fields).
                # can_narrate_next_element=True: LLM may prompt user for the next element's photos.
                "_internal_flags": {
                    "fotos_elemento_registered": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": False,
                    "delivery_outcome_status": "not_requested",
                },
            }


@tool
async def completar_elemento_actual() -> dict[str, Any]:
    """
    Marcar el elemento actual como completo y pasar al siguiente.

    Usa esta herramienta cuando todos los datos requeridos del elemento
    han sido recogidos y validados.

    Returns:
        Información sobre el siguiente elemento o paso.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()
    current_step = _get_current_step_from_context()

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get current element
    element_code = _get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Idempotency guard: Check if element already completed
    element_data_status = case_state.get("element_data_status", {})
    if element_data_status.get(element_code) == ELEMENT_STATUS_COMPLETE:
        logger.info(
            "completar_elemento_actual_idempotent",
            element_code=element_code,
            element_code=element_code,
            idempotent=True,
        )
        # Element already complete, check what's next
        element_codes = case_state.get("element_codes", [])
        current_idx = case_state.get("current_element_index", 0)

        # Check if there are more elements or if all done
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
                "fsm_state_update": fsm_state,
                "_internal_flags": {
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
                "fsm_state_update": fsm_state,
                "_internal_flags": {
                    "elemento_completed": True,
                    "can_narrate_next_element": True,
                    "all_elements_complete": True,
                },
            }

    category_id = case_state.get("category_id")
    case_id = case_state.get("case_id")

    if not category_id or not case_id:
        return _tool_error_response("Expediente no configurado correctamente")

    # Get element
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    # Check if all required fields are collected
    fields = await _get_required_fields_for_element(str(element.id))
    case_element = await _get_or_create_case_element_data(case_id, element_code)
    if not case_element:
        return _tool_error_response(
            "Error al acceder a los datos del elemento. Intenta de nuevo."
        )
    collected_values = case_element.field_values or {}

    missing_required = []
    missing_field_keys = []
    for field in fields:
        if not _evaluate_field_condition(field, collected_values, fields):
            continue
        if field.is_required and field.field_key not in collected_values:
            missing_required.append(field.field_label)
            missing_field_keys.append(field.field_key)

    if missing_required:
        # Build detailed error message with field_keys
        fields_detail = [
            f"{label} (field_key={key})"
            for label, key in zip(missing_required, missing_field_keys)
        ]
        return _tool_error_response(
            f"Faltan campos obligatorios: {', '.join(fields_detail)}. "
            "Recógelos antes de completar el elemento usando los field_keys indicados."
        )

    # Mark element as complete in database
    await _update_case_element_data(
        case_id,
        element_code,
        {
            "status": "completed",
            "data_completed_at": datetime.now(UTC),
        },
    )

    # V2: Also mark complete in ElementStateService and derive next element from DB.
    # Runs alongside V1 FSM path — if V2 is enabled we can override next_element and
    # all_done with DB-authoritative values; V1 FSM still updates for tool compatibility.
    _v2_all_done: bool | None = None
    _v2_next_element_code: str | None = None
    _v2_next_element_index: int | None = None
    if get_settings().EXPEDIENTE_V2_ENABLED:
        try:
            from agent.services.element_state_service import get_element_state_service

            _ess_completar = get_element_state_service()
            await _ess_completar.mark_element_complete(case_id, element_code)
            _element_codes_v2 = case_state.get("element_codes", [])
            _v2_next_code = await _ess_completar.advance_to_next_element(
                case_id, _element_codes_v2
            )
            _v2_next_element_code = _v2_next_code
            _v2_all_done = _v2_next_code is None
            if _v2_next_code and _v2_next_code in _element_codes_v2:
                _v2_next_element_index = _element_codes_v2.index(_v2_next_code)
            logger.debug(
                "completar_elemento_v2",
                element_code=element_code,
                next_code=_v2_next_code,
                all_done=_v2_all_done,
            )
        except Exception as _ess_comp_err:
            logger.warning(
                "completar_elemento_v2_failed",
                element_code=element_code,
                error=str(_ess_comp_err),
            )
            # Fallback: V1 dict-based logic determines all_done / next element

    # Update FSM state
    element_data_status = case_state.get("element_data_status", {}).copy()
    element_data_status[element_code] = ELEMENT_STATUS_COMPLETE
    element_codes = case_state.get("element_codes", [])

    # Check if all elements are complete (V2 DB-authoritative when available)
    all_done: bool
    if _v2_all_done is not None:
        all_done = _v2_all_done
    else:
        all_done = all(
            element_data_status.get(code) == ELEMENT_STATUS_COMPLETE
            for code in element_codes
        )

    # Belt-and-suspenders: ensure the completing element's batch is finalized
    # BEFORE opening the next-element batch (or the base-docs batch).
    # This closes the race window where assign_upload_batch() could still find
    # the first-element batch open (finalized_at IS NULL) and incorrectly reuse
    # it for second-element photos arriving during live ingest.
    # finalize_for_scope() is idempotent — already-finalized batches are silently
    # skipped (returns None), so calling it here is always safe.
    if get_settings().EXPEDIENTE_V2_ENABLED:
        try:
            finalized_batch_id = (
                await get_case_image_batch_service().finalize_for_scope(
                    case_id=case_id,
                    expediente_sub_mode="collect_element_data",
                    element_code=element_code,
                    status="completed",
                )
            )
            logger.info(
                "completar_elemento_actual.batch_finalized",
                case_id=case_id,
                element_code=element_code,
                finalized_batch_id=finalized_batch_id,
            )
        except Exception as _fin_err:
            # Non-fatal: log and continue — the is_live_ingest guard in
            # resolve_for_scope() provides a second layer of protection.
            logger.warning(
                "completar_elemento_actual.batch_finalize_failed",
                case_id=case_id,
                element_code=element_code,
                error=str(_fin_err),
            )

    if all_done:
        if get_settings().EXPEDIENTE_V2_ENABLED:
            await get_case_image_batch_service().open_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                opened_at=datetime.now(UTC),
            )
        # All elements complete - transition to COLLECT_BASE_DOCS
        new_fsm_state = _transition_to_step(fsm_state, CollectionStep.COLLECT_BASE_DOCS)
        new_fsm_state = _update_fsm_state(
            new_fsm_state,
            {"element_data_status": element_data_status},
        )
        return {
            "success": True,
            "element_code": element_code,
            "element_complete": True,
            "all_elements_complete": True,
            "next_step": "COLLECT_BASE_DOCS",
            "fsm_state_update": new_fsm_state,
            # Defense-in-depth: root-level fields for direct extractors
            "current_element_index": case_state.get("current_element_index", 0),
            # Neutral message: no description of next sub-mode (anti-anticipation fix)
            "message": "Todos los elementos registrados correctamente.",
            # Phase 2 canonical certainty flags.
            "_internal_flags": {
                "elemento_completed": True,
                "can_narrate_next_element": True,
                "all_elements_complete": True,
            },
        }
    else:
        # More elements to process — V2: prefer DB-derived next element index
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

        new_fsm_state = _update_fsm_state(
            fsm_state,
            {
                "current_element_index": next_idx,
                "element_phase": "photos",
                "element_data_status": element_data_status,
            },
        )

        # Get next element info
        next_element_obj = None
        if next_element:
            next_element_obj = await _get_element_by_code(next_element, category_id)
        if get_settings().EXPEDIENTE_V2_ENABLED and next_element:
            await get_case_image_batch_service().open_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_element_data",
                element_code=next_element,
                opened_at=datetime.now(UTC),
            )

        return {
            "success": True,
            "element_code": element_code,
            "element_complete": True,
            "all_elements_complete": False,
            "next_element_code": next_element,
            "next_element_name": next_element_obj.name if next_element_obj else None,
            "progress": {
                "completed": sum(
                    1
                    for s in element_data_status.values()
                    if s == ELEMENT_STATUS_COMPLETE
                ),
                "total": len(element_codes),
            },
            "fsm_state_update": new_fsm_state,
            # Defense-in-depth: root-level fields for direct extractors
            "element_phase": "photos",
            "current_element_index": next_idx,
            # Neutral message: no mention of next element (anti-anticipation fix)
            "message": f"{element.name} completado ✅",
            # Phase 2 canonical certainty flags.
            "_internal_flags": {
                "elemento_completed": True,
                "can_narrate_next_element": True,
                "all_elements_complete": False,
            },
        }


@tool
async def obtener_progreso_elementos() -> dict[str, Any]:
    """
    Obtener el progreso actual de la recolección de elementos.

    Returns:
        Información sobre el progreso de cada elemento.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()

    progress = _get_element_collection_progress(case_state)

    return {
        "success": True,
        **progress,
        "message": (
            f"Progreso: {progress['completed_elements']}/{progress['total_elements']} elementos completados. "
            f"Elemento actual: {progress['current_element_code']} ({progress['current_phase']})."
        ),
    }


async def _get_case_image_count(
    case_id: str, upload_batch_id: str | None = None
) -> int:
    """
    Get the count of base documentation images for a case from the database.

    Only counts images where element_code IS NULL (ficha técnica, permiso,
    vistas del vehículo). Element-specific photos (element_code IS NOT NULL)
    are excluded to avoid false positives when confirming base documentation.
    """
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
                        "base_docs_batch_scope_mismatch",
                        case_id=case_id,
                        upload_batch_id=upload_batch_id,
                        scoped_count=scoped_count,
                        unscoped_count=unscoped_count,
                        fallback_used=True,
                        message="Using unscoped fallback count for base docs - images may have been uploaded before batch scope opened",
                    )
                    return unscoped_count

            return scoped_count
    except Exception as e:
        logger.warning(
            "failed_to_get_case_image_count",
            error=str(e),
            case_id=case_id,
        )
        return 0


async def _get_element_image_count(
    case_id: str,
    element_code: str,
    upload_batch_id: str | None = None,
) -> int:
    """
    Get the count of images for a specific element within a case.

    Filters CaseImage by both case_id AND element_code to verify
    that the user actually sent photos for the current element
    before confirming.
    """
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
                        "element_image_count_batch_scope_mismatch",
                        case_id=case_id,
                        element_code=element_code,
                        upload_batch_id=upload_batch_id,
                        scoped_count=scoped_count,
                        unscoped_count=unscoped_count,
                        fallback_used=True,
                        message="Using unscoped fallback count - images may have been uploaded before batch scope opened",
                    )
                    return unscoped_count

            return scoped_count
    except Exception as e:
        logger.warning(
            "failed_to_get_element_image_count",
            error=str(e),
            case_id=case_id,
        )
        return 0


async def _escalate_image_receipt_issue(case_id: str, conversation_id: str) -> None:
    """
    Silently escalate when user says they sent images but we didn't receive any.

    Creates a real escalation in Chatwoot (private note only, no user-facing
    message) so a human agent can follow up on the missing images.
    """
    try:
        from agent.services.escalation_service import perform_escalation

        await perform_escalation(
            conversation_id=conversation_id,
            reason=(
                f"El usuario indica que ha enviado imágenes (case_id={case_id}) "
                "pero el sistema no las ha recibido. "
                "Posible problema técnico de Chatwoot/WhatsApp."
            ),
            source="auto",
            is_technical_error=True,
        )

        logger.info(
            "image_receipt_escalation_completed",
            case_id=case_id,
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.error(
            "failed_to_escalate_image_receipt_issue",
            case_id=case_id,
            conversation_id=conversation_id,
            error=str(e),
            exc_info=True,
        )


@tool
async def confirmar_documentacion_base(
    usuario_confirma: bool | None = None,
) -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado la documentación base.

    **Fuente de verdad única**: esta es la ÚNICA herramienta que puede
    certificar que la documentación base ha sido recibida.  Nunca declares
    "he recibido tu documentación" ni "documentación completa/confirmada"
    sin que esta herramienta devuelva ``success=True``.

    La documentación base incluye:
    - Ficha técnica del vehículo
    - Permiso de circulación
    - Vistas del vehículo (frontal, laterales, trasera)

    Usa esta herramienta SOLO cuando el usuario confirme en tiempo pasado
    que ya los envió ("ya los mandé", "listo", "enviado").  No la llames
    en el turno de bienvenida/kickoff al sub-modo collect_base_docs —
    espera a que el usuario confirme el envío primero.

    Args:
        usuario_confirma: True si el usuario confirma explícitamente que ya envió
                         las imágenes. Solo usa este parámetro si preguntaste al
                         usuario y respondió afirmativamente.

    Returns:
        Estado actualizado, siguiente paso es COLLECT_PERSONAL.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    current_step = _get_current_step_from_context()
    conversation_id = state.get("conversation_id")

    # Validate step
    if current_step != CollectionStep.COLLECT_BASE_DOCS:
        # Idempotency guard: Check if we're past this step (already confirmed)
        past_steps = [
            CollectionStep.COLLECT_PERSONAL,
            CollectionStep.COLLECT_VEHICLE,
            CollectionStep.COLLECT_WORKSHOP,
            CollectionStep.REVIEW_SUMMARY,
            CollectionStep.COMPLETED,
        ]
        if current_step in past_steps:
            logger.info(
                "confirmar_documentacion_base_idempotent",
            current_step=current_step.value,
                current_step=current_step.value,
                idempotent=True,
            )
            return {
                "success": True,
                "base_docs_confirmed": True,
                "already_confirmed": True,
                "message": "La documentación base ya fue confirmada. Continuamos con el expediente.",
                "fsm_state_update": fsm_state,
                # Phase 2 canonical certainty flags (idempotent path).
                # Transition narration is always the runtime's job, not the tool's.
                "_internal_flags": {
                    "base_docs_registered": True,
                    "can_narrate_next_step_details": False,
                    "delivery_outcome_status": "not_requested",
                },
            }
        # Different error for wrong step (e.g., IDLE or COLLECT_ELEMENT_DATA)
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_BASE_DOCS. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    case_state = _get_mode_context()
    case_id = case_state.get("case_id")
    active_base_batch_id: str | None = None

    if not case_id:
        return _tool_error_response("No hay expediente activo")

    if get_settings().EXPEDIENTE_V2_ENABLED:
        active_scope = build_upload_scope(
            case_id=case_id,
            expediente_sub_mode="collect_base_docs",
            element_code=None,
        )
        active_batch = (
            await get_case_image_batch_service().resolve_for_scope(
                active_scope, allow_create=False
            )
            if active_scope
            else None
        )
        active_base_batch_id = active_batch.batch_id if active_batch else None

    # Check how many images we have received
    image_count = await _get_case_image_count(case_id, active_base_batch_id)
    base_doc_descriptions = case_state.get("base_doc_descriptions") or []
    min_required_images = max(len(base_doc_descriptions), 2)

    logger.info(
        "confirmar_documentacion_base_called",
        case_id=case_id,
        image_count=image_count,
        usuario_confirma=usuario_confirma,
    )

    # If we have enough images, proceed normally
    if image_count >= min_required_images:
        if get_settings().EXPEDIENTE_V2_ENABLED:
            await get_case_image_batch_service().finalize_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                status="confirmed",
            )
        # Update FSM state
        new_fsm_state = _update_fsm_state(
            fsm_state,
            {"base_docs_received": True},
        )

        # Transition to COLLECT_PERSONAL
        new_fsm_state = _transition_to_step(
            new_fsm_state, CollectionStep.COLLECT_PERSONAL
        )

        return {
            "success": True,
            "base_docs_confirmed": True,
            "images_received": image_count,
            "next_step": "COLLECT_PERSONAL",
            "fsm_state_update": new_fsm_state,
            # Defense-in-depth: root-level field for direct extractors
            "base_docs_received": True,
            # Neutral message: no description of next sub-mode (anti-anticipation fix)
            "message": "Documentación base recibida y registrada correctamente.",
            # Phase 2 canonical certainty flags.
            # Docs are registered — transition narration is always the runtime's job.
            "_internal_flags": {
                "base_docs_registered": True,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    # Not enough images - check if user has confirmed
    if usuario_confirma is True:
        # Race condition guard: WhatsApp text arrives before images (~2-5s delay).
        # Wait briefly and re-check before deciding to escalate.
        import asyncio

        await asyncio.sleep(4)
        image_count = await _get_case_image_count(case_id, active_base_batch_id)
        logger.info(
            "confirmar_documentacion_base: re-checked image count after delay",
            case_id=case_id,
            image_count_after_wait=image_count,
        )

        if image_count >= min_required_images:
            if get_settings().EXPEDIENTE_V2_ENABLED:
                await get_case_image_batch_service().finalize_for_scope(
                    case_id=case_id,
                    expediente_sub_mode="collect_base_docs",
                    element_code=None,
                    status="confirmed",
                )
            # Images arrived during the wait — proceed normally
            new_fsm_state = _update_fsm_state(
                fsm_state,
                {"base_docs_received": True},
            )
            new_fsm_state = _transition_to_step(
                new_fsm_state, CollectionStep.COLLECT_PERSONAL
            )
            return {
                "success": True,
                "base_docs_confirmed": True,
                "images_received": image_count,
                "next_step": "COLLECT_PERSONAL",
                "fsm_state_update": new_fsm_state,
                "base_docs_received": True,
                # Neutral message: no description of next sub-mode (anti-anticipation fix)
                "message": "Documentación base recibida y registrada correctamente.",
                # Phase 2 canonical certainty flags.
                # Docs are registered — transition narration is always the runtime's job.
                "_internal_flags": {
                    "base_docs_registered": True,
                    "can_narrate_next_step_details": False,
                    "delivery_outcome_status": "not_requested",
                },
            }

        # Still not enough after waiting — escalate silently to human review
        if conversation_id:
            await _escalate_image_receipt_issue(case_id, conversation_id)
        if get_settings().EXPEDIENTE_V2_ENABLED:
            await get_case_image_batch_service().finalize_for_scope(
                case_id=case_id,
                expediente_sub_mode="collect_base_docs",
                element_code=None,
                status="confirmed",
            )

        # Escalation is mutually exclusive with progression — do NOT advance
        # the FSM or confirm docs. A human agent will review.
        return {
            "success": False,
            "escalated": True,
            "images_received": image_count,
            "current_step": "collect_base_docs",
            "message": (
                "He registrado una incidencia con la recepción de documentos. "
                "Un agente humano revisará el caso. Mientras tanto, puedes "
                "intentar reenviar los documentos."
            ),
            "_internal_flags": {
                "base_docs_registered": False,
                "can_narrate_next_step_details": False,
                "delivery_outcome_status": "not_requested",
            },
        }

    # Not enough images and user hasn't confirmed yet
    # Ask the user to confirm (without saying "we didn't receive anything")
    # Build dynamic list of expected documents from base_doc_descriptions
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


@tool
async def reenviar_imagenes_elemento(element_code: str | None = None) -> dict[str, Any]:
    """
    Reenviar las imágenes de ejemplo para el elemento actual o especificado.

    Usa esta herramienta cuando el usuario pide ver las imágenes de
    ejemplo de nuevo.

    Args:
        element_code: Código del elemento (opcional, usa el actual si no se especifica)

    Returns:
        Información del elemento para que puedas mostrar sus imágenes de ejemplo.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = _get_mode_context()
    current_step = _get_current_step_from_context()

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = _get_current_element_code(case_state)

    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    category_id = case_state.get("category_id")
    if not category_id:
        return _tool_error_response("No hay categoría definida en el expediente")

    # Get element ID first (without loading images to avoid DetachedInstanceError)
    element_basic = await _get_element_by_code(
        element_code, category_id, load_images=False
    )
    if not element_basic:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    # Use element_service to get images properly serialized within an active session
    from agent.services.element_service import get_element_service

    element_service = get_element_service()
    element_details = await element_service.get_element_with_images(
        str(element_basic.id)
    )

    if not element_details:
        return _tool_error_response(
            f"No se pudieron obtener detalles del elemento '{element_code}'"
        )

    # Build example images list from the properly serialized dict
    example_images = []
    conversation_id = state.get("conversation_id", "unknown")

    for img in element_details.get("images", []):
        # Check status field (not is_active, which doesn't exist on ElementImage)
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

    # Sort by display order (already sorted by element_service, but being explicit)
    example_images.sort(key=lambda x: x.get("display_order", 0))

    logger.info(
        "reenviar_imagenes_elemento_images_found",
            image_count=len(example_images),
            element_code=element_code,
        conversation_id=conversation_id,
    )

    # Images included in return dict below (under _pending_images)
    # ContextVar doesn't work with LangChain ainvoke (copied context isolation)

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


# =============================================================================
# Export all tools
# =============================================================================

element_data_tools = [
    obtener_campos_elemento,
    guardar_datos_elemento,
    confirmar_fotos_elemento,
    completar_elemento_actual,
    obtener_progreso_elementos,
    confirmar_documentacion_base,
    reenviar_imagenes_elemento,
]
