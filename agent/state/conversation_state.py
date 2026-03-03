"""
MSI-a - Conversation State Schema.

New state design based on modes instead of FSM phases.
Compatible with LangGraph StateGraph and Redis checkpointer.

Key differences from v1:
- current_mode replaces fsm_state-based phase detection
- mode_context holds per-mode data (replaces case_collection dict)
- retry_state is per-mode (not global)
- mode_history tracks navigation for context preservation
- No FSM dependency
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Annotated, Any, Literal, TypedDict

from operator import add

from langgraph.types import Overwrite


# ---------------------------------------------------------------------------
# Pending Variant Resolution Types
# ---------------------------------------------------------------------------

class VariantResolution(TypedDict, total=False):
    """A single resolved variant allocation within a pending variant group."""

    variant_code: str       # Resolved variant code (e.g., "SUSPENSION_DEL")
    quantity: int           # How many units assigned to this variant
    confidence: float       # 0.0-1.0 confidence in the resolution
    source: str             # How it was resolved: "user_explicit" | "user_inferred" | "default"


class PendingVariantGroup(TypedDict, total=False):
    """
    Enriched pending variant entry supporting multi-element quantity allocation.

    Backward-compatible: legacy entries (with only ``codigo_base``, ``pregunta``,
    ``opciones``) are normalized at runtime via ``normalize_pending_variants()``.

    Fields:
        pending_id: Unique ID for this variant group (e.g., "SUSPENSION_0").
        codigo_base: Element type code (e.g., "SUSPENSION").
        pregunta: The variant question to ask the user.
        opciones: List of option strings (legacy format kept for prompt rendering).
        cantidad_total: Total units of this element needing variant resolution.
        cantidad_resuelta: How many units have been assigned a variant so far.
        cantidad_pendiente: Remaining = cantidad_total - cantidad_resuelta.
        resoluciones: List of resolution records (variant_code + quantity).
        status: "pending" (none resolved) | "partial" (some resolved) | "resolved" (all done).
    """

    pending_id: str
    codigo_base: str
    pregunta: str
    opciones: list[str]
    cantidad_total: int
    cantidad_resuelta: int
    cantidad_pendiente: int
    resoluciones: list[VariantResolution]
    status: str  # "pending" | "partial" | "resolved"


# ---------------------------------------------------------------------------
# Image Delivery Outcome Types
# ---------------------------------------------------------------------------

ImageDeliveryOutcomeStatus = Literal[
    "not_requested",
    "intent_created",
    "full_success",
    "partial_success",
    "failure",
]


class ImageDeliveryOutcomeData(TypedDict, total=False):
    """Transport-level delivery outcome for queued example images."""

    status: ImageDeliveryOutcomeStatus
    request_id: str | None
    scope: str | None
    requested_count: int
    attempted_count: int
    sent_count: int
    failed_count: int
    transport_error: str | None
    updated_at: str

# ---------------------------------------------------------------------------
# Custom Reducers for State Persistence
# ---------------------------------------------------------------------------
# LangGraph behavior: Fields WITHOUT reducers get REPLACED by state_input.
# Fields WITH reducers get MERGED according to the reducer function.
#
# CRITICAL: Without reducers, mode_context and other fields are lost between
# conversation turns because main.py doesn't include them in state_input.
# ---------------------------------------------------------------------------


def preserve_if_none(current: Any, update: Any) -> Any:
    """
    Preserve checkpoint value if update is None.
    
    Use for fields that should persist unless explicitly changed:
    - current_mode, previous_mode
    - client_type, user_name, user_id
    - Flags (agent_disabled, escalation_triggered, etc.)
    - Timestamps
    
    Args:
        current: Value from checkpoint (previous turn)
        update: Value from current node output
        
    Returns:
        update if not None, else current
    """
    if update is None:
        return current
    return update


def merge_dicts(current: dict | None, update: dict | None) -> dict:
    """
    Deep merge dictionaries, preserving existing keys.
    
    Use for nested data structures:
    - mode_context: Per-mode working data
    - draft_contexts: Saved contexts from other modes
    - user_profile: Known user data
    
    Behavior:
    - If update is None → return current (preserve)
    - If current is None → return update (initialize)
    - Otherwise → shallow merge {**current, **update}
    
    Args:
        current: Value from checkpoint
        update: Value from current node output
        
    Returns:
        Merged dict
    """
    if update is None:
        return current or {}
    if current is None:
        return update or {}
    return {**current, **update}


def merge_retry_state(current: dict | None, update: dict | None) -> dict:
    """
    Merge retry state, preserving counters unless explicitly reset.
    
    Special handling for retry_state to ensure counters persist.
    
    Args:
        current: Value from checkpoint
        update: Value from current node output
        
    Returns:
        Merged retry state
    """
    if update is None:
        return current or {}
    if current is None:
        return update or {}
    # Full replacement if update has retry_count=0 (intentional reset)
    if update.get("retry_count") == 0:
        return update
    return {**current, **update}


def append_unique_list(current: list | None, update: list | None) -> list:
    """
    Append to list, avoiding duplicates for mode_history.
    
    Args:
        current: List from checkpoint
        update: List from current node output
        
    Returns:
        Combined list (current + new items from update)
    """
    if update is None:
        return current or []
    if current is None:
        return update or []
    # Append only items not already in current
    result = list(current)
    for item in update:
        if item not in result:
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Mode definitions
# ---------------------------------------------------------------------------

ConversationMode = Literal[
    "START",
    "CONSULTA_MODE",
    "PRESUPUESTO_MODE",
    "EXPEDIENTE_MODE",
    "ESCALATION",
    "COMPLETED",
]

# Expediente sub-modes (internal to EXPEDIENTE_MODE)
ExpedienteSubMode = Literal[
    "DATOS_PERSONALES",
    "DATOS_VEHICULO",
    "DOCUMENTACION_ELEMENTOS",
    "DOCUMENTACION_BASE",
    "TALLER",
    "REVISION",
]

# ---------------------------------------------------------------------------
# Retry state (per-mode)
# ---------------------------------------------------------------------------

class RetryStateData(TypedDict, total=False):
    """Retry tracking data. Resets when changing modes."""

    retry_count: int
    consecutive_errors: int
    last_error_type: str | None
    last_error_message: str | None
    first_error_at: str | None   # ISO timestamp
    last_retry_at: str | None    # ISO timestamp
    last_validation_context: dict[str, Any] | None  # Phase 3: validation error context


def create_empty_retry_state() -> RetryStateData:
    """Create a fresh retry state."""
    return RetryStateData(
        retry_count=0,
        consecutive_errors=0,
        last_error_type=None,
        last_error_message=None,
        first_error_at=None,
        last_retry_at=None,
        last_validation_context=None,
    )


# ---------------------------------------------------------------------------
# Mode context (per-mode, survives within a mode)
# ---------------------------------------------------------------------------

class ModeContextData(TypedDict, total=False):
    """
    Contextual data for the current mode.

    Each mode uses a subset of these fields.
    The context is preserved when returning to a mode (via draft_contexts).
    """

    # --- CONSULTA_MODE ---
    consulta_history: list[dict[str, str]]  # [{question, answer}]

    # --- PRESUPUESTO_MODE (fusionado con ex-VIABILIDAD) ---
    categoria_slug: str | None
    elemento_tentativo: dict[str, Any] | None
    elemento_confirmado: dict[str, Any] | None
    # Removed variante_resuelta flag (REFACTOR-001): derived from len(pending_variants) == 0
    vehiculo: dict[str, str] | None           # {marca, modelo}
    elementos_confirmados: list[dict[str, Any]]
    element_codes: list[str]
    tarifa_calculada: dict[str, Any] | None
    precio_comunicado: bool
    imagenes_enviadas: bool
    imagenes_envio_intent_creado: bool
    imagenes_delivery_request_id: str | None
    imagenes_delivery_outcome: ImageDeliveryOutcomeData | None
    pending_variants: list[PendingVariantGroup | dict[str, Any]]  # Variant questions pending (enriched or legacy dicts)
    waiting_for_image_choice: bool            # ✅ NUEVO: User is responding to A/B options
    # ELIMINADO: estimacion_precio (ya no hay "estimación")
    # ELIMINADO: viabilidad_resultado (concepto obsoleto)
    # ELIMINADO: precio_calculado (REFACTOR-001): redundant with tarifa_calculada["datos"]["price"]
    # ELIMINADO: opcion_seleccionada (REFACTOR-001): never read anywhere

    # --- EXPEDIENTE_MODE ---
    case_id: str | None                       # UUID of Case record
    sub_modo: ExpedienteSubMode | None
    datos_personales: dict[str, str | None]
    datos_vehiculo: dict[str, str | None]
    documentacion_elementos: dict[str, Any]   # {code: {photos_done, data_done, fields}}
    documentacion_base: dict[str, Any]
    datos_taller: dict[str, str | None] | None
    taller_propio: bool | None
    tariff_tier_id: str | None
    tariff_amount: float | None
    current_element_index: int
    element_phase: str                        # "photos" | "data"
    element_data_status: dict[str, str]       # {code: "pending"|"photos_done"|...}
    base_docs_received: bool
    received_images: list[str]


# ---------------------------------------------------------------------------
# Main conversation state for LangGraph StateGraph
# ---------------------------------------------------------------------------

class ConversationState(TypedDict, total=False):
    """
    Current conversation state for LangGraph StateGraph.

    All fields are optional (total=False) for partial state updates.

    Designed for mode-based architecture:
    - Modes replace FSM phases
    - Context is per-mode
    - Retry tracking is per-mode
    - Navigation history enables context preservation
    
    IMPORTANT - Reducers:
    - Fields with Annotated[..., reducer] persist between turns
    - Fields WITHOUT reducers get REPLACED by state_input each turn
    - Use preserve_if_none for simple values that should persist
    - Use merge_dicts for nested dicts that should be merged
    """

    # ── Core Metadata ──────────────────────────────────────────────────────
    conversation_id: Annotated[str, preserve_if_none]  # LangGraph thread_id
    user_phone: Annotated[str, preserve_if_none]       # E.164 format
    user_name: Annotated[str | None, preserve_if_none]
    user_id: Annotated[str | None, preserve_if_none]   # Database UUID
    client_type: Annotated[str | None, preserve_if_none]  # "particular" | "professional"

    # ── Mode Management ────────────────────────────────────────────────────
    current_mode: Annotated[ConversationMode, preserve_if_none]
    previous_mode: Annotated[ConversationMode | None, preserve_if_none]
    mode_history: Annotated[list[str], append_unique_list]  # Navigation stack

    # ── Mode Context (CRITICAL - must persist between turns) ──────────────
    mode_context: Annotated[ModeContextData, merge_dicts]  # Current mode's working data
    draft_contexts: Annotated[dict[str, Any], merge_dicts]  # Saved contexts from other modes
    #   Example: {"PRESUPUESTO_MODE": {elementos_confirmados: [...], ...}}
    #   Used to restore context when returning to a mode

    # ── Retry / Fallback ───────────────────────────────────────────────────
    retry_state: Annotated[RetryStateData, merge_retry_state]  # Current mode's retry tracking

    # ── Messages ───────────────────────────────────────────────────────────
    messages: Annotated[list[dict[str, Any]], add]  # Append-only history
    user_message: str | None            # Current incoming message (transient, OK to replace)
    ai_response: str | None             # Last AI response (transient, OK to replace)
    conversation_summary: Annotated[str | None, preserve_if_none]  # Summarised older messages
    total_message_count: Annotated[int, preserve_if_none]
    
    # ── Conversion Tracking (Sales Funnel) ────────────────────────────────────
    mode_message_count: Annotated[int, preserve_if_none]  # Messages in current mode
    presupuesto_offered_count: Annotated[int, preserve_if_none]  # Times presupuesto offered
    last_nudge_message_count: Annotated[int, preserve_if_none]  # When last nudge was sent

    # ── Tool Results (transient, cleared each turn) ────────────────────────
    pending_images: dict[str, Any] | None    # Images to send to user (transient)
    tarifa_actual: dict[str, Any] | None     # Last tariff calculation (transient)
    incoming_attachments: list[dict[str, Any]]  # User attachments this turn (transient)

    # ── Mode Chaining (transient) ──────────────────────────────────────────
    _chain_next_mode: bool | None            # Signal: re-invoke graph for next mode in same turn
    _is_chained_turn: bool | None            # Signal: this turn is a synthetic continuation

    # ── Flags ──────────────────────────────────────────────────────────────
    is_first_interaction: Annotated[bool, preserve_if_none]
    agent_disabled: Annotated[bool, preserve_if_none]  # Panic button
    escalation_triggered: Annotated[bool, preserve_if_none]
    escalation_reason: Annotated[str | None, preserve_if_none]
    pending_human_decision: Annotated[bool, preserve_if_none]  # User was offered human help

    # ── Persistent Data (survives mode changes) ────────────────────────────
    user_profile: Annotated[dict[str, Any], merge_dicts]  # Known user data from DB
    draft_quote: Annotated[dict[str, Any] | None, preserve_if_none]  # Saved quote

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at: Annotated[str, preserve_if_none]  # ISO format
    updated_at: Annotated[str, preserve_if_none]
    last_activity_at: Annotated[str, preserve_if_none]

    # ── Node Tracking ──────────────────────────────────────────────────────
    last_node: Annotated[str | None, preserve_if_none]


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def create_initial_state(
    conversation_id: str,
    phone: str,
    user_name: str | None = None,
    user_id: str | None = None,
    client_type: str | None = None,
    user_profile: dict[str, Any] | None = None,
) -> ConversationState:
    """
    Create a fresh conversation state for a new conversation.

    Args:
        conversation_id: Unique conversation / thread ID.
        phone: User phone in E.164 format.
        user_name: Optional user display name.
        user_id: Optional database user UUID.
        client_type: Optional "particular" or "professional".
        user_profile: Optional pre-loaded user data from DB.

    Returns:
        A fully initialised ConversationState.
    """
    now = datetime.now(UTC).isoformat()

    return ConversationState(
        # Core
        conversation_id=conversation_id,
        user_phone=phone,
        user_name=user_name,
        user_id=user_id,
        client_type=client_type,
        # Mode
        current_mode="START",
        previous_mode=None,
        mode_history=[],
        # Context
        mode_context=ModeContextData(),
        draft_contexts={},
        # Retry
        retry_state=create_empty_retry_state(),
        # Messages
        messages=[],
        user_message=None,
        ai_response=None,
        conversation_summary=None,
        total_message_count=0,
        # Tool results
        pending_images=None,
        tarifa_actual=None,
        incoming_attachments=[],
        # Flags
        is_first_interaction=True,
        agent_disabled=False,
        escalation_triggered=False,
        escalation_reason=None,
        pending_human_decision=False,
        # Persistent
        user_profile=user_profile or {},
        draft_quote=None,
        # Timestamps
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        # Debug
        last_node=None,
    )


def transition_mode(
    state: ConversationState,
    new_mode: ConversationMode,
    *,
    preserve_keys: list[str] | None = None,
    new_context: ModeContextData | None = None,
) -> dict[str, Any]:
    """
    Build a state update dict for a mode transition.

    This function does NOT mutate ``state``; it returns a dict suitable
    for merging by the LangGraph reducer.

    Behaviour:
    1. Save current mode_context into draft_contexts (for later restore).
    2. Reset retry_state (new mode, new counter).
    3. Set new mode as current_mode.
    4. Optionally carry over specific keys from the old context.
    5. Optionally restore a previously saved draft context.

    Args:
        state: Current conversation state.
        new_mode: Target mode to transition to.
        preserve_keys: Keys from current context to carry into new mode.
        new_context: Explicit context dict for the new mode.

    Returns:
        Dict with state updates (current_mode, mode_context, etc.)
    """
    now = datetime.now(UTC).isoformat()
    current_mode = state.get("current_mode", "START")
    current_context = state.get("mode_context", {})

    # 1. Save current context as draft
    draft_contexts = dict(state.get("draft_contexts", {}))
    if current_mode != "START" and current_context:
        draft_contexts[current_mode] = dict(current_context)

    # 2. Build new context
    if new_context is not None:
        target_context = dict(new_context)
    elif new_mode in draft_contexts:
        # Restore previously saved context for this mode
        target_context = dict(draft_contexts.pop(new_mode))
    else:
        target_context = {}

    # 3. Carry over specified keys from old context
    if preserve_keys:
        for key in preserve_keys:
            if key in current_context and key not in target_context:
                target_context[key] = current_context[key]

    # 3b. Preserve image tracking across mode transitions
    # These keys track whether images were shown in a previous mode,
    # so downstream modes can avoid re-offering the same images.
    IMAGE_TRACKING_KEYS = ["presupuesto_images_shown", "images_shown_for_elements"]
    for key in IMAGE_TRACKING_KEYS:
        if key in current_context and key not in target_context:
            target_context[key] = current_context[key]

    # 4. Build mode_history
    history = list(state.get("mode_history", []))
    if current_mode != "START":
        history.append(current_mode)

    return {
        "current_mode": new_mode,
        "previous_mode": current_mode,
        "mode_history": history,
        "mode_context": Overwrite(target_context),       # Bypass merge_dicts → clean context
        "draft_contexts": Overwrite(draft_contexts),     # Bypass merge_dicts → pop() works
        "retry_state": create_empty_retry_state(),
        "mode_message_count": 0,  # Reset counter on mode transition
        "updated_at": now,
        "last_activity_at": now,
    }
