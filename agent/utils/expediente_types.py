"""
Expediente (case collection) type definitions and constants.

Extracted from fsm_compat.py as part of the FSM compat layer removal.
These are the canonical type definitions used across the agent for
case collection state tracking.
"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict


class CollectionStep(str, Enum):
    """FSM states for case data collection (element-by-element flow)."""

    IDLE = "idle"
    COLLECT_ELEMENT_DATA = "collect_element_data"
    COLLECT_BASE_DOCS = "collect_base_docs"
    COLLECT_PERSONAL = "collect_personal"
    COLLECT_VEHICLE = "collect_vehicle"
    COLLECT_WORKSHOP = "collect_workshop"
    REVIEW_SUMMARY = "review_summary"
    COMPLETED = "completed"


class CaseCollectionState(TypedDict, total=False):
    """
    Case collection state structure.

    In mode-based architecture, this is constructed from mode_context.
    """

    step: str
    case_id: str | None
    personal_data: dict[str, str | None]
    vehicle_data: dict[str, str | None]
    taller_propio: bool | None
    taller_data: dict[str, str | None] | None
    category_slug: str | None
    category_id: str | None
    element_codes: list[str]
    current_element_index: int
    element_phase: str
    element_data_status: dict[str, str]
    base_docs_received: bool
    base_doc_descriptions: list[str]
    received_images: list[str]
    tariff_tier_id: str | None
    tariff_amount: float | None
    last_prompt: str | None
    retry_count: int
    error_message: str | None


# Element status constants
ELEMENT_STATUS_PENDING = "pending"
ELEMENT_STATUS_PHOTOS_DONE = "photos_done"
ELEMENT_STATUS_DATA_DONE = "data_done"
ELEMENT_STATUS_COMPLETE = "complete"
