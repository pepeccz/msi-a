"""
MSI Automotive - FSM (Finite State Machine) module.

Provides state machines for complex conversation flows:
- Case collection: Collecting user data and images for homologation expedientes
"""

from agent.fsm.case_collection import (
    # Enums
    CollectionStep,
    # Types
    CaseFSMState,
    # State management
    create_initial_fsm_state,
    get_case_fsm_state,
    update_case_fsm_state,
    is_case_collection_active,
    get_current_step,
    # Transitions
    can_transition_to,
    transition_to,
    reset_fsm,
    # Validation
    validate_email,
    validate_matricula,
    normalize_matricula,
    validate_personal_data,
    validate_vehicle_data,
    # Helpers
    get_required_images_for_elements,
    get_step_prompt,
    # Constants
    MAX_RETRIES_PER_STEP,
)

__all__ = [
    # Enums
    "CollectionStep",
    # Types
    "CaseFSMState",
    # State management
    "create_initial_fsm_state",
    "get_case_fsm_state",
    "update_case_fsm_state",
    "is_case_collection_active",
    "get_current_step",
    # Transitions
    "can_transition_to",
    "transition_to",
    "reset_fsm",
    # Validation
    "validate_email",
    "validate_matricula",
    "normalize_matricula",
    "validate_personal_data",
    "validate_vehicle_data",
    # Helpers
    "get_required_images_for_elements",
    "get_step_prompt",
    # Constants
    "MAX_RETRIES_PER_STEP",
]
