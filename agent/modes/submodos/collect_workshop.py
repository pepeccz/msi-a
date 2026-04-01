"""
Handler for EXPEDIENTE COLLECT_WORKSHOP sub-mode.

Asks whether the user provides their own workshop or uses MSI.
If own workshop: collects workshop data.

Tool: actualizar_datos_taller()
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from agent.modes.submodos._shared import _get_workshop_tools
from agent.state.conversation_state import ConversationState


class WorkshopHandler:
    """Handler for COLLECT_WORKSHOP sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to COLLECT_WORKSHOP."""
        return _get_workshop_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_WORKSHOP sub-mode.

        Delegates to the coordinator's LLM loop with workshop-data tools.
        mode_context is passed by reference — mutations inside llm_loop_fn
        propagate to the caller automatically.
        """
        tools = self.get_tools()
        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_WORKSHOP",
        )
