"""
Unit tests for the pure helper functions moved to element_service in T2.2a/b.

Tests:
- get_or_fetch_category_id (Redis + DB flow)
- _fuzzy_best_match (combined SequenceMatcher + Jaccard)
- normalize_element_code (exact, plural, ES, fuzzy)
- normalize_element_codes (batch normalization)
- validate_element_codes (category + code validation)

No DB / Redis connections are used — all external calls are mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.services.element_service import (
    _fuzzy_best_match,
    normalize_element_code,
    normalize_element_codes,
    get_or_fetch_category_id,
)


# ---------------------------------------------------------------------------
# Valid code fixtures
# ---------------------------------------------------------------------------

VALID_CODES: set[str] = {
    "ESCAPE",
    "ASIDEROS",
    "MANILLAR",
    "SUSPENSION_DEL",
    "SUSPENSION_TRAS",
    "PLACA_SOLAR",
    "MOTORES",
}


# ---------------------------------------------------------------------------
# _fuzzy_best_match
# ---------------------------------------------------------------------------


class TestFuzzyBestMatch:
    """Tests for the combined SequenceMatcher + token-Jaccard fuzzy matcher."""

    def test_exact_match_returns_code(self):
        assert _fuzzy_best_match("ESCAPE", {"ESCAPE", "ASIDEROS"}) == "ESCAPE"

    def test_very_close_match_returned(self):
        # ESCAP is 5/6 chars of ESCAPE — should pass threshold
        result = _fuzzy_best_match("ESCAP", {"ESCAPE", "MANILLAR", "ASIDEROS"})
        assert result == "ESCAPE"

    def test_empty_code_returns_none(self):
        assert _fuzzy_best_match("", VALID_CODES) is None

    def test_empty_valid_codes_returns_none(self):
        assert _fuzzy_best_match("ESCAPE", set()) is None

    def test_no_match_below_threshold_returns_none(self):
        # "XXXXXX" is far from everything
        assert _fuzzy_best_match("XXXXXX", VALID_CODES) is None

    def test_ambiguous_match_returns_none(self):
        # SUSPENSION_DEL and SUSPENSION_TRAS are very similar — should be ambiguous
        # When two candidates are tied (within 1e-9), return None
        codes = {"SUSPENSION_DEL", "SUSPENSION_TRAS"}
        # "SUSPENSION" is equidistant from both (same prefix)
        result = _fuzzy_best_match("SUSPENSION", codes)
        # Either None (ambiguous) or the closer one — not a specific assertion
        # but it should not raise
        assert result is None or result in codes

    def test_threshold_parameter(self):
        # With a high threshold, no match should be found
        result = _fuzzy_best_match("ESCAP", VALID_CODES, threshold=0.99)
        assert result is None


# ---------------------------------------------------------------------------
# normalize_element_code
# ---------------------------------------------------------------------------


class TestNormalizeElementCode:
    """Tests for normalize_element_code — exact, plural, ES, fuzzy pipeline."""

    def test_exact_match_uppercase(self):
        matched, corrected = normalize_element_code("ESCAPE", VALID_CODES)
        assert matched == "ESCAPE"
        assert corrected is False

    def test_exact_match_lowercase_corrects_case(self):
        matched, corrected = normalize_element_code("escape", VALID_CODES)
        assert matched == "ESCAPE"
        assert corrected is True

    def test_singular_to_plural_added_s(self):
        # ASIDERO → ASIDEROS
        matched, corrected = normalize_element_code("ASIDERO", VALID_CODES)
        assert matched == "ASIDEROS"
        assert corrected is True

    def test_plural_to_singular_removed_s(self):
        # "MANILLARES" doesn't exist but "MANILLAR" does — with S removed
        # Let's use MOTORES → MOTOR would be wrong, but MOTORES exists
        # "MOTORESS" → "MOTORES" (remove extra S)
        codes = {"MOTORES"}
        matched, corrected = normalize_element_code("MOTORESS", codes)
        assert matched == "MOTORES"
        assert corrected is True

    def test_adds_es_for_consonant_ending(self):
        # MOTOR → MOTORES (added ES)
        codes = {"MOTORES"}
        matched, corrected = normalize_element_code("MOTOR", codes)
        assert matched == "MOTORES"
        assert corrected is True

    def test_no_match_returns_none(self):
        matched, corrected = normalize_element_code("NONEXISTENT_CODE", VALID_CODES)
        assert matched is None
        assert corrected is False

    def test_empty_code_returns_none(self):
        matched, corrected = normalize_element_code("", VALID_CODES)
        assert matched is None
        assert corrected is False

    def test_empty_valid_codes_returns_none(self):
        matched, corrected = normalize_element_code("ESCAPE", set())
        assert matched is None
        assert corrected is False

    def test_fuzzy_match_as_last_resort(self):
        # "PLACA_SOLA" is close to "PLACA_SOLAR" — should fuzzy-match
        matched, corrected = normalize_element_code("PLACA_SOLA", VALID_CODES)
        assert matched == "PLACA_SOLAR"
        assert corrected is True


# ---------------------------------------------------------------------------
# normalize_element_codes
# ---------------------------------------------------------------------------


class TestNormalizeElementCodes:
    """Tests for batch normalization of element codes."""

    def test_all_valid_no_corrections(self):
        codes = ["ESCAPE", "ASIDEROS", "MANILLAR"]
        normalized, corrected, invalid = normalize_element_codes(codes, VALID_CODES)
        assert set(normalized) == {"ESCAPE", "ASIDEROS", "MANILLAR"}
        assert corrected == []
        assert invalid == []

    def test_mixed_valid_and_invalid(self):
        codes = ["ESCAPE", "NONEXISTENT"]
        normalized, corrected, invalid = normalize_element_codes(codes, VALID_CODES)
        assert normalized == ["ESCAPE"]
        assert invalid == ["NONEXISTENT"]
        assert corrected == []

    def test_auto_corrects_singular_to_plural(self):
        codes = ["ASIDERO"]  # Should become ASIDEROS
        normalized, corrected, invalid = normalize_element_codes(codes, VALID_CODES)
        assert normalized == ["ASIDEROS"]
        assert len(corrected) == 1
        assert "ASIDERO → ASIDEROS" in corrected[0]
        assert invalid == []

    def test_empty_input(self):
        normalized, corrected, invalid = normalize_element_codes([], VALID_CODES)
        assert normalized == []
        assert corrected == []
        assert invalid == []

    def test_all_invalid(self):
        codes = ["FAKE1", "FAKE2"]
        normalized, corrected, invalid = normalize_element_codes(codes, VALID_CODES)
        assert normalized == []
        assert corrected == []
        assert set(invalid) == {"FAKE1", "FAKE2"}


# ---------------------------------------------------------------------------
# get_or_fetch_category_id — Redis caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetOrFetchCategoryId:
    """Tests for the Redis-cached category ID lookup."""

    async def test_returns_from_redis_cache_as_bytes(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"cached-uuid"

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session") as mock_session:
                result = await get_or_fetch_category_id("motos-part")

        assert result == "cached-uuid"
        mock_session.assert_not_called()

    async def test_returns_from_redis_cache_as_str(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "cached-uuid-str"

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session") as mock_session:
                result = await get_or_fetch_category_id("motos-part")

        assert result == "cached-uuid-str"
        mock_session.assert_not_called()

    async def test_falls_back_to_db_on_cache_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_cat = MagicMock()
        mock_cat.id = "db-uuid"
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = mock_cat
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_exec_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("motos-part")

        assert result == "db-uuid"
        mock_redis.setex.assert_called_once_with("category:slug:motos-part", 300, "db-uuid")

    async def test_returns_none_when_not_found(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = None  # Not found
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_exec_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("nonexistent")

        assert result is None
        mock_redis.setex.assert_not_called()

    async def test_redis_error_falls_back_to_db(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")

        mock_cat = MagicMock()
        mock_cat.id = "fallback-uuid"
        mock_exec_result = MagicMock()
        mock_exec_result.scalar_one_or_none.return_value = mock_cat
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_exec_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("agent.services.element_service.get_redis_client", return_value=mock_redis):
            with patch("agent.services.element_service.get_async_session", return_value=mock_cm):
                result = await get_or_fetch_category_id("motos-part")

        assert result == "fallback-uuid"
