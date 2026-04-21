"""
ExpedienteState — isolated TypedDict schema for the expediente subgraph.

This module provides:
- ``ExpedienteState``: ~50-key TypedDict for the expediente subgraph's state.
  Uses ``operator.add`` for messages (append-only). All other keys have plain
  overwrite semantics within a single subgraph invocation — no ``merge_dicts``
  reducer is used, eliminating zombie-key issues entirely.

- ``parent_to_expediente()``: Extracts expediente fields from a
  ``ConversationState``-shaped dict (parent graph state) to build the input
  for the subgraph.

- ``expediente_to_parent_updates()``: Converts the subgraph's output state
  back to a dict suitable for merging into the parent ``ConversationState``.

Design reference: AD-2 (State Boundary Design) in the expediente-subgraph-refactor design.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage

from agent.state.conversation_state import RetryStateData, create_empty_retry_state


# ---------------------------------------------------------------------------
# Keys that belong in mode_context (round-tripped through boundary)
# ---------------------------------------------------------------------------

#: Keys that live in ``mode_context`` and are round-tripped through the boundary.
#: Order is arbitrary; membership determines what survives parent→exp→parent.
_EXPEDIENTE_MC_KEYS: frozenset[str] = frozenset(
    {
        # Routing
        "expediente_sub_mode",
        # Case identity
        "case_id",
        "category_id",
        "categoria_slug",
        "element_codes",
        "element_display_names",
        "tariff_tier_id",
        "tariff_amount",
        # Element collection
        "current_element_index",
        "current_element_code",
        "element_phase",
        "element_data_status",
        "element_data_all_collected",
        "current_element_field_keys",
        "element_states",
        "v2_collection_context",
        # Sub-mode data
        "base_docs_received",
        "base_doc_descriptions",
        "personal_data",
        "vehicle_data",
        "taller_propio",
        "taller_data",
        # Transition / continuity
        "expediente_transition_marker",
        "just_transitioned_from",
        "editing_from_review",
        "_review_fallback_count",
        "review_blocked_reason",
        # Coordinator signals
        "case_instructions",
        "expediente_intro_message",
        "expediente_intro_sent",
        "_guard_photo_fired_this_turn",
        "pending_recovery_case",
        "expediente_completed",
        "expediente_cancelled",
        # Kickoff confirmation flag (consumed on first EXPEDIENTE_MODE turn)
        "expediente_kickoff_pending",
        # Inherited from PRESUPUESTO
        "tarifa_calculada",
        "precio_comunicado",
        "imagenes_enviadas",
        "imagenes_enviadas_codigos",
        "vehiculo",
        "elementos_confirmados",
        "presupuesto_images_shown",
        # WS6 — collection completion flags
        "personal_collected",
        "vehicle_collected",
        "workshop_collected",
        # Layer B: dual-mode image gate sentinel
        "elementos_descripciones_entregadas",
    }
)


# ---------------------------------------------------------------------------
# ExpedienteState TypedDict
# ---------------------------------------------------------------------------


class ExpedienteState(TypedDict, total=False):
    """
    Isolated state schema for the expediente subgraph.

    All fields are optional (``total=False``) — the subgraph only carries
    the fields it needs.

    Reducer strategy:
    - ``messages``: ``operator.add`` — append-only within the subgraph.
    - All other keys: no reducer (plain overwrite) — since the subgraph runs
      as a single node in the parent graph, each invocation starts from a fresh
      mapped state.  No ``merge_dicts`` is used here, eliminating zombie keys.

    Note on tombstone keys: Within the parent's ``mode_context`` the ``merge_dicts``
    reducer required explicit ``None`` tombstones to overwrite stale checkpoint values.
    Inside this subgraph there is NO ``merge_dicts``, so all fields naturally overwrite
    each invocation. The keys that were previously "tombstone-prone" (e.g.
    ``pending_recovery_case``, ``case_instructions``) are plain
    fields here — no special annotation needed.
    """

    # ── Identity (read-only from parent) ──────────────────────────────────
    conversation_id: str
    user_id: str | None
    user_phone: str
    user_name: str | None
    client_type: str | None

    # ── Routing ───────────────────────────────────────────────────────────
    expediente_sub_mode: str  # e.g. "collect_element_data"
    user_message: str
    incoming_attachments: list[dict[str, Any]]

    # ── Case identity ─────────────────────────────────────────────────────
    case_id: str | None
    category_id: str | None
    categoria_slug: str | None  # Inherited from PRESUPUESTO
    element_codes: list[str]
    element_display_names: dict[str, str]
    tariff_tier_id: str | None
    tariff_amount: float | None

    # ── Element collection ────────────────────────────────────────────────
    current_element_index: int
    current_element_code: str | None
    element_phase: str  # "photos" | "data"
    element_data_status: dict[str, str]
    element_data_all_collected: bool
    # Previously a tombstone key in mode_context; plain field here (naturally overwrites)
    current_element_field_keys: list[dict[str, Any]] | None
    element_states: dict[str, Any]
    v2_collection_context: dict[str, Any] | None

    # ── Sub-mode data ─────────────────────────────────────────────────────
    base_docs_received: bool
    base_doc_descriptions: list[str]
    personal_data: dict[str, str | None]
    vehicle_data: dict[str, str | None]
    taller_propio: bool | None
    taller_data: dict[str, str | None] | None

    # ── Transition/continuity ─────────────────────────────────────────────
    # Previously a tombstone key in mode_context; plain field here (naturally overwrites)
    expediente_transition_marker: dict[str, Any] | None
    just_transitioned_from: str | None
    editing_from_review: bool
    # Previously a tombstone key; plain field here (naturally overwrites each invocation)
    _review_fallback_count: int
    review_blocked_reason: str | None

    # ── Coordinator signals ───────────────────────────────────────────────
    # Previously tombstone keys; plain fields here (naturally overwrite each invocation)
    case_instructions: str | None
    expediente_intro_message: str | None
    expediente_intro_sent: bool
    _guard_photo_fired_this_turn: bool
    # Previously a tombstone key; consumed exactly once by entry_router
    pending_recovery_case: dict[str, Any] | None
    expediente_completed: bool
    expediente_cancelled: bool

    # ── Inherited from PRESUPUESTO ────────────────────────────────────────
    tarifa_calculada: dict[str, Any] | None
    precio_comunicado: bool
    imagenes_enviadas: bool
    imagenes_enviadas_codigos: list[str]
    vehiculo: dict[str, str] | None
    elementos_confirmados: list[dict[str, Any]]
    presupuesto_images_shown: bool
    warnings_acknowledged: bool  # Set True by iniciar_expediente success hook

    # ── Collection completion flags (WS6 flexible routing) ───────────────
    # Set to True by each collection node when all data for that section has
    # been gathered.  Default to False via .get("key", False) — backward
    # compatible with old checkpoints that don't have these keys.
    personal_collected: bool
    vehicle_collected: bool
    workshop_collected: bool

    # ── Dual-mode image gate (Layer B) ────────────────────────────────────
    # Codes for which the literal INSTRUCCIONES DE FOTOS description block
    # has already been returned to the LLM in EXPEDIENTE_MODE.
    # Prevents repeated description delivery after the first EXPEDIENTE turn.
    # Tombstoned to [] on fresh expediente initialization.
    elementos_descripciones_entregadas: list[str]

    # ── Parent conversation context (read-only, refreshed each invocation) ─
    conversation_summary: str | None

    # ── Error handling / retry threading ─────────────────────────────────
    # retry_state is threaded from parent ConversationState through the boundary
    # so that sub-nodes can track business errors across turns (Ola 1 / design).
    # Plain overwrite semantics — no merge_dicts needed inside the subgraph.
    retry_state: RetryStateData

    # ── Exit reason discriminator (Ola 1.6 / ADR-010) ────────────────────
    # Set on every terminal Command update so the boundary wrapper can
    # determine the outcome without inspecting ai_response content.
    # Values: "response" | "max_iterations" | "error" | "escalated" | "no_tool_calls"
    exit_reason: str

    # ── Boundary-only sentinel keys (Ola 1.7) ────────────────────────────
    # These are set by _build_expediente_node when the retry limit is reached
    # and consumed + stripped by _expediente_subgraph_node boundary wrapper.
    # They MUST NOT persist into mode_context or the parent state.
    _fallback_triggered: bool
    escalation_reason: str

    # ── Output (written by nodes, read at boundary) ───────────────────────
    ai_response: str
    pending_images: dict[str, Any] | None
    # Append-only within the subgraph — same semantics as ConversationState.messages
    messages: Annotated[list[dict[str, Any]], operator.add]


# Keys that live at the parent top level — NOT in mode_context.
# These are passed into the subgraph for read access but are NOT written
# back into mode_context on the return trip.
_PARENT_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
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
        # Retry state — lives at parent top level, NOT in mode_context (ADR-010)
        "retry_state",
        # Exit reason discriminator — top-level parent key
        "exit_reason",
        # Boundary-only sentinels — consumed by wrapper, never persisted
        "_fallback_triggered",
        "escalation_reason",
    }
)


# ---------------------------------------------------------------------------
# Boundary mapping functions
# ---------------------------------------------------------------------------


def parent_to_expediente(parent_state: dict[str, Any]) -> ExpedienteState:
    """
    Extract expediente-relevant fields from a ``ConversationState``-shaped dict.

    Called at the parent↔subgraph boundary BEFORE the subgraph is invoked.
    All ~40+ expediente keys are mapped; unknown keys in ``mode_context`` are
    preserved in a pass-through bucket so they are not silently dropped.

    WS4 migration — cross-mode key locations:
      Old location (mode_context whitelist)  →  New location (shared_context)
      ─────────────────────────────────────     ──────────────────────────────
      mode_context["element_codes"]          →  shared_context["element_codes"]
      mode_context["tarifa_calculada"]       →  shared_context["tarifa_calculada"]
      mode_context["categoria_slug"]         →  shared_context["categoria_slug"]
      mode_context["precio_comunicado"]      →  shared_context["precio_comunicado"]
      mode_context["imagenes_enviadas"]      →  shared_context["imagenes_enviadas"]
      mode_context["vehiculo"]               →  shared_context["vehiculo"]
      mode_context["elementos_confirmados"]  →  shared_context["elementos_confirmados"]

    For backward compat, mode_context values are used as fallback if
    shared_context key is absent (supports old checkpoints without shared_context).

    Args:
        parent_state: A ``ConversationState``-shaped dict (parent graph output).

    Returns:
        ``ExpedienteState`` dict ready to pass as input to the subgraph.
    """
    mc: dict[str, Any] = parent_state.get("mode_context") or {}
    sc: dict[str, Any] = parent_state.get("shared_context") or {}

    # Start with all mode_context keys (captures both declared and undeclared runtime keys)
    exp: dict[str, Any] = dict(mc)

    # Cross-mode keys: prefer shared_context, fall back to mode_context for old checkpoints.
    # Only domain keys + warnings_acknowledged survive the mode boundary.
    # UX-flow flags (precio_comunicado, imagenes_enviadas, presupuesto_images_shown,
    # advertencias_comunicadas) are PRE_EXPEDIENTE-internal; they do NOT propagate.
    _cross_mode_keys = (
        "element_codes",
        "elementos_confirmados",
        "tarifa_calculada",
        "categoria_slug",
        "vehiculo",
        "warnings_acknowledged",
        "imagenes_enviadas_codigos",
    )
    for key in _cross_mode_keys:
        if key in sc:
            exp[key] = sc[key]
        # else: already present from mc dict above (backward compat)

    # Override / supplement with top-level parent fields
    exp.update(
        {
            # Identity
            "conversation_id": parent_state.get("conversation_id", ""),
            "user_id": parent_state.get("user_id"),
            "user_phone": parent_state.get("user_phone", ""),
            "user_name": parent_state.get("user_name"),
            "client_type": parent_state.get("client_type"),
            # Turn data
            "user_message": parent_state.get("user_message") or "",
            "incoming_attachments": parent_state.get("incoming_attachments") or [],
            # Messages: carry parent conversation history so the LLM has context
            # from prior modes (e.g. presupuesto flow).  The sub-mode node
            # formats these via format_messages_for_llm() before sending to the LLM.
            "messages": parent_state.get("messages") or [],
            "conversation_summary": parent_state.get("conversation_summary"),
            # Thread retry_state from parent — default to empty for backward compat
            # with old Redis checkpoints that don't have this key yet.
            "retry_state": parent_state.get("retry_state") or create_empty_retry_state(),
        }
    )

    return ExpedienteState(**{k: v for k, v in exp.items()})  # type: ignore[misc]


def expediente_to_parent_updates(exp_state: ExpedienteState) -> dict[str, Any]:
    """
    Convert the subgraph's output state into parent state update dict.

    Called at the subgraph→parent boundary AFTER the subgraph completes.
    The returned dict is suitable for merging into ``ConversationState`` via
    the parent graph's ``merge_dicts`` reducer on ``mode_context``.

    Args:
        exp_state: The ``ExpedienteState`` returned by the subgraph.

    Returns:
        Dict with keys ``ai_response``, ``pending_images``, and ``mode_context``
        (a flat dict of all expediente mode_context keys for the parent to merge).
    """
    # Build mode_context update from all expediente keys in exp_state
    # (excludes top-level-only keys like conversation_id, user_message, messages)
    mc_updates: dict[str, Any] = {}

    for key, value in exp_state.items():
        # Skip keys that belong at the parent top level, not in mode_context
        if key in _PARENT_TOP_LEVEL_KEYS:
            continue
        mc_updates[key] = value

    # Extract mode transition signals BEFORE building the return dict.
    # _transition_to takes precedence over pending_mode_transition.
    # These must be popped from mc_updates so they don't persist as stale
    # keys in mode_context.
    transition = mc_updates.pop("_transition_to", None) or mc_updates.pop(
        "pending_mode_transition", None
    )
    # If _transition_to was found, also clean up pending_mode_transition
    if transition and "pending_mode_transition" in mc_updates:
        mc_updates.pop("pending_mode_transition")

    # Build messages for parent checkpoint continuity
    messages: list = []
    user_message = exp_state.get("user_message") or ""
    ai_response = exp_state.get("ai_response") or ""
    if user_message.strip():
        messages.append(
            HumanMessage(content=f"<USER_MESSAGE>\n{user_message}\n</USER_MESSAGE>")
        )
    if ai_response.strip():
        messages.append(AIMessage(content=ai_response))

    result: dict[str, Any] = {
        "ai_response": exp_state.get("ai_response", ""),
        "pending_images": exp_state.get("pending_images"),
        "mode_context": mc_updates,
        "messages": messages,
        # Write retry_state back at parent top level (NOT inside mode_context).
        # ADR-010 tombstone: if the state carries a reset, write the empty struct
        # explicitly so the parent's merge_retry_state reducer overwrites the stale
        # Redis checkpoint value (never use pop() without assigning None or a value).
        "retry_state": exp_state.get("retry_state") or create_empty_retry_state(),
    }

    if transition:
        result["current_mode"] = transition

    # Promote boundary-only sentinel keys to top level if present.
    # The _expediente_subgraph_node boundary wrapper consumes and strips them.
    if exp_state.get("_fallback_triggered"):
        result["_fallback_triggered"] = exp_state["_fallback_triggered"]
    if exp_state.get("escalation_reason"):
        result["escalation_reason"] = exp_state["escalation_reason"]

    # Exit reason is also a top-level key when set.
    if exp_state.get("exit_reason"):
        result["exit_reason"] = exp_state["exit_reason"]

    return result
