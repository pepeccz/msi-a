"""
ConversationImageService — persist image attachments for ConversationMessage rows.

Three entry points:
  - download_and_persist_inbound: called by the attachment download worker for user-sent images
  - persist_outbound_urls: called after bot sends images (no download, URL-only)
  - store_admin_upload: called by the admin upload endpoint (validate → temp write → send → commit)
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog

import httpx

from database.models import MessageAttachment
from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings
from shared.image_security import (
    ImageSecurityError,
    sanitize_filename,
    validate_image_full,
    validate_url,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from fastapi import UploadFile
    from database.models import ConversationMessage

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ATTACHMENT_DOWNLOAD_TIMEOUT = 30  # seconds per attempt
ATTACHMENT_RETRY_DELAYS = (1.0, 4.0, 16.0)  # exponential backoff: attempt 0, 1, 2

# Only image/* MIME types are processed; all others are silently dropped
_IMAGE_MIME_PREFIX = "image/"


# ---------------------------------------------------------------------------
# Low-level download helper (SSRF-safe, auth-aware)
# ---------------------------------------------------------------------------


async def download_chatwoot_image(url: str) -> bytes:
    """
    Download an image from a Chatwoot data URL and return raw bytes.

    Authentication:
      - Sends ``api_access_token`` header when the URL belongs to the Chatwoot API domain.

    SSRF prevention:
      - ``validate_url`` must be called BEFORE this function (see caller in
        ``download_and_persist_inbound``).

    Retries are handled by the caller (worker level); this helper does a single
    HTTP GET and raises on non-2xx responses or network errors.
    """
    settings = get_settings()
    headers: dict[str, str] = {}

    if settings.CHATWOOT_API_URL and settings.CHATWOOT_API_URL in url:
        headers["api_access_token"] = settings.CHATWOOT_API_TOKEN

    async with httpx.AsyncClient(timeout=ATTACHMENT_DOWNLOAD_TIMEOUT, follow_redirects=False) as client:
        current_url = url
        max_redirects = 5
        redirects = 0

        while redirects <= max_redirects:
            response = await client.get(current_url, headers=headers)

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location:
                    raise OSError(f"Redirect with no Location header from {current_url}")
                # Validate the redirect target before following (SSRF prevention)
                settings2 = get_settings()
                allowed = _get_allowed_domains(settings2)
                validate_url(location, allowed)
                current_url = location
                redirects += 1
                continue

            if response.status_code >= 400:
                raise OSError(f"HTTP {response.status_code} fetching {current_url}")

            return response.content

    raise OSError(f"Exceeded {max_redirects} redirects fetching {url}")


def _get_allowed_domains(settings) -> list[str]:
    """Build SSRF allowlist from settings."""
    domains: list[str] = []
    if settings.CHATWOOT_API_URL:
        hostname = urlparse(settings.CHATWOOT_API_URL).hostname
        if hostname:
            domains.append(hostname)
    if settings.CHATWOOT_STORAGE_DOMAIN:
        domains.append(settings.CHATWOOT_STORAGE_DOMAIN)
    return domains


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class ConversationImageService:
    """
    Manages persistence of image attachments for ConversationMessage rows.

    Instantiated with ``uploads_base`` (defaults to settings.UPLOADS_DIR) to
    allow dependency injection in tests.
    """

    def __init__(self, uploads_base: Path | None = None) -> None:
        if uploads_base is None:
            settings = get_settings()
            self.uploads_base = Path(settings.UPLOADS_DIR)
        else:
            self.uploads_base = uploads_base

    # ------------------------------------------------------------------
    # Inbound (user-sent via Chatwoot)
    # ------------------------------------------------------------------

    async def download_and_persist_inbound(
        self,
        session: "AsyncSession",
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        chatwoot_attachments: list[dict],
    ) -> list[MessageAttachment]:
        """
        Download, validate, store, and persist inbound image attachments.

        Only processes attachments whose ``type`` starts with ``image/``.
        Non-image attachments (PDF, audio, video) are silently dropped.

        On validation or download failure: the attachment row is skipped,
        a WARNING is logged, and processing continues for remaining attachments.

        Args:
            session: Active AsyncSession (caller is responsible for commit/flush).
            conversation_id: UUID of the ConversationHistory row.
            message_id: UUID of the ConversationMessage row that owns these attachments.
            chatwoot_attachments: List of dicts with keys ``url``, ``name``, ``type``.

        Returns:
            List of persisted MessageAttachment rows (may be shorter than input
            if some attachments were skipped due to validation failures).
        """
        settings = get_settings()
        allowed_domains = _get_allowed_domains(settings)

        # Destination directory for this conversation's images
        conv_dir = self.uploads_base / "conversation_images" / str(conversation_id)
        conv_dir.mkdir(parents=True, exist_ok=True)

        rows: list[MessageAttachment] = []
        position = 0

        for att in chatwoot_attachments:
            url: str = att.get("url", "")
            name: str = att.get("name", "")
            content_type: str = att.get("type", "")

            # Skip non-image attachments silently
            if not content_type.startswith(_IMAGE_MIME_PREFIX):
                logger.debug(
                    "attachment_skipped_non_image",
                    extra={"url": url, "content_type": content_type},
                )
                continue

            try:
                # SSRF check before any network call
                validate_url(url, allowed_domains)

                # Download bytes
                image_bytes = await download_chatwoot_image(url)

                # Security validation (magic numbers + PIL)
                validation = validate_image_full(image_bytes, declared_mime=content_type)
                detected_mime: str = validation["detected_mime"]
                width: int | None = validation.get("width")
                height: int | None = validation.get("height")
                file_size: int | None = validation.get("file_size")

                # Determine extension from detected MIME
                ext = _mime_to_ext(detected_mime)
                stored_name = f"{uuid.uuid4()}.{ext}"

                # Write to disk
                dest_path = conv_dir / stored_name
                dest_path.write_bytes(image_bytes)

                # Relative URL served by GET /conversation-images/{conv_id}/{filename}
                relative_url = f"/conversation-images/{conversation_id}/{stored_name}"

                row = MessageAttachment(
                    message_id=message_id,
                    kind="image",
                    url=relative_url,
                    chatwoot_url=url,
                    content_type=detected_mime,
                    filename=sanitize_filename(name) if name else stored_name,
                    size_bytes=file_size,
                    width=width,
                    height=height,
                    position=position,
                )
                session.add(row)
                rows.append(row)
                position += 1

            except ImageSecurityError as exc:
                logger.warning(
                    "inbound_attachment_validation_failed",
                    message_id=str(message_id),
                    chatwoot_url=url,
                    reason=str(exc),
                )
            except Exception as exc:
                logger.error(
                    "inbound_attachment_download_failed",
                    message_id=str(message_id),
                    chatwoot_url=url,
                    error=str(exc),
                )

        if rows:
            await session.flush()

        return rows

    # ------------------------------------------------------------------
    # Outbound (bot-sent via send_images)
    # ------------------------------------------------------------------

    async def persist_outbound_urls(
        self,
        session: "AsyncSession",
        message_id: uuid.UUID,
        image_urls: list[str],
    ) -> list[MessageAttachment]:
        """
        Persist bot-sent image URLs as MessageAttachment rows.

        The URLs are already public (served from our /images/ or /case-images/ endpoint).
        No download or validation is performed — bot-outbound images have already been
        validated during the case collection phase.

        Width, height, and chatwoot_url are left null for outbound rows.

        Args:
            session: Active AsyncSession.
            message_id: UUID of the ConversationMessage row.
            image_urls: Ordered list of URLs the bot sent to Chatwoot.

        Returns:
            List of persisted MessageAttachment rows.
        """
        if not image_urls:
            return []

        rows: list[MessageAttachment] = []
        for position, url in enumerate(image_urls):
            row = MessageAttachment(
                message_id=message_id,
                kind="image",
                url=url,
                chatwoot_url=None,
                content_type=None,
                filename=None,
                size_bytes=None,
                width=None,
                height=None,
                position=position,
            )
            session.add(row)
            rows.append(row)

        await session.flush()
        return rows

    # ------------------------------------------------------------------
    # Admin upload (multipart/form-data)
    # ------------------------------------------------------------------

    async def store_admin_upload(
        self,
        session: "AsyncSession",
        conversation_id: uuid.UUID,
        conversation_history_id: uuid.UUID,
        conversation_chatwoot_id: str,
        files: list["UploadFile"],
        caption: str | None,
        admin_user_id: uuid.UUID,
    ) -> tuple["ConversationMessage", list[MessageAttachment]]:
        """
        Validate, persist, and send admin-uploaded images via Chatwoot.

        Rollback order (see Design A3):
          1. Read all files into memory.
          2. validate_image_full for each — fail-fast HTTP 400 on any failure.
          3. Write to temp paths (.tmp_{uuid}.{ext}) inside conv_dir.
          4. Build DB objects (not yet added to session).
          5. Send via Chatwoot using the FINAL public URLs. On failure →
             delete temp files, raise HTTP 500.
          6. On success: rename temp → final paths (os.replace — atomic on same FS).
          7. Return (message, attachments) — caller adds to session and commits.

        Args:
            session: Active AsyncSession — caller adds rows and commits.
            conversation_id: Internal UUID of the conversation (used for disk path).
            conversation_history_id: FK for ConversationMessage.conversation_history_id
                (NOT NULL). Caller must look this up from the ConversationHistory row
                before calling this method.
            conversation_chatwoot_id: Numeric string used for the Chatwoot API call.
            files: List of UploadFile objects (1–10).
            caption: Optional message caption.
            admin_user_id: UUID of the admin performing the upload.

        Returns:
            (ConversationMessage, list[MessageAttachment]) — caller must add and commit.

        Raises:
            HTTPException 400: Validation failure.
            HTTPException 500: Chatwoot send failure.
        """
        import os
        from fastapi import HTTPException
        from database.models import ConversationMessage

        conv_dir = self.uploads_base / "conversation_images" / str(conversation_id)
        conv_dir.mkdir(parents=True, exist_ok=True)

        # Step 1 + 2: Read into memory and validate each file
        validated: list[tuple[bytes, dict, str]] = []  # (bytes, validation_result, original_filename)
        for f in files:
            content = await f.read()
            try:
                result = validate_image_full(content, declared_mime=f.content_type or "")
            except ImageSecurityError as exc:
                raise HTTPException(status_code=400, detail=f"Imagen inválida: {exc}") from exc
            validated.append((content, result, f.filename or "upload"))

        # Step 3: Write temp files
        temp_items: list[tuple[Path, Path, str, dict, str]] = []
        # Each tuple: (temp_path, final_path, ext, validation_result, original_filename)
        for content_bytes, validation_result, original_filename in validated:
            detected_mime = validation_result["detected_mime"]
            ext = _mime_to_ext(detected_mime)
            file_uuid = str(uuid.uuid4())
            temp_path = conv_dir / f".tmp_{file_uuid}.{ext}"
            final_path = conv_dir / f"{file_uuid}.{ext}"
            temp_path.write_bytes(content_bytes)
            temp_items.append((temp_path, final_path, ext, validation_result, original_filename))

        # Step 4: Build DB objects (not yet added to session)
        msg = ConversationMessage(
            conversation_history_id=conversation_history_id,
            role="human_agent",
            author_type="human_agent",
            author_user_id=admin_user_id,
            content=caption or "",
            has_images=True,
            image_count=len(files),
        )

        attachment_rows: list[MessageAttachment] = []
        final_urls: list[str] = []
        for position, (_, final_path, _, validation_result, original_filename) in enumerate(temp_items):
            detected_mime = validation_result["detected_mime"]
            relative_url = f"/conversation-images/{conversation_id}/{final_path.name}"
            final_urls.append(relative_url)
            row = MessageAttachment(
                kind="image",
                url=relative_url,
                chatwoot_url=None,
                content_type=detected_mime,
                filename=sanitize_filename(original_filename),
                size_bytes=validation_result.get("file_size"),
                width=validation_result.get("width"),
                height=validation_result.get("height"),
                position=position,
                uploaded_by_admin_user_id=admin_user_id,
            )
            attachment_rows.append(row)

        # Step 5: Send to Chatwoot using the relative URLs (the API serves these)
        try:
            client = ChatwootClient()
            settings = get_settings()
            # Build absolute URLs for Chatwoot by prepending the API base URL
            api_base = getattr(settings, "API_BASE_URL", "") or ""
            absolute_urls = [
                f"{api_base}{url}" if not url.startswith("http") else url
                for url in final_urls
            ]
            await client.send_images(
                conversation_id=int(conversation_chatwoot_id),
                image_urls=absolute_urls,
                caption_first=caption,
            )
        except Exception as exc:
            # Cleanup temp files on failure
            for temp_path, _, _, _, _ in temp_items:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            logger.error(
                "admin_upload_chatwoot_send_failed",
                extra={
                    "conversation_id": str(conversation_id),
                    "error": str(exc),
                },
            )
            raise HTTPException(status_code=500, detail="Error al enviar imágenes a Chatwoot") from exc

        # Step 6: Atomic rename temp → final (only after successful Chatwoot send)
        for temp_path, final_path, _, _, _ in temp_items:
            os.replace(str(temp_path), str(final_path))

        return msg, attachment_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mime_to_ext(mime: str) -> str:
    """Map a detected MIME type to a file extension."""
    mapping = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }
    return mapping.get(mime, "jpg")


# Singleton accessor
_service: ConversationImageService | None = None


def get_conversation_image_service() -> ConversationImageService:
    """Return the module-level singleton ConversationImageService."""
    global _service
    if _service is None:
        _service = ConversationImageService()
    return _service
