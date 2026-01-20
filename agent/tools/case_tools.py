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
    get_required_images_for_elements,
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
        return {
            "success": False,
            "error": (
                f"Ya tienes un expediente abierto (ID: {str(existing_case.id)[:8]}...). "
                f"Debes completarlo o cancelarlo antes de abrir otro."
            ),
            "existing_case_id": str(existing_case.id),
        }

    # Get category ID
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        return {
            "success": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada",
        }

    # Create new case
    case_id = uuid.uuid4()

    # Get required images for these elements
    required_images = get_required_images_for_elements(codigos_elementos, categoria_vehiculo)
    pending_image_names = [img["display_name"] for img in required_images]

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
        "required_images": required_images,
        "received_images": [],
        "pending_images": pending_image_names,
        "tariff_tier_id": tier_id,
        "tariff_amount": tarifa_calculada,
        "taller_propio": None,  # Will be asked in COLLECT_WORKSHOP
        "taller_data": None,
        "retry_count": 0,
    })

    # Get prompt for next step (images first!)
    case_fsm_state = get_case_fsm_state(new_fsm_state)
    prompt = get_step_prompt(CollectionStep.COLLECT_IMAGES, case_fsm_state)

    return {
        "success": True,
        "case_id": str(case_id),
        "message": prompt,
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
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return {
            "success": False,
            "error": "No hay expediente activo. Usa iniciar_expediente primero.",
        }

    current_step = get_current_step(fsm_state)

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

        for key in ["marca", "modelo", "anio", "matricula", "bastidor"]:
            if key in datos_vehiculo and datos_vehiculo[key]:
                value = datos_vehiculo[key].strip()
                if key == "matricula":
                    value = normalize_matricula(value)
                merged_vehicle[key] = value

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
            # Transition to workshop question (new flow!)
            new_fsm_state = transition_to(new_fsm_state, CollectionStep.COLLECT_WORKSHOP)
            next_step = CollectionStep.COLLECT_WORKSHOP
            case_fsm_state = get_case_fsm_state(new_fsm_state)
            message = get_step_prompt(next_step, case_fsm_state)
        else:
            message = f"Faltan los siguientes datos: {', '.join(missing)}. Por favor, proporcionaos."

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
    Primero se pregunta si quiere que MSI aporte el certificado o si usara su propio
    taller. Si usa taller propio, se piden los datos del taller.

    Args:
        taller_propio: None para preguntar, False si MSI aporta certificado,
                       True si el cliente usa su propio taller
        datos_taller: Dict con datos del taller (solo si taller_propio=True):
            - nombre: str
            - responsable: str
            - domicilio: str
            - provincia: str
            - ciudad: str
            - telefono: str
            - registro_industrial: str
            - actividad: str

    Returns:
        Dict con resultado y siguiente paso
    """
    state = get_current_state()
    if not state:
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return {"success": False, "error": "No hay expediente activo"}

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.COLLECT_WORKSHOP:
        return {
            "success": False,
            "error": f"El paso actual no es recoleccion de datos del taller (es {current_step.value})",
        }

    updates_for_db = {}
    updates_for_fsm = {}

    # Handle taller_propio decision
    if taller_propio is not None:
        updates_for_fsm["taller_propio"] = taller_propio
        updates_for_db["taller_propio"] = taller_propio

    # If user provides workshop data
    if datos_taller:
        existing_taller = case_fsm_state.get("taller_data") or {}
        merged_taller = {**existing_taller}

        taller_fields = [
            "nombre", "responsable", "domicilio", "provincia",
            "ciudad", "telefono", "registro_industrial", "actividad",
        ]
        for key in taller_fields:
            if key in datos_taller and datos_taller[key]:
                merged_taller[key] = datos_taller[key].strip()

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
        new_fsm_state = transition_to(new_fsm_state, CollectionStep.REVIEW_SUMMARY)
        case_fsm_state = get_case_fsm_state(new_fsm_state)
        message = get_step_prompt(CollectionStep.REVIEW_SUMMARY, case_fsm_state)
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
            new_fsm_state = transition_to(new_fsm_state, CollectionStep.REVIEW_SUMMARY)
            case_fsm_state = get_case_fsm_state(new_fsm_state)
            message = get_step_prompt(CollectionStep.REVIEW_SUMMARY, case_fsm_state)
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
async def procesar_imagen_expediente(
    display_name: str,
    element_code: str | None = None,
    image_type: str = "element_photo",
) -> dict[str, Any]:
    """
    Procesa una imagen recibida del usuario y la guarda en el expediente.

    Usa esta herramienta cuando el usuario envía una imagen durante la
    recolección de documentación. La imagen se descarga desde Chatwoot
    y se guarda con un nombre descriptivo.

    Args:
        display_name: Nombre descriptivo de la imagen (ej: "escape_foto_general")
        element_code: Código del elemento relacionado (opcional, ej: "ESCAPE")
        image_type: Tipo de imagen: "base_documentation", "element_photo", "other"

    Returns:
        Dict con:
        - success: bool
        - message: str
        - images_remaining: int (imágenes que faltan)
        - can_continue: bool (si se puede avanzar al siguiente paso)
    """
    state = get_current_state()
    if not state:
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")
    incoming_attachments = state.get("incoming_attachments", [])

    if not case_id:
        return {"success": False, "error": "No hay expediente activo"}

    # SECURITY: Check image count limit per case
    MAX_IMAGES_PER_CASE = 50
    try:
        async with get_async_session() as session:
            from sqlalchemy import func, select

            count_query = select(func.count(CaseImage.id)).where(
                CaseImage.case_id == uuid.UUID(case_id)
            )
            image_count = (await session.execute(count_query)).scalar() or 0

            if image_count >= MAX_IMAGES_PER_CASE:
                return {
                    "success": False,
                    "error": f"Limite alcanzado: maximo {MAX_IMAGES_PER_CASE} imagenes por expediente.",
                }
    except Exception as e:
        logger.error(f"Error checking image count: {e}")
        # Continue anyway - don't block on count check failure

    if not incoming_attachments:
        return {
            "success": False,
            "error": "No se recibió ninguna imagen en este mensaje",
        }

    # Get image attachment (first image in list)
    image_attachment = None
    for att in incoming_attachments:
        if att.get("file_type") == "image":
            image_attachment = att
            break

    if not image_attachment:
        return {
            "success": False,
            "error": "No se encontró ninguna imagen adjunta",
        }

    # Download and save image
    from api.services.chatwoot_image_service import get_chatwoot_image_service

    image_service = get_chatwoot_image_service()

    download_result = await image_service.download_image(
        data_url=image_attachment["data_url"],
        display_name=display_name,
        element_code=element_code,
    )

    if not download_result:
        return {
            "success": False,
            "error": "Error al descargar la imagen. Por favor, intenta enviarla de nuevo.",
        }

    # Save to database
    try:
        async with get_async_session() as session:
            case_image = CaseImage(
                id=uuid.uuid4(),
                case_id=uuid.UUID(case_id),
                stored_filename=download_result["stored_filename"],
                original_filename=download_result.get("original_filename"),
                mime_type=download_result["mime_type"],
                file_size=download_result.get("file_size"),
                display_name=display_name,
                element_code=element_code,
                image_type=image_type,
            )
            session.add(case_image)
            await session.commit()

            logger.info(
                f"Case image saved: case_id={case_id} | display_name={display_name}",
                extra={
                    "case_id": case_id,
                    "display_name": display_name,
                    "stored_filename": download_result["stored_filename"],
                },
            )

    except Exception as e:
        logger.error(f"Failed to save case image: {e}", exc_info=True)
        return {"success": False, "error": f"Error al guardar la imagen: {str(e)}"}

    # Update FSM state
    received_images = case_fsm_state.get("received_images", [])
    pending_images = case_fsm_state.get("pending_images", [])

    if display_name not in received_images:
        received_images.append(display_name)
    if display_name in pending_images:
        pending_images.remove(display_name)

    new_fsm_state = update_case_fsm_state(fsm_state, {
        "received_images": received_images,
        "pending_images": pending_images,
    })

    # Check if all required images are received
    required_images = case_fsm_state.get("required_images", [])
    required_display_names = [
        img["display_name"] for img in required_images
        if img.get("is_required", True)
    ]
    all_required_received = all(
        name in received_images for name in required_display_names
    )

    message = f"Imagen '{display_name}' recibida y guardada correctamente."

    if pending_images:
        message += f"\n\nFaltan {len(pending_images)} imagen(es)."
    elif all_required_received:
        message += "\n\n¡Ya tienes todas las imágenes requeridas! ¿Quieres continuar al resumen?"

    return {
        "success": True,
        "message": message,
        "images_remaining": len(pending_images),
        "can_continue": all_required_received,
        "fsm_state_update": new_fsm_state,
    }


@tool
async def procesar_imagenes_expediente(
    display_names: list[str],
    element_codes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Procesa MÚLTIPLES imágenes del usuario para un expediente activo.

    USA ESTA HERRAMIENTA cuando el usuario envíe UNA O MÁS imágenes.
    Procesa todas las imágenes en un solo paso.

    Args:
        display_names: Lista de nombres descriptivos para cada imagen
                      Ejemplo: ["ficha_tecnica", "matricula_visible", "escape_foto_general"]
        element_codes: Lista OPCIONAL de códigos de elementos (uno por imagen o None)
                      Ejemplo: [None, None, "ESCAPE"]

    Returns:
        Dict con success, mensaje y estado actualizado
    """
    state = get_current_state()
    if not state:
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")
    conversation_id = state.get("conversation_id")
    incoming_attachments = state.get("incoming_attachments", [])

    if not case_id:
        return {"success": False, "error": "No hay expediente activo. Usa iniciar_expediente() primero."}

    # Get ALL images from attachments
    image_attachments = [
        att for att in incoming_attachments
        if att.get("file_type") == "image"
    ]

    if not image_attachments:
        return {"success": False, "error": "No hay imágenes en este mensaje."}

    # Validate count matches
    num_images = len(image_attachments)
    num_names = len(display_names)

    if num_images != num_names:
        return {
            "success": False,
            "error": (
                f"ERROR: Detecté {num_images} imágenes pero recibí {num_names} nombres.\n"
                f"Debes proporcionar exactamente un nombre para cada imagen.\n"
                f"Imágenes detectadas: {num_images}\n"
                f"Nombres recibidos: {num_names}"
            )
        }

    # Validate element_codes if provided
    if element_codes and len(element_codes) != num_images:
        return {
            "success": False,
            "error": (
                f"ERROR: Si proporcionas element_codes, debe haber uno por imagen.\n"
                f"Imágenes: {num_images}, element_codes: {len(element_codes)}"
            )
        }

    # Check image limit
    MAX_IMAGES_PER_CASE = 50
    try:
        from sqlalchemy import func, select

        async with get_async_session() as session:
            count_query = select(func.count()).select_from(CaseImage).where(CaseImage.case_id == uuid.UUID(case_id))
            current_image_count = (await session.execute(count_query)).scalar() or 0

            if current_image_count + num_images > MAX_IMAGES_PER_CASE:
                return {
                    "success": False,
                    "error": f"Límite alcanzado: máximo {MAX_IMAGES_PER_CASE} imágenes por expediente. (Tienes {current_image_count}, intentas agregar {num_images})",
                }
    except Exception as e:
        logger.error(f"Error checking image count: {e}")

    # Process each image
    from api.services.chatwoot_image_service import get_chatwoot_image_service
    image_service = get_chatwoot_image_service()

    results = []
    failed = []
    received_images = case_fsm_state.get("received_images", [])
    pending_images = case_fsm_state.get("pending_images", [])

    for idx, (att, name) in enumerate(zip(image_attachments, display_names)):
        element_code = element_codes[idx] if element_codes and idx < len(element_codes) else None

        try:
            # Download image
            download_result = await image_service.download_image(
                data_url=att["data_url"],
                display_name=name,
                element_code=element_code,
            )

            if not download_result:
                failed.append(f"Imagen {idx+1} ({name}): Error al descargar")
                continue

            # Determine image type
            image_type = "general"
            if name in ["ficha_tecnica", "matricula_visible"]:
                image_type = "base"
            elif element_code:
                image_type = "element"

            # Save to database
            async with get_async_session() as session:
                case_image = CaseImage(
                    id=uuid.uuid4(),
                    case_id=uuid.UUID(case_id),
                    stored_filename=download_result["stored_filename"],
                    original_filename=download_result.get("original_filename"),
                    mime_type=download_result["mime_type"],
                    file_size=download_result.get("file_size"),
                    display_name=name,
                    element_code=element_code,
                    image_type=image_type,
                )
                session.add(case_image)
                await session.commit()

            # Update FSM state tracking
            if name not in received_images:
                received_images.append(name)
            if name in pending_images:
                pending_images.remove(name)

            results.append(f"✓ {name}")

            logger.info(
                f"[procesar_imagenes_expediente] Image {idx+1} saved | case_id={case_id}",
                extra={"name": name, "element_code": element_code, "conversation_id": conversation_id}
            )

        except Exception as e:
            failed.append(f"Imagen {idx+1} ({name}): {str(e)}")
            logger.error(
                f"[procesar_imagenes_expediente] Failed to process image {idx+1}",
                extra={"name": name, "error": str(e), "conversation_id": conversation_id}
            )

    # Update FSM state
    new_fsm_state = update_case_fsm_state(fsm_state, {
        "received_images": received_images,
        "pending_images": pending_images,
    })

    # Check if all required images are received
    required_images = case_fsm_state.get("required_images", [])
    required_display_names = [
        img["display_name"] for img in required_images
        if img.get("is_required", True)
    ]
    all_required_received = all(
        name in received_images for name in required_display_names
    )

    # Build response
    response_lines = []
    if results:
        response_lines.append(f"✅ Procesadas {len(results)} imágenes correctamente:")
        response_lines.extend(results)

    if failed:
        response_lines.append(f"\n⚠️ {len(failed)} imágenes fallaron:")
        response_lines.extend(failed)

    if not results and not failed:
        return {"success": False, "error": "No se pudo procesar ninguna imagen."}

    message = "\n".join(response_lines)

    if pending_images:
        message += f"\n\nFaltan {len(pending_images)} imagen(es) pendientes."
    elif all_required_received:
        message += "\n\n¡Ya tienes todas las imágenes requeridas! ¿Quieres continuar al resumen?"

    return {
        "success": True,
        "message": message,
        "processed_count": len(results),
        "failed_count": len(failed),
        "images_remaining": len(pending_images),
        "can_continue": all_required_received,
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
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return {"success": False, "error": "No hay expediente activo"}

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.COLLECT_IMAGES:
        return {
            "success": False,
            "error": f"No estas en el paso de recoleccion de imagenes (actual: {current_step.value})",
        }

    # Transition to personal data collection (new flow!)
    new_fsm_state = transition_to(fsm_state, CollectionStep.COLLECT_PERSONAL)
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
        return {"success": False, "error": "No se pudo obtener el contexto"}

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")
    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return {"success": False, "error": "No hay expediente activo"}

    current_step = get_current_step(fsm_state)
    if current_step != CollectionStep.REVIEW_SUMMARY:
        return {
            "success": False,
            "error": f"No estás en el paso de revisión (actual: {current_step.value})",
        }

    # Create escalation
    escalation_id = uuid.uuid4()

    try:
        async with get_async_session() as session:
            # Create escalation
            escalation = Escalation(
                id=escalation_id,
                conversation_id=str(conversation_id),
                user_id=uuid.UUID(user_id) if user_id else None,
                reason="Expediente de homologación completado - Pendiente de revisión",
                source="case_completion",
                status="pending",
                triggered_at=datetime.now(UTC),
                metadata_={
                    "case_id": case_id,
                    "elements": case_fsm_state.get("element_codes", []),
                    "tariff_amount": case_fsm_state.get("tariff_amount"),
                },
            )
            session.add(escalation)

            # Update case
            case = await session.get(Case, uuid.UUID(case_id))
            if case:
                case.status = "pending_review"
                case.escalation_id = escalation_id
                case.completed_at = datetime.now(UTC)
                case.updated_at = datetime.now(UTC)

            await session.commit()

            logger.info(
                f"Case finalized: case_id={case_id} | escalation_id={escalation_id}",
                extra={
                    "case_id": case_id,
                    "escalation_id": str(escalation_id),
                    "conversation_id": conversation_id,
                },
            )

    except Exception as e:
        logger.error(f"Failed to finalize case: {e}", exc_info=True)
        return {"success": False, "error": f"Error al finalizar: {str(e)}"}

    # Disable bot in Chatwoot
    try:
        from shared.chatwoot_client import ChatwootClient

        chatwoot = ChatwootClient()
        await chatwoot.update_conversation_attributes(
            conversation_id=int(conversation_id),
            attributes={"atencion_automatica": False},
        )
        logger.info(f"Bot disabled for conversation {conversation_id}")

        # Add label
        try:
            await chatwoot.add_labels(int(conversation_id), ["expediente-completo"])
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"Failed to disable bot: {e}")

    # Reset FSM
    new_fsm_state = reset_fsm(fsm_state)

    return {
        "success": True,
        "message": (
            "¡Perfecto! Tu expediente ha sido enviado para revisión.\n\n"
            "Un agente de MSI Automotive lo revisará y se pondrá en contacto "
            "contigo a la mayor brevedad posible.\n\n"
            "¡Gracias por confiar en nosotros!"
        ),
        "case_id": case_id,
        "escalation_id": str(escalation_id),
        "next_step": CollectionStep.COMPLETED.value,
        "fsm_state_update": new_fsm_state,
        "escalation_triggered": True,
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
        return {"success": False, "error": "No se pudo obtener el contexto"}

    fsm_state = state.get("fsm_state")
    case_fsm_state = get_case_fsm_state(fsm_state)
    case_id = case_fsm_state.get("case_id")

    if not case_id:
        return {"success": False, "error": "No hay expediente activo que cancelar"}

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
        return {"success": False, "error": "No se pudo obtener el contexto"}

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
    pending_images = case_fsm_state.get("pending_images", [])

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
        "images_pending": len(pending_images),
        "elements": case_fsm_state.get("element_codes", []),
        "tariff_amount": case_fsm_state.get("tariff_amount"),
    }


# List of all case tools
CASE_TOOLS = [
    iniciar_expediente,
    actualizar_datos_expediente,
    actualizar_datos_taller,
    procesar_imagen_expediente,
    procesar_imagenes_expediente,
    continuar_a_datos_personales,
    finalizar_expediente,
    cancelar_expediente,
    obtener_estado_expediente,
]


def get_case_tools() -> list:
    """Get all case management tools."""
    return CASE_TOOLS
