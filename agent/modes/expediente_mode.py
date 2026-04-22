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

import hashlib
import json
import re
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any

import structlog

from agent.services.expediente_constants import (
    CERT_SUPPLEMENT_EUR,
    STEP_LABELS,
    TOTAL_STEPS,
    step_prefix,
)

if TYPE_CHECKING:
    from agent.services.element_state_service import ElementStateService
    from agent.services.intent_classifier import IntentClassifier
    from database.models import Case, User
from agent.modes.presupuesto_mode import _apply_tool_flags
from agent.services.expediente_onboarding import (
    build_new_expediente_case_instructions,
    build_resume_expediente_case_instructions,
)
from agent.services.case_image_batch_service import get_case_image_batch_service
from agent.state.conversation_state import ConversationState
from agent.utils.expediente_types import CollectionStep
from agent.utils.validation import PHOTO_COMPLETION_INTENT_RE
from database.connection import get_async_session
from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Module-level helpers extracted to submodos/_shared.py (Phase A refactor)
from agent.modes.submodos._shared import *  # noqa: F401, F403 — backward-compat re-export
from agent.utils.expediente_types import CollectionStep  # noqa: F401 — enum replacing module-level string constants

# Phase B: all 6 handler modules
from agent.modes.submodos.collect_personal import PersonalHandler as _PersonalHandler
from agent.modes.submodos.collect_vehicle import VehicleHandler as _VehicleHandler
from agent.modes.submodos.collect_workshop import WorkshopHandler as _WorkshopHandler
from agent.modes.submodos.collect_base_docs import BaseDocsHandler as _BaseDocsHandler
from agent.modes.submodos.review_summary import ReviewHandler as _ReviewHandler
from agent.modes.submodos.collect_element_data import (
    ElementDataHandler as _ElementDataHandler,
)

_personal_handler = _PersonalHandler()
_vehicle_handler = _VehicleHandler()
_workshop_handler = _WorkshopHandler()
_base_docs_handler = _BaseDocsHandler()
_review_handler = _ReviewHandler()
_element_data_handler = _ElementDataHandler()



class ExpedienteModeNode:
    """
    EXPEDIENTE_MODE: Guard + context helpers for the expediente subgraph.

    The live message-processing path runs through ``expediente_subgraph_node``
    (agent/graph/expediente_subgraph.py), NOT through this class.  This class
    survives only to provide:
    - ``_guard_photo_completion_intent``: deterministic photo-confirmation gate
    - ``extract_context_from_tool``:  static context-extraction helper
    - ``_initialize_mode_context`` and recovery helpers: DB bootstrap on entry
    """

    def __init__(self) -> None:
        self.mode_name = "EXPEDIENTE_MODE"
        self._logger = logger.bind(mode=self.mode_name)
        self._tools_cache: dict[str, list] = {}  # Tools per sub-mode
        self._element_state_svc: ElementStateService | None = None
        self._intent_classifier_svc: IntentClassifier | None = None

    def _get_element_state_svc(self) -> ElementStateService | None:
        """Return ElementStateService singleton (always enabled)."""
        if self._element_state_svc is None:
            from agent.services.element_state_service import get_element_state_service

            self._element_state_svc = get_element_state_service()
        return self._element_state_svc

    def _get_intent_classifier_svc(self) -> IntentClassifier | None:
        """Return IntentClassifier singleton (always enabled)."""
        if self._intent_classifier_svc is None:
            from agent.services.intent_classifier import get_intent_classifier

            self._intent_classifier_svc = get_intent_classifier()
        return self._intent_classifier_svc

    # ------------------------------------------------------------------
    # Abstract method implementations (removed: _process_message — see expediente_subgraph_node)


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

        Handles two entry paths:
        1. Normal entry (from PRE_EXPEDIENTE_MODE confirmation) — queries by conversation_id
        2. Recovery entry (from preprocess_node after checkpoint expiry) — uses
           ``pending_recovery_case`` already injected into mode_context by preprocess_node.
           In this case, the LLM is guided to offer the user a warm resume greeting.

        Args:
            conversation_id: Conversation ID (new thread after checkpoint expiry)
            current_context: Current mode_context (may contain pending_recovery_case)
            state: Full conversation state (for user_id access before ContextVar is set)

        Returns:
            Initialized mode_context with case data
        """
        # ── Recovery path: orphaned expediente detected by preprocess_node ──────
        # preprocess_node injected pending_recovery_case when it found an active
        # Case in PostgreSQL belonging to this user but from a different conversation
        # thread (i.e. the Redis checkpoint expired).
        pending_recovery = current_context.get("pending_recovery_case")
        if pending_recovery and isinstance(pending_recovery, dict):
            return await self._build_recovery_context(
                conversation_id=conversation_id,
                recovery_data=pending_recovery,
                current_context=current_context,
            )

        # ── Normal path: query by conversation_id ──────────────────────────────
        from database.connection import get_async_session
        from database.models import Case

        try:
            async with get_async_session() as session:
                from sqlalchemy import select

                # Find active case for this conversation
                result = await session.execute(
                    select(Case)
                    .where(Case.conversation_id == conversation_id)
                    .where(
                        Case.status.in_(["collecting", "pending_review", "in_progress"])
                    )
                    .order_by(Case.created_at.desc())
                )
                case = result.scalar_one_or_none()

                if not case:
                    logger.warning(
                        "no_active_case_for_expediente_attempting_auto_create",
                        conversation_id=conversation_id,
                    )
                    # Auto-create case from mode_context data
                    # (carried from PRESUPUESTO → EXPEDIENTE via shared_context)
                    return await self._auto_create_case(
                        conversation_id,
                        current_context,
                        state,
                    )

                # Resolve category_slug from relationship (Case has no
                # category_slug column — only category_id FK).
                category_slug = (
                    case.category.slug
                    if case.category
                    else current_context.get("categoria_slug", "")
                )
                codes = case.element_codes or []

                from sqlalchemy import select as sa_select
                from database.models import CaseElementData

                # ── Reconcile element progress from DB ──────────────────────
                # When re-entering EXPEDIENTE_MODE (e.g. after reconnect or
                # restart), rebuild element_data_status and current_element_index
                # from persisted CaseElementData records instead of resetting
                # everything to 0/pending. This prevents the agent from asking
                # for photos that were already confirmed.
                ced_result = await session.execute(
                    sa_select(CaseElementData).where(CaseElementData.case_id == case.id)
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

                    reconciled_index = (
                        min(first_incomplete_idx, len(codes) - 1) if codes else 0
                    )
                    reconciled_phase = first_incomplete_phase

                    # Determine if all elements are already completed
                    all_elements_done = (
                        all(v == "completed" for v in reconciled_status.values())
                        if reconciled_status
                        else False
                    )
                else:
                    # No DB records yet — start fresh
                    reconciled_status = {code: "pending" for code in codes}
                    reconciled_index = 0
                    reconciled_phase = "photos"
                    all_elements_done = False

                # ── Override reconciled values from ElementStateService ────
                # The service is the authoritative source of truth for element
                # completion.  Override the dict-based reconciliation above.
                _ess_v2 = self._get_element_state_svc()
                if _ess_v2 is not None and codes:
                    try:
                        all_elements_done = await _ess_v2.is_all_elements_complete(
                            str(case.id), codes
                        )
                        _current_el_code_v2 = await _ess_v2.get_current_element(
                            str(case.id), codes
                        )
                        if (
                            _current_el_code_v2 is not None
                            and _current_el_code_v2 in codes
                        ):
                            reconciled_index = codes.index(_current_el_code_v2)
                            # Derive phase from DB status
                            _el_state_v2 = await _ess_v2.get_element_state(
                                str(case.id), _current_el_code_v2
                            )
                            if _el_state_v2 is not None:
                                _db_status_v2 = ced_by_code.get(
                                    _current_el_code_v2, "pending_photos"
                                )
                                reconciled_phase = (
                                    "data"
                                    if _db_status_v2 == "pending_data"
                                    else "photos"
                                )
                        elif all_elements_done:
                            reconciled_index = len(codes) - 1
                        logger.info(
                            "reconciled_from_element_state_service",
                            case_id=str(case.id),
                            all_elements_done=all_elements_done,
                            current_element=_current_el_code_v2,
                            reconciled_index=reconciled_index,
                            reconciled_phase=reconciled_phase,
                        )
                    except Exception as _ess_err:
                        logger.warning(
                            "element_state_service_reconcile_failed",
                            case_id=str(case.id),
                            error=str(_ess_err),
                        )
                        # Fallback: keep dict-based values computed above

                logger.info(
                    "reconciled_element_progress_from_db",
                    case_id=str(case.id),
                    total_elements=len(codes),
                    completed=sum(
                        1 for v in reconciled_status.values() if v == "completed"
                    ),
                    current_index=reconciled_index,
                    all_done=all_elements_done,
                )

                # Determine correct sub_mode based on reconciled element state
                # Prefer sub_mode already in context (set by previous turns),
                # but if all elements are done and context says collect_element_data,
                # advance to collect_base_docs automatically.
                persisted_sub_mode = current_context.get(
                    "expediente_sub_mode", CollectionStep.COLLECT_ELEMENT_DATA.value
                )
                if all_elements_done and persisted_sub_mode == CollectionStep.COLLECT_ELEMENT_DATA.value:
                    reconciled_sub_mode = CollectionStep.COLLECT_BASE_DOCS.value
                    logger.info(
                        "auto_advanced_sub_mode_all_elements_done",
                        case_id=str(case.id),
                        from_sub_mode=CollectionStep.COLLECT_ELEMENT_DATA.value,
                        to_sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
                    )
                else:
                    reconciled_sub_mode = persisted_sub_mode

                # Load base doc descriptions from DB/cache for this category
                (
                    base_doc_descriptions,
                    loaded_category_data,
                ) = await _load_base_doc_descriptions(category_slug)
                hydrated_context = await _hydrate_case_context_from_db(
                    case,
                    case.user,
                    reconciled_sub_mode,
                )

                # Build FSM state so element_data_tools can work on
                # the first turn after re-entering EXPEDIENTE_MODE.
                existing_fsm_state = {
                    "case_collection": {
                        "step": hydrated_context.get(
                            "fsm_step", CollectionStep.COLLECT_ELEMENT_DATA.value
                        ),
                        "case_id": str(case.id),
                        "category_slug": category_slug,
                        "category_id": str(case.category_id)
                        if case.category_id
                        else None,
                        "element_codes": codes,
                        "current_element_index": reconciled_index,
                        "element_phase": reconciled_phase,
                        "element_data_status": reconciled_status,
                        "base_docs_received": hydrated_context.get(
                            "base_docs_received", False
                        ),
                        "base_doc_descriptions": base_doc_descriptions,
                        "received_images": [],
                        "tariff_tier_id": str(case.tariff_tier_id)
                        if case.tariff_tier_id
                        else None,
                        "tariff_amount": float(case.tariff_amount)
                        if case.tariff_amount
                        else None,
                        "taller_propio": hydrated_context.get("taller_propio"),
                        "taller_data": hydrated_context.get("taller_data"),
                        "retry_count": 0,
                    }
                }

                # P2.4: Resolve display names — prefer elementos_confirmados
                # from current_context (rich variant data from presupuesto),
                # fall back to DB query for backward compatibility.
                _ctx_confirmed: list[dict[str, Any]] | None = current_context.get(
                    "elementos_confirmados"
                )
                _init_display_names: dict[str, str] = {}
                if _ctx_confirmed and isinstance(_ctx_confirmed, list):
                    _init_display_names = {
                        elem.get("code", ""): elem.get("name") or elem.get("code", "")
                        for elem in _ctx_confirmed
                        if isinstance(elem, dict) and elem.get("code")
                    }
                # Supplement/fallback: DB query for any codes not in confirmed data
                _missing_init = [c for c in codes if c not in _init_display_names]
                if _missing_init:
                    _category_id_str = str(case.category_id) if case.category_id else ""
                    _db_display_names = await _resolve_element_display_names(
                        _missing_init, _category_id_str
                    )
                    _init_display_names.update(_db_display_names)

                # Initialize context with case data
                initialized_context = {
                    **current_context,
                    "case_id": str(case.id),
                    "category_id": str(case.category_id) if case.category_id else None,
                    "category_slug": category_slug,
                    "element_codes": codes,
                    # P2.4: display names from elementos_confirmados + DB fallback
                    "element_display_names": _init_display_names,
                    "current_element_index": reconciled_index,
                    "element_phase": reconciled_phase,
                    "element_data_status": reconciled_status,
                    "base_docs_received": hydrated_context.get(
                        "base_docs_received", False
                    ),
                    "base_doc_descriptions": base_doc_descriptions,
                    "category_data": loaded_category_data
                    or current_context.get("category_data"),
                    "personal_data": hydrated_context.get("personal_data", {}),
                    "vehicle_data": hydrated_context.get("vehicle_data", {}),
                    "taller_propio": hydrated_context.get("taller_propio"),
                    "taller_data": hydrated_context.get("taller_data"),
                    "tariff_tier_id": str(case.tariff_tier_id)
                    if case.tariff_tier_id
                    else None,
                    "tariff_amount": float(case.tariff_amount)
                    if case.tariff_amount
                    else None,
                    "received_images": [],
                    "_fsm_state_init": existing_fsm_state,
                    "expediente_sub_mode": reconciled_sub_mode,
                }

                logger.info(
                    "initialized_mode_context_from_db",
                    case_id=str(case.id),
                    element_count=len(codes),
                    category_slug=category_slug,
                    has_display_names=bool(_init_display_names),
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

    # _auto_create_case and _build_recovery_context removed (T-9).
    # Duplicated logic now lives in agent.services.expediente_init,
    # which is used by the expediente subgraph entry_router (AD-4).

    # ------------------------------------------------------------------
    # Layer A: deterministic pre-loop guard — photo completion intent
    # ------------------------------------------------------------------

    async def _guard_photo_completion_intent(
        self,
        user_message: str,
        mode_context: dict[str, Any],
        state: dict[str, Any],
        conversation_id: str,
        force: bool = False,
    ) -> bool:
        """
        Deterministic pre-loop guard for photo-completion intent.

        Fires only when BOTH conditions hold (unless ``force=True``):
        1. Current element_phase is "photos" (waiting for user to confirm photos).
        2. User message matches ``_PHOTO_COMPLETION_INTENT_RE`` (e.g. "listo",
           "ya", "enviadas", "hechas", …).

        When it fires, calls ``confirmar_fotos_elemento`` directly with
        ``usuario_confirma=True`` — without going through the LLM — and
        updates ``mode_context`` in-place so the subsequent ``_run_llm_loop``
        sees the advanced phase and avoids re-asking for photos.

        Args:
            user_message: Raw user text for regex matching.
            mode_context: Mutable mode context dict (updated in-place on fire).
            state: Full conversation state (needed to set ContextVars for tool).
            conversation_id: For structured logging.
            force: When True, skip the regex check and go straight to calling
                ``confirmar_fotos_elemento``. Used by the Layer B coherence
                interceptor when the LLM already called ``guardar_datos_elemento``
                while ``element_phase=="photos"`` — the guardar tool's error
                response signals the intent without the user having said "listo".

        Returns:
            True if the guard fired (phase advanced), False if it was a no-op.
        """
        # Condition 1: only fire when waiting for photo confirmation
        if mode_context.get("element_phase") != "photos":
            return False

        # Condition 2: user message must signal photo completion (skipped when force=True)
        # V2: Use IntentClassifier to distinguish COMPLETION_SIGNAL from REJECTION,
        # which fixes the "no es necesario" bug where the regex matched rejection phrases.
        if not force:
            _ic_v2 = self._get_intent_classifier_svc()
            if _ic_v2 is not None:
                # Build classification context from current element state
                from agent.services.intent_classifier import ClassificationContext

                _ic_element_code = mode_context.get("current_element_code") or ""
                _ic_pending_fields: list[str] = []
                _el_states: dict[str, Any] = mode_context.get("element_states") or {}
                _el_entry = _el_states.get(_ic_element_code, {})
                # Use display_name from 7-state dict if available
                _ic_element_name: str = _el_entry.get("display_name", _ic_element_code)

                # Extract last agent message for context
                _messages_hist = (
                    state.get("messages", []) if isinstance(state, dict) else []
                )
                _last_agent_msg: str = ""
                for _m in reversed(_messages_hist):
                    if isinstance(_m, dict) and _m.get("role") == "assistant":
                        _last_agent_msg = _m.get("content", "")[:200]
                        break
                    elif hasattr(_m, "type") and getattr(_m, "type") == "ai":
                        _last_agent_msg = str(getattr(_m, "content", ""))[:200]
                        break

                _has_images = bool(
                    isinstance(state, dict) and state.get("incoming_attachments")
                )

                _ic_ctx = ClassificationContext(
                    current_phase="photos",
                    current_element_name=_ic_element_name,
                    pending_fields=_ic_pending_fields,
                    last_agent_message=_last_agent_msg,
                )
                try:
                    _ic_result = await _ic_v2.classify(
                        user_message, _ic_ctx, _has_images
                    )
                    from agent.services.intent_classifier import UserIntent

                    if _ic_result.intent == UserIntent.REJECTION:
                        # User explicitly rejected / said "not needed" — do NOT fire guard
                        logger.info(
                            "photo_guard_skipped_rejection_intent",
                            conversation_id=conversation_id,
                            intent=_ic_result.intent.value,
                            confidence=_ic_result.confidence,
                            message_preview=user_message[:60],
                        )
                        return False
                    elif _ic_result.intent != UserIntent.COMPLETION_SIGNAL:
                        # Not a completion signal — fall through to regex as final arbiter
                        if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                            return False
                except Exception as _ic_err:
                    logger.warning(
                        "photo_guard_intent_classifier_failed",
                        conversation_id=conversation_id,
                        error=str(_ic_err),
                    )
                    # Fallback to regex on error
                    if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                        return False
            else:
                # IntentClassifier not available: regex-only fallback
                if not _PHOTO_COMPLETION_INTENT_RE.search(user_message):
                    return False

        logger.info(
            "photo_guard_triggered",
            conversation_id=conversation_id,
            element_code=mode_context.get("current_element_code"),
            element_index=mode_context.get("current_element_index"),
            message_preview=user_message[:60],
        )

        try:
            # TASK-09 Layer A hardening: Set element state to "confirming_photos" BEFORE
            # calling confirmar_fotos_elemento so the state machine reflects the intent
            # immediately (even if the tool is still polling).  Layer A's post-call
            # logic below will advance to the final state once the tool returns.
            _pre_call_el_code: str | None = mode_context.get(
                "current_element_code"
            ) or (
                (mode_context.get("element_codes") or [None])[
                    mode_context.get("current_element_index", 0)
                ]
                if mode_context.get("element_codes")
                else None
            )
            if _pre_call_el_code:
                _set_element_state(
                    mode_context,
                    _pre_call_el_code,
                    ELEMENT_STATE_CONFIRMING_PHOTOS,
                )
                logger.debug(
                    "photo_guard_pre_call_state_set",
                    conversation_id=conversation_id,
                    element_code=_pre_call_el_code,
                    state=ELEMENT_STATE_CONFIRMING_PHOTOS,
                )

            # Import and call the tool directly (bypasses LLM)
            from agent.tools.element_data_tools import confirmar_fotos_elemento

            guard_result = await confirmar_fotos_elemento.ainvoke(
                {"usuario_confirma": True}
            )

            # Parse result (tool may return dict or JSON string)
            try:
                guard_result_dict: dict[str, Any] = (
                    json.loads(guard_result)
                    if isinstance(guard_result, str)
                    else guard_result
                )
            except (json.JSONDecodeError, ValueError):
                guard_result_dict = {}

            if not isinstance(guard_result_dict, dict):
                guard_result_dict = {}

            # Apply tool flags to mode_context in-place
            _apply_tool_flags(mode_context, guard_result_dict, self._logger)

            # Extract context updates (phase advance, sub-mode transition, etc.)
            guard_context = ExpedienteModeNode.extract_context_from_tool(
                "confirmar_fotos_elemento",
                {"usuario_confirma": True},
                guard_result
                if isinstance(guard_result, str)
                else json.dumps(guard_result_dict),
                mode_context,
            )
            mode_context.update(guard_context)

            # TASK-05 + TASK-09: Update per-element 7-state machine.
            # After confirmar_fotos_elemento fires and mode_context is updated:
            # - new element_phase == "data" → photos confirmed → advance to photos_confirmed
            # - all_elements_complete → element is fully done (no data fields)
            # - else → still in confirming state (poll in-flight; pre-call already set it)
            #
            # CRITICAL: Use _pre_call_el_code (captured BEFORE the tool call at line ~1774),
            # NOT mode_context, because extract_context_from_tool may have already advanced
            # current_element_index to the NEXT element. Re-deriving from the mutated context
            # would target the wrong element (bug: photo_guard_premature_state_advance).
            if _pre_call_el_code:
                _raw_photos_count = guard_result_dict.get("photos_count", 0)
                _guard_photos_count: int = (
                    _raw_photos_count if isinstance(_raw_photos_count, int) else 0
                )
                if _guard_photos_count == 0 and not guard_result_dict.get("success"):
                    # Phase-1 poll found 0 photos (retry path)
                    _set_element_state(
                        mode_context,
                        _pre_call_el_code,
                        ELEMENT_STATE_RETRY_PHOTOS,
                    )
                elif guard_result_dict.get("all_elements_complete"):
                    # confirmar_fotos_elemento completed the last element (no data fields)
                    _set_element_state(
                        mode_context,
                        _pre_call_el_code,
                        ELEMENT_STATE_ELEMENT_COMPLETE,
                        data_complete=True,
                    )
                elif mode_context.get("element_phase") == "data":
                    # Photos confirmed — advancing to data collection
                    _set_element_state(
                        mode_context,
                        _pre_call_el_code,
                        ELEMENT_STATE_PHOTOS_CONFIRMED,
                        photos_count=_guard_photos_count,
                    )
                else:
                    # Poll in progress (confirming_photos)
                    _set_element_state(
                        mode_context,
                        _pre_call_el_code,
                        ELEMENT_STATE_CONFIRMING_PHOTOS,
                    )

            # Detect divergence between pre-call element and post-context element
            _post_context_el_code: str | None = mode_context.get(
                "current_element_code"
            ) or (
                (mode_context.get("element_codes") or [None])[
                    mode_context.get("current_element_index", 0)
                ]
                if mode_context.get("element_codes")
                else None
            )
            if _pre_call_el_code != _post_context_el_code:
                logger.info(
                    "photo_guard_post_call_element_divergence",
                    conversation_id=conversation_id,
                    pre_call_element=_pre_call_el_code,
                    post_context_element=_post_context_el_code,
                )

            logger.info(
                "photo_guard_completed",
                conversation_id=conversation_id,
                tool_success=guard_result_dict.get("success", False),
                state_target_element=_pre_call_el_code,
                new_element_phase=mode_context.get("element_phase"),
                triggered_transition=bool(guard_context.get("expediente_sub_mode")),
                all_elements_complete=guard_result_dict.get(
                    "all_elements_complete", False
                ),
            )

            return True

        except Exception as guard_error:
            # Non-fatal: log warning and let LLM loop handle it normally
            self._logger.warning(
                "photo_guard_failed",
                conversation_id=conversation_id,
                error=str(guard_error),
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Static helpers (extracted from ExpedienteLoopEngine)
    # ------------------------------------------------------------------

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
    def extract_context_from_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        result: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract mode context updates from tool results.

        Extracted from ExpedienteLoopEngine to allow use without the old loop.
        Handles sub-mode transitions, element collection progress, and FSM updates.
        """
        updates: dict[str, Any] = {}

        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return updates

        if not isinstance(data, dict):
            return updates

        # Standard contract: tools can declare mode_context updates via _context_updates
        if "_context_updates" in data:
            ctx_updates = data["_context_updates"]
            if isinstance(ctx_updates, dict):
                updates.update(ctx_updates)

        # Detect sub-mode transitions from tool metadata
        # Skip transition detection on error results to prevent false transitions.
        if tool_name in ("completar_elemento_actual", "confirmar_fotos_elemento"):
            if data.get("error") or data.get("success") is False:
                pass
            elif data.get("all_elements_complete"):
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.COLLECT_ELEMENT_DATA.value,
                    to_sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
                    tool_name=tool_name,
                )

        elif tool_name == "confirmar_documentacion_base":
            if (
                data.get("success")
                and not data.get("already_confirmed")
                and not data.get("escalated")
            ):
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=CollectionStep.COLLECT_BASE_DOCS.value,
                    to_sub_mode=CollectionStep.COLLECT_PERSONAL.value,
                    tool_name=tool_name,
                )

        elif tool_name in ("actualizar_datos_personales", "actualizar_datos_vehiculo"):
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step == "collect_vehicle":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=CollectionStep.COLLECT_PERSONAL.value,
                        to_sub_mode=CollectionStep.COLLECT_VEHICLE.value,
                        tool_name=tool_name,
                    )
                elif next_step == "collect_workshop":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=CollectionStep.COLLECT_VEHICLE.value,
                        to_sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
                        tool_name=tool_name,
                    )

        elif tool_name == "actualizar_datos_taller":
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step is None:
                    pass
                elif next_step == "collect_workshop":
                    pass  # Stay in COLLECT_WORKSHOP
                else:
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
                        to_sub_mode=CollectionStep.REVIEW_SUMMARY.value,
                        tool_name=tool_name,
                    )

        elif tool_name == "finalizar_expediente":
            if data.get("success"):
                updates["expediente_completed"] = True
                updates["_transition_to"] = "PRE_EXPEDIENTE_MODE"

        elif tool_name == "iniciar_expediente":
            if data.get("success"):
                flags = data.get("_internal_flags", {})
                if isinstance(flags, dict) and flags.get("intro_already_sent"):
                    updates["intro_already_sent"] = True

        elif tool_name == "cancelar_expediente":
            if data.get("success"):
                updates["expediente_cancelled"] = True
                updates["_transition_to"] = "PRE_EXPEDIENTE_MODE"

        elif tool_name == "editar_expediente":
            if data.get("success"):
                next_step = data.get("next_step")
                _STEP_TO_SUBMODE = {
                    "collect_personal": CollectionStep.COLLECT_PERSONAL.value,
                    "collect_vehicle": CollectionStep.COLLECT_VEHICLE.value,
                    "collect_workshop": CollectionStep.COLLECT_WORKSHOP.value,
                    "collect_base_docs": CollectionStep.COLLECT_BASE_DOCS.value,
                    "collect_element_data": CollectionStep.COLLECT_ELEMENT_DATA.value,
                }
                if next_step in _STEP_TO_SUBMODE:
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=CollectionStep.REVIEW_SUMMARY.value,
                        to_sub_mode=_STEP_TO_SUBMODE[next_step],
                        tool_name=tool_name,
                    )
                    updates["editing_from_review"] = True

        # Track element progress
        if tool_name in (
            "confirmar_fotos_elemento",
            "guardar_datos_elemento",
            "completar_elemento_actual",
        ):
            if "current_element_index" in data:
                updates["current_element_index"] = data["current_element_index"]
            if "element_phase" in data:
                updates["element_phase"] = data["element_phase"]

        # Extract field_keys from tool results
        if tool_name in ("confirmar_fotos_elemento", "obtener_campos_elemento"):
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys
        elif tool_name == "guardar_datos_elemento":
            field_keys = _extract_field_keys_from_tool_result(data)
            if field_keys:
                updates["current_element_field_keys"] = field_keys
            if (
                data.get("all_required_collected")
                and data.get("action") == "ELEMENT_DATA_COMPLETE"
            ):
                updates["element_data_all_collected"] = True
                updates["current_element_field_keys"] = None
            else:
                updates["element_data_all_collected"] = False
        elif tool_name == "completar_elemento_actual":
            updates["current_element_field_keys"] = None
            updates["element_data_all_collected"] = False

        # FSM compatibility: unwrap case_collection_update
        if "case_collection_update" in data:
            fsm_update = data["case_collection_update"]
            if isinstance(fsm_update, dict):
                case_coll = fsm_update.get("case_collection", {})
                if isinstance(case_coll, dict) and case_coll:
                    updates.update(case_coll)
        elif "case_collection" in data:
            fsm_updates = data["case_collection"]
            if isinstance(fsm_updates, dict):
                updates.update(fsm_updates)

        return updates
