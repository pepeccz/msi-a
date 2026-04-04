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
from agent.modes.generic_loop import generic_llm_loop, GenericLoopResult
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

        Delegates to _process_with_generic_loop() (generic loop path).
        """
        return await self._process_with_generic_loop(message, state)

    # ------------------------------------------------------------------
    # Generic loop path (T2.2)
    # ------------------------------------------------------------------

    async def _process_with_generic_loop(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a message by delegating to generic_llm_loop().

        Minimal wiring for T2.2:
        1. Assemble system prompt (reuse existing builder).
        2. Build LLM via _get_llm() (injects credentials, tools, max_tokens).
        3. Define on_tool_result to capture key context flags from tool results.
        4. Call generic_llm_loop() with all the assembled pieces.
        5. Merge result.context_updates into mode_context and return.

        The S4 price-authority injection, constraint validation, image extraction,
        and the rest of the business-logic post-processing are intentionally kept
        minimal here — they will be wired in subsequent tasks.

        """
        conversation_id = str(state.get("conversation_id", "unknown"))
        mode_context = dict(state.get("mode_context") or {})
        messages = state.get("messages", [])

        # Enrich mode_context with runtime flags (same as old loop)
        mode_context["_client_type"] = state.get("client_type", "particular")
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # T3.2d — Load DraftQuote on resume (REQ-P3-1-3)
        await _load_active_draft_quote_into_context(conversation_id, mode_context)

        # 1. Build system prompt (identical to old loop)
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="PRESUPUESTO_MODE",
            mode_context=mode_context,
            client_context=client_context,
        )

        # 2. Build conversation history (without system prompt — that's separate)
        llm_history = list(format_messages_for_llm(messages))
        llm_history.append(
            {
                "role": "user",
                "content": f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>",
            }
        )

        # 3. Get tools and LLM
        tools = self.get_tools(mode_context=mode_context)
        _initial_has_unresolved = _has_unresolved_variants(mode_context)
        llm = self._get_llm(
            tools,
            tool_choice="required" if _initial_has_unresolved else None,
        )

        # 4. Configure ContextVars (same as old loop — tools need this)
        # T2.5: A single set_current_state() is sufficient — image_tools now
        # uses the shared ContextVar from agent.state.helpers (REQ-P2-2).
        from typing import cast

        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context
        set_current_state(full_state)

        # Track dedup cache (required by base_mode._execute_and_log_tool)
        self._tool_dedup_cache = {}

        try:
            # 5. Define on_tool_result callback to capture important flags
            context_from_tools: dict[str, Any] = {}
            # Accumulator for cross-call variant resolution (Option A fix).
            # Each call to seleccionar_variante_por_respuesta may resolve only ONE
            # pending variant (stale ContextVar snapshot per call). We accumulate
            # resolved codigo_base → variant_code here so the injection fires only
            # when ALL original pending variants from the start of this turn are
            # covered — even when the LLM makes parallel calls.
            _resolved_variants_this_turn: dict[str, str] = {}

            async def on_tool_result(
                tool_name: str,
                result_dict: dict[str, Any],
                tool_args: dict[str, Any],
                context_updates: dict[str, Any],
            ) -> dict[str, Any] | None:
                """
                Callback invoked by generic_llm_loop after each tool execution.
                Extracts key context flags from tool results.

                Note: _extract_context_from_tool expects a JSON string for
                the result argument.  We serialize result_dict here.
                tool_args is now passed from generic_llm_loop (W-3 fix).

                Returns an optional dict that generic_llm_loop uses to:
                - inject_messages: update the LLM's world-view mid-loop
                - rebind_tools: switch toolset after variant resolution
                - rebind_tool_choice: clear tool_choice restriction
                """
                # Serialize dict → string for _extract_context_from_tool compatibility
                result_str = json.dumps(result_dict, ensure_ascii=False)

                # Extract structural context from tool results (same logic as old loop)
                tool_context = self._extract_context_from_tool(
                    tool_name,
                    tool_args,  # W-3 fix: tool_args now available
                    result_str,
                    current_element_codes=list(mode_context.get("element_codes") or []),
                )
                context_from_tools.update(tool_context)

                # Apply _internal_flags from tool results (transition signals, state flags).
                # Without this, confirmar_presupuesto()._internal_flags._transition_to
                # is silently lost and the mode never transitions to EXPEDIENTE_MODE.
                # NOTE: Must run BEFORE ContextVar refresh so flags (e.g. pending_variants)
                # are visible to subsequent tools in the same iteration.
                _apply_tool_flags(mode_context, result_dict, logger)

                # Refresh ContextVar so subsequent tools in this loop iteration
                # see ALL accumulated context: both extracted context (categoria_slug,
                # element_codes) and internal flags (pending_variants, precio_comunicado).
                # Without this, tool_executor reads stale state from turn start.
                _refreshed_state = dict(state)
                _refreshed_ctx = dict(mode_context)
                _refreshed_ctx.update(context_from_tools)
                _refreshed_state["mode_context"] = _refreshed_ctx
                set_current_state(_refreshed_state)

                # W-4 fix: S4 price-authority injection in generic path.
                # When calcular_tarifa_con_elementos succeeds, inject the exact
                # price into context_updates so the LLM always uses authoritative data.
                if tool_name == "calcular_tarifa_con_elementos" and result_dict.get(
                    "success"
                ):
                    precio = None
                    datos = result_dict.get("datos")
                    if isinstance(datos, dict):
                        precio = datos.get("price")
                    elif isinstance(result_dict.get("precio_final"), (int, float)):
                        precio = result_dict.get("precio_final")
                    if precio is not None:
                        context_updates["price_authority"] = {
                            "precio": precio,
                            "source": "calcular_tarifa_con_elementos",
                        }

                # Extract pending images from enviar_imagenes_ejemplo
                if tool_name == "enviar_imagenes_ejemplo":
                    images = self._extract_pending_images(result_str)
                    if images:
                        context_from_tools["_pending_images"] = images

                # ── Variant discovery injection ───────────────────────────────
                # When identificar_y_resolver_elementos returns pending variants,
                # inject a factual state-update system message so the LLM attempts
                # auto-resolution (Paso 5.5) before asking the user.
                # This fires on first-turn variant discovery (mode_context has no
                # pending_variants yet) as well as on re-identification after vehicle
                # correction.
                if tool_name == "identificar_y_resolver_elementos":
                    preguntas = result_dict.get("preguntas_variantes") or []
                    if preguntas:
                        # Build readable list of variants with their options
                        variant_lines: list[str] = []
                        for pv in preguntas:
                            codigo = pv.get("codigo_base", "?")
                            opciones = pv.get("opciones", [])
                            if isinstance(opciones, list) and opciones:
                                opts_str = ", ".join(str(o) for o in opciones)
                            else:
                                # Fall back to elements_con_variantes if opciones absent
                                elems = result_dict.get("elementos_con_variantes", [])
                                matching = next(
                                    (
                                        e
                                        for e in elems
                                        if e.get("codigo_base") == codigo
                                    ),
                                    None,
                                )
                                if matching:
                                    variantes = matching.get("variantes", [])
                                    opts_str = ", ".join(
                                        v.get("nombre") or v.get("codigo") or str(v)
                                        for v in variantes
                                        if isinstance(v, dict)
                                    )
                                else:
                                    opts_str = "(ver pregunta)"
                            variant_lines.append(f"- {codigo}: [{opts_str}]")

                        variants_block = "\n".join(variant_lines)
                        inject_text = (
                            f"[Estado]: identificar_y_resolver_elementos encontró "
                            f"{len(preguntas)} elemento(s) con variantes pendientes.\n"
                            f'Texto original del usuario: "{message}"\n'
                            f"Variantes pendientes:\n{variants_block}\n"
                            f"Antes de preguntar al usuario, intenta resolver cada "
                            f"variante llamando a seleccionar_variante_por_respuesta "
                            f"con el texto original (o la cláusula relevante del mensaje)."
                        )

                        logger.info(
                            "presupuesto_variant_discovery_injection",
                            num_variants=len(preguntas),
                            conversation_id=conversation_id,
                        )

                        return {
                            "inject_messages": [
                                {"role": "system", "content": inject_text}
                            ],
                        }

                # ── Opción C: Variant-resolution state injection ──────────────
                # When seleccionar_variante_por_respuesta resolves ALL pending
                # variants, inject a factual state-update message and rebind to
                # the full toolset so the LLM can call calcular_tarifa_con_elementos
                # on the very next iteration — without seeing stale system prompt
                # content that still lists unresolved variants.
                #
                # FIX (fix/variant-parallel-resolution): The old code evaluated
                # all_explicitly_resolved per-call using only THIS call's flags.
                # When the LLM makes parallel calls (e.g. user says "B y A"),
                # call-1 sees [PLACA_SOLAR:resolved, TOLDO_LAT:pending] and
                # call-2 sees [TOLDO_LAT:resolved, PLACA_SOLAR:pending] (stale
                # ContextVar snapshot — not updated between parallel calls).
                # Neither call saw all variants resolved → injection never fired.
                #
                # FIX (Option A): Use a closure-local accumulator dict that
                # survives across all calls in this turn. Injection fires when
                # the accumulator covers ALL codes from the original pending list
                # (immutable snapshot from the START of this turn).
                if (
                    tool_name == "seleccionar_variante_por_respuesta"
                    and not result_dict.get("error")
                ):
                    # Step 1: Accumulate resolved variants from this call's flags.
                    # Only entries with status == "resolved" are counted —
                    # needs_clarification and pending are NOT added to the accumulator.
                    tool_flags = result_dict.get("_internal_flags", {})
                    for pv in tool_flags.get("pending_variants", []):
                        if isinstance(pv, dict) and pv.get("status") == "resolved":
                            cb = pv.get("codigo_base")
                            if cb:
                                # Prefer selected_variant from the tool result (actual
                                # element code like TOLDO_GALIBO) over resoluciones[]
                                # .variant_code which may contain option TEXT instead
                                # of the code (e.g. "A - Toldo lateral (sin afectar
                                # galibo)") when resolved via LLM interpretation.
                                sv = result_dict.get("selected_variant")
                                if sv and cb == tool_args.get("codigo_elemento_base", "").upper():
                                    _resolved_variants_this_turn[cb] = sv
                                else:
                                    # Guard: don't overwrite a valid element code
                                    # with a corrupted option text from a parallel
                                    # tool call's resoluciones snapshot.
                                    import re as _re_guard

                                    _EC_RE = _re_guard.compile(r"^[A-Z][A-Z0-9_]+$")
                                    existing_val = _resolved_variants_this_turn.get(cb)
                                    if existing_val and _EC_RE.match(existing_val):
                                        pass  # Already has correct code, skip
                                    else:
                                        for res in pv.get("resoluciones", []):
                                            vc = (
                                                res.get("variant_code")
                                                if isinstance(res, dict)
                                                else getattr(
                                                    res, "variant_code", None
                                                )
                                            )
                                            if vc:
                                                _resolved_variants_this_turn[cb] = vc
                                                break

                    # Step 2: Immutable snapshot of pending codes at turn start.
                    # mode_context is captured at closure creation time (start of turn)
                    # and is NOT mutated by parallel calls — safe reference.
                    original_pending_codes = {
                        pv.get("codigo_base")
                        for pv in (mode_context.get("pending_variants") or [])
                        if isinstance(pv, dict) and pv.get("codigo_base")
                    }

                    # Step 3: Fire injection only when accumulator covers ALL originals.
                    all_resolved_accumulated = bool(
                        original_pending_codes
                    ) and original_pending_codes.issubset(
                        set(_resolved_variants_this_turn.keys())
                    )

                    if all_resolved_accumulated:
                        # Build state-update injection with all accumulated codes
                        import re as _re

                        _ELEMENT_CODE_RE = _re.compile(r"^[A-Z][A-Z0-9_]+$")
                        resolved_codes: list[str] = []
                        for _rc in _resolved_variants_this_turn.values():
                            if _ELEMENT_CODE_RE.match(_rc):
                                resolved_codes.append(_rc)
                            else:
                                logger.warning(
                                    "presupuesto_resolved_code_rejected",
                                    rejected_value=_rc,
                                    reason="does not match element code pattern",
                                )

                        # Also include codes from context_from_tools (accumulated this turn)
                        ctx_codes = list(context_from_tools.get("element_codes") or [])
                        for c in ctx_codes:
                            if c not in resolved_codes and _ELEMENT_CODE_RE.match(c):
                                resolved_codes.append(c)

                        codes_str = (
                            ", ".join(resolved_codes)
                            if resolved_codes
                            else "(ver contexto)"
                        )

                        inject_msg = (
                            f"[Estado actualizado]: Todas las variantes han sido confirmadas. "
                            f"Códigos resueltos: {codes_str}. "
                            f"Siguiente paso: llamar calcular_tarifa_con_elementos "
                            f"con estos códigos."
                        )

                        logger.info(
                            "presupuesto_variants_all_resolved_injection",
                            resolved_codes=resolved_codes,
                            conversation_id=conversation_id,
                        )

                        # FIX 1 (fix/variant-state-persistence): Persist all-resolved
                        # state into context_updates so it survives the merge priority
                        # chain in presupuesto_mode:
                        #   {**mode_context, **context_from_tools, **loop_result.context_updates}
                        # Without this, loop_result.context_updates may contain
                        # resolved entries (non-empty list) from _apply_internal_flags
                        # which overwrites context_from_tools["pending_variants"] = [].
                        # context_updates is the same mutable dict as
                        # result.context_updates (passed by reference from generic_loop.py
                        # line ~350). Writing to it here is equivalent to writing via
                        # _apply_internal_flags. Multiple calls are idempotent.
                        context_updates["pending_variants"] = []
                        context_updates["element_codes"] = resolved_codes

                        return {
                            "inject_messages": [
                                {"role": "system", "content": inject_msg}
                            ],
                            "rebind_tools": self.get_tools(mode_context={}),
                            "rebind_tool_choice": None,
                        }

                return None

            # 6. Delegate to generic_llm_loop
            loop_result: GenericLoopResult = await generic_llm_loop(
                system_prompt=system_prompt,
                messages=llm_history,
                tools=tools,
                max_iterations=10,
                conversation_id=conversation_id,
                mode_name="PRESUPUESTO_MODE",
                state=full_state,
                llm=llm,
                on_tool_result=on_tool_result,
            )

            # 7. Merge all updates into mode_context
            #    Priority: loop context_updates > tool-extracted context > base mode_context
            updated_context = {
                **mode_context,
                **context_from_tools,
                **loop_result.context_updates,
            }

            # Apply first-turn intro guard (same as old loop)
            ai_response = _finalize_first_turn_intro(
                loop_result.ai_response, mode_context
            )

            # Build result dict
            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
            }

            # Propagate mode transition signal to top-level state.
            # _apply_tool_flags writes _transition_to into mode_context;
            # LangGraph needs current_mode at root level to route the next turn.
            _transition_target = updated_context.pop("_transition_to", None)
            if _transition_target:
                result_dict["current_mode"] = _transition_target
                # Clean up transient key (TOMBSTONE so merge_dicts overwrites checkpoint)
                updated_context["_transition_to"] = None
                self._logger.info(
                    "presupuesto_mode_transition",
                    target=_transition_target,
                    conversation_id=conversation_id,
                )

            # Propagate mode chaining signal to top-level state.
            # main.py checks result["_chain_next_mode"] to re-invoke the graph
            # in the same turn (zero-friction UX). Without this promotion,
            # the flag stays buried in mode_context and chaining never fires.
            _chain = updated_context.pop("_chain_next_mode", None)
            if _chain:
                result_dict["_chain_next_mode"] = True
                updated_context["_chain_next_mode"] = None  # TOMBSTONE

            # Bubble up pending images if any, then clean from mode_context
            pending_images = context_from_tools.get("_pending_images")
            if pending_images:
                result_dict["pending_images"] = pending_images
                updated_context.pop("_pending_images", None)

            self._logger.info(
                "presupuesto_generic_loop_response",
                exit_reason=loop_result.exit_reason,
                tools_called=list(loop_result.tools_called),
                response_length=len(ai_response),
                conversation_id=conversation_id,
            )

            return result_dict

        finally:
            # Always clean up ContextVars and dedup cache
            clear_current_state()
            clear_image_tools_state()
            self._tool_dedup_cache = None
            # T3.2d — Deactivate DraftQuote on mode exit (REQ-P3-1-4)
            try:
                from agent.tools.draft_quote_service import _deactivate_draft_quote

                await _deactivate_draft_quote(conversation_id=conversation_id)
            except Exception as e:
                logger.warning("draft_quote_deactivation_failed", error=str(e))

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
