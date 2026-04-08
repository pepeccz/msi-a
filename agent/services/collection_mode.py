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


def _count_based_mode(
    pending_fields: list[FieldInfo],
) -> CollectionMode:
    """
    Core count-and-conditional logic (extracted from the original determine_collection_mode).

    Priority:
    1. <= 2 pending fields → SEQUENTIAL
    2. No conditionals → BATCH
    3. Simple conditionals (1 level) → HYBRID
    4. Nested conditionals → SEQUENTIAL
    """
    total_pending = len(pending_fields)

    if total_pending <= 2:
        logger.debug(f"[collection_mode] SEQUENTIAL: {total_pending} fields (<=2)")
        return CollectionMode.SEQUENTIAL

    conditional_fields = [f for f in pending_fields if f.has_condition]
    base_fields = [f for f in pending_fields if not f.has_condition]

    if len(conditional_fields) == 0:
        logger.debug(f"[collection_mode] BATCH: {total_pending} fields, no conditionals")
        return CollectionMode.BATCH

    conditional_parents = {f.condition_field_key for f in conditional_fields if f.condition_field_key}
    conditional_keys = {f.field_key for f in conditional_fields}
    has_nested = bool(conditional_parents & conditional_keys)

    if has_nested:
        logger.debug("[collection_mode] SEQUENTIAL: has nested conditionals")
        return CollectionMode.SEQUENTIAL

    logger.debug(
        f"[collection_mode] HYBRID: {len(base_fields)} base + {len(conditional_fields)} conditional"
    )
    return CollectionMode.HYBRID


def determine_collection_mode(
    fields: list[FieldInfo],
    collected_values: dict[str, Any] | None = None,
    *,
    turn_count: int = 0,
    client_type: str | None = None,
    consecutive_errors: int = 0,
    element_complexity: int = 0,
) -> CollectionMode:
    """
    Determine the optimal collection mode for a set of fields.

    Base decision logic (unchanged — backward-compat guaranteed):
    1. If 0-2 fields total → SEQUENTIAL
    2. If 3+ fields and NO conditionals → BATCH
    3. If 3+ fields WITH conditionals:
       - Simple (1 level) → HYBRID
       - Nested/complex → SEQUENTIAL

    Adaptive overrides (priority-ordered, highest first):
    P1 — Error override: consecutive_errors >= 2 → SEQUENTIAL
    P2 — Fatigue bias: turn_count > 15 and pending >= 3 → BATCH
    P3 — Client type: "particular" + turns <= 15 + 3-4 pending → SEQUENTIAL
    P4 — Complexity: element_complexity >= 5 + simple conditionals → HYBRID

    Args:
        fields: List of FieldInfo objects.
        collected_values: Already collected field values (for re-evaluation).
        turn_count: Number of messages in the current mode (from mode_message_count).
        client_type: User type ("particular" | "professional" | None).
        consecutive_errors: Consecutive tool/validation errors from retry_state.
        element_complexity: Proxy for field-set complexity (e.g. total field count
            for the element, regardless of what's already collected).

    Returns:
        CollectionMode enum value
    """
    if not fields:
        return CollectionMode.SEQUENTIAL

    collected_values = collected_values or {}

    pending_fields = [f for f in fields if f.field_key not in collected_values]

    if not pending_fields:
        return CollectionMode.SEQUENTIAL

    # ── Base mode from count/conditional logic ─────────────────────────────────
    base_mode = _count_based_mode(pending_fields)

    total_pending = len(pending_fields)

    # ── P1: Error override ─────────────────────────────────────────────────────
    if consecutive_errors >= 2:
        logger.debug(
            f"[collection_mode] P1 SEQUENTIAL override: consecutive_errors={consecutive_errors}"
        )
        return CollectionMode.SEQUENTIAL

    # ── P2: Fatigue bias ───────────────────────────────────────────────────────
    if turn_count > 15 and total_pending >= 3:
        logger.debug(
            f"[collection_mode] P2 BATCH override: turn_count={turn_count}, pending={total_pending}"
        )
        return CollectionMode.BATCH

    # ── P3: Client-type preference ─────────────────────────────────────────────
    if client_type == "particular" and turn_count <= 15 and 3 <= total_pending <= 4:
        logger.debug(
            f"[collection_mode] P3 SEQUENTIAL override: particular client, pending={total_pending}"
        )
        return CollectionMode.SEQUENTIAL

    # ── P4: Complexity bias (only when there are simple conditionals) ──────────
    if element_complexity >= 5:
        conditional_fields = [f for f in pending_fields if f.has_condition]
        if conditional_fields:
            # Check they are simple (not nested) — same logic as _count_based_mode
            conditional_parents = {
                f.condition_field_key
                for f in conditional_fields
                if f.condition_field_key
            }
            conditional_keys = {f.field_key for f in conditional_fields}
            has_nested = bool(conditional_parents & conditional_keys)
            if not has_nested:
                logger.debug(
                    f"[collection_mode] P4 HYBRID override: complexity={element_complexity}"
                )
                return CollectionMode.HYBRID

    return base_mode


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
    example_value: str | None = None,
    field_retry_count: int = 0,
    is_required: bool = True,
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
        example_value: Example value for the field (shown after 2nd failure)
        field_retry_count: How many times this field has failed validation
        is_required: Whether the field is required (optional fields can be skipped)

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

    # After 2nd failure: append example value if available
    if field_retry_count >= 2 and example_value:
        recovery_prompt = f"{recovery_prompt} Por ejemplo: {example_value}"

    # Determine action
    action = "RE_ASK"
    if not is_required and field_retry_count >= 3:
        action = "SKIP_OPTIONAL"
        recovery_prompt = (
            "Este campo es opcional. Puedes saltarlo si lo prefieres, "
            "o intenta proporcionar el valor correcto."
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
            "action": action,
            "prompt_suggestion": recovery_prompt,
        },
    }
