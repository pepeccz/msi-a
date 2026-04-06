"""
Tests for ModeAwareTTLSaver.aput() — SCAN-based TTL key refresh.

Covers:
- aput uses scan_iter (non-blocking), never KEYS (blocking)
- pipeline.expire called once per scanned key
- No pipeline created when scan_iter returns empty
- scan_iter exception is swallowed, logged as WARNING, and aput still returns
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Stub dependencies not installed in local test env
# ---------------------------------------------------------------------------

if "structlog" not in sys.modules:
    _structlog_stub = types.ModuleType("structlog")
    _structlog_stub.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog_stub

for _name in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _name not in sys.modules:
        _stub = types.ModuleType(_name)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_name] = _stub

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

THREAD_ID = "conv-abc-123"
DEFAULT_TTL_BY_MODE: dict[str, int] = {
    "CONSULTA_MODE": 60,
    "PRESUPUESTO_MODE": 240,
    "EXPEDIENTE_MODE": 10080,
    "ESCALATION": 120,
    "_default": 1440,
}


def _make_config(thread_id: str = THREAD_ID) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _make_checkpoint(mode: str = "PRESUPUESTO_MODE") -> dict:
    return {"channel_values": {"current_mode": mode}}


def _build_saver(mock_redis: MagicMock) -> "ModeAwareTTLSaver":  # noqa: F821
    """Instantiate ModeAwareTTLSaver with a fully-mocked Redis client."""
    from agent.state.checkpointer import ModeAwareTTLSaver

    saver = ModeAwareTTLSaver.__new__(ModeAwareTTLSaver)
    saver._ttl_by_mode = DEFAULT_TTL_BY_MODE
    saver._redis = mock_redis
    return saver


def _make_redis_mock(scan_keys: list[bytes] | None = None) -> MagicMock:
    """
    Build a Redis mock whose scan_iter() is an async generator returning *scan_keys*.
    Also provides a pipeline mock with expire / execute methods.
    """
    redis_mock = MagicMock()

    # Async generator for scan_iter
    keys = scan_keys or []

    async def _scan_iter(**kwargs):  # noqa: ANN202
        for k in keys:
            yield k

    redis_mock.scan_iter = _scan_iter

    # pipeline() is a sync factory returning an object with async methods
    pipe_mock = MagicMock()
    pipe_mock.expire = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[True] * len(keys))

    redis_mock.pipeline = MagicMock(return_value=pipe_mock)

    # Ensure .keys is present but should NOT be called
    redis_mock.keys = AsyncMock(side_effect=AssertionError("keys() must not be called"))

    return redis_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckpointerScanBasedTTL:
    """ModeAwareTTLSaver.aput() must use scan_iter, never KEYS."""

    # ------------------------------------------------------------------
    # Test 1: scan_iter used, keys() never called
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_aput_uses_scan_not_keys(self):
        """aput must call scan_iter and must NOT call redis.keys()."""
        redis_mock = _make_redis_mock(scan_keys=[b"checkpoint:conv-abc-123:ns:v1"])
        saver = _build_saver(redis_mock)

        config = _make_config()
        checkpoint = _make_checkpoint("PRESUPUESTO_MODE")
        sentinel_result = {"configurable": {"thread_id": THREAD_ID, "checkpoint_id": "v1"}}

        with patch.object(
            saver.__class__.__bases__[0],
            "aput",
            new=AsyncMock(return_value=sentinel_result),
        ):
            result = await saver.aput(config, checkpoint, {}, {})

        # redis.keys must never have been awaited
        redis_mock.keys.assert_not_called()

        # Result propagated from super().aput()
        assert result == sentinel_result

    # ------------------------------------------------------------------
    # Test 2: pipeline.expire called once per scanned key
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_aput_applies_ttl_to_scanned_keys(self):
        """pipeline.expire must be called exactly once for each key scan_iter yields."""
        scanned_keys = [
            b"checkpoint:conv-abc-123:ns:v1",
            b"checkpoint_write:conv-abc-123:ns:v1",
            b"checkpoint_latest:conv-abc-123:ns",
        ]
        redis_mock = _make_redis_mock(scan_keys=scanned_keys)
        saver = _build_saver(redis_mock)

        config = _make_config()
        checkpoint = _make_checkpoint("PRESUPUESTO_MODE")
        expected_ttl_seconds = DEFAULT_TTL_BY_MODE["PRESUPUESTO_MODE"] * 60  # 14400

        with patch.object(
            saver.__class__.__bases__[0],
            "aput",
            new=AsyncMock(return_value=config),
        ):
            await saver.aput(config, checkpoint, {}, {})

        pipe_mock = redis_mock.pipeline.return_value
        assert pipe_mock.expire.call_count == len(scanned_keys), (
            f"Expected expire called {len(scanned_keys)} times, "
            f"got {pipe_mock.expire.call_count}"
        )

        # Verify each call passes the correct TTL
        expected_calls = [call(key, expected_ttl_seconds) for key in scanned_keys]
        pipe_mock.expire.assert_has_calls(expected_calls, any_order=False)

        # pipeline.execute must have been awaited
        pipe_mock.execute.assert_awaited_once()

    # ------------------------------------------------------------------
    # Test 3: no keys → no pipeline created
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_aput_no_keys_no_pipeline(self):
        """When scan_iter yields nothing, pipeline() must not be called."""
        redis_mock = _make_redis_mock(scan_keys=[])
        saver = _build_saver(redis_mock)

        config = _make_config()
        checkpoint = _make_checkpoint("CONSULTA_MODE")

        with patch.object(
            saver.__class__.__bases__[0],
            "aput",
            new=AsyncMock(return_value=config),
        ):
            result = await saver.aput(config, checkpoint, {}, {})

        redis_mock.pipeline.assert_not_called()
        assert result == config

    # ------------------------------------------------------------------
    # Test 4: scan_iter raises → WARNING logged, aput still returns
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_aput_scan_error_swallowed(self):
        """scan_iter exception must be swallowed; aput must return super()'s result."""
        redis_mock = MagicMock()

        # scan_iter raises immediately
        async def _boom(**kwargs):  # noqa: ANN202
            raise ConnectionError("Redis unavailable")
            yield  # make it a generator to satisfy the async for loop

        redis_mock.scan_iter = _boom
        redis_mock.keys = AsyncMock(side_effect=AssertionError("keys() must not be called"))

        saver = _build_saver(redis_mock)

        config = _make_config()
        checkpoint = _make_checkpoint("ESCALATION")
        sentinel_result = {"configurable": {"checkpoint_id": "v99"}}

        warning_log = MagicMock()

        with patch.object(
            saver.__class__.__bases__[0],
            "aput",
            new=AsyncMock(return_value=sentinel_result),
        ):
            # Patch the module-level structlog logger used inside checkpointer
            with patch("agent.state.checkpointer._structlog") as mock_structlog:
                mock_structlog.warning = warning_log
                result = await saver.aput(config, checkpoint, {}, {})

        # Must return the checkpoint result despite the error
        assert result == sentinel_result

        # Must have logged a warning
        warning_log.assert_called_once()
        call_kwargs = warning_log.call_args
        event_name = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("event", "")
        assert "ttl" in event_name.lower() or "fail" in event_name.lower(), (
            f"Expected warning event name to contain 'ttl' or 'fail', got: {event_name!r}"
        )
