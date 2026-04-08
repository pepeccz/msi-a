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
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


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

    Key behaviors:
    - calcular_tarifa_con_elementos success → price_authority_confirmed = True
    - identificar_y_resolver_elementos with variants → variant_pending signal
    - enviar_imagenes_ejemplo → _pending_images captured in state
    - confirmar_presupuesto → pending_mode_transition signal (already via _state_update)

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

    # ── calcular_tarifa_con_elementos ─────────────────────────────────────
    if tool_name == "calcular_tarifa_con_elementos":
        if success is not False:
            # Price calculation succeeded — mark price authority confirmed
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

            # Also capture tarifa_calculada in mode_context for system prompt assembly
            tarifa_data = {
                "precio_final": precio,
                "datos": datos,
            }
            # Merge into mode_context update
            existing_mc = dict(mode_context)
            existing_mc["tarifa_calculada"] = tarifa_data
            existing_mc["precio_comunicado"] = True
            existing_mc["imagenes_enviadas"] = False  # Reset for new quote
            updates["mode_context"] = existing_mc

        else:
            logger.debug(
                "presupuesto_hook_tariff_failed_no_price_authority",
                error=result_dict.get("error"),
                conversation_id=state.get("_conversation_id", "unknown"),
            )

    # ── identificar_y_resolver_elementos ─────────────────────────────────
    elif tool_name == "identificar_y_resolver_elementos":
        preguntas_variantes = result_dict.get("preguntas_variantes") or []
        elementos_con_variantes = result_dict.get("elementos_con_variantes") or []

        if preguntas_variantes or elementos_con_variantes:
            # Variants detected — signal for tool filtering and prompt context
            updates["variant_pending"] = True

            logger.info(
                "presupuesto_hook_variant_pending_detected",
                num_variants=len(preguntas_variantes),
                conversation_id=state.get("_conversation_id", "unknown"),
            )

        elif result_dict.get("elementos_listos"):
            # All elements resolved cleanly — clear any stale variant signal
            updates["variant_pending"] = False

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
