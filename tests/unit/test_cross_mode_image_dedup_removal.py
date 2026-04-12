"""
Unit tests: Cross-Mode Image Dedup Removal (Batch 3 — SDD fix-agent-antipatterns)

Background
----------
`IMAGE_TRACKING_KEYS` in `transition_mode()` previously preserved BOTH:
    - `presupuesto_images_shown`  — intentional (sales funnel tracking)
    - `images_shown_for_elements` — BUG: blocks legitimate re-sends in new mode

After fix: `images_shown_for_elements` MUST NOT be propagated on mode transitions.
`presupuesto_images_shown` MUST still be propagated (intentional cross-mode flag).

Design Reference: AD-4 in design.md — images_shown_for_elements removal
Spec Reference:   Spec 3, Scenario "User enters EXPEDIENTE_MODE after seeing images in PRESUPUESTO_MODE"
Tasks:            3.1 [RED], 3.2 [GREEN] — conversation_state.py IMAGE_TRACKING_KEYS
"""

from __future__ import annotations

import sys
import types

# Stub heavy optional dependencies before any agent import
sys.modules.setdefault("phonenumbers", types.ModuleType("phonenumbers"))

import pytest

from agent.state.conversation_state import transition_mode


# ---------------------------------------------------------------------------
# Helper: unwrap LangGraph Overwrite wrapper
# ---------------------------------------------------------------------------


def _unwrap_mode_context(result: dict) -> dict:
    """
    Extract the actual dict from transition_mode()'s 'mode_context' value.

    transition_mode() wraps mode_context in LangGraph's Overwrite() wrapper.
    The wrapper has a `.value` attribute containing the real dict.
    Falls back to treating the value directly as a dict if no wrapper detected.
    """
    raw = result.get("mode_context")
    if raw is None:
        return {}
    # LangGraph Overwrite wrapper exposes the inner dict via .value
    if hasattr(raw, "value"):
        return raw.value or {}
    # Older / alternative Overwrite shapes
    if hasattr(raw, "data"):
        return raw.data or {}
    # Already a plain dict
    if isinstance(raw, dict):
        return raw
    return {}


def _unwrap_shared_context(result: dict) -> dict:
    """
    Extract the actual dict from a state's 'shared_context' value.

    shared_context is NOT returned by transition_mode() — it lives outside
    mode_context and is preserved by LangGraph's merge_dicts reducer.
    This helper reads shared_context from the INPUT state (not the result).
    Falls back to empty dict if absent or wrapped.
    """
    raw = result.get("shared_context")
    if raw is None:
        return {}
    if hasattr(raw, "value"):
        return raw.value or {}
    if isinstance(raw, dict):
        return raw
    return {}


# ---------------------------------------------------------------------------
# Helpers: minimal state builders
# ---------------------------------------------------------------------------


def _make_presupuesto_state_with_images_shown(
    element_code: str = "ESCAPE",
    prior_mode: str = "PRESUPUESTO_MODE",
) -> dict:
    """
    Build a minimal ConversationState-compatible dict where PRESUPUESTO_MODE
    is active and images have been shown for an element.

    This simulates the state just before a mode transition is triggered.

    After autonomous-agent-refactor (WS4):
    - presupuesto_images_shown lives in shared_context (cross-mode, never wiped)
    - images_shown_for_elements lives in mode_context (intentionally wiped on transition)
    """
    return {
        "current_mode": prior_mode,
        "mode_context": {
            "precio_comunicado": True,
            "imagenes_enviadas": True,
            "images_shown_for_elements": [element_code.upper()],
            "element_codes": [element_code.upper()],
        },
        "shared_context": {
            "presupuesto_images_shown": True,
        },
        "mode_history": [],
        "draft_contexts": {},
        "retry_state": {},
        "mode_message_count": 0,
    }


# ---------------------------------------------------------------------------
# Task 3.1 — RED tests
# These tests describe the DESIRED behaviour AFTER the fix.
# They FAIL against the current (unfixed) code because `transition_mode()`
# still carries over `images_shown_for_elements` via IMAGE_TRACKING_KEYS.
# ---------------------------------------------------------------------------


class TestImagesShownForElementsNotPropagated:
    """
    SPEC: On mode transition, `images_shown_for_elements` MUST NOT be
    present in the new mode_context.
    """

    def test_images_shown_for_elements_absent_after_transition(self) -> None:
        """
        SPEC: When PRESUPUESTO_MODE → EXPEDIENTE_MODE transition occurs,
        `images_shown_for_elements` MUST NOT appear in the returned mode_context.

        This is the primary acceptance criterion for the fix (Task 3.1/3.2).
        Will FAIL against current code (key is in IMAGE_TRACKING_KEYS).
        Will PASS after task 3.2 removes the key from IMAGE_TRACKING_KEYS.
        """
        state = _make_presupuesto_state_with_images_shown(element_code="ESCAPE")

        result = transition_mode(state, "EXPEDIENTE_MODE")
        mode_context_data = _unwrap_mode_context(result)

        assert "images_shown_for_elements" not in mode_context_data, (
            "BUG: `images_shown_for_elements` was propagated to EXPEDIENTE_MODE. "
            "This key MUST be removed from IMAGE_TRACKING_KEYS so that "
            "element images can be re-sent in a new mode context. "
            f"mode_context after transition: {mode_context_data}"
        )

    def test_images_shown_for_elements_absent_with_multiple_elements(self) -> None:
        """
        TRIANGULATION: Key absent regardless of how many elements are in the list.
        """
        state = _make_presupuesto_state_with_images_shown(element_code="ESCAPE")
        state["mode_context"]["images_shown_for_elements"] = [
            "ESCAPE",
            "SUSPENSION",
            "MANILLAR",
        ]

        result = transition_mode(state, "EXPEDIENTE_MODE")
        mode_context_data = _unwrap_mode_context(result)

        assert "images_shown_for_elements" not in mode_context_data, (
            "TRIANGULATION: `images_shown_for_elements` with multiple codes "
            "must not be propagated. Got: "
            f"{mode_context_data.get('images_shown_for_elements')}"
        )

    def test_images_shown_for_elements_absent_transitioning_to_consulta(
        self,
    ) -> None:
        """
        TRIANGULATION: Key absent regardless of target mode.
        PRESUPUESTO_MODE → CONSULTA_MODE should also not carry the key.
        """
        state = _make_presupuesto_state_with_images_shown(element_code="CARENADO")

        result = transition_mode(state, "CONSULTA_MODE")
        mode_context_data = _unwrap_mode_context(result)

        assert "images_shown_for_elements" not in mode_context_data, (
            "TRIANGULATION: `images_shown_for_elements` must not propagate "
            "to any target mode, not only EXPEDIENTE_MODE. "
            f"mode_context after transition: {mode_context_data}"
        )


class TestPresupuestoImagesShownStillPropagated:
    """
    SPEC: `presupuesto_images_shown` MUST survive mode transitions.

    After WS4 (autonomous-agent-refactor), `presupuesto_images_shown` lives in
    `shared_context` (not `mode_context`).  transition_mode() intentionally does
    NOT touch shared_context — LangGraph's merge_dicts reducer preserves it
    automatically.  These tests verify:
      1. The key is set in shared_context (not mode_context) in the input state.
      2. transition_mode() does NOT include `presupuesto_images_shown` in mode_context.
      3. transition_mode() does NOT overwrite shared_context (no shared_context key
         in the returned dict, so the reducer keeps the existing value).
    """

    def test_presupuesto_images_shown_is_still_present_after_transition(
        self,
    ) -> None:
        """
        REGRESSION GUARD: `presupuesto_images_shown` lives in shared_context and
        transition_mode() does not overwrite it (no shared_context key in result).
        """
        state = _make_presupuesto_state_with_images_shown(element_code="ESCAPE")
        # After WS4: presupuesto_images_shown is in shared_context, not mode_context
        assert state["shared_context"]["presupuesto_images_shown"] is True

        result = transition_mode(state, "EXPEDIENTE_MODE")

        # transition_mode() must NOT include shared_context in result
        # (the reducer preserves it automatically)
        assert "shared_context" not in result, (
            "REGRESSION: transition_mode() must NOT set shared_context in the "
            "returned dict — the merge_dicts reducer preserves it automatically. "
            f"result keys: {list(result.keys())}"
        )

        # presupuesto_images_shown must NOT be in mode_context (it's in shared_context)
        mode_context_data = _unwrap_mode_context(result)
        assert "presupuesto_images_shown" not in mode_context_data, (
            "presupuesto_images_shown should NOT be in mode_context after WS4 — "
            "it lives in shared_context. "
            f"mode_context after transition: {mode_context_data}"
        )

    def test_only_images_shown_for_elements_removed_presupuesto_key_kept(
        self,
    ) -> None:
        """
        TRIANGULATION: After transition, images_shown_for_elements is absent from
        mode_context AND shared_context is not overwritten by transition_mode().
        presupuesto_images_shown survives because it's in shared_context (not mode_context).
        """
        state = _make_presupuesto_state_with_images_shown(element_code="MANILLAR")

        result = transition_mode(state, "EXPEDIENTE_MODE")
        mode_context_data = _unwrap_mode_context(result)

        # transition_mode() must NOT overwrite shared_context
        assert "shared_context" not in result, (
            "transition_mode() must not set shared_context — reducer preserves it. "
            f"result keys: {list(result.keys())}"
        )
        # presupuesto_images_shown must NOT bleed into mode_context
        assert "presupuesto_images_shown" not in mode_context_data, (
            "presupuesto_images_shown belongs in shared_context, not mode_context. "
            f"mode_context: {mode_context_data}"
        )
        # images_shown_for_elements must also be absent from mode_context (bug key)
        assert "images_shown_for_elements" not in mode_context_data, (
            "images_shown_for_elements should NOT be propagated (bug key). "
            f"Got: {mode_context_data}"
        )


class TestTransitionModeOutputShape:
    """
    Sanity/structural tests for transition_mode() return — ensures our
    test helpers work correctly.
    """

    def test_transition_mode_returns_dict_with_expected_keys(self) -> None:
        """transition_mode() must return a dict with at least current_mode and mode_context."""
        state = _make_presupuesto_state_with_images_shown()
        result = transition_mode(state, "EXPEDIENTE_MODE")

        assert isinstance(result, dict), "transition_mode must return a dict"
        assert "mode_context" in result, "result must contain 'mode_context' key"
        assert "current_mode" in result, "result must contain 'current_mode' key"
        assert result["current_mode"] == "EXPEDIENTE_MODE"

    def test_images_shown_for_elements_absent_from_empty_source_context(
        self,
    ) -> None:
        """
        Edge case: when `images_shown_for_elements` is NOT in source context,
        the transition must also not introduce it.
        """
        state = {
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": True,
                # No image-tracking keys at all
            },
            "mode_history": [],
            "draft_contexts": {},
            "retry_state": {},
            "mode_message_count": 0,
        }

        result = transition_mode(state, "EXPEDIENTE_MODE")
        mode_context_data = _unwrap_mode_context(result)

        assert "images_shown_for_elements" not in mode_context_data, (
            "images_shown_for_elements must not appear in mode_context "
            "even if it was absent in the source. "
            f"Got: {mode_context_data}"
        )
