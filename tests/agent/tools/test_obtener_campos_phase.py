"""
T3 — Concern C: phase-aware fields in obtener_campos_elemento.

Spec: ObtenerCamposElementoPhaseAwareFields
  - phase="photos" → result["fields"] == []
  - phase="data"   → result["fields"] has at least one entry
  - Other keys (phase, photos_required, element_code, etc.) must be present in both cases.

Strategy: test get_element_fields() directly (the service function that owns the logic)
to avoid the complexity of patching dynamic imports inside element_data_service.py.
The tool is a thin wrapper — the assertion is on the service's return shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(field_key: str = "num_bastidor") -> MagicMock:
    """Build a minimal field mock."""
    f = MagicMock()
    f.field_key = field_key
    f.is_required = True
    f.is_collected = False
    f.to_dict = MagicMock(
        return_value={
            "field_key": field_key,
            "label": "Número de bastidor",
            "is_required": True,
            "is_collected": False,
        }
    )
    return f


def _make_el_state(phase: str, pending_fields: list | None = None) -> MagicMock:
    """Build a minimal ElementState mock for a given phase."""
    if pending_fields is None and phase == "data":
        pending_fields = [_make_field("num_bastidor")]
    elif pending_fields is None:
        pending_fields = []

    state = MagicMock()
    state.phase = phase
    state.photos_required = 2
    state.photos_confirmed_count = 0
    state.display_name = "Escape"
    state.pending_fields = pending_fields
    state.all_fields = pending_fields
    state.warnings = []
    state.to_dict = MagicMock(
        return_value={
            "phase": phase,
            "photos_required": 2,
            "photos_confirmed_count": 0,
            "pending_fields": [],
        }
    )
    return state


# ---------------------------------------------------------------------------
# Tests — target: agent.services.element_data_service.get_element_fields
# ---------------------------------------------------------------------------


class TestObtenerCamposPhaseAware:
    """
    Spec coverage: ObtenerCamposElementoPhaseAwareFields — both scenarios.
    Tests the service function get_element_fields directly.
    """

    @pytest.mark.asyncio
    async def test_phase_photos_returns_empty_fields(self):
        """
        T3 — phase=photos → result['fields'] must be an empty list.
        """
        from agent.services.element_data_service import get_element_fields

        # Even if pending_fields is non-empty, phase=photos must return fields=[]
        el_state = _make_el_state(phase="photos", pending_fields=[_make_field("some_future_field")])

        # Build a mock for the V2 service
        ess_mock = MagicMock()
        ess_mock.get_element_state = AsyncMock(return_value=el_state)

        # The FieldInfo/CollectionMode imports are dynamic in get_element_fields.
        # We need to patch the factory function AND the collection_mode dependency.
        # Since they're imported locally, we patch them at their source.
        import unittest.mock as _um

        with (
            _um.patch(
                "agent.services.element_state_service.get_element_state_service",
                return_value=ess_mock,
            ),
            _um.patch(
                "agent.services.collection_mode.CollectionMode",
                MagicMock(),
            ),
            _um.patch(
                "agent.services.collection_mode.FieldInfo",
                MagicMock(from_db_field=MagicMock(return_value=MagicMock())),
            ),
            _um.patch(
                "agent.services.collection_mode.determine_collection_mode",
                return_value=MagicMock(value="form"),
            ),
        ):
            result = await get_element_fields(
                element_code="ESCAPE",
                case_id="case-001",
                category_id="cat-001",
                element_codes=["ESCAPE"],
                mode_context={"case_id": "case-001", "category_id": "cat-001"},
            )

        assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
        assert result.get("success") is True, f"Expected success=True: {result}"
        assert result.get("fields") == [], (
            f"phase=photos → fields MUST be []. Got: {result.get('fields')!r}"
        )
        # Other required keys must be present
        for key in ("phase", "photos_required", "element_code"):
            assert key in result, f"Key '{key}' must be present in result: {result.keys()}"

    @pytest.mark.asyncio
    async def test_phase_data_returns_populated_fields(self):
        """
        T3 — phase=data → result['fields'] must contain at least one entry.
        """
        from agent.services.element_data_service import get_element_fields

        pending = [_make_field("num_bastidor")]
        el_state = _make_el_state(phase="data", pending_fields=pending)

        ess_mock = MagicMock()
        ess_mock.get_element_state = AsyncMock(return_value=el_state)

        import unittest.mock as _um

        with (
            _um.patch(
                "agent.services.element_state_service.get_element_state_service",
                return_value=ess_mock,
            ),
            _um.patch(
                "agent.services.collection_mode.CollectionMode",
                MagicMock(),
            ),
            _um.patch(
                "agent.services.collection_mode.FieldInfo",
                MagicMock(from_db_field=MagicMock(return_value=MagicMock())),
            ),
            _um.patch(
                "agent.services.collection_mode.determine_collection_mode",
                return_value=MagicMock(value="form"),
            ),
        ):
            result = await get_element_fields(
                element_code="ESCAPE",
                case_id="case-001",
                category_id="cat-001",
                element_codes=["ESCAPE"],
                mode_context={"case_id": "case-001", "category_id": "cat-001"},
            )

        assert isinstance(result, dict), f"Expected dict, got: {type(result)}"
        assert result.get("success") is True, f"Expected success=True: {result}"
        fields = result.get("fields")
        assert isinstance(fields, list), f"Expected list for fields, got: {fields!r}"
        assert len(fields) > 0, (
            f"phase=data → fields MUST have at least one entry. Got: {fields!r}"
        )
        # Other required keys must be present
        for key in ("phase", "photos_required", "element_code"):
            assert key in result, f"Key '{key}' must be present in result: {result.keys()}"
