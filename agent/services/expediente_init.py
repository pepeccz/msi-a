"""
Expediente initialization helpers — extracted from ExpedienteModeNode.

These are pure async functions (not class methods) used by the subgraph's
``entry_router`` node to initialize or recover expediente state before
routing to a sub-mode node.

Design reference:
- AD-4 (Coordinator Logic Distribution): entry_router absorbs initialization
- AD-5 (FSM Shim Compatibility): _fsm_state_init pattern preserved
- AD-7 (Recovery & Multi-day Flow): pending_recovery_case consumed here

Functions:
- ``initialize_expediente(state)``: Main entry — decides which path to take
- ``_auto_create_case(state)``: Create/resume Case record in PostgreSQL
- ``_build_recovery_context(state)``: Rebuild mode_context from orphaned Case

IMPORTANT: These functions work with ``ExpedienteState``-shaped dicts (not
``ConversationState``). They are copied (not moved) from ``expediente_mode.py``
so the v1 coordinator stays intact behind the feature flag.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def initialize_expediente(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Initialize expediente state on the first entry to the subgraph.

    Decision tree:
    1. If ``case_id`` is already present → no-op (return empty dict).
    2. If ``pending_recovery_case`` is present → delegate to
       ``_build_recovery_context()`` (orphaned expediente recovery path).
    3. Otherwise → delegate to ``_auto_create_case()`` (normal creation/resume).

    Args:
        state: ``ExpedienteState``-shaped dict from the subgraph.

    Returns:
        Dict of state updates to merge into ``ExpedienteState``.
        Empty dict when ``case_id`` is already present (no-op).
    """
    # ── Fast path: already initialized ──────────────────────────────────────
    if state.get("case_id"):
        return {}

    # ── Recovery path: orphaned expediente from preprocess_node ─────────────
    pending_recovery = state.get("pending_recovery_case")
    if pending_recovery and isinstance(pending_recovery, dict):
        logger.info(
            "expediente_init_recovery_path",
            conversation_id=state.get("conversation_id", "unknown"),
            recovery_case_id=pending_recovery.get("case_id"),
        )
        return await _build_recovery_context(state)

    # ── Normal path: query DB or auto-create ─────────────────────────────────
    logger.info(
        "expediente_init_normal_path",
        conversation_id=state.get("conversation_id", "unknown"),
        categoria_slug=state.get("categoria_slug"),
    )
    return await _auto_create_case(state)


async def _auto_create_case(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Query PostgreSQL for an active case or create a new one.

    Extracted from ``ExpedienteModeNode._auto_create_case()`` and
    ``ExpedienteModeNode._initialize_mode_context()`` in ``expediente_mode.py``.
    Handles:
    - Existing case found by conversation_id → resume
    - Existing case from another conversation (particular) → block
    - No case found → create new Case record
    - Recovery via ``get_or_create_active_case()`` helper

    Args:
        state: ``ExpedienteState``-shaped dict.

    Returns:
        Dict of state updates including ``case_id``, ``_fsm_state_init``,
        ``case_instructions``, etc.
        May include ``blocked_existing_case_id`` if a particular has a
        conflicting active case from another conversation.
    """
    import json
    from typing import cast

    from agent.services.case_helpers import get_or_create_active_case
    from agent.services.case_service import _get_category_id_by_slug
    from agent.modes.submodos._shared import (
        COLLECT_ELEMENT_DATA,
        COLLECT_BASE_DOCS,
    )
    from agent.utils.expediente_types import CollectionStep

    conversation_id: str = state.get("conversation_id") or ""
    current_context = dict(state)

    # ── Step 1: Try to find existing case by conversation_id ─────────────────
    from database.connection import get_async_session
    from database.models import Case

    try:
        async with get_async_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Case)
                .where(Case.conversation_id == conversation_id)
                .where(Case.status.in_(["collecting", "pending_review", "in_progress"]))
                .order_by(Case.created_at.desc())
            )
            case = result.scalar_one_or_none()

            if case:
                # Existing case found for this conversation — resume
                return await _resume_existing_case(case, state)

    except Exception as e:
        logger.warning(
            "expediente_init_db_query_failed",
            conversation_id=conversation_id,
            error=str(e),
        )
        # Fall through to creation path

    # ── Step 2: No existing case — try auto-create or detect conflicts ────────
    categoria_slug = current_context.get("categoria_slug")

    # P2.4: Read elementos_confirmados as PRIMARY source for element codes
    elementos_confirmados: list[dict[str, Any]] | None = current_context.get(
        "elementos_confirmados"
    )
    _confirmed_display_names: dict[str, str] | None = None
    if elementos_confirmados and isinstance(elementos_confirmados, list):
        element_codes = [
            elem.get("code", "")
            for elem in elementos_confirmados
            if isinstance(elem, dict) and elem.get("code")
        ]
        _confirmed_display_names = {
            elem.get("code", ""): elem.get("name") or elem.get("code", "")
            for elem in elementos_confirmados
            if isinstance(elem, dict) and elem.get("code")
        }
    else:
        element_codes = current_context.get("element_codes", [])

    if not categoria_slug or not element_codes:
        logger.error(
            "expediente_init_cannot_create_case_missing_data",
            conversation_id=conversation_id,
            has_categoria=bool(categoria_slug),
            has_elements=bool(element_codes),
        )
        return {}

    # Get client_type and user_id from state
    client_type_safe: str | None = cast(str | None, current_context.get("client_type"))
    user_id_safe = current_context.get("user_id")
    user_id_safe_str = str(user_id_safe) if user_id_safe is not None else None

    # Get category ID from slug
    category_id = await _get_category_id_by_slug(categoria_slug)
    if not category_id:
        logger.error(
            "expediente_init_category_not_found",
            categoria_slug=categoria_slug,
        )
        return {}

    # Extract tariff data if available
    tarifa_calculada = current_context.get("tarifa_calculada")
    tarifa_amount = None
    tier_id = None

    if tarifa_calculada:
        if isinstance(tarifa_calculada, str):
            try:
                tarifa_calculada = json.loads(tarifa_calculada)
            except (ValueError, TypeError):
                pass
        if isinstance(tarifa_calculada, dict):
            datos = tarifa_calculada.get("datos", {})
            tarifa_amount = datos.get("price")
            tier_id = datos.get("tier_id")

    # Delegate to the shared idempotent helper
    try:
        case, created = await get_or_create_active_case(
            user_id=user_id_safe_str,
            conversation_id=conversation_id,
            category_id=category_id,
            element_codes=element_codes,
            tariff_tier_id=tier_id,
            tariff_amount=tarifa_amount,
            client_type=client_type_safe,
        )
    except RuntimeError:
        logger.error(
            "expediente_init_create_case_helper_failed",
            conversation_id=conversation_id,
            exc_info=True,
        )
        return {}

    # ── Path A: Existing case from another conversation ───────────────────────
    if not created:
        if (
            client_type_safe != "professional"
            and case.conversation_id != conversation_id
        ):
            # Block particular with conflicting active case
            from datetime import datetime

            created_at_str = (
                case.created_at.strftime("%d/%m/%Y a las %H:%M")
                if case.created_at
                else "fecha desconocida"
            )
            status_desc = {
                "collecting": "en proceso de recolección de datos",
                "pending_images": "pendiente de imágenes",
            }.get(case.status, case.status)

            logger.warning(
                "expediente_init_blocked_particular",
                existing_case_id=str(case.id),
                existing_conversation_id=case.conversation_id,
                new_conversation_id=conversation_id,
                client_type=client_type_safe,
            )

            block_instructions = (
                "⚠️ EXPEDIENTE BLOQUEADO — NO CREAR EXPEDIENTE NUEVO\n\n"
                "El usuario ya tiene un expediente activo:\n"
                f"- Estado: {status_desc}\n"
                f"- Creado: {created_at_str}\n\n"
                "Los particulares solo pueden tener UN expediente activo a la vez.\n\n"
                "DEBES informar al usuario y ofrecerle DOS opciones:\n"
                "1. Retomar el expediente activo (retomar donde lo dejó)\n"
                "2. Cancelar el expediente actual con cancelar_expediente() "
                "y luego iniciar uno nuevo.\n\n"
                "NO llames a iniciar_expediente() ni crees nada nuevo. "
                "NO preguntes datos personales ni de vehículo. "
                "Primero resuelve el conflicto con el usuario."
            )

            return {
                "case_instructions": block_instructions,
                "blocked_existing_case_id": str(case.id),
                "expediente_sub_mode": COLLECT_ELEMENT_DATA,
            }

        # Same conversation or professional: resume existing case
        return await _resume_existing_case(case, state)

    # ── Path B: New case created ──────────────────────────────────────────────
    return await _initialize_new_case(
        case=case,
        state=state,
        categoria_slug=categoria_slug,
        category_id=category_id,
        element_codes=element_codes,
        confirmed_display_names=_confirmed_display_names,
        tarifa_amount=tarifa_amount,
        tier_id=tier_id,
        user_id_safe_str=user_id_safe_str,
    )


async def _resume_existing_case(
    case: Any,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Build state updates for resuming an existing Case."""
    from agent.modes.submodos._shared import COLLECT_ELEMENT_DATA, COLLECT_BASE_DOCS
    from agent.utils.expediente_types import CollectionStep

    current_context = dict(state)
    categoria_slug = (
        case.category.slug
        if case.category
        else current_context.get("categoria_slug", "")
    )
    codes = case.element_codes or current_context.get("element_codes", [])

    # Load base doc descriptions
    from agent.modes.expediente_mode import (
        _load_base_doc_descriptions,
        _hydrate_case_context_from_db,
    )

    (
        resume_base_doc_descriptions,
        resume_category_data,
    ) = await _load_base_doc_descriptions(categoria_slug)
    resume_sub_mode = current_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA)
    hydrated_context = await _hydrate_case_context_from_db(
        case, case.user, resume_sub_mode
    )

    category_id_str = str(case.category_id) if case.category_id else None
    tier_id_str = str(case.tariff_tier_id) if case.tariff_tier_id else None
    tariff_amount_val = float(case.tariff_amount) if case.tariff_amount else None

    existing_fsm = {
        "case_collection": {
            "step": hydrated_context.get(
                "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
            ),
            "case_id": str(case.id),
            "category_slug": categoria_slug,
            "category_id": category_id_str,
            "element_codes": codes,
            "current_element_index": 0,
            "element_phase": "photos",
            "element_data_status": {code: "pending" for code in codes},
            "base_docs_received": hydrated_context.get("base_docs_received", False),
            "base_doc_descriptions": resume_base_doc_descriptions,
            "received_images": [],
            "tariff_tier_id": tier_id_str,
            "tariff_amount": tariff_amount_val,
            "taller_propio": hydrated_context.get("taller_propio"),
            "taller_data": hydrated_context.get("taller_data"),
            "retry_count": 0,
        }
    }

    return {
        "case_id": str(case.id),
        "category_id": category_id_str,
        "category_slug": categoria_slug,
        "element_codes": codes,
        "current_element_index": 0,
        "element_phase": "photos",
        "element_data_status": {code: "pending" for code in codes},
        "base_docs_received": hydrated_context.get("base_docs_received", False),
        "base_doc_descriptions": resume_base_doc_descriptions,
        "personal_data": hydrated_context.get("personal_data", {}),
        "vehicle_data": hydrated_context.get("vehicle_data", {}),
        "taller_propio": hydrated_context.get("taller_propio"),
        "taller_data": hydrated_context.get("taller_data"),
        "tariff_tier_id": tier_id_str,
        "tariff_amount": tariff_amount_val,
        "received_images": [],
        "expediente_intro_sent": current_context.get("expediente_intro_sent", True),
        "_fsm_state_init": existing_fsm,
        "expediente_sub_mode": resume_sub_mode,
    }


async def _initialize_new_case(
    case: Any,
    state: dict[str, Any],
    categoria_slug: str,
    category_id: str,
    element_codes: list[str],
    confirmed_display_names: dict[str, str] | None,
    tarifa_amount: float | None,
    tier_id: str | None,
    user_id_safe_str: str | None,
) -> dict[str, Any]:
    """Build state updates for a freshly created Case."""
    from agent.modes.submodos._shared import COLLECT_ELEMENT_DATA
    from agent.services.expediente_onboarding import (
        build_new_expediente_case_instructions,
    )
    from agent.modes.expediente_mode import (
        _load_base_doc_descriptions,
        _resolve_element_display_names,
        _build_element_photo_instructions,
    )
    from agent.services.case_service import _load_user_data_for_case
    from agent.services.case_image_batch_service import get_case_image_batch_service
    from datetime import datetime, UTC

    case_id = case.id
    current_context = dict(state)

    # Get base documentation descriptions
    base_doc_descriptions: list[str] = []
    category_data: dict[str, Any] | None = None
    try:
        from agent.services.tarifa_service import get_tarifa_service

        tarifa_service = get_tarifa_service()
        category_data = await tarifa_service.get_category_data(categoria_slug)
        if category_data and category_data.get("base_documentation"):
            base_doc_descriptions = [
                bd["description"] for bd in category_data["base_documentation"]
            ]
    except Exception as e:
        logger.warning(
            "expediente_init_base_docs_failed",
            error=str(e),
            categoria_slug=categoria_slug,
        )

    # Pre-populate personal data from existing user profile
    prefilled_personal_data = await _load_user_data_for_case(user_id_safe_str) or {}

    first_element = element_codes[0] if element_codes else None

    # Resolve element display names
    if confirmed_display_names:
        element_display_names = confirmed_display_names
        missing_codes = [c for c in element_codes if c not in element_display_names]
        if missing_codes:
            db_names = await _resolve_element_display_names(missing_codes, category_id)
            element_display_names.update(db_names)
    else:
        element_display_names = await _resolve_element_display_names(
            element_codes, category_id
        )

    first_element_display = (
        element_display_names.get(first_element, first_element)
        if first_element
        else None
    )

    # Build pre-filled data context for LLM
    prefilled_context = ""
    if prefilled_personal_data:
        filled_fields = {k: v for k, v in prefilled_personal_data.items() if v}
        if filled_fields:
            field_labels = {
                "nombre": "Nombre",
                "apellidos": "Apellidos",
                "dni_cif": "DNI/CIF",
                "email": "Email",
                "domicilio_calle": "Calle",
                "domicilio_localidad": "Localidad",
                "domicilio_provincia": "Provincia",
                "domicilio_cp": "CP",
            }
            filled_summary = ", ".join(
                f"{field_labels.get(k, k)}: {v}"
                for k, v in filled_fields.items()
                if k != "itv_nombre"
            )
            prefilled_context = (
                f"\nDATOS PERSONALES YA REGISTRADOS DEL USUARIO:\n"
                f"  {filled_summary}\n"
                f"Cuando llegues a COLLECT_PERSONAL, presenta estos datos al usuario "
                f"y pregunta si son correctos antes de pedir nuevos.\n"
            )

    # Build per-element photo instructions
    element_photo_instructions = _build_element_photo_instructions(
        current_context.get("tarifa_calculada"),
    )

    case_instructions = build_new_expediente_case_instructions(
        first_element_display=first_element_display or "elemento",
        total_elements=len(element_codes),
        prefilled_context=prefilled_context,
        element_photo_instructions=element_photo_instructions,
        intro_already_sent=True,
        auto_created=True,
    )

    # Build FSM state for tool compatibility
    initial_fsm_state = {
        "case_collection": {
            "step": "collect_element_data",
            "case_id": str(case_id),
            "category_slug": categoria_slug,
            "category_id": category_id,
            "element_codes": element_codes,
            "current_element_index": 0,
            "element_phase": "photos",
            "element_data_status": {code: "pending" for code in element_codes},
            "base_docs_received": False,
            "base_doc_descriptions": base_doc_descriptions,
            "received_images": [],
            "tariff_tier_id": tier_id,
            "tariff_amount": tarifa_amount,
            "taller_propio": None,
            "taller_data": None,
            "retry_count": 0,
        }
    }

    # Open image batch scope for first element
    if element_codes:
        await get_case_image_batch_service().open_for_scope(
            case_id=str(case_id),
            expediente_sub_mode=COLLECT_ELEMENT_DATA,
            element_code=element_codes[0],
            opened_at=datetime.now(UTC),
        )

    logger.info(
        "expediente_init_new_case_created",
        case_id=str(case_id),
        conversation_id=current_context.get("conversation_id", "unknown"),
        element_count=len(element_codes),
        categoria_slug=categoria_slug,
    )

    return {
        "case_id": str(case_id),
        "category_id": category_id,
        "category_slug": categoria_slug,
        "element_codes": element_codes,
        "element_display_names": element_display_names,
        "current_element_index": 0,
        "element_phase": "photos",
        "element_data_status": {code: "pending" for code in element_codes},
        "base_docs_received": False,
        "base_doc_descriptions": base_doc_descriptions,
        "category_data": category_data,
        "personal_data": prefilled_personal_data,
        "vehicle_data": {},
        "taller_propio": None,
        "taller_data": None,
        "tariff_tier_id": tier_id,
        "tariff_amount": float(tarifa_amount) if tarifa_amount else None,
        "received_images": [],
        "expediente_intro_sent": False,
        "case_instructions": case_instructions,
        "_fsm_state_init": initial_fsm_state,
        "expediente_sub_mode": current_context.get(
            "expediente_sub_mode", COLLECT_ELEMENT_DATA
        ),
    }


async def _build_recovery_context(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Build state updates for an orphaned expediente recovery.

    Extracted from ``ExpedienteModeNode._build_recovery_context()`` in
    ``expediente_mode.py``.

    The ``pending_recovery_case`` in ``state`` contains all DB data already
    loaded by ``preprocess_node``. This function:
    1. Builds the FSM state so element_data_tools work on the first turn.
    2. Crafts a warm ``case_instructions`` message for the LLM.
    3. Updates the case's ``conversation_id`` in DB.
    4. Clears ``pending_recovery_case`` (tombstone to None).

    Args:
        state: ``ExpedienteState``-shaped dict with ``pending_recovery_case``.

    Returns:
        Dict of state updates. ``pending_recovery_case`` is always set to None.
    """
    from agent.modes.submodos._shared import COLLECT_ELEMENT_DATA
    from agent.utils.expediente_types import CollectionStep
    from agent.services.expediente_onboarding import (
        build_resume_expediente_case_instructions,
    )
    from agent.modes.expediente_mode import (
        _load_base_doc_descriptions,
        _hydrate_case_context_from_db,
        _resolve_element_display_names,
    )

    recovery_data: dict[str, Any] = state.get("pending_recovery_case") or {}
    conversation_id: str = state.get("conversation_id") or ""

    case_id = recovery_data.get("case_id", "")
    category_slug = recovery_data.get("category_slug") or ""
    category_id = recovery_data.get("category_id")
    element_codes = recovery_data.get("element_codes") or []
    element_data_status = recovery_data.get("element_data_status") or {}
    tariff_tier_id = recovery_data.get("tariff_tier_id")
    tariff_amount = recovery_data.get("tariff_amount")
    inferred_sub_mode = recovery_data.get("inferred_sub_mode", COLLECT_ELEMENT_DATA)
    created_at_str = recovery_data.get("created_at_str", "fecha desconocida")

    # Load base doc descriptions
    (
        recovery_base_doc_descriptions,
        recovery_category_data,
    ) = await _load_base_doc_descriptions(category_slug)

    # Map element_data_status to full status dict
    full_status: dict[str, str] = {}
    for code in element_codes:
        full_status[code] = element_data_status.get(code, "pending_photos")

    # Determine current_element_index: first element not yet "completed"
    current_index = 0
    current_phase = "photos"
    for idx, code in enumerate(element_codes):
        s = full_status.get(code, "pending_photos")
        if s != "completed":
            current_index = idx
            current_phase = "data" if s == "pending_data" else "photos"
            break

    # Describe progress for the LLM's resume greeting
    completed_count = sum(1 for s in full_status.values() if s == "completed")
    total_count = len(element_codes)

    _recovery_display_names = await _resolve_element_display_names(
        [c for c in element_codes if isinstance(c, str)],
        str(category_id) if category_id else "",
    )
    _resolved_elements = [
        _recovery_display_names.get(str(code), str(code))
        for code in element_codes
        if code is not None
    ]
    elementos_str = (
        ", ".join(_resolved_elements) if _resolved_elements else "desconocidos"
    )
    progress_desc = f"{completed_count}/{total_count} elementos completados"

    sub_mode_labels = {
        COLLECT_ELEMENT_DATA: "Fotos y datos de elementos",
        "collect_base_docs": "Documentación base del vehículo",
        "collect_personal": "Datos personales",
        "collect_vehicle": "Datos del vehículo",
        "collect_workshop": "Certificado del taller",
        "review_summary": "Revisión final",
    }
    resume_phase_label = sub_mode_labels.get(inferred_sub_mode, inferred_sub_mode)

    hydrated_context: dict[str, Any] = {}

    # Update conversation_id in DB (best-effort)
    try:
        import uuid as _uuid
        from database.connection import get_async_session
        from database.models import Case

        async with get_async_session() as session:
            case_obj = await session.get(Case, _uuid.UUID(case_id))
            if case_obj:
                hydrated_context = await _hydrate_case_context_from_db(
                    case_obj,
                    case_obj.user,
                    inferred_sub_mode,
                )
            if case_obj and case_obj.conversation_id != conversation_id:
                old_conv_id = case_obj.conversation_id
                case_obj.conversation_id = conversation_id
                await session.commit()
                logger.info(
                    "expediente_init_recovery_updated_conversation_id",
                    case_id=case_id,
                    old_conversation_id=old_conv_id,
                    new_conversation_id=conversation_id,
                )
    except Exception as e:
        logger.warning(
            "expediente_init_recovery_failed_to_update_conversation_id",
            case_id=case_id,
            conversation_id=conversation_id,
            error=str(e),
        )

    # Build FSM state for tool compatibility
    recovered_fsm = {
        "case_collection": {
            "step": hydrated_context.get(
                "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
            ),
            "case_id": case_id,
            "category_slug": category_slug,
            "category_id": category_id,
            "element_codes": element_codes,
            "current_element_index": current_index,
            "element_phase": current_phase,
            "element_data_status": full_status,
            "base_docs_received": hydrated_context.get("base_docs_received", False),
            "base_doc_descriptions": recovery_base_doc_descriptions,
            "received_images": [],
            "tariff_tier_id": tariff_tier_id,
            "tariff_amount": tariff_amount,
            "taller_propio": hydrated_context.get("taller_propio"),
            "taller_data": hydrated_context.get("taller_data"),
            "retry_count": 0,
        }
    }

    case_instructions = (
        build_resume_expediente_case_instructions(
            elementos_str=elementos_str,
            progress_desc=progress_desc,
            resume_phase_label=resume_phase_label or inferred_sub_mode,
            created_at_str=created_at_str,
        )
        + "\nIMPORTANTE: El expediente YA EXISTE en la base de datos. "
        "NO llames a iniciar_expediente()."
    )

    logger.info(
        "expediente_init_recovery_context_built",
        case_id=case_id,
        conversation_id=conversation_id,
        inferred_sub_mode=inferred_sub_mode,
        progress=progress_desc,
    )

    return {
        "case_id": case_id,
        "category_id": category_id,
        "category_slug": category_slug,
        "element_codes": element_codes,
        "element_display_names": _recovery_display_names,
        "current_element_index": current_index,
        "element_phase": current_phase,
        "element_data_status": full_status,
        "base_docs_received": hydrated_context.get("base_docs_received", False),
        "base_doc_descriptions": recovery_base_doc_descriptions,
        "category_data": recovery_category_data,
        "personal_data": hydrated_context.get("personal_data", {}),
        "vehicle_data": hydrated_context.get("vehicle_data", {}),
        "taller_propio": hydrated_context.get("taller_propio"),
        "taller_data": hydrated_context.get("taller_data"),
        "tariff_tier_id": tariff_tier_id,
        "tariff_amount": tariff_amount,
        "received_images": [],
        "expediente_intro_sent": state.get("expediente_intro_sent", True),
        "case_instructions": case_instructions,
        "_fsm_state_init": recovered_fsm,
        "expediente_sub_mode": inferred_sub_mode,
        # Tombstone: consumed exactly once — cleared so it won't re-trigger
        "pending_recovery_case": None,
    }
