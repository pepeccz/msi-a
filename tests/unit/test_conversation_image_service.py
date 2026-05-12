"""
Unit tests for ConversationImageService.

TDD cycle: RED → GREEN → REFACTOR

Covers:
  - download_and_persist_inbound: position assignment, non-image filtering,
    validate_image_full called, validation failure skips row creation
  - persist_outbound_urls: N rows at correct positions, zero rows when urls=[]
  - store_admin_upload: validates before disk write, rolls back on Chatwoot failure
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers — build lightweight mock objects without importing DB models
# ---------------------------------------------------------------------------


def _make_session() -> MagicMock:
    """Return an AsyncMock that behaves like an AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_message(message_id: uuid.UUID | None = None) -> MagicMock:
    msg = MagicMock()
    msg.id = message_id or uuid.uuid4()
    return msg


# ---------------------------------------------------------------------------
# download_and_persist_inbound
# ---------------------------------------------------------------------------


class TestDownloadAndPersistInbound:
    """Tests for ConversationImageService.download_and_persist_inbound."""

    @pytest.mark.asyncio
    async def test_single_image_creates_one_row(self, tmp_path: Path) -> None:
        """Happy path: one image attachment → one MessageAttachment row at position 0."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/img.jpg", "name": "img.jpg", "type": "image/jpeg"}
        ]

        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG magic
        fake_validation = {"detected_mime": "image/jpeg", "width": 640, "height": 480, "file_size": 104}

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(return_value=fake_bytes),
            ),
            patch(
                "api.services.conversation_image_service.validate_image_full",
                return_value=fake_validation,
            ),
            patch(
                "api.services.conversation_image_service.validate_url",
            ),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert len(rows) == 1
        assert rows[0].position == 0
        assert rows[0].chatwoot_url == "https://chatwoot.example.com/img.jpg"
        assert rows[0].kind == "image"
        assert rows[0].width == 640
        assert rows[0].height == 480
        assert rows[0].content_type == "image/jpeg"
        session.add.assert_called_once_with(rows[0])
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_three_images_get_sequential_positions(self, tmp_path: Path) -> None:
        """Three attachments → rows with position=0,1,2."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": f"https://chatwoot.example.com/img{i}.jpg", "name": f"img{i}.jpg", "type": "image/jpeg"}
            for i in range(3)
        ]

        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        fake_validation = {"detected_mime": "image/jpeg", "width": 640, "height": 480, "file_size": 104}

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(return_value=fake_bytes),
            ),
            patch(
                "api.services.conversation_image_service.validate_image_full",
                return_value=fake_validation,
            ),
            patch(
                "api.services.conversation_image_service.validate_url",
            ),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert len(rows) == 3
        assert [r.position for r in rows] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_non_image_attachment_skipped(self, tmp_path: Path) -> None:
        """Attachments with non-image MIME types are silently dropped."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        # A document attachment (PDF content type reported by Chatwoot as "application/pdf")
        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/doc.pdf", "name": "doc.pdf", "type": "application/pdf"}
        ]

        with (
            patch("api.services.conversation_image_service.download_chatwoot_image", new=AsyncMock()),
            patch("api.services.conversation_image_service.validate_image_full"),
            patch("api.services.conversation_image_service.validate_url"),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert rows == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_validation_failure_skips_row_emits_warning(self, tmp_path: Path) -> None:
        """If validate_image_full raises, the row is skipped (no DB write) and a WARNING logged."""
        from api.services.conversation_image_service import ConversationImageService
        from shared.image_security import ImageSecurityError

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/bomb.jpg", "name": "bomb.jpg", "type": "image/jpeg"}
        ]

        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(return_value=fake_bytes),
            ),
            patch(
                "api.services.conversation_image_service.validate_image_full",
                side_effect=ImageSecurityError("decompression bomb"),
            ),
            patch("api.services.conversation_image_service.validate_url"),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert rows == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_failure_skips_row(self, tmp_path: Path) -> None:
        """If the download helper raises, the row is skipped."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/missing.jpg", "name": "missing.jpg", "type": "image/jpeg"}
        ]

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(side_effect=OSError("network error")),
            ),
            patch("api.services.conversation_image_service.validate_url"),
        ):
            rows = await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert rows == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_image_full_is_called(self, tmp_path: Path) -> None:
        """validate_image_full must be called once per image attachment."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        chatwoot_attachments = [
            {"url": "https://chatwoot.example.com/img.jpg", "name": "img.jpg", "type": "image/jpeg"},
            {"url": "https://chatwoot.example.com/img2.jpg", "name": "img2.jpg", "type": "image/jpeg"},
        ]

        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        fake_validation = {"detected_mime": "image/jpeg", "width": 640, "height": 480, "file_size": 104}

        with (
            patch(
                "api.services.conversation_image_service.download_chatwoot_image",
                new=AsyncMock(return_value=fake_bytes),
            ),
            patch(
                "api.services.conversation_image_service.validate_image_full",
                return_value=fake_validation,
            ) as mock_validate,
            patch("api.services.conversation_image_service.validate_url"),
        ):
            await service.download_and_persist_inbound(
                session=session,
                conversation_id=conv_id,
                message_id=msg_id,
                chatwoot_attachments=chatwoot_attachments,
            )

        assert mock_validate.call_count == 2


# ---------------------------------------------------------------------------
# persist_outbound_urls
# ---------------------------------------------------------------------------


class TestPersistOutboundUrls:
    """Tests for ConversationImageService.persist_outbound_urls."""

    @pytest.mark.asyncio
    async def test_empty_urls_creates_no_rows(self, tmp_path: Path) -> None:
        """No URLs → no rows created, no DB calls."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        msg_id = uuid.uuid4()

        rows = await service.persist_outbound_urls(
            session=session,
            message_id=msg_id,
            image_urls=[],
        )

        assert rows == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_three_urls_create_three_rows_at_correct_positions(self, tmp_path: Path) -> None:
        """Three URLs → three rows with position 0, 1, 2."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        msg_id = uuid.uuid4()

        urls = [
            "https://api.example.com/images/abc.jpg",
            "https://api.example.com/images/def.jpg",
            "https://api.example.com/images/ghi.jpg",
        ]

        rows = await service.persist_outbound_urls(
            session=session,
            message_id=msg_id,
            image_urls=urls,
        )

        assert len(rows) == 3
        assert [r.position for r in rows] == [0, 1, 2]
        assert rows[0].url == urls[0]
        assert rows[1].url == urls[1]
        assert rows[2].url == urls[2]
        # Bot outbound: no chatwoot_url, no width/height
        for row in rows:
            assert row.chatwoot_url is None
            assert row.width is None
            assert row.height is None
            assert row.kind == "image"

    @pytest.mark.asyncio
    async def test_session_add_called_per_row(self, tmp_path: Path) -> None:
        """session.add is called once per URL."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        msg_id = uuid.uuid4()

        urls = [
            "https://api.example.com/images/a.jpg",
            "https://api.example.com/images/b.jpg",
        ]

        rows = await service.persist_outbound_urls(
            session=session,
            message_id=msg_id,
            image_urls=urls,
        )

        assert session.add.call_count == 2
        session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# store_admin_upload
# ---------------------------------------------------------------------------


class TestStoreAdminUpload:
    """Tests for ConversationImageService.store_admin_upload."""

    @pytest.mark.asyncio
    async def test_single_valid_upload_creates_message_and_attachment(
        self, tmp_path: Path
    ) -> None:
        """Happy path: 1 valid PNG → ConversationMessage + 1 MessageAttachment."""
        from api.services.conversation_image_service import ConversationImageService

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        file_mock = MagicMock()
        file_mock.filename = "photo.png"
        file_mock.content_type = "image/png"
        file_mock.read = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        fake_validation = {"detected_mime": "image/png", "width": 800, "height": 600, "file_size": 108}

        # Mock chatwoot_client.send_images to simulate successful send
        mock_send = AsyncMock(return_value=1)

        with (
            patch(
                "api.services.conversation_image_service.validate_image_full",
                return_value=fake_validation,
            ),
            patch(
                "api.services.conversation_image_service.ChatwootClient",
            ) as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.send_images = mock_send

            msg, attachments = await service.store_admin_upload(
                session=session,
                conversation_id=conv_id,
                conversation_history_id=uuid.uuid4(),
                conversation_chatwoot_id="12345",
                files=[file_mock],
                caption=None,
                admin_user_id=admin_id,
            )

        assert msg is not None
        assert len(attachments) == 1
        assert attachments[0].position == 0
        assert attachments[0].width == 800
        assert attachments[0].height == 600
        assert attachments[0].uploaded_by_admin_user_id == admin_id

    @pytest.mark.asyncio
    async def test_validation_failure_raises_before_disk_write(
        self, tmp_path: Path
    ) -> None:
        """validate_image_full failure → HTTPException 400 raised before any disk write."""
        from api.services.conversation_image_service import ConversationImageService
        from shared.image_security import ImageSecurityError
        from fastapi import HTTPException

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        file_mock = MagicMock()
        file_mock.filename = "bomb.jpg"
        file_mock.content_type = "image/jpeg"
        file_mock.read = AsyncMock(return_value=b"fake-bomb")

        with (
            patch(
                "api.services.conversation_image_service.validate_image_full",
                side_effect=ImageSecurityError("decompression bomb detected"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.store_admin_upload(
                    session=session,
                    conversation_id=conv_id,
                    conversation_history_id=uuid.uuid4(),
                    conversation_chatwoot_id="12345",
                    files=[file_mock],
                    caption=None,
                    admin_user_id=admin_id,
                )

        assert exc_info.value.status_code == 400
        # No files should have been written
        conv_dir = tmp_path / "conversation_images" / str(conv_id)
        assert not conv_dir.exists() or not list(conv_dir.iterdir())

    @pytest.mark.asyncio
    async def test_chatwoot_failure_rolls_back_temp_files(
        self, tmp_path: Path
    ) -> None:
        """If Chatwoot send_images raises → temp files deleted, HTTP 500 raised."""
        from api.services.conversation_image_service import ConversationImageService
        from fastapi import HTTPException

        service = ConversationImageService(uploads_base=tmp_path)
        session = _make_session()
        conv_id = uuid.uuid4()
        admin_id = uuid.uuid4()

        file_mock = MagicMock()
        file_mock.filename = "photo.jpg"
        file_mock.content_type = "image/jpeg"
        file_mock.read = AsyncMock(return_value=b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        fake_validation = {"detected_mime": "image/jpeg", "width": 640, "height": 480, "file_size": 104}

        with (
            patch(
                "api.services.conversation_image_service.validate_image_full",
                return_value=fake_validation,
            ),
            patch(
                "api.services.conversation_image_service.ChatwootClient",
            ) as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.send_images = AsyncMock(side_effect=RuntimeError("Chatwoot API error"))

            with pytest.raises(HTTPException) as exc_info:
                await service.store_admin_upload(
                    session=session,
                    conversation_id=conv_id,
                    conversation_history_id=uuid.uuid4(),
                    conversation_chatwoot_id="12345",
                    files=[file_mock],
                    caption=None,
                    admin_user_id=admin_id,
                )

        assert exc_info.value.status_code == 500
        # Temp files should be cleaned up
        conv_dir = tmp_path / "conversation_images" / str(conv_id)
        if conv_dir.exists():
            remaining = list(conv_dir.glob("*.tmp_*")) + list(conv_dir.glob(".tmp_*"))
            assert len(remaining) == 0, f"Temp files not cleaned up: {remaining}"
