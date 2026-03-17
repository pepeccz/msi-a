from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncGenerator, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.modes.expediente_mode import ExpedienteModeNode
from agent.services.expediente_onboarding import build_expediente_opening_overview
from agent.state.conversation_state import ConversationState
from agent.tools.image_tools import (
    _clear_element_images_sent_this_turn,
    clear_image_tools_state,
    enviar_imagenes_ejemplo,
    set_current_state_for_image_tools,
)
from agent.utils.fsm_compat import CollectionStep
from database.models import Base, Case, CaseImage, User


@pytest_asyncio.fixture
async def sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def sqlite_session(sqlite_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(
        sqlite_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


def _make_session_context(session: AsyncSession):
    @asynccontextmanager
    async def _context():
        yield session

    return _context


async def _create_case(session: AsyncSession) -> Case:
    user = User(phone=f"+346{uuid.uuid4().int % 100000000:08d}")
    session.add(user)
    await session.flush()

    case = Case(
        conversation_id=f"conv-{uuid.uuid4().hex[:8]}",
        user_id=user.id,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def _seed_case_images(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    element_code: str | None,
    count: int,
    upload_batch_id: str | None,
) -> None:
    for index in range(count):
        session.add(
            CaseImage(
                case_id=case_id,
                stored_filename=f"{uuid.uuid4().hex}.jpg",
                original_filename=f"photo_{index + 1}.jpg",
                display_name=f"photo_{index + 1}",
                mime_type="image/jpeg",
                element_code=element_code,
                upload_batch_id=upload_batch_id,
            )
        )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_scoped_count_returns_images(sqlite_session: AsyncSession) -> None:
    from agent.tools.element_data_tools import _get_element_image_count

    case = await _create_case(sqlite_session)
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="ESCAPE",
        count=3,
        upload_batch_id="batch-1",
    )

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ), patch("agent.tools.element_data_tools.logger.warning") as mock_warning:
        count = await _get_element_image_count(
            str(case.id),
            "ESCAPE",
            upload_batch_id="batch-1",
        )

    assert count == 3
    mock_warning.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_scoped_count_zero_unscoped_has_images(sqlite_session: AsyncSession) -> None:
    from agent.tools.element_data_tools import _get_element_image_count

    case = await _create_case(sqlite_session)
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="PLACA_SOLAR",
        count=2,
        upload_batch_id=None,
    )

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ):
        count = await _get_element_image_count(
            str(case.id),
            "PLACA_SOLAR",
            upload_batch_id="missing-batch",
        )

    assert count == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_both_counts_zero(sqlite_session: AsyncSession) -> None:
    from agent.tools.element_data_tools import _get_element_image_count

    case = await _create_case(sqlite_session)

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ):
        count = await _get_element_image_count(
            str(case.id),
            "MANILLAR",
            upload_batch_id="missing-batch",
        )

    assert count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_logging_on_fallback(sqlite_session: AsyncSession) -> None:
    from agent.tools.element_data_tools import _get_element_image_count

    case = await _create_case(sqlite_session)
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="TOLDO",
        count=1,
        upload_batch_id=None,
    )

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ), patch("agent.tools.element_data_tools.logger.warning") as mock_warning:
        count = await _get_element_image_count(
            str(case.id),
            "TOLDO",
            upload_batch_id="scoped-batch",
        )

    assert count == 1
    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[0] == "element_image_count_batch_scope_mismatch"
    assert mock_warning.call_args.kwargs["extra"] == {
        "case_id": str(case.id),
        "element_code": "TOLDO",
        "upload_batch_id": "scoped-batch",
        "scoped_count": 0,
        "unscoped_count": 1,
        "fallback_used": True,
        "message": "Using unscoped fallback count - images may have been uploaded before batch scope opened",
    }


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("scoped_count", "unscoped_count", "upload_batch_id", "expected_count", "expect_warning"),
    [
        pytest.param(3, 2, "batch-1", 3, False, id="scoped-hit-returns-scoped"),
        pytest.param(0, 3, "batch-1", 3, True, id="fallback-returns-unscoped"),
        pytest.param(0, 0, "batch-1", 0, False, id="both-zero-returns-zero"),
        pytest.param(0, 3, None, 3, False, id="no-batch-id-returns-direct-count"),
    ],
)
async def test_get_case_image_count_handles_batch_scope_fallback(
    sqlite_session: AsyncSession,
    scoped_count: int,
    unscoped_count: int,
    upload_batch_id: str | None,
    expected_count: int,
    expect_warning: bool,
) -> None:
    from agent.tools.element_data_tools import _get_case_image_count

    case = await _create_case(sqlite_session)

    if scoped_count:
        await _seed_case_images(
            sqlite_session,
            case_id=case.id,
            element_code=None,
            count=scoped_count,
            upload_batch_id=upload_batch_id,
        )

    extra_unscoped_count = max(unscoped_count - scoped_count, 0)
    if extra_unscoped_count:
        await _seed_case_images(
            sqlite_session,
            case_id=case.id,
            element_code=None,
            count=extra_unscoped_count,
            upload_batch_id=None,
        )

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ), patch("agent.tools.element_data_tools.logger.warning") as mock_warning:
        count = await _get_case_image_count(
            str(case.id),
            upload_batch_id=upload_batch_id,
        )

    assert count == expected_count
    if expect_warning:
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[0] == "base_docs_batch_scope_mismatch"
        assert mock_warning.call_args.kwargs["extra"] == {
            "case_id": str(case.id),
            "upload_batch_id": upload_batch_id,
            "scoped_count": 0,
            "unscoped_count": expected_count,
            "fallback_used": True,
            "message": "Using unscoped fallback count for base docs - images may have been uploaded before batch scope opened",
        }
    else:
        mock_warning.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_case_image_count_excludes_element_images(sqlite_session: AsyncSession) -> None:
    from agent.tools.element_data_tools import _get_case_image_count

    case = await _create_case(sqlite_session)
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="ESCAPE",
        count=2,
        upload_batch_id="batch-1",
    )
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="MANILLAR",
        count=1,
        upload_batch_id=None,
    )

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ), patch("agent.tools.element_data_tools.logger.warning") as mock_warning:
        count = await _get_case_image_count(
            str(case.id),
            upload_batch_id="batch-1",
        )

    assert count == 0
    mock_warning.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_confirmar_fotos_elemento_advances_after_receiving_images(
    sqlite_session: AsyncSession,
) -> None:
    import agent.tools.element_data_tools as element_data_tools

    case = await _create_case(sqlite_session)
    await _seed_case_images(
        sqlite_session,
        case_id=case.id,
        element_code="ESCAPE",
        count=2,
        upload_batch_id=None,
    )

    element_data_tools._photos_confirmed_this_turn.clear()

    state = {
        "conversation_id": "conv-fallback",
        "fsm_state": {
            "case_collection": {
                "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                "case_id": str(case.id),
                "category_id": str(uuid.uuid4()),
                "element_codes": ["ESCAPE", "MANILLAR"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {
                    "ESCAPE": "pending_photos",
                    "MANILLAR": "pending_photos",
                },
            }
        },
    }
    case_state = state["fsm_state"]["case_collection"]

    batch_service = MagicMock()
    batch_service.resolve_for_scope = AsyncMock(
        return_value=SimpleNamespace(batch_id="scoped-batch")
    )
    batch_service.finalize_for_scope = AsyncMock()

    mock_element = MagicMock()
    mock_element.id = uuid.uuid4()
    mock_element.name = "Escape"

    with patch(
        "agent.tools.element_data_tools.get_async_session",
        new=_make_session_context(sqlite_session),
    ), patch(
        "agent.tools.element_data_tools.get_current_state",
        return_value=state,
    ), patch(
        "agent.tools.element_data_tools.get_case_fsm_state",
        return_value=case_state,
    ), patch(
        "agent.tools.element_data_tools.get_current_step",
        return_value=CollectionStep.COLLECT_ELEMENT_DATA,
    ), patch(
        "agent.tools.element_data_tools.get_current_element_code",
        return_value="ESCAPE",
    ), patch(
        "agent.tools.element_data_tools.get_element_phase",
        return_value="photos",
    ), patch(
        "agent.tools.element_data_tools.get_case_image_batch_service",
        return_value=batch_service,
    ), patch(
        "agent.tools.element_data_tools.get_settings",
        return_value=SimpleNamespace(EXPEDIENTE_V2_ENABLED=True),
    ), patch(
        "agent.tools.element_data_tools._get_element_by_code",
        new=AsyncMock(return_value=mock_element),
    ), patch(
        "agent.tools.element_data_tools._get_required_fields_for_element",
        new=AsyncMock(return_value=[]),
    ), patch(
        "agent.tools.element_data_tools._update_case_element_data",
        new=AsyncMock(),
    ):
        result = await element_data_tools.confirmar_fotos_elemento.ainvoke({})

    assert result["success"] is True
    assert result["photos_confirmed"] is True
    assert result["element_complete"] is True
    assert result["all_elements_complete"] is False
    assert result["current_element_index"] == 1
    assert result["next_element"] == "MANILLAR"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_intro_is_injected_on_first_expediente_turn() -> None:
    node = ExpedienteModeNode()
    intro_message = build_expediente_opening_overview()
    state = cast(ConversationState, {
        "conversation_id": "conv-intro",
        "mode_context": cast(Any, {
            "case_id": str(uuid.uuid4()),
            "expediente_sub_mode": "collect_element_data",
            "current_element_index": 0,
            "element_phase": "data",
            "expediente_intro_sent": False,
            "expediente_intro_message": intro_message,
        }),
    })

    with patch.object(
        node,
        "_handle_element_data",
        new=AsyncMock(return_value={"ai_response": "Ahora mandame las fotos.", "mode_context": {}}),
    ):
        result = await node._process_message("hola", state)

    assert result["ai_response"].startswith(intro_message)
    assert result["mode_context"]["expediente_intro_sent"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_enviar_imagenes_ejemplo_soft_blocks_duplicate_sends() -> None:
    state = {
        "conversation_id": "conv-images",
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "images_shown_for_elements": ["ESCAPE"],
        },
    }

    _clear_element_images_sent_this_turn()
    try:
        set_current_state_for_image_tools(state)
        with patch("agent.tools.image_tools.get_element_service") as mock_service:
            result = await enviar_imagenes_ejemplo.ainvoke(
                {
                    "tipo": "elemento",
                    "codigo_elemento": "escape",
                    "categoria": "motos-part",
                }
            )
    finally:
        clear_image_tools_state()
        _clear_element_images_sent_this_turn()

    assert result["success"] is True
    assert result["already_shown"] is True
    assert result["images_already_shown"] is True
    assert result["element_code"] == "ESCAPE"
    assert "ya se mostraron durante el presupuesto" in result["message"]
    mock_service.assert_not_called()
