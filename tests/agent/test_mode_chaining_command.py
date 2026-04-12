"""
Tests for WS1: Eliminate External Mode Chaining.

Verifies that the old external while-loop chaining pattern has been fully
removed and replaced with LangGraph-native Command(goto=...) routing.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path


AGENT_DIR = Path(__file__).parent.parent.parent / "agent"


# ---------------------------------------------------------------------------
# T-WS1-1a: _chain_next_mode and _is_chained_turn removed from ConversationState
# ---------------------------------------------------------------------------


def test_chain_next_mode_fields_deleted():
    """
    _chain_next_mode and _is_chained_turn must NOT appear as annotations
    in ConversationState.

    WS4 already removed them from the TypedDict fields; this test guards
    against regressions.
    """
    from agent.state.conversation_state import ConversationState

    annotations = ConversationState.__annotations__
    assert "_chain_next_mode" not in annotations, (
        "_chain_next_mode is still declared as a ConversationState field — "
        "it must be removed (WS1 / WS4)"
    )
    assert "_is_chained_turn" not in annotations, (
        "_is_chained_turn is still declared as a ConversationState field — "
        "it must be removed (WS1 / WS4)"
    )


# ---------------------------------------------------------------------------
# T-WS1-1b: No chaining loop in main.py
# ---------------------------------------------------------------------------


def test_no_chain_loop_in_main():
    """
    The external while-loop chaining pattern must be completely removed from main.py.

    Specifically, none of these identifiers should appear:
    - _chain_next_mode
    - MAX_CHAIN_DEPTH
    - chain_state_input
    - _is_chained_turn
    """
    main_path = AGENT_DIR / "main.py"
    assert main_path.exists(), f"main.py not found at {main_path}"

    source = main_path.read_text()

    forbidden = [
        "_chain_next_mode",
        "MAX_CHAIN_DEPTH",
        "chain_state_input",
        "_is_chained_turn",
    ]
    found = [token for token in forbidden if token in source]
    assert not found, (
        f"main.py still contains chaining tokens: {found}. "
        "Remove the external while-loop chaining code (WS1-T5)."
    )


# ---------------------------------------------------------------------------
# T-WS1-1c: No synthetic message in any agent source file
# ---------------------------------------------------------------------------


def test_no_synthetic_message():
    """
    The synthetic user message "Vamos, empezamos con el expediente" must not
    appear in any agent source file.

    This string was injected by the old chaining loop to bootstrap EXPEDIENTE_MODE.
    With Command(goto=...) routing, no such synthetic message is needed.
    """
    synthetic = "Vamos, empezamos con el expediente"

    offending: list[str] = []
    for py_file in AGENT_DIR.rglob("*.py"):
        try:
            content = py_file.read_text()
        except OSError:
            continue
        if synthetic in content:
            offending.append(str(py_file.relative_to(AGENT_DIR.parent)))

    assert not offending, (
        f"Synthetic chaining message found in: {offending}. "
        "Remove it — Command(goto=...) replaces the synthetic user message (WS1-T5)."
    )
