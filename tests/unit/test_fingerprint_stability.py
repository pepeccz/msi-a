"""Unit tests for _build_attachment_fingerprint stability.

Verifies that the fingerprint function produces:
- Identical hashes for the same image delivered via different signed URLs
- Different hashes for genuinely different attachments
- Graceful fallback when Chatwoot attachment ``id`` is missing
"""

from __future__ import annotations

import hashlib

import pytest

from agent.services.image_handling import _build_attachment_fingerprint


# ──────────────────────────────────────────────────────────────────
# Stability: same image, different data_url → same fingerprint
# ──────────────────────────────────────────────────────────────────


class TestFingerprintStability:
    """The root-cause scenario: Chatwoot Active Storage signed URLs change."""

    def test_same_attachment_different_data_url_produces_identical_fingerprint(self):
        """Core regression test: data_url changes must NOT affect fingerprint."""
        msg_id = 12345

        webhook_attachment = {
            "id": 9001,
            "file_type": "image",
            "data_url": "https://storage.chatwoot.com/rails/active_storage/blobs/redirect/eyJfcmFpb...SIGNED_A/photo.jpg",
            "file_size": 54321,
            "filename": "photo.jpg",
        }

        api_attachment = {
            "id": 9001,
            "file_type": "image",
            "data_url": "https://storage.chatwoot.com/rails/active_storage/blobs/redirect/eyJfcmFpb...SIGNED_B/photo.jpg",
            "file_size": 54321,
            "filename": "photo.jpg",
        }

        fp_webhook = _build_attachment_fingerprint(msg_id, webhook_attachment)
        fp_api = _build_attachment_fingerprint(msg_id, api_attachment)

        assert fp_webhook == fp_api, (
            "Fingerprints must be identical regardless of data_url; "
            "only stable fields (id, file_size, filename) matter"
        )

    def test_fingerprint_is_sha256_hex(self):
        """Fingerprint must be a 64-char lowercase hex SHA-256 digest."""
        attachment = {"id": 1, "file_size": 100, "filename": "test.jpg"}
        fp = _build_attachment_fingerprint(42, attachment)

        assert len(fp) == 64
        assert fp == fp.lower()
        # Verify it's valid hex
        int(fp, 16)

    def test_fingerprint_uses_stable_id_not_data_url(self):
        """Verify the computed hash matches the expected stable basis."""
        msg_id = 100
        attachment = {"id": 55, "file_size": 2048, "filename": "doc.png"}

        expected_basis = "|".join(["100", "55", "2048", "doc.png"])
        expected_fp = hashlib.sha256(expected_basis.encode("utf-8")).hexdigest()

        actual_fp = _build_attachment_fingerprint(msg_id, attachment)
        assert actual_fp == expected_fp


# ──────────────────────────────────────────────────────────────────
# Uniqueness: different attachments → different fingerprints
# ──────────────────────────────────────────────────────────────────


class TestFingerprintUniqueness:
    """Genuinely different images must produce different fingerprints."""

    def test_different_attachment_ids_produce_different_fingerprints(self):
        att_a = {"id": 1, "file_size": 1000, "filename": "a.jpg"}
        att_b = {"id": 2, "file_size": 1000, "filename": "a.jpg"}

        fp_a = _build_attachment_fingerprint(42, att_a)
        fp_b = _build_attachment_fingerprint(42, att_b)

        assert fp_a != fp_b

    def test_different_message_ids_produce_different_fingerprints(self):
        att = {"id": 1, "file_size": 1000, "filename": "a.jpg"}

        fp_a = _build_attachment_fingerprint(100, att)
        fp_b = _build_attachment_fingerprint(200, att)

        assert fp_a != fp_b

    def test_different_file_sizes_produce_different_fingerprints(self):
        att_a = {"id": 1, "file_size": 1000, "filename": "a.jpg"}
        att_b = {"id": 1, "file_size": 2000, "filename": "a.jpg"}

        fp_a = _build_attachment_fingerprint(42, att_a)
        fp_b = _build_attachment_fingerprint(42, att_b)

        assert fp_a != fp_b

    def test_different_filenames_produce_different_fingerprints(self):
        att_a = {"id": 1, "file_size": 1000, "filename": "a.jpg"}
        att_b = {"id": 1, "file_size": 1000, "filename": "b.jpg"}

        fp_a = _build_attachment_fingerprint(42, att_a)
        fp_b = _build_attachment_fingerprint(42, att_b)

        assert fp_a != fp_b


# ──────────────────────────────────────────────────────────────────
# Fallback: missing or None fields
# ──────────────────────────────────────────────────────────────────


class TestFingerprintFallback:
    """The function must not crash when fields are absent or None."""

    def test_missing_id_produces_fingerprint(self):
        """When attachment has no 'id' key, fingerprint still computes."""
        att = {"file_size": 1000, "filename": "a.jpg"}
        fp = _build_attachment_fingerprint(42, att)

        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_none_id_produces_fingerprint(self):
        """When attachment id is explicitly None."""
        att = {"id": None, "file_size": 1000, "filename": "a.jpg"}
        fp = _build_attachment_fingerprint(42, att)

        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_missing_id_and_none_id_produce_same_fingerprint(self):
        """Missing and None id should both resolve to empty string."""
        att_missing = {"file_size": 1000, "filename": "a.jpg"}
        att_none = {"id": None, "file_size": 1000, "filename": "a.jpg"}

        fp_missing = _build_attachment_fingerprint(42, att_missing)
        fp_none = _build_attachment_fingerprint(42, att_none)

        assert fp_missing == fp_none

    def test_none_message_id_produces_fingerprint(self):
        """When chatwoot_message_id is None (e.g. manual upload)."""
        att = {"id": 1, "file_size": 1000, "filename": "a.jpg"}
        fp = _build_attachment_fingerprint(None, att)

        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_empty_attachment_produces_fingerprint(self):
        """Completely empty attachment dict must not crash."""
        fp = _build_attachment_fingerprint(None, {})

        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_file_name_fallback(self):
        """Attachment with 'file_name' instead of 'filename' must work."""
        att_fn = {"id": 1, "file_size": 1000, "filename": "a.jpg"}
        att_file_name = {"id": 1, "file_size": 1000, "file_name": "a.jpg"}

        fp_fn = _build_attachment_fingerprint(42, att_fn)
        fp_file_name = _build_attachment_fingerprint(42, att_file_name)

        assert fp_fn == fp_file_name

    def test_missing_id_still_differentiates_by_other_fields(self):
        """Even without id, file_size + filename provide some uniqueness."""
        att_a = {"file_size": 1000, "filename": "a.jpg"}
        att_b = {"file_size": 2000, "filename": "b.jpg"}

        fp_a = _build_attachment_fingerprint(42, att_a)
        fp_b = _build_attachment_fingerprint(42, att_b)

        assert fp_a != fp_b
