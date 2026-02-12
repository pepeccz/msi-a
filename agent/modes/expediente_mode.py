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
            mode_context = await self._initialize_mode_context(conversation_id, mode_context)

        # Determine current sub-mode
        sub_mode = mode_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA)

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
    ) -> dict[str, Any]:
        """
        Initialize mode_context from DB when entering EXPEDIENTE_MODE.

        This loads the active case data for v1 tools compatibility.
        V1 tools expect case_id, category_id, element_codes, etc. in the FSM state,
        which we store in mode_context.

        Args:
            conversation_id: Conversation ID
            current_context: Current mode_context (may be empty)

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
                        conversation_id, current_context,
                    )

                # Initialize context with case data
                initialized_context = {
                    **current_context,
                    "case_id": str(case.id),
                    "category_id": str(case.category_id) if case.category_id else None,
                    "category_slug": case.category_slug,
                    "element_codes": case.element_codes or [],
                    "current_element_index": 0,  # Start from first element
                    "element_phase": "photos",  # Start with photos phase
                    "element_data_status": {
                        code: "pending" for code in (case.element_codes or [])
                    },
                    "base_docs_received": False,
                    "base_doc_descriptions": [],
                    "personal_data": {},
                    "vehicle_data": {},
                    "taller_propio": None,
                    "taller_data": None,
                    "tariff_tier_id": str(case.tariff_tier_id) if case.tariff_tier_id else None,
                    "tariff_amount": float(case.tariff_amount) if case.tariff_amount else None,
                    "received_images": [],
                    "expediente_sub_mode": current_context.get("expediente_sub_mode", COLLECT_ELEMENT_DATA),
                }

                logger.info(
                    "initialized_mode_context_from_db",
                    case_id=str(case.id),
                    element_count=len(case.element_codes or []),
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
    # Auto-create case (Phase 0 hotfix)
    # ------------------------------------------------------------------

    async def _auto_create_case(
        self,
        conversation_id: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Auto-create a Case when entering EXPEDIENTE_MODE without one.

        Uses data preserved in mode_context from PRESUPUESTO → EVAL_GATEWAY
        transition (via CONTEXT_PRESERVE_RULES in mode_transitions.py).

        Required keys in current_context:
        - categoria_slug: str (from PRESUPUESTO_MODE)
        - element_codes: list[str] (from PRESUPUESTO_MODE)

        Optional keys:
        - tarifa_calculada: dict (from calcular_tarifa_con_elementos)
        """
        import uuid
        from decimal import Decimal
        from database.connection import get_async_session
        from database.models import Case
        from sqlalchemy import select
        from agent.tools.case_tools import (
            _get_active_case_for_conversation,
            _get_category_id_by_slug,
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
            # Use the existing case to initialize context
            return {
                **current_context,
                "case_id": str(existing_case.id),
                "category_id": str(existing_case.category_id) if existing_case.category_id else None,
                "category_slug": categoria_slug,
                "element_codes": existing_case.element_codes or element_codes,
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {
                    code: "pending" for code in (existing_case.element_codes or element_codes)
                },
                "base_docs_received": False,
                "base_doc_descriptions": [],
                "personal_data": {},
                "vehicle_data": {},
                "taller_propio": None,
                "taller_data": None,
                "tariff_tier_id": str(existing_case.tariff_tier_id) if existing_case.tariff_tier_id else None,
                "tariff_amount": float(existing_case.tariff_amount) if existing_case.tariff_amount else None,
                "received_images": [],
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

        # Get user_id from state ContextVar
        from agent.state.helpers import get_current_state
        full_state = get_current_state() or {}
        user_id_str = full_state.get("user_id")

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
                await session.commit()

                logger.info(
                    "auto_created_case_for_expediente",
                    case_id=str(case_id),
                    conversation_id=conversation_id,
                    element_count=len(element_codes),
                    categoria_slug=categoria_slug,
                )

                return {
                    **current_context,
                    "case_id": str(case_id),
                    "category_id": category_id,
                    "category_slug": categoria_slug,
                    "element_codes": element_codes,
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": {
                        code: "pending" for code in element_codes
                    },
                    "base_docs_received": False,
                    "base_doc_descriptions": [],
                    "personal_data": {},
                    "vehicle_data": {},
                    "taller_propio": None,
                    "taller_data": None,
                    "tariff_tier_id": tier_id,
                    "tariff_amount": float(tarifa_amount) if tarifa_amount else None,
                    "received_images": [],
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

        Tool: actualizar_datos_expediente(seccion="datos_personales")
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

        Tool: actualizar_datos_expediente(seccion="datos_vehiculo")
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

        # ── 2. Build LLM messages ───────────────────────────────────────
        llm_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        llm_messages.extend(format_messages_for_llm(messages))
        llm_messages.append({
            "role": "user",
            "content": f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>",
        })

        # ── 3. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: EXPEDIENTE uses 30+ tools that need state via ContextVars.
        # IMPORTANT: Preserve nested structure - tools read from state["mode_context"]
        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context  # Preserve nested structure
        set_current_state(full_state)
        set_current_state_for_image_tools(full_state)

        # ── 4. Get LLM with tools ───────────────────────────────────────
        llm = self._get_llm(tools)

        # ── 5. Tool calling loop ─────────────────────────────────────────
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
                    
                    # Constraint validation (anti-hallucination)
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        is_valid, error_injection = await self._validate_response_constraints(
                            ai_response,
                            list(tools_called),
                            state,
                        )
                        
                        if not is_valid and error_injection:
                            validation_retries += 1
                            self._logger.warning(
                                "constraint_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                                sub_mode=sub_mode_name,
                            )
                            llm_messages.append({
                                "role": "user",
                                "content": f"[SYSTEM VALIDATION ERROR]: {error_injection}",
                            })
                            continue
                    
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
                    result_dict = json.loads(result) if isinstance(result, str) else result
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
                from agent.router.mode_transitions import validate_transition
                allowed, reason = validate_transition(self.mode_name, transition_target)
                if allowed:
                    result_dict["current_mode"] = transition_target
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

        # Detect sub-mode transitions from tool metadata
        if tool_name == "completar_elemento_actual":
            # Check if all elements are done → transition to COLLECT_BASE_DOCS
            if data.get("all_elements_complete"):
                updates["expediente_sub_mode"] = COLLECT_BASE_DOCS
                updates["just_transitioned_from"] = COLLECT_ELEMENT_DATA

        elif tool_name == "confirmar_documentacion_base":
            if data.get("success"):
                updates["expediente_sub_mode"] = COLLECT_PERSONAL
                updates["just_transitioned_from"] = COLLECT_BASE_DOCS

        elif tool_name == "actualizar_datos_expediente":
            seccion = tool_args.get("seccion")
            if data.get("success"):
                if seccion == "datos_personales":
                    updates["expediente_sub_mode"] = COLLECT_VEHICLE
                    updates["just_transitioned_from"] = COLLECT_PERSONAL
                elif seccion == "datos_vehiculo":
                    updates["expediente_sub_mode"] = COLLECT_WORKSHOP
                    updates["just_transitioned_from"] = COLLECT_VEHICLE

        elif tool_name == "actualizar_datos_taller":
            if data.get("success"):
                updates["expediente_sub_mode"] = REVIEW_SUMMARY
                updates["just_transitioned_from"] = COLLECT_WORKSHOP

        elif tool_name == "finalizar_expediente":
            if data.get("success"):
                # Mark as completed — transition out of EXPEDIENTE_MODE
                updates["expediente_completed"] = True
                # Could transition to COMPLETED mode or back to START

        elif tool_name == "cancelar_expediente":
            if data.get("success"):
                updates["expediente_cancelled"] = True

        # Track element progress
        if tool_name in ("confirmar_fotos_elemento", "guardar_datos_elemento", "completar_elemento_actual"):
            if "current_element_index" in data:
                updates["current_element_index"] = data["current_element_index"]
            if "element_phase" in data:
                updates["element_phase"] = data["element_phase"]

        # FSM compatibility: v1 tools return "case_collection" updates from fsm_compat layer
        # These need to be applied to mode_context to maintain state consistency
        if "case_collection" in data:
            fsm_updates = data["case_collection"]
            if isinstance(fsm_updates, dict):
                # Merge FSM updates into mode_context
                # This handles updates from v1 tools via the compatibility layer
                updates.update(fsm_updates)
                logger.debug(
                    "Applied FSM compatibility updates to mode_context",
                    tool_name=tool_name,
                    fsm_updates=list(fsm_updates.keys()),
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
        iniciar_expediente,
        consulta_durante_expediente,
        obtener_estado_expediente,
        cancelar_expediente,
    )
    from agent.tools.shared_tools import escalar_a_humano

    return [
        # Case creation (needed when entering EXPEDIENTE_MODE without a case)
        iniciar_expediente,
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

