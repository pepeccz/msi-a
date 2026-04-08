"""
MSI-a — Post-Tool Hooks for Mode-Specific State Extraction (AD-4, T-17).

Provides ``presupuesto_post_tool_hook`` and ``consulta_post_tool_hook`` for use
as ``post_tool_hook`` callbacks in ``ModeLoopConfig``.

Design principles:
- NEVER inject fake AIMessage objects (protocol corruption anti-pattern)
- Return state update dicts that post_tool_node will apply to pending_state_updates
- Reuse ``_extract_context_from_tool`` from PresupuestoModeNode (same logic, clean output)
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
# PRESUPUESTO post-tool hook
# ---------------------------------------------------------------------------


async def presupuesto_post_tool_hook(
    tool_name: str,
    result_dict: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Post-tool hook for PRESUPUESTO_MODE.

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
        from agent.modes.presupuesto_mode import PresupuestoModeNode

        tool_args = _extract_tool_args_from_messages(state, tool_name)
        current_element_codes = mode_context.get("element_codes", [])

        # _extract_context_from_tool expects result as JSON string or dict.
        result_json = (
            json.dumps(result_dict)
            if isinstance(result_dict, dict)
            else str(result_dict)
        )
        structural_mc = PresupuestoModeNode._extract_context_from_tool(
            tool_name,
            tool_args,
            result_json,
            current_element_codes,
        )
    except Exception as exc:
        logger.warning(
            "presupuesto_hook_extraction_failed",
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
                "presupuesto_hook_price_authority_confirmed",
                precio=precio,
                conversation_id=state.get("_conversation_id", "unknown"),
            )

            # tarifa_calculada in mode_context for system prompt assembly.
            # NOTE: structural_mc["tarifa_calculada"] has the full result dict.
            # hook_mc_updates wins — we add the structured version here.
            tarifa_data = {
                "precio_final": precio,
                "datos": datos,
            }
            hook_mc_updates["tarifa_calculada"] = tarifa_data
            # precio_comunicado and imagenes_enviadas come from _extract_context_from_tool
            # via _state_update in the tool result. We keep them here as hook overrides
            # to ensure they are always set even if extraction misses them.
            hook_mc_updates["precio_comunicado"] = True
            hook_mc_updates["imagenes_enviadas"] = False  # Reset for new quote

        else:
            logger.debug(
                "presupuesto_hook_tariff_failed_no_price_authority",
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
                "presupuesto_hook_variant_pending_detected",
                num_variants=len(preguntas_variantes),
                conversation_id=state.get("_conversation_id", "unknown"),
            )
        # NOTE: variant_pending bool (old dead code) NOT written here.
        # pending_variants LIST is written by structural_mc from _extract_context_from_tool.

    # ── enviar_imagenes_ejemplo ───────────────────────────────────────────
    elif tool_name == "enviar_imagenes_ejemplo":
        # Capture pending images for main.py's image delivery pipeline
        pending_images = result_dict.get("_pending_images")
        if pending_images:
            updates["_pending_images"] = pending_images
            logger.info(
                "presupuesto_hook_pending_images_captured",
                conversation_id=state.get("_conversation_id", "unknown"),
            )

        # Mark images as sent (may also come from _state_update)
        updates["imagenes_enviadas"] = True

    # ── confirmar_presupuesto ─────────────────────────────────────────────
    elif tool_name == "confirmar_presupuesto":
        # The transition signal should already be in _state_update from the tool.
        # This hook just confirms it was processed.
        if result_dict.get("success"):
            logger.info(
                "presupuesto_hook_confirm_presupuesto_success",
                conversation_id=state.get("_conversation_id", "unknown"),
            )

    # ── All other tools: no specific hook behavior ────────────────────────
    else:
        logger.debug(
            "presupuesto_hook_no_specific_behavior",
            tool_name=tool_name,
            conversation_id=state.get("_conversation_id", "unknown"),
        )

    # ── STEP 3: Three-layer merge ─────────────────────────────────────────
    # Layer 1: base mode_context (existing state snapshot)
    # Layer 2: structural_mc from _extract_context_from_tool (fills element_codes etc.)
    # Layer 3: hook_mc_updates (hook-specific overrides, WIN on conflict)
    merged_mc = {**mode_context, **structural_mc, **hook_mc_updates}
    updates["mode_context"] = merged_mc

    return updates


# ---------------------------------------------------------------------------
# CONSULTA post-tool hook (pass-through)
# ---------------------------------------------------------------------------


async def consulta_post_tool_hook(
    tool_name: str,
    result_dict: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Post-tool hook for CONSULTA_MODE.

    CONSULTA has no complex post-tool domain logic — all state updates
    flow through the standard _state_update mechanism in ToolMessages.

    This hook is a pass-through that returns an empty dict. It exists so
    that CONSULTA_MODE can explicitly declare its hook and make it clear
    the simple path was intentional.

    Args:
        tool_name: Name of the tool that was just executed.
        result_dict: The parsed tool result dict.
        state: Current ToolLoopState.

    Returns:
        Empty dict (no additional state updates needed for CONSULTA).
    """
    return {}
