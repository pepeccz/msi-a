"""
Phase 4 (fix-base-docs-transition-guard): end-to-end integration.

Validates the composition of the three Phase 1–3 fixes across the expediente
handler + entry_router surfaces:

  1. `BaseDocsHandler.handle("lisot")` with sufficient docs deterministically
     invokes `confirm_base_documentation` and surfaces
     `pending_state_updates._transition_to = "collect_personal"` WITHOUT
     calling the LLM loop (no `enviar_imagenes_ejemplo` re-injection).

  2. `entry_router` rescues a personal-data message ("mi DNI es 12345678A")
     stuck in `collect_base_docs` (sufficient docs) to `collect_personal_node`
     with `_transition_to` emitted.

  3. Negative: `listado` in base_docs does NOT trigger the deterministic close
     (false-positive guard: length > 6). Handler falls through to the LLM loop.

This test intentionally exercises composition (handler + router + service +
transition emission) without spinning up Redis/DB/LLM — the underlying units
are already unit-tested in Phases 1–3; Phase 4 is about wiring.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.utils.expediente_types import CollectionStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_get_session_active_case():
    """`get_async_session` returning a non-terminal ('collecting') case."""
    mock_case = MagicMock()
    mock_case.status = "collecting"
    mock_result = MagicMock()
    mock_result.first.return_value = mock_case
    mock_session = AsyncMock()
    mock_session.scalars = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _fake():
        yield mock_session

    return _fake


def _base_state(**overrides):
    state = {
        "case_id": "case-integration-1",
        "conversation_id": "conv-integration-1",
        "expediente_sub_mode": CollectionStep.COLLECT_BASE_DOCS.value,
        "user_message": "",
        "incoming_attachments": [],
        "element_phase": None,
        "current_element_code": None,
        "element_data_status": {},
        "personal_collected": False,
        "vehicle_collected": False,
        "workshop_collected": False,
        "taller_propio": None,
        "messages": [],
        # 2 PDFs already registered ⇒ sufficient (router short-circuits on this flag)
        "base_docs_registered": True,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Scenario 1: end-to-end "lisot" transition via BaseDocsHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lisot_handler_emits_transition_without_llm() -> None:
    """`lisot` + sufficient docs → deterministic close, NO LLM, NO example
    images, `_transition_to == collect_personal` surfaced to state updates.
    """
    service_result = {
        "success": True,
        "base_docs_confirmed": True,
        "message": "Documentación base recibida y registrada correctamente.",
        "_state_update": {
            "base_docs_registered": True,
            "can_narrate_next_step_details": False,
            "delivery_outcome_status": "not_requested",
            "_transition_to": CollectionStep.COLLECT_PERSONAL.value,
        },
    }

    # Lazy imports: conftest.pytest_collectstart rolls back sys.modules before
    # each top-level test module collection; earlier test files may have caused
    # a reload of `agent.modes.submodos.collect_base_docs`. Importing inside the
    # test body guarantees we patch and use the SAME module instance.
    from agent.modes.submodos import collect_base_docs as cbd_mod

    llm_loop = AsyncMock()
    with patch.object(
        cbd_mod,
        "confirm_base_documentation",
        new_callable=AsyncMock,
        return_value=service_result,
    ) as svc_mock:
        handler = cbd_mod.BaseDocsHandler()
        result = await handler.handle(
            message="lisot",
            state=_base_state(user_message="lisot"),
            mode_context={
                "expediente_sub_mode": CollectionStep.COLLECT_BASE_DOCS.value,
            },
            llm_loop_fn=llm_loop,
        )

    # Deterministic guard fired: service called exactly once.
    svc_mock.assert_awaited_once()

    # LLM loop NEVER entered — no chance for `enviar_imagenes_ejemplo`
    # (or any other tool) to be re-injected on this turn.
    llm_loop.assert_not_called()

    # Canonical ADR-005 channel carries the transition.
    assert (
        result["pending_state_updates"]["_transition_to"]
        == CollectionStep.COLLECT_PERSONAL.value
    )

    # User-facing ACK came from the service envelope (not from any prompt
    # that could reference example images).
    assert "Documentación base" in result["ai_response"]
    assert "enviar_imagenes_ejemplo" not in result["ai_response"]


# ---------------------------------------------------------------------------
# Scenario 2: router rescues personal-data message from base_docs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_rescues_personal_data_after_base_docs() -> None:
    """Second scenario: user sends personal data ("mi DNI es 12345678A") while
    sub_mode is still `collect_base_docs` and docs are sufficient. The
    entry_router MUST rescue the turn to `collect_personal_node`.
    """
    from agent.modes import expediente_nodes as expediente_nodes_mod

    state = _base_state(user_message="mi DNI es 12345678A")

    with patch.object(
        expediente_nodes_mod,
        "get_async_session",
        new=_mock_get_session_active_case(),
    ):
        cmd = await expediente_nodes_mod.entry_router(state)

    assert cmd.goto == "collect_personal_node"
    assert cmd.update is not None
    assert (
        cmd.update.get("expediente_sub_mode")
        == CollectionStep.COLLECT_PERSONAL.value
    )
    assert (
        cmd.update.get("_transition_to")
        == CollectionStep.COLLECT_PERSONAL.value
    )
    # user_message is NOT rewritten — personal node consumes it intact.
    assert (
        "user_message" not in cmd.update
        or cmd.update["user_message"] == state["user_message"]
    )


# ---------------------------------------------------------------------------
# Scenario 3: false-positive guard — "listado" must NOT trigger close.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listado_does_not_trigger_deterministic_close() -> None:
    """`listado` in base_docs with sufficient docs must fall through to the
    LLM loop — the length guard (≤6) and vocabulary reject it. Ensures no
    false-positive transition is emitted.
    """
    from agent.modes.submodos import collect_base_docs as cbd_mod

    llm_loop = AsyncMock(
        return_value={"ai_response": "llm-handled", "mode_context": {}}
    )
    with patch.object(
        cbd_mod,
        "confirm_base_documentation",
        new_callable=AsyncMock,
    ) as svc_mock:
        handler = cbd_mod.BaseDocsHandler()
        result = await handler.handle(
            message="listado",
            state=_base_state(user_message="listado"),
            mode_context={
                "expediente_sub_mode": CollectionStep.COLLECT_BASE_DOCS.value,
            },
            llm_loop_fn=llm_loop,
        )

    # Service NEVER called: the deterministic guard rejected the token.
    svc_mock.assert_not_called()
    # LLM loop IS called — normal flow preserved.
    llm_loop.assert_awaited_once()
    assert result["ai_response"] == "llm-handled"
