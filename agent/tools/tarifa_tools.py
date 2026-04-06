"""
MSI Automotive - Tarifa Tools for LangGraph Agent.

These tools allow the conversational agent to calculate tariffs
and retrieve documentation for vehicle homologations.
"""

import logging
import uuid
from datetime import datetime, UTC, timedelta
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import select

from agent.services.tarifa_service import get_tarifa_service
from agent.state.helpers import get_current_state
from agent.tools.schemas import (
    ListarCategoriasInput,
    ListarTarifasInput,
    ObtenerServiciosAdicionalesInput,
)
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.utils.tool_helpers import tool_error_response
from database.connection import get_async_session
from database.models import Escalation
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Cache TTL for duplicate escalation prevention (5 minutes)
# Prevents multiple escalations from being created in quick succession
CACHE_TTL_MINUTES = 5


@tool(args_schema=ListarCategoriasInput)
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="CATEGORY_LIST_FAILED",
    user_message="Lo siento, no pude obtener las categorías disponibles. ¿Puedes intentarlo de nuevo?",
)
async def listar_categorias() -> dict[str, Any]:
    """
    Lista las categorías de vehículos disponibles para homologación.

    Use this tool when the user asks what types of vehicles can be homologated,
    or when you need to know what categories are available.

    IMPORTANT: This tool filters categories dynamically based on:
    - Client type from context (particular/professional)
    - Availability of active tariffs for that client type in the database

    Returns:
        List of available vehicle categories with their descriptions.
    """
    service = get_tarifa_service()

    # Get current state to determine client_type
    state = get_current_state()
    client_type = state.get("client_type", "particular") if state else "particular"

    # Get categories dynamically from database (only those with active tariffs for this client_type)
    categories = await service.get_supported_categories_for_client(client_type)

    if not categories:
        return {
            "success": True,
            "message": f"No hay categorías de vehículos disponibles para clientes de tipo '{client_type}'.",
            "data": {"categories": []},
            "tool_name": "listar_categorias",
        }

    lines = ["CATEGORIAS DE VEHICULOS DISPONIBLES:", ""]
    for cat in categories:
        lines.append(f"- {cat['name']} ({cat['slug']})")
        if cat.get("description"):
            lines.append(f"  {cat['description']}")

    return {
        "success": True,
        "message": "\n".join(lines),
        "data": {"categories": categories},
        "tool_name": "listar_categorias",
    }


@tool(args_schema=ListarTarifasInput)
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="TARIFF_LIST_FAILED",
    user_message="Lo siento, no pude obtener las tarifas. ¿Puedes intentarlo de nuevo?",
)
async def listar_tarifas(categoria_vehiculo: str, tipo_cliente: str = "particular") -> dict[str, Any]:
    """
    Lista las tarifas disponibles para una categoría de vehículo.

    Use this tool when the user wants to know what pricing tiers exist
    or what types of homologations are available.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        tipo_cliente: "particular" o "professional"

    Returns:
        List of tariff tiers with prices and conditions.
    """
    # Normalize category slug (LLM may send uppercase)
    categoria_vehiculo = categoria_vehiculo.lower().strip()
    
    service = get_tarifa_service()
    data = await service.get_category_data(categoria_vehiculo)

    if not data:
        categories = await service.get_active_categories()
        available = ", ".join(c["slug"] for c in categories)
        return {
            "success": False,
            "message": f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {available}",
            "data": {"available_categories": [c["slug"] for c in categories]},
            "tool_name": "listar_tarifas",
        }

    lines = [
        f"TARIFAS PARA {data['category']['name'].upper()} ({tipo_cliente.capitalize()}):",
        "",
        "Precios SIN IVA:",
        "",
    ]

    for tier in data["tiers"]:
        lines.append(f"- {tier['name']}: {tier['price']} EUR + IVA")
        if tier.get("conditions"):
            lines.append(f"  {tier['conditions']}")

        # Show keywords if available
        rules = tier.get("classification_rules") or {}
        keywords = rules.get("applies_if_any", [])
        if keywords:
            lines.append(f"  Aplica para: {', '.join(keywords[:5])}" + ("..." if len(keywords) > 5 else ""))

        lines.append("")

    return {
        "success": True,
        "message": "\n".join(lines),
        "data": {
            "category": data['category'],
            "tiers": data["tiers"],
        },
        "tool_name": "listar_tarifas",
    }


@tool(args_schema=ObtenerServiciosAdicionalesInput)
@handle_tool_errors(
    error_category=ErrorCategory.DATABASE_ERROR,
    error_code="SERVICES_LIST_FAILED",
    user_message="Lo siento, no pude obtener los servicios adicionales. ¿Puedes intentarlo de nuevo?",
)
async def obtener_servicios_adicionales(categoria_vehiculo: str = "") -> dict[str, Any]:
    """
    Obtiene los servicios adicionales disponibles (certificados, urgencias, etc.).

    Use this tool when the user asks about additional services like:
    - Workshop certificates
    - Rush processing
    - Brake testing

    Args:
        categoria_vehiculo: Opcional. Categoría para ver servicios específicos.

    Returns:
        List of available additional services with prices.
    """
    service = get_tarifa_service()

    # Normalize category slug if provided (LLM may send uppercase)
    if categoria_vehiculo:
        categoria_vehiculo = categoria_vehiculo.lower().strip()

    if categoria_vehiculo:
        data = await service.get_category_data(categoria_vehiculo)
        if data:
            services = data.get("additional_services", [])
        else:
            services = []
    else:
        # Get services from any category (they're global anyway)
        categories = await service.get_active_categories()
        if categories:
            data = await service.get_category_data(categories[0]["slug"])
            services = data.get("additional_services", []) if data else []
        else:
            services = []

    if not services:
        return {
            "success": True,
            "message": "No hay servicios adicionales disponibles en este momento.",
            "data": {"services": []},
            "tool_name": "obtener_servicios_adicionales",
        }

    lines = ["SERVICIOS ADICIONALES DISPONIBLES:", ""]
    for s in services:
        lines.append(f"- {s['name']}: {s['price']} EUR")
        if s.get("description"):
            lines.append(f"  {s['description']}")

    return {
        "success": True,
        "message": "\n".join(lines),
        "data": {"services": services},
        "tool_name": "obtener_servicios_adicionales",
    }


# Export all tools (only non-redundant ones)
ALL_TOOLS = [
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
]


def get_tarifa_tools() -> list:
    """Get all tariff-related tools for the agent."""
    return ALL_TOOLS


__all__ = [
    "listar_categorias",
    "listar_tarifas",
    "obtener_servicios_adicionales",
    "get_tarifa_tools",
    "ALL_TOOLS",
]
