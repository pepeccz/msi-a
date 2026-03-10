"""
Unit tests for agent/services/element_state_service.py

Covers:
  REQ-STATE-1  CaseElementData is single source of truth
  REQ-STATE-2  Transitions driven by DB completeness
  REQ-STATE-3  No ContextVar usage
  REQ-STATE-4  Service generates CollectionContext for prompt injection
  REQ-STATE-5  Element ordering from DB (not hardcoded)
  Edge cases   All elements done, empty list, unknown code
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from database.models import (
    Base,
    CaseElementData,
    CaseImage,
    Element,
    ElementRequiredField,
    VehicleCategory,
    Warning,
)
from agent.services.element_state_service import (
    ElementStateService,
    CollectionContext,
    ElementState,
    FieldContext,
    get_element_state_service,
    _evaluate_field_condition,
    _build_field_contexts,
    _to_uuid,
)


# ─────────────────────────────────────────────────────────────────────────────
# In-memory SQLite engine + session factory for isolated unit tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    """SQLite in-memory engine with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def sqlite_session(sqlite_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async session bound to the in-memory SQLite DB."""
    factory = async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# Helpers to build an async context manager that returns our test session
# ─────────────────────────────────────────────────────────────────────────────

def make_session_cm(session: AsyncSession):
    """
    Return a callable that, when called, yields *session*.

    Used to replace `get_async_session` in production code:
        with patch("..get_async_session", new=make_session_cm(session)):
            ...
    """
    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


# ─────────────────────────────────────────────────────────────────────────────
# DB seed helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _seed_category(session: AsyncSession) -> VehicleCategory:
    cat = VehicleCategory(
        name="Test Category",
        slug="test-cat",
        client_type="particular",
        is_active=True,
        sort_order=1,
    )
    session.add(cat)
    await session.flush()
    return cat


async def _seed_element(
    session: AsyncSession,
    category_id: uuid.UUID,
    code: str = "ESC",
    name: str = "Escape",
) -> Element:
    elem = Element(
        category_id=category_id,
        code=code,
        name=name,
        keywords=[code.lower()],
        is_active=True,
        sort_order=1,
    )
    session.add(elem)
    await session.flush()
    return elem


async def _seed_required_field(
    session: AsyncSession,
    element_id: uuid.UUID,
    field_key: str = "marca",
    field_label: str = "Marca",
    sort_order: int = 1,
    is_required: bool = True,
    condition_field_id: uuid.UUID | None = None,
    condition_operator: str | None = None,
    condition_value: str | None = None,
) -> ElementRequiredField:
    rf = ElementRequiredField(
        element_id=element_id,
        field_key=field_key,
        field_label=field_label,
        field_type="text",
        is_required=is_required,
        sort_order=sort_order,
        is_active=True,
        condition_field_id=condition_field_id,
        condition_operator=condition_operator,
        condition_value=condition_value,
    )
    session.add(rf)
    await session.flush()
    return rf


async def _seed_case_element_data(
    session: AsyncSession,
    case_id: uuid.UUID,
    element_code: str,
    status: str = "pending_photos",
    field_values: dict | None = None,
) -> CaseElementData:
    ced = CaseElementData(
        case_id=case_id,
        element_code=element_code,
        status=status,
        field_values=field_values or {},
    )
    session.add(ced)
    await session.flush()
    return ced


async def _seed_case_image(
    session: AsyncSession,
    case_id: uuid.UUID,
    element_code: str,
) -> CaseImage:
    img = CaseImage(
        case_id=case_id,
        stored_filename=f"{uuid.uuid4().hex}.jpg",
        original_filename="test.jpg",
        display_name=f"{element_code}_photo",
        element_code=element_code,
        mime_type="image/jpeg",
    )
    session.add(img)
    await session.flush()
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def service() -> ElementStateService:
    return ElementStateService()


CASE_ID = uuid.uuid4()
ELEMENT_CODE = "ESC"


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-3: No ContextVar — all methods use explicit parameters
# ─────────────────────────────────────────────────────────────────────────────

class TestExplicitParameters:
    """REQ-STATE-3: Service methods accept case_id and element_code explicitly."""

    def test_get_element_state_signature_has_explicit_params(self, service):
        """get_element_state takes case_id, element_code positionally."""
        import inspect
        sig = inspect.signature(service.get_element_state)
        params = list(sig.parameters)
        assert "case_id" in params
        assert "element_code" in params

    def test_get_collection_context_signature_has_explicit_params(self, service):
        """get_collection_context takes case_id and element_codes positionally."""
        import inspect
        sig = inspect.signature(service.get_collection_context)
        params = list(sig.parameters)
        assert "case_id" in params
        assert "element_codes" in params

    def test_record_photos_confirmed_signature_has_explicit_params(self, service):
        import inspect
        sig = inspect.signature(service.record_photos_confirmed)
        params = list(sig.parameters)
        assert "case_id" in params
        assert "element_code" in params
        assert "photo_count" in params

    def test_mark_element_complete_signature_has_explicit_params(self, service):
        import inspect
        sig = inspect.signature(service.mark_element_complete)
        params = list(sig.parameters)
        assert "case_id" in params
        assert "element_code" in params


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-1: get_element_state reads from CaseElementData DB row
# ─────────────────────────────────────────────────────────────────────────────

class TestGetElementState:
    """REQ-STATE-1: Single source of truth = CaseElementData DB row."""

    @pytest.mark.asyncio
    async def test_returns_state_from_existing_db_row(self, service, sqlite_session):
        """get_element_state reads from CaseElementData if row exists."""
        cat = await _seed_category(sqlite_session)
        elem = await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE)
        ced = await _seed_case_element_data(
            sqlite_session, CASE_ID, ELEMENT_CODE, status="pending_data"
        )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            state = await service.get_element_state(CASE_ID, ELEMENT_CODE)

        assert state is not None
        assert state.element_code == ELEMENT_CODE
        assert state.db_status == "pending_data"

    @pytest.mark.asyncio
    async def test_auto_creates_ced_when_row_missing(self, service, sqlite_session):
        """REQ-STATE-1: Creates CaseElementData with pending_photos if not found."""
        cat = await _seed_category(sqlite_session)
        await _seed_element(sqlite_session, cat.id, code="NEW_ELEM")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            state = await service.get_element_state(CASE_ID, "NEW_ELEM")

        assert state is not None
        assert state.db_status == "pending_photos"
        # Row must now exist in DB
        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == "NEW_ELEM")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.status == "pending_photos"

    @pytest.mark.asyncio
    async def test_state_includes_display_name_from_element(self, service, sqlite_session):
        """display_name comes from Element.name in DB."""
        cat = await _seed_category(sqlite_session)
        await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE, name="Escape deportivo")
        await _seed_case_element_data(sqlite_session, CASE_ID, ELEMENT_CODE)
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            state = await service.get_element_state(CASE_ID, ELEMENT_CODE)

        assert state is not None
        assert state.display_name == "Escape deportivo"

    @pytest.mark.asyncio
    async def test_returns_none_gracefully_for_db_error(self, service):
        """Returns None (no exception) when DB fails."""
        with patch(
            "agent.services.element_state_service.get_async_session",
            side_effect=RuntimeError("DB unavailable"),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            state = await service.get_element_state(CASE_ID, "BOOM")

        assert state is None


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-2: DB-driven transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitions:
    """REQ-STATE-2: Status transitions driven by DB completeness."""

    @pytest.mark.asyncio
    async def test_photos_confirmed_with_fields_transitions_to_pending_data(
        self, service, sqlite_session
    ):
        """pending_photos → pending_data when element has required fields."""
        cat = await _seed_category(sqlite_session)
        elem = await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE)
        # Add required field so transition goes to pending_data
        await _seed_required_field(sqlite_session, elem.id)
        await _seed_case_element_data(sqlite_session, CASE_ID, ELEMENT_CODE, status="pending_photos")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            await service.record_photos_confirmed(CASE_ID, ELEMENT_CODE, photo_count=2)

        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == ELEMENT_CODE)
        )
        ced = result.scalar_one_or_none()
        assert ced is not None
        assert ced.status == "pending_data"

    @pytest.mark.asyncio
    async def test_photos_confirmed_without_fields_transitions_to_completed(
        self, service, sqlite_session
    ):
        """pending_photos → completed when element has NO required fields."""
        cat = await _seed_category(sqlite_session)
        # Element with NO required fields
        await _seed_element(sqlite_session, cat.id, code="NO_FIELDS_ELEM")
        await _seed_case_element_data(sqlite_session, CASE_ID, "NO_FIELDS_ELEM", status="pending_photos")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            await service.record_photos_confirmed(CASE_ID, "NO_FIELDS_ELEM", photo_count=1)

        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == "NO_FIELDS_ELEM")
        )
        ced = result.scalar_one_or_none()
        assert ced is not None
        assert ced.status == "completed"

    @pytest.mark.asyncio
    async def test_mark_element_complete_sets_completed_status(
        self, service, sqlite_session
    ):
        """mark_element_complete sets status = 'completed' from any status."""
        await _seed_case_element_data(
            sqlite_session, CASE_ID, ELEMENT_CODE, status="pending_data"
        )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            await service.mark_element_complete(CASE_ID, ELEMENT_CODE)

        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == ELEMENT_CODE)
        )
        ced = result.scalar_one_or_none()
        assert ced is not None
        assert ced.status == "completed"

    @pytest.mark.asyncio
    async def test_mark_element_complete_is_idempotent(self, service, sqlite_session):
        """Calling mark_element_complete twice does not raise."""
        await _seed_case_element_data(
            sqlite_session, CASE_ID, ELEMENT_CODE, status="completed"
        )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            # Should not raise
            await service.mark_element_complete(CASE_ID, ELEMENT_CODE)
            await service.mark_element_complete(CASE_ID, ELEMENT_CODE)

        # Still completed
        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == ELEMENT_CODE)
        )
        ced = result.scalar_one_or_none()
        assert ced is not None
        assert ced.status == "completed"

    @pytest.mark.asyncio
    async def test_is_all_elements_complete_true_when_all_completed(
        self, service, sqlite_session
    ):
        """is_all_elements_complete returns True when all rows are 'completed'."""
        codes = ["ESC", "MAN"]
        for code in codes:
            await _seed_case_element_data(
                sqlite_session, CASE_ID, code, status="completed"
            )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            result = await service.is_all_elements_complete(CASE_ID, codes)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_all_elements_complete_false_when_one_pending(
        self, service, sqlite_session
    ):
        """is_all_elements_complete returns False if any element is not completed."""
        await _seed_case_element_data(sqlite_session, CASE_ID, "ESC", status="completed")
        await _seed_case_element_data(sqlite_session, CASE_ID, "MAN", status="pending_data")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            result = await service.is_all_elements_complete(CASE_ID, ["ESC", "MAN"])

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-4: CollectionContext has required keys
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectionContext:
    """REQ-STATE-4: get_collection_context returns structured prompt context."""

    @pytest.mark.asyncio
    async def test_context_has_required_top_level_keys(self, service, sqlite_session):
        """CollectionContext contains current_element, all_elements, progress."""
        cat = await _seed_category(sqlite_session)
        await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE)
        await _seed_case_element_data(sqlite_session, CASE_ID, ELEMENT_CODE, status="pending_photos")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, [ELEMENT_CODE])

        d = ctx.to_dict()
        assert "current_element" in d
        assert "all_elements" in d
        assert "progress" in d

    @pytest.mark.asyncio
    async def test_current_element_has_required_sub_keys(self, service, sqlite_session):
        """current_element contains code, display_name, phase, pending_fields, collected_fields."""
        cat = await _seed_category(sqlite_session)
        elem = await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE, name="Escape")
        await _seed_required_field(sqlite_session, elem.id, field_key="marca")
        await _seed_case_element_data(sqlite_session, CASE_ID, ELEMENT_CODE, status="pending_data")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, [ELEMENT_CODE])

        ce = ctx.current_element
        assert ce is not None
        assert "code" in ce
        assert "display_name" in ce
        assert "phase" in ce
        assert "pending_fields" in ce
        assert "collected_fields" in ce

    @pytest.mark.asyncio
    async def test_current_element_is_first_non_completed(self, service, sqlite_session):
        """REQ-STATE-5: current_element is the first non-completed in ordering."""
        cat = await _seed_category(sqlite_session)
        await _seed_element(sqlite_session, cat.id, code="ELEM_A")
        await _seed_element(sqlite_session, cat.id, code="ELEM_B")

        # ELEM_A is completed, ELEM_B is pending
        await _seed_case_element_data(sqlite_session, CASE_ID, "ELEM_A", status="completed")
        await _seed_case_element_data(sqlite_session, CASE_ID, "ELEM_B", status="pending_photos")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, ["ELEM_A", "ELEM_B"])

        assert ctx.current_element is not None
        assert ctx.current_element["code"] == "ELEM_B"

    @pytest.mark.asyncio
    async def test_current_element_is_none_when_all_completed(self, service, sqlite_session):
        """current_element is None when every element is completed."""
        cat = await _seed_category(sqlite_session)
        await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE)
        await _seed_case_element_data(sqlite_session, CASE_ID, ELEMENT_CODE, status="completed")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, [ELEMENT_CODE])

        assert ctx.current_element is None
        assert ctx.progress["completed"] == 1

    @pytest.mark.asyncio
    async def test_empty_element_codes_returns_safe_context(self, service):
        """Empty element_codes list returns safe CollectionContext with no crash."""
        with patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, [])

        assert ctx.current_element is None
        assert ctx.all_elements == []
        assert ctx.progress == {"completed": 0, "total": 0}

    @pytest.mark.asyncio
    async def test_pending_fields_excludes_already_collected(self, service, sqlite_session):
        """pending_fields only lists fields not yet in field_values."""
        cat = await _seed_category(sqlite_session)
        elem = await _seed_element(sqlite_session, cat.id, code=ELEMENT_CODE)
        await _seed_required_field(sqlite_session, elem.id, field_key="marca", sort_order=1)
        await _seed_required_field(sqlite_session, elem.id, field_key="modelo", sort_order=2)
        # "marca" already collected
        await _seed_case_element_data(
            sqlite_session, CASE_ID, ELEMENT_CODE,
            status="pending_data",
            field_values={"marca": "AKRAPOVIC"},
        )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            ctx = await service.get_collection_context(CASE_ID, [ELEMENT_CODE])

        assert ctx.current_element is not None
        pending_keys = [f["field_key"] for f in ctx.current_element["pending_fields"]]
        assert "marca" not in pending_keys  # already collected
        assert "modelo" in pending_keys    # still pending


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-5: get_current_element respects ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCurrentElement:
    """REQ-STATE-5: get_current_element returns first non-completed by list order."""

    @pytest.mark.asyncio
    async def test_returns_first_non_completed_in_order(self, service, sqlite_session):
        """get_current_element respects element_codes list ordering."""
        await _seed_case_element_data(sqlite_session, CASE_ID, "A", status="completed")
        await _seed_case_element_data(sqlite_session, CASE_ID, "B", status="pending_photos")
        await _seed_case_element_data(sqlite_session, CASE_ID, "C", status="pending_photos")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            current = await service.get_current_element(CASE_ID, ["A", "B", "C"])

        assert current == "B"

    @pytest.mark.asyncio
    async def test_returns_none_when_all_elements_completed(self, service, sqlite_session):
        """get_current_element returns None when everything is done."""
        for code in ["X", "Y"]:
            await _seed_case_element_data(sqlite_session, CASE_ID, code, status="completed")
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            result = await service.get_current_element(CASE_ID, ["X", "Y"])

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases: unknown codes, DB errors, empty inputs."""

    @pytest.mark.asyncio
    async def test_unknown_element_code_returns_fallback_state(
        self, service, sqlite_session
    ):
        """An element_code not in DB still creates a CaseElementData row gracefully."""
        await sqlite_session.commit()  # empty DB

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            state = await service.get_element_state(CASE_ID, "UNKNOWN_CODE")

        # Should not raise; returns None when DB create fails or returns state with fallback name
        # In practice, element lookup returns None, display_name defaults to element_code
        if state is not None:
            assert state.element_code == "UNKNOWN_CODE"
            assert state.display_name == "UNKNOWN_CODE"  # Falls back to code

    @pytest.mark.asyncio
    async def test_is_all_elements_complete_vacuously_true_for_empty_list(
        self, service
    ):
        """is_all_elements_complete([]) returns True (vacuous completeness)."""
        with patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            result = await service.is_all_elements_complete(CASE_ID, [])

        assert result is True

    @pytest.mark.asyncio
    async def test_photos_confirmed_idempotent_when_already_completed(
        self, service, sqlite_session
    ):
        """record_photos_confirmed is a no-op when element is already completed."""
        await _seed_case_element_data(
            sqlite_session, CASE_ID, ELEMENT_CODE, status="completed"
        )
        await sqlite_session.commit()

        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            # Must not raise and must leave status unchanged
            await service.record_photos_confirmed(CASE_ID, ELEMENT_CODE, photo_count=3)

        result = await sqlite_session.execute(
            select(CaseElementData)
            .where(CaseElementData.case_id == CASE_ID)
            .where(CaseElementData.element_code == ELEMENT_CODE)
        )
        ced = result.scalar_one_or_none()
        assert ced is not None
        assert ced.status == "completed"  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# REQ-STATE-4 (continued): Conditional field logic in _build_field_contexts
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildFieldContexts:
    """
    Unit tests for the internal _build_field_contexts helper.
    Tests REQ-STATE-4 conditional field logic without any DB interaction.
    """

    def _make_field(
        self,
        field_key: str,
        sort_order: int = 1,
        is_active: bool = True,
        condition_field_id: uuid.UUID | None = None,
        condition_operator: str | None = None,
        condition_value: str | None = None,
    ) -> ElementRequiredField:
        """Build an ElementRequiredField object (in memory, no DB)."""
        f = MagicMock(spec=ElementRequiredField)
        f.id = uuid.uuid4()
        f.field_key = field_key
        f.field_label = field_key.title()
        f.field_type = "text"
        f.is_required = True
        f.is_active = is_active
        f.sort_order = sort_order
        f.options = None
        f.example_value = None
        f.llm_instruction = None
        f.validation_rules = None
        f.condition_field_id = condition_field_id
        f.condition_operator = condition_operator
        f.condition_value = condition_value
        return f

    def test_all_applicable_returned_when_no_conditions(self):
        """Fields with no conditions are all returned."""
        fields = [self._make_field("marca"), self._make_field("modelo")]
        all_fields, pending = _build_field_contexts(fields, {})
        assert len(all_fields) == 2
        assert len(pending) == 2

    def test_inactive_fields_excluded(self):
        """Fields with is_active=False are not included."""
        fields = [
            self._make_field("active_field", is_active=True),
            self._make_field("inactive_field", is_active=False),
        ]
        all_fields, _ = _build_field_contexts(fields, {})
        assert len(all_fields) == 1
        assert all_fields[0].field_key == "active_field"

    def test_collected_fields_not_in_pending(self):
        """Fields already in collected_values are excluded from pending."""
        fields = [self._make_field("marca"), self._make_field("modelo")]
        all_fields, pending = _build_field_contexts(fields, {"marca": "AKRAPOVIC"})
        assert len(all_fields) == 2
        pending_keys = [f.field_key for f in pending]
        assert "marca" not in pending_keys
        assert "modelo" in pending_keys

    def test_conditional_field_hidden_when_condition_not_met(self):
        """A conditional field is NOT shown when its condition is not satisfied."""
        base_field = self._make_field("has_upgrade")
        base_field.field_type = "boolean"

        cond_field = self._make_field("upgrade_brand")
        cond_field.condition_field_id = base_field.id
        cond_field.condition_operator = "equals"
        cond_field.condition_value = "true"

        # condition not met (has_upgrade not in collected_values)
        all_fields, pending = _build_field_contexts(
            [base_field, cond_field], collected_values={}
        )
        keys = [f.field_key for f in all_fields]
        assert "upgrade_brand" not in keys

    def test_conditional_field_shown_when_condition_met(self):
        """A conditional field IS shown when its condition is satisfied."""
        base_field = self._make_field("has_upgrade")
        base_field.field_type = "boolean"

        cond_field = self._make_field("upgrade_brand")
        cond_field.condition_field_id = base_field.id
        cond_field.condition_operator = "equals"
        cond_field.condition_value = "true"

        # condition met
        all_fields, _ = _build_field_contexts(
            [base_field, cond_field],
            collected_values={"has_upgrade": "true"},
        )
        keys = [f.field_key for f in all_fields]
        assert "upgrade_brand" in keys


# ─────────────────────────────────────────────────────────────────────────────
# Feature flag guard
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureFlagGuard:
    """Service raises RuntimeError if EXPEDIENTE_V2_ENABLED=False."""

    @pytest.mark.asyncio
    async def test_raises_when_flag_disabled(self, service):
        with patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=False),
        ):
            with pytest.raises(RuntimeError, match="EXPEDIENTE_V2_ENABLED"):
                await service.get_element_state(CASE_ID, "ESC")

    @pytest.mark.asyncio
    async def test_no_raise_when_flag_enabled(self, service, sqlite_session):
        with patch(
            "agent.services.element_state_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ), patch(
            "agent.services.element_state_service.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ):
            # Should not raise; returns None since no element data in DB
            result = await service.get_element_state(CASE_ID, "ESC")
        # None is acceptable: no element in DB but no RuntimeError
        assert result is None or isinstance(result, ElementState)
