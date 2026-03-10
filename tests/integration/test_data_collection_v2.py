"""
Integration tests: Data collection flow (TASK 6.4).

Tests the element data collection pipeline with mocked DB dependencies.

Covers:
  REQ-COLLECT-1  Single field collected, remaining pending fields returned
  REQ-COLLECT-2  All fields collected → auto-complete signal
  REQ-COLLECT-4  Conditional fields respected (skipped when condition not met)
  REQ-COLLECT-5  DB-driven: new field in DB automatically works
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from database.models import (
    Base,
    Case,
    CaseElementData,
    Element,
    ElementRequiredField,
    User,
    VehicleCategory,
)


# ─────────────────────────────────────────────────────────────────────────────
# SQLite in-memory engine
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def sqlite_engine():
    """SQLite in-memory engine with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def sqlite_session(sqlite_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh AsyncSession backed by SQLite in-memory."""
    factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


def _make_session_context(session: AsyncSession):
    """Return context manager always yielding the given session."""

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


# ─────────────────────────────────────────────────────────────────────────────
# DB seed helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _create_category(session: AsyncSession) -> VehicleCategory:
    cat = VehicleCategory(
        name="Autocaravanas",
        slug="aseicars",
        client_type="particular",
        description="Test category",
        is_active=True,
        sort_order=1,
    )
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def _create_case(session: AsyncSession) -> Case:
    user = User(phone=f"+346{uuid.uuid4().int % 100000000:08d}")
    session.add(user)
    await session.flush()
    case = Case(
        conversation_id=f"integ-{uuid.uuid4().hex[:8]}",
        user_id=user.id,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def _create_element_with_fields(
    session: AsyncSession,
    category_id: uuid.UUID,
    element_code: str,
    field_specs: list[dict],  # [{"key": str, "label": str, "required": bool, "sort_order": int}]
) -> tuple[Element, list[ElementRequiredField]]:
    """Create an Element with associated ElementRequiredField rows."""
    element = Element(
        category_id=category_id,
        code=element_code,
        name=f"Element {element_code}",
        description="Test element",
        is_active=True,
        sort_order=1,
    )
    session.add(element)
    await session.flush()

    fields = []
    for spec in field_specs:
        field = ElementRequiredField(
            element_id=element.id,
            field_key=spec["key"],
            field_label=spec.get("label", spec["key"]),
            field_type=spec.get("type", "text"),
            is_required=spec.get("required", True),
            sort_order=spec.get("sort_order", 1),
            is_active=True,
            condition_field_id=spec.get("condition_field_id"),
            condition_operator=spec.get("condition_operator"),
            condition_value=spec.get("condition_value"),
        )
        session.add(field)
        fields.append(field)

    await session.commit()
    await session.refresh(element)
    return element, fields


async def _seed_case_element_data(
    session: AsyncSession,
    case_id: uuid.UUID,
    element_code: str,
    status: str = "pending_data",
    field_values: dict | None = None,
) -> CaseElementData:
    ced = CaseElementData(
        case_id=case_id,
        element_code=element_code,
        status=status,
        field_values=field_values or {},
    )
    session.add(ced)
    await session.commit()
    await session.refresh(ced)
    return ced


# ─────────────────────────────────────────────────────────────────────────────
# REQ-COLLECT-1: Single field collection → pending_fields returned
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_field_collected_remaining_returned(sqlite_session):
    """
    REQ-COLLECT-1: After saving 1 field, get_pending_fields returns the other 4.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    # Create element with 5 fields (simulating PLACA_SOLAR_REG_INT)
    field_specs = [
        {"key": "marca_placa", "label": "Marca placa", "sort_order": 1},
        {"key": "marca_regulador", "label": "Marca regulador", "sort_order": 2},
        {"key": "modelo_regulador", "label": "Modelo regulador", "sort_order": 3},
        {"key": "contrasena_hom", "label": "Contraseña homologación", "sort_order": 4},
        {"key": "ubicacion_regulador", "label": "Ubicación regulador", "sort_order": 5},
    ]
    element, fields = await _create_element_with_fields(
        sqlite_session, category.id, "PLACA_SOLAR_REG_INT", field_specs
    )

    # Seed CaseElementData with 1 field already collected
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "PLACA_SOLAR_REG_INT",
        status="pending_data",
        field_values={"marca_placa": "SOLARFAM"},
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "PLACA_SOLAR_REG_INT", str(category.id)
        )

    # Should return 4 remaining fields (not marca_placa, which is collected)
    pending_keys = [f.field_key for f in pending]
    assert "marca_placa" not in pending_keys
    assert len(pending) == 4
    assert "marca_regulador" in pending_keys
    assert "modelo_regulador" in pending_keys
    assert "contrasena_hom" in pending_keys
    assert "ubicacion_regulador" in pending_keys


@pytest.mark.asyncio
async def test_record_field_value_updates_jsonb(sqlite_session):
    """
    REQ-COLLECT-1: record_field_value merges field into CaseElementData.field_values.
    """
    case = await _create_case(sqlite_session)
    await _seed_case_element_data(
        sqlite_session, case.id, "PLACA_SOLAR_REG_INT", "pending_data"
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        await svc.record_field_value(
            str(case.id), "PLACA_SOLAR_REG_INT", "marca_placa", "SOLARFAM"
        )

    # Verify the DB update
    result = await sqlite_session.execute(
        select(CaseElementData)
        .where(CaseElementData.case_id == case.id)
        .where(CaseElementData.element_code == "PLACA_SOLAR_REG_INT")
    )
    ced = result.scalar_one_or_none()
    assert ced is not None
    assert ced.field_values.get("marca_placa") == "SOLARFAM"


@pytest.mark.asyncio
async def test_record_field_value_merges_not_replaces(sqlite_session):
    """
    REQ-COLLECT-1: record_field_value merges into existing dict (upsert semantics).
    """
    case = await _create_case(sqlite_session)
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "PLACA_SOLAR_REG_INT",
        "pending_data",
        field_values={"marca_placa": "SOLARFAM"},
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        await svc.record_field_value(
            str(case.id), "PLACA_SOLAR_REG_INT", "marca_regulador", "VICTRON"
        )

    result = await sqlite_session.execute(
        select(CaseElementData)
        .where(CaseElementData.case_id == case.id)
        .where(CaseElementData.element_code == "PLACA_SOLAR_REG_INT")
    )
    ced = result.scalar_one_or_none()
    # Both fields should exist
    assert ced.field_values.get("marca_placa") == "SOLARFAM"
    assert ced.field_values.get("marca_regulador") == "VICTRON"


# ─────────────────────────────────────────────────────────────────────────────
# REQ-COLLECT-2: All fields collected → auto-complete
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_fields_provided_marks_element_complete(sqlite_session):
    """
    REQ-COLLECT-2: When all 5 required fields are in field_values,
    mark_element_complete() transitions CaseElementData.status to 'completed'.
    """
    case = await _create_case(sqlite_session)
    # Seed with 4/5 fields already collected
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "PLACA_SOLAR_REG_INT",
        "pending_data",
        field_values={
            "marca_placa": "SOLARFAM",
            "marca_regulador": "VICTRON",
            "modelo_regulador": "SmartSolar 100/30",
            "contrasena_hom": "AB123",
        },
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()

        # Add the 5th field
        await svc.record_field_value(
            str(case.id), "PLACA_SOLAR_REG_INT", "ubicacion_regulador", "bajo_asiento"
        )

        # Now mark complete
        await svc.mark_element_complete(str(case.id), "PLACA_SOLAR_REG_INT")

    result = await sqlite_session.execute(
        select(CaseElementData)
        .where(CaseElementData.case_id == case.id)
        .where(CaseElementData.element_code == "PLACA_SOLAR_REG_INT")
    )
    ced = result.scalar_one_or_none()
    assert ced is not None
    assert ced.status == "completed"
    assert ced.data_completed_at is not None


@pytest.mark.asyncio
async def test_mark_element_complete_idempotent(sqlite_session):
    """
    REQ-COLLECT-2: mark_element_complete() is idempotent — calling it twice
    does not raise and status remains 'completed'.
    """
    case = await _create_case(sqlite_session)
    await _seed_case_element_data(
        sqlite_session, case.id, "PLACA_SOLAR_REG_INT", "completed"
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        # Should not raise
        await svc.mark_element_complete(str(case.id), "PLACA_SOLAR_REG_INT")
        await svc.mark_element_complete(str(case.id), "PLACA_SOLAR_REG_INT")

    result = await sqlite_session.execute(
        select(CaseElementData)
        .where(CaseElementData.case_id == case.id)
        .where(CaseElementData.element_code == "PLACA_SOLAR_REG_INT")
    )
    ced = result.scalar_one_or_none()
    assert ced.status == "completed"


@pytest.mark.asyncio
async def test_all_required_collected_flag_when_all_done(sqlite_session):
    """
    REQ-COLLECT-2: ElementState.pending_fields is empty when all 5 fields collected.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    field_specs = [
        {"key": "marca_placa", "label": "Marca placa", "sort_order": 1},
        {"key": "marca_regulador", "label": "Marca regulador", "sort_order": 2},
        {"key": "modelo_regulador", "label": "Modelo regulador", "sort_order": 3},
        {"key": "contrasena_hom", "label": "Contraseña", "sort_order": 4},
        {"key": "ubicacion_regulador", "label": "Ubicación", "sort_order": 5},
    ]
    await _create_element_with_fields(
        sqlite_session, category.id, "PLACA_SOLAR_REG_INT", field_specs
    )

    # All 5 fields collected
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "PLACA_SOLAR_REG_INT",
        "pending_data",
        field_values={
            "marca_placa": "SOLARFAM",
            "marca_regulador": "VICTRON",
            "modelo_regulador": "SmartSolar 100/30",
            "contrasena_hom": "AB123",
            "ubicacion_regulador": "bajo_asiento",
        },
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "PLACA_SOLAR_REG_INT", str(category.id)
        )

    assert len(pending) == 0


# ─────────────────────────────────────────────────────────────────────────────
# REQ-COLLECT-4: Conditional fields respected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conditional_field_skipped_when_condition_not_met(sqlite_session):
    """
    REQ-COLLECT-4: A field with condition_operator='equals', condition_value='si'
    is NOT returned in pending_fields when the anchor field value is 'no'.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    # Create element with:
    #  field_A: unconditional
    #  field_B: conditional (shown only when field_A == "si")
    element = Element(
        category_id=category.id,
        code="TEST_ELEMENT",
        name="Test Element",
        is_active=True,
        sort_order=1,
    )
    sqlite_session.add(element)
    await sqlite_session.flush()

    field_a = ElementRequiredField(
        element_id=element.id,
        field_key="tiene_certificado",
        field_label="¿Tiene certificado?",
        field_type="boolean",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    sqlite_session.add(field_a)
    await sqlite_session.flush()

    field_b = ElementRequiredField(
        element_id=element.id,
        field_key="numero_certificado",
        field_label="Número de certificado",
        field_type="text",
        is_required=True,
        sort_order=2,
        is_active=True,
        condition_field_id=field_a.id,
        condition_operator="equals",
        condition_value="si",
    )
    sqlite_session.add(field_b)
    await sqlite_session.commit()

    # Seed CaseElementData with field_A = "no"
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "TEST_ELEMENT",
        "pending_data",
        field_values={"tiene_certificado": "no"},
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "TEST_ELEMENT", str(category.id)
        )

    # field_B should NOT be in pending (condition not met)
    pending_keys = [f.field_key for f in pending]
    assert "numero_certificado" not in pending_keys
    # field_A already collected, so no pending required fields
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_conditional_field_appears_when_condition_met(sqlite_session):
    """
    REQ-COLLECT-4: Conditional field IS returned when anchor field == condition_value.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    element = Element(
        category_id=category.id,
        code="TEST_ELEMENT_2",
        name="Test Element 2",
        is_active=True,
        sort_order=1,
    )
    sqlite_session.add(element)
    await sqlite_session.flush()

    field_a = ElementRequiredField(
        element_id=element.id,
        field_key="tiene_certificado",
        field_label="¿Tiene certificado?",
        field_type="boolean",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    sqlite_session.add(field_a)
    await sqlite_session.flush()

    field_b = ElementRequiredField(
        element_id=element.id,
        field_key="numero_certificado",
        field_label="Número de certificado",
        field_type="text",
        is_required=True,
        sort_order=2,
        is_active=True,
        condition_field_id=field_a.id,
        condition_operator="equals",
        condition_value="si",
    )
    sqlite_session.add(field_b)
    await sqlite_session.commit()

    # Seed with field_A = "si" — condition IS met
    await _seed_case_element_data(
        sqlite_session,
        case.id,
        "TEST_ELEMENT_2",
        "pending_data",
        field_values={"tiene_certificado": "si"},
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "TEST_ELEMENT_2", str(category.id)
        )

    # field_B should appear in pending (condition met)
    pending_keys = [f.field_key for f in pending]
    assert "numero_certificado" in pending_keys


# ─────────────────────────────────────────────────────────────────────────────
# REQ-COLLECT-5: DB-driven — new field works automatically
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_db_field_automatically_appears_in_pending(sqlite_session):
    """
    REQ-COLLECT-5: A new ElementRequiredField added to the DB for an element
    appears in get_pending_fields without any code change.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    # Create element with 1 initial field
    field_specs_initial = [
        {"key": "marca_placa", "label": "Marca placa", "sort_order": 1},
    ]
    element, initial_fields = await _create_element_with_fields(
        sqlite_session, category.id, "DYNAMIC_ELEMENT", field_specs_initial
    )

    await _seed_case_element_data(
        sqlite_session, case.id, "DYNAMIC_ELEMENT", "pending_data"
    )

    # Add a NEW field to the DB dynamically (simulating admin action)
    new_field = ElementRequiredField(
        element_id=element.id,
        field_key="nuevo_campo",
        field_label="Nuevo campo añadido",
        field_type="text",
        is_required=True,
        sort_order=2,
        is_active=True,
    )
    sqlite_session.add(new_field)
    await sqlite_session.commit()
    # Explicitly expire the element's loaded relationships so the service
    # re-fetches required_fields from DB (expire_on_commit=False is set on factory).
    # Use expire on the element only to avoid triggering lazy loads on other objects.
    sqlite_session.expire(element, ["required_fields"])

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "DYNAMIC_ELEMENT", str(category.id)
        )

    pending_keys = [f.field_key for f in pending]
    # NEW field must appear automatically
    assert "nuevo_campo" in pending_keys
    assert "marca_placa" in pending_keys


@pytest.mark.asyncio
async def test_deactivated_field_excluded_from_pending(sqlite_session):
    """
    REQ-COLLECT-5: A field with is_active=False is NOT returned by get_pending_fields.
    This ensures DB-driven exclusion works automatically.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    element = Element(
        category_id=category.id,
        code="INACTIVE_FIELD_ELEMENT",
        name="Inactive Field Element",
        is_active=True,
        sort_order=1,
    )
    sqlite_session.add(element)
    await sqlite_session.flush()

    # Active field
    active_field = ElementRequiredField(
        element_id=element.id,
        field_key="campo_activo",
        field_label="Campo activo",
        field_type="text",
        is_required=True,
        sort_order=1,
        is_active=True,
    )
    # Inactive field (should be excluded)
    inactive_field = ElementRequiredField(
        element_id=element.id,
        field_key="campo_inactivo",
        field_label="Campo inactivo",
        field_type="text",
        is_required=True,
        sort_order=2,
        is_active=False,
    )
    sqlite_session.add(active_field)
    sqlite_session.add(inactive_field)
    await sqlite_session.commit()

    await _seed_case_element_data(
        sqlite_session, case.id, "INACTIVE_FIELD_ELEMENT", "pending_data"
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "INACTIVE_FIELD_ELEMENT", str(category.id)
        )

    pending_keys = [f.field_key for f in pending]
    assert "campo_activo" in pending_keys
    assert "campo_inactivo" not in pending_keys


# ─────────────────────────────────────────────────────────────────────────────
# Element ordering (REQ-STATE-5 / REQ-COLLECT-5)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_fields_ordered_by_sort_order(sqlite_session):
    """
    REQ-COLLECT-5: Fields are returned in sort_order ascending order.
    """
    category = await _create_category(sqlite_session)
    case = await _create_case(sqlite_session)

    field_specs = [
        {"key": "campo_3", "label": "Campo 3", "sort_order": 3},
        {"key": "campo_1", "label": "Campo 1", "sort_order": 1},
        {"key": "campo_2", "label": "Campo 2", "sort_order": 2},
    ]
    await _create_element_with_fields(
        sqlite_session, category.id, "ORDER_ELEMENT", field_specs
    )

    await _seed_case_element_data(
        sqlite_session, case.id, "ORDER_ELEMENT", "pending_data"
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        pending = await svc.get_pending_fields(
            str(case.id), "ORDER_ELEMENT", str(category.id)
        )

    keys = [f.field_key for f in pending]
    assert keys == ["campo_1", "campo_2", "campo_3"]


# ─────────────────────────────────────────────────────────────────────────────
# Multi-element progress tracking
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_element_returns_first_non_completed(sqlite_session):
    """
    REQ-COLLECT-2: get_current_element() returns the first element not completed.
    """
    case = await _create_case(sqlite_session)

    # First element: completed
    await _seed_case_element_data(
        sqlite_session, case.id, "ELEMENT_A", "completed"
    )
    # Second element: pending_data (current)
    await _seed_case_element_data(
        sqlite_session, case.id, "ELEMENT_B", "pending_data"
    )

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        current = await svc.get_current_element(
            str(case.id), ["ELEMENT_A", "ELEMENT_B"]
        )

    assert current == "ELEMENT_B"


@pytest.mark.asyncio
async def test_is_all_elements_complete_returns_true_when_all_done(sqlite_session):
    """
    REQ-COLLECT-2: is_all_elements_complete() is True only when every
    element has status='completed'.
    """
    case = await _create_case(sqlite_session)

    await _seed_case_element_data(sqlite_session, case.id, "ELEM_1", "completed")
    await _seed_case_element_data(sqlite_session, case.id, "ELEM_2", "completed")

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        all_done = await svc.is_all_elements_complete(
            str(case.id), ["ELEM_1", "ELEM_2"]
        )

    assert all_done is True


@pytest.mark.asyncio
async def test_is_all_elements_complete_returns_false_when_one_pending(sqlite_session):
    """
    REQ-COLLECT-2: is_all_elements_complete() is False when any element is not completed.
    """
    case = await _create_case(sqlite_session)

    await _seed_case_element_data(sqlite_session, case.id, "ELEM_1", "completed")
    await _seed_case_element_data(sqlite_session, case.id, "ELEM_2", "pending_data")

    with patch(
        "agent.services.element_state_service.get_async_session",
        side_effect=_make_session_context(sqlite_session),
    ), patch(
        "agent.services.element_state_service.get_settings"
    ) as mock_settings:
        mock_settings.return_value.EXPEDIENTE_V2_ENABLED = True

        from agent.services.element_state_service import ElementStateService

        svc = ElementStateService()
        all_done = await svc.is_all_elements_complete(
            str(case.id), ["ELEM_1", "ELEM_2"]
        )

    assert all_done is False
