"""Unit tests for PDF reconciliation fix in image_handling.py.

Root cause: reconcile_missing_images() used `file_type != "image"` as a skip guard,
which excluded PDFs (file_type == "file"). The fix replaces the guard with
`is_saveable_attachment()`, which accepts both images AND PDFs.

Regression scenario from 2026-04-15 live test:
  - User sent PDF (ficha técnica) via WhatsApp
  - Chatwoot stored it as file_type="file", content_type="application/pdf"
  - Reconciliation skipped it → base_docs image_count=0 → escalation triggered
"""

from __future__ import annotations

import pytest

from agent.services.image_handling import (
    is_saveable_attachment,
    is_image_attachment,
    is_document_attachment,
)


# ──────────────────────────────────────────────────────────────────
# is_saveable_attachment — unit tests
# ──────────────────────────────────────────────────────────────────


class TestIsSaveableAttachment:
    """Verify that is_saveable_attachment accepts images AND PDFs."""

    def test_image_attachment_is_saveable(self):
        """Standard image attachment must pass the guard."""
        attachment = {"file_type": "image", "data_url": "https://example.com/photo.jpg"}
        assert is_saveable_attachment(attachment) is True

    def test_pdf_attachment_is_saveable(self):
        """PDF attachment (file_type='file') must pass the guard — this is the regression case."""
        attachment = {
            "file_type": "file",
            "content_type": "application/pdf",
            "data_url": "https://example.com/ficha_tecnica.pdf",
        }
        assert is_saveable_attachment(attachment) is True

    def test_audio_attachment_is_not_saveable(self):
        """Audio attachments must be rejected."""
        attachment = {"file_type": "audio", "data_url": "https://example.com/voice.ogg"}
        assert is_saveable_attachment(attachment) is False

    def test_video_attachment_is_not_saveable(self):
        """Video attachments must be rejected."""
        attachment = {"file_type": "video", "data_url": "https://example.com/video.mp4"}
        assert is_saveable_attachment(attachment) is False

    def test_unknown_file_type_is_not_saveable(self):
        """Unknown file types must not be treated as saveable."""
        attachment = {"file_type": "sticker", "data_url": "https://example.com/sticker.webp"}
        assert is_saveable_attachment(attachment) is False

    def test_missing_file_type_is_not_saveable(self):
        """Attachment with no file_type must not be treated as saveable."""
        attachment = {"data_url": "https://example.com/unknown"}
        assert is_saveable_attachment(attachment) is False


# ──────────────────────────────────────────────────────────────────
# Reconciliation loop guard — behavioural regression test
# ──────────────────────────────────────────────────────────────────


class TestReconciliationPdfGuard:
    """Verify that the reconciliation skip-guard does NOT exclude PDFs.

    This test simulates the exact attachment list that triggered the bug:
    a message with a PDF attachment (file_type='file') that was incorrectly
    skipped before the fix.
    """

    def test_pdf_attachment_is_not_skipped_by_reconciliation_guard(self):
        """PDF attachment must NOT be filtered out by the reconciliation guard.

        Before the fix: `attachment.get('file_type') != 'image'` → True for PDFs → skipped.
        After the fix: `not is_saveable_attachment(attachment)` → False for PDFs → processed.
        """
        attachments = [
            {
                "id": 8001,
                "file_type": "file",
                "content_type": "application/pdf",
                "data_url": "https://chatwoot.example.com/file.pdf",
                "filename": "ficha_tecnica.pdf",
                "file_size": 512000,
            },
        ]

        # Simulate the reconciliation guard with the OLD (broken) logic
        old_guard_skipped = [
            att for att in attachments
            if att.get("file_type") != "image"  # old guard — WRONG
        ]

        # Simulate the reconciliation guard with the NEW (fixed) logic
        new_guard_skipped = [
            att for att in attachments
            if not is_saveable_attachment(att)  # new guard — CORRECT
        ]

        # Old logic would skip the PDF
        assert len(old_guard_skipped) == 1, "Old guard incorrectly skips PDF"

        # New logic must NOT skip the PDF
        assert len(new_guard_skipped) == 0, (
            "New guard must not skip a PDF attachment — it should be processed"
        )

    def test_image_attachment_still_processed_after_fix(self):
        """Image attachments must still pass through the fixed guard."""
        attachments = [
            {
                "id": 7001,
                "file_type": "image",
                "data_url": "https://chatwoot.example.com/photo.jpg",
                "filename": "foto.jpg",
                "file_size": 204800,
            },
        ]

        skipped = [
            att for att in attachments
            if not is_saveable_attachment(att)
        ]

        assert len(skipped) == 0, "Image attachment must not be skipped by fixed guard"

    def test_audio_still_skipped_after_fix(self):
        """Audio attachments must still be skipped by the fixed guard."""
        attachments = [
            {
                "id": 6001,
                "file_type": "audio",
                "data_url": "https://chatwoot.example.com/audio.ogg",
            },
        ]

        skipped = [
            att for att in attachments
            if not is_saveable_attachment(att)
        ]

        assert len(skipped) == 1, "Audio attachment must still be skipped by fixed guard"

    def test_mixed_attachments_only_audio_skipped(self):
        """Mixed message: image + PDF both processed; audio skipped."""
        attachments = [
            {"file_type": "image", "data_url": "https://example.com/photo.jpg"},
            {"file_type": "file", "content_type": "application/pdf", "data_url": "https://example.com/doc.pdf"},
            {"file_type": "audio", "data_url": "https://example.com/audio.ogg"},
        ]

        to_process = [att for att in attachments if is_saveable_attachment(att)]
        skipped = [att for att in attachments if not is_saveable_attachment(att)]

        assert len(to_process) == 2
        assert len(skipped) == 1
        assert skipped[0]["file_type"] == "audio"
