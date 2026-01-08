"""
MSI Automotive - Tariff Tools for LangGraph Agent.

These tools allow the conversational agent to calculate tariffs
and retrieve documentation for vehicle homologations.
"""

import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from langchain_core.tools import tool

from agent.services.tarifa_service import get_tarifa_service
from agent.state.helpers import get_current_state
from database.connection import get_async_session
from database.models import Escalation
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings

logger = logging.getLogger(__name__)


@tool
async def listar_categorias() -> str:
    """
    Lista las categorías de vehículos disponibles para homologación.

    Use this tool when the user asks what types of vehicles can be homologated,
    or when you need to know what categories are available.

    IMPORTANT: This tool filters categories by client_type from context.
    Particulares only see "motos", profesionales only see "aseicars".

    Returns:
        List of available vehicle categories with their descriptions.
    """
    service = get_tarifa_service()

    # Get current state to determine client_type
    state = get_current_state()
    client_type = state.get("client_type", "particular") if state else "particular"

    categories = await service.get_active_categories()

    if not categories:
        return "No hay categorías de vehículos disponibles en este momento."

    # Filter categories by client_type
    # Mapping: particular -> motos, professional -> aseicars
    if client_type == "particular":
        categories = [c for c in categories if c["slug"] == "motos"]
    elif client_type == "professional":
        categories = [c for c in categories if c["slug"] == "aseicars"]

    if not categories:
        return f"No hay categorías disponibles para clientes de tipo '{client_type}'."

    lines = ["Categorias de vehiculos disponibles:", ""]
    for cat in categories:
        lines.append(f"• {cat['name']} ({cat['slug']})")
        if cat.get("description"):
            lines.append(f"  {cat['description']}")

    return "\n".join(lines)


@tool
async def calcular_tarifa(
    categoria_vehiculo: str,
    descripcion_elementos: str,
    tipo_cliente: str = "particular",
) -> str:
    """
    Calcula el precio de homologación según la categoría de vehículo y los elementos a modificar.

    Use this tool when the user wants to know the price for homologating specific modifications.
    IMPORTANT: Always use this tool before providing a price estimate.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        descripcion_elementos: Descripción en lenguaje natural de los elementos a homologar.
                              Ejemplo: "escalera mecánica y toldo lateral"
                                       "placas solares en el techo y antena parabólica"
        tipo_cliente: "particular" o "professional" (profesional/taller)

    Returns:
        Calculated tariff with price, tier, breakdown, and warnings.
        IMPORTANT: Los precios NO incluyen IVA. Siempre indicar "+IVA" al usuario.
    """
    service = get_tarifa_service()

    # =========================================================================
    # VALIDACIÓN: Coherencia entre tipo_cliente y categoria_vehiculo
    # =========================================================================
    if tipo_cliente == "particular" and categoria_vehiculo != "motos":
        return (
            "Error: Los particulares solo pueden homologar MOTOCICLETAS. "
            f"La categoría '{categoria_vehiculo}' no está disponible para particulares. "
            "Si el usuario tiene un vehículo diferente a una moto, explícale que debe "
            "contactar directamente con MSI Automotive (msi@msihomologacion.com) o escalar a un agente humano."
        )

    if tipo_cliente == "professional" and categoria_vehiculo != "aseicars":
        return (
            "Error: Los profesionales solo pueden homologar AUTOCARAVANAS (aseicars). "
            f"La categoría '{categoria_vehiculo}' no está disponible para profesionales. "
            "Si el usuario tiene un vehículo diferente a una autocaravana, explícale que debe "
            "contactar directamente con MSI Automotive (msi@msihomologacion.com) o escalar a un agente humano."
        )

    if not descripcion_elementos.strip():
        return "Error: Debes especificar los elementos a homologar."

    # Count elements roughly from description
    # This is a simple heuristic - the AI should have already identified elements
    separators = [",", " y ", " e ", " + "]
    element_count = 1
    desc_lower = descripcion_elementos.lower()
    for sep in separators:
        if sep in desc_lower:
            element_count = max(element_count, desc_lower.count(sep) + 1)

    result = await service.select_tariff_by_rules(
        category_slug=categoria_vehiculo,
        elements_description=descripcion_elementos,
        element_count=element_count,
        client_type=tipo_cliente,
    )

    return service.format_tariff_response(result)


@tool
async def obtener_documentacion(
    categoria_vehiculo: str,
    descripcion_elementos: str = "",
) -> dict[str, Any]:
    """
    Obtiene la documentación necesaria para homologar elementos específicos.

    Use this tool when the user asks what photos or documents they need to provide.
    Returns both text descriptions and image URLs that should be sent to the user.

    Args:
        categoria_vehiculo: Categoría del vehículo. Usa el slug exacto:
                           - "aseicars" para autocaravanas (códigos 32xx, 33xx)
                           - "motos" para motocicletas
        descripcion_elementos: Descripción de los elementos a homologar.
                              Usado para buscar documentación específica por keyword.
                              Ejemplo: "escalera y toldo" buscará docs de escalera y toldo.

    Returns:
        Dictionary with:
        - "texto": Text description of required documentation
        - "imagenes": List of example image URLs to send to user
    """
    service = get_tarifa_service()

    result = await service.get_documentation(
        categoria_vehiculo,
        descripcion_elementos if descripcion_elementos.strip() else None,
    )
    text, images = service.format_documentation_response(result)

    return {
        "texto": text,
        "imagenes": images,
    }


@tool
async def listar_tarifas(categoria_vehiculo: str, tipo_cliente: str = "particular") -> str:
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
    service = get_tarifa_service()
    data = await service.get_category_data(categoria_vehiculo, tipo_cliente)

    if not data:
        categories = await service.get_active_categories()
        return f"Categoría '{categoria_vehiculo}' no encontrada. Categorías disponibles: {', '.join(c['slug'] for c in categories)}"

    lines = [
        f"**Tarifas para {data['category']['name']}** ({tipo_cliente.capitalize()}):",
        "",
        "Precios SIN IVA:",
        "",
    ]

    for tier in data["tiers"]:
        lines.append(f"• **{tier['code']} - {tier['name']}**: {tier['price']}€ + IVA")
        if tier.get("conditions"):
            lines.append(f"  {tier['conditions']}")

        # Show keywords if available
        rules = tier.get("classification_rules") or {}
        keywords = rules.get("applies_if_any", [])
        if keywords:
            lines.append(f"  Aplica para: {', '.join(keywords[:5])}" + ("..." if len(keywords) > 5 else ""))

        lines.append("")

    return "\n".join(lines)


@tool
async def obtener_servicios_adicionales(categoria_vehiculo: str = "") -> str:
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
        return "No hay servicios adicionales disponibles en este momento."

    lines = ["**Servicios adicionales disponibles:**", ""]
    for s in services:
        lines.append(f"• **{s['name']}**: {s['price']}€")
        if s.get("description"):
            lines.append(f"  {s['description']}")

    return "\n".join(lines)


@tool
async def escalar_a_humano(motivo: str) -> dict[str, Any]:
    """
    Escala la conversación a un agente humano.

    Use this tool when:
    - The user explicitly asks to speak with a human
    - You cannot answer the user's question
    - The user needs special assistance not covered by standard processes
    - There's a complex case that requires human judgment

    Args:
        motivo: Brief reason for escalation (in Spanish).

    Returns:
        Dict with:
        - "result": Confirmation message for the user
        - "escalation_triggered": True to signal escalation
        - "escalation_id": UUID of the escalation record
    """
    settings = get_settings()

    # Get current state from context (set by execute_tool_call)
    state = get_current_state()
    if not state:
        logger.error("No state available in escalar_a_humano - cannot escalate")
        return {
            "result": (
                "Lo siento, tuve un problema técnico al escalar. "
                "Por favor, intenta de nuevo o contacta directamente con MSI Automotive."
            ),
            "escalation_triggered": False,
        }

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")
    user_phone = state.get("user_phone", "desconocido")

    if not conversation_id:
        logger.error("No conversation_id in state - cannot escalate")
        return {
            "result": (
                "Lo siento, no pude identificar la conversación. "
                "Por favor, contacta directamente con MSI Automotive."
            ),
            "escalation_triggered": False,
        }

    logger.info(
        f"Escalation requested | conversation_id={conversation_id} | reason={motivo}",
        extra={
            "conversation_id": conversation_id,
            "user_id": str(user_id) if user_id else None,
            "reason": motivo,
        },
    )

    escalation_id = uuid.uuid4()
    chatwoot = ChatwootClient()

    # =========================================================================
    # STEP 1: Disable bot (CRITICAL - must succeed)
    # =========================================================================
    try:
        conv_id_int = int(conversation_id)
        await chatwoot.update_conversation_attributes(
            conversation_id=conv_id_int,
            attributes={"atencion_automatica": False},
        )
        logger.info(
            f"Bot disabled for conversation {conversation_id}",
            extra={"conversation_id": conversation_id},
        )
    except Exception as e:
        logger.error(
            f"CRITICAL: Failed to disable bot for conversation {conversation_id}: {e}",
            exc_info=True,
        )
        # Even if this fails, we continue - better to record escalation
        # and have bot still responding than to silently fail

    # =========================================================================
    # STEP 2: Add label "escalado" (best-effort)
    # =========================================================================
    try:
        await chatwoot.add_labels(
            conversation_id=conv_id_int,
            labels=["escalado"],
        )
        logger.info(f"Label 'escalado' added to conversation {conversation_id}")
    except Exception as e:
        logger.warning(
            f"Could not add label to conversation {conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
        )

    # =========================================================================
    # STEP 3: Add private note with context (best-effort)
    # =========================================================================
    try:
        note = (
            f"ESCALACION AUTOMATICA\n"
            f"---\n"
            f"Motivo: {motivo}\n"
            f"Usuario: {user_phone}\n"
            f"Escalation ID: {escalation_id}\n"
            f"Timestamp: {datetime.now(UTC).isoformat()}\n"
            f"---\n"
            f"El bot ha sido desactivado para esta conversacion."
        )
        await chatwoot.add_private_note(
            conversation_id=conv_id_int,
            note=note,
        )
        logger.info(f"Private note added to conversation {conversation_id}")
    except Exception as e:
        logger.warning(
            f"Could not add private note to conversation {conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
        )

    # =========================================================================
    # STEP 4: Attempt team assignment (best-effort, expected to fail often)
    # =========================================================================
    team_id = settings.CHATWOOT_TEAM_GROUP_ID
    if team_id:
        try:
            await chatwoot.assign_to_team(
                conversation_id=conv_id_int,
                team_id=int(team_id),
            )
            logger.info(
                f"Conversation {conversation_id} assigned to team {team_id}"
            )
        except Exception as e:
            # Expected to fail if bot token lacks permission
            logger.debug(
                f"Team assignment failed (expected): {e}",
                extra={"conversation_id": conversation_id},
            )

    # =========================================================================
    # STEP 5: Save escalation record to database
    # =========================================================================
    try:
        async with get_async_session() as session:
            escalation = Escalation(
                id=escalation_id,
                conversation_id=str(conversation_id),
                user_id=uuid.UUID(str(user_id)) if user_id else None,
                reason=motivo,
                source="tool_call",
                status="pending",
                triggered_at=datetime.now(UTC),
                metadata_={
                    "user_phone": user_phone,
                    "priority": "normal",
                },
            )
            session.add(escalation)
            await session.commit()
            logger.info(
                f"Escalation {escalation_id} saved to database",
                extra={
                    "escalation_id": str(escalation_id),
                    "conversation_id": conversation_id,
                },
            )
    except Exception as e:
        logger.error(
            f"Failed to save escalation to database: {e}",
            exc_info=True,
        )
        # Continue anyway - the bot is disabled, which is the critical part

    logger.info(
        f"Escalation completed | escalation_id={escalation_id} | "
        f"conversation_id={conversation_id}",
        extra={
            "escalation_id": str(escalation_id),
            "conversation_id": conversation_id,
            "reason": motivo,
        },
    )

    return {
        "result": (
            "He registrado tu solicitud de atencion personalizada. "
            "Un agente de MSI Automotive se pondra en contacto contigo lo antes posible. "
            f"Motivo de la consulta: {motivo}"
        ),
        "escalation_triggered": True,
        "escalation_id": str(escalation_id),
    }


# Export all tools
ALL_TOOLS = [
    listar_categorias,
    calcular_tarifa,
    obtener_documentacion,
    listar_tarifas,
    obtener_servicios_adicionales,
    escalar_a_humano,
]


def get_tarifa_tools() -> list:
    """Get all tariff-related tools for the agent."""
    return ALL_TOOLS
