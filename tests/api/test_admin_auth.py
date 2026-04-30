"""
TDD tests for secure-admin-auth Phase A — cookie fallback in get_current_user.

Tasks covered:
  A2: cookie-only auth → GET /admin/me → 200
  A3: bearer-only auth → GET /admin/me → 200 (backward-compat regression)
  A4: both present → bearer JTI wins
  A5: expired cookie → 401
  A6: no credentials → 401

Strategy:
  Build a minimal FastAPI app that wires get_current_user into a /admin/me
  route, stubbing all heavy external dependencies (DB, Redis, jose, passlib)
  so these tests run without a full Docker environment.

  JWT tokens are created directly via the jose library (also stubbed with a
  real-ish implementation using PyJWT or jose, depending on what's available)
  or, more portably, using the same create_access_token() helper that lives
  in api.routes.admin after the heavy deps are stubbed.

Implementation note:
  We load api.routes.admin via sys.modules stub injection (same pattern as
  test_admin_user_type_change.py) so we can swap out the DB lookup and Redis
  blacklist check for controlled mocks.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Bootstrap — load api.routes.admin without full Docker environment
# ---------------------------------------------------------------------------

def _make_jose_stub():
    """Return a jose stub that performs real HS256 JWT encode/decode."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    class _JWTError(Exception):
        pass

    class _JWT:
        """Minimal JWT implementation sufficient for HS256 tests."""

        @staticmethod
        def encode(claims: dict, key: str, algorithm: str = "HS256") -> str:
            header = {"alg": algorithm, "typ": "JWT"}

            def _b64(data: bytes) -> str:
                return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

            h = _b64(json.dumps(header, separators=(",", ":")).encode())
            p = _b64(json.dumps(claims, separators=(",", ":"), default=str).encode())
            sig_input = f"{h}.{p}".encode()
            sig = hmac.new(key.encode(), sig_input, hashlib.sha256).digest()
            return f"{h}.{p}.{_b64(sig)}"

        @staticmethod
        def decode(token: str, key: str, algorithms=None) -> dict:
            parts = token.split(".")
            if len(parts) != 3:
                raise _JWTError("Invalid token structure")

            def _dec(s: str) -> bytes:
                # Restore padding
                s += "=" * (-len(s) % 4)
                return base64.urlsafe_b64decode(s)

            header_raw, payload_raw, sig_raw = parts
            sig_input = f"{header_raw}.{payload_raw}".encode()
            expected_sig = hmac.new(
                key.encode(), sig_input, hashlib.sha256
            ).digest()

            if not hmac.compare_digest(expected_sig, _dec(sig_raw)):
                raise _JWTError("Signature verification failed")

            payload = json.loads(_dec(payload_raw))

            # Check expiry
            exp = payload.get("exp")
            if exp is not None:
                if isinstance(exp, str):
                    # May be ISO string from str(datetime)
                    raise _JWTError("Expired token (cannot parse exp)")
                if exp < time.time():
                    raise _JWTError("Token has expired")

            return payload

    jose_stub = ModuleType("jose")
    jose_stub.jwt = _JWT()
    jose_stub.JWTError = _JWTError

    jwt_stub = ModuleType("jose.jwt")
    jwt_stub.encode = _JWT.encode
    jwt_stub.decode = _JWT.decode
    return jose_stub, jwt_stub, _JWTError


def _bootstrap_admin_module():
    """Load api.routes.admin with all external deps stubbed."""
    jose_stub, jwt_mod_stub, JWTError = _make_jose_stub()

    sys.modules["jose"] = jose_stub
    sys.modules["jose.jwt"] = jwt_mod_stub

    # passlib stubs
    bcrypt_stub = MagicMock()
    bcrypt_stub.verify = MagicMock(return_value=False)
    bcrypt_stub.hash = MagicMock(return_value="hashed")
    passlib_stub = ModuleType("passlib")
    passlib_hash_stub = ModuleType("passlib.hash")
    passlib_hash_stub.bcrypt = bcrypt_stub
    passlib_context_stub = ModuleType("passlib.context")
    passlib_context_stub.CryptContext = MagicMock()
    sys.modules["passlib"] = passlib_stub
    sys.modules["passlib.hash"] = passlib_hash_stub
    sys.modules["passlib.context"] = passlib_context_stub

    # Minimal stubs for heavy shared / service modules
    for mod_name in [
        "shared.chatwoot_client",
        "shared.chatwoot_sync",
        "shared.image_security",
        "api.services",
        "api.services.conversation_reset_coordinator",
        "api.services.garbage_collection_service",
        "api.services.conversation_reset_db_executor",
        "api.services.conversation_reset_redis_executor",
        "api.services.conversation_reset_files_executor",
        "api.services.conversation_reset_chatwoot_executor",
    ]:
        if mod_name not in sys.modules:
            stub = ModuleType(mod_name)
            stub.ChatwootClient = MagicMock()
            stub.get_redis_client = MagicMock()
            stub.sync_agent_to_chatwoot = AsyncMock(return_value=None)
            stub.resync_agent_to_chatwoot = AsyncMock(return_value=None)
            stub.ConversationResetCoordinator = MagicMock()
            stub.ResetExecutionContext = MagicMock()
            stub.GCResult = MagicMock()
            stub.run_gc = AsyncMock()
            stub.ConversationResetDatabaseExecutor = MagicMock()
            stub.ConversationResetRedisExecutor = MagicMock()
            stub.ConversationResetFilesExecutor = MagicMock()
            stub.ConversationResetChatwootExecutor = MagicMock()
            sys.modules[mod_name] = stub

    # Load api.models.admin_user (real Pydantic models — no heavy deps)
    import importlib.util
    if "api.models.admin_user" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.models.admin_user",
            "/home/pepe/Proyectos/msi-a/api/models/admin_user.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["api.models.admin_user"] = mod
        spec.loader.exec_module(mod)

    # Now load admin.py
    spec = importlib.util.spec_from_file_location(
        "api.routes.admin",
        "/home/pepe/Proyectos/msi-a/api/routes/admin.py",
    )
    admin_mod = importlib.util.module_from_spec(spec)
    sys.modules["api.routes.admin"] = admin_mod
    spec.loader.exec_module(admin_mod)

    # Attach the real JWTError to the module so its except clause works
    admin_mod.JWTError = JWTError
    return admin_mod


admin_module = _bootstrap_admin_module()

# ---------------------------------------------------------------------------
# JWT helpers — create tokens via admin_module.create_access_token
# (same code path as the real login handler)
# ---------------------------------------------------------------------------

_SECRET = "test-secret-key-for-admin-jwt-tests-only"
_ALGORITHM = "HS256"


def _patch_settings(secret: str = _SECRET):
    """Context manager that patches get_settings to return a known JWT secret."""
    settings_mock = MagicMock()
    settings_mock.ADMIN_JWT_SECRET = secret
    settings_mock.ENVIRONMENT = "test"
    return patch.object(admin_module, "get_settings", return_value=settings_mock)


def _make_valid_token(
    *,
    username: str = "testadmin",
    user_id: str | None = None,
    role: str = "admin",
    jti: str | None = None,
    secret: str = _SECRET,
) -> str:
    """Create a well-formed, non-expired JWT signed with the test secret."""
    import time
    user_id = user_id or str(uuid.uuid4())
    jti = jti or str(uuid.uuid4())
    claims = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "type": "admin",
        "jti": jti,
        "exp": int(time.time()) + 86400,  # 24 hours from now
        "iat": int(time.time()),
    }
    return admin_module.jwt.encode(claims, secret, algorithm=_ALGORITHM)


def _make_expired_token(
    *,
    username: str = "testadmin",
    user_id: str | None = None,
    jti: str | None = None,
    secret: str = _SECRET,
) -> str:
    """Create an expired JWT (exp in the past)."""
    import time
    user_id = user_id or str(uuid.uuid4())
    jti = jti or str(uuid.uuid4())
    claims = {
        "sub": username,
        "user_id": user_id,
        "role": "admin",
        "type": "admin",
        "jti": jti,
        "exp": int(time.time()) - 3600,  # 1 hour ago
        "iat": int(time.time()) - 7200,
    }
    return admin_module.jwt.encode(claims, secret, algorithm=_ALGORITHM)


# ---------------------------------------------------------------------------
# Minimal FastAPI app for testing get_current_user
# ---------------------------------------------------------------------------

def _make_test_app(admin_user_mock: MagicMock, redis_mock: MagicMock):
    """Build a minimal FastAPI app wiring get_current_user → /admin/me."""
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, Depends, Request

    app = FastAPI()

    @app.get("/admin/me")
    async def get_me(
        request: Request,
        current_user=Depends(admin_module.get_current_user),
    ):
        return {
            "username": current_user.username,
            "role": current_user.role,
        }

    return app


# ---------------------------------------------------------------------------
# Shared DB + Redis mock helpers
# ---------------------------------------------------------------------------

def _make_db_mock(admin_user: MagicMock):
    """Return a get_async_session context manager that yields a session
    whose execute() returns the given admin_user."""
    from contextlib import asynccontextmanager

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=admin_user)
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


def _make_admin_user(username: str = "testadmin", role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.username = username
    user.role = role
    user.is_active = True
    user.id = uuid.uuid4()
    return user


def _make_redis_mock(blacklisted_jtis: set[str] | None = None):
    """Return a mock Redis client where blacklisted JTIs return a truthy value."""
    blacklisted = blacklisted_jtis or set()
    redis_mock = MagicMock()

    async def _get(key: str):
        jti = key.removeprefix("token_blacklist:")
        return b"1" if jti in blacklisted else None

    redis_mock.get = _get
    return redis_mock


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    return asyncio.run(coro)


async def _call_get_current_user(
    *,
    bearer_token: str | None = None,
    cookie_token: str | None = None,
    admin_user: MagicMock | None = None,
    blacklisted_jtis: set[str] | None = None,
):
    """Call get_current_user directly with the right patches in place.

    Simulates what FastAPI would inject: an HTTPAuthorizationCredentials from
    the bearer header (or None) plus Request.cookies for the cookie.
    """
    from fastapi import Request
    from fastapi.security import HTTPAuthorizationCredentials

    user = admin_user or _make_admin_user()
    redis_mock = _make_redis_mock(blacklisted_jtis)
    db_ctx = _make_db_mock(user)

    # Build a minimal Request-like object with cookies
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/me",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)
    if cookie_token:
        # Inject cookie into request scope headers (Starlette reads from here)
        cookie_header = f"admin_token={cookie_token}".encode()
        scope["headers"] = [(b"cookie", cookie_header)]
        request = Request(scope)

    # Build credentials object (Bearer)
    credentials = None
    if bearer_token:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=bearer_token
        )

    with _patch_settings():
        with patch.object(admin_module, "get_redis_client", return_value=redis_mock):
            with patch.object(admin_module, "get_async_session", db_ctx):
                return await admin_module.get_current_user(
                    credentials=credentials,
                    request=request,
                )


# ===========================================================================
# A2 — cookie-only → 200
# ===========================================================================

class TestCookieOnlyAuth:
    """A2: Valid admin_token cookie, no Authorization header → authenticated."""

    def test_cookie_only_returns_user(self):
        """get_current_user with a valid cookie and no bearer must return the user."""
        token = _make_valid_token(username="cookieadmin")
        user = _make_admin_user(username="cookieadmin")

        result = _run_async(
            _call_get_current_user(cookie_token=token, admin_user=user)
        )

        assert result.username == "cookieadmin"


# ===========================================================================
# A3 — bearer-only → 200 (backward-compat regression)
# ===========================================================================

class TestBearerOnlyAuth:
    """A3: Valid Bearer token, no cookie → still returns 200."""

    def test_bearer_only_returns_user(self):
        """Bearer-only path must continue to work after cookie fallback is added."""
        token = _make_valid_token(username="beareradmin")
        user = _make_admin_user(username="beareradmin")

        result = _run_async(
            _call_get_current_user(bearer_token=token, admin_user=user)
        )

        assert result.username == "beareradmin"


# ===========================================================================
# A4 — both present → bearer JTI wins
# ===========================================================================

class TestBearerWinsWhenBothPresent:
    """A4: When both cookie and bearer are present, bearer takes precedence."""

    def test_bearer_jti_used_not_cookie_jti(self):
        """Bearer JTI must be extracted, not the cookie JTI.

        We blacklist the cookie JTI so that if bearer wins, the call succeeds
        (the cookie JTI is not checked). If the implementation incorrectly uses
        the cookie, the blacklist check will fire and raise 401.
        """
        cookie_jti = str(uuid.uuid4())
        bearer_jti = str(uuid.uuid4())

        cookie_token = _make_valid_token(jti=cookie_jti)
        bearer_token = _make_valid_token(jti=bearer_jti)
        user = _make_admin_user()

        # Blacklist only the cookie JTI — if bearer wins, call succeeds
        result = _run_async(
            _call_get_current_user(
                bearer_token=bearer_token,
                cookie_token=cookie_token,
                admin_user=user,
                blacklisted_jtis={cookie_jti},
            )
        )

        assert result.is_active is True


# ===========================================================================
# A5 — expired cookie → 401
# ===========================================================================

class TestExpiredCookie:
    """A5: Expired cookie (no bearer) → 401."""

    def test_expired_cookie_raises_401(self):
        """An expired JWT in the cookie must result in 401, not 200."""
        from fastapi import HTTPException

        expired_token = _make_expired_token()
        user = _make_admin_user()

        with pytest.raises(HTTPException) as exc_info:
            _run_async(
                _call_get_current_user(
                    cookie_token=expired_token,
                    admin_user=user,
                )
            )

        assert exc_info.value.status_code == 401


# ===========================================================================
# A6 — no credentials → 401
# ===========================================================================

class TestNoCredentials:
    """A6: Neither bearer nor cookie → 401."""

    def test_no_credentials_raises_401(self):
        """Absent both Authorization header and cookie must return 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _run_async(
                _call_get_current_user()
            )

        assert exc_info.value.status_code == 401
