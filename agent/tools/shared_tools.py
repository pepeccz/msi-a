"""
MSI-a current - Shared Tools.

Universal tools available in ALL conversation modes.

These tools are always bound to the LLM regardless of the current mode.
Mode-specific tools are added by each mode's ``get_tools()`` method.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from langchain_core.runnables import RunnableConfig

from agent.state.helpers import get_tool_state

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class EscalarAHumanoInput(BaseModel):
    """Input schema for escalar_a_humano tool."""

    motivo: str = Field(
        description=(
            "Motivo de la escalación. Ejemplos: "
            "'El usuario quiere hablar con una persona', "
            "'Caso técnicamente complejo', "
            "'Error recurrente en el proceso'"
        ),
    )
    es_error_tecnico: bool = Field(
        default=False,
        description="True si la escalación es por un error técnico del sistema",
    )
    contexto: str = Field(
        default="",
        description="Resumen breve del contexto de la conversación",
    )


# ---------------------------------------------------------------------------
# Universal tools
# ---------------------------------------------------------------------------


@tool(args_schema=EscalarAHumanoInput)
async def escalar_a_humano(
    motivo: str,
    es_error_tecnico: bool = False,
    contexto: str = "",
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Conectar al usuario con un agente humano de MSI Automotive.

    Usa esta herramienta cuando:
    - El usuario lo pide explícitamente ("quiero hablar con una persona")
    - El caso es demasiado complejo para resolver automáticamente
    - Hay errores recurrentes que no se pueden resolver
    - El usuario está frustrado o insatisfecho

    IMPORTANTE: Siempre incluye un motivo claro para la escalación.
    """
    from agent.services.escalation_service import perform_escalation

    # Get conversation context (prefer RunnableConfig, fall back to ContextVar)
    state = get_tool_state(config)
    if not state:
        logger.error("escalar_a_humano_no_state")
        return {
            "success": False,
            "message": (
                "Lo siento, tuve un problema técnico al escalar. "
                "Por favor, intenta de nuevo o contacta directamente "
                "con MSI Automotive."
            ),
            "escalation_triggered": False,
            "terminate_processing": False,
        }

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")
    user_phone = state.get("user_phone", "desconocido")

    if not conversation_id:
        logger.error("escalar_a_humano_no_conversation_id")
        return {
            "success": False,
            "message": (
                "Lo siento, no pude identificar la conversación. "
                "Por favor, contacta directamente con MSI Automotive."
            ),
            "escalation_triggered": False,
            "terminate_processing": False,
        }

    logger.info(
        "tool_escalar_a_humano",
        conversation_id=conversation_id,
        motivo=motivo,
        es_error_tecnico=es_error_tecnico,
        contexto_preview=contexto[:100] if contexto else "",
    )

    result = await perform_escalation(
        conversation_id=str(conversation_id),
        user_id=str(user_id) if user_id else None,
        user_phone=str(user_phone),
        reason=motivo,
        source="tool_call",
        is_technical_error=es_error_tecnico,
    )

    # Add flags that the mode node uses to stop processing
    result["escalation_triggered"] = True
    result["tool_name"] = "escalar_a_humano"

    # ADR-005 / ADR-010: declare state changes via _state_update.
    # Tombstone last_cta_emitted so merge_dicts overwrites the stale "cta_5"
    # value from the Redis checkpoint (explicit None required, absence preserves).
    result["_state_update"] = {"last_cta_emitted": None}

    return result


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def get_shared_tools() -> list:
    """
    Return the list of universal tools available in all modes.

    These are always included when binding tools to the LLM,
    regardless of the current conversation mode.
    """
    return [
        escalar_a_humano,
    ]
