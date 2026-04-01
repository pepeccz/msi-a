"""Smoke tests for expediente_types and expediente_validators modules."""

from __future__ import annotations

from typing import get_type_hints

from agent.utils.expediente_types import (
    ELEMENT_STATUS_COMPLETE,
    ELEMENT_STATUS_DATA_DONE,
    ELEMENT_STATUS_PENDING,
    ELEMENT_STATUS_PHOTOS_DONE,
    CaseCollectionState,
    CollectionStep,
)
from agent.utils.expediente_validators import (
    validate_cp,
    validate_dni_cif,
    validate_email,
    validate_matricula,
    validate_personal_data,
    validate_vehicle_data,
    validate_workshop_data,
    normalize_matricula,
)


class TestCollectionStep:
    """CollectionStep enum has 8 members with correct values."""

    def test_member_count(self) -> None:
        assert len(CollectionStep) == 8

    def test_member_values(self) -> None:
        expected = {
            "IDLE": "idle",
            "COLLECT_ELEMENT_DATA": "collect_element_data",
            "COLLECT_BASE_DOCS": "collect_base_docs",
            "COLLECT_PERSONAL": "collect_personal",
            "COLLECT_VEHICLE": "collect_vehicle",
            "COLLECT_WORKSHOP": "collect_workshop",
            "REVIEW_SUMMARY": "review_summary",
            "COMPLETED": "completed",
        }
        for name, value in expected.items():
            member = CollectionStep[name]
            assert member.value == value, (
                f"{name} should be {value!r}, got {member.value!r}"
            )

    def test_is_str_enum(self) -> None:
        assert isinstance(CollectionStep.IDLE, str)
        assert CollectionStep.IDLE == "idle"


class TestCaseCollectionState:
    """CaseCollectionState TypedDict has 20 keys with total=False."""

    def test_key_count(self) -> None:
        hints = get_type_hints(CaseCollectionState)
        assert len(hints) == 20, (
            f"Expected 20 keys, got {len(hints)}: {sorted(hints.keys())}"
        )

    def test_expected_keys(self) -> None:
        expected_keys = {
            "step",
            "case_id",
            "personal_data",
            "vehicle_data",
            "taller_propio",
            "taller_data",
            "category_slug",
            "category_id",
            "element_codes",
            "current_element_index",
            "element_phase",
            "element_data_status",
            "base_docs_received",
            "base_doc_descriptions",
            "received_images",
            "tariff_tier_id",
            "tariff_amount",
            "last_prompt",
            "retry_count",
            "error_message",
        }
        hints = get_type_hints(CaseCollectionState)
        assert set(hints.keys()) == expected_keys

    def test_total_false(self) -> None:
        # total=False means __required_keys__ is empty
        assert not CaseCollectionState.__required_keys__


class TestElementStatusConstants:
    """Element status constants match their string values."""

    def test_values(self) -> None:
        assert ELEMENT_STATUS_PENDING == "pending"
        assert ELEMENT_STATUS_PHOTOS_DONE == "photos_done"
        assert ELEMENT_STATUS_DATA_DONE == "data_done"
        assert ELEMENT_STATUS_COMPLETE == "complete"


class TestValidatorsImportable:
    """All 8 validators are importable and callable."""

    def test_validate_email(self) -> None:
        assert validate_email("user@example.com") is True
        assert validate_email("") is False

    def test_validate_matricula(self) -> None:
        assert validate_matricula("1234ABC") is True
        assert validate_matricula("") is False

    def test_normalize_matricula(self) -> None:
        assert normalize_matricula(" 1234 abc ") == "1234ABC"

    def test_validate_dni_cif(self) -> None:
        assert validate_dni_cif("12345678A") is True
        assert validate_dni_cif("") is False

    def test_validate_cp(self) -> None:
        assert validate_cp("28001") is True
        assert validate_cp("00000") is False

    def test_validate_personal_data_missing(self) -> None:
        is_valid, missing = validate_personal_data({})
        assert is_valid is False
        assert len(missing) > 0

    def test_validate_vehicle_data_missing(self) -> None:
        is_valid, missing = validate_vehicle_data({})
        assert is_valid is False
        assert len(missing) > 0

    def test_validate_workshop_data_none(self) -> None:
        is_valid, missing = validate_workshop_data(None)
        assert is_valid is False
        assert "datos del taller" in missing
