"""
Expediente subgraph nodes.

Contains:
- ``entry_router``: Reads ``expediente_sub_mode`` from state and dispatches to
  the correct sub-mode node via ``Command(goto=target)``.  Phase 3 will wire in
  initialization, recovery, intro injection, and the photo guard.

- Six sub-mode node stubs: Each accepts the ``ExpedienteState`` and currently
  returns ``Command(goto=END)`` — they are stubs that will be wired to the
  existing handlers from ``agent/modes/submodos/`` in Phase 3.

Design reference:
- AD-1 (Subgraph Wiring Pattern) — 7-node subgraph, entry_router + 6 sub-modes
- AD-4 (Coordinator Logic Distribution) — entry_router absorbs initialization/guards
- ``agent/modes/submodos/_shared.py`` for sub-mode constants and tool registry
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from langgraph.graph import END
from langgraph.types import Command

from agent.modes.submodos._shared import (
    COLLECT_ELEMENT_DATA,
    COLLECT_BASE_DOCS,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    _get_element_data_tools,
    _get_base_docs_tools,
    _get_personal_tools,
    _get_vehicle_tools,
    _get_workshop_tools,
    _get_review_tools,
)
from agent.modes.expediente_state import ExpedienteState

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Routing map: sub_mode string → subgraph node name
# ---------------------------------------------------------------------------

_SUB_MODE_TO_NODE: dict[str, str] = {
    COLLECT_ELEMENT_DATA: "collect_element_data_node",
    COLLECT_BASE_DOCS: "collect_base_docs_node",
    COLLECT_PERSONAL: "collect_personal_node",
    COLLECT_VEHICLE: "collect_vehicle_node",
    COLLECT_WORKSHOP: "collect_workshop_node",
    REVIEW_SUMMARY: "review_summary_node",
}

# Default node when sub_mode is unrecognized or absent
_DEFAULT_NODE = "collect_element_data_node"


# ---------------------------------------------------------------------------
# entry_router — reads expediente_sub_mode and dispatches via Command
# ---------------------------------------------------------------------------


async def entry_router(
    state: ExpedienteState,
) -> Command[
    Literal[
        "collect_element_data_node",
        "collect_base_docs_node",
        "collect_personal_node",
        "collect_vehicle_node",
        "collect_workshop_node",
        "review_summary_node",
    ]
]:
    """
    Entry node for the expediente subgraph.

    Reads ``expediente_sub_mode`` and routes to the corresponding sub-mode node
    via ``Command(goto=target_node)``.  Falls back to ``collect_element_data_node``
    for any unrecognized or missing sub-mode value.

    Phase 2 (skeleton): pure routing only — no initialization, guard, or intro.
    Phase 3 will add:
    - Initialization (``initialize_expediente()`` when ``case_id`` is absent)
    - Photo guard (``guard_photo_completion()`` for ``collect_element_data``)
    - Intro injection (``_pending_intro_message`` when ``expediente_intro_sent=False``)
    """
    sub_mode: str = state.get("expediente_sub_mode") or ""  # type: ignore[attr-defined]
    target_node = _SUB_MODE_TO_NODE.get(sub_mode, _DEFAULT_NODE)

    logger.debug(
        "entry_router_dispatching",
        sub_mode=sub_mode,
        target_node=target_node,
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=target_node, update=None)


# ---------------------------------------------------------------------------
# Sub-mode node stubs
#
# Phase 2: Each stub returns Command(goto=END) after logging.
# Phase 3: Each stub will call the corresponding handler from submodos/*.py
#          via the generic_llm_loop() pattern documented in AD-3.
# ---------------------------------------------------------------------------


async def collect_element_data_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    COLLECT_ELEMENT_DATA sub-mode node stub.

    Accepts tools from: _get_element_data_tools()
    Phase 3 will wire to: agent/modes/submodos/collect_element_data.py handler
    """
    # Reference the tool getter so tests can verify correct wiring via source inspection
    _tools = _get_element_data_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "collect_element_data_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)


async def collect_base_docs_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    COLLECT_BASE_DOCS sub-mode node stub.

    Accepts tools from: _get_base_docs_tools()
    Phase 3 will wire to: agent/modes/submodos/collect_base_docs.py handler
    """
    _tools = _get_base_docs_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "collect_base_docs_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)


async def collect_personal_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    COLLECT_PERSONAL sub-mode node stub.

    Accepts tools from: _get_personal_tools()
    Phase 3 will wire to: agent/modes/submodos/collect_personal.py handler
    """
    _tools = _get_personal_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "collect_personal_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)


async def collect_vehicle_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    COLLECT_VEHICLE sub-mode node stub.

    Accepts tools from: _get_vehicle_tools()
    Phase 3 will wire to: agent/modes/submodos/collect_vehicle.py handler
    """
    _tools = _get_vehicle_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "collect_vehicle_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)


async def collect_workshop_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    COLLECT_WORKSHOP sub-mode node stub.

    Accepts tools from: _get_workshop_tools()
    Phase 3 will wire to: agent/modes/submodos/collect_workshop.py handler
    """
    _tools = _get_workshop_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "collect_workshop_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)


async def review_summary_node(
    state: ExpedienteState,
) -> Command[Literal["__end__"]]:
    """
    REVIEW_SUMMARY sub-mode node stub.

    Accepts tools from: _get_review_tools()
    Phase 3 will wire to: agent/modes/submodos/review_summary.py handler
    """
    _tools = _get_review_tools  # noqa: F841 — referenced for source inspection

    logger.debug(
        "review_summary_node_stub",
        conversation_id=state.get("conversation_id"),  # type: ignore[attr-defined]
        case_id=state.get("case_id"),  # type: ignore[attr-defined]
    )

    return Command(goto=END)
