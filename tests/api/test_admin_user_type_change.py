"""
Tests for client_type change guard in api.routes.admin.update_user().

Tasks 1.7, 1.8, 1.9 — harden-client-type-edges

Requirements verified:
  - 1.7: PUT /api/admin/users/{id} with client_type change AND active case → HTTP 409
  - 1.8: PUT /api/admin/users/{id} with client_type change AND no active case → HTTP 200
  - 1.9: PUT /api/admin/users/{id} with only other fields AND active case → HTTP 200

Import strategy:
  - Load api.routes.admin via importlib to bypass heavy transitive deps
    (jose, passlib, phonenumbers, etc.)
  - Stub all external modules in sys.modules before loading the module under test
  - Call update_user() directly with mocked session and dependencies
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from contextlib import asynccontextmanager
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Bootstrap: load api.routes.admin without full app environment
# ---------------------------------------------------------------------------


def _bootstrap_admin_module():
    """Load api.routes.admin and return the module.

    Stubs all heavy transitive dependencies so this test file
    doesn't need a full Docker environment.
    """
    heavy_deps = [
        "jose", "jose.jwt",
        "passlib", "passlib.hash", "passlib.context",
        "phonenumbers",
        "bcrypt",
    ]
    for mod in heavy_deps:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    # passlib.hash.bcrypt needs .verify and .hash
    if "passlib.hash" in sys.modules:
        sys.modules["passlib.hash"].bcrypt = MagicMock()

    # Stub shared modules
    for mod in [
        "shared.chatwoot_client",
        "shared.chatwoot_sync",
        "shared.redis_client",
        "shared.image_security",
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
            # Provide common attributes used by admin.py
            stub.ChatwootClient = MagicMock()
            stub.get_redis_client = MagicMock()
            stub.ConversationResetCoordinator = MagicMock()
            stub.ResetExecutionContext = MagicMock()
            stub.GCResult = MagicMock()
            stub.run_gc = AsyncMock()
            stub.ConversationResetDatabaseExecutor = MagicMock()
            stub.ConversationResetRedisExecutor = MagicMock()
            stub.ConversationResetFilesExecutor = MagicMock()
            stub.ConversationResetChatwootExecutor = MagicMock()
            sys.modules[mod] = stub

    # Stub api.models.admin_user (Pydantic models used by admin.py)
    if "api.models.admin_user" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.models.admin_user",
            "/home/pepe/Proyectos/msi-a/api/models/admin_user.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["api.models.admin_user"] = mod
        spec.loader.exec_module(mod)

    # Load the target module
    spec = importlib.util.spec_from_file_location(
        "api.routes.admin",
        "/home/pepe/Proyectos/msi-a/api/routes/admin.py",
    )
    admin_mod = importlib.util.module_from_spec(spec)
    sys.modules["api.routes.admin"] = admin_mod
    spec.loader.exec_module(admin_mod)
    return admin_mod


admin_module = _bootstrap_admin_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    client_type: str = "particular",
    updated_at=None,
    created_at=None,
) -> MagicMock:
    """Build a mock User object matching admin.py field accesses."""
    from datetime import UTC, datetime

    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.client_type = client_type
    user.phone = "+34600000001"
    user.first_name = "Test"
    user.last_name = "User"
    user.email = "test@example.com"
    user.nif_cif = None
    user.company_name = None
    user.domicilio_calle = None
    user.domicilio_localidad = None
    user.domicilio_provincia = None
    user.domicilio_cp = None
    user.chatwoot_contact_id = None
    user.metadata_ = {}
    user.created_at = created_at or datetime.now(UTC)
    user.updated_at = updated_at or datetime.now(UTC)
    return user


def _make_update_request(
    **kwargs,
) -> MagicMock:
    """Build a mock UserUpdateRequest (Pydantic model substitute)."""
    req = MagicMock()
    # Defaults — all None unless overridden
    req.client_type = kwargs.get("client_type", None)
    req.first_name = kwargs.get("first_name", None)
    req.last_name = kwargs.get("last_name", None)
    req.email = kwargs.get("email", None)
    req.metadata = kwargs.get("metadata", None)
    # model_dump(exclude_unset=True) should return only the provided fields
    provided = {k: v for k, v in kwargs.items() if v is not None}
    req.model_dump = MagicMock(return_value=provided)
    return req


def _make_session(
    user: MagicMock,
    active_case_count: int = 0,
) -> tuple[MagicMock, asynccontextmanager]:
    """Build an AsyncSession mock and its context manager factory.

    session.get(User, user_id) → user
    session.execute(count query) → scalar() → active_case_count
    """
    session = AsyncMock()
    session.get = AsyncMock(return_value=user)

    count_result = MagicMock()
    count_result.scalar = MagicMock(return_value=active_case_count)
    session.execute = AsyncMock(return_value=count_result)

    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    return session, _ctx


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Task 1.7 — client_type change blocked when active case exists (HTTP 409)
# ---------------------------------------------------------------------------


class TestClientTypeChangeBlockedWithActiveCase:
    """1.7: PUT with client_type change AND active case must return HTTP 409."""

    def test_returns_409_when_active_case_exists(self):
        """When user has 1 active case (status=collecting) and admin tries to
        change client_type, the endpoint must raise HTTP 409."""
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, client_type="particular")
        data = _make_update_request(client_type="professional")

        _session, session_ctx = _make_session(user, active_case_count=1)
        mock_current_user = {"id": str(uuid.uuid4()), "role": "admin"}

        async def _call():
            with patch.object(admin_module, "get_async_session", session_ctx):
                return await admin_module.update_user(
                    user_id=user_id,
                    data=data,
                    current_user=mock_current_user,
                )

        with pytest.raises(HTTPException) as exc_info:
            _run(_call())

        assert exc_info.value.status_code == 409, (
            f"Expected HTTP 409 Conflict, got {exc_info.value.status_code}. "
            f"Detail: {exc_info.value.detail}"
        )
        assert "client_type" in exc_info.value.detail.lower() or \
               "expediente" in exc_info.value.detail.lower() or \
               "activo" in exc_info.value.detail.lower(), (
            f"Expected detail to mention active case / client_type conflict. "
            f"Got: {exc_info.value.detail!r}"
        )

    def test_returns_409_when_two_active_cases_exist(self):
        """HTTP 409 also applies when there are 2+ active cases."""
        from fastapi import HTTPException

        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, client_type="particular")
        data = _make_update_request(client_type="professional")

        _session, session_ctx = _make_session(user, active_case_count=2)
        mock_current_user = {"id": str(uuid.uuid4()), "role": "admin"}

        async def _call():
            with patch.object(admin_module, "get_async_session", session_ctx):
                return await admin_module.update_user(
                    user_id=user_id,
                    data=data,
                    current_user=mock_current_user,
                )

        with pytest.raises(HTTPException) as exc_info:
            _run(_call())

        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Task 1.8 — client_type change allowed when no active case (HTTP 200)
# ---------------------------------------------------------------------------


class TestClientTypeChangeAllowedNoActiveCase:
    """1.8: PUT with client_type change AND no active case must return HTTP 200."""

    def test_returns_200_when_no_active_cases(self):
        """When user has zero active cases, client_type change must succeed."""
        import json

        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, client_type="particular")
        data = _make_update_request(client_type="professional")

        _session, session_ctx = _make_session(user, active_case_count=0)
        mock_current_user = {"id": str(uuid.uuid4()), "role": "admin"}

        # Stub Chatwoot sync (best-effort, not relevant here)
        chatwoot_stub = ModuleType("shared.chatwoot_sync")
        chatwoot_stub.sync_user_to_chatwoot = AsyncMock(return_value=False)
        sys.modules["shared.chatwoot_sync"] = chatwoot_stub

        async def _call():
            with patch.object(admin_module, "get_async_session", session_ctx):
                return await admin_module.update_user(
                    user_id=user_id,
                    data=data,
                    current_user=mock_current_user,
                )

        response = _run(_call())

        body = json.loads(response.body)
        # After the update the mock user.client_type was set to "professional"
        # (setattr called by the update loop); confirm 200 via absence of exception
        assert response.status_code == 200, (
            f"Expected HTTP 200, got {response.status_code}. Body: {body}"
        )


# ---------------------------------------------------------------------------
# Task 1.9 — other field update unaffected by active case (HTTP 200)
# ---------------------------------------------------------------------------


class TestOtherFieldUpdateUnaffectedByActiveCase:
    """1.9: PUT with only first_name (no client_type) must return HTTP 200
    even when user has active cases."""

    def test_first_name_update_not_blocked_by_active_case(self):
        """When client_type is NOT in the update payload, the active-case check
        must be skipped entirely — HTTP 200 is expected."""
        import json

        user_id = uuid.uuid4()
        user = _make_user(user_id=user_id, client_type="particular")
        # Only updating first_name — no client_type in payload
        data = _make_update_request(first_name="Ana")

        # Session has 1 active case — but since client_type is not changing,
        # the 409 guard must not fire
        _session, session_ctx = _make_session(user, active_case_count=1)
        mock_current_user = {"id": str(uuid.uuid4()), "role": "admin"}

        chatwoot_stub = ModuleType("shared.chatwoot_sync")
        chatwoot_stub.sync_user_to_chatwoot = AsyncMock(return_value=False)
        sys.modules["shared.chatwoot_sync"] = chatwoot_stub

        async def _call():
            with patch.object(admin_module, "get_async_session", session_ctx):
                return await admin_module.update_user(
                    user_id=user_id,
                    data=data,
                    current_user=mock_current_user,
                )

        response = _run(_call())

        assert response.status_code == 200, (
            f"Expected HTTP 200 for first_name-only update, got {response.status_code}."
        )
