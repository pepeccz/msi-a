"""
MSI Automotive - Cases (Expedientes) API Routes.

Provides endpoints for managing homologation cases in the admin panel.
Includes listing, detail views, status management, and image downloads.
"""

import io
import logging
import uuid
import zipfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from api.routes.admin import get_current_user, require_role
from api.services.chatwoot_image_service import get_chatwoot_image_service
from database.connection import get_async_session
from database.models import (
    AdminUser,
    Case,
    CaseImage,
    VehicleCategory,
    User,
    Escalation,
)
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/cases")


# =============================================================================
# Request/Response Models
# =============================================================================


class CaseStatusUpdate(BaseModel):
    """Request body for updating case status."""
    status: str
    notes: str | None = None


class CaseImageValidation(BaseModel):
    """Request body for validating case images."""
    is_valid: bool
    validation_notes: str | None = None


# =============================================================================
# Statistics Endpoint
# =============================================================================


@router.get("/stats")
async def get_case_stats(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get case statistics for dashboard.

    Returns:
        Statistics: counts by status, today totals
    """
    async with get_async_session() as session:
        # Count by status
        status_counts = await session.execute(
            select(Case.status, func.count(Case.id))
            .group_by(Case.status)
        )
        counts_by_status = dict(status_counts.all())

        # Get today's date boundaries in UTC
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Cases created today
        created_today = await session.scalar(
            select(func.count(Case.id)).where(
                Case.created_at >= today_start,
            )
        ) or 0

        # Cases resolved today
        resolved_today = await session.scalar(
            select(func.count(Case.id)).where(
                Case.status == "resolved",
                Case.resolved_at >= today_start,
            )
        ) or 0

        # Total active cases (collecting, pending_images, pending_review, in_progress)
        active_statuses = ["collecting", "pending_images", "pending_review", "in_progress"]
        active_count = sum(
            counts_by_status.get(s, 0) for s in active_statuses
        )

        return JSONResponse(
            content={
                "pending_review": counts_by_status.get("pending_review", 0),
                "in_progress": counts_by_status.get("in_progress", 0),
                "collecting": counts_by_status.get("collecting", 0),
                "resolved_today": resolved_today,
                "created_today": created_today,
                "total_active": active_count,
                "by_status": counts_by_status,
            }
        )


# =============================================================================
# List Endpoint
# =============================================================================


@router.get("")
async def list_cases(
    current_user: AdminUser = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> JSONResponse:
    """
    List cases with pagination and filters.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        status: Filter by status
        search: Search in nombre, apellidos, email, vehiculo_matricula

    Returns:
        Paginated list of cases
    """
    async with get_async_session() as session:
        # Build count query with join for search
        count_query = select(func.count(Case.id)).outerjoin(User, Case.user_id == User.id)
        if status:
            count_query = count_query.where(Case.status == status)
        if search:
            search_filter = f"%{search}%"
            count_query = count_query.where(
                (User.first_name.ilike(search_filter)) |
                (User.last_name.ilike(search_filter)) |
                (User.email.ilike(search_filter)) |
                (Case.vehiculo_matricula.ilike(search_filter))
            )
        total = await session.scalar(count_query) or 0

        # Build cases query with eager loading
        query = (
            select(Case)
            .options(
                selectinload(Case.category),
                selectinload(Case.user),
            )
            .order_by(Case.created_at.desc())
        )

        if status:
            query = query.where(Case.status == status)
        if search:
            search_filter = f"%{search}%"
            query = query.outerjoin(User, Case.user_id == User.id).where(
                (User.first_name.ilike(search_filter)) |
                (User.last_name.ilike(search_filter)) |
                (User.email.ilike(search_filter)) |
                (Case.vehiculo_matricula.ilike(search_filter))
            )

        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        cases = result.scalars().all()

        # Get image counts for each case
        case_ids = [c.id for c in cases]
        image_counts: dict[uuid.UUID, int] = {}
        if case_ids:
            img_count_result = await session.execute(
                select(CaseImage.case_id, func.count(CaseImage.id))
                .where(CaseImage.case_id.in_(case_ids))
                .group_by(CaseImage.case_id)
            )
            image_counts = dict(img_count_result.all())

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(c.id),
                        "conversation_id": c.conversation_id,
                        "user_id": str(c.user_id) if c.user_id else None,
                        "user_phone": c.user.phone if c.user else None,
                        "status": c.status,
                        "current_step": (c.metadata_ or {}).get("current_step"),
                        # User info (from related User)
                        "user_first_name": c.user.first_name if c.user else None,
                        "user_last_name": c.user.last_name if c.user else None,
                        "user_email": c.user.email if c.user else None,
                        # Vehicle data
                        "vehiculo_marca": c.vehiculo_marca,
                        "vehiculo_modelo": c.vehiculo_modelo,
                        "vehiculo_matricula": c.vehiculo_matricula,
                        "category_slug": c.category.slug if c.category else None,
                        "category_name": c.category.name if c.category else None,
                        "element_codes": c.element_codes,
                        "tariff_amount": float(c.tariff_amount) if c.tariff_amount else None,
                        "image_count": image_counts.get(c.id, 0),
                        "created_at": c.created_at.isoformat(),
                        "updated_at": c.updated_at.isoformat(),
                        "resolved_by": c.resolved_by,
                    }
                    for c in cases
                ],
                "total": total,
                "has_more": offset + len(cases) < total,
            }
        )


# =============================================================================
# Detail Endpoint
# =============================================================================


@router.get("/{case_id}")
async def get_case(
    case_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a single case by ID with all details and images.

    Args:
        case_id: Case UUID

    Returns:
        Case details with images
    """
    async with get_async_session() as session:
        # Get case with all relations
        result = await session.execute(
            select(Case)
            .options(
                selectinload(Case.category),
                selectinload(Case.user),
                selectinload(Case.images),
                selectinload(Case.escalation),
            )
            .where(Case.id == case_id)
        )
        case = result.scalar_one_or_none()

        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get image service for URLs
        image_service = get_chatwoot_image_service()

        return JSONResponse(
            content={
                "id": str(case.id),
                "conversation_id": case.conversation_id,
                "user_id": str(case.user_id) if case.user_id else None,
                "user_phone": case.user.phone if case.user else None,
                "status": case.status,
                "current_step": (case.metadata_ or {}).get("current_step"),
                # User personal data (from related User)
                "user_first_name": case.user.first_name if case.user else None,
                "user_last_name": case.user.last_name if case.user else None,
                "user_email": case.user.email if case.user else None,
                "user_nif_cif": case.user.nif_cif if case.user else None,
                "user_domicilio_calle": case.user.domicilio_calle if case.user else None,
                "user_domicilio_localidad": case.user.domicilio_localidad if case.user else None,
                "user_domicilio_provincia": case.user.domicilio_provincia if case.user else None,
                "user_domicilio_cp": case.user.domicilio_cp if case.user else None,
                # ITV (stays in Case)
                "itv_nombre": case.itv_nombre,
                # Vehicle data
                "vehiculo_marca": case.vehiculo_marca,
                "vehiculo_modelo": case.vehiculo_modelo,
                "vehiculo_anio": case.vehiculo_anio,
                "vehiculo_matricula": case.vehiculo_matricula,
                "vehiculo_bastidor": case.vehiculo_bastidor,
                # Category and elements
                "category_id": str(case.category_id) if case.category_id else None,
                "category_slug": case.category.slug if case.category else None,
                "category_name": case.category.name if case.category else None,
                "element_codes": case.element_codes,
                # Tariff
                "tariff_tier_id": str(case.tariff_tier_id) if case.tariff_tier_id else None,
                "tariff_amount": float(case.tariff_amount) if case.tariff_amount else None,
                # Taller (workshop)
                "taller_propio": case.taller_propio,
                "taller_nombre": case.taller_nombre,
                "taller_responsable": case.taller_responsable,
                "taller_domicilio": case.taller_domicilio,
                "taller_provincia": case.taller_provincia,
                "taller_ciudad": case.taller_ciudad,
                "taller_telefono": case.taller_telefono,
                "taller_registro_industrial": case.taller_registro_industrial,
                "taller_actividad": case.taller_actividad,
                # Cambios dimensionales
                "cambio_plazas": case.cambio_plazas,
                "plazas_iniciales": case.plazas_iniciales,
                "plazas_finales": case.plazas_finales,
                "cambio_altura": case.cambio_altura,
                "altura_final": case.altura_final,
                "cambio_ancho": case.cambio_ancho,
                "ancho_final": case.ancho_final,
                "cambio_longitud": case.cambio_longitud,
                "longitud_final": case.longitud_final,
                # Escalation
                "escalation_id": str(case.escalation_id) if case.escalation_id else None,
                "escalation_status": case.escalation.status if case.escalation else None,
                # Metadata
                "notes": case.notes,
                "metadata": case.metadata_,
                # Timestamps
                "created_at": case.created_at.isoformat(),
                "updated_at": case.updated_at.isoformat(),
                "completed_at": case.completed_at.isoformat() if case.completed_at else None,
                "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
                "resolved_by": case.resolved_by,
                # Images
                "images": [
                    {
                        "id": str(img.id),
                        "display_name": img.display_name,
                        "description": img.description,
                        "element_code": img.element_code,
                        "image_type": img.image_type,
                        "mime_type": img.mime_type,
                        "file_size": img.file_size,
                        "is_valid": img.is_valid,
                        "validation_notes": img.validation_notes,
                        "url": image_service.get_image_url(img.stored_filename),
                        "created_at": img.created_at.isoformat(),
                    }
                    for img in case.images
                ],
            }
        )


# =============================================================================
# Status Management
# =============================================================================


@router.post("/{case_id}/status")
async def update_case_status(
    case_id: uuid.UUID,
    data: CaseStatusUpdate,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Update case status.

    Valid status transitions:
    - pending_review -> in_progress (take case)
    - in_progress -> resolved (resolve case)
    - any -> cancelled (cancel case)

    Args:
        case_id: Case UUID
        data: New status and optional notes

    Returns:
        Updated case info
    """
    valid_statuses = [
        "collecting", "pending_images", "pending_review",
        "in_progress", "resolved", "cancelled", "abandoned"
    ]

    if data.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    async with get_async_session() as session:
        case = await session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        old_status = case.status
        now = datetime.now(UTC)

        # Update status
        case.status = data.status
        case.updated_at = now

        # Add notes if provided
        if data.notes:
            existing_notes = case.notes or ""
            timestamp = now.strftime("%Y-%m-%d %H:%M")
            new_note = f"[{timestamp} - {current_user.display_name or current_user.username}] {data.notes}"
            case.notes = f"{existing_notes}\n{new_note}".strip()

        # Handle resolved status
        if data.status == "resolved":
            case.resolved_at = now
            case.resolved_by = current_user.display_name or current_user.username

            # Reactivate bot in Chatwoot
            await _reactivate_bot(case.conversation_id, current_user)

        await session.commit()
        await session.refresh(case)

        logger.info(
            f"Case {case_id} status changed: {old_status} -> {data.status} "
            f"by {current_user.username}",
            extra={
                "case_id": str(case_id),
                "old_status": old_status,
                "new_status": data.status,
                "changed_by": current_user.username,
            },
        )

        return JSONResponse(
            content={
                "id": str(case.id),
                "status": case.status,
                "updated_at": case.updated_at.isoformat(),
                "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
                "resolved_by": case.resolved_by,
                "message": f"Case status updated to {data.status}",
            }
        )


@router.post("/{case_id}/take")
async def take_case(
    case_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Take a case (change status from pending_review to in_progress).

    Args:
        case_id: Case UUID

    Returns:
        Updated case info
    """
    async with get_async_session() as session:
        case = await session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        if case.status != "pending_review":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot take case with status '{case.status}'. Must be 'pending_review'."
            )

        case.status = "in_progress"
        case.updated_at = datetime.now(UTC)

        # Add note
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        agent_name = current_user.display_name or current_user.username
        note = f"[{timestamp}] Expediente tomado por {agent_name}"
        case.notes = f"{case.notes or ''}\n{note}".strip()

        await session.commit()
        await session.refresh(case)

        logger.info(f"Case {case_id} taken by {current_user.username}")

        return JSONResponse(
            content={
                "id": str(case.id),
                "status": case.status,
                "message": "Case taken successfully",
            }
        )


@router.post("/{case_id}/resolve")
async def resolve_case(
    case_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Resolve a case and reactivate bot in Chatwoot.

    Args:
        case_id: Case UUID

    Returns:
        Updated case info
    """
    async with get_async_session() as session:
        case = await session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        if case.status == "resolved":
            raise HTTPException(status_code=400, detail="Case is already resolved")

        now = datetime.now(UTC)
        agent_name = current_user.display_name or current_user.username

        case.status = "resolved"
        case.resolved_at = now
        case.resolved_by = agent_name
        case.updated_at = now

        # Add note
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        note = f"[{timestamp}] Expediente resuelto por {agent_name}"
        case.notes = f"{case.notes or ''}\n{note}".strip()

        await session.commit()
        await session.refresh(case)

        # Reactivate bot
        await _reactivate_bot(case.conversation_id, current_user)

        logger.info(f"Case {case_id} resolved by {current_user.username}")

        return JSONResponse(
            content={
                "id": str(case.id),
                "status": case.status,
                "resolved_at": case.resolved_at.isoformat(),
                "resolved_by": case.resolved_by,
                "message": "Case resolved successfully",
            }
        )


# =============================================================================
# Image Endpoints
# =============================================================================


@router.get("/{case_id}/images/{image_id}")
async def download_case_image(
    case_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download a single case image with descriptive filename.

    Args:
        case_id: Case UUID
        image_id: Image UUID

    Returns:
        Image file stream
    """
    async with get_async_session() as session:
        # Verify case exists
        case = await session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get image
        result = await session.execute(
            select(CaseImage).where(
                CaseImage.id == image_id,
                CaseImage.case_id == case_id,
            )
        )
        image = result.scalar_one_or_none()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        # Get image bytes
        image_service = get_chatwoot_image_service()
        image_data = await image_service.get_image_bytes(image.stored_filename)

        if not image_data:
            raise HTTPException(status_code=404, detail="Image file not found")

        content, mime_type = image_data

        # Create descriptive filename
        ext = image.stored_filename.rsplit(".", 1)[-1]
        download_filename = f"{image.display_name}.{ext}"

        return StreamingResponse(
            io.BytesIO(content),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"',
                "Content-Length": str(len(content)),
            },
        )


@router.get("/{case_id}/images/download-all")
async def download_all_images(
    case_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download all case images as a ZIP file.

    Args:
        case_id: Case UUID

    Returns:
        ZIP file stream
    """
    async with get_async_session() as session:
        # Get case with images
        result = await session.execute(
            select(Case)
            .options(selectinload(Case.images))
            .where(Case.id == case_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        if not case.images:
            raise HTTPException(status_code=404, detail="No images found for this case")

        # Create ZIP in memory
        zip_buffer = io.BytesIO()
        image_service = get_chatwoot_image_service()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for img in case.images:
                image_data = await image_service.get_image_bytes(img.stored_filename)
                if image_data:
                    content, _ = image_data
                    ext = img.stored_filename.rsplit(".", 1)[-1]
                    filename = f"{img.display_name}.{ext}"
                    zf.writestr(filename, content)

        zip_buffer.seek(0)

        # Create descriptive ZIP filename
        matricula = case.vehiculo_matricula or "sin_matricula"
        user_name = ""
        if case.user:
            user_name = f"{case.user.first_name or ''} {case.user.last_name or ''}".strip()
        user_name = (user_name or "").replace(" ", "_")
        zip_filename = f"expediente_{matricula}_{user_name}.zip"

        logger.info(f"Generated ZIP for case {case_id} with {len(case.images)} images")

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{zip_filename}"',
            },
        )


@router.put("/{case_id}/images/{image_id}/validate")
async def validate_image(
    case_id: uuid.UUID,
    image_id: uuid.UUID,
    data: CaseImageValidation,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Validate a case image (mark as valid/invalid).

    Args:
        case_id: Case UUID
        image_id: Image UUID
        data: Validation status

    Returns:
        Updated image info
    """
    async with get_async_session() as session:
        # Verify case exists
        case = await session.get(Case, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        # Get image
        result = await session.execute(
            select(CaseImage).where(
                CaseImage.id == image_id,
                CaseImage.case_id == case_id,
            )
        )
        image = result.scalar_one_or_none()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        # Update validation
        image.is_valid = data.is_valid
        image.validation_notes = data.validation_notes

        await session.commit()
        await session.refresh(image)

        logger.info(
            f"Image {image_id} validated as {'valid' if data.is_valid else 'invalid'} "
            f"by {current_user.username}"
        )

        return JSONResponse(
            content={
                "id": str(image.id),
                "is_valid": image.is_valid,
                "validation_notes": image.validation_notes,
                "message": "Image validation updated",
            }
        )


# =============================================================================
# Helper Functions
# =============================================================================


async def _reactivate_bot(conversation_id: str, current_user: AdminUser) -> None:
    """
    Reactivate the bot in Chatwoot for a conversation.

    Args:
        conversation_id: Chatwoot conversation ID
        current_user: Admin user who resolved the case
    """
    try:
        conv_id_int = int(conversation_id)
        chatwoot_client = ChatwootClient()

        # Reactivate atencion_automatica
        await chatwoot_client.update_conversation_attributes(
            conversation_id=conv_id_int,
            attributes={"atencion_automatica": True},
        )

        # Send notification message
        resolution_message = (
            "Tu expediente ha sido procesado. El asistente automático está "
            "nuevamente disponible. ¿En qué más puedo ayudarte?"
        )
        await chatwoot_client.send_message(
            customer_phone="",
            message=resolution_message,
            conversation_id=conv_id_int,
        )

        # Remove "expediente" label (best-effort)
        try:
            await chatwoot_client.remove_labels(
                conversation_id=conv_id_int,
                labels=["expediente"],
            )
        except Exception as e:
            logger.warning(f"Could not remove label: {e}")

        # Add private note
        try:
            agent_name = current_user.display_name or current_user.username
            note = (
                f"EXPEDIENTE RESUELTO\n"
                f"---\n"
                f"Resuelto por: {agent_name}\n"
                f"El bot ha sido reactivado para esta conversación.\n"
            )
            await chatwoot_client.add_private_note(
                conversation_id=conv_id_int,
                note=note,
            )
        except Exception as e:
            logger.warning(f"Could not add resolution note: {e}")

        logger.info(f"Bot reactivated for conversation {conv_id_int}")

    except ValueError:
        logger.error(f"Invalid conversation_id format: {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to reactivate bot for conversation {conversation_id}: {e}")
