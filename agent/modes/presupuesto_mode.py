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
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10


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

    flags = tool_result.get("_internal_flags", {})
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
# A/B routing safety net (Task 3.1 — _AB_PATTERNS)
# ---------------------------------------------------------------------------
# Compiled regex patterns mirroring the intent_router's VER_IMAGENES and
# ABRIR_EXPEDIENTE patterns.  Used by _check_ab_intent_mismatch() to detect
# when the LLM selected the wrong A/B tool relative to the user's message.
# Binary match: any pattern match → confidence 1.0 (always ≥ 0.85 threshold).

_AB_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    # Option A — user wants to see example images
    "enviar_imagenes_ejemplo": [
        # Ultra-short "A" / "Opción A"
        re.compile(r"^\s*([Aa]|opci[oó]n\s*[Aa]|la\s*[Aa])\s*[.!?]?\s*$", re.I),
        # Natural language: "ver/mostrar/enviar las fotos/imágenes/ejemplos"
        re.compile(
            r"\b(ver|mostrar|enviar|quiero|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b",
            re.I,
        ),
        # Imperative with pronouns: "muéstrame/envíame las fotos"
        re.compile(
            r"\b(s[ií],?\s*)?(mostr[aá]|env[ií]a|manda)\s+(las\s+)?(fotos?|im[aá]genes?)\b",
            re.I,
        ),
        # Enclitics: "mostrame/enviame/dame las fotos"
        re.compile(
            r"\b(mostr[aá]me|env[ií]ame|mandame|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b",
            re.I,
        ),
    ],
    # Option B — user wants to open an expediente directly
    "confirmar_presupuesto": [
        # Ultra-short "B" / "Opción B"
        re.compile(r"^\s*([Bb]|opci[oó]n\s*[Bb]|la\s*[Bb])\s*[.!?]?\s*$", re.I),
        # Natural language: "abrir/empezar/iniciar expediente/trámite/caso"
        re.compile(r"\b(iniciar|empezar|abrir)\s*(expediente|caso|tr[aá]mite)\b", re.I),
    ],
}


def _check_ab_intent_mismatch(
    tool_name: str,
    user_message: str,
    mode_context: dict[str, Any],
) -> str | None:
    """
    Detect A/B routing mismatch after price has been communicated.

    Guards:
    1. precio_comunicado must be True (A/B choice only relevant post-price).
    2. tool_name must be one of the two A/B tools.
    3. _ab_safety_fired must be False (max 1 intervention per _process_message() call).

    Logic:
    - Checks whether the user message matches patterns for the *other* tool.
    - Binary confidence: any regex match → confidence 1.0 (≥ 0.85 threshold).

    Returns:
        A structured "[VERIFICACIÓN INTERNA]" string if mismatch detected,
        or None if no mismatch (or guards not satisfied).
    """
    # Guard 1: Only fire post-price
    if not mode_context.get("precio_comunicado"):
        return None

    # Guard 2: Only fire for the two A/B tools
    if tool_name not in ("enviar_imagenes_ejemplo", "confirmar_presupuesto"):
        return None

    # Guard 3: Only one intervention per turn
    if mode_context.get("_ab_safety_fired", False):
        return None

    # Determine the opposite tool and its patterns
    if tool_name == "enviar_imagenes_ejemplo":
        opposite_tool = "confirmar_presupuesto"
    else:
        opposite_tool = "enviar_imagenes_ejemplo"

    opposite_patterns = _AB_PATTERNS.get(opposite_tool, [])

    # Check if any pattern for the *opposite* tool matches the user message
    matched = any(p.search(user_message) for p in opposite_patterns)
    if not matched:
        return None

    # Map tool names to human-readable intent labels for the reconsider message
    _intent_labels = {
        "enviar_imagenes_ejemplo": "ver fotos de ejemplo (Opción A)",
        "confirmar_presupuesto": "abrir expediente (Opción B)",
    }

    detected_intent = _intent_labels.get(opposite_tool, opposite_tool)
    correct_tool = opposite_tool

    reconsider_msg = (
        f"[VERIFICACIÓN INTERNA]: El mensaje del cliente sugiere que eligió la opción "
        f"contraria a la herramienta que seleccionaste.\n"
        f"- Herramienta seleccionada: {tool_name}\n"
        f"- Intent detectado: {detected_intent}\n"
        f"Reconsidera tu elección. ¿Llamar a {correct_tool} en su lugar?"
    )
    return reconsider_msg


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

        Same LLM-driven loop as ViabilidadModeNode, but with:
        - enviar_imagenes_ejemplo tool
        - Stricter price-before-images enforcement
        - Image result extraction from tool returns
        """
        settings = get_settings()
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))
        messages = state.get("messages", [])

        # Ensure client_type is accessible in mode_context for format_mode_context
        mode_context["_client_type"] = state.get("client_type", "particular")

        # Pass is_first_interaction so the prompt can enforce the mandatory greeting+ID
        # This flag is set by preprocess_node (total_message_count == 1)
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # ── 1. Build system prompt ───────────────────────────────────────
        # The loader owns phase-aware prompt selection based on mode_context.
        if mode_context.get("precio_comunicado"):
            logger.debug(
                "presupuesto_phase_aware_prompt",
                phase="post_price",
                mode_key="PRESUPUESTO_MODE",
                conversation_id=conversation_id,
            )
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="PRESUPUESTO_MODE",
            mode_context=mode_context,
            client_context=client_context,
        )

        # ── 2. Build LLM messages ───────────────────────────────────────
        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        llm_messages.extend(format_messages_for_llm(messages))
        llm_messages.append(
            {
                "role": "user",
                "content": f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>",
            }
        )

        # ── 3. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: Tools need access to both root state AND mode_context.
        # Use full_state pattern (same as EXPEDIENTE_MODE) for consistency.
        # IMPORTANT: Preserve nested structure - tools read from state["mode_context"]
        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context  # Preserve nested structure
        set_current_state(full_state)
        set_current_state_for_image_tools(full_state)

        # DEBUG: Log initial ContextVar state
        self._logger.info(
            "contextvar_set_initial",
            precio_comunicado=mode_context.get("precio_comunicado"),
            tarifa_calculada_exists=bool(mode_context.get("tarifa_calculada")),
            conversation_id=conversation_id,
        )

        # ── 4. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools(mode_context=mode_context)
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        pending_images: dict[str, Any] | None = None
        all_applied_flags: dict[str, Any] = {}
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2

        # Phase 3 (A/B safety net): one intervention per _process_message() call.
        # Set to True after the first mismatch is injected so the safety net
        # does not fire again in subsequent tool iterations of the same turn.
        _ab_safety_fired: bool = False

        # Phase 3: Initialize retry state for validation error recovery
        retry_state = state.get("retry_state", create_empty_retry_state())

        # Latency gating: use configurable iteration limit when flag is ON
        _effective_max_iterations = MAX_TOOL_ITERATIONS
        if settings.ENABLE_LATENCY_GATING:
            _effective_max_iterations = settings.MAX_TOOL_ITERATIONS_PRESUPUESTO
        _loop_hit_max: bool = False

        # ── Init per-turn dedup cache ────────────────────────────────────────
        # Activates the guard in base_mode._execute_and_log_tool() for this turn.
        # Reset to None in the finally block (even on exception) to prevent
        # stale cache entries leaking into the next turn.
        self._tool_dedup_cache = {}

        try:
            for iteration in range(_effective_max_iterations):
                # ── Code Guard 3.1: reset per-iteration flag ──────────────────
                # Tracks whether calcular_tarifa_con_elementos succeeded in THIS
                # LLM iteration.  Resets every iteration so the guard only fires
                # when both tools appear in the SAME LLM response (same turn).
                _tarifa_called_this_turn = False

                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self._invoke_with_fallback(
                        llm_messages,
                        tools,
                        llm_error,
                        conversation_id,
                    )

                # Track token usage
                await self._track_token_usage(conversation_id, response)

                # Check for tool calls
                tool_calls = getattr(response, "tool_calls", None)

                if not tool_calls:
                    ai_response = response.content or ""

                    # Empty LLM response retry: if the LLM returned empty
                    # content AND no tool calls (e.g. DeepSeek HTTP 200 with
                    # empty body), retry once with a reprompt instead of
                    # breaking out to the safety-net generic error.
                    if not ai_response and iteration == 0:
                        self._logger.warning(
                            "empty_llm_response_retry",
                            iteration=iteration,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SYSTEM]: Tu respuesta anterior estuvo vacía. "
                                    "Por favor, responde al mensaje del usuario. "
                                    "Si necesitas información, usa las herramientas disponibles."
                                ),
                            }
                        )
                        continue

                    # Constraint validation (anti-hallucination)
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        (
                            is_valid,
                            error_injection,
                        ) = await self._validate_response_constraints(
                            ai_response,
                            list(tools_called),
                            state,
                            current_mode_context=mode_context,  # Phase 1B: use updated context
                            available_tool_names={t.name for t in tools},
                        )

                        if not is_valid and error_injection:
                            validation_retries += 1
                            self._logger.warning(
                                "constraint_validation_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                                ai_response_preview=ai_response[:200],
                                constraint_triggered=error_injection[:100],
                                tools_called=list(tools_called),
                                conversation_id=conversation_id,
                            )
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                                }
                            )
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        # Task 5.2: This path also enforces "precio antes de imágenes"
                        # invariant.  The hallucinated response is discarded entirely
                        # and replaced with a safe reprompt that contains NO pricing
                        # claims and NO image references.  Any pending_images from a
                        # prior tool call are explicitly cleared to guarantee that the
                        # fallback message cannot be followed by stale image sends.
                        self._logger.error(
                            "constraint_retries_exhausted",
                            retries=validation_retries,
                            ai_response_preview=ai_response[:200],
                            tools_called=list(tools_called),
                            precio_comunicado=mode_context.get(
                                "precio_comunicado", False
                            ),
                            conversation_id=conversation_id,
                        )
                        ai_response = self._fallback.get_reprompt(
                            retry_state, self._policy
                        )
                        # Clear any pending images to prevent stale delivery
                        pending_images = None

                    # REFACTOR-001 Phase 2: Pattern matching REMOVED
                    # precio_comunicado is now set explicitly by calcular_tarifa_con_elementos
                    # via _internal_flags in tool return value

                    # REFACTOR-001 Phase 2: A/B option detection REMOVED
                    # LLM will naturally offer images, user accepts via enviar_imagenes_ejemplo tool

                    break

                # Execute tool calls
                llm_messages.append(self._ai_message_to_dict(response))

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    tools_called.add(tool_name)

                    self._logger.info(
                        "tool_call",
                        tool=tool_name,
                        args_preview=str(tool_args)[:100],
                        iteration=iteration + 1,
                    )
                    if settings.ENABLE_LATENCY_GATING:
                        logger.info(
                            "tool_loop_iteration",
                            iteration=iteration + 1,
                            max=_effective_max_iterations,
                            mode="PRESUPUESTO",
                            tool_name=tool_name,
                        )

                    # ── Code Guard 3.3: block images in same turn as tarifa ──
                    # If the LLM called calcular_tarifa AND enviar_imagenes in
                    # the SAME LLM response, inject a synthetic blocked result
                    # and break the inner tool loop.  This forces a new LLM
                    # invocation where the LLM will see the tarifa result +
                    # "images blocked" and naturally produce the correct message
                    # (price communicated + A/B options).
                    # Only applies to tipo="presupuesto" (not "elemento" or
                    # "documentacion_base").
                    if (
                        tool_name == "enviar_imagenes_ejemplo"
                        and _tarifa_called_this_turn
                        and tool_args.get("tipo") == "presupuesto"
                    ):
                        blocked_result = {
                            "success": False,
                            "blocked": True,
                            "message": (
                                "SISTEMA: Las imágenes NO pueden enviarse en el mismo turno "
                                "que se calculó la tarifa. "
                                "Comunica el precio al usuario en este mensaje. "
                                "Ofrece opciones: A) Ver fotos de ejemplo, "
                                "B) Abrir expediente directamente. "
                                "Llama a enviar_imagenes_ejemplo SOLO si el usuario elige "
                                "A en el siguiente turno."
                            ),
                        }
                        self._logger.warning(
                            "image_send_blocked_same_turn_as_tarifa",
                            tool=tool_name,
                            tipo=tool_args.get("tipo"),
                            iteration=iteration + 1,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps(
                                    blocked_result, ensure_ascii=False
                                ),
                            }
                        )
                        break  # Exit inner loop → force new LLM turn

                    # ── A/B routing safety net (Task 3.3) ─────────────────────
                    # After the price has been communicated, detect when the LLM
                    # picks the wrong A/B tool relative to the user's message.
                    # Inject a [VERIFICACIÓN INTERNA] ToolMessage so the LLM can
                    # self-correct in the next iteration — the original tool is
                    # NOT executed.  Max 1 intervention per turn (_ab_safety_fired).
                    _ab_reconsider = _check_ab_intent_mismatch(
                        tool_name=tool_name,
                        user_message=message,
                        mode_context={
                            **mode_context,
                            "_ab_safety_fired": _ab_safety_fired,
                        },
                    )
                    if _ab_reconsider is not None:
                        _ab_safety_fired = True
                        mode_context["_ab_safety_fired"] = True
                        logger.warning(
                            "ab_intent_mismatch_detected",
                            tool_name=tool_name,
                            user_message=message[:120],
                            reconsider=_ab_reconsider,
                            conversation_id=conversation_id,
                        )
                        # Inject synthetic ToolMessage (visible to LLM, not to user)
                        # The LLM will see the reconsider message and re-evaluate
                        llm_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": json.dumps(
                                    {"success": False, "message": _ab_reconsider},
                                    ensure_ascii=False,
                                ),
                            }
                        )
                        break  # Exit inner tool loop → let LLM self-correct

                    result = await self._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tools=tools,
                        iteration=iteration + 1,
                    )

                    # ═══════════════════════════════════════════════════════════
                    # Phase 3: Validation error retry logic
                    # ═══════════════════════════════════════════════════════════
                    is_val_error, error_dict = self._is_validation_error(result)

                    if is_val_error and error_dict:  # Type guard
                        should_retry, retry_state = self._handle_validation_retry(
                            tool_name=tool_name,
                            error_dict=error_dict,
                            retry_state=retry_state,
                            llm_messages=llm_messages,
                        )

                        if should_retry:
                            # Reprompt added to llm_messages, continue LLM loop
                            self._logger.info(
                                "validation_retry_triggered",
                                tool=tool_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            break  # Exit tool loop, go to next iteration
                        else:
                            # Max retries reached - escalate
                            self._logger.warning(
                                "validation_escalation",
                                tool=tool_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            return {
                                "ai_response": self._fallback.get_validation_reprompt(
                                    retry_state, self._policy
                                ),
                                "current_mode": "ESCALATION",
                                "escalation_triggered": True,
                                "escalation_reason": "max_validation_retries",
                                "retry_state": retry_state,
                                "mode_context": mode_context,
                            }
                    # ═══════════════════════════════════════════════════════════
                    # End Phase 3 validation retry logic
                    # ═══════════════════════════════════════════════════════════

                    # S2: Reset validation retry counters after successful tool call
                    # Prevents stale errors from contaminating reprompts in later iterations
                    if retry_state.get("retry_count", 0) > 0:
                        retry_state = _reset_validation_retry_state(retry_state)

                    # REFACTOR-001 Phase 2: Apply tool flags BEFORE extracting context
                    # BUG FIX: Use _parse_tool_result so plain-text tool errors never
                    # raise JSONDecodeError at the mode boundary (VARIANT-COMBINED-2).
                    result_dict = _parse_tool_result(result, tool_name)
                    _apply_tool_flags(mode_context, result_dict, self._logger)

                    # ── Code Guard 3.2: set flag when tarifa succeeds ─────────
                    # Set AFTER parsing result_dict so we can check "success".
                    # Used by Guard 3.3 to block enviar_imagenes_ejemplo in the
                    # same iteration.
                    if (
                        tool_name == "calcular_tarifa_con_elementos"
                        and isinstance(result_dict, dict)
                        and result_dict.get("success")
                    ):
                        _tarifa_called_this_turn = True
                        self._logger.debug(
                            "tarifa_called_this_turn_flag_set",
                            iteration=iteration + 1,
                            conversation_id=conversation_id,
                        )

                    # Track all applied flags for final authority
                    parsed_flags = (
                        result_dict.get("_internal_flags", {})
                        if isinstance(result_dict, dict)
                        else {}
                    )
                    all_applied_flags.update(parsed_flags)

                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name,
                        tool_args,
                        result,
                        current_element_codes=list(
                            mode_context.get("element_codes") or []
                        ),
                    )
                    context_updates.update(tool_context)

                    # REFACTOR-001 Phase 2: Simplified reset logic
                    # Flags are now managed by tools via _internal_flags
                    # No manual reset needed - calcular_tarifa sets precio_comunicado=True automatically

                    # Extract pending images from enviar_imagenes_ejemplo
                    if tool_name == "enviar_imagenes_ejemplo":
                        images_data = self._extract_pending_images(result)
                        if images_data:
                            pending_images = images_data
                            # NOTE: imagenes_enviadas flag is set to True by main.py after
                            # transport-level delivery (async). The tool's _internal_flags
                            # intentionally keeps it False until delivery is confirmed.

                            # Cross-mode image tracking (T-6 / TASK-13):
                            # These flags survive mode transitions so EXPEDIENTE knows
                            # images were already shown during presupuesto.
                            if tool_args.get("tipo") == "presupuesto":
                                mode_context["presupuesto_images_shown"] = True
                                raw_current_codes = mode_context.get(
                                    "element_codes", []
                                )
                                raw_shown_codes = mode_context.get(
                                    "images_shown_for_elements", []
                                )
                                current_codes_source: list[Any] = (
                                    raw_current_codes
                                    if isinstance(raw_current_codes, list)
                                    else []
                                )
                                shown_codes_source: list[Any] = (
                                    raw_shown_codes
                                    if isinstance(raw_shown_codes, list)
                                    else []
                                )
                                current_codes = [
                                    str(code).upper()
                                    for code in current_codes_source
                                    if code
                                ]
                                if current_codes:
                                    already_shown = [
                                        str(code).upper()
                                        for code in shown_codes_source
                                        if code
                                    ]
                                    mode_context["images_shown_for_elements"] = list(
                                        dict.fromkeys([*already_shown, *current_codes])
                                    )
                        else:
                            # Rama A cleanup (TASK-13): image send failed or tool returned no
                            # pending payload (e.g. duplicate-blocked, tarifa-blocked, or error).
                            # Mark attempt as done so the bot can proceed to expediente CTA
                            # without being stuck waiting for successful image delivery.
                            mode_context["imagenes_envio_intent_creado"] = True
                            self._logger.info(
                                "rama_a_image_send_failed_expediente_cta_unblocked",
                                tool_result_success=result_dict.get("success", False)
                                if isinstance(result_dict, dict)
                                else False,
                                conversation_id=conversation_id,
                            )

                    # Apply structural context updates to mode_context
                    mode_context.update(context_updates)

                    # ── Mid-loop tool re-evaluation (fix: pending_variants resolved) ──────
                    # When the last variant resolves, pending_variants drops to [].
                    # Re-bind the LLM so calcular_tarifa_con_elementos is available next iteration.
                    _new_tools = self.get_tools(mode_context=mode_context)
                    if {t.name for t in _new_tools} != {t.name for t in tools}:
                        tools = _new_tools
                        llm = self._get_llm(tools)
                        self._logger.info(
                            "tool_set_rebound_mid_loop",
                            iteration=iteration + 1,
                            new_tools=[t.name for t in tools],
                            conversation_id=conversation_id,
                        )

                    llm_messages.append(
                        {
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call_id,
                        }
                    )

                    # ═══════════════════════════════════════════════════════════
                    # S3: Inject guidance for category-not-found errors
                    # (not captured by _is_validation_error — these come from
                    # element_tools when the category slug is not found in DB)
                    # This gives the LLM immediate context without waiting for
                    # a reprompt cycle.
                    # ═══════════════════════════════════════════════════════════
                    if (
                        isinstance(result_dict, dict)
                        and result_dict.get("error") == "category_not_found"
                    ):
                        available = result_dict.get("available_categories", [])
                        slug_used = result_dict.get("categoria_usada", "")
                        if available:
                            cats_text = ", ".join(c["slug"] for c in available[:6])
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        f"[SISTEMA]: La categoría '{slug_used}' no existe. "
                                        f"Categorías disponibles para este cliente: {cats_text}. "
                                        f"Elige la categoría correcta de esta lista y reintenta."
                                    ),
                                }
                            )
                        elif slug_used:
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        f"[SISTEMA]: La categoría '{slug_used}' no existe. "
                                        f"Usa listar_categorias() para ver las opciones disponibles."
                                    ),
                                }
                            )
                    # ═══════════════════════════════════════════════════════════
                    # End S3 category-not-found injection
                    # ═══════════════════════════════════════════════════════════

                    # ═══════════════════════════════════════════════════════════
                    # S4: Price-authority injection after tariff calculation
                    # When calcular_tarifa_con_elementos succeeds, inject the
                    # exact price as a high-priority system message so the LLM
                    # does NOT anchor on stale prices from earlier turns.
                    # Fires ONLY for this tool on success AND when datos.price
                    # is present — guards ensure zero noise for all other cases.
                    # ═══════════════════════════════════════════════════════════
                    if (
                        tool_name == "calcular_tarifa_con_elementos"
                        and isinstance(result_dict, dict)
                        and result_dict.get("success") is not False
                    ):
                        _s4_datos = result_dict.get("datos", {})
                        _s4_price = (
                            _s4_datos.get("price")
                            if isinstance(_s4_datos, dict)
                            else None
                        )
                        if _s4_price is not None:
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        f"[SISTEMA]: PRECIO AUTORITATIVO de este cálculo: "
                                        f"{_s4_price} EUR +IVA. "
                                        f"Usa EXACTAMENTE este número. "
                                        f"Ignora precios de turnos anteriores del historial."
                                    ),
                                }
                            )
                            self._logger.info(
                                "price_authority_injected",
                                price=_s4_price,
                                conversation_id=conversation_id,
                            )
                    # ═══════════════════════════════════════════════════════════
                    # End S4 price-authority injection
                    # ═══════════════════════════════════════════════════════════

                    # ═══════════════════════════════════════════════════════════
                    # PHASE 1A: Fast-path break on transition signal
                    # When a tool signals _transition_to, stop immediately.
                    # The tool's message IS the response — no extra LLM iteration.
                    # ═══════════════════════════════════════════════════════════
                    if mode_context.get("_transition_to"):
                        # Extract tool's message as the final ai_response
                        transition_message = ""
                        if isinstance(result_dict, dict):
                            transition_message = result_dict.get(
                                "message", ""
                            ) or result_dict.get("texto", "")
                        if transition_message:
                            ai_response = transition_message
                        # B-path: user skipped presupuesto images — flag prevents prompt confusion.
                        # Setting presupuesto_images_shown=True with empty images_shown_for_elements
                        # tells EXPEDIENTE "the user made their image choice — don't auto-send".
                        if tool_name == "confirmar_presupuesto":
                            mode_context["presupuesto_images_shown"] = True
                            if "images_shown_for_elements" not in mode_context:
                                mode_context["images_shown_for_elements"] = []
                        self._logger.info(
                            "transition_fast_path_break",
                            target=mode_context["_transition_to"],
                            tool=tool_name,
                            has_message=bool(transition_message),
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop

                # Fast-path: also break outer iteration loop on transition
                if mode_context.get("_transition_to"):
                    break

            else:
                # Task 5.2: max iterations exhausted — another fallback path.
                # Clear pending images to enforce "precio antes de imágenes"
                # invariant: the fallback message must not be followed by stale
                # image delivery from a mid-loop tool call that was interrupted.
                _loop_hit_max = True
                self._logger.warning(
                    "max_tool_iterations",
                    iterations=_effective_max_iterations,
                    precio_comunicado=mode_context.get("precio_comunicado", False),
                )
                if settings.ENABLE_LATENCY_GATING:
                    logger.info(
                        "tool_loop_complete",
                        iterations=_effective_max_iterations,
                        exit_reason="max_iterations",
                        mode="PRESUPUESTO",
                    )
                pending_images = None  # Prevent stale image sends
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, me ha llevado más tiempo del esperado. "
                        "¿Puedes repetir tu consulta?"
                    )

            ai_response = _finalize_first_turn_intro(ai_response, mode_context)

            # Log tool loop completion for latency telemetry
            if settings.ENABLE_LATENCY_GATING and not _loop_hit_max:
                logger.info(
                    "tool_loop_complete",
                    iterations=iteration + 1 if tools_called else 0,
                    exit_reason="no_tool_calls" if not tools_called else "break",
                    mode="PRESUPUESTO",
                )

            # ── 6. Build state updates ───────────────────────────────────────
            # Merge context: mode_context is base, context_updates adds structural data,
            # all_applied_flags has FINAL AUTHORITY over boolean flags
            updated_context = {**mode_context, **context_updates}
            # _internal_flags always win over stale context_updates values
            for key, value in all_applied_flags.items():
                if key.startswith("_"):
                    continue  # Skip internal keys like _transition_to
                updated_context[key] = value

            # #13: Increment presupuesto_offered_count when price was successfully
            # communicated this turn.  precio_comunicado is set by calcular_tarifa via
            # _internal_flags — we look at the authoritative post-flags context here.
            # presupuesto_offered_count lives at ROOT level (not mode_context), so we
            # carry it as a root-level key in the returned result_dict.
            _current_offered = state.get("presupuesto_offered_count") or 0
            _precio_now = updated_context.get("precio_comunicado", False)
            _precio_before = (state.get("mode_context") or {}).get(
                "precio_comunicado", False
            )
            _new_offered_count: int = _current_offered
            if _precio_now and not _precio_before:
                # Price was communicated for the first time this turn → increment
                _new_offered_count = _current_offered + 1
                self._logger.info(
                    "presupuesto_offered_count_incremented",
                    from_=_current_offered,
                    to=_new_offered_count,
                    conversation_id=conversation_id,
                )

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: Persist retry state
                "presupuesto_offered_count": _new_offered_count,
            }

            # Propagate mode transition if signaled by a tool
            transition_target = updated_context.pop("_transition_to", None)
            updated_context["_transition_to"] = (
                None  # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
            )
            transition_applied = False
            if transition_target:
                from agent.router.mode_transitions import (
                    validate_transition,
                    get_preserve_keys,
                )
                from agent.state.conversation_state import transition_mode

                allowed, reason = validate_transition(self.mode_name, transition_target)
                if allowed:
                    preserve = get_preserve_keys(self.mode_name, transition_target)
                    transition_updates = transition_mode(
                        state,
                        transition_target,
                        preserve_keys=preserve,
                    )
                    # Merge transition updates, but keep our ai_response
                    saved_response = result_dict["ai_response"]
                    result_dict.update(transition_updates)
                    result_dict["ai_response"] = saved_response
                    transition_applied = True
                    self._logger.info(
                        "mode_transition_from_tool",
                        target=transition_target,
                        conversation_id=conversation_id,
                    )
                else:
                    self._logger.warning(
                        "mode_transition_blocked",
                        target=transition_target,
                        reason=reason,
                        conversation_id=conversation_id,
                    )

            # Propagate chain signal to root state (for main.py to detect)
            # Only chain if the transition was actually applied.
            # CRITICAL: After consuming, set to None (not pop) so merge_dicts
            # overwrites the checkpoint value. pop() leaves the old value alive
            # because merge_dicts({**current, **update}) only adds/overwrites keys
            # present in update — absent keys survive from current.
            chain_signal = updated_context.pop("_chain_next_mode", None)
            updated_context["_chain_next_mode"] = None  # Kill stale checkpoint value
            if chain_signal and transition_applied:
                result_dict["_chain_next_mode"] = True
                self._logger.info(
                    "chain_signal_propagated",
                    target=transition_target,
                    conversation_id=conversation_id,
                )

            # NOTE: tarifa_actual NO LONGER propagated to root state.
            # Tools now access tarifa_calculada directly from mode_context via full_state pattern.
            # This eliminates data duplication and maintains single source of truth.
            if updated_context.get("_tarifa_actual"):
                # Remove signal key (no longer needed)
                # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
                updated_context.pop("_tarifa_actual")
                updated_context["_tarifa_actual"] = None  # TOMBSTONE

            # Bubble up pending images for the main node to send
            if pending_images:
                result_dict["pending_images"] = pending_images
                # Persist follow_up text so LLM sees it next turn (Bug A fix)
                follow_up = pending_images.get("follow_up_message")
                if follow_up:
                    updated_context["last_follow_up_sent"] = follow_up

            self._logger.info(
                "presupuesto_response",
                response_length=len(ai_response),
                tools_called=list(tools_called),
                context_keys=list(context_updates.keys()),
                has_pending_images=pending_images is not None,
            )

            return result_dict

        finally:
            # ── 7. Cleanup ContextVars ──────────────────────────────────────
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()
            # ── Deactivate per-turn dedup cache ────────────────────────────
            self._tool_dedup_cache = None

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
            # IMPORTANT: Clear previous identification/pricing data
            # With merge_dicts reducer, we must explicitly clear obsolete fields
            # to prevent stale data from previous queries confusing the LLM
            updates["tarifa_calculada"] = None
            # REFACTOR-001: Flag resets (precio_comunicado, imagenes_enviadas)
            # now handled by _internal_flags in tool return value

            listos = data.get("elementos_listos", [])
            variantes = data.get("elementos_con_variantes", [])
            preguntas = data.get("preguntas_variantes", [])

            if listos and not variantes:
                updates["elemento_confirmado"] = listos[0] if len(listos) == 1 else None
                updates["element_codes"] = [e.get("codigo") for e in listos]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["elemento_tentativo"] = None  # Clear tentative
                updates["pending_variants"] = []  # Clear variant questions
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = preguntas
                updates["elemento_confirmado"] = None  # Clear confirmed
                # RC-2a: No resolved elements yet — clear stale element_codes so they
                # cannot corrupt calcular_tarifa or enviar_imagenes guards.
                updates["element_codes"] = []

            updates["categoria_slug"] = tool_args.get(
                "categoria_vehiculo",
                tool_args.get("categoria"),
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

            if has_selection and not data.get("error"):
                # ══════════════════════════════════════════════════════════
                # FIX: Incremental pending_variants update (no premature clear)
                # If the tool returned updated pending_variants via _internal_flags,
                # use that. Otherwise, for legacy single-selection, check if all
                # entries are resolved before clearing.
                # ══════════════════════════════════════════════════════════
                from agent.state.helpers import normalize_pending_variants

                tool_flags = data.get("_internal_flags", {})
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
