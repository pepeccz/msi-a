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
    6. LLM offers to proceed to EVALUACION_GATEWAY

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
from datetime import datetime, UTC
from typing import Any, cast

import structlog
from langchain_openai import ChatOpenAI

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState, create_empty_retry_state
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import format_messages_for_llm, set_current_state, clear_current_state
from agent.tools.image_tools import set_current_state_for_image_tools, clear_image_tools_state
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10


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
        import json
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
      B) Open case directly (transition to EVALUACION_GATEWAY)

    Critical rules:
    - PRICE must be communicated BEFORE sending images
    - After price, offer 2 options (not just one)
    - NO concept of "estimación" vs "precio exacto" (always exact)
    """

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
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))
        messages = state.get("messages", [])

        # ✅ FASE 1 FIX: Detectar respuesta del usuario a opciones A/B
        if mode_context.get("waiting_for_image_choice"):
            # Usuario está respondiendo a "¿Opción A (fotos) o B (sin fotos)?"
            message_lower = message.lower().strip()
            
            # Detectar "A" o variantes (ver fotos)
            import re
            if re.search(r'\b(a|opci[oó]n\s+a|ver.*foto)', message_lower):
                mode_context["waiting_for_image_choice"] = False
                # Removed opcion_seleccionada flag (REFACTOR-001): never read
                self._logger.info(
                    "option_a_selected",
                    conversation_id=conversation_id,
                    user_message=message[:50],
                )
            # Detectar "B" o variantes (sin fotos)
            elif re.search(r'\b(b|opci[oó]n\s+b|no.*foto)', message_lower):
                mode_context["waiting_for_image_choice"] = False
                # Removed opcion_seleccionada flag (REFACTOR-001): never read
                self._logger.info(
                    "option_b_selected",
                    conversation_id=conversation_id,
                    user_message=message[:50],
                )

        # ── 1. Build system prompt ───────────────────────────────────────
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
        llm_messages.append({
            "role": "user",
            "content": f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>",
        })

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
            waiting_for_image_choice=mode_context.get("waiting_for_image_choice"),
            tarifa_calculada_exists=bool(mode_context.get("tarifa_calculada")),
            conversation_id=conversation_id,
        )

        # ── 4. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools()
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        pending_images: dict[str, Any] | None = None
        all_applied_flags: dict[str, Any] = {}
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2
        
        # Phase 3: Initialize retry state for validation error recovery
        retry_state = state.get("retry_state", create_empty_retry_state())

        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self._invoke_with_fallback(
                        llm_messages, tools, llm_error, conversation_id,
                    )

                # Track token usage
                await self._track_token_usage(conversation_id, response)

                # Check for tool calls
                tool_calls = getattr(response, "tool_calls", None)

                if not tool_calls:
                    ai_response = response.content or ""
                    
                    # Constraint validation (anti-hallucination)
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        is_valid, error_injection = await self._validate_response_constraints(
                            ai_response,
                            list(tools_called),
                            state,
                            current_mode_context=mode_context,  # Phase 1B: use updated context
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
                            llm_messages.append({
                                "role": "system",
                                "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                            })
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        self._logger.error(
                            "constraint_retries_exhausted",
                            retries=validation_retries,
                            ai_response_preview=ai_response[:200],
                            tools_called=list(tools_called),
                            conversation_id=conversation_id,
                        )
                        ai_response = "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"
                    
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

                    # REFACTOR-001 Phase 2: Apply tool flags BEFORE extracting context
                    # BUG FIX: result is JSON string, parse explicitly for clarity
                    import json
                    result_dict = json.loads(result) if isinstance(result, str) else result
                    _apply_tool_flags(mode_context, result_dict, self._logger)

                    # Track all applied flags for final authority
                    parsed_flags = result_dict.get("_internal_flags", {}) if isinstance(result_dict, dict) else {}
                    all_applied_flags.update(parsed_flags)

                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name, tool_args, result,
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
                            # NOTE: imagenes_enviadas flag now managed by _internal_flags (REFACTOR-001)

                    # Apply structural context updates to mode_context
                    mode_context.update(context_updates)

                    llm_messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call_id,
                    })

                    # ═══════════════════════════════════════════════════════════
                    # PHASE 1A: Fast-path break on transition signal
                    # When a tool signals _transition_to, stop immediately.
                    # The tool's message IS the response — no extra LLM iteration.
                    # ═══════════════════════════════════════════════════════════
                    if mode_context.get("_transition_to"):
                        # Extract tool's message as the final ai_response
                        transition_message = ""
                        if isinstance(result_dict, dict):
                            transition_message = (
                                result_dict.get("message", "")
                                or result_dict.get("texto", "")
                            )
                        if transition_message:
                            ai_response = transition_message
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
                self._logger.warning(
                    "max_tool_iterations",
                    iterations=MAX_TOOL_ITERATIONS,
                )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, me ha llevado más tiempo del esperado. "
                        "¿Puedes repetir tu consulta?"
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

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: Persist retry state
            }

            # Propagate mode transition if signaled by a tool
            transition_target = updated_context.pop("_transition_to", None)
            transition_applied = False
            if transition_target:
                from agent.router.mode_transitions import validate_transition, get_preserve_keys
                from agent.state.conversation_state import transition_mode
                allowed, reason = validate_transition(self.mode_name, transition_target)
                if allowed:
                    preserve = get_preserve_keys(self.mode_name, transition_target)
                    transition_updates = transition_mode(
                        state, transition_target, preserve_keys=preserve,
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
            # Only chain if the transition was actually applied
            chain_signal = updated_context.pop("_chain_next_mode", None)
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
                updated_context.pop("_tarifa_actual")

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

    def get_tools(self) -> list:
        """Return tools available in PRESUPUESTO_MODE."""
        if self._tools is None:
            self._tools = _get_presupuesto_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers (shared pattern)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_llm(tools: list) -> ChatOpenAI:
        """Get configured LLM instance with tools bound."""
        settings = get_settings()

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=3000,  # Increased from 1500 to prevent truncation with large system prompts
            default_headers={
                "HTTP-Referer": settings.SITE_URL,
                "X-Title": settings.SITE_NAME,
            },
        )

        if tools:
            llm = llm.bind_tools(tools)

        return llm

    async def _invoke_with_fallback(
        self,
        messages: list[dict[str, Any]],
        tools: list,
        original_error: Exception,
        conversation_id: str,
    ) -> Any:
        """Try Ollama fallback when cloud LLM fails."""
        from openai import (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            APIStatusError,
        )

        if not isinstance(
            original_error,
            (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError),
        ):
            raise original_error

        self._logger.warning(
            "cloud_llm_failed_trying_ollama",
            error_type=type(original_error).__name__,
            conversation_id=conversation_id,
        )

        try:
            from langchain_ollama import ChatOllama

            settings = get_settings()
            ollama_llm = ChatOllama(
                model=settings.LOCAL_CAPABLE_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                temperature=0.3,
            )
            if tools:
                ollama_llm = ollama_llm.bind_tools(tools)

            response = await ollama_llm.ainvoke(messages)
            self._logger.info("ollama_fallback_succeeded", conversation_id=conversation_id)
            return response

        except Exception:
            self._logger.warning("ollama_fallback_failed", conversation_id=conversation_id)
            raise original_error

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
    ) -> dict[str, Any]:
        """
        Extract mode context updates from a tool call and its result.

        Same logic as ViabilidadModeNode, plus:
        - Tracks precio_comunicado for price-before-images enforcement
        - Tracks presupuesto_completado when price is calculated
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
                updates["pending_variants"] = []       # Clear variant questions
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = preguntas
                updates["elemento_confirmado"] = None  # Clear confirmed

            updates["categoria_slug"] = tool_args.get(
                "categoria_vehiculo",
                tool_args.get("categoria"),
            )

        elif tool_name == "seleccionar_variante_por_respuesta":
            if data.get("success") or data.get("codigo"):
                # REFACTOR-001: Removed variante_resuelta - derived from len(pending_variants) == 0
                updates["pending_variants"] = []
                code = data.get("codigo") or data.get("code")
                if code:
                    updates["elemento_confirmado"] = {
                        "code": code,
                        "name": data.get("nombre") or data.get("name", code),
                    }

        elif tool_name == "calcular_tarifa_con_elementos":
            # Handle nested structure: tool returns {texto, datos: {price, ...}, ...}
            # REFACTOR-001: Removed precio_calculado redundant field - use tarifa_calculada directly
            updates["tarifa_calculada"] = data  # Store full response including imagenes_ejemplo
            # NOTE: precio_comunicado and imagenes_enviadas flags are managed
            # in _process_message to avoid accessing mode_context in static method
            # NOTE: NO longer propagate to root state (_tarifa_actual removed)
            # Tools access tarifa_calculada directly from mode_context

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
        # Transition to EVALUACION_GATEWAY (confirm quote → open case)
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

