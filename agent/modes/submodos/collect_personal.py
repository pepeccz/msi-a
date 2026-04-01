"""
Handler for EXPEDIENTE COLLECT_PERSONAL sub-mode.

Collects personal data: nombre, apellidos, email, teléfono, DNI/CIF,
domicilio, ITV.

Tool: actualizar_datos_expediente(datos_personales={...})
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from agent.modes.submodos._shared import _get_personal_tools
from agent.state.conversation_state import ConversationState


class PersonalHandler:
    """Handler for COLLECT_PERSONAL sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to COLLECT_PERSONAL."""
        return _get_personal_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_PERSONAL sub-mode.

        Delegates to the coordinator's LLM loop with personal-data tools.
        mode_context is passed by reference — mutations inside llm_loop_fn
        propagate to the caller automatically.
        """
        tools = self.get_tools()
        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_PERSONAL",
        )
