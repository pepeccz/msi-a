"""
Regulatory Documents API Routes.

Provides endpoints for managing regulatory documents including
upload, listing, activation/deactivation, and deletion.
"""

import hashlib
import uuid
from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func

import logging

from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import RegulatoryDocument, DocumentChunk, AdminUser
from api.services.qdrant_service import get_qdrant_service
from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/regulatory-documents", tags=["regulatory-documents"])

PROCESSING_STREAM = "document_processing_stream"


# =============================================================================
# Request/Response Models
# =============================================================================


class DocumentUpdateRequest(BaseModel):
    """Update request for regulatory document metadata."""
    title: str | None = None
    document_type: str | None = None
    document_number: str | None = None
    description: str | None = None
    tags: list[str] | None = None


# =============================================================================
# Upload Endpoint
# =============================================================================


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    document_number: str = Form(None),
    description: str = Form(None),
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Upload a new regulatory document.

    The document will be queued for processing via Redis Streams.
    Processing includes: PDF extraction, chunking, embedding, and indexing.

    Args:
        file: PDF file to upload
        title: Document title
        document_type: Type (e.g., reglamento, directiva, orden)
        document_number: Optional official document number
        description: Optional description
        current_user: Authenticated admin user

    Returns:
        Document ID and initial status
    """
    settings = get_settings()

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    # Validate file size
    content = await file.read()
    if len(content) > settings.DOCUMENT_MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.DOCUMENT_MAX_SIZE_MB}MB"
        )

    # Calculate file hash for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    async with get_async_session() as session:
        # Check for duplicate
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.file_hash == file_hash)
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Document already exists with ID: {existing.id}"
            )

        # Create upload directory
        upload_dir = Path(settings.DOCUMENT_UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        stored_filename = f"{uuid.uuid4()}.pdf"
        file_path = upload_dir / stored_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(content)

        # Create database record
        doc = RegulatoryDocument(
            title=title,
            document_type=document_type,
            document_number=document_number,
            filename=file.filename,
            stored_filename=stored_filename,
            file_size=len(content),
            file_hash=file_hash,
            description=description,
            status="pending",
            processing_progress=0,
            uploaded_by=current_user.username
        )

        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        logger.info(
            f"Document uploaded: {doc.id} ({doc.title}) by {current_user.username}"
        )

        # Queue for processing
        try:
            redis = get_redis_client()
            await redis.xadd(
                PROCESSING_STREAM,
                {"document_id": str(doc.id)}
            )
            logger.info(f"Document {doc.id} queued for processing")
        except Exception as e:
            logger.error(f"Failed to queue document for processing: {e}")
            # Don't fail the upload, just update status
            doc.status = "failed"
            doc.error_message = f"Failed to queue for processing: {e}"
            await session.commit()

        return JSONResponse(
            status_code=201,
            content={
                "id": str(doc.id),
                "status": doc.status,
                "message": "Document uploaded and queued for processing"
            }
        )


# =============================================================================
# List/Get Endpoints
# =============================================================================


@router.get("")
async def list_documents(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    is_active: bool | None = None,
    document_type: str | None = None,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    List regulatory documents with pagination and filters.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        status: Filter by status (pending, processing, indexed, failed)
        is_active: Filter by active status
        document_type: Filter by document type
        current_user: Authenticated admin user

    Returns:
        Paginated list of documents
    """
    async with get_async_session() as session:
        # Build count query
        count_query = select(func.count(RegulatoryDocument.id))
        if status:
            count_query = count_query.where(RegulatoryDocument.status == status)
        if is_active is not None:
            count_query = count_query.where(RegulatoryDocument.is_active == is_active)
        if document_type:
            count_query = count_query.where(RegulatoryDocument.document_type == document_type)

        total = await session.scalar(count_query) or 0

        # Build documents query
        query = select(RegulatoryDocument).order_by(RegulatoryDocument.created_at.desc())
        if status:
            query = query.where(RegulatoryDocument.status == status)
        if is_active is not None:
            query = query.where(RegulatoryDocument.is_active == is_active)
        if document_type:
            query = query.where(RegulatoryDocument.document_type == document_type)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        docs = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(d.id),
                        "title": d.title,
                        "document_type": d.document_type,
                        "document_number": d.document_number,
                        "filename": d.filename,
                        "file_size": d.file_size,
                        "status": d.status,
                        "processing_progress": d.processing_progress,
                        "error_message": d.error_message,
                        "total_pages": d.total_pages,
                        "total_chunks": d.total_chunks,
                        "extraction_method": d.extraction_method,
                        "description": d.description,
                        "tags": d.tags,
                        "is_active": d.is_active,
                        "uploaded_by": d.uploaded_by,
                        "created_at": d.created_at.isoformat(),
                        "updated_at": d.updated_at.isoformat(),
                        "indexed_at": d.indexed_at.isoformat() if d.indexed_at else None,
                    }
                    for d in docs
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(docs) < total,
            }
        )


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a single regulatory document by ID.

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user

    Returns:
        Document details including chunk count
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get chunk count
        chunk_count = await session.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document_id
            )
        ) or 0

        return JSONResponse(
            content={
                "id": str(doc.id),
                "title": doc.title,
                "document_type": doc.document_type,
                "document_number": doc.document_number,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "file_hash": doc.file_hash,
                "status": doc.status,
                "processing_progress": doc.processing_progress,
                "error_message": doc.error_message,
                "total_pages": doc.total_pages,
                "total_chunks": doc.total_chunks,
                "chunk_count": chunk_count,
                "extraction_method": doc.extraction_method,
                "description": doc.description,
                "tags": doc.tags,
                "is_active": doc.is_active,
                "version": doc.version,
                "uploaded_by": doc.uploaded_by,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
                "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
                "activated_at": doc.activated_at.isoformat() if doc.activated_at else None,
                "deactivated_at": doc.deactivated_at.isoformat() if doc.deactivated_at else None,
            }
        )


# =============================================================================
# Update Endpoint
# =============================================================================


@router.put("/{document_id}")
async def update_document(
    document_id: uuid.UUID,
    data: DocumentUpdateRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Update document metadata.

    Args:
        document_id: Document UUID
        data: Fields to update
        current_user: Authenticated admin user

    Returns:
        Updated document
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(doc, field, value)

        await session.commit()
        await session.refresh(doc)

        logger.info(
            f"Document {document_id} updated by {current_user.username}: {list(update_data.keys())}"
        )

        return JSONResponse(
            content={
                "id": str(doc.id),
                "title": doc.title,
                "document_type": doc.document_type,
                "document_number": doc.document_number,
                "description": doc.description,
                "tags": doc.tags,
                "updated_at": doc.updated_at.isoformat(),
            }
        )


# =============================================================================
# Activation Endpoints
# =============================================================================


@router.post("/{document_id}/activate")
async def activate_document(
    document_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Activate a document for RAG queries.

    Only indexed documents can be activated.

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user

    Returns:
        Success message
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.status != "indexed":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot activate document with status '{doc.status}'. Only indexed documents can be activated."
            )

        if doc.is_active:
            return JSONResponse(content={"message": "Document is already active"})

        # Update document
        doc.is_active = True
        doc.activated_at = datetime.now(UTC)
        doc.deactivated_at = None
        await session.commit()

        # Update Qdrant payloads
        try:
            qdrant_service = get_qdrant_service()
            await qdrant_service.update_document_active_status(str(document_id), True)
        except Exception as e:
            logger.error(f"Failed to update Qdrant active status: {e}")
            # Don't fail the request, DB is source of truth

        logger.info(f"Document {document_id} activated by {current_user.username}")

        return JSONResponse(content={"message": "Document activated successfully"})


@router.post("/{document_id}/deactivate")
async def deactivate_document(
    document_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Deactivate a document from RAG queries.

    Deactivated documents won't appear in search results.

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user

    Returns:
        Success message
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if not doc.is_active:
            return JSONResponse(content={"message": "Document is already inactive"})

        # Update document
        doc.is_active = False
        doc.deactivated_at = datetime.now(UTC)
        await session.commit()

        # Update Qdrant payloads
        try:
            qdrant_service = get_qdrant_service()
            await qdrant_service.update_document_active_status(str(document_id), False)
        except Exception as e:
            logger.error(f"Failed to update Qdrant active status: {e}")
            # Don't fail the request, DB is source of truth

        logger.info(f"Document {document_id} deactivated by {current_user.username}")

        return JSONResponse(content={"message": "Document deactivated successfully"})


# =============================================================================
# Delete Endpoint
# =============================================================================


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Delete a document permanently.

    This will:
    - Remove chunks from Qdrant
    - Delete the PDF file
    - Delete the database record (cascades to chunks)

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user

    Returns:
        Success message
    """
    settings = get_settings()

    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete from Qdrant first
        try:
            qdrant_service = get_qdrant_service()
            await qdrant_service.delete_document_chunks(str(document_id))
            logger.info(f"Deleted Qdrant chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete Qdrant chunks: {e}")
            # Continue with deletion anyway

        # Delete the file
        try:
            file_path = Path(settings.DOCUMENT_UPLOAD_DIR) / doc.stored_filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            # Continue with deletion anyway

        # Delete from database (cascades to chunks)
        await session.delete(doc)
        await session.commit()

        logger.info(f"Document {document_id} deleted by {current_user.username}")

        return JSONResponse(content={"message": "Document deleted successfully"})


# =============================================================================
# Reprocess Endpoint
# =============================================================================


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Reprocess a document (re-extract, re-chunk, re-embed, re-index).

    Useful if processing failed or to apply new chunking settings.

    Args:
        document_id: Document UUID
        current_user: Authenticated admin user

    Returns:
        Success message
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete existing chunks from Qdrant
        try:
            qdrant_service = get_qdrant_service()
            await qdrant_service.delete_document_chunks(str(document_id))
        except Exception as e:
            logger.warning(f"Failed to delete existing Qdrant chunks: {e}")

        # Delete existing chunks from DB
        await session.execute(
            DocumentChunk.__table__.delete().where(
                DocumentChunk.document_id == document_id
            )
        )

        # Reset document status
        doc.status = "pending"
        doc.processing_progress = 0
        doc.error_message = None
        doc.total_chunks = None
        doc.indexed_at = None
        await session.commit()

        # Queue for reprocessing
        try:
            redis = get_redis_client()
            await redis.xadd(
                PROCESSING_STREAM,
                {"document_id": str(doc.id)}
            )
            logger.info(f"Document {document_id} queued for reprocessing")
        except Exception as e:
            logger.error(f"Failed to queue document for reprocessing: {e}")
            doc.status = "failed"
            doc.error_message = f"Failed to queue for reprocessing: {e}"
            await session.commit()
            raise HTTPException(
                status_code=500,
                detail="Failed to queue document for reprocessing"
            )

        logger.info(f"Document {document_id} queued for reprocessing by {current_user.username}")

        return JSONResponse(
            content={
                "message": "Document queued for reprocessing",
                "status": "pending"
            }
        )


# =============================================================================
# Stats Endpoint
# =============================================================================


@router.get("/stats/summary")
async def get_stats_summary(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get summary statistics for regulatory documents.

    Returns:
        Document and chunk statistics
    """
    async with get_async_session() as session:
        # Total documents by status
        total_docs = await session.scalar(
            select(func.count(RegulatoryDocument.id))
        ) or 0

        indexed_docs = await session.scalar(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.status == "indexed"
            )
        ) or 0

        active_docs = await session.scalar(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.is_active == True,
                RegulatoryDocument.status == "indexed"
            )
        ) or 0

        pending_docs = await session.scalar(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.status.in_(["pending", "processing"])
            )
        ) or 0

        failed_docs = await session.scalar(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.status == "failed"
            )
        ) or 0

        # Total chunks
        total_chunks = await session.scalar(
            select(func.count(DocumentChunk.id))
        ) or 0

        # Total file size
        total_size = await session.scalar(
            select(func.sum(RegulatoryDocument.file_size))
        ) or 0

        return JSONResponse(
            content={
                "total_documents": total_docs,
                "indexed_documents": indexed_docs,
                "active_documents": active_docs,
                "pending_documents": pending_docs,
                "failed_documents": failed_docs,
                "total_chunks": total_chunks,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
            }
        )
