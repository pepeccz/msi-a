"""
Guard: agent.modes.submodos._shared must NOT expose module-level string
constants for sub-mode names after Batch D of the refactor.

This test is expected to FAIL until Batch D removes the constants. Once Batch D
is applied (delete the 6 constants + _SUB_MODE_TO_COLLECTION_STEP identity map),
this test turns GREEN and must stay green.

Requirements: R2.1 — No module-level constants in _shared.py
              R2.2 — _SUB_MODE_TO_COLLECTION_STEP identity map removed
"""

from __future__ import annotations

import importlib

import pytest

# Constants that Batch D must remove from agent.modes.submodos._shared
_FORBIDDEN_CONSTANTS = [
    "COLLECT_ELEMENT_DATA",
    "COLLECT_BASE_DOCS",
    "COLLECT_PERSONAL",
    "COLLECT_VEHICLE",
    "COLLECT_WORKSHOP",
    "REVIEW_SUMMARY",
]


@pytest.fixture(scope="module")
def shared_module():
    """Import the _shared module fresh (avoids stale cache between test runs)."""
    return importlib.import_module("agent.modes.submodos._shared")


@pytest.mark.parametrize("constant_name", _FORBIDDEN_CONSTANTS)
def test_shared_does_not_expose_submode_string_constant(
    shared_module, constant_name: str
) -> None:
    """
    Each of the 6 sub-mode string constants must NOT exist as a module-level
    attribute on agent.modes.submodos._shared after Batch D.

    CollectionStep in agent.utils.expediente_types is the single source of truth.
    """
    assert not hasattr(shared_module, constant_name), (
        f"agent.modes.submodos._shared still exposes {constant_name!r} as a "
        f"module-level constant. Remove it in Batch D and use "
        f"CollectionStep.{constant_name}.value instead."
    )


def test_shared_does_not_expose_sub_mode_to_collection_step_map(
    shared_module,
) -> None:
    """
    The _SUB_MODE_TO_COLLECTION_STEP identity map must NOT exist as a
    module-level attribute on agent.modes.submodos._shared after Batch D.

    It duplicates CollectionStep and adds drift risk with zero added value.
    """
    assert not hasattr(shared_module, "_SUB_MODE_TO_COLLECTION_STEP"), (
        "agent.modes.submodos._shared still exposes _SUB_MODE_TO_COLLECTION_STEP. "
        "Remove the identity map in Batch D — use CollectionStep.X.value directly."
    )
