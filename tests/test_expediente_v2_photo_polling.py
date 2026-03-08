"""Unit tests for TASK-14 two-phase photo polling in confirmar_fotos_elemento."""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agent.utils.fsm_compat import CollectionStep


def _build_state() -> dict:
    return {
        "conversation_id": "123",
        "user_phone": "+34600000000",
        "fsm_state": {
            "case_collection": {
                "step": CollectionStep.COLLECT_ELEMENT_DATA.value,
                "case_id": str(uuid4()),
                "category_id": str(uuid4()),
                "element_codes": ["SUBCHASIS"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {"SUBCHASIS": "pending_photos"},
            }
        },
    }


def _patch_common(
    image_count_side_effect: list[int],
    call_order: list[str],
) -> tuple[ExitStack, AsyncMock]:
    """Patch dependencies needed by confirmar_fotos_elemento for polling tests."""
    state = _build_state()
    case_state = state["fsm_state"]["case_collection"]

    sleep_mock = AsyncMock(side_effect=lambda *_args, **_kwargs: call_order.append("sleep"))
    image_count_mock = AsyncMock(side_effect=image_count_side_effect)

    chatwoot_instance = MagicMock()

    async def _send_message(**_kwargs):
        call_order.append("send")
        return {"id": 1}

    chatwoot_instance.send_message = AsyncMock(side_effect=_send_message)

    stack = ExitStack()
    stack.enter_context(
        patch("agent.tools.element_data_tools.get_current_state", return_value=state)
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.get_case_fsm_state", return_value=case_state)
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.get_current_step", return_value=CollectionStep.COLLECT_ELEMENT_DATA)
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.get_current_element_code", return_value="SUBCHASIS")
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.get_element_phase", return_value="photos")
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools._get_element_image_count", image_count_mock)
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools._get_element_by_code", AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="Subchasis")))
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools._get_required_fields_for_element", AsyncMock(return_value=[]))
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools._update_case_element_data", AsyncMock())
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.transition_to", return_value={"case_collection": {}})
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.update_case_fsm_state", return_value={"case_collection": {}})
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools.asyncio.sleep", sleep_mock)
    )
    stack.enter_context(
        patch("agent.tools.element_data_tools._tool_error_response", side_effect=lambda msg, **_kw: {"success": False, "error": msg})
    )
    stack.enter_context(
        patch("shared.chatwoot_client.ChatwootClient", return_value=chatwoot_instance)
    )

    # Keep waits deterministic in assertions
    stack.enter_context(
        patch(
            "shared.config.get_settings",
            return_value=SimpleNamespace(
                PHOTO_COMPLETION_WAIT_SECONDS=5,
                PHOTO_COMPLETION_RETRY_WAIT_SECONDS=10,
            ),
        )
    )

    return stack, sleep_mock


@pytest.mark.asyncio
async def test_confirmar_fotos_success_on_first_poll() -> None:
    from agent.tools.element_data_tools import confirmar_fotos_elemento

    call_order: list[str] = []
    stack, sleep_mock = _patch_common([0, 1], call_order)
    with stack:
        result = await confirmar_fotos_elemento.ainvoke({"usuario_confirma": True})

    assert result["success"] is True
    assert sleep_mock.await_count == 1
    assert "send" in call_order
    assert call_order.index("send") < call_order.index("sleep")


@pytest.mark.asyncio
async def test_confirmar_fotos_success_on_second_poll() -> None:
    from agent.tools.element_data_tools import confirmar_fotos_elemento

    call_order: list[str] = []
    stack, sleep_mock = _patch_common([0, 0, 1], call_order)
    with stack:
        result = await confirmar_fotos_elemento.ainvoke({"usuario_confirma": True})

    assert result["success"] is True
    assert sleep_mock.await_count == 2


@pytest.mark.asyncio
async def test_confirmar_fotos_fail_after_both_polls() -> None:
    from agent.tools.element_data_tools import confirmar_fotos_elemento

    call_order: list[str] = []
    stack, sleep_mock = _patch_common([0, 0, 0], call_order)
    with stack:
        result = await confirmar_fotos_elemento.ainvoke({"usuario_confirma": True})

    assert result["success"] is False
    assert "No he podido recuperar" in result["message"]
    assert sleep_mock.await_count == 2
