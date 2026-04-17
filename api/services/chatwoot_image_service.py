"""
MSI Automotive - Chatwoot Image Download Service.

Downloads images from Chatwoot data URLs and stores them for case management.
Includes security validation to prevent SSRF and malicious file uploads.
"""

import asyncio
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from shared.config import get_settings
from shared.image_security import (
    PDF_MAX_PAGES,
    ImageSecurityError,
    get_extension_for_mime,
    sanitize_filename,
    validate_image_full,
    validate_url,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reason codes for download failures (7 canonical codes)
# ---------------------------------------------------------------------------

ReasonCode = Literal[
    "pdf_too_many_pages",
    "file_too_large",
    "file_type_not_allowed",
    "pdf_dangerous_content",
    "url_rejected",
    "corrupt_or_mismatch",
    "fallback_unknown",
]

# Spanish user-facing messages for each reason code.
# Uses format()-style placeholders resolved at module load time.
_CASE_IMAGES_MAX_SIZE_MB: int = 15  # fallback; overridden at service init if needed

REASON_MESSAGES: dict[str, str] = {
    "pdf_too_many_pages": (
        f"El PDF supera el máximo permitido de {PDF_MAX_PAGES} páginas. "
        "Envíalo dividido en partes más pequeñas."
    ),
    "file_too_large": (
        "El archivo supera el tamaño máximo permitido. "
        "Envíalo en menor resolución o divídelo."
    ),
    "file_type_not_allowed": (
        "El formato del archivo no está permitido. "
        "Envíalo como foto (JPG/PNG) o como PDF."
    ),
    "pdf_dangerous_content": (
        "No puedo procesar este PDF porque no superó la verificación de seguridad. "
        "Envíalo como foto o exporta uno nuevo sin elementos interactivos."
    ),
    "url_rejected": (
        "No pude acceder al archivo enviado. Reenvíalo por favor."
    ),
    "corrupt_or_mismatch": (
        "El archivo parece dañado o tiene un formato inconsistente. "
        "Hazle una foto nueva y reenvíala."
    ),
    "fallback_unknown": (
        "No pude procesar este archivo. "
        "Intenta enviarlo de nuevo — como foto (JPG/PNG) o como PDF."
    ),
}


@dataclass(frozen=True)
class DownloadResult:
    """
    Typed result for a single image download attempt.

    On success: success=True, data=<payload dict>, reason_code=None, reason_message=None.
    On failure: success=False, data=None, reason_code=<code>, reason_message=<Spanish string>.
    """

    success: bool
    data: dict[str, Any] | None = None
    reason_code: ReasonCode | None = None
    reason_message: str | None = None

    @classmethod
    def ok(cls, payload: dict[str, Any]) -> "DownloadResult":
        """Create a successful download result carrying the given payload."""
        return cls(success=True, data=payload)

    @classmethod
    def fail(cls, code: ReasonCode) -> "DownloadResult":
        """Create a failed download result for the given reason code."""
        return cls(
            success=False,
            reason_code=code,
            reason_message=REASON_MESSAGES[code],
        )


def _classify_security_error(exc: ImageSecurityError) -> ReasonCode:
    """
    Map an ImageSecurityError message to one of the 7 canonical reason codes.

    Uses prefix/substring matching on the exception message (brittle-resistant:
    all branches are unit-tested and a catch-all fallback_unknown handles drift).
    """
    msg = str(exc).lower()

    if "page limit" in msg or ("page" in msg and "exceed" in msg):
        return "pdf_too_many_pages"
    if "too large" in msg or "size exceeds" in msg:
        return "file_too_large"
    if "file type not allowed" in msg or "type not allowed" in msg:
        return "file_type_not_allowed"
    if "dangerous content" in msg or "javascript" in msg or "embedded" in msg:
        return "pdf_dangerous_content"
    if (
        "domain not allowed" in msg
        or "private/local" in msg
        or "invalid url scheme" in msg
        or "metadata endpoint" in msg
    ):
        return "url_rejected"
    if (
        "invalid image file" in msg
        or "decompression bomb" in msg
        or "corrupt" in msg
        or "magic" in msg
        or "mismatch" in msg
        or "too small" in msg
        or "could not detect" in msg
    ):
        return "corrupt_or_mismatch"

    return "fallback_unknown"


# Supported image MIME types
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/pdf",
}

# Mime type to extension mapping
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
    "application/pdf": "pdf",
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
        self.chatwoot_storage_domain = settings.CHATWOOT_STORAGE_DOMAIN

        # Allowed domains for image downloads (SSRF prevention)
        chatwoot_api_hostname = urlparse(self.chatwoot_api_url).hostname
        self.allowed_domains = []

        if chatwoot_api_hostname:
            self.allowed_domains.append(chatwoot_api_hostname)

        # Add storage domain if configured (for active_storage URLs)
        if self.chatwoot_storage_domain:
            self.allowed_domains.append(self.chatwoot_storage_domain)

        logger.info(f"Chatwoot image download allowed domains: {self.allowed_domains}")

        # Ensure directory exists
        self.case_images_dir.mkdir(parents=True, exist_ok=True)

    async def download_image(
        self,
        data_url: str,
        display_name: str,
        element_code: str | None = None,
    ) -> "DownloadResult":
        """
        Download an image from Chatwoot and store it locally.

        Args:
            data_url: URL to download the image from (Chatwoot data_url)
            display_name: Descriptive name for the image (e.g., "escape_foto_general")
            element_code: Optional element code this image relates to

        Returns:
            DownloadResult: success=True with data payload on success, or
            success=False with reason_code and reason_message on failure.
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_DOWNLOAD_RETRIES):
            try:
                return await self._download_with_retry(
                    data_url, display_name, element_code, attempt
                )
            except ImageSecurityError as e:
                # Security errors are permanent — no retry value, classify immediately.
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {data_url}: {e}"
                )
                last_exc = e
                break
            except Exception as e:
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {data_url}: {e}"
                )
                last_exc = e
                if attempt < MAX_DOWNLOAD_RETRIES - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

        logger.error(f"All download attempts failed for {data_url}")
        if isinstance(last_exc, ImageSecurityError):
            return DownloadResult.fail(_classify_security_error(last_exc))
        return DownloadResult.fail("fallback_unknown")

    async def _download_with_retry(
        self,
        data_url: str,
        display_name: str,
        element_code: str | None,
        attempt: int,
    ) -> "DownloadResult":
        """Internal download method with single attempt and security validation."""
        # SECURITY: Validate URL (SSRF prevention)
        try:
            validate_url(data_url, self.allowed_domains)
        except ImageSecurityError as e:
            logger.error(f"URL validation failed: {e} | URL: {data_url}")
            raise

        headers = {}

        # Add Chatwoot auth header if URL is from Chatwoot
        if self.chatwoot_api_url in data_url:
            headers["api_access_token"] = self.chatwoot_api_token

        # SECURITY: Handle redirects manually to validate each redirect URL
        # This prevents SSRF via malicious redirects while allowing valid Chatwoot redirects
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            current_url = data_url
            max_redirects = 5
            redirect_count = 0
            
            while redirect_count <= max_redirects:
                response = await client.get(current_url, headers=headers, follow_redirects=False)
                
                # Check if it's a redirect
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get("location")
                    if not redirect_url:
                        raise Exception(f"Redirect {response.status_code} without Location header")
                    
                    # Handle relative URLs
                    if redirect_url.startswith("/"):
                        parsed = urlparse(current_url)
                        redirect_url = f"{parsed.scheme}://{parsed.netloc}{redirect_url}"
                    
                    # SECURITY: Validate redirect URL is also in allowed domains
                    try:
                        validate_url(redirect_url, self.allowed_domains)
                    except ImageSecurityError as e:
                        logger.error(f"Redirect URL validation failed: {e} | Redirect: {redirect_url}")
                        raise
                    
                    logger.debug(f"Following redirect {redirect_count + 1}: {redirect_url}")
                    current_url = redirect_url
                    redirect_count += 1
                    continue
                
                # Not a redirect, check for errors
                response.raise_for_status()
                break
            else:
                raise Exception(f"Too many redirects ({max_redirects})")

            content = response.content
            file_size = len(content)

            # Check file size BEFORE expensive validation
            if file_size > self.max_size:
                logger.warning(
                    f"Image too large ({file_size} bytes > {self.max_size}): {data_url}"
                )
                raise ImageSecurityError(f"File too large: {file_size} bytes exceeds size limit")

            # Get declared MIME type from response
            declared_mime = response.headers.get("content-type", "").split(";")[0].strip()
            if not declared_mime or declared_mime == "application/octet-stream":
                parsed_url = urlparse(data_url)
                guessed = mimetypes.guess_type(parsed_url.path)[0]
                declared_mime = guessed or "image/jpeg"

            # SECURITY: Full image validation (magic numbers + PIL)
            try:
                validation_result = validate_image_full(
                    content=content,
                    declared_mime=declared_mime,
                    url=data_url,
                    allowed_domains=self.allowed_domains,
                )
            except ImageSecurityError as e:
                logger.error(f"Image security validation failed: {e} | URL: {data_url}")
                raise

            # Use validated MIME type and dimensions
            mime_type = validation_result["detected_mime"]
            width = validation_result["width"]
            height = validation_result["height"]

            # Get extension from validated MIME type
            ext = get_extension_for_mime(mime_type)

            # Generate stored filename
            stored_filename = f"{uuid.uuid4()}.{ext}"
            file_path = self.case_images_dir / stored_filename

            # Extract and SANITIZE original filename
            original_filename = None
            content_disposition = response.headers.get("content-disposition", "")
            if "filename=" in content_disposition:
                try:
                    extracted = content_disposition.split("filename=")[1].strip("\"'")
                    original_filename = sanitize_filename(extracted)
                except Exception:
                    pass
            if not original_filename:
                parsed_url = urlparse(data_url)
                path_parts = parsed_url.path.split("/")
                if path_parts and "." in path_parts[-1]:
                    original_filename = sanitize_filename(path_parts[-1])

            # Save validated file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(
                f"Image downloaded and validated: {stored_filename} "
                f"({width}x{height}, {file_size} bytes, {mime_type})"
            )

            return DownloadResult.ok({
                "stored_filename": stored_filename,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "file_size": file_size,
                "width": width,
                "height": height,
                "display_name": display_name,
                "element_code": element_code,
                "file_path": str(file_path),
            })

    async def download_multiple_images(
        self,
        images: list[dict[str, Any]],
    ) -> list["DownloadResult"]:
        """
        Download multiple images concurrently.

        Args:
            images: List of dicts with:
                - data_url: URL to download
                - display_name: Descriptive name
                - element_code: Optional element code

        Returns:
            List of DownloadResult — one per input image (success or failure).
            All results are included so callers can inspect failure reason codes.
        """
        tasks = [
            self.download_image(
                img["data_url"],
                img["display_name"],
                img.get("element_code"),
            )
            for img in images
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[DownloadResult] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                logger.error(f"Image download failed: {images[i]['data_url']}: {result}")
                results.append(DownloadResult.fail("fallback_unknown"))
            else:
                results.append(result)  # type: ignore[arg-type]

        return results

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
            "pdf": "application/pdf",
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
