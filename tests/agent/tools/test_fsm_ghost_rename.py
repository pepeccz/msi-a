"""
RED-phase tests for fix-element-data-tools-fsm-state — Ghost function rename.

Bug: `element_data_tools.py` contains 7 calls to `_update_fsm_state()` and
4 calls to `_transition_to_step()`, NEITHER of which exists anywhere in the
codebase. This causes a NameError at runtime whenever any of those tools
executes the affected code paths.

The correct functions already exist in the same module:
- `_build_case_update(fsm_state, updates) -> dict`  (line 126)
- `_set_collection_step(fsm_state, step) -> dict`   (line 145)

These tests document the desired behavior and FAIL today (RED phase).
They will pass in Phase 2 (GREEN) after the ghost calls are replaced.

Tasks covered: 1.1, 1.2, 1.3 from the SDD tasks artifact.
"""

from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agent.tools.element_data_tools as edt_module


# ---------------------------------------------------------------------------
# T1 — `_update_fsm_state` does NOT exist (confirms the bug)
# ---------------------------------------------------------------------------


class TestGhostFunctionAbsence:
    """
    T1 — Confirm the naming bug: `_update_fsm_state` should NOT exist as a
    name in the `element_data_tools` module namespace.

    This test PASSES today (the function is absent) which confirms the bug is
    real. The complementary test T3 is the one that FAILS today.
    """

    def test_update_fsm_state_does_not_exist_in_module(self):
        """
        _update_fsm_state is NOT defined in element_data_tools.
        Its presence would mean the rename already happened.
        This test is a sentinel: if it fails, Phase 2 introduced the
        name (which would be wrong — the goal is to use _build_case_update).
        """
        assert not hasattr(edt_module, "_update_fsm_state"), (
            "_update_fsm_state must NOT be defined in element_data_tools. "
            "The 7 call sites should use _build_case_update instead."
        )

    def test_transition_to_step_does_not_exist_in_module(self):
        """
        _transition_to_step is NOT defined in element_data_tools.
        The 4 call sites should use _set_collection_step instead.
        """
        assert not hasattr(edt_module, "_transition_to_step"), (
            "_transition_to_step must NOT be defined in element_data_tools. "
            "The ~4 call sites should use _set_collection_step instead."
        )


# ---------------------------------------------------------------------------
# T2 — `_build_case_update` EXISTS and has the correct semantics
# ---------------------------------------------------------------------------


class TestBuildCaseUpdateExists:
    """
    T2 — `_build_case_update` is present, callable, and returns a dict with
    ``case_collection`` key (shallow-merge semantics). This test passes today
    and documents the contract that the renamed call sites must honour.
    """

    def test_build_case_update_is_callable(self):
        """_build_case_update must be defined and callable."""
        assert hasattr(edt_module, "_build_case_update"), (
            "_build_case_update must be defined in element_data_tools."
        )
        assert callable(edt_module._build_case_update)

    def test_build_case_update_returns_case_collection_key(self):
        """
        Given any fsm_state dict and an updates dict, _build_case_update must
        return a dict with a 'case_collection' key containing the merged data.

        This is the contract that each of the 7 ghost call sites must satisfy.
        """
        fsm_state = {"case_collection": {"element_phase": "photos", "retries": 0}}
        updates = {"element_phase": "data"}

        result = edt_module._build_case_update(fsm_state, updates)

        assert isinstance(result, dict), "Must return a dict."
        assert "case_collection" in result, "Must contain 'case_collection' key."
        inner = result["case_collection"]
        assert inner["element_phase"] == "data", "Updates must override existing keys."
        assert inner.get("retries") == 0, "Existing keys not in updates must survive."

    def test_build_case_update_empty_updates_is_noop(self):
        """
        Given an empty updates dict, _build_case_update must return the same
        case_collection as the input (no data loss).
        """
        fsm_state = {"case_collection": {"step": "collect_element_data"}}
        result = edt_module._build_case_update(fsm_state, {})

        assert result["case_collection"] == {"step": "collect_element_data"}

    def test_set_collection_step_is_callable(self):
        """_set_collection_step must be defined and callable."""
        assert hasattr(edt_module, "_set_collection_step"), (
            "_set_collection_step must be defined in element_data_tools."
        )
        assert callable(edt_module._set_collection_step)


# ---------------------------------------------------------------------------
# T3 — `confirmar_fotos_elemento` does NOT raise NameError (FAILS today)
# ---------------------------------------------------------------------------


def _make_case_id() -> str:
    return str(uuid.uuid4())


def _make_mode_context(
    case_id: str,
    element_codes: list[str] | None = None,
    element_phase: str = "photos",
    current_element_index: int = 0,
) -> dict:
    """Build a realistic CaseCollectionState-like mode_context dict."""
    return {
        "step": "collect_element_data",
        "case_id": case_id,
        "category_id": str(uuid.uuid4()),
        "category_slug": "motos-part",
        "element_codes": element_codes or ["ESCAPE"],
        "current_element_index": current_element_index,
        "element_phase": element_phase,
        "element_data_status": {},
        "base_docs_received": False,
        "base_doc_descriptions": [],
    }


def _make_conversation_state(case_id: str, element_codes: list[str]) -> dict:
    """Build a minimal ConversationState-like dict with EXPEDIENTE_MODE active."""
    return {
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": _make_mode_context(case_id, element_codes),
        "fsm_state": None,
    }


def _build_element_mock(code: str, name: str) -> MagicMock:
    """Return a minimal ORM-like Element mock."""
    element = MagicMock()
    element.id = uuid.uuid4()
    element.code = code
    element.name = name
    return element


def _build_session_mock(
    element: MagicMock,
    required_fields: list[MagicMock] | None = None,
    case: MagicMock | None = None,
) -> AsyncMock:
    """
    Build an async session mock that returns the given element from DB queries
    and the provided required_fields (empty list = no fields = element has none).

    With EXPEDIENTE_V2_ENABLED=False, confirmar_fotos_elemento() makes these
    session.execute() calls in order (each helper opens its OWN session via
    get_async_session(), so side_effect fires once per call):

      1. _get_element_image_count  → scalar()           → int (image count)
      2. _get_element_by_code      → scalar_one_or_none → Element | None
      3. _get_required_fields_for_element → scalars().all() → list[Field]
      4. _update_case_element_data → scalar_one_or_none → CaseElementData | None
    """
    required_fields = required_fields or []

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    # Call 1: _get_element_image_count — SELECT count() → scalar() → 3
    scalar_result_images = MagicMock()
    scalar_result_images.scalar = MagicMock(return_value=3)  # 3 images

    # Call 2: _get_element_by_code — SELECT Element → scalar_one_or_none → element
    scalar_result_element = MagicMock()
    scalar_result_element.scalar_one_or_none = MagicMock(return_value=element)

    # Call 3: _get_required_fields_for_element — SELECT fields → scalars().all()
    scalars_result_fields = MagicMock()
    scalars_result_fields.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=required_fields))
    )

    # Call 4: _update_case_element_data — SELECT CaseElementData → scalar_one_or_none → None
    # (None is fine here — the function handles the no-record case gracefully)
    scalar_result_case_element_data = MagicMock()
    scalar_result_case_element_data.scalar_one_or_none = MagicMock(return_value=None)

    mock_session.execute = AsyncMock(
        side_effect=[
            scalar_result_images,  # 1. image count
            scalar_result_element,  # 2. Element lookup
            scalars_result_fields,  # 3. ElementRequiredField lookup
            scalar_result_case_element_data,  # 4. CaseElementData update lookup
        ]
    )

    return mock_session


class TestConfirmarFotosElementoNoNameError:
    """
    T3 — `confirmar_fotos_elemento` must NOT raise NameError when called with
    mock DB dependencies that simulate 3 images and usuario_confirma=True.

    THIS TEST FAILS TODAY (RED phase) because line 1561 calls `_update_fsm_state`
    which is not defined, raising NameError at runtime.

    After Phase 2 (GREEN), the call sites are renamed to _build_case_update and
    this test passes.
    """

    @pytest.fixture
    def case_id(self) -> str:
        return _make_case_id()

    @pytest.fixture
    def element(self) -> MagicMock:
        return _build_element_mock("ESCAPE", "Escape homologado")

    @pytest.fixture
    def required_field(self) -> MagicMock:
        """A single required field so element_phase advances to 'data'."""
        field = MagicMock()
        field.id = uuid.uuid4()
        field.field_key = "material"
        field.field_label = "Material del escape"
        field.field_type = "select"
        field.is_required = True
        field.options = ["acero", "titanio", "aluminio"]
        field.example = None
        field.instruction = "¿De qué material es el escape?"
        field.condition_field_id = None
        field.condition_operator = None
        field.condition_value = None
        field.display_order = 1
        return field

    @pytest.mark.asyncio
    async def test_confirmar_fotos_no_nameerror_with_required_fields(
        self, case_id, element, required_field
    ):
        """
        Given:  A realistic EXPEDIENTE_MODE state with ESCAPE as the current
                element, 3 images uploaded, and a required field defined.
        When:   confirmar_fotos_elemento(usuario_confirma=True) is called.
        Then:   No NameError is raised.
                The result is a dict (not an exception).

        BUG: Today this raises NameError at line 1561 because `_update_fsm_state`
        does not exist. The fix (Phase 2) renames it to `_build_case_update`.
        """
        conversation_state = _make_conversation_state(case_id, ["ESCAPE"])
        session_mock = _build_session_mock(element, [required_field])

        with (
            patch.object(
                edt_module,
                "_get_mode_context",
                return_value=MagicMock(
                    **{
                        "get.side_effect": lambda key, *args: {
                            "step": "collect_element_data",
                            "case_id": case_id,
                            "category_id": str(uuid.uuid4()),
                            "category_slug": "motos-part",
                            "element_codes": ["ESCAPE"],
                            "current_element_index": 0,
                            "element_phase": "photos",
                            "element_data_status": {},
                            "base_docs_received": False,
                            "base_doc_descriptions": [],
                        }.get(key, args[0] if args else None),
                    }
                ),
            ),
            patch(
                "agent.tools.element_data_tools.get_current_state",
                return_value={
                    "current_mode": "EXPEDIENTE_MODE",
                    "mode_context": _make_mode_context(case_id, ["ESCAPE"]),
                    "fsm_state": None,
                },
            ),
            patch(
                "agent.tools.element_data_tools.get_async_session",
                return_value=session_mock,
            ),
            patch(
                "agent.tools.element_data_tools.get_settings",
                return_value=MagicMock(
                    EXPEDIENTE_V2_ENABLED=False,
                    ENABLE_LLM_VARIANT_INTERPRETATION=True,
                ),
            ),
            patch(
                "agent.tools.element_data_tools._get_current_step_from_context",
                return_value=edt_module.CollectionStep.COLLECT_ELEMENT_DATA,
            ),
        ):
            # Access the underlying coroutine of the @tool-wrapped function
            func = edt_module.confirmar_fotos_elemento.coroutine

            # This should NOT raise NameError — but it does today (RED)
            result = await func(usuario_confirma=True)

        # If we reach here (after Phase 2), assert the expected shape
        assert isinstance(result, dict), (
            "confirmar_fotos_elemento must return a dict, not raise an exception."
        )
        assert result.get("success") is True, f"Expected success=True, got: {result}"

    @pytest.mark.asyncio
    async def test_confirmar_fotos_result_has_element_phase_data(
        self, case_id, element, required_field
    ):
        """
        Given:  Confirmed photos + an element that has required fields.
        When:   confirmar_fotos_elemento() succeeds (after Phase 2 fix).
        Then:   result['element_phase'] == 'data' (advanced from 'photos').

        This documents REQ-2: Successful photo confirmation.
        """
        conversation_state = _make_conversation_state(case_id, ["ESCAPE"])
        session_mock = _build_session_mock(element, [required_field])

        with (
            patch.object(
                edt_module,
                "_get_mode_context",
                return_value=MagicMock(
                    **{
                        "get.side_effect": lambda key, *args: {
                            "step": "collect_element_data",
                            "case_id": case_id,
                            "category_id": str(uuid.uuid4()),
                            "category_slug": "motos-part",
                            "element_codes": ["ESCAPE"],
                            "current_element_index": 0,
                            "element_phase": "photos",
                            "element_data_status": {},
                            "base_docs_received": False,
                            "base_doc_descriptions": [],
                        }.get(key, args[0] if args else None),
                    }
                ),
            ),
            patch(
                "agent.tools.element_data_tools.get_current_state",
                return_value={
                    "current_mode": "EXPEDIENTE_MODE",
                    "mode_context": _make_mode_context(case_id, ["ESCAPE"]),
                    "fsm_state": None,
                },
            ),
            patch(
                "agent.tools.element_data_tools.get_async_session",
                return_value=session_mock,
            ),
            patch(
                "agent.tools.element_data_tools.get_settings",
                return_value=MagicMock(
                    EXPEDIENTE_V2_ENABLED=False,
                    ENABLE_LLM_VARIANT_INTERPRETATION=True,
                ),
            ),
            patch(
                "agent.tools.element_data_tools._get_current_step_from_context",
                return_value=edt_module.CollectionStep.COLLECT_ELEMENT_DATA,
            ),
        ):
            func = edt_module.confirmar_fotos_elemento.coroutine
            result = await func(usuario_confirma=True)

        assert isinstance(result, dict)
        assert result.get("element_phase") == "data", (
            "After confirming photos on an element with required fields, "
            "element_phase must advance to 'data'. "
            f"Got result keys: {list(result.keys())}"
        )
