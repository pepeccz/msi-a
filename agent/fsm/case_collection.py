"""
MSI Automotive - Case Collection FSM (Finite State Machine).

This module implements the FSM for collecting user data and images
to create homologation expedientes (cases).

States (element-by-element flow with photos + data per element):
    IDLE -> COLLECT_ELEMENT_DATA (per element: photos then data) ->
    COLLECT_BASE_DOCS -> COLLECT_PERSONAL -> COLLECT_VEHICLE ->
    COLLECT_WORKSHOP -> REVIEW_SUMMARY -> COMPLETED

The FSM state is stored in ConversationState.fsm_state and persisted
via the LangGraph checkpointer.
"""

import logging
import re
from enum import Enum
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class CollectionStep(str, Enum):
    """FSM states for case data collection (element-by-element flow)."""

    IDLE = "idle"  # No collection active
    COLLECT_ELEMENT_DATA = "collect_element_data"  # Per-element: photos then required data
    COLLECT_BASE_DOCS = "collect_base_docs"  # Base documentation (ficha técnica, permiso, etc.)
    COLLECT_PERSONAL = "collect_personal"  # Collecting personal data only
    COLLECT_VEHICLE = "collect_vehicle"  # Collecting vehicle data (marca, modelo, matricula, año)
    COLLECT_WORKSHOP = "collect_workshop"  # Asking about workshop (MSI vs own)
    REVIEW_SUMMARY = "review_summary"  # Final review before submission
    COMPLETED = "completed"  # Case submitted for review


class CaseFSMState(TypedDict, total=False):
    """
    FSM state structure for case collection.

    Stored in ConversationState.fsm_state["case_collection"].
    """

    # Current step in the FSM
    step: str  # CollectionStep value

    # Database references
    case_id: str | None  # UUID of the Case record

    # Personal data (collected in COLLECT_PERSONAL - expanded)
    personal_data: dict[str, str | None]  # nombre, apellidos, email, telefono, dni_cif, domicilio_*, itv_nombre

    # Vehicle data (also collected in COLLECT_PERSONAL now)
    vehicle_data: dict[str, str | None]  # marca, modelo, anio, matricula, bastidor

    # Workshop data (collected in COLLECT_WORKSHOP if taller_propio=True)
    taller_propio: bool | None  # None=not asked, False=MSI provides, True=client provides
    taller_data: dict[str, str | None] | None  # nombre, responsable, domicilio, provincia, ciudad, telefono, registro_industrial, actividad

    # Elements and category (set when case is created)
    category_slug: str | None
    category_id: str | None  # UUID
    element_codes: list[str]

    # Element-by-element collection tracking (COLLECT_ELEMENT_DATA)
    current_element_index: int  # Index in element_codes list (0-based)
    element_phase: str  # "photos" or "data" - what we're collecting for current element
    element_data_status: dict[str, str]  # Per element: "pending", "photos_done", "data_done", "complete"

    # Base documentation tracking (COLLECT_BASE_DOCS)
    base_docs_received: bool  # Whether base docs have been received

    # Legacy: received_images for total count (still useful for summary)
    received_images: list[str]  # filenames of received images (for counting)

    # Tariff info (set when case is created)
    tariff_tier_id: str | None
    tariff_amount: float | None

    # Control
    last_prompt: str | None  # Last prompt sent to user
    retry_count: int  # Retries for current step
    error_message: str | None  # Last error if any


# Maximum retries per step before offering escalation
MAX_RETRIES_PER_STEP = 3

# Email validation regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Spanish matricula patterns (modern and old)
MATRICULA_REGEX = re.compile(
    r"^([0-9]{4}[A-Z]{3}|[A-Z]{1,2}[0-9]{4}[A-Z]{0,2})$",
    re.IGNORECASE,
)

# Spanish DNI/NIE/CIF patterns
# DNI: 8 digits + letter (12345678A)
# NIE: X/Y/Z + 7 digits + letter (X1234567A)
# CIF: Letter + 8 digits (or 7 digits + letter) (B12345678)
DNI_CIF_REGEX = re.compile(
    r"^([0-9]{8}[A-Z]|[XYZ][0-9]{7}[A-Z]|[A-Z][0-9]{7,8}[A-Z0-9]?)$",
    re.IGNORECASE,
)

# Spanish postal code (5 digits, 01000-52999)
CP_REGEX = re.compile(r"^(0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}$")


def create_initial_fsm_state() -> CaseFSMState:
    """Create a fresh FSM state for case collection."""
    return CaseFSMState(
        step=CollectionStep.IDLE.value,
        case_id=None,
        personal_data={
            "nombre": None,
            "apellidos": None,
            "email": None,
            "telefono": None,
            # New expanded fields
            "dni_cif": None,
            "domicilio_calle": None,
            "domicilio_localidad": None,
            "domicilio_provincia": None,
            "domicilio_cp": None,
            "itv_nombre": None,
        },
        vehicle_data={
            "marca": None,
            "modelo": None,
            "anio": None,
            "matricula": None,
            "bastidor": None,
        },
        # Workshop data
        taller_propio=None,  # None=not asked, False=MSI provides, True=client provides
        taller_data=None,  # Will be dict when taller_propio=True
        category_slug=None,
        category_id=None,
        element_codes=[],
        # Element-by-element collection tracking
        current_element_index=0,
        element_phase="photos",  # Start with photos for each element
        element_data_status={},  # Will be populated when case starts: {"SUSP_TRAS": "pending", ...}
        # Base documentation
        base_docs_received=False,
        # Total images received (for summary)
        received_images=[],
        tariff_tier_id=None,
        tariff_amount=None,
        last_prompt=None,
        retry_count=0,
        error_message=None,
    )


def get_case_fsm_state(fsm_state: dict[str, Any] | None) -> CaseFSMState:
    """
    Extract case collection FSM state from conversation fsm_state.

    Args:
        fsm_state: The full fsm_state dict from ConversationState

    Returns:
        CaseFSMState dict (creates fresh one if not exists)
    """
    if not fsm_state:
        return create_initial_fsm_state()

    case_state = fsm_state.get("case_collection")
    if not case_state:
        return create_initial_fsm_state()

    # Ensure all required keys exist
    initial = create_initial_fsm_state()
    for key in initial:
        if key not in case_state:
            case_state[key] = initial[key]

    return case_state


def update_case_fsm_state(
    fsm_state: dict[str, Any] | None,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Update case collection FSM state and return new fsm_state.

    Args:
        fsm_state: Current full fsm_state dict
        updates: Updates to apply to case_collection

    Returns:
        New fsm_state dict with updates applied
    """
    if fsm_state is None:
        fsm_state = {}

    case_state = get_case_fsm_state(fsm_state)
    case_state.update(updates)

    new_fsm_state = fsm_state.copy()
    new_fsm_state["case_collection"] = case_state

    return new_fsm_state


def is_case_collection_active(fsm_state: dict[str, Any] | None) -> bool:
    """Check if there's an active case collection in progress."""
    case_state = get_case_fsm_state(fsm_state)
    step = case_state.get("step", CollectionStep.IDLE.value)
    return step not in (CollectionStep.IDLE.value, CollectionStep.COMPLETED.value)


def get_current_step(fsm_state: dict[str, Any] | None) -> CollectionStep:
    """Get the current collection step."""
    case_state = get_case_fsm_state(fsm_state)
    step_value = case_state.get("step", CollectionStep.IDLE.value)
    try:
        return CollectionStep(step_value)
    except ValueError:
        return CollectionStep.IDLE


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
    """
    valid_transitions: dict[CollectionStep, list[CollectionStep]] = {
        CollectionStep.IDLE: [
            CollectionStep.COLLECT_ELEMENT_DATA,  # Start with first element
        ],
        CollectionStep.COLLECT_ELEMENT_DATA: [
            CollectionStep.COLLECT_ELEMENT_DATA,  # Stay for next element or phase
            CollectionStep.COLLECT_BASE_DOCS,  # All elements done -> base docs
        ],
        CollectionStep.COLLECT_BASE_DOCS: [
            CollectionStep.COLLECT_PERSONAL,  # After base docs, collect personal data
        ],
        CollectionStep.COLLECT_PERSONAL: [
            CollectionStep.COLLECT_VEHICLE,  # After personal, collect vehicle data
        ],
        CollectionStep.COLLECT_VEHICLE: [
            CollectionStep.COLLECT_WORKSHOP,  # Then ask about workshop
        ],
        CollectionStep.COLLECT_WORKSHOP: [
            CollectionStep.REVIEW_SUMMARY,  # Finally review
        ],
        CollectionStep.REVIEW_SUMMARY: [
            CollectionStep.COMPLETED,
            CollectionStep.COLLECT_ELEMENT_DATA,  # Go back to start if edits needed
        ],
        CollectionStep.COMPLETED: [],
    }

    # Allow transition to IDLE from any state (cancel)
    if target_step == CollectionStep.IDLE:
        return True

    allowed = valid_transitions.get(current_step, [])
    return target_step in allowed


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_matricula(matricula: str) -> bool:
    """Validate Spanish vehicle plate format."""
    if not matricula:
        return False
    # Remove spaces and normalize
    clean = matricula.strip().replace(" ", "").replace("-", "").upper()
    return bool(MATRICULA_REGEX.match(clean))


def normalize_matricula(matricula: str) -> str:
    """Normalize matricula to uppercase without spaces."""
    return matricula.strip().replace(" ", "").replace("-", "").upper()


def validate_dni_cif(dni_cif: str) -> bool:
    """Validate Spanish DNI/NIE/CIF format."""
    if not dni_cif:
        return False
    clean = dni_cif.strip().replace(" ", "").replace("-", "").upper()
    return bool(DNI_CIF_REGEX.match(clean))


def validate_cp(cp: str) -> bool:
    """Validate Spanish postal code format."""
    if not cp:
        return False
    clean = cp.strip().replace(" ", "")
    return bool(CP_REGEX.match(clean))


def validate_personal_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
    """
    Validate personal data completeness (expanded for new flow).

    Required fields:
    - nombre, apellidos
    - dni_cif
    - email
    - domicilio_calle, domicilio_localidad, domicilio_provincia, domicilio_cp
    - itv_nombre

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


def validate_vehicle_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
    """
    Validate vehicle data completeness.

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


def get_step_prompt(step: CollectionStep, fsm_state: CaseFSMState) -> str:
    """
    Get the prompt message for a given step.

    Args:
        step: Current collection step
        fsm_state: Current FSM state

    Returns:
        Prompt message for the user
    """
    prompts = {
        CollectionStep.COLLECT_ELEMENT_DATA: _get_element_data_prompt(fsm_state),
        CollectionStep.COLLECT_BASE_DOCS: _get_base_docs_prompt(fsm_state),
        CollectionStep.COLLECT_PERSONAL: (
            "¡Perfecto! Ya tengo toda la información de los elementos.\n\n"
            "Ahora necesito tus datos personales:\n"
            "• Nombre y apellidos\n"
            "• DNI o CIF\n"
            "• Email\n"
            "• Domicilio completo (calle, numero, localidad, provincia, codigo postal)\n"
            "• Nombre de la ITV donde pasaras la inspeccion\n\n"
            "Ejemplo:\n"
            "Juan Garcia Lopez, 12345678A, juan@email.com\n"
            "C/ Mayor 10, Madrid, Madrid, 28001\n"
            "ITV Alcobendas"
        ),
        CollectionStep.COLLECT_VEHICLE: (
            "Ahora necesito los datos del vehiculo:\n\n"
            "• Marca\n"
            "• Modelo\n"
            "• Matricula\n"
            "• Año de primera matriculacion\n\n"
            "Puedes enviarlo en un solo mensaje, por ejemplo:\n"
            "BMW R1200GS, 1234ABC, 2019"
        ),
        CollectionStep.COLLECT_WORKSHOP: _get_workshop_prompt(fsm_state),
        CollectionStep.REVIEW_SUMMARY: _get_summary_prompt(fsm_state),
        CollectionStep.COMPLETED: (
            "¡Perfecto! Tu expediente ha sido enviado para revision. "
            "Un agente lo revisara y se pondra en contacto contigo pronto."
        ),
    }

    return prompts.get(step, "")


def _get_element_data_prompt(fsm_state: CaseFSMState) -> str:
    """
    Generate prompt for element-by-element data collection.
    
    The actual prompt content is generated dynamically by the tools based on:
    - current_element_index: which element we're on
    - element_phase: "photos" or "data"
    - element_data_status: status of each element
    
    This function returns a generic fallback prompt.
    The conversational_agent node will use the element_data_tools to get specific prompts.
    """
    element_codes = fsm_state.get("element_codes", [])
    current_idx = fsm_state.get("current_element_index", 0)
    phase = fsm_state.get("element_phase", "photos")
    
    if not element_codes:
        return "Error: No hay elementos seleccionados para el expediente."
    
    if current_idx >= len(element_codes):
        return "Todos los elementos han sido procesados."
    
    current_element = element_codes[current_idx]
    total = len(element_codes)
    
    if phase == "photos":
        return (
            f"Elemento {current_idx + 1} de {total}: {current_element}\n\n"
            f"Envíame las fotos necesarias para este elemento.\n"
            f"Cuando hayas enviado todas las fotos, escribe 'listo'."
        )
    else:  # phase == "data"
        return (
            f"Elemento {current_idx + 1} de {total}: {current_element}\n\n"
            f"Ahora necesito los datos técnicos de este elemento.\n"
            f"Te iré preguntando campo por campo."
        )


def _get_base_docs_prompt(fsm_state: CaseFSMState) -> str:
    """Generate prompt for base documentation collection (ficha técnica, permiso, etc.)."""
    return (
        "¡Perfecto! Ya tenemos toda la información de los elementos.\n\n"
        "Ahora necesito la documentación base del vehículo:\n"
        "• Ficha técnica del vehículo\n"
        "• Permiso de circulación\n\n"
        "Puedes enviar fotos o PDF de estos documentos.\n"
        "Cuando hayas enviado todo, escribe 'listo'."
    )


def _get_workshop_prompt(fsm_state: CaseFSMState) -> str:
    """Generate prompt for workshop data collection step."""
    taller_propio = fsm_state.get("taller_propio")

    # First question: ask if MSI provides certificate or client uses own workshop
    if taller_propio is None:
        return (
            "Ahora necesito saber sobre el certificado del taller.\n\n"
            "¿Quieres que MSI aporte el certificado del taller (coste adicional de 85€), "
            "o usarás tu propio taller?\n\n"
            "Responde:\n"
            "• 'MSI' si quieres que nosotros lo gestionemos (+85€)\n"
            "• 'Propio' si usarás tu taller y nos proporcionarás sus datos"
        )

    # If taller_propio=True, ask for workshop data
    if taller_propio:
        return (
            "Perfecto, necesito los datos de tu taller:\n\n"
            "• Nombre del taller\n"
            "• Responsable\n"
            "• Direccion (calle y numero)\n"
            "• Provincia\n"
            "• Ciudad\n"
            "• Telefono\n"
            "• Numero de Registro Industrial\n"
            "• Actividad del taller\n\n"
            "Puedes enviarlo todo junto."
        )

    # If taller_propio=False, MSI handles it - no more data needed
    return "Perfecto, MSI se encargara del certificado del taller. Continuamos."


def _get_summary_prompt(fsm_state: CaseFSMState) -> str:
    """Generate summary prompt for review."""
    personal = fsm_state.get("personal_data", {})
    vehicle = fsm_state.get("vehicle_data", {})
    elements = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    received = fsm_state.get("received_images", [])
    tariff = fsm_state.get("tariff_amount")
    taller_propio = fsm_state.get("taller_propio")
    taller_data = fsm_state.get("taller_data", {})
    base_docs = fsm_state.get("base_docs_received", False)

    # Build domicilio string
    domicilio_parts = []
    if personal.get("domicilio_calle"):
        domicilio_parts.append(personal["domicilio_calle"])
    if personal.get("domicilio_localidad"):
        domicilio_parts.append(personal["domicilio_localidad"])
    if personal.get("domicilio_provincia"):
        domicilio_parts.append(personal["domicilio_provincia"])
    if personal.get("domicilio_cp"):
        domicilio_parts.append(personal["domicilio_cp"])
    domicilio_str = ", ".join(domicilio_parts) if domicilio_parts else "-"

    summary_parts = [
        "RESUMEN DEL EXPEDIENTE",
        "=" * 25,
        "",
        "DATOS PERSONALES:",
        f"  Nombre: {personal.get('nombre', '-')} {personal.get('apellidos', '')}",
        f"  DNI/CIF: {personal.get('dni_cif', '-')}",
        f"  Email: {personal.get('email', '-')}",
        f"  Domicilio: {domicilio_str}",
        "",
        "VEHICULO:",
        f"  Marca/Modelo: {vehicle.get('marca', '-')} {vehicle.get('modelo', '')}",
        f"  Matricula: {vehicle.get('matricula', '-')}",
        "",
        "ITV:",
        f"  {personal.get('itv_nombre', '-')}",
        "",
        "TALLER:",
    ]

    # Add taller info
    if taller_propio is False:
        summary_parts.append("  MSI aporta el certificado")
    elif taller_propio is True and taller_data:
        summary_parts.append(f"  Nombre: {taller_data.get('nombre', '-')}")
        summary_parts.append(f"  Responsable: {taller_data.get('responsable', '-')}")
        summary_parts.append(f"  Direccion: {taller_data.get('domicilio', '-')}, {taller_data.get('ciudad', '-')}, {taller_data.get('provincia', '-')}")
        summary_parts.append(f"  Telefono: {taller_data.get('telefono', '-')}")
        summary_parts.append(f"  Registro Industrial: {taller_data.get('registro_industrial', '-')}")
    else:
        summary_parts.append("  (pendiente)")

    # Add elements with status
    summary_parts.extend([
        "",
        "ELEMENTOS A HOMOLOGAR:",
    ])
    if elements:
        for elem in elements:
            status = element_status.get(elem, "pending")
            status_icon = "✓" if status == "complete" else "○"
            summary_parts.append(f"  {status_icon} {elem}")
    else:
        summary_parts.append("  (ninguno)")

    # Add base docs status
    summary_parts.extend([
        "",
        "DOCUMENTACION BASE:",
        f"  {'✓' if base_docs else '○'} Ficha técnica y permiso de circulación",
        "",
        f"FOTOS RECIBIDAS: {len(received)}",
        "",
    ])

    if tariff:
        summary_parts.append(f"TARIFA: {tariff}EUR + IVA")
        summary_parts.append("")

    summary_parts.extend([
        "¿Todo es correcto? Responde 'Si' para enviar el expediente",
        "o 'No' si necesitas modificar algo.",
    ])

    return "\n".join(summary_parts)


def transition_to(
    fsm_state: dict[str, Any] | None,
    target_step: CollectionStep,
) -> dict[str, Any]:
    """
    Transition FSM to a new step.

    Args:
        fsm_state: Current full fsm_state dict
        target_step: Target step to transition to

    Returns:
        Updated fsm_state dict

    Raises:
        ValueError: If transition is not valid
    """
    current_step = get_current_step(fsm_state)

    if not can_transition_to(current_step, target_step):
        raise ValueError(
            f"Invalid transition from {current_step.value} to {target_step.value}"
        )

    logger.info(
        f"FSM transition: {current_step.value} -> {target_step.value}"
    )

    return update_case_fsm_state(
        fsm_state,
        {
            "step": target_step.value,
            "retry_count": 0,
            "error_message": None,
        },
    )


def reset_fsm(fsm_state: dict[str, Any] | None) -> dict[str, Any]:
    """Reset FSM to initial state (cancel current collection)."""
    if fsm_state is None:
        fsm_state = {}

    new_fsm_state = fsm_state.copy()
    new_fsm_state["case_collection"] = create_initial_fsm_state()

    return new_fsm_state


# =============================================================================
# Element Data Collection Helpers
# =============================================================================

# Element data status values
ELEMENT_STATUS_PENDING = "pending"  # Not started
ELEMENT_STATUS_PHOTOS_DONE = "photos_done"  # Photos received, data pending
ELEMENT_STATUS_DATA_DONE = "data_done"  # Data collected, photos pending (shouldn't happen normally)
ELEMENT_STATUS_COMPLETE = "complete"  # Both photos and data done


def initialize_element_data_status(element_codes: list[str]) -> dict[str, str]:
    """
    Initialize element_data_status dict for a list of element codes.
    
    Args:
        element_codes: List of element codes in user's original order
        
    Returns:
        Dict mapping element_code -> status ("pending" for all initially)
    """
    return {code: ELEMENT_STATUS_PENDING for code in element_codes}


def get_current_element_code(fsm_state: CaseFSMState) -> str | None:
    """
    Get the current element code being collected.
    
    Returns:
        Element code string or None if no elements or index out of range
    """
    element_codes = fsm_state.get("element_codes", [])
    current_idx = fsm_state.get("current_element_index", 0)
    
    if not element_codes or current_idx >= len(element_codes):
        return None
    
    return element_codes[current_idx]


def get_element_phase(fsm_state: CaseFSMState) -> str:
    """Get the current phase for element collection: 'photos' or 'data'."""
    return fsm_state.get("element_phase", "photos")


def is_current_element_photos_done(fsm_state: CaseFSMState) -> bool:
    """Check if photos are done for the current element."""
    element_code = get_current_element_code(fsm_state)
    if not element_code:
        return False
    
    status = fsm_state.get("element_data_status", {}).get(element_code, ELEMENT_STATUS_PENDING)
    return status in (ELEMENT_STATUS_PHOTOS_DONE, ELEMENT_STATUS_COMPLETE)


def is_current_element_complete(fsm_state: CaseFSMState) -> bool:
    """Check if the current element is fully complete (photos + data)."""
    element_code = get_current_element_code(fsm_state)
    if not element_code:
        return False
    
    status = fsm_state.get("element_data_status", {}).get(element_code, ELEMENT_STATUS_PENDING)
    return status == ELEMENT_STATUS_COMPLETE


def are_all_elements_complete(fsm_state: CaseFSMState) -> bool:
    """Check if all elements have been fully collected (photos + data)."""
    element_codes = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    
    if not element_codes:
        return True  # No elements = done
    
    return all(
        element_status.get(code) == ELEMENT_STATUS_COMPLETE
        for code in element_codes
    )


def get_next_pending_element_index(fsm_state: CaseFSMState) -> int | None:
    """
    Get the index of the next element that needs processing.
    
    Returns:
        Index of next pending element, or None if all complete
    """
    element_codes = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    
    for idx, code in enumerate(element_codes):
        if element_status.get(code) != ELEMENT_STATUS_COMPLETE:
            return idx
    
    return None


def update_element_status(
    fsm_state: dict[str, Any] | None,
    element_code: str,
    new_status: str,
) -> dict[str, Any]:
    """
    Update the status of a specific element.
    
    Args:
        fsm_state: Current FSM state
        element_code: Element code to update
        new_status: New status value (use ELEMENT_STATUS_* constants)
        
    Returns:
        Updated fsm_state
    """
    case_state = get_case_fsm_state(fsm_state)
    element_data_status = case_state.get("element_data_status", {}).copy()
    element_data_status[element_code] = new_status
    
    return update_case_fsm_state(fsm_state, {"element_data_status": element_data_status})


def advance_to_next_element_or_phase(
    fsm_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    """
    Advance to the next element or phase in collection.
    
    Logic:
    1. If current phase is "photos" and photos done -> switch to "data" phase
    2. If current phase is "data" and data done -> move to next element (photos phase)
    3. If all elements complete -> return (fsm_state, True) to signal completion
    
    Returns:
        Tuple of (updated_fsm_state, all_elements_complete)
    """
    case_state = get_case_fsm_state(fsm_state)
    element_codes = case_state.get("element_codes", [])
    current_idx = case_state.get("current_element_index", 0)
    phase = case_state.get("element_phase", "photos")
    element_status = case_state.get("element_data_status", {})
    
    if not element_codes:
        return fsm_state or {}, True
    
    current_code = element_codes[current_idx] if current_idx < len(element_codes) else None
    
    if not current_code:
        return fsm_state or {}, True
    
    current_status = element_status.get(current_code, ELEMENT_STATUS_PENDING)
    
    # If photos phase and photos are done, switch to data phase
    if phase == "photos" and current_status in (ELEMENT_STATUS_PHOTOS_DONE, ELEMENT_STATUS_COMPLETE):
        # Check if element has required fields - if not, mark as complete and move on
        # (This check will be done in the tools, here we just switch phase)
        return update_case_fsm_state(fsm_state, {"element_phase": "data"}), False
    
    # If data phase and element is complete, move to next element
    if phase == "data" and current_status == ELEMENT_STATUS_COMPLETE:
        next_idx = current_idx + 1
        
        # Check if there are more elements
        if next_idx < len(element_codes):
            return update_case_fsm_state(
                fsm_state,
                {
                    "current_element_index": next_idx,
                    "element_phase": "photos",
                },
            ), False
        else:
            # All elements done
            return fsm_state or {}, True
    
    # No advancement needed
    return fsm_state or {}, False


def get_element_collection_progress(fsm_state: CaseFSMState) -> dict[str, Any]:
    """
    Get a summary of element collection progress.
    
    Returns:
        Dict with progress info:
        {
            "total_elements": int,
            "completed_elements": int,
            "current_element_index": int,
            "current_element_code": str | None,
            "current_phase": str,
            "elements": [
                {"code": str, "status": str, "is_current": bool},
                ...
            ]
        }
    """
    element_codes = fsm_state.get("element_codes", [])
    element_status = fsm_state.get("element_data_status", {})
    current_idx = fsm_state.get("current_element_index", 0)
    phase = fsm_state.get("element_phase", "photos")
    
    completed = sum(
        1 for code in element_codes
        if element_status.get(code) == ELEMENT_STATUS_COMPLETE
    )
    
    elements_info = [
        {
            "code": code,
            "status": element_status.get(code, ELEMENT_STATUS_PENDING),
            "is_current": idx == current_idx,
        }
        for idx, code in enumerate(element_codes)
    ]
    
    return {
        "total_elements": len(element_codes),
        "completed_elements": completed,
        "current_element_index": current_idx,
        "current_element_code": element_codes[current_idx] if current_idx < len(element_codes) else None,
        "current_phase": phase,
        "elements": elements_info,
    }
