"""Regression tests for resume-bot state mutation using a REAL checkpointer.

TDD: RED -> GREEN -> REFACTOR. Without an explicit `as_node`, LangGraph's
ambiguous-update inference writes a degenerate `versions_seen` on a
checkpoint-less thread's first `aupdate_state` call; the next call on that
thread then raises `InvalidUpdateError`. `resume_bot()` chains three such
calls, so it 500s on the first resume of such a thread.

These tests assert the DESIRED behavior (the sequence succeeds), not
`pytest.raises(InvalidUpdateError)`, so they survive as permanent regression
guards once fixed.

Uses a real `StateGraph` + `MemorySaver` (NOT `AsyncMock`, NOT the real
conversation graph — that compiles the expediente subgraph + every mode
node). The inference bug depends only on checkpoint/versions_seen/node
names, never on node bodies, so a minimal graph with an entry node named
from STATE_MUTATION_AS_NODE reproduces it exactly. Precedent:
tests/unit/test_expediente_e2e.py.
"""

# NOTE: deliberately NO `from __future__ import annotations` here. LangGraph
# resolves a state schema's annotations via `get_type_hints()`, and stringized
# annotations fail to resolve (`NameError: Annotated`) once the test module is
# no longer reachable through `sys.modules` under its own name.

from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agent.state.mutation_config import STATE_MUTATION_AS_NODE
from api.services.state_snapshot_service import (
    inject_human_messages_to_state,
    restore_state,
)


class _MiniState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    current_mode: str
    mode_context: dict


@pytest.fixture
def real_graph() -> Any:
    """Minimal graph; entry node name == STATE_MUTATION_AS_NODE (load-bearing:
    breaks loudly if the constant drifts from the graph's entry node)."""
    graph = StateGraph(_MiniState)
    graph.add_node(STATE_MUTATION_AS_NODE, lambda state: {})
    graph.add_node("router", lambda state: {})
    graph.add_edge(START, STATE_MUTATION_AS_NODE)
    graph.add_edge(STATE_MUTATION_AS_NODE, "router")
    graph.add_edge("router", END)
    return graph.compile(checkpointer=MemorySaver())


def _make_snapshot(
    *,
    thread_id: str,
    current_mode: str = "PRE_EXPEDIENTE_MODE",
    messages: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "thread_id": thread_id,
        "state": {"current_mode": current_mode, "messages": messages or []},
    }


def _make_fake_session(interval_messages: list[Any]) -> AsyncMock:
    """No DB: the select() is built but never executed against one."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = interval_messages
    session.execute = AsyncMock(return_value=execute_result)
    return session


def _make_interval_message(
    *,
    author_type: str = "human_agent",
    content: str = "Hola, ¿cómo va todo?",
    created_at: datetime | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = uuid4()
    msg.author_type = author_type
    msg.author_user_id = uuid4() if author_type == "human_agent" else None
    msg.content = content
    msg.created_at = created_at or datetime.now(UTC)
    msg.chatwoot_message_id = None
    return msg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_state_twice_on_same_thread_succeeds(real_graph: Any) -> None:
    """Two sequential restore_state() calls on the same thread never raise.

    Call #1 on a checkpoint-less thread writes a degenerate versions_seen
    map today; call #2 currently raises InvalidUpdateError.
    """
    thread_id = "thread-red-1"
    snapshot = _make_snapshot(thread_id=thread_id)

    await restore_state(chatwoot_conversation_id=thread_id, snapshot=snapshot, graph=real_graph)
    await restore_state(chatwoot_conversation_id=thread_id, snapshot=snapshot, graph=real_graph)

    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await real_graph.aget_state(config)
    assert checkpoint.values["current_mode"] == "PRE_EXPEDIENTE_MODE"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_sequence_restore_then_inject_succeeds(real_graph: Any) -> None:
    """restore_state -> inject_human_messages_to_state succeeds; add_messages
    accumulates restored history, injected HumanMessage, then the marker."""
    thread_id = "thread-red-2"
    paused_at = datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)

    snapshot = _make_snapshot(
        thread_id=thread_id,
        messages=[{"type": "ai", "content": "Bienvenido, ¿en qué te ayudo?"}],
    )
    await restore_state(chatwoot_conversation_id=thread_id, snapshot=snapshot, graph=real_graph)

    interval_message = _make_interval_message(
        content="Te atiende un agente humano",
        created_at=datetime(2026, 5, 11, 11, 0, 0, tzinfo=UTC),
    )
    injected_count = await inject_human_messages_to_state(
        chatwoot_conversation_id=thread_id,
        conversation_history_id=uuid4(),
        paused_at=paused_at,
        session=_make_fake_session([interval_message]),
        graph=real_graph,
    )
    assert injected_count == 1

    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await real_graph.aget_state(config)
    messages = checkpoint.values["messages"]

    assert len(messages) == 3
    assert messages[0].content == "Bienvenido, ¿en qué te ayudo?"
    assert messages[1].additional_kwargs.get("author_type") == "human_agent"
    assert messages[1].content == "Te atiende un agente humano"
    assert "[Reanudación]" in messages[2].content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_sequence_is_idempotent(real_graph: Any) -> None:
    """Full resume chain run twice never raises; each run appends exactly
    one marker (accumulation via add_messages is correct, not a bug)."""
    thread_id = "thread-red-3"
    paused_at = datetime(2026, 5, 11, 10, 0, 0, tzinfo=UTC)

    async def _run_resume_sequence() -> None:
        snapshot = _make_snapshot(thread_id=thread_id)
        await restore_state(chatwoot_conversation_id=thread_id, snapshot=snapshot, graph=real_graph)
        interval_message = _make_interval_message(
            author_type="user",
            content="Sigo esperando",
            created_at=datetime(2026, 5, 11, 11, 0, 0, tzinfo=UTC),
        )
        await inject_human_messages_to_state(
            chatwoot_conversation_id=thread_id,
            conversation_history_id=uuid4(),
            paused_at=paused_at,
            session=_make_fake_session([interval_message]),
            graph=real_graph,
        )

    await _run_resume_sequence()
    await _run_resume_sequence()

    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = await real_graph.aget_state(config)
    messages = checkpoint.values["messages"]

    resume_markers = [m for m in messages if "[Reanudación]" in getattr(m, "content", "")]
    assert len(resume_markers) == 2
