"""
MSI Automotive - Image Storage Service.

Handles image upload, storage, and retrieval for documentation images.
Includes security validation for uploaded images.
"""

import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select

from database.connection import get_async_session
from database.models import UploadedImage
from shared.config import get_settings
from shared.image_security import (
    ImageSecurityError,
    get_extension_for_mime,
    sanitize_filename,
    validate_image_full,
)

logger = logging.getLogger(__name__)


class ImageService:
    """Service for managing uploaded images."""

    def __init__(self):
        settings = get_settings()
        self.upload_dir = Path(settings.IMAGE_UPLOAD_DIR)
        self.base_url = settings.IMAGE_BASE_URL
        self.max_size = settings.IMAGE_MAX_SIZE_MB * 1024 * 1024  # Convert to bytes

        # Ensure upload directory exists
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def upload_image(
        self,
        file: UploadFile,
        category: str | None = None,
        description: str | None = None,
        username: str | None = None,
    ) -> dict:
        """
        Upload an image and store metadata with security validation.

        Args:
            file: FastAPI UploadFile
            category: Optional category for organization
            description: Optional description
            username: Username of uploader

        Returns:
            Dict with image metadata and URL
        """
        # Read file content
        content = await file.read()
        file_size = len(content)

        # Check file size first (before expensive validation)
        if file_size > self.max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Archivo demasiado grande. Maximo: {self.max_size // 1024 // 1024}MB",
            )

        # SECURITY: Full image validation (magic numbers + PIL)
        try:
            validation_result = validate_image_full(
                content=content,
                declared_mime=file.content_type or "application/octet-stream",
            )
        except ImageSecurityError as e:
            logger.warning(f"Image validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Imagen invalida: {str(e)}",
            )

        # Use validated data
        mime_type = validation_result["detected_mime"]
        width = validation_result["width"]
        height = validation_result["height"]

        # Generate unique filename with validated extension
        original_filename = sanitize_filename(file.filename or "image")
        ext = get_extension_for_mime(mime_type)
        stored_filename = f"{uuid.uuid4()}.{ext}"
        file_path = self.upload_dir / stored_filename

        # Save validated file
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(
            f"Image uploaded and validated: {stored_filename} "
            f"({width}x{height}, {file_size} bytes, {mime_type})"
        )

        # Save metadata to database
        async with get_async_session() as session:
            image = UploadedImage(
                filename=original_filename,
                stored_filename=stored_filename,
                mime_type=mime_type,
                file_size=file_size,
                width=width,
                height=height,
                category=category,
                description=description,
                uploaded_by=username,
            )
            session.add(image)
            await session.commit()
            await session.refresh(image)

            return {
                "id": str(image.id),
                "url": f"{self.base_url}/{stored_filename}",
                "filename": original_filename,
                "stored_filename": stored_filename,
                "mime_type": mime_type,
                "file_size": file_size,
                "width": width,
                "height": height,
                "category": category,
                "description": description,
                "uploaded_by": username,
                "created_at": image.created_at.isoformat(),
            }

    async def delete_image(self, image_id: str) -> bool:
        """
        Delete an image by ID.

        Args:
            image_id: UUID of the image

        Returns:
            True if deleted, False if not found
        """
        async with get_async_session() as session:
            image = await session.get(UploadedImage, uuid.UUID(image_id))
            if not image:
                return False

            # Delete file
            file_path = self.upload_dir / image.stored_filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Image file deleted: {image.stored_filename}")

            # Delete metadata
            await session.delete(image)
            await session.commit()

            return True

    async def list_images(
        self,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        List uploaded images with pagination.

        Args:
            category: Filter by category
            limit: Max results
            offset: Skip results

        Returns:
            Dict with items, total, and has_more
        """
        async with get_async_session() as session:
            # Count
            count_query = select(func.count(UploadedImage.id))
            if category:
                count_query = count_query.where(UploadedImage.category == category)
            total = (await session.execute(count_query)).scalar() or 0

            # Fetch
            query = select(UploadedImage).order_by(UploadedImage.created_at.desc())
            if category:
                query = query.where(UploadedImage.category == category)
            query = query.offset(offset).limit(limit)

            result = await session.execute(query)
            images = result.scalars().all()

            return {
                "items": [
                    {
                        "id": str(img.id),
                        "url": f"{self.base_url}/{img.stored_filename}",
                        "filename": img.filename,
                        "stored_filename": img.stored_filename,
                        "mime_type": img.mime_type,
                        "file_size": img.file_size,
                        "width": img.width,
                        "height": img.height,
                        "category": img.category,
                        "description": img.description,
                        "uploaded_by": img.uploaded_by,
                        "created_at": img.created_at.isoformat(),
                    }
                    for img in images
                ],
                "total": total,
                "has_more": offset + len(images) < total,
            }

    async def get_image(self, image_id: str) -> dict | None:
        """
        Get a single image by ID.

        Args:
            image_id: UUID of the image

        Returns:
            Image dict or None if not found
        """
        async with get_async_session() as session:
            image = await session.get(UploadedImage, uuid.UUID(image_id))
            if not image:
                return None

            return {
                "id": str(image.id),
                "url": f"{self.base_url}/{image.stored_filename}",
                "filename": image.filename,
                "stored_filename": image.stored_filename,
                "mime_type": image.mime_type,
                "file_size": image.file_size,
                "width": image.width,
                "height": image.height,
                "category": image.category,
                "description": image.description,
                "uploaded_by": image.uploaded_by,
                "created_at": image.created_at.isoformat(),
            }


# Singleton
_image_service: ImageService | None = None


def get_image_service() -> ImageService:
    """Get singleton image service instance."""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service
