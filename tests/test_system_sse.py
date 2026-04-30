"""
TDD tests for secure-admin-auth Phase B Batch B-β — SSE no-cookie → 401.

Task B7: Verify that the SSE log endpoint returns 401 when no Bearer token
is supplied. This replaces the old ?token= query-param auth with standard
Bearer header auth (forwarded by the Next.js proxy route from the cookie).

Strategy:
  Load api.routes.system with heavy deps (Docker API, httpx) stubbed so the
  auth guard is reached before any real I/O occurs.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Bootstrap — load api.routes.system without Docker / heavy deps
# ---------------------------------------------------------------------------

def _bootstrap_system_module():
    """Load api.routes.system with external deps stubbed."""
    import importlib.util

    # Re-use the jose stub and admin module bootstrap from test_admin_auth
    # if already loaded; otherwise set up minimal stubs.

    # Ensure jose is stubbed (may already be done by test_admin_auth)
    if "jose" not in sys.modules:
        import base64
        import hashlib
        import hmac as _hmac
        import json
        import time

        class _JWTError(Exception):
            pass

        class _JWT:
            @staticmethod
            def encode(claims: dict, key: str, algorithm: str = "HS256") -> str:
                header = {"alg": algorithm, "typ": "JWT"}

                def _b64(data: bytes) -> str:
                    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

                h = _b64(json.dumps(header, separators=(",", ":")).encode())
                p = _b64(json.dumps(claims, separators=(",", ":"), default=str).encode())
                sig_input = f"{h}.{p}".encode()
                sig = _hmac.new(key.encode(), sig_input, hashlib.sha256).digest()
                return f"{h}.{p}.{_b64(sig)}"

            @staticmethod
            def decode(token: str, key: str, algorithms=None) -> dict:
                parts = token.split(".")
                if len(parts) != 3:
                    raise _JWTError("Invalid token structure")

                def _dec(s: str) -> bytes:
                    s += "=" * (-len(s) % 4)
                    return base64.urlsafe_b64decode(s)

                header_raw, payload_raw, sig_raw = parts
                sig_input = f"{header_raw}.{payload_raw}".encode()
                expected_sig = _hmac.new(
                    key.encode(), sig_input, hashlib.sha256
                ).digest()

                if not _hmac.compare_digest(expected_sig, _dec(sig_raw)):
                    raise _JWTError("Signature verification failed")

                payload = json.loads(_dec(payload_raw))
                exp = payload.get("exp")
                if exp is not None:
                    if isinstance(exp, str):
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
        sys.modules["jose"] = jose_stub
        sys.modules["jose.jwt"] = jwt_stub

    # Passlib stubs
    if "passlib" not in sys.modules:
        bcrypt_stub = MagicMock()
        passlib_stub = ModuleType("passlib")
        passlib_hash_stub = ModuleType("passlib.hash")
        passlib_hash_stub.bcrypt = bcrypt_stub
        passlib_context_stub = ModuleType("passlib.context")
        passlib_context_stub.CryptContext = MagicMock()
        sys.modules["passlib"] = passlib_stub
        sys.modules["passlib.hash"] = passlib_hash_stub
        sys.modules["passlib.context"] = passlib_context_stub

    # Shared / service stubs
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

    # Load api.models.admin_user
    if "api.models.admin_user" not in sys.modules:
        import importlib.util as ilu
        spec = ilu.spec_from_file_location(
            "api.models.admin_user",
            "/home/pepe/Proyectos/msi-a/api/models/admin_user.py",
        )
        mod = ilu.module_from_spec(spec)
        sys.modules["api.models.admin_user"] = mod
        spec.loader.exec_module(mod)

    # Load api.routes.admin (required by system.py)
    if "api.routes.admin" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "api.routes.admin",
            "/home/pepe/Proyectos/msi-a/api/routes/admin.py",
        )
        admin_mod = importlib.util.module_from_spec(spec)
        sys.modules["api.routes.admin"] = admin_mod
        spec.loader.exec_module(admin_mod)
        jose_stub = sys.modules["jose"]
        admin_mod.JWTError = jose_stub.JWTError

    # Load api.routes.system
    spec = importlib.util.spec_from_file_location(
        "api.routes.system",
        "/home/pepe/Proyectos/msi-a/api/routes/system.py",
    )
    system_mod = importlib.util.module_from_spec(spec)
    sys.modules["api.routes.system"] = system_mod
    spec.loader.exec_module(system_mod)
    return system_mod


system_module = _bootstrap_system_module()


# ---------------------------------------------------------------------------
# Minimal FastAPI test app
# ---------------------------------------------------------------------------

def _make_system_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(system_module.router)
    return app


# ---------------------------------------------------------------------------
# B7: SSE endpoint — no Bearer → 401
# ---------------------------------------------------------------------------

class TestSSENoBearerReturns401:
    """B7: GET /api/admin/system/{service}/logs without Authorization → 401.

    After the migration from ?token= to Bearer header auth, the SSE endpoint
    must reject unauthenticated requests with HTTP 401.
    """

    def test_no_auth_header_returns_401(self):
        """Unauthenticated request to SSE endpoint returns 401."""
        import asyncio
        from httpx import AsyncClient, ASGITransport

        app = _make_system_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/admin/system/agent/logs",
                    headers={"Accept": "text/event-stream"},
                )
            return response

        response = asyncio.run(_run())
        assert response.status_code == 401

    def test_invalid_bearer_returns_401(self):
        """Invalid (non-JWT) Bearer token → 401."""
        import asyncio
        from httpx import AsyncClient, ASGITransport

        app = _make_system_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/admin/system/agent/logs",
                    headers={
                        "Accept": "text/event-stream",
                        "Authorization": "Bearer not-a-valid-jwt",
                    },
                )
            return response

        response = asyncio.run(_run())
        assert response.status_code == 401
