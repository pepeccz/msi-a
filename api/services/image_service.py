"""
MSI Automotive - Image Storage Service.

Handles image upload, storage, and retrieval for documentation images.
"""

import logging
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select

from database.connection import get_async_session
from database.models import UploadedImage
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Allowed MIME types
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


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
        Upload an image and store metadata.

        Args:
            file: FastAPI UploadFile
            category: Optional category for organization
            description: Optional description
            username: Username of uploader

        Returns:
            Dict with image metadata and URL
        """
        # Validate file type
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de archivo no permitido. Permitidos: {', '.join(ALLOWED_MIME_TYPES)}",
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        if file_size > self.max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Archivo demasiado grande. Maximo: {self.max_size // 1024 // 1024}MB",
            )

        # Generate unique filename
        original_filename = file.filename or "image"
        ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else "jpg"
        stored_filename = f"{uuid.uuid4()}.{ext}"
        file_path = self.upload_dir / stored_filename

        # Get image dimensions
        width, height = None, None
        try:
            from PIL import Image

            img = Image.open(BytesIO(content))
            width, height = img.size
        except Exception as e:
            logger.warning(f"Could not read image dimensions: {e}")

        # Save file
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Image saved: {stored_filename} ({file_size} bytes)")

        # Save metadata to database
        async with get_async_session() as session:
            image = UploadedImage(
                filename=original_filename,
                stored_filename=stored_filename,
                mime_type=file.content_type,
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
                "mime_type": file.content_type,
                "file_size": file_size,
                "width": width,
                "height": height,
                "category": category,
                "description": description,
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
                        "mime_type": img.mime_type,
                        "file_size": img.file_size,
                        "width": img.width,
                        "height": img.height,
                        "category": img.category,
                        "description": img.description,
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
                "mime_type": image.mime_type,
                "file_size": image.file_size,
                "width": image.width,
                "height": image.height,
                "category": image.category,
                "description": image.description,
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
