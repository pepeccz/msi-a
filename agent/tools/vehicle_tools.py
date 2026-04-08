"""
MSI Automotive - Vehicle Type Identification Tool.

Thin wrapper over VehicleClassificationService.
Business logic lives in agent/services/vehicle_classification_service.py.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from agent.services.vehicle_classification_service import classify_vehicle
from langchain_core.runnables import RunnableConfig

from agent.state.helpers import get_tool_state
from agent.tools.schemas import IdentificarTipoVehiculoInput
from agent.utils.errors import ErrorCategory, handle_tool_errors

logger = logging.getLogger(__name__)


@tool(args_schema=IdentificarTipoVehiculoInput)
@handle_tool_errors(
    error_category=ErrorCategory.LLM_ERROR,
    error_code="VEHICLE_CLASSIFICATION_FAILED",
    user_message="Lo siento, no pude identificar el tipo de vehículo. ¿Podrías confirmarme qué tipo de vehículo tienes?",
)
async def identificar_tipo_vehiculo(
    marca: str, modelo: str, config: RunnableConfig | None = None
) -> dict[str, Any]:
    """
    Identifica el tipo de vehiculo a partir de su marca y modelo.

    Usa esta herramienta cuando el usuario mencione un vehiculo especifico
    (como "Honda CBF600", "Mercedes Sprinter", "Hymer B-Klasse") y necesites
    determinar a que categoria pertenece para poder usar las herramientas
    de tarifas correctas.

    Args:
        marca: Marca del vehiculo (ej: "Honda", "Mercedes", "Hymer", "Yamaha")
        modelo: Modelo del vehiculo (ej: "CBF600", "Sprinter", "B-Klasse", "MT-07")

    Returns:
        Dict con:
        - success: bool
        - message: str (user-facing message)
        - data: dict with tipo, confianza, categoria_sugerida, descripcion, pedir_confirmacion
        - tool_name: str
    """
    state = get_tool_state(config)
    client_type = state.get("client_type", "particular")

    result_data = await classify_vehicle(
        marca=marca,
        modelo=modelo,
        client_type=client_type,
    )

    success = result_data["tipo"] != "desconocido" or result_data["confianza"] != "baja"
    if result_data["_provider"] == "none":
        success = False

    if success:
        return {
            "success": True,
            "message": f"Vehículo identificado como {result_data['tipo']} ({result_data['confianza']})",
            "data": result_data,
            "tool_name": "identificar_tipo_vehiculo",
        }

    return {
        "success": False,
        "message": (
            f"No pude identificar el tipo de vehículo "
            f"{result_data['marca']} {result_data['modelo']}. "
            "Por favor, indícame qué tipo de vehículo es."
        ),
        "data": result_data,
        "tool_name": "identificar_tipo_vehiculo",
    }


# Export tools list
VEHICLE_TOOLS = [identificar_tipo_vehiculo]


def get_vehicle_tools() -> list:
    """Get all vehicle identification tools."""
    return VEHICLE_TOOLS


__all__ = [
    "identificar_tipo_vehiculo",
    "get_vehicle_tools",
    "VEHICLE_TOOLS",
]
