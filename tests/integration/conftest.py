"""
Conftest for integration tests.

Applies SQLite type compatibility patches so that PostgreSQL-specific column
types (JSONB, UUID) render correctly in aiosqlite in-memory databases used
for isolated integration tests.

This file is automatically loaded by pytest for all tests in this directory.
"""

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
