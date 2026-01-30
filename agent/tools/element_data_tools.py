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
"""

import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from langchain_core.tools import tool

from agent.fsm.case_collection import (
    CollectionStep,
    get_case_fsm_state,
    update_case_fsm_state,
    get_current_step,
    transition_to,
    get_current_element_code,
    get_element_phase,
    update_element_status,
    is_current_element_photos_done,
    is_current_element_complete,
    are_all_elements_complete,
    get_element_collection_progress,
    ELEMENT_STATUS_PENDING,
    ELEMENT_STATUS_PHOTOS_DONE,
    ELEMENT_STATUS_COMPLETE,
)
from agent.state.helpers import get_current_state
from agent.utils.errors import ErrorCategory
from agent.utils.tool_helpers import tool_error_response
from database.connection import get_async_session
from database.models import Case, CaseElementData, Element, ElementRequiredField

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

from agent.utils.text_utils import normalize_field_key as _normalize_field_key


async def _get_element_by_code(element_code: str, category_id: str, load_images: bool = False) -> Element | None:
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
                Element.is_active == True  # noqa: E712
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
            f"Database error in _get_element_by_code: {e}",
            extra={"element_code": element_code, "category_id": category_id, "load_images": load_images},
            exc_info=True,
        )
        return None


async def _get_required_fields_for_element(element_id: str) -> list[ElementRequiredField]:
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
            f"Database error in _get_required_fields_for_element: {e}",
            extra={"element_id": element_id},
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
            insert_stmt = insert(CaseElementData).values(
                case_id=uuid.UUID(case_id),
                element_code=element_code,
                status="pending_photos",
                field_values={},
            ).on_conflict_do_nothing(
                index_elements=['case_id', 'element_code']  # Unique constraint
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
            f"Database error in _get_or_create_case_element_data: {e}",
            extra={"case_id": case_id, "element_code": element_code},
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
            f"Database error in _update_case_element_data: {e}",
            extra={"case_id": case_id, "element_code": element_code, "updates": list(updates.keys())},
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
            clean_value = re.sub(r'\s*(mm|cm|m|kg|g|cc|cv|hp|kw|€|euros?)\s*$', '', clean_value, flags=re.IGNORECASE)
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
            return False, f"El texto debe tener al menos {rules['min_length']} caracteres"
        if "max_length" in rules and len(str(value)) > rules["max_length"]:
            return False, f"El texto debe tener como máximo {rules['max_length']} caracteres"
        if "pattern" in rules:
            import re
            if not re.match(rules["pattern"], str(value)):
                # Include pattern description or example if available
                pattern_hint = rules.get("pattern_description") or rules.get("example")
                if pattern_hint:
                    return False, f"El formato no es válido. Ejemplo esperado: {pattern_hint}"
                return False, f"El formato no es válido (patrón requerido: {rules['pattern']})"

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
            f"Conditional field '{field.field_key}' references non-existent condition_field_id: "
            f"{field.condition_field_id}. Showing field by default.",
            extra={
                "field_key": field.field_key,
                "field_id": str(field.id),
                "condition_field_id": str(field.condition_field_id),
                "available_field_ids": [str(f.id) for f in all_fields],
            }
        )
        return True  # Condition field not found, show by default

    condition_value = collected_values.get(condition_field.field_key)
    operator = field.condition_operator or "equals"
    expected = field.condition_value

    if operator == "equals":
        return str(condition_value).lower() == str(expected).lower() if condition_value else False
    elif operator == "not_equals":
        return str(condition_value).lower() != str(expected).lower() if condition_value else True
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
        step_val = current_step.value if isinstance(current_step, CollectionStep) else current_step
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

    fsm_state = state.get("fsm_state")
    case_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    # Validate we're in the right step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = get_current_element_code(case_state)
    
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
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
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
        1 for f in fields_info 
        if f["is_required"] and f["is_collected"]
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
    case_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = get_current_element_code(case_state)
    
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Validate phase (should be in "data" phase)
    phase = get_element_phase(case_state)
    if phase != "data":
        return _tool_error_response(
            f"Estamos en fase '{phase}', no 'data'. "
            "Primero confirma las fotos con confirmar_fotos_elemento()."
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
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
    current_values = case_element.field_values.copy() if case_element.field_values else {}

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
                    f"Field key normalized: '{field_key}' -> '{actual_field_key}'",
                    extra={"element_code": element_code}
                )
        
        if not field:
            results.append({
                "field_key": field_key,
                "status": "ignored",
                "message": f"Campo '{field_key}' no existe para este elemento",
            })
            continue

        # Check condition
        if not _evaluate_field_condition(field, current_values, fields):
            results.append({
                "field_key": field_key,
                "status": "skipped",
                "message": f"Campo '{field_key}' no aplica según las condiciones",
            })
            continue

        # Idempotency guard: Check if field already has this exact value
        existing_value = current_values.get(actual_field_key)
        if existing_value == value:
            idempotent_count += 1
            results.append({
                "field_key": actual_field_key,
                "status": "already_saved",
                "value": value,
                "message": f"Campo '{field.field_label}' ya tiene este valor",
            })
            logger.info(
                f"guardar_datos_elemento idempotent field | element={element_code} | field={actual_field_key}",
                extra={
                    "element_code": element_code,
                    "field_key": actual_field_key,
                    "idempotent": True,
                }
            )
            continue  # Skip validation and DB write

        # Validate
        is_valid, error_msg = _validate_field_value(value, field)
        if not is_valid:
            errors.append(f"{field.field_label}: {error_msg}")
            results.append({
                "field_key": actual_field_key,
                "status": "error",
                "message": error_msg,
            })
        else:
            # Use the actual DB field key for storage
            current_values[actual_field_key] = value
            results.append({
                "field_key": actual_field_key,
                "status": "saved",
                "value": value,
            })

    # Save to database
    await _update_case_element_data(
        case_id,
        element_code,
        {"field_values": current_values},
    )

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

    # Collect ignored fields to warn about them prominently
    ignored_fields = [r["field_key"] for r in results if r["status"] == "ignored"]
    
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
            f"[guardar_datos_elemento] Ignored fields: {ignored_fields}",
            extra={"element_code": element_code, "ignored": ignored_fields, "valid": valid_field_keys}
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
            "fields_with_errors": [r["field_key"] for r in results if r["status"] == "error"],
            "prompt_suggestion": f"Hubo un problema con algunos datos. {'; '.join(errors)}. Por favor, verifica y vuelve a proporcionar los valores correctos."
        }
        response["message"] = f"Errores en {len(errors)} campos. Verifica: {'; '.join(errors)}"
        
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
            fields_structure = get_fields_for_mode(collection_mode, pending_fields, current_values)
            
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
                    field_items = [f"{f['field_label']} (field_key={f['field_key']})" for f in batch_fields]
                    response["message"] = f"Datos guardados. Aun faltan: {', '.join(field_items)}"
                else:
                    response["message"] = f"Datos guardados. Faltan: {', '.join(missing_fields)}"
        else:
            response["message"] = f"Datos guardados. Faltan: {', '.join(missing_fields)}"
    else:
        response["message"] = "Todos los datos del elemento han sido guardados correctamente."
        response["action"] = "ELEMENT_DATA_COMPLETE"

    return response


@tool
async def confirmar_fotos_elemento() -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado todas las fotos del elemento actual.
    
    Usa esta herramienta cuando el usuario diga "listo" o similar
    después de enviar las fotos de un elemento.
    
    Después de confirmar, automáticamente pasamos a recoger los datos
    técnicos del elemento (si tiene campos requeridos).
    
    Returns:
        Estado actualizado y próximo paso.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    case_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get current element
    element_code = get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Validate phase (should be in "photos" phase)
    phase = get_element_phase(case_state)
    if phase != "photos":
        # Idempotency guard: Check if this is a repeat call (photos already confirmed)
        if phase == "data" and is_current_element_photos_done(case_state):
            logger.info(
                f"confirmar_fotos_elemento called idempotently | element_code={element_code}",
                extra={
                    "element_code": element_code,
                    "idempotent": True,
                    "phase": phase,
                },
            )
            return {
                "success": True,
                "photos_confirmed": True,
                "already_confirmed": True,
                "element_code": element_code,
                "message": f"Las fotos de {element_code} ya fueron confirmadas. Continuamos con los datos técnicos.",
                "fsm_state_update": fsm_state,  # Return current state unchanged
            }
        # Different error for truly wrong phase
        return _tool_error_response(
            f"Fase incorrecta: {phase}. No se puede confirmar fotos desde esta fase."
        )

    category_id = case_state.get("category_id")
    case_id = case_state.get("case_id")

    if not category_id or not case_id:
        return _tool_error_response("Expediente no configurado correctamente")

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

    # Update FSM state
    element_data_status = case_state.get("element_data_status", {}).copy()
    
    if fields:
        # Has required fields - switch to data phase
        element_data_status[element_code] = ELEMENT_STATUS_PHOTOS_DONE
        new_fsm_state = update_case_fsm_state(
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
            new_fsm_state = transition_to(fsm_state, CollectionStep.COLLECT_BASE_DOCS)
            new_fsm_state = update_case_fsm_state(
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
                "message": (
                    f"Fotos de {element.name} confirmadas. "
                    "Todos los elementos están completos. "
                    "Ahora necesito la documentación base del vehículo."
                ),
            }
        else:
            # More elements to process
            current_idx = case_state.get("current_element_index", 0)
            next_idx = current_idx + 1
            next_element = element_codes[next_idx] if next_idx < len(element_codes) else None
            
            new_fsm_state = update_case_fsm_state(
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
                "message": (
                    f"Fotos de {element.name} confirmadas. "
                    f"Pasamos al siguiente elemento: {next_element}."
                ),
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
    case_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get current element
    element_code = get_current_element_code(case_state)
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    # Idempotency guard: Check if element already completed
    element_data_status = case_state.get("element_data_status", {})
    if element_data_status.get(element_code) == ELEMENT_STATUS_COMPLETE:
        logger.info(
            f"completar_elemento_actual called idempotently | element_code={element_code}",
            extra={
                "element_code": element_code,
                "idempotent": True,
            },
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
        return _tool_error_response("Error al acceder a los datos del elemento. Intenta de nuevo.")
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

    # Update FSM state
    element_data_status = case_state.get("element_data_status", {}).copy()
    element_data_status[element_code] = ELEMENT_STATUS_COMPLETE
    element_codes = case_state.get("element_codes", [])

    # Check if all elements are complete
    all_done = all(
        element_data_status.get(code) == ELEMENT_STATUS_COMPLETE
        for code in element_codes
    )

    if all_done:
        # All elements complete - transition to COLLECT_BASE_DOCS
        new_fsm_state = transition_to(fsm_state, CollectionStep.COLLECT_BASE_DOCS)
        new_fsm_state = update_case_fsm_state(
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
            "message": (
                f"Elemento {element.name} completado. "
                "Todos los elementos están listos. "
                "Ahora necesito la documentación base del vehículo."
            ),
        }
    else:
        # More elements to process
        current_idx = case_state.get("current_element_index", 0)
        next_idx = current_idx + 1
        next_element = element_codes[next_idx] if next_idx < len(element_codes) else None

        new_fsm_state = update_case_fsm_state(
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

        return {
            "success": True,
            "element_code": element_code,
            "element_complete": True,
            "all_elements_complete": False,
            "next_element_code": next_element,
            "next_element_name": next_element_obj.name if next_element_obj else None,
            "progress": {
                "completed": sum(1 for s in element_data_status.values() if s == ELEMENT_STATUS_COMPLETE),
                "total": len(element_codes),
            },
            "fsm_state_update": new_fsm_state,
            "message": (
                f"Elemento {element.name} completado. "
                f"Pasamos al siguiente: {next_element_obj.name if next_element_obj else next_element}."
            ),
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
    case_state = get_case_fsm_state(fsm_state)

    progress = get_element_collection_progress(case_state)
    
    return {
        "success": True,
        **progress,
        "message": (
            f"Progreso: {progress['completed_elements']}/{progress['total_elements']} elementos completados. "
            f"Elemento actual: {progress['current_element_code']} ({progress['current_phase']})."
        ),
    }


async def _get_case_image_count(case_id: str) -> int:
    """
    Get the count of images for a case from the database.
    
    This is used to validate that documentation images were received.
    """
    try:
        from sqlalchemy import func, select
        from database.models import CaseImage
        
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count()).select_from(CaseImage).where(
                    CaseImage.case_id == uuid.UUID(case_id)
                )
            )
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"Failed to get case image count: {e}")
        return 0


async def _escalate_image_receipt_issue(case_id: str, conversation_id: str) -> None:
    """
    Silently escalate when user says they sent images but we didn't receive any.
    
    Creates an escalation record for human review without telling the user
    there was a technical issue.
    """
    try:
        from database.models import Escalation
        
        async with get_async_session() as session:
            escalation = Escalation(
                case_id=uuid.UUID(case_id),
                conversation_id=conversation_id,
                reason="El usuario ha enviado las imagenes pero el sistema no las ha recibido",
                is_technical_error=True,
                status="pending",
            )
            session.add(escalation)
            await session.commit()
            
            logger.warning(
                f"Escalation created for image receipt issue | case_id={case_id}",
                extra={
                    "case_id": case_id,
                    "conversation_id": conversation_id,
                    "escalation_reason": "images_not_received",
                }
            )
    except Exception as e:
        logger.error(f"Failed to create escalation for image receipt issue: {e}", exc_info=True)


@tool
async def confirmar_documentacion_base(
    usuario_confirma: bool | None = None,
) -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado la documentación base.
    
    La documentación base incluye:
    - Ficha técnica del vehículo
    - Permiso de circulación
    - Vistas del vehículo (frontal, laterales, trasera)
    
    Usa esta herramienta cuando el usuario diga "listo" después de
    enviar estos documentos.
    
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
    current_step = get_current_step(fsm_state)
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
                f"confirmar_documentacion_base called idempotently | current_step={current_step.value}",
                extra={
                    "current_step": current_step.value,
                    "idempotent": True,
                }
            )
            return {
                "success": True,
                "base_docs_confirmed": True,
                "already_confirmed": True,
                "message": "La documentación base ya fue confirmada. Continuamos con el expediente.",
                "fsm_state_update": fsm_state,
            }
        # Different error for wrong step (e.g., IDLE or COLLECT_ELEMENT_DATA)
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_BASE_DOCS. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    case_state = get_case_fsm_state(fsm_state)
    case_id = case_state.get("case_id")
    
    if not case_id:
        return _tool_error_response("No hay expediente activo")

    # Check how many images we have received
    image_count = await _get_case_image_count(case_id)
    min_required_images = 2  # At least ficha técnica + permiso
    
    logger.info(
        f"confirmar_documentacion_base called | case_id={case_id} | "
        f"image_count={image_count} | usuario_confirma={usuario_confirma}",
        extra={
            "case_id": case_id,
            "image_count": image_count,
            "usuario_confirma": usuario_confirma,
        }
    )
    
    # If we have enough images, proceed normally
    if image_count >= min_required_images:
        # Update FSM state
        new_fsm_state = update_case_fsm_state(
            fsm_state,
            {"base_docs_received": True},
        )
        
        # Transition to COLLECT_PERSONAL
        new_fsm_state = transition_to(new_fsm_state, CollectionStep.COLLECT_PERSONAL)

        return {
            "success": True,
            "base_docs_confirmed": True,
            "images_received": image_count,
            "next_step": "COLLECT_PERSONAL",
            "fsm_state_update": new_fsm_state,
            "message": (
                "Documentación base recibida. "
                "Ahora necesito tus datos personales."
            ),
        }
    
    # Not enough images - check if user has confirmed
    if usuario_confirma is True:
        # User says they sent the images but we don't have them
        # Escalate silently to human review
        if conversation_id:
            await _escalate_image_receipt_issue(case_id, conversation_id)
        
        # Still proceed (let human agent handle it)
        new_fsm_state = update_case_fsm_state(
            fsm_state,
            {"base_docs_received": True},
        )
        new_fsm_state = transition_to(new_fsm_state, CollectionStep.COLLECT_PERSONAL)
        
        return {
            "success": True,
            "base_docs_confirmed": True,
            "images_received": image_count,
            "escalated": True,
            "next_step": "COLLECT_PERSONAL",
            "fsm_state_update": new_fsm_state,
            "message": (
                "Perfecto, continuamos. "
                "Ahora necesito tus datos personales."
            ),
        }
    
    # Not enough images and user hasn't confirmed yet
    # Ask the user to confirm (without saying "we didn't receive anything")
    return {
        "success": False,
        "needs_confirmation": True,
        "images_received": image_count,
        "current_step": current_step.value,
        "message": (
            "¿Has enviado ya la ficha técnica y el permiso de circulación?\n\n"
            "Necesito estos documentos para continuar:\n"
            "• Ficha técnica del vehículo\n"
            "• Permiso de circulación\n"
            "• Vistas del vehículo (frontal, laterales, trasera)\n\n"
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
    case_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    # Validate step
    if current_step != CollectionStep.COLLECT_ELEMENT_DATA:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_ELEMENT_DATA. Paso actual: {current_step.value}",
            current_step=current_step,
        )

    # Get element code
    if not element_code:
        element_code = get_current_element_code(case_state)
    
    if not element_code:
        return _tool_error_response("No hay elemento actual seleccionado")

    category_id = case_state.get("category_id")
    if not category_id:
        return _tool_error_response("No hay categoría definida en el expediente")

    # Get element ID first (without loading images to avoid DetachedInstanceError)
    element_basic = await _get_element_by_code(element_code, category_id, load_images=False)
    if not element_basic:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    # Use element_service to get images properly serialized within an active session
    from agent.services.element_service import get_element_service
    element_service = get_element_service()
    element_details = await element_service.get_element_with_images(str(element_basic.id))
    
    if not element_details:
        return _tool_error_response(f"No se pudieron obtener detalles del elemento '{element_code}'")

    # Build example images list from the properly serialized dict
    example_images = []
    conversation_id = state.get("conversation_id", "unknown")
    
    for img in element_details.get("images", []):
        # Check status field (not is_active, which doesn't exist on ElementImage)
        if img.get("status") == "active":
            example_images.append({
                "url": img["image_url"],
                "tipo": "elemento",
                "elemento": element_details["name"],
                "descripcion": img.get("description") or "",
                "display_order": img.get("sort_order", 0),
                "status": "active",
            })
    
    # Sort by display order (already sorted by element_service, but being explicit)
    example_images.sort(key=lambda x: x.get("display_order", 0))
    
    logger.info(
        f"[reenviar_imagenes_elemento] Found {len(example_images)} active images for {element_code}",
        extra={"conversation_id": conversation_id, "element_code": element_code}
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
        ) if example_images else (
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
