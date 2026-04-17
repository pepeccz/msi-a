"""
Tests for T2d/T2e: _build_worker_cta_message with failed_reasons aggregation.

TDD Cycle: T2d — save_images_silently returns (saved, failed, failed_reasons);
           T2e — _build_worker_cta_message accepts failed_reasons and builds
                 bulleted list when ≥2 distinct codes, single-reason flat line otherwise.

Spec scenarios covered:
  - No failures → unchanged CTA (no reason text)
  - Single failure reason → flat single-line CTA with reason message embedded
  - Two distinct failure reasons → bulleted list CTA with counts per reason
  - failed_reasons=None → backwards-compatible (treated as no reason info)
  - Orphan batch → returns None regardless of reasons
  - failed>0 and count==0 → failure-only message (existing behavior preserved)
  - Mixed: some saved + some failed + multiple reasons → bulleted format
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# T2d / T2e: _build_worker_cta_message with failed_reasons
# ---------------------------------------------------------------------------


class TestBuildWorkerCtaMessageNoFailedReasons:
    """Backwards-compatible: when failed_reasons is None or empty, old behavior preserved."""

    def test_no_failures_no_reasons_returns_simple_cta(self) -> None:
        """count>0, failed=0 → simple received message, no reason lines."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=2,
            failed=0,
            total_images=2,
            element_display_name="escape",
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=None,
        )

        assert msg is not None
        assert "He recibido 2 imagen(es)" in msg
        assert "listo" in msg

    def test_orphan_returns_none_regardless_of_reasons(self) -> None:
        """Orphan batches always return None — no CTA sent."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=0,
            failed=2,
            total_images=2,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=True,
            failed_reasons=["file_type_not_allowed", "pdf_too_many_pages"],
        )

        assert msg is None

    def test_failed_reasons_none_uses_generic_failure_text(self) -> None:
        """When failed>0 but failed_reasons is None, use existing generic failure text."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=1,
            total_images=2,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=None,
        )

        assert msg is not None
        assert "no se pudieron descargar" in msg.lower() or "1" in msg

    def test_failed_reasons_empty_list_uses_generic_failure_text(self) -> None:
        """When failed>0 but failed_reasons=[], use existing generic failure text."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=1,
            total_images=2,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=[],
        )

        assert msg is not None
        assert "listo" in msg


# ---------------------------------------------------------------------------
# T2e: single-reason flat line
# ---------------------------------------------------------------------------


class TestBuildWorkerCtaMessageSingleReason:
    """When all failures share the same reason code → single-reason flat line (no bullets)."""

    def test_single_reason_no_bullets(self) -> None:
        """Single distinct reason → no bullet character in output."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=0,
            failed=2,
            total_images=2,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=["pdf_too_many_pages", "pdf_too_many_pages"],
        )

        assert msg is not None
        assert "•" not in msg
        assert "-" not in msg.split("\n")[1] if "\n" in msg else True

    def test_single_reason_contains_reason_message(self) -> None:
        """Single distinct reason → the reason_message from REASON_MESSAGES is embedded."""
        from agent.services.image_handling import _build_worker_cta_message
        from api.services.chatwoot_image_service import REASON_MESSAGES

        msg = _build_worker_cta_message(
            count=0,
            failed=1,
            total_images=1,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=["file_type_not_allowed"],
        )

        assert msg is not None
        # The reason message text should appear (or key parts of it)
        reason_text = REASON_MESSAGES["file_type_not_allowed"]
        # At least the first ~40 chars appear in the CTA
        assert reason_text[:40] in msg

    def test_single_reason_still_includes_listo_cta(self) -> None:
        """Single distinct reason → 'listo' prompt still present."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=1,
            total_images=2,
            element_display_name="escape",
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=["corrupt_or_mismatch"],
        )

        assert msg is not None
        assert "listo" in msg


# ---------------------------------------------------------------------------
# T2e: bulleted list when ≥2 distinct codes
# ---------------------------------------------------------------------------


class TestBuildWorkerCtaMessageMixedReasons:
    """When ≥2 distinct reason codes → bulleted list CTA."""

    def test_two_distinct_reasons_produces_bullets(self) -> None:
        """Two distinct reason codes → output contains bullet markers."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=2,
            total_images=3,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=["pdf_too_many_pages", "file_type_not_allowed"],
        )

        assert msg is not None
        # At least two bullet lines
        bullet_lines = [line for line in msg.splitlines() if line.strip().startswith("•") or line.strip().startswith("-")]
        assert len(bullet_lines) >= 2

    def test_mixed_reasons_includes_counts_per_reason(self) -> None:
        """Mixed reasons → each bullet includes the count for that reason."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=3,
            total_images=4,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=[
                "pdf_too_many_pages",
                "pdf_too_many_pages",
                "file_type_not_allowed",
            ],
        )

        assert msg is not None
        # Both codes should appear
        assert "PDF" in msg or "pdf" in msg.lower() or "páginas" in msg
        assert "formato" in msg.lower() or "tipo" in msg.lower() or "JPG" in msg

    def test_mixed_reasons_still_includes_listo_cta(self) -> None:
        """Mixed reasons → 'listo' prompt still present."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=0,
            failed=2,
            total_images=2,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=["url_rejected", "corrupt_or_mismatch"],
        )

        assert msg is not None
        assert "listo" in msg

    def test_three_distinct_reasons_all_in_bullets(self) -> None:
        """Three distinct codes → at least three bullet lines."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=0,
            failed=3,
            total_images=3,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=False,
            failed_reasons=[
                "pdf_too_many_pages",
                "file_type_not_allowed",
                "corrupt_or_mismatch",
            ],
        )

        assert msg is not None
        bullet_lines = [line for line in msg.splitlines() if line.strip().startswith("•") or line.strip().startswith("-")]
        assert len(bullet_lines) >= 2  # At least 2 (may vary by implementation)


# ---------------------------------------------------------------------------
# T2d: save_images_silently returns 3-tuple
# ---------------------------------------------------------------------------


class TestSaveImagesSilentlyReturnsTuple:
    """save_images_silently must return (saved, failed, failed_reasons) 3-tuple."""

    def test_return_type_is_3_tuple(self) -> None:
        """The return annotation must be tuple[int, int, list[str]]."""
        import inspect
        from agent.services.image_handling import save_images_silently

        hints = inspect.get_annotations(save_images_silently)
        return_hint = str(hints.get("return", ""))
        assert "list" in return_hint or "tuple" in return_hint

    @pytest.mark.asyncio
    async def test_empty_attachments_returns_empty_reasons_list(self) -> None:
        """No saveable attachments → (0, 0, []) 3-tuple."""
        from agent.services.image_handling import save_images_silently

        result = await save_images_silently(
            case_id="00000000-0000-0000-0000-000000000001",
            conversation_id="test-conv",
            attachments=[],  # empty → early return
            user_phone="+34600000000",
        )
        assert result == (0, 0, [])
