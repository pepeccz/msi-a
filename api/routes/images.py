"""
MSI Automotive - Image Upload API routes.

Handles image upload, listing, and deletion for the admin panel.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from api.middleware.rate_limit import get_rate_limiter
from api.routes.admin import get_current_user
from api.services.image_service import get_image_service
from database.models import AdminUser
from shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    category: str | None = Query(None, description="Image category"),
    description: str | None = Query(None, description="Image description"),
    user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Upload an image with rate limiting and security validation.

    Requires authentication. Stores image locally and saves metadata to DB.

    Args:
        file: Image file to upload
        category: Optional category (documentation, example, etc.)
        description: Optional description

    Returns:
        Image metadata including URL
    """
    # Rate limiting: 10 uploads per minute per user
    limiter = get_rate_limiter()
    rate_limit_key = f"upload:{user.username}"

    if not limiter.check_rate_limit(rate_limit_key, max_requests=10, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes. Espera 1 minuto e intenta de nuevo.",
        )

    service = get_image_service()
    result = await service.upload_image(
        file=file,
        category=category,
        description=description,
        username=user.username,
    )

    logger.info(
        f"Image uploaded: {result['filename']} by {user.username}",
        extra={"image_id": result["id"]},
    )

    return JSONResponse(status_code=201, content=result)


@router.get("/images")
async def list_images(
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AdminUser = Depends(get_current_user),
) -> dict:
    """
    List uploaded images with pagination.

    Args:
        category: Optional category filter
        limit: Max results (1-200)
        offset: Skip results

    Returns:
        Paginated list of images
    """
    service = get_image_service()
    return await service.list_images(category=category, limit=limit, offset=offset)


@router.get("/images/{image_id}")
async def get_image(
    image_id: str,
    user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get a single image metadata by ID.

    Args:
        image_id: UUID of the image

    Returns:
        Image metadata or 404
    """
    service = get_image_service()
    result = await service.get_image(image_id)

    if not result:
        return JSONResponse(status_code=404, content={"detail": "Image not found"})

    return JSONResponse(content=result)


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(
    image_id: str,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """
    Delete an image.

    Removes both the file and database record.

    Args:
        image_id: UUID of the image

    Raises:
        404 if image not found
    """
    service = get_image_service()
    deleted = await service.delete_image(image_id)

    if not deleted:
        return JSONResponse(status_code=404, content={"detail": "Image not found"})

    logger.info(
        f"Image deleted: {image_id} by {user.username}",
        extra={"image_id": image_id},
    )


# =============================================================================
# Public endpoint for serving images (no auth required)
# =============================================================================


def get_public_image_router() -> APIRouter:
    """
    Get router for public image serving.

    This is separate so it can be mounted without auth.
    """
    public_router = APIRouter()

    @public_router.get("/{filename}", response_model=None)
    async def serve_image(filename: str) -> FileResponse | JSONResponse:
        """
        Serve an uploaded image file.

        This endpoint is public (no auth) so images can be displayed
        in WhatsApp messages sent via Chatwoot.

        SECURITY: Validates filename to prevent path traversal attacks.

        Args:
            filename: Stored filename (UUID-based)

        Returns:
            Image file or 404
        """
        from shared.image_security import ImageSecurityError, validate_filename

        # Validate filename (path traversal prevention)
        try:
            safe_filename = validate_filename(filename)
        except ImageSecurityError as e:
            logger.warning(f"Invalid filename requested: {filename} | Error: {e}")
            return JSONResponse(status_code=400, content={"detail": "Invalid filename"})

        settings = get_settings()
        upload_dir = Path(settings.IMAGE_UPLOAD_DIR).resolve()
        file_path = upload_dir / safe_filename

        # Additional check: ensure resolved path is within upload directory
        try:
            resolved_path = file_path.resolve()
            if not resolved_path.is_relative_to(upload_dir):
                logger.error(
                    f"Path traversal attempt detected: {filename} -> {resolved_path}"
                )
                return JSONResponse(status_code=403, content={"detail": "Access denied"})
        except Exception as e:
            logger.error(f"Path resolution error: {e}")
            return JSONResponse(status_code=400, content={"detail": "Invalid path"})

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "Image not found"})

        # Verify it's a file (not a directory)
        if not file_path.is_file():
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        return FileResponse(file_path)

    return public_router


def get_case_images_router() -> APIRouter:
    """
    Get router for serving case/expediente images.

    This serves images uploaded by users during case collection.
    Separate from regular images to keep user uploads isolated.
    """
    case_router = APIRouter()

    @case_router.get("/{filename}", response_model=None)
    async def serve_case_image(filename: str) -> FileResponse | JSONResponse:
        """
        Serve a case image file.

        This endpoint is public (no auth) so images can be displayed
        in the admin panel without authentication issues.

        SECURITY: Validates filename to prevent path traversal attacks.

        Args:
            filename: Stored filename (UUID-based)

        Returns:
            Image file or 404
        """
        from shared.image_security import ImageSecurityError, validate_filename

        # Validate filename (path traversal prevention)
        try:
            safe_filename = validate_filename(filename)
        except ImageSecurityError as e:
            logger.warning(f"Invalid case image filename requested: {filename} | Error: {e}")
            return JSONResponse(status_code=400, content={"detail": "Invalid filename"})

        settings = get_settings()
        case_images_dir = Path(settings.CASE_IMAGES_DIR).resolve()
        file_path = case_images_dir / safe_filename

        # Additional check: ensure resolved path is within case images directory
        try:
            resolved_path = file_path.resolve()
            if not resolved_path.is_relative_to(case_images_dir):
                logger.error(
                    f"Path traversal attempt detected in case images: {filename} -> {resolved_path}"
                )
                return JSONResponse(status_code=403, content={"detail": "Access denied"})
        except Exception as e:
            logger.error(f"Path resolution error in case images: {e}")
            return JSONResponse(status_code=400, content={"detail": "Invalid path"})

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "Case image not found"})

        # Verify it's a file (not a directory)
        if not file_path.is_file():
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        return FileResponse(file_path)

    return case_router
