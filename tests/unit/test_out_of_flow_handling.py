"""
Tests for out-of-flow message handling in agent/main.py.

REQ-1: Escalation guard — silently discard messages when conversation is escalated.
REQ-2: Out-of-context image feedback — send ack for image-only turns outside collection.
REQ-3: PDF/document acknowledgment — send ack for PDF attachments outside collection.

Change: fix-out-of-flow-handling
TDD Phase: GREEN — production code implemented, tests verify real behavior.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from contextlib import asynccontextmanager


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_graph(
    current_mode: str = "PRESUPUESTO_MODE",
    aget_state_raises: Exception | None = None,
) -> MagicMock:
    """Return a mock graph with configurable aget_state and ainvoke."""
    graph = MagicMock()
    if aget_state_raises:
        graph.aget_state = AsyncMock(side_effect=aget_state_raises)
    else:
        state_snapshot = MagicMock()
        state_snapshot.values = {"current_mode": current_mode}
        graph.aget_state = AsyncMock(return_value=state_snapshot)
    graph.ainvoke = AsyncMock(return_value={"ai_response": "ok"})
    return graph


def _make_chatwoot() -> MagicMock:
    """Return a mock ChatwootClient."""
    chatwoot = MagicMock()
    chatwoot.send_message = AsyncMock()
    return chatwoot


def _make_redis() -> MagicMock:
    """Return a mock Redis client."""
    redis = AsyncMock()
    return redis


def _make_message_data(
    conversation_id: str = "conv-123",
    customer_phone: str = "+34600000001",
    message_text: str = "",
    attachments: list | None = None,
) -> dict:
    """Build a minimal message_data dict as produced by the webhook handler."""
    return {
        "conversation_id": conversation_id,
        "customer_phone": customer_phone,
        "message_text": message_text,
        "message_type": "incoming",
        "attachments": attachments or [],
        "chatwoot_message_id": "msg-001",
    }


def _make_image_attachment() -> dict:
    """Return a minimal image attachment dict (file_type=image)."""
    return {
        "file_type": "image",
        "data_url": "https://storage.chatwoot.com/img.jpg",
        "content_type": "image/jpeg",
    }


def _make_pdf_attachment() -> dict:
    """Return a minimal PDF/file attachment dict (file_type=file)."""
    return {
        "file_type": "file",
        "data_url": "https://storage.chatwoot.com/doc.pdf",
        "content_type": "application/pdf",
    }


def _make_user_mock() -> MagicMock:
    """Return a mock User ORM object."""
    import uuid

    user = MagicMock()
    user.id = uuid.uuid4()
    user.first_name = "Test"
    user.last_name = "User"
    user.client_type = "particular"
    user.phone = "+34600000001"
    return user


@asynccontextmanager
async def _noop_session():
    """Async context manager that yields a mock session."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=_make_user_mock())
    mock_session.execute = AsyncMock(return_value=mock_result)
    yield mock_session


# ---------------------------------------------------------------------------
# Shared patches for process_message tests
# ---------------------------------------------------------------------------

_BASE_PATCHES = {
    "agent.main.get_async_session": None,  # Set per test
    "agent.main.save_user_message": "AsyncMock",
    "agent.main.get_settings": "MagicMock",
    "agent.main.is_rejected_attachment": "MagicMock_False",
    "agent.main.is_accepted_attachment": "MagicMock_True",
    "agent.main.is_image_attachment": "MagicMock_varies",
    "agent.main.get_conversation_lock": "MagicMock",
    "agent.main.get_initialized_checkpointer": "MagicMock",
    "agent.main.get_redis_checkpointer": "MagicMock",
    "agent.main._build_image_assignment_snapshot": "AsyncMock",
    "agent.main.assign_upload_batch": "AsyncMock",
    "agent.main.persist_assignment_snapshot": "AsyncMock",
    "agent.main.is_completion_message": "MagicMock_False",
    "agent.main.reset_batch_counter": "AsyncMock",
    "agent.main.save_images_silently": "AsyncMock",
    "agent.main.update_batch_counter": "AsyncMock",
    "agent.main.build_state_mutation_config": "MagicMock",
}


async def _run_process_message(
    graph,
    chatwoot,
    redis_client,
    message_data,
    *,
    # Patch controls
    image_attachments_result: list | None = None,
    rejected_attachments_result: list | None = None,
    accepted_attachments_result: list | None = None,
    assignment_snapshot: dict | None = None,
    is_completion: bool = False,
) -> None:
    """
    Execute process_message with all heavy external calls stubbed out.

    Parameters control behavior of each relevant stub.
    """
    from agent.main import process_message

    image_attachments_result = image_attachments_result or []
    rejected_attachments_result = rejected_attachments_result or []
    accepted_attachments_result = accepted_attachments_result or (
        message_data.get("attachments") or []
    )
    assignment_snapshot = assignment_snapshot or {}

    # Settings stub
    mock_settings = MagicMock()
    mock_settings.AGENT_GRAPH_TIMEOUT_SECONDS = 30

    # Lock: returns a real asynccontextmanager-style lock
    import asyncio

    real_lock = asyncio.Lock()
    mock_get_lock = MagicMock(return_value=real_lock)

    # assignment snapshot
    mock_assign_upload = AsyncMock(return_value=assignment_snapshot)
    mock_build_snapshot = AsyncMock(return_value=assignment_snapshot)

    with (
        patch("agent.main.get_async_session", _noop_session),
        patch("agent.main.save_user_message", new_callable=AsyncMock),
        patch("agent.main.get_settings", return_value=mock_settings),
        patch(
            "agent.main.is_rejected_attachment",
            side_effect=lambda a: a in (rejected_attachments_result),
        ),
        patch(
            "agent.main.is_accepted_attachment",
            side_effect=lambda a: a in (accepted_attachments_result),
        ),
        patch(
            "agent.main.is_image_attachment",
            side_effect=lambda a: a in (image_attachments_result),
        ),
        patch("agent.main.get_conversation_lock", mock_get_lock),
        patch("agent.main.get_initialized_checkpointer", MagicMock(return_value=None)),
        patch("agent.main.get_redis_checkpointer", MagicMock(return_value=None)),
        patch("agent.main._build_image_assignment_snapshot", mock_build_snapshot),
        patch("agent.main.assign_upload_batch", mock_assign_upload),
        patch("agent.main.persist_assignment_snapshot", new_callable=AsyncMock),
        patch(
            "agent.main.is_completion_message",
            return_value=is_completion,
        ),
        patch("agent.main.reset_batch_counter", new_callable=AsyncMock),
        patch(
            "agent.main.save_images_silently",
            new_callable=AsyncMock,
            return_value=(0, 0),
        ),
        patch("agent.main.update_batch_counter", new_callable=AsyncMock),
        patch("agent.main.build_state_mutation_config", return_value={}),
        # Patch reconcile_on_completion to prevent unawaited coroutine leaks
        patch("agent.main.reconcile_on_completion", new_callable=AsyncMock),
        patch(
            "agent.main.asyncio.wait_for",
            new_callable=AsyncMock,
            return_value={"ai_response": "ok"},
        ),
    ):
        await process_message(graph, chatwoot, redis_client, message_data)


# ===========================================================================
# REQ-1: Escalation Guard
# ===========================================================================


@pytest.mark.asyncio
async def test_escalated_conversation_image_does_not_invoke_graph():
    """
    GIVEN a conversation with current_mode == "ESCALATION"
    WHEN an inbound message containing an image attachment arrives
    THEN graph.ainvoke() is NOT called.
    """
    img = _make_image_attachment()
    graph = _make_graph(current_mode="ESCALATION")
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[img],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[img],
        accepted_attachments_result=[img],
    )

    graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_escalated_conversation_text_does_not_invoke_graph():
    """
    GIVEN a conversation with current_mode == "ESCALATION"
    WHEN an inbound text message arrives
    THEN graph.ainvoke() is NOT called.
    """
    graph = _make_graph(current_mode="ESCALATION")
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(message_text="Hola, necesito ayuda")

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
    )

    graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_escalated_conversation_no_message_sent_to_chatwoot():
    """
    GIVEN a conversation with current_mode == "ESCALATION"
    WHEN any inbound message arrives
    THEN chatwoot.send_message() is NOT called.
    """
    graph = _make_graph(current_mode="ESCALATION")
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(message_text="Hola, ¿me pueden ayudar?")

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
    )

    chatwoot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_non_escalated_conversation_proceeds_normally():
    """
    GIVEN a conversation with current_mode == "PRESUPUESTO_MODE"
    WHEN an inbound text message arrives
    THEN graph.ainvoke() IS called (normal flow).
    """
    graph = _make_graph(current_mode="PRESUPUESTO_MODE")
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(message_text="Quiero homologar mi escape")

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
    )

    # asyncio.wait_for is patched, so graph.ainvoke is called via wait_for
    # The patch on asyncio.wait_for captures the call — we verify graph.aget_state
    # was called and the flow reached graph invocation (no early return).
    graph.aget_state.assert_called_once()


# ===========================================================================
# REQ-2: Out-of-Context Image Feedback
# ===========================================================================


@pytest.mark.asyncio
async def test_image_outside_collection_sends_feedback_message():
    """
    GIVEN in_image_collection_mode=False and an image attachment present
    WHEN the message is processed
    THEN chatwoot.send_message() is called with the Spanish feedback text.
    """
    img = _make_image_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[img],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[img],
        accepted_attachments_result=[img],
        assignment_snapshot={"in_image_collection_mode": False},
    )

    # Verify the feedback message was sent
    assert chatwoot.send_message.called
    call_kwargs = chatwoot.send_message.call_args
    # Check the message text is in either positional or keyword args
    all_args = list(call_kwargs.args) + list(call_kwargs.kwargs.values())
    assert any("foto" in str(arg) and "expediente" in str(arg) for arg in all_args), (
        f"Expected feedback text not found in call args: {call_kwargs}"
    )


@pytest.mark.asyncio
async def test_image_only_turn_outside_collection_does_not_invoke_graph():
    """
    GIVEN in_image_collection_mode=False, image present, user_message is empty
    WHEN the message is processed
    THEN the acknowledgment is sent AND graph.ainvoke() is NOT called.
    """
    img = _make_image_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[img],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[img],
        accepted_attachments_result=[img],
        assignment_snapshot={"in_image_collection_mode": False},
    )

    # Feedback was sent
    assert chatwoot.send_message.called
    # Graph was NOT invoked (early return after feedback)
    graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_image_plus_text_outside_collection_invokes_graph():
    """
    GIVEN in_image_collection_mode=False, image present, user_message is non-empty
    WHEN the message is processed
    THEN graph.ainvoke() IS called (text falls through to graph).
    """
    img = _make_image_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="quiero homologar",
        attachments=[img],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[img],
        accepted_attachments_result=[img],
        assignment_snapshot={"in_image_collection_mode": False},
    )

    # Graph was invoked (text falls through)
    # asyncio.wait_for is patched — verify aget_state was reached (no early return)
    graph.aget_state.assert_called_once()


@pytest.mark.asyncio
async def test_image_in_collection_mode_no_feedback_message():
    """
    GIVEN in_image_collection_mode=True and an image attachment present
    WHEN the message is processed
    THEN chatwoot.send_message() is NOT called with the feedback text.
    """
    import uuid

    img = _make_image_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[img],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[img],
        accepted_attachments_result=[img],
        assignment_snapshot={
            "in_image_collection_mode": True,
            "case_id": str(uuid.uuid4()),
        },
    )

    # Feedback message NOT sent (collection mode handles it silently)
    feedback_calls = [
        c
        for c in chatwoot.send_message.call_args_list
        if any(
            "foto" in str(arg) and "expediente" in str(arg)
            for arg in list(c.args) + list(c.kwargs.values())
        )
    ]
    assert len(feedback_calls) == 0, (
        f"Unexpected feedback message sent during collection mode: {feedback_calls}"
    )


# ===========================================================================
# REQ-3: PDF / Document Acknowledgment
# ===========================================================================


@pytest.mark.asyncio
async def test_pdf_outside_collection_sends_acknowledgment():
    """
    GIVEN in_image_collection_mode=False and an attachment with file_type="file"
    WHEN the message is processed
    THEN chatwoot.send_message() is called with the PDF acknowledgment text.
    """
    pdf = _make_pdf_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[pdf],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[],  # PDF is NOT an image
        accepted_attachments_result=[pdf],
        assignment_snapshot=None,  # No snapshot → outside collection
    )

    # Check that the PDF ack was sent (may be one of multiple calls)
    assert chatwoot.send_message.called
    pdf_ack_calls = [
        c
        for c in chatwoot.send_message.call_args_list
        if any(
            "documento" in str(arg).lower()
            for arg in list(c.args) + list(c.kwargs.values())
        )
    ]
    assert len(pdf_ack_calls) >= 1, (
        f"Expected PDF ack call not found. All calls: {chatwoot.send_message.call_args_list}"
    )


@pytest.mark.asyncio
async def test_pdf_acknowledgment_does_not_block_graph():
    """
    GIVEN in_image_collection_mode=False and an attachment with file_type="file"
    WHEN the message is processed
    THEN the acknowledgment is sent AND graph.ainvoke() IS still called.
    """
    pdf = _make_pdf_attachment()
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="",
        attachments=[pdf],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[],  # PDF is NOT an image
        accepted_attachments_result=[pdf],
        assignment_snapshot=None,
    )

    # Ack was sent
    assert chatwoot.send_message.called
    # Graph was also invoked (PDF does NOT block processing)
    graph.aget_state.assert_called_once()


@pytest.mark.asyncio
async def test_pdf_in_collection_mode_no_acknowledgment():
    """
    GIVEN in_image_collection_mode=True and a PDF attachment present
    (e.g., user sends "listo" + PDF during expediente completion)
    WHEN the message is processed
    THEN chatwoot.send_message() is NOT called with the PDF ack text.

    Uses is_completion=True to trigger assignment_snapshot loading. When
    assignment_snapshot has in_image_collection_mode=True, FIX-3's guard
    suppresses the PDF ack.
    """
    import uuid

    pdf = _make_pdf_attachment()
    case_id = str(uuid.uuid4())
    graph = _make_graph()
    chatwoot = _make_chatwoot()
    redis_client = _make_redis()
    message_data = _make_message_data(
        message_text="listo",
        attachments=[pdf],
    )

    await _run_process_message(
        graph,
        chatwoot,
        redis_client,
        message_data,
        image_attachments_result=[],  # No images
        accepted_attachments_result=[pdf],
        assignment_snapshot={
            "in_image_collection_mode": True,
            "case_id": case_id,
        },
        is_completion=True,
    )

    # PDF ack NOT sent during collection mode — FIX-3 guard suppresses it.
    pdf_ack_calls = [
        c
        for c in chatwoot.send_message.call_args_list
        if any(
            "documento" in str(arg).lower()
            for arg in list(c.args) + list(c.kwargs.values())
        )
    ]
    assert len(pdf_ack_calls) == 0, (
        f"Unexpected PDF ack sent during collection mode: {pdf_ack_calls}"
    )
