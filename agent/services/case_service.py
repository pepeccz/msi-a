"""
MSI-a — Case (expediente) business logic service.

Extracted from agent/tools/case_tools.py as part of the tools-refactor Wave 3.
All DB access, validation, and FSM transitions live here.  The tool module
becomes a thin wrapper that reads state, calls this service and returns the
result to LangGraph.

Service NEVER imports from agent/tools/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from agent.services.expediente_constants import CERT_SUPPLEMENT_EUR
from agent.services.expediente_helpers import (
    INITIAL_CASE_STATE,
    STEP_PROMPTS,
    build_case_update,
    can_transition_to,
    get_current_step,
    get_mode_context,
    is_collection_active,
    reset_case_collection,
    set_collection_step,
)
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.utils.expediente_types import (
    ELEMENT_STATUS_PENDING,
    CaseCollectionState,
    CollectionStep,
)
from agent.utils.expediente_validators import (
    normalize_matricula,
    validate_personal_data,
    validate_vehicle_data,
    validate_workshop_data,
)
from agent.utils.tool_helpers import tool_error_response
from database.connection import get_async_session
from database.models import Case, Element, Escalation, User

logger = structlog.get_logger(__name__)

# Minimum confidence threshold for element matching validation (70%)
MIN_CONFIDENCE_THRESHOLD = 0.7


# =============================================================================
# Private DB helpers
# =============================================================================


def _get_case_id_with_fallback(
    state: dict,
    case_fsm_state: CaseCollectionState,
) -> str | None:
    """
    Get case_id from FSM state with fallback to mode_context.

    The FSM ContextVar can lose case_id when current_mode != EXPEDIENTE_MODE
    due to timing issues.  This helper provides a defensive fallback.
    """
    case_id = case_fsm_state.get("case_id")
    if not case_id:
        mode_context = state.get("mode_context", {})
        case_id = mode_context.get("case_id")
        if case_id:
            logger.warning(
                "case_id_fsm_fallback",
                case_id=case_id,
                current_mode=state.get("current_mode"),
                msg="case_id recovered from mode_context (FSM state was stale)",
            )
    return case_id


async def _get_category_id_by_slug(slug: str) -> str | None:
    """Get category UUID by slug.  Returns None on error or missing slug."""
    try:
        async with get_async_session() as session:
            from sqlalchemy import select
            from database.models import VehicleCategory

            result = await session.execute(
                select(VehicleCategory.id).where(VehicleCategory.slug == slug)
            )
            row = result.first()
            return str(row[0]) if row else None
    except Exception as e:
        logger.error(
            "database_error_fetching_category_by_slug",
            slug=slug,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def _validate_element_codes_for_category(
    category_id: str,
    element_codes: list[str],
) -> tuple[bool, list[str], list[str], list[str], list[str]]:
    """
    Validate that element codes exist for the given category with fuzzy correction.

    Returns:
        Tuple of (is_valid, invalid_codes, valid_codes_for_category,
                  normalized_codes, corrections)
    """
    from agent.services.element_service import normalize_element_codes

    async with get_async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Element.code)
            .where(Element.category_id == uuid.UUID(category_id))
            .where(Element.is_active == True)  # noqa: E712
        )
        valid_codes = {row[0] for row in result.fetchall()}

        normalized_codes, corrections, invalid_codes = normalize_element_codes(
            element_codes, valid_codes
        )

        if corrections:
            logger.info(
                "element_codes_auto_corrected",
                corrections=corrections,
                category_id=category_id,
            )

        return (
            len(invalid_codes) == 0,
            sorted(invalid_codes),
            sorted(valid_codes),
            normalized_codes,
            corrections,
        )


async def _update_case_metadata(case_id: str, updates: dict[str, Any]) -> None:
    """Update case metadata with current step info (best-effort)."""
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
        logger.warning(
            "failed_to_update_case_metadata",
            case_id=case_id,
            updates=list(updates.keys()),
            error=str(e),
            exc_info=True,
        )


async def _transition_with_db_sync(
    fsm_state: dict[str, Any] | None = None,
    target_step: CollectionStep = CollectionStep.IDLE,
    case_id: str | None = None,
    mode_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Transition FSM to a new step and sync step to DB metadata.

    Returns a flat dict with ``expediente_sub_mode`` set to the new step value,
    ready to merge directly into mode_context / _state_update.

    Args:
        fsm_state:    Ignored (kept for backward compatibility). Use mode_context.
        target_step:  The CollectionStep to transition into.
        case_id:      Case UUID string for DB metadata sync (optional).
        mode_context: Optional dict for current step lookup (bypasses ContextVar).

    Raises:
        ValueError: If the transition from current step to target step is invalid.
    """
    current_step = get_current_step(mode_context=mode_context)
    if not can_transition_to(current_step, target_step):
        raise ValueError(
            f"Invalid FSM transition from '{current_step.value}' to '{target_step.value}'"
        )

    if case_id:
        await _update_case_metadata(case_id, {"current_step": target_step.value})

    return {"expediente_sub_mode": target_step.value}


async def _load_user_data_for_case(user_id: str | None) -> dict[str, str | None] | None:
    """
    Load existing user data from DB and map to case personal_data format.

    Returns None if user has no meaningful data or user_id is None.
    """
    if not user_id:
        return None

    try:
        async with get_async_session() as session:
            user = await session.get(User, uuid.UUID(user_id))
            if not user:
                return None

            if not any([user.first_name, user.nif_cif, user.email, user.domicilio_calle]):
                return None

            return {
                "nombre": user.first_name,
                "apellidos": user.last_name,
                "dni_cif": user.nif_cif,
                "email": user.email,
                "telefono": None,
                "domicilio_calle": user.domicilio_calle,
                "domicilio_localidad": user.domicilio_localidad,
                "domicilio_provincia": user.domicilio_provincia,
                "domicilio_cp": user.domicilio_cp,
                "itv_nombre": None,
            }
    except Exception as e:
        logger.warning(
            "failed_to_load_user_data_for_case",
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )
        return None


def _get_phase_guidance(step: CollectionStep) -> str:
    """Return LLM guidance message for a given collection step."""
    guidance_map = {
        CollectionStep.IDLE: "No hay expediente activo. Usa iniciar_expediente() para crear uno.",
        CollectionStep.COLLECT_ELEMENT_DATA: (
            "Recolectando fotos y datos por elemento. "
            "Usa confirmar_fotos_elemento() cuando el usuario envíe las fotos y diga 'listo'. "
            "Luego usa guardar_datos_elemento() para los datos técnicos. "
            "Finalmente usa completar_elemento_actual() para pasar al siguiente."
        ),
        CollectionStep.COLLECT_BASE_DOCS: (
            "Recolectando documentación base (ficha técnica, permiso). "
            "Usa confirmar_documentacion_base() cuando el usuario termine."
        ),
        CollectionStep.COLLECT_PERSONAL: "Recolectando datos personales. Usa actualizar_datos_expediente(datos_personales=...) para guardar.",
        CollectionStep.COLLECT_VEHICLE: "Recolectando datos del vehículo. Usa actualizar_datos_expediente(datos_vehiculo=...) para guardar.",
        CollectionStep.COLLECT_WORKSHOP: "Preguntando sobre taller. Usa actualizar_datos_taller() para guardar la decisión.",
        CollectionStep.REVIEW_SUMMARY: "Mostrando resumen final. Usa finalizar_expediente() cuando el usuario confirme.",
        CollectionStep.COMPLETED: "Expediente completado. No requiere más acciones.",
    }
    return guidance_map.get(step, "Paso desconocido.")


# =============================================================================
# Public service methods
# =============================================================================


async def initiate_case(
    categoria_vehiculo: str,
    codigos_elementos: list[str],
    tarifa_calculada: float | None,
    tier_id: str | None,
    conversation_id: str,
    user_id: str | None,
    client_type: str | None,
    state: dict[str, Any],
    mode_context: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Initiate case collection: validate inputs, create DB record, initialise FSM.

    Returns a result dict ready to be returned by the iniciar_expediente tool.
    """
    from agent.services.expediente_onboarding import (
        build_expediente_opening_overview,
        build_new_expediente_case_instructions,
    )
    from agent.services.case_image_batch_service import get_case_image_batch_service
    from agent.services.case_helpers import get_or_create_active_case
    from agent.services.tarifa_service import get_tarifa_service

    # Normalise slug
    categoria_vehiculo = categoria_vehiculo.lower().strip()

    # Defensive: verify state completeness (prevents NULL DB records)
    from agent.utils.tool_decorators import check_state_completeness

    required_state = ["categoria_slug", "user_id"]
    state_check = check_state_completeness(state, required_state)
    if not state_check["complete"]:
        missing = state_check["missing"]
        return tool_error_response(
            message=f"Estado incompleto: faltan {', '.join(missing)}",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="INCOMPLETE_STATE",
            guidance=(
                "No puedes iniciar un expediente sin tener el contexto completo. "
                "Verifica que se haya identificado la categoría del vehículo y el usuario."
            ),
            context={"missing_fields": missing},
        )

    # Defensive fallback: extract tariff from state if LLM didn't pass params
    if tarifa_calculada is None or tier_id is None:
        logger.warning(
            "iniciar_expediente_tariff_params_missing",
            tarifa_calculada=tarifa_calculada,
            tier_id=tier_id,
            conversation_id=conversation_id,
        )
        tarifa_data = mode_context.get("tarifa_calculada")
        if tarifa_data:
            try:
                import json

                if isinstance(tarifa_data, str):
                    tarifa_data = json.loads(tarifa_data)
                datos = tarifa_data.get("datos", {})
                if tarifa_calculada is None and datos.get("price") is not None:
                    tarifa_calculada = float(datos.get("price"))
                    logger.info("iniciar_expediente_price_extracted_from_state", price=tarifa_calculada)
                if tier_id is None and datos.get("tier_id"):
                    tier_id = datos.get("tier_id")
                    logger.info("iniciar_expediente_tier_id_extracted_from_state", tier_id=tier_id)
            except Exception as e:
                logger.error(
                    "iniciar_expediente_tariff_extraction_failed",
                    error=str(e),
                    tarifa_data_type=type(tarifa_data).__name__,
                    exc_info=True,
                )
        else:
            logger.warning(
                "iniciar_expediente_no_tarifa_in_mode_context",
                mode_context_keys=list(mode_context.keys()),
            )

    # Phase guard: only allowed from IDLE
    current_step = get_current_step()
    if current_step not in (CollectionStep.IDLE, CollectionStep.COMPLETED):
        return tool_error_response(
            message="No se puede iniciar un expediente durante una recolección activa.",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="FSM_NOT_IDLE",
            guidance=(
                f"Estás en fase '{current_step.value}'. "
                f"Completa o cancela el expediente actual antes de abrir uno nuevo."
            ),
            context={"current_step": current_step.value},
        )

    # Get category ID
    category_id = await _get_category_id_by_slug(categoria_vehiculo)
    if not category_id:
        return {
            "success": False,
            "error": f"Categoría '{categoria_vehiculo}' no encontrada",
        }

    # Validate element codes with fuzzy correction
    (
        is_valid,
        invalid_codes,
        valid_codes,
        normalized_codes,
        corrections,
    ) = await _validate_element_codes_for_category(category_id, codigos_elementos)

    if corrections:
        logger.info(
            "iniciar_expediente_codes_auto_corrected",
            corrections=corrections,
            original_codes=codigos_elementos,
            normalized_codes=normalized_codes,
            category_slug=categoria_vehiculo,
        )

    if not is_valid:
        valid_codes_display = list(valid_codes)[:30]
        if len(valid_codes) > 30:
            valid_codes_display.append(f"... (+{len(valid_codes) - 30} más)")

        logger.warning(
            "iniciar_expediente_invalid_element_codes",
            invalid_codes=invalid_codes,
            provided_codes=codigos_elementos,
            category_slug=categoria_vehiculo,
        )
        return tool_error_response(
            message=f"Códigos de elementos no válidos: {', '.join(invalid_codes)}",
            error_category=ErrorCategory.VALIDATION_ERROR,
            error_code="INVALID_ELEMENT_CODES",
            guidance=(
                f"Los códigos {invalid_codes} no existen en la categoría '{categoria_vehiculo}'.\n\n"
                f"CÓDIGOS VÁLIDOS: {', '.join(valid_codes_display)}\n\n"
                "QUÉ HACER: Debes usar identificar_y_resolver_elementos() para obtener "
                "los códigos correctos, y luego calcular_tarifa_con_elementos() antes de "
                "llamar a iniciar_expediente(). NO inventes códigos de elementos."
            ),
        )

    element_codes_to_use = normalized_codes if normalized_codes else codigos_elementos

    # Idempotent case creation
    try:
        case, created = await get_or_create_active_case(
            user_id=user_id,
            conversation_id=conversation_id,
            category_id=category_id,
            element_codes=element_codes_to_use,
            tariff_tier_id=tier_id,
            tariff_amount=tarifa_calculada,
            client_type=client_type,
        )
        case_id = case.id
    except Exception as e:
        logger.error("failed_to_create_case", error=str(e), exc_info=True)
        return {"success": False, "error": f"Error al crear el expediente: {str(e)}"}

    # Handle existing active case (particular user already has one)
    if not created:
        status_desc = {
            "collecting": "en proceso de recolección de datos",
            "pending_images": "pendiente de imágenes",
        }.get(case.status, case.status)
        created_at_str = (
            case.created_at.strftime("%d/%m/%Y a las %H:%M") if case.created_at else "fecha desconocida"
        )
        return tool_error_response(
            message="El usuario ya tiene un expediente activo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="PARTICULAR_CASE_ALREADY_ACTIVE",
            guidance=(
                f"El usuario ya tiene un expediente activo "
                f"(ID: {case.id}, estado: {status_desc}, "
                f"creado el {created_at_str}). "
                f"Los particulares solo pueden tener UN expediente activo a la vez. "
                f"Informa al usuario y ofrécele DOS opciones:\n"
                f"1. Retomar el expediente activo (continuar donde lo dejó)\n"
                f"2. Cancelar el expediente actual (usando cancelar_expediente()) "
                f"y luego abrir uno nuevo.\n"
                f"NO intentes crear el nuevo expediente hasta que el actual esté "
                f"cancelado o completado."
            ),
            context={
                "active_case_id": str(case.id),
                "active_case_status": case.status,
                "active_case_created_at": created_at_str,
                "client_type": client_type or "unknown",
            },
        )

    logger.info(
        "case_created",
        case_id=str(case_id),
        conversation_id=conversation_id,
        elements=element_codes_to_use,
        original_codes=codigos_elementos if corrections else None,
    )

    # Fetch base doc descriptions for this category
    tarifa_service = get_tarifa_service()
    category_data = await tarifa_service.get_category_data(categoria_vehiculo)
    base_doc_descriptions: list[str] = []
    if category_data and category_data.get("base_documentation"):
        base_doc_descriptions = [bd["description"] for bd in category_data["base_documentation"]]

    # Build initial case state fields for mode_context
    first_element = element_codes_to_use[0] if element_codes_to_use else None

    imperative_message = build_new_expediente_case_instructions(
        first_element_display=first_element or "elemento",
        total_elements=len(element_codes_to_use),
        intro_already_sent=True,
        auto_created=False,
    )

    if first_element:
        await get_case_image_batch_service().open_for_scope(
            case_id=str(case_id),
            expediente_sub_mode="collect_element_data",
            element_code=first_element,
            opened_at=datetime.now(UTC),
        )

    return {
        "success": True,
        "case_id": str(case_id),
        "first_element": first_element,
        "total_elements": len(element_codes_to_use),
        "message": imperative_message,
        "expediente_intro_message": build_expediente_opening_overview(),
        "expediente_intro_sent": False,
        "next_step": CollectionStep.COLLECT_ELEMENT_DATA.value,
        "_state_update": {
            "intro_already_sent": True,
            "expediente_intro_sent": False,
            # Flat state updates for mode_context (T-26 refactor — flat _state_update)
            "expediente_sub_mode": CollectionStep.COLLECT_ELEMENT_DATA.value,
            "case_id": str(case_id),
            "category_slug": categoria_vehiculo,
            "category_id": category_id,
            "element_codes": element_codes_to_use,
            "current_element_index": 0,
            "element_phase": "photos",
            "element_data_status": {code: ELEMENT_STATUS_PENDING for code in element_codes_to_use},
            "base_docs_received": False,
            "base_doc_descriptions": base_doc_descriptions,
            "received_images": [],
            "tariff_tier_id": tier_id,
            "tariff_amount": tarifa_calculada,
            "taller_propio": None,
            "taller_data": None,
        },
    }


async def get_case_status(
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return the current status of the active expediente.

    Performs an authoritative DB read with fallback to mode_context.
    """
    if not is_collection_active():
        return {
            "success": True,
            "has_active_case": False,
            "message": "No hay expediente activo en este momento.",
        }

    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    db_case: Case | None = None
    if case_id:
        try:
            from sqlalchemy import select as sa_select
            from sqlalchemy.orm import selectinload

            async with get_async_session() as session:
                result = await session.execute(
                    sa_select(Case)
                    .where(Case.id == uuid.UUID(str(case_id)))
                    .options(
                        selectinload(Case.images),
                        selectinload(Case.element_data),
                        selectinload(Case.user),
                    )
                )
                db_case = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning(
                "obtener_estado_expediente_db_fallback",
                case_id=str(case_id),
                error=str(exc),
                msg="DB query failed — falling back to stale mode_context",
            )

    if db_case is not None:
        images_received = len(db_case.images)
        element_codes: list[str] = list(db_case.element_codes or [])
        element_data_status: dict[str, str] = {
            ced.element_code: ced.status for ced in db_case.element_data
        }
        taller_propio = db_case.taller_propio
        taller_nombre = db_case.taller_nombre
        tariff_amount_raw = float(db_case.tariff_amount) if db_case.tariff_amount is not None else None

        user = db_case.user
        itv_complete = bool(db_case.itv_nombre)
        if user is not None:
            personal_data_complete = all([
                user.first_name, user.last_name, user.email, user.nif_cif,
                user.domicilio_calle, user.domicilio_localidad,
                user.domicilio_provincia, user.domicilio_cp,
                itv_complete,
            ])
        else:
            personal_data = case_fsm_state.get("personal_data", {})
            personal_data_complete = all(
                personal_data.get(k)
                for k in ["nombre", "apellidos", "email", "dni_cif",
                          "domicilio_calle", "domicilio_localidad",
                          "domicilio_provincia", "domicilio_cp", "itv_nombre"]
            )

        vehicle_data_complete = all([
            db_case.vehiculo_marca, db_case.vehiculo_modelo,
            db_case.vehiculo_anio, db_case.vehiculo_matricula,
            db_case.vehiculo_bastidor,
        ])

        if taller_propio is False:
            taller_data_complete = True
        elif taller_propio is True:
            taller_data_complete = bool(taller_nombre)
        else:
            taller_data_complete = False

        case_status = db_case.status
        if case_status in ("resolved", "cancelled", "abandoned"):
            current_step: CollectionStep = CollectionStep.COMPLETED
        elif case_status in ("pending_review", "in_progress"):
            current_step = CollectionStep.REVIEW_SUMMARY
        elif taller_propio is None and vehicle_data_complete and personal_data_complete:
            current_step = CollectionStep.COLLECT_WORKSHOP
        elif not vehicle_data_complete and personal_data_complete:
            current_step = CollectionStep.COLLECT_VEHICLE
        elif not personal_data_complete and (vehicle_data_complete or not element_codes):
            current_step = CollectionStep.COLLECT_PERSONAL
        elif element_codes:
            all_elements_done = all(
                element_data_status.get(code, ELEMENT_STATUS_PENDING) == "completed"
                for code in element_codes
            )
            current_step = CollectionStep.COLLECT_ELEMENT_DATA if not all_elements_done else CollectionStep.COLLECT_BASE_DOCS
        else:
            current_step = get_current_step()

        data_source = "db"
    else:
        logger.warning(
            "obtener_estado_expediente_mode_context_fallback",
            case_id=str(case_id) if case_id else None,
            msg="Using stale mode_context as fallback (DB case not found)",
        )
        personal_data = case_fsm_state.get("personal_data", {})
        vehicle_data = case_fsm_state.get("vehicle_data", {})
        images_received = len(case_fsm_state.get("received_images", []))
        element_codes = case_fsm_state.get("element_codes", [])
        element_data_status = case_fsm_state.get("element_data_status", {})
        taller_propio = case_fsm_state.get("taller_propio")
        tariff_amount_raw = case_fsm_state.get("tariff_amount")
        personal_data_complete = all(
            personal_data.get(k)
            for k in ["nombre", "apellidos", "email", "dni_cif",
                      "domicilio_calle", "domicilio_localidad",
                      "domicilio_provincia", "domicilio_cp", "itv_nombre"]
        )
        vehicle_data_complete = all(
            vehicle_data.get(k) for k in ["marca", "modelo", "matricula", "anio", "bastidor"]
        )
        taller_data_complete = taller_propio is False or bool(case_fsm_state.get("taller_data"))
        current_step = get_current_step()
        data_source = "fallback"

    # Build per-element status list
    element_status = []
    for code in element_codes:
        raw_status = element_data_status.get(code, ELEMENT_STATUS_PENDING)
        if raw_status == "completed":
            status = "completed"
        elif raw_status == "pending_data":
            status = "pending_data"
        else:
            status = "pending_photos"
        element_status.append({"code": code, "status": status})

    # Compute precio_total
    try:
        if taller_propio is False and tariff_amount_raw is not None:
            precio_certificado: float | None = CERT_SUPPLEMENT_EUR
            precio_total: float | None = float(tariff_amount_raw) + CERT_SUPPLEMENT_EUR
        elif taller_propio is True and tariff_amount_raw is not None:
            precio_certificado = 0
            precio_total = float(tariff_amount_raw)
        else:
            precio_certificado = None
            precio_total = None
    except (TypeError, ValueError):
        precio_certificado = None
        precio_total = None
        logger.warning("precio_total_calculo_fallback", tariff_amount=tariff_amount_raw)

    current_step_value = current_step.value if isinstance(current_step, CollectionStep) else str(current_step)

    return {
        "success": True,
        "has_active_case": True,
        "case_id": str(case_id) if case_id else case_fsm_state.get("case_id"),
        "current_step": current_step_value,
        "personal_data_complete": personal_data_complete,
        "vehicle_data_complete": vehicle_data_complete,
        "taller_propio": taller_propio,
        "taller_data_complete": taller_data_complete,
        "images_received": images_received,
        "elements": element_codes,
        "element_status": element_status,
        "tariff_amount": tariff_amount_raw,
        "precio_certificado": precio_certificado,
        "precio_total": precio_total,
        "data_source": data_source,
    }


async def update_personal_data(
    datos_personales: dict[str, str] | None,
    datos_vehiculo: dict[str, str] | None,
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Save personal and/or vehicle data to DB and advance FSM.

    Returns a result dict ready to be returned by actualizar_datos_expediente.
    """
    # Format validation
    if datos_personales and datos_personales.get("email"):
        from agent.utils.tool_decorators import validate_email

        is_valid, error_msg = validate_email(datos_personales["email"])
        if not is_valid:
            return tool_error_response(
                message=f"Email inválido: {error_msg}",
                error_category=ErrorCategory.VALIDATION_ERROR,
                error_code="INVALID_EMAIL",
                guidance="Pide al usuario que proporcione un email válido con formato correcto (ej: usuario@dominio.com)",
                context={"email": datos_personales["email"]},
            )

    if datos_personales and datos_personales.get("dni_cif"):
        from agent.utils.tool_decorators import validate_dni

        is_valid, error_msg = validate_dni(datos_personales["dni_cif"])
        if not is_valid:
            return tool_error_response(
                message=f"DNI/NIE/CIF inválido: {error_msg}",
                error_category=ErrorCategory.VALIDATION_ERROR,
                error_code="INVALID_DNI",
                guidance="Pide al usuario que proporcione un DNI, NIE o CIF válido.",
                context={"dni_cif": datos_personales["dni_cif"]},
            )

    if datos_personales is None and datos_vehiculo is None:
        return tool_error_response(
            message="No se recibieron datos para guardar. "
            "Usa datos_personales={...} para datos del titular "
            "o datos_vehiculo={...} para datos del vehículo.",
            error_category=ErrorCategory.VALIDATION_ERROR,
            error_code="NO_DATA_PROVIDED",
            guidance=(
                "Llama a la herramienta con datos_personales={nombre: '...', apellidos: '...', ...} "
                "o datos_vehiculo={marca: '...', modelo: '...', ...}. "
                "NO uses los parámetros 'seccion' ni 'datos' — no existen."
            ),
        )

    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    if not case_id:
        return tool_error_response(
            message="No hay expediente activo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_ACTIVE_CASE",
            guidance="Usa iniciar_expediente() primero para crear un expediente.",
        )

    current_step = get_current_step()
    allowed_phases = [CollectionStep.COLLECT_PERSONAL, CollectionStep.COLLECT_VEHICLE]
    if current_step not in allowed_phases:
        return tool_error_response(
            message="Esta herramienta solo funciona durante la recolección de datos personales o del vehículo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="WRONG_PHASE",
            guidance=_get_phase_guidance(current_step),
            context={"current_step": current_step.value},
        )

    updates_for_case: dict[str, Any] = {}
    updates_for_user: dict[str, Any] = {}
    updates_for_fsm: dict[str, Any] = {}

    if datos_personales:
        existing_personal = case_fsm_state.get("personal_data", {})
        merged_personal = {**existing_personal}

        personal_fields = [
            "nombre", "apellidos", "email", "dni_cif",
            "domicilio_calle", "domicilio_localidad", "domicilio_provincia",
            "domicilio_cp", "itv_nombre",
        ]

        incoming_personal = {
            k: v.strip()
            for k, v in datos_personales.items()
            if k in personal_fields and v
        }
        is_idempotent = all(
            existing_personal.get(key) == value
            for key, value in incoming_personal.items()
        )

        if is_idempotent and incoming_personal:
            full_existing_personal = case_fsm_state.get("personal_data", {})
            is_complete, _ = validate_personal_data(full_existing_personal)

            if is_complete and current_step == CollectionStep.COLLECT_PERSONAL:
                transition = await _transition_with_db_sync(
                    target_step=CollectionStep.COLLECT_VEHICLE,
                    case_id=case_id,
                )
                next_step_val = CollectionStep.COLLECT_VEHICLE.value
            else:
                transition = {}
                next_step_val = current_step.value

            logger.info(
                "actualizar_datos_personales_idempotent",
                case_id=case_id,
                fields=list(incoming_personal.keys()),
                is_complete=is_complete,
                next_step=next_step_val,
            )
            return {
                "success": True,
                "already_saved": True,
                "message": "Estos datos personales ya están guardados. Continuamos.",
                "next_step": next_step_val,
                "_state_update": transition,
            }

        for key in personal_fields:
            if key in datos_personales and datos_personales[key]:
                merged_personal[key] = datos_personales[key].strip()

        unknown_personal = set(datos_personales.keys()) - set(personal_fields)
        if unknown_personal:
            logger.warning(
                "actualizar_datos_expediente_unknown_personal_fields",
                unknown_fields=list(unknown_personal),
                valid_fields=personal_fields,
                received_fields=list(datos_personales.keys()),
            )

        updates_for_fsm["personal_data"] = merged_personal

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
        if merged_personal.get("itv_nombre"):
            updates_for_case["itv_nombre"] = merged_personal["itv_nombre"]

    if datos_vehiculo:
        # Pre-populate marca/modelo from presupuesto context (REQ-07)
        vehiculo_from_presupuesto = (state.get("mode_context") or {}).get("vehiculo") or {}
        if isinstance(vehiculo_from_presupuesto, dict):
            for field in ("marca", "modelo"):
                if not datos_vehiculo.get(field) and vehiculo_from_presupuesto.get(field):
                    datos_vehiculo = dict(datos_vehiculo)
                    datos_vehiculo[field] = vehiculo_from_presupuesto[field]
                    logger.info(
                        "actualizar_datos_expediente_pre_populated_from_presupuesto",
                        field=field,
                        value=vehiculo_from_presupuesto[field],
                        case_id=case_id,
                    )

        existing_vehicle = case_fsm_state.get("vehicle_data", {})
        merged_vehicle = {**existing_vehicle}
        vehicle_fields = ["marca", "modelo", "anio", "matricula", "bastidor"]

        incoming_vehicle: dict[str, str] = {}
        for key in vehicle_fields:
            if key in datos_vehiculo and datos_vehiculo[key]:
                value = datos_vehiculo[key].strip()
                if key == "matricula":
                    value = normalize_matricula(value)
                incoming_vehicle[key] = value

        is_idempotent = all(
            existing_vehicle.get(key) == value
            for key, value in incoming_vehicle.items()
        )

        if is_idempotent and incoming_vehicle:
            full_existing_vehicle = case_fsm_state.get("vehicle_data", {})
            is_complete, _ = validate_vehicle_data(full_existing_vehicle)

            if is_complete and current_step == CollectionStep.COLLECT_VEHICLE:
                transition = await _transition_with_db_sync(
                    target_step=CollectionStep.COLLECT_WORKSHOP,
                    case_id=case_id,
                )
                next_step_val = CollectionStep.COLLECT_WORKSHOP.value
            else:
                transition = {}
                next_step_val = current_step.value

            logger.info(
                "actualizar_datos_vehiculo_idempotent",
                case_id=case_id,
                fields=list(incoming_vehicle.keys()),
                is_complete=is_complete,
                next_step=next_step_val,
            )
            return {
                "success": True,
                "already_saved": True,
                "message": "Estos datos del vehículo ya están guardados. Continuamos.",
                "next_step": next_step_val,
                "_state_update": transition,
            }

        for key in vehicle_fields:
            if key in datos_vehiculo and datos_vehiculo[key]:
                value = datos_vehiculo[key].strip()
                if key == "matricula":
                    value = normalize_matricula(value)
                merged_vehicle[key] = value

        unknown_vehicle = set(datos_vehiculo.keys()) - set(vehicle_fields)
        if unknown_vehicle:
            logger.warning(
                "actualizar_datos_expediente_unknown_vehicle_fields",
                unknown_fields=list(unknown_vehicle),
                valid_fields=vehicle_fields,
                received_fields=list(datos_vehiculo.keys()),
            )

        updates_for_fsm["vehicle_data"] = merged_vehicle

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

    # DB update
    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if not case:
                return {"success": False, "error": "No se encontro el expediente"}

            if updates_for_user and case.user_id:
                user = await session.get(User, case.user_id)
                if user:
                    for key, value in updates_for_user.items():
                        setattr(user, key, value)
                    user.updated_at = datetime.now(UTC)
                    logger.info("user_updated", user_id=str(case.user_id), updates=list(updates_for_user.keys()))

            if updates_for_case:
                for key, value in updates_for_case.items():
                    setattr(case, key, value)
                case.updated_at = datetime.now(UTC)
                logger.info("case_updated", case_id=case_id, updates=list(updates_for_case.keys()))

            await session.commit()

            if updates_for_user and case.user_id:
                try:
                    from shared.chatwoot_sync import sync_user_to_chatwoot

                    user = await session.get(User, case.user_id)
                    if user:
                        await sync_user_to_chatwoot(user)
                except Exception as sync_error:
                    logger.warning(
                        "failed_to_sync_user_to_chatwoot",
                        user_id=str(case.user_id),
                        error=str(sync_error),
                        exc_info=True,
                    )
    except Exception as e:
        logger.error(
            "failed_to_update_case_user",
            case_id=case_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        return {"success": False, "error": f"Error al actualizar: {str(e)}"}

    next_step = current_step
    message = ""
    missing: list[str] = []
    transition: dict[str, Any] = {}

    if current_step == CollectionStep.COLLECT_PERSONAL:
        personal_data = updates_for_fsm.get("personal_data", case_fsm_state.get("personal_data", {}))
        is_valid, missing = validate_personal_data(personal_data)
        if is_valid:
            transition = await _transition_with_db_sync(
                target_step=CollectionStep.COLLECT_VEHICLE,
                case_id=case_id,
            )
            next_step = CollectionStep.COLLECT_VEHICLE
            message = "Datos personales guardados correctamente."
        else:
            message = f"Faltan los siguientes datos personales: {', '.join(missing)}. Por favor, proporciónalos."

    elif current_step == CollectionStep.COLLECT_VEHICLE:
        vehicle_data = updates_for_fsm.get("vehicle_data", case_fsm_state.get("vehicle_data", {}))
        is_valid, missing = validate_vehicle_data(vehicle_data)
        if is_valid:
            transition = await _transition_with_db_sync(
                target_step=CollectionStep.COLLECT_WORKSHOP,
                case_id=case_id,
            )
            next_step = CollectionStep.COLLECT_WORKSHOP
            message = "Datos del vehículo guardados correctamente."
        else:
            message = f"Faltan los siguientes datos del vehiculo: {', '.join(missing)}. Por favor, proporciónalos."

    return {
        "success": True,
        "message": message,
        "next_step": next_step.value if isinstance(next_step, CollectionStep) else next_step,
        "missing_fields": missing,
        "_state_update": {
            "datos_updated": True,
            "confirmed_fields": list(
                updates_for_fsm.get("personal_data", updates_for_fsm.get("vehicle_data", {}))
            ),
            "can_narrate_completion": len(missing) == 0,
            # Flat mode_context updates (T-26 refactor — flat _state_update)
            **updates_for_fsm,
            **transition,
        },
    }


async def update_workshop_data(
    taller_propio: bool | None,
    datos_taller: dict[str, str] | None,
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save workshop decision and data to DB, advance FSM to REVIEW_SUMMARY when complete."""
    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    if not case_id:
        return tool_error_response(
            message="No hay expediente activo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_ACTIVE_CASE",
            guidance="Usa iniciar_expediente() primero para crear un expediente.",
        )

    current_step = get_current_step()
    if current_step != CollectionStep.COLLECT_WORKSHOP:
        return tool_error_response(
            message="Esta herramienta solo funciona en la fase de recolección de taller",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="WRONG_PHASE",
            guidance=f"Estás en '{current_step.value}'. Completa primero esa fase antes de pedir datos del taller.",
            context={"current_step": current_step.value},
        )

    updates_for_db: dict[str, Any] = {}
    updates_for_fsm: dict[str, Any] = {}

    if taller_propio is not None:
        existing_taller_propio = case_fsm_state.get("taller_propio")
        if existing_taller_propio == taller_propio:
            if not datos_taller:
                if existing_taller_propio is False:
                    next_step = CollectionStep.REVIEW_SUMMARY.value
                    can_narrate_completion = True
                elif existing_taller_propio is True:
                    taller_data = case_fsm_state.get("taller_data")
                    is_valid, _ = validate_workshop_data(taller_data)
                    next_step = CollectionStep.REVIEW_SUMMARY.value if is_valid else CollectionStep.COLLECT_WORKSHOP.value
                    can_narrate_completion = is_valid
                else:
                    next_step = CollectionStep.COLLECT_WORKSHOP.value
                    can_narrate_completion = False

                return {
                    "success": True,
                    "already_saved": True,
                    "message": "Esta decisión sobre el taller ya está guardada. Continuamos.",
                    "next_step": next_step,
                    "_state_update": {
                        "taller_updated": True,
                        "can_narrate_completion": can_narrate_completion,
                    },
                }

        updates_for_fsm["taller_propio"] = taller_propio
        updates_for_db["taller_propio"] = taller_propio

    if datos_taller:
        # Normalise alternative field names
        field_mappings = {
            "direccion": "domicilio", "address": "domicilio",
            "numero_registro": "registro_industrial", "registro": "registro_industrial",
            "nif": "registro_industrial", "cif": "registro_industrial",
            "encargado": "responsable", "contacto": "responsable",
            "tlf": "telefono", "tel": "telefono", "phone": "telefono",
        }
        for alt_name, correct_name in field_mappings.items():
            if alt_name in datos_taller and correct_name not in datos_taller:
                datos_taller[correct_name] = datos_taller.pop(alt_name)

        existing_taller = case_fsm_state.get("taller_data") or {}
        merged_taller = {**existing_taller}

        taller_fields = [
            "nombre", "responsable", "domicilio", "provincia", "ciudad",
            "telefono", "registro_industrial", "actividad",
        ]
        for key in taller_fields:
            if key in datos_taller and datos_taller[key]:
                merged_taller[key] = datos_taller[key].strip()

        unknown_taller = set(datos_taller.keys()) - set(taller_fields)
        if unknown_taller:
            logger.warning(
                "actualizar_datos_taller_unknown_fields",
                unknown_fields=list(unknown_taller),
                valid_fields=taller_fields,
                received_fields=list(datos_taller.keys()),
            )

        updates_for_fsm["taller_data"] = merged_taller

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

    if updates_for_db:
        try:
            async with get_async_session() as session:
                case = await session.get(Case, uuid.UUID(case_id))
                if case:
                    for key, value in updates_for_db.items():
                        setattr(case, key, value)
                    case.updated_at = datetime.now(UTC)
                    await session.commit()
                    logger.info("case_taller_data_updated", case_id=case_id, updates=list(updates_for_db.keys()))
        except Exception as e:
            logger.error(
                "failed_to_update_case_taller_data",
                case_id=case_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return {"success": False, "error": f"Error al actualizar: {str(e)}"}

    current_taller_propio = updates_for_fsm.get("taller_propio", case_fsm_state.get("taller_propio"))

    if current_taller_propio is False:
        transition = await _transition_with_db_sync(
            target_step=CollectionStep.REVIEW_SUMMARY,
            case_id=case_id,
        )
        return {
            "success": True,
            "message": "Perfecto, MSI gestionará el certificado del taller.",
            "next_step": CollectionStep.REVIEW_SUMMARY.value,
            "_state_update": {
                "taller_updated": True,
                "can_narrate_completion": True,
                **updates_for_fsm,
                **transition,
            },
        }

    if current_taller_propio is True:
        taller_data = updates_for_fsm.get("taller_data", case_fsm_state.get("taller_data"))
        is_valid, missing = validate_workshop_data(taller_data)
        if is_valid:
            transition = await _transition_with_db_sync(
                target_step=CollectionStep.REVIEW_SUMMARY,
                case_id=case_id,
            )
            return {
                "success": True,
                "message": "Datos del taller guardados correctamente.",
                "next_step": CollectionStep.REVIEW_SUMMARY.value,
                "_state_update": {
                    "taller_updated": True,
                    "can_narrate_completion": True,
                    **updates_for_fsm,
                    **transition,
                },
            }
        else:
            return {
                "success": True,
                "message": f"Faltan los siguientes datos del taller: {', '.join(missing)}. Por favor, proporcionaos.",
                "next_step": CollectionStep.COLLECT_WORKSHOP.value,
                "missing_fields": missing,
                "_state_update": {
                    "taller_updated": True,
                    "can_narrate_completion": False,
                    **updates_for_fsm,
                },
            }

    # taller_propio still None — still need to ask
    return {
        "success": True,
        "message": STEP_PROMPTS.get(CollectionStep.COLLECT_WORKSHOP, ""),
        "next_step": CollectionStep.COLLECT_WORKSHOP.value,
        "_state_update": {
            "taller_updated": False,
            "can_narrate_completion": False,
            **updates_for_fsm,
        },
    }


async def handle_query_during_case(
    consulta: str | None,
    accion: str,
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Handle user queries and actions during an active expediente.

    Supports responder, cancelar, pausar, reanudar actions.
    """
    case_fsm_state = get_mode_context()
    current_step = get_current_step()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    accion = accion.lower().strip() if accion else "responder"
    valid_actions = ["responder", "cancelar", "pausar", "reanudar"]
    if accion not in valid_actions:
        accion = "responder"

    if accion == "cancelar":
        if case_id:
            return await cancel_case(
                motivo=consulta or "Cancelado por el usuario",
                state=state,
            )
        return {
            "success": True,
            "message": "No hay expediente activo que cancelar. Puedes ayudar al usuario con cualquier consulta.",
        }

    if not is_collection_active():
        return {
            "success": True,
            "has_active_case": False,
            "message": (
                "No hay expediente activo en este momento. "
                "Puedes responder la consulta del usuario libremente y ofrecerle "
                "ayuda con presupuestos o abrir un nuevo expediente."
            ),
        }

    step_descriptions = {
        CollectionStep.COLLECT_ELEMENT_DATA: "recolección de fotos y datos por elemento",
        CollectionStep.COLLECT_BASE_DOCS: "documentación base del vehículo",
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
        prompt = STEP_PROMPTS.get(current_step, "")
        return {
            "success": True,
            "message": f"Continuemos con el expediente. Estabas en el paso de {step_desc}.\n\n{prompt}",
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


async def cancel_case(
    motivo: str,
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cancel the active expediente and reset FSM state."""
    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    if not case_id:
        return tool_error_response(
            message="No hay expediente activo que cancelar",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_ACTIVE_CASE",
            guidance="No hay ningún expediente en curso. Puedes ayudar al usuario con consultas o crear uno nuevo con iniciar_expediente().",
        )

    try:
        async with get_async_session() as session:
            case = await session.get(Case, uuid.UUID(case_id))
            if case:
                if case.status == "cancelled":
                    logger.info("case_already_cancelled_idempotent", case_id=case_id)
                    return {
                        "success": True,
                        "already_cancelled": True,
                        "message": "El expediente ya fue cancelado anteriormente. Si necesitas ayuda con algo más, no dudes en preguntar.",
                        "_state_update": {
                            "expediente_sub_mode": CollectionStep.IDLE.value,
                            "expediente_cancelled": True,
                        },
                    }

                case.status = "cancelled"
                case.updated_at = datetime.now(UTC)
                case.notes = (case.notes or "") + f"\nCancelado: {motivo}"
                await session.commit()
                logger.info("case_cancelled", case_id=case_id, reason=motivo)

    except Exception as e:
        logger.error("failed_to_cancel_case", error=str(e), exc_info=True)
        return {"success": False, "error": f"Error al cancelar: {str(e)}"}

    return {
        "success": True,
        "message": "El expediente ha sido cancelado. Si necesitas ayuda con algo más, no dudes en preguntar.",
        "_state_update": {
            "expediente_sub_mode": CollectionStep.IDLE.value,
            "expediente_cancelled": True,
        },
    }


async def edit_case(
    seccion: str,
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Allow user to go back and edit a section from REVIEW_SUMMARY."""
    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    if not case_id:
        return tool_error_response(
            message="No hay expediente activo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_ACTIVE_CASE",
            guidance="No hay expediente en curso. Si el usuario quiere abrir uno, usa iniciar_expediente().",
        )

    current_step = get_current_step()

    if current_step != CollectionStep.REVIEW_SUMMARY:
        return tool_error_response(
            message="Solo puedes editar desde la revisión del resumen",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="WRONG_PHASE",
            guidance=(
                f"Esta herramienta solo funciona en la fase de revisión (review_summary). "
                f"Estás en '{current_step.value}'. Completa primero la recolección de datos."
            ),
            context={"current_step": current_step.value},
        )

    seccion_lower = seccion.lower().strip()

    RESTRICTED_SECTIONS = [
        "elemento", "elementos", "fotos", "datos_elementos", "element",
        "element_data", "foto", "imagenes", "datos_elemento", "campos",
    ]
    if any(term in seccion_lower for term in RESTRICTED_SECTIONS):
        return {
            "success": False,
            "error": "NO_PUEDE_EDITAR_ELEMENTOS",
            "message": (
                "No puedes volver a editar fotos o datos de elementos. "
                "Los elementos completados son inmutables.\n\n"
                "Solo puedes editar:\n"
                "• Datos personales (nombre, DNI, email, dirección, ITV)\n"
                "• Datos del vehículo (marca, modelo, matrícula, año, bastidor)\n"
                "• Datos del taller (nombre, responsable, dirección, etc.)\n"
                "• Documentación base (ficha técnica, permiso de circulación)\n\n"
                "Si necesitas cambiar datos de elementos, deberás cancelar este expediente "
                "y crear uno nuevo con iniciar_expediente()."
            ),
            "available_sections": ["personal", "vehiculo", "taller", "documentacion"],
            "tool_name": "editar_expediente",
        }

    section_mapping = {
        "personal": CollectionStep.COLLECT_PERSONAL,
        "datos_personales": CollectionStep.COLLECT_PERSONAL,
        "personales": CollectionStep.COLLECT_PERSONAL,
        "vehiculo": CollectionStep.COLLECT_VEHICLE,
        "vehículo": CollectionStep.COLLECT_VEHICLE,
        "datos_vehiculo": CollectionStep.COLLECT_VEHICLE,
        "coche": CollectionStep.COLLECT_VEHICLE,
        "moto": CollectionStep.COLLECT_VEHICLE,
        "taller": CollectionStep.COLLECT_WORKSHOP,
        "workshop": CollectionStep.COLLECT_WORKSHOP,
        "documentacion": CollectionStep.COLLECT_BASE_DOCS,
        "documentación": CollectionStep.COLLECT_BASE_DOCS,
        "docs": CollectionStep.COLLECT_BASE_DOCS,
        "base_docs": CollectionStep.COLLECT_BASE_DOCS,
        "ficha": CollectionStep.COLLECT_BASE_DOCS,
        "permiso": CollectionStep.COLLECT_BASE_DOCS,
    }

    target_step = section_mapping.get(seccion_lower)

    if not target_step:
        return tool_error_response(
            message=f"Sección '{seccion}' no reconocida",
            error_category=ErrorCategory.VALIDATION_ERROR,
            error_code="INVALID_SECTION",
            guidance=(
                "Secciones válidas para editar:\n"
                "- 'personal': datos personales (nombre, DNI, email, dirección)\n"
                "- 'vehiculo': datos del vehículo (marca, modelo, matrícula)\n"
                "- 'taller': datos del taller\n"
                "- 'documentacion': documentación base (ficha técnica, permiso)\n\n"
                "NOTA: No se puede volver a editar las fotos y datos de los elementos."
            ),
            context={"current_step": current_step.value},
        )

    try:
        transition = await _transition_with_db_sync(
            target_step=target_step,
            case_id=case_id,
        )
    except ValueError as e:
        logger.error("invalid_transition_in_editar_expediente", error=str(e))
        return tool_error_response(
            message=f"Transición no válida a '{target_step.value}'",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="INVALID_TRANSITION",
            guidance=_get_phase_guidance(current_step),
            context={"current_step": current_step.value},
        )

    prompt = STEP_PROMPTS.get(target_step, "")
    section_names = {
        CollectionStep.COLLECT_PERSONAL: "datos personales",
        CollectionStep.COLLECT_VEHICLE: "datos del vehículo",
        CollectionStep.COLLECT_WORKSHOP: "datos del taller",
        CollectionStep.COLLECT_BASE_DOCS: "documentación base",
    }
    section_name = section_names.get(target_step, target_step.value)

    logger.info(
        "user_editing_section",
        section_name=section_name,
        case_id=case_id,
        from_step=current_step.value,
        to_step=target_step.value,
        section=seccion,
    )

    return {
        "success": True,
        "message": (
            f"Perfecto, vamos a editar los {section_name}.\n\n"
            f"{prompt}\n\n"
            f"Cuando termines, volveremos al resumen para que puedas confirmar."
        ),
        "next_step": target_step.value,
        "editing_section": section_name,
        "_state_update": {
            "expediente_edited": True,
            "edit_target_sub_mode": target_step.value,
            "can_narrate_completion": False,
            **transition,
        },
    }


async def finalize_case(
    state: dict[str, Any],
    fsm_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Mark case as pending_review, notify Chatwoot, and reset FSM.

    Idempotent: safe to call twice on the same case.
    """
    conversation_id = state.get("conversation_id")
    case_fsm_state = get_mode_context()
    case_id = _get_case_id_with_fallback(state, case_fsm_state)

    if not case_id:
        return tool_error_response(
            message="No hay expediente activo",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="NO_ACTIVE_CASE",
            guidance="Usa iniciar_expediente() primero para crear un expediente.",
        )

    current_step = get_current_step()
    if current_step != CollectionStep.REVIEW_SUMMARY:
        step_order = [
            "collect_element_data", "collect_personal", "collect_vehicle",
            "collect_workshop", "review_summary",
        ]
        current_idx = step_order.index(current_step.value) if current_step.value in step_order else -1
        remaining_steps = step_order[current_idx + 1:] if current_idx >= 0 else step_order

        return tool_error_response(
            message="No puedes finalizar el expediente todavía",
            error_category=ErrorCategory.FSM_STATE_ERROR,
            error_code="WRONG_PHASE",
            guidance=(
                f"Debes completar estos pasos primero: {', '.join(remaining_steps)}. "
                f"Usa las herramientas: actualizar_datos_expediente(), actualizar_datos_taller(). "
                f"NO digas al usuario que el expediente está completado."
            ),
            context={"current_step": current_step.value},
        )

    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async with get_async_session() as session:
            _result = await session.execute(
                select(Case)
                .where(Case.id == uuid.UUID(case_id))
                .options(selectinload(Case.category))
            )
            case = _result.scalar_one_or_none()
            if case is None:
                return tool_error_response(
                    message=f"No se encontró el expediente {case_id}",
                    error_category=ErrorCategory.DATABASE_ERROR,
                    error_code="CASE_NOT_FOUND",
                    guidance="El expediente no existe en la base de datos.",
                )

            # Idempotency
            if case.status == "pending_review":
                logger.info("case_already_finalized_idempotent", case_id=case_id, conversation_id=conversation_id)
                return {
                    "success": True,
                    "already_finalized": True,
                    "message": (
                        "Tu expediente ya fue enviado para revisión.\n\n"
                        "Un agente de MSI Automotive lo revisará y se pondrá en contacto "
                        "contigo a la mayor brevedad posible.\n\n"
                        "Mientras tanto, si tienes alguna otra consulta, estaré encantado de ayudarte."
                    ),
                    "case_id": case_id,
                    "next_step": CollectionStep.COMPLETED.value,
                    "_state_update": {
                        "case_finalized": True,
                        "can_narrate_completion": True,
                        "expediente_sub_mode": CollectionStep.COMPLETED.value,
                        "expediente_completed": True,
                    },
                }

            case.status = "pending_review"
            case.completed_at = datetime.now(UTC)
            case.updated_at = datetime.now(UTC)

            metadata = case.metadata_ or {}
            metadata["current_step"] = CollectionStep.COMPLETED.value
            metadata["completed_at"] = datetime.now(UTC).isoformat()
            case.metadata_ = metadata

            await session.commit()

            logger.info("case_finalized_pending_review", case_id=case_id, conversation_id=conversation_id)

            # Notify Chatwoot (best-effort)
            try:
                from shared.chatwoot_client import ChatwootClient
                from shared.config import get_settings

                settings = get_settings()
                chatwoot = ChatwootClient()
                conv_id = int(conversation_id)

                element_codes = case.element_codes or []
                categoria_slug = case.category.slug if case.category else "N/A"
                element_summary = ", ".join(element_codes) if element_codes else "N/A"

                taller_propio_fin = case.taller_propio
                tarifa_raw = case.tariff_amount
                try:
                    if taller_propio_fin is False and tarifa_raw is not None:
                        tarifa_float = float(tarifa_raw)
                        precio_display = f"{tarifa_float:.2f}€ + {CERT_SUPPLEMENT_EUR}€ (certificado MSI) + IVA = {tarifa_float + CERT_SUPPLEMENT_EUR:.2f}€ total + IVA"
                    elif tarifa_raw is not None:
                        precio_display = f"{float(tarifa_raw):.2f}€ + IVA"
                    else:
                        precio_display = "N/A"
                except (TypeError, ValueError):
                    precio_display = f"{tarifa_raw}€ + IVA" if tarifa_raw else "N/A"
                    logger.warning("precio_display_calculo_fallback", tarifa_raw=tarifa_raw)

                note_content = (
                    "📋 **Expediente completado y pendiente de revisión**\n\n"
                    f"- **Caso ID**: `{case_id}`\n"
                    f"- **Categoría**: {categoria_slug}\n"
                    f"- **Elementos**: {element_summary}\n"
                    f"- **Precio**: {precio_display}\n"
                    f"- **Completado**: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M')}\n\n"
                    "El expediente necesita revisión humana antes de proceder."
                )

                await chatwoot.add_private_note(conversation_id=conv_id, note=note_content)
                await chatwoot.add_labels(conversation_id=conv_id, labels=["expediente-pendiente"])

                logger.info("finalizar_expediente_chatwoot_notified", case_id=case_id, conversation_id=conversation_id)
            except Exception as e:
                logger.warning(
                    "finalizar_expediente_chatwoot_notification_failed",
                    case_id=case_id,
                    error=str(e),
                )

    except Exception as e:
        logger.error("failed_to_finalize_case", error=str(e), exc_info=True)
        return tool_error_response(
            message=f"Error al finalizar el expediente: {str(e)}",
            error_category=ErrorCategory.DATABASE_ERROR,
            error_code="FINALIZE_FAILED",
            guidance="Intenta de nuevo. Si el problema persiste, contacta con soporte.",
            context={"current_step": current_step.value},
        )

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
        "_state_update": {
            "case_finalized": True,
            "can_narrate_completion": True,
            "expediente_sub_mode": CollectionStep.COMPLETED.value,
            "expediente_completed": True,
        },
    }
