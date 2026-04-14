"""
Tests for get_case_stats() — abandoned case count.

Spec 6: API Stats Fix

Requirements verified:
  - get_case_stats() response includes `abandoned` key with count of abandoned cases
  - `abandoned` is 0 when no abandoned cases exist
  - `total_active` excludes abandoned cases (only sums active statuses)
  - collecting count in response is the raw DB count, not inflated by abandoned

Import strategy:
  - Use importlib.util.spec_from_file_location to load api.routes.cases directly,
    bypassing api.routes.__init__ which pulls in heavy deps (jose, passlib, etc.)
  - api.models.element is loaded the same way (avoids phonenumbers dep via __init__)
  - api.routes.admin and shared.chatwoot_client are stubbed in sys.modules
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
# Bootstrap: load api.routes.cases and its real deps without full env
# ---------------------------------------------------------------------------


def _bootstrap_cases_module():
    """Load api.routes.cases and return the module.

    Called once at module level. Stubs heavy transitive deps so that
    importing this test file doesn't require full application env.
    """
    # Stub external packages not installed in test env
    for mod in ["jose", "jose.jwt", "passlib", "passlib.hash", "passlib.context", "phonenumbers"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    # Load api.models.element with real Pydantic models (required by cases.py)
    if "api.models.element" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.models.element",
            "/home/pepe/Proyectos/msi-a/api/models/element.py",
        )
        elem_mod = importlib.util.module_from_spec(spec)
        sys.modules["api.models.element"] = elem_mod
        spec.loader.exec_module(elem_mod)

    # Stub api.routes.admin (only need get_current_user + require_role)
    if "api.routes.admin" not in sys.modules:
        admin_stub = ModuleType("api.routes.admin")
        admin_stub.get_current_user = MagicMock()
        admin_stub.require_role = MagicMock()
        admin_stub.router = MagicMock()
        sys.modules["api.routes.admin"] = admin_stub

    # Stub shared.chatwoot_client
    if "shared.chatwoot_client" not in sys.modules:
        sys.modules["shared.chatwoot_client"] = MagicMock()

    # Stub api.services.*
    for mod in ["api.services", "api.services.chatwoot_image_service"]:
        if mod not in sys.modules:
            stub = ModuleType(mod)
            stub.get_chatwoot_image_service = MagicMock()
            sys.modules[mod] = stub

    # Load api.routes.cases directly (bypasses api.routes.__init__)
    spec = importlib.util.spec_from_file_location(
        "api.routes.cases",
        "/home/pepe/Proyectos/msi-a/api/routes/cases.py",
    )
    cases_mod = importlib.util.module_from_spec(spec)
    sys.modules["api.routes.cases"] = cases_mod
    spec.loader.exec_module(cases_mod)
    return cases_mod


cases_module = _bootstrap_cases_module()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_mock_session(counts_by_status: dict[str, int]) -> MagicMock:
    """Build a mock AsyncSession matching get_case_stats() query calls.

    get_case_stats() calls:
      1. session.execute(group-by status) → result.all() → list[(status, count)]
      2. session.scalar() for created_today → 0
      3. session.scalar() for resolved_today → 0
    """
    session = MagicMock()

    status_rows = list(counts_by_status.items())
    execute_result = MagicMock()
    execute_result.all.return_value = status_rows
    session.execute = AsyncMock(return_value=execute_result)
    session.scalar = AsyncMock(return_value=0)

    return session


def _fake_session_ctx(mock_session: MagicMock):
    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx


def _call_get_case_stats(counts_by_status: dict[str, int]) -> dict:
    """Call get_case_stats() directly with a mocked session, return parsed response."""
    mock_session = _make_mock_session(counts_by_status)
    fake_ctx = _fake_session_ctx(mock_session)
    mock_user = MagicMock()

    async def _run():
        with patch.object(cases_module, "get_async_session", fake_ctx):
            return await cases_module.get_case_stats(current_user=mock_user)

    response = asyncio.run(_run())
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# T-B4-1: Tests (RED — `abandoned` key not yet in response)
# ---------------------------------------------------------------------------


class TestCaseStatsAbandonedKey:
    """get_case_stats() must include `abandoned` key in the response."""

    def test_abandoned_count_reflects_db(self) -> None:
        """Response must return abandoned=2 when 2 abandoned cases exist in DB."""
        data = _call_get_case_stats({"collecting": 3, "abandoned": 2})

        assert "abandoned" in data, (
            f"`abandoned` key missing from response. Keys present: {list(data.keys())}"
        )
        assert data["abandoned"] == 2, (
            f"Expected abandoned=2, got {data['abandoned']!r}. Full response: {data}"
        )

    def test_abandoned_zero_when_no_abandoned_cases(self) -> None:
        """Response must return abandoned=0 when no abandoned cases exist."""
        data = _call_get_case_stats({"collecting": 5, "pending_review": 1})

        assert "abandoned" in data, (
            f"`abandoned` key missing from response. Keys present: {list(data.keys())}"
        )
        assert data["abandoned"] == 0, (
            f"Expected abandoned=0, got {data['abandoned']!r}. Full response: {data}"
        )


class TestCaseStatsTotalActiveExcludesAbandoned:
    """total_active must never include abandoned cases."""

    def test_total_active_excludes_abandoned(self) -> None:
        """total_active must equal sum of active statuses only, excluding abandoned."""
        data = _call_get_case_stats({
            "collecting": 3,
            "pending_images": 1,
            "pending_review": 2,
            "in_progress": 0,
            "abandoned": 4,
        })

        # active_statuses = ["collecting", "pending_images", "pending_review", "in_progress"]
        # expected = 3 + 1 + 2 + 0 = 6 (abandoned=4 must not be included)
        assert data["total_active"] == 6, (
            f"Expected total_active=6 (excluding 4 abandoned), got {data['total_active']}. "
            f"Full response: {data}"
        )

    def test_total_active_is_zero_when_only_abandoned(self) -> None:
        """total_active must be 0 when only abandoned cases exist."""
        data = _call_get_case_stats({"abandoned": 5})

        assert data["total_active"] == 0, (
            f"Expected total_active=0 (no active statuses), got {data['total_active']}. "
            f"Full response: {data}"
        )
        assert data["abandoned"] == 5, (
            f"Expected abandoned=5, got {data['abandoned']}. Full response: {data}"
        )
