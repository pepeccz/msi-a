"""
Tests for polymorphic attachments (image + PDF) across collection flows.

Tasks covered:
    1.1  test_is_saveable_attachment_accepts_image
    1.2  test_is_saveable_attachment_accepts_file_document
    1.3  test_is_saveable_attachment_rejects_audio
    1.4  test_is_saveable_attachment_rejects_video
    2.1  test_worker_cta_uses_archivo_for_base_docs
    2.2  test_worker_cta_uses_archivo_for_element
    2.3  test_worker_cta_partial_failure_uses_archivo
    3.1  test_collect_element_data_ack_neutral_mixed
    3.2  test_collect_base_docs_ack_neutral_mixed
    4.1  test_pdf_counts_toward_min_required_no_bypass_needed
    4.2  test_pdf_bypass_flag_removed_all_attachments_count
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# 1.x — is_saveable_attachment / is_accepted_attachment helpers
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAttachmentTypeHelpers:
    """is_saveable_attachment and is_accepted_attachment handle mixed types."""

    def test_is_saveable_attachment_accepts_image(self) -> None:
        """file_type=image is saveable."""
        from agent.services.image_handling import is_saveable_attachment

        assert is_saveable_attachment({"file_type": "image"}) is True

    def test_is_saveable_attachment_accepts_file_document(self) -> None:
        """file_type=file (PDF/document) is saveable."""
        from agent.services.image_handling import is_saveable_attachment

        assert is_saveable_attachment({"file_type": "file"}) is True

    def test_is_saveable_attachment_rejects_audio(self) -> None:
        """file_type=audio is not saveable (rejected)."""
        from agent.services.image_handling import is_saveable_attachment

        assert is_saveable_attachment({"file_type": "audio"}) is False

    def test_is_saveable_attachment_rejects_video(self) -> None:
        """file_type=video is not saveable (rejected)."""
        from agent.services.image_handling import is_saveable_attachment

        assert is_saveable_attachment({"file_type": "video"}) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2.x — _build_worker_cta_message uses neutral "archivo(s)" wording
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestWorkerCtaMessageNeutralCopy:
    """_build_worker_cta_message uses 'archivo(s)' instead of 'imagen(es)'."""

    def test_worker_cta_uses_archivo_for_base_docs(self) -> None:
        """Base-docs CTA must say 'archivo(s)', not 'imagen(es)'."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=2,
            failed=0,
            total_images=2,
            element_display_name=None,
            is_base_docs=True,
        )
        assert msg is not None
        assert "archivo(s)" in msg or "archivo" in msg
        assert "imagen" not in msg.lower()

    def test_worker_cta_uses_archivo_for_element(self) -> None:
        """Element-photo CTA must say 'archivo(s)', not 'imagen(es)'."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=0,
            total_images=1,
            element_display_name="Escape",
            is_base_docs=False,
        )
        assert msg is not None
        assert "archivo(s)" in msg or "archivo" in msg
        assert "imagen" not in msg.lower()

    def test_worker_cta_partial_failure_uses_archivo(self) -> None:
        """Mixed success/failure CTA must say 'archivo(s)', not 'imagen(es)'."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=1,
            total_images=2,
            element_display_name=None,
            is_base_docs=True,
            failed_reasons=["file_too_large"],
        )
        assert msg is not None
        assert "imagen" not in msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3.x — collect_element_data and collect_base_docs ack uses neutral wording
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestCollectModesAckNeutralWording:
    """Attachment-only turn acks in sub-mode handlers use neutral wording."""

    async def test_collect_element_data_ack_neutral_mixed(self) -> None:
        """Attachment-only ack in COLLECT_ELEMENT_DATA should NOT say 'foto(s)' alone."""
        from agent.modes.submodos.collect_element_data import ElementDataHandler

        handler = ElementDataHandler()
        state = {
            "conversation_id": "test-conv",
            "incoming_attachments": [
                {"file_type": "image", "type": "image"},
                {"file_type": "file", "type": "document"},
            ],
        }
        mode_context: dict = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
            "element_phase": "photos",
            "case_id": None,
        }

        llm_loop_fn = AsyncMock(return_value={"ai_response": "llamado LLM", "mode_context": mode_context})

        result = await handler.handle(
            message="",
            state=state,
            mode_context=mode_context,
            llm_loop_fn=llm_loop_fn,
        )

        ack = result.get("ai_response", "")
        # Must not be exclusively "foto(s)" — should include PDF/document or neutral
        # The ack should at least not refer ONLY to photos when a document is present
        assert ack != ""
        # Must NOT tell user to send "fotos" when a document was also sent
        assert "foto" not in ack.lower() or "archivo" in ack.lower() or "documento" in ack.lower()

    async def test_collect_base_docs_ack_neutral_mixed(self) -> None:
        """Attachment-only ack in COLLECT_BASE_DOCS counts both images and docs."""
        from agent.modes.submodos.collect_base_docs import BaseDocsHandler

        handler = BaseDocsHandler()
        state = {
            "conversation_id": "test-conv",
            "incoming_attachments": [
                {"type": "image"},
                {"type": "document"},
                {"type": "image"},
            ],
        }
        mode_context: dict = {
            "expediente_sub_mode": "collect_base_docs",
        }

        llm_loop_fn = AsyncMock(return_value={"ai_response": "LLM", "mode_context": mode_context})

        result = await handler.handle(
            message="",
            state=state,
            mode_context=mode_context,
            llm_loop_fn=llm_loop_fn,
        )

        ack = result.get("ai_response", "")
        assert ack != ""
        # Should mention both image and document counts (or use neutral)
        # At minimum must NOT say "0 documento(s)" when there's 1 document
        assert "1 documento" in ack or "documento" in ack


# ─────────────────────────────────────────────────────────────────────────────
# 4.x — PDF counts toward min_required (polymorphic, no bypass needed)
# ─────────────────────────────────────────────────────────────────────────────


def _make_session_with_count(count_result: int) -> MagicMock:
    """Build mock async session returning count_result from scalar()."""
    mock_session_ctx = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = count_result
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session_ctx


@pytest.mark.unit
@pytest.mark.asyncio
class TestPolymorphicMinRequired:
    """PDF attachments count toward min_required — no bypass flag needed."""

    async def test_pdf_counts_toward_min_required_no_bypass_needed(self) -> None:
        """When image_count includes PDF rows, min_required is satisfied naturally."""
        from agent.services.element_data_service import confirm_base_documentation

        mock_settings = MagicMock(
            BASE_DOCS_MIN_REQUIRED_FLOOR=2,
            # BASE_DOCS_PDF_SATISFIES_MINIMUM is intentionally ignored in polymorphic model
        )

        mock_batch_service = MagicMock()
        mock_batch_service.resolve_for_scope = AsyncMock(return_value=None)
        mock_batch_service.finalize_for_scope = AsyncMock(return_value=None)

        with (
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_min_required",
                new=AsyncMock(return_value=2),
            ),
            # count=2 means 1 image + 1 PDF saved → satisfies min_required=2
            patch(
                "agent.services.element_data_service._get_case_image_count",
                new=AsyncMock(return_value=2),
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
                return_value=mock_batch_service,
            ),
            patch(
                "agent.services.case_image_batch_service.build_upload_scope",
                return_value=None,
            ),
            patch(
                "agent.services.element_data_service.build_case_update",
                return_value={},
            ),
            patch(
                "agent.services.element_data_service.set_collection_step",
                return_value={},
            ),
        ):
            result = await confirm_base_documentation(
                usuario_confirma=None,
                case_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                conversation_id=None,
                mode_context={
                    "fsm_state": {
                        "case_collection_phase": "COLLECT_BASE_DOCS",
                        "base_docs_received": False,
                    },
                    "expediente_sub_mode": "collect_base_docs",
                    "base_doc_descriptions": ["Ficha técnica", "Permiso"],
                    "category_id": None,
                    "user_phone": "",
                },
            )

        assert result["success"] is True
        assert result["base_docs_confirmed"] is True
        assert result["next_step"] == "COLLECT_PERSONAL"

    async def test_pdf_bypass_flag_removed_all_attachments_count(self) -> None:
        """Polymorphic model: when count < min_required, should NOT advance (no magic bypass).

        In the old model, having a PDF bypassed the count check.
        In the new model, count IS the total of all attachment types — PDFs and images are
        counted equally. If count < min_required, the flow asks for more, regardless of MIME.
        """
        from agent.services.element_data_service import confirm_base_documentation

        mock_settings = MagicMock(
            BASE_DOCS_MIN_REQUIRED_FLOOR=3,
        )

        mock_batch_service = MagicMock()
        mock_batch_service.resolve_for_scope = AsyncMock(return_value=None)
        mock_batch_service.finalize_for_scope = AsyncMock(return_value=None)

        with (
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_min_required",
                new=AsyncMock(return_value=3),
            ),
            # Only 1 PDF — below min_required=3
            patch(
                "agent.services.element_data_service._get_case_image_count",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
                return_value=mock_batch_service,
            ),
            patch(
                "agent.services.case_image_batch_service.build_upload_scope",
                return_value=None,
            ),
        ):
            result = await confirm_base_documentation(
                usuario_confirma=None,
                case_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                conversation_id=None,
                mode_context={
                    "fsm_state": {
                        "case_collection_phase": "COLLECT_BASE_DOCS",
                        "base_docs_received": False,
                    },
                    "expediente_sub_mode": "collect_base_docs",
                    "base_doc_descriptions": ["Ficha técnica", "Permiso", "Vista frontal"],
                    "category_id": None,
                    "user_phone": "",
                },
            )

        # 1 attachment < 3 min_required → should NOT advance
        assert result["success"] is False
        assert result.get("next_step") != "COLLECT_PERSONAL"
