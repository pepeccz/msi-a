"""
MSI-a - EXPEDIENTE_MODE Node.

Formal case collection mode for homologation expedientes.
This is the most complex mode with 6 sub-modes.

Flow:
    1. COLLECT_ELEMENT_DATA (per element: photos → data)
    2. COLLECT_BASE_DOCS (ficha técnica, permiso, vistas)
    3. COLLECT_PERSONAL (nombre, DNI, email, domicilio, etc.)
    4. COLLECT_VEHICLE (marca, modelo, matrícula, bastidor)
    5. COLLECT_WORKSHOP (optional if taller_propio=True)
    6. REVIEW_SUMMARY (final confirmation)

Architecture:
    - Sub-mode stored in mode_context["expediente_sub_mode"]
    - LLM-driven within each sub-mode (like other modes)
    - Tools recycled from v1 (element_data_tools, case_tools)
    - Digressions BLOCKED (only escalation allowed)

Sub-mode switching:
    Tools like completar_elemento_actual() return updates to
    expediente_sub_mode, causing next invocation to route to new handler.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from typing import Any, cast

import structlog
from langchain_openai import ChatOpenAI

from agent.modes.base_mode import BaseModeNode
from agent.modes.presupuesto_mode import _apply_tool_flags
from agent.state.conversation_state import ConversationState, create_empty_retry_state
from agent.prompts.loader import assemble_system_prompt
from agent.state.helpers import format_messages_for_llm, set_current_state, clear_current_state
from agent.tools.image_tools import set_current_state_for_image_tools, clear_image_tools_state
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Max tool call iterations per turn
MAX_TOOL_ITERATIONS = 10

# Sub-mode constants (matching v1 CollectionStep names for easy tool recycling)
COLLECT_ELEMENT_DATA = "collect_element_data"
COLLECT_BASE_DOCS = "collect_base_docs"
COLLECT_PERSONAL = "collect_personal"
COLLECT_VEHICLE = "collect_vehicle"
COLLECT_WORKSHOP = "collect_workshop"
REVIEW_SUMMARY = "review_summary"


# ---------------------------------------------------------------------------
# Module-level helpers (used by static methods inside the class)
# ---------------------------------------------------------------------------

def _extract_field_keys_from_tool_result(data: dict[str, Any]) -> list[dict[str, str]] | None:
    """
    Extract field_key info from tool results generically.

    Works with any tool that returns field information (confirmar_fotos_elemento,
    obtener_campos_elemento, guardar_datos_elemento).  Returns a compact list
    of dicts with ``field_key`` and ``field_label`` so the prompt loader can
    inject them into the system prompt without duplicating business logic.

    Looks for fields in these locations (in priority order):
    1. ``data["fields"]`` — list of field dicts from obtener_campos_elemento / batch mode
    2. ``data["current_field"]`` — single field dict from sequential mode
    """
    field_keys: list[dict[str, str]] = []
    seen: set[str] = set()

    # Source 1: explicit "fields" array (obtener_campos_elemento, batch/hybrid mode)
    fields_list = data.get("fields")
    if isinstance(fields_list, list):
        for f in fields_list:
            if isinstance(f, dict) and "field_key" in f:
                fk = f["field_key"]
                if fk not in seen:
                    seen.add(fk)
                    field_keys.append({
                        "field_key": fk,
                        "field_label": f.get("field_label", fk),
                    })

    # Source 2: sequential mode "current_field"
    current_field = data.get("current_field")
    if isinstance(current_field, dict) and "field_key" in current_field:
        fk = current_field["field_key"]
        if fk not in seen:
            seen.add(fk)
            field_keys.append({
                "field_key": fk,
                "field_label": current_field.get("field_label", fk),
            })

    return field_keys if field_keys else None


class ExpedienteModeNode(BaseModeNode):
    """
    EXPEDIENTE_MODE: Formal case data collection.

    This mode orchestrates 6 sub-modes, each responsible for collecting
    specific data:
    - COLLECT_ELEMENT_DATA: Photos + technical data per element
    - COLLECT_BASE_DOCS: Base vehicle documents
    - COLLECT_PERSONAL: Personal data (nombre, DNI, email, etc.)
    - COLLECT_VEHICLE: Vehicle data (marca, modelo, matrícula)
    - COLLECT_WORKSHOP: Workshop data (if taller_propio=True)
    - REVIEW_SUMMARY: Final confirmation before submission

    Sub-mode routing happens automatically via tool returns that update
    expediente_sub_mode in mode_context.
    """

    def __init__(self) -> None:
        super().__init__("EXPEDIENTE_MODE")
        self._tools_cache: dict[str, list] = {}  # Tools per sub-mode

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message in EXPEDIENTE_MODE.

        Routes to appropriate sub-mode handler based on expediente_sub_mode.
        """
        conversation_id = state.get("conversation_id", "unknown")
        mode_context = dict(state.get("mode_context", {}))

        # Initialize mode_context from DB if empty (first entry to EXPEDIENTE_MODE)
        if not mode_context.get("case_id"):
            mode_context = await self._initialize_mode_context(
                conversation_id, mode_context, state,
            )

        # Determine current sub-mode
        sub_mode = mode_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA)

        # Reconcile element_phase with DB if case_id exists (safety net)
        case_id = mode_context.get("case_id")
        if case_id and mode_context.get("element_phase") == "photos":
            # Check if DB says photos are already done for current element
            current_el_code = mode_context.get("current_element_code")
            if current_el_code:
                try:
                    from database.connection import get_async_session
                    from database.models import CaseElementData
                    from sqlalchemy import select
                    import uuid as _uuid

                    async with get_async_session() as session:
                        result = await session.execute(
                            select(CaseElementData.status)
                            .where(CaseElementData.case_id == _uuid.UUID(str(case_id)))
                            .where(CaseElementData.element_code == current_el_code)
                        )
                        db_status = result.scalar_one_or_none()
                        if db_status == "pending_data":
                            mode_context["element_phase"] = "data"
                            logger.warning(
                                "state_reconciled_from_db",
                                field="element_phase",
                                stale_value="photos",
                                corrected_value="data",
                                case_id=case_id,
                                element_code=current_el_code,
                            )
                except Exception as e:
                    # Non-critical — if reconciliation fails, continue with existing state
                    logger.debug("state_reconciliation_skipped", error=str(e))

        self._logger.info(
            "expediente_processing",
            sub_mode=sub_mode,
            message_preview=message[:60],
        )

        # Route to sub-mode handler
        if sub_mode == COLLECT_ELEMENT_DATA:
            return await self._handle_element_data(message, state, mode_context)
        elif sub_mode == COLLECT_BASE_DOCS:
            return await self._handle_base_docs(message, state, mode_context)
        elif sub_mode == COLLECT_PERSONAL:
            return await self._handle_personal(message, state, mode_context)
        elif sub_mode == COLLECT_VEHICLE:
            return await self._handle_vehicle(message, state, mode_context)
        elif sub_mode == COLLECT_WORKSHOP:
            return await self._handle_workshop(message, state, mode_context)
        elif sub_mode == REVIEW_SUMMARY:
            return await self._handle_review(message, state, mode_context)
        else:
            # Unknown sub-mode — reset to start
            self._logger.error(
                "unknown_sub_mode",
                sub_mode=sub_mode,
            )
            return {
                "ai_response": (
                    "Hubo un error en el flujo del expediente. "
                    "Vamos a reiniciar desde el principio."
                ),
                "mode_context": {
                    **mode_context,
                    "expediente_sub_mode": COLLECT_ELEMENT_DATA,
                },
            }

    def get_tools(self) -> list:
        """
        Return tools available in EXPEDIENTE_MODE.

        Tools vary by sub-mode, but this method returns ALL tools
        (the sub-mode handlers will filter appropriately).
        """
        # Return all expediente tools (sub-mode handlers filter)
        return _get_all_expediente_tools()

    # ------------------------------------------------------------------
    # Mode context initialization
    # ------------------------------------------------------------------

    async def _initialize_mode_context(
        self,
        conversation_id: str,
        current_context: dict[str, Any],
        state: ConversationState | None = None,
    ) -> dict[str, Any]:
        """
        Initialize mode_context from DB when entering EXPEDIENTE_MODE.

        This loads the active case data for v1 tools compatibility.
        V1 tools expect case_id, category_id, element_codes, etc. in the FSM state,
        which we store in mode_context.

        Args:
            conversation_id: Conversation ID
            current_context: Current mode_context (may be empty)
            state: Full conversation state (for user_id access before ContextVar is set)

        Returns:
            Initialized mode_context with case data
        """
        from database.connection import get_async_session
        from database.models import Case

        try:
            async with get_async_session() as session:
                from sqlalchemy import select

                # Find active case for this conversation
                result = await session.execute(
                    select(Case)
                    .where(Case.conversation_id == conversation_id)
                    .where(Case.status.in_(["collecting", "pending_review", "in_progress"]))
                    .order_by(Case.created_at.desc())
                )
                case = result.scalar_one_or_none()

                if not case:
                    logger.warning(
                        "no_active_case_for_expediente_attempting_auto_create",
                        conversation_id=conversation_id,
                    )
                    # Auto-create case from mode_context data
                    # (carried from PRESUPUESTO → EVAL_GATEWAY → EXPEDIENTE
                    # via CONTEXT_PRESERVE_RULES in mode_transitions.py)
                    return await self._auto_create_case(
                        conversation_id, current_context, state,
                    )

                # Resolve category_slug from relationship (Case has no
                # category_slug column — only category_id FK).
                category_slug = (
                    case.category.slug if case.category else
                    current_context.get("categoria_slug", "")
                )
                codes = case.element_codes or []

                from agent.utils.fsm_compat import (
                    initialize_element_data_status,
                    update_case_fsm_state,
                )
                from sqlalchemy import select as sa_select
                from database.models import CaseElementData

                # ── Reconcile element progress from DB ──────────────────────
                # When re-entering EXPEDIENTE_MODE (e.g. after reconnect or
                # restart), rebuild element_data_status and current_element_index
                # from persisted CaseElementData records instead of resetting
                # everything to 0/pending. This prevents the agent from asking
                # for photos that were already confirmed.
                ced_result = await session.execute(
                    sa_select(CaseElementData)
                    .where(CaseElementData.case_id == case.id)
                )
                ced_rows = list(ced_result.scalars().all())
                ced_by_code: dict[str, str] = {
                    row.element_code: row.status for row in ced_rows
                }

                if ced_by_code:
                    # Rebuild element_data_status honoring persisted statuses
                    reconciled_status: dict[str, str] = {}
                    first_incomplete_idx: int = len(codes)  # Default: all done
                    first_incomplete_phase: str = "photos"

                    for idx, code in enumerate(codes):
                        db_status = ced_by_code.get(code)
                        if db_status == "completed":
                            reconciled_status[code] = "completed"
                        elif db_status == "pending_data":
                            reconciled_status[code] = "pending_data"
                            if first_incomplete_idx == len(codes):
                                first_incomplete_idx = idx
                                first_incomplete_phase = "data"
                        else:
                            # pending_photos or not in DB yet
                            reconciled_status[code] = "pending_photos"
                            if first_incomplete_idx == len(codes):
                                first_incomplete_idx = idx
                                first_incomplete_phase = "photos"

                    reconciled_index = min(first_incomplete_idx, len(codes) - 1) if codes else 0
                    reconciled_phase = first_incomplete_phase

                    # Determine if all elements are already completed
                    all_elements_done = all(
                        v == "completed" for v in reconciled_status.values()
                    ) if reconciled_status else False
                else:
                    # No DB records yet — start fresh
                    reconciled_status = initialize_element_data_status(codes)
                    reconciled_index = 0
                    reconciled_phase = "photos"
                    all_elements_done = False

                logger.info(
                    "reconciled_element_progress_from_db",
                    case_id=str(case.id),
                    total_elements=len(codes),
                    completed=sum(1 for v in reconciled_status.values() if v == "completed"),
                    current_index=reconciled_index,
                    all_done=all_elements_done,
                )

                # Determine correct sub_mode based on reconciled element state
                # Prefer sub_mode already in context (set by previous turns),
                # but if all elements are done and context says collect_element_data,
                # advance to collect_base_docs automatically.
                persisted_sub_mode = current_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA)
                if all_elements_done and persisted_sub_mode == COLLECT_ELEMENT_DATA:
                    reconciled_sub_mode = COLLECT_BASE_DOCS
                    logger.info(
                        "auto_advanced_sub_mode_all_elements_done",
                        case_id=str(case.id),
                        from_sub_mode=COLLECT_ELEMENT_DATA,
                        to_sub_mode=COLLECT_BASE_DOCS,
                    )
                else:
                    reconciled_sub_mode = persisted_sub_mode

                # Build FSM state so element_data_tools can work on
                # the first turn after re-entering EXPEDIENTE_MODE.
                existing_fsm_state = update_case_fsm_state(None, {
                    "step": "collect_element_data",
                    "case_id": str(case.id),
                    "category_slug": category_slug,
                    "category_id": str(case.category_id) if case.category_id else None,
                    "element_codes": codes,
                    "current_element_index": reconciled_index,
                    "element_phase": reconciled_phase,
                    "element_data_status": reconciled_status,
                    "base_docs_received": False,
                    "base_doc_descriptions": [],
                    "received_images": [],
                    "tariff_tier_id": str(case.tariff_tier_id) if case.tariff_tier_id else None,
                    "tariff_amount": float(case.tariff_amount) if case.tariff_amount else None,
                    "taller_propio": None,
                    "taller_data": None,
                    "retry_count": 0,
                })

                # Initialize context with case data
                initialized_context = {
                    **current_context,
                    "case_id": str(case.id),
                    "category_id": str(case.category_id) if case.category_id else None,
                    "category_slug": category_slug,
                    "element_codes": codes,
                    "current_element_index": reconciled_index,
                    "element_phase": reconciled_phase,
                    "element_data_status": reconciled_status,
                    "base_docs_received": False,
                    "base_doc_descriptions": [],
                    "personal_data": {},
                    "vehicle_data": {},
                    "taller_propio": None,
                    "taller_data": None,
                    "tariff_tier_id": str(case.tariff_tier_id) if case.tariff_tier_id else None,
                    "tariff_amount": float(case.tariff_amount) if case.tariff_amount else None,
                    "received_images": [],
                    "_fsm_state_init": existing_fsm_state,
                    "expediente_sub_mode": reconciled_sub_mode,
                }

                logger.info(
                    "initialized_mode_context_from_db",
                    case_id=str(case.id),
                    element_count=len(codes),
                    category_slug=category_slug,
                )

                return initialized_context

        except Exception as e:
            logger.error(
                "failed_to_initialize_mode_context",
                error=str(e),
                conversation_id=conversation_id,
                exc_info=True,
            )
            return current_context

    # ------------------------------------------------------------------
    # Auto-create case when entering EXPEDIENTE without an existing Case
    # ------------------------------------------------------------------

    async def _auto_create_case(
        self,
        conversation_id: str,
        current_context: dict[str, Any],
        state: ConversationState | None = None,
    ) -> dict[str, Any]:
        """
        Auto-create a Case when entering EXPEDIENTE_MODE without one.

        Uses data preserved in mode_context from PRESUPUESTO → EVAL_GATEWAY
        transition (via CONTEXT_PRESERVE_RULES in mode_transitions.py).

        This method produces the SAME initialization as ``iniciar_expediente``
        in ``case_tools.py``, including:
        - CaseElementData rows per element
        - base_doc_descriptions from tarifa_service
        - Proper element_data_status via initialize_element_data_status()
        - Imperative instructions for the LLM in case_instructions

        Required keys in current_context:
        - categoria_slug: str (from PRESUPUESTO_MODE)
        - element_codes: list[str] (from PRESUPUESTO_MODE)

        Optional keys:
        - tarifa_calculada: dict (from calcular_tarifa_con_elementos)

        Args:
            conversation_id: Conversation ID
            current_context: Current mode_context with preserved data
            state: Full conversation state (user_id read from here, NOT ContextVar)
        """
        import uuid
        from decimal import Decimal
        from database.connection import get_async_session
        from database.models import Case, CaseElementData
        from sqlalchemy import select
        from agent.tools.case_tools import (
            _get_active_case_for_conversation,
            _get_category_id_by_slug,
        )
        from agent.utils.fsm_compat import (
            initialize_element_data_status,
            update_case_fsm_state,
        )

        categoria_slug = current_context.get("categoria_slug")
        element_codes = current_context.get("element_codes", [])

        if not categoria_slug or not element_codes:
            logger.error(
                "cannot_auto_create_case_missing_data",
                conversation_id=conversation_id,
                has_categoria=bool(categoria_slug),
                has_elements=bool(element_codes),
                context_keys=list(current_context.keys()),
            )
            return current_context

        # Safety check: don't create a duplicate
        existing_case = await _get_active_case_for_conversation(conversation_id)
        if existing_case:
            logger.info(
                "auto_create_case_found_existing",
                case_id=str(existing_case.id),
                conversation_id=conversation_id,
            )
            codes = existing_case.element_codes or element_codes
            category_id_str = str(existing_case.category_id) if existing_case.category_id else None
            tier_id_str = str(existing_case.tariff_tier_id) if existing_case.tariff_tier_id else None
            tariff_amount_val = float(existing_case.tariff_amount) if existing_case.tariff_amount else None

            # Build FSM state for existing case so tools work immediately
            existing_fsm = update_case_fsm_state(None, {
                "step": "collect_element_data",
                "case_id": str(existing_case.id),
                "category_slug": categoria_slug,
                "category_id": category_id_str,
                "element_codes": codes,
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": initialize_element_data_status(codes),
                "base_docs_received": False,
                "base_doc_descriptions": [],
                "received_images": [],
                "tariff_tier_id": tier_id_str,
                "tariff_amount": tariff_amount_val,
                "taller_propio": None,
                "taller_data": None,
                "retry_count": 0,
            })

            return {
                **current_context,
                "case_id": str(existing_case.id),
                "category_id": category_id_str,
                "category_slug": categoria_slug,
                "element_codes": codes,
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": initialize_element_data_status(codes),
                "base_docs_received": False,
                "base_doc_descriptions": [],
                "personal_data": {},
                "vehicle_data": {},
                "taller_propio": None,
                "taller_data": None,
                "tariff_tier_id": tier_id_str,
                "tariff_amount": tariff_amount_val,
                "received_images": [],
                "_fsm_state_init": existing_fsm,
                "expediente_sub_mode": current_context.get(
                    "expediente_sub_mode", COLLECT_ELEMENT_DATA,
                ),
            }

        # Get category ID from slug
        category_id = await _get_category_id_by_slug(categoria_slug)
        if not category_id:
            logger.error(
                "auto_create_case_category_not_found",
                categoria_slug=categoria_slug,
            )
            return current_context

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

        # Get base documentation descriptions for this category
        base_doc_descriptions: list[str] = []
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
                "auto_create_case_base_docs_failed",
                error=str(e),
                categoria_slug=categoria_slug,
            )


        # Get user_id from state parameter (NOT ContextVar — it's not set yet
        # at this point; set_current_state() runs later in _process_message L609)
        state_dict = dict(state) if state else {}
        user_id_str = state_dict.get("user_id")
        user_phone_str = state_dict.get("user_phone", "")

        # Pre-populate personal data from existing user profile
        from agent.tools.case_tools import _load_user_data_for_fsm
        prefilled_personal_data = await _load_user_data_for_fsm(user_id_str) or {}

        # NOTE: We intentionally do NOT inject phone here. The WhatsApp number
        # is authoritative and already stored in User.phone. Including it in
        # prefilled_personal_data causes the LLM to label it as "Teléfono" in the
        # prefilled summary, which confuses the LLM when the user sends their data
        # as a comma-separated list (e.g., "Pepe, 623226544, pepe@...") — the LLM
        # sees the phone already logged and misidentifies the next number as phone
        # instead of DNI, then asks for the DNI separately.

        first_element = element_codes[0] if element_codes else None

        try:
            async with get_async_session() as session:
                case_id = uuid.uuid4()
                case = Case(
                    id=case_id,
                    conversation_id=conversation_id,
                    user_id=uuid.UUID(user_id_str) if user_id_str else None,
                    status="collecting",
                    category_id=uuid.UUID(category_id),
                    element_codes=element_codes,
                    tariff_tier_id=uuid.UUID(tier_id) if tier_id else None,
                    tariff_amount=Decimal(str(tarifa_amount)) if tarifa_amount else None,
                    metadata_={
                        "started_at": datetime.now(UTC).isoformat(),
                        "category_slug": categoria_slug,
                        "auto_created": True,
                        "current_step": "collect_element_data",
                    },
                )
                session.add(case)

                # Create CaseElementData rows per element (missing in original)
                for code in element_codes:
                    element_data_row = CaseElementData(
                        id=uuid.uuid4(),
                        case_id=case_id,
                        element_code=code,
                        status="pending_photos",
                        field_values={},
                    )
                    session.add(element_data_row)

                await session.commit()

                logger.info(
                    "auto_created_case_for_expediente",
                    case_id=str(case_id),
                    conversation_id=conversation_id,
                    element_count=len(element_codes),
                    categoria_slug=categoria_slug,
                    element_data_rows=len(element_codes),
                    has_base_docs=len(base_doc_descriptions) > 0,
                )

                # Build FSM state for tool compatibility
                # Tools read state["fsm_state"]["case_collection"]
                initial_fsm_state = update_case_fsm_state(None, {
                    "step": "collect_element_data",
                    "case_id": str(case_id),
                    "category_slug": categoria_slug,
                    "category_id": category_id,
                    "element_codes": element_codes,
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": initialize_element_data_status(element_codes),
                    "base_docs_received": False,
                    "base_doc_descriptions": base_doc_descriptions,
                    "received_images": [],
                    "tariff_tier_id": tier_id,
                    "tariff_amount": tarifa_amount,
                    "taller_propio": None,
                    "taller_data": None,
                    "retry_count": 0,
                })

                # Build phase overview for UX
                phase_overview = (
                    "FASES DEL EXPEDIENTE:\n"
                    "  1. 📸 Fotos + datos técnicos de cada elemento\n"
                    "  2. 📄 Documentación base (ficha técnica, permiso, DNI titular)\n"
                    "  3. 👤 Datos personales\n"
                    "  4. 🚗 Datos del vehículo\n"
                    "  5. 🔧 Certificado del taller\n"
                    "  6. ✅ Revisión y confirmación final\n"
                )

                # Build pre-filled data context for LLM
                prefilled_context = ""
                if prefilled_personal_data:
                    filled_fields = {k: v for k, v in prefilled_personal_data.items() if v}
                    if filled_fields:
                        field_labels = {
                            "nombre": "Nombre", "apellidos": "Apellidos",
                            "dni_cif": "DNI/CIF", "email": "Email",
                            # "telefono" intentionally omitted — already in User.phone from WhatsApp
                            "domicilio_calle": "Calle", "domicilio_localidad": "Localidad",
                            "domicilio_provincia": "Provincia", "domicilio_cp": "CP",
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

                # Build imperative instructions for the LLM
                # NOTE: We intentionally do NOT inject element image descriptions here.
                # The LLM learns what photos to request only via enviar_imagenes_ejemplo()
                # tool results (captions). Pre-injecting descriptions causes duplicated
                # text in the user-facing message (system prompt paraphrase + image captions).
                case_instructions = (
                    f"EXPEDIENTE CREADO AUTOMÁTICAMENTE.\n\n"
                    f"{phase_overview}"
                    f"{prefilled_context}"
                    f"\nEMPEZAMOS con el primer elemento: {first_element} "
                    f"({1}/{len(element_codes)}).\n\n"
                    "INSTRUCCIONES OBLIGATORIAS:\n"
                    "1. Comunica brevemente que el expediente está abierto y las fases\n"
                    "2. Pregunta al usuario si quiere ver imágenes de ejemplo del elemento\n"
                    "3. SOLO usa enviar_imagenes_ejemplo() si el usuario las pide\n"
                    "4. Pide al usuario que envíe las fotos del elemento\n"
                    "5. Cuando diga 'listo', usa confirmar_fotos_elemento()\n"
                    "6. Luego recoge los datos técnicos con guardar_datos_elemento()\n"
                    "7. Usa completar_elemento_actual() para pasar al siguiente\n\n"
                    f"ELEMENTO ACTUAL: {first_element}\n"
                    f"TOTAL ELEMENTOS: {len(element_codes)}\n"
                    "IMPORTANTE: El expediente ya está creado. NO llames a "
                    "iniciar_expediente(). Empieza directamente.\n"
                    "RECUERDA: NUNCA digas que el expediente está completo sin llamar "
                    "a finalizar_expediente()."
                )

                return {
                    **current_context,
                    "case_id": str(case_id),
                    "category_id": category_id,
                    "category_slug": categoria_slug,
                    "element_codes": element_codes,
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": initialize_element_data_status(element_codes),
                    "base_docs_received": False,
                    "base_doc_descriptions": base_doc_descriptions,
                    "personal_data": prefilled_personal_data,
                    "vehicle_data": {},
                    "taller_propio": None,
                    "taller_data": None,
                    "tariff_tier_id": tier_id,
                    "tariff_amount": float(tarifa_amount) if tarifa_amount else None,
                    "received_images": [],
                    "case_instructions": case_instructions,
                    # Carry FSM state so _run_llm_loop can inject it into
                    # the ContextVar BEFORE tools execute.  Without this,
                    # element_data_tools fail with "case_collection not found".
                    "_fsm_state_init": initial_fsm_state,
                    "expediente_sub_mode": current_context.get(
                        "expediente_sub_mode", COLLECT_ELEMENT_DATA,
                    ),
                }

        except Exception as e:
            logger.error(
                "auto_create_case_failed",
                error=str(e),
                conversation_id=conversation_id,
                exc_info=True,
            )
            return current_context

    # ------------------------------------------------------------------
    # Sub-mode handlers
    # ------------------------------------------------------------------

    async def _handle_element_data(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_ELEMENT_DATA sub-mode.

        Per-element flow:
        1. Send example images (enviar_imagenes_ejemplo)
        2. User sends photos → confirmar_fotos_elemento()
        3. Ask for technical data → guardar_datos_elemento()
        4. completar_elemento_actual() → next element or COLLECT_BASE_DOCS
        """
        tools = _get_element_data_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_ELEMENT_DATA",
        )

    async def _handle_base_docs(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_BASE_DOCS sub-mode.

        User sends base documentation (ficha técnica, permiso, vistas).
        Tool: confirmar_documentacion_base()
        """
        tools = _get_base_docs_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_BASE_DOCS",
        )

    async def _handle_personal(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_PERSONAL sub-mode.

        Collect personal data: nombre, apellidos, email, teléfono,
        DNI/CIF, domicilio, ITV.

        Tool: actualizar_datos_expediente(datos_personales={...})
        """
        tools = _get_personal_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_PERSONAL",
        )

    async def _handle_vehicle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_VEHICLE sub-mode.

        Collect vehicle data: marca, modelo, año, matrícula, bastidor.

        Tool: actualizar_datos_expediente(datos_vehiculo={...})
        """
        tools = _get_vehicle_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_VEHICLE",
        )

    async def _handle_workshop(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_WORKSHOP sub-mode.

        Ask if user provides own workshop or uses MSI.
        If own workshop: collect workshop data.

        Tool: actualizar_datos_taller()
        """
        tools = _get_workshop_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_WORKSHOP",
        )

    async def _handle_review(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Handle REVIEW_SUMMARY sub-mode.

        Present summary of all collected data.
        User confirms → finalizar_expediente()
        User rejects → editar_expediente()

        Tools: finalizar_expediente(), editar_expediente()
        """
        tools = _get_review_tools()
        return await self._run_llm_loop(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="REVIEW_SUMMARY",
        )

    # ------------------------------------------------------------------
    # LLM loop (shared across all sub-modes)
    # ------------------------------------------------------------------

    async def _run_llm_loop(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        tools: list,
        sub_mode_name: str,
    ) -> dict[str, Any]:
        """
        Run the LLM tool-calling loop for a sub-mode.

        Same pattern as other modes (viabilidad, presupuesto, consulta).
        """
        conversation_id = state.get("conversation_id", "unknown")
        messages = state.get("messages", [])

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)
        
        # Map sub-mode to prompt key (matching MODE_MODULES in loader.py)
        sub_mode_to_prompt = {
            "COLLECT_ELEMENT_DATA": "EXPEDIENTE_DOCUMENTACION_ELEMENTOS",
            "COLLECT_BASE_DOCS": "EXPEDIENTE_DOCUMENTACION_BASE",
            "COLLECT_PERSONAL": "EXPEDIENTE_DATOS_PERSONALES",
            "COLLECT_VEHICLE": "EXPEDIENTE_DATOS_VEHICULO",
            "COLLECT_WORKSHOP": "EXPEDIENTE_TALLER",
            "REVIEW_SUMMARY": "EXPEDIENTE_REVISION",
        }
        mode_prompt_name = sub_mode_to_prompt.get(sub_mode_name, "EXPEDIENTE_DOCUMENTACION_ELEMENTOS")
        
        system_prompt = assemble_system_prompt(
            mode=mode_prompt_name,
            mode_context=mode_context,
            client_context=client_context,
        )

        # Inject case_instructions if present (from _auto_create_case)
        # This tells the LLM that the case is already created and what to do
        case_instructions = mode_context.get("case_instructions")
        if case_instructions:
            system_prompt += (
                "\n\n---\n\n"
                "<CASE_CONTEXT>\n"
                f"{case_instructions}\n"
                "</CASE_CONTEXT>"
            )
            # Clear after first use (avoid repeating on every turn)
            mode_context.pop("case_instructions", None)

        # ── 2. Build LLM messages ───────────────────────────────────────
        # Check for images and prepend context if present
        incoming_attachments = state.get("incoming_attachments", [])
        image_count = len(incoming_attachments)
        if image_count > 0:
            image_notice = f"[El usuario ha enviado {image_count} imagen(es) junto con este mensaje]\n\n"
        else:
            image_notice = ""
        
        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        llm_messages.extend(format_messages_for_llm(messages))
        llm_messages.append({
            "role": "user",
            "content": f"<USER_MESSAGE>\n{image_notice}{message}\n</USER_MESSAGE>",
        })

        # ── 3. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: EXPEDIENTE uses 30+ tools that need state via ContextVars.
        # IMPORTANT: Preserve nested structure - tools read from state["mode_context"]
        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context  # Preserve nested structure

        # Inject FSM state built by _auto_create_case so that
        # element_data_tools can read state["fsm_state"]["case_collection"].
        # Without this, the first turn after auto-creation fails because
        # the ContextVar has no fsm_state and tools raise KeyError.
        fsm_init = mode_context.pop("_fsm_state_init", None)
        if fsm_init:
            full_state["fsm_state"] = fsm_init
            logger.info(
                "injected_fsm_state_from_auto_create",
                case_id=fsm_init.get("case_collection", {}).get("case_id"),
                conversation_id=conversation_id,
            )

        set_current_state(full_state)
        set_current_state_for_image_tools(full_state)

        # ── 4. Get LLM with tools ───────────────────────────────────────
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
        # Pre-compile regex for false-completion guard (outside loop for efficiency)
        _FALSE_COMPLETION_RE = re.compile(
            r"expediente\s+(?:est[aá]\s+)?(?:complet|enviad|finaliz|cerrad|tramitad|list)"
            r"|(?:tu|el|su)\s+(?:caso|expediente)\s+(?:ha\s+sido|est[aá])\s+(?:enviad|complet|cerrad|registrad)"
            r"|hemos\s+(?:terminad|completad|finaliz|cerrad)\s+(?:el\s+)?(?:expediente|caso|proceso)"
            r"|ya\s+(?:hemos\s+)?(?:terminad|completad)\s+(?:el\s+)?(?:expediente|proceso)"
            r"|todo\s+(?:est[aá]|listo)\s+(?:completad|guardad|registrad)",
            re.IGNORECASE,
        )
        ai_response = ""
        context_updates: dict[str, Any] = {}
        tools_called: set[str] = set()
        pending_images: dict[str, Any] | None = None
        all_applied_flags: dict[str, Any] = {}
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2
        
        # Phase 3: Initialize retry state for validation error recovery
        retry_state = state.get("retry_state", create_empty_retry_state())

        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self._invoke_with_fallback(
                        llm_messages, tools, llm_error, conversation_id,
                    )

                # Track token usage
                await self._track_token_usage(conversation_id, response)

                # Check for tool calls
                tool_calls = getattr(response, "tool_calls", None)

                if not tool_calls:
                    ai_response = response.content or ""
                    
                    # Empty LLM response retry: if the LLM returned empty
                    # content AND no tool calls (e.g. DeepSeek HTTP 200 with
                    # empty body), retry once with a reprompt instead of
                    # breaking out to the safety-net generic error.
                    if not ai_response and iteration == 0:
                        self._logger.warning(
                            "empty_llm_response_retry",
                            iteration=iteration,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append({
                            "role": "system",
                            "content": (
                                "[SYSTEM]: Tu respuesta anterior estuvo vacía. "
                                "Por favor, responde al mensaje del usuario. "
                                "Si necesitas información, usa las herramientas disponibles."
                            ),
                        })
                        continue
                    
                    # ── Guard: false completion detection ───────────────────────
                    # Detect if the LLM declared the expediente as complete/sent
                    # in any sub-mode BEFORE REVIEW_SUMMARY, without having called
                    # finalizar_expediente(). This prevents the agent from lying to
                    # the user about the state of the case.
                    if (
                        ai_response
                        and sub_mode_name != REVIEW_SUMMARY
                        and "finalizar_expediente" not in tools_called
                        and validation_retries < MAX_VALIDATION_RETRIES
                        and _FALSE_COMPLETION_RE.search(str(ai_response))
                    ):
                            validation_retries += 1
                            self._logger.warning(
                                "false_completion_detected",
                                sub_mode=sub_mode_name,
                                retry=validation_retries,
                                conversation_id=conversation_id,
                            )
                            llm_messages.append({
                                "role": "system",
                                "content": (
                                    "[SISTEMA - ERROR CRÍTICO]: Has declarado que el expediente está completo "
                                    f"pero estamos en el sub-modo '{sub_mode_name}', NO en REVIEW_SUMMARY. "
                                    "NUNCA declares el expediente como completo, enviado o terminado hasta que "
                                    "el usuario haya confirmado el resumen final y hayas llamado a "
                                    "finalizar_expediente(). "
                                    "Continúa recogiendo los datos que corresponden a este sub-modo."
                                ),
                            })
                            continue

                    # Constraint validation (anti-hallucination)
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        is_valid, error_injection = await self._validate_response_constraints(
                            ai_response,
                            list(tools_called),
                            state,
                            current_mode_context=mode_context,  # Phase 1B: use updated context
                            available_tool_names={t.name for t in tools},
                        )
                        
                        if not is_valid and error_injection:
                            validation_retries += 1
                            self._logger.warning(
                                "constraint_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                                sub_mode=sub_mode_name,
                            )
                            # Phase 4B: Unified role "system" + IMPORTANT instruction
                            llm_messages.append({
                                "role": "system",
                                "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                            })
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        self._logger.error(
                            "constraint_retries_exhausted",
                            retries=validation_retries,
                            sub_mode=sub_mode_name,
                            conversation_id=conversation_id,
                        )
                        ai_response = "Disculpa, déjame reformularte la respuesta. ¿Podrías repetirme qué necesitas?"
                    
                    break

                # Execute tool calls
                llm_messages.append(self._ai_message_to_dict(response))

                for tool_call in tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    tools_called.add(tool_name)

                    self._logger.info(
                        "tool_call",
                        tool=tool_name,
                        sub_mode=sub_mode_name,
                        iteration=iteration + 1,
                    )

                    result = await self._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tools=tools,
                        iteration=iteration + 1,
                    )

                    # ═══════════════════════════════════════════════════════════
                    # Phase 3: Validation error retry logic
                    # ═══════════════════════════════════════════════════════════
                    is_val_error, error_dict = self._is_validation_error(result)
                    
                    if is_val_error and error_dict:  # Type guard
                        should_retry, retry_state = self._handle_validation_retry(
                            tool_name=tool_name,
                            error_dict=error_dict,
                            retry_state=retry_state,
                            llm_messages=llm_messages,
                        )
                        
                        if should_retry:
                            # Reprompt added to llm_messages, continue LLM loop
                            self._logger.info(
                                "validation_retry_triggered",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            break  # Exit tool loop, go to next iteration
                        else:
                            # Max retries reached - escalate
                            self._logger.warning(
                                "validation_escalation",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            return {
                                "ai_response": self._fallback.get_validation_reprompt(
                                    retry_state, self._policy
                                ),
                                "current_mode": "ESCALATION",
                                "escalation_triggered": True,
                                "escalation_reason": "max_validation_retries",
                                "retry_state": retry_state,
                                "mode_context": mode_context,
                            }
                    # ═══════════════════════════════════════════════════════════
                    # End Phase 3 validation retry logic
                    # ═══════════════════════════════════════════════════════════

                    # REFACTOR-001: Apply tool flags BEFORE extracting context
                    # Parse result for _apply_tool_flags (handles JSON string)
                    # Defensive: some tools (e.g. escalar_a_humano) return plain
                    # text, not JSON — guard against JSONDecodeError.
                    try:
                        result_dict = json.loads(result) if isinstance(result, str) else result
                    except (json.JSONDecodeError, ValueError):
                        result_dict = {"raw_text": result}
                    _apply_tool_flags(mode_context, result_dict, self._logger)

                    # Track all applied flags for final authority
                    parsed_flags = result_dict.get("_internal_flags", {}) if isinstance(result_dict, dict) else {}
                    all_applied_flags.update(parsed_flags)

                    # Extract context from tool results
                    tool_context = self._extract_context_from_tool(
                        tool_name, tool_args, result, mode_context,
                    )
                    context_updates.update(tool_context)

                    # Extract pending images from enviar_imagenes_ejemplo
                    if tool_name == "enviar_imagenes_ejemplo":
                        images_data = self._extract_pending_images(result)
                        if images_data:
                            pending_images = images_data

                    # Re-inject ContextVar after each tool call
                    # This ensures tools read updated state in subsequent iterations
                    mode_context.update(context_updates)
                    updated_state = dict(state)
                    updated_state["mode_context"] = mode_context
                    set_current_state(updated_state)
                    set_current_state_for_image_tools(updated_state)

                    llm_messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_call_id,
                    })

                    # ═══════════════════════════════════════════════════════════
                    # PHASE F-3: Fast-path break on sub-mode transition
                    # When a tool signals a change to expediente_sub_mode,
                    # stop the LLM loop immediately. The neutral tool message
                    # IS the response — the new sub-mode handles the next turn.
                    # This prevents the LLM from anticipating the next sub-mode's
                    # content in the same turn as the transition tool call.
                    #
                    # NOTE: We read `context_updates` (not mode_context) because
                    # mode_context was already mutated above (line 1245). The
                    # context_updates dict captures what the tool *just* changed,
                    # so checking it directly avoids a stale-value false-negative.
                    # ═══════════════════════════════════════════════════════════
                    new_sub_mode = context_updates.get("expediente_sub_mode")
                    if new_sub_mode and new_sub_mode != sub_mode_name.lower():
                        closing_message = ""
                        if isinstance(result_dict, dict):
                            closing_message = result_dict.get("message", "")
                        if closing_message:
                            ai_response = closing_message
                        self._logger.info(
                            "sub_mode_transition_fast_path_break",
                            from_sub_mode=sub_mode_name,
                            to_sub_mode=new_sub_mode,
                            tool=tool_name,
                            iteration=iteration + 1,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop — LLM should NOT iterate further

                    # ═══════════════════════════════════════════════════════════
                    # PHASE 1A: Fast-path break on transition signal
                    # When a tool signals _transition_to, stop immediately.
                    # The tool's message IS the response — no extra LLM iteration.
                    # ═══════════════════════════════════════════════════════════
                    if mode_context.get("_transition_to"):
                        transition_message = ""
                        if isinstance(result_dict, dict):
                            transition_message = (
                                result_dict.get("message", "")
                                or result_dict.get("texto", "")
                            )
                        if transition_message:
                            ai_response = transition_message
                        self._logger.info(
                            "transition_fast_path_break",
                            target=mode_context["_transition_to"],
                            tool=tool_name,
                            has_message=bool(transition_message),
                            sub_mode=sub_mode_name,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop

                # Fast-path: also break outer iteration loop on transition
                if mode_context.get("_transition_to"):
                    break

                # Fast-path: break outer iteration loop on sub-mode transition
                # context_updates has the new sub_mode from the tool; sub_mode_name
                # is the UPPER-CASED version of the current sub-mode (before transition).
                _new_sub = context_updates.get("expediente_sub_mode")
                if _new_sub and _new_sub != sub_mode_name.lower():
                    break

            else:
                self._logger.warning(
                    "max_tool_iterations",
                    sub_mode=sub_mode_name,
                    iterations=MAX_TOOL_ITERATIONS,
                )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, me ha llevado más tiempo del esperado. "
                        "¿Puedes repetir?"
                    )

            # ── 6. Build state updates ───────────────────────────────────────
            # Merge context: mode_context is base, context_updates adds structural data,
            # all_applied_flags has FINAL AUTHORITY over boolean flags
            updated_context = {**mode_context, **context_updates}
            # _internal_flags always win over stale context_updates values
            for key, value in all_applied_flags.items():
                if key.startswith("_"):
                    continue  # Skip internal keys like _transition_to
                updated_context[key] = value

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: Persist retry state
            }

            # Propagate mode transition if signaled by a tool
            transition_target = updated_context.pop("_transition_to", None)
            if transition_target:
                from agent.router.mode_transitions import validate_transition, get_preserve_keys
                from agent.state.conversation_state import transition_mode
                allowed, reason = validate_transition(self.mode_name, transition_target)
                if allowed:
                    preserve = get_preserve_keys(self.mode_name, transition_target)
                    transition_updates = transition_mode(
                        state, transition_target, preserve_keys=preserve,
                    )
                    # Merge transition updates, but keep our ai_response
                    saved_response = result_dict["ai_response"]
                    result_dict.update(transition_updates)
                    result_dict["ai_response"] = saved_response
                    self._logger.info(
                        "mode_transition_from_tool",
                        target=transition_target,
                        sub_mode=sub_mode_name,
                        conversation_id=conversation_id,
                    )
                else:
                    self._logger.warning(
                        "mode_transition_blocked",
                        target=transition_target,
                        reason=reason,
                        sub_mode=sub_mode_name,
                        conversation_id=conversation_id,
                    )

            # Bubble up pending images
            if pending_images:
                result_dict["pending_images"] = pending_images
                # Persist follow_up text so LLM sees it next turn (Bug A fix)
                follow_up = pending_images.get("follow_up_message")
                if follow_up:
                    updated_context["last_follow_up_sent"] = follow_up

            self._logger.info(
                "expediente_sub_mode_response",
                sub_mode=sub_mode_name,
                response_length=len(ai_response),
                tools_called=list(tools_called),
                has_pending_images=pending_images is not None,
            )

            # T-4: Clear stale transition marker after prompt consumed it this turn.
            # If a NEW transition happened via _extract_context_from_tool() during
            # this same turn, it will have re-set the flag in context_updates which
            # is already merged into updated_context — so we only clear if it was
            # NOT freshly set by a tool in this turn.
            if "just_transitioned_from" in updated_context and "just_transitioned_from" not in context_updates:
                updated_context.pop("just_transitioned_from", None)

            return result_dict

        finally:
            # ── 7. Cleanup ContextVars ──────────────────────────────────────
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()

    # ------------------------------------------------------------------
    # Context extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_context_from_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract mode context updates from tool results.

        Key updates:
        - Sub-mode transitions (expediente_sub_mode)
        - Element collection progress
        - Case completion status
        """
        updates: dict[str, Any] = {}

        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return updates

        if not isinstance(data, dict):
            return updates

        # Standard contract: tools can declare mode_context updates via _context_updates
        # This is the preferred mechanism for new tools (see tool_context_contract.py)
        if "_context_updates" in data:
            ctx_updates = data["_context_updates"]
            if isinstance(ctx_updates, dict):
                updates.update(ctx_updates)
                logger.debug(
                    "applied_context_updates_contract",
                    tool_name=tool_name,
                    keys=list(ctx_updates.keys()),
                )

        # Detect sub-mode transitions from tool metadata
        if tool_name in ("completar_elemento_actual", "confirmar_fotos_elemento"):
            # Both tools can signal that all elements are done (e.g. last element
            # has no required fields → confirmar_fotos_elemento completes it directly
            # without going through completar_elemento_actual).
            if data.get("all_elements_complete"):
                updates["expediente_sub_mode"] = COLLECT_BASE_DOCS
                updates["just_transitioned_from"] = COLLECT_ELEMENT_DATA

        elif tool_name == "confirmar_documentacion_base":
            if data.get("success"):
                updates["expediente_sub_mode"] = COLLECT_PERSONAL
                updates["just_transitioned_from"] = COLLECT_BASE_DOCS

        elif tool_name == "actualizar_datos_expediente":
            # Detect transition by next_step in result (not by "seccion" param which doesn't exist)
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step == "collect_vehicle":
                    updates["expediente_sub_mode"] = COLLECT_VEHICLE
                    updates["just_transitioned_from"] = COLLECT_PERSONAL
                elif next_step == "collect_workshop":
                    updates["expediente_sub_mode"] = COLLECT_WORKSHOP
                    updates["just_transitioned_from"] = COLLECT_VEHICLE

        elif tool_name == "actualizar_datos_taller":
            if data.get("success"):
                next_step = data.get("next_step", "review_summary")
                if next_step == "collect_workshop":
                    # Still collecting workshop data (taller_propio=True, need details)
                    pass  # Stay in COLLECT_WORKSHOP, don't transition
                else:
                    updates["expediente_sub_mode"] = REVIEW_SUMMARY
                    updates["just_transitioned_from"] = COLLECT_WORKSHOP

        elif tool_name == "finalizar_expediente":
            if data.get("success"):
                # Mark as completed — transition to COMPLETED mode
                updates["expediente_completed"] = True
                updates["_transition_to"] = "COMPLETED"

        elif tool_name == "cancelar_expediente":
            if data.get("success"):
                updates["expediente_cancelled"] = True
                updates["_transition_to"] = "PRESUPUESTO_MODE"

        elif tool_name == "editar_expediente":
            # User wants to edit a section from REVIEW_SUMMARY — route back to that sub-mode
            if data.get("success"):
                next_step = data.get("next_step")
                _STEP_TO_SUBMODE = {
                    "collect_personal": COLLECT_PERSONAL,
                    "collect_vehicle": COLLECT_VEHICLE,
                    "collect_workshop": COLLECT_WORKSHOP,
                    "collect_base_docs": COLLECT_BASE_DOCS,
                    "collect_element_data": COLLECT_ELEMENT_DATA,
                }
                if next_step in _STEP_TO_SUBMODE:
                    updates["expediente_sub_mode"] = _STEP_TO_SUBMODE[next_step]
                    updates["editing_from_review"] = True

        # Track element progress
        if tool_name in ("confirmar_fotos_elemento", "guardar_datos_elemento", "completar_elemento_actual"):
            if "current_element_index" in data:
                updates["current_element_index"] = data["current_element_index"]
            if "element_phase" in data:
                updates["element_phase"] = data["element_phase"]

        # Extract field_keys from tool results so they can be injected into the
        # system prompt.  This prevents the LLM from guessing/abbreviating keys.
        if tool_name in ("confirmar_fotos_elemento", "obtener_campos_elemento"):
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys
        elif tool_name == "guardar_datos_elemento":
            # After saving, update field_keys with remaining (missing) fields
            # so the prompt stays current for the next turn.
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys

            # If all required fields are collected, signal the LLM to call
            # completar_elemento_actual() immediately.  Without this, the LLM
            # might generate a confirmation message and skip the tool call,
            # leaving the element stuck in "pending_data" forever.
            if data.get("all_required_collected") and data.get("action") == "ELEMENT_DATA_COMPLETE":
                updates["element_data_all_collected"] = True
                # Clear stale field_keys — there's nothing left to ask
                updates["current_element_field_keys"] = None
                logger.info(
                    "element_data_complete_signal_set",
                    element_code=data.get("element_code"),
                )
            else:
                # Ensure the flag is cleared if data is still incomplete
                updates["element_data_all_collected"] = False
        elif tool_name == "completar_elemento_actual":
            # Element done — clear stale field_keys and completion signal so they
            # don't leak to next element
            updates["current_element_field_keys"] = None
            updates["element_data_all_collected"] = False

        # FSM compatibility: v1 tools return state updates via fsm_compat layer.
        # Tools wrap updates in: {"fsm_state_update": {"case_collection": {actual_updates}}}
        # We need to unwrap BOTH levels to extract the actual state changes.
        #
        # Level 1: data["fsm_state_update"]["case_collection"] (standard v1 tool pattern)
        # Level 2: data["case_collection"] (direct — fallback if tool returns flat)
        if "fsm_state_update" in data:
            fsm_update = data["fsm_state_update"]
            if isinstance(fsm_update, dict):
                case_coll = fsm_update.get("case_collection", {})
                if isinstance(case_coll, dict) and case_coll:
                    updates.update(case_coll)
                    logger.debug(
                        "applied_fsm_state_update_to_mode_context",
                        tool_name=tool_name,
                        fsm_keys=list(case_coll.keys()),
                    )
        elif "case_collection" in data:
            fsm_updates = data["case_collection"]
            if isinstance(fsm_updates, dict):
                updates.update(fsm_updates)
                logger.debug(
                    "applied_case_collection_to_mode_context",
                    tool_name=tool_name,
                    fsm_keys=list(fsm_updates.keys()),
                )

        return updates

    @staticmethod
    def _extract_pending_images(result: str) -> dict[str, Any] | None:
        """Extract pending images from enviar_imagenes_ejemplo result."""
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(data, dict):
            return None

        return data.get("_pending_images")

    # ------------------------------------------------------------------
    # LLM helpers (shared pattern)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_llm(tools: list) -> ChatOpenAI:
        """Get configured LLM instance with tools bound."""
        settings = get_settings()

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=1500,
            default_headers={
                "HTTP-Referer": settings.SITE_URL,
                "X-Title": settings.SITE_NAME,
            },
        )

        if tools:
            llm = llm.bind_tools(tools)

        return llm

    async def _invoke_with_fallback(
        self,
        messages: list[dict[str, Any]],
        tools: list,
        original_error: Exception,
        conversation_id: str,
    ) -> Any:
        """Try Ollama fallback when cloud LLM fails."""
        from openai import (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            APIStatusError,
        )

        if not isinstance(
            original_error,
            (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError),
        ):
            raise original_error

        self._logger.warning(
            "cloud_llm_failed_trying_ollama",
            error_type=type(original_error).__name__,
            conversation_id=conversation_id,
        )

        try:
            from langchain_ollama import ChatOllama

            settings = get_settings()
            ollama_llm = ChatOllama(
                model=settings.LOCAL_CAPABLE_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                temperature=0.3,
            )
            if tools:
                ollama_llm = ollama_llm.bind_tools(tools)

            response = await ollama_llm.ainvoke(messages)
            self._logger.info("ollama_fallback_succeeded", conversation_id=conversation_id)
            return response

        except Exception:
            self._logger.warning("ollama_fallback_failed", conversation_id=conversation_id)
            raise original_error

    # _execute_tool inherited from BaseModeNode

    @staticmethod
    def _build_client_context(state: ConversationState) -> str:
        """Build client-specific context string for the prompt."""
        parts: list[str] = []

        client_type = state.get("client_type", "particular")
        type_display = "PROFESIONAL" if client_type == "professional" else "PARTICULAR"
        parts.append(f"Cliente: **{type_display}**")

        user_name = state.get("user_name")
        if user_name:
            parts.append(f"Nombre: {user_name}")

        return "\n".join(parts)

    @staticmethod
    def _ai_message_to_dict(response: Any) -> dict[str, Any]:
        """Convert an LLM AIMessage to a dict for the messages list."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if hasattr(response, "tool_calls") and response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                }
                for tc in response.tool_calls
            ]
        return msg

    @staticmethod
    def _log_token_usage(response: Any, conversation_id: str) -> None:
        """Log token usage from LLM response metadata."""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.debug(
                "llm_token_usage",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                conversation_id=conversation_id,
            )


# ---------------------------------------------------------------------------
# Tool registries per sub-mode
# ---------------------------------------------------------------------------

def _get_element_data_tools() -> list:
    """Tools for COLLECT_ELEMENT_DATA sub-mode."""
    from agent.tools.element_data_tools import (
        obtener_campos_elemento,
        guardar_datos_elemento,
        confirmar_fotos_elemento,
        completar_elemento_actual,
        obtener_progreso_elementos,
        reenviar_imagenes_elemento,
    )
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.case_tools import (
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Element data collection
        obtener_campos_elemento,
        guardar_datos_elemento,
        confirmar_fotos_elemento,
        completar_elemento_actual,
        obtener_progreso_elementos,
        reenviar_imagenes_elemento,
        # Images
        enviar_imagenes_ejemplo,
        # Case management
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        # Universal
        escalar_a_humano,
    ]


def _get_base_docs_tools() -> list:
    """Tools for COLLECT_BASE_DOCS sub-mode."""
    from agent.tools.element_data_tools import confirmar_documentacion_base
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.case_tools import (
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        confirmar_documentacion_base,
        enviar_imagenes_ejemplo,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_personal_tools() -> list:
    """Tools for COLLECT_PERSONAL sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_vehicle_tools() -> list:
    """Tools for COLLECT_VEHICLE sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_workshop_tools() -> list:
    """Tools for COLLECT_WORKSHOP sub-mode."""
    from agent.tools.case_tools import (
        actualizar_datos_taller,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        actualizar_datos_taller,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
        escalar_a_humano,
    ]


def _get_review_tools() -> list:
    """Tools for REVIEW_SUMMARY sub-mode."""
    from agent.tools.case_tools import (
        finalizar_expediente,
        editar_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        finalizar_expediente,
        editar_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        escalar_a_humano,
    ]


def _get_all_expediente_tools() -> list:
    """Get all expediente tools (for reference)."""
    # Combine all sub-mode tools (removing duplicates)
    all_tools_nested = [
        _get_element_data_tools(),
        _get_base_docs_tools(),
        _get_personal_tools(),
        _get_vehicle_tools(),
        _get_workshop_tools(),
        _get_review_tools(),
    ]
    
    # Flatten and deduplicate by tool name
    seen_names: set[str] = set()
    all_tools: list = []
    for tool_list in all_tools_nested:
        for tool in tool_list:
            if tool.name not in seen_names:
                seen_names.add(tool.name)
                all_tools.append(tool)
    
    return all_tools

