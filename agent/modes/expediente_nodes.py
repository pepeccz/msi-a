"""
Expediente subgraph nodes.

Contains:
- ``entry_router``: Reads ``expediente_sub_mode`` from state and dispatches to
  the correct sub-mode node via ``Command(goto=target)``.

- ``_build_expediente_node``: DRY factory that builds a wired expediente sub-mode
  node from (mode_name, sub_mode, get_tools_fn).  Each returned node:
  1. Converts ExpedienteState → ToolLoopState
  2. Builds ModeLoopConfig with expediente_post_tool_hook
  3. Invokes build_mode_tool_loop subgraph
  4. Merges pending_state_updates back to ExpedienteState update
  5. Returns Command(goto=END, update=merged)

- Six sub-mode nodes built by the factory:
  collect_element_data_node, collect_base_docs_node, collect_personal_node,
  collect_vehicle_node, collect_workshop_node, review_summary_node.

Design reference:
- AD-1 (Subgraph Wiring Pattern) — 7-node subgraph, entry_router + 6 sub-modes
- AD-4 (Coordinator Logic Distribution) — entry_router absorbs initialization/guards
- ``agent/modes/submodos/_shared.py`` for sub-mode constants and tool registry
"""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from agent.modes.submodos._shared import (
    _get_element_data_tools,
    _get_base_docs_tools,
    _get_personal_tools,
    _get_vehicle_tools,
    _get_workshop_tools,
    _get_review_tools,
)
from agent.utils.expediente_types import CollectionStep
from agent.modes.expediente_state import ExpedienteState
from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
from agent.modes.post_tool_hooks import expediente_post_tool_hook
from agent.prompts.loader import assemble_system_prompt
from agent.services.expediente_init import initialize_expediente
from agent.state.helpers import format_messages_for_llm
from agent.fallback.transient_errors import is_transient_error
from agent.fallback.fallback_handler import get_fallback_handler, RetryErrorType
from agent.state.conversation_state import create_empty_retry_state
from database.connection import get_async_session
from database.models import Case
from agent.tools.case_tools import obtener_estado_expediente

# ---------------------------------------------------------------------------
# Intent detection helpers (WS6 flexible routing)
# ---------------------------------------------------------------------------

_VEHICLE_KEYWORDS: frozenset[str] = frozenset(
    {"matrícula", "matricula", "bastidor", "marca", "modelo", "vehículo", "vehiculo", "coche"}
)
_WORKSHOP_KEYWORDS: frozenset[str] = frozenset({"taller", "rae", "instalador"})
_PERSONAL_KEYWORDS: frozenset[str] = frozenset(
    {"nombre", "apellido", "dni", "cif", "nif", "email", "correo", "teléfono", "telefono"}
)


def _detect_collection_intent(message: str) -> str | None:
    """
    Detect which collection section the user is trying to provide data for.

    Scans lowercased message for keyword hits and returns the intent string
    with the most matches.  Returns None if no keywords match.

    Returns one of: "collect_vehicle", "collect_workshop", "collect_personal", None.
    No LLM call — pure keyword counting, case-insensitive.
    """
    msg = message.lower()
    vehicle_hits = sum(1 for kw in _VEHICLE_KEYWORDS if kw in msg)
    workshop_hits = sum(1 for kw in _WORKSHOP_KEYWORDS if kw in msg)
    personal_hits = sum(1 for kw in _PERSONAL_KEYWORDS if kw in msg)

    best = max(vehicle_hits, workshop_hits, personal_hits)
    if best == 0:
        return None

    if vehicle_hits == best:
        return "collect_vehicle"
    if workshop_hits == best:
        return "collect_workshop"
    return "collect_personal"

# GraphRecursionError is in langgraph.errors — import with fallback for environments
# where langgraph version differs.
try:
    from langgraph.errors import GraphRecursionError
except ImportError:  # pragma: no cover — older langgraph versions
    GraphRecursionError = RecursionError  # type: ignore[misc, assignment]

logger = structlog.get_logger(__name__)

# Case statuses that indicate the expediente is complete — entry_router
# checks against DB and exits EXPEDIENTE_MODE if the case is in one of these.
_TERMINAL_CASE_STATUSES: frozenset[str] = frozenset(
    {"pending_review", "resolved", "cancelled", "abandoned"}
)

# Max tool call iterations per turn for all expediente nodes
MAX_TOOL_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Routing map: sub_mode string → subgraph node name
# ---------------------------------------------------------------------------

_SUB_MODE_TO_NODE: dict[str, str] = {
    CollectionStep.COLLECT_ELEMENT_DATA.value: "collect_element_data_node",
    CollectionStep.COLLECT_BASE_DOCS.value: "collect_base_docs_node",
    CollectionStep.COLLECT_PERSONAL.value: "collect_personal_node",
    CollectionStep.COLLECT_VEHICLE.value: "collect_vehicle_node",
    CollectionStep.COLLECT_WORKSHOP.value: "collect_workshop_node",
    CollectionStep.REVIEW_SUMMARY.value: "review_summary_node",
}

# Default node when sub_mode is unrecognized or absent
_DEFAULT_NODE = "collect_element_data_node"


# ---------------------------------------------------------------------------
# Overview emission helper — pure function, testable without LangGraph infra
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# entry_router — reads expediente_sub_mode and dispatches via Command
# ---------------------------------------------------------------------------


async def entry_router(
    state: ExpedienteState,
) -> Command[
    Literal[
        "collect_element_data_node",
        "collect_base_docs_node",
        "collect_personal_node",
        "collect_vehicle_node",
        "collect_workshop_node",
        "review_summary_node",
        "join_collections_node",
    ]
]:
    """
    Entry node for the expediente subgraph.

    Reads ``expediente_sub_mode`` and routes to the corresponding sub-mode node
    via ``Command(goto=target_node)``.  Falls back to ``collect_element_data_node``
    for any unrecognized or missing sub-mode value.

    When ``case_id`` is absent, calls ``initialize_expediente()`` to create or
    recover a Case record in PostgreSQL before routing.  The initialization
    result is merged into state via ``Command(update=init_updates, goto=...)``.

    If initialization fails (returns empty dict with no ``case_id``), the router
    logs the error and escalates by routing to ``collect_element_data_node`` so
    the sub-mode node can handle the degraded state gracefully.
    """
    case_id = state.get("case_id")  # type: ignore[attr-defined]
    conversation_id = state.get("conversation_id", "unknown")  # type: ignore[attr-defined]

    if not case_id:
        logger.info(
            "entry_router_initializing_expediente",
            conversation_id=conversation_id,
        )
        try:
            init_updates = await initialize_expediente(dict(state))  # type: ignore[arg-type]
        except Exception as exc:
            logger.error(
                "entry_router_init_failed",
                conversation_id=conversation_id,
                error=str(exc),
            )
            init_updates = {}

        if not init_updates.get("case_id"):
            logger.error(
                "entry_router_init_returned_no_case_id",
                conversation_id=conversation_id,
                current_mode=state.get("expediente_sub_mode"),  # type: ignore[attr-defined]
            )
            # Route to default node — sub-mode node will handle missing case_id
            return Command(goto=_DEFAULT_NODE, update=init_updates or None)

        # Determine target from the sub_mode resolved by initialization
        sub_mode: str = init_updates.get("expediente_sub_mode") or state.get("expediente_sub_mode") or ""  # type: ignore[attr-defined]
        target_node = _SUB_MODE_TO_NODE.get(sub_mode, _DEFAULT_NODE)

        # Prevent the presupuesto-era user_message (e.g. "abreme el expediente")
        # from leaking into the first sub-mode turn.  Without this, the LLM
        # misinterprets the message as a request to open an expediente and
        # calls obtener_estado_expediente instead of starting collection.
        # Same pattern as the photo_completion_guard (line ~244).
        init_updates["user_message"] = (
            "[Sistema: expediente creado correctamente. "
            "Iniciar recolección de datos del primer elemento.]"
        )

        logger.debug(
            "entry_router_dispatching_after_init",
            sub_mode=sub_mode,
            target_node=target_node,
            case_id=init_updates.get("case_id"),
            conversation_id=conversation_id,
        )

        return Command(update=init_updates, goto=target_node)

    # ── DB safety net: check if case is in a terminal status ───────────
    # If the case was finalized/cancelled externally (admin panel, API) but
    # the checkpoint still has current_mode=EXPEDIENTE_MODE, detect it here
    # and exit the subgraph.  Lightweight PK lookup, no full case load.
    try:
        from sqlalchemy import select as sa_select

        async with get_async_session() as session:
            result = await session.scalars(
                sa_select(Case).where(Case.id == case_id).limit(1)
            )
            db_case = result.first()
            if db_case and db_case.status in _TERMINAL_CASE_STATUSES:
                logger.info(
                    "entry_router_case_terminal",
                    case_id=case_id,
                    db_status=db_case.status,
                    conversation_id=conversation_id,
                )
                _STATUS_MESSAGES = {
                    "pending_review": (
                        "Tu expediente ya fue enviado para revisión. "
                        "Un agente de MSI Automotive se pondrá en contacto contigo. "
                        "¿Puedo ayudarte con algo más?"
                    ),
                    "resolved": (
                        "Tu expediente ya fue completado. "
                        "¿Puedo ayudarte con algo más?"
                    ),
                    "cancelled": (
                        "Tu expediente anterior fue cancelado. "
                        "¿Quieres empezar uno nuevo o tienes alguna consulta?"
                    ),
                    "abandoned": (
                        "Tu expediente anterior fue abandonado. "
                        "¿Quieres empezar uno nuevo o tienes alguna consulta?"
                    ),
                }
                return Command(
                    goto=END,
                    update={
                        "_transition_to": "PRE_EXPEDIENTE_MODE",
                        "ai_response": _STATUS_MESSAGES.get(
                            db_case.status,
                            "Tu expediente ya no está activo. ¿Puedo ayudarte con algo más?",
                        ),
                    },
                )
    except Exception as exc:
        logger.warning(
            "entry_router_db_guard_failed",
            case_id=case_id,
            error=str(exc),
            error_type=type(exc).__name__,
            conversation_id=conversation_id,
        )
        # Fallback: continue with checkpoint-based routing

    # case_id already present — pure routing, no initialization needed
    sub_mode = state.get("expediente_sub_mode") or ""  # type: ignore[attr-defined]
    target_node = _SUB_MODE_TO_NODE.get(sub_mode, _DEFAULT_NODE)

    # T-5: Phase reconciliation (lightweight — only checks current element).
    # If element_phase is "photos" but the DB-backed status shows the element
    # is already in "pending_data", the photos step was already completed.
    # Correct the phase to "data" so we don't ask for photos again.
    if sub_mode == CollectionStep.COLLECT_ELEMENT_DATA.value and state.get("element_phase") == "photos":  # type: ignore[attr-defined]
        current_code: str | None = state.get("current_element_code")  # type: ignore[attr-defined]
        if current_code:
            element_status = (state.get("element_data_status") or {}).get(current_code)  # type: ignore[attr-defined]
            if element_status == "pending_data":
                logger.info(
                    "entry_router_phase_reconciliation",
                    conversation_id=conversation_id,
                    element_code=current_code,
                    old_phase="photos",
                    new_phase="data",
                )
                return Command(
                    update={"element_phase": "data"},
                    goto=target_node,
                )

    # T-4: Photo-completion guard (pre-LLM, deterministic).
    # Only fires when: case_id exists + sub_mode is collect_element_data +
    # element_phase is "photos".  The guard checks user intent internally and
    # populates `guard_updates` in-place when it fires.
    if sub_mode == CollectionStep.COLLECT_ELEMENT_DATA.value and state.get("element_phase") == "photos":  # type: ignore[attr-defined]
        from agent.services.expediente_guards import guard_photo_completion

        guard_updates: dict[str, Any] = {}
        guard_fired = await guard_photo_completion(dict(state), guard_updates)  # type: ignore[arg-type]
        if guard_fired and guard_updates:
            # Guard may have transitioned sub_mode (e.g. element with no
            # required fields completes all elements → collect_base_docs).
            # Recalculate target_node so we route to the correct node.
            guard_sub_mode = guard_updates.get("expediente_sub_mode", sub_mode)
            guard_target = _SUB_MODE_TO_NODE.get(guard_sub_mode, target_node)

            # Prevent stale user_message from leaking into the destination
            # sub-mode.  When the guard transitions to a DIFFERENT sub-mode
            # (e.g. collect_element_data → collect_base_docs), the original
            # message (typically "listo") must NOT reach the new node — it
            # would be misinterpreted as a confirmation for the new step.
            if guard_sub_mode != sub_mode:
                guard_updates["user_message"] = (
                    "[Sistema: transición automática desde recolección de "
                    "elementos. Todos los elementos completados. "
                    "Iniciar recolección de documentación base.]"
                )

            logger.debug(
                "entry_router_photo_guard_fired",
                conversation_id=conversation_id,
                original_target=target_node,
                guard_target=guard_target,
                guard_sub_mode=guard_sub_mode,
            )
            return Command(update=guard_updates, goto=guard_target)

    # ── WS6: Flexible routing for personal/vehicle/workshop ──────────────
    # After element_data + base_docs are complete, the three collection
    # sub-modes have NO data dependencies on each other.  Allow any order
    # by reading completion flags and detecting intent from the user message.
    # The sequential routing for COLLECT_ELEMENT_DATA and COLLECT_BASE_DOCS
    # above is UNCHANGED — this block only activates for the remaining steps.
    # REVIEW_SUMMARY is handled by direct routing further up (_SUB_MODE_TO_NODE).
    _flexible_sub_modes = {CollectionStep.COLLECT_PERSONAL.value, CollectionStep.COLLECT_VEHICLE.value, CollectionStep.COLLECT_WORKSHOP.value}
    if sub_mode in _flexible_sub_modes or (
        sub_mode not in _SUB_MODE_TO_NODE and sub_mode not in {CollectionStep.COLLECT_ELEMENT_DATA.value, CollectionStep.COLLECT_BASE_DOCS.value}
    ):
        # Only apply flexible routing when past the sequential phase
        personal_done = state.get("personal_collected", False)  # type: ignore[attr-defined]
        vehicle_done = state.get("vehicle_collected", False)  # type: ignore[attr-defined]
        workshop_done = state.get("workshop_collected", False)  # type: ignore[attr-defined]

        # Workshop skip: particular clients with taller_propio=False don't need workshop
        taller_propio = state.get("taller_propio")  # type: ignore[attr-defined]
        if not workshop_done and taller_propio is False:
            workshop_done = True
            logger.info(
                "entry_router_workshop_skipped",
                conversation_id=conversation_id,
                reason="taller_propio=False",
            )

        if personal_done and vehicle_done and workshop_done:
            logger.debug(
                "entry_router_all_collections_done",
                conversation_id=conversation_id,
            )
            return Command(goto="join_collections_node")

        # Intent detection from user message (keyword-based, no LLM)
        intent = _detect_collection_intent(state.get("user_message", ""))  # type: ignore[attr-defined]
        if intent:
            # Only route to intent target if that section is not yet collected
            intent_collected_flag = f"{intent.replace('collect_', '')}_collected"
            if not state.get(intent_collected_flag, False):  # type: ignore[attr-defined]
                intent_target = _SUB_MODE_TO_NODE.get(intent, "collect_personal_node")
                logger.debug(
                    "entry_router_intent_routing",
                    intent=intent,
                    target=intent_target,
                    conversation_id=conversation_id,
                )
                return Command(
                    goto=intent_target,
                    update={"expediente_sub_mode": intent},
                )

        # Default order: personal → vehicle → workshop
        if not personal_done:
            return Command(
                goto="collect_personal_node",
                update={"expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value},
            )
        elif not vehicle_done:
            return Command(
                goto="collect_vehicle_node",
                update={"expediente_sub_mode": CollectionStep.COLLECT_VEHICLE.value},
            )
        else:
            return Command(
                goto="collect_workshop_node",
                update={"expediente_sub_mode": CollectionStep.COLLECT_WORKSHOP.value},
            )

    logger.debug(
        "entry_router_dispatching",
        sub_mode=sub_mode,
        target_node=target_node,
        case_id=case_id,
        conversation_id=conversation_id,
    )

    return Command(goto=target_node)


# ---------------------------------------------------------------------------
# _trio_complete — pure helper, no side-effects
# ---------------------------------------------------------------------------


def _trio_complete(update: dict[str, Any], state: dict[str, Any]) -> bool:
    """
    Return True iff all three collection sections (personal, vehicle, workshop)
    are done after merging *update* on top of *state*.

    Workshop is treated as done when:
    - ``update["workshop_collected"]`` is True, OR
    - ``state["workshop_collected"]`` is True (not overridden), OR
    - ``taller_propio`` is False in either update or state (workshop skipped).

    Args:
        update: The merged update dict produced after the tool loop completes.
                Keys in update take precedence over the same keys in state.
        state:  Current ExpedienteState-like dict (checkpoint values).

    Returns:
        True when the full trio is satisfied, False otherwise.
    """
    # Resolve each flag: update wins over state
    personal_done: bool = bool(
        update.get("personal_collected", state.get("personal_collected", False))
    )
    vehicle_done: bool = bool(
        update.get("vehicle_collected", state.get("vehicle_collected", False))
    )

    # Workshop skip: taller_propio=False makes workshop implicitly done
    taller_propio = update.get("taller_propio", state.get("taller_propio"))
    if taller_propio is False:
        workshop_done = True
    else:
        workshop_done = bool(
            update.get("workshop_collected", state.get("workshop_collected", False))
        )

    return personal_done and vehicle_done and workshop_done


# ---------------------------------------------------------------------------
# join_collections_node — WS6 pure routing node
# ---------------------------------------------------------------------------


async def join_collections_node(
    state: ExpedienteState,
    config: Any = None,
) -> Command[Literal["review_summary_node"]]:
    """
    Pure routing node — no LLM call, no user-facing message.

    Reached when all 3 collection flags (personal, vehicle, workshop) are True.
    Routes to review_summary_node so the agent can present a final summary.

    This node exists as a named waypoint so that entry_router can target it
    explicitly via Command(goto="join_collections_node"), making the routing
    intent explicit in the subgraph DAG.
    """
    conversation_id = state.get("conversation_id", "unknown")  # type: ignore[attr-defined]
    logger.debug(
        "join_collections_node_routing",
        conversation_id=conversation_id,
    )
    return Command(
        goto="review_summary_node",
        update={"expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value},
    )


# ---------------------------------------------------------------------------
# Helpers: ExpedienteState → ToolLoopState mapping
# ---------------------------------------------------------------------------


def _build_mode_context_from_expediente_state(state: ExpedienteState) -> dict[str, Any]:
    """
    Convert flat ExpedienteState to nested mode_context dict for the tool loop.

    Copies all ExpedienteState keys that are conceptually "mode_context" keys
    (case identity, element collection, sub-mode data, transitions, coordinator
    signals, FSM compat, inherited PRESUPUESTO fields) into a flat dict.

    Top-level-only keys (conversation_id, user_message, messages, ai_response,
    pending_images, incoming_attachments, user_id, user_phone, user_name, client_type)
    are intentionally excluded — they are passed separately.

    Args:
        state: Current ExpedienteState dict.

    Returns:
        mode_context dict suitable for ``ToolLoopState["_mode_context"]``.
    """
    # All keys from ExpedienteState except the parent-top-level-only ones
    _SKIP_KEYS = frozenset(
        {
            "conversation_id",
            "user_id",
            "user_phone",
            "user_name",
            "client_type",
            "user_message",
            "incoming_attachments",
            "messages",
            "ai_response",
            "pending_images",
        }
    )
    return {k: v for k, v in state.items() if k not in _SKIP_KEYS}


def _build_client_context(state: ExpedienteState) -> str:
    """
    Build client context string for the system prompt.

    Mirrors ``PresupuestoModeNode._build_client_context`` but reads from
    ``ExpedienteState`` (flat dict) rather than ``ConversationState``.
    """
    parts: list[str] = []

    client_type = state.get("client_type") or "particular"  # type: ignore[attr-defined]
    type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
    parts.append(f"Cliente: **{type_display}**")
    parts.append(f'Usa tipo_cliente: "{client_type}" en herramientas.')

    user_name = state.get("user_name")  # type: ignore[attr-defined]
    if user_name:
        parts.append(f"Nombre: {user_name}")

    return "\n".join(parts)


def _build_full_state_for_tools(
    state: ExpedienteState,
    mode_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a ConversationState-shaped dict for passing to tools via RunnableConfig.

    Tools call ``get_tool_state(config)`` which reads from
    ``config["configurable"]["state"]``.  They expect nested ``mode_context``.

    Args:
        state:        Current ExpedienteState dict.
        mode_context: Already-built mode_context for this turn.

    Returns:
        Full state dict with mode_context properly nested.
    """
    full_state: dict[str, Any] = dict(state)  # type: ignore[arg-type]
    full_state["mode_context"] = mode_context
    # Also expose top-level aliases for tools that read conversation_id directly
    full_state.setdefault("conversation_id", state.get("conversation_id", "unknown"))  # type: ignore[attr-defined]
    return full_state


def _merge_loop_result_to_expediente(
    state: ExpedienteState,
    loop_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge tool loop output back to ExpedienteState-compatible update dict.

    Processes ``pending_state_updates`` from the loop result — which may contain
    a nested ``mode_context`` sub-dict — and flattens it to the top level so that
    LangGraph can apply it directly to the ExpedienteState checkpoint.

    Also surfaces ``ai_response``, ``exit_reason``, and ``pending_images``.

    Args:
        state:       Original ExpedienteState (for defaults).
        loop_result: Output dict from ``subgraph.ainvoke()``.

    Returns:
        Flat dict suitable as ``Command(goto=END, update=...)`` payload.
    """
    ai_response: str = loop_result.get("ai_response", "")
    exit_reason: str = loop_result.get("exit_reason", "response")
    pending_updates: dict[str, Any] = dict(loop_result.get("pending_state_updates") or {})

    # Merge nested mode_context from pending_state_updates into top-level update.
    # This is identical to how PresupuestoModeNode handles the loop result.
    nested_mc: dict[str, Any] | None = pending_updates.pop("mode_context", None)
    merged: dict[str, Any] = {"ai_response": ai_response, "exit_reason": exit_reason}

    # Apply flat pending_state_updates (non-mode_context keys)
    merged.update(pending_updates)

    # Flatten nested mode_context keys to top level for ExpedienteState
    if isinstance(nested_mc, dict):
        merged.update(nested_mc)

    # Bubble up pending images if any
    pending_images = pending_updates.get("_pending_images") or merged.pop("_pending_images", None)
    if pending_images:
        merged["pending_images"] = pending_images

    return merged


# ---------------------------------------------------------------------------
# _auto_emit_review_summary — deterministic review dispatch within the same turn
# ---------------------------------------------------------------------------


async def _auto_emit_review_summary(
    *,
    update: dict[str, Any],
    state: dict[str, Any],
    mode_name: str,
    conversation_id: str,
) -> dict[str, Any]:
    """
    Auto-invoke ``review_summary_node`` within the current turn and merge
    its output into *update*.

    Called when the last of the three collection sections (personal / vehicle /
    workshop-or-skipped) is completed in the same turn, so that the user
    receives the actual summary as ``ai_response`` — not a promise from the LLM.

    Spec: escenario 9, regla dura 11.
    Anti-pattern: escenario 9.bis.

    Args:
        update:          Merged update dict after the collection tool loop.
                         Modified in-place and returned.
        state:           Current ExpedienteState as a plain dict (checkpoint values).
        mode_name:       Mode identifier for structured logging.
        conversation_id: Conversation identifier for structured logging.

    Returns:
        *update* enriched with the review_summary ai_response (and any other
        keys from the review Command.update).  On error, returns *update* unchanged
        (fail-open — next turn's entry_router will route to review).
    """
    logger.info(
        "expediente_node_auto_emit_review_summary",
        mode=mode_name,
        conversation_id=conversation_id,
        reason="trio_complete_in_same_turn",
    )
    # Build a merged state snapshot for review_summary_node.
    # It must see the freshly set completion flags and the correct sub_mode
    # so that its tool loop can compute the DB-backed summary.
    review_state: dict[str, Any] = {
        **state,
        **{k: v for k, v in update.items() if k != "ai_response"},
        "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
    }
    try:
        review_cmd = await review_summary_node(review_state)
        if review_cmd is not None and getattr(review_cmd, "update", None):
            # Merge review output into update; review wins on ai_response
            update = dict(update)
            update.update(review_cmd.update)
            logger.debug(
                "expediente_node_auto_emit_review_summary_done",
                mode=mode_name,
                conversation_id=conversation_id,
            )
    except Exception as review_exc:
        logger.error(
            "expediente_node_auto_emit_review_summary_failed",
            mode=mode_name,
            error=str(review_exc),
            conversation_id=conversation_id,
        )
        # Fail-open: leave update as-is; next turn will route to review

    return update


# ---------------------------------------------------------------------------
# Sub-mode node factory
# ---------------------------------------------------------------------------


def _build_expediente_node(
    *,
    mode_name: str,
    sub_mode: str,
    get_tools_fn: Callable[[], list],
    completion_flag: str | None = None,
    own_sub_mode: str | None = None,
) -> Callable[[ExpedienteState, RunnableConfig], Any]:  # noqa: FA100
    """
    Factory for wired expediente sub-mode nodes.

    Returns an async function suitable as a LangGraph node that:
    1. Converts ExpedienteState → ModeLoopConfig + ToolLoopState
    2. Invokes build_mode_tool_loop subgraph
    3. Merges pending_state_updates back to ExpedienteState update
    4. Optionally sets a completion flag when the sub-mode has transitioned away
    5. Returns Command(goto=END, update=merged)

    The returned node catches ``GraphRecursionError`` (max_iterations exceeded) and
    any unexpected exceptions, returning a safe Command in both cases.

    Args:
        mode_name:       Identifier for structured logging (e.g. "EXPEDIENTE_COLLECT_PERSONAL").
        sub_mode:        CollectionStep value passed directly to assemble_system_prompt
                         (e.g. ``CollectionStep.COLLECT_PERSONAL.value`` → ``"collect_personal"``).
                         No prefix stripping is performed — the value is used as-is.
        get_tools_fn:    Zero-argument function returning the tool list for this sub-mode.
        completion_flag: Optional ExpedienteState key to set to True when this node's
                         sub-mode is complete.  Set when the merged update's
                         ``expediente_sub_mode`` differs from ``own_sub_mode``.
                         Example: ``"personal_collected"`` for the personal node.
        own_sub_mode:    The sub-mode string that this node owns (e.g. "collect_personal").
                         Used to detect when the tool loop has transitioned away.

    Returns:
        Async node function ``_node(state, config) -> Command``.
    """

    async def _node(
        state: ExpedienteState,
        config: RunnableConfig | None = None,
    ) -> Command[Literal["__end__"]]:
        conversation_id = str(state.get("conversation_id", "unknown"))  # type: ignore[attr-defined]
        user_message = str(state.get("user_message") or "")  # type: ignore[attr-defined]

        # Build mode_context from ExpedienteState for the tool loop
        mode_context = _build_mode_context_from_expediente_state(state)

        # Force the correct sub_mode — the node is authoritative for its own
        # sub_mode, regardless of what the checkpoint or pending_state_updates
        # may contain (fixes stale "idle" propagation after tool errors).
        if own_sub_mode:
            mode_context["expediente_sub_mode"] = own_sub_mode

        # Build client context for the prompt
        client_context = _build_client_context(state)

        loop_config = ModeLoopConfig(
            mode_name=mode_name,
            get_tools=lambda ctx: get_tools_fn(),
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="EXPEDIENTE_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                sub_mode=sub_mode,
                client_context=client_context,
            ),
            post_tool_hook=expediente_post_tool_hook,
            max_iterations=MAX_TOOL_ITERATIONS,
        )

        loop_result_obj = build_mode_tool_loop(loop_config)

        # Format parent conversation history so the LLM has context from
        # prior modes (e.g. the presupuesto flow that led here).
        # The subgraph is compiled with checkpointer=False, so messages
        # are set fresh by parent_to_expediente each invocation — no
        # accumulation risk.
        parent_messages = state.get("messages", [])  # type: ignore[attr-defined]
        llm_history = list(format_messages_for_llm(
            parent_messages,
            conversation_summary=state.get("conversation_summary"),  # type: ignore[attr-defined]
        ))

        # Build initial ToolLoopState
        initial_state: dict[str, Any] = {
            "messages": llm_history + [
                HumanMessage(content=f"<USER_MESSAGE>\n{user_message}\n</USER_MESSAGE>")
            ],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": mode_name,
        }

        try:
            # Invoke — pass recursion_limit so LangGraph enforces it
            loop_result = await loop_result_obj.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result_obj.recursion_limit},
            )
        except GraphRecursionError:
            logger.warning(
                "expediente_node_max_iterations_reached",
                mode=mode_name,
                conversation_id=conversation_id,
            )
            return Command(
                goto=END,
                update={
                    "exit_reason": "max_iterations",
                    "ai_response": "",
                },
            )
        except Exception as exc:
            # Tier 1 gate: transient infrastructure errors are re-raised so
            # LangGraph's RetryPolicy (Tier 1) can handle them.  Business errors
            # are handled here (Tier 2 reprompt or Tier 3 escalation signal).
            if is_transient_error(exc):
                raise

            logger.error(
                "expediente_node_unexpected_error",
                mode=mode_name,
                error=str(exc),
                conversation_id=conversation_id,
            )

            # Tier 2: business error — record and decide reprompt vs escalation signal
            fallback = get_fallback_handler()
            policy = fallback.get_policy("EXPEDIENTE_MODE")
            retry_state = state.get("retry_state") or create_empty_retry_state()  # type: ignore[attr-defined]
            retry_state = fallback.record_error(
                retry_state,
                RetryErrorType.USER_CONFUSION,
                str(exc),
            )

            logger.warning(
                "expediente_node_business_error",
                mode=mode_name,
                retry_count=retry_state.get("retry_count"),
                conversation_id=conversation_id,
            )

            if fallback.should_fallback(retry_state, policy):
                # Tier 3 signal: boundary wrapper will call perform_fallback_escalation
                return Command(
                    goto=END,
                    update={
                        "exit_reason": "escalated",
                        "ai_response": policy.msg_limit or "",
                        "_fallback_triggered": True,
                        "escalation_reason": (
                            f"expediente_retry_limit_{retry_state.get('retry_count', 0)}"
                        ),
                        "retry_state": retry_state,
                    },
                )
            else:
                # Below limit: return reprompt message
                reprompt = fallback.get_reprompt(retry_state, policy)
                return Command(
                    goto=END,
                    update={
                        "exit_reason": "business_error",
                        "ai_response": reprompt,
                        "retry_state": retry_state,
                    },
                )

        # Merge loop result back to ExpedienteState update
        update = _merge_loop_result_to_expediente(state, loop_result)

        # Ola 5 / S3: reset consecutive_errors on successful turn (per-turn success path).
        # retry_count is NOT reset here — only completion_flag=True resets it fully.
        retry_state = state.get("retry_state") or create_empty_retry_state()  # type: ignore[attr-defined]
        fallback = get_fallback_handler()
        policy = fallback.get_policy("EXPEDIENTE_MODE")
        retry_state = fallback.record_success(retry_state, policy)
        update["retry_state"] = retry_state

        # WS6: Inject completion flag when the tool loop has transitioned away
        # from this node's own sub-mode.  This signals entry_router that the
        # section is done and it can route to the next collection step.
        if completion_flag and own_sub_mode:
            updated_sub_mode = update.get("expediente_sub_mode", own_sub_mode)
            if updated_sub_mode != own_sub_mode:
                update[completion_flag] = True
                logger.debug(
                    "expediente_node_collection_complete",
                    mode=mode_name,
                    flag=completion_flag,
                    new_sub_mode=updated_sub_mode,
                    conversation_id=conversation_id,
                )
                # Ola 5 / S6: reset retry_state fully on completion_flag=True.
                # The section is done — clear error count so the next section
                # starts clean.  ADR-010: assign empty struct (not None/absent).
                update["retry_state"] = create_empty_retry_state()

        # Spec escenario 9 / regla dura 11: auto-emit review_summary within
        # the same turn when the last of the three sections (personal / vehicle
        # / workshop-or-skipped) is completed.
        #
        # Condition: this node has a completion_flag AND the flag was just set
        # (transition away from own_sub_mode) AND after setting it the full
        # trio is now satisfied.
        #
        # When the condition holds, invoke review_summary_node inline so that
        # its ai_response (the real summary) replaces whatever the LLM emitted
        # (which may be a promise — escenario 9.bis anti-pattern).  The user
        # sees a single ai_response per turn: the actual summary.
        if completion_flag and own_sub_mode and update.get(completion_flag) is True:
            if _trio_complete(update, dict(state)):  # type: ignore[arg-type]
                update = await _auto_emit_review_summary(
                    update=update,
                    state=dict(state),  # type: ignore[arg-type]
                    mode_name=mode_name,
                    conversation_id=conversation_id,
                )

        logger.debug(
            "expediente_node_complete",
            mode=mode_name,
            exit_reason=update.get("exit_reason", "response"),
            tools_called=loop_result.get("tools_called", []),
            conversation_id=conversation_id,
        )

        return Command(goto=END, update=update)

    _node.__name__ = f"{sub_mode}_node"
    _node.__qualname__ = _node.__name__
    return _node


# ---------------------------------------------------------------------------
# Six wired sub-mode nodes
# ---------------------------------------------------------------------------

collect_element_data_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_ELEMENT_DATA",
    sub_mode=CollectionStep.COLLECT_ELEMENT_DATA.value,
    get_tools_fn=_get_element_data_tools,
)

collect_base_docs_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_BASE_DOCS",
    sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
    get_tools_fn=_get_base_docs_tools,
)

collect_personal_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_PERSONAL",
    sub_mode=CollectionStep.COLLECT_PERSONAL.value,
    get_tools_fn=_get_personal_tools,
    completion_flag="personal_collected",
    own_sub_mode=CollectionStep.COLLECT_PERSONAL.value,
)

collect_vehicle_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_VEHICLE",
    sub_mode=CollectionStep.COLLECT_VEHICLE.value,
    get_tools_fn=_get_vehicle_tools,
    completion_flag="vehicle_collected",
    own_sub_mode=CollectionStep.COLLECT_VEHICLE.value,
)

collect_workshop_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
    sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
    get_tools_fn=_get_workshop_tools,
    completion_flag="workshop_collected",
    own_sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
)

# FIXME: guard logic below is duplicated from ReviewHandler.handle() in
# submodos/review_summary.py. Delete ReviewHandler once this node is verified
# in production. See fix-pre-to-expediente-state-propagation design AD-2.
async def review_summary_node(
    state: ExpedienteState,
    config: RunnableConfig | None = None,
) -> Command[Literal["__end__"]]:
    """
    Standalone REVIEW_SUMMARY node with deterministic pre-call of
    obtener_estado_expediente.

    Steps:
    1. Call obtener_estado_expediente.ainvoke({}) before the LLM loop.
    2. On data_source=="fallback": block (first) or escalate (second failure).
    3. On success: inject result as synthetic ToolMessage in initial messages.
    4. Delegate to build_mode_tool_loop and return Command(goto=END, ...).

    ADR-010 rule 13: the LLM must never receive a prompt referencing
    obtener_estado_expediente output unless that output was deterministically
    injected here.
    """
    conversation_id = str(state.get("conversation_id", "unknown"))  # type: ignore[attr-defined]
    user_message = str(state.get("user_message") or "")  # type: ignore[attr-defined]
    mode_context = _build_mode_context_from_expediente_state(state)

    # ── Step 1: Pre-call obtener_estado_expediente ───────────────────────────
    try:
        pre_call_result: dict[str, Any] = await obtener_estado_expediente.ainvoke({})
    except Exception as exc:
        logger.warning(
            "review_pre_call_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
        pre_call_result = {"data_source": "fallback"}

    # ── Step 2: Fallback guard ────────────────────────────────────────────────
    if pre_call_result.get("data_source") == "fallback":
        fallback_count = (state.get("_review_fallback_count") or 0) + 1  # type: ignore[attr-defined]
        logger.warning(
            "review_blocked_fallback_data",
            conversation_id=conversation_id,
            fallback_count=fallback_count,
        )
        if fallback_count >= 2:
            from agent.tools.shared_tools import escalar_a_humano as _escalar

            await _escalar.ainvoke(
                {
                    "motivo": (
                        "Review blocked: obtener_estado_expediente returned fallback "
                        f"data {fallback_count} consecutive times. "
                        "Possible DB connectivity issue."
                    ),
                    "es_error_tecnico": True,
                }
            )
            logger.warning(
                "review_fallback_escalated",
                conversation_id=conversation_id,
                fallback_count=fallback_count,
            )
            return Command(
                goto=END,
                update={
                    "ai_response": (
                        "Estoy teniendo dificultades para verificar los datos de tu expediente. "
                        "Voy a pasarte con un agente de MSI que podrá ayudarte directamente."
                    ),
                    "_review_fallback_count": None,
                    "review_blocked_reason": "stale_data",
                    "exit_reason": "response",
                },
            )
        return Command(
            goto=END,
            update={
                "ai_response": (
                    "Estoy verificando los datos de tu expediente. "
                    "¿Puedes repetir tu mensaje en unos segundos?"
                ),
                "_review_fallback_count": fallback_count,
                "review_blocked_reason": "stale_data",
                "exit_reason": "response",
            },
        )

    # DB read succeeded — tombstone fallback counter if it was set
    if state.get("_review_fallback_count"):  # type: ignore[attr-defined]
        mode_context["_review_fallback_count"] = None

    # ── Step 3: Build initial messages with synthetic ToolMessage ────────────
    client_context = _build_client_context(state)
    loop_config = ModeLoopConfig(
        mode_name="EXPEDIENTE_REVIEW_SUMMARY",
        get_tools=lambda ctx: _get_review_tools(),
        get_system_prompt=lambda loop_state: assemble_system_prompt(
            mode="EXPEDIENTE_MODE",
            mode_context=loop_state.get("_mode_context", mode_context),
            sub_mode=CollectionStep.REVIEW_SUMMARY.value,
            client_context=client_context,
        ),
        post_tool_hook=expediente_post_tool_hook,
        max_iterations=MAX_TOOL_ITERATIONS,
    )
    loop_result_obj = build_mode_tool_loop(loop_config)

    parent_messages = state.get("messages", [])  # type: ignore[attr-defined]
    llm_history = list(format_messages_for_llm(
        parent_messages,
        conversation_summary=state.get("conversation_summary"),  # type: ignore[attr-defined]
    ))

    pre_call_tool_message = ToolMessage(
        content=json.dumps(pre_call_result, ensure_ascii=False),
        tool_call_id="precall-obtener-estado-expediente",
        name="obtener_estado_expediente",
    )

    initial_state: dict[str, Any] = {
        "messages": llm_history + [
            HumanMessage(content=f"<USER_MESSAGE>\n{user_message}\n</USER_MESSAGE>"),
            pre_call_tool_message,
        ],
        "_mode_context": mode_context,
        "_conversation_id": conversation_id,
        "_mode_name": "EXPEDIENTE_REVIEW_SUMMARY",
    }

    # ── Step 4: Invoke tool loop ──────────────────────────────────────────────
    try:
        loop_result = await loop_result_obj.graph.ainvoke(
            initial_state,
            config={"recursion_limit": loop_result_obj.recursion_limit},
        )
    except GraphRecursionError:
        logger.warning(
            "expediente_node_max_iterations_reached",
            mode="EXPEDIENTE_REVIEW_SUMMARY",
            conversation_id=conversation_id,
        )
        return Command(
            goto=END,
            update={
                "exit_reason": "max_iterations",
                "ai_response": "",
            },
        )
    except Exception as exc:
        if is_transient_error(exc):
            raise
        logger.error(
            "expediente_node_unexpected_error",
            mode="EXPEDIENTE_REVIEW_SUMMARY",
            error=str(exc),
            conversation_id=conversation_id,
        )
        return Command(
            goto=END,
            update={
                "exit_reason": "error",
                "ai_response": "",
            },
        )

    update = _merge_loop_result_to_expediente(state, loop_result)

    logger.debug(
        "expediente_node_complete",
        mode="EXPEDIENTE_REVIEW_SUMMARY",
        exit_reason=update.get("exit_reason", "response"),
        tools_called=loop_result.get("tools_called", []),
        conversation_id=conversation_id,
    )

    return Command(goto=END, update=update)
