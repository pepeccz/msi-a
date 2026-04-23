"""
Phase 2 (fix-base-docs-transition-guard): deterministic completion guard.

Strict TDD — RED tests written BEFORE the implementation.

Covers:
  * `is_completion_token` helper — exact + typo-tolerant vocabulary
  * `BaseDocsHandler.handle()` deterministic close when
    docs are sufficient and the user types a completion token
  * Fall-through to the LLM when docs are insufficient
  * Regression: attachment-only guard still works
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch as _patch


# ---------------------------------------------------------------------------
# is_completion_token — pure helper tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "listo",
        "LISTO",
        "Listo",
        "LISTO ",
        "  listo  ",
        "Listo!",
    ],
)
def test_is_completion_token_exact_listo(raw: str) -> None:
    from agent.modes.submodos.collect_base_docs import is_completion_token

    assert is_completion_token(raw) is True


@pytest.mark.parametrize("raw", ["lisot", "listoo", "lixto", "listp"])
def test_is_completion_token_listo_typos(raw: str) -> None:
    from agent.modes.submodos.collect_base_docs import is_completion_token

    assert is_completion_token(raw) is True, f"expected listo-typo match for {raw!r}"


def test_is_completion_token_rejects_listado() -> None:
    from agent.modes.submodos.collect_base_docs import is_completion_token

    assert is_completion_token("listado") is False


@pytest.mark.parametrize("raw", ["hola", "buenas", "", "   ", "listoooooo"])
def test_is_completion_token_rejects_non_completion(raw: str) -> None:
    from agent.modes.submodos.collect_base_docs import is_completion_token

    assert is_completion_token(raw) is False


@pytest.mark.parametrize(
    "raw",
    ["ok", "OK", "dale", "ya", "termine", "terminé", "terminado", "finalizado", "fin"],
)
def test_is_completion_token_exact_vocabulary(raw: str) -> None:
    from agent.modes.submodos.collect_base_docs import is_completion_token

    assert is_completion_token(raw) is True


# ---------------------------------------------------------------------------
# BaseDocsHandler.handle() — deterministic close behaviour
# ---------------------------------------------------------------------------


def _base_state(**overrides):
    state = {
        "case_id": "case-1",
        "conversation_id": "conv-1",
        "incoming_attachments": [],
        "user_message": "",
    }
    state.update(overrides)
    return state


async def test_handler_deterministic_close_with_sufficient_docs() -> None:
    """When user types a completion token and the service reports success
    with `_transition_to`, the handler MUST NOT call the LLM loop and MUST
    surface the transition via `pending_state_updates`.
    """
    from agent.modes.submodos.collect_base_docs import BaseDocsHandler

    llm_loop = AsyncMock()
    service_result = {
        "success": True,
        "base_docs_confirmed": True,
        "message": "Documentación base recibida y registrada correctamente.",
        "_state_update": {
            "base_docs_registered": True,
            "can_narrate_next_step_details": False,
            "delivery_outcome_status": "not_requested",
            "_transition_to": "collect_personal",
        },
    }

    with _patch(
        "agent.modes.submodos.collect_base_docs.confirm_base_documentation",
        new_callable=AsyncMock,
        return_value=service_result,
    ) as svc_mock:
        handler = BaseDocsHandler()
        result = await handler.handle(
            message="lisot",
            state=_base_state(),
            mode_context={"expediente_sub_mode": "collect_base_docs"},
            llm_loop_fn=llm_loop,
        )

    svc_mock.assert_awaited_once()
    llm_loop.assert_not_called()
    assert result["pending_state_updates"]["_transition_to"] == "collect_personal"
    assert "Documentación base" in result["ai_response"]


async def test_handler_falls_through_on_insufficient_docs() -> None:
    """When docs are insufficient the service returns success=False; the
    handler MUST delegate to the LLM loop so it can reprompt for missing docs.
    """
    from agent.modes.submodos.collect_base_docs import BaseDocsHandler

    llm_loop = AsyncMock(
        return_value={"ai_response": "llm-handled", "mode_context": {}}
    )
    service_result = {
        "success": False,
        "message": "Faltan documentos.",
    }

    with _patch(
        "agent.modes.submodos.collect_base_docs.confirm_base_documentation",
        new_callable=AsyncMock,
        return_value=service_result,
    ):
        handler = BaseDocsHandler()
        result = await handler.handle(
            message="listo",
            state=_base_state(),
            mode_context={"expediente_sub_mode": "collect_base_docs"},
            llm_loop_fn=llm_loop,
        )

    llm_loop.assert_awaited_once()
    assert result["ai_response"] == "llm-handled"


async def test_handler_does_not_close_on_non_completion_text() -> None:
    """Non-completion text must skip the deterministic guard entirely
    (service never called) and delegate to the LLM loop.
    """
    from agent.modes.submodos.collect_base_docs import BaseDocsHandler

    llm_loop = AsyncMock(
        return_value={"ai_response": "llm-handled", "mode_context": {}}
    )

    with _patch(
        "agent.modes.submodos.collect_base_docs.confirm_base_documentation",
        new_callable=AsyncMock,
    ) as svc_mock:
        handler = BaseDocsHandler()
        await handler.handle(
            message="hola, ¿cómo va?",
            state=_base_state(),
            mode_context={"expediente_sub_mode": "collect_base_docs"},
            llm_loop_fn=llm_loop,
        )

    svc_mock.assert_not_called()
    llm_loop.assert_awaited_once()


async def test_handler_attachment_only_guard_still_works() -> None:
    """Regression: attachment-only turn (no text) must still go through the
    original ack path, NOT invoke the service, NOT call the LLM loop.
    """
    from agent.modes.submodos.collect_base_docs import BaseDocsHandler

    llm_loop = AsyncMock()
    with _patch(
        "agent.modes.submodos.collect_base_docs.confirm_base_documentation",
        new_callable=AsyncMock,
    ) as svc_mock:
        handler = BaseDocsHandler()
        result = await handler.handle(
            message="",
            state=_base_state(
                incoming_attachments=[{"type": "image"}, {"type": "document"}]
            ),
            mode_context={},
            llm_loop_fn=llm_loop,
        )

    svc_mock.assert_not_called()
    llm_loop.assert_not_called()
    assert "Recibidos" in result["ai_response"]
    assert '"listo"' in result["ai_response"]
