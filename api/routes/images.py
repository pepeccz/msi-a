"""
MSI Automotive - Image Upload API routes.

Handles image upload, listing, and deletion for the admin panel.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from api.routes.admin import get_current_user
from api.services.image_service import get_image_service
from shared.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    category: str | None = Query(None, description="Image category"),
    description: str | None = Query(None, description="Image description"),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Upload an image.

    Requires authentication. Stores image locally and saves metadata to DB.

    Args:
        file: Image file to upload
        category: Optional category (documentation, example, etc.)
        description: Optional description

    Returns:
        Image metadata including URL
    """
    service = get_image_service()
    result = await service.upload_image(
        file=file,
        category=category,
        description=description,
        username=user.get("sub"),
    )

    logger.info(
        f"Image uploaded: {result['filename']} by {user.get('sub')}",
        extra={"image_id": result["id"]},
    )

    return JSONResponse(status_code=201, content=result)


@router.get("/images")
async def list_images(
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
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
    user: dict = Depends(get_current_user),
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
    user: dict = Depends(get_current_user),
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
        f"Image deleted: {image_id} by {user.get('sub')}",
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

    @public_router.get("/{filename}")
    async def serve_image(filename: str) -> FileResponse:
        """
        Serve an uploaded image file.

        This endpoint is public (no auth) so images can be displayed
        in WhatsApp messages sent via Chatwoot.

        Args:
            filename: Stored filename (UUID-based)

        Returns:
            Image file or 404
        """
        settings = get_settings()
        file_path = Path(settings.IMAGE_UPLOAD_DIR) / filename

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": "Image not found"})

        return FileResponse(file_path)

    return public_router
