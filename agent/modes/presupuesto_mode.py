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
from agent.state.conversation_state import ConversationState
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import format_messages_for_llm, set_current_state, clear_current_state
from agent.tools.image_tools import set_current_state_for_image_tools, clear_image_tools_state
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10


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
        # CRITICAL: Tools like enviar_imagenes_ejemplo and case_tools need state
        # via ContextVars. Set before tool execution, clear in finally block.
        state_dict = cast(dict[str, Any], state)
        set_current_state(state_dict)
        set_current_state_for_image_tools(state_dict)

        # ── 4. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools()
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        pending_images: dict[str, Any] | None = None
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2

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

                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name, tool_args, result,
                    )
                    context_updates.update(tool_context)

                    # Extract pending images from enviar_imagenes_ejemplo
                    if tool_name == "enviar_imagenes_ejemplo":
                        images_data = self._extract_pending_images(result)
                        if images_data:
                            pending_images = images_data
                            context_updates["imagenes_enviadas"] = True

                    llm_messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call_id,
                    })
            else:
                self._logger.warning(
                    "max_tool_iterations",
                    iterations=MAX_TOOL_ITERATIONS,
                )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpá, me llevó más tiempo del esperado. "
                        "¿Podés repetir tu consulta?"
                    )

            # ── 6. Build state updates ───────────────────────────────────────
            updated_context = {**mode_context, **context_updates}

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
            }

            # Bubble up pending images for the main node to send
            if pending_images:
                result_dict["pending_images"] = pending_images

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
            listos = data.get("elementos_listos", [])
            variantes = data.get("elementos_con_variantes", [])
            preguntas = data.get("preguntas_variantes", [])

            if listos and not variantes:
                updates["elemento_confirmado"] = listos[0] if len(listos) == 1 else None
                updates["element_codes"] = [e.get("codigo") for e in listos]
                updates["variante_resuelta"] = True
            elif variantes:
                updates["elemento_tentativo"] = variantes[0]
                updates["variante_resuelta"] = False
                updates["pending_variants"] = preguntas

            updates["categoria_slug"] = tool_args.get(
                "categoria_vehiculo",
                tool_args.get("categoria"),
            )

        elif tool_name == "seleccionar_variante_por_respuesta":
            if data.get("success") or data.get("codigo"):
                updates["variante_resuelta"] = True
                updates["pending_variants"] = []
                code = data.get("codigo") or data.get("code")
                if code:
                    updates["elemento_confirmado"] = {
                        "code": code,
                        "name": data.get("nombre") or data.get("name", code),
                    }

        elif tool_name == "calcular_tarifa_con_elementos":
            precio = data.get("precio_final") or data.get("price") or data.get("total")
            if precio:
                updates["precio_calculado"] = float(precio)  # Renamed from precio_exacto
                updates["tarifa_calculada"] = data
                # precio_comunicado is set when LLM mentions the price in text

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
            if data.get("success"):
                updates["imagenes_enviadas"] = True

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

    Full element identification + pricing + image tools + iniciar_expediente.
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
    from agent.tools.case_tools import iniciar_expediente
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element identification & resolution
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        # Exact pricing
        calcular_tarifa_con_elementos,
        # Example images (after price communication)
        enviar_imagenes_ejemplo,
        # Expediente initiation (shortcut from PRESUPUESTO)
        iniciar_expediente,
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

