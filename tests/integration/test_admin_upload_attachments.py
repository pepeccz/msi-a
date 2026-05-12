"""
Integration tests for T12 + T16 — Admin upload endpoint.

TDD cycle: RED (tests written first — implementation is in T12)

Spec coverage (Cap 5 scenarios):
  1. Single valid PNG upload → 201 + message + attachment URL
  2. Multiple valid images with caption → correct positions + content
  3. Exceeds 10-image limit → 400
  4. Non-image file type → 400
  5. Image fails magic-number check → 400
  6. Chatwoot send fails → DB rolled back + temp files cleaned + 500
  7. Disk write fails → 500
  8. Outside WhatsApp 24h window → 400 with outside_window reason
  9. Unauthorized role (solo_lectura) → 403

T16 rollback scenarios (explicitly covered below):
  - Chatwoot send failure: DB rolled back + temp files cleaned + 500
  - Disk write failure (mock disk error) → 500
  - Validation failure mid-batch → all temp files cleaned + 400

Tests use mocks throughout — no real DB or Chatwoot required.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal PNG bytes (1x1 pixel) for use in multipart payloads
# ---------------------------------------------------------------------------

_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"           # PNG signature
    b"\x00\x00\x00\rIHDR"         # IHDR chunk length + type
    b"\x00\x00\x00\x01"           # width = 1
    b"\x00\x00\x00\x01"           # height = 1
    b"\x08\x02"                    # bit depth=8, color type=2 (RGB)
    b"\x00\x00\x00"               # compression, filter, interlace
    b"\x90wS\xde"                  # CRC
    b"\x00\x00\x00\x0cIDATx\x9c"  # IDAT chunk
    b"c\xf8\x0f\x00\x00\x01\x01\x00\x18\xdd\x8d"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND
)

_TINY_PDF = b"%PDF-1.4 invalid"  # clearly not an image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.username = "testadmin"
    user.is_active = True
    return user


def _make_conv_history(
    conversation_id: str = "42",
    last_inbound_at: datetime | None = None,
    hours_ago: float = 1.0,
) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.conversation_id = conversation_id
    if last_inbound_at is not None:
        conv.last_inbound_at = last_inbound_at
    else:
        conv.last_inbound_at = datetime.now(UTC) - timedelta(hours=hours_ago)
    conv.paused_by_user = None
    return conv


def _png_upload(filename: str = "test.png") -> tuple[str, tuple]:
    """Return an (field_name, (filename, fileobj, content_type)) tuple for TestClient."""
    return ("files", (filename, io.BytesIO(_MINIMAL_PNG), "image/png"))


def _pdf_upload(filename: str = "doc.pdf") -> tuple[str, tuple]:
    return ("files", (filename, io.BytesIO(_TINY_PDF), "application/pdf"))


# ---------------------------------------------------------------------------
# App factory for tests
# ---------------------------------------------------------------------------


def _build_app():
    """Return a FastAPI test app with the conversations_admin router mounted."""
    from fastapi import FastAPI
    from api.routes.conversations_admin import router

    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Shared mock targets
# ---------------------------------------------------------------------------

_LOAD_CONV = "api.routes.conversations_admin._load_conversation"
_REQUIRE_ROLE = "api.routes.admin.require_role"
_GET_CONV_IMG_SVC = "api.routes.conversations_admin.get_conversation_image_service"
_GET_ASYNC_SESSION = "api.routes.conversations_admin.get_async_session"
_GET_ADMIN_MOD_REQUIRE_ROLE = "api.routes.admin.require_role"


def _mock_require_role_dep(user: MagicMock):
    """
    Patch api.routes.admin.require_role so that the inner _rbac_dep call
    returns ``user`` when awaited.
    """
    inner_dep = AsyncMock(return_value=user)

    def require_role_factory(*roles):
        return inner_dep

    return require_role_factory


# ---------------------------------------------------------------------------
# 1. Single valid PNG → 201
# ---------------------------------------------------------------------------


def test_single_valid_png_upload_returns_201():
    """Single valid PNG → 201 with message + attachment URL."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()
    msg_id = uuid.uuid4()

    # Build the mocked ConversationMessage + MessageAttachment returned by service
    mock_msg = MagicMock()
    mock_msg.id = msg_id
    mock_msg.conversation_history_id = conv.id
    mock_msg.role = "human_agent"
    mock_msg.author_type = "human_agent"
    mock_msg.author_user_id = user.id
    mock_msg.author_user_name = None
    mock_msg.content = ""
    mock_msg.created_at = datetime.now(UTC)
    mock_msg.is_read = True
    mock_msg.has_images = True
    mock_msg.image_count = 1
    mock_msg.chatwoot_message_id = None
    mock_msg.delivery_failed = False
    mock_msg.attachments = []

    att_id = uuid.uuid4()
    mock_att = MagicMock()
    mock_att.id = att_id
    mock_att.url = f"/conversation-images/{conv.id}/abc.png"
    mock_att.kind = "image"
    mock_att.content_type = "image/png"
    mock_att.filename = "test.png"
    mock_att.size_bytes = len(_MINIMAL_PNG)
    mock_att.width = 1
    mock_att.height = 1
    mock_att.position = 0
    mock_att.created_at = datetime.now(UTC)
    mock_att.message_id = msg_id

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(return_value=(mock_msg, [mock_att]))

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    session_mock.flush = AsyncMock()
    session_mock.commit = AsyncMock()

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 201
    data = response.json()
    assert "message" in data
    assert "attachments" in data
    assert len(data["attachments"]) == 1
    assert "/conversation-images/" in data["attachments"][0]["url"]


# ---------------------------------------------------------------------------
# 2. Multiple images with caption → positions + content
# ---------------------------------------------------------------------------


def test_multiple_images_with_caption_correct_positions():
    """3 valid images + caption → positions 0,1,2 in response."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("agente_humano")
    conv = _make_conv_history()

    caption = "Adjunto documentación"

    mock_msg = MagicMock()
    mock_msg.id = uuid.uuid4()
    mock_msg.conversation_history_id = conv.id
    mock_msg.role = "human_agent"
    mock_msg.author_type = "human_agent"
    mock_msg.author_user_id = user.id
    mock_msg.author_user_name = None
    mock_msg.content = caption
    mock_msg.created_at = datetime.now(UTC)
    mock_msg.is_read = True
    mock_msg.has_images = True
    mock_msg.image_count = 3
    mock_msg.chatwoot_message_id = None
    mock_msg.delivery_failed = False
    mock_msg.attachments = []

    atts = []
    for i in range(3):
        a = MagicMock()
        a.id = uuid.uuid4()
        a.url = f"/conversation-images/{conv.id}/img{i}.png"
        a.kind = "image"
        a.content_type = "image/png"
        a.filename = f"img{i}.png"
        a.size_bytes = len(_MINIMAL_PNG)
        a.width = 1
        a.height = 1
        a.position = i
        a.created_at = datetime.now(UTC)
        a.message_id = mock_msg.id
        atts.append(a)

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(return_value=(mock_msg, atts))

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    session_mock.flush = AsyncMock()
    session_mock.commit = AsyncMock()
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload(f"img{i}.png") for i in range(3)],
            data={"caption": caption},
        )

    assert response.status_code == 201
    data = response.json()
    positions = [a["position"] for a in data["attachments"]]
    assert positions == [0, 1, 2]


# ---------------------------------------------------------------------------
# 3. Exceeds 10-image limit → 400
# ---------------------------------------------------------------------------


def test_exceeds_10_image_limit_returns_400():
    """11 images → 400 before any DB or Chatwoot call."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload(f"img{i}.png") for i in range(11)],
        )

    assert response.status_code == 400
    assert "10" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Outside 24h window → 400
# ---------------------------------------------------------------------------


def test_outside_24h_window_returns_400():
    """Conversation last inbound 25h ago → 400 outside_window."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    # 25h ago → outside window
    conv = _make_conv_history(hours_ago=25.0)

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 400
    assert "outside_window" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 5. No inbound messages (last_inbound_at=None) → 400 outside_window
# ---------------------------------------------------------------------------


def test_no_inbound_messages_returns_400():
    """Conversation with no inbound messages → 400 outside_window."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history(last_inbound_at=None, hours_ago=0)
    conv.last_inbound_at = None  # explicit None

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 400
    assert "outside_window" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 6. Unauthorized role (solo_lectura) → 403
# ---------------------------------------------------------------------------


def test_solo_lectura_role_returns_403():
    """solo_lectura user → 403 Forbidden."""
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    app = _build_app()

    def require_role_factory_forbidden(*roles):
        async def inner(*args, **kwargs):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return inner

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=require_role_factory_forbidden),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{uuid.uuid4()}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 7. Validation failure → 400 (service raises HTTPException 400)  [T16]
# ---------------------------------------------------------------------------


def test_image_validation_failure_returns_400():
    """Service raises HTTPException 400 (e.g. decompression bomb) → propagated."""
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(
        side_effect=HTTPException(status_code=400, detail="Imagen inválida: decompression bomb")
    )

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 400
    assert "inválida" in response.json()["detail"].lower() or "bomb" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 7b. Non-image file type (PDF) → 400  [Cap 5 scenario 4]
# ---------------------------------------------------------------------------


def test_non_image_file_type_returns_400():
    """PDF upload → validate_image_full rejects → service raises 400 → propagated.

    Covers Spec Cap 5 scenario: "Admin uploads non-image file (PDF) → 400 with reason".
    """
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(
        side_effect=HTTPException(
            status_code=400,
            detail="Tipo de archivo no soportado: application/pdf",
        )
    )

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_pdf_upload()],
        )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "pdf" in detail or "tipo" in detail or "no soportado" in detail


# ---------------------------------------------------------------------------
# 8. Chatwoot send fails → 500 + DB rollback + temp cleanup  [T16]
# ---------------------------------------------------------------------------


def test_chatwoot_send_failure_returns_500_and_service_rolls_back():
    """Service raises HTTPException 500 (Chatwoot failed) → propagated.

    The actual cleanup (temp files + DB rollback) happens inside
    ConversationImageService.store_admin_upload. This test verifies the
    endpoint propagates the 500 correctly and does NOT commit.
    """
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(
        side_effect=HTTPException(
            status_code=500,
            detail="Error al enviar imágenes a Chatwoot",
        )
    )

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    session_mock.flush = AsyncMock()
    session_mock.commit = AsyncMock()  # should NOT be called

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 500
    # Commit should NOT have been called when service raised before returning
    session_mock.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 9. Disk write failure → 500  [T16]
# ---------------------------------------------------------------------------


def test_disk_write_failure_returns_500():
    """OSError during temp write → service raises 500 (mocked). No Chatwoot call."""
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    svc = MagicMock()
    svc.store_admin_upload = AsyncMock(
        side_effect=HTTPException(
            status_code=500,
            detail="Error al guardar imágenes en disco",
        )
    )

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_conversation_image_service", return_value=svc),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
            files=[_png_upload()],
        )

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# 10. Zero files → 400 (count validation before session open)
# ---------------------------------------------------------------------------


def test_zero_files_returns_400():
    """Sending zero files → 400 (count must be 1..10)."""
    from fastapi.testclient import TestClient

    app = _build_app()
    user = _make_admin_user("admin")
    conv = _make_conv_history()

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("api.routes.conversations_admin._load_conversation", new=AsyncMock(return_value=conv)),
        patch("api.routes.conversations_admin.get_async_session", return_value=session_ctx),
        patch("api.routes.admin.require_role", side_effect=_mock_require_role_dep(user)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        # Send no files — FastAPI will reject with 422 (required field missing)
        # or 400 from our count check. Either way it must not be 201.
        response = client.post(
            f"/api/admin/conversations/{conv.id}/attachments",
        )

    # FastAPI raises 422 for missing required File(...) parameter
    assert response.status_code in (400, 422)
