"""
Tests for BASE_DOCS_MIN_REQUIRED_FLOOR setting and _get_base_docs_min_required() helper.

T-01: Setting exists in shared/config.py with correct defaults and validation.
T-03: Helper returns max(db_count, len(descriptions), floor) with DB failure fallback.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# T-01: BASE_DOCS_MIN_REQUIRED_FLOOR setting
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestBaseDossMinRequiredFloorSetting:
    """T-01: Setting exists with correct defaults and Pydantic validation."""

    def test_setting_default_is_four(self) -> None:
        """Default value must be 4."""
        from shared.config import get_settings

        settings = get_settings()
        assert settings.BASE_DOCS_MIN_REQUIRED_FLOOR == 4

    def test_setting_is_int(self) -> None:
        """Setting must be an integer."""
        from shared.config import get_settings

        settings = get_settings()
        assert isinstance(settings.BASE_DOCS_MIN_REQUIRED_FLOOR, int)

    def test_setting_can_be_overridden(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting can be overridden via env var BASE_DOCS_MIN_REQUIRED_FLOOR=6."""
        import importlib
        import shared.config as _cfg_mod

        monkeypatch.setenv("BASE_DOCS_MIN_REQUIRED_FLOOR", "6")
        # Re-create Settings with the new env var (bypass lru_cache)
        fresh_settings = _cfg_mod.Settings()
        assert fresh_settings.BASE_DOCS_MIN_REQUIRED_FLOOR == 6

    def test_setting_rejects_below_two(self) -> None:
        """Pydantic must raise ValidationError for values below ge=2."""
        import shared.config as _cfg_mod
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _cfg_mod.Settings(BASE_DOCS_MIN_REQUIRED_FLOOR=1)

    def test_setting_rejects_above_twenty(self) -> None:
        """Pydantic must raise ValidationError for values above le=20."""
        import shared.config as _cfg_mod
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _cfg_mod.Settings(BASE_DOCS_MIN_REQUIRED_FLOOR=21)


# ─────────────────────────────────────────────────────────────────────────────
# T-03: _get_base_docs_min_required() helper
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetBaseDocsMinRequired:
    """T-03: Helper returns correct minimum across DB count, descriptions, and floor."""

    def _make_session_mock(self, db_count: int) -> MagicMock:
        """Build a mock async session context manager returning db_count."""
        mock_session_ctx = MagicMock()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_count
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_session_ctx

    def _make_failing_session_mock(self) -> MagicMock:
        """Build a mock async session context manager that raises on enter."""
        mock_session_ctx = MagicMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB connection failed")
        )
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_session_ctx

    async def test_scenario_a_db_count_wins(self) -> None:
        """SCENARIO A: db_count=7, descriptions=3, floor=4 → returns 7."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_session_mock(db_count=7)
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=["doc1", "doc2", "doc3"],
            )

        assert result == 7

    async def test_scenario_b_descriptions_wins(self) -> None:
        """SCENARIO B: db_count=3, descriptions=8, floor=4 → returns 8."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_session_mock(db_count=3)
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=["d"] * 8,
            )

        assert result == 8

    async def test_scenario_c_floor_wins_empty_descriptions(self) -> None:
        """SCENARIO C: db_count=1, descriptions=[], floor=4 → returns 4."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_session_mock(db_count=1)
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=[],
            )

        assert result == 4

    async def test_scenario_d_db_failure_falls_back_to_descriptions_or_floor(
        self,
    ) -> None:
        """SCENARIO D: DB raises Exception → non-fatal, returns max(len(descriptions), floor)."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_failing_session_mock()
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            # Should not raise — must be non-fatal
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=["doc1", "doc2"],
            )

        # max(len(["doc1","doc2"]), floor=4) → 4
        assert result == 4

    async def test_scenario_d_db_failure_descriptions_win_over_floor(self) -> None:
        """SCENARIO D (variant): DB fails, 6 descriptions, floor=4 → returns 6."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_failing_session_mock()
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=["d"] * 6,
            )

        assert result == 6

    async def test_scenario_e_zero_count_never_returns_two(self) -> None:
        """SCENARIO E: db_count=0, descriptions=[], floor=4 → returns 4, never 2."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_session_ctx = self._make_session_mock(db_count=0)
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=[],
            )

        assert result == 4
        assert result != 2

    async def test_no_category_id_skips_db_uses_floor(self) -> None:
        """No category_id → skip DB query, use max(len(descriptions), floor)."""
        from agent.services.element_data_service import _get_base_docs_min_required

        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with patch(
            "agent.services.element_data_service._get_base_docs_settings",
            return_value=mock_settings,
        ):
            result = await _get_base_docs_min_required(
                case_id="case-1",
                category_id=None,
                base_doc_descriptions=["doc1"],
            )

        assert result == 4  # max(1, 4) → 4

    async def test_query_includes_is_active_filter(self) -> None:
        """DB query MUST include is_active=True to exclude soft-deleted records.

        Verifies W-1 fix: the WHERE clause must filter out inactive BaseDocumentation
        rows so that soft-deleted records are not counted toward the minimum.
        """
        from sqlalchemy import and_

        from agent.services.element_data_service import _get_base_docs_min_required

        captured_where_clauses: list = []

        class _CapturingMockResult:
            def scalar_one_or_none(self):
                return 3

        class _CapturingMockSession:
            async def execute(self, stmt):
                # Capture the WHERE clause description for assertion
                captured_where_clauses.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
                return _CapturingMockResult()

        mock_session_ctx = MagicMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(
            return_value=_CapturingMockSession()
        )
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_settings = MagicMock(BASE_DOCS_MIN_REQUIRED_FLOOR=4)

        with (
            patch(
                "agent.services.element_data_service.get_async_session",
                mock_session_ctx,
            ),
            patch(
                "agent.services.element_data_service._get_base_docs_settings",
                return_value=mock_settings,
            ),
        ):
            await _get_base_docs_min_required(
                case_id="case-1",
                category_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                base_doc_descriptions=["doc1"],
            )

        assert captured_where_clauses, "No SQL was executed — DB was not queried"
        sql = captured_where_clauses[0]
        # The compiled SQL must include the is_active filter
        assert "is_active" in sql, (
            f"is_active filter missing from query. Got: {sql}"
        )
        assert "true" in sql.lower() or "True" in sql, (
            f"is_active = true condition not found in query. Got: {sql}"
        )
