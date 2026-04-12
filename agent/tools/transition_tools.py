"""
MSI-a - Transition Tools.

Lightweight tools that signal mode transitions via _state_update.
These tools don't perform heavy business logic — they validate preconditions
and return a transition signal that the mode node propagates.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain.tools import tool

from langchain_core.runnables import RunnableConfig

from agent.state.helpers import get_tool_state
from agent.tools.schemas import ConfirmarPresupuestoInput

logger = structlog.get_logger(__name__)


@tool(args_schema=ConfirmarPresupuestoInput)
async def confirmar_presupuesto(config: RunnableConfig | None = None) -> dict[str, Any]:
    """
    Confirma que el usuario quiere proceder con el presupuesto y abrir un expediente de homologacion.

    Usa esta herramienta SOLO cuando el usuario confirme que quiere iniciar el expediente
    o proceder con la homologacion. Ejemplos de confirmacion del usuario:
    - "Dale", "Si", "Adelante", "Perfecto", "Venga"
    - "Quiero abrir el expediente"
    - "Vamos con la homologacion"
    - Opcion B (abrir expediente directamente)

    NO uses esta herramienta si:
    - El usuario pide ver fotos de ejemplo (usa enviar_imagenes_ejemplo)
    - El usuario hace otra pregunta
    - No se ha comunicado el precio todavia

    Returns:
        Dict con confirmacion y señal de transicion directa a EXPEDIENTE_MODE.
    """
    state = get_tool_state(config)
    if not state:
        return {
            "success": False,
            "error": "No se pudo obtener el contexto de la conversacion",
        }

    mode_context = state.get("mode_context", {})

    # Precondition: price must have been communicated
    if not mode_context.get("precio_comunicado"):
        logger.warning(
            "confirmar_presupuesto_no_price",
            conversation_id=state.get("conversation_id"),
        )
        return {
            "success": False,
            "message": (
                "No puedo iniciar el expediente todavia porque no se ha "
                "comunicado el precio. Primero calcula la tarifa."
            ),
            "error": "PRICE_NOT_COMMUNICATED",
        }

    # Precondition: tariff must exist
    tarifa = mode_context.get("tarifa_calculada")
    if not tarifa:
        return {
            "success": False,
            "message": "No hay tarifa calculada. Calcula primero el presupuesto.",
            "error": "NO_TARIFF",
        }

    # Extract summary for gateway
    element_codes = mode_context.get("element_codes", [])
    categoria = mode_context.get("categoria_slug", "desconocida")

    # Parse tarifa data
    precio = None
    if isinstance(tarifa, dict):
        datos = tarifa.get("datos", {})
        precio = datos.get("price")
    elif isinstance(tarifa, str):
        import json

        try:
            tarifa_parsed = json.loads(tarifa)
            datos = tarifa_parsed.get("datos", {})
            precio = datos.get("price")
        except (json.JSONDecodeError, TypeError):
            pass

    logger.info(
        "confirmar_presupuesto_ok",
        conversation_id=state.get("conversation_id"),
        precio=precio,
        elementos=element_codes,
        categoria=categoria,
    )

    return {
        "success": True,
        "message": "El usuario ha confirmado el presupuesto. Expediente en preparación.",
        "resumen": {
            "precio": precio,
            "elementos": element_codes,
            "categoria": categoria,
        },
        "_state_update": {
            "_transition_to": "EXPEDIENTE_MODE",
        },
    }


# Exports
TRANSITION_TOOLS = [confirmar_presupuesto]


def get_transition_tools() -> list:
    """Get all transition-related tools."""
    return TRANSITION_TOOLS


__all__ = [
    "confirmar_presupuesto",
    "get_transition_tools",
    "TRANSITION_TOOLS",
]
