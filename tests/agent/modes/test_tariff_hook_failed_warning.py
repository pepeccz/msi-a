"""
Unit test for tariff hook failure observability uplift.

Regression: post_tool_hooks.py:211 used logger.debug for
pre_expediente_hook_tariff_failed_no_price_authority — invisible under
INFO filter. R3 self-heal tariff failures went silent for two releases.
Fix: upgrade to logger.warning. This is a failure signal, not debug chatter.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.asyncio
async def test_tariff_tool_failure_emits_warning():
    from agent.modes import post_tool_hooks

    state = {
        "_mode_context": {"_conversation_id": "conv-1"},
        "_conversation_id": "conv-1",
    }

    fake_result = {
        "success": False,
        "error": "simulated tariff failure",
    }

    with patch.object(post_tool_hooks, "logger") as mock_logger:
        await post_tool_hooks.pre_expediente_post_tool_hook(
            tool_name="calcular_tarifa_con_elementos",
            result_dict=fake_result,
            state=state,
        )

    warning_calls = [
        c for c in mock_logger.warning.call_args_list
        if c.args and c.args[0] == "pre_expediente_hook_tariff_failed_no_price_authority"
    ]
    assert len(warning_calls) == 1, (
        f"tariff_failed_no_price_authority must fire as WARNING (not DEBUG). "
        f"warning calls: {mock_logger.warning.call_args_list} | "
        f"debug calls: {mock_logger.debug.call_args_list}"
    )
    kw = warning_calls[0].kwargs
    assert kw["error"] == "simulated tariff failure"
    assert kw["conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_tariff_tool_success_does_not_emit_failure_warning():
    """Triangulation: success path → no failure warning."""
    from agent.modes import post_tool_hooks

    state = {
        "_mode_context": {"_conversation_id": "conv-ok"},
        "_conversation_id": "conv-ok",
    }

    fake_result = {
        "success": True,
        "datos": {"price": 480.0},
        "_state_update": {},
    }

    with patch.object(post_tool_hooks, "logger") as mock_logger:
        await post_tool_hooks.pre_expediente_post_tool_hook(
            tool_name="calcular_tarifa_con_elementos",
            result_dict=fake_result,
            state=state,
        )

    tnf_warnings = [
        c for c in mock_logger.warning.call_args_list
        if c.args and c.args[0] == "pre_expediente_hook_tariff_failed_no_price_authority"
    ]
    assert len(tnf_warnings) == 0
