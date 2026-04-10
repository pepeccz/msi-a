"""
Expediente subgraph nodes.

Contains:
- ``entry_router``: Reads ``expediente_sub_mode`` from state and dispatches to
  the correct sub-mode node via ``Command(goto=target)``.

- ``_build_expediente_node``: DRY factory that builds a wired expediente sub-mode
  node from (mode_name, prompt_mode, get_tools_fn).  Each returned node:
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

from typing import Any, Callable, Literal

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from agent.modes.submodos._shared import (
    COLLECT_ELEMENT_DATA,
    COLLECT_BASE_DOCS,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    _get_element_data_tools,
    _get_base_docs_tools,
    _get_personal_tools,
    _get_vehicle_tools,
    _get_workshop_tools,
    _get_review_tools,
)
from agent.modes.expediente_state import ExpedienteState
from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
from agent.modes.post_tool_hooks import expediente_post_tool_hook
from agent.prompts.loader import assemble_system_prompt
from agent.services.expediente_init import initialize_expediente
from agent.state.helpers import set_current_state, clear_current_state

# GraphRecursionError is in langgraph.errors — import with fallback for environments
# where langgraph version differs.
try:
    from langgraph.errors import GraphRecursionError
except ImportError:  # pragma: no cover — older langgraph versions
    GraphRecursionError = RecursionError  # type: ignore[misc, assignment]

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn for all expediente nodes
MAX_TOOL_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Routing map: sub_mode string → subgraph node name
# ---------------------------------------------------------------------------

_SUB_MODE_TO_NODE: dict[str, str] = {
    COLLECT_ELEMENT_DATA: "collect_element_data_node",
    COLLECT_BASE_DOCS: "collect_base_docs_node",
    COLLECT_PERSONAL: "collect_personal_node",
    COLLECT_VEHICLE: "collect_vehicle_node",
    COLLECT_WORKSHOP: "collect_workshop_node",
    REVIEW_SUMMARY: "review_summary_node",
}

# Default node when sub_mode is unrecognized or absent
_DEFAULT_NODE = "collect_element_data_node"


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

        logger.debug(
            "entry_router_dispatching_after_init",
            sub_mode=sub_mode,
            target_node=target_node,
            case_id=init_updates.get("case_id"),
            conversation_id=conversation_id,
        )

        return Command(update=init_updates, goto=target_node)

    # case_id already present — pure routing, no initialization needed
    sub_mode = state.get("expediente_sub_mode") or ""  # type: ignore[attr-defined]
    target_node = _SUB_MODE_TO_NODE.get(sub_mode, _DEFAULT_NODE)

    # T-5: Phase reconciliation (lightweight — only checks current element).
    # If element_phase is "photos" but the DB-backed status shows the element
    # is already in "pending_data", the photos step was already completed.
    # Correct the phase to "data" so we don't ask for photos again.
    if sub_mode == COLLECT_ELEMENT_DATA and state.get("element_phase") == "photos":  # type: ignore[attr-defined]
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
    if sub_mode == COLLECT_ELEMENT_DATA and state.get("element_phase") == "photos":  # type: ignore[attr-defined]
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

    logger.debug(
        "entry_router_dispatching",
        sub_mode=sub_mode,
        target_node=target_node,
        case_id=case_id,
        conversation_id=conversation_id,
    )

    return Command(goto=target_node, update=None)


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
    Build a ConversationState-shaped dict for the ContextVar (legacy tools).

    Legacy tools (e.g. escalar_a_humano) call ``get_tool_state()`` which reads
    ``_current_state`` ContextVar.  They expect nested ``mode_context``.

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
# Sub-mode node factory
# ---------------------------------------------------------------------------


def _build_expediente_node(
    *,
    mode_name: str,
    prompt_mode: str,
    get_tools_fn: Callable[[], list],
) -> Callable[[ExpedienteState, RunnableConfig], Any]:  # noqa: FA100
    """
    Factory for wired expediente sub-mode nodes.

    Returns an async function suitable as a LangGraph node that:
    1. Converts ExpedienteState → ModeLoopConfig + ToolLoopState
    2. Invokes build_mode_tool_loop subgraph
    3. Merges pending_state_updates back to ExpedienteState update
    4. Returns Command(goto=END, update=merged)

    The returned node catches ``GraphRecursionError`` (max_iterations exceeded) and
    any unexpected exceptions, returning a safe Command in both cases.

    Args:
        mode_name:    Identifier for structured logging (e.g. "EXPEDIENTE_COLLECT_PERSONAL").
        prompt_mode:  Key for assemble_system_prompt (e.g. "EXPEDIENTE_DATOS_PERSONALES").
        get_tools_fn: Zero-argument function returning the tool list for this sub-mode.

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

        # Build client context for the prompt
        client_context = _build_client_context(state)

        # Determine the expediente sub_mode string for the prompt loader.
        # The prompt loader resolves "EXPEDIENTE_MODE" + sub_mode → the correct
        # mode module (e.g. "EXPEDIENTE_DATOS_PERSONALES" → expediente_datos_personales.md).
        # prompt_mode is already the fully-qualified key (e.g. "EXPEDIENTE_DATOS_PERSONALES"),
        # so we pass mode="EXPEDIENTE_MODE" and sub_mode=<suffix> by stripping the prefix.
        _EXPEDIENTE_PREFIX = "EXPEDIENTE_"
        prompt_sub_mode = (
            prompt_mode[len(_EXPEDIENTE_PREFIX):]
            if prompt_mode.startswith(_EXPEDIENTE_PREFIX)
            else prompt_mode
        )

        loop_config = ModeLoopConfig(
            mode_name=mode_name,
            get_tools=lambda ctx: get_tools_fn(),
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="EXPEDIENTE_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                sub_mode=prompt_sub_mode,
                client_context=client_context,
            ),
            post_tool_hook=expediente_post_tool_hook,
            max_iterations=MAX_TOOL_ITERATIONS,
        )

        subgraph = build_mode_tool_loop(loop_config)

        # Build initial ToolLoopState
        initial_state: dict[str, Any] = {
            "messages": [
                HumanMessage(content=f"<USER_MESSAGE>\n{user_message}\n</USER_MESSAGE>")
            ],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": mode_name,
        }

        # Set ContextVar for legacy tools (transition period)
        full_state_for_tools = _build_full_state_for_tools(state, mode_context)
        set_current_state(full_state_for_tools)

        try:
            loop_result = await subgraph.ainvoke(initial_state)
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
            logger.error(
                "expediente_node_unexpected_error",
                mode=mode_name,
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
        finally:
            clear_current_state()

        # Merge loop result back to ExpedienteState update
        update = _merge_loop_result_to_expediente(state, loop_result)

        logger.debug(
            "expediente_node_complete",
            mode=mode_name,
            exit_reason=update.get("exit_reason", "response"),
            tools_called=loop_result.get("tools_called", []),
            conversation_id=conversation_id,
        )

        return Command(goto=END, update=update)

    _node.__name__ = f"{prompt_mode.lower()}_node"
    _node.__qualname__ = _node.__name__
    return _node


# ---------------------------------------------------------------------------
# Six wired sub-mode nodes
# ---------------------------------------------------------------------------

collect_element_data_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_ELEMENT_DATA",
    prompt_mode="EXPEDIENTE_DOCUMENTACION_ELEMENTOS",
    get_tools_fn=_get_element_data_tools,
)

collect_base_docs_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_BASE_DOCS",
    prompt_mode="EXPEDIENTE_DOCUMENTACION_BASE",
    get_tools_fn=_get_base_docs_tools,
)

collect_personal_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_PERSONAL",
    prompt_mode="EXPEDIENTE_DATOS_PERSONALES",
    get_tools_fn=_get_personal_tools,
)

collect_vehicle_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_VEHICLE",
    prompt_mode="EXPEDIENTE_DATOS_VEHICULO",
    get_tools_fn=_get_vehicle_tools,
)

collect_workshop_node = _build_expediente_node(
    mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
    prompt_mode="EXPEDIENTE_TALLER",
    get_tools_fn=_get_workshop_tools,
)

review_summary_node = _build_expediente_node(
    mode_name="EXPEDIENTE_REVIEW_SUMMARY",
    prompt_mode="EXPEDIENTE_REVISION",
    get_tools_fn=_get_review_tools,
)
