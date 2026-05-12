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

from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.routes.admin import require_role
from database.models import AdminUser
from shared.config import get_settings
from shared.image_security import sanitize_filename

logger = structlog.get_logger(__name__)

router = APIRouter()


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
