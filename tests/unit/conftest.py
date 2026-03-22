"""
conftest.py for tests/unit/

Pre-patches missing optional dependencies that are not installed in the
test environment (e.g. phonenumbers, which is only used at runtime in
api/models/chatwoot_webhook.py). This prevents ImportError during
pytest collection of tests that import from agent.main or api.services.
"""

import sys
import types
from unittest.mock import MagicMock


def _install_stub(name: str) -> None:
    """Install a MagicMock stub for *name* if not already installed."""
    if name not in sys.modules:
        stub = MagicMock()
        stub.__name__ = name
        sys.modules[name] = stub


# Stub out phonenumbers — not installed in test env
_install_stub("phonenumbers")
_install_stub("phonenumbers.phonenumberutil")

# ---------------------------------------------------------------------------
# Stub structlog — not installed in local test env.
# Must happen BEFORE any test file imports from agent.* because
# agent/__init__.py → agent.graph.conversation_graph → import structlog.
# ---------------------------------------------------------------------------
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

# Stub langgraph.checkpoint.redis — not installed locally.
# agent/state/__init__.py → checkpointer.py → langgraph.checkpoint.redis.aio
for _redis_mod_name in (
    "langgraph.checkpoint.redis",
    "langgraph.checkpoint.redis.aio",
):
    if _redis_mod_name not in sys.modules:
        _redis_stub = types.ModuleType(_redis_mod_name)
        _redis_stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod_name] = _redis_stub


# ─────────────────────────────────────────────────────────────────────────────
# SQLite type compatibility for PostgreSQL-specific types (JSONB, UUID)
# ─────────────────────────────────────────────────────────────────────────────
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402


def _visit_JSONB(self, type_, **kw) -> str:  # noqa: N802
    """Render JSONB as JSON for SQLite compatibility."""
    return "JSON"


def _visit_UUID(self, type_, **kw) -> str:  # noqa: N802
    """Render PostgreSQL UUID type as VARCHAR(36) for SQLite compatibility."""
    return "VARCHAR(36)"


if not hasattr(SQLiteTypeCompiler, "_msia_patched"):
    SQLiteTypeCompiler.visit_JSONB = _visit_JSONB  # type: ignore[attr-defined]
    SQLiteTypeCompiler.visit_UUID = _visit_UUID  # type: ignore[attr-defined]
    SQLiteTypeCompiler._msia_patched = True  # type: ignore[attr-defined]
