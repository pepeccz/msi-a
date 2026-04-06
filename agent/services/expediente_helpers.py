"""
MSI-a — Expediente collection helpers (shared between case_tools and element_data_tools).

These four helpers (and their associated constants) were duplicated verbatim
in ``agent/tools/case_tools.py`` and ``agent/tools/element_data_tools.py``.
They are extracted here so the two tool modules can import from a single
location instead of maintaining identical copies.

The original private names (underscore-prefixed) have been kept as aliases at
the bottom of this file so that existing call sites in the tool modules do not
break before they are updated to import from here directly.

Public API (drop the underscore for new code):
    get_mode_context()           — read CaseCollectionState from ContextVar
    get_current_step()           — get CollectionStep from current context
    build_case_update()          — merge updates into case_collection dict
    set_collection_step()        — convenience wrapper around build_case_update
    can_transition_to()          — validate a CollectionStep transition
    is_collection_active()       — check if a case is in progress
    reset_case_collection()      — reset collection state to IDLE

Constants:
    INITIAL_CASE_STATE           — CaseCollectionState with all fields at zero/None
    STEP_PROMPTS                 — dict[CollectionStep, str]
    VALID_TRANSITIONS            — dict[CollectionStep, list[CollectionStep]]
"""

from __future__ import annotations

from typing import Any

import structlog

from agent.state.helpers import get_current_state
from agent.utils.expediente_types import (
    CaseCollectionState,
    CollectionStep,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INITIAL_CASE_STATE: CaseCollectionState = CaseCollectionState(
    step=CollectionStep.IDLE.value,
    case_id=None,
    personal_data={},
    vehicle_data={},
    taller_propio=None,
    taller_data=None,
    category_slug=None,
    category_id=None,
    element_codes=[],
    current_element_index=0,
    element_phase="photos",
    element_data_status={},
    base_docs_received=False,
    base_doc_descriptions=[],
    received_images=[],
    tariff_tier_id=None,
    tariff_amount=None,
    last_prompt=None,
    retry_count=0,
    error_message=None,
)

STEP_PROMPTS: dict[CollectionStep, str] = {
    CollectionStep.COLLECT_ELEMENT_DATA: "Volvemos a datos de elementos. El sub-modo gestionará el resto.",
    CollectionStep.COLLECT_BASE_DOCS: "Volvemos a documentación base. El sub-modo gestionará el resto.",
    CollectionStep.COLLECT_PERSONAL: "Volvemos a datos personales. El sub-modo gestionará el resto.",
    CollectionStep.COLLECT_VEHICLE: "Volvemos a datos del vehículo. El sub-modo gestionará el resto.",
    CollectionStep.COLLECT_WORKSHOP: "Volvemos al certificado del taller. El sub-modo gestionará el resto.",
    CollectionStep.REVIEW_SUMMARY: "Revisión del expediente.",
    CollectionStep.COMPLETED: "Expediente enviado.",
}

VALID_TRANSITIONS: dict[CollectionStep, list[CollectionStep]] = {
    CollectionStep.IDLE: [
        CollectionStep.COLLECT_ELEMENT_DATA,
    ],
    CollectionStep.COLLECT_ELEMENT_DATA: [
        CollectionStep.COLLECT_ELEMENT_DATA,
        CollectionStep.COLLECT_BASE_DOCS,
    ],
    CollectionStep.COLLECT_BASE_DOCS: [
        CollectionStep.COLLECT_PERSONAL,
    ],
    CollectionStep.COLLECT_PERSONAL: [
        CollectionStep.COLLECT_VEHICLE,
    ],
    CollectionStep.COLLECT_VEHICLE: [
        CollectionStep.COLLECT_WORKSHOP,
    ],
    CollectionStep.COLLECT_WORKSHOP: [
        CollectionStep.REVIEW_SUMMARY,
    ],
    CollectionStep.REVIEW_SUMMARY: [
        CollectionStep.COMPLETED,
        CollectionStep.COLLECT_BASE_DOCS,
        CollectionStep.COLLECT_PERSONAL,
        CollectionStep.COLLECT_VEHICLE,
        CollectionStep.COLLECT_WORKSHOP,
    ],
    CollectionStep.COMPLETED: [],
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_mode_context() -> CaseCollectionState:
    """
    Read expediente state from the current ContextVar snapshot.

    Returns INITIAL_CASE_STATE (a safe zero-value) when:
    - There is no active state (first call, between turns).
    - The current mode is not EXPEDIENTE_MODE.

    This mirrors the behaviour of the private ``_get_mode_context()`` that
    lived in both case_tools.py and element_data_tools.py.
    """
    state = get_current_state()
    if not state:
        return INITIAL_CASE_STATE.copy()  # type: ignore[return-value]

    mode_context = state.get("mode_context", {})

    if state.get("current_mode") != "EXPEDIENTE_MODE":
        return INITIAL_CASE_STATE.copy()  # type: ignore[return-value]

    return CaseCollectionState(
        step=mode_context.get("expediente_sub_mode", CollectionStep.IDLE.value),
        case_id=mode_context.get("case_id"),
        category_slug=mode_context.get("category_slug"),
        category_id=mode_context.get("category_id"),
        element_codes=mode_context.get("element_codes", []),
        current_element_index=mode_context.get("current_element_index", 0),
        element_phase=mode_context.get("element_phase", "photos"),
        element_data_status=mode_context.get("element_data_status", {}),
        personal_data=mode_context.get("personal_data", {}),
        vehicle_data=mode_context.get("vehicle_data", {}),
        taller_propio=mode_context.get("taller_propio"),
        taller_data=mode_context.get("taller_data"),
        base_docs_received=mode_context.get("base_docs_received", False),
        base_doc_descriptions=mode_context.get("base_doc_descriptions", []),
        received_images=mode_context.get("received_images", []),
        tariff_tier_id=mode_context.get("tariff_tier_id"),
        tariff_amount=mode_context.get("tariff_amount"),
        last_prompt=None,
        retry_count=0,
        error_message=None,
    )


def get_current_step() -> CollectionStep:
    """
    Return the current CollectionStep from the ContextVar state.

    Falls back to CollectionStep.IDLE on invalid or missing step values.
    """
    mc = get_mode_context()
    step_val = mc.get("step", CollectionStep.IDLE.value)
    try:
        return CollectionStep(step_val)
    except ValueError:
        logger.warning(
            "expediente_helpers_invalid_step",
            step_val=step_val,
            fallback=CollectionStep.IDLE.value,
        )
        return CollectionStep.IDLE


def build_case_update(
    fsm_state: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge *updates* into the existing case_collection dict with ADR-006 semantics.

    Chained calls accumulate updates instead of overwriting previous ones.

    Args:
        fsm_state: Current FSM state dict (may already contain "case_collection").
        updates:   New key-value pairs to merge into the case collection.

    Returns:
        Dict with a single "case_collection" key containing the merged state.
    """
    existing: dict[str, Any] = {}
    if isinstance(fsm_state, dict) and "case_collection" in fsm_state:
        existing = dict(fsm_state["case_collection"])
    existing.update(updates)
    return {"case_collection": existing}


def set_collection_step(
    fsm_state: dict[str, Any] | None,
    target_step: CollectionStep,
) -> dict[str, Any]:
    """
    Transition the collection to *target_step*.

    Convenience wrapper around ``build_case_update`` that only updates the
    ``step`` key.

    Args:
        fsm_state:   Current FSM state dict.
        target_step: The CollectionStep to transition into.

    Returns:
        Dict with "case_collection" key containing the step update.
    """
    return build_case_update(fsm_state, {"step": target_step.value})


def can_transition_to(
    current_step: CollectionStep,
    target_step: CollectionStep,
) -> bool:
    """
    Return True if transitioning from *current_step* to *target_step* is valid.

    Transitions to CollectionStep.IDLE are always permitted (reset/cancel path).

    Args:
        current_step: The step the collection is currently in.
        target_step:  The step we want to move to.
    """
    if target_step == CollectionStep.IDLE:
        return True
    return target_step in VALID_TRANSITIONS.get(current_step, [])


def is_collection_active(fsm_state: dict[str, Any] | None = None) -> bool:
    """
    Return True if there is an active case collection in progress.

    A collection is active when the current step is neither IDLE nor COMPLETED.
    The *fsm_state* parameter is accepted for API compatibility but the
    authoritative source is always the ContextVar (via ``get_mode_context()``).

    Args:
        fsm_state: Ignored (kept for backward compatibility with call sites
                   that pass the old FSM state dict).
    """
    mc = get_mode_context()
    step = mc.get("step", CollectionStep.IDLE.value)
    return step not in (CollectionStep.IDLE.value, CollectionStep.COMPLETED.value)


def reset_case_collection(fsm_state: dict[str, Any] | None) -> dict[str, Any]:
    """
    Reset case collection to the initial IDLE state.

    Args:
        fsm_state: Current FSM state dict to augment (pass ``None`` for a fresh reset).

    Returns:
        Updated FSM state dict with "case_collection" set to INITIAL_CASE_STATE.
    """
    if fsm_state is None:
        fsm_state = {}
    new_fsm_state = fsm_state.copy()
    new_fsm_state["case_collection"] = INITIAL_CASE_STATE.copy()
    return new_fsm_state


# ---------------------------------------------------------------------------
# Backward-compat aliases (private names used by tool modules before extraction)
# ---------------------------------------------------------------------------
# Import these from here if you need to keep existing call sites unchanged.
# New code should use the public names (no underscore prefix) above.

_get_mode_context = get_mode_context
_get_current_step_from_context = get_current_step
_build_case_update = build_case_update
_set_collection_step = set_collection_step
_can_transition_to = can_transition_to
_is_collection_active = is_collection_active
_reset_case_collection = reset_case_collection

# Constants aliases
_INITIAL_CASE_STATE = INITIAL_CASE_STATE
_STEP_PROMPTS = STEP_PROMPTS
_VALID_TRANSITIONS = VALID_TRANSITIONS

__all__ = [
    # Public API
    "get_mode_context",
    "get_current_step",
    "build_case_update",
    "set_collection_step",
    "can_transition_to",
    "is_collection_active",
    "reset_case_collection",
    # Constants
    "INITIAL_CASE_STATE",
    "STEP_PROMPTS",
    "VALID_TRANSITIONS",
    # Backward-compat aliases
    "_get_mode_context",
    "_get_current_step_from_context",
    "_build_case_update",
    "_set_collection_step",
    "_can_transition_to",
    "_is_collection_active",
    "_reset_case_collection",
    "_INITIAL_CASE_STATE",
    "_STEP_PROMPTS",
    "_VALID_TRANSITIONS",
]
