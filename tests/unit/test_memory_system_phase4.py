"""
Tests for Phase 4 of memory system refactor (refactor-memory-system).

Covers WS4: Garbage Collection service.

- run_gc with dry_run=True: no records deleted, correct counts returned
- run_gc with dry_run=False: records deleted
- Retention boundary: 89-day-old record NOT deleted, 91-day-old record IS deleted
- Empty DB: returns zero counts without error

Uses an in-memory SQLite database (aiosqlite) via SQLAlchemy async.
The tests/unit/conftest.py already patches SQLiteTypeCompiler to render
PostgreSQL-specific types (JSONB, UUID) as SQLite-compatible equivalents.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base, ConversationHistory, ConversationMessage


# ---------------------------------------------------------------------------
# In-memory DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_engine_sqlite():
    """
    Ephemeral in-memory SQLite engine for a single test.

    The conftest.py in this directory already patches SQLiteTypeCompiler so
    that JSONB → JSON and UUID → VARCHAR(36), making the full ORM schema
    usable with aiosqlite.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine_sqlite) -> AsyncSession:
    """Provide a fresh session bound to the in-memory engine."""
    factory = async_sessionmaker(
        db_engine_sqlite,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conversation(days_ago: int) -> ConversationHistory:
    """Build an unsaved ConversationHistory whose started_at is *days_ago* days in the past."""
    started = datetime.now(UTC) - timedelta(days=days_ago)
    return ConversationHistory(
        id=uuid.uuid4(),
        conversation_id=f"conv-{uuid.uuid4().hex[:8]}",
        started_at=started,
    )


def _make_message(conv: ConversationHistory, n: int = 1) -> list[ConversationMessage]:
    """Build *n* unsaved ConversationMessage records linked to *conv*."""
    return [
        ConversationMessage(
            id=uuid.uuid4(),
            conversation_history_id=conv.id,
            role="user",
            content=f"message {i}",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunGCDryRun:
    """run_gc with dry_run=True: counts are correct, nothing is deleted."""

    @pytest.mark.asyncio
    async def test_dry_run_returns_correct_counts(self, db_session: AsyncSession) -> None:
        # Two old conversations (>90 days), each with 2 messages
        old1 = _make_conversation(days_ago=100)
        old2 = _make_conversation(days_ago=95)
        msgs1 = _make_message(old1, n=2)
        msgs2 = _make_message(old2, n=2)

        db_session.add_all([old1, old2, *msgs1, *msgs2])
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=True)

        assert result.dry_run is True
        assert result.conversations_deleted == 2
        assert result.messages_deleted == 4

    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete_records(self, db_session: AsyncSession) -> None:
        old = _make_conversation(days_ago=100)
        db_session.add(old)
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc
        from sqlalchemy import select

        await run_gc(db_session, retention_days=90, dry_run=True)

        # Record must still exist
        still_there = await db_session.scalar(
            select(ConversationHistory).where(ConversationHistory.id == old.id)
        )
        assert still_there is not None

    @pytest.mark.asyncio
    async def test_dry_run_duration_is_positive(self, db_session: AsyncSession) -> None:
        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=True)
        assert result.duration_seconds >= 0.0


class TestRunGCDelete:
    """run_gc with dry_run=False: records are actually deleted."""

    @pytest.mark.asyncio
    async def test_deletes_old_conversations(self, db_session: AsyncSession) -> None:
        old = _make_conversation(days_ago=100)
        msgs = _make_message(old, n=3)
        db_session.add_all([old, *msgs])
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc
        from sqlalchemy import select

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.dry_run is False
        assert result.conversations_deleted == 1
        assert result.messages_deleted == 3

        # Verify records gone
        gone = await db_session.scalar(
            select(ConversationHistory).where(ConversationHistory.id == old.id)
        )
        assert gone is None

    @pytest.mark.asyncio
    async def test_cascade_deletes_messages(self, db_session: AsyncSession) -> None:
        """
        run_gc reports the correct message count it would cascade-delete.

        Note: SQLite does NOT enforce FK CASCADE by default, so we verify via
        the GCResult rather than querying the DB after deletion (which would
        succeed only on PostgreSQL).
        """
        old = _make_conversation(days_ago=120)
        msgs = _make_message(old, n=5)
        db_session.add_all([old, *msgs])
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        # GC reports it found 5 messages to cascade-delete
        assert result.messages_deleted == 5

    @pytest.mark.asyncio
    async def test_preserves_recent_conversations(self, db_session: AsyncSession) -> None:
        recent = _make_conversation(days_ago=10)
        old = _make_conversation(days_ago=100)
        db_session.add_all([recent, old])
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc
        from sqlalchemy import select

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.conversations_deleted == 1

        still_there = await db_session.scalar(
            select(ConversationHistory).where(ConversationHistory.id == recent.id)
        )
        assert still_there is not None


class TestRetentionBoundary:
    """Retention boundary tests: 89-day record survives, 91-day record is deleted."""

    @pytest.mark.asyncio
    async def test_89_days_old_not_deleted(self, db_session: AsyncSession) -> None:
        conv = _make_conversation(days_ago=89)
        db_session.add(conv)
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.conversations_deleted == 0

    @pytest.mark.asyncio
    async def test_91_days_old_is_deleted(self, db_session: AsyncSession) -> None:
        conv = _make_conversation(days_ago=91)
        db_session.add(conv)
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.conversations_deleted == 1

    @pytest.mark.asyncio
    async def test_one_second_before_cutoff_not_deleted(self, db_session: AsyncSession) -> None:
        """A record whose started_at is 1 second BEFORE the cutoff boundary is NOT deleted."""
        # cutoff = now - 90d.  We set started_at = cutoff + 1s, which is strictly
        # newer than the cutoff, so started_at < cutoff is False → NOT deleted.
        cutoff = datetime.now(UTC) - timedelta(days=90)
        conv = ConversationHistory(
            id=uuid.uuid4(),
            conversation_id=f"conv-boundary-{uuid.uuid4().hex[:8]}",
            started_at=cutoff + timedelta(seconds=1),
        )
        db_session.add(conv)
        await db_session.commit()

        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.conversations_deleted == 0


class TestEmptyDB:
    """Empty DB: run_gc returns zeros without error."""

    @pytest.mark.asyncio
    async def test_empty_db_returns_zeros(self, db_session: AsyncSession) -> None:
        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=False)

        assert result.conversations_deleted == 0
        assert result.messages_deleted == 0
        assert result.images_deleted == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_empty_db_dry_run_returns_zeros(self, db_session: AsyncSession) -> None:
        from api.services.garbage_collection_service import run_gc

        result = await run_gc(db_session, retention_days=90, dry_run=True)

        assert result.conversations_deleted == 0
        assert result.messages_deleted == 0
        assert result.dry_run is True
        assert result.errors == []
