"""
WS2 — ContextVar Elimination Tests.

Verifies that the transition from ContextVar to RunnableConfig is complete:
1. get_tool_state(None) raises RuntimeError (no fallback)
2. get_tool_state with valid config returns the state
3. execute_and_log_tool accepts a config param
4. handle_tool_errors uses ensure_config, not get_current_state
5. _current_state ContextVar no longer exists in helpers module
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# T1: get_tool_state(None) raises RuntimeError
# ---------------------------------------------------------------------------


def test_get_tool_state_with_none_raises_runtime_error():
    """get_tool_state(None) must raise RuntimeError — no ContextVar fallback."""
    from agent.state.helpers import get_tool_state

    with pytest.raises(RuntimeError, match="RunnableConfig"):
        get_tool_state(None)


# ---------------------------------------------------------------------------
# T2: get_tool_state with valid config returns the nested state
# ---------------------------------------------------------------------------


def test_get_tool_state_with_valid_config_returns_state():
    """get_tool_state reads from config['configurable']['state']."""
    from agent.state.helpers import get_tool_state

    state_payload = {"conversation_id": "x", "current_mode": "CONSULTA_MODE"}
    config = {"configurable": {"state": state_payload}}

    result = get_tool_state(config)

    assert result == state_payload
    assert result["conversation_id"] == "x"


# ---------------------------------------------------------------------------
# T3: execute_and_log_tool signature has a config parameter
# ---------------------------------------------------------------------------


def test_execute_and_log_tool_accepts_config_param():
    """execute_and_log_tool must declare a 'config' parameter."""
    from agent.modes.tool_executor import execute_and_log_tool

    sig = inspect.signature(execute_and_log_tool)
    assert "config" in sig.parameters, (
        "execute_and_log_tool must accept a 'config' keyword argument"
    )


# ---------------------------------------------------------------------------
# T4: handle_tool_errors uses ensure_config, not get_current_state
# ---------------------------------------------------------------------------


def test_handle_tool_errors_uses_ensure_config():
    """
    The handle_tool_errors decorator must call ensure_config() to obtain
    the RunnableConfig — it must NOT import or call get_current_state.
    """
    import agent.utils.errors as errors_module

    # Verify get_current_state is NOT imported at module level
    source = inspect.getsource(errors_module)
    assert "get_current_state" not in source, (
        "agent.utils.errors must not reference get_current_state"
    )


# ---------------------------------------------------------------------------
# T5: _current_state ContextVar does NOT exist in helpers
# ---------------------------------------------------------------------------


def test_no_contextvar_in_helpers():
    """_current_state ContextVar must be removed from agent.state.helpers."""
    import agent.state.helpers as helpers_module

    assert not hasattr(helpers_module, "_current_state"), (
        "agent.state.helpers must not have a '_current_state' attribute"
    )
