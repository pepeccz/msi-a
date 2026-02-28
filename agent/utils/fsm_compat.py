"""
FSM Compatibility Layer for Mode-Based Architecture.

This module provides backward compatibility for v1 tools that expect FSM-based state.
It translates mode_context (current architecture) to FSM state structure (v1 tools).

Architecture:
    - Current: mode_context stores sub-mode + case data
    - v1: fsm_state stores FSM step + case data
    - This layer: Bridges the two by reading from mode_context and exposing FSM API

Usage:
    Tools import from here instead of v1's agent.fsm.case_collection:
    
    # Old (v1, archived)
    from archive.agent-v1.fsm.case_collection import get_current_step, CollectionStep
    
    # Current (compatibility layer)
    from agent.utils.fsm_compat import get_current_step, CollectionStep

Deprecation Status:
    This module is quarantined for future migration.  All public functions
    are instrumented with ``@deprecated_compat`` so usage is tracked via
    structured logs.  See agent-harmony-latency-hardening Phase 2.

Author: MSI-a Team
Date: 2026-02-02
"""

from __future__ import annotations

import functools
import inspect
import re
from enum import Enum
from typing import Any, Callable, TypedDict, TypeVar

import structlog

from agent.state.helpers import get_current_state

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Deprecation decorator for FSM-compat quarantine
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def deprecated_compat(*, replacement: str) -> Callable[[F], F]:
    """
    Mark a public FSM-compat function as deprecated.

    Instruments the function with structured logging so usage can be
    tracked without breaking callers.

    Behavior:
    - ``ENABLE_STATE_CONTRACT_ENFORCEMENT = True``  → logs at WARNING.
    - ``ENABLE_STATE_CONTRACT_ENFORCEMENT = False`` → logs at DEBUG.

    The decorator does NOT alter runtime behavior — it only instruments.

    Args:
        replacement: Human-readable description of the canonical replacement
            (e.g. ``"use mode_context directly"``).

    Returns:
        Decorated function with identical signature and behavior.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Gather caller info for telemetry
            frame = inspect.currentframe()
            caller_frame = frame.f_back if frame else None
            caller_info = "unknown"
            if caller_frame:
                caller_info = (
                    f"{caller_frame.f_code.co_filename}:{caller_frame.f_lineno}"
                    f" in {caller_frame.f_code.co_name}"
                )

            # Determine log level from feature flag
            from agent.utils.feature_flags import is_flag_enabled

            enforce = is_flag_enabled("ENABLE_STATE_CONTRACT_ENFORCEMENT")

            log_kwargs = {
                "function": fn.__name__,
                "caller": caller_info,
                "replacement": replacement,
            }

            if enforce:
                logger.warning("fsm_compat_deprecated_usage", **log_kwargs)
            else:
                logger.debug("fsm_compat_usage", **log_kwargs)

            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator

# =============================================================================
# CollectionStep Enum (Exact copy from v1 for compatibility)
# =============================================================================


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


# =============================================================================
# CaseFSMState TypedDict (Exact copy from v1 for compatibility)
# =============================================================================


class CaseFSMState(TypedDict, total=False):
    """
    FSM state structure for case collection.
    
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


# =============================================================================
# Element Status Constants
# =============================================================================

ELEMENT_STATUS_PENDING = "pending"
ELEMENT_STATUS_PHOTOS_DONE = "photos_done"
ELEMENT_STATUS_DATA_DONE = "data_done"  # Shouldn't happen normally
ELEMENT_STATUS_COMPLETE = "complete"


# =============================================================================
# Validation Regexes (Copy from v1)
# =============================================================================

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

MATRICULA_REGEX = re.compile(
    r"^([0-9]{4}[A-Z]{3}|[A-Z]{1,2}[0-9]{4}[A-Z]{0,2})$",
    re.IGNORECASE,
)

DNI_CIF_REGEX = re.compile(
    r"^([0-9]{8}[A-Z]|[XYZ][0-9]{7}[A-Z]|[A-Z][0-9]{7,8}[A-Z0-9]?)$",
    re.IGNORECASE,
)

CP_REGEX = re.compile(r"^(0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}$")


# =============================================================================
# Mode-Context to FSM Mapping
# =============================================================================


def _get_fsm_state_from_context() -> CaseFSMState:
    """
    Construct FSM state from current conversation state's mode_context.
    
    This is the CORE translation function. It reads mode_context and
    reconstructs the FSM state that v1 tools expect.
    
    Returns:
        CaseFSMState compatible with v1 tools
    """
    state = get_current_state()
    if not state:
        return _create_initial_fsm_state()
    
    mode_context = state.get("mode_context", {})
    current_mode = state.get("current_mode", "START")
    
    # If not in EXPEDIENTE mode, return IDLE
    if current_mode != "EXPEDIENTE_MODE":
        return _create_initial_fsm_state()
    
    # Map expediente sub-mode to FSM step
    sub_mode = mode_context.get("expediente_sub_mode", "collect_element_data")
    fsm_step = sub_mode  # Sub-modes use same names as FSM steps
    
    # Extract case data from mode_context
    case_id = mode_context.get("case_id")
    category_id = mode_context.get("category_id")
    category_slug = mode_context.get("category_slug")
    element_codes = mode_context.get("element_codes", [])
    
    # Element-by-element tracking
    current_element_index = mode_context.get("current_element_index", 0)
    element_phase = mode_context.get("element_phase", "photos")
    element_data_status = mode_context.get("element_data_status", {})
    
    # Personal/vehicle/workshop data
    personal_data = mode_context.get("personal_data", {})
    vehicle_data = mode_context.get("vehicle_data", {})
    taller_propio = mode_context.get("taller_propio")
    taller_data = mode_context.get("taller_data")
    
    # Base docs
    base_docs_received = mode_context.get("base_docs_received", False)
    base_doc_descriptions = mode_context.get("base_doc_descriptions", [])
    
    # Tariff info
    tariff_tier_id = mode_context.get("tariff_tier_id")
    tariff_amount = mode_context.get("tariff_amount")
    
    # Images (if tracked)
    received_images = mode_context.get("received_images", [])
    
    # Construct FSM state
    fsm_state = CaseFSMState(
        step=fsm_step,
        case_id=case_id,
        category_slug=category_slug,
        category_id=category_id,
        element_codes=element_codes,
        current_element_index=current_element_index,
        element_phase=element_phase,
        element_data_status=element_data_status,
        personal_data=personal_data,
        vehicle_data=vehicle_data,
        taller_propio=taller_propio,
        taller_data=taller_data,
        base_docs_received=base_docs_received,
        base_doc_descriptions=base_doc_descriptions,
        received_images=received_images,
        tariff_tier_id=tariff_tier_id,
        tariff_amount=tariff_amount,
        last_prompt=None,
        retry_count=0,
        error_message=None,
    )
    
    return fsm_state


def _create_initial_fsm_state() -> CaseFSMState:
    """Create a fresh FSM state (IDLE)."""
    return CaseFSMState(
        step=CollectionStep.IDLE.value,
        case_id=None,
        personal_data={},
        vehicle_data={},
        taller_propio=None,
        taller_data=None,
        category_slug=None,
        category_id=None,
        element_codes=[],
        current_element_index=0,
        element_phase="photos",
        element_data_status={},
        base_docs_received=False,
        base_doc_descriptions=[],
        received_images=[],
        tariff_tier_id=None,
        tariff_amount=None,
        last_prompt=None,
        retry_count=0,
        error_message=None,
    )


# =============================================================================
# FSM Helper Functions (Compatible with v1 tools)
# =============================================================================


@deprecated_compat(replacement="read from mode_context directly")
def get_case_fsm_state(fsm_state: dict[str, Any] | None) -> CaseFSMState:
    """
    Extract case collection FSM state.
    
    In mode-based architecture, we ignore the input and reconstruct from context.
    This ensures tools always get fresh state from mode_context.
    
    Args:
        fsm_state: Ignored (kept for API compatibility)
    
    Returns:
        CaseFSMState constructed from current mode_context
    """
    return _get_fsm_state_from_context()


@deprecated_compat(replacement="return mode_context updates from tool/node directly")
def update_case_fsm_state(
    fsm_state: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Update case collection FSM state with MERGE semantics.
    
    In mode-based architecture, this returns updates for mode_context.
    The mode node will apply these to mode_context.
    
    Chained calls accumulate updates instead of overwriting:
        step1 = transition_to(state, COLLECT_BASE_DOCS)
        step2 = update_case_fsm_state(step1, {"element_data_status": {...}})
        # step2 contains BOTH "step" and "element_data_status"
    
    Args:
        fsm_state: Previous FSM state (merged with new updates)
        updates: New updates to apply
    
    Returns:
        Dict with "case_collection" key containing merged updates
    """
    # Merge with existing case_collection if present (chained calls)
    existing: dict[str, Any] = {}
    if isinstance(fsm_state, dict) and "case_collection" in fsm_state:
        existing = dict(fsm_state["case_collection"])
    existing.update(updates)
    return {"case_collection": existing}


@deprecated_compat(replacement="read mode_context['expediente_sub_mode'] directly")
def get_current_step(fsm_state: dict[str, Any] | None) -> CollectionStep:
    """
    Get the current collection step.
    
    Args:
        fsm_state: Ignored (reconstructed from context)
    
    Returns:
        CollectionStep enum value
    """
    case_state = get_case_fsm_state(fsm_state)
    step_value = case_state.get("step", CollectionStep.IDLE.value)
    try:
        return CollectionStep(step_value)
    except ValueError:
        return CollectionStep.IDLE


@deprecated_compat(replacement="return {'expediente_sub_mode': target} from node")
def transition_to(
    fsm_state: dict[str, Any] | None,
    target_step: CollectionStep,
) -> dict[str, Any]:
    """
    Transition to a new FSM step.
    
    Args:
        fsm_state: Current FSM state (ignored)
        target_step: Target CollectionStep
    
    Returns:
        Updated FSM state dict
    """
    return update_case_fsm_state(fsm_state, {"step": target_step.value})


# =============================================================================
# Element-Specific Helper Functions
# =============================================================================


@deprecated_compat(replacement="read mode_context['element_codes'][mode_context['current_element_index']]")
def get_current_element_code(fsm_state: CaseFSMState) -> str | None:
    """
    Get the current element code being collected.
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        Element code string or None
    """
    element_codes = fsm_state.get("element_codes", [])
    current_idx = fsm_state.get("current_element_index", 0)
    
    if not element_codes or current_idx >= len(element_codes):
        return None
    
    return element_codes[current_idx]


@deprecated_compat(replacement="read mode_context['element_phase'] directly")
def get_element_phase(fsm_state: CaseFSMState) -> str:
    """
    Get the current phase for element collection: 'photos' or 'data'.
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        Phase string ("photos" or "data")
    """
    return fsm_state.get("element_phase", "photos")


@deprecated_compat(replacement="check mode_context['element_data_status'][code] directly")
def is_current_element_photos_done(fsm_state: CaseFSMState) -> bool:
    """
    Check if photos are done for the current element.
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        True if photos done, False otherwise
    """
    element_code = get_current_element_code(fsm_state)
    if not element_code:
        return False
    
    status = fsm_state.get("element_data_status", {}).get(element_code, ELEMENT_STATUS_PENDING)
    return status in (ELEMENT_STATUS_PHOTOS_DONE, ELEMENT_STATUS_COMPLETE)


@deprecated_compat(replacement="check mode_context['element_data_status'][code] == 'complete'")
def is_current_element_complete(fsm_state: CaseFSMState) -> bool:
    """
    Check if the current element is fully complete (photos + data).
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        True if complete, False otherwise
    """
    element_code = get_current_element_code(fsm_state)
    if not element_code:
        return False
    
    status = fsm_state.get("element_data_status", {}).get(element_code, ELEMENT_STATUS_PENDING)
    return status == ELEMENT_STATUS_COMPLETE


@deprecated_compat(replacement="check all mode_context['element_data_status'] values == 'complete'")
def are_all_elements_complete(fsm_state: CaseFSMState) -> bool:
    """
    Check if all elements have been fully collected (photos + data).
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        True if all complete, False otherwise
    """
    element_codes = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    
    if not element_codes:
        return True  # No elements = done
    
    return all(
        element_status.get(code) == ELEMENT_STATUS_COMPLETE
        for code in element_codes
    )


@deprecated_compat(replacement="update mode_context['element_data_status'] directly")
def update_element_status(
    fsm_state: dict[str, Any] | None,
    element_code: str,
    new_status: str,
) -> dict[str, Any]:
    """
    Update the status of a specific element.
    
    Args:
        fsm_state: Current FSM state (ignored)
        element_code: Element code to update
        new_status: New status value (use ELEMENT_STATUS_* constants)
    
    Returns:
        Updated fsm_state dict (for mode_context update)
    """
    case_state = get_case_fsm_state(fsm_state)
    element_data_status = case_state.get("element_data_status", {}).copy()
    element_data_status[element_code] = new_status
    
    return update_case_fsm_state(fsm_state, {"element_data_status": element_data_status})


@deprecated_compat(replacement="compute progress from mode_context keys directly")
def get_element_collection_progress(fsm_state: CaseFSMState) -> dict[str, Any]:
    """
    Get a summary of element collection progress.
    
    Args:
        fsm_state: CaseFSMState dict
    
    Returns:
        Dict with progress info
    """
    element_codes = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    current_idx = fsm_state.get("current_element_index", 0)
    phase = fsm_state.get("element_phase", "photos")
    
    completed = sum(
        1 for code in element_codes
        if element_status.get(code) == ELEMENT_STATUS_COMPLETE
    )
    
    current_code = element_codes[current_idx] if current_idx < len(element_codes) else None
    
    elements_info = [
        {
            "code": code,
            "status": element_status.get(code, ELEMENT_STATUS_PENDING),
            "is_current": code == current_code,
        }
        for code in element_codes
    ]
    
    return {
        "total_elements": len(element_codes),
        "completed_elements": completed,
        "current_element_index": current_idx,
        "current_element_code": current_code,
        "current_phase": phase,
        "elements": elements_info,
    }


# =============================================================================
# Validation Functions (Copy from v1)
# =============================================================================


@deprecated_compat(replacement="use Pydantic EmailStr or agent.utils.tool_decorators.validate_email")
def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


@deprecated_compat(replacement="use dedicated validation in agent.utils.tool_decorators")
def validate_matricula(matricula: str) -> bool:
    """Validate Spanish vehicle plate format."""
    if not matricula:
        return False
    clean = matricula.strip().replace(" ", "").replace("-", "").upper()
    return bool(MATRICULA_REGEX.match(clean))


@deprecated_compat(replacement="use dedicated normalization in agent.utils.tool_decorators")
def normalize_matricula(matricula: str) -> str:
    """Normalize matricula to uppercase without spaces."""
    return matricula.strip().replace(" ", "").replace("-", "").upper()


@deprecated_compat(replacement="use agent.utils.tool_decorators.validate_dni")
def validate_dni_cif(dni_cif: str) -> bool:
    """Validate Spanish DNI/NIE/CIF format."""
    if not dni_cif:
        return False
    clean = dni_cif.strip().replace(" ", "").replace("-", "").upper()
    return bool(DNI_CIF_REGEX.match(clean))


@deprecated_compat(replacement="use dedicated validation in agent.utils.tool_decorators")
def validate_cp(cp: str) -> bool:
    """Validate Spanish postal code format."""
    if not cp:
        return False
    clean = cp.strip().replace(" ", "")
    return bool(CP_REGEX.match(clean))


@deprecated_compat(replacement="use Pydantic schema validation in expediente_mode")
def validate_personal_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
    """
    Validate personal data completeness.
    
    Required fields:
        - nombre, apellidos
        - dni_cif
        - email
        - domicilio_calle, domicilio_localidad, domicilio_provincia, domicilio_cp
        - itv_nombre
    
    Args:
        data: Personal data dict
    
    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing = []
    
    # Basic personal info
    if not data.get("nombre"):
        missing.append("nombre")
    
    if not data.get("apellidos"):
        missing.append("apellidos")
    
    # DNI/CIF
    dni_cif = data.get("dni_cif")
    if not dni_cif:
        missing.append("DNI/CIF")
    elif not validate_dni_cif(dni_cif):
        missing.append("DNI/CIF (formato inválido)")
    
    # Email
    email = data.get("email")
    if not email:
        missing.append("email")
    elif not validate_email(email):
        missing.append("email (formato inválido)")
    
    # Domicilio
    if not data.get("domicilio_calle"):
        missing.append("calle")
    
    if not data.get("domicilio_localidad"):
        missing.append("localidad")
    
    if not data.get("domicilio_provincia"):
        missing.append("provincia")
    
    cp = data.get("domicilio_cp")
    if not cp:
        missing.append("codigo postal")
    elif not validate_cp(cp):
        missing.append("codigo postal (formato inválido)")
    
    # ITV
    if not data.get("itv_nombre"):
        missing.append("nombre de la ITV")
    
    # telefono is optional (we have WhatsApp)
    
    return len(missing) == 0, missing


@deprecated_compat(replacement="use Pydantic schema validation in expediente_mode")
def validate_vehicle_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
    """
    Validate vehicle data completeness.
    
    Args:
        data: Vehicle data dict
    
    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing = []
    
    if not data.get("marca"):
        missing.append("marca")
    
    if not data.get("modelo"):
        missing.append("modelo")
    
    # anio is REQUIRED
    anio = data.get("anio")
    if not anio:
        missing.append("año")
    else:
        try:
            year = int(anio)
            if year < 1900 or year > 2030:
                missing.append("año (debe ser entre 1900 y 2030)")
        except (ValueError, TypeError):
            missing.append("año (formato inválido)")
    
    matricula = data.get("matricula")
    if not matricula:
        missing.append("matrícula")
    elif not validate_matricula(matricula):
        missing.append("matrícula (formato inválido)")
    
    # bastidor is optional
    
    return len(missing) == 0, missing


@deprecated_compat(replacement="use Pydantic schema validation in expediente_mode")
def validate_workshop_data(data: dict[str, str | None] | None) -> tuple[bool, list[str]]:
    """
    Validate workshop data completeness (only required if taller_propio=True).
    
    Required fields when client uses own workshop:
        - nombre (workshop name)
        - responsable (responsible person)
        - domicilio (address)
        - provincia
        - ciudad
        - telefono
        - registro_industrial (industrial registry number)
        - actividad (activity description)
    
    Args:
        data: Workshop data dict or None
    
    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    if not data:
        return False, ["datos del taller"]
    
    missing = []
    
    if not data.get("nombre"):
        missing.append("nombre del taller")
    
    if not data.get("responsable"):
        missing.append("responsable del taller")
    
    if not data.get("domicilio"):
        missing.append("domicilio del taller")
    
    if not data.get("provincia"):
        missing.append("provincia del taller")
    
    if not data.get("ciudad"):
        missing.append("ciudad del taller")
    
    if not data.get("telefono"):
        missing.append("telefono del taller")
    
    if not data.get("registro_industrial"):
        missing.append("numero de registro industrial")
    
    if not data.get("actividad"):
        missing.append("actividad del taller")
    
    return len(missing) == 0, missing


@deprecated_compat(replacement="check mode_context['expediente_sub_mode'] not in ('idle', 'completed')")
def is_case_collection_active(fsm_state: dict[str, Any] | None) -> bool:
    """
    Check if there's an active case collection in progress.
    
    Args:
        fsm_state: FSM state dict (ignored, reconstructed from context)
    
    Returns:
        True if active, False otherwise
    """
    case_state = get_case_fsm_state(fsm_state)
    step = case_state.get("step", CollectionStep.IDLE.value)
    return step not in (CollectionStep.IDLE.value, CollectionStep.COMPLETED.value)


@deprecated_compat(replacement="use mode_transitions.py transition governance")
def can_transition_to(
    current_step: CollectionStep,
    target_step: CollectionStep,
) -> bool:
    """
    Check if transition from current to target step is valid.
    
    Valid transitions (element-by-element flow):
        IDLE -> COLLECT_ELEMENT_DATA (via iniciar_expediente)
        COLLECT_ELEMENT_DATA -> COLLECT_ELEMENT_DATA (next element) | COLLECT_BASE_DOCS (all elements done)
        COLLECT_BASE_DOCS -> COLLECT_PERSONAL
        COLLECT_PERSONAL -> COLLECT_VEHICLE
        COLLECT_VEHICLE -> COLLECT_WORKSHOP
        COLLECT_WORKSHOP -> REVIEW_SUMMARY
        REVIEW_SUMMARY -> COMPLETED | COLLECT_ELEMENT_DATA (user wants to edit)
        Any -> IDLE (cancel)
    
    Args:
        current_step: Current CollectionStep
        target_step: Target CollectionStep
    
    Returns:
        True if transition is valid, False otherwise
    """
    valid_transitions: dict[CollectionStep, list[CollectionStep]] = {
        CollectionStep.IDLE: [
            CollectionStep.COLLECT_ELEMENT_DATA,
        ],
        CollectionStep.COLLECT_ELEMENT_DATA: [
            CollectionStep.COLLECT_ELEMENT_DATA,
            CollectionStep.COLLECT_BASE_DOCS,
        ],
        CollectionStep.COLLECT_BASE_DOCS: [
            CollectionStep.COLLECT_PERSONAL,
        ],
        CollectionStep.COLLECT_PERSONAL: [
            CollectionStep.COLLECT_VEHICLE,
        ],
        CollectionStep.COLLECT_VEHICLE: [
            CollectionStep.COLLECT_WORKSHOP,
        ],
        CollectionStep.COLLECT_WORKSHOP: [
            CollectionStep.REVIEW_SUMMARY,
        ],
        CollectionStep.REVIEW_SUMMARY: [
            CollectionStep.COMPLETED,
            CollectionStep.COLLECT_BASE_DOCS,
            CollectionStep.COLLECT_PERSONAL,
            CollectionStep.COLLECT_VEHICLE,
            CollectionStep.COLLECT_WORKSHOP,
        ],
        CollectionStep.COMPLETED: [],
    }
    
    # Allow transition to IDLE from any state (cancel)
    if target_step == CollectionStep.IDLE:
        return True
    
    allowed = valid_transitions.get(current_step, [])
    return target_step in allowed


@deprecated_compat(replacement="use dynamic prompts from agent/prompts/modes/")
def get_step_prompt(step: CollectionStep, fsm_state: CaseFSMState) -> str:
    """
    Get the prompt message for a given step.
    
    NOTE: This is a simplified version for compatibility.
    The mode-based architecture uses dynamic prompts loaded from files.
    
    Args:
        step: Current collection step
        fsm_state: Current FSM state
    
    Returns:
        Prompt message for the user
    """
    prompts = {
        CollectionStep.COLLECT_ELEMENT_DATA: (
            "Recolectando datos de elementos. "
            "Usa las herramientas de element_data_tools para obtener instrucciones específicas."
        ),
        CollectionStep.COLLECT_BASE_DOCS: (
            "Ahora necesito la documentación base del vehículo:\n"
            "• Ficha técnica\n"
            "• Permiso de circulación\n"
            "• Vistas del vehículo\n\n"
            "Cuando hayas enviado todo, escribe 'listo'."
        ),
        CollectionStep.COLLECT_PERSONAL: (
            "Ahora necesito tus datos personales:\n"
            "• Nombre y apellidos\n"
            "• DNI o CIF\n"
            "• Email\n"
            "• Domicilio completo\n"
            "• Nombre de la ITV"
        ),
        CollectionStep.COLLECT_VEHICLE: (
            "Ahora necesito los datos del vehículo:\n"
            "• Marca\n"
            "• Modelo\n"
            "• Matrícula\n"
            "• Año de primera matriculación"
        ),
        CollectionStep.COLLECT_WORKSHOP: (
            "Para la ITV necesitas un certificado del taller de instalación.\n"
            "¿Quieres que MSI lo gestione (85€ +IVA), o tienes tu propio taller registrado?"
        ),
        CollectionStep.REVIEW_SUMMARY: (
            "Revisemos todos los datos antes de enviar el expediente."
        ),
        CollectionStep.COMPLETED: (
            "¡Perfecto! Tu expediente ha sido enviado para revisión."
        ),
    }
    
    return prompts.get(step, "")


@deprecated_compat(replacement="return mode_context reset from node directly")
def reset_fsm(fsm_state: dict[str, Any] | None) -> dict[str, Any]:
    """
    Reset FSM to initial state (cancel current collection).
    
    In mode-based architecture, this returns updates to reset mode_context.
    
    Args:
        fsm_state: Current FSM state (ignored)
    
    Returns:
        Updated FSM state dict (for mode_context reset)
    """
    if fsm_state is None:
        fsm_state = {}
    
    new_fsm_state = fsm_state.copy()
    new_fsm_state["case_collection"] = _create_initial_fsm_state()
    
    return new_fsm_state


@deprecated_compat(replacement="construct status dict inline or in a mode helper")
def initialize_element_data_status(element_codes: list[str]) -> dict[str, str]:
    """
    Initialize element_data_status dict for a list of element codes.
    
    Args:
        element_codes: List of element codes in user's original order
    
    Returns:
        Dict mapping element_code -> status ("pending" for all initially)
    """
    return {code: ELEMENT_STATUS_PENDING for code in element_codes}
