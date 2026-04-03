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
from agent.modes.generic_loop import GenericLoopResult, generic_llm_loop
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
        """Process a user message in CONSULTA_MODE via generic loop."""
        return await self._process_with_generic_loop(message, state)

    async def _process_with_generic_loop(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a message by delegating to generic_llm_loop().

        Minimal wiring for T2.4:
        1. Assemble system prompt (reuse existing builder).
        2. Build LLM via _get_llm() (injects credentials, tools, max_tokens).
        3. Call generic_llm_loop() with on_tool_result=None — consulta has no
           complex state extraction from tools.
        4. Merge result.context_updates into mode_context and return.

        """
        conversation_id = str(state.get("conversation_id", "unknown"))
        mode_context = dict(state.get("mode_context") or {})
        messages = state.get("messages", [])

        # Enrich mode_context with runtime flags (same as old loop)
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # 1. Build system prompt (identical to old loop)
        client_context = self._build_client_context(state)
        system_prompt = assemble_system_prompt(
            mode="CONSULTA_MODE",
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
        tools = self.get_tools()
        llm = self._get_llm(tools)

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
            # 5. Delegate to generic_llm_loop
            # on_tool_result=None — consulta has no complex state extraction
            loop_result: GenericLoopResult = await generic_llm_loop(
                system_prompt=system_prompt,
                messages=llm_history,
                tools=tools,
                max_iterations=8,
                conversation_id=conversation_id,
                mode_name="CONSULTA_MODE",
                state=full_state,
                llm=llm,
                on_tool_result=None,
            )

            # 6. Merge all updates into mode_context
            updated_context = {
                **mode_context,
                **loop_result.context_updates,
            }

            self._logger.info(
                "consulta_generic_loop_response",
                exit_reason=loop_result.exit_reason,
                tools_called=list(loop_result.tools_called),
                response_length=len(loop_result.ai_response),
                conversation_id=conversation_id,
            )

            return {
                "ai_response": loop_result.ai_response,
                "mode_context": updated_context,
            }

        finally:
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()
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
