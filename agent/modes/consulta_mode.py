"""
MSI-a - CONSULTA_MODE Node.

Educational mode for general questions about vehicle homologation.
Handles ~10% of traffic — the informational entry point.

Flow:
    1. User asks a general question about homologation
    2. LLM uses tools to search documentation (RAG), list categories, etc.
    3. LLM provides an informative response
    4. Detects when user shows interest in specific elements → suggests transition

Available tools:
    - listar_categorias (vehicle category listing)
    - listar_elementos (element listing per category)
    - obtener_servicios_adicionales (additional services info)
    - escalar_a_humano (universal)

Architecture:
    Same pattern as ViabilidadModeNode: LLM-driven tool calling loop.
    The system prompt guides the LLM to stay informational and detect
    transition opportunities when the user mentions specific elements.
"""

from __future__ import annotations

import hashlib
import re as _re_module
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
MAX_TOOL_ITERATIONS = 8

# Max entries in consulta_history rolling window
MAX_CONSULTA_HISTORY = 10


def _fingerprint_message(message: str) -> str:
    """
    Create a lightweight fingerprint for repeated-question detection.

    Strategy: lowercase + strip punctuation + take first 100 chars → sha256 hex.
    This avoids heavy NLP while still catching near-duplicate questions.
    """
    normalized = _re_module.sub(r"[^\w\s]", "", message.lower()).strip()
    normalized = _re_module.sub(r"\s+", " ", normalized)[:100]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class ConsultaModeNode(BaseModeNode):
    """
    CONSULTA_MODE: Answer general informational questions.

    Uses the LLM with informational tools to:
    - Answer questions about homologation (via RAG)
    - Show available vehicle categories
    - List elements that can be homologated
    - Explain the process and timeline
    - Detect transition opportunities to VIABILIDAD/PRESUPUESTO
    """

    def __init__(self) -> None:
        super().__init__("CONSULTA_MODE")
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
        Process a user message in CONSULTA_MODE.

        Same LLM-driven loop as ViabilidadModeNode but with
        informational tools instead of element identification tools.

        Phase 3: Now includes validation retry logic.
        """
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))
        messages = state.get("messages", [])
        retry_state = state.get("retry_state", create_empty_retry_state())

        # Pass is_first_interaction so the prompt can enforce mandatory greeting+ID
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # ── Entity extraction with latency gating ──────────────────────
        from agent.services.entity_extraction_service import (
            get_entity_extraction_service,
        )

        settings = get_settings()
        message_history = state.get("messages", [])

        # Latency gating: skip entity extraction for short/trivial messages
        # when ENABLE_LATENCY_GATING is on.  Uses a simple heuristic (message
        # length + keyword presence) — NO additional LLM call.
        _skip_extraction = False
        _skip_reason = ""

        if settings.ENABLE_LATENCY_GATING and message:
            _ENTITY_INDICATOR_RE = (
                r"\b(moto|coche|cami[oó]n|furgoneta|quad|buggy|turismo|veh[ií]culo"
                r"|escape|subchasis|suspension|suspensi[oó]n|manillar|luces|llantas"
                r"|frenos|silenciador|chasis|motor|kit|barra|defensa|paragolpes"
                r"|honda|yamaha|bmw|mercedes|kawasaki|suzuki|ducati|ktm|harley"
                r"|homologar|homologaci[oó]n|modificar|modificaci[oó]n"
                r"|presupuesto|precio|cu[aá]nto)\b"
            )
            import re as _re

            _has_indicators = bool(_re.search(_ENTITY_INDICATOR_RE, message.lower()))
            _long_enough = len(message) > 20

            if not (_has_indicators or _long_enough):
                _skip_extraction = True
                _skip_reason = f"short_msg({len(message)}chars)_no_entity_indicators"

        if _skip_extraction:
            # Preserve any previously extracted entities from mode_context
            entities: dict[str, Any] = {
                "elementos": mode_context.get("remembered_elementos", []),
                "marca": mode_context.get("remembered_marca"),
                "modelo": mode_context.get("remembered_modelo"),
            }
            logger.info(
                "entity_extraction_gated",
                skipped=True,
                reason=_skip_reason,
                mode="CONSULTA",
            )
        else:
            extraction_service = get_entity_extraction_service()
            entities = await extraction_service.extract_entities(
                message_history,
                max_messages=5,
            )
            logger.info(
                "entity_extraction_gated",
                skipped=False,
                reason="indicators_present"
                if settings.ENABLE_LATENCY_GATING
                else "gating_disabled",
                mode="CONSULTA",
            )

        # Store in mode_context
        mode_context["remembered_elementos"] = entities.get("elementos", [])
        mode_context["remembered_marca"] = entities.get("marca")
        mode_context["remembered_modelo"] = entities.get("modelo")

        logger.info(
            "consulta_context_memory",
            elementos=mode_context["remembered_elementos"],
            marca=mode_context["remembered_marca"],
            modelo=mode_context["remembered_modelo"],
        )

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="CONSULTA_MODE",
            mode_context=mode_context,
            client_context=client_context,
        )

        # ── NUEVO: Inject context memory into prompt ─────────────────────
        context_additions: list[str] = []

        if mode_context.get("remembered_elementos"):
            elementos_str = ", ".join(mode_context["remembered_elementos"])
            context_additions.append(
                f"\n**CONTEXTO IMPORTANTE**: El usuario mencionó estos elementos previamente: {elementos_str}. "
                f"NO vuelvas a preguntar qué quiere modificar si ya lo mencionó."
            )

        if mode_context.get("remembered_marca") and mode_context.get(
            "remembered_modelo"
        ):
            marca = mode_context["remembered_marca"]
            modelo = mode_context["remembered_modelo"]
            context_additions.append(
                f"\n**VEHÍCULO DEL USUARIO**: {marca} {modelo}. "
                f'Si necesitas clasificarlo, llama a identificar_tipo_vehiculo("{marca}", "{modelo}").'
            )

        if context_additions:
            system_prompt += "\n\n" + "\n".join(context_additions)

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

        # ── 3. First interaction greeting ────────────────────────────────
        is_first = state.get("is_first_interaction", False)
        if is_first and not messages:
            # Inject greeting context
            llm_messages.insert(
                -1,
                {
                    "role": "system",
                    "content": (
                        "Esta es la PRIMERA interacción del usuario. "
                        "Saluda brevemente y ofrece ayuda. "
                        "NO hagas preguntas múltiples — sé conciso."
                    ),
                },
            )

        # ── 3b. Repeated-question detection (#14) ────────────────────────
        # Lightweight: fingerprint the user message and check against
        # consulta_history.  If a match is found, inject a hint into the
        # LLM messages so it can reference the previous answer without
        # re-running all tools.  This is SILENT — no user-visible notice.
        _msg_fingerprint = _fingerprint_message(message)
        _prior_answer: str | None = None
        _raw_ch = cast(Any, mode_context).get("consulta_history")
        _consulta_history: list[dict[str, str]] = (
            list(_raw_ch) if isinstance(_raw_ch, list) else []
        )

        for _entry in _consulta_history:
            if _entry.get("fingerprint") == _msg_fingerprint:
                _prior_answer = _entry.get("answer")
                break

        if _prior_answer:
            llm_messages.append(
                {
                    "role": "system",
                    "content": (
                        "El usuario pregunta algo similar a una pregunta anterior. "
                        f"Respuesta anterior: {_prior_answer}. "
                        "Puedes referirte a ella brevemente y preguntar si necesita más detalle."
                    ),
                }
            )
            logger.info(
                "consulta_repeated_question_detected",
                fingerprint=_msg_fingerprint,
                conversation_id=conversation_id,
            )

        # ── 4. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: Tools like listar_categorias, obtener_servicios_adicionales,
        # and escalar_a_humano need state via ContextVars.
        state_dict = cast(dict[str, Any], state)
        set_current_state(state_dict)
        set_current_state_for_image_tools(state_dict)

        # ── 5. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools()
        llm = self._get_llm(tools)

        # ── 6. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2

        # Latency gating: use configurable iteration limit when flag is ON
        _effective_max_iterations = MAX_TOOL_ITERATIONS
        if settings.ENABLE_LATENCY_GATING:
            _effective_max_iterations = settings.MAX_TOOL_ITERATIONS_CONSULTA

        _last_tool_name: str = ""
        _loop_hit_max: bool = False

        # ── Init per-turn dedup cache ────────────────────────────────────────
        # Activates the guard in base_mode._execute_and_log_tool() for this turn.
        # Reset to None in the finally block (even on exception) to prevent
        # stale cache entries leaking into the next turn.
        self._tool_dedup_cache = {}

        try:
            for iteration in range(_effective_max_iterations):
                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self._invoke_with_fallback(
                        llm_messages,
                        tools,
                        llm_error,
                        conversation_id,
                    )

                tool_calls = getattr(response, "tool_calls", None)

                # Track token usage on every LLM invocation (inside the loop)
                # This ensures all iterations are counted, not just the last one.
                await self._track_token_usage(conversation_id, response)

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
                            conversation_id=state.get("conversation_id", "unknown"),
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
                                "constraint_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                            )
                            # Phase 4B: Unified role "system" + IMPORTANT instruction
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                                }
                            )
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        self._logger.error(
                            "constraint_retries_exhausted",
                            retries=validation_retries,
                            conversation_id=state.get("conversation_id", "unknown"),
                        )
                        ai_response = "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"

                    break

                # Execute tool calls
                llm_messages.append(self._ai_message_to_dict(response))

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    tools_called.add(tool_name)

                    _last_tool_name = tool_name
                    self._logger.info(
                        "tool_call",
                        tool=tool_name,
                        iteration=iteration + 1,
                    )
                    if settings.ENABLE_LATENCY_GATING:
                        logger.info(
                            "tool_loop_iteration",
                            iteration=iteration + 1,
                            max=_effective_max_iterations,
                            mode="CONSULTA",
                            tool_name=tool_name,
                        )

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
                            )
                            break  # Exit tool loop, go to next iteration
                        else:
                            # Max retries reached - escalate
                            self._logger.warning(
                                "validation_escalation",
                                tool=tool_name,
                                retry_count=retry_state.get("retry_count"),
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

                    llm_messages.append(
                        {
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call_id,
                        }
                    )
            else:
                # Max iterations exhausted
                _loop_hit_max = True
                if settings.ENABLE_LATENCY_GATING:
                    logger.info(
                        "tool_loop_complete",
                        iterations=_effective_max_iterations,
                        exit_reason="max_iterations",
                        mode="CONSULTA",
                    )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, no he podido completar la búsqueda. "
                        "¿Puedes reformular tu pregunta?"
                    )

            # Log tool loop completion for latency telemetry
            if settings.ENABLE_LATENCY_GATING and not _loop_hit_max:
                logger.info(
                    "tool_loop_complete",
                    iterations=iteration + 1 if tools_called else 0,
                    exit_reason="no_tool_calls" if not tools_called else "break",
                    mode="CONSULTA",
                )

            # ── 7. Build state updates ───────────────────────────────────────
            # Note: token usage is tracked inside the loop (after each LLM call)
            updated_context = {**mode_context, **context_updates}

            # #12: Populate consulta_history (rolling window, max 10 entries)
            # Only append when there is a real AI response (not a fallback/error)
            _ai_resp_str: str = ai_response if isinstance(ai_response, str) else ""
            if _ai_resp_str and not _ai_resp_str.startswith("Disculpa,"):
                _raw_history = cast(Any, updated_context).get("consulta_history")
                _history: list[dict[str, str]] = (
                    list(_raw_history) if isinstance(_raw_history, list) else []
                )
                _answer_summary: str = _ai_resp_str[:300]  # Keep summary short
                _history.append(
                    {
                        "fingerprint": _msg_fingerprint,
                        "question": message[:200],
                        "answer": _answer_summary,
                    }
                )
                # Rolling window: keep only the last MAX_CONSULTA_HISTORY entries
                if len(_history) > MAX_CONSULTA_HISTORY:
                    _history = _history[-MAX_CONSULTA_HISTORY:]
                updated_context["consulta_history"] = _history

            self._logger.info(
                "consulta_response",
                response_length=len(ai_response),
                consultas_count=len(updated_context.get("consulta_history", [])),
                retry_count=retry_state.get(
                    "retry_count", 0
                ),  # Phase 3: log retry count
            )

            return {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: return updated retry state
            }

        finally:
            # ── 9. Cleanup ContextVars ──────────────────────────────────────
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()
            # ── Deactivate per-turn dedup cache ────────────────────────────
            self._tool_dedup_cache = None

    def get_tools(self) -> list:
        """Return tools available in CONSULTA_MODE."""
        if self._tools is None:
            self._tools = _get_consulta_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers — delegated to BaseModeNode
    # ------------------------------------------------------------------
    # _get_llm() and _invoke_with_fallback() are inherited from BaseModeNode.
    # CONSULTA uses the default _default_max_tokens = 1500.

    # _execute_tool inherited from BaseModeNode

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_client_context(state: ConversationState) -> str:
        """Build client-specific context string."""
        parts: list[str] = []

        client_type = state.get("client_type", "particular")
        type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        parts.append(f"Cliente: **{type_display}**")

        user_name = state.get("user_name")
        if user_name:
            parts.append(f"Nombre: {user_name}")

        return "\n".join(parts)

    @staticmethod
    def _ai_message_to_dict(response: Any) -> dict[str, Any]:
        """Convert an LLM AIMessage to a dict."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if hasattr(response, "tool_calls") and response.tool_calls:
            msg["tool_calls"] = [
                {"id": tc["id"], "name": tc["name"], "args": tc["args"]}
                for tc in response.tool_calls
            ]
        return msg


# ---------------------------------------------------------------------------
# RAG query tool (new for v2 — wraps api/services/rag_service)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tool registry for CONSULTA_MODE
# ---------------------------------------------------------------------------


def _get_consulta_tools() -> list:
    """
    Get the tool set for CONSULTA_MODE.

    Informational tools only — no element identification or pricing.
    """
    from agent.tools.tarifa_tools import (
        listar_categorias,
        obtener_servicios_adicionales,
    )
    from agent.tools.element_tools import listar_elementos
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Catalog browsing
        listar_categorias,
        listar_elementos,
        # Additional services info
        obtener_servicios_adicionales,
        # Universal
        escalar_a_humano,
    ]
