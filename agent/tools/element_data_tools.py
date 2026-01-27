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
from database.connection import get_async_session
from database.models import Case, CaseElementData, Element, ElementRequiredField

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_element_by_code(element_code: str, category_id: str) -> Element | None:
    """Get element by code and category."""
    async with get_async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Element)
            .where(Element.code == element_code)
            .where(Element.category_id == uuid.UUID(category_id))
            .where(Element.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()


async def _get_required_fields_for_element(element_id: str) -> list[ElementRequiredField]:
    """Get all active required fields for an element, ordered by sort_order."""
    async with get_async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(ElementRequiredField)
            .where(ElementRequiredField.element_id == uuid.UUID(element_id))
            .where(ElementRequiredField.is_active == True)  # noqa: E712
            .order_by(ElementRequiredField.sort_order)
        )
        return list(result.scalars().all())


async def _get_or_create_case_element_data(
    case_id: str,
    element_code: str,
) -> CaseElementData:
    """Get or create CaseElementData record for a case-element pair."""
    async with get_async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == uuid.UUID(case_id))
            .where(CaseElementData.element_code == element_code)
        )
        record = result.scalar_one_or_none()

        if not record:
            record = CaseElementData(
                case_id=uuid.UUID(case_id),
                element_code=element_code,
                status="pending_photos",
                field_values={},
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        return record


async def _update_case_element_data(
    case_id: str,
    element_code: str,
    updates: dict[str, Any],
) -> CaseElementData | None:
    """Update CaseElementData record."""
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
            if "min" in rules and num_val < rules["min"]:
                return False, f"El valor debe ser mayor o igual a {rules['min']}"
            if "max" in rules and num_val > rules["max"]:
                return False, f"El valor debe ser menor o igual a {rules['max']}"
        except (ValueError, TypeError):
            return False, f"'{value}' no es un número válido"

    elif field.field_type == "boolean":
        if str(value).lower() not in ("true", "false", "sí", "si", "no", "1", "0"):
            return False, "El valor debe ser Sí o No"

    elif field.field_type == "select":
        if field.options and value not in field.options:
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
                return False, f"El formato no es válido"

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
    """Create a standardized error response for tools."""
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

    # Get current data
    case_element = await _get_or_create_case_element_data(case_id, element_code)
    current_values = case_element.field_values.copy() if case_element.field_values else {}

    # Validate and save each field
    results = []
    errors = []
    for field_key, value in datos.items():
        field = fields_by_key.get(field_key)
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

        # Validate
        is_valid, error_msg = _validate_field_value(value, field)
        if not is_valid:
            errors.append(f"{field.field_label}: {error_msg}")
            results.append({
                "field_key": field_key,
                "status": "error",
                "message": error_msg,
            })
        else:
            current_values[field_key] = value
            results.append({
                "field_key": field_key,
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

    response = {
        "success": len(errors) == 0,
        "element_code": element_code,
        "results": results,
        "saved_count": sum(1 for r in results if r["status"] == "saved"),
        "error_count": len(errors),
        "all_required_collected": all_required_collected,
    }

    if errors:
        response["errors"] = errors
        response["message"] = f"Errores en {len(errors)} campos: {'; '.join(errors)}"
    elif missing_fields:
        # Find next field to ask
        next_field = None
        for field in fields:
            if not _evaluate_field_condition(field, current_values, fields):
                continue
            if field.is_required and field.field_key not in current_values:
                next_field = field
                break
        
        response["missing_fields"] = missing_fields
        
        if next_field:
            # Build options text for select fields
            options_text = ""
            if next_field.field_type == "select" and next_field.options:
                options_list = next_field.options if isinstance(next_field.options, list) else []
                if options_list:
                    options_text = f"\nOpciones válidas: {', '.join(options_list)}"
            
            example_text = f"\nEjemplo: {next_field.example_value}" if next_field.example_value else ""
            
            response["next_field"] = {
                "field_key": next_field.field_key,
                "field_label": next_field.field_label,
                "field_type": next_field.field_type,
                "options": next_field.options if next_field.field_type == "select" else None,
                "instruction": next_field.llm_instruction,
            }
            response["message"] = (
                f"Datos guardados.\n\n"
                f"⚠️ SIGUIENTE CAMPO OBLIGATORIO:\n"
                f"Pregunta al usuario: {next_field.llm_instruction}\n\n"
                f"Campo: {next_field.field_label}\n"
                f"Tipo: {next_field.field_type}"
                f"{options_text}"
                f"{example_text}\n\n"
                f"NO preguntes otros datos. Sigue SOLO esta instrucción."
            )
        else:
            response["message"] = f"Datos guardados. Faltan: {', '.join(missing_fields)}"
    else:
        response["message"] = "Todos los datos del elemento han sido guardados correctamente."

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
        return _tool_error_response(
            f"Ya estamos en fase '{phase}'. Las fotos ya fueron confirmadas."
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
        
        # Get first required field info
        first_field = fields[0]
        
        # Build options text if field is select type
        options_text = ""
        if first_field.field_type == "select" and first_field.options:
            options_list = first_field.options if isinstance(first_field.options, list) else []
            if options_list:
                options_text = f"\nOpciones válidas: {', '.join(options_list)}"
        
        # Build example text
        example_text = f"\nEjemplo: {first_field.example_value}" if first_field.example_value else ""
        
        # Build imperative message that LLM MUST follow
        imperative_message = (
            f"Fotos de {element.name} confirmadas.\n\n"
            f"⚠️ SIGUIENTE PASO OBLIGATORIO:\n"
            f"Pregunta al usuario EXACTAMENTE esto: {first_field.llm_instruction}\n\n"
            f"Campo: {first_field.field_label}\n"
            f"Tipo: {first_field.field_type}"
            f"{options_text}"
            f"{example_text}\n\n"
            f"NO preguntes otros datos. Sigue SOLO esta instrucción."
        )
        
        return {
            "success": True,
            "element_code": element_code,
            "element_name": element.name,
            "photos_confirmed": True,
            "has_required_fields": True,
            "total_fields": len(fields),
            "next_phase": "data",
            "first_field": {
                "field_key": first_field.field_key,
                "field_label": first_field.field_label,
                "field_type": first_field.field_type,
                "options": first_field.options if first_field.field_type == "select" else None,
                "example": first_field.example_value,
                "instruction": first_field.llm_instruction,
            },
            "all_fields": [
                {
                    "field_key": f.field_key,
                    "field_label": f.field_label,
                    "field_type": f.field_type,
                    "is_required": f.is_required if hasattr(f, 'is_required') else True,
                    "condition": f.condition_field_key if hasattr(f, 'condition_field_key') else None,
                }
                for f in fields
            ],
            "fsm_state": new_fsm_state,
            "message": imperative_message,
        }
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
                "fsm_state": new_fsm_state,
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
                "fsm_state": new_fsm_state,
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
    collected_values = case_element.field_values or {}

    missing_required = []
    for field in fields:
        if not _evaluate_field_condition(field, collected_values, fields):
            continue
        if field.is_required and field.field_key not in collected_values:
            missing_required.append(field.field_label)

    if missing_required:
        return _tool_error_response(
            f"Faltan campos obligatorios: {', '.join(missing_required)}. "
            "Recógelos antes de completar el elemento."
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
            "fsm_state": new_fsm_state,
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
            "fsm_state": new_fsm_state,
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


@tool
async def confirmar_documentacion_base() -> dict[str, Any]:
    """
    Confirmar que el usuario ha enviado la documentación base.
    
    La documentación base incluye:
    - Ficha técnica del vehículo
    - Permiso de circulación
    
    Usa esta herramienta cuando el usuario diga "listo" después de
    enviar estos documentos.
    
    Returns:
        Estado actualizado, siguiente paso es COLLECT_PERSONAL.
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No hay estado de conversación activo")

    fsm_state = state.get("fsm_state")
    current_step = get_current_step(fsm_state)

    # Validate step
    if current_step != CollectionStep.COLLECT_BASE_DOCS:
        return _tool_error_response(
            f"Esta herramienta solo funciona en COLLECT_BASE_DOCS. Paso actual: {current_step.value}",
            current_step=current_step,
        )

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
        "next_step": "COLLECT_PERSONAL",
        "fsm_state": new_fsm_state,
        "message": (
            "Documentación base recibida. "
            "Ahora necesito tus datos personales."
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

    # Get element with example images
    element = await _get_element_by_code(element_code, category_id)
    if not element:
        return _tool_error_response(f"Elemento '{element_code}' no encontrado")

    return {
        "success": True,
        "element_code": element_code,
        "element_name": element.name,
        "example_images": element.example_images or [],
        "description": element.description,
        "should_send_images": True,
        "message": (
            f"Aquí tienes las imágenes de ejemplo para {element.name}. "
            "Envíame fotos similares de tu vehículo."
        ),
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
