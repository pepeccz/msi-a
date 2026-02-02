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
    - consultar_documentacion_rag (RAG query for regulatory docs)
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

from datetime import datetime, UTC
from typing import Any

import structlog
from langchain_openai import ChatOpenAI

from agent.modes.base_mode import BaseModeNode
from agent.state.conversation_state import ConversationState
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import format_messages_for_llm
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 8


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
        """
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))
        messages = state.get("messages", [])

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="CONSULTA_MODE",
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

        # ── 3. First interaction greeting ────────────────────────────────
        is_first = state.get("is_first_interaction", False)
        if is_first and not messages:
            # Inject greeting context
            llm_messages.insert(-1, {
                "role": "system",
                "content": (
                    "Esta es la PRIMERA interacción del usuario. "
                    "Saluda brevemente y ofrece ayuda. "
                    "NO hagas preguntas múltiples — sé conciso."
                ),
            })

        # ── 4. Get LLM with tools ───────────────────────────────────────
        tools = self.get_tools()
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = await llm.ainvoke(llm_messages)
            except Exception as llm_error:
                response = await self._invoke_with_fallback(
                    llm_messages, tools, llm_error, conversation_id,
                )

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
                            "constraint_retry",
                            retry=validation_retries,
                            max_retries=MAX_VALIDATION_RETRIES,
                        )
                        llm_messages.append({
                            "role": "user",
                            "content": f"[SYSTEM VALIDATION ERROR]: {error_injection}",
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
                    iteration=iteration + 1,
                )

                result = await self._execute_tool(tool_name, tool_args, tools)

                # Track consultas for analytics
                if tool_name == "consultar_documentacion_rag":
                    history = context_updates.get(
                        "consulta_history",
                        mode_context.get("consulta_history", []),
                    )
                    history = list(history)  # copy
                    history.append({
                        "question": tool_args.get("consulta", message),
                        "answered": True,
                    })
                    context_updates["consulta_history"] = history

                llm_messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id,
                })
        else:
            if not ai_response:
                ai_response = response.content or (
                    "Disculpá, no pude completar la búsqueda. "
                    "¿Podés reformular tu pregunta?"
                )

        # ── 6. Build state updates ───────────────────────────────────────
        updated_context = {**mode_context, **context_updates}

        self._logger.info(
            "consulta_response",
            response_length=len(ai_response),
            consultas_count=len(updated_context.get("consulta_history", [])),
        )

        return {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

    def get_tools(self) -> list:
        """Return tools available in CONSULTA_MODE."""
        if self._tools is None:
            self._tools = _get_consulta_tools()
        return self._tools

    # ------------------------------------------------------------------
    # LLM helpers (shared pattern with ViabilidadModeNode)
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
            self._logger.info("ollama_fallback_succeeded")
            return response

        except Exception:
            self._logger.warning("ollama_fallback_failed")
            raise original_error

    # ------------------------------------------------------------------
    # Tool execution (same pattern as ViabilidadModeNode)
    # ------------------------------------------------------------------

    @staticmethod
    async def _execute_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        tools: list,
    ) -> str:
        """Execute a tool by name and return its string result."""
        tool_fn = None
        for t in tools:
            if t.name == tool_name:
                tool_fn = t
                break

        if tool_fn is None:
            return f"Error: herramienta '{tool_name}' no encontrada"

        try:
            result = await tool_fn.ainvoke(tool_args)
            if isinstance(result, dict):
                import json
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            logger.error("tool_execution_error", tool=tool_name, error=str(e))
            return f"Error ejecutando {tool_name}: {str(e)}"

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

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ConsultarDocumentacionInput(BaseModel):
    """Input schema for consultar_documentacion_rag tool."""

    consulta: str = Field(
        description=(
            "La pregunta del usuario sobre homologación, normativa, "
            "procesos, plazos, requisitos, etc. Escríbela en español."
        ),
    )


@tool(args_schema=ConsultarDocumentacionInput)
async def consultar_documentacion_rag(consulta: str) -> str:
    """Buscar información en la documentación regulatoria de homologación.

    Usa esta herramienta para responder preguntas generales sobre:
    - Qué es la homologación y cómo funciona
    - Normativa y reglamentos aplicables
    - Plazos y procesos típicos
    - Requisitos generales de documentación
    - Obligaciones legales

    Args:
        consulta: La pregunta del usuario en español.

    Returns:
        Respuesta basada en documentación oficial con citas.
        Si no hay información disponible, lo indica claramente.
    """
    try:
        from api.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        result = await rag_service.query(query_text=consulta)

        answer = result.get("answer", "")
        citations = result.get("citations", [])

        if not answer:
            return (
                "No encontré información específica sobre eso en la "
                "documentación disponible. Puedo conectarte con un "
                "especialista si necesitás información más detallada."
            )

        # Format citations if available
        response = answer
        if citations:
            source_names = list({
                c.get("document_title", "Documento")
                for c in citations[:3]
            })
            response += f"\n\n_Fuentes: {', '.join(source_names)}_"

        return response

    except Exception as e:
        logger.error("rag_query_error", error=str(e))
        return (
            "No pude consultar la documentación en este momento. "
            "Puedo responder basándome en información general, "
            "o conectarte con un agente que te ayude."
        )


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
        # RAG documentation search
        consultar_documentacion_rag,
        # Catalog browsing
        listar_categorias,
        listar_elementos,
        # Additional services info
        obtener_servicios_adicionales,
        # Universal
        escalar_a_humano,
    ]

