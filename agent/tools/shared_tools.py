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
) -> str:
    """Conectar al usuario con un agente humano de MSI Automotive.

    Usa esta herramienta cuando:
    - El usuario lo pide explícitamente ("quiero hablar con una persona")
    - El caso es demasiado complejo para resolver automáticamente
    - Hay errores recurrentes que no se pueden resolver
    - El usuario está frustrado o insatisfecho

    IMPORTANTE: Siempre incluí un motivo claro para la escalación.
    """
    logger.info(
        "tool_escalar_a_humano",
        motivo=motivo,
        es_error_tecnico=es_error_tecnico,
        contexto_preview=contexto[:100] if contexto else "",
    )

    # In production this will:
    # 1. Create an Escalation record in the database
    # 2. Assign the Chatwoot conversation to a human team
    # 3. Add labels to the conversation
    # For now, return a confirmation message

    return (
        "Escalación registrada correctamente. "
        "Un agente humano atenderá al usuario en breve. "
        f"Motivo: {motivo}"
    )


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
