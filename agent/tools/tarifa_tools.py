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


@tool
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


@tool
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


@tool
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


@tool
@handle_tool_errors(
    error_category=ErrorCategory.EXTERNAL_API_ERROR,
    error_code="ESCALATION_FAILED",
    user_message="Lo siento, hubo un problema técnico al escalar. Por favor, contacta directamente con MSI Automotive.",
)
async def escalar_a_humano(motivo: str, es_error_tecnico: bool = False) -> dict[str, Any]:
    """
    Escala la conversación a un agente humano.

    Use this tool when:
    - The user explicitly asks to speak with a human
    - You cannot answer the user's question
    - The user needs special assistance not covered by standard processes
    - There's a complex case that requires human judgment
    - A technical error occurred that prevents proper processing

    Args:
        motivo: Brief reason for escalation (in Spanish).
        es_error_tecnico: Set to True if escalating due to a technical error
                          (tool failure, processing error, unexpected behavior).
                          Set to False (default) if user explicitly requested
                          human assistance or for non-error cases.

    Returns:
        Dict with:
        - "success": bool
        - "message": Confirmation message for the user
        - "escalation_triggered": True to signal escalation
        - "escalation_id": UUID of the escalation record
    """
    settings = get_settings()

    # Get current state from context (set by execute_tool_call)
    state = get_current_state()
    if not state:
        logger.error("No state available in escalar_a_humano - cannot escalate")
        return tool_error_response(
            message="Lo siento, tuve un problema técnico al escalar. Por favor, intenta de nuevo o contacta directamente con MSI Automotive.",
            error_category=ErrorCategory.CONFIGURATION_ERROR,
            error_code="NO_STATE_CONTEXT",
            guidance="El sistema no tiene acceso al contexto de la conversación. Intenta enviar tu mensaje de nuevo.",
        )

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")
    user_phone = state.get("user_phone", "desconocido")

    if not conversation_id:
        logger.error("No conversation_id in state - cannot escalate")
        return tool_error_response(
            message="Lo siento, no pude identificar la conversación. Por favor, contacta directamente con MSI Automotive.",
            error_category=ErrorCategory.CONFIGURATION_ERROR,
            error_code="NO_CONVERSATION_ID",
            guidance="Intenta enviar tu mensaje de nuevo o contacta directamente.",
        )

    # =========================================================================
    # DUPLICATE ESCALATION PREVENTION
    # Check if an escalation was created in the last 5 minutes
    # =========================================================================
    try:
        async with get_async_session() as session:
            recent_escalations = await session.execute(
                select(Escalation)
                .where(Escalation.conversation_id == str(conversation_id))
                .where(Escalation.triggered_at > datetime.now(UTC) - timedelta(minutes=CACHE_TTL_MINUTES))
                .order_by(Escalation.triggered_at.desc())
                .limit(1)
            )
            existing_escalation = recent_escalations.scalar_one_or_none()
            
            if existing_escalation:
                logger.warning(
                    f"DUPLICATE_ESCALATION_PREVENTED | conversation_id={conversation_id} | "
                    f"existing_id={existing_escalation.id}",
                    extra={
                        "metric_type": "duplicate_prevention",
                        "conversation_id": conversation_id,
                        "existing_escalation_id": str(existing_escalation.id),
                        "duplicate_prevented": True,
                    },
                )
                return {
                    "success": True,
                    "message": (
                        "Un agente de MSI Automotive se pondrá en contacto contigo "
                        "lo antes posible para ayudarte."
                    ),
                    "escalation_triggered": True,
                    "escalation_id": str(existing_escalation.id),
                    "duplicate_prevented": True,
                    "terminate_processing": True,
                    "tool_name": "escalar_a_humano",
                }
    except Exception as e:
        # Don't block escalation on duplicate check failure
        logger.error(
            f"Error checking for duplicate escalations: {e}",
            extra={"conversation_id": conversation_id},
        )

    escalation_type = "technical_error" if es_error_tecnico else "user_request"
    logger.info(
        f"Escalation requested | conversation_id={conversation_id} | reason={motivo} | type={escalation_type}",
        extra={
            "conversation_id": conversation_id,
            "user_id": str(user_id) if user_id else None,
            "reason": motivo,
            "escalation_type": escalation_type,
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
        labels = ["escalado", "error-tecnico"] if es_error_tecnico else ["escalado"]
        await chatwoot.add_labels(
            conversation_id=conv_id_int,
            labels=labels,
        )
        logger.info(f"Labels {labels} added to conversation {conversation_id}")
    except Exception as e:
        logger.warning(
            f"Could not add label to conversation {conversation_id}: {e}",
            extra={"conversation_id": conversation_id},
        )

    # =========================================================================
    # STEP 3: Add private note with context (best-effort)
    # =========================================================================
    try:
        note_title = "ESCALACION POR ERROR TECNICO" if es_error_tecnico else "ESCALACION AUTOMATICA"
        note = (
            f"{note_title}\n"
            f"---\n"
            f"Tipo: {'Error tecnico' if es_error_tecnico else 'Solicitud usuario'}\n"
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
        escalation_source = "error" if es_error_tecnico else "tool_call"
        escalation_priority = "high" if es_error_tecnico else "normal"
        async with get_async_session() as session:
            escalation = Escalation(
                id=escalation_id,
                conversation_id=str(conversation_id),
                user_id=uuid.UUID(str(user_id)) if user_id else None,
                reason=motivo,
                source=escalation_source,
                status="pending",
                triggered_at=datetime.now(UTC),
                metadata_={
                    "user_phone": user_phone,
                    "priority": escalation_priority,
                    "is_technical_error": es_error_tecnico,
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

    if es_error_tecnico:
        result_message = (
            "Disculpa las molestias, experimente un error procesando tu consulta. "
            "He escalado tu conversacion a un agente humano de MSI Automotive que "
            "se pondra en contacto contigo lo antes posible para ayudarte."
        )
    else:
        result_message = (
            "He registrado tu solicitud de atencion personalizada. "
            "Un agente de MSI Automotive se pondra en contacto contigo lo antes posible. "
            f"Motivo de la consulta: {motivo}"
        )

    return {
        "success": True,
        "message": result_message,
        "escalation_triggered": True,
        "escalation_id": str(escalation_id),
        "terminate_processing": True,  # Signal to stop tool execution loop
        "tool_name": "escalar_a_humano",
    }


# Export all tools (only non-redundant ones)
ALL_TOOLS = [
    listar_categorias,
    listar_tarifas,
    obtener_servicios_adicionales,
    escalar_a_humano,
]


def get_tarifa_tools() -> list:
    """Get all tariff-related tools for the agent."""
    return ALL_TOOLS
