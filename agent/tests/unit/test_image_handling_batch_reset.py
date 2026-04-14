"""
Unit tests for image_handling.reset_all_batch_counters.

T6 — fix-image-batch-ux:
  - reset_all_batch_counters deletes scoped keys via SCAN + DEL
  - reset_all_batch_counters deletes the legacy key
  - reset_all_batch_counters cleans the snapshot and batch_state keys
"""

from unittest.mock import AsyncMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONV_ID = "42"


def _make_redis(scan_pages: list[tuple[int, list[bytes]]]) -> AsyncMock:
    """
    Build a mock redis client whose scan() returns the given pages in order.
    scan_pages is a list of (cursor, keys) tuples:
        [(100, [b"key1", b"key2"]), (0, [])]   # two-page scan
    """
    redis = AsyncMock()

    scan_iter = iter(scan_pages)

    async def _scan(cursor, match, count):
        return next(scan_iter)

    redis.scan = _scan
    redis.delete = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResetAllBatchCounters:
    @pytest.mark.asyncio
    async def test_scan_and_delete_scoped_keys(self):
        """SCAN returns two scoped keys; they must be deleted."""
        from agent.services.image_handling import reset_all_batch_counters

        scoped_keys = [b"image_batch:42:scope1", b"image_batch:42:scope2"]
        redis = _make_redis([(0, scoped_keys)])

        await reset_all_batch_counters(redis, _CONV_ID)

        redis.delete.assert_any_call(*scoped_keys)

    @pytest.mark.asyncio
    async def test_legacy_key_deleted(self):
        """The legacy key image_batch:{conv_id} must always be deleted."""
        from agent.services.image_handling import reset_all_batch_counters

        redis = _make_redis([(0, [])])  # scan returns nothing

        await reset_all_batch_counters(redis, _CONV_ID)

        # legacy key is image_batch:42 (no scope suffix)
        legacy_key = f"image_batch:{_CONV_ID}"
        calls = [str(c) for c in redis.delete.call_args_list]
        assert any(legacy_key in c for c in calls), (
            f"Legacy key {legacy_key!r} not deleted. Calls: {redis.delete.call_args_list}"
        )

    @pytest.mark.asyncio
    async def test_snapshot_and_state_keys_deleted(self):
        """image_assignment_snapshot and image_batch_state keys must be deleted."""
        from agent.services.image_handling import reset_all_batch_counters

        redis = _make_redis([(0, [])])

        await reset_all_batch_counters(redis, _CONV_ID)

        snapshot_key = f"image_assignment_snapshot:{_CONV_ID}"
        state_key = f"image_batch_state:{_CONV_ID}"
        calls = [str(c) for c in redis.delete.call_args_list]
        assert any(snapshot_key in c for c in calls), (
            f"Snapshot key not deleted. Calls: {redis.delete.call_args_list}"
        )
        assert any(state_key in c for c in calls), (
            f"Batch state key not deleted. Calls: {redis.delete.call_args_list}"
        )

    @pytest.mark.asyncio
    async def test_multi_page_scan(self):
        """SCAN pagination: cursor != 0 → keep scanning until cursor == 0."""
        from agent.services.image_handling import reset_all_batch_counters

        page1_keys = [b"image_batch:42:a", b"image_batch:42:b"]
        page2_keys = [b"image_batch:42:c"]
        redis = _make_redis([(99, page1_keys), (0, page2_keys)])

        await reset_all_batch_counters(redis, _CONV_ID)

        redis.delete.assert_any_call(*page1_keys)
        redis.delete.assert_any_call(*page2_keys)

    @pytest.mark.asyncio
    async def test_empty_scan_no_batch_delete(self):
        """If SCAN returns no scoped keys, only legacy + snapshot + state are deleted."""
        from agent.services.image_handling import reset_all_batch_counters

        redis = _make_redis([(0, [])])

        await reset_all_batch_counters(redis, _CONV_ID)

        # Only the three individual keys should be deleted, no batch call for scoped keys
        delete_calls = redis.delete.call_args_list
        # Every call should be a single-key delete (no *list expansion from scan)
        for c in delete_calls:
            args = c[0]
            assert len(args) == 1, (
                f"Unexpected multi-key delete when scan was empty: {args}"
            )
