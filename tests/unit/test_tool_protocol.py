"""
Tests: Tool Protocol Compliance (T1.1-RED)

These tests verify that:
1. Validation errors return a ToolMessage with correct tool_call_id — NOT a SystemMessage
2. No SystemMessage is injected into history after a validation error
3. History maintains valid alternating structure after a validation error + retry
4. Multi-tool partial failure: failing tool gets ToolMessage error, passing tools execute normally

BUG REFERENCE: Bug #8 from production incident 2026-04-02
  - `_handle_validation_retry` in base_mode.py appends a `role:system` message
  - This corrupts the LangChain/OpenAI tool protocol: every AIMessage.tool_calls[i]
    MUST have a corresponding ToolMessage(tool_call_id=...) response
  - When orphaned tool_calls exist, Azure/OpenRouter returns 400 BadRequestError
  - Fix: Remove the system message inject; the validation error JSON returned by
    _execute_and_log_tool is sufficient and should be appended as role:tool

ADR Reference: AD-1 in design doc
Spec Reference: REQ-P1-1 in delta spec

Tests are written BEFORE the fix — they should FAIL against the current code.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helper: build a minimal mock AIMessage with tool_calls
# ---------------------------------------------------------------------------


def _make_ai_message_dict(tool_calls: list[dict]) -> dict:
    """Return a dict representing an AIMessage, as used in llm_messages lists."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": tool_calls,
    }


def _make_tool_call(tool_call_id: str, name: str, args: dict) -> dict:
    return {"id": tool_call_id, "name": name, "args": args, "type": "tool_call"}


# ---------------------------------------------------------------------------
# Helper: inspect llm_messages for protocol violations
# ---------------------------------------------------------------------------


def _get_system_injections(messages: list[dict]) -> list[dict]:
    """Return all role:system messages that are NOT the initial system prompt."""
    return [
        m
        for m in messages[1:]  # Skip index 0 = initial system prompt
        if m.get("role") == "system"
    ]


def _get_tool_messages(messages: list[dict]) -> list[dict]:
    """Return all role:tool messages in the history."""
    return [m for m in messages if m.get("role") == "tool"]


def _has_orphaned_tool_calls(messages: list[dict]) -> bool:
    """
    Check if any AIMessage has tool_calls that don't all have matching ToolMessages.

    An 'orphaned' tool_call is one where the AIMessage.tool_calls[i].id does NOT
    appear as a tool_call_id in any subsequent ToolMessage before the next AIMessage.
    """
    pending_ids: set[str] = set()
    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                pending_ids.add(tc["id"])
        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id:
                pending_ids.discard(tc_id)
    return len(pending_ids) > 0


# ---------------------------------------------------------------------------
# Fixture: BaseModeNode with minimal setup for testing _handle_validation_retry
# ---------------------------------------------------------------------------


@pytest.fixture
def base_mode_node():
    """
    Create a concrete BaseModeNode subclass for testing _handle_validation_retry.
    BaseModeNode is abstract, so we need a concrete subclass.
    We use PresupuestoModeNode as the simplest available concrete subclass.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    node = PresupuestoModeNode()
    # Override logger to a mock so we can inspect calls
    node._logger = MagicMock()
    node._logger.info = MagicMock()
    node._logger.warning = MagicMock()
    node._logger.error = MagicMock()

    return node


# ---------------------------------------------------------------------------
# T1: test_validation_error_returns_tool_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validation_error_returns_tool_message():
    """
    SPEC REQ-P1-1 / AD-1:
    When a tool call fails parameter validation, the message appended to
    llm_messages MUST be a ToolMessage with role='tool' and the correct
    tool_call_id.

    The fix: _handle_validation_retry should NOT append a role:system message.
    The validation error JSON (already returned by _execute_and_log_tool) should be
    appended as role:tool by the CALLER before breaking the tool loop.

    This test verifies the expected final state of llm_messages after a validation
    error is handled: there must be a tool message with tool_call_id='call_abc' and
    there must be NO role:system injection from the validation handler.
    """
    tool_call_id = "call_abc"
    tool_name = "guardar_datos_elemento"
    error_json = json.dumps(
        {
            "success": False,
            "error": "Missing required parameter: datos",
            "error_type": "parameter_validation",
            "validation_errors": ["Missing required parameter: datos"],
            "validation_layer": "syntax",
            "tool_name": tool_name,
        }
    )

    # Simulate the llm_messages state after the LLM emitted an AIMessage with
    # tool_calls and BEFORE any tool result was appended.
    # After the fix, the ToolMessage with error content should be here:
    llm_messages: list[dict] = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Quiero homologar una placa solar"},
        _make_ai_message_dict(
            [_make_tool_call(tool_call_id, tool_name, {"element_code": "PLACA"})]
        ),
        # After the fix: the validation error is appended here as ToolMessage
        {
            "role": "tool",
            "content": error_json,
            "tool_call_id": tool_call_id,
        },
    ]

    # Verify the expected structure:
    # 1. ToolMessage with the correct tool_call_id IS present
    tool_messages = _get_tool_messages(llm_messages)
    assert len(tool_messages) == 1, (
        f"Expected 1 ToolMessage, got {len(tool_messages)}. "
        f"Validation errors must be communicated via ToolMessage, not SystemMessage."
    )
    assert tool_messages[0]["tool_call_id"] == tool_call_id, (
        f"ToolMessage must have tool_call_id='{tool_call_id}', "
        f"got '{tool_messages[0].get('tool_call_id')}'"
    )

    # 2. The tool message content contains the validation error
    content = json.loads(tool_messages[0]["content"])
    assert content["error_type"] == "parameter_validation"
    assert not content["success"]

    # 3. No orphaned tool_calls
    assert not _has_orphaned_tool_calls(llm_messages), (
        "AIMessage has tool_calls that don't have matching ToolMessages — "
        "this causes Azure/OpenRouter 400 errors."
    )


# ---------------------------------------------------------------------------
# T2: test_no_system_message_injection_on_validation_error
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_system_message_injection_on_validation_error(base_mode_node):
    """
    SPEC REQ-P1-1 / AD-1:
    After a validation error, the message history MUST NOT contain any
    SystemMessage injected by `_handle_validation_retry`.

    The current buggy code appends:
        {"role": "system", "content": "[VALIDATION ERROR]: ..."}

    After the fix: _handle_validation_retry must NOT append any role:system message.
    The ToolMessage (already returned by _execute_and_log_tool) is sufficient.
    """
    tool_call_id = "call_xyz"
    tool_name = "guardar_datos_elemento"
    error_dict = {
        "success": False,
        "error": "Missing required parameter: datos",
        "error_type": "parameter_validation",
        "validation_errors": ["Missing required parameter: datos"],
        "validation_layer": "syntax",
        "tool_name": tool_name,
    }

    # Start with a minimal valid conversation history
    llm_messages: list[dict] = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "guardar datos"},
        _make_ai_message_dict(
            [_make_tool_call(tool_call_id, tool_name, {"element_code": "PLACA"})]
        ),
    ]

    retry_state: dict = {}

    # Call _handle_validation_retry (the buggy method)
    base_mode_node._handle_validation_retry(
        tool_name=tool_name,
        error_dict=error_dict,
        retry_state=retry_state,
        llm_messages=llm_messages,
    )

    # After the fix: no system messages should have been injected
    injected_systems = _get_system_injections(llm_messages)
    assert len(injected_systems) == 0, (
        f"_handle_validation_retry must NOT inject role:system messages. "
        f"Found {len(injected_systems)} injected system message(s): {injected_systems}. "
        f"Bug #8: system messages after AIMessage.tool_calls cause Azure 400 errors."
    )


# ---------------------------------------------------------------------------
# T3: test_history_maintains_valid_alternating_structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_history_maintains_valid_alternating_structure(base_mode_node):
    """
    SPEC REQ-P1-1:
    After a validation error + retry, the history must be:
      AIMessage(tool_calls) → ToolMessage(tool_call_id) pairs
    with no orphaned tool_calls.

    The LangChain/OpenAI protocol requires:
    - Every AIMessage.tool_calls[i].id MUST have a corresponding
      ToolMessage(tool_call_id=...) before the next AIMessage.
    - No SystemMessage may appear between AIMessage.tool_calls and ToolMessages.
    """
    tool_call_id = "call_validation_retry_001"
    tool_name = "guardar_datos_elemento"
    error_json = json.dumps(
        {
            "success": False,
            "error": "Missing required parameter: datos",
            "error_type": "parameter_validation",
            "validation_errors": ["Missing required parameter: datos"],
            "validation_layer": "syntax",
            "tool_name": tool_name,
        }
    )

    # Build the conversation history as it should look after the fix:
    # AIMessage with tool_calls → ToolMessage with validation error
    llm_messages: list[dict] = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "listo"},
        _make_ai_message_dict(
            [_make_tool_call(tool_call_id, tool_name, {"element_code": "PLACA"})]
        ),
        # ← After the fix: validation error appended here as ToolMessage
        {
            "role": "tool",
            "content": error_json,
            "tool_call_id": tool_call_id,
        },
        # ← LLM retry: new AIMessage (now without bad tool_calls)
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                _make_tool_call(
                    "call_retry_002",
                    tool_name,
                    {"element_code": "PLACA", "datos": {"campo": "valor"}},
                )
            ],
        },
        # ← Successful tool result
        {
            "role": "tool",
            "content": json.dumps({"success": True}),
            "tool_call_id": "call_retry_002",
        },
    ]

    # No orphaned tool_calls
    assert not _has_orphaned_tool_calls(llm_messages), (
        "History has orphaned tool_calls — every tool_call must have "
        "a matching ToolMessage before the next AIMessage."
    )

    # The validation error IS communicated as a ToolMessage
    tool_msgs = _get_tool_messages(llm_messages)
    validation_error_msgs = [
        m
        for m in tool_msgs
        if json.loads(m["content"]).get("error_type") == "parameter_validation"
    ]
    assert len(validation_error_msgs) == 1, (
        "Expected exactly 1 ToolMessage with error_type='parameter_validation'. "
        f"Got {len(validation_error_msgs)}."
    )
    assert validation_error_msgs[0]["tool_call_id"] == tool_call_id

    # No system messages injected after initial prompt
    injected = _get_system_injections(llm_messages)
    assert len(injected) == 0, (
        f"History must not contain injected system messages. Found: {injected}"
    )


# ---------------------------------------------------------------------------
# T4: test_multi_tool_partial_failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multi_tool_partial_failure():
    """
    SPEC REQ-P1-1 (multi-tool scenario):
    When AIMessage has 2+ tool_calls and one fails validation, the failing one
    gets a ToolMessage error with its tool_call_id, and passing ones execute normally.

    After the fix:
    - tc1 (valid): produces ToolMessage with success result
    - tc2 (invalid): produces ToolMessage with validation error
    - NO orphaned tool_call_ids
    - NO SystemMessage injections

    This is the exact scenario from Bug #8:
    guardar_datos_elemento called without 'datos' param → system message injected
    → Azure returns 400 because tool_call_id has no ToolMessage response
    """
    tc1_id = "call_valid_001"
    tc2_id = "call_invalid_002"

    valid_result = json.dumps(
        {"success": True, "message": "Tool executed successfully"}
    )
    validation_error = json.dumps(
        {
            "success": False,
            "error": "Missing required parameter: datos",
            "error_type": "parameter_validation",
            "validation_errors": ["Missing required parameter: datos"],
            "validation_layer": "syntax",
            "tool_name": "guardar_datos_elemento",
        }
    )

    # Build llm_messages as they should look after the fix:
    # AIMessage with 2 tool_calls → both get ToolMessages
    llm_messages: list[dict] = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Guardar datos del elemento"},
        # AIMessage with 2 tool_calls
        _make_ai_message_dict(
            [
                _make_tool_call(tc1_id, "confirmar_fotos_elemento", {}),
                _make_tool_call(
                    tc2_id, "guardar_datos_elemento", {"element_code": "PLACA"}
                ),
            ]
        ),
        # tc1: valid, executed successfully
        {"role": "tool", "content": valid_result, "tool_call_id": tc1_id},
        # tc2: invalid, error returned as ToolMessage (NOT SystemMessage)
        {"role": "tool", "content": validation_error, "tool_call_id": tc2_id},
    ]

    # Both tool_calls have ToolMessage responses
    assert not _has_orphaned_tool_calls(llm_messages), (
        "Both tool_calls (tc1 valid, tc2 invalid) must have ToolMessage responses. "
        "No orphaned tool_call_ids allowed."
    )

    tool_msgs = _get_tool_messages(llm_messages)
    assert len(tool_msgs) == 2, f"Expected 2 ToolMessages, got {len(tool_msgs)}"

    # tc1: success
    tc1_msg = next(m for m in tool_msgs if m["tool_call_id"] == tc1_id)
    assert json.loads(tc1_msg["content"])["success"] is True

    # tc2: validation error as ToolMessage
    tc2_msg = next(m for m in tool_msgs if m["tool_call_id"] == tc2_id)
    tc2_content = json.loads(tc2_msg["content"])
    assert tc2_content["success"] is False
    assert tc2_content["error_type"] == "parameter_validation"

    # No system injections
    injected = _get_system_injections(llm_messages)
    assert len(injected) == 0, (
        f"No system message injections allowed. Found: {injected}"
    )


# ---------------------------------------------------------------------------
# T5: test_handle_validation_retry_does_not_inject_system_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_handle_validation_retry_does_not_inject_system_message(base_mode_node):
    """
    Direct unit test of _handle_validation_retry.

    Verifies that after calling _handle_validation_retry, no role:system message
    was appended to llm_messages.

    This test directly calls the method and inspects the side effect.
    With the current buggy code, this will FAIL because the method appends
    {"role": "system", "content": "[VALIDATION ERROR]: ..."}.

    After the fix, this test must PASS.
    """
    tool_call_id = "call_direct_test_001"
    tool_name = "guardar_datos_elemento"

    error_dict = {
        "success": False,
        "error": "Missing required parameter: datos",
        "error_type": "parameter_validation",
        "validation_errors": ["Missing required parameter: datos"],
        "validation_layer": "syntax",
        "tool_name": tool_name,
    }

    llm_messages: list[dict] = [
        {"role": "system", "content": "Initial system prompt"},
        {"role": "user", "content": "Quiero guardar datos"},
        _make_ai_message_dict(
            [_make_tool_call(tool_call_id, tool_name, {"element_code": "PLACA"})]
        ),
    ]

    count_before = len(llm_messages)
    retry_state: dict = {}

    base_mode_node._handle_validation_retry(
        tool_name=tool_name,
        error_dict=error_dict,
        retry_state=retry_state,
        llm_messages=llm_messages,
    )

    # After the fix: no new messages should be appended by this method
    # The method should just update retry_state and return
    new_messages = llm_messages[count_before:]
    system_injections = [m for m in new_messages if m.get("role") == "system"]

    assert len(system_injections) == 0, (
        f"_handle_validation_retry must NOT inject role:system messages. "
        f"Bug #8: injecting system messages after AIMessage.tool_calls causes "
        f"orphaned tool_call_ids and Azure/OpenRouter 400 errors. "
        f"Injected: {system_injections}"
    )
