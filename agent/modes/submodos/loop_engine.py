"""
ExpedienteLoopEngine — extracted from ExpedienteModeNode Phase C.

Contains _run_llm_loop (→ run()) and _extract_context_from_tool (→ extract_context_from_tool())
plus 8 static helpers. Wired to coordinator via composition (parent reference).

See: docs/decisions/010-expediente-state-integrity.md (tombstone protocol)
     docs/decisions/011-presupuesto-price-integrity.md (price injection pattern)
"""

# DEPRECATED (Phase 2): This module is superseded by agent/modes/generic_loop.py
# Remove after USE_GENERIC_LOOP=True is validated in production.
# All modes now route through generic_llm_loop() when USE_GENERIC_LOOP=True.
# This file is retained as the fallback path for USE_GENERIC_LOOP=False.

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, cast

import structlog
from langchain_openai import ChatOpenAI  # noqa: F401 — kept for completeness

from agent.modes.presupuesto_mode import _apply_tool_flags
from agent.modes.expediente_guardrails import (
    CertaintyEnvelope,
    ClaimClass,
    normalize_tool_payload,
    evaluate_progression_eligibility,
    evaluate_claim_eligibility,
    evaluate_kickoff_truthfulness,
    log_guardrail_triggered,
    persist_envelope,
    load_envelope,
    build_prompt_certainty_context,
)
from agent.modes.submodos._shared import (
    # Sub-mode constants
    COLLECT_ELEMENT_DATA,
    COLLECT_BASE_DOCS,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    MAX_TOOL_ITERATIONS,
    # Step maps
    _SUBMODE_STEP_MAP,
    # Tool matrix
    _is_tool_blocked,
    # Element state machine
    ELEMENT_STATE_CONFIRMING_PHOTOS,
    ELEMENT_STATE_RETRY_PHOTOS,
    ELEMENT_STATE_PHOTOS_CONFIRMED,
    ELEMENT_STATE_DATA_COLLECTION,
    ELEMENT_STATE_ELEMENT_COMPLETE,
    _set_element_state,
    # Taller domain guard
    _TALLER_DOMAIN_GUARD_SUBMODES,
    _TALLER_DOMAIN_RE,
    # Progress/prefix helpers
    _inject_step_prefix,
    _progress_prefix,
    _gate_response_claims,
    # Anti-repetition
    _check_anti_repetition,
    _store_turn_hash,
    # Transition helpers
    _build_transition_closure,
    _build_element_completion_transition_closure,
    _get_transition_base_documentation,
    _set_transition_updates,
    # Field/retry helpers
    _extract_field_keys_from_tool_result,
    _reset_validation_retry_state,
)
from agent.prompts.loader import assemble_system_prompt
from agent.state.conversation_state import ConversationState, create_empty_retry_state
from agent.state.helpers import (
    format_messages_for_llm,
    set_current_state,
    clear_current_state,
)
from agent.tools.image_tools import (
    set_current_state_for_image_tools,
    clear_image_tools_state,
)
from agent.utils.expediente_transition_adapter import canonicalize_transition
from shared.config import get_settings

if TYPE_CHECKING:
    from agent.modes.expediente_mode import ExpedienteModeNode

logger = structlog.get_logger(__name__)


class ExpedienteLoopEngine:
    """Loop engine extracted from ExpedienteModeNode (Phase C of expediente-split)."""

    def __init__(self, parent: "ExpedienteModeNode") -> None:
        self.parent = parent

    async def run(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        tools: list,
        sub_mode_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run the LLM tool-calling loop for a sub-mode.

        Same pattern as other modes (viabilidad, presupuesto, consulta).

        Optional kwargs:
            pre_call_tool_result (str | None): JSON-serialised result from a
                tool that was called deterministically BEFORE this loop (e.g.
                obtener_estado_expediente in REVIEW_SUMMARY).  If provided, it
                is injected as a system message right after the user message so
                the LLM sees authoritative data before generating a response.
            pre_call_tool_name (str | None): Name of the pre-called tool (used
                for logging and to mark it in tools_called so it is not called
                again).
        """
        conversation_id = state.get("conversation_id", "unknown")
        messages = state.get("messages", [])

        active_transition_marker = self._get_active_transition_marker(
            mode_context,
            sub_mode_name,
        )
        if active_transition_marker:
            self.parent._logger.info(
                "expediente_transition_marker_consumed",
                from_sub_mode=active_transition_marker.get("from_sub_mode"),
                to_sub_mode=active_transition_marker.get("to_sub_mode"),
                tool=active_transition_marker.get("tool_name"),
                sub_mode=sub_mode_name,
                conversation_id=conversation_id,
            )

        # ── 1. Build system prompt ───────────────────────────────────────
        client_context = self._build_client_context(state)

        # ── Certainty guardrails: initialise per-turn envelope ───────────────
        # Initialised here (before prompt assembly) so _guardrails_enabled is
        # available both when building prompt_mode_context and inside the tool loop.
        # We keep a *current-turn* envelope that accumulates evidence from every
        # tool call in this turn.  It starts fresh each turn (conservative: nothing
        # confirmed yet) with the current sub_mode already set.
        _guardrails_settings = get_settings()
        _guardrails_enabled: bool = (
            _guardrails_settings.EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED
        )
        _current_sub_mode_lc: str = sub_mode_name.lower()
        # The previous turn's envelope (persisted in mode_context) is loaded for
        # reference but NOT merged into the current turn — each turn starts clean.
        _prev_envelope: CertaintyEnvelope = load_envelope(
            mode_context, _current_sub_mode_lc
        )
        _turn_envelope: CertaintyEnvelope = CertaintyEnvelope.empty(
            sub_mode=_current_sub_mode_lc
        )

        prompt_mode_context = dict(mode_context)
        if active_transition_marker:
            prompt_mode_context["expediente_transition_marker"] = (
                active_transition_marker
            )

        # ── Certainty guardrails: inject previous turn's envelope into prompt ──
        # The *previous* turn's envelope is what the LLM should use for context.
        # The current turn's envelope is built during the tool loop below.
        if _guardrails_enabled:
            _cert_ctx = build_prompt_certainty_context(_prev_envelope)
            prompt_mode_context.update(_cert_ctx)

        # Map sub-mode to prompt key (matching MODE_MODULES in loader.py)
        sub_mode_to_prompt = {
            "COLLECT_ELEMENT_DATA": "EXPEDIENTE_DOCUMENTACION_ELEMENTOS",
            "COLLECT_BASE_DOCS": "EXPEDIENTE_DOCUMENTACION_BASE",
            "COLLECT_PERSONAL": "EXPEDIENTE_DATOS_PERSONALES",
            "COLLECT_VEHICLE": "EXPEDIENTE_DATOS_VEHICULO",
            "COLLECT_WORKSHOP": "EXPEDIENTE_TALLER",
            "REVIEW_SUMMARY": "EXPEDIENTE_REVISION",
        }
        mode_prompt_name = sub_mode_to_prompt.get(
            sub_mode_name, "EXPEDIENTE_DOCUMENTACION_ELEMENTOS"
        )

        system_prompt = assemble_system_prompt(
            mode=mode_prompt_name,
            mode_context=prompt_mode_context,
            client_context=client_context,
        )

        # Inject case_instructions if present (from _auto_create_case)
        # This tells the LLM that the case is already created and what to do
        case_instructions = mode_context.get("case_instructions")
        if case_instructions:
            system_prompt += (
                f"\n\n---\n\n<CASE_CONTEXT>\n{case_instructions}\n</CASE_CONTEXT>"
            )
            # Clear after first use (avoid repeating on every turn)
            # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
            mode_context.pop("case_instructions", None)
            mode_context["case_instructions"] = None  # TOMBSTONE

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
        llm_messages.append(
            {
                "role": "user",
                "content": f"<USER_MESSAGE>\n{image_notice}{message}\n</USER_MESSAGE>",
            }
        )

        # ── Deterministic pre-call injection ─────────────────────────────────
        # If the caller provides a pre-called tool result (e.g. from
        # _handle_review), inject it as a system message so the LLM sees
        # authoritative DB data before generating a response.  Also mark the
        # tool as already called to prevent duplicate invocation.
        pre_call_tool_result: str | None = kwargs.get("pre_call_tool_result")
        pre_call_tool_name: str | None = kwargs.get("pre_call_tool_name")
        if pre_call_tool_result and pre_call_tool_name:
            llm_messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[RESULTADO PRE-CARGADO de {pre_call_tool_name}]: "
                        f"{pre_call_tool_result}\n\n"
                        "IMPORTANTE: Usa EXCLUSIVAMENTE estos datos para el resumen. "
                        "No uses precios ni datos de mensajes anteriores."
                    ),
                }
            )
            self.parent._logger.debug(
                "pre_call_result_injected",
                tool=pre_call_tool_name,
                sub_mode=sub_mode_name,
                conversation_id=conversation_id,
            )

        # ── 3. Configure ContextVars for tool execution ───────────────────
        # CRITICAL: EXPEDIENTE uses 30+ tools that need state via ContextVars.
        # IMPORTANT: Preserve nested structure - tools read from state["mode_context"]
        full_state = dict(cast(dict[str, Any], state))
        full_state["mode_context"] = mode_context  # Preserve nested structure

        # Inject FSM state built by _auto_create_case so that
        # element_data_tools can read state["fsm_state"]["case_collection"].
        # Without this, the first turn after auto-creation fails because
        # the ContextVar has no fsm_state and tools raise KeyError.
        # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
        fsm_init = mode_context.pop("_fsm_state_init", None)
        mode_context["_fsm_state_init"] = None  # TOMBSTONE
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
        llm = self.parent._get_llm(tools)

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
        # RC-2: If photo guard fired before the LLM loop, register the tool it called
        # so the constraint validator knows it already ran deterministically this turn.
        # TOMBSTONE: assign False after pop so merge_dicts overwrites checkpoint; never use pop() alone
        _guard_photo_fired = mode_context.pop("_guard_photo_fired_this_turn", False)
        mode_context["_guard_photo_fired_this_turn"] = False  # TOMBSTONE
        if _guard_photo_fired:
            tools_called.add("confirmar_fotos_elemento")
            self.parent._logger.debug(
                "guard_tool_registered_in_tools_called",
                tool="confirmar_fotos_elemento",
                conversation_id=conversation_id,
            )
        # Pre-call registration: if the caller injected a deterministic tool
        # result via kwargs, register the tool so it won't be called again.
        if pre_call_tool_name and pre_call_tool_result:
            tools_called.add(pre_call_tool_name)
        pending_images: dict[str, Any] | None = None
        all_applied_flags: dict[str, Any] = {}
        validation_retries = 0
        MAX_VALIDATION_RETRIES = 2
        _case_finalized: bool = (
            False  # FASE 3: set True when case_finalized guard fires
        )
        # G2/G3 post-loop guard: allow only ONE reprompt retry per turn
        # to avoid infinite loops when the LLM refuses to call a tool.
        _g23_reprompt_done: bool = False

        # Phase 3: Initialize retry state for validation error recovery
        retry_state = state.get("retry_state", create_empty_retry_state())

        # Latency gating: use configurable iteration limit when flag is ON
        settings = get_settings()
        _effective_max_iterations = MAX_TOOL_ITERATIONS
        if settings.ENABLE_LATENCY_GATING:
            _effective_max_iterations = settings.MAX_TOOL_ITERATIONS_EXPEDIENTE
        _loop_hit_max: bool = False

        # ── Init per-turn dedup cache ────────────────────────────────────────
        # Activates the guard in base_mode._execute_and_log_tool() for this turn.
        # Reset to None in the finally block (even on exception) to prevent
        # stale cache entries leaking into the next turn.
        self.parent._tool_dedup_cache = {}

        try:
            for iteration in range(_effective_max_iterations):
                try:
                    response = await llm.ainvoke(llm_messages)
                except Exception as llm_error:
                    response = await self.parent._invoke_with_fallback(
                        llm_messages,
                        tools,
                        llm_error,
                        conversation_id,
                    )

                # Track token usage
                await self.parent._track_token_usage(conversation_id, response)

                # Check for tool calls
                tool_calls = getattr(response, "tool_calls", None)

                if not tool_calls:
                    ai_response = response.content or ""

                    # Empty LLM response retry: if the LLM returned empty
                    # content AND no tool calls (e.g. DeepSeek HTTP 200 with
                    # empty body), retry once with a reprompt instead of
                    # breaking out to the safety-net generic error.
                    if not ai_response and iteration == 0:
                        self.parent._logger.warning(
                            "empty_llm_response_retry",
                            iteration=iteration,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SYSTEM]: Tu respuesta anterior estuvo vacía. "
                                    "Por favor, responde al mensaje del usuario. "
                                    "Si necesitas información, usa las herramientas disponibles."
                                ),
                            }
                        )
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
                        self.parent._logger.warning(
                            "false_completion_detected",
                            sub_mode=sub_mode_name,
                            retry=validation_retries,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SISTEMA - ERROR CRÍTICO]: Has declarado que el expediente está completo "
                                    f"pero estamos en el sub-modo '{sub_mode_name}', NO en REVIEW_SUMMARY. "
                                    "NUNCA declares el expediente como completo, enviado o terminado hasta que "
                                    "el usuario haya confirmado el resumen final y hayas llamado a "
                                    "finalizar_expediente(). "
                                    "Continúa recogiendo los datos que corresponden a este sub-modo."
                                ),
                            }
                        )
                        continue

                    # ── Guard: G2/G3 data-collection enforcement ────────────────
                    # In COLLECT_PERSONAL / COLLECT_VEHICLE, when tools are
                    # available but the LLM returned no tool call, inject a single
                    # system reprompt instructing it to use actualizar_datos_expediente.
                    # The kickoff-turn exemption is implicit: callers that want a
                    # pure question turn (no tools) pass tools=[] to disable the guard.
                    # Only one retry is allowed (_g23_reprompt_done) to prevent
                    # infinite loops; if the LLM still skips the tool after the
                    # retry, we fall through to normal constraint validation.
                    _DATA_COLLECTION_SUBMODES = {"COLLECT_PERSONAL", "COLLECT_VEHICLE"}
                    if (
                        sub_mode_name in _DATA_COLLECTION_SUBMODES
                        and tools  # tools were available to call
                        and not _g23_reprompt_done  # only one retry
                    ):
                        _g23_reprompt_done = True
                        _reprompt_tool_names = [
                            t.name for t in tools if hasattr(t, "name")
                        ]
                        self.parent._logger.warning(
                            "g23_data_collection_reprompt",
                            sub_mode=sub_mode_name,
                            iteration=iteration,
                            available_tools=_reprompt_tool_names,
                            conversation_id=conversation_id,
                        )
                        llm_messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "[SISTEMA]: El usuario acaba de proporcionar datos. "
                                    "DEBES llamar actualizar_datos_expediente() para guardar "
                                    "los datos. NO respondas con texto sin llamar la herramienta."
                                ),
                            }
                        )
                        continue

                    # Constraint validation (anti-hallucination)
                    # Task 2.1: Skip constraint validation on kickoff turns where the LLM
                    # correctly asks for data without calling any tool yet.  The sub-modes
                    # collect_base_docs, collect_personal, and collect_vehicle all begin
                    # with a first-ask turn where the agent should ask the user to provide
                    # data/images — no tool call is needed or expected.  Running the
                    # constraint validator on these no-tool turns causes false positives
                    # (e.g. images_narration_blocked firing on "envíame las fotos adjuntas").
                    _KICKOFF_SKIP_SUBMODES = {
                        COLLECT_BASE_DOCS.lower(),
                        COLLECT_PERSONAL.lower(),
                        COLLECT_VEHICLE.lower(),
                    }
                    _is_kickoff_no_tool_turn = (
                        not tools_called
                        and sub_mode_name.lower() in _KICKOFF_SKIP_SUBMODES
                    )
                    if ai_response and validation_retries < MAX_VALIDATION_RETRIES:
                        if _is_kickoff_no_tool_turn:
                            # Kickoff ask: no tools expected, skip constraint check.
                            self.parent._logger.debug(
                                "constraint_validation_skipped_kickoff",
                                sub_mode=sub_mode_name,
                                reason="no_tools_called_on_kickoff_turn",
                            )
                            # Phase truthfulness guard: detect wrong-step-number claims.
                            # The LLM may hallucinate content from a different sub-mode
                            # (e.g. "Paso 5/6 — Taller" when we are in collect_personal).
                            # Strip the offending prefix and log a warning so the response
                            # still reaches the user without the wrong-phase decoration.
                            _expected_step = _SUBMODE_STEP_MAP.get(
                                sub_mode_name.lower() if sub_mode_name else ""
                            )
                            _step_mismatch_re = re.compile(r"[Pp]aso\s+(\d)\s*/\s*6")
                            _step_match = _step_mismatch_re.search(ai_response)
                            if (
                                _step_match
                                and _expected_step is not None
                                and int(_step_match.group(1)) != _expected_step
                            ):
                                self.parent._logger.warning(
                                    "kickoff_phase_mismatch_detected",
                                    claimed_step=int(_step_match.group(1)),
                                    expected_step=_expected_step,
                                    sub_mode=sub_mode_name,
                                    conversation_id=state.get(
                                        "conversation_id", "unknown"
                                    ),
                                )
                                ai_response = _step_mismatch_re.sub(
                                    "", ai_response
                                ).strip()
                            # Advancement-language guard: detect phase-advancement claims
                            # without tool evidence on kickoff no-tool turns.
                            _advancement_re = re.compile(
                                r"siguiente\s+paso|pasemos\s+a"
                                r"|continuamos\s+con\s+el\s+paso"
                                r"|hemos\s+completado|ya\s+tenemos\s+todo",
                                re.IGNORECASE,
                            )
                            if _advancement_re.search(ai_response):
                                self.parent._logger.warning(
                                    "kickoff_advancement_without_tools",
                                    sub_mode=sub_mode_name,
                                    conversation_id=state.get(
                                        "conversation_id", "unknown"
                                    ),
                                )
                                ai_response = _advancement_re.sub(
                                    "", ai_response
                                ).strip()
                            # ── Domain violation guard: taller vocabulary in personal/vehicle ──────
                            if (
                                sub_mode_name
                                and sub_mode_name.lower()
                                in _TALLER_DOMAIN_GUARD_SUBMODES
                            ):
                                if _TALLER_DOMAIN_RE.search(ai_response):
                                    self.parent._logger.warning(
                                        "kickoff_domain_violation_detected",
                                        violation_type="taller_in_personal_vehicle",
                                        sub_mode=sub_mode_name,
                                        conversation_id=state.get(
                                            "conversation_id", "unknown"
                                        ),
                                    )
                                    ai_response = _TALLER_DOMAIN_RE.sub(
                                        "", ai_response
                                    ).strip()
                            is_valid, error_injection = True, None
                        else:
                            (
                                is_valid,
                                error_injection,
                            ) = await self.parent._validate_response_constraints(
                                ai_response,
                                list(tools_called),
                                state,
                                current_mode_context=mode_context,  # Phase 1B: use updated context
                                available_tool_names={t.name for t in tools},
                            )

                        if not is_valid and error_injection:
                            validation_retries += 1
                            self.parent._logger.warning(
                                "constraint_retry",
                                retry=validation_retries,
                                max_retries=MAX_VALIDATION_RETRIES,
                                sub_mode=sub_mode_name,
                            )
                            # Phase 4B: Unified role "system" + IMPORTANT instruction
                            llm_messages.append(
                                {
                                    "role": "system",
                                    "content": f"[CONSTRAINT VALIDATION ERROR]: {error_injection}\n\nIMPORTANT: You MUST call the required tools to fix this issue. Do NOT generate explanatory text without tool calls.",
                                }
                            )
                            continue
                    elif ai_response and validation_retries >= MAX_VALIDATION_RETRIES:
                        # Phase 4A: Safety net — don't send hallucinated response
                        self.parent._logger.error(
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

                    self.parent._logger.info(
                        "tool_call",
                        tool=tool_name,
                        sub_mode=sub_mode_name,
                        iteration=iteration + 1,
                    )
                    if settings.ENABLE_LATENCY_GATING:
                        logger.info(
                            "tool_loop_iteration",
                            iteration=iteration + 1,
                            max=_effective_max_iterations,
                            mode="EXPEDIENTE",
                            tool_name=tool_name,
                        )

                    # ═══════════════════════════════════════════════════════════
                    # TASK-08: Phase-aware tool matrix enforcement
                    # Check BEFORE executing the tool. When EXPEDIENTE_V2_ENABLED
                    # is True, consult EXPEDIENTE_TOOL_MATRIX and, if the tool is
                    # blocked in the current (sub_mode, element_phase), skip
                    # execution entirely and inject a synthetic tool result.
                    # The LLM sees the blocked response and retries with the
                    # correct tool for the current phase.
                    #
                    # escalar_a_humano is NEVER blocked (safety override enforced
                    # inside _is_tool_blocked).
                    # ═══════════════════════════════════════════════════════════
                    if settings.EXPEDIENTE_V2_ENABLED:
                        _current_sub_mode_key = sub_mode_name.lower()
                        _current_element_phase: str | None = mode_context.get(
                            "element_phase"
                        )
                        _blocked = _is_tool_blocked(
                            tool_name=tool_name,
                            sub_mode=_current_sub_mode_key,
                            element_phase=_current_element_phase,
                        )
                        if _blocked:
                            logger.warning(
                                "tool_blocked_by_matrix",
                                tool=tool_name,
                                sub_mode=_current_sub_mode_key,
                                element_phase=_current_element_phase,
                                conversation_id=conversation_id,
                                iteration=iteration + 1,
                            )
                            # Inject synthetic blocked result — do NOT call the tool
                            _blocked_result = json.dumps(
                                {
                                    "blocked": True,
                                    "success": False,
                                    "message": (
                                        "Esta acción no está disponible en la fase actual. "
                                        f"El tool '{tool_name}' no se puede usar en "
                                        f"sub_mode='{_current_sub_mode_key}', "
                                        f"element_phase='{_current_element_phase}'."
                                    ),
                                }
                            )
                            llm_messages.append(
                                {
                                    "role": "tool",
                                    "content": _blocked_result,
                                    "tool_call_id": tool_call_id,
                                }
                            )
                            continue  # Let LLM see blocked result and retry
                    # ═══════════════════════════════════════════════════════════
                    # End TASK-08 tool matrix enforcement
                    # ═══════════════════════════════════════════════════════════

                    result = await self.parent._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tools=tools,
                        iteration=iteration + 1,
                    )

                    # ═══════════════════════════════════════════════════════════
                    # Phase 3: Validation error retry logic
                    # ═══════════════════════════════════════════════════════════
                    is_val_error, error_dict = self.parent._is_validation_error(result)

                    if is_val_error and error_dict:  # Type guard
                        should_retry, retry_state = (
                            self.parent._handle_validation_retry(
                                tool_name=tool_name,
                                error_dict=error_dict,
                                retry_state=retry_state,
                                llm_messages=llm_messages,
                            )
                        )

                        if should_retry:
                            # Reprompt added to llm_messages, continue LLM loop
                            self.parent._logger.info(
                                "validation_retry_triggered",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            break  # Exit tool loop, go to next iteration
                        else:
                            # Max retries reached - escalate
                            self.parent._logger.warning(
                                "validation_escalation",
                                tool=tool_name,
                                sub_mode=sub_mode_name,
                                retry_count=retry_state.get("retry_count"),
                                conversation_id=conversation_id,
                            )
                            return {
                                "ai_response": self.parent._fallback.get_validation_reprompt(
                                    retry_state, self.parent._policy
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

                    # S2: Reset validation retry counters after successful tool call
                    # Prevents stale errors from contaminating reprompts in later iterations
                    if retry_state.get("retry_count", 0) > 0:
                        retry_state = _reset_validation_retry_state(retry_state)

                    # REFACTOR-001: Apply tool flags BEFORE extracting context
                    # Parse result for _apply_tool_flags (handles JSON string)
                    # Defensive: some tools (e.g. escalar_a_humano) return plain
                    # text, not JSON — guard against JSONDecodeError.
                    try:
                        result_dict = (
                            json.loads(result) if isinstance(result, str) else result
                        )
                    except (json.JSONDecodeError, ValueError):
                        result_dict = {"raw_text": result}
                    _apply_tool_flags(mode_context, result_dict, self.parent._logger)

                    # ═══════════════════════════════════════════════════════════
                    # Layer B: Coherence interceptor — auto-heal when LLM calls
                    # guardar_datos_elemento or completar_elemento_actual while
                    # element_phase=="photos".
                    #
                    # Case 1 — guardar_datos_elemento:
                    #   This is defense-in-depth for the case where Layer A (the
                    #   pre-loop _guard_photo_completion_intent) did NOT fire because
                    #   the user sent data without saying "listo" (regex miss).
                    #   The guardar tool detects the inconsistency and returns
                    #   guidance=="confirmar_fotos_primero" instead of saving data.
                    #   We intercept that response here and transparently auto-call
                    #   confirmar_fotos_elemento(force=True) before the LLM retries.
                    #
                    # Case 2 — completar_elemento_actual (TASK-09 addition):
                    #   Same issue: LLM may call completar_elemento_actual() while still
                    #   in photos phase, skipping photo confirmation entirely.  We
                    #   intercept and auto-confirm photos first so the element advances
                    #   through the correct state machine transitions.
                    #
                    # Guard against re-entry: if Layer A already fired,
                    # element_phase was advanced to "data" BEFORE _run_llm_loop
                    # started, so mode_context.element_phase != "photos" here and
                    # this block is a no-op.
                    # ═══════════════════════════════════════════════════════════

                    # Determine if Layer B should trigger.
                    _layer_b_should_fire = False
                    _layer_b_trigger_reason = ""
                    # V2: Verify DB element phase before firing to avoid double-fire.
                    # If DB already reports the current element as pending_data/completed,
                    # mode_context["element_phase"] is stale — do not trigger interceptor.
                    _layer_b_db_phase: str = mode_context.get("element_phase", "photos")
                    _layer_b_ess = self.parent._get_element_state_svc()
                    if (
                        _layer_b_ess is not None
                        and mode_context.get("element_phase") == "photos"
                    ):
                        _lb_case_id = mode_context.get("case_id")
                        _lb_el_code = mode_context.get("current_element_code")
                        if _lb_case_id and _lb_el_code:
                            try:
                                _lb_el_state = await _layer_b_ess.get_element_state(
                                    str(_lb_case_id), _lb_el_code
                                )
                                if _lb_el_state is not None:
                                    # DB says photos already confirmed → skip interceptor
                                    _lb_db_status = (
                                        ced_by_code.get(_lb_el_code)
                                        if "ced_by_code" in dir()
                                        else None
                                    )
                                    # Derive from element state directly
                                    _lb_el_state_dict = (
                                        _lb_el_state.to_dict()
                                        if hasattr(_lb_el_state, "to_dict")
                                        else {}
                                    )
                                    _lb_ced_status = _lb_el_state_dict.get(
                                        "status", "pending_photos"
                                    )
                                    if _lb_ced_status in ("pending_data", "completed"):
                                        _layer_b_db_phase = "data"
                                        logger.debug(
                                            "layer_b_db_phase_override",
                                            case_id=_lb_case_id,
                                            element_code=_lb_el_code,
                                            db_status=_lb_ced_status,
                                            skipping_interceptor=True,
                                        )
                            except Exception as _lb_err:
                                logger.debug(
                                    "layer_b_db_check_failed", error=str(_lb_err)
                                )

                    if _layer_b_db_phase == "photos":
                        if (
                            tool_name == "guardar_datos_elemento"
                            and isinstance(result_dict, dict)
                            and result_dict.get("guidance") == "confirmar_fotos_primero"
                        ):
                            _layer_b_should_fire = True
                            _layer_b_trigger_reason = "guardar_while_photos"
                        elif tool_name == "completar_elemento_actual":
                            # TASK-09: LLM called completar without confirming photos first
                            _layer_b_should_fire = True
                            _layer_b_trigger_reason = "completar_while_photos"

                    if _layer_b_should_fire:
                        logger.warning(
                            "photo_coherence_interceptor_triggered",
                            conversation_id=conversation_id,
                            tool_name=tool_name,
                            trigger_reason=_layer_b_trigger_reason,
                            element_code=mode_context.get("current_element_code"),
                            element_index=mode_context.get("current_element_index"),
                        )
                        # Force-call confirmar_fotos_elemento bypassing regex check.
                        # This advances element_phase to "data" in mode_context
                        # (in-place) so the LLM retry sees the correct phase.
                        interceptor_fired = (
                            await self.parent._guard_photo_completion_intent(
                                user_message="",
                                mode_context=mode_context,
                                state=cast(dict[str, Any], state),
                                conversation_id=conversation_id,
                                force=True,
                            )
                        )
                        # TASK-09: After interceptor auto-confirms photos, update the
                        # state machine to reflect photos_confirmed (if EXPEDIENTE_V2_ENABLED
                        # and _guard_photo_completion_intent didn't already advance to a
                        # terminal state).  The guard sets states internally; we only add
                        # the explicit photos_confirmed marker here when the interceptor
                        # fired but the post-call logic in _guard_photo_completion_intent
                        # left the state as "confirming_photos" (poll still in-flight).
                        # In practice this is a no-op for success paths because
                        # _guard_photo_completion_intent already advances to photos_confirmed
                        # or element_complete.  This is a belt-and-suspenders safety net.
                        # Agent Architecture Refactor T1.2b: use USE_ELEMENT_STATE_SERVICE
                        # (granular flag, default=True) instead of EXPEDIENTE_V2_ENABLED.
                        if (
                            interceptor_fired
                            and get_settings().USE_ELEMENT_STATE_SERVICE
                            and mode_context.get("element_phase") == "data"
                        ):
                            _layer_b_el_code: str | None = mode_context.get(
                                "current_element_code"
                            ) or (
                                (mode_context.get("element_codes") or [None])[
                                    mode_context.get("current_element_index", 0)
                                ]
                                if mode_context.get("element_codes")
                                else None
                            )
                            if _layer_b_el_code:
                                _layer_b_existing = (
                                    (mode_context.get("element_states") or {})
                                    .get(_layer_b_el_code, {})
                                    .get("state")
                                )
                                # Only advance if still at confirming_photos
                                # (guard may have already set photos_confirmed)
                                if _layer_b_existing == ELEMENT_STATE_CONFIRMING_PHOTOS:
                                    _set_element_state(
                                        mode_context,
                                        _layer_b_el_code,
                                        ELEMENT_STATE_PHOTOS_CONFIRMED,
                                    )
                                    logger.debug(
                                        "layer_b_photos_confirmed_state_set",
                                        conversation_id=conversation_id,
                                        element_code=_layer_b_el_code,
                                        trigger_reason=_layer_b_trigger_reason,
                                    )
                        logger.info(
                            "photo_coherence_interceptor_completed",
                            conversation_id=conversation_id,
                            interceptor_fired=interceptor_fired,
                            trigger_reason=_layer_b_trigger_reason,
                            new_element_phase=mode_context.get("element_phase"),
                        )
                    # ═══════════════════════════════════════════════════════════
                    # End Layer B coherence interceptor
                    # ═══════════════════════════════════════════════════════════

                    # Track all applied flags for final authority
                    parsed_flags = (
                        result_dict.get("_internal_flags", {})
                        if isinstance(result_dict, dict)
                        else {}
                    )
                    all_applied_flags.update(parsed_flags)

                    # ═══════════════════════════════════════════════════════════
                    # FASE 3: Early-exit guard for case_finalized
                    # When finalizar_expediente() succeeds it returns
                    # _internal_flags: {"case_finalized": True}.  The moment we
                    # detect that flag we MUST stop the tool loop and use the
                    # tool's own message as the final user-facing response.
                    #
                    # This prevents the LLM from continuing to call other tools
                    # (e.g. escalar_a_humano) after finalization, which would
                    # overwrite the correct Chatwoot labels and confuse the user.
                    #
                    # Defensive: we check EVERY tool result in the batch, not
                    # just the last one.  If any tool carries this flag (unlikely
                    # for non-finalizar tools, but defensive programming),
                    # we honour it and stop immediately.
                    #
                    # The guard does NOT fire on failure paths because
                    # finalizar_expediente() only sets case_finalized on
                    # success=True; error paths return success=False with no flag.
                    # ═══════════════════════════════════════════════════════════
                    if parsed_flags.get("case_finalized") is True:
                        finalization_message = ""
                        if isinstance(result_dict, dict):
                            finalization_message = result_dict.get(
                                "message", ""
                            ) or result_dict.get("texto", "")
                        if finalization_message:
                            ai_response = finalization_message
                        _case_finalized = True
                        logger.info(
                            "expediente_case_finalized_guard_triggered",
                            case_finalized=True,
                            tool_name=tool_name,
                            conversation_id=conversation_id,
                        )
                        break  # Exit inner tool loop — finalization is terminal

                    # Extract context from tool results
                    tool_context = self.extract_context_from_tool(
                        tool_name,
                        tool_args,
                        result,
                        mode_context,
                    )

                    # ── Certainty guardrails: accumulate envelope + gate transitions ──
                    if _guardrails_enabled:
                        _turn_envelope = normalize_tool_payload(
                            tool_name=tool_name,
                            raw_result=result,
                            current_sub_mode=_current_sub_mode_lc,
                            existing_envelope=_turn_envelope,
                        )
                        # If _extract_context_from_tool signalled a transition,
                        # check whether the envelope supports it.  If not, remove
                        # the transition keys from tool_context so the transition
                        # is suppressed this turn.
                        _proposed_target: str | None = tool_context.get(
                            "expediente_sub_mode"
                        )
                        if _proposed_target:
                            _prog_allowed, _prog_reason = (
                                evaluate_progression_eligibility(
                                    _turn_envelope, _proposed_target
                                )
                            )
                            log_guardrail_triggered(
                                reason=_prog_reason,
                                sub_mode=_current_sub_mode_lc,
                                tool_name=tool_name,
                                conversation_id=conversation_id,
                                allowed=_prog_allowed,
                                extra={"transition_target": _proposed_target},
                            )
                            if not _prog_allowed:
                                # Suppress the transition — remove all transition keys
                                for _tkey in (
                                    "expediente_sub_mode",
                                    "just_transitioned_from",
                                    "expediente_transition_marker",
                                ):
                                    tool_context.pop(_tkey, None)
                                logger.warning(
                                    "expediente_transition_suppressed_by_guardrail",
                                    reason=_prog_reason,
                                    proposed_target=_proposed_target,
                                    sub_mode=_current_sub_mode_lc,
                                    tool_name=tool_name,
                                    conversation_id=conversation_id,
                                )

                    context_updates.update(tool_context)

                    # TASK-05: Update per-element 7-state machine in _run_llm_loop.
                    # Fired AFTER _extract_context_from_tool so that mode_context
                    # is already partially updated (element_phase, element_code, etc.).
                    # Agent Architecture Refactor T1.2b: use USE_ELEMENT_STATE_SERVICE
                    # (granular flag, default=True) instead of EXPEDIENTE_V2_ENABLED.
                    if (
                        settings.USE_ELEMENT_STATE_SERVICE
                        and sub_mode_name == "COLLECT_ELEMENT_DATA"
                    ):
                        # Merge pending context_updates into a temporary view so helpers
                        # see the latest element_phase / element_code values.
                        _v2_ctx = {**mode_context, **context_updates}
                        _v2_el_code: str | None = _v2_ctx.get(
                            "current_element_code"
                        ) or (
                            (_v2_ctx.get("element_codes") or [None])[
                                _v2_ctx.get("current_element_index", 0)
                            ]
                            if _v2_ctx.get("element_codes")
                            else None
                        )
                        if _v2_el_code:
                            if tool_name == "confirmar_fotos_elemento":
                                _v2_count_raw = (
                                    result_dict.get("photos_count", 0)
                                    if isinstance(result_dict, dict)
                                    else 0
                                )
                                _v2_count: int = (
                                    _v2_count_raw
                                    if isinstance(_v2_count_raw, int)
                                    else 0
                                )
                                if (
                                    result_dict.get("all_elements_complete")
                                    if isinstance(result_dict, dict)
                                    else False
                                ):
                                    # No data fields — element fully done immediately
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_ELEMENT_COMPLETE,
                                        data_complete=True,
                                    )
                                elif _v2_ctx.get("element_phase") == "data":
                                    # Photos successfully verified → moving to data
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_PHOTOS_CONFIRMED,
                                        photos_count=_v2_count,
                                    )
                                else:
                                    # Polling in progress
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_CONFIRMING_PHOTOS,
                                    )
                            elif tool_name == "obtener_campos_elemento":
                                if _v2_ctx.get("element_phase") == "data":
                                    # Now actively collecting field data
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_DATA_COLLECTION,
                                    )
                            elif tool_name == "guardar_datos_elemento":
                                if _v2_ctx.get("element_phase") == "data":
                                    # Still in data collection
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_DATA_COLLECTION,
                                    )
                            elif tool_name == "completar_elemento_actual":
                                if isinstance(result_dict, dict) and result_dict.get(
                                    "success"
                                ):
                                    # Element fully complete
                                    _set_element_state(
                                        mode_context,
                                        _v2_el_code,
                                        ELEMENT_STATE_ELEMENT_COMPLETE,
                                        data_complete=True,
                                    )

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

                    llm_messages.append(
                        {
                            "role": "tool",
                            "content": result,
                            "tool_call_id": tool_call_id,
                        }
                    )

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
                        _base_docs = _get_transition_base_documentation(mode_context)
                        # Phase 3.2: Use generalised transition matrix when flag is ON;
                        # fall back to legacy element-only closure when flag is OFF.
                        if settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE:
                            deterministic_closure = _build_transition_closure(
                                from_sub_mode=sub_mode_name.lower(),
                                to_sub_mode=new_sub_mode,
                                tool_name=tool_name,
                                tool_data=result_dict
                                if isinstance(result_dict, dict)
                                else None,
                                base_documentation=_base_docs,
                            )
                        else:
                            deterministic_closure = (
                                _build_element_completion_transition_closure(
                                    from_sub_mode=sub_mode_name.lower(),
                                    to_sub_mode=new_sub_mode,
                                    tool_name=tool_name,
                                    tool_data=result_dict
                                    if isinstance(result_dict, dict)
                                    else None,
                                    base_documentation=_base_docs,
                                )
                            )
                        closing_message = deterministic_closure or ""
                        if not closing_message and isinstance(result_dict, dict):
                            closing_message = result_dict.get("message", "")
                        if closing_message:
                            ai_response = closing_message
                        # Mark that the closure already delivered field-level
                        # kickoff content so the next sub-mode prompt skips the
                        # duplicate introductory question.
                        if deterministic_closure and new_sub_mode != REVIEW_SUMMARY:
                            mode_context["kickoff_question_injected"] = True
                        # Observability: trace closure emission for transition diagnostics
                        self.parent._logger.info(
                            "expediente_transition_closure_emitted",
                            from_sub_mode=sub_mode_name,
                            to_sub_mode=new_sub_mode,
                            tool=tool_name,
                            has_deterministic_closure=bool(deterministic_closure),
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
                            transition_message = result_dict.get(
                                "message", ""
                            ) or result_dict.get("texto", "")
                        if transition_message:
                            ai_response = transition_message
                        self.parent._logger.info(
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

                # FASE 3: Break outer iteration loop when case_finalized guard fired
                if _case_finalized:
                    break

                # Fast-path: break outer iteration loop on sub-mode transition
                # context_updates has the new sub_mode from the tool; sub_mode_name
                # is the UPPER-CASED version of the current sub-mode (before transition).
                _new_sub = context_updates.get("expediente_sub_mode")
                if _new_sub and _new_sub != sub_mode_name.lower():
                    break

            else:
                _loop_hit_max = True
                self.parent._logger.warning(
                    "max_tool_iterations",
                    sub_mode=sub_mode_name,
                    iterations=_effective_max_iterations,
                )
                if settings.ENABLE_LATENCY_GATING:
                    logger.info(
                        "tool_loop_complete",
                        iterations=_effective_max_iterations,
                        exit_reason="max_iterations",
                        mode="EXPEDIENTE",
                        sub_mode=sub_mode_name,
                    )
                if not ai_response:
                    ai_response = response.content or (
                        "Disculpa, me ha llevado más tiempo del esperado. "
                        "¿Puedes repetir?"
                    )

            # ═══════════════════════════════════════════════════════════════════
            # GUARD: Auto-complete element when LLM skips completar_elemento_actual
            #
            # Bug scenario:
            #   1. LLM calls guardar_datos_elemento() → all fields saved
            #   2. LLM generates closing text WITHOUT calling completar_elemento_actual()
            #   3. Element stuck in "pending_data" → dead-air, no transition
            #
            # Fix: If guardar_datos_elemento signaled all fields are complete
            # (element_data_all_collected == True) and the LLM did not call
            # completar_elemento_actual in this turn, we call it programmatically.
            # ═══════════════════════════════════════════════════════════════════
            if (
                sub_mode_name == "COLLECT_ELEMENT_DATA"
                and "guardar_datos_elemento" in tools_called
                and "completar_elemento_actual" not in tools_called
                and context_updates.get("element_data_all_collected") is True
                and not context_updates.get(
                    "expediente_sub_mode"
                )  # No transition already set
            ):
                self.parent._logger.warning(
                    "expediente_auto_complete_element_guard_triggered",
                    conversation_id=conversation_id,
                    sub_mode=sub_mode_name,
                    tools_called_this_turn=list(tools_called),
                    element_code=mode_context.get("current_element_code")
                    or (
                        mode_context.get("element_codes", [None])[
                            mode_context.get("current_element_index", 0)
                        ]
                        if mode_context.get("element_codes")
                        else None
                    ),
                )

                try:
                    # Execute the tool programmatically (same path as LLM-driven)
                    # Note: completar_elemento_actual is dispatched by name via
                    # _execute_and_log_tool, which finds it in the `tools` list.
                    guard_result = await self.parent._execute_and_log_tool(
                        conversation_id=conversation_id,
                        tool_name="completar_elemento_actual",
                        tool_args={},
                        tools=tools,
                        iteration=MAX_TOOL_ITERATIONS + 1,  # Distinguishable iteration
                    )

                    tools_called.add("completar_elemento_actual")

                    # Parse result (same pattern as main loop)
                    try:
                        guard_result_dict = (
                            json.loads(guard_result)
                            if isinstance(guard_result, str)
                            else guard_result
                        )
                    except (json.JSONDecodeError, ValueError):
                        guard_result_dict = {"raw_text": guard_result}

                    # Apply tool flags
                    _apply_tool_flags(
                        mode_context, guard_result_dict, self.parent._logger
                    )
                    if isinstance(guard_result_dict, dict):
                        parsed_flags = guard_result_dict.get("_internal_flags", {})
                        all_applied_flags.update(parsed_flags)

                    # Extract context updates (drives sub-mode transition)
                    guard_context = self.extract_context_from_tool(
                        "completar_elemento_actual",
                        {},
                        guard_result,
                        mode_context,
                    )
                    context_updates.update(guard_context)

                    # Re-inject ContextVar with updated state
                    mode_context.update(guard_context)
                    updated_state = dict(state)
                    updated_state["mode_context"] = mode_context
                    set_current_state(updated_state)
                    set_current_state_for_image_tools(updated_state)

                    # Handle sub-mode transition (same logic as PHASE F-3 fast-path)
                    new_sub_mode = guard_context.get("expediente_sub_mode")
                    if new_sub_mode and new_sub_mode != sub_mode_name.lower():
                        _base_docs = _get_transition_base_documentation(mode_context)
                        # Phase 3.2: Use generalised matrix when flag is ON (guard path)
                        if settings.ENABLE_SAME_TURN_TRANSITION_CLOSURE:
                            deterministic_closure = _build_transition_closure(
                                from_sub_mode=sub_mode_name.lower(),
                                to_sub_mode=new_sub_mode,
                                tool_name="completar_elemento_actual",
                                tool_data=guard_result_dict
                                if isinstance(guard_result_dict, dict)
                                else None,
                                base_documentation=_base_docs,
                            )
                        else:
                            deterministic_closure = (
                                _build_element_completion_transition_closure(
                                    from_sub_mode=sub_mode_name.lower(),
                                    to_sub_mode=new_sub_mode,
                                    tool_name="completar_elemento_actual",
                                    tool_data=guard_result_dict
                                    if isinstance(guard_result_dict, dict)
                                    else None,
                                    base_documentation=_base_docs,
                                )
                            )
                        if deterministic_closure:
                            ai_response = deterministic_closure
                            # Mark kickoff injection so sub-mode prompt skips
                            # duplicate question (skip for review — tool-first).
                            if new_sub_mode != REVIEW_SUMMARY:
                                mode_context["kickoff_question_injected"] = True
                        elif isinstance(guard_result_dict, dict):
                            ai_response = (
                                guard_result_dict.get("message", "") or ai_response
                            )
                    elif isinstance(guard_result_dict, dict) and guard_result_dict.get(
                        "success"
                    ):
                        # Element complete but more elements remaining — build deterministic kickoff
                        _kickoff = self._build_next_element_kickoff(
                            completed_element_name=guard_result_dict.get("message", "")
                            .replace(" completado ✅", "")
                            .strip(),
                            next_element_name=guard_result_dict.get(
                                "next_element_name", ""
                            ),
                            element_phase=guard_result_dict.get("element_phase", ""),
                        )
                        ai_response = (
                            _kickoff
                            if _kickoff is not None
                            else guard_result_dict.get("message", "")
                        )

                    self.parent._logger.info(
                        "expediente_auto_complete_element_guard_completed",
                        conversation_id=conversation_id,
                        guard_success=isinstance(guard_result_dict, dict)
                        and guard_result_dict.get("success", False),
                        triggered_transition=bool(
                            guard_context.get("expediente_sub_mode")
                        ),
                        all_elements_complete=isinstance(guard_result_dict, dict)
                        and guard_result_dict.get("all_elements_complete", False),
                    )

                except Exception as guard_error:
                    # Non-fatal: log and continue with existing response
                    self.parent._logger.error(
                        "expediente_auto_complete_element_guard_failed",
                        error=str(guard_error),
                        conversation_id=conversation_id,
                        exc_info=True,
                    )

            # Log tool loop completion for latency telemetry
            if settings.ENABLE_LATENCY_GATING and not _loop_hit_max:
                logger.info(
                    "tool_loop_complete",
                    iterations=iteration + 1 if tools_called else 0,
                    exit_reason="no_tool_calls" if not tools_called else "break",
                    mode="EXPEDIENTE",
                    sub_mode=sub_mode_name,
                )

            # ── 6. Build state updates ───────────────────────────────────────
            # Merge context: mode_context is base, context_updates adds structural data,
            # all_applied_flags has FINAL AUTHORITY over boolean flags
            transitioned_this_turn = bool(context_updates.get("expediente_sub_mode"))

            # ── Bug 1 fix: same-turn transition marker ────────────────────────
            # active_transition_marker is read at the START of _run_llm_loop (before
            # tools execute) — it only sees markers set on PRIOR turns.  When a tool
            # (e.g. confirmar_fotos_elemento) sets a new transition marker THIS turn,
            # it ends up in context_updates["expediente_transition_marker"], NOT in
            # mode_context.  effective_transition_marker merges both so the kickoff
            # guard fires on the originating turn, not one turn too late.
            effective_transition_marker: dict[str, Any] | None = (
                active_transition_marker
            )
            if effective_transition_marker is None:
                _same_turn_marker = context_updates.get("expediente_transition_marker")
                if isinstance(_same_turn_marker, dict) and _same_turn_marker.get(
                    "requires_kickoff"
                ):
                    effective_transition_marker = _same_turn_marker

            ai_response_text: str = str(ai_response or "")

            # ── Certainty guardrails: finalise envelope + inject into prompt context ──
            if _guardrails_enabled:
                # Mark first-destination-turn flag when a kickoff marker is active and
                # no further transition happened this turn.
                if effective_transition_marker and not transitioned_this_turn:
                    _turn_envelope = CertaintyEnvelope(
                        **{
                            **_turn_envelope.to_dict(),
                            "is_first_destination_turn": True,
                            # Anti-anticipation: if the existing response is not
                            # actionable, block transition claims in the prompt.
                            "allowed_transition_claims": self._is_actionable_kickoff_response(
                                ai_response_text
                            ),
                            "kickoff_required": not self._is_actionable_kickoff_response(
                                ai_response_text
                            ),
                        }
                    )

                # Persist envelope so loader.py and next turn can read it.
                persist_envelope(mode_context, _turn_envelope)

                # Extend kickoff guard with truthfulness check.
                if effective_transition_marker and not transitioned_this_turn:
                    _truth_ok, _truth_reason = evaluate_kickoff_truthfulness(
                        _turn_envelope, _current_sub_mode_lc
                    )
                    log_guardrail_triggered(
                        reason=_truth_reason,
                        sub_mode=_current_sub_mode_lc,
                        conversation_id=conversation_id,
                        allowed=_truth_ok,
                    )

                    # ── Task 3.2: Claim eligibility gate for NEXT_STEP_DESCRIPTION ──
                    # When this is the first destination turn after a transition and
                    # the LLM response is not yet actionable (kickoff guard is about
                    # to fire), also evaluate whether a NEXT_STEP_DESCRIPTION claim
                    # is permitted.  This creates a structured audit trail so the
                    # guardrail dashboard can track same-turn anticipatory narration.
                    if not self._is_actionable_kickoff_response(ai_response_text):
                        _claim_ok, _claim_reason = evaluate_claim_eligibility(
                            _turn_envelope,
                            ClaimClass.NEXT_STEP_DESCRIPTION,
                            _current_sub_mode_lc,
                        )
                        log_guardrail_triggered(
                            reason=_claim_reason,
                            sub_mode=_current_sub_mode_lc,
                            claim_class=ClaimClass.NEXT_STEP_DESCRIPTION.value,
                            conversation_id=conversation_id,
                            allowed=_claim_ok,
                        )
                        # Task 3.4: Emit dedicated blocked event for dashboards.
                        if not _claim_ok:
                            logger.warning(
                                "expediente_next_step_narration_blocked",
                                conversation_id=conversation_id,
                                sub_mode=_current_sub_mode_lc,
                                reason_code=_claim_reason,
                                from_sub_mode=effective_transition_marker.get(
                                    "from_sub_mode"
                                ),
                                to_sub_mode=effective_transition_marker.get(
                                    "to_sub_mode"
                                ),
                                enforced=True,
                            )

            # Kickoff guard fires when: (1) we just transitioned to a new sub-mode AND
            # (2) the LLM response is not actionable (no question/CTA).
            # The `transitioned_this_turn` condition was removed because it suppressed
            # the kickoff exactly when needed — on the transition turn itself.
            # Bug 1 fix: uses effective_transition_marker (not active_transition_marker)
            # so the guard also fires when the marker was set THIS turn by a tool call.
            if effective_transition_marker and not self._is_actionable_kickoff_response(
                ai_response_text
            ):
                ai_response = self._build_transition_kickoff_message(
                    sub_mode_name=sub_mode_name,
                    mode_context=mode_context,
                )
                self.parent._logger.warning(
                    "expediente_transition_kickoff_guard_triggered",
                    from_sub_mode=effective_transition_marker.get("from_sub_mode"),
                    to_sub_mode=effective_transition_marker.get("to_sub_mode"),
                    sub_mode=sub_mode_name,
                    tools_called=list(tools_called),
                    conversation_id=conversation_id,
                )

            updated_context = {**mode_context, **context_updates}
            # _internal_flags always win over stale context_updates values
            for key, value in all_applied_flags.items():
                if key.startswith("_"):
                    continue  # Skip internal keys like _transition_to
                updated_context[key] = value

            # ── TASK-07: Anti-repetition guard (MD5 hash of last 2 assistant turns) ──
            # Step 2 of final-response assembly: check for repeat BEFORE progress prefix.
            # If the new message matches either of the last 2 stored hashes, prepend
            # "Para recordarte: " so the user knows it is intentional, not a bug.
            # Feature-flagged: only active when EXPEDIENTE_V2_ENABLED=True.
            _final_response_str = str(ai_response or "")
            if settings.EXPEDIENTE_V2_ENABLED and _final_response_str:
                _final_response_str = _check_anti_repetition(
                    _final_response_str, mode_context
                )
                ai_response = _final_response_str

            # ── TASK-06: Inject deterministic progress prefix on final user-facing response ──
            # Only active when EXPEDIENTE_V2_ENABLED=True.  Uses _inject_step_prefix()
            # which is idempotent (never double-prefixes) and skips empty messages.
            # Applied to the terminal user-facing response — not to tool call turns.
            _current_sub_mode = mode_context.get(
                "expediente_sub_mode", sub_mode_name.lower()
            )
            if settings.EXPEDIENTE_V2_ENABLED:
                ai_response = _inject_step_prefix(
                    str(ai_response or ""), _current_sub_mode
                )

            # ── TASK-07: Store MD5 of the final sent message (post-prefix) ──
            # Step 4: Hash stored AFTER progress prefix injection — we track the exact
            # bytes the user sees so future comparisons are accurate.
            # updated_context is built just below; store into mode_context in-place so
            # the mutation is captured when we merge into updated_context next.
            if settings.EXPEDIENTE_V2_ENABLED:
                _store_turn_hash(str(ai_response or ""), mode_context)
                # Propagate mutation to updated_context (built before _store_turn_hash ran)
                updated_context["_last_agent_turns"] = mode_context.get(
                    "_last_agent_turns", []
                )

            # ── Task 3.3: Pre-response claim gate ────────────────────────────
            # AFTER the LLM/tool loop and all post-processing guards, but BEFORE
            # ai_response is returned, run a final regex-based claim gate.
            # This is the last line of defence against unsupported assertions in
            # the assembled response.  Only active when guardrails are enabled.
            #
            # We accumulate evaluation counters here so Task 3.4 turn-summary
            # log can include them.
            _gate_blocked: int = 0
            _gate_allowed: int = 0
            if _guardrails_enabled and ai_response:
                _gated_response, _gate_blocked, _gate_allowed = _gate_response_claims(
                    ai_response=str(ai_response),
                    turn_envelope=_turn_envelope,
                    sub_mode=_current_sub_mode_lc,
                    conversation_id=conversation_id,
                    guardrails_enabled=True,
                )
                if _gated_response != str(ai_response):
                    self.parent._logger.info(
                        "expediente_claim_gate_rewrite",
                        sub_mode=_current_sub_mode_lc,
                        conversation_id=conversation_id,
                        blocked_count=_gate_blocked,
                        original_length=len(str(ai_response)),
                        rewritten_length=len(_gated_response),
                    )
                ai_response = _gated_response

            # ── Task 3.4: Turn-summary observability ─────────────────────────
            # Emit one structured log per expediente turn when guardrails are ON.
            # Aggregates all guardrail evaluations performed this turn (from tool
            # loop + pre-response gate) so dashboards can compute block-rate
            # without joining multiple events.
            if _guardrails_enabled:
                # Count progression evaluations that happened during the tool loop.
                # We proxy via tools_called to avoid double-tracking; each tool
                # that was normalised had its progression eligibility checked once.
                _total_evaluations = len(tools_called) + _gate_blocked + _gate_allowed
                logger.info(
                    "expediente_certainty_turn_summary",
                    conversation_id=conversation_id,
                    sub_mode=_current_sub_mode_lc,
                    tools_called_count=len(tools_called),
                    total_evaluations=_total_evaluations,
                    blocked_count=_gate_blocked,
                    allowed_count=_gate_allowed,
                    case_id=mode_context.get("case_id"),
                )

            result_dict: dict[str, Any] = {
                "ai_response": ai_response,
                "mode_context": updated_context,
                "retry_state": retry_state,  # Phase 3: Persist retry state
            }

            # Propagate mode transition if signaled by a tool
            # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
            transition_target = updated_context.pop("_transition_to", None)
            updated_context["_transition_to"] = None  # TOMBSTONE
            if transition_target:
                from agent.router.mode_transitions import (
                    validate_transition,
                    get_preserve_keys,
                )
                from agent.state.conversation_state import transition_mode

                allowed, reason = validate_transition(
                    self.parent.mode_name, transition_target
                )
                if allowed:
                    preserve = get_preserve_keys(
                        self.parent.mode_name, transition_target
                    )
                    transition_updates = transition_mode(
                        state,
                        transition_target,
                        preserve_keys=preserve,
                    )
                    # Merge transition updates, but keep our ai_response
                    saved_response = result_dict["ai_response"]
                    result_dict.update(transition_updates)
                    result_dict["ai_response"] = saved_response
                    self.parent._logger.info(
                        "mode_transition_from_tool",
                        target=transition_target,
                        sub_mode=sub_mode_name,
                        conversation_id=conversation_id,
                    )
                else:
                    self.parent._logger.warning(
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

            self.parent._logger.info(
                "expediente_sub_mode_response",
                sub_mode=sub_mode_name,
                response_length=len(ai_response),
                tools_called=list(tools_called),
                has_pending_images=pending_images is not None,
            )

            # Clear transition marker once the destination turn consumed it.
            # Keep it only when a new transition is set in this same turn.
            if (
                active_transition_marker
                and "expediente_transition_marker" not in context_updates
            ):
                # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint; never use pop() alone
                updated_context.pop("expediente_transition_marker", None)
                updated_context["expediente_transition_marker"] = None  # TOMBSTONE
                updated_context.pop("just_transitioned_from", None)
                updated_context["just_transitioned_from"] = None  # TOMBSTONE
                self.parent._logger.info(
                    "expediente_transition_marker_cleared",
                    from_sub_mode=active_transition_marker.get("from_sub_mode"),
                    to_sub_mode=active_transition_marker.get("to_sub_mode"),
                    sub_mode=sub_mode_name,
                    conversation_id=conversation_id,
                )

            return result_dict

        finally:
            # ── 7. Cleanup ContextVars ──────────────────────────────────────
            # CRITICAL: Always clear state to prevent leakage to other conversations
            clear_current_state()
            clear_image_tools_state()
            # ── Deactivate per-turn dedup cache ────────────────────────────
            self.parent._tool_dedup_cache = None

    @staticmethod
    def extract_context_from_tool(
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
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=COLLECT_ELEMENT_DATA,
                    to_sub_mode=COLLECT_BASE_DOCS,
                    tool_name=tool_name,
                )

        elif tool_name == "confirmar_documentacion_base":
            # Only advance when success=True AND not already_confirmed AND not
            # escalated.  When escalated=True the tool handed off to a human
            # agent — advancing the sub-mode would skip the base-docs phase
            # that still needs human review.
            if (
                data.get("success")
                and not data.get("already_confirmed")
                and not data.get("escalated")
            ):
                _set_transition_updates(
                    updates=updates,
                    from_sub_mode=COLLECT_BASE_DOCS,
                    to_sub_mode=COLLECT_PERSONAL,
                    tool_name=tool_name,
                )

        elif tool_name == "actualizar_datos_expediente":
            # Detect transition by next_step in result (not by "seccion" param which doesn't exist)
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step == "collect_vehicle":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_PERSONAL,
                        to_sub_mode=COLLECT_VEHICLE,
                        tool_name=tool_name,
                    )
                elif next_step == "collect_workshop":
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_VEHICLE,
                        to_sub_mode=COLLECT_WORKSHOP,
                        tool_name=tool_name,
                    )

        elif tool_name == "actualizar_datos_taller":
            if data.get("success"):
                next_step = data.get("next_step")
                if next_step is None:
                    pass
                elif next_step == "collect_workshop":
                    # Still collecting workshop data (taller_propio=True, need details)
                    pass  # Stay in COLLECT_WORKSHOP, don't transition
                else:
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=COLLECT_WORKSHOP,
                        to_sub_mode=REVIEW_SUMMARY,
                        tool_name=tool_name,
                    )

        elif tool_name == "finalizar_expediente":
            if data.get("success"):
                # Mark as completed — transition to COMPLETED mode
                updates["expediente_completed"] = True
                updates["_transition_to"] = "COMPLETED"

        elif tool_name == "iniciar_expediente":
            if data.get("success"):
                # Propagate intro_already_sent flag from _internal_flags to
                # mode_context so that subsequent calls to
                # build_new_expediente_case_instructions() know the intro was
                # already delivered via expediente_intro_message.
                flags = data.get("_internal_flags", {})
                if isinstance(flags, dict) and flags.get("intro_already_sent"):
                    updates["intro_already_sent"] = True

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
                    _set_transition_updates(
                        updates=updates,
                        from_sub_mode=REVIEW_SUMMARY,
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
            if (
                data.get("all_required_collected")
                and data.get("action") == "ELEMENT_DATA_COMPLETE"
            ):
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
        # Tools wrap updates in: {"case_collection_update": {"case_collection": {actual_updates}}}
        # We need to unwrap BOTH levels to extract the actual state changes.
        #
        # Level 1: data["case_collection_update"]["case_collection"] (standard v1 tool pattern)
        # Level 2: data["case_collection"] (direct — fallback if tool returns flat)
        if "case_collection_update" in data:
            fsm_update = data["case_collection_update"]
            if isinstance(fsm_update, dict):
                case_coll = fsm_update.get("case_collection", {})
                if isinstance(case_coll, dict) and case_coll:
                    updates.update(case_coll)
                    logger.debug(
                        "applied_case_collection_update_to_mode_context",
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

        if isinstance(data.get("expediente_intro_message"), str):
            updates["expediente_intro_message"] = data["expediente_intro_message"]
        if isinstance(data.get("expediente_intro_sent"), bool):
            updates["expediente_intro_sent"] = data["expediente_intro_sent"]

        marker = updates.get("expediente_transition_marker")
        if isinstance(marker, dict):
            logger.info(
                "expediente_transition_marker_set",
                from_sub_mode=marker.get("from_sub_mode"),
                to_sub_mode=marker.get("to_sub_mode"),
                tool=marker.get("tool_name"),
                requires_kickoff=marker.get("requires_kickoff"),
            )

        # ===================================================================
        # ADAPTER INTEGRATION: Canonical transition canonicalization (Task 3.1)
        # ===================================================================
        # Normalize heterogeneous transition signals into canonical sub-mode values.
        # This is additive: existing extraction logic runs first, then adapter
        # may override if it finds a different canonical value from any channel.
        from shared.config import get_settings

        settings = get_settings()
        if settings.ENABLE_CANONICAL_TRANSITION_ADAPTER:
            # Build tool_result from available data (the parsed result dict)
            tool_result = data if isinstance(data, dict) else {}

            transition = canonicalize_transition(tool_result)

            if transition.target_sub_mode is not None:
                # Adapter found a canonical transition — apply it
                updates["expediente_sub_mode"] = transition.target_sub_mode
                logger.info(
                    "expediente_transition_canonicalized",
                    target=transition.target_sub_mode,
                    source=transition.source_channel,
                    conflicts=transition.conflicts,
                    tool_name=tool_name,
                )
        # ===================================================================

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

    @staticmethod
    def _get_active_transition_marker(
        mode_context: dict[str, Any],
        sub_mode_name: str,
    ) -> dict[str, Any] | None:
        """Return marker when current turn is destination post-transition turn."""
        current_sub_mode = sub_mode_name.lower()

        marker = mode_context.get("expediente_transition_marker")
        if isinstance(marker, dict):
            marker_to = marker.get("to_sub_mode")
            if marker_to == current_sub_mode and marker.get("requires_kickoff"):
                return marker
            return None

        # Backward compatibility for contexts that only have legacy marker.
        legacy_from = mode_context.get("just_transitioned_from")
        if legacy_from:
            return {
                "from_sub_mode": legacy_from,
                "to_sub_mode": current_sub_mode,
                "tool_name": "legacy_marker",
                "requires_kickoff": True,
            }

        return None

    @staticmethod
    def _is_actionable_kickoff_response(response_text: str) -> bool:
        """Heuristic to detect whether first destination turn is actionable."""
        if not response_text:
            return False

        text = response_text.strip().lower()
        if not text:
            return False

        if "?" in text:
            return True

        actionable_cues = (
            "enviame",
            "envíame",
            "necesito",
            "indica",
            "indicame",
            "indícame",
            "dime",
            "confirma",
            "comparte",
            "facilita",
            "pasa",
        )
        return any(cue in text for cue in actionable_cues)

    @staticmethod
    def _build_next_element_kickoff(
        completed_element_name: str,
        next_element_name: str,
        element_phase: str,
    ) -> str | None:
        """Build deterministic kickoff message for element N+1 within COLLECT_ELEMENT_DATA.

        Returns a deterministic Spanish message confirming element N is complete and
        announcing element N+1 with phase-appropriate instruction.
        Returns None if next_element_name is falsy (graceful degradation).
        """
        if not next_element_name:
            return None

        line1 = f"{completed_element_name} completado ✅"
        line2 = f"Ahora necesito la documentación de: **{next_element_name}**."

        if element_phase == "photos":
            line3 = "Envíame las fotos correspondientes cuando puedas."
        elif element_phase == "data":
            line3 = "Dime los datos técnicos cuando puedas."
        else:
            line3 = "Dime cuando estés listo para continuar."

        return f"{line1}\n{line2}\n{line3}"

    @staticmethod
    def _build_transition_kickoff_message(
        *,
        sub_mode_name: str,
        mode_context: dict[str, Any],
    ) -> str:
        """Fallback destination kickoff to prevent dead-air after transition."""
        from agent.services.expediente_constants import CERT_SUPPLEMENT_EUR

        # Map UPPER_CASE sub_mode_name to lower-case constant for prefix lookup
        sub_mode_lower = sub_mode_name.lower()
        prefix = _progress_prefix(sub_mode_lower)

        if sub_mode_name == "COLLECT_BASE_DOCS":
            body = (
                "Perfecto. Para continuar necesito que me envies fotos legibles de la ficha tecnica, "
                "permiso de circulacion y DNI del titular (ambas caras)."
            )
            cta = "¿Tienes los documentos a mano para enviarlos?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_PERSONAL":
            body = (
                "Perfecto. Ahora necesito tus datos personales para el expediente: nombre, apellidos, "
                "DNI/CIF, email, domicilio completo e ITV."
            )
            cta = "¿Tienes todo listo para empezar?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_VEHICLE":
            body = "Perfecto. Ahora necesito los datos del vehiculo: marca, modelo, ano, matricula y bastidor (VIN)."
            cta = "¿Tienes la documentacion del vehiculo a mano?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "COLLECT_WORKSHOP":
            # Keep workshop messaging coherent with explicit decision state.
            if mode_context.get("taller_propio") is False:
                body = (
                    f"Perfecto. Confirmame si quieres que MSI gestione el certificado de taller por {CERT_SUPPLEMENT_EUR} EUR +IVA "
                    "para continuar con el expediente."
                )
            else:
                body = (
                    f"Para la ITV necesitamos el certificado del taller. ¿Prefieres que MSI lo gestione por {CERT_SUPPLEMENT_EUR} EUR +IVA "
                    "o tienes taller propio registrado?"
                )
            cta = "¿Como prefieres proceder?"
            return f"{prefix}\n\n{body}\n\n{cta}"

        if sub_mode_name == "REVIEW_SUMMARY":
            # Terminal step — no CTA, just the informational message
            body = "Perfecto. Te presento el resumen del expediente en este paso y luego me confirmas si esta todo correcto."
            return f"{prefix}\n\n{body}"

        # Fallback for unknown sub-modes
        default_message = "Perfecto, seguimos con el siguiente paso del expediente."
        if prefix:
            return f"{prefix}\n\n{default_message}"
        return default_message

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
