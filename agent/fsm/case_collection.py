"""
MSI Automotive - Case Collection FSM (Finite State Machine).

This module implements the FSM for collecting user data and images
to create homologation expedientes (cases).

States (optimized flow - images first to reduce friction):
    IDLE -> CONFIRM_START -> COLLECT_IMAGES -> COLLECT_PERSONAL ->
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
    """FSM states for case data collection (images-first flow)."""

    IDLE = "idle"  # No collection active
    CONFIRM_START = "confirm_start"  # Asking if user wants to open case
    COLLECT_IMAGES = "collect_images"  # Receiving required images (FIRST!)
    COLLECT_PERSONAL = "collect_personal"  # Collecting all personal + vehicle data
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

    # Images tracking (used in COLLECT_IMAGES)
    required_images: list[dict[str, Any]]  # [{code, display_name, description}]
    received_images: list[str]  # display_names of received images
    pending_images: list[str]  # display_names still missing

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
        # Workshop data (new)
        taller_propio=None,  # None=not asked, False=MSI provides, True=client provides
        taller_data=None,  # Will be dict when taller_propio=True
        category_slug=None,
        category_id=None,
        element_codes=[],
        required_images=[],
        received_images=[],
        pending_images=[],
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

    Valid transitions (images-first flow to reduce friction):
        IDLE -> CONFIRM_START
        CONFIRM_START -> COLLECT_IMAGES | IDLE (user declined)
        COLLECT_IMAGES -> COLLECT_PERSONAL | COLLECT_IMAGES (more images)
        COLLECT_PERSONAL -> COLLECT_WORKSHOP
        COLLECT_WORKSHOP -> REVIEW_SUMMARY
        REVIEW_SUMMARY -> COMPLETED | COLLECT_IMAGES (user wants to edit)
        Any -> IDLE (cancel)
    """
    valid_transitions: dict[CollectionStep, list[CollectionStep]] = {
        CollectionStep.IDLE: [CollectionStep.CONFIRM_START],
        CollectionStep.CONFIRM_START: [
            CollectionStep.COLLECT_IMAGES,  # Start with images first!
            CollectionStep.IDLE,
        ],
        CollectionStep.COLLECT_IMAGES: [
            CollectionStep.COLLECT_PERSONAL,  # After images, collect personal data
            CollectionStep.COLLECT_IMAGES,  # Can stay for more images
        ],
        CollectionStep.COLLECT_PERSONAL: [
            CollectionStep.COLLECT_WORKSHOP,  # Then ask about workshop
        ],
        CollectionStep.COLLECT_WORKSHOP: [
            CollectionStep.REVIEW_SUMMARY,  # Finally review
        ],
        CollectionStep.REVIEW_SUMMARY: [
            CollectionStep.COMPLETED,
            CollectionStep.COLLECT_IMAGES,  # Go back to start if edits needed
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

    # anio is optional but if provided must be valid
    anio = data.get("anio")
    if anio:
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


def get_required_images_for_elements(
    element_codes: list[str],
    category_slug: str,
) -> list[dict[str, Any]]:
    """
    Get list of required images based on elements to homologate.

    Args:
        element_codes: List of element codes (e.g., ["ESCAPE", "ALUMBRADO"])
        category_slug: Vehicle category slug

    Returns:
        List of required image specs:
        [{"code": "ESCAPE", "display_name": "escape_foto_general", "description": "..."}]
    """
    # Base documentation required for all cases
    required = [
        {
            "code": "BASE",
            "display_name": "ficha_tecnica",
            "description": "Foto de la ficha técnica del vehículo",
            "is_required": True,
        },
        {
            "code": "BASE",
            "display_name": "matricula_visible",
            "description": "Foto del vehículo con matrícula visible",
            "is_required": True,
        },
    ]

    # Element-specific images
    element_image_specs: dict[str, list[dict[str, Any]]] = {
        "ESCAPE": [
            {
                "display_name": "escape_foto_general",
                "description": "Foto general del escape instalado",
                "is_required": True,
            },
            {
                "display_name": "escape_etiqueta_homologacion",
                "description": "Foto de la etiqueta de homologación del escape",
                "is_required": True,
            },
        ],
        "ALUMBRADO": [
            {
                "display_name": "alumbrado_foto_general",
                "description": "Foto de los faros/luces instalados",
                "is_required": True,
            },
            {
                "display_name": "alumbrado_etiqueta",
                "description": "Foto de la etiqueta de homologación de las luces",
                "is_required": False,
            },
        ],
        "MANILLAR": [
            {
                "display_name": "manillar_foto_general",
                "description": "Foto del manillar instalado",
                "is_required": True,
            },
        ],
        "SUSPENSION": [
            {
                "display_name": "suspension_foto_delantera",
                "description": "Foto de la suspensión delantera",
                "is_required": True,
            },
            {
                "display_name": "suspension_foto_trasera",
                "description": "Foto de la suspensión trasera",
                "is_required": True,
            },
        ],
        "LLANTAS": [
            {
                "display_name": "llantas_foto_delantera",
                "description": "Foto de la llanta delantera",
                "is_required": True,
            },
            {
                "display_name": "llantas_foto_trasera",
                "description": "Foto de la llanta trasera",
                "is_required": True,
            },
        ],
        "CARENADO": [
            {
                "display_name": "carenado_foto_lateral",
                "description": "Foto lateral del carenado",
                "is_required": True,
            },
            {
                "display_name": "carenado_foto_frontal",
                "description": "Foto frontal del carenado",
                "is_required": True,
            },
        ],
        "ESPEJOS": [
            {
                "display_name": "espejos_foto_general",
                "description": "Foto de los espejos instalados",
                "is_required": True,
            },
        ],
        # Autocaravanas elements
        "ESC_MEC": [
            {
                "display_name": "escalera_foto_plegada",
                "description": "Foto de la escalera plegada",
                "is_required": True,
            },
            {
                "display_name": "escalera_foto_desplegada",
                "description": "Foto de la escalera desplegada",
                "is_required": True,
            },
        ],
        "TOLDO_LAT": [
            {
                "display_name": "toldo_foto_cerrado",
                "description": "Foto del toldo cerrado",
                "is_required": True,
            },
            {
                "display_name": "toldo_foto_abierto",
                "description": "Foto del toldo abierto (si es posible)",
                "is_required": False,
            },
        ],
        "PLACA_SOLAR": [
            {
                "display_name": "placa_solar_foto_techo",
                "description": "Foto de la placa solar en el techo",
                "is_required": True,
            },
        ],
        "ANTENA": [
            {
                "display_name": "antena_foto_general",
                "description": "Foto de la antena instalada",
                "is_required": True,
            },
        ],
        "PORTABICIS": [
            {
                "display_name": "portabicis_foto_instalado",
                "description": "Foto del portabicicletas instalado",
                "is_required": True,
            },
        ],
    }

    for code in element_codes:
        code_upper = code.upper()
        if code_upper in element_image_specs:
            for spec in element_image_specs[code_upper]:
                required.append({
                    "code": code_upper,
                    "display_name": spec["display_name"],
                    "description": spec["description"],
                    "is_required": spec.get("is_required", True),
                })
        else:
            # Generic photo for unknown elements
            required.append({
                "code": code_upper,
                "display_name": f"{code_upper.lower()}_foto_general",
                "description": f"Foto del elemento {code_upper}",
                "is_required": True,
            })

    return required


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
        CollectionStep.CONFIRM_START: (
            "¿Te gustaría que abra un expediente para procesar tu homologación? "
            "Necesitaré algunas fotos y datos. Empezaremos por las fotos."
        ),
        CollectionStep.COLLECT_IMAGES: _get_images_prompt(fsm_state),
        CollectionStep.COLLECT_PERSONAL: (
            "¡Perfecto, ya tengo todas las fotos! Ahora necesito tus datos.\n\n"
            "Por favor, indícame en un solo mensaje:\n"
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
        CollectionStep.COLLECT_WORKSHOP: _get_workshop_prompt(fsm_state),
        CollectionStep.REVIEW_SUMMARY: _get_summary_prompt(fsm_state),
        CollectionStep.COMPLETED: (
            "¡Perfecto! Tu expediente ha sido enviado para revision. "
            "Un agente lo revisara y se pondra en contacto contigo pronto."
        ),
    }

    return prompts.get(step, "")


def _get_images_prompt(fsm_state: CaseFSMState) -> str:
    """Generate prompt for image collection step."""
    pending = fsm_state.get("pending_images", [])
    received = fsm_state.get("received_images", [])
    required = fsm_state.get("required_images", [])

    # Find descriptions for pending images
    pending_with_desc = []
    for display_name in pending:
        for img in required:
            if img["display_name"] == display_name:
                pending_with_desc.append(
                    f"• {img['description']}"
                )
                break

    if not pending:
        return "¡Ya tengo todas las fotos necesarias! Vamos al resumen."

    # Count required vs optional
    required_pending = [
        p for p in pending
        if any(
            r["display_name"] == p and r.get("is_required", True)
            for r in required
        )
    ]

    progress = f"Fotos recibidas: {len(received)}/{len(required)}\n\n"

    if required_pending:
        return (
            progress
            + "Ahora necesito que me envíes las siguientes fotos:\n\n"
            + "\n".join(pending_with_desc[:3])  # Show max 3 at a time
            + ("\n\n(y más...)" if len(pending_with_desc) > 3 else "")
            + "\n\nPuedes enviarlas una por una o varias a la vez."
        )
    else:
        return (
            progress
            + "Ya tengo todas las fotos obligatorias. "
            + f"Opcionalmente puedes enviar: {', '.join(pending)}\n\n"
            + "¿Quieres continuar al resumen o enviar más fotos?"
        )


def _get_workshop_prompt(fsm_state: CaseFSMState) -> str:
    """Generate prompt for workshop data collection step."""
    taller_propio = fsm_state.get("taller_propio")

    # First question: ask if MSI provides certificate or client uses own workshop
    if taller_propio is None:
        return (
            "Ahora necesito saber sobre el certificado del taller.\n\n"
            "¿Quieres que MSI aporte el certificado del taller (lo gestionamos nosotros), "
            "o usaras tu propio taller?\n\n"
            "Responde:\n"
            "• 'MSI' si quieres que nosotros lo gestionemos\n"
            "• 'Propio' si usaras tu taller y nos proporcionaras sus datos"
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
    received = fsm_state.get("received_images", [])
    tariff = fsm_state.get("tariff_amount")
    taller_propio = fsm_state.get("taller_propio")
    taller_data = fsm_state.get("taller_data", {})

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

    summary_parts.extend([
        "",
        "ELEMENTOS A HOMOLOGAR:",
        "  " + ", ".join(elements) if elements else "  (ninguno)",
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
