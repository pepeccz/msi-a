"""
MSI-a - PRE_EXPEDIENTE_MODE Node.

Merged mode: handles informational queries AND exact pricing.
Covers ~100% of pre-expediente traffic (formerly CONSULTA_MODE + PRESUPUESTO_MODE).

Flow:
    Discovery phase (no element_codes yet):
    1. User asks for info or describes what they want to homologate
    2. LLM can answer informational queries (listar_categorias, obtener_documentacion_elemento, etc.)
    3. LLM identifies elements, resolves variants
    4. Transitions to pricing phase automatically (element_codes now populated)

    Pricing phase (element_codes populated, price not yet communicated):
    5. LLM calculates exact price with calcular_tarifa_con_elementos
    6. LLM communicates PRICE + WARNINGS (mandatory before images)

    Post-price phase (precio_comunicado=True):
    7. LLM offers example images (enviar_imagenes_ejemplo)
    8. LLM offers to proceed to EXPEDIENTE_MODE via confirmar_presupuesto

Available tools (10-tool superset):
    - identificar_y_resolver_elementos (element identification + variant detection)
    - seleccionar_variante_por_respuesta (variant resolution)
    - calcular_tarifa_con_elementos (exact tariff calculation)
    - enviar_imagenes_ejemplo (example image sending — gated by tarifa_calculada)
    - confirmar_presupuesto (transition to EXPEDIENTE_MODE — gated by price)
    - listar_categorias (category listing)
    - listar_elementos (element listing)
    - obtener_servicios_adicionales (additional services info)
    - identificar_tipo_vehiculo (vehicle classification)
    - escalar_a_humano (universal escalation)
    NOTE: obtener_documentacion_elemento removed — doc info is now embedded in
          identificar_y_resolver_elementos response (documentacion key, Batch 2)

Dynamic tool filtering (4 gates, Gate 2 removed):
    Gate 1 (variant): unresolved pending_variants → [seleccionar, escalar] only
    Gate 5 (images): tarifa_calculada absent or has no imagenes_ejemplo → remove enviar_imagenes_ejemplo
    Gate 3 (confirmar): NOT (precio_comunicado=True AND tarifa_calculada non-None dict) → remove confirmar_presupuesto
    Gate 4 (calcular): element_codes empty → remove calcular_tarifa_con_elementos
    NOTE: Gate 2 (re-id) removed — additive identification is now supported

Architecture:
    Same LLM-driven loop as PresupuestoModeNode. The system prompt enforces
    the critical rule: PRICE BEFORE IMAGES.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from typing import Any, cast

import structlog
from langchain_openai import ChatOpenAI

from langgraph.types import Command

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState, create_empty_retry_state, transition_mode
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import (
    format_messages_for_llm,
)
from agent.tools.image_tools import (
    clear_image_tools_state,
)
from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook
from agent.prompts.kickoff_markers import is_kickoff_hallucination
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Minimum confidence score for variant selection to be accepted as context
VARIANT_CONFIDENCE_THRESHOLD: float = 0.7

# Canonical CTA 5 text (post-images call-to-action).
# Defined here as a constant so the enforcement function and tests share the same source of truth.
_CTA_5 = "¿Abrimos expediente o tienes alguna duda?"

# Semantic-equivalence matcher for CTA 5 — tolerates voseo/tuteo drift ("tenés"/"tienes")
# and trailing whitespace. Anchored to end-of-string so it only matches when the CTA
# already closes the response. Prevents duplicate-CTA emission when the LLM drifts
# to tuteo (e.g. "¿Abrimos expediente o tienes alguna duda?") instead of the canonical voseo.
_CTA_5_EQUIVALENT_RE = re.compile(
    r"¿\s*Abrimos\s+expediente\s+o\s+(?:tenés|tienes)\s+alguna\s+duda\s*\?\s*$",
    re.IGNORECASE,
)


def _should_force_tool_choice(mc: dict) -> str | None:
    """Return "required" iff all 4 POST_PRICE + CTA-5 conditions hold; else None.

    This lambda is wired into ModeLoopConfig.get_tool_choice so that, on the
    turn immediately after CTA 5 is emitted, the cloud LLM is forced to call a
    tool instead of responding with free text.

    Conditions (ALL must be True):
        1. precio_comunicado is True
        2. tarifa_calculada is a non-None, non-empty value
        3. imagenes_enviadas_codigos is a non-empty list
        4. mode_context["last_cta_emitted"] == "cta_5"

    Design: D2 in design artifact. Mirrors the 4 equivalent-proof conditions
    for POST_PRICE + CTA-5 without reading a phase enum.

    Args:
        mc: Current mode_context dict.

    Returns:
        "required" if all 4 conditions hold; None otherwise.
    """
    if (
        mc.get("precio_comunicado") is True
        and bool(mc.get("tarifa_calculada"))
        and bool(mc.get("imagenes_enviadas_codigos"))
        and mc.get("last_cta_emitted") == "cta_5"
    ):
        logger.info(
            "tool_choice_forced_required",
            precio_comunicado=True,
            tarifa_calculada_present=True,
            imagenes_count=len(mc.get("imagenes_enviadas_codigos") or []),
            last_cta_emitted="cta_5",
        )
        return "required"
    return None


def _enforce_cta5_if_needed(
    ai_response: str,
    precio_comunicado: bool,
    imagenes_enviadas_codigos: list | None,
) -> str:
    """Deterministic CTA 5 enforcement — escenario 7.bis / regla 9.

    Post-tool-loop hook called before returning the turn's ai_response.
    Guarantees that, when both preconditions are met, the response ends with
    the canonical CTA 5 literal.

    Preconditions (BOTH must be true to activate enforcement):
        - precio_comunicado is True
        - imagenes_enviadas_codigos is a non-empty list

    Behaviour:
        - LLM text is empty or whitespace only → emit CTA 5 as sole content.
        - LLM text already ends with canonical CTA 5 → passthrough (no-op).
        - LLM text ends with a semantically equivalent CTA (e.g. tuteo variant
          "¿Abrimos expediente o tienes alguna duda?") → NORMALIZE the tail to
          the canonical voseo form without duplicating. This prevents the
          double-CTA emission seen when the LLM drifts to tuteo.
        - LLM text present without any CTA variant → append canonical CTA 5.
        - Preconditions not met → return ai_response unchanged.

    Args:
        ai_response: Raw text produced by the LLM this turn.
        precio_comunicado: Whether the price was communicated to the client.
        imagenes_enviadas_codigos: Codes of images sent so far (non-empty = images were sent).

    Returns:
        The (possibly modified) response string.
    """
    # Guard: preconditions
    if not precio_comunicado or not imagenes_enviadas_codigos:
        return ai_response

    stripped = ai_response.strip()

    # Case 3: empty / whitespace only → CTA 5 as sole content
    if not stripped:
        return _CTA_5

    # Case 2a: already ends with canonical CTA 5 → no-op
    if stripped.endswith(_CTA_5):
        return ai_response

    # Case 2b: ends with a semantically equivalent CTA (tuteo drift, spacing, casing) →
    # replace the matched tail with the canonical CTA. Preserves any leading content.
    match = _CTA_5_EQUIVALENT_RE.search(stripped)
    if match:
        prefix = stripped[: match.start()].rstrip()
        if prefix:
            return f"{prefix}\n\n{_CTA_5}"
        return _CTA_5

    # Case 1: useful text without any CTA variant → append with newline separator
    return f"{stripped}\n\n{_CTA_5}"


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
    as uncaught ``JSONDecodeError`` at the PRE_EXPEDIENTE mode boundary.

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


class PreExpedienteModeNode(BaseModeNode):
    """
    PRE_EXPEDIENTE_MODE: Merged informational + pricing mode.

    Covers ~100% of pre-expediente traffic (formerly CONSULTA_MODE + PRESUPUESTO_MODE).
    Entry point for both informational queries and pricing requests.

    Uses the LLM with the full 11-tool superset to:
    - Answer informational queries (catalog, documentation, vehicle classification)
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
    - identifies_disclosure: EU AI Act (first interaction disclosure) handled here
    """

    # Increased from default 1500 to prevent truncation with large system prompts.
    _default_max_tokens: int = 3000

    def __init__(self) -> None:
        super().__init__("PRE_EXPEDIENTE_MODE")
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
        Process a user message in PRE_EXPEDIENTE_MODE.

        Always uses the ToolNode subgraph engine (generic_llm_loop deleted in T-25).
        """
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
        - generic_loop tool callback (domain logic → pre_expediente_post_tool_hook)
        - message injection anti-pattern (fake AIMessage → state updates)
        - rebind_tools (mid-loop tool switching → get_tools(mode_context) filtering)
        - _apply_tool_flags (in-place mutation → _state_update via ToolMessages)

        This path:
        1. Builds ModeLoopConfig with pre_expediente-specific settings.
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

        # Load DraftQuote on resume (same as presupuesto path)
        await _load_active_draft_quote_into_context(conversation_id, mode_context)

        # Build client context for the prompt
        client_context = self._build_client_context(state)

        # Capture mode_context snapshot for closure (variant filtering etc.)
        _mode_context_snapshot = dict(mode_context)

        def _get_tools_with_filtering(ctx: dict) -> list:
            """
            Return tool list for this turn, applying the 4-gate priority system.

            Priority-ordered gate system for PRE_EXPEDIENTE_MODE:

            Gate 1 (highest priority): Variant gate
                When unresolved variants exist, ONLY variant tools are available.
                This prevents the LLM from calling any other tool while a
                variant question is pending.

            Gate 5: enviar_imagenes_ejemplo requires calculated tariff with images
                Only available when tarifa_calculada is a non-empty dict with imagenes_ejemplo.
                Prevents the LLM from calling enviar_imagenes before a tariff is calculated.

            Gate 3: confirmar_presupuesto availability
                Only available when price has been communicated AND tariff exists.
                Defense-in-depth: the tool itself has a code-level guard too.

            Gate 4: calcular_tarifa_con_elementos efficiency
                Excluded when no elements identified (would fail gracefully anyway).

            NOTE: Gate 2 (re-identification prevention) was removed to support
                additive identification (adding elements to an existing quote).
            """
            # ── GATE 1 (highest priority): Variant gate ──
            pending = (ctx or {}).get("pending_variants") or []
            unresolved = [v for v in pending if v.get("status") != "resolved"]
            if unresolved:
                # Restrict to variant resolution tools only
                from agent.tools.element_tools import seleccionar_variante_por_respuesta
                from agent.tools.shared_tools import escalar_a_humano

                return [seleccionar_variante_por_respuesta, escalar_a_humano]

            # ── No variant gate: build full tool set ──
            tools = list(_get_pre_expediente_tools())  # all 11 tools

            # ── GATE 5: enviar_imagenes_ejemplo requires calculated tariff with images ──
            # Only available when tarifa_calculada is a non-empty dict with imagenes_ejemplo.
            # Prevents the LLM from calling enviar_imagenes before a tariff is calculated.
            tarifa_calculada = (ctx or {}).get("tarifa_calculada")
            has_tarifa_with_images = (
                isinstance(tarifa_calculada, dict)
                and bool(tarifa_calculada)
                and bool(tarifa_calculada.get("imagenes_ejemplo"))
            )
            if not has_tarifa_with_images:
                from agent.tools.image_tools import enviar_imagenes_ejemplo
                tools = [t for t in tools if t is not enviar_imagenes_ejemplo]

            # ── GATE 3: confirmar_presupuesto availability ──
            # Only available when price has been communicated AND tariff exists.
            # Defense-in-depth: the tool itself has a code-level guard too.
            precio_comunicado = bool((ctx or {}).get("precio_comunicado"))
            has_tarifa = isinstance(tarifa_calculada, dict) and bool(tarifa_calculada)
            has_elements = bool((ctx or {}).get("element_codes"))

            if not (precio_comunicado and has_tarifa):
                from agent.tools.transition_tools import confirmar_presupuesto
                tools = [t for t in tools if t is not confirmar_presupuesto]

            # ── GATE 4: calcular_tarifa_con_elementos efficiency ──
            # Excluded when no elements identified (would fail anyway, saves tokens).
            if not has_elements:
                from agent.tools.element_tools import calcular_tarifa_con_elementos
                tools = [t for t in tools if t is not calcular_tarifa_con_elementos]

            return tools

        # Build ModeLoopConfig
        config = ModeLoopConfig(
            mode_name="PRE_EXPEDIENTE_MODE",
            get_tools=_get_tools_with_filtering,
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="PRE_EXPEDIENTE_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                client_context=client_context,
            ),
            post_tool_hook=pre_expediente_post_tool_hook,
            max_iterations=MAX_TOOL_ITERATIONS,
            max_tokens=self._default_max_tokens,
            get_tool_choice=lambda mc: _should_force_tool_choice(mc),
        )

        # Compile the subgraph
        loop_result_obj = build_mode_tool_loop(config)

        # Format conversation history
        llm_history = list(format_messages_for_llm(
            messages,
            conversation_summary=state.get("conversation_summary"),
        ))

        # Build initial ToolLoopState
        initial_state = {
            "messages": llm_history
            + [HumanMessage(content=f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>")],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": "PRE_EXPEDIENTE_MODE",
        }

        try:
            # Invoke the subgraph — pass recursion_limit so LangGraph enforces it
            loop_result = await loop_result_obj.graph.ainvoke(
                initial_state,
                config={"recursion_limit": loop_result_obj.recursion_limit},
            )
        finally:
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

        # Merge pending_state_updates into mode_context
        # pending_updates may contain nested mode_context key — merge carefully
        # shared_context is cross-mode: extract BEFORE merging into mode_context
        shared_context_update = pending_updates.pop("shared_context", None)
        nested_mc = pending_updates.pop("mode_context", None)
        updated_context = {**mode_context, **pending_updates}
        if isinstance(nested_mc, dict):
            updated_context.update(nested_mc)

        self._logger.info(
            "pre_expediente_tool_loop_response",
            exit_reason=exit_reason,
            tools_called=tools_called,
            response_length=len(ai_response),
            conversation_id=conversation_id,
        )

        result_dict: dict[str, Any] = {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

        # Propagate shared_context update to top-level (cross-mode, merge_dicts handles it)
        if shared_context_update and isinstance(shared_context_update, dict):
            result_dict["shared_context"] = shared_context_update

        # Propagate mode transition signal to top-level state
        # pending_mode_transition in mode_context → current_mode at root
        _transition_target = updated_context.pop("pending_mode_transition", None)
        if _transition_target:
            result_dict["current_mode"] = _transition_target
            updated_context["pending_mode_transition"] = None  # TOMBSTONE
            self._logger.info(
                "pre_expediente_mode_transition_tool_loop",
                target=_transition_target,
                conversation_id=conversation_id,
            )

        # Also check _transition_to from _state_update (legacy key from tools)
        _legacy_transition = updated_context.pop("_transition_to", None)
        if _legacy_transition and "current_mode" not in result_dict:
            result_dict["current_mode"] = _legacy_transition
            updated_context["_transition_to"] = None  # TOMBSTONE

        # Bubble up pending images if any
        pending_images = pending_updates.get("_pending_images") or updated_context.pop(
            "_pending_images", None
        )
        if pending_images:
            result_dict["pending_images"] = pending_images

        # ── CAPA 3: Hallucinated-transition self-heal ─────────────────────────
        # Invariant: this block runs AFTER _transition_to propagation (lines above)
        # and BEFORE the CTA 5 gate (below). The CTA gate reads
        # result_dict.get("current_mode") to decide whether to skip enforcement;
        # therefore this block MUST write result_dict["current_mode"] BEFORE the gate.
        #
        # When the LLM emits a kickoff declaration WITHOUT calling confirmar_presupuesto,
        # the mode stays stuck in PRE_EXPEDIENTE. This block detects that condition and
        # applies the same synthetic _state_update that confirmar_presupuesto would have
        # returned, routing through result_dict["current_mode"] (canonical post-propagation
        # channel) and updated_context (mode_context fields).
        #
        # Preconditions (all must be True to fire):
        #   1. No real transition already in result_dict (current_mode falsy)
        #   2. confirmar_presupuesto NOT in tools_called this turn
        #   3. ai_response matches KICKOFF_MARKER_RE (EOS-anchored, last 200 chars)
        #   4. precio_comunicado=True in updated_context
        #   5. tarifa_calculada non-empty in updated_context
        #
        # If markers are present but preconditions 4-5 fail (price not communicated yet),
        # a diagnostic WARNING is emitted without mutating state.
        _has_real_transition = bool(result_dict.get("current_mode"))
        _tool_was_called = "confirmar_presupuesto" in tools_called
        _has_kickoff_marker = is_kickoff_hallucination(ai_response)

        if not _has_real_transition and not _tool_was_called and _has_kickoff_marker:
            _precio_ok = bool(updated_context.get("precio_comunicado"))
            _tarifa_ok = bool(updated_context.get("tarifa_calculada"))

            if _precio_ok and _tarifa_ok:
                # Fire: apply synthetic transition equivalent to confirmar_presupuesto return
                self._logger.warning(
                    "pre_expediente_hallucinated_kickoff_self_heal",
                    conversation_id=conversation_id,
                    tools_called=tools_called,
                    ai_response_tail=ai_response[-120:],
                )
                result_dict["current_mode"] = "EXPEDIENTE_MODE"
                updated_context["expediente_kickoff_pending"] = True
                sc = result_dict.get("shared_context") or {}
                sc["warnings_acknowledged"] = True
                result_dict["shared_context"] = sc
            else:
                # Marker detected but preconditions not satisfied — diagnostic only
                self._logger.warning(
                    "pre_expediente_hallucinated_kickoff_self_heal_preconditions_not_met",
                    conversation_id=conversation_id,
                    tools_called=tools_called,
                    reason="self_heal_preconditions_not_met",
                    precio_comunicado=updated_context.get("precio_comunicado"),
                    tarifa_present=bool(updated_context.get("tarifa_calculada")),
                    ai_response_tail=ai_response[-120:],
                )
        # ── end Capa 3 ────────────────────────────────────────────────────────

        # Mark precio_comunicado=True AFTER the LLM generates its response,
        # but ONLY if calcular_tarifa was called THIS turn. The tariff tool
        # no longer sets this flag — it only populates tarifa_calculada.
        # We check tools_called to avoid false positives when the LLM
        # answers a random question with a stale tarifa in context.
        _tarifa_called_this_turn = "calcular_tarifa_con_elementos" in tools_called
        if (
            _tarifa_called_this_turn
            and updated_context.get("tarifa_calculada")
            and not updated_context.get("precio_comunicado")
        ):
            updated_context["precio_comunicado"] = True
            sc = result_dict.get("shared_context") or {}
            sc["precio_comunicado"] = True
            result_dict["shared_context"] = sc

        # ── last_cta_emitted lifecycle (D3, D4) ─────────────────────────────
        # Per-turn flag: ALWAYS reset to None before the CTA 5 gate so the flag
        # persists for exactly ONE turn (ADR-010 tombstone pattern, D4).
        # The gate below then overwrites to "cta_5" only when it actually fires.
        updated_context["last_cta_emitted"] = None

        # Enforce CTA 5 deterministically — escenario 7.bis / regla 9.
        # When precio_comunicado=True AND imagenes_enviadas_codigos is non-empty,
        # guarantee the response ends with the canonical CTA 5 literal.
        # _enforce_cta5_if_needed is a pure function: it appends if missing,
        # is a no-op if already present, and emits CTA 5 alone for empty responses.
        # Read price flag from updated_context (may have been set just above).
        #
        # CTA 5 gate (Capa 2 — Layer 2): skip enforcement when this turn already
        # emits a mode transition (result_dict["current_mode"] is truthy). Asking
        # "¿Abrimos expediente?" right before entering EXPEDIENTE_MODE or ESCALATION
        # contradicts the handoff and confuses the user.
        if not result_dict.get("current_mode"):
            result_dict["ai_response"] = _enforce_cta5_if_needed(
                ai_response=result_dict["ai_response"],
                precio_comunicado=bool(updated_context.get("precio_comunicado")),
                imagenes_enviadas_codigos=updated_context.get("imagenes_enviadas_codigos") or [],
            )
            # Set flag IFF the gate actually appended (or confirmed) CTA 5 in the response.
            if result_dict["ai_response"].endswith(_CTA_5):
                updated_context["last_cta_emitted"] = "cta_5"

        return result_dict

    def get_tools(self, mode_context: dict | None = None) -> list:
        """Return tools available in PRE_EXPEDIENTE_MODE.

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
            self._tools = _get_pre_expediente_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers — delegated to BaseModeNode
    # ------------------------------------------------------------------
    # _get_llm() and _invoke_with_fallback() are inherited from BaseModeNode.
    # _default_max_tokens = 3000 overrides the base default (1500) so that
    # PRE_EXPEDIENTE responses are never truncated with large system prompts.

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

        Same logic as PresupuestoModeNode, plus:
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
                # T-09: Additive merge — re-identification extends codes, doesn't replace
                existing_codes = set(current_element_codes or [])
                updates["element_codes"] = list(existing_codes | set(ready_codes))
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["elemento_tentativo"] = None  # Clear tentative
                updates["pending_variants"] = []  # Clear variant questions
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = preguntas
                updates["elemento_confirmado"] = None  # Clear confirmed
                # T-09: Additive merge for partial codes (elements without variants)
                # Previously this cleared element_codes entirely (RC-2a), which
                # dropped elements that had no variants (e.g. PLACA_SOLAR) when
                # other elements did have variants (e.g. TOLDO_LAT).
                existing_codes = set(current_element_codes or [])
                updates["element_codes"] = list(existing_codes | set(ready_codes))

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
            # This data survives the PRE_EXPEDIENTE → EXPEDIENTE transition via
            # shared_context (WS4) so EXPEDIENTE knows exactly which elements
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
# Tool registry for PRE_EXPEDIENTE_MODE
# ---------------------------------------------------------------------------


def _get_pre_expediente_tools() -> list:
    """
    Get the 10-tool superset for PRE_EXPEDIENTE_MODE.

    Merges tools from former CONSULTA_MODE and PRESUPUESTO_MODE:
    - All element identification + pricing + image tools from PRESUPUESTO
    - obtener_servicios_adicionales from CONSULTA (informational)

    Dynamic filtering in _get_tools_with_filtering() further restricts
    the active set based on conversation phase (gates 1, 3, 4, 5).
    NOTE: obtener_documentacion_elemento removed (T-04). Doc info is now
    embedded in identificar_y_resolver_elementos response (Batch 2, T-05).
    """
    from agent.tools.element_tools import (
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        calcular_tarifa_con_elementos,
        listar_elementos,
    )
    from agent.tools.tarifa_tools import listar_categorias, obtener_servicios_adicionales
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
        # Additional services (from CONSULTA_MODE)
        obtener_servicios_adicionales,
        # Vehicle classification
        identificar_tipo_vehiculo,
        # Universal
        escalar_a_humano,
    ]


# ---------------------------------------------------------------------------
# T3.2: Module-level DraftQuote helpers (Phase 3)
#
# These are module-level functions (not class methods) so they can be
# patched in tests without instantiating PreExpedienteModeNode.
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

    Called at the start of PRE_EXPEDIENTE_MODE processing so the LLM can
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
