"""
MSI-a - VIABILIDAD_MODE Node.

Evaluates whether a vehicle modification can be legally homologated.
Handles 65% of traffic — the main entry point for most users.

Flow:
    1. User describes what they want to homologate
    2. LLM uses tools to identify elements, resolve variants
    3. LLM calculates a price estimate (wide range ±30%)
    4. LLM communicates viability + price + documentation needed
    5. Offers transition to PRESUPUESTO_MODE for exact pricing

Recycled v1 tools:
    - identificar_y_resolver_elementos (element identification + variant detection)
    - seleccionar_variante_por_respuesta (variant resolution)
    - calcular_tarifa_con_elementos (tariff calculation)
    - identificar_tipo_vehiculo (vehicle classification)
    - listar_categorias (category listing)
    - listar_elementos (element listing)
    - obtener_documentacion_elemento (required docs for element)

Architecture:
    The LLM decides the conversation flow via tool calls. We do NOT
    hardcode the flow in Python — the system prompt guides the LLM to
    follow the correct sequence. This matches v1's successful pattern.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import format_messages_for_llm, compress_tool_result
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn (prevents infinite loops)
MAX_TOOL_ITERATIONS = 10


class ViabilidadModeNode(BaseModeNode):
    """
    VIABILIDAD_MODE: Evaluate if a modification can be homologated.

    Uses the LLM with recycled v1 tools to:
    - Identify elements from free-text descriptions
    - Resolve variant ambiguities
    - Calculate price estimates (wide range)
    - Assess viability and documentation needs

    The LLM drives the conversation — the system prompt defines
    the flow, and the mode node provides tools + context.
    """

    def __init__(self) -> None:
        super().__init__("VIABILIDAD_MODE")
        self._tools: list | None = None  # Lazy-loaded

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message in VIABILIDAD_MODE.

        Strategy:
        1. Assemble mode-specific system prompt
        2. Build LLM messages (system + history + user message)
        3. Run LLM → tool loop until we get a final text response
        4. Extract mode context updates from tool results
        5. Return ai_response + context updates
        """
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))
        messages = state.get("messages", [])

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="VIABILIDAD_MODE",
            mode_context=mode_context,
            client_context=client_context,
        )

        # ── 2. Build LLM messages ───────────────────────────────────────
        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history (formatted with security wrapping)
        llm_messages.extend(format_messages_for_llm(messages))

        # Add current user message (wrapped for security)
        llm_messages.append({
            "role": "user",
            "content": f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>",
        })

        # ── 3. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools()
        llm = self._get_llm(tools)

        # ── 4. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = await llm.ainvoke(llm_messages)
            except Exception as llm_error:
                # Try Ollama fallback on cloud LLM failure
                response = await self._invoke_with_fallback(
                    llm_messages, tools, llm_error, conversation_id,
                )

            # Track token usage
            await self._track_token_usage(conversation_id, response)

            # Check for tool calls
            tool_calls = getattr(response, "tool_calls", None)

            if not tool_calls:
                # Final text response — validate constraints before accepting
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
                            "constraint_retry",
                            retry=validation_retries,
                            max_retries=MAX_VALIDATION_RETRIES,
                        )
                        # Inject error and retry
                        llm_messages.append({
                            "role": "user",
                            "content": f"[SYSTEM VALIDATION ERROR]: {error_injection}",
                        })
                        continue  # Retry LLM call
                
                break  # Valid response or max retries reached

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

                # Execute the tool with timing + persistent logging
                result = await self._execute_and_log_tool(
                    conversation_id=conversation_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tools=tools,
                    iteration=iteration + 1,
                )

                # Extract context updates from tool results
                tool_context = self._extract_context_from_tool(
                    tool_name, tool_args, result,
                )
                context_updates.update(tool_context)

                # Add tool result to messages
                llm_messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id,
                })
        else:
            # Exhausted iterations — use whatever response we have
            self._logger.warning(
                "max_tool_iterations",
                iterations=MAX_TOOL_ITERATIONS,
            )
            if not ai_response:
                ai_response = response.content or (
                    "Disculpá, me llevó más tiempo del esperado. "
                    "¿Podés repetir tu consulta?"
                )

        # ── 5. Build state updates ───────────────────────────────────────
        updated_context = {**mode_context, **context_updates}

        result: dict[str, Any] = {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

        # Check if we should send images
        # (populated if calcular_tarifa was called and images were requested)
        if context_updates.get("pending_images"):
            result["pending_images"] = context_updates.pop("pending_images")

        self._logger.info(
            "viabilidad_response",
            response_length=len(ai_response),
            tools_called=list(tools_called),
            context_keys=list(context_updates.keys()),
        )

        return result

    def get_tools(self) -> list:
        """Return tools available in VIABILIDAD_MODE."""
        if self._tools is None:
            self._tools = _get_viabilidad_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers
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
            max_tokens=1500,
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

        # Only fallback on transient errors
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

        This keeps mode_context in sync with what the tools have done,
        so the prompt's MODE CONTEXT section stays accurate.
        """
        import json

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
                # All elements ready
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
                # Promote to confirmed
                code = data.get("codigo") or data.get("code")
                if code:
                    updates["elemento_confirmado"] = {
                        "code": code,
                        "name": data.get("nombre") or data.get("name", code),
                    }

        elif tool_name == "calcular_tarifa_con_elementos":
            precio = data.get("precio_final") or data.get("price") or data.get("total")
            if precio:
                updates["estimacion_precio"] = [
                    int(float(precio) * 0.85),
                    int(float(precio) * 1.15),
                ]
                updates["tarifa_calculada"] = data
                updates["precio_comunicado"] = True

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

        return updates

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

# ---------------------------------------------------------------------------
# Tool registry for VIABILIDAD_MODE
# ---------------------------------------------------------------------------

def _get_viabilidad_tools() -> list:
    """
    Get the tool set for VIABILIDAD_MODE.

    Recycles existing v1 tools that are relevant for viability evaluation.
    These tools are well-tested and handle the full element identification
    and pricing flow.
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
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element identification & resolution
        identificar_y_resolver_elementos,
        seleccionar_variante_por_respuesta,
        # Pricing (wide estimate)
        calcular_tarifa_con_elementos,
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
