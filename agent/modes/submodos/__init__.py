# Re-export handler-agnostic public symbols from _shared for external callers.
# This allows code that previously imported from expediente_mode to continue
# working after the Phase A refactor.

from agent.modes.submodos._shared import (  # noqa: F401
    # Sub-mode constants
    COLLECT_ELEMENT_DATA,
    COLLECT_BASE_DOCS,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    MAX_TOOL_ITERATIONS,
    # Step maps
    SUB_MODE_STEP,
    _SUBMODE_STEP_MAP,
    _SUB_MODE_TO_COLLECTION_STEP,
    _POST_BASE_DOCS_SUB_MODES,
    # Tool matrix
    EXPEDIENTE_TOOL_MATRIX,
    # Progress
    EXPEDIENTE_STEP_PREFIX,
    EXPEDIENTE_INTRO_MESSAGE,
    # Element state machine
    ELEMENT_STATE_AWAITING_PHOTOS,
    ELEMENT_STATE_PHOTOS_RECEIVED,
    ELEMENT_STATE_CONFIRMING_PHOTOS,
    ELEMENT_STATE_RETRY_PHOTOS,
    ELEMENT_STATE_PHOTOS_CONFIRMED,
    ELEMENT_STATE_DATA_COLLECTION,
    ELEMENT_STATE_ELEMENT_COMPLETE,
    ELEMENT_STATES,
)

# Phase B: all 6 handler classes
from agent.modes.submodos.collect_personal import PersonalHandler  # noqa: F401
from agent.modes.submodos.collect_vehicle import VehicleHandler  # noqa: F401
from agent.modes.submodos.collect_workshop import WorkshopHandler  # noqa: F401
from agent.modes.submodos.collect_base_docs import BaseDocsHandler  # noqa: F401
from agent.modes.submodos.review_summary import ReviewHandler  # noqa: F401
from agent.modes.submodos.collect_element_data import ElementDataHandler  # noqa: F401
from agent.modes.submodos.loop_engine import ExpedienteLoopEngine  # noqa: F401
