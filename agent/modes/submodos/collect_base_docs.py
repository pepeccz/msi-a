"""
Handler for EXPEDIENTE COLLECT_BASE_DOCS sub-mode.

User sends base documentation (ficha técnica, permiso, vistas).
Tool: confirmar_documentacion_base()
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

import structlog

from agent.modes.submodos._shared import _get_base_docs_tools
from agent.state.conversation_state import ConversationState

logger = structlog.get_logger(__name__)


class BaseDocsHandler:
    """Handler for COLLECT_BASE_DOCS sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to COLLECT_BASE_DOCS."""
        return _get_base_docs_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_BASE_DOCS sub-mode.

        Guard: image-only turns (no text) are acknowledged deterministically
        without invoking the LLM. When the user sends text, delegates to the
        coordinator's LLM loop with base-docs tools.
        """
        # ── Guard: image-only turns (no text) ─────────────────────────────
        incoming_attachments = state.get("incoming_attachments", [])
        if not message.strip() and incoming_attachments:
            ack = (
                f"Recibidas {len(incoming_attachments)} foto(s) de documentación base. "
                'Cuando hayas terminado de enviar documentos, escribe "listo".'
            )
            logger.info(
                "image_only_turn_ack",
                conversation_id=state.get("conversation_id", "unknown"),
                image_count=len(incoming_attachments),
                sub_mode="COLLECT_BASE_DOCS",
            )
            return {
                "ai_response": ack,
                "mode_context": mode_context,
            }

        tools = self.get_tools()
        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_BASE_DOCS",
        )
