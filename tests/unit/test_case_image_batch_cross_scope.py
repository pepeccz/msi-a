"""
Unit tests for cross-scope batch guard — expediente-element-photo-cross-assignment.

Covers Phase 3 acceptance criteria:

1. test_resolve_for_scope_skips_cross_scope_batch_when_live_ingest
   REQ: When is_live_ingest=True and a historical batch belongs to a DIFFERENT
   element scope, resolve_for_scope must NOT return that stale batch. It must
   fall through to find/create the correct batch for the requested scope.

2. test_resolve_for_scope_allows_same_scope_historical_when_live_ingest
   REQ: When is_live_ingest=True and the historical batch matches the SAME scope
   as the requested scope, the guard must NOT fire — the batch is returned.

3. test_resolve_for_scope_reconcile_path_not_affected
   REQ: When is_live_ingest=False (default / reconciliation path), cross-scope
   historical batches ARE returned as usual — timestamp-based ownership is
   unconditional for recovery scenarios.

4. test_completar_elemento_finalizes_batch_before_advance
   REQ: completar_elemento_actual() must call finalize_for_scope() for the
   completing element's batch BEFORE advancing to the next element.

5. test_element_handoff_photos_go_to_correct_element (end-to-end regression)
   REQ: After element_1 is completed and the agent advances to element_2, any
   new photos arriving via live ingest must be persisted under element_2's batch,
   NOT element_1's stale/open batch.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.services.case_image_batch_service import (
    CaseImageBatchService,
    build_upload_scope,
    get_case_image_batch_service,
)
from database.models import Base, Case, CaseImage, CaseImageUploadBatch, User


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def sqlite_engine():
    """SQLite in-memory engine — isolated per test function."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_session(sqlite_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


def make_session_cm(session: AsyncSession):
    """Return an asynccontextmanager factory that always yields the same session."""

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


async def _seed_case(session: AsyncSession) -> Case:
    """Create a minimal User + Case and return the Case."""
    user = User(phone=f"+346{uuid.uuid4().int % 100000000:08d}")
    session.add(user)
    await session.flush()
    case = Case(conversation_id=f"conv-{uuid.uuid4().hex[:8]}", user_id=user.id)
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


def _make_element_batch(
    case: Case,
    element_code: str,
    opened_at: datetime,
    finalized_at: datetime | None = None,
    status: str = "open",
) -> CaseImageUploadBatch:
    """Factory for CaseImageUploadBatch rows used in cross-scope tests."""
    scope_key = (
        f"case:{case.id}:sub_mode:collect_element_data:scope:element:{element_code}"
    )
    return CaseImageUploadBatch(
        batch_id=str(uuid.uuid4()),
        case_id=case.id,
        upload_scope_key=scope_key,
        owner_scope="element_photo",
        owner_element_code=element_code,
        expediente_sub_mode="collect_element_data",
        status=status,
        opened_at=opened_at,
        finalized_at=finalized_at,
        last_activity_at=opened_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Cross-scope guard fires: live ingest must skip stale batch
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_for_scope_skips_cross_scope_batch_when_live_ingest(
    sqlite_session: AsyncSession,
) -> None:
    """
    GUARD ACTIVE (is_live_ingest=True, different scope):
    When a live image arrives for element_2 but the DB's historical-window match
    returns element_1's still-open (or recently-closed) batch, resolve_for_scope
    must NOT return that stale batch.

    Instead it must fall through to the current-scope lookup / create path and
    return a batch for element_2.
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    # element_1 batch opened 5 minutes ago — NOT yet finalized
    elem1_batch = _make_element_batch(
        case,
        "ESCAPE",
        opened_at=now - timedelta(minutes=5),
        finalized_at=None,  # still "open" — the bug scenario
        status="open",
    )
    sqlite_session.add(elem1_batch)
    await sqlite_session.commit()

    # Caller requests element_2 scope at "now" (message_created_at just received)
    scope_elem2 = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="MANILLAR",
    )
    assert scope_elem2 is not None

    service = CaseImageBatchService()
    # Use a timestamp that falls inside elem1's open window
    msg_ts = int((now - timedelta(minutes=2)).timestamp())

    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        resolution = await service.resolve_for_scope(
            scope_elem2,
            allow_create=True,
            message_created_at=msg_ts,
            is_live_ingest=True,  # ← guard active
        )

    # Must NOT return elem1's batch
    assert resolution is not None, "A batch must be resolved (new one created)"
    assert resolution.batch_id != elem1_batch.batch_id, (
        "Guard must prevent returning element_1's stale batch for element_2 live ingest"
    )
    assert resolution.owner_element_code == "MANILLAR", (
        f"Resolved batch must belong to MANILLAR, got {resolution.owner_element_code!r}"
    )
    assert resolution.is_historical is False, (
        "A freshly created batch must not be marked historical"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Guard does NOT fire for same-scope historical match
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_for_scope_allows_same_scope_historical_when_live_ingest(
    sqlite_session: AsyncSession,
) -> None:
    """
    GUARD INACTIVE (is_live_ingest=True, SAME scope):
    When the historical-window match returns a batch that belongs to the SAME
    element scope as the requested scope, the guard must not fire — the batch
    is valid and should be returned.
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    # element_1 batch, still open
    elem1_batch = _make_element_batch(
        case,
        "ESCAPE",
        opened_at=now - timedelta(minutes=5),
        finalized_at=None,
        status="open",
    )
    sqlite_session.add(elem1_batch)
    await sqlite_session.commit()

    # Request the SAME scope (element_1) with is_live_ingest=True
    scope_elem1 = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="ESCAPE",
    )
    assert scope_elem1 is not None

    service = CaseImageBatchService()
    msg_ts = int((now - timedelta(minutes=2)).timestamp())

    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        resolution = await service.resolve_for_scope(
            scope_elem1,
            allow_create=True,
            message_created_at=msg_ts,
            is_live_ingest=True,  # ← guard active, but scope matches
        )

    # The existing batch for ESCAPE must be returned (guard does not interfere)
    assert resolution is not None
    assert resolution.owner_element_code == "ESCAPE", (
        f"Same-scope historical batch must be returned, got {resolution.owner_element_code!r}"
    )
    # Because the batch is still open and its scope_key matches, the current-scope
    # path (not historical path) will return it, but the key assertion is that
    # we do NOT get a different batch.
    assert resolution.batch_id == elem1_batch.batch_id, (
        "Must reuse the existing open batch for the same element scope"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — Reconciliation path (is_live_ingest=False) is NOT affected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_for_scope_reconcile_path_not_affected(
    sqlite_session: AsyncSession,
) -> None:
    """
    RECONCILIATION PATH (is_live_ingest=False, different scope):
    The cross-scope guard must NOT activate when is_live_ingest=False.
    Timestamp-based ownership remains unconditional for recovery/reconciliation.

    A Chatwoot message whose timestamp falls within element_1's window must be
    returned as element_1's batch — even when the caller is asking about element_2.
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    # element_1 batch: opened and finalized (complete lifecycle)
    elem1_open = now - timedelta(minutes=15)
    elem1_close = now - timedelta(minutes=8)
    elem1_batch = _make_element_batch(
        case,
        "ESCAPE",
        opened_at=elem1_open,
        finalized_at=elem1_close,
        status="confirmed",
    )
    # element_2 batch: currently active
    elem2_batch = _make_element_batch(
        case,
        "MANILLAR",
        opened_at=now - timedelta(minutes=7),
        finalized_at=None,
        status="open",
    )
    sqlite_session.add_all([elem1_batch, elem2_batch])
    await sqlite_session.commit()

    # Scope for element_2 (the currently active element)
    scope_elem2 = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="MANILLAR",
    )
    assert scope_elem2 is not None

    # Message timestamp falls inside element_1's window
    msg_ts_in_elem1_window = int((elem1_open + timedelta(minutes=3)).timestamp())

    service = CaseImageBatchService()
    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        resolution = await service.resolve_for_scope(
            scope_elem2,
            allow_create=True,
            message_created_at=msg_ts_in_elem1_window,
            is_live_ingest=False,  # ← reconciliation path, guard INACTIVE
        )

    # Must return element_1's historical batch (cross-scope guard must NOT fire)
    assert resolution is not None
    assert resolution.batch_id == elem1_batch.batch_id, (
        "Reconciliation path must return the historical batch regardless of scope mismatch"
    )
    assert resolution.owner_element_code == "ESCAPE", (
        f"Reconciliation must respect the timestamp window, got {resolution.owner_element_code!r}"
    )
    assert resolution.is_historical is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — completar_elemento_actual finalizes batch before advancing
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_completar_elemento_finalizes_batch_before_advance(
    sqlite_session: AsyncSession,
) -> None:
    """
    completar_elemento_actual() MUST call finalize_for_scope() for the completing
    element BEFORE it opens the next-element batch.

    We verify this by:
    1. Setting up a mock case with an open batch for element_1 (ESCAPE).
    2. Calling completar_elemento_actual() in a fully-mocked context (no real LLM).
    3. Asserting that finalize_for_scope was called with ESCAPE before
       open_for_scope is called for the next element.

    Implementation note: We use the real CollectionStep enum so that isinstance()
    checks inside the tool work correctly. We mock get_current_step() to return
    CollectionStep.COLLECT_ELEMENT_DATA, which is the valid step for this tool.
    """
    from agent.utils.expediente_types import CollectionStep

    case = await _seed_case(sqlite_session)
    case_id = str(case.id)
    category_id = str(uuid.uuid4())
    element_code = "ESCAPE"
    next_element_code = "MANILLAR"

    # Build minimal FSM case_state matching get_case_fsm_state() output
    case_state = {
        "case_id": case_id,
        "category_id": category_id,
        "element_codes": [element_code, next_element_code],
        "current_element_index": 0,
        "element_phase": "photos",
        "element_data_status": {
            element_code: "photos_done",
            next_element_code: "pending",
        },
        "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
    }
    # Minimal fsm_state wrapper
    fsm_state: dict = {"case_state": case_state}

    # Capture call order to verify finalize happens before open
    call_order: list[str] = []

    async def _fake_finalize_for_scope(**kwargs):
        call_order.append(f"finalize:{kwargs.get('element_code')}")
        return str(uuid.uuid4())

    async def _fake_open_for_scope(**kwargs):
        call_order.append(f"open:{kwargs.get('element_code')}")
        return MagicMock(batch_id=str(uuid.uuid4()))

    mock_batch_service = AsyncMock()
    mock_batch_service.finalize_for_scope = AsyncMock(
        side_effect=_fake_finalize_for_scope
    )
    mock_batch_service.open_for_scope = AsyncMock(side_effect=_fake_open_for_scope)

    # Mock element lookup to return a simple element object
    mock_element = MagicMock()
    mock_element.id = uuid.uuid4()
    mock_element.name = "Escape"

    # Mock case element data (no required fields outstanding)
    mock_case_element = MagicMock()
    mock_case_element.field_values = {}

    # Use the real CollectionStep so isinstance() works inside the tool
    with (
        patch(
            "agent.tools.element_data_tools.get_current_state",
            return_value={"fsm_state": fsm_state},
        ),
        patch(
            "agent.tools.element_data_tools.get_case_fsm_state",
            return_value=case_state,
        ),
        # Return the REAL enum member so isinstance(current_step, CollectionStep) passes
        patch(
            "agent.tools.element_data_tools.get_current_step",
            return_value=CollectionStep.COLLECT_ELEMENT_DATA,
        ),
        patch(
            "agent.tools.element_data_tools.get_current_element_code",
            return_value=element_code,
        ),
        patch(
            "agent.tools.element_data_tools._get_element_by_code",
            new=AsyncMock(return_value=mock_element),
        ),
        patch(
            "agent.tools.element_data_tools._get_required_fields_for_element",
            new=AsyncMock(return_value=[]),  # No required fields → can complete
        ),
        patch(
            "agent.tools.element_data_tools._get_or_create_case_element_data",
            new=AsyncMock(return_value=mock_case_element),
        ),
        patch(
            "agent.tools.element_data_tools._update_case_element_data",
            new=AsyncMock(),
        ),
        patch(
            "agent.tools.element_data_tools.get_case_image_batch_service",
            return_value=mock_batch_service,
        ),
        patch(
            "agent.tools.element_data_tools.get_settings",
            return_value=MagicMock(EXPEDIENTE_V2_ENABLED=True),
        ),
        patch(
            "agent.tools.element_data_tools.update_element_status",
            return_value=fsm_state,
        ),
        patch(
            "agent.tools.element_data_tools.update_case_fsm_state",
            return_value=fsm_state,
        ),
        patch(
            "agent.tools.element_data_tools.transition_to",
            return_value=fsm_state,
        ),
        # ELEMENT_STATUS_COMPLETE is already imported — patch with real string value
        patch(
            "agent.tools.element_data_tools.ELEMENT_STATUS_COMPLETE",
            "completed",
        ),
    ):
        from agent.tools.element_data_tools import completar_elemento_actual

        result = await completar_elemento_actual.coroutine()

    # The tool must have succeeded (not returned an error)
    assert result.get("success") is True, (
        f"completar_elemento_actual must succeed, got: {result}"
    )

    # finalize must have been called for the completing element
    finalize_calls = [c for c in call_order if c.startswith("finalize:")]
    assert len(finalize_calls) >= 1, (
        "finalize_for_scope must be called for the completing element before advancing"
    )
    assert finalize_calls[0] == f"finalize:{element_code}", (
        f"First finalize call must be for {element_code!r}, got {finalize_calls[0]!r}"
    )

    # If open was called, it must have happened AFTER finalize
    open_calls = [c for c in call_order if c.startswith("open:")]
    if open_calls:
        finalize_pos = next(
            i for i, c in enumerate(call_order) if c.startswith("finalize:")
        )
        open_pos = next(i for i, c in enumerate(call_order) if c.startswith("open:"))
        assert finalize_pos < open_pos, (
            f"finalize (pos {finalize_pos}) must precede open (pos {open_pos})"
        )

    # Verify finalize_for_scope was invoked with the completing element's exact args
    mock_batch_service.finalize_for_scope.assert_awaited()
    finalize_kwargs = mock_batch_service.finalize_for_scope.call_args.kwargs
    assert finalize_kwargs.get("element_code") == element_code, (
        f"finalize_for_scope must receive element_code={element_code!r}, "
        f"got {finalize_kwargs.get('element_code')!r}"
    )
    assert finalize_kwargs.get("case_id") == case_id, (
        f"finalize_for_scope must receive case_id={case_id!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — End-to-end regression: photos go to correct element after handoff
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_element_handoff_photos_go_to_correct_element(
    sqlite_session: AsyncSession,
) -> None:
    """
    REGRESSION TEST: The exact bug this change fixes.

    Scenario:
    1. Agent is collecting photos for element_1 (ESCAPE). Batch B1 is open.
    2. User says "listo" → completar_elemento_actual() is called.
       - B1 must be finalized (finalized_at set).
       - A new batch B2 is opened for element_2 (MANILLAR).
    3. User sends new photos for element_2.
       - is_live_ingest=True and agent state says element_2 is current.
       - Photos must be persisted under B2 (MANILLAR), NOT under B1 (ESCAPE).

    This test verifies the complete guard path in resolve_for_scope using real
    SQLite rows to simulate the before/after state.
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    # ── Step 1: Simulate element_1 batch lifecycle ────────────────────────────
    # B1 opened 10 minutes ago for ESCAPE
    b1_open = now - timedelta(minutes=10)
    b1_batch = _make_element_batch(
        case,
        "ESCAPE",
        opened_at=b1_open,
        finalized_at=None,  # still open (pre-fix state)
        status="open",
    )
    sqlite_session.add(b1_batch)
    await sqlite_session.commit()

    service = CaseImageBatchService()

    # ── Step 2: Finalize B1 (simulating completar_elemento_actual) ────────────
    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        finalized_id = await service.finalize_for_scope(
            case_id=str(case.id),
            expediente_sub_mode="collect_element_data",
            element_code="ESCAPE",
            status="completed",
        )

    assert finalized_id == b1_batch.batch_id, (
        "finalize_for_scope must return element_1's batch_id"
    )

    # Reload and verify finalized_at is set
    await sqlite_session.refresh(b1_batch)
    assert b1_batch.finalized_at is not None, (
        "Element_1 batch must have finalized_at set after completar_elemento_actual"
    )

    # ── Step 3: Open B2 for element_2 (MANILLAR) ─────────────────────────────
    scope_elem2 = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="MANILLAR",
    )
    assert scope_elem2 is not None

    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        b2_resolution = await service.resolve_for_scope(
            scope_elem2,
            allow_create=True,
            is_live_ingest=False,  # Opening new batch — no cross-scope guard needed
        )

    assert b2_resolution is not None
    b2_batch_id = b2_resolution.batch_id
    assert b2_batch_id != b1_batch.batch_id, "B2 must be a different batch than B1"
    assert b2_resolution.owner_element_code == "MANILLAR"

    # ── Step 4: New photos arrive for element_2 via live ingest ──────────────
    # The message was sent now (after element_1 was finalized)
    msg_ts_for_elem2 = int(now.timestamp())

    with patch(
        "agent.services.case_image_batch_service.get_async_session",
        new=make_session_cm(sqlite_session),
    ):
        live_resolution = await service.resolve_for_scope(
            scope_elem2,
            allow_create=True,
            message_created_at=msg_ts_for_elem2,
            is_live_ingest=True,  # Live ingest path — guard active
        )

    # Must resolve to B2 (MANILLAR), NOT B1 (ESCAPE)
    assert live_resolution is not None
    assert live_resolution.batch_id == b2_batch_id, (
        f"New photos for element_2 must go to B2 ({b2_batch_id!r}), "
        f"not B1 ({b1_batch.batch_id!r})"
    )
    assert live_resolution.owner_element_code == "MANILLAR", (
        f"Live ingest batch must belong to MANILLAR, got {live_resolution.owner_element_code!r}"
    )

    # ── Step 5: Verify no photo contamination via CaseImage attribution ───────
    # Simulate inserting both element images with their correct batch assignments
    img_elem1 = CaseImage(
        case_id=case.id,
        stored_filename=f"{uuid.uuid4().hex}.jpg",
        original_filename="escape_photo.jpg",
        display_name="escape_photo",
        mime_type="image/jpeg",
        element_code="ESCAPE",
        upload_batch_id=finalized_id,  # B1
        attachment_fingerprint=f"fp-escape-{uuid.uuid4().hex}",
    )
    img_elem2 = CaseImage(
        case_id=case.id,
        stored_filename=f"{uuid.uuid4().hex}.jpg",
        original_filename="manillar_photo.jpg",
        display_name="manillar_photo",
        mime_type="image/jpeg",
        element_code="MANILLAR",
        upload_batch_id=b2_batch_id,  # B2
        attachment_fingerprint=f"fp-manillar-{uuid.uuid4().hex}",
    )
    sqlite_session.add_all([img_elem1, img_elem2])
    await sqlite_session.commit()

    # Query scoped to B1 (ESCAPE) must return only ESCAPE images
    result_b1 = await sqlite_session.execute(
        select(CaseImage)
        .where(CaseImage.case_id == case.id)
        .where(CaseImage.upload_batch_id == finalized_id)
    )
    b1_images = result_b1.scalars().all()
    assert len(b1_images) == 1
    assert all(img.element_code == "ESCAPE" for img in b1_images), (
        "Only ESCAPE photos must appear in B1 scoped count"
    )

    # Query scoped to B2 (MANILLAR) must return only MANILLAR images
    result_b2 = await sqlite_session.execute(
        select(CaseImage)
        .where(CaseImage.case_id == case.id)
        .where(CaseImage.upload_batch_id == b2_batch_id)
    )
    b2_images = result_b2.scalars().all()
    assert len(b2_images) == 1
    assert all(img.element_code == "MANILLAR" for img in b2_images), (
        "Only MANILLAR photos must appear in B2 scoped count — no cross-contamination"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auxiliary: Warning log is emitted on cross-scope skip
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_for_scope_emits_warning_on_cross_scope_skip(
    sqlite_session: AsyncSession,
) -> None:
    """
    REQ-TEL-1: resolve_for_scope must emit a structured 'batch_scope_conflict_detected'
    WARNING log when it skips a cross-scope historical batch during live ingest.
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    elem1_batch = _make_element_batch(
        case,
        "ESCAPE",
        opened_at=now - timedelta(minutes=5),
        finalized_at=None,
        status="open",
    )
    sqlite_session.add(elem1_batch)
    await sqlite_session.commit()

    scope_elem2 = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="MANILLAR",
    )
    assert scope_elem2 is not None

    service = CaseImageBatchService()
    msg_ts = int((now - timedelta(minutes=2)).timestamp())

    with (
        patch(
            "agent.services.case_image_batch_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ),
        patch("agent.services.case_image_batch_service.logger") as mock_logger,
    ):
        await service.resolve_for_scope(
            scope_elem2,
            allow_create=True,
            message_created_at=msg_ts,
            is_live_ingest=True,
        )

    # Verify the structured warning was emitted
    warning_calls = [
        c
        for c in mock_logger.warning.call_args_list
        if c.args and "batch_scope_conflict_detected" in str(c.args[0])
    ]
    assert len(warning_calls) >= 1, (
        "Must emit 'batch_scope_conflict_detected' warning when skipping cross-scope batch"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Regression: batch_scope_conflict race condition (REQ-3)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_scope_conflict_race_condition_handled(
    sqlite_session: AsyncSession,
) -> None:
    """
    REG-TEST (REQ-3): When photos for TOLDO_GALIBO arrive before PLACA_SOLAR's
    batch is finalized (finalized_at=None), resolve_for_scope with is_live_ingest=True
    MUST:
    - NOT raise any exception
    - Emit a 'batch_scope_conflict_detected' warning
    - Skip the unfinalised PLACA batch
    - Return a new batch scoped to TOLDO_GALIBO

    Design ref: sdd/fix-finalize-lock-image-flow/design
    Spec ref:   sdd/fix-finalize-lock-image-flow/spec (REQ-3)
    """
    case = await _seed_case(sqlite_session)
    now = datetime.now(UTC)

    # PLACA_SOLAR batch is open (unfinalised — the race condition state)
    placa_batch = _make_element_batch(
        case,
        "PLACA_SOLAR",
        opened_at=now - timedelta(minutes=5),
        finalized_at=None,  # NOT finalized — the race condition
        status="open",
    )
    sqlite_session.add(placa_batch)
    await sqlite_session.commit()

    scope_toldo = build_upload_scope(
        case_id=str(case.id),
        expediente_sub_mode="collect_element_data",
        element_code="TOLDO_GALIBO",
    )
    assert scope_toldo is not None

    service = CaseImageBatchService()
    # Timestamp that falls within PLACA's open window
    msg_ts = int((now - timedelta(minutes=2)).timestamp())

    raised_exception: Exception | None = None
    result = None

    with (
        patch(
            "agent.services.case_image_batch_service.get_async_session",
            new=make_session_cm(sqlite_session),
        ),
        patch("agent.services.case_image_batch_service.logger") as mock_logger,
    ):
        try:
            result = await service.resolve_for_scope(
                scope_toldo,
                allow_create=True,
                message_created_at=msg_ts,
                is_live_ingest=True,  # Live ingest — guard active
            )
        except Exception as exc:
            raised_exception = exc

    # REQ-3a: No exception raised
    assert raised_exception is None, (
        f"resolve_for_scope must NOT raise when PLACA batch is unfinalised and "
        f"TOLDO arrives with is_live_ingest=True. "
        f"Got exception: {raised_exception!r}"
    )

    # REQ-3b: Returns a new batch for TOLDO_GALIBO (not PLACA_SOLAR's batch)
    assert result is not None, "resolve_for_scope must return a batch for TOLDO_GALIBO"
    assert result.owner_element_code == "TOLDO_GALIBO", (
        f"Returned batch must belong to TOLDO_GALIBO, got {result.owner_element_code!r}"
    )
    assert result.batch_id != placa_batch.batch_id, (
        "Must NOT return PLACA_SOLAR's unfinalised batch when TOLDO arrives"
    )

    # REQ-3c: Emits batch_scope_conflict_detected warning
    warning_calls = [
        c
        for c in mock_logger.warning.call_args_list
        if c.args and "batch_scope_conflict_detected" in str(c.args[0])
    ]
    assert len(warning_calls) >= 1, (
        "Must emit 'batch_scope_conflict_detected' warning when "
        "skipping unfinalised PLACA batch for TOLDO live ingest"
    )
