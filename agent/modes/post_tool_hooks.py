"""
MSI-a — Post-Tool Hooks for Mode-Specific State Extraction (AD-4, T-17).

Provides ``pre_expediente_post_tool_hook`` for use as ``post_tool_hook`` callback
in ``ModeLoopConfig``.

Design principles:
- NEVER inject fake AIMessage objects (protocol corruption anti-pattern)
- Return state update dicts that post_tool_node will apply to pending_state_updates
- Reuse ``_extract_context_from_tool`` from PreExpedienteModeNode (same logic, clean output)
- SystemMessage may be appended to messages list for factual context injection (AD-4),
  but only as a LAST RESORT; prefer state updates.

AD-4 — What each on_tool_result behavior becomes:

| Old behavior                  | New mechanism                              |
|-------------------------------|-------------------------------------------|
| inject_messages fake assistant| state update dict (no message injection)   |
| _extract_context_from_tool    | same function, called here directly        |
| _apply_tool_flags             | tool returns _state_update; post_tool_node applies |
| rebind_tools mid-loop         | get_tools(mode_context) reads pending state |
| pending_images capture        | _pending_images key in state update        |

fix-extract-context-dead-code (AD-4 wiring fix):
  _extract_context_from_tool was never called from this hook — 14 extraction paths
  were dead code. This file wires the call at the START of the hook so that
  element_codes, categoria_slug, pending_variants, tarifa_calculada,
  elementos_confirmados, precio_comunicado, and imagenes_enviadas are all populated
  correctly on every tool call.

  Merge order (three-layer):
    1. base mode_context (from state snapshot)
    2. structural_mc from _extract_context_from_tool (fills element_codes, etc.)
    3. hook_mc_updates (hook-specific: tarifa_calculada price key, precio_comunicado)
  Hook-specific values WIN on conflict (hook is last-writer).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: extract tool_args from the last AIMessage in state
# ---------------------------------------------------------------------------


def _extract_tool_args_from_messages(state: dict, tool_name: str) -> dict:
    """
    Extract tool_args for ``tool_name`` from the last AIMessage in state["messages"].

    Walks backwards through ``state["messages"]`` to find the most recent
    AIMessage (or AIMessageChunk) that has tool_calls. Matches the first
    tool_call entry whose ``name == tool_name`` and returns its ``args`` dict.

    Uses duck-typing (``type(msg).__name__``) instead of ``isinstance()`` to
    avoid class identity issues when langchain_core.messages is reloaded in
    test environments.

    Args:
        state:     Hook state dict (contains "messages" list).
        tool_name: Name of the tool whose args we want to recover.

    Returns:
        The ``args`` dict for the matching tool_call, or ``{}`` if not found.
    """
    for msg in reversed(state.get("messages", [])):
        if type(msg).__name__ in ("AIMessage", "AIMessageChunk"):
            for tc in getattr(msg, "tool_calls", None) or []:
                if tc.get("name") == tool_name:
                    return tc.get("args") or {}
    return {}


# ---------------------------------------------------------------------------
# PRE_EXPEDIENTE post-tool hook
# ---------------------------------------------------------------------------


async def pre_expediente_post_tool_hook(
    tool_name: str,
    result_dict: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Post-tool hook for PRE_EXPEDIENTE_MODE.

    Called by post_tool_node after each tool execution. Returns a dict of
    additional state updates to merge into pending_state_updates.

    Replaces on_tool_result + inject_messages from the old generic_llm_loop path.

    Key behaviors (post fix-extract-context-dead-code):
    - Calls _extract_context_from_tool at entry for structural context population
    - calcular_tarifa_con_elementos success → price_authority_confirmed = True
    - identificar_y_resolver_elementos with variants → pending_variants LIST (not bool)
    - enviar_imagenes_ejemplo → _pending_images captured in state + imagenes_enviadas
    - confirmar_presupuesto → pending_mode_transition signal (already via _state_update)

    Merge order (three-layer):
    1. base mode_context (from state["_mode_context"] snapshot)
    2. structural_mc from _extract_context_from_tool (fills element_codes, etc.)
    3. hook_mc_updates (hook-specific overrides: precio_comunicado, tarifa_calculada price)
    Hook-specific values WIN on conflict.

    IMPORTANT: This hook NEVER injects fake AIMessage objects.
    It only returns state update dicts.

    Args:
        tool_name: Name of the tool that was just executed.
        result_dict: The parsed tool result dict.
        state: Current ToolLoopState at time of hook invocation.

    Returns:
        Dict of additional state updates to merge into pending_state_updates.
        Empty dict if no additional updates are needed.
    """
    updates: dict[str, Any] = {}
    mode_context = dict(state.get("_mode_context") or {})

    # Merge pending mode_context from accumulated state updates so the
    # three-layer merge base reflects changes from earlier tool calls
    # in the same turn (e.g. first tool resolved variants, second tool
    # should see that resolution in the base layer).
    accumulated_mc = (state.get("pending_state_updates") or {}).get("mode_context")
    if isinstance(accumulated_mc, dict):
        mode_context.update(accumulated_mc)

    if not isinstance(result_dict, dict):
        return updates

    success = result_dict.get("success")

    # ── STEP 1: Structural extraction via _extract_context_from_tool ─────
    # Called at the START for every tool call so element_codes, categoria_slug,
    # pending_variants, tarifa_calculada, elementos_confirmados, etc. are always
    # populated. This was dead code before (function existed but was never called).
    structural_mc: dict[str, Any] = {}
    try:
        # Function-level import to avoid circular imports (AD-4 convention).
        from agent.modes.pre_expediente_mode import PreExpedienteModeNode

        tool_args = _extract_tool_args_from_messages(state, tool_name)
        current_element_codes = mode_context.get("element_codes", [])

        # _extract_context_from_tool expects result as JSON string or dict.
        result_json = (
            json.dumps(result_dict)
            if isinstance(result_dict, dict)
            else str(result_dict)
        )
        structural_mc = PreExpedienteModeNode._extract_context_from_tool(
            tool_name,
            tool_args,
            result_json,
            current_element_codes,
        )
    except Exception as exc:
        logger.warning(
            "pre_expediente_hook_extraction_failed",
            tool_name=tool_name,
            error=str(exc),
            conversation_id=state.get("_conversation_id", "unknown"),
        )
        # structural_mc stays {} — hook-specific logic below still runs

    # ── STEP 2: Hook-specific logic ───────────────────────────────────────
    # These updates are hook-specific (not handled by _extract_context_from_tool)
    # and WIN over structural_mc on key conflicts.
    hook_mc_updates: dict[str, Any] = {}

    # ── calcular_tarifa_con_elementos ─────────────────────────────────────
    if tool_name == "calcular_tarifa_con_elementos":
        if success is not False:
            # Price calculation succeeded — mark price authority confirmed (root-level)
            updates["price_authority_confirmed"] = True

            # Extract price for logging
            precio = None
            datos = result_dict.get("datos")
            if isinstance(datos, dict):
                precio = datos.get("price")
            elif isinstance(result_dict.get("precio_final"), (int, float)):
                precio = result_dict.get("precio_final")

            logger.info(
                "pre_expediente_hook_price_authority_confirmed",
                precio=precio,
                conversation_id=state.get("_conversation_id", "unknown"),
            )

            # tarifa_calculada: structural_mc (layer 2) already has the full
            # result dict including imagenes_ejemplo, documentacion, etc.
            # Do NOT override it here — a partial dict would strip images.
            # Only set the flags that the hook is authoritative for.
            # Cross-mode keys go into shared_context (WS4).
            # T-06: imagenes_enviadas NOT reset — delta filtering handles new elements.
            # NOTE: precio_comunicado is NOT set here. The tariff is "calculated"
            # but the LLM hasn't communicated it to the user yet. The flag
            # stays False so format_mode_context shows "DEBES comunicarlo"
            # and the phase stays at PRICING until the LLM generates a response
            # that includes the price. precio_comunicado=True is set AFTER
            # the LLM response is generated, in the mode node's post-response hook.

        else:
            # Upgraded from DEBUG to WARNING — this is a failure signal that
            # caused R3 self-heal silent regressions across two SDD changes.
            # See sdd/fix-r3-tool-not-found.
            logger.warning(
                "pre_expediente_hook_tariff_failed_no_price_authority",
                error=result_dict.get("error"),
                conversation_id=state.get("_conversation_id", "unknown"),
            )

    # ── identificar_y_resolver_elementos ─────────────────────────────────
    elif tool_name == "identificar_y_resolver_elementos":
        # Variant detection logging (structural work done in structural_mc)
        preguntas_variantes = result_dict.get("preguntas_variantes") or []
        elementos_con_variantes = result_dict.get("elementos_con_variantes") or []

        if preguntas_variantes or elementos_con_variantes:
            logger.info(
                "pre_expediente_hook_variant_pending_detected",
                num_variants=len(preguntas_variantes),
                conversation_id=state.get("_conversation_id", "unknown"),
            )
        # NOTE: variant_pending bool (old dead code) NOT written here.
        # pending_variants LIST is written by structural_mc from _extract_context_from_tool.

        # ── Gap A: mid-turn phase revalidation (AC-2.1, AC-2.2, AC-2.3) ──
        # When this tool resets precio_comunicado (and/or other phase flags) via
        # _state_update.shared_context, those values must WIN in the three-layer
        # merge so the NEXT llm_node call within the same turn assembles its
        # system prompt with the fresh (not stale turn-start) flag values.
        #
        # WHY hook_mc_updates (Layer 3) and not structural_mc (Layer 2):
        #   _extract_context_from_tool does NOT read _state_update.shared_context
        #   for precio_comunicado — that flag is managed post-LLM-response in
        #   _process_message. Here the tool is explicitly RESETTING it, so the hook
        #   must be the authoritative layer that propagates the reset.
        #
        # NOTE — divergence from design Q2 wording ("mutate state['_mode_context']
        #   in place"): direct in-place mutation of state["_mode_context"] is not
        #   possible in LangGraph's state machine. The equivalent effect is achieved
        #   by writing to hook_mc_updates (Layer 3) which goes into
        #   pending_state_updates["mode_context"], already merged by llm_node
        #   (tool_loop.py:454-458) before every get_system_prompt call.
        _tool_su = result_dict.get("_state_update") or {}
        _tool_sc = _tool_su.get("shared_context") or {}
        _PHASE_FLAGS = ("precio_comunicado",)
        for _flag in _PHASE_FLAGS:
            if _flag in _tool_sc:
                hook_mc_updates[_flag] = _tool_sc[_flag]
                logger.debug(
                    "pre_expediente_hook_phase_flag_flushed",
                    flag=_flag,
                    old_value=mode_context.get(_flag),
                    new_value=_tool_sc[_flag],
                    conversation_id=state.get("_conversation_id", "unknown"),
                )

    # ── enviar_imagenes_ejemplo ───────────────────────────────────────────
    elif tool_name == "enviar_imagenes_ejemplo":
        # Skip on error — don't mark images as sent if tool failed
        if result_dict.get("error") or result_dict.get("success") is False:
            pass
        else:
            # Capture pending images for main.py's image delivery pipeline
            pending_images = result_dict.get("_pending_images")
            if pending_images:
                updates["_pending_images"] = pending_images
                logger.info(
                    "pre_expediente_hook_pending_images_captured",
                    conversation_id=state.get("_conversation_id", "unknown"),
                )

            # T-08: Append sent codes (not replace) to imagenes_enviadas_codigos
            state_update = result_dict.get("_state_update", {})
            sc = state_update.get("shared_context", {})
            pending_codes: list[str] = list(sc.get("imagenes_enviadas_codigos_pending", []))

            # Read existing codes from mode_context (cross-turn persistence)
            mc_existing: list[str] = list(mode_context.get("imagenes_enviadas_codigos") or [])
            # Merge: preserve existing, append new (dedup, preserve order)
            merged = list(dict.fromkeys(mc_existing + pending_codes))

            # Dual-write: bool + list
            existing_sc = (updates.get("shared_context") or {})
            updates["shared_context"] = {
                **existing_sc,
                "imagenes_enviadas": bool(merged),
                "imagenes_enviadas_codigos": merged,
            }
            # Also write flat mode_context key for same-turn reads
            updates["imagenes_enviadas"] = bool(merged)
            updates["imagenes_enviadas_codigos"] = merged

    # ── confirmar_presupuesto ─────────────────────────────────────────────
    elif tool_name == "confirmar_presupuesto":
        # The transition signal should already be in _state_update from the tool.
        # This hook confirms it was processed and passes through the intro emission
        # fields so they survive the PRE_EXPEDIENTE → EXPEDIENTE_MODE boundary.
        # Without these two lines the fields are lost because the PRE hook runs
        # (not the EXPEDIENTE hook whose _extract_expediente_context already maps them).
        if result_dict.get("success"):
            logger.info(
                "pre_expediente_hook_confirm_presupuesto_success",
                conversation_id=state.get("_conversation_id", "unknown"),
            )
            # Pass intro emission fields from tool _state_update through to
            # pending_state_updates so parent_to_expediente can carry them.
            tool_su = result_dict.get("_state_update") or {}
            if isinstance(tool_su.get("expediente_intro_message"), str):
                updates["expediente_intro_message"] = tool_su["expediente_intro_message"]
            if isinstance(tool_su.get("expediente_intro_sent"), bool):
                updates["expediente_intro_sent"] = tool_su["expediente_intro_sent"]

    # ── iniciar_expediente ────────────────────────────────────────────────
    elif tool_name == "iniciar_expediente":
        if success is not False:
            existing_sc = updates.get("shared_context") or {}
            updates["shared_context"] = {
                **existing_sc,
                "warnings_acknowledged": True,
            }
            logger.info(
                "pre_expediente_hook_warnings_acknowledged",
                conversation_id=state.get("_conversation_id", "unknown"),
            )

    # ── seleccionar_variante_por_respuesta ───────────────────────────────
    elif tool_name == "seleccionar_variante_por_respuesta":
        # When seleccionar runs in the same AIMessage as identificar, the
        # tool's ContextVar is stale (no pending entries yet) so it returns
        # without _state_update. structural_mc won't update pending_variants
        # either (it relies on _state_update). Compensate here by marking
        # the matching entry resolved in the accumulated mode_context.
        selected = result_dict.get("selected_variant")
        codigo_base = (
            result_dict.get("codigo_base")
            or _extract_tool_args_from_messages(state, tool_name).get(
                "codigo_elemento_base", ""
            )
        )
        has_structural_pv = "pending_variants" in structural_mc

        if selected and not result_dict.get("error") and not has_structural_pv:
            # structural_mc didn't update pending_variants — compensate
            pending = list(mode_context.get("pending_variants") or [])
            codigo_base_upper = codigo_base.upper() if codigo_base else ""
            updated = False
            for entry in pending:
                if (
                    entry.get("codigo_base", "").upper() == codigo_base_upper
                    and entry.get("status") != "resolved"
                ):
                    entry["status"] = "resolved"
                    entry["cantidad_resuelta"] = entry.get("cantidad_total", 1)
                    entry["cantidad_pendiente"] = 0
                    entry.setdefault("resoluciones", []).append(
                        {
                            "variant_code": selected,
                            "quantity": 1,
                            "confidence": result_dict.get("confidence", 0.9),
                            "source": "hook_compensated",
                        }
                    )
                    updated = True
                    break
            if updated:
                hook_mc_updates["pending_variants"] = pending
                logger.info(
                    "pre_expediente_hook_variant_compensated",
                    codigo_base=codigo_base,
                    selected=selected,
                    conversation_id=state.get("_conversation_id", "unknown"),
                )

    # ── All other tools: no specific hook behavior ────────────────────────
    else:
        logger.debug(
            "pre_expediente_hook_no_specific_behavior",
            tool_name=tool_name,
            conversation_id=state.get("_conversation_id", "unknown"),
        )

    # ── STEP 3: Three-layer merge ─────────────────────────────────────────
    # Layer 1: base mode_context (existing state snapshot)
    # Layer 2: structural_mc from _extract_context_from_tool (fills element_codes etc.)
    # Layer 3: hook_mc_updates (hook-specific overrides, WIN on conflict)
    merged_mc = {**mode_context, **structural_mc, **hook_mc_updates}
    updates["mode_context"] = merged_mc

    # ── STEP 4: Propagate cross-mode keys to shared_context (WS4) ────────
    # Only domain keys survive ALL mode transitions via merge_dicts reducer.
    # UX-flow flags (precio_comunicado, imagenes_enviadas, presupuesto_images_shown,
    # advertencias_comunicadas) are PRE_EXPEDIENTE-internal; they do NOT cross modes.
    _CROSS_MODE_KEYS = (
        "element_codes",
        "elementos_confirmados",
        "tarifa_calculada",
        "categoria_slug",
        "vehiculo",
    )
    sc_from_hook: dict[str, Any] = {}
    for _k in _CROSS_MODE_KEYS:
        if _k in merged_mc:
            sc_from_hook[_k] = merged_mc[_k]
    if sc_from_hook:
        existing_sc = updates.get("shared_context") or {}
        updates["shared_context"] = {**existing_sc, **sc_from_hook}

    return updates


# Backward compat alias — any code that still imports presupuesto_post_tool_hook
# continues to work during the Redis checkpoint TTL window.
presupuesto_post_tool_hook = pre_expediente_post_tool_hook


# ---------------------------------------------------------------------------
# EXPEDIENTE pure extraction helper
# ---------------------------------------------------------------------------


def _extract_expediente_context(
    tool_name: str,
    result_dict: dict[str, Any],
    current_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Pure function: dispatch on tool_name and extract mode_context updates.

    Extracted from ExpedienteModeNode.extract_context_from_tool() (static method)
    so it can be called from the post-tool hook without importing the class.

    Returns a dict of mode_context updates.  No side effects.
    """
    # Function-level imports to avoid circular imports (same convention as presupuesto hook).
    from agent.modes.submodos._shared import (
        _set_transition_updates,
        _extract_field_keys_from_tool_result,
    )
    from agent.utils.expediente_types import CollectionStep

    updates: dict[str, Any] = {}
    data = result_dict  # already a dict (caller guarantees)

    # Standard contract: tools can declare mode_context updates via _context_updates
    if "_context_updates" in data:
        ctx_updates = data["_context_updates"]
        if isinstance(ctx_updates, dict):
            updates.update(ctx_updates)

    # ── Sub-mode transitions ──────────────────────────────────────────────
    # Skip transition detection on error results to prevent false transitions.
    if tool_name in ("completar_elemento_actual", "confirmar_fotos_elemento"):
        if data.get("error") or data.get("success") is False:
            pass
        elif data.get("all_elements_complete"):
            _set_transition_updates(
                updates=updates,
                from_sub_mode=CollectionStep.COLLECT_ELEMENT_DATA.value,
                to_sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
                tool_name=tool_name,
            )

    elif tool_name == "confirmar_documentacion_base":
        if (
            data.get("success")
            and not data.get("already_confirmed")
            and not data.get("escalated")
        ):
            _set_transition_updates(
                updates=updates,
                from_sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
                to_sub_mode=CollectionStep.COLLECT_PERSONAL.value,
                tool_name=tool_name,
            )

    elif tool_name in ("actualizar_datos_personales", "actualizar_datos_vehiculo"):
        if data.get("success"):
            next_step = data.get("next_step")
            if next_step == "collect_vehicle":
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.COLLECT_PERSONAL.value,
                    to_sub_mode=CollectionStep.COLLECT_VEHICLE.value,
                    tool_name=tool_name,
                )
            elif next_step == "collect_workshop":
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.COLLECT_VEHICLE.value,
                    to_sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
                    tool_name=tool_name,
                )

    elif tool_name == "actualizar_datos_taller":
        if data.get("success"):
            next_step = data.get("next_step")
            if next_step is None:
                pass
            elif next_step == "collect_workshop":
                pass  # Stay in COLLECT_WORKSHOP
            else:
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
                    to_sub_mode=CollectionStep.REVIEW_SUMMARY.value,
                    tool_name=tool_name,
                )

    elif tool_name == "finalizar_expediente":
        if data.get("success"):
            updates["expediente_completed"] = True
            updates["_transition_to"] = "PRE_EXPEDIENTE_MODE"

    elif tool_name == "iniciar_expediente":
        if data.get("success"):
            flags = data.get("_internal_flags", {})
            if isinstance(flags, dict) and flags.get("intro_already_sent"):
                updates["intro_already_sent"] = True

    elif tool_name == "cancelar_expediente":
        if data.get("success"):
            updates["expediente_cancelled"] = True
            updates["_transition_to"] = "PRE_EXPEDIENTE_MODE"

    elif tool_name == "editar_expediente":
        if data.get("success"):
            next_step = data.get("next_step")
            _STEP_TO_SUBMODE = {
                "collect_personal": CollectionStep.COLLECT_PERSONAL.value,
                "collect_vehicle": CollectionStep.COLLECT_VEHICLE.value,
                "collect_workshop": CollectionStep.COLLECT_WORKSHOP.value,
                "collect_base_docs": CollectionStep.COLLECT_BASE_DOCS.value,
                "collect_element_data": CollectionStep.COLLECT_ELEMENT_DATA.value,
            }
            if next_step in _STEP_TO_SUBMODE:
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.REVIEW_SUMMARY.value,
                    to_sub_mode=_STEP_TO_SUBMODE[next_step],
                    tool_name=tool_name,
                )
                updates["editing_from_review"] = True

    # ── Element progress tracking ─────────────────────────────────────────
    if tool_name in (
        "confirmar_fotos_elemento",
        "guardar_datos_elemento",
        "completar_elemento_actual",
    ):
        if "current_element_index" in data:
            updates["current_element_index"] = data["current_element_index"]
        if "element_phase" in data:
            updates["element_phase"] = data["element_phase"]

    # ── Field key extraction ──────────────────────────────────────────────
    if tool_name in ("confirmar_fotos_elemento", "obtener_campos_elemento"):
        field_keys = _extract_field_keys_from_tool_result(data)
        if field_keys:
            updates["current_element_field_keys"] = field_keys
    elif tool_name == "guardar_datos_elemento":
        field_keys = _extract_field_keys_from_tool_result(data)
        if field_keys:
            updates["current_element_field_keys"] = field_keys
        if (
            data.get("all_required_collected")
            and data.get("action") == "ELEMENT_DATA_COMPLETE"
        ):
            updates["element_data_all_collected"] = True
            updates["current_element_field_keys"] = None
        else:
            updates["element_data_all_collected"] = False
    elif tool_name == "completar_elemento_actual":
        updates["current_element_field_keys"] = None
        updates["element_data_all_collected"] = False

    # ── FSM compatibility: unwrap case_collection_update ─────────────────
    if "case_collection_update" in data:
        fsm_update = data["case_collection_update"]
        if isinstance(fsm_update, dict):
            case_coll = fsm_update.get("case_collection", {})
            if isinstance(case_coll, dict) and case_coll:
                updates.update(case_coll)
    elif "case_collection" in data:
        fsm_updates = data["case_collection"]
        if isinstance(fsm_updates, dict):
            updates.update(fsm_updates)

    # ── Intro signals ─────────────────────────────────────────────────────
    if isinstance(data.get("expediente_intro_message"), str):
        updates["expediente_intro_message"] = data["expediente_intro_message"]
    if isinstance(data.get("expediente_intro_sent"), bool):
        updates["expediente_intro_sent"] = data["expediente_intro_sent"]

    return updates


# ---------------------------------------------------------------------------
# EXPEDIENTE post-tool hook
# ---------------------------------------------------------------------------


async def expediente_post_tool_hook(
    tool_name: str,
    result_dict: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Post-tool hook for EXPEDIENTE_MODE and all 6 sub-modes.

    Called by post_tool_node after each tool execution.  Returns a dict of
    additional state updates to merge into pending_state_updates.

    Follows the EXACT same three-layer merge pattern as presupuesto_post_tool_hook:
      Layer 1 = state["_mode_context"] + state.get("pending_state_updates", {}).get("mode_context", {})
      Layer 2 = _extract_expediente_context(tool_name, result_dict, layer1_mc)  [wrapped in try/except]
      Layer 3 = hook-specific overrides (currently none for expediente)
    Layer 3 wins on conflict.

    IMPORTANT: This hook NEVER injects fake AIMessage objects.
    It only returns state update dicts.

    Args:
        tool_name: Name of the tool that was just executed.
        result_dict: The parsed tool result dict.
        state: Current ToolLoopState at time of hook invocation.

    Returns:
        Dict of additional state updates to merge into pending_state_updates.
        Empty dict if result_dict is not a dict.
    """
    updates: dict[str, Any] = {}

    # ── Build Layer 1: base mode_context ─────────────────────────────────
    mode_context = dict(state.get("_mode_context") or {})

    # Merge pending mode_context from accumulated state updates so the
    # three-layer merge base reflects changes from earlier tool calls
    # in the same turn.
    accumulated_mc = (state.get("pending_state_updates") or {}).get("mode_context")
    if isinstance(accumulated_mc, dict):
        mode_context.update(accumulated_mc)

    if not isinstance(result_dict, dict):
        return updates

    # ── STEP 1 (Layer 2): Structural extraction ───────────────────────────
    structural_mc: dict[str, Any] = {}
    try:
        structural_mc = _extract_expediente_context(tool_name, result_dict, mode_context)
    except Exception as exc:
        logger.warning(
            "expediente_hook_extraction_failed",
            tool_name=tool_name,
            error=str(exc),
            conversation_id=state.get("_conversation_id", "unknown"),
        )
        # structural_mc stays {} — hook continues with Layer 1 only

    # ── STEP 2 (Layer 3): Hook-specific overrides ─────────────────────────
    hook_mc_updates: dict[str, Any] = {}

    # ── Session recovery acknowledgement (T-28) ───────────────────────────
    # When a user returns to an orphaned expediente, the recovery prompt is
    # shown on the FIRST turn only. After the first tool call, we set
    # recovery_acknowledged=True so the prompt is not repeated (one-shot protocol).
    # Condition: pending_recovery_case is present AND recovery not yet acknowledged.
    if mode_context.get("pending_recovery_case") and not mode_context.get(
        "recovery_acknowledged"
    ):
        hook_mc_updates["recovery_acknowledged"] = True
        logger.info(
            "expediente_hook_recovery_acknowledged",
            tool_name=tool_name,
            conversation_id=state.get("_conversation_id", "unknown"),
        )

    # ── Image-emitting tools: capture _pending_images ────────────────────
    # Tools that deliver images to the user via Chatwoot set _pending_images
    # in their result dict. The hook captures it here so the main loop's
    # delivery pipeline can dispatch the images.
    # Top-level key (not inside mode_context) so _merge_loop_result_to_state
    # in expediente_nodes.py can bubble it up to result["pending_images"].
    #
    # enviar_imagenes_ejemplo — normal image delivery path
    # reenviar_imagenes_elemento — explicit user-triggered resend bypass
    _IMAGE_EMITTING_TOOLS = {"enviar_imagenes_ejemplo", "reenviar_imagenes_elemento"}
    if tool_name in _IMAGE_EMITTING_TOOLS and not (
        result_dict.get("error") or result_dict.get("success") is False
    ):
        pending_images = result_dict.get("_pending_images")
        if pending_images:
            updates["_pending_images"] = pending_images
            logger.info(
                "expediente_hook_pending_images_captured",
                conversation_id=state.get("_conversation_id", "unknown"),
            )

    # ── STEP 3: Three-layer merge ─────────────────────────────────────────
    merged_mc = {**mode_context, **structural_mc, **hook_mc_updates}
    updates["mode_context"] = merged_mc

    return updates
