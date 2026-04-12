"""
Unit tests for WS2 — ContextVar elimination (updated from T2.5).

WS2 supersedes T2.5: instead of consolidating into a single shared ContextVar,
WS2 fully removes the ContextVar pattern from helpers.py and image_tools.py.
State is now passed via RunnableConfig / ensure_config().

Verifies REQ-WS2:
  - helpers.py has NO ContextVar definitions (_current_state is gone)
  - image_tools.py has NO own ContextVar for state (only _pending_images_result remains)
  - get_current_state / set_current_state / clear_current_state do NOT exist in helpers
  - generic_loop.py does NOT exist (deleted in T-25)
  - set_current_state_for_image_tools does NOT exist in image_tools
"""

from __future__ import annotations

import inspect
from pathlib import Path


# ---------------------------------------------------------------------------
# Test 1 — helpers.py has NO ContextVar for state (WS2 complete removal)
# ---------------------------------------------------------------------------


def test_helpers_has_no_contextvar():
    """
    After WS2, agent.state.helpers must NOT define _current_state, set_current_state,
    get_current_state, or clear_current_state.

    State is now passed via RunnableConfig / ensure_config() — no ContextVar needed.

    This replaces the T2.5 test that verified shared ContextVar identity.
    WS2 removes the ContextVar entirely, making T2.5 obsolete.
    """
    import agent.state.helpers as helpers_module

    # Verify ContextVar functions are gone
    assert not hasattr(helpers_module, "set_current_state"), (
        "set_current_state still exists in helpers.py — WS2 not fully applied. "
        "This function was part of the ContextVar pattern that WS2 removes."
    )
    assert not hasattr(helpers_module, "get_current_state"), (
        "get_current_state still exists in helpers.py — WS2 not fully applied. "
        "Tools now access state via get_tool_state(config) or ensure_config()."
    )
    assert not hasattr(helpers_module, "clear_current_state"), (
        "clear_current_state still exists in helpers.py — WS2 not fully applied."
    )
    assert not hasattr(helpers_module, "_current_state"), (
        "_current_state ContextVar still exists in helpers.py — WS2 not fully applied. "
        "State is now passed via RunnableConfig, not ContextVar."
    )

    # Verify get_tool_state still exists (the replacement)
    assert hasattr(helpers_module, "get_tool_state"), (
        "get_tool_state must exist in helpers.py — it is the WS2 replacement for get_current_state."
    )


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

    After WS2 is implemented:
      - The line `_current_state: ContextVar[...] = ContextVar("image_tools_current_state", ...)`
        is removed from image_tools.py
      - image_tools uses get_tool_state(config) or ensure_config() instead
      - NOTE: _pending_images_result ContextVar is KEPT — it is not a duplicate
        and is specific to image tool result queuing.

    This test checks for the SPECIFIC duplicate: "image_tools_current_state".
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
        "WS2 requires removing this specific definition — it duplicates the shared "
        "'current_state' ContextVar from agent.state.helpers. "
        "image_tools must use get_tool_state(config) or ensure_config() instead."
    )

    # Also verify there's no _current_state = ContextVar(...) assignment
    # (the module-level variable that was the problem)
    import re

    has_own_current_state_cv = bool(
        re.search(r"_current_state\s*[:=].*ContextVar\(", source)
    )
    assert not has_own_current_state_cv, (
        "image_tools.py still assigns a _current_state ContextVar. "
        "After WS2, this must be removed and replaced with get_tool_state(config) "
        "or ensure_config() from langchain_core.runnables."
    )


# ---------------------------------------------------------------------------
# Test 4 — image_tools has no set_current_state_for_image_tools (WS2)
# ---------------------------------------------------------------------------


def test_image_tools_no_set_current_state_for_image_tools():
    """
    After WS2, image_tools.py must NOT export set_current_state_for_image_tools.

    This function was the workaround for the duplicate ContextVar problem:
    callers had to call BOTH set_current_state() AND set_current_state_for_image_tools()
    to ensure both ContextVars saw the state.

    WS2 removes the entire ContextVar pattern — the function must not exist.
    """
    import agent.tools.image_tools as image_tools_module

    assert not hasattr(image_tools_module, "set_current_state_for_image_tools"), (
        "set_current_state_for_image_tools still exists in image_tools.py — WS2 not applied. "
        "This function was part of the duplicate ContextVar workaround that WS2 removes."
    )
