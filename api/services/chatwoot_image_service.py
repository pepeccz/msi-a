"""
MSI Automotive - Chatwoot Image Download Service.

Downloads images from Chatwoot data URLs and stores them for case management.
"""

import asyncio
import logging
import mimetypes
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from shared.config import get_settings

logger = logging.getLogger(__name__)

# Supported image MIME types
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}

# Mime type to extension mapping
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}

# Download timeout in seconds
DOWNLOAD_TIMEOUT = 30

# Max retries for download
MAX_DOWNLOAD_RETRIES = 3


class ChatwootImageService:
    """
    Service for downloading and storing images from Chatwoot.

    Used during case collection to store user-uploaded images.
    """

    def __init__(self):
        settings = get_settings()
        self.case_images_dir = Path(settings.CASE_IMAGES_DIR)
        self.base_url = settings.CASE_IMAGES_BASE_URL
        self.max_size = settings.CASE_IMAGES_MAX_SIZE_MB * 1024 * 1024  # bytes
        self.chatwoot_api_url = settings.CHATWOOT_API_URL
        self.chatwoot_api_token = settings.CHATWOOT_API_TOKEN

        # Ensure directory exists
        self.case_images_dir.mkdir(parents=True, exist_ok=True)

    async def download_image(
        self,
        data_url: str,
        display_name: str,
        element_code: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Download an image from Chatwoot and store it locally.

        Args:
            data_url: URL to download the image from (Chatwoot data_url)
            display_name: Descriptive name for the image (e.g., "escape_foto_general")
            element_code: Optional element code this image relates to

        Returns:
            Dict with stored image info, or None if download failed:
            {
                "stored_filename": str,
                "original_filename": str | None,
                "mime_type": str,
                "file_size": int,
                "display_name": str,
                "element_code": str | None,
                "file_path": str,
            }
        """
        for attempt in range(MAX_DOWNLOAD_RETRIES):
            try:
                return await self._download_with_retry(
                    data_url, display_name, element_code, attempt
                )
            except Exception as e:
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {data_url}: {e}"
                )
                if attempt < MAX_DOWNLOAD_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"All download attempts failed for {data_url}")
                    return None

        return None

    async def _download_with_retry(
        self,
        data_url: str,
        display_name: str,
        element_code: str | None,
        attempt: int,
    ) -> dict[str, Any] | None:
        """Internal download method with single attempt."""
        headers = {}

        # Add Chatwoot auth header if URL is from Chatwoot
        if self.chatwoot_api_url in data_url:
            headers["api_access_token"] = self.chatwoot_api_token

        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            response = await client.get(data_url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            content = response.content
            file_size = len(content)

            # Check file size
            if file_size > self.max_size:
                logger.warning(
                    f"Image too large ({file_size} bytes > {self.max_size}): {data_url}"
                )
                return None

            # Determine MIME type
            mime_type = response.headers.get("content-type", "").split(";")[0].strip()
            if not mime_type or mime_type == "application/octet-stream":
                # Try to guess from URL
                parsed_url = urlparse(data_url)
                guessed = mimetypes.guess_type(parsed_url.path)[0]
                mime_type = guessed or "image/jpeg"

            # Validate image type
            if mime_type not in SUPPORTED_IMAGE_TYPES:
                logger.warning(f"Unsupported image type {mime_type}: {data_url}")
                # Still try to process - might be incorrectly labeled
                mime_type = "image/jpeg"

            # Get extension
            ext = MIME_TO_EXT.get(mime_type, "jpg")

            # Generate stored filename
            stored_filename = f"{uuid.uuid4()}.{ext}"
            file_path = self.case_images_dir / stored_filename

            # Try to extract original filename from URL or headers
            original_filename = None
            content_disposition = response.headers.get("content-disposition", "")
            if "filename=" in content_disposition:
                try:
                    original_filename = content_disposition.split("filename=")[1].strip('"\'')
                except Exception:
                    pass
            if not original_filename:
                parsed_url = urlparse(data_url)
                path_parts = parsed_url.path.split("/")
                if path_parts and "." in path_parts[-1]:
                    original_filename = path_parts[-1]

            # Save file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(
                f"Image downloaded and saved: {stored_filename} "
                f"({file_size} bytes, {mime_type})"
            )

            return {
                "stored_filename": stored_filename,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "file_size": file_size,
                "display_name": display_name,
                "element_code": element_code,
                "file_path": str(file_path),
            }

    async def download_multiple_images(
        self,
        images: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Download multiple images concurrently.

        Args:
            images: List of dicts with:
                - data_url: URL to download
                - display_name: Descriptive name
                - element_code: Optional element code

        Returns:
            List of successfully downloaded image info dicts
        """
        tasks = [
            self.download_image(
                img["data_url"],
                img["display_name"],
                img.get("element_code"),
            )
            for img in images
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        downloaded = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Image download failed: {images[i]['data_url']}: {result}")
            elif result is not None:
                downloaded.append(result)

        return downloaded

    def get_image_path(self, stored_filename: str) -> Path | None:
        """Get full path for a stored image."""
        path = self.case_images_dir / stored_filename
        if path.exists():
            return path
        return None

    def get_image_url(self, stored_filename: str) -> str:
        """Get URL for serving a stored image."""
        return f"{self.base_url}/{stored_filename}"

    def delete_image(self, stored_filename: str) -> bool:
        """
        Delete a stored image.

        Args:
            stored_filename: Filename to delete

        Returns:
            True if deleted, False if not found
        """
        path = self.case_images_dir / stored_filename
        if path.exists():
            path.unlink()
            logger.info(f"Case image deleted: {stored_filename}")
            return True
        return False

    async def get_image_bytes(self, stored_filename: str) -> tuple[bytes, str] | None:
        """
        Read image bytes from storage.

        Args:
            stored_filename: Filename to read

        Returns:
            Tuple of (bytes, mime_type) or None if not found
        """
        path = self.case_images_dir / stored_filename
        if not path.exists():
            return None

        ext = stored_filename.rsplit(".", 1)[-1].lower()
        mime_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")

        with open(path, "rb") as f:
            return f.read(), mime_type


# Singleton
_chatwoot_image_service: ChatwootImageService | None = None


def get_chatwoot_image_service() -> ChatwootImageService:
    """Get singleton Chatwoot image service instance."""
    global _chatwoot_image_service
    if _chatwoot_image_service is None:
        _chatwoot_image_service = ChatwootImageService()
    return _chatwoot_image_service
