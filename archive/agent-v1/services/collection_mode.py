"""
MSI Automotive - Smart Collection Mode Service.

This module determines the optimal data collection mode for element fields
based on the number of fields, conditional dependencies, and complexity.

Collection Modes:
    - SEQUENTIAL: 1-2 fields, or complex conditionals - ask one at a time
    - BATCH: 3+ fields without conditionals - ask all at once
    - HYBRID: Mix - ask base fields first, then conditional fields as a group
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CollectionMode(str, Enum):
    """Data collection mode for element fields."""
    
    SEQUENTIAL = "sequential"  # One field at a time
    BATCH = "batch"  # All fields at once
    HYBRID = "hybrid"  # Base fields first, then conditionals


@dataclass
class FieldInfo:
    """Simplified field information for collection mode analysis."""
    
    field_key: str
    field_label: str
    field_type: str
    is_required: bool
    has_condition: bool
    condition_field_key: str | None = None
    options: list[str] | None = None
    llm_instruction: str | None = None
    example_value: str | None = None
    validation_rules: dict[str, Any] | None = None
    
    @classmethod
    def from_db_field(cls, field: Any) -> "FieldInfo":
        """Create FieldInfo from database ElementRequiredField model."""
        return cls(
            field_key=field.field_key,
            field_label=field.field_label,
            field_type=field.field_type,
            is_required=field.is_required if hasattr(field, 'is_required') else True,
            has_condition=bool(field.condition_field_id) if hasattr(field, 'condition_field_id') else False,
            condition_field_key=field.condition_field_key if hasattr(field, 'condition_field_key') else None,
            options=field.options if hasattr(field, 'options') else None,
            llm_instruction=field.llm_instruction if hasattr(field, 'llm_instruction') else None,
            example_value=field.example_value if hasattr(field, 'example_value') else None,
            validation_rules=field.validation_rules if hasattr(field, 'validation_rules') else None,
        )


def determine_collection_mode(
    fields: list[FieldInfo],
    collected_values: dict[str, Any] | None = None,
) -> CollectionMode:
    """
    Determine the optimal collection mode for a set of fields.
    
    Decision logic:
    1. If 0-2 fields total → SEQUENTIAL (more human, conversational)
    2. If 3+ fields and NO conditionals → BATCH (efficient)
    3. If 3+ fields WITH conditionals:
       - If conditionals are simple (1 level) → HYBRID
       - If conditionals are nested/complex → SEQUENTIAL
    
    Args:
        fields: List of FieldInfo objects
        collected_values: Already collected field values (for re-evaluation)
    
    Returns:
        CollectionMode enum value
    """
    if not fields:
        return CollectionMode.SEQUENTIAL
    
    collected_values = collected_values or {}
    
    # Filter out already collected fields
    pending_fields = [f for f in fields if f.field_key not in collected_values]
    
    if not pending_fields:
        return CollectionMode.SEQUENTIAL  # Nothing to collect
    
    total_pending = len(pending_fields)
    
    # Rule 1: Few fields → SEQUENTIAL
    if total_pending <= 2:
        logger.debug(f"[collection_mode] SEQUENTIAL: {total_pending} fields (<=2)")
        return CollectionMode.SEQUENTIAL
    
    # Analyze conditionals
    conditional_fields = [f for f in pending_fields if f.has_condition]
    base_fields = [f for f in pending_fields if not f.has_condition]
    
    # Rule 2: No conditionals → BATCH
    if len(conditional_fields) == 0:
        logger.debug(f"[collection_mode] BATCH: {total_pending} fields, no conditionals")
        return CollectionMode.BATCH
    
    # Rule 3: Has conditionals - check complexity
    # Simple conditional = depends on a base field (1 level)
    # Complex conditional = depends on another conditional field (nested)
    
    conditional_parents = {f.condition_field_key for f in conditional_fields if f.condition_field_key}
    conditional_keys = {f.field_key for f in conditional_fields}
    
    # Check if any conditional depends on another conditional (nested)
    has_nested = bool(conditional_parents & conditional_keys)
    
    if has_nested:
        logger.debug(f"[collection_mode] SEQUENTIAL: has nested conditionals")
        return CollectionMode.SEQUENTIAL
    
    # Simple conditionals → HYBRID
    logger.debug(f"[collection_mode] HYBRID: {len(base_fields)} base + {len(conditional_fields)} conditional")
    return CollectionMode.HYBRID


def get_fields_for_mode(
    mode: CollectionMode,
    fields: list[FieldInfo],
    collected_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the appropriate field structure based on collection mode.
    
    Returns different structures based on mode:
    
    SEQUENTIAL:
        {
            "mode": "sequential",
            "current_field": FieldInfo,
            "remaining_count": int
        }
    
    BATCH:
        {
            "mode": "batch",
            "fields": [FieldInfo, ...],
            "total_count": int
        }
    
    HYBRID:
        {
            "mode": "hybrid",
            "phase": "base" | "conditional",
            "fields": [FieldInfo, ...],  # Current phase fields
            "awaiting_fields": [FieldInfo, ...]  # Conditional fields waiting for triggers
        }
    
    Args:
        mode: The collection mode
        fields: All fields for the element
        collected_values: Already collected values
    
    Returns:
        Dict with mode-specific field structure
    """
    collected_values = collected_values or {}
    
    # Filter out already collected and evaluate conditionals
    pending_fields = []
    for f in fields:
        if f.field_key in collected_values:
            continue
        
        # Check if conditional field should be shown
        if f.has_condition and f.condition_field_key:
            parent_value = collected_values.get(f.condition_field_key)
            if parent_value is None:
                continue  # Parent not yet answered, skip for now
        
        pending_fields.append(f)
    
    if not pending_fields:
        return {
            "mode": mode.value,
            "complete": True,
            "message": "Todos los campos han sido recolectados."
        }
    
    if mode == CollectionMode.SEQUENTIAL:
        current_field = pending_fields[0]
        return {
            "mode": "sequential",
            "action": "ASK_FIELD",
            "current_field": _field_to_dict(current_field),
            "remaining_count": len(pending_fields) - 1,
        }
    
    elif mode == CollectionMode.BATCH:
        return {
            "mode": "batch",
            "action": "ASK_BATCH",
            "fields": [_field_to_dict(f) for f in pending_fields],
            "total_count": len(pending_fields),
        }
    
    else:  # HYBRID
        # Separate base and conditional
        base_fields = [f for f in pending_fields if not f.has_condition]
        conditional_fields = [f for f in pending_fields if f.has_condition]
        
        if base_fields:
            # Still have base fields to ask
            return {
                "mode": "hybrid",
                "action": "ASK_BATCH",
                "phase": "base",
                "fields": [_field_to_dict(f) for f in base_fields],
                "awaiting_conditional": len(conditional_fields),
            }
        elif conditional_fields:
            # Base fields done, now conditional
            return {
                "mode": "hybrid",
                "action": "ASK_BATCH",
                "phase": "conditional",
                "fields": [_field_to_dict(f) for f in conditional_fields],
                "total_count": len(conditional_fields),
            }
        else:
            return {
                "mode": "hybrid",
                "complete": True,
                "message": "Todos los campos han sido recolectados."
            }


def _field_to_dict(field: FieldInfo) -> dict[str, Any]:
    """Convert FieldInfo to dict for tool response."""
    result = {
        "field_key": field.field_key,
        "field_label": field.field_label,
        "field_type": field.field_type,
        "is_required": field.is_required,
    }
    
    if field.options:
        result["options"] = field.options
    
    if field.llm_instruction:
        result["instruction"] = field.llm_instruction
    
    if field.example_value:
        result["example"] = field.example_value
    
    if field.validation_rules:
        result["validation"] = field.validation_rules
    
    return result


def format_batch_prompt(fields: list[dict[str, Any]], element_name: str) -> str:
    """
    Format a batch collection prompt for the LLM to present to the user.
    
    This creates a natural-language list of fields to collect.
    
    CRITICAL: Includes field_key explicitly to prevent LLM from guessing incorrect keys.
    
    Args:
        fields: List of field dicts (from _field_to_dict)
        element_name: Name of the element being collected
    
    Returns:
        Formatted prompt string (for LLM guidance, not direct user display)
    """
    if not fields:
        return ""
    
    lines = [f"Datos a recoger para {element_name}:"]
    
    for i, field in enumerate(fields, 1):
        # Include field_key explicitly so LLM knows EXACTLY what to use in guardar_datos_elemento()
        line = f"{i}. {field['field_label']} [USAR field_key: '{field['field_key']}']"
        
        if field.get("options"):
            options_str = ", ".join(field["options"])
            line += f" (opciones: {options_str})"
        elif field.get("example"):
            line += f" (ej: {field['example']})"
        
        if field["field_type"] == "boolean":
            line += " (Sí/No)"
        
        lines.append(line)
    
    return "\n".join(lines)


def create_error_recovery_response(
    error_code: str,
    error_message: str,
    field_key: str | None = None,
    user_value: Any = None,
    valid_options: list[str] | None = None,
    validation_hint: str | None = None,
) -> dict[str, Any]:
    """
    Create a structured error response that helps the LLM recover gracefully.
    
    Args:
        error_code: Error type (INVALID_TYPE, OUT_OF_RANGE, UNKNOWN_FIELD, etc.)
        error_message: Technical error message
        field_key: Field that caused the error (if applicable)
        user_value: Value the user provided
        valid_options: Valid options for the field
        validation_hint: Human-readable hint for the user
    
    Returns:
        Structured error response dict
    """
    # Generate recovery prompt based on error type
    recovery_prompts = {
        "OUT_OF_RANGE": f"El valor esta fuera del rango permitido. {validation_hint or ''}",
        "INVALID_FORMAT": f"El formato no es valido. {validation_hint or ''}",
        "INVALID_OPTION": f"Esa opcion no es valida. Las opciones son: {', '.join(valid_options) if valid_options else 'ver opciones'}",
        "UNKNOWN_FIELD": "Ese campo no existe para este elemento. Revisa los campos disponibles.",
        "MISSING_REQUIRED": f"El campo es obligatorio. {validation_hint or 'Por favor, proporciona un valor.'}",
        "INVALID_TYPE": f"El tipo de dato no es correcto. {validation_hint or ''}",
    }
    
    recovery_prompt = recovery_prompts.get(
        error_code, 
        validation_hint or "Por favor, verifica el dato e intentalo de nuevo."
    )
    
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": error_message,
            "field": field_key,
            "user_value": user_value,
            "valid_options": valid_options,
            "hint": validation_hint,
        },
        "recovery": {
            "action": "RE_ASK",
            "prompt_suggestion": recovery_prompt,
        },
    }
