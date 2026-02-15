"""
MSI-a - Escalation Service.

Centralized escalation logic used by both the ``escalar_a_humano`` tool and
the ``escalation_node`` in the conversation graph.

Performs the full 6-step escalation flow:
1. Duplicate prevention (5-min window)
2. Disable bot in Chatwoot
3. Add labels to Chatwoot conversation
4. Add private note with context
5. Attempt team assignment (best-effort)
6. Save Escalation record to PostgreSQL

Ported from v1 ``archive/agent-v1/tools/tarifa_tools.py:222-488``,
adapted to v2 architecture.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from database.connection import get_async_session
from database.models import Escalation
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Duplicate escalation window (minutes)
DUPLICATE_WINDOW_MINUTES = 5


async def perform_escalation(
    conversation_id: str,
    user_id: str | None = None,
    user_phone: str = "desconocido",
    reason: str = "Solicitud de escalación",
    source: str = "tool_call",
    is_technical_error: bool = False,
) -> dict[str, Any]:
    """
    Execute the full escalation flow.

    This is the single source of truth for escalation logic — both the
    ``escalar_a_humano`` tool and the ``escalation_node`` delegate here.

    Args:
        conversation_id: Chatwoot conversation ID.
        user_id: UUID string of the user (optional).
        user_phone: User phone number for context.
        reason: Human-readable reason for escalation.
        source: Escalation source (tool_call, auto, fallback, panic).
        is_technical_error: True if caused by a system error.

    Returns:
        Dict with:
        - success: bool
        - escalation_id: str (UUID)
        - message: str (user-facing message in Spanish)
        - duplicate_prevented: bool
        - terminate_processing: bool
    """
    settings = get_settings()

    # =========================================================================
    # STEP 1: Duplicate escalation prevention
    # =========================================================================
    try:
        async with get_async_session() as session:
            cutoff = datetime.now(UTC) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
            result = await session.execute(
                select(Escalation)
                .where(Escalation.conversation_id == str(conversation_id))
                .where(Escalation.triggered_at > cutoff)
                .order_by(Escalation.triggered_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(
                    "duplicate_escalation_prevented",
                    conversation_id=conversation_id,
                    existing_escalation_id=str(existing.id),
                )
                return {
                    "success": True,
                    "escalation_id": str(existing.id),
                    "message": (
                        "Un agente de MSI Automotive se pondrá en contacto contigo "
                        "lo antes posible para ayudarte."
                    ),
                    "duplicate_prevented": True,
                    "terminate_processing": True,
                }
    except Exception as e:
        # Don't block escalation on duplicate check failure
        logger.error(
            "duplicate_check_failed",
            conversation_id=conversation_id,
            error=str(e),
        )

    escalation_id = uuid.uuid4()
    escalation_type = "technical_error" if is_technical_error else "user_request"
    conv_id_int = int(conversation_id)

    logger.info(
        "escalation_requested",
        conversation_id=conversation_id,
        user_id=user_id,
        reason=reason,
        source=source,
        escalation_type=escalation_type,
        escalation_id=str(escalation_id),
    )

    chatwoot = ChatwootClient()

    # =========================================================================
    # STEP 2: Disable bot (CRITICAL — must succeed)
    # =========================================================================
    try:
        await chatwoot.update_conversation_attributes(
            conversation_id=conv_id_int,
            attributes={"atencion_automatica": False},
        )
        logger.info(
            "bot_disabled",
            conversation_id=conversation_id,
        )
    except Exception as e:
        # Even if this fails, continue — better to record escalation
        logger.error(
            "critical_bot_disable_failed",
            conversation_id=conversation_id,
            error=str(e),
            exc_info=True,
        )

    # =========================================================================
    # STEP 3: Add labels (best-effort)
    # =========================================================================
    try:
        labels = ["escalado", "error-tecnico"] if is_technical_error else ["escalado"]
        await chatwoot.add_labels(
            conversation_id=conv_id_int,
            labels=labels,
        )
        logger.info(
            "labels_added",
            conversation_id=conversation_id,
            labels=labels,
        )
    except Exception as e:
        logger.warning(
            "add_labels_failed",
            conversation_id=conversation_id,
            error=str(e),
        )

    # =========================================================================
    # STEP 4: Add private note with context (best-effort)
    # =========================================================================
    try:
        note_title = (
            "ESCALACIÓN POR ERROR TÉCNICO" if is_technical_error
            else "ESCALACIÓN AUTOMÁTICA"
        )
        note = (
            f"{note_title}\n"
            f"---\n"
            f"Tipo: {'Error técnico' if is_technical_error else 'Solicitud usuario'}\n"
            f"Fuente: {source}\n"
            f"Motivo: {reason}\n"
            f"Usuario: {user_phone}\n"
            f"Escalation ID: {escalation_id}\n"
            f"Timestamp: {datetime.now(UTC).isoformat()}\n"
            f"---\n"
            f"El bot ha sido desactivado para esta conversación."
        )
        await chatwoot.add_private_note(
            conversation_id=conv_id_int,
            note=note,
        )
        logger.info(
            "private_note_added",
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.warning(
            "add_private_note_failed",
            conversation_id=conversation_id,
            error=str(e),
        )

    # =========================================================================
    # STEP 5: Attempt team assignment (best-effort, expected to fail often)
    # =========================================================================
    team_id = settings.CHATWOOT_TEAM_GROUP_ID
    if team_id and team_id != "group_id":  # Skip if using default placeholder
        try:
            await chatwoot.assign_to_team(
                conversation_id=conv_id_int,
                team_id=int(team_id),
            )
            logger.info(
                "team_assigned",
                conversation_id=conversation_id,
                team_id=team_id,
            )
        except Exception as e:
            # Expected to fail if bot token lacks permission
            logger.debug(
                "team_assignment_failed_expected",
                conversation_id=conversation_id,
                error=str(e),
            )

    # =========================================================================
    # STEP 6: Save escalation record to database
    # =========================================================================
    try:
        escalation_priority = "high" if is_technical_error else "normal"
        async with get_async_session() as session:
            escalation = Escalation(
                id=escalation_id,
                conversation_id=str(conversation_id),
                user_id=uuid.UUID(str(user_id)) if user_id else None,
                reason=reason,
                source=source,
                status="pending",
                triggered_at=datetime.now(UTC),
                metadata_={
                    "user_phone": user_phone,
                    "priority": escalation_priority,
                    "is_technical_error": is_technical_error,
                    "escalation_type": escalation_type,
                },
            )
            session.add(escalation)
            await session.commit()
            logger.info(
                "escalation_saved",
                escalation_id=str(escalation_id),
                conversation_id=conversation_id,
            )
    except Exception as e:
        logger.error(
            "escalation_db_save_failed",
            escalation_id=str(escalation_id),
            conversation_id=conversation_id,
            error=str(e),
            exc_info=True,
        )
        # Continue — the bot is disabled, which is the critical part

    # =========================================================================
    # Build response
    # =========================================================================
    logger.info(
        "escalation_completed",
        escalation_id=str(escalation_id),
        conversation_id=conversation_id,
        source=source,
        reason=reason,
    )

    if is_technical_error:
        user_message = (
            "Disculpa las molestias, he experimentado un error procesando tu consulta. "
            "He escalado tu conversación a un agente humano de MSI Automotive que "
            "se pondrá en contacto contigo lo antes posible para ayudarte."
        )
    else:
        user_message = (
            "He registrado tu solicitud de atención personalizada. "
            "Un agente de MSI Automotive se pondrá en contacto contigo lo antes posible. "
            f"Motivo de la consulta: {reason}"
        )

    return {
        "success": True,
        "escalation_id": str(escalation_id),
        "message": user_message,
        "duplicate_prevented": False,
        "terminate_processing": True,
    }
