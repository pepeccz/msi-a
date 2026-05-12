"""
MSI Automotive — Conversation Images serving endpoint.

Serves image attachments stored locally for conversation messages.
Images are stored at: uploads/conversation_images/{conv_id}/{uuid}.{ext}

Authentication: requires valid admin JWT (same dep as /images/ admin routes).
The endpoint is proxied same-origin via Next.js rewrite:
  /conversation-images/:path* → {API_URL}/conversation-images/:path*

Security:
  - sanitize_filename() prevents path traversal in the filename segment.
  - path.is_relative_to() guard ensures the resolved path stays within
    the expected directory even after filename sanitization.
  - No directory listing — only direct file serving.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, UTC
from pathlib import Path
from typing import AsyncIterator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin import require_role
from database.connection import get_async_session
from database.models import AdminUser, MessageAttachment, ConversationMessage
from shared.config import get_settings
from shared.image_security import sanitize_filename

logger = structlog.get_logger(__name__)

router = APIRouter()


# NOTE: route order matters — the zip route MUST be declared before the
# catch-all {filename} route below, otherwise FastAPI will match "zip"
# as a filename parameter and never reach this handler.
@router.get("/conversation-images/zip/{conv_id}")
async def download_conversation_images_zip(
    conv_id: UUID,
    ids: str = Query(..., description="Comma-separated MessageAttachment UUIDs"),
    user: AdminUser = Depends(require_role("admin", "agente_humano", "solo_lectura")),
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """
    Stream a zip archive containing the requested attachments.

    Used by the inbox frontend to support drag-out of an entire album to
    the OS file explorer (browsers only allow one URL per drag operation,
    so multi-image albums are packed into a single zip).

    Security:
      - Each attachment ID is validated to belong to a message inside
        ``conv_id``. IDs that don't match are silently dropped (no info
        leak about other conversations).
      - Filenames inside the zip are sanitized to prevent zip-slip.

    Args:
        conv_id: Conversation UUID (folder name on disk).
        ids: Comma-separated MessageAttachment UUIDs.

    Returns:
        StreamingResponse with ``application/zip`` content.

    Raises:
        HTTPException 400: malformed UUID in ``ids``.
        HTTPException 404: no attachments matched.
    """
    settings = get_settings()
    uploads_base = Path(settings.UPLOADS_DIR)
    base_dir = (uploads_base / "conversation_images" / str(conv_id)).resolve()

    try:
        attachment_ids = [UUID(s.strip()) for s in ids.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment id(s)")

    if not attachment_ids:
        raise HTTPException(status_code=400, detail="No attachment ids provided")

    stmt = (
        select(MessageAttachment, ConversationMessage.conversation_history_id)
        .join(ConversationMessage, MessageAttachment.message_id == ConversationMessage.id)
        .where(MessageAttachment.id.in_(attachment_ids))
        .order_by(ConversationMessage.created_at, MessageAttachment.position)
    )
    result = await session.execute(stmt)
    rows = result.all()

    files_to_zip: list[tuple[Path, str]] = []
    counter = 1
    for attachment, _conv_history_id in rows:
        url_parts = attachment.url.rsplit("/", 2)
        if len(url_parts) < 2:
            continue
        url_conv_id, url_filename = url_parts[-2], url_parts[-1]
        if url_conv_id != str(conv_id):
            continue  # silently drop cross-conversation IDs

        safe_filename = sanitize_filename(url_filename)
        disk_path = (base_dir / safe_filename).resolve()
        if not disk_path.is_relative_to(base_dir) or not disk_path.is_file():
            continue

        if attachment.filename:
            name_in_zip = sanitize_filename(attachment.filename)
        else:
            ext = disk_path.suffix or ".jpg"
            name_in_zip = f"imagen_{counter:02d}{ext}"
        files_to_zip.append((disk_path, name_in_zip))
        counter += 1

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="No matching attachments")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}
        for disk_path, name in files_to_zip:
            count = seen_names.get(name, 0)
            if count > 0:
                stem = Path(name).stem
                suffix = Path(name).suffix
                final_name = f"{stem}_{count}{suffix}"
            else:
                final_name = name
            seen_names[name] = count + 1
            zf.write(disk_path, arcname=final_name)

    buffer.seek(0)

    logger.info(
        "conversation_images_zip_served",
        conv_id=str(conv_id),
        file_count=len(files_to_zip),
        size_bytes=buffer.getbuffer().nbytes,
        admin_user_id=str(user.id),
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    download_filename = f"imagenes_{conv_id}_{timestamp}.zip"

    async def stream() -> AsyncIterator[bytes]:
        chunk_size = 64 * 1024
        while True:
            chunk = buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"',
            "Content-Length": str(buffer.getbuffer().nbytes),
        },
    )


@router.get("/conversation-images/{conv_id}/{filename}")
async def serve_conversation_image(
    conv_id: UUID,
    filename: str,
    user: AdminUser = Depends(require_role("admin", "agente_humano", "solo_lectura")),
) -> FileResponse:
    """
    Serve a conversation image attachment.

    Requires valid admin JWT with one of the allowed roles:
    admin, agente_humano, or solo_lectura (design A2). This explicit guard
    ensures new roles added in the future do NOT get automatic access.

    Args:
        conv_id: UUID of the conversation (sub-directory name).
        filename: Stored filename (UUID-based, e.g. ``{uuid}.jpg``).
        user: Injected authenticated admin user (auth guard only).

    Returns:
        FileResponse with the image content.

    Raises:
        HTTPException 404: File not found or path traversal blocked.
    """
    settings = get_settings()
    uploads_base = Path(settings.UPLOADS_DIR)

    # Sanitize to prevent path traversal via the filename segment
    safe_filename = sanitize_filename(filename)

    base_dir = (uploads_base / "conversation_images" / str(conv_id)).resolve()
    candidate_path = (base_dir / safe_filename).resolve()

    # Guard: ensure resolved path stays inside the per-conversation directory
    if not candidate_path.is_relative_to(base_dir):
        logger.warning(
            "conv_image_path_traversal_blocked",
            conv_id=str(conv_id),
            filename=filename,
            safe_filename=safe_filename,
        )
        raise HTTPException(status_code=404, detail="Not found")

    if not candidate_path.exists() or not candidate_path.is_file():
        logger.warning(
            "conv_image_missing",
            conv_id=str(conv_id),
            filename=safe_filename,
        )
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(candidate_path)
