"""
MSI Automotive - Case Management Tools for LangGraph Agent.

Tools for collecting user data and images to create homologation cases (expedientes).
"""

import logging
import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

from langchain_core.tools import tool

from agent.fsm.case_collection import (
    CollectionStep,
    get_case_fsm_state,
    update_case_fsm_state,
    is_case_collection_active,
    get_current_step,
    transition_to,
    validate_personal_data,
    validate_vehicle_data,
    validate_workshop_data,
    normalize_matricula,
    get_step_prompt,
    reset_fsm,
)
from agent.state.helpers import get_current_state
from database.connection import get_async_session
from database.models import Case, CaseImage, Escalation, User

logger = logging.getLogger(__name__)


async def _get_active_case_for_conversation(conversation_id: str) -> Case | None:
    """Get active (non-closed) case for a conversation."""
    active_statuses = ["collecting", "pending_images", "pending_review", "in_progress"]

    async with get_async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Case)
            .where(Case.conversation_id == conversation_id)
            .where(Case.status.in_(active_statuses))
            .order_by(Case.created_at.desc())
        )
        return result.scalar_one_or_none()


async def _get_category_id_by_slug(slug: str) -> str | None:
    """Get category UUID by slug."""
    async with get_async_session() as session:
        from sqlalchemy import select
        from database.models import VehicleCategory

        result = await session.execute(
            select(VehicleCategory.id).where(VehicleCategory.slug == slug)
        )
        row = result.first()
        return str(row[0]) if row else None


async def _update_case_metadata(case_id: str, updates: dict[str, Any]) -> None:
    """Update case metadata with current step info."""
    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if case:
                metadata = case.metadata_ or {}
                metadata.update(updates)
                metadata["last_step_at"] = datetime.now(UTC).isoformat()
                case.metadata_ = metadata
                case.updated_at = datetime.now(UTC)
                await session.commit()
    except Exception as e:
        logger.warning(f"Failed to update case metadata: {e}")


# =============================================================================
# FSM Validation Helpers
# =============================================================================

def _get_phase_guidance(step: CollectionStep) -> str:
    """Get guidance message for what to do in each FSM step."""
    guidance_map = {
        CollectionStep.IDLE: "No hay expediente activo. Usa iniciar_expediente() para crear uno.",
        CollectionStep.CONFIRM_START: "Esperando confirmación del usuario para abrir expediente.",
        CollectionStep.COLLECT_IMAGES: "Recolectando imágenes. Usa continuar_a_datos_personales() cuando el usuario diga 'listo'.",
        CollectionStep.COLLECT_PERSONAL: "Recolectando datos personales. Usa actualizar_datos_expediente(datos_personales=...) para guardar.",
        CollectionStep.COLLECT_VEHICLE: "Recolectando datos del vehículo. Usa actualizar_datos_expediente(datos_vehiculo=...) para guardar.",
        CollectionStep.COLLECT_WORKSHOP: "Preguntando sobre taller. Usa actualizar_datos_taller() para guardar la decisión.",
        CollectionStep.REVIEW_SUMMARY: "Mostrando resumen final. Usa finalizar_expediente() cuando el usuario confirme.",
        CollectionStep.COMPLETED: "Expediente completado. No requiere más acciones.",
    }
    return guidance_map.get(step, "Paso desconocido.")


def _tool_error_response(
    error: str,
    current_step: CollectionStep | str | None = None,
    guidance: str | None = None,
) -> dict[str, Any]:
    """
    Create a standardized error response for tools.
    
    Always includes 'message' field so that conversational_agent
    can inject mandatory instructions to the LLM.
    
    Args:
        error: Error description
        current_step: Current FSM step (for context)
        guidance: What the LLM should do instead
        
    Returns:
        Dict with success=False, error, message, and optional fields
    """
    step_value = current_step.value if isinstance(current_step, CollectionStep) else current_step
    
    # Build message with all context
    message_parts = [f"ERROR: {error}"]
    
    if guidance:
        message_parts.append(f"QUÉ HACER: {guidance}")
    elif step_value:
        # Auto-generate guidance from step
        try:
            step_enum = CollectionStep(step_value)
            message_parts.append(f"QUÉ HACER: {_get_phase_guidance(step_enum)}")
        except ValueError:
            pass
    
    if step_value:
        message_parts.append(f"PASO ACTUAL: {step_value}")
    
    return {
        "success": False,
        "error": error,
        "message": "\n\n".join(message_parts),
        "current_step": step_value,
    }


def _personal_data_complete(data: dict[str, Any] | None) -> bool:
    """Check if personal data has all required fields."""
    if not data:
        return False
    required = ["nombre", "apellidos", "dni_cif", "email"]
    return all(data.get(f) for f in required)


def _vehicle_data_complete(data: dict[str, Any] | None) -> bool:
    """Check if vehicle data has all required fields."""
    if not data:
        return False
    required = ["marca", "modelo", "matricula", "anio"]
    return all(data.get(f) for f in required)


async def _transition_with_db_sync(
    fsm_state: dict[str, Any] | None,
    target_step: CollectionStep,
    case_id: str | None = None,
) -> dict[str, Any]:
    """
    Transition FSM to a new step and sync to database.
    
    Wraps transition_to() and ensures DB metadata is updated.
    
    Args:
        fsm_state: Current FSM state
        target_step: Target step to transition to
        case_id: Case ID for DB sync (optional)
        
    Returns:
        New FSM state dict
    """
    new_fsm_state = transition_to(fsm_state, target_step)
    
    if case_id:
        await _update_case_metadata(case_id, {
            "current_step": target_step.value,
        })
    
    return new_fsm_state


async def _load_user_data_for_fsm(user_id: str | None) -> dict[str, str | None] | None:
    """
    Load existing user data from DB and map to FSM personal_data format.

    Maps User model fields to the FSM personal_data dict structure:
        User.first_name -> personal_data["nombre"]
        User.last_name -> personal_data["apellidos"]
        User.nif_cif -> personal_data["dni_cif"]
        User.email -> personal_data["email"]
        User.domicilio_* -> personal_data["domicilio_*"]

    Returns:
        Dict with personal_data fields, or None if no meaningful data exists.
    """
    if not user_id:
        return None

    try:
        async with get_async_session() as session:
            user = await session.get(User, uuid.UUID(user_id))
            if not user:
                return None

            # Only return if user has meaningful data beyond just a name
            if not any([user.first_name, user.nif_cif, user.email, user.domicilio_calle]):
                return None

            return {
                "nombre": user.first_name,
                "apellidos": user.last_name,
                "dni_cif": user.nif_cif,
                "email": user.email,
                "telefono": None,  # Already have WhatsApp
                "domicilio_calle": user.domicilio_calle,
                "domicilio_localidad": user.domicilio_localidad,
                "domicilio_provincia": user.domicilio_provincia,
                "domicilio_cp": user.domicilio_cp,
                "itv_nombre": None,  # ITV is per-case, always ask
            }
    except Exception as e:
        logger.warning(f"Failed to load user data for FSM pre-population: {e}")
        return None


@tool
async def iniciar_expediente(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    tarifa_calculada: float | None = None,
    tier_id: str | None = None,
) -> dict[str, Any]:
    """
    Inicia la recolección de datos para abrir un expediente de homologación.

    Usa esta herramienta cuando el usuario acepta abrir un expediente después
    de recibir un presupuesto. Crea un nuevo caso en la base de datos y
    comienza la recolección de datos personales.

    Args:
        categoria_vehiculo: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        codigos_elementos: Lista de códigos de elementos a homologar (ej: ["ESCAPE", "ALUMBRADO"])
        tarifa_calculada: Precio calculado sin IVA (opcional)
        tier_id: UUID del tier de tarifa (opcional)

    Returns:
        Dict con:
        - success: bool
        - message: str (prompt para el usuario)
        - case_id: str (si éxito)
        - error: str (si fallo)
    """
    # Get conversation context
    state = get_current_state()
    if not state:
        return {
            "success": False,
            "error": "No se pudo obtener el contexto de la conversación",
        }

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")

    if not conversation_id:
        return {
            "success": False,
            "error": "No se encontró el ID de conversación",
        }

    # Check if user already has an active case
    existing_case = await _get_active_case_for_conversation(conversation_id)
    if existing_case:
        status_desc = {
            "collecting": "en proceso de recolección de datos",
            "pending_images": "pendiente de imágenes",
            "pending_review": "pendiente de revisión por un agente",
            "in_progress": "siendo gestionado por un agente",
        }.get(existing_case.status, existing_case.status)
        
        return _tool_error_response(
            "Ya tienes un expediente en curso",
            guidance=(
                f"Tu expediente está {status_desc}. "
                f"No puedes abrir otro hasta que se complete o cancele el actual. "
                f"Si tienes dudas, puedo ayudarte con consultas mientras tanto."
            ),
        )

    # Get category ID
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        return {
            "success": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada",
        }

    # Create new case
    case_id = uuid.uuid4()

    try:
        async with get_async_session() as session:
            case = Case(
                id=case_id,
                conversation_id=conversation_id,
                user_id=uuid.UUID(user_id) if user_id else None,
                status="collecting",
                category_id=uuid.UUID(category_id),
                element_codes=codigos_elementos,
                tariff_tier_id=uuid.UUID(tier_id) if tier_id else None,
                tariff_amount=Decimal(str(tarifa_calculada)) if tarifa_calculada else None,
                metadata_={
                    "started_at": datetime.now(UTC).isoformat(),
                    "category_slug": categoria_vehiculo,
                    "current_step": CollectionStep.COLLECT_IMAGES.value,
                },
            )
            session.add(case)
            await session.commit()

            logger.info(
                f"Case created: case_id={case_id} | conversation_id={conversation_id}",
                extra={
                    "case_id": str(case_id),
                    "conversation_id": conversation_id,
                    "elements": codigos_elementos,
                },
            )

    except Exception as e:
        logger.error(f"Failed to create case: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error al crear el expediente: {str(e)}",
        }

    # Initialize FSM state (images-first flow)
    fsm_state = state.get("fsm_state")
    new_fsm_state = update_case_fsm_state(fsm_state, {
        "step": CollectionStep.COLLECT_IMAGES.value,  # Start with images!
        "case_id": str(case_id),
        "category_slug": categoria_vehiculo,
        "category_id": category_id,
        "element_codes": codigos_elementos,
        "received_images": [],  # Track received images for counting
        "tariff_tier_id": tier_id,
        "tariff_amount": tarifa_calculada,
        "taller_propio": None,  # Will be asked in COLLECT_WORKSHOP
        "taller_data": None,
        "retry_count": 0,
    })

    # Get prompt for next step (images first!)
    case_fsm_state = get_case_fsm_state(new_fsm_state)
    prompt = get_step_prompt(CollectionStep.COLLECT_IMAGES, case_fsm_state)

    # Make the message imperative so LLM uses it directly
    imperative_message = (
        "EXPEDIENTE CREADO. Ahora debes pedir las fotos al usuario.\n\n"
        "INSTRUCCIONES OBLIGATORIAS:\n"
        "1. NO pidas datos personales todavia - primero van las FOTOS\n"
        "2. NO vuelvas a enviar imagenes de ejemplo - ya las vio antes\n"
        "3. Dile al usuario que envie las fotos que vio en los ejemplos\n"
        "4. Cuando diga 'listo', usa continuar_a_datos_personales()\n\n"
        f"RESPONDE AL USUARIO CON ALGO COMO:\n{prompt}"
    )

    return {
        "success": True,
        "case_id": str(case_id),
        "message": imperative_message,
        "next_step": CollectionStep.COLLECT_IMAGES.value,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def actualizar_datos_expediente(
    datos_personales: dict[str, str] | None = None,
    datos_vehiculo: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Actualiza los datos del expediente activo con informacion del usuario.

    Usa esta herramienta para guardar datos personales o de vehiculo que el
    usuario proporcione durante la conversacion. Se usa despues de recolectar
    las imagenes.

    Args:
        datos_personales: Dict con campos (todos obligatorios excepto telefono):
            - nombre: str
            - apellidos: str
            - dni_cif: str (DNI, NIE o CIF)
            - email: str
            - telefono: str (opcional)
            - domicilio_calle: str
            - domicilio_localidad: str
            - domicilio_provincia: str
            - domicilio_cp: str (codigo postal)
            - itv_nombre: str (nombre de la ITV)
        datos_vehiculo: Dict con campos opcionales:
            - marca: str
            - modelo: str
            - anio: str (año del vehiculo)
            - matricula: str
            - bastidor: str (opcional)

    Returns:
        Dict con:
        - success: bool
        - message: str (siguiente prompt o confirmacion)
        - next_step: str (siguiente paso del FSM)
        - missing_fields: list[str] (campos que faltan)
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return _tool_error_response(
            "No hay expediente activo",
            guidance="Usa iniciar_expediente() primero para crear un expediente."
        )

    current_step = get_current_step(fsm_state)
    
    # Validate that we're in a phase where data collection is allowed
    allowed_phases = [
        CollectionStep.COLLECT_PERSONAL,
        CollectionStep.COLLECT_VEHICLE,
    ]
    if current_step not in allowed_phases:
        return _tool_error_response(
            "Esta herramienta solo funciona durante la recolección de datos personales o del vehículo",
            current_step=current_step,
        )

    # Update database and FSM state
    updates_for_case = {}  # Fields that go to Case table
    updates_for_user = {}  # Fields that go to User table
    updates_for_fsm = {}

    if datos_personales:
        # Merge with existing personal data
        existing_personal = case_fsm_state.get("personal_data", {})
        merged_personal = {**existing_personal}

        # All personal data fields (expanded)
        personal_fields = [
            "nombre", "apellidos", "email", "telefono",
            "dni_cif", "domicilio_calle", "domicilio_localidad",
            "domicilio_provincia", "domicilio_cp", "itv_nombre",
        ]
        for key in personal_fields:
            if key in datos_personales and datos_personales[key]:
                merged_personal[key] = datos_personales[key].strip()

        # Log unknown fields for debugging (helps identify LLM using wrong field names)
        unknown_personal = set(datos_personales.keys()) - set(personal_fields)
        if unknown_personal:
            logger.warning(
                f"actualizar_datos_expediente: campos no reconocidos en datos_personales: {unknown_personal}. "
                f"Campos válidos: {personal_fields}",
                extra={"unknown_fields": list(unknown_personal), "received_fields": list(datos_personales.keys())},
            )

        updates_for_fsm["personal_data"] = merged_personal

        # Prepare User updates (personal data goes to User)
        if merged_personal.get("nombre"):
            updates_for_user["first_name"] = merged_personal["nombre"]
        if merged_personal.get("apellidos"):
            updates_for_user["last_name"] = merged_personal["apellidos"]
        if merged_personal.get("email"):
            updates_for_user["email"] = merged_personal["email"]
        if merged_personal.get("dni_cif"):
            updates_for_user["nif_cif"] = merged_personal["dni_cif"].upper().replace(" ", "")
        if merged_personal.get("domicilio_calle"):
            updates_for_user["domicilio_calle"] = merged_personal["domicilio_calle"]
        if merged_personal.get("domicilio_localidad"):
            updates_for_user["domicilio_localidad"] = merged_personal["domicilio_localidad"]
        if merged_personal.get("domicilio_provincia"):
            updates_for_user["domicilio_provincia"] = merged_personal["domicilio_provincia"]
        if merged_personal.get("domicilio_cp"):
            updates_for_user["domicilio_cp"] = merged_personal["domicilio_cp"].replace(" ", "")

        # ITV goes to Case (not personal data)
        if merged_personal.get("itv_nombre"):
            updates_for_case["itv_nombre"] = merged_personal["itv_nombre"]

    if datos_vehiculo:
        # Merge with existing vehicle data
        existing_vehicle = case_fsm_state.get("vehicle_data", {})
        merged_vehicle = {**existing_vehicle}

        vehicle_fields = ["marca", "modelo", "anio", "matricula", "bastidor"]
        for key in vehicle_fields:
            if key in datos_vehiculo and datos_vehiculo[key]:
                value = datos_vehiculo[key].strip()
                if key == "matricula":
                    value = normalize_matricula(value)
                merged_vehicle[key] = value

        # Log unknown fields for debugging
        unknown_vehicle = set(datos_vehiculo.keys()) - set(vehicle_fields)
        if unknown_vehicle:
            logger.warning(
                f"actualizar_datos_expediente: campos no reconocidos en datos_vehiculo: {unknown_vehicle}. "
                f"Campos válidos: {vehicle_fields}",
                extra={"unknown_fields": list(unknown_vehicle), "received_fields": list(datos_vehiculo.keys())},
            )

        updates_for_fsm["vehicle_data"] = merged_vehicle

        # Vehicle data goes to Case
        if merged_vehicle.get("marca"):
            updates_for_case["vehiculo_marca"] = merged_vehicle["marca"]
        if merged_vehicle.get("modelo"):
            updates_for_case["vehiculo_modelo"] = merged_vehicle["modelo"]
        if merged_vehicle.get("anio"):
            try:
                updates_for_case["vehiculo_anio"] = int(merged_vehicle["anio"])
            except ValueError:
                pass
        if merged_vehicle.get("matricula"):
            updates_for_case["vehiculo_matricula"] = merged_vehicle["matricula"]
        if merged_vehicle.get("bastidor"):
            updates_for_case["vehiculo_bastidor"] = merged_vehicle["bastidor"]

    # Update database
    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if not case:
                return {"success": False, "error": "No se encontro el expediente"}

            # Update User with personal data
            if updates_for_user and case.user_id:
                user = await session.get(User, case.user_id)
                if user:
                    for key, value in updates_for_user.items():
                        setattr(user, key, value)
                    user.updated_at = datetime.now(UTC)
                    logger.info(
                        f"User updated: user_id={case.user_id}",
                        extra={"user_id": str(case.user_id), "updates": list(updates_for_user.keys())},
                    )

            # Update Case with vehicle/ITV data
            if updates_for_case:
                for key, value in updates_for_case.items():
                    setattr(case, key, value)
                case.updated_at = datetime.now(UTC)
                logger.info(
                    f"Case updated: case_id={case_id}",
                    extra={"case_id": case_id, "updates": list(updates_for_case.keys())},
                )

            await session.commit()
    except Exception as e:
        logger.error(f"Failed to update case/user: {e}", exc_info=True)
        return {"success": False, "error": f"Error al actualizar: {str(e)}"}

    # Update FSM state
    new_fsm_state = update_case_fsm_state(fsm_state, updates_for_fsm)
    case_fsm_state = get_case_fsm_state(new_fsm_state)

    # Determine next step based on validation
    next_step = current_step
    message = ""
    missing = []

    if current_step == CollectionStep.COLLECT_PERSONAL:
        personal_data = case_fsm_state.get("personal_data", {})
        is_valid, missing = validate_personal_data(personal_data)

        if is_valid:
            # AUTO-TRANSITION: Personal data complete -> Vehicle data
            new_fsm_state = await _transition_with_db_sync(
                new_fsm_state, CollectionStep.COLLECT_VEHICLE, case_id
            )
            next_step = CollectionStep.COLLECT_VEHICLE
            case_fsm_state = get_case_fsm_state(new_fsm_state)
            message = get_step_prompt(next_step, case_fsm_state)
            logger.info(
                f"Auto-transition: COLLECT_PERSONAL -> COLLECT_VEHICLE | case_id={case_id}",
                extra={"case_id": case_id, "transition": "personal_to_vehicle"},
            )
        else:
            message = f"Faltan los siguientes datos personales: {', '.join(missing)}. Por favor, proporcionalos."

    elif current_step == CollectionStep.COLLECT_VEHICLE:
        vehicle_data = case_fsm_state.get("vehicle_data", {})
        is_valid, missing = validate_vehicle_data(vehicle_data)

        if is_valid:
            # AUTO-TRANSITION: Vehicle data complete -> Workshop question
            new_fsm_state = await _transition_with_db_sync(
                new_fsm_state, CollectionStep.COLLECT_WORKSHOP, case_id
            )
            next_step = CollectionStep.COLLECT_WORKSHOP
            case_fsm_state = get_case_fsm_state(new_fsm_state)
            message = get_step_prompt(next_step, case_fsm_state)
            logger.info(
                f"Auto-transition: COLLECT_VEHICLE -> COLLECT_WORKSHOP | case_id={case_id}",
                extra={"case_id": case_id, "transition": "vehicle_to_workshop"},
            )
        else:
            message = f"Faltan los siguientes datos del vehiculo: {', '.join(missing)}. Por favor, proporcionalos."

    return {
        "success": True,
        "message": message,
        "next_step": next_step.value if isinstance(next_step, CollectionStep) else next_step,
        "missing_fields": missing,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def actualizar_datos_taller(
    taller_propio: bool | None = None,
    datos_taller: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Actualiza los datos del taller en el expediente.

    Usa esta herramienta cuando el usuario responde sobre el certificado del taller.
    Primero se pregunta si quiere que MSI aporte el certificado (+85€) o si usara su propio
    taller. Si usa taller propio, se piden los datos del taller.

    Args:
        taller_propio: None para preguntar, False si MSI aporta certificado,
                       True si el cliente usa su propio taller
        datos_taller: Dict con datos del taller (TODOS son obligatorios si taller_propio=True):
            - nombre: Nombre del taller (ej: "Taller García")
            - responsable: Nombre del responsable (ej: "Luis Martínez")
            - domicilio: Dirección completa (ej: "C/ Industrial 10, Polígono Norte")
            - provincia: Provincia (ej: "Madrid")
            - ciudad: Ciudad (ej: "Alcobendas")
            - telefono: Teléfono de contacto (ej: "912345678")
            - registro_industrial: Número de registro industrial (ej: "TAL-12345")
            - actividad: Actividad del taller (ej: "reparación de motocicletas")

    Ejemplo de llamada completa:
        actualizar_datos_taller(
            taller_propio=True,
            datos_taller={
                "nombre": "Taller García",
                "responsable": "Luis Martínez",
                "domicilio": "C/ Industrial 10",
                "provincia": "Madrid",
                "ciudad": "Alcobendas",
                "telefono": "912345678",
                "registro_industrial": "TAL-12345",
                "actividad": "reparación de motocicletas"
            }
        )

    Returns:
        Dict con resultado y siguiente paso
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return _tool_error_response(
            "No hay expediente activo",
            guidance="Usa iniciar_expediente() primero para crear un expediente."
        )

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.COLLECT_WORKSHOP:
        return _tool_error_response(
            f"Esta herramienta solo funciona en la fase de recolección de taller",
            current_step=current_step,
            guidance=f"Estás en '{current_step.value}'. Completa primero esa fase antes de pedir datos del taller."
        )

    updates_for_db = {}
    updates_for_fsm = {}

    # Handle taller_propio decision
    if taller_propio is not None:
        updates_for_fsm["taller_propio"] = taller_propio
        updates_for_db["taller_propio"] = taller_propio

    # If user provides workshop data
    if datos_taller:
        # Map alternative field names that LLM might use
        field_mappings = {
            "direccion": "domicilio",
            "address": "domicilio",
            "numero_registro": "registro_industrial",
            "registro": "registro_industrial",
            "nif": "registro_industrial",
            "cif": "registro_industrial",
            "encargado": "responsable",
            "contacto": "responsable",
            "tlf": "telefono",
            "tel": "telefono",
            "phone": "telefono",
        }
        for alt_name, correct_name in field_mappings.items():
            if alt_name in datos_taller and correct_name not in datos_taller:
                datos_taller[correct_name] = datos_taller.pop(alt_name)
        
        existing_taller = case_fsm_state.get("taller_data") or {}
        merged_taller = {**existing_taller}

        taller_fields = [
            "nombre", "responsable", "domicilio", "provincia",
            "ciudad", "telefono", "registro_industrial", "actividad",
        ]
        for key in taller_fields:
            if key in datos_taller and datos_taller[key]:
                merged_taller[key] = datos_taller[key].strip()

        # Log unknown fields for debugging (after mapping)
        unknown_taller = set(datos_taller.keys()) - set(taller_fields)
        if unknown_taller:
            logger.warning(
                f"actualizar_datos_taller: campos no reconocidos: {unknown_taller}. "
                f"Campos válidos: {taller_fields}",
                extra={"unknown_fields": list(unknown_taller), "received_fields": list(datos_taller.keys())},
            )

        updates_for_fsm["taller_data"] = merged_taller

        # Prepare DB updates (map to taller_* columns)
        if merged_taller.get("nombre"):
            updates_for_db["taller_nombre"] = merged_taller["nombre"]
        if merged_taller.get("responsable"):
            updates_for_db["taller_responsable"] = merged_taller["responsable"]
        if merged_taller.get("domicilio"):
            updates_for_db["taller_domicilio"] = merged_taller["domicilio"]
        if merged_taller.get("provincia"):
            updates_for_db["taller_provincia"] = merged_taller["provincia"]
        if merged_taller.get("ciudad"):
            updates_for_db["taller_ciudad"] = merged_taller["ciudad"]
        if merged_taller.get("telefono"):
            updates_for_db["taller_telefono"] = merged_taller["telefono"]
        if merged_taller.get("registro_industrial"):
            updates_for_db["taller_registro_industrial"] = merged_taller["registro_industrial"]
        if merged_taller.get("actividad"):
            updates_for_db["taller_actividad"] = merged_taller["actividad"]

    # Update database
    if updates_for_db:
        try:
            async with get_async_session() as session:
                case = await session.get(Case, uuid.UUID(case_id))
                if case:
                    for key, value in updates_for_db.items():
                        setattr(case, key, value)
                    case.updated_at = datetime.now(UTC)
                    await session.commit()
                    logger.info(
                        f"Case taller data updated: case_id={case_id}",
                        extra={"case_id": case_id, "updates": list(updates_for_db.keys())},
                    )
        except Exception as e:
            logger.error(f"Failed to update case taller data: {e}", exc_info=True)
            return {"success": False, "error": f"Error al actualizar: {str(e)}"}

    # Update FSM state
    new_fsm_state = update_case_fsm_state(fsm_state, updates_for_fsm)
    case_fsm_state = get_case_fsm_state(new_fsm_state)

    # Determine next action
    current_taller_propio = case_fsm_state.get("taller_propio")

    # If MSI provides certificate, go straight to review
    if current_taller_propio is False:
        new_fsm_state = await _transition_with_db_sync(
            new_fsm_state, CollectionStep.REVIEW_SUMMARY, case_id
        )
        case_fsm_state = get_case_fsm_state(new_fsm_state)
        message = get_step_prompt(CollectionStep.REVIEW_SUMMARY, case_fsm_state)
        logger.info(
            f"Auto-transition: COLLECT_WORKSHOP -> REVIEW_SUMMARY (MSI certificate) | case_id={case_id}",
            extra={"case_id": case_id, "taller_propio": False},
        )
        
        return {
            "success": True,
            "message": message,
            "next_step": CollectionStep.REVIEW_SUMMARY.value,
            "fsm_state_update": new_fsm_state,
        }

    # If client uses own workshop, validate workshop data
    if current_taller_propio is True:
        taller_data = case_fsm_state.get("taller_data")
        is_valid, missing = validate_workshop_data(taller_data)

        if is_valid:
            new_fsm_state = await _transition_with_db_sync(
                new_fsm_state, CollectionStep.REVIEW_SUMMARY, case_id
            )
            case_fsm_state = get_case_fsm_state(new_fsm_state)
            message = get_step_prompt(CollectionStep.REVIEW_SUMMARY, case_fsm_state)
            logger.info(
                f"Auto-transition: COLLECT_WORKSHOP -> REVIEW_SUMMARY (own workshop) | case_id={case_id}",
                extra={"case_id": case_id, "taller_propio": True},
            )
            
            return {
                "success": True,
                "message": message,
                "next_step": CollectionStep.REVIEW_SUMMARY.value,
                "fsm_state_update": new_fsm_state,
            }
        else:
            message = f"Faltan los siguientes datos del taller: {', '.join(missing)}. Por favor, proporcionaos."
            return {
                "success": True,
                "message": message,
                "next_step": CollectionStep.COLLECT_WORKSHOP.value,
                "missing_fields": missing,
                "fsm_state_update": new_fsm_state,
            }

    # Still need to ask if taller_propio is None
    message = get_step_prompt(CollectionStep.COLLECT_WORKSHOP, case_fsm_state)
    return {
        "success": True,
        "message": message,
        "next_step": CollectionStep.COLLECT_WORKSHOP.value,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def continuar_a_datos_personales() -> dict[str, Any]:
    """
    Avanza al paso de recoleccion de datos personales despues de recibir las imagenes.

    Usa esta herramienta cuando el usuario ha enviado todas las imagenes
    requeridas y quiere continuar con sus datos personales.

    Returns:
        Dict con el siguiente prompt
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return _tool_error_response(
            "No hay expediente activo",
            guidance="Usa iniciar_expediente() primero para crear un expediente."
        )

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.COLLECT_IMAGES:
        return _tool_error_response(
            "Esta herramienta solo funciona durante la recolección de imágenes",
            current_step=current_step,
            guidance=f"Estás en '{current_step.value}'. Esta herramienta es para cuando el usuario termina de enviar fotos."
        )

    # Transition to personal data collection (new flow!)
    new_fsm_state = await _transition_with_db_sync(fsm_state, CollectionStep.COLLECT_PERSONAL, case_id)

    # PRE-POPULATE: Load existing user data into FSM personal_data
    user_id = state.get("user_id")
    existing_data = await _load_user_data_for_fsm(user_id)
    if existing_data:
        new_fsm_state = update_case_fsm_state(new_fsm_state, {
            "personal_data": existing_data,
        })
        filled_fields = [k for k, v in existing_data.items() if v]
        logger.info(
            f"Pre-populated personal_data from User DB | case_id={case_id} | "
            f"filled={filled_fields}",
            extra={"case_id": case_id, "filled_fields": filled_fields},
        )

    case_fsm_state = get_case_fsm_state(new_fsm_state)
    message = get_step_prompt(CollectionStep.COLLECT_PERSONAL, case_fsm_state)

    return {
        "success": True,
        "message": message,
        "next_step": CollectionStep.COLLECT_PERSONAL.value,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def finalizar_expediente() -> dict[str, Any]:
    """
    Completa el expediente y escala a un agente humano para revisión.

    Usa esta herramienta cuando el usuario confirma el resumen del expediente.
    El expediente se marca como pendiente de revisión, se crea una escalación
    y se deshabilita el bot para que un agente humano atienda al cliente.

    Returns:
        Dict con confirmación y ID de escalación
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")
    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return _tool_error_response(
            "No hay expediente activo",
            guidance="Usa iniciar_expediente() primero para crear un expediente."
        )

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.REVIEW_SUMMARY:
        # Provide clear guidance on what steps need to be completed
        step_order = ["collect_images", "collect_personal", "collect_vehicle", "collect_workshop", "review_summary"]
        current_idx = step_order.index(current_step.value) if current_step.value in step_order else -1
        remaining_steps = step_order[current_idx + 1:] if current_idx >= 0 else step_order
        
        return _tool_error_response(
            f"No puedes finalizar el expediente todavía",
            current_step=current_step,
            guidance=(
                f"Debes completar estos pasos primero: {', '.join(remaining_steps)}. "
                f"Usa las herramientas: actualizar_datos_expediente(), actualizar_datos_taller(). "
                f"NO digas al usuario que el expediente está completado."
            )
        )

    # Mark case as pending_review (no escalation, bot stays active)
    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if case:
                case.status = "pending_review"
                case.completed_at = datetime.now(UTC)
                case.updated_at = datetime.now(UTC)

                # Update metadata with completed step
                metadata = case.metadata_ or {}
                metadata["current_step"] = CollectionStep.COMPLETED.value
                metadata["completed_at"] = datetime.now(UTC).isoformat()
                case.metadata_ = metadata

            await session.commit()

            logger.info(
                f"Case finalized (pending_review): case_id={case_id}",
                extra={
                    "case_id": case_id,
                    "conversation_id": conversation_id,
                },
            )

    except Exception as e:
        logger.error(f"Failed to finalize case: {e}", exc_info=True)
        return _tool_error_response(
            f"Error al finalizar el expediente: {str(e)}",
            current_step=current_step,
            guidance="Intenta de nuevo. Si el problema persiste, contacta con soporte."
        )

    # Reset FSM (bot stays active for further consultations)
    new_fsm_state = reset_fsm(fsm_state)

    return {
        "success": True,
        "message": (
            "¡Perfecto! Tu expediente ha sido enviado para revisión.\n\n"
            "Un agente de MSI Automotive lo revisará y se pondrá en contacto "
            "contigo a la mayor brevedad posible.\n\n"
            "Mientras tanto, si tienes alguna otra consulta, estaré encantado de ayudarte."
        ),
        "case_id": case_id,
        "next_step": CollectionStep.COMPLETED.value,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def cancelar_expediente(
    motivo: str = "Cancelado por el usuario",
) -> dict[str, Any]:
    """
    Cancela el expediente activo.

    Usa esta herramienta cuando el usuario quiere cancelar el proceso
    de recolección de datos.

    Args:
        motivo: Razón de la cancelación

    Returns:
        Dict con confirmación
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return _tool_error_response(
            "No hay expediente activo que cancelar",
            guidance="No hay ningún expediente en curso. Puedes ayudar al usuario con consultas o crear uno nuevo con iniciar_expediente()."
        )

    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if case:
                case.status = "cancelled"
                case.updated_at = datetime.now(UTC)
                case.notes = (case.notes or "") + f"\nCancelado: {motivo}"
                await session.commit()

                logger.info(
                    f"Case cancelled: case_id={case_id} | reason={motivo}",
                    extra={"case_id": case_id, "reason": motivo},
                )

    except Exception as e:
        logger.error(f"Failed to cancel case: {e}", exc_info=True)
        return {"success": False, "error": f"Error al cancelar: {str(e)}"}

    # Reset FSM
    new_fsm_state = reset_fsm(fsm_state)

    return {
        "success": True,
        "message": "El expediente ha sido cancelado. Si necesitas ayuda con algo más, no dudes en preguntar.",
        "fsm_state_update": new_fsm_state,
    }


@tool
async def obtener_estado_expediente() -> dict[str, Any]:
    """
    Obtiene el estado actual del expediente activo.

    Usa esta herramienta para consultar en qué paso se encuentra
    la recolección de datos y qué información falta.

    Returns:
        Dict con estado del expediente
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")

    fsm_state = state.get("fsm_state")

    if not is_case_collection_active(fsm_state):
        return {
            "success": True,
            "has_active_case": False,
            "message": "No hay expediente activo en este momento.",
        }

    case_fsm_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)

    personal_data = case_fsm_state.get("personal_data", {})
    vehicle_data = case_fsm_state.get("vehicle_data", {})
    received_images = case_fsm_state.get("received_images", [])

    # Check personal data completeness (expanded fields)
    required_personal_fields = [
        "nombre", "apellidos", "email", "dni_cif",
        "domicilio_calle", "domicilio_localidad",
        "domicilio_provincia", "domicilio_cp", "itv_nombre",
    ]
    personal_data_complete = all(personal_data.get(k) for k in required_personal_fields)

    return {
        "success": True,
        "has_active_case": True,
        "case_id": case_fsm_state.get("case_id"),
        "current_step": current_step.value,
        "personal_data_complete": personal_data_complete,
        "vehicle_data_complete": all(vehicle_data.get(k) for k in ["marca", "modelo", "matricula"]),
        "taller_propio": case_fsm_state.get("taller_propio"),
        "taller_data_complete": case_fsm_state.get("taller_propio") is False or bool(case_fsm_state.get("taller_data")),
        "images_received": len(received_images),
        "elements": case_fsm_state.get("element_codes", []),
        "tariff_amount": case_fsm_state.get("tariff_amount"),
    }


@tool
async def consulta_durante_expediente(
    consulta: str | None = None,
    accion: str = "responder",
) -> dict[str, Any]:
    """
    Maneja consultas y acciones del usuario durante un expediente activo.
    
    Usa esta herramienta cuando el usuario:
    - Hace una pregunta no relacionada con el paso actual del expediente
    - Quiere cancelar el expediente
    - Necesita pausar para hacer algo más
    - Quiere reanudar después de una pausa
    
    Args:
        consulta: La pregunta o solicitud del usuario (opcional)
        accion: Tipo de acción:
            - "responder": Responder consulta sin perder el contexto del expediente
            - "cancelar": Cancelar el expediente (delega a cancelar_expediente)
            - "pausar": Pausar temporalmente para atender otra cosa
            - "reanudar": Continuar con el expediente después de una pausa
    
    Returns:
        Dict con instrucciones sobre cómo proceder
    """
    state = get_current_state()
    if not state:
        return _tool_error_response("No se pudo obtener el contexto")
    
    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    current_step = get_current_step(fsm_state)
    case_id = case_fsm_state.get("case_id")
    
    # Normalize action
    accion = accion.lower().strip() if accion else "responder"
    valid_actions = ["responder", "cancelar", "pausar", "reanudar"]
    if accion not in valid_actions:
        accion = "responder"
    
    # Handle cancel action
    if accion == "cancelar":
        if case_id:
            return await cancelar_expediente(motivo=consulta or "Cancelado por el usuario")
        return {
            "success": True,
            "message": "No hay expediente activo que cancelar. Puedes ayudar al usuario con cualquier consulta.",
        }
    
    # Check if there's an active case
    if not is_case_collection_active(fsm_state):
        return {
            "success": True,
            "has_active_case": False,
            "message": (
                "No hay expediente activo en este momento. "
                "Puedes responder la consulta del usuario libremente y ofrecerle "
                "ayuda con presupuestos o abrir un nuevo expediente."
            ),
        }
    
    # Get step description in Spanish
    step_descriptions = {
        CollectionStep.COLLECT_IMAGES: "recolección de imágenes",
        CollectionStep.COLLECT_PERSONAL: "datos personales",
        CollectionStep.COLLECT_VEHICLE: "datos del vehículo",
        CollectionStep.COLLECT_WORKSHOP: "datos del taller",
        CollectionStep.REVIEW_SUMMARY: "revisión del resumen",
    }
    step_desc = step_descriptions.get(current_step, current_step.value)
    
    if accion == "pausar":
        return {
            "success": True,
            "message": (
                f"Expediente pausado temporalmente. El usuario estaba en el paso de {step_desc}. "
                f"Responde su consulta o atiende su solicitud. "
                f"Cuando quiera continuar, recuérdale en qué paso estaba y pregunta si desea continuar."
            ),
            "current_step": current_step.value,
            "paused": True,
        }
    
    if accion == "reanudar":
        prompt = get_step_prompt(current_step, case_fsm_state)
        return {
            "success": True,
            "message": (
                f"Continuemos con el expediente. Estabas en el paso de {step_desc}.\n\n{prompt}"
            ),
            "current_step": current_step.value,
            "resumed": True,
        }
    
    # Default: "responder"
    return {
        "success": True,
        "message": (
            f"El usuario tiene un expediente activo en el paso de '{step_desc}'. "
            f"Responde su consulta: '{consulta or '(no especificada)'}'. "
            f"Después de responder, recuérdale amablemente que tiene un expediente pendiente "
            f"y pregunta si quiere continuar con el proceso de {step_desc}."
        ),
        "current_step": current_step.value,
        "has_active_case": True,
    }


# List of all case tools
# NOTE: procesar_imagen* tools were removed - images are now handled silently
# in main.py with batching and timeout confirmation
CASE_TOOLS = [
    iniciar_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    continuar_a_datos_personales,
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
    consulta_durante_expediente,
]


def get_case_tools() -> list:
    """Get all case management tools."""
    return CASE_TOOLS
