"""
Unit tests for T2.5 — Consolidate ContextVar (RED phase).

Verifies REQ-P2-2:
  - image_tools.py has ZERO ContextVar definitions of its own
  - image_tools reads state via the SAME ContextVar defined in agent.state.helpers
  - set_current_state_for_image_tools() is NOT called from generic_loop.py

All tests are pure static/import checks plus ContextVar identity tests.
No DB, no Redis, no real LLM.
"""

from __future__ import annotations

import inspect
from pathlib import Path


# ---------------------------------------------------------------------------
# Test 1 — image_tools uses the SHARED ContextVar from helpers
# ---------------------------------------------------------------------------


def test_image_tools_use_shared_contextvar():
    """
    image_tools must read state from the SAME ContextVar as helpers.

    Strategy: set state via helpers.set_current_state(), then verify that
    image_tools._current_state (if it still exists) or helpers._current_state
    sees the same value. The real check is that both modules share the same
    ContextVar object identity.

    After T2.5 is implemented:
      - image_tools no longer defines its own _current_state
      - It imports get_current_state from helpers
      - Setting via helpers.set_current_state() is visible to image_tools via
        the shared get_current_state()

    This test will FAIL before the fix because image_tools has its OWN
    separate ContextVar ("image_tools_current_state") that is NOT set by
    helpers.set_current_state().
    """
    from agent.state.helpers import (
        set_current_state,
        get_current_state,
        _current_state as helpers_cv,
    )
    import importlib
    import agent.tools.image_tools as image_tools_module

    test_state = {"test_key": "shared_value", "conversation_id": "test-123"}

    # Set via the helpers module (shared ContextVar)
    set_current_state(test_state)

    # After T2.5: image_tools uses get_current_state from helpers
    # so reading helpers.get_current_state() and image_tools.get_current_state
    # should return the same object.
    # The proxy test: verify image_tools does NOT have its own _current_state
    # that is DIFFERENT from helpers._current_state
    assert not hasattr(image_tools_module, "_current_state") or (
        image_tools_module._current_state is helpers_cv
    ), (
        "image_tools defines its own _current_state ContextVar separate from "
        "helpers._current_state. After T2.5, image_tools must use the shared "
        "ContextVar from agent.state.helpers."
    )

    # Also verify that get_current_state() (from helpers) returns what we set
    retrieved = get_current_state()
    assert retrieved is test_state, (
        f"get_current_state() returned {retrieved!r} instead of {test_state!r}"
    )

    # Cleanup
    from agent.state.helpers import clear_current_state

    clear_current_state()


# ---------------------------------------------------------------------------
# Test 2 — generic_loop.py does NOT call set_current_state_for_image_tools
# ---------------------------------------------------------------------------


def test_no_set_current_state_for_image_tools_in_loop():
    """
    generic_loop.py must NOT contain calls to set_current_state_for_image_tools.

    T-25 (loop-to-toolnode-migration): generic_loop.py was deleted entirely.
    The file no longer exists, which is a stronger guarantee than just not
    having set_current_state_for_image_tools in it.
    """
    generic_loop_path = (
        Path(__file__).parent.parent.parent / "agent" / "modes" / "generic_loop.py"
    )
    # T-25: the file must NOT exist (deleted in loop-to-toolnode-migration Phase 4)
    assert not generic_loop_path.exists(), (
        f"generic_loop.py still exists at {generic_loop_path} — it should be deleted by T-25."
    )


# ---------------------------------------------------------------------------
# Test 3 — image_tools.py has NO own ContextVar definition
# ---------------------------------------------------------------------------


def test_image_tools_no_own_contextvar():
    """
    image_tools.py must NOT define its own _current_state ContextVar.

    The specific problem in REQ-P2-2 is the DUPLICATED _current_state ContextVar
    (named "image_tools_current_state") that is SEPARATE from the shared one in
    helpers.py. This is what causes tools to see stale state when only
    set_current_state() is called (and not set_current_state_for_image_tools()).

    After T2.5 is implemented:
      - The line `_current_state: ContextVar[...] = ContextVar("image_tools_current_state", ...)`
        is removed from image_tools.py
      - image_tools imports get_current_state from agent.state.helpers instead
      - NOTE: _pending_images_result ContextVar is KEPT — it is not a duplicate
        and is specific to image tool result queuing.

    This test checks for the SPECIFIC duplicate: "image_tools_current_state".
    It will FAIL while image_tools still has its own _current_state ContextVar,
    and PASS after T2.5 is implemented.
    """
    image_tools_path = (
        Path(__file__).parent.parent.parent / "agent" / "tools" / "image_tools.py"
    )
    assert image_tools_path.exists(), f"image_tools.py not found at {image_tools_path}"

    source = image_tools_path.read_text(encoding="utf-8")

    # The specific duplicate ContextVar that causes the bug: "image_tools_current_state"
    # This is the ContextVar that SHADOWS the shared one from helpers.
    assert '"image_tools_current_state"' not in source, (
        "image_tools.py still contains the duplicate 'image_tools_current_state' ContextVar. "
        "T2.5 requires removing this specific definition — it duplicates the shared "
        "'current_state' ContextVar from agent.state.helpers. "
        "image_tools must use get_current_state() from helpers instead."
    )

    # Also verify there's no _current_state = ContextVar(...) assignment
    # (the module-level variable that was the problem)
    import re

    has_own_current_state_cv = bool(
        re.search(r"_current_state\s*[:=].*ContextVar\(", source)
    )
    assert not has_own_current_state_cv, (
        "image_tools.py still assigns a _current_state ContextVar. "
        "After T2.5, this must be removed and replaced with an import of "
        "get_current_state from agent.state.helpers."
    )
