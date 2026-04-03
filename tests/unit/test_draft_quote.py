"""
Unit tests for DraftQuote DB persistence — T3.2 (RED phase).

Tests validate:
1. test_draft_quote_model_has_required_columns — modelo tiene todas las columnas requeridas
2. test_unique_active_draft_per_conversation — upsert desactiva el anterior antes de insertar
3. test_draft_quote_write_is_fire_and_forget — error en DB no propaga excepción
4. test_draft_quote_loaded_on_presupuesto_resume — DraftQuote activo se inyecta en mode_context
5. test_draft_quote_deactivated_on_mode_exit — al salir de PRESUPUESTO_MODE, is_active=False
6. test_no_draft_quote_no_error — sin DraftQuote activo, arranque sin error

All tests use SQLite in-memory + pure mocks — no real PostgreSQL, no Redis.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select


# ---------------------------------------------------------------------------
# SQLite in-memory session fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_session():
    """Provide an in-memory SQLite session with all tables created."""
    from database.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with SessionLocal() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test 1 — DraftQuote model has all required columns
# ---------------------------------------------------------------------------


def test_draft_quote_model_has_required_columns():
    """
    The DraftQuote model must have: id, conversation_id, category_slug,
    elements, precio_final, is_active, calculated_at columns.
    """
    from database.models import DraftQuote
    from sqlalchemy import inspect as sa_inspect

    # Check that the model exists and has the expected columns
    mapper = DraftQuote.__mapper__
    column_names = {col.key for col in mapper.columns}

    required_columns = {
        "id",
        "conversation_id",
        "category_slug",
        "elements",
        "precio_final",
        "is_active",
        "calculated_at",
        "created_at",
    }

    missing = required_columns - column_names
    assert not missing, (
        f"DraftQuote is missing required columns: {missing}. "
        f"Available columns: {column_names}"
    )


# ---------------------------------------------------------------------------
# Test 2 — unique active draft per conversation (upsert deactivates old one)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unique_active_draft_per_conversation(async_session):
    """
    When _upsert_draft_quote is called twice for the same conversation,
    the first DraftQuote must be deactivated (is_active=False) before
    the second one is inserted with is_active=True.

    At most ONE is_active=True row per conversation.
    """
    from database.models import DraftQuote
    from agent.tools.draft_quote_service import _upsert_draft_quote

    # We need a valid conversation_id. Since FK constraints are relaxed in SQLite,
    # we can use a fake UUID.
    conv_id = str(uuid.uuid4())

    # First upsert
    await _upsert_draft_quote(
        session=async_session,
        conversation_id=conv_id,
        category_slug="motos-part",
        elements=["ESCAPE"],
        tier_id=None,
        precio_final=Decimal("140.00"),
    )
    await async_session.commit()

    # Second upsert — should deactivate the first
    await _upsert_draft_quote(
        session=async_session,
        conversation_id=conv_id,
        category_slug="motos-part",
        elements=["ESCAPE", "MANILLAR"],
        tier_id=None,
        precio_final=Decimal("250.00"),
    )
    await async_session.commit()

    # Query all drafts for this conversation
    result = await async_session.execute(
        select(DraftQuote).where(DraftQuote.conversation_id == uuid.UUID(conv_id))
    )
    drafts = result.scalars().all()

    # Should have 2 drafts total
    assert len(drafts) == 2, f"Expected 2 drafts, got {len(drafts)}"

    # Only one should be active
    active_drafts = [d for d in drafts if d.is_active]
    inactive_drafts = [d for d in drafts if not d.is_active]

    assert len(active_drafts) == 1, f"Expected 1 active draft, got {len(active_drafts)}"
    assert len(inactive_drafts) == 1, (
        f"Expected 1 inactive draft, got {len(inactive_drafts)}"
    )

    # The active draft should be the second one (latest price)
    active = active_drafts[0]
    assert active.precio_final == Decimal("250.00")
    assert active.elements == ["ESCAPE", "MANILLAR"]


# ---------------------------------------------------------------------------
# Test 3 — DraftQuote write is fire-and-forget (DB error doesn't propagate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_quote_write_is_fire_and_forget():
    """
    When the DB write for DraftQuote fails, the error must NOT surface
    as a tool error. The tool should return success=True regardless.
    """
    from agent.tools.element_tools import _fire_and_forget_draft_quote

    # Mock the service-level upsert to raise (this is what _fire_and_forget calls)
    with patch(
        "agent.tools.draft_quote_service._upsert_draft_quote",
        side_effect=RuntimeError("DB connection lost"),
    ):
        # Mock get_async_session so we don't need a real DB
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "agent.tools.element_tools.get_async_session"
            if False
            else "database.connection.get_async_session",
            return_value=mock_session,
        ):
            # The fire-and-forget wrapper should catch the exception silently
            # We call it directly — it catches the error internally
            await _fire_and_forget_draft_quote(
                conversation_id="conv-test-ff",
                category_slug="motos-part",
                elements=["ESCAPE"],
                tier_id=None,
                precio_final=Decimal("140.00"),
            )
            # If we get here, the exception was caught correctly (no re-raise)


# ---------------------------------------------------------------------------
# Test 4 — DraftQuote loaded on presupuesto resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_quote_loaded_on_presupuesto_resume():
    """
    When presupuesto_mode starts with an existing active DraftQuote,
    it should inject draft_precio, draft_elements, draft_category
    into mode_context before the LLM call.
    """
    from agent.modes.presupuesto_mode import _load_active_draft_quote_into_context

    # Mock DraftQuote returned from DB
    mock_draft = MagicMock()
    mock_draft.precio_final = Decimal("410.00")
    mock_draft.elements = ["ESCAPE", "MANILLAR"]
    mock_draft.category_slug = "motos-part"

    async def mock_load_draft(conversation_id: str):
        return mock_draft

    mode_context = {}

    with patch(
        "agent.modes.presupuesto_mode._load_active_draft_quote",
        side_effect=mock_load_draft,
    ):
        await _load_active_draft_quote_into_context(
            conversation_id="conv-resume-test",
            mode_context=mode_context,
        )

    # mode_context should have been updated with draft data
    assert "draft_precio" in mode_context, (
        "mode_context should contain draft_precio after loading DraftQuote"
    )
    assert mode_context["draft_precio"] == "410.00"
    assert mode_context["draft_elements"] == ["ESCAPE", "MANILLAR"]
    assert mode_context["draft_category"] == "motos-part"


# ---------------------------------------------------------------------------
# Test 5 — DraftQuote deactivated on mode exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_quote_deactivated_on_mode_exit(async_session):
    """
    When the agent transitions OUT of PRESUPUESTO_MODE,
    any is_active=True DraftQuote must be set to is_active=False.
    """
    from database.models import DraftQuote
    from agent.tools.draft_quote_service import (
        _upsert_draft_quote,
        _deactivate_draft_quote,
    )

    conv_id = str(uuid.uuid4())

    # Create an active draft
    await _upsert_draft_quote(
        session=async_session,
        conversation_id=conv_id,
        category_slug="motos-part",
        elements=["ESCAPE"],
        tier_id=None,
        precio_final=Decimal("140.00"),
    )
    await async_session.commit()

    # Verify it's active
    result = await async_session.execute(
        select(DraftQuote).where(
            DraftQuote.conversation_id == uuid.UUID(conv_id),
            DraftQuote.is_active == True,
        )
    )
    assert result.scalar_one_or_none() is not None, "Should have an active draft"

    # Now deactivate (mode exit)
    await _deactivate_draft_quote(
        session=async_session,
        conversation_id=conv_id,
    )
    await async_session.commit()

    # Verify no active drafts remain
    result2 = await async_session.execute(
        select(DraftQuote).where(
            DraftQuote.conversation_id == uuid.UUID(conv_id),
            DraftQuote.is_active == True,
        )
    )
    active = result2.scalar_one_or_none()
    assert active is None, "After mode exit, no active DraftQuote should remain"


# ---------------------------------------------------------------------------
# Test 6 — No DraftQuote active → presupuesto starts clean, no error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_draft_quote_no_error():
    """
    When no DraftQuote exists for a conversation, presupuesto_mode
    should start cleanly without raising any error and mode_context
    should NOT have draft_* keys injected.
    """
    from agent.modes.presupuesto_mode import _load_active_draft_quote_into_context

    async def mock_load_draft_none(conversation_id: str):
        return None  # No draft found

    mode_context = {}

    with patch(
        "agent.modes.presupuesto_mode._load_active_draft_quote",
        side_effect=mock_load_draft_none,
    ):
        # Should NOT raise
        await _load_active_draft_quote_into_context(
            conversation_id="conv-no-draft",
            mode_context=mode_context,
        )

    # mode_context should NOT have draft keys injected
    assert "draft_precio" not in mode_context, (
        "No draft_precio should be injected when no DraftQuote exists"
    )
    assert "draft_elements" not in mode_context
    assert "draft_category" not in mode_context
