"""
MSI-a - Conversation Graph.

The main LangGraph StateGraph that wires together:
- Entry node (message preprocessing)
- Router node (intent classification + digression detection)
- Mode nodes (one per conversation mode)
- Escalation node

Architecture (POST FUSION + MEMORY REFACTOR):
                    ┌──────────────┐
    START ──────────│  preprocess   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    router     │
                    └──────┬───────┘
                           │ (conditional)
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐  ┌──────────┐
        │ consulta  │ │presupuest│  │expediente│
        └────┬─────┘ └────┬─────┘  └────┬─────┘
             │            │              │
             └────────────┼──────────────┘
                          │
                   ┌──────▼───────┐
                   │maybe_summarize│ ──── END
                   └──────────────┘

Changes from v2.0:
- Removed VIABILIDAD_MODE node
- Removed EVALUACION_GATEWAY node (dead code — confirmar_presupuesto transitions directly to EXPEDIENTE)
- PRESUPUESTO_MODE is now main entry point (handles ~90% traffic)
- Direct routing from START → PRESUPUESTO

Each mode node returns state updates, including optionally a new
``current_mode`` which causes the next invocation to route differently.

Persistence: Uses Redis checkpointer (recycled from v1).

Orphaned Expediente Recovery (recover-expediente-from-db):
- Redis checkpointer TTL is 24h; expedientes can take days to complete.
- On first message (START mode), preprocess_node checks PostgreSQL for an
  active Case by user_id. If found, it injects a recovery signal so
  EXPEDIENTE_MODE can resume without re-creation.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

import structlog
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, Overwrite, RetryPolicy

from agent.state.conversation_state import (
    ConversationState,
    ConversationMode,
    create_empty_retry_state,
    transition_mode,
)
from agent.router.intent_router import (
    IntentResult,
    UserIntent,
    INTENT_TO_MODE,
    get_intent_router,
)
from agent.router.digression_manager import get_digression_manager
from agent.router.mode_transitions import (
    is_transition_allowed,
    validate_transition,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Transient error predicate + LangGraph RetryPolicy for LLM nodes (ADR-012)
# ---------------------------------------------------------------------------


def _is_transient_error(exc: BaseException) -> bool:
    """
    Return True if *exc* is a transient infrastructure error.

    Used by _LLM_RETRY to tell LangGraph which exceptions should trigger
    automatic node retries (Tier 1 of the 4-tier error handling strategy).
    See ADR-012 for the full strategy.

    Args:
        exc: The exception to classify.

    Returns:
        True for network / LLM API errors worth retrying.
        False for business errors (validation, logic, user confusion).
    """
    import httpx

    TRANSIENT: tuple[type[BaseException], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        ConnectionError,
        TimeoutError,
    )
    try:
        from openai import APIConnectionError, APITimeoutError, InternalServerError

        TRANSIENT = (*TRANSIENT, APIConnectionError, APITimeoutError, InternalServerError)
    except ImportError:
        pass

    return isinstance(exc, TRANSIENT)


# Applied only to nodes that call the LLM (consulta, presupuesto, expediente).
# Preprocess, router, and maybe_summarize do no LLM work and should fail fast.
_LLM_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=1.0,
    backoff_factor=2.0,
    retry_on=_is_transient_error,
)


# Outer graph recursion limit.
# max_iterations (10) * 2 (nodes per iter) + buffer = ~32.
# This accommodates outer graph steps (preprocess + router + mode + END = ~4)
# plus potential chained mode calls.
# Must be passed at ainvoke() time — LangGraph ignores compiled.config patches.
_RECURSION_LIMIT = 32


# ---------------------------------------------------------------------------
# Node names (constants to avoid typos)
# ---------------------------------------------------------------------------

NODE_PREPROCESS = "preprocess"
NODE_ROUTER = "router"
NODE_CONSULTA = "consulta_mode"
NODE_PRESUPUESTO = "presupuesto_mode"
NODE_EXPEDIENTE = "expediente_mode"
NODE_ESCALATION = "escalation"
NODE_SUMMARIZE = "maybe_summarize"

# All mode node names mapped from ConversationMode values
MODE_TO_NODE: dict[str, str] = {
    "CONSULTA_MODE": NODE_CONSULTA,
    "PRESUPUESTO_MODE": NODE_PRESUPUESTO,
    "EXPEDIENTE_MODE": NODE_EXPEDIENTE,
    "ESCALATION": NODE_ESCALATION,
}


# ---------------------------------------------------------------------------
# Preprocess node
# ---------------------------------------------------------------------------


async def preprocess_node(state: ConversationState, *, store=None) -> dict[str, Any]:
    """
    Entry node: prepare the incoming message for processing.

    Responsibilities:
    - Extract and normalise user message
    - Increment message counter
    - Update activity timestamp
    - Handle agent_disabled flag (panic button)
    - Load user profile from Store (WS3: cross-thread memory)

    This is deliberately lightweight — routing logic lives in router_node.
    """
    now = datetime.now(UTC).isoformat()
    user_message = state.get("user_message", "")

    logger.info(
        "preprocess_incoming",
        conversation_id=state.get("conversation_id"),
        mode=state.get("current_mode", "START"),
        message_length=len(user_message) if user_message else 0,
    )

    # Panic button: if agent is disabled, route to escalation immediately
    if state.get("agent_disabled", False):
        return {
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "escalation_reason": "agent_disabled",
            "last_node": NODE_PREPROCESS,
            "updated_at": now,
            "last_activity_at": now,
        }

    total = state.get("total_message_count", 0) + 1
    mode_msg_count = state.get("mode_message_count", 0) + 1

    base_updates: dict[str, Any] = {
        "total_message_count": total,
        "mode_message_count": mode_msg_count,
        "is_first_interaction": total == 1,
        "last_node": NODE_PREPROCESS,
        "updated_at": now,
        "last_activity_at": now,
        # Reset transient fields — prevent cross-turn persistence (Bug B fix)
        "pending_images": None,
        "tarifa_actual": None,
        "incoming_attachments": [],
        "ai_response": None,  # Defensive: prevent stale response if mode node fails
    }

    # ── Orphaned expediente recovery ────────────────────────────────────
    # When the Redis checkpoint expires (24h TTL) but an expediente is still
    # active in PostgreSQL, the agent starts fresh (START mode, no context).
    # Check for an orphaned active case on the very first message so the
    # agent can offer to resume it rather than starting from scratch.
    #
    # Conditions for recovery check:
    # 1. This is the first message (total == 1) — fresh conversation thread
    # 2. current_mode is START (no live checkpoint)
    # 3. The mode_context has no case_id (not already in expediente flow)
    current_mode = state.get("current_mode", "START")
    mode_context = state.get("mode_context") or {}
    has_active_case_in_context = bool(mode_context.get("case_id"))

    if total == 1 and current_mode == "START" and not has_active_case_in_context:
        recovered = await _try_recover_orphaned_expediente(state)
        if recovered:
            # Inject recovery signal into state — router will route to EXPEDIENTE_MODE
            # and expediente_mode will pick up pending_recovery_case from mode_context
            logger.info(
                "orphaned_expediente_recovered",
                conversation_id=state.get("conversation_id"),
                case_id=recovered.get("case_id"),
                case_status=recovered.get("status"),
                element_codes=recovered.get("element_codes"),
            )
            base_updates["current_mode"] = "EXPEDIENTE_MODE"
            # Wrap in Overwrite so merge_dicts doesn't mix with stale checkpoint keys
            base_updates["mode_context"] = Overwrite(
                {
                    "pending_recovery_case": recovered,
                    # Pre-seed the expediente sub-mode inferred from DB state
                    "expediente_sub_mode": recovered.get(
                        "inferred_sub_mode", "collect_element_data"
                    ),
                }
            )

    # ── Cross-thread profile loading (WS3) ──────────────────────────────
    # On first message, load user profile from Store to enrich state with
    # data from previous conversations (past quotes, expedientes, etc.)
    if total == 1 and store is not None:
        user_phone = state.get("user_phone", "")
        if user_phone:
            from agent.graph.user_profile_store import load_user_profile  # noqa: PLC0415

            profile = await load_user_profile(store, user_phone)
            if profile:
                # Only inject fields not already set by main.py's DB lookup
                if not state.get("user_name") and profile.get("user_name"):
                    base_updates["user_name"] = profile["user_name"]
                if not state.get("client_type") and profile.get("client_type"):
                    base_updates["client_type"] = profile["client_type"]
                # Merge profile into user_profile field for downstream access
                base_updates["user_profile"] = profile
                logger.info(
                    "user_profile_loaded_from_store",
                    user_phone=user_phone,
                    has_past_quotes=bool(profile.get("past_quotes")),
                    has_past_expedientes=bool(profile.get("past_expedientes")),
                )

    return base_updates


async def _try_recover_orphaned_expediente(
    state: ConversationState,
) -> dict[str, Any] | None:
    """
    Query PostgreSQL for an active Case belonging to this user.

    Called from preprocess_node only on the first message of a fresh
    conversation thread (total_message_count == 1, current_mode == START).

    Recovery conditions:
    - user_id is known (looked up from DB in main.py before graph invocation)
    - An active Case exists with status in ["collecting", "pending_images"]
    - The case is NOT from the current conversation_id (that would already
      be handled by _initialize_mode_context in expediente_mode.py)

    Returns a recovery dict suitable for mode_context["pending_recovery_case"],
    or None if no recovery is needed.

    This function is deliberately defensive — any DB error returns None so
    the normal flow continues unaffected.
    """
    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id", "")

    if not user_id:
        # New user not yet in DB — no case to recover
        return None

    try:
        import uuid as _uuid
        from sqlalchemy import select as _select
        from database.connection import get_async_session
        from database.models import Case, CaseElementData

        RECOVERABLE_STATUSES = ["collecting", "pending_images"]

        async with get_async_session() as session:
            # Look for the most recently active case by user_id
            result = await session.execute(
                _select(Case)
                .where(Case.user_id == _uuid.UUID(user_id))
                .where(Case.status.in_(RECOVERABLE_STATUSES))
                .order_by(Case.updated_at.desc())
                .limit(1)
            )
            case = result.scalar_one_or_none()

            if not case:
                return None

            # If the case belongs to THIS conversation, _initialize_mode_context
            # in expediente_mode.py will handle it via its own query. Skip.
            if case.conversation_id == conversation_id:
                return None

            # Load CaseElementData to determine sub-mode progress
            ced_result = await session.execute(
                _select(CaseElementData).where(CaseElementData.case_id == case.id)
            )
            ced_rows = list(ced_result.scalars().all())
            ced_by_code: dict[str, str] = {
                row.element_code: row.status for row in ced_rows
            }

            codes = case.element_codes or []

            # Infer sub-mode from DB state
            inferred_sub_mode = _infer_sub_mode_from_db(case, ced_by_code, codes)

            # Resolve category_slug (Case stores category_id FK, not slug)
            category_slug = case.category.slug if case.category else None
            # category is lazy="selectin" so already loaded by relationship

            created_at_str = (
                case.created_at.strftime("%d/%m/%Y a las %H:%M")
                if case.created_at
                else "fecha desconocida"
            )

            # Compute time gap since last activity so the LLM can calibrate
            # the recovery greeting (e.g. "a few minutes" vs "a few days ago").
            last_activity = case.updated_at or case.created_at
            if last_activity:
                gap = datetime.now(UTC) - last_activity
                raw_hours = gap.total_seconds() / 3600
                # Never negative (clock skew / sub-second precision)
                time_gap_hours = round(max(0.0, raw_hours), 1)
                last_activity_at_iso = last_activity.isoformat()
            else:
                time_gap_hours = None
                last_activity_at_iso = None

            return {
                "case_id": str(case.id),
                "original_conversation_id": case.conversation_id,
                "status": case.status,
                "category_slug": category_slug,
                "category_id": str(case.category_id) if case.category_id else None,
                "element_codes": codes,
                "tariff_tier_id": str(case.tariff_tier_id)
                if case.tariff_tier_id
                else None,
                "tariff_amount": float(case.tariff_amount)
                if case.tariff_amount
                else None,
                "inferred_sub_mode": inferred_sub_mode,
                "element_data_status": ced_by_code,
                "created_at_str": created_at_str,
                # Personal/vehicle already in DB? Tells LLM how far along we got
                "has_vehicle_data": bool(case.vehiculo_marca and case.vehiculo_modelo),
                "has_personal_data": bool(case.itv_nombre),
                # Time gap signals for recovery UX (T-22)
                "time_gap_hours": time_gap_hours,
                "last_activity_at_iso": last_activity_at_iso,
            }

    except Exception as e:
        logger.warning(
            "orphaned_expediente_recovery_failed",
            user_id=user_id,
            conversation_id=conversation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _infer_sub_mode_from_db(
    case: Any,
    ced_by_code: dict[str, str],
    element_codes: list[str],
) -> str:
    """
    Infer the expediente sub-mode from persisted DB data.

    Decision tree (first matching condition wins):
    1. All elements "completed" AND vehicle_data filled → collect_workshop or later
    2. All elements "completed" → collect_base_docs
    3. Some elements "pending_data" → collect_element_data (data phase for first pending)
    4. Default → collect_element_data (photos phase)
    """
    if not element_codes:
        return "collect_personal"

    statuses = [ced_by_code.get(code, "pending_photos") for code in element_codes]
    all_completed = all(s == "completed" for s in statuses)
    any_pending_data = any(s == "pending_data" for s in statuses)

    if all_completed:
        # Check if personal data was collected
        if case.itv_nombre:
            # ITV is the last personal field collected — if set, personal is done
            if case.vehiculo_marca and case.vehiculo_modelo:
                # Vehicle done too — workshop or later
                if case.taller_propio is not None:
                    return "review_summary"
                return "collect_workshop"
            return "collect_vehicle"
        # Base docs phase (after elements, before personal)
        return "collect_base_docs"

    if any_pending_data:
        return "collect_element_data"

    # Default: start from element photos
    return "collect_element_data"


# ---------------------------------------------------------------------------
# Router node
# ---------------------------------------------------------------------------


async def router_node(state: ConversationState) -> dict[str, Any]:
    """
    Central routing logic.

    Decides which mode node should process the current message.

    Strategy:
    1. If current_mode is active (not START) and not terminal:
       a. Check for digression (focused modes only)
       b. If digression → transition to target mode
       c. If not → stay in current mode (no state change needed)
    2. If current_mode is START or needs re-routing:
       a. Classify intent
       b. Transition to suggested mode

    The router does NOT process the message — it only decides WHERE to route.
    """
    current_mode: str = state.get("current_mode", "START")
    user_message: str = state.get("user_message", "")
    now = datetime.now(UTC).isoformat()

    logger.info(
        "router_evaluating",
        current_mode=current_mode,
        message_preview=user_message[:60],
    )

    # ── FIX-4: Detect unexpected state reset ─────────────────────────────
    mode_context = state.get("mode_context") or {}
    if current_mode == "START" and mode_context:
        has_tarifa = bool(mode_context.get("tarifa_calculada"))
        has_categoria = bool(mode_context.get("categoria_slug"))
        has_elements = bool(mode_context.get("element_codes"))
        message_count = state.get("message_count", 0)

        if has_tarifa or has_categoria or has_elements:
            logger.warning(
                "unexpected_state_reset_detected",
                conversation_id=state.get("conversation_id"),
                mode_context_keys=list(mode_context.keys()),
                has_tarifa=has_tarifa,
                has_categoria=has_categoria,
                has_elements=has_elements,
                message_count=message_count,
            )
            # Auto-recover: if we have tarifa data, restore to PRESUPUESTO_MODE
            if has_tarifa and has_categoria:
                logger.warning(
                    "auto_recovering_to_presupuesto",
                    conversation_id=state.get("conversation_id"),
                    categoria=mode_context.get("categoria_slug"),
                )
                current_mode = "PRESUPUESTO_MODE"
                # Return state update to restore the mode
                return {
                    "current_mode": "PRESUPUESTO_MODE",
                    "last_node": NODE_ROUTER,
                    "updated_at": now,
                }

    # ── Terminal modes: should not be routed ─────────────────────────────
    if current_mode in ("ESCALATION", "COMPLETED"):
        return {"last_node": NODE_ROUTER, "updated_at": now}

    # ── Active mode: check for digression first ─────────────────────────
    if current_mode != "START":
        digression_mgr = get_digression_manager()
        digression = await digression_mgr.check(
            message=user_message,
            current_mode=current_mode,
            mode_context=state.get("mode_context"),
        )

        if digression.is_digression:
            target = digression.target_mode or "CONSULTA_MODE"
            allowed, reason = validate_transition(current_mode, target)

            if allowed:
                updates = transition_mode(state, target)
                updates["last_node"] = NODE_ROUTER
                logger.info(
                    "digression_transition",
                    from_mode=current_mode,
                    to_mode=target,
                    type=digression.digression_type.value,
                )
                return updates
            else:
                logger.warning(
                    "digression_blocked",
                    from_mode=current_mode,
                    to_mode=target,
                    reason=reason,
                )
                # Stay in current mode — the mode node will handle it
                return {"last_node": NODE_ROUTER, "updated_at": now}

        # ── Re-evaluate intent in CONSULTA_MODE ─────────────────────────
        # CONSULTA is permissive (allows_digression=True), so the digression
        # manager never fires. But if the user clearly wants a quote
        # ("quiero homologar X"), we should transition to PRESUPUESTO_MODE
        # instead of letting the LLM handle it without pricing tools.
        if current_mode == "CONSULTA_MODE":
            intent_router = get_intent_router()
            mc = state.get("mode_context") or {}
            context_hints = {
                "precio_comunicado": bool(mc.get("precio_comunicado")),
                "tarifa_calculada": bool(mc.get("tarifa_calculada")),
            }
            intent_result = await intent_router.classify(
                message=user_message,
                current_mode=current_mode,
                history=state.get("messages", [])[-6:],
                mode_context=context_hints,
            )
            if (
                intent_result.intent == UserIntent.PRESUPUESTO_DIRECTO
                and intent_result.confidence >= 0.75
            ):
                updates = transition_mode(state, "PRESUPUESTO_MODE")
                updates["last_node"] = NODE_ROUTER
                logger.info(
                    "consulta_to_presupuesto_reclassification",
                    intent=intent_result.intent.value,
                    confidence=intent_result.confidence,
                    message_preview=user_message[:60],
                )
                return updates

        # No digression (and no reclassification): stay in current mode
        return {"last_node": NODE_ROUTER, "updated_at": now}

    # ── START mode: classify intent and route ────────────────────────────
    intent_router = get_intent_router()
    mc = state.get("mode_context") or {}
    context_hints = {
        "precio_comunicado": bool(mc.get("precio_comunicado")),
        "tarifa_calculada": bool(mc.get("tarifa_calculada")),
    }
    intent_result: IntentResult = await intent_router.classify(
        message=user_message,
        current_mode=current_mode,
        history=state.get("messages", [])[-6:],
        mode_context=context_hints,
    )

    target_mode = _resolve_target_mode(intent_result, state)

    logger.info(
        "intent_routed",
        intent=intent_result.intent.value,
        confidence=intent_result.confidence,
        target_mode=target_mode,
    )

    # ── CANCELAR: full reset — clear mode context and restart ────────────
    if intent_result.intent == UserIntent.CANCELAR:
        return {
            "current_mode": "START",
            "mode_context": Overwrite({}),
            "retry_state": create_empty_retry_state(),
            "ai_response": "Entendido, empezamos de nuevo. ¿En qué puedo ayudarte?",
            "last_node": NODE_ROUTER,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    # Build transition
    updates = transition_mode(state, target_mode)
    updates["last_node"] = NODE_ROUTER

    # Attach clarification question if confidence was low
    if intent_result.clarification_question:
        # The mode node will see this and can use it
        ctx = dict(updates.get("mode_context", {}))
        ctx["clarification_question"] = intent_result.clarification_question
        updates["mode_context"] = ctx

    return updates


def _resolve_target_mode(
    intent_result: IntentResult,
    state: ConversationState,
) -> str:
    """
    Resolve the target mode from an IntentResult.

    Handles context-dependent intents (CONFIRMACION, RECHAZO)
    that depend on previous mode.
    """
    suggested = intent_result.suggested_mode

    # Cancel → unconditional reset to START (handled specially in router_node)
    if intent_result.intent == UserIntent.CANCELAR:
        return "START"

    # Context-dependent intents
    if intent_result.intent == UserIntent.CONFIRMACION:
        prev = state.get("previous_mode")
        if prev == "PRESUPUESTO_MODE":
            return "EXPEDIENTE_MODE"
        # Default: treat as general query
        return "CONSULTA_MODE"

    if intent_result.intent == UserIntent.RECHAZO:
        return "CONSULTA_MODE"

    # If suggested mode is empty or invalid, default to CONSULTA
    if not suggested or suggested not in MODE_TO_NODE:
        return "CONSULTA_MODE"

    return suggested


# ---------------------------------------------------------------------------
# Mode routing function (conditional edge)
# ---------------------------------------------------------------------------


def route_to_mode(state: ConversationState) -> str:
    """
    Conditional edge function: returns the node name for the current mode.

    Called AFTER router_node to determine which mode node to invoke.
    """
    current_mode: str = state.get("current_mode", "CONSULTA_MODE")

    # Map mode to node name
    node = MODE_TO_NODE.get(current_mode)
    if node:
        return node

    # Terminal / reset modes — router already set ai_response
    if current_mode in ("COMPLETED", "START"):
        return END

    # Default fallback
    logger.warning("unknown_mode_routing_to_consulta", mode=current_mode)
    return NODE_CONSULTA


# ---------------------------------------------------------------------------
# Mode nodes (all real implementations)
# ---------------------------------------------------------------------------

# CONSULTA_MODE
_consulta_node_instance: Any = None


def _get_consulta_node() -> Any:
    """Lazy-load ConsultaModeNode to avoid circular imports."""
    global _consulta_node_instance
    if _consulta_node_instance is None:
        from agent.modes.consulta_mode import ConsultaModeNode

        _consulta_node_instance = ConsultaModeNode()
    return _consulta_node_instance


async def consulta_mode_node(state: ConversationState) -> Command:
    """CONSULTA_MODE node — delegates to ConsultaModeNode.process()."""
    node = _get_consulta_node()
    result = await node.process(state)
    return Command(goto=NODE_SUMMARIZE, update=result)


# PRESUPUESTO_MODE (includes former VIABILIDAD_MODE)
_presupuesto_node_instance: Any = None


def _get_presupuesto_node() -> Any:
    """Lazy-load PresupuestoModeNode to avoid circular imports."""
    global _presupuesto_node_instance
    if _presupuesto_node_instance is None:
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        _presupuesto_node_instance = PresupuestoModeNode()
    return _presupuesto_node_instance


async def presupuesto_mode_node(state: ConversationState) -> Command:
    """PRESUPUESTO_MODE node — delegates to PresupuestoModeNode.process().

    Returns Command(goto=...) in ALL cases:
    - Normal turn  → goto=maybe_summarize
    - EXPEDIENTE transition → goto=expediente_mode (WS1: internal routing via Command)
    """
    node = _get_presupuesto_node()
    result = await node.process(state)

    # Detect transition signal from confirmar_presupuesto tool
    target_mode = result.pop("current_mode", None)
    if target_mode == "EXPEDIENTE_MODE":
        # Build transition state update (saves draft context, resets retry, etc.)
        transition_updates = transition_mode(state, "EXPEDIENTE_MODE")
        # Merge mode-node result on top of transition updates
        # (ai_response, mode_context, messages from the mode node take precedence)
        merged = {**transition_updates, **result}
        logger.info(
            "presupuesto_command_goto_expediente",
            conversation_id=state.get("conversation_id"),
        )
        return Command(goto=NODE_EXPEDIENTE, update=merged)

    # Normal case: restore current_mode if it was set to something else
    if target_mode is not None:
        result["current_mode"] = target_mode

    return Command(goto=NODE_SUMMARIZE, update=result)


async def escalation_node(state: ConversationState) -> dict[str, Any]:
    """
    Handle escalation to human agent.

    This node performs the full escalation flow:
    1. Disables bot in Chatwoot (atencion_automatica=False)
    2. Adds labels ("escalado") to the conversation
    3. Adds a private note with escalation context
    4. Attempts team assignment (best-effort)
    5. Saves Escalation record to PostgreSQL
    6. Returns farewell message to user

    Triggered by:
    - FallbackAction.ESCALATE_TO_HUMAN (retry limit exceeded)
    - Panic button (agent disabled)
    - Mode transition to ESCALATION
    """
    from agent.services.escalation_service import perform_escalation

    conversation_id = state.get("conversation_id", "")
    user_id = state.get("user_id")
    user_phone = state.get("user_phone", "desconocido")
    reason = state.get("escalation_reason", "user_request")
    previous_mode = state.get("previous_mode", state.get("current_mode"))

    # Determine source from context
    if "retry_limit" in str(reason):
        source = "fallback"
    elif reason == "panic_button":
        source = "panic"
    else:
        source = "auto"

    is_technical = "error" in str(reason).lower() or "retry_limit" in str(reason)

    logger.info(
        "escalation_node_triggered",
        conversation_id=conversation_id,
        reason=reason,
        source=source,
        previous_mode=previous_mode,
    )

    # Perform the full escalation (Chatwoot + DB)
    result = await perform_escalation(
        conversation_id=str(conversation_id),
        user_id=str(user_id) if user_id else None,
        user_phone=str(user_phone),
        reason=str(reason),
        source=source,
        is_technical_error=is_technical,
    )

    # Use service message or fallback
    ai_response = result.get(
        "message",
        (
            "Te voy a conectar con un especialista que te puede "
            "ayudar mejor. Espera un momento..."
        ),
    )

    return Command(
        goto=NODE_SUMMARIZE,
        update={
            "ai_response": ai_response,
            "current_mode": "ESCALATION",
            "escalation_triggered": True,
            "escalation_reason": reason,
            "last_node": NODE_ESCALATION,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_conversation_graph() -> StateGraph:
    """
    Build the current conversation StateGraph.

    Returns a compiled StateGraph (not yet compiled — caller provides
    the checkpointer).

    Usage::

        graph_builder = build_conversation_graph()
        checkpointer = get_redis_checkpointer()
        graph = graph_builder.compile(checkpointer=checkpointer)
    """
    graph = StateGraph(ConversationState)

    # ── Add nodes ────────────────────────────────────────────────────────
    graph.add_node(NODE_PREPROCESS, preprocess_node)
    graph.add_node(NODE_ROUTER, router_node)
    # LLM-calling nodes get RetryPolicy for transient infrastructure errors (ADR-012).
    # Tier 1: LangGraph retries up to 3 times with exponential backoff.
    # Tier 2: FallbackHandler handles business errors inside each mode node.
    graph.add_node(NODE_CONSULTA, consulta_mode_node, retry_policy=_LLM_RETRY)
    graph.add_node(NODE_PRESUPUESTO, presupuesto_mode_node, retry_policy=_LLM_RETRY)

    # ── Expediente subgraph node ────────────────────────────────────────────
    # Expediente is mounted as a compiled LangGraph subgraph with 7 nodes
    # (entry_router + 6 sub-modes). The subgraph uses checkpointer=False
    # because the parent graph's Redis checkpointer already persists all
    # state; no interrupts are needed inside the subgraph.
    #
    # The boundary wrapper translates between ConversationState (parent) and
    # ExpedienteState (subgraph) using mapping functions.
    from agent.graph.expediente_subgraph import build_expediente_subgraph  # noqa: PLC0415
    from agent.modes.expediente_state import (  # noqa: PLC0415
        parent_to_expediente,
        expediente_to_parent_updates,
    )

    _exp_subgraph = build_expediente_subgraph().compile(checkpointer=False)

    async def _expediente_subgraph_node(
        state: ConversationState,
    ) -> Command:
        """
        Boundary wrapper for the expediente subgraph node.

        Translates between ConversationState (parent) and ExpedienteState
        (subgraph) using the two boundary mapping functions.
        Returns Command(goto=maybe_summarize) so the graph topology is
        consistent: all mode nodes use Command routing (WS1).
        """
        exp_input = parent_to_expediente(state)
        exp_output = await _exp_subgraph.ainvoke(exp_input)
        updates = expediente_to_parent_updates(exp_output)
        return Command(goto=NODE_SUMMARIZE, update=updates)

    graph.add_node(NODE_EXPEDIENTE, _expediente_subgraph_node, retry_policy=_LLM_RETRY)
    logger.info("expediente_subgraph_mounted")

    graph.add_node(NODE_ESCALATION, escalation_node)

    # ── Summarization node (WS2: refactor-memory-system) ─────────────────
    from agent.graph.summarize_node import maybe_summarize  # noqa: PLC0415

    graph.add_node(NODE_SUMMARIZE, maybe_summarize)

    # ── Entry edge ───────────────────────────────────────────────────────
    graph.add_edge(START, NODE_PREPROCESS)
    graph.add_edge(NODE_PREPROCESS, NODE_ROUTER)

    # ── Router → mode nodes (conditional) ────────────────────────────────
    graph.add_conditional_edges(
        NODE_ROUTER,
        route_to_mode,
        {
            NODE_CONSULTA: NODE_CONSULTA,
            NODE_PRESUPUESTO: NODE_PRESUPUESTO,
            NODE_EXPEDIENTE: NODE_EXPEDIENTE,
            NODE_ESCALATION: NODE_ESCALATION,
            END: END,  # CANCELAR resets to START → router provides ai_response → END
        },
    )

    # ── maybe_summarize → END ─────────────────────────────────────────────
    # Mode nodes route via Command(goto=NODE_SUMMARIZE) — no static edges needed.
    # maybe_summarize checks if the conversation exceeds the message threshold.
    # If so, it builds a deterministic summary and trims old messages via RemoveMessage.
    graph.add_edge(NODE_SUMMARIZE, END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph factory
# ---------------------------------------------------------------------------


async def create_compiled_graph(
    checkpointer: Any | None = None,
    store: Any | None = None,
) -> Any:
    """
    Create and return a compiled conversation graph.

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence.
                      If None, uses in-memory (for testing).
        store: Optional LangGraph Store for cross-thread memory (WS3).
               If None, Store-dependent nodes gracefully skip persistence.

    Returns:
        Compiled StateGraph ready for ainvoke().
    """
    graph_builder = build_conversation_graph()

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        compile_kwargs["interrupt_before"] = None
        compile_kwargs["interrupt_after"] = None
    if store is not None:
        compile_kwargs["store"] = store

    compiled = graph_builder.compile(**compile_kwargs)

    logger.info(
        "conversation_graph_compiled",
        has_checkpointer=checkpointer is not None,
        recursion_limit=_RECURSION_LIMIT,
    )
    return compiled
