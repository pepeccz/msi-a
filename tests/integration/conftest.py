"""
Conftest for integration tests.

Applies SQLite type compatibility patches so that PostgreSQL-specific column
types (JSONB, UUID) render correctly in aiosqlite in-memory databases used
for isolated integration tests.

Also stubs optional dependencies not installed in the local test environment
(structlog, phonenumbers, langgraph.checkpoint.redis).

This file is automatically loaded by pytest for all tests in this directory.
"""

import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub optional deps before any test import
# ---------------------------------------------------------------------------


def _install_stub(name: str) -> None:
    if name not in sys.modules:
        stub = MagicMock()
        stub.__name__ = name
        sys.modules[name] = stub


_install_stub("phonenumbers")
_install_stub("phonenumbers.phonenumberutil")

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

for _mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _mod not in sys.modules:
        _stub = types.ModuleType(_mod)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_mod] = _stub

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler


def _visit_JSONB(self, type_, **kw) -> str:  # noqa: N802
    """Render JSONB as JSON for SQLite compatibility."""
    return "JSON"


def _visit_UUID(self, type_, **kw) -> str:  # noqa: N802
    """Render PostgreSQL UUID type as VARCHAR(36) for SQLite compatibility."""
    return "VARCHAR(36)"


# Apply patches once at import time (idempotent)
if not hasattr(SQLiteTypeCompiler, "_msia_patched"):
    SQLiteTypeCompiler.visit_JSONB = _visit_JSONB  # type: ignore[attr-defined]
    SQLiteTypeCompiler.visit_UUID = _visit_UUID  # type: ignore[attr-defined]
    SQLiteTypeCompiler._msia_patched = True  # type: ignore[attr-defined]
