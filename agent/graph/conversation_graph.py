"""
MSI-a - Conversation Graph.

The main LangGraph StateGraph that wires together:
- Entry node (message preprocessing)
- Router node (intent classification + digression detection)
- Mode nodes (one per conversation mode)
- Escalation node

Architecture (POST FUSION):
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
             │      ┌─────▼──────┐       │
             │      │eval_gateway│       │
             │      └─────┬──────┘       │
             │            │              │
             └────────────┼──────────────┘
                          │
                    ┌─────▼──────┐
                    │  escalation │ ──── END
                    └────────────┘

Changes from v2.0:
- Removed VIABILIDAD_MODE node
- PRESUPUESTO_MODE is now main entry point (handles ~90% traffic)
- Direct routing from START → PRESUPUESTO

Each mode node returns state updates, including optionally a new
``current_mode`` which causes the next invocation to route differently.

Persistence: Uses Redis checkpointer (recycled from v1).
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

import structlog
from langgraph.graph import StateGraph, START, END

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
    get_preserve_keys,
    validate_transition,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Node names (constants to avoid typos)
# ---------------------------------------------------------------------------

NODE_PREPROCESS = "preprocess"
NODE_ROUTER = "router"
NODE_CONSULTA = "consulta_mode"
NODE_PRESUPUESTO = "presupuesto_mode"
NODE_EVAL_GATEWAY = "evaluacion_gateway"
NODE_EXPEDIENTE = "expediente_mode"
NODE_ESCALATION = "escalation"

# All mode node names mapped from ConversationMode values
MODE_TO_NODE: dict[str, str] = {
    "CONSULTA_MODE": NODE_CONSULTA,
    "PRESUPUESTO_MODE": NODE_PRESUPUESTO,
    "EVALUACION_GATEWAY": NODE_EVAL_GATEWAY,
    "EXPEDIENTE_MODE": NODE_EXPEDIENTE,
    "ESCALATION": NODE_ESCALATION,
}


# ---------------------------------------------------------------------------
# Preprocess node
# ---------------------------------------------------------------------------

async def preprocess_node(state: ConversationState) -> dict[str, Any]:
    """
    Entry node: prepare the incoming message for processing.

    Responsibilities:
    - Extract and normalise user message
    - Increment message counter
    - Update activity timestamp
    - Handle agent_disabled flag (panic button)

    This is deliberately lightweight — routing logic lives in router_node.
    """
    now = datetime.now(UTC).isoformat()
    user_message = state.get("user_message", "")
    is_chained = state.get("_is_chained_turn", False)

    logger.info(
        "preprocess_incoming",
        conversation_id=state.get("conversation_id"),
        mode=state.get("current_mode", "START"),
        message_length=len(user_message) if user_message else 0,
        is_chained_turn=is_chained,
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

    # Chained turn: skip counter increments (synthetic continuation, not a real user message)
    if is_chained:
        return {
            "last_node": NODE_PREPROCESS,
            "updated_at": now,
            "last_activity_at": now,
            # Reset transient fields
            "pending_images": None,
            "tarifa_actual": None,
            "incoming_attachments": [],
            "ai_response": None,
            "_chain_next_mode": None,
        }

    total = state.get("total_message_count", 0) + 1
    mode_msg_count = state.get("mode_message_count", 0) + 1

    return {
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
        "_chain_next_mode": None,  # Reset chain signal
    }


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
                preserve = digression.context_to_preserve or []
                updates = transition_mode(state, target, preserve_keys=preserve)
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
            intent_result = await intent_router.classify(
                message=user_message,
                current_mode=current_mode,
            )
            if (
                intent_result.intent == UserIntent.PRESUPUESTO_DIRECTO
                and intent_result.confidence >= 0.75
            ):
                preserve = get_preserve_keys("CONSULTA_MODE", "PRESUPUESTO_MODE")
                updates = transition_mode(
                    state, "PRESUPUESTO_MODE", preserve_keys=preserve,
                )
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
    intent_result: IntentResult = await intent_router.classify(
        message=user_message,
        current_mode=current_mode,
    )

    target_mode = _resolve_target_mode(intent_result, state)

    logger.info(
        "intent_routed",
        intent=intent_result.intent.value,
        confidence=intent_result.confidence,
        target_mode=target_mode,
    )

    # Build transition
    preserve = get_preserve_keys("START", target_mode)
    updates = transition_mode(state, target_mode, preserve_keys=preserve)
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

    # Context-dependent intents
    if intent_result.intent == UserIntent.CONFIRMACION:
        prev = state.get("previous_mode")
        if prev == "EVALUACION_GATEWAY":
            return "EXPEDIENTE_MODE"
        if prev == "PRESUPUESTO_MODE":
            return "EVALUACION_GATEWAY"
        # Default: treat as general query
        return "CONSULTA_MODE"

    if intent_result.intent == UserIntent.RECHAZO:
        prev = state.get("previous_mode")
        if prev == "EVALUACION_GATEWAY":
            return "PRESUPUESTO_MODE"
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

    # Terminal modes
    if current_mode == "COMPLETED":
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


async def consulta_mode_node(state: ConversationState) -> dict[str, Any]:
    """CONSULTA_MODE node — delegates to ConsultaModeNode.process()."""
    node = _get_consulta_node()
    return await node.process(state)


# PRESUPUESTO_MODE (includes former VIABILIDAD_MODE)
_presupuesto_node_instance: Any = None


def _get_presupuesto_node() -> Any:
    """Lazy-load PresupuestoModeNode to avoid circular imports."""
    global _presupuesto_node_instance
    if _presupuesto_node_instance is None:
        from agent.modes.presupuesto_mode import PresupuestoModeNode
        _presupuesto_node_instance = PresupuestoModeNode()
    return _presupuesto_node_instance


async def presupuesto_mode_node(state: ConversationState) -> dict[str, Any]:
    """PRESUPUESTO_MODE node — delegates to PresupuestoModeNode.process()."""
    node = _get_presupuesto_node()
    return await node.process(state)


# EVALUACION_GATEWAY
_evaluacion_gateway_instance: Any = None


def _get_evaluacion_gateway_node() -> Any:
    """Lazy-load EvaluacionGatewayNode to avoid circular imports."""
    global _evaluacion_gateway_instance
    if _evaluacion_gateway_instance is None:
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode
        _evaluacion_gateway_instance = EvaluacionGatewayNode()
    return _evaluacion_gateway_instance


async def evaluacion_gateway_node(state: ConversationState) -> dict[str, Any]:
    """EVALUACION_GATEWAY node — delegates to EvaluacionGatewayNode.process()."""
    node = _get_evaluacion_gateway_node()
    return await node.process(state)


# EXPEDIENTE_MODE
_expediente_node_instance: Any = None


def _get_expediente_node() -> Any:
    """Lazy-load ExpedienteModeNode to avoid circular imports."""
    global _expediente_node_instance
    if _expediente_node_instance is None:
        from agent.modes.expediente_mode import ExpedienteModeNode
        _expediente_node_instance = ExpedienteModeNode()
    return _expediente_node_instance


async def expediente_mode_node(state: ConversationState) -> dict[str, Any]:
    """EXPEDIENTE_MODE node — delegates to ExpedienteModeNode.process()."""
    node = _get_expediente_node()
    return await node.process(state)


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
    ai_response = result.get("message", (
        "Te voy a conectar con un especialista que te puede "
        "ayudar mejor. Espera un momento..."
    ))

    return {
        "ai_response": ai_response,
        "current_mode": "ESCALATION",
        "escalation_triggered": True,
        "escalation_reason": reason,
        "last_node": NODE_ESCALATION,
        "updated_at": datetime.now(UTC).isoformat(),
    }


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
    graph.add_node(NODE_CONSULTA, consulta_mode_node)
    graph.add_node(NODE_PRESUPUESTO, presupuesto_mode_node)
    graph.add_node(NODE_EVAL_GATEWAY, evaluacion_gateway_node)
    graph.add_node(NODE_EXPEDIENTE, expediente_mode_node)
    graph.add_node(NODE_ESCALATION, escalation_node)

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
            NODE_EVAL_GATEWAY: NODE_EVAL_GATEWAY,
            NODE_EXPEDIENTE: NODE_EXPEDIENTE,
            NODE_ESCALATION: NODE_ESCALATION,
        },
    )

    # ── Mode nodes → END ─────────────────────────────────────────────────
    # Each mode node is a terminal node for this invocation.
    # The next user message will trigger a new invocation starting from
    # preprocess → router, which reads the updated current_mode.
    graph.add_edge(NODE_CONSULTA, END)
    graph.add_edge(NODE_PRESUPUESTO, END)
    graph.add_edge(NODE_EVAL_GATEWAY, END)
    graph.add_edge(NODE_EXPEDIENTE, END)
    graph.add_edge(NODE_ESCALATION, END)

    return graph


# ---------------------------------------------------------------------------
# Compiled graph factory
# ---------------------------------------------------------------------------

async def create_compiled_graph(
    checkpointer: Any | None = None,
) -> Any:
    """
    Create and return a compiled conversation graph.

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence.
                      If None, uses in-memory (for testing).

    Returns:
        Compiled StateGraph ready for ainvoke().
    """
    graph_builder = build_conversation_graph()

    if checkpointer is not None:
        compiled = graph_builder.compile(checkpointer=checkpointer)
    else:
        compiled = graph_builder.compile()

    logger.info("conversation_graph_compiled", has_checkpointer=checkpointer is not None)
    return compiled
