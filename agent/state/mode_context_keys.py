"""
Canonical key sets for mode_context and state updates.

Provides compile-time documentation and runtime validation of which keys
are valid in mode_context updates and top-level state updates returned
by mode nodes.

Populated from a full codebase scan of:
- agent/modes/*.py (all keys written to mode_context and state updates)
- agent/tools/*.py (all _internal_flags and _context_updates keys)
- agent/state/conversation_state.py (ConversationState TypedDict)
- agent/utils/fsm_compat.py (keys read from mode_context)

Gated behind ``ENABLE_STATE_CONTRACT_ENFORCEMENT`` feature flag:
- True  → log structured warnings for unknown keys AND strip them
- False → log at DEBUG level only (complete no-op on data)
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Canonical mode_context keys
# ---------------------------------------------------------------------------
# Every key that any mode, tool, or service reads/writes to mode_context.
# Organised by origin for maintainability.

# Keys from ModeContextData TypedDict (conversation_state.py)
_TYPED_DICT_KEYS = frozenset(
    {
        # CONSULTA_MODE
        "consulta_history",
        # PRESUPUESTO_MODE
        "categoria_slug",
        "elemento_tentativo",
        "elemento_confirmado",
        "vehiculo",
        "elementos_confirmados",
        "element_codes",
        "tarifa_calculada",
        "precio_comunicado",
        "imagenes_enviadas",
        "imagenes_envio_intent_creado",
        "imagenes_delivery_request_id",
        "imagenes_delivery_outcome",
        "pending_variants",
        "waiting_for_image_choice",
        # EXPEDIENTE_MODE
        "case_id",
        "datos_personales",
        "datos_vehiculo",
        "documentacion_elementos",
        "documentacion_base",
        "datos_taller",
        "taller_propio",
        "tariff_tier_id",
        "tariff_amount",
        "current_element_index",
        "element_phase",
        "element_data_status",
        "base_docs_received",
        "received_images",
    }
)

# Keys written by modes at runtime (not in TypedDict but used in practice)
_MODE_RUNTIME_KEYS = frozenset(
    {
        # presupuesto_mode.py runtime writes
        "_transition_to",
        "_client_type",
        "_is_first_interaction",
        "_tarifa_actual",
        "_chain_next_mode",
        "presupuesto_images_shown",
        "images_shown_for_elements",  # list[str] - element codes whose example images were already shown
        "last_follow_up_sent",
        # consulta_mode.py runtime writes
        "remembered_elementos",
        "remembered_marca",
        "remembered_modelo",
        # expediente_mode.py runtime writes
        "expediente_sub_mode",
        "just_transitioned_from",
        "expediente_transition_marker",
        "expediente_completed",
        "expediente_cancelled",
        "editing_from_review",
        "current_element_field_keys",
        "element_data_all_collected",
        "current_element_code",
        "case_instructions",
        "expediente_intro_message",
        "expediente_intro_sent",
        # expediente_mode.py initialization keys
        "category_id",
        "category_data",
        "category_slug",
        "base_doc_descriptions",
        "personal_data",
        "vehicle_data",
        "taller_data",
        "tariff_tier_id",
        "tariff_amount",
        # guard flags (RC-2: photo-confirmation duplicate guard)
        "_guard_photo_fired_this_turn",
        # expediente_mode.py — element display name cache
        "element_display_names",  # written by _resolve_element_display_names() in expediente_mode.py
        # expediente_mode.py — FSM initialization handoff key (tombstoned by loop_engine.py:264)
        "_fsm_state_init",  # Runtime flag: carries initial FSM state to loop_engine; tombstoned after first consumption
    }
)

# Keys set via _internal_flags from tools
_TOOL_FLAG_KEYS = frozenset(
    {
        # element_tools.py _internal_flags
        "precio_comunicado",
        "imagenes_enviadas",
        "imagenes_envio_intent_creado",
        "pending_variants",
        "elemento_confirmado",
        "element_codes",
        "elementos_confirmados",
        "tarifa_calculada",
        "categoria_slug",
        # image_tools.py _internal_flags
        "imagenes_enviadas",
        "imagenes_envio_intent_creado",
        "imagenes_delivery_request_id",
        "imagenes_delivery_outcome",
        "delivery_scope",
        "delivery_outcome_status",
        "can_narrate_delivery_success",
        "delivery_intent_created",
        # element_data_tools.py _internal_flags
        "all_elements_complete",
        "can_narrate_next_element",
        "fotos_elemento_registered",
        # element_data_tools.py _internal_flags — confirmar_documentacion_base()
        "base_docs_registered",  # written by confirmar_documentacion_base()
        "can_narrate_next_step_details",  # written by confirmar_documentacion_base()
        # element_data_tools.py _internal_flags — completar_elemento_actual()
        "elemento_completed",  # written by completar_elemento_actual()
        # case_tools.py _internal_flags — actualizar_datos_expediente()
        "datos_updated",  # written by actualizar_datos_expediente()
        "confirmed_fields",  # written by actualizar_datos_expediente()
        "can_narrate_completion",  # written by actualizar_datos_expediente(), gestionar_taller(), finalizar_expediente()
        "taller_updated",  # written by gestionar_taller()
        # case_tools.py _internal_flags — finalizar_expediente()
        "case_finalized",  # written by finalizar_expediente()
        # case_tools.py _internal_flags — editar_campo_expediente()
        "expediente_edited",  # written by editar_campo_expediente()
        "edit_target_sub_mode",  # written by editar_campo_expediente()
        # transition_tools.py _internal_flags
        "_transition_to",
        "_chain_next_mode",
    }
)

# Keys set via _context_updates contract (tool_context_contract.py)
_CONTEXT_UPDATE_KEYS = frozenset(
    {
        "element_phase",
        "element_data_status",
        "expediente_sub_mode",
        "current_element_index",
        "base_docs_received",
    }
)

# Keys from case collection compat layer reads (mode-based architecture)
_CASE_COLLECTION_COMPAT_KEYS = frozenset(
    {
        "base_docs_received",
        "base_doc_descriptions",
        "personal_data",
        "vehicle_data",
        "taller_propio",
        "taller_data",
        "received_images",
        # CaseCollectionState fields written to mode_context via case collection update dicts
        "step",  # CaseCollectionState.step — current collection step
        "retry_count",  # CaseCollectionState.retry_count — per-step retry counter
    }
)

# Union of all valid mode_context keys
CANONICAL_MODE_CONTEXT_KEYS: frozenset[str] = (
    _TYPED_DICT_KEYS
    | _MODE_RUNTIME_KEYS
    | _TOOL_FLAG_KEYS
    | _CONTEXT_UPDATE_KEYS
    | _CASE_COLLECTION_COMPAT_KEYS
)


# ---------------------------------------------------------------------------
# Canonical top-level state update keys
# ---------------------------------------------------------------------------
# Every key that mode nodes are allowed to return as top-level state updates.
# Derived from ConversationState TypedDict + keys set in base_mode.py process().

CANONICAL_STATE_UPDATE_KEYS: frozenset[str] = frozenset(
    {
        # Core metadata
        "conversation_id",
        "user_phone",
        "user_name",
        "user_id",
        "client_type",
        # Mode management
        "current_mode",
        "previous_mode",
        "mode_history",
        # Mode context
        "mode_context",
        "draft_contexts",
        # Retry / fallback
        "retry_state",
        # Messages
        "messages",
        "user_message",
        "ai_response",
        "conversation_summary",
        "total_message_count",
        # Conversion tracking
        "mode_message_count",
        "presupuesto_offered_count",
        "last_nudge_message_count",
        # Tool results (transient)
        "pending_images",
        "tarifa_actual",
        "incoming_attachments",
        # Mode chaining (transient)
        "_chain_next_mode",
        "_is_chained_turn",
        # Flags
        "is_first_interaction",
        "agent_disabled",
        "escalation_triggered",
        "escalation_reason",
        "pending_human_decision",
        # Persistent data
        "user_profile",
        "draft_quote",
        # Timestamps
        "created_at",
        "updated_at",
        "last_activity_at",
        # Node tracking
        "last_node",
    }
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_mode_context_update(
    updates: dict[str, Any],
    mode: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Validate a mode_context update dict against the canonical key set.

    Behavior depends on ``ENABLE_STATE_CONTRACT_ENFORCEMENT`` setting:
    - **True**: logs structured warnings for unknown keys and strips them.
    - **False**: passes everything through (no-op) but logs at DEBUG level.

    Args:
        updates: Dict of mode_context key-value pairs to validate.
        mode: Current mode name (for logging context).

    Returns:
        Tuple of (cleaned_updates, warnings_list).
        - cleaned_updates: the validated dict (keys stripped if enforcement ON).
        - warnings_list: list of human-readable warning strings.
    """
    from shared.config import get_settings

    settings = get_settings()
    enforce = settings.ENABLE_STATE_CONTRACT_ENFORCEMENT

    unknown_keys = set(updates.keys()) - CANONICAL_MODE_CONTEXT_KEYS
    if not unknown_keys:
        return updates, []

    warnings: list[str] = [
        f"Unknown mode_context key '{k}' in mode {mode}" for k in sorted(unknown_keys)
    ]

    if enforce:
        logger.warning(
            "non_canonical_mode_context_keys_stripped",
            mode=mode,
            unknown_keys=sorted(unknown_keys),
            count=len(unknown_keys),
        )
        cleaned = {k: v for k, v in updates.items() if k not in unknown_keys}
        return cleaned, warnings
    else:
        logger.debug(
            "non_canonical_mode_context_keys_detected",
            mode=mode,
            unknown_keys=sorted(unknown_keys),
            count=len(unknown_keys),
        )
        return updates, warnings


def validate_state_update(
    updates: dict[str, Any],
    mode: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Validate a top-level state update dict against the canonical key set.

    Behavior depends on ``ENABLE_STATE_CONTRACT_ENFORCEMENT`` setting:
    - **True**: logs structured warnings for unknown keys and strips them.
    - **False**: passes everything through (no-op) but logs at DEBUG level.

    Args:
        updates: Dict of top-level state key-value pairs to validate.
        mode: Current mode name (for logging context).

    Returns:
        Tuple of (cleaned_updates, warnings_list).
        - cleaned_updates: the validated dict (keys stripped if enforcement ON).
        - warnings_list: list of human-readable warning strings.
    """
    from shared.config import get_settings

    settings = get_settings()
    enforce = settings.ENABLE_STATE_CONTRACT_ENFORCEMENT

    unknown_keys = set(updates.keys()) - CANONICAL_STATE_UPDATE_KEYS
    if not unknown_keys:
        return updates, []

    warnings: list[str] = [
        f"Unknown state update key '{k}' in mode {mode}" for k in sorted(unknown_keys)
    ]

    if enforce:
        logger.warning(
            "non_canonical_state_update_keys_stripped",
            mode=mode,
            unknown_keys=sorted(unknown_keys),
            count=len(unknown_keys),
        )
        cleaned = {k: v for k, v in updates.items() if k not in unknown_keys}
        return cleaned, warnings
    else:
        logger.debug(
            "non_canonical_state_update_keys_detected",
            mode=mode,
            unknown_keys=sorted(unknown_keys),
            count=len(unknown_keys),
        )
        return updates, warnings
