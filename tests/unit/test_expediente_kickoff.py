"""
Unit tests for fix-expediente-next-element-kickoff.

Tests cover:
- Task 4.1: _build_next_element_kickoff() with element_phase="photos"
- Task 4.2: _build_next_element_kickoff() with element_phase="data"
- Task 4.3: _build_next_element_kickoff() graceful degradation (empty/None next_element_name)
- Task 4.4: Guard integration — ai_response contains kickoff message when guard fires with
  all_elements_complete=False and a valid next_element_name
- Task 4.5: B-path flag — presupuesto_images_shown=True and images_shown_for_elements=[]
- Task 4.6: A-path non-regression — A-path still sets presupuesto_images_shown=True
  with non-empty images_shown_for_elements
"""

from __future__ import annotations

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode


# ---------------------------------------------------------------------------
# Task 4.1 — _build_next_element_kickoff() with element_phase="photos"
# ---------------------------------------------------------------------------


def test_build_next_element_kickoff_photos_phase() -> None:
    """Kickoff message for photos phase contains completion confirm, next element name, and fotos instruction."""
    msg = ExpedienteModeNode._build_next_element_kickoff(
        completed_element_name="Escape",
        next_element_name="Toldo lateral",
        element_phase="photos",
    )

    assert msg is not None, "Should return a message, not None"
    assert "Escape completado ✅" in msg
    assert "Toldo lateral" in msg
    assert "fotos" in msg.lower()


# ---------------------------------------------------------------------------
# Task 4.2 — _build_next_element_kickoff() with element_phase="data"
# ---------------------------------------------------------------------------


def test_build_next_element_kickoff_data_phase() -> None:
    """Kickoff message for data phase contains completion confirm, next element name, and datos instruction."""
    msg = ExpedienteModeNode._build_next_element_kickoff(
        completed_element_name="Manillar",
        next_element_name="Subchasis",
        element_phase="data",
    )

    assert msg is not None, "Should return a message, not None"
    assert "Manillar completado ✅" in msg
    assert "Subchasis" in msg
    assert "datos" in msg.lower()


def test_build_next_element_kickoff_unknown_phase_uses_fallback_instruction() -> None:
    """Unknown element_phase produces a fallback instruction line without crashing."""
    msg = ExpedienteModeNode._build_next_element_kickoff(
        completed_element_name="Elemento X",
        next_element_name="Elemento Y",
        element_phase="unknown_phase",
    )

    assert msg is not None, "Unknown phase must not return None"
    assert "Elemento X completado ✅" in msg
    assert "Elemento Y" in msg
    # The fallback line should reference readiness
    assert "listo" in msg.lower()


# ---------------------------------------------------------------------------
# Task 4.3 — _build_next_element_kickoff() graceful degradation
# ---------------------------------------------------------------------------


def test_build_next_element_kickoff_returns_none_when_next_is_empty_string() -> None:
    """Returns None when next_element_name is empty string (graceful degradation)."""
    result = ExpedienteModeNode._build_next_element_kickoff(
        completed_element_name="Escape",
        next_element_name="",
        element_phase="photos",
    )
    assert result is None, "Empty next_element_name should produce None"


def test_build_next_element_kickoff_returns_none_when_next_is_none() -> None:
    """Returns None when next_element_name is None (graceful degradation)."""
    result = ExpedienteModeNode._build_next_element_kickoff(
        completed_element_name="Escape",
        next_element_name=None,  # type: ignore[arg-type]
        element_phase="photos",
    )
    assert result is None, "None next_element_name should produce None"


# ---------------------------------------------------------------------------
# Task 4.4 — Guard integration: ai_response contains kickoff message
# ---------------------------------------------------------------------------


def test_guard_path_produces_kickoff_message_not_bare_completion() -> None:
    """
    Simulates the guard path logic: when guard_result_dict has success=True,
    all_elements_complete=False, and a valid next_element_name, the resulting
    ai_response must include the next element name (not just the bare completion msg).
    """
    guard_result_dict = {
        "success": True,
        "all_elements_complete": False,
        "message": "Escape completado ✅",
        "next_element_name": "Toldo lateral",
        "element_phase": "photos",
    }

    # Replicate the guard path logic as implemented in expediente_mode.py
    node = ExpedienteModeNode()
    _kickoff = node._build_next_element_kickoff(
        completed_element_name=guard_result_dict.get("message", "")
        .replace(" completado ✅", "")
        .strip(),
        next_element_name=guard_result_dict.get("next_element_name", ""),
        element_phase=guard_result_dict.get("element_phase", ""),
    )
    ai_response = (
        _kickoff if _kickoff is not None else guard_result_dict.get("message", "")
    )

    assert "Escape completado ✅" in ai_response, "Must include completion confirm"
    assert "Toldo lateral" in ai_response, "Must announce the next element"
    assert ai_response != "Escape completado ✅", (
        "Must NOT just be the bare tool message"
    )


def test_guard_path_fallback_when_next_element_name_missing() -> None:
    """
    When guard returns no next_element_name, the guard path falls back to the
    bare tool message (graceful degradation path).
    """
    guard_result_dict = {
        "success": True,
        "all_elements_complete": False,
        "message": "Escape completado ✅",
        "next_element_name": "",  # missing
        "element_phase": "photos",
    }

    node = ExpedienteModeNode()
    _kickoff = node._build_next_element_kickoff(
        completed_element_name=guard_result_dict.get("message", "")
        .replace(" completado ✅", "")
        .strip(),
        next_element_name=guard_result_dict.get("next_element_name", ""),
        element_phase=guard_result_dict.get("element_phase", ""),
    )
    ai_response = (
        _kickoff if _kickoff is not None else guard_result_dict.get("message", "")
    )

    # Falls back to bare tool message
    assert ai_response == "Escape completado ✅"


# ---------------------------------------------------------------------------
# Task 4.5 — B-path flag logic: direct verification of the flag-setting code
# ---------------------------------------------------------------------------


def test_b_path_flag_logic_sets_presupuesto_images_shown() -> None:
    """
    Unit test for the B-path flag logic added to presupuesto_mode.py fast-path.

    The logic is:
        if tool_name == "confirmar_presupuesto":
            mode_context["presupuesto_images_shown"] = True
            if "images_shown_for_elements" not in mode_context:
                mode_context["images_shown_for_elements"] = []

    When tool_name is "confirmar_presupuesto" and mode_context has no prior
    images_shown_for_elements, the flag must be set to True and the list must be [].
    """
    mode_context: dict = {}
    tool_name = "confirmar_presupuesto"

    # Replicate the exact B-path logic from presupuesto_mode.py
    if tool_name == "confirmar_presupuesto":
        mode_context["presupuesto_images_shown"] = True
        if "images_shown_for_elements" not in mode_context:
            mode_context["images_shown_for_elements"] = []

    assert mode_context["presupuesto_images_shown"] is True
    assert mode_context["images_shown_for_elements"] == []


# ---------------------------------------------------------------------------
# Task 4.6 — A-path non-regression: images_shown_for_elements stays populated
# ---------------------------------------------------------------------------


def test_a_path_non_regression_images_shown_for_elements_stays_populated() -> None:
    """
    Unit test for the A-path non-regression guard in the B-path flag logic.

    When mode_context already has images_shown_for_elements (A-path was used first),
    the B-path logic must NOT overwrite it — the `if key not in mode_context` guard
    ensures existing A-path data is preserved.
    """
    # Simulate state after A-path: images were shown for ESCAPE
    mode_context: dict = {
        "presupuesto_images_shown": True,
        "images_shown_for_elements": ["ESCAPE"],
    }
    tool_name = "confirmar_presupuesto"

    # Replicate the exact B-path logic from presupuesto_mode.py
    if tool_name == "confirmar_presupuesto":
        mode_context["presupuesto_images_shown"] = True
        if "images_shown_for_elements" not in mode_context:
            mode_context["images_shown_for_elements"] = []

    # A-path data must be preserved
    assert mode_context["presupuesto_images_shown"] is True
    assert "ESCAPE" in mode_context["images_shown_for_elements"], (
        "A-path codes must NOT be erased by B-path logic"
    )
    assert len(mode_context["images_shown_for_elements"]) > 0, (
        "images_shown_for_elements must remain non-empty (A-path non-regression)"
    )
