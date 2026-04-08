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

Architecture (Phase 2):
    Uses build_mode_tool_loop() when "CONSULTA_MODE" is in TOOLNODE_ENABLED_MODES.
    Falls back to generic_llm_loop for backward compatibility when flag is off.
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
from agent.modes.tool_loop import build_mode_tool_loop, ModeLoopConfig
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

    When TOOLNODE_ENABLED_MODES includes "CONSULTA_MODE", uses the new
    build_mode_tool_loop() subgraph engine. Otherwise falls back to
    generic_llm_loop for backward compatibility.
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

        Routes to the new ToolNode subgraph engine if CONSULTA_MODE is in
        TOOLNODE_ENABLED_MODES, otherwise uses the legacy generic_llm_loop.
        """
        # Always use the new ToolNode engine (generic_llm_loop deleted in T-25).
        # Feature flag TOOLNODE_ENABLED_MODES is no longer needed for CONSULTA
        # since the fallback is removed.
        return await self._process_with_tool_loop(message, state)

    async def _process_with_tool_loop(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process using the new build_mode_tool_loop() subgraph engine (AD-1).

        Advantages over generic_llm_loop:
        - No ContextVar staleness (tools access state via RunnableConfig)
        - Proper AIMessage → ToolMessage protocol (no inject_messages)
        - Clean state accumulation via pending_state_updates
        - LangGraph-native recursion_limit guard
        """
        conversation_id = str(state.get("conversation_id", "unknown"))
        mode_context = dict(state.get("mode_context") or {})
        messages = list(state.get("messages", []))

        # Enrich mode_context with runtime flags
        mode_context["_is_first_interaction"] = state.get("is_first_interaction", False)

        # Build client context for the prompt
        client_context = self._build_client_context(state)

        # Build ModeLoopConfig with CONSULTA-specific settings
        config = ModeLoopConfig(
            mode_name="CONSULTA_MODE",
            get_tools=lambda ctx: _get_consulta_tools(),
            get_system_prompt=lambda loop_state: assemble_system_prompt(
                mode="CONSULTA_MODE",
                mode_context=loop_state.get("_mode_context", mode_context),
                client_context=client_context,
            ),
            post_tool_hook=None,  # CONSULTA has no complex post-tool domain logic
            max_iterations=MAX_TOOL_ITERATIONS,
        )

        # Build and compile the subgraph
        subgraph = build_mode_tool_loop(config)

        # Format conversation history for the inner loop
        llm_history = list(format_messages_for_llm(messages))

        # Build initial ToolLoopState
        from langchain_core.messages import HumanMessage

        initial_state = {
            "messages": llm_history
            + [HumanMessage(content=f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>")],
            "_mode_context": mode_context,
            "_conversation_id": conversation_id,
            "_mode_name": "CONSULTA_MODE",
        }

        # Invoke the subgraph
        loop_result = await subgraph.ainvoke(initial_state)

        # Extract result fields
        ai_response = loop_result.get("ai_response", "")
        exit_reason = loop_result.get("exit_reason", "response")
        tools_called = loop_result.get("tools_called", [])
        pending_updates = loop_result.get("pending_state_updates", {})

        # Merge pending_state_updates into mode_context
        updated_context = {**mode_context, **pending_updates}

        self._logger.info(
            "consulta_tool_loop_response",
            exit_reason=exit_reason,
            tools_called=tools_called,
            response_length=len(ai_response),
            conversation_id=conversation_id,
        )

        return {
            "ai_response": ai_response,
            "mode_context": updated_context,
        }

    # _process_with_generic_loop removed in T-25 (generic_loop.py deleted).
    # CONSULTA always uses _process_with_tool_loop now.

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
