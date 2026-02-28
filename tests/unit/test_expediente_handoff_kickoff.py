"""Regression tests for expediente handoff kickoff continuity."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode
from agent.prompts.loader import format_mode_context


@pytest.mark.unit
def test_loader_transition_context_requires_destination_kickoff() -> None:
    """Loader context must instruct destination-first actionable kickoff."""
    ctx = {
        "expediente_sub_mode": "collect_base_docs",
        "expediente_transition_marker": {
            "from_sub_mode": "collect_element_data",
            "to_sub_mode": "collect_base_docs",
            "tool_name": "completar_elemento_actual",
            "requires_kickoff": True,
        },
    }

    rendered = format_mode_context("EXPEDIENTE_DOCUMENTACION_BASE", ctx)
    assert "primer turno" in rendered.lower()
    assert "kickoff obligatorio" in rendered.lower()
    assert "no asumas que ya se pidió" in rendered.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sub_mode_name", "expected_fragment"),
    [
        ("COLLECT_BASE_DOCS", "fotos"),
        ("COLLECT_PERSONAL", "datos personales"),
        ("COLLECT_VEHICLE", "datos del vehiculo"),
        ("COLLECT_WORKSHOP", "85 EUR +IVA"),
        ("REVIEW_SUMMARY", "resumen"),
    ],
)
def test_transition_kickoff_message_matrix_is_actionable(
    sub_mode_name: str,
    expected_fragment: str,
) -> None:
    """Each destination sub-mode must have actionable kickoff fallback text."""
    message = ExpedienteModeNode._build_transition_kickoff_message(
        sub_mode_name=sub_mode_name,
        mode_context={},
    )

    assert expected_fragment.lower() in message.lower()
    assert ExpedienteModeNode._is_actionable_kickoff_response(message)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transition_marker_lifecycle_consumed_and_cleared_with_dead_air_guard() -> None:
    """First destination turn must be actionable and clear consumed marker."""
    node = ExpedienteModeNode()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content="Perfecto, continuamos.", tool_calls=[]),
    )

    mode_context = {
        "expediente_sub_mode": "collect_base_docs",
        "expediente_transition_marker": {
            "from_sub_mode": "collect_element_data",
            "to_sub_mode": "collect_base_docs",
            "tool_name": "completar_elemento_actual",
            "requires_kickoff": True,
        },
        "just_transitioned_from": "collect_element_data",
    }
    state = {
        "conversation_id": "conv-kickoff-1",
        "messages": [],
        "mode_context": dict(mode_context),
        "retry_state": {},
    }

    with patch.object(node, "_get_llm", return_value=mock_llm), patch.object(
        node,
        "_track_token_usage",
        new=AsyncMock(return_value=None),
    ), patch.object(
        node,
        "_validate_response_constraints",
        new=AsyncMock(return_value=(True, None)),
    ):
        result = await node._run_llm_loop(
            message="ok",
            state=state,
            mode_context=mode_context,
            tools=[],
            sub_mode_name="COLLECT_BASE_DOCS",
        )

    assert "fotos" in str(result.get("ai_response", "")).lower()
    assert "expediente_transition_marker" not in result["mode_context"]
    assert "just_transitioned_from" not in result["mode_context"]


@pytest.mark.unit
def test_transition_kickoff_observability_events_present() -> None:
    """Transition + kickoff continuity events must be emitted for diagnostics."""
    from agent.modes import expediente_mode

    source = inspect.getsource(expediente_mode)
    assert "expediente_transition_marker_set" in source
    assert "expediente_transition_marker_consumed" in source
    assert "expediente_transition_marker_cleared" in source
    assert "expediente_transition_kickoff_guard_triggered" in source
    assert "requires_kickoff" in source
