"""
Unit tests for finalize_lock lifecycle — Phase 1 RED tests.

Tests verify BUG #4: finalize_lock must be explicitly deleted after
reconcile_on_completion completes in agent/main.py (V2 path), so subsequent
element batches in the same conversation are not blocked.

Design ref: sdd/fix-finalize-lock-image-flow/design
Spec ref:   sdd/fix-finalize-lock-image-flow/spec (REQ-1)

TESTING STRATEGY:
- We call process_message() with a "listo" message under V2=True, mocking all I/O.
- Critical assertion: after process_message, redis_client.delete was called with
  the finalize_lock_key (or lock key is absent from in-memory Redis state).
- RED: Tests 1 & 2 FAIL (delete never called, lock stays in Redis).
- GREEN: Passes after the try/finally fix is applied to agent/main.py.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager, ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The lock key prefix (matches IMAGE_FINALIZE_LOCK_PREFIX in image_handling.py)
FINALIZE_LOCK_PREFIX = "finalize_lock:"


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_listo_message(conversation_id: str, phone: str = "+34600000001") -> dict:
    """Build minimal message_data dict for a 'listo' completion message."""
    return {
        "conversation_id": conversation_id,
        "message_text": "listo",
        "message_type": "incoming",
        "customer_phone": phone,
        "attachments": [],
        "chatwoot_message_id": "12345",
        "message_created_at": 1700000000,
        "chatwoot_message_created_at": 1700000000,
        "user_id": None,
    }


def _make_mock_user(phone: str = "+34600000001") -> MagicMock:
    """Build a mock User ORM object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.phone = phone
    user.first_name = "Test"
    user.last_name = "User"
    user.client_type = "particular"
    return user


def _make_mock_settings(v2_enabled: bool = True) -> MagicMock:
    """Build mock settings object."""
    settings = MagicMock()
    settings.EXPEDIENTE_V2_ENABLED = v2_enabled
    settings.ENVIRONMENT = "test"
    settings.AGENT_NAME = "MSI Agent"
    settings.MESSAGE_BATCH_WINDOW_SECONDS = 0
    settings.ENABLE_LLM_METRICS = False
    settings.ENABLE_TOOL_LOGGING = False
    return settings


def _make_fake_session(mock_user: MagicMock):
    """Build an async session mock that returns mock_user on execute."""
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=mock_user)
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    return fake_session


def _build_patches(mock_user, mock_settings, reconcile_mock) -> list:
    """Build list of (target, kwargs) pairs for ExitStack patching."""
    fake_session = _make_fake_session(mock_user)

    @asynccontextmanager
    async def _fake_get_async_session():
        yield fake_session

    mock_lock = asyncio.Lock()

    return [
        ("agent.main.get_settings", {"return_value": mock_settings}),
        ("agent.main.get_async_session", {"new": _fake_get_async_session}),
        ("agent.main.is_completion_message", {"return_value": True}),
        ("agent.main.is_in_image_collection_mode", {"return_value": False}),
        ("agent.main.is_image_attachment", {"return_value": False}),
        ("agent.main.is_accepted_attachment", {"return_value": True}),
        ("agent.main.is_rejected_attachment", {"return_value": False}),
        (
            "agent.main.get_mode_context_from_checkpoint",
            {
                "new": AsyncMock(
                    return_value={"expediente_sub_mode": "collect_element_data"}
                )
            },
        ),
        ("agent.main.get_current_element_code", {"return_value": "PLACA_SOLAR"}),
        (
            "agent.main.get_case_id_from_mode_context",
            {"return_value": str(uuid.uuid4())},
        ),
        ("agent.main.persist_assignment_snapshot", {"new": AsyncMock()}),
        (
            "agent.main.assign_upload_batch",
            {
                "new": AsyncMock(
                    return_value={
                        "upload_batch_id": str(uuid.uuid4()),
                        "upload_scope_key": "scope",
                        "resolved_batch_is_historical": False,
                        "in_image_collection_mode": False,
                        "case_id": str(uuid.uuid4()),
                        "element_code": "PLACA_SOLAR",
                    }
                )
            },
        ),
        ("agent.main.reset_batch_counter", {"new": AsyncMock()}),
        ("agent.main.save_user_message", {"new": AsyncMock()}),
        ("agent.main.reconcile_on_completion", {"new": reconcile_mock}),
        ("agent.main.image_batch_confirmation_worker", {"new": AsyncMock()}),
        ("agent.main.get_initialized_checkpointer", {"return_value": None}),
        ("agent.main.get_redis_checkpointer", {"return_value": MagicMock()}),
        ("agent.main.get_conversation_lock", {"return_value": mock_lock}),
        ("agent.main.save_images_silently", {"new": AsyncMock(return_value=(0, 0))}),
        ("agent.main.update_batch_counter", {"new": AsyncMock()}),
        (
            "agent.main._build_image_assignment_snapshot",
            {
                "new": AsyncMock(
                    return_value={
                        "in_image_collection_mode": False,
                        "case_id": str(uuid.uuid4()),
                        "element_code": None,
                    }
                )
            },
        ),
    ]


async def _call_process_message_v2(
    redis_mock: AsyncMock, reconcile_side_effect=None
) -> None:
    """
    Run process_message with a 'listo' message under V2=True.
    All external I/O is mocked.
    Raises ConnectionError if one propagates from the handler.
    """
    mock_user = _make_mock_user()
    mock_settings = _make_mock_settings(v2_enabled=True)
    reconcile_mock = (
        AsyncMock(return_value=None)
        if reconcile_side_effect is None
        else AsyncMock(side_effect=reconcile_side_effect)
    )
    patches = _build_patches(mock_user, mock_settings, reconcile_mock)

    conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
    msg = _make_listo_message(conversation_id)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "ai_response": "Procesado.",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {},
            "messages": [],
        }
    )
    mock_chatwoot = AsyncMock()
    mock_chatwoot.send_message = AsyncMock(return_value={"id": 1})

    with ExitStack() as stack:
        for target, kwargs in patches:
            stack.enter_context(patch(target, **kwargs))
        from agent.main import process_message

        try:
            await process_message(mock_graph, mock_chatwoot, redis_mock, msg)
        except ConnectionError:
            raise
        except Exception:
            pass  # Swallow unrelated errors (graph invoke, etc.)


# ============================================================================
# Test 1 — finalize_lock deleted after reconcile_on_completion succeeds
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_lock_deleted_after_reconcile_on_completion() -> None:
    """
    BUG #4 regression: After reconcile_on_completion returns (V2 path),
    redis_client.delete MUST be called with the finalize_lock_key.

    RED: FAILS before fix — delete is never called.
    GREEN: Passes after `try/finally` is added to agent/main.py ~L998.
    """
    deleted_keys: list[str] = []

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.exists = AsyncMock(return_value=0)

    async def _capture_delete(*args):
        deleted_keys.extend(args)
        return len(args)

    mock_redis.delete = AsyncMock(side_effect=_capture_delete)

    await _call_process_message_v2(mock_redis)

    finalize_lock_deletes = [
        k for k in deleted_keys if k.startswith(FINALIZE_LOCK_PREFIX)
    ]

    assert len(finalize_lock_deletes) >= 1, (
        f"redis_client.delete must be called with a key matching '{FINALIZE_LOCK_PREFIX}*' "
        f"after reconcile_on_completion returns. "
        f"All deleted keys: {deleted_keys}. "
        f"FIX: Wrap V2 reconcile try/except in try/finally; add "
        f"`await redis_client.delete(finalize_lock_key)` to the finally block "
        f"(agent/main.py ~L998-1037)."
    )


# ============================================================================
# Test 2 — finalize_lock not blocking second element CTA
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_lock_not_blocking_second_element_cta() -> None:
    """
    BUG #4 regression: After PLACA_SOLAR reconcile completes, finalize_lock
    must be absent so the TOLDO_GALIBO batch worker sends its CTA.

    Uses an in-memory Redis state tracker to verify the key is removed.

    RED: Fails before fix — lock is set but never deleted.
    GREEN: Passes after the finally block deletes the lock.
    """
    redis_state: dict[str, str] = {}

    async def _mock_set(key, value, ex=None, nx=False, **kwargs):
        if nx and key in redis_state:
            return None
        redis_state[key] = value
        return True

    async def _mock_delete(*keys):
        deleted = 0
        for key in keys:
            if key in redis_state:
                del redis_state[key]
                deleted += 1
        return deleted

    async def _mock_exists(*keys):
        return sum(1 for k in keys if k in redis_state)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(side_effect=_mock_set)
    mock_redis.delete = AsyncMock(side_effect=_mock_delete)
    mock_redis.exists = AsyncMock(side_effect=_mock_exists)

    await _call_process_message_v2(mock_redis)

    lock_keys_remaining = [k for k in redis_state if k.startswith(FINALIZE_LOCK_PREFIX)]
    assert len(lock_keys_remaining) == 0, (
        f"All finalize_lock keys must be absent after reconcile completes so "
        f"the next element batch CTA worker is not suppressed. "
        f"Remaining lock keys: {lock_keys_remaining}. "
        f"Full Redis state: {redis_state}. "
        f"FIX: delete lock in finally block in agent/main.py."
    )


# ============================================================================
# Test 3 — finalize_lock delete failure is non-fatal
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_lock_delete_failure_is_non_fatal() -> None:
    """
    BUG #4 design: If redis.delete raises, the error must be swallowed.
    The delete is best-effort; TTL expiry is the fallback if Redis is down.

    Note: Before the fix there is no delete call, so this test passes trivially.
    After the fix adds the delete, this test verifies the inner try/except exists.
    If the fix omits the try/except, ConnectionError propagates → test FAILS.
    """

    async def _failing_delete(*args):
        raise ConnectionError("Redis temporarily unavailable")

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.delete = AsyncMock(side_effect=_failing_delete)

    raised_connection_error = False
    try:
        await _call_process_message_v2(mock_redis)
    except ConnectionError:
        raised_connection_error = True

    assert not raised_connection_error, (
        "process_message must NOT raise ConnectionError when redis.delete fails. "
        "The delete failure in the finally block must be caught in an inner try/except. "
        "FIX: wrap `await redis_client.delete(finalize_lock_key)` in try/except Exception."
    )
