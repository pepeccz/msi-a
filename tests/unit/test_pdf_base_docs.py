"""
Tests for PDF base docs short-circuit feature.

Tasks covered:
    2.1  test_setting_default_true
    2.2  test_setting_env_override_false
    2.3  test_has_pdf_in_base_docs_returns_true
    2.4  test_has_pdf_in_base_docs_no_pdf
    2.5  test_has_pdf_in_base_docs_db_error
    2.6  test_confirm_base_docs_pdf_bypasses_count
    2.7  test_confirm_base_docs_flag_off_falls_through
    2.8  test_confirm_base_docs_zero_images_no_bypass
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# 2.1 / 2.2 — Setting: BASE_DOCS_PDF_SATISFIES_MINIMUM
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestBaseDOcsPdfSatisfiesMinimumSetting:
    """Setting exists in shared/config.py with correct default and env override."""

    def test_setting_default_true(self) -> None:
        """Default value must be True (bool)."""
        from shared.config import get_settings

        settings = get_settings()
        assert settings.BASE_DOCS_PDF_SATISFIES_MINIMUM is True

    def test_setting_env_override_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting can be overridden to False via env var."""
        import shared.config as _cfg_mod

        monkeypatch.setenv("BASE_DOCS_PDF_SATISFIES_MINIMUM", "false")
        fresh_settings = _cfg_mod.Settings()
        assert fresh_settings.BASE_DOCS_PDF_SATISFIES_MINIMUM is False


# ─────────────────────────────────────────────────────────────────────────────
# 2.3 / 2.4 / 2.5 — _has_pdf_in_base_docs() helper
# ─────────────────────────────────────────────────────────────────────────────


def _make_session_with_exists(exists_result: bool) -> MagicMock:
    """Build a mock async session that returns *exists_result* from scalar()."""
    mock_session_ctx = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = exists_result
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session_ctx


def _make_failing_session() -> MagicMock:
    """Build a mock async session context manager that raises on enter."""
    mock_session_ctx = MagicMock()
    mock_session_ctx.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("DB down")
    )
    mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session_ctx


@pytest.mark.unit
@pytest.mark.asyncio
class TestHasPdfInBaseDocs:
    """Unit tests for _has_pdf_in_base_docs() helper."""

    async def test_has_pdf_in_base_docs_returns_true(self) -> None:
        """Returns True when a PDF CaseImage with element_code=None exists."""
        from agent.services.element_data_service import _has_pdf_in_base_docs

        mock_session_ctx = _make_session_with_exists(True)

        with patch(
            "agent.services.element_data_service.get_async_session",
            mock_session_ctx,
        ):
            result = await _has_pdf_in_base_docs(
                case_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                upload_batch_id=None,
            )

        assert result is True

    async def test_has_pdf_in_base_docs_no_pdf(self) -> None:
        """Returns False when no PDF rows exist (only image/* rows)."""
        from agent.services.element_data_service import _has_pdf_in_base_docs

        mock_session_ctx = _make_session_with_exists(False)

        with patch(
            "agent.services.element_data_service.get_async_session",
            mock_session_ctx,
        ):
            result = await _has_pdf_in_base_docs(
                case_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                upload_batch_id=None,
            )

        assert result is False

    async def test_has_pdf_in_base_docs_db_error(self) -> None:
        """Returns False (fail-closed) without raising when DB raises an exception."""
        from agent.services.element_data_service import _has_pdf_in_base_docs

        mock_session_ctx = _make_failing_session()

        with patch(
            "agent.services.element_data_service.get_async_session",
            mock_session_ctx,
        ):
            # Must not raise
            result = await _has_pdf_in_base_docs(
                case_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                upload_batch_id=None,
            )

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 2.6 / 2.7 / 2.8 — confirm_base_documentation() PDF bypass integration
# ─────────────────────────────────────────────────────────────────────────────


def _base_mode_context() -> dict:
    """Minimal mode_context for confirm_base_documentation tests."""
    return {
        "fsm_state": {
            "case_collection_phase": "COLLECT_BASE_DOCS",
            "base_docs_received": False,
        },
        "expediente_sub_mode": "collect_base_docs",
        "base_doc_descriptions": ["Ficha técnica", "Permiso de circulación"],
        "category_id": None,
        "user_phone": "",
    }


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfirmBaseDocsPdfBypass:
    """
    Integration tests for confirm_base_documentation() PDF bypass logic.

    These tests mock the lower-level helpers to isolate the bypass branch.
    """

    async def test_confirm_base_docs_pdf_bypasses_count(self) -> None:
        """PDF present + image_count < min_required + flag ON → advance to COLLECT_PERSONAL."""
        from agent.services.element_data_service import confirm_base_documentation

        # Settings with flag ON
        mock_settings = MagicMock(
            BASE_DOCS_MIN_REQUIRED_FLOOR=4,
            BASE_DOCS_PDF_SATISFIES_MINIMUM=True,
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
                new=AsyncMock(return_value=4),
            ),
            patch(
                "agent.services.element_data_service._get_case_image_count",
                new=AsyncMock(return_value=1),  # 1 < 4: would normally be rejected
            ),
            patch(
                "agent.services.element_data_service._has_pdf_in_base_docs",
                new=AsyncMock(return_value=True),
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
                mode_context=_base_mode_context(),
            )

        assert result["success"] is True
        assert result["base_docs_confirmed"] is True
        assert result["next_step"] == "COLLECT_PERSONAL"

    async def test_confirm_base_docs_flag_off_falls_through(self) -> None:
        """PDF present + image_count < min_required + flag OFF → NOT advanced, prompts for more."""
        from agent.services.element_data_service import confirm_base_documentation

        # Settings with flag OFF
        mock_settings = MagicMock(
            BASE_DOCS_MIN_REQUIRED_FLOOR=4,
            BASE_DOCS_PDF_SATISFIES_MINIMUM=False,
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
                new=AsyncMock(return_value=4),
            ),
            patch(
                "agent.services.element_data_service._get_case_image_count",
                new=AsyncMock(return_value=1),  # 1 < 4
            ),
            patch(
                "agent.services.element_data_service._has_pdf_in_base_docs",
                new=AsyncMock(return_value=True),  # PDF is present but flag is OFF
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
                mode_context=_base_mode_context(),
            )

        # With flag off, PDF bypass should NOT fire — system should NOT advance
        assert result["success"] is False
        assert result.get("next_step") != "COLLECT_PERSONAL"
        assert result.get("needs_confirmation") is True

    async def test_confirm_base_docs_zero_images_no_bypass(self) -> None:
        """image_count=0 + flag ON → guard prevents advancement even if stale PDF exists."""
        from agent.services.element_data_service import confirm_base_documentation

        mock_settings = MagicMock(
            BASE_DOCS_MIN_REQUIRED_FLOOR=4,
            BASE_DOCS_PDF_SATISFIES_MINIMUM=True,
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
                new=AsyncMock(return_value=4),
            ),
            patch(
                "agent.services.element_data_service._get_case_image_count",
                new=AsyncMock(return_value=0),  # ZERO images
            ),
            patch(
                "agent.services.element_data_service._has_pdf_in_base_docs",
                new=AsyncMock(return_value=True),  # Would return True but guard stops it
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
                mode_context=_base_mode_context(),
            )

        # Zero images — must NOT advance regardless of PDF flag
        assert result["success"] is False
        assert result.get("next_step") != "COLLECT_PERSONAL"
