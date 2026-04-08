"""
MSI-a - PRESUPUESTO_MODE Node.

Exact pricing mode for confirmed vehicle modifications.
Handles ~25% of traffic — users who want a formal quote.

Flow:
    1. User describes what they want (or context from VIABILIDAD transition)
    2. LLM identifies elements, resolves variants
    3. LLM calculates exact price with calcular_tarifa_con_elementos
    4. LLM communicates PRICE + WARNINGS (mandatory before images)
    5. LLM offers example images (enviar_imagenes_ejemplo)
    6. LLM offers to proceed to EXPEDIENTE_MODE via confirmar_presupuesto

Recycled v1 tools:
    - identificar_y_resolver_elementos (element identification + variant detection)
    - seleccionar_variante_por_respuesta (variant resolution)
    - calcular_tarifa_con_elementos (exact tariff calculation)
    - enviar_imagenes_ejemplo (example image sending)
    - listar_categorias (category listing)
    - listar_elementos (element listing)
    - obtener_documentacion_elemento (required docs for element)
    - identificar_tipo_vehiculo (vehicle classification)

Architecture:
    Same LLM-driven loop as ViabilidadModeNode. The system prompt enforces
    the critical rule: PRICE BEFORE IMAGES.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from typing import Any, cast

import structlog
from langchain_openai import ChatOpenAI

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState, create_empty_retry_state
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import (
    format_messages_for_llm,
    set_current_state,
    clear_current_state,
)
from agent.tools.image_tools import (
    set_current_state_for_image_tools,
    clear_image_tools_state,
)
from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
from agent.modes.post_tool_hooks import presupuesto_post_tool_hook
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Minimum confidence score for variant selection to be accepted as context
VARIANT_CONFIDENCE_THRESHOLD: float = 0.7


_FIRST_TURN_GREETING_RE = (
    r"\b(hola|buenas|buenos\s+d[ií]as|buenas\s+tardes|buenas\s+noches|hey)\b"
)
_FIRST_TURN_IA_ID_RE = (
    r"(asistente\s+con\s+ia|asistente\s+con\s+inteligencia\s+artificial|"
    r"soy\s+(el\s+)?asistente\s+con\s+ia|"
    r"soy\s+(el\s+)?asistente\s+con\s+inteligencia\s+artificial)"
)


def _finalize_first_turn_intro(ai_response: Any, mode_context: dict[str, Any]) -> str:
    """Ensure first-turn legal IA intro + short greeting exactly once."""
    if not mode_context.get("_is_first_interaction"):
        return str(ai_response or "")

    response = str(ai_response or "").strip()
    if not response:
        return str(ai_response or "")

    import re

    has_greeting = bool(re.search(_FIRST_TURN_GREETING_RE, response.lower()))
    has_ia_identification = bool(re.search(_FIRST_TURN_IA_ID_RE, response.lower()))

    if has_greeting and has_ia_identification:
        return str(ai_response or "")

    intro_parts: list[str] = []
    if not has_greeting:
        intro_parts.append("¡Hola!")
    if not has_ia_identification:
        intro_parts.append("Soy el asistente con IA de MSI Automotive.")

    intro = " ".join(intro_parts).strip()
    if not intro:
        return str(ai_response or "")

    return f"{intro} {response}".strip()


def _apply_tool_flags(
    mode_context: dict,
    tool_result: dict | str,
    logger: Any,
) -> None:
    """
    Apply _internal_flags from tool result to mode_context.

    This is the NEW pattern for explicit state management:
    - Tools declare state changes in their return value
    - Mode applies those changes atomically
    - Changes are persisted via ConversationState

    BUG FIX: _execute_and_log_tool returns JSON STRING, not dict.
    This function now accepts both STRING and DICT for robustness.

    Args:
        mode_context: Current mode context (will be modified in-place)
        tool_result: Tool return value with optional _internal_flags
                     Can be STRING (JSON) or DICT
        logger: Logger instance for debugging
    """
    # BUG FIX: Parse JSON string if needed
    if isinstance(tool_result, str):
        try:
            tool_result = json.loads(tool_result)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "apply_tool_flags_invalid_json",
                error=str(e),
                result_preview=tool_result[:100] if tool_result else "",
            )
            return

    # Type guard after parsing
    if not isinstance(tool_result, dict):
        logger.warning(
            "apply_tool_flags_invalid_type",
            type=type(tool_result).__name__,
        )
        return

    # Dual-reader: prefer _state_update (new canonical key), fall back to _internal_flags
    flags = tool_result.get("_state_update") or tool_result.get("_internal_flags", {})
    if not flags:
        logger.debug(
            "apply_tool_flags_no_flags",
            conversation_id=mode_context.get("conversation_id"),
        )
        return

    logger.info(
        "applying_tool_flags",
        flags=list(flags.keys()),
        values={k: v for k, v in flags.items()},
        conversation_id=mode_context.get("conversation_id"),
    )

    # Separate transition signal from context flags
    transition_to = flags.pop("_transition_to", None)
    if transition_to:
        mode_context["_transition_to"] = transition_to
        logger.info(
            "transition_signal_received",
            target=transition_to,
            conversation_id=mode_context.get("conversation_id"),
        )

    # Apply remaining flags to mode_context
    mode_context.update(flags)


def _reset_validation_retry_state(retry_state: dict) -> dict:
    """
    Partial reset of retry_state after a successful tool call.
    Resets validation-specific counters while preserving consecutive_errors
    (which drives the outer escalation logic in BaseModeNode.process()).
    """
    return {
        **retry_state,
        "retry_count": 0,
        "last_validation_context": None,
        "last_error_type": None,
        "last_error_message": None,
    }


def _parse_tool_result(
    result: str | dict[str, Any], tool_name: str = ""
) -> dict[str, Any]:
    """
    Safely coerce a raw tool result into a dict without raising.

    ``_execute_and_log_tool()`` in BaseModeNode returns a JSON **string**.
    Downstream code that needs a dict must go through this helper so that
    plain-text error payloads (returned by failing tools) never propagate
    as uncaught ``JSONDecodeError`` at the PRESUPUESTO mode boundary.

    Args:
        result:    Raw tool output — either a JSON string or an already-parsed dict.
        tool_name: Optional tool name used for structured logging only.

    Returns:
        Parsed dict in all cases:
        - Valid JSON string  → parsed dict.
        - Plain-text string  → ``{"success": False, "error": text, "raw_message": text,
                                   "result_format": "plain_text"}``.
        - Empty string       → ``{"success": False, "error": "empty_result",
                                   "message": "No se pudo obtener respuesta del servicio",
                                   "result_format": "plain_text"}``.
        - Already a dict     → returned as-is.
        - Unexpected type    → ``{"success": False, "error": "unexpected_type"}``.
    """
    # Already a dict — nothing to do.
    if isinstance(result, dict):
        return result

    if not isinstance(result, str):
        logger.warning(
            "parse_tool_result_unexpected_type",
            tool=tool_name,
            received_type=type(result).__name__,
        )
        return {
            "success": False,
            "error": "unexpected_type",
            "result_format": "plain_text",
        }

    # Empty string guard.
    if not result.strip():
        logger.warning(
            "parse_tool_result_empty_string",
            tool=tool_name,
        )
        return {
            "success": False,
            "error": "empty_result",
            "message": "No se pudo obtener respuesta del servicio",
            "result_format": "plain_text",
        }

    # Happy path: try JSON.
    try:
        parsed = json.loads(result)
        if isinstance(parsed, dict):
            return parsed
        # JSON parsed but not a dict (e.g. a bare list or number) — treat as error.
        logger.warning(
            "parse_tool_result_non_dict_json",
            tool=tool_name,
            parsed_type=type(parsed).__name__,
        )
        return {
            "success": False,
            "error": "non_dict_json",
            "raw_message": result,
            "result_format": "plain_text",
        }
    except json.JSONDecodeError:
        logger.warning(
            "parse_tool_result_json_decode_error",
            tool=tool_name,
            result_preview=result[:120],
        )
        return {
            "success": False,
            "error": result,
            "raw_message": result,
            "result_format": "plain_text",
        }


# ---------------------------------------------------------------------------
# Variant state helpers
# ---------------------------------------------------------------------------


def _has_unresolved_variants(mode_context: dict) -> bool:
    """
    Return True when ``mode_context`` contains at least one pending variant
    whose status is not yet ``"resolved"``.

    Used to decide whether to enforce ``tool_choice="required"`` so the LLM
    cannot emit free text while a variant question is active.

    Reused at:
    - Initial LLM build (line ~481): first call to ``_get_llm``.
    - Mid-loop tool rebind (line ~901): after ``get_tools()`` changes tool set.

    Args:
        mode_context: Current mode context dict (may be ``None`` or empty).

    Returns:
        ``True`` if any variant entry has ``status != "resolved"``.
        ``False`` when the list is empty, absent, or all variants are resolved.
    """
    pending = (mode_context or {}).get("pending_variants") or []
    return any(v.get("status") != "resolved" for v in pending if isinstance(v, dict))


class PresupuestoModeNode(BaseModeNode):
    """
    PRESUPUESTO_MODE: Main pricing mode (fusionado con VIABILIDAD).

    Handles ~90% of traffic (VIABILIDAD + PRESUPUESTO combinados).
    Entry point for "Quiero homologar X" queries.

    Uses the LLM with full pricing + image tools to:
    - Identify elements from free-text descriptions
    - Resolve variant ambiguities
    - Calculate tariff IMMEDIATELY (no "estimación" step)
    - Communicate price + warnings (MANDATORY before images)
    - Offer 2 clear options:
      A) View documentation/images (then ask about opening case)
      B) Open case directly (transition to EXPEDIENTE_MODE)

    Critical rules:
    - PRICE must be communicated BEFORE sending images
    - After price, offer 2 options (not just one)
    - NO concept of "estimación" vs "precio exacto" (always exact)
    """

    # Increased from default 1500 to prevent truncation with large system prompts.
    _default_max_tokens: int = 3000

    def __init__(self) -> None:
        super().__init__("PRESUPUESTO_MODE")
        self._tools: list | None = None

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message in PRESUPUESTO_MODE.

        Routes to the new ToolNode subgraph engine if PRESUPUESTO_MODE is in
        TOOLNODE_ENABLED_MODES, otherwise uses the legacy generic_llm_loop.
        """
        settings = get_settings()
        enabled_modes = [
            m.strip() for m in settings.TOOLNODE_ENABLED_MODES.split(",") if m.strip()
        ]

        # Always use the new ToolNode engine (generic_llm_loop deleted in T-25).
        # Feature flag TOOLNODE_ENABLED_MODES no longer gates PRESUPUESTO.
        _ = enabled_modes  # noqa: F841 — kept for potential future use
        return await self._process_with_tool_loop(message, state)

    # ------------------------------------------------------------------
    # New ToolNode subgraph path (T-18)
    # ------------------------------------------------------------------

    async def _process_with_tool_loop(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process using the new build_mode_tool_loop() subgraph engine (AD-1, T-18).

        Replaces:
        - generic_loop tool callback (domain logic → presupuesto_post_tool_hook)
        - message injection anti-pattern (fake AIMessage → state updates)
        - rebind_tools (mid-loop tool switching → get_tools(mode_context) filtering)
        - _apply_tool_flags (in-place mutation → _state_update via ToolMessages)

        This path:
        1. Builds ModeLoopConfig with presupuesto-specific settings.
        2. Invokes the compiled subgraph.
        3. Merges pending_state_updates into mode_context.
        4. Propagates transition signals and pending_images to caller.
        """
        from langchain_core.messages import HumanMessage

        conversation_id = str(state.get("conversation_id", "unknown"))
        mode_context = dict(state.get("mode_context") or {})
        messages = list(state.get("messages", []))

        # Enrich mode_context with runtime flags
        mode_context["_client_type"] = state.get("client_type", "particular")
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # Load DraftQuote on resume (same as generic path)
        await _load_active_draft_quote_into_context(conversation_id, mode_context)

        # Build client context for the prompt
        client_context = self._build_client_context(state)

        # Capture mode_context snapshot for closure (variant filtering etc.)
        _mode_context_snapshot = dict(mode_context)

        def _get_tools_with_filtering(ctx: dict) -> list:
            """
            Return tool list for this turn, applying the price-gate and variant-gate.

            Price gate: if price not confirmed, exclude enviar_imagenes_ejemplo.
            Variant gate: if pending_variants exist, restrict to variant tools only.
            Re-id gate: once elements are identified (element_codes non-empty),
            block identificar_y_resolver_elementos to prevent the LLM from
            re-calling it after variant resolution, which resets state.
            (Mirrors the old rebind_tools behavior — now state-driven.)
            """
            pending = (ctx or {}).get("pending_variants") or []
            unresolved = [v for v in pending if v.get("status") != "resolved"]
            if unresolved:
                # Restrict to variant resolution tools only (same as get_tools() R4 rule)
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                from agent.tools.shared_tools import escalar_a_humano

                return [seleccionar_variante_por_respuesta, escalar_a_humano]

            tools = _get_presupuesto_tools()

            # Once identification has happened (element_codes populated), block
            # re-identification. The LLM must use seleccionar_variante_por_respuesta
            # for variant answers, not re-call identificar (anti-pattern 04).
            has_elements = bool((ctx or {}).get("element_codes"))
            if has_elements:
                from agent.tools.element_tools import identificar_y_resolver_elementos

                tools = [t for t in tools if t is not identificar_y_resolver_elementos]

            return tools

        # Build ModeLoopConfig
        config = ModeLoopConfig(
            mode_name="PRESUPUESTO_MODE",
            get_tools=_get_tools_with_filtering,
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="PRESUPUESTO_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                client_context=client_context,
            ),
            post_tool_hook=presupuesto_post_tool_hook,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=self._default_max_tokens,
        )

        # Compile the subgraph
        subgraph = build_mode_tool_loop(config)

        # Format conversation history
        llm_history = list(format_messages_for_llm(messages))

        # Build initial ToolLoopState
        initial_state = {
            "messages": llm_history
            + [HumanMessage(content=f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>")],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": "PRESUPUESTO_MODE",
        }

        # Set ContextVar for legacy tools (transition period)
        full_state = dict(state)  # type: ignore[arg-type]
        full_state["mode_context"] = mode_context
        set_current_state(full_state)
        set_current_state_for_image_tools(full_state)

        try:
            # Invoke the subgraph
            loop_result = await subgraph.ainvoke(initial_state)
        finally:
            clear_current_state()
            clear_image_tools_state()
            try:
                from agent.tools.draft_quote_service import _deactivate_draft_quote

                await _deactivate_draft_quote(conversation_id=conversation_id)
            except Exception as e:
                logger.warning("draft_quote_deactivation_failed", error=str(e))

        # Extract result fields
        ai_response = loop_result.get("ai_response", "")
        exit_reason = loop_result.get("exit_reason", "response")
        tools_called = loop_result.get("tools_called", [])
        pending_updates = dict(loop_result.get("pending_state_updates") or {})

        # Apply first-turn intro guard
        ai_response = _finalize_first_turn_intro(ai_response, mode_context)

        # Merge pending_state_updates into mode_context
        # pending_updates may contain nested mode_context key — merge carefully
        nested_mc = pending_updates.pop("mode_context", None)
        updated_context = {**mode_context, **pending_updates}
        if isinstance(nested_mc, dict):
            updated_context.update(nested_mc)

        self._logger.info(
            "presupuesto_tool_loop_response",
            exit_reason=exit_reason,
            tools_called=tools_called,
            response_length=len(ai_response),
            conversation_id=conversation_id,
        )

        result_dict: dict[str, Any] = {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

        # Propagate mode transition signal to top-level state
        # pending_mode_transition in mode_context → current_mode at root
        _transition_target = updated_context.pop("pending_mode_transition", None)
        if _transition_target:
            result_dict["current_mode"] = _transition_target
            updated_context["pending_mode_transition"] = None  # TOMBSTONE
            self._logger.info(
                "presupuesto_mode_transition_tool_loop",
                target=_transition_target,
                conversation_id=conversation_id,
            )

        # Also check _transition_to from _state_update (legacy key from tools)
        _legacy_transition = updated_context.pop("_transition_to", None)
        if _legacy_transition and "current_mode" not in result_dict:
            result_dict["current_mode"] = _legacy_transition
            updated_context["_transition_to"] = None  # TOMBSTONE

        # Propagate mode chaining signal
        _chain = updated_context.pop("_chain_next_mode", None)
        if _chain:
            result_dict["_chain_next_mode"] = True
            updated_context["_chain_next_mode"] = None  # TOMBSTONE

        # Bubble up pending images if any
        pending_images = pending_updates.get("_pending_images") or updated_context.pop(
            "_pending_images", None
        )
        if pending_images:
            result_dict["pending_images"] = pending_images

        return result_dict

    # _process_with_generic_loop removed in T-25 (generic_loop.py deleted).
    # PRESUPUESTO always uses _process_with_tool_loop now.

    def get_tools(self, mode_context: dict | None = None) -> list:
        """Return tools available in PRESUPUESTO_MODE.

        R4 — Structural tool restriction:
        When pending_variants is non-empty, restrict to variant-resolution tools only.
        This is a temporary, narrow restriction lifted immediately once all variants resolve.
        Structurally prevents re-identification while a variant question is active.
        """
        pending = (mode_context or {}).get("pending_variants") or []
        unresolved = [v for v in pending if v.get("status") != "resolved"]
        if unresolved:
            # Restrict: only variant resolution + universal escalation tool
            from agent.tools.element_tools import seleccionar_variante_por_respuesta
            from agent.tools.shared_tools import escalar_a_humano

            return [seleccionar_variante_por_respuesta, escalar_a_humano]
        # Full toolset — cache for reuse
        if self._tools is None:
            self._tools = _get_presupuesto_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers — delegated to BaseModeNode
    # ------------------------------------------------------------------
    # _get_llm() and _invoke_with_fallback() are inherited from BaseModeNode.
    # _default_max_tokens = 3000 overrides the base default (1500) so that
    # PRESUPUESTO responses are never truncated with large system prompts.

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    # _execute_tool inherited from BaseModeNode

    # ------------------------------------------------------------------
    # Context extraction from tool results
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_context_from_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
        current_element_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Extract mode context updates from a tool call and its result.

        Same logic as ViabilidadModeNode, plus:
        - Tracks precio_comunicado for price-before-images enforcement
        - Tracks presupuesto_completado when price is calculated

        Args:
            current_element_codes: Current element_codes from mode_context, used to
                accumulate codes across multiple seleccionar_variante_por_respuesta
                calls in the same turn (fixes blocked_stale_budget_scope bug).
        """
        updates: dict[str, Any] = {}

        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return updates

        if not isinstance(data, dict):
            return updates

        if tool_name == "identificar_y_resolver_elementos":
            # Skip context extraction on error results — failed tool calls
            # produce no valid context and would corrupt mode_context with
            # wrong values (e.g. categoria_slug from the failed request).
            if data.get("error"):
                return updates

            # IMPORTANT: Clear previous identification/pricing data
            # With merge_dicts reducer, we must explicitly clear obsolete fields
            # to prevent stale data from previous queries confusing the LLM
            updates["tarifa_calculada"] = None
            # REFACTOR-001: Flag resets (precio_comunicado, imagenes_enviadas)
            # now handled by _internal_flags in tool return value

            listos = data.get("elementos_listos", [])
            variantes = data.get("elementos_con_variantes", [])
            preguntas = data.get("preguntas_variantes", [])

            # Codes from elementos_listos are always valid (no variant needed)
            ready_codes = [e.get("codigo") for e in listos if e.get("codigo")]

            if listos and not variantes:
                updates["elemento_confirmado"] = listos[0] if len(listos) == 1 else None
                updates["element_codes"] = ready_codes
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["elemento_tentativo"] = None  # Clear tentative
                updates["pending_variants"] = []  # Clear variant questions
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = preguntas
                updates["elemento_confirmado"] = None  # Clear confirmed
                # Preserve ready element codes from this identification.
                # Previously this cleared element_codes entirely (RC-2a), which
                # dropped elements that had no variants (e.g. PLACA_SOLAR) when
                # other elements did have variants (e.g. TOLDO_LAT).
                updates["element_codes"] = ready_codes

            # Read from tool result first (robust), fallback to tool_args
            updates["categoria_slug"] = (
                data.get("categoria_slug")
                or tool_args.get("categoria_vehiculo")
                or tool_args.get("categoria")
            )

        elif tool_name == "seleccionar_variante_por_respuesta":
            # Detect successful selection — tool returns "selected_variant" (single)
            # or "selected_variants" (multi-select), NOT "success" or "codigo"
            has_selection = bool(
                data.get("selected_variant")
                or data.get("selected_variants")
                or data.get("success")  # forward compat
                or data.get("codigo")  # legacy compat
            )
            confidence = data.get("confidence", 1.0)
            is_confident = confidence >= VARIANT_CONFIDENCE_THRESHOLD or data.get("mode") == "multi_select"

            if has_selection and not data.get("error") and is_confident:
                # ══════════════════════════════════════════════════════════
                # FIX: Incremental pending_variants update (no premature clear)
                # If the tool returned updated pending_variants via _internal_flags,
                # use that. Otherwise, for legacy single-selection, check if all
                # entries are resolved before clearing.
                # ══════════════════════════════════════════════════════════
                from agent.state.helpers import normalize_pending_variants

                # Dual-reader: prefer _state_update (new canonical), fall back to _internal_flags
                tool_flags = data.get("_state_update") or data.get(
                    "_internal_flags", {}
                )
                tool_pending = tool_flags.get("pending_variants")

                if tool_pending is not None:
                    # Tool provided authoritative updated state — use it directly
                    normalized = normalize_pending_variants(tool_pending)
                    all_resolved = all(
                        pv.get("status") == "resolved" for pv in normalized
                    )
                    if all_resolved:
                        updates["pending_variants"] = []
                    else:
                        updates["pending_variants"] = [dict(pv) for pv in normalized]
                else:
                    # Legacy path: single variant resolved without enriched state.
                    # DO NOT blanket-clear all pending_variants — other elements
                    # may still have unresolved variants in a multi-element scenario.
                    # The modern tool always provides _internal_flags.pending_variants,
                    # so this path only fires for truly legacy callers.
                    # Leaving pending_variants UNSET here preserves the existing
                    # mode_context entries. The calcular_tarifa_con_elementos tool
                    # has its own guard that blocks calculation if unresolved
                    # variants remain.
                    pass

                # Single variant selection
                code = (
                    data.get("selected_variant")
                    or data.get("codigo")
                    or data.get("code")
                )
                if code:
                    updates["elemento_confirmado"] = {
                        "code": code,
                        "name": data.get("name") or data.get("nombre", code),
                    }
                    # FIX: Accumulate codes across multiple seleccionar_variante calls
                    # in the same turn. Previously `= [code]` would overwrite the list
                    # on each call, leaving only the last resolved variant in
                    # mode_context["element_codes"]. This caused the guardrail in
                    # enviar_imagenes_ejemplo to fire (blocked_stale_budget_scope)
                    # because mode_context had 1 code but tarifa_calculada had 2+.
                    existing = list(current_element_codes or [])
                    if code not in existing:
                        existing.append(code)
                    updates["element_codes"] = existing

                # Multi-select variant selection
                elif data.get("selected_variants"):
                    codes = data["selected_variants"]
                    updates["element_codes"] = codes
                    names = data.get("names", codes)
                    updates["elemento_confirmado"] = {
                        "code": codes[0],
                        "name": names[0] if names else codes[0],
                    }
            # If "error" in response, do NOT clear pending_variants — keep blocking calcular_tarifa

        elif tool_name == "calcular_tarifa_con_elementos":
            # Skip context extraction on error — don't store error dicts as tarifa
            if data.get("error") or data.get("success") is False:
                return updates

            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            # REFACTOR-001: Removed precio_calculado redundant field - use tarifa_calculada directly
            updates["tarifa_calculada"] = (
                data  # Store full response including imagenes_ejemplo
            )
            # NOTE: precio_comunicado and imagenes_enviadas flags are managed
            # in _process_message to avoid accessing mode_context in static method
            # NOTE: NO longer propagate to root state (_tarifa_actual removed)
            # Tools access tarifa_calculada directly from mode_context

            # RC-2b: Sync element_codes from tarifa result (authoritative source).
            # Only applied on success and when datos.element_codes is non-empty.
            if data.get("success") is not False:
                _datos = data.get("datos", {})
                if isinstance(_datos, dict):
                    _tarifa_codes = _datos.get("element_codes", [])
                    if _tarifa_codes:
                        updates["element_codes"] = _tarifa_codes
                        logger.debug(
                            "element_codes_synced_from_tarifa",
                            count=len(_tarifa_codes),
                            codes=_tarifa_codes,
                        )

            # ── Populate elementos_confirmados for rich variant handoff to EXPEDIENTE ──
            # Build a list of {code, name, variant_of} from the tariff response.
            # This data survives the PRESUPUESTO → EXPEDIENTE transition via
            # CONTEXT_PRESERVE_RULES so EXPEDIENTE knows exactly which elements
            # (including variant detail) were priced.
            if data.get("success") is not False:
                elementos: list[dict[str, Any]] = []
                datos = data.get("datos", {})
                if isinstance(datos, dict):
                    element_names = datos.get("elements", [])
                    element_codes = datos.get("element_codes", [])
                    # Zip codes and names together for rich entries
                    for idx, code in enumerate(element_codes):
                        name = element_names[idx] if idx < len(element_names) else code
                        elementos.append(
                            {
                                "code": code,
                                "name": name,
                                "variant_of": None,  # Not available in tariff response
                            }
                        )

                # Fallback: derive from element_codes if datos lacked detail
                if not elementos:
                    codes = (
                        datos.get("element_codes", [])
                        if isinstance(datos, dict)
                        else []
                    ) or data.get("element_codes", [])
                    if not codes:
                        # Last resort: try from mode_context via current_element_codes
                        codes = current_element_codes or []
                    elementos = [
                        {"code": c, "name": c, "variant_of": None} for c in codes
                    ]

                if elementos:
                    updates["elementos_confirmados"] = elementos
                    logger.info(
                        "elementos_confirmados_populated",
                        count=len(elementos),
                        codes=[e["code"] for e in elementos],
                    )

        elif tool_name == "identificar_tipo_vehiculo":
            # Skip context extraction on error
            if data.get("error"):
                return updates

            categoria = data.get("categoria_sugerida") or data.get("category_slug")
            if categoria:
                updates["categoria_slug"] = categoria
            marca = data.get("marca")
            modelo = data.get("modelo")
            if marca or modelo:
                updates["vehiculo"] = {
                    "marca": marca or "desconocida",
                    "modelo": modelo or "desconocido",
                }

        elif tool_name == "enviar_imagenes_ejemplo":
            pass  # Flag managed by _internal_flags (REFACTOR-001)

        return updates

    @staticmethod
    def _extract_pending_images(result: str) -> dict[str, Any] | None:
        """
        Extract pending images payload from enviar_imagenes_ejemplo result.

        The tool returns _pending_images in its result dict which contains
        the actual image URLs to send via Chatwoot.
        """
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        return data.get("_pending_images")

    # ------------------------------------------------------------------
    # Client context builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_client_context(state: ConversationState) -> str:
        """Build the client-specific context string for the prompt."""
        parts: list[str] = []

        client_type = state.get("client_type", "particular")
        type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        parts.append(f"Cliente: **{type_display}**")
        parts.append(f'Usa tipo_cliente: "{client_type}" en herramientas.')

        user_name = state.get("user_name")
        if user_name:
            parts.append(f"Nombre: {user_name}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Message conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ai_message_to_dict(response: Any) -> dict[str, Any]:
        """Convert an LLM AIMessage to a dict for the messages list."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if hasattr(response, "tool_calls") and response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                }
                for tc in response.tool_calls
            ]
        return msg

    @staticmethod
    def _log_token_usage(response: Any, conversation_id: str) -> None:
        """Log token usage from LLM response metadata."""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.debug(
                "llm_token_usage",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                conversation_id=conversation_id,
            )


# ---------------------------------------------------------------------------
# Tool registry for PRESUPUESTO_MODE
# ---------------------------------------------------------------------------


def _get_presupuesto_tools() -> list:
    """
    Get the tool set for PRESUPUESTO_MODE.

    Full element identification + pricing + image tools + confirmar_presupuesto.
    This is the most tool-rich mode (besides EXPEDIENTE).
    """
    from agent.tools.element_tools import (
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        calcular_tarifa_con_elementos,
        listar_elementos,
        obtener_documentacion_elemento,
    )
    from agent.tools.tarifa_tools import listar_categorias
    from agent.tools.vehicle_tools import identificar_tipo_vehiculo
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.transition_tools import confirmar_presupuesto
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element identification & resolution
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        # Exact pricing
        calcular_tarifa_con_elementos,
        # Example images (after price communication)
        enviar_imagenes_ejemplo,
        # Transition to EXPEDIENTE_MODE (confirm quote → open case)
        confirmar_presupuesto,
        # Catalog browsing
        listar_categorias,
        listar_elementos,
        # Documentation info
        obtener_documentacion_elemento,
        # Vehicle classification
        identificar_tipo_vehiculo,
        # Universal
        escalar_a_humano,
    ]


# ---------------------------------------------------------------------------
# T3.2: Module-level DraftQuote helpers (Phase 3)
#
# These are module-level functions (not class methods) so they can be
# patched in tests without instantiating PresupuestoModeNode.
# ---------------------------------------------------------------------------


async def _load_active_draft_quote(conversation_id: str):
    """
    Load the active DraftQuote for a conversation from the database.

    Module-level so it can be easily mocked in tests.

    Returns:
        DraftQuote ORM instance, or None if not found.
    """
    from agent.tools.draft_quote_service import (
        _load_active_draft_quote as _svc_load,
    )

    return await _svc_load(conversation_id)


async def _load_active_draft_quote_into_context(
    conversation_id: str,
    mode_context: dict,
) -> None:
    """
    Load the active DraftQuote and inject draft_* keys into mode_context.

    Called at the start of PRESUPUESTO_MODE processing so the LLM can
    answer "¿cuánto era el presupuesto?" without recalculating.

    If no DraftQuote is found, mode_context is NOT modified.
    Errors are caught silently — never block the agent.

    Args:
        conversation_id: Conversation UUID as string.
        mode_context: Mode context dict (mutated in-place if draft found).
    """
    try:
        draft = await _load_active_draft_quote(conversation_id)
        if draft:
            mode_context["draft_precio"] = str(draft.precio_final)
            mode_context["draft_elements"] = draft.elements
            mode_context["draft_category"] = draft.category_slug
    except Exception as exc:
        logger.warning(
            "draft_quote_load_into_context_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
