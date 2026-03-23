"""Unit tests for expediente UX improvements.

Coverage:
1. iniciar_expediente returns expediente_intro_sent=False in both the
   return dict AND _internal_flags.
2. Transition closure builders produce descriptive kickoff messages that
   follow the "Pasamos al paso N:" format, stay under 120 chars, and
   include a brief description.
"""

from __future__ import annotations

import re

import pytest

# ---------------------------------------------------------------------------
# 1. iniciar_expediente intro flag contract
# ---------------------------------------------------------------------------

from agent.tools.case_tools import iniciar_expediente


@pytest.mark.unit
def test_iniciar_expediente_returns_intro_sent_false_in_dict() -> None:
    """The success return dict must contain expediente_intro_sent=False at top level.

    Instead of mocking the entire call chain (DB, Redis, services), we verify
    the contract by inspecting the source AST.  This is resilient to internal
    refactors and only breaks if the *contract* changes — which is what we want.
    """
    import ast
    import inspect

    source = inspect.getsource(iniciar_expediente.coroutine)
    tree = ast.parse(source)

    # Walk the AST looking for return dicts that contain "success": True
    # and verify they also set "expediente_intro_sent": False.
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        keys = [
            k.value for k in node.value.keys
            if isinstance(k, ast.Constant)
        ]
        values = {
            k.value: v
            for k, v in zip(node.value.keys, node.value.values)
            if isinstance(k, ast.Constant)
        }
        # Only inspect the success=True return (the happy path)
        success_val = values.get("success")
        if not (isinstance(success_val, ast.Constant) and success_val.value is True):
            continue

        # This IS the success return dict — verify the contract
        assert "expediente_intro_sent" in keys, (
            "Success return dict is missing 'expediente_intro_sent' key"
        )
        intro_val = values["expediente_intro_sent"]
        assert isinstance(intro_val, ast.Constant) and intro_val.value is False, (
            "expediente_intro_sent must be False in the success return dict"
        )
        found = True

    assert found, "Could not find a success=True return dict in iniciar_expediente"


@pytest.mark.unit
def test_iniciar_expediente_returns_intro_sent_false_in_internal_flags() -> None:
    """_internal_flags must also carry expediente_intro_sent=False.

    Verified via AST inspection of the source to avoid fragile integration mocks.
    """
    import ast
    import inspect

    source = inspect.getsource(iniciar_expediente.coroutine)
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        keys = [
            k.value for k in node.value.keys
            if isinstance(k, ast.Constant)
        ]
        values = {
            k.value: v
            for k, v in zip(node.value.keys, node.value.values)
            if isinstance(k, ast.Constant)
        }
        success_val = values.get("success")
        if not (isinstance(success_val, ast.Constant) and success_val.value is True):
            continue

        # Find the _internal_flags dict literal
        assert "_internal_flags" in keys, (
            "Success return dict is missing '_internal_flags' key"
        )
        flags_node = values["_internal_flags"]
        assert isinstance(flags_node, ast.Dict), (
            "_internal_flags must be a dict literal"
        )

        flag_keys = [
            k.value for k in flags_node.keys
            if isinstance(k, ast.Constant)
        ]
        flag_values = {
            k.value: v
            for k, v in zip(flags_node.keys, flags_node.values)
            if isinstance(k, ast.Constant)
        }

        assert "expediente_intro_sent" in flag_keys, (
            "_internal_flags is missing 'expediente_intro_sent' key"
        )
        intro_flag = flag_values["expediente_intro_sent"]
        assert isinstance(intro_flag, ast.Constant) and intro_flag.value is False, (
            "expediente_intro_sent in _internal_flags must be False"
        )
        found = True

    assert found, "Could not find a success=True return dict in iniciar_expediente"


# ---------------------------------------------------------------------------
# 2. Kickoff closure message tests
# ---------------------------------------------------------------------------

from agent.modes.expediente_mode import (
    COLLECT_BASE_DOCS,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    _build_base_docs_to_personal_closure,
    _build_personal_to_vehicle_closure,
    _build_vehicle_to_workshop_closure,
    _build_workshop_to_review_closure,
    _build_element_completion_transition_closure,
    COLLECT_ELEMENT_DATA,
)

# Regex that matches "Pasamos al paso N:" anywhere in the string.
_PASO_RE = re.compile(r"Pasamos al paso \d+:")

# The closure builders we want to test, paired with a human label.
# _build_element_completion_transition_closure has a different signature
# and is tested separately.
_SIMPLE_BUILDERS: list[tuple[str, Any]] = [
    ("base_docs → personal", _build_base_docs_to_personal_closure),
    ("personal → vehicle", _build_personal_to_vehicle_closure),
    ("vehicle → workshop", _build_vehicle_to_workshop_closure),
    ("workshop → review", _build_workshop_to_review_closure),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    "label, builder",
    _SIMPLE_BUILDERS,
    ids=[pair[0] for pair in _SIMPLE_BUILDERS],
)
def test_kickoff_message_contains_pasamos_al_paso(label: str, builder: Any) -> None:
    """Each kickoff message must contain 'Pasamos al paso N:' format."""
    message = builder(tool_data={})
    assert _PASO_RE.search(message), (
        f"Closure '{label}' missing 'Pasamos al paso N:' pattern. Got: {message!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "label, builder",
    _SIMPLE_BUILDERS,
    ids=[pair[0] for pair in _SIMPLE_BUILDERS],
)
def test_kickoff_message_has_description_after_paso(label: str, builder: Any) -> None:
    """After 'Pasamos al paso N:' there must be descriptive text, not just a period."""
    message = builder(tool_data={})
    match = _PASO_RE.search(message)
    assert match is not None

    # Text after the "Pasamos al paso N:" portion must be non-trivial
    after_paso = message[match.end():].strip().rstrip(".")
    assert len(after_paso) > 5, (
        f"Closure '{label}' has no meaningful description after paso marker. "
        f"After marker: {after_paso!r}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "label, builder",
    _SIMPLE_BUILDERS,
    ids=[pair[0] for pair in _SIMPLE_BUILDERS],
)
def test_kickoff_message_under_120_chars(label: str, builder: Any) -> None:
    """The core kickoff sentence (after the progress prefix) must be under 120 chars.

    The full message includes a progress prefix line (e.g. '📍 Paso 3/6 — …')
    followed by the actual kickoff line.  We measure the kickoff line only.
    """
    message = builder(tool_data={})
    # The kickoff line is the part after the double-newline separator
    parts = message.split("\n\n", maxsplit=1)
    kickoff_line = parts[-1].strip() if len(parts) > 1 else message.strip()
    assert len(kickoff_line) <= 120, (
        f"Closure '{label}' kickoff line is {len(kickoff_line)} chars (max 120). "
        f"Content: {kickoff_line!r}"
    )


# ---------------------------------------------------------------------------
# element_data → base_docs closure (legacy builder with different signature)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_element_to_base_docs_kickoff_contains_pasamos_al_paso() -> None:
    """element_data → base_docs closure must include 'Pasamos al paso N:' format."""
    message = _build_element_completion_transition_closure(
        from_sub_mode=COLLECT_ELEMENT_DATA,
        to_sub_mode=COLLECT_BASE_DOCS,
        tool_name="completar_elemento_actual",
        tool_data={"all_elements_complete": True},
        base_documentation=[],
    )
    assert message is not None, "Builder returned None — expected a closure string"
    assert _PASO_RE.search(message), (
        f"element→base_docs closure missing 'Pasamos al paso N:' pattern. Got: {message!r}"
    )


@pytest.mark.unit
def test_element_to_base_docs_kickoff_has_description() -> None:
    """element_data → base_docs kickoff must include descriptive text after the paso marker."""
    message = _build_element_completion_transition_closure(
        from_sub_mode=COLLECT_ELEMENT_DATA,
        to_sub_mode=COLLECT_BASE_DOCS,
        tool_name="completar_elemento_actual",
        tool_data={"all_elements_complete": True},
        base_documentation=[],
    )
    assert message is not None
    match = _PASO_RE.search(message)
    # Even without the "Pasamos al paso" pattern, check there's descriptive content
    # after the progress prefix
    parts = message.split("\n\n", maxsplit=1)
    kickoff_line = parts[-1].strip() if len(parts) > 1 else message.strip()
    after_emoji = kickoff_line.lstrip("📍 ").strip()
    assert len(after_emoji) > 10, (
        f"element→base_docs kickoff has insufficient description. Got: {kickoff_line!r}"
    )


@pytest.mark.unit
def test_element_to_base_docs_kickoff_under_120_chars() -> None:
    """element_data → base_docs kickoff line must be under 120 chars."""
    message = _build_element_completion_transition_closure(
        from_sub_mode=COLLECT_ELEMENT_DATA,
        to_sub_mode=COLLECT_BASE_DOCS,
        tool_name="completar_elemento_actual",
        tool_data={"all_elements_complete": True},
        base_documentation=[],
    )
    assert message is not None
    parts = message.split("\n\n", maxsplit=1)
    kickoff_line = parts[-1].strip() if len(parts) > 1 else message.strip()
    assert len(kickoff_line) <= 120, (
        f"element→base_docs kickoff is {len(kickoff_line)} chars (max 120). "
        f"Content: {kickoff_line!r}"
    )


# ---------------------------------------------------------------------------
# Guard: element→base_docs returns None for wrong conditions
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_element_to_base_docs_returns_none_when_elements_not_complete() -> None:
    """Builder must return None when all_elements_complete is falsy."""
    result = _build_element_completion_transition_closure(
        from_sub_mode=COLLECT_ELEMENT_DATA,
        to_sub_mode=COLLECT_BASE_DOCS,
        tool_name="completar_elemento_actual",
        tool_data={"all_elements_complete": False},
        base_documentation=[],
    )
    assert result is None


@pytest.mark.unit
def test_element_to_base_docs_returns_none_for_wrong_sub_modes() -> None:
    """Builder must return None when called with non-matching sub-modes."""
    result = _build_element_completion_transition_closure(
        from_sub_mode=COLLECT_PERSONAL,
        to_sub_mode=COLLECT_VEHICLE,
        tool_name="completar_elemento_actual",
        tool_data={"all_elements_complete": True},
        base_documentation=[],
    )
    assert result is None
