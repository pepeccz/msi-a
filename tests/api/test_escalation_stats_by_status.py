"""
TDD tests for EscalationStats `by_status` extension.

Spec ref: Slice 0, T0.3 / T0.5 — extend GET /api/admin/escalations/stats
with a `by_status: dict[str, int]` field computed via GROUP BY status.

Requirements verified:
  - Response includes `by_status` key
  - `by_status` is a dict with string keys and integer values
  - All known statuses present in DB appear as keys
  - Statuses NOT present in DB still appear as keys with count 0
    (this ensures FilterChips always has a chip for every status, including zeroes)
  - Sum of by_status values equals total escalation count (consistency guard)
  - Existing keys (pending, in_progress, resolved_today, total_today) are NOT removed

Import strategy:
  Same sys.modules stub-injection pattern as test_case_stats_abandoned.py.
  Load api.routes.admin directly via importlib, stub heavy deps (jose, passlib,
  phonenumbers, shared.chatwoot_client, shared.chatwoot_sync, shared.settings_cache,
  api.services.*) so tests run without Docker.

Known status values (from database/models.py Escalation.status comment):
  "pending", "in_progress", "resolved"
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from contextlib import asynccontextmanager
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Bootstrap: load api.routes.admin without full Docker environment
# ---------------------------------------------------------------------------

# Known escalation status values per Escalation.status column comment
KNOWN_STATUSES = ["pending", "in_progress", "resolved"]


def _bootstrap_admin_module():
    """Load api.routes.admin and return the module.

    Stubs all heavy transitive dependencies so this test file can be collected
    and run without a running Docker / full application environment.
    """
    # Heavy packages not available in the local test env
    for mod in [
        "jose",
        "jose.jwt",
        "passlib",
        "passlib.hash",
        "passlib.context",
        "phonenumbers",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    # Stub shared.chatwoot_client (imported at admin.py module level)
    for mod in ["shared.chatwoot_client", "shared.chatwoot_sync", "shared.settings_cache"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    # Stub api.services.* modules referenced in admin.py imports
    for mod in [
        "api.services",
        "api.services.conversation_reset_coordinator",
        "api.services.garbage_collection_service",
        "api.services.conversation_reset_db_executor",
        "api.services.conversation_reset_redis_executor",
        "api.services.conversation_reset_files_executor",
        "api.services.conversation_reset_chatwoot_executor",
    ]:
        if mod not in sys.modules:
            stub = ModuleType(mod)
            # Provide minimal symbols referenced by admin.py imports
            stub.ConversationResetCoordinator = MagicMock()
            stub.ResetExecutionContext = MagicMock()
            stub.GCResult = MagicMock()
            stub.run_gc = MagicMock()
            stub.ConversationResetDatabaseExecutor = MagicMock()
            stub.ConversationResetRedisExecutor = MagicMock()
            stub.ConversationResetFilesExecutor = MagicMock()
            stub.ConversationResetChatwootExecutor = MagicMock()
            sys.modules[mod] = stub

    # Load real api.models.admin_user so FastAPI response_model validation works
    if "api.models.admin_user" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.models.admin_user",
            "/home/pepe/Projects/Clientes/msi-a/api/models/admin_user.py",
        )
        admin_user_mod = importlib.util.module_from_spec(spec)
        sys.modules["api.models.admin_user"] = admin_user_mod
        spec.loader.exec_module(admin_user_mod)

    # Load api.routes.admin directly via importlib (bypasses api.routes.__init__)
    spec = importlib.util.spec_from_file_location(
        "api.routes.admin",
        "/home/pepe/Projects/Clientes/msi-a/api/routes/admin.py",
    )
    admin_mod = importlib.util.module_from_spec(spec)
    sys.modules["api.routes.admin"] = admin_mod
    spec.loader.exec_module(admin_mod)
    return admin_mod


admin_module = _bootstrap_admin_module()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_mock_session_for_stats(
    *,
    group_by_rows: list[tuple[str, int]],
    pending: int = 0,
    in_progress: int = 0,
    resolved_today: int = 0,
    total_today: int = 0,
) -> MagicMock:
    """Build a mock AsyncSession matching get_escalation_stats() query calls.

    The extended get_escalation_stats() will call:
      1. session.scalar() → pending_count
      2. session.scalar() → in_progress_count
      3. session.scalar() → resolved_today
      4. session.scalar() → total_today
      5. session.execute(GROUP BY status) → result.all() → list[(status, count)]

    We model this with a scalar side_effect list for the scalar() calls and
    a single execute() mock for the GROUP BY query.
    """
    session = MagicMock()

    # scalar() is called 4 times in order: pending, in_progress, resolved_today, total_today
    session.scalar = AsyncMock(side_effect=[pending, in_progress, resolved_today, total_today])

    # execute() is called once for GROUP BY
    execute_result = MagicMock()
    execute_result.all.return_value = group_by_rows
    session.execute = AsyncMock(return_value=execute_result)

    return session


def _fake_session_ctx(mock_session: MagicMock):
    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx


def _call_get_escalation_stats(
    *,
    group_by_rows: list[tuple[str, int]],
    pending: int = 0,
    in_progress: int = 0,
    resolved_today: int = 0,
    total_today: int = 0,
) -> dict:
    """Call get_escalation_stats() directly with a mocked session and return parsed JSON."""
    mock_session = _make_mock_session_for_stats(
        group_by_rows=group_by_rows,
        pending=pending,
        in_progress=in_progress,
        resolved_today=resolved_today,
        total_today=total_today,
    )
    fake_ctx = _fake_session_ctx(mock_session)
    mock_user = MagicMock()

    async def _run():
        with patch.object(admin_module, "get_async_session", fake_ctx):
            return await admin_module.get_escalation_stats(current_user=mock_user)

    response = asyncio.run(_run())
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Tests — RED phase: these must FAIL until by_status is implemented
# ---------------------------------------------------------------------------


class TestEscalationStatsByStatusPresent:
    """by_status key must be present in the stats response."""

    def test_by_status_key_present(self) -> None:
        """Response must include a by_status key."""
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 3), ("in_progress", 1)]
        )
        assert "by_status" in data, (
            f"`by_status` key missing from response. Keys present: {list(data.keys())}"
        )

    def test_by_status_is_dict(self) -> None:
        """by_status must be a dict, not a list or None."""
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 2)]
        )
        assert isinstance(data.get("by_status"), dict), (
            f"`by_status` must be a dict, got {type(data.get('by_status')).__name__!r}. "
            f"Value: {data.get('by_status')!r}"
        )


class TestEscalationStatsByStatusValues:
    """by_status must correctly reflect DB GROUP BY counts."""

    def test_counts_match_db_rows(self) -> None:
        """by_status values must match the counts returned by GROUP BY."""
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 5), ("in_progress", 2), ("resolved", 10)]
        )
        by_status = data["by_status"]
        assert by_status.get("pending") == 5, (
            f"Expected pending=5, got {by_status.get('pending')!r}"
        )
        assert by_status.get("in_progress") == 2, (
            f"Expected in_progress=2, got {by_status.get('in_progress')!r}"
        )
        assert by_status.get("resolved") == 10, (
            f"Expected resolved=10, got {by_status.get('resolved')!r}"
        )

    def test_all_known_statuses_present_even_if_zero(self) -> None:
        """All known status keys must appear even when DB count is zero.

        This ensures FilterChips always receives a chip for every status,
        including those with zero matching items (shown as opacity-60 per spec).
        """
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 3)]  # in_progress and resolved absent from DB
        )
        by_status = data["by_status"]
        for status in KNOWN_STATUSES:
            assert status in by_status, (
                f"Status '{status}' missing from by_status even though it's a known status. "
                f"by_status: {by_status!r}"
            )
        assert by_status["in_progress"] == 0, (
            f"Expected in_progress=0 (not in DB), got {by_status['in_progress']!r}"
        )
        assert by_status["resolved"] == 0, (
            f"Expected resolved=0 (not in DB), got {by_status['resolved']!r}"
        )

    def test_empty_db_gives_zero_for_all_known_statuses(self) -> None:
        """When no escalations exist, by_status must have 0 for all known statuses."""
        data = _call_get_escalation_stats(group_by_rows=[])
        by_status = data["by_status"]
        assert isinstance(by_status, dict)
        for status in KNOWN_STATUSES:
            assert status in by_status, (
                f"Status '{status}' missing from by_status on empty DB. "
                f"by_status: {by_status!r}"
            )
            assert by_status[status] == 0, (
                f"Expected {status}=0 on empty DB, got {by_status[status]!r}"
            )

    def test_values_are_integers(self) -> None:
        """by_status values must be integers (not strings or floats)."""
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 7), ("resolved", 3)]
        )
        by_status = data["by_status"]
        for key, val in by_status.items():
            assert isinstance(val, int), (
                f"by_status['{key}'] must be int, got {type(val).__name__!r}: {val!r}"
            )

    def test_sum_equals_total_escalations(self) -> None:
        """Sum of by_status values must equal the total count across all statuses."""
        rows = [("pending", 4), ("in_progress", 2), ("resolved", 6)]
        data = _call_get_escalation_stats(group_by_rows=rows)
        by_status = data["by_status"]
        total = sum(rows[i][1] for i in range(len(rows)))
        assert sum(by_status.values()) == total, (
            f"Sum of by_status values ({sum(by_status.values())}) "
            f"does not equal total ({total}). by_status: {by_status!r}"
        )


class TestEscalationStatsExistingKeysPreserved:
    """Existing response keys must not be removed by the extension."""

    def test_existing_keys_still_present(self) -> None:
        """pending, in_progress, resolved_today, total_today must still be in response."""
        data = _call_get_escalation_stats(
            group_by_rows=[("pending", 2)],
            pending=2,
            in_progress=0,
            resolved_today=1,
            total_today=3,
        )
        for key in ("pending", "in_progress", "resolved_today", "total_today"):
            assert key in data, (
                f"Existing key '{key}' missing from response after extension. "
                f"Keys present: {list(data.keys())}"
            )

    def test_existing_values_match_scalars(self) -> None:
        """Existing scalar values must still be correct after extension."""
        data = _call_get_escalation_stats(
            group_by_rows=[],
            pending=5,
            in_progress=3,
            resolved_today=2,
            total_today=10,
        )
        assert data["pending"] == 5
        assert data["in_progress"] == 3
        assert data["resolved_today"] == 2
        assert data["total_today"] == 10
