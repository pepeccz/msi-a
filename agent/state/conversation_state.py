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

# ---------------------------------------------------------------------------
# Mode definitions
# ---------------------------------------------------------------------------

ConversationMode = Literal[
    "START",
    "CONSULTA_MODE",
    "PRESUPUESTO_MODE",
    "EVALUACION_GATEWAY",
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


def create_empty_retry_state() -> RetryStateData:
    """Create a fresh retry state."""
    return RetryStateData(
        retry_count=0,
        consecutive_errors=0,
        last_error_type=None,
        last_error_message=None,
        first_error_at=None,
        last_retry_at=None,
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
    variante_resuelta: bool
    vehiculo: dict[str, str] | None           # {marca, modelo}
    elementos_confirmados: list[dict[str, Any]]
    element_codes: list[str]
    tarifa_calculada: dict[str, Any] | None
    precio_comunicado: bool
    imagenes_enviadas: bool
    pending_variants: list[dict[str, Any]]    # Variant questions pending
    waiting_for_image_choice: bool            # ✅ NUEVO: User is responding to A/B options
    # ELIMINADO: estimacion_precio (ya no hay "estimación")
    # ELIMINADO: viabilidad_resultado (concepto obsoleto)

    # --- EVALUACION_GATEWAY ---
    quote_accepted: bool | None               # None=not asked, True/False

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
    current conversation state for LangGraph StateGraph.

    All fields are optional (total=False) for partial state updates.

    Designed for mode-based architecture:
    - Modes replace FSM phases
    - Context is per-mode
    - Retry tracking is per-mode
    - Navigation history enables context preservation
    """

    # ── Core Metadata ──────────────────────────────────────────────────────
    conversation_id: str                # LangGraph thread_id
    user_phone: str                     # E.164 format
    user_name: str | None
    user_id: str | None                 # Database UUID
    client_type: str | None             # "particular" | "professional"

    # ── Mode Management ────────────────────────────────────────────────────
    current_mode: ConversationMode
    previous_mode: ConversationMode | None
    mode_history: list[str]             # Navigation stack

    # ── Mode Context ───────────────────────────────────────────────────────
    mode_context: ModeContextData       # Current mode's working data
    draft_contexts: dict[str, Any]      # Saved contexts from other modes
    #   Example: {"PRESUPUESTO_MODE": {elementos_confirmados: [...], ...}}
    #   Used to restore context when returning to a mode

    # ── Retry / Fallback ───────────────────────────────────────────────────
    retry_state: RetryStateData         # Current mode's retry tracking

    # ── Messages ───────────────────────────────────────────────────────────
    messages: Annotated[list[dict[str, Any]], add]  # Append-only history
    user_message: str | None            # Current incoming message
    ai_response: str | None             # Last AI response (for sending)
    conversation_summary: str | None    # Summarised older messages
    total_message_count: int
    
    # ── Conversion Tracking (Sales Funnel) ────────────────────────────────────
    mode_message_count: int             # Messages in current mode (resets on transition)
    presupuesto_offered_count: int      # Times presupuesto was explicitly offered
    last_nudge_message_count: int       # mode_message_count when last nudge was sent

    # ── Tool Results (transient, cleared each turn) ────────────────────────
    pending_images: dict[str, Any] | None    # Images to send to user
    tarifa_actual: dict[str, Any] | None     # Last tariff calculation
    incoming_attachments: list[dict[str, Any]]  # User attachments this turn

    # ── Flags ──────────────────────────────────────────────────────────────
    is_first_interaction: bool
    agent_disabled: bool                # Panic button
    escalation_triggered: bool
    escalation_reason: str | None
    pending_human_decision: bool        # User was offered human help

    # ── Persistent Data (survives mode changes) ────────────────────────────
    user_profile: dict[str, Any]        # Known user data from DB
    draft_quote: dict[str, Any] | None  # Saved quote (presupuesto borrador)

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at: str                     # ISO format
    updated_at: str
    last_activity_at: str

    # ── Node Tracking ──────────────────────────────────────────────────────
    last_node: str | None


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

    # 4. Build mode_history
    history = list(state.get("mode_history", []))
    if current_mode != "START":
        history.append(current_mode)

    return {
        "current_mode": new_mode,
        "previous_mode": current_mode,
        "mode_history": history,
        "mode_context": target_context,
        "draft_contexts": draft_contexts,
        "retry_state": create_empty_retry_state(),
        "mode_message_count": 0,  # Reset counter on mode transition
        "updated_at": now,
        "last_activity_at": now,
    }
