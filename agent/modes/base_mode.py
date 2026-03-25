"""
MSI-a - Base Mode Node.

Abstract base class that every mode node inherits from.

Provides:
- Fallback handling (record_error / record_success / should_fallback)
- Retry state management
- Standard process() entry point
- Error classification
- Tool execution helpers

Each concrete mode must implement:
- _process_message()  → mode-specific logic
- get_tools()         → available tools for this mode
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any, cast

import structlog

from agent.fallback.fallback_handler import (
    FallbackHandler,
    RetryErrorType,
    RetryPolicy,
    get_fallback_handler,
)
from agent.state.conversation_state import (
    ConversationState,
    RetryStateData,
    create_empty_retry_state,
)

logger = structlog.get_logger(__name__)

# Tools excluded from per-turn dedup guard.
# These have their own dedup semantics or are safety-critical paths
# where the guard could interfere with correct behavior.
TOOL_DEDUP_EXCLUDED: frozenset[str] = frozenset(
    {
        "escalar_a_humano",  # Safety valve — own dedup window
        "enviar_imagenes_ejemplo",  # Rich own dedup with LLM-visible feedback
        "iniciar_expediente",  # DB record creation with own idempotency
        "finalizar_expediente",  # One-shot finalization with own guards
    }
)


class BaseModeNode(ABC):
    """
    Base class for all current conversation mode nodes.

    Usage in a mode implementation::

        class ViabilidadModeNode(BaseModeNode):

            def __init__(self):
                super().__init__("VIABILIDAD_MODE")

            async def _process_message(self, message, state):
                # ... mode-specific logic ...
                return {"ai_response": "...", "mode_context": {...}}

            def get_tools(self):
                return [identificar_elemento, ...]
    """

    # Per-turn tool-call dedup cache.
    # None  = guard inactive (between turns).
    # {}    = guard active (during a turn).
    # Set to {} at the start of _process_message(); reset to None in its finally block.
    _tool_dedup_cache: dict[str, str] | None = None

    def __init__(self, mode_name: str) -> None:
        self.mode_name = mode_name
        self._fallback: FallbackHandler = get_fallback_handler()
        self._policy: RetryPolicy = self._fallback.get_policy(mode_name)
        self._logger = logger.bind(mode=mode_name)

    # ------------------------------------------------------------------
    # Public entry point (called by the graph)
    # ------------------------------------------------------------------

    async def process(self, state: ConversationState) -> dict[str, Any]:
        """
        Main entry point called by the LangGraph node.

        Orchestrates:
        1. Extract message + retry state from graph state
        2. Start turn telemetry envelope (if flag enabled)
        3. Delegate to ``_process_message`` (mode-specific)
        4. On success → reset consecutive error counter
        5. On error  → increment counter, check fallback
        6. Emit turn telemetry

        Returns:
            Dict with state updates to merge into the graph state.
        """
        from agent.services.turn_telemetry import (
            complete_turn,
            emit_turn_telemetry,
            start_turn,
        )

        message = cast(str, state.get("user_message", ""))
        retry_state: RetryStateData = state.get(
            "retry_state", create_empty_retry_state()
        )
        conversation_id = str(state.get("conversation_id", "unknown"))

        now = datetime.now(UTC).isoformat()

        # Start telemetry envelope
        mode_context = state.get("mode_context") or {}
        sub_mode = (
            mode_context.get("expediente_sub_mode")
            if isinstance(mode_context, dict)
            else None
        )
        envelope = start_turn(conversation_id, self.mode_name, sub_mode=sub_mode)

        try:
            from shared.config import get_settings as _get_settings

            _settings = _get_settings()

            # Mode-specific processing — L3 turn timeout defense
            try:
                result = await asyncio.wait_for(
                    self._process_message(message, state),
                    timeout=float(_settings.AGENT_TURN_TIMEOUT_SECONDS),
                )
            except asyncio.TimeoutError:
                self._logger.error(
                    "turn_timeout",
                    conversation_id=conversation_id,
                    mode=self.mode_name,
                    timeout_seconds=_settings.AGENT_TURN_TIMEOUT_SECONDS,
                )
                return {
                    "ai_response": (
                        "Disculpa, me está llevando demasiado tiempo procesar tu mensaje. "
                        "¿Podrías repetirlo?"
                    ),
                    "retry_state": retry_state,
                    "last_node": f"{self.mode_name}_timeout",
                    "updated_at": now,
                    "last_activity_at": now,
                    "messages": self._build_turn_messages(
                        message,
                        "Disculpa, me está llevando demasiado tiempo procesar tu mensaje. ¿Podrías repetirlo?",
                        now,
                    ),
                }

            # Success: reset consecutive errors
            updated_retry = self._fallback.record_success(retry_state, self._policy)

            # Safety net: guarantee ai_response is never empty/None
            if not result.get("ai_response"):
                self._logger.error(
                    "empty_ai_response_safety_net",
                    mode=self.mode_name,
                    conversation_id=state.get("conversation_id"),
                )
                result["ai_response"] = (
                    "Disculpa, he tenido un problema procesando tu mensaje. "
                    "¿Puedes repetir tu consulta?"
                )

            # Merge retry update into result
            result["retry_state"] = updated_retry
            result["last_node"] = self.mode_name
            result["updated_at"] = now
            result["last_activity_at"] = now

            # If _process_message signaled escalation (e.g. validation
            # max retries), perform it NOW so Chatwoot is notified
            # immediately — don't depend on the user sending another msg.
            if result.get("escalation_triggered"):
                result = await self._perform_immediate_escalation(
                    result,
                    state,
                )

            # Validate state updates against canonical key sets
            # (gated behind ENABLE_STATE_CONTRACT_ENFORCEMENT flag)
            result, validation_warnings = self._validate_canonical_keys(result)

            # Persist conversation history to LangGraph checkpoint (Bug A fix)
            result["messages"] = self._build_turn_messages(
                message,
                result.get("ai_response", ""),
                now,
            )

            # Populate telemetry from result (best-effort)
            self._populate_telemetry_from_result(envelope, result)
            envelope.state_warnings = validation_warnings
            envelope.exit_reason = "no_tool_calls"
            complete_turn(envelope)
            emit_turn_telemetry(envelope)

            return result

        except Exception as exc:
            error_result = self._handle_error(exc, retry_state, state)

            # If fallback triggered escalation, perform it NOW
            # (don't wait for next message — user may never send one)
            if error_result.get("escalation_triggered"):
                error_result = await self._perform_immediate_escalation(
                    error_result,
                    state,
                )

            # Persist messages even on error path
            error_result["messages"] = self._build_turn_messages(
                message,
                error_result.get("ai_response", ""),
                now,
            )

            # Telemetry for error path
            envelope.exit_reason = "error"
            envelope.error = str(exc)[:500]
            complete_turn(envelope)
            emit_turn_telemetry(envelope)

            return error_result

    # ------------------------------------------------------------------
    # Message history persistence (Bug A fix)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_turn_messages(
        user_message: str,
        ai_response: str,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        """
        Build message dicts for this turn to persist in the checkpoint.

        The ``messages`` field uses an ``add`` reducer (append-only), so
        returning these from ``process()`` appends them to the history.

        Args:
            user_message: The user's message this turn.
            ai_response: The assistant's response this turn.
            timestamp: ISO timestamp for both messages.

        Returns:
            List of message dicts (user + assistant).
        """
        msgs: list[dict[str, Any]] = []
        if user_message:
            msgs.append(
                {
                    "role": "user",
                    "content": user_message,
                    "timestamp": timestamp,
                }
            )
        if ai_response:
            msgs.append(
                {
                    "role": "assistant",
                    "content": ai_response,
                    "timestamp": timestamp,
                }
            )
        return msgs

    # ------------------------------------------------------------------
    # Turn telemetry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _populate_telemetry_from_result(
        envelope: Any,
        result: dict[str, Any],
    ) -> None:
        """
        Populate telemetry envelope fields from mode result dict.

        Best-effort extraction — silently ignores missing keys.
        Mode subclasses can set fields directly on the envelope for
        more precise data (e.g. tool_iterations, tools_called).

        Args:
            envelope: ``TurnTelemetryEnvelope`` instance.
            result: Dict returned by ``_process_message()``.
        """
        # Extract state_warnings from canonical key validation
        # (set by _validate_canonical_keys → validate_state_update)
        mode_ctx = result.get("mode_context")
        if isinstance(mode_ctx, dict):
            envelope.sub_mode = mode_ctx.get("expediente_sub_mode", envelope.sub_mode)

    # ------------------------------------------------------------------
    # Abstract methods (implement in subclasses)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _process_message(
        self,
        message: str,
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Process a user message within this mode.

        Must return a dict with at least:
        - ``ai_response``: str - The response to send to the user.

        May also include:
        - ``mode_context``: dict - Updates to the current mode context.
        - ``current_mode``: str - If the mode wants to transition.
        - ``pending_images``: dict - Images to send.
        - Any other ConversationState keys.
        """
        ...

    @abstractmethod
    def get_tools(self) -> list:
        """Return the list of LangChain tools available in this mode."""
        ...

    # ------------------------------------------------------------------
    # LLM helpers (shared across all mode nodes)
    # ------------------------------------------------------------------

    # Subclasses may override this to change the default max_tokens.
    # E.g. PresupuestoModeNode sets 3000 to avoid truncation.
    _default_max_tokens: int = 1500

    def _get_llm(self, tools: list) -> "ChatOpenAI":
        """
        Get a configured ChatOpenAI instance with tools bound.

        Reads ``request_timeout`` and ``max_retries`` from Settings so
        that every LLM call has a finite HTTP timeout (L1 defense).

        Subclasses control ``max_tokens`` via the ``_default_max_tokens``
        class attribute.

        Args:
            tools: LangChain tools to bind to the model.

        Returns:
            A ``ChatOpenAI`` instance (with tools bound if any).
        """
        from langchain_openai import ChatOpenAI as _ChatOpenAI
        from shared.config import get_settings

        settings = get_settings()

        llm = _ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=self._default_max_tokens,
            request_timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
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
        """
        Try Ollama fallback when the cloud LLM fails.

        Only attempts fallback for known API errors (rate-limit,
        connection, timeout, status) **and** ``asyncio.TimeoutError``
        (L1 request timeout).  All other exceptions are re-raised
        immediately.

        Args:
            messages: The LLM message list.
            tools: LangChain tools to bind on the fallback model.
            original_error: The exception from the primary LLM call.
            conversation_id: For log correlation.

        Returns:
            The fallback LLM response.

        Raises:
            The *original_error* if fallback also fails or is not
            applicable.
        """
        import asyncio as _asyncio

        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )

        recoverable = (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            APIStatusError,
            _asyncio.TimeoutError,
        )

        if not isinstance(original_error, recoverable):
            raise original_error

        self._logger.warning(
            "cloud_llm_failed_trying_ollama",
            error_type=type(original_error).__name__,
            conversation_id=conversation_id,
        )

        try:
            from langchain_ollama import ChatOllama
            from shared.config import get_settings

            settings = get_settings()
            ollama_llm = ChatOllama(
                model=settings.LOCAL_CAPABLE_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                temperature=0.3,
                timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
            )
            if tools:
                ollama_llm = ollama_llm.bind_tools(tools)

            response = await ollama_llm.ainvoke(messages)
            self._logger.info(
                "ollama_fallback_succeeded",
                conversation_id=conversation_id,
            )
            return response

        except Exception:
            self._logger.warning(
                "ollama_fallback_failed",
                conversation_id=conversation_id,
            )
            raise original_error

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

    # ------------------------------------------------------------------
    # Tool result contract enforcement (Phase 2 hardening)
    # ------------------------------------------------------------------

    def _audit_tool_result_contract(
        self,
        tool_name: str,
        tool_result: str,
        conversation_id: str | None = None,
    ) -> None:
        """
        Audit a tool result for contract consistency.

        Checks:
        1. If ``_internal_flags`` contains ``current_mode``, logs a mode
           transition at INFO level.
        2. If both ``_internal_flags`` and ``_context_updates`` are present
           and share overlapping keys, logs an ambiguity warning.

        This is a pure observability method — it never modifies data.

        Args:
            tool_name: Name of the tool that produced the result.
            tool_result: JSON-encoded tool result string.
            conversation_id: Optional conversation ID for log correlation.
        """
        import json as _json

        try:
            data = (
                _json.loads(tool_result)
                if isinstance(tool_result, str)
                else tool_result
            )
        except (ValueError, TypeError):
            return

        if not isinstance(data, dict):
            return

        flags = data.get("_internal_flags", {})
        ctx_updates = data.get("_context_updates", {})

        # 1. Log mode transitions signaled by _internal_flags
        if isinstance(flags, dict) and "current_mode" in flags:
            self._logger.info(
                "tool_internal_flags_mode_transition",
                tool=tool_name,
                target_mode=flags["current_mode"],
                conversation_id=conversation_id,
            )

        transition_to_flag = (
            flags.get("_transition_to") if isinstance(flags, dict) else None
        )
        if transition_to_flag:
            self._logger.info(
                "tool_internal_flags_transition_signal",
                tool=tool_name,
                target_mode=transition_to_flag,
                conversation_id=conversation_id,
            )

        # 2. Warn on ambiguous dual-contract keys
        if isinstance(flags, dict) and isinstance(ctx_updates, dict):
            overlap = set(flags.keys()) & set(ctx_updates.keys())
            if overlap:
                self._logger.warning(
                    "tool_result_contract_ambiguity",
                    tool=tool_name,
                    conflicting_keys=sorted(overlap),
                    conversation_id=conversation_id,
                    detail=(
                        "Tool returned both _internal_flags and _context_updates "
                        "with overlapping keys. _internal_flags should take precedence."
                    ),
                )

    # ------------------------------------------------------------------
    # Canonical key validation (state contract enforcement)
    # ------------------------------------------------------------------

    def _validate_canonical_keys(
        self,
        result: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Validate mode result against canonical key sets.

        Checks both the top-level state update keys and mode_context keys
        (if present) against the canonical sets defined in
        ``agent.state.mode_context_keys``.

        Gated behind ``ENABLE_STATE_CONTRACT_ENFORCEMENT``:
        - True: strips unknown keys and logs warnings.
        - False: logs at DEBUG level only (no data modification).

        Args:
            result: Dict of state updates returned by ``_process_message()``.

        Returns:
            Tuple of (validated result dict, list of warning strings).
        """
        from agent.state.mode_context_keys import (
            validate_mode_context_update,
            validate_state_update,
        )

        all_warnings: list[str] = []

        # Validate top-level state keys
        result, state_warnings = validate_state_update(result, self.mode_name)
        all_warnings.extend(state_warnings)

        # Validate mode_context keys if present
        mode_ctx = result.get("mode_context")
        if isinstance(mode_ctx, dict):
            cleaned_ctx, ctx_warnings = validate_mode_context_update(
                mode_ctx,
                self.mode_name,
            )
            all_warnings.extend(ctx_warnings)
            if ctx_warnings:
                result["mode_context"] = cleaned_ctx

        return result, all_warnings

    # ------------------------------------------------------------------
    # Constraint validation (anti-hallucination)
    # ------------------------------------------------------------------

    async def _validate_response_constraints(
        self,
        ai_content: str,
        tools_called: list[str],
        state: ConversationState,
        current_mode_context: dict[str, Any] | None = None,
        available_tool_names: set[str] | None = None,
    ) -> tuple[bool, str | None]:
        """
        Validate LLM response against database-driven constraints.

        This prevents hallucinations like mentioning prices without calling
        calcular_tarifa, or sending images without tools.

        Args:
            ai_content: LLM response text
            tools_called: List of tool names called in this turn
            state: Current conversation state
            current_mode_context: OPTIONAL - The mode_context updated during THIS turn.
                If provided, used instead of state["mode_context"] for skip logic.
                This fixes the stale-state bug where tarifa_calculada computed in
                the same turn wasn't visible to _should_skip_constraint().
            available_tool_names: OPTIONAL - Set of tool names available in the
                current mode. If provided, constraints whose required tools are
                not available will be skipped (prevents false violations in modes
                that don't have the required tools).

        Returns:
            Tuple of (is_valid, error_injection_message)
            - If valid: (True, None)
            - If invalid: (False, "Error message to inject")
        """
        from agent.services.constraint_service import (
            get_constraints_for_category,
            validate_response_hybrid,
        )

        # Use current turn's mode_context if provided, otherwise fall back to state
        mode_context = (
            current_mode_context
            if current_mode_context is not None
            else dict(state.get("mode_context", {}))
        )
        category_slug = mode_context.get("category_slug")
        # Note: category_slug can be None — global constraints still apply

        try:
            constraints = await get_constraints_for_category(category_slug)
            if not constraints:
                return True, None

            # Phase 2: Hybrid validation — regex pre-filter + LLM confirmation
            # Uses current turn's mode_context for accurate skip logic (Phase 1B fix)
            is_valid, error_injection = await validate_response_hybrid(
                ai_content,
                set(tools_called) if isinstance(tools_called, list) else tools_called,
                constraints,
                fsm_state=mode_context,
                available_tool_names=available_tool_names,
            )

            if not is_valid and error_injection:
                self._logger.warning(
                    "constraint_violation",
                    tools_called=tools_called,
                    error=error_injection,
                )

            return is_valid, error_injection

        except Exception as e:
            # Never block the agent on constraint validation errors
            self._logger.error(
                "constraint_validation_error",
                error=str(e),
                exc_info=True,
            )
            return True, None  # Fail open

    # ------------------------------------------------------------------
    # Token tracking (cost monitoring)
    # ------------------------------------------------------------------

    async def _track_token_usage(
        self,
        conversation_id: str,
        response: Any,
    ) -> None:
        """
        Track token usage from LLM response.

        Fire-and-forget - errors never block the agent.

        Args:
            conversation_id: Conversation ID
            response: LLM response object (with usage attribute)
        """
        from agent.services.token_tracking import record_token_usage

        try:
            usage = getattr(response, "usage_metadata", None) or getattr(
                response, "usage", None
            )
            if not usage:
                return

            input_tokens = getattr(usage, "input_tokens", 0) or getattr(
                usage, "prompt_tokens", 0
            )
            output_tokens = getattr(usage, "output_tokens", 0) or getattr(
                usage, "completion_tokens", 0
            )

            if input_tokens > 0 or output_tokens > 0:
                await record_token_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
        except Exception as e:
            # Never block the agent on tracking errors
            self._logger.debug(
                "token_tracking_error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Tool logging (observability)
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_tool_result(result: str) -> tuple[str, str | None]:
        """
        Classify a tool result string as "success", "error", or "blocked".

        Inspects the raw result (JSON string or plain text) to derive an
        explicit ``result_type`` and an optional ``error_message`` without
        relying on fragile text-matching heuristics in
        ``classify_result()``.

        Classification rules
        --------------------
        - **error**:   result is a JSON dict with ``success=False`` OR
                       ``"error"`` key present, OR result is a non-JSON
                       plain-text string.
        - **blocked**: result is a JSON dict containing at least one of the
                       known duplicate-block phrases.
        - **success**: anything else.

        Args:
            result: The raw string returned by ``_execute_tool``.

        Returns:
            Tuple of (result_type, error_message).
            ``error_message`` is ``None`` when ``result_type`` is not
            ``"error"``.
        """
        import json as _json

        if not result:
            return ("success", None)

        # --- Attempt JSON parse ---
        try:
            data = _json.loads(result)
        except (ValueError, TypeError):
            # Non-JSON plain text → treat as error
            return (
                "error",
                result[:500] if isinstance(result, str) else str(result)[:500],
            )

        if not isinstance(data, dict):
            # Valid JSON but not a dict (e.g. list, int) → success
            return ("success", None)

        # --- Explicit success=False or error key ---
        if data.get("success") is False or "error" in data:
            error_msg: str | None = (
                data.get("error") or data.get("message") or "Tool returned failure"
            )
            if isinstance(error_msg, str):
                error_msg = error_msg[:500]
            # Distinguish blocked from error
            _block_phrases = (
                "ya fueron enviadas",
                "no vuelvas a enviar",
                "ya fue enviada",
                "bloqueando duplicado",
            )
            result_lower = result.lower()
            if any(p in result_lower for p in _block_phrases):
                return ("blocked", None)
            return ("error", error_msg)

        return ("success", None)

    async def _log_tool_call(
        self,
        conversation_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        execution_time_ms: int | None = None,
        iteration: int = 0,
        result_type: str = "success",
        error_message: str | None = None,
    ) -> None:
        """
        Log tool call to database for observability.

        This is fire-and-forget - errors never block the agent.

        Args:
            conversation_id: Conversation ID
            tool_name: Name of the tool called
            parameters: Tool parameters (will be sanitized)
            result_summary: Tool result summary (will be truncated)
            execution_time_ms: Execution time in milliseconds
            iteration: Current iteration number
            result_type: Explicit outcome classification ("success", "error",
                "blocked"). Defaults to "success" for backward compatibility.
            error_message: Full error message when result_type is "error".
        """
        from agent.services.tool_logging_service import log_tool_call

        try:
            await log_tool_call(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=parameters,
                result_summary=result_summary,
                execution_time_ms=execution_time_ms,
                iteration=iteration,
                result_type=result_type,
                error_message=error_message,
            )
        except Exception as e:
            # Never block the agent on logging errors
            self._logger.debug(
                "tool_logging_error",
                error=str(e),
                tool=tool_name,
            )

    # ------------------------------------------------------------------
    # Tool execution (shared logic)
    # ------------------------------------------------------------------

    @staticmethod
    async def _execute_tool(
        tool_name: str,
        tool_args: dict[str, Any],
        tools: list,
    ) -> str:
        """
        Execute a tool by name and return its string result.

        Finds the tool in the provided list, invokes it, and ensures
        the result is always a string (JSON-encodes dicts).
        """
        import json as _json

        tool_fn = None
        for t in tools:
            if t.name == tool_name:
                tool_fn = t
                break

        if tool_fn is None:
            return f"Error: herramienta '{tool_name}' no encontrada"

        try:
            result = await tool_fn.ainvoke(tool_args)
            if isinstance(result, dict):
                return _json.dumps(result, ensure_ascii=False)
            return str(result)
        except Exception as e:
            logger.error("tool_execution_error", tool=tool_name, error=str(e))
            return f"Error ejecutando {tool_name}: {str(e)}"

    async def _execute_and_log_tool(
        self,
        conversation_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        tools: list,
        iteration: int = 0,
    ) -> str:
        """
        Execute a tool with validation, timing, and persistent logging.

        NEW: Validates parameters BEFORE execution (defensive programming).

        Combines validation + _execute_tool + timing + _log_tool_call into
        a single call. All modes should use this instead of _execute_tool directly.

        Args:
            conversation_id: Conversation ID for logging
            tool_name: Name of the tool to execute
            tool_args: Tool arguments dict
            tools: List of available tools
            iteration: Current tool loop iteration (1-based)

        Returns:
            String result from the tool execution (or validation error as JSON)
        """
        import json as _json
        import time as _time
        from agent.utils.tool_validation import get_tool_validator

        # Find the tool instance
        tool_fn = None
        for t in tools:
            if t.name == tool_name:
                tool_fn = t
                break

        if tool_fn is None:
            error_response = {
                "success": False,
                "error": f"Herramienta '{tool_name}' no encontrada",
                "error_type": "tool_not_found",
            }
            return _json.dumps(error_response, ensure_ascii=False)

        # ================================================================
        # NEW: VALIDATE PARAMETERS BEFORE EXECUTION
        # ================================================================
        validator = get_tool_validator()

        # Extract state for validation
        # The validator will look for keys like "case_id", "categoria_slug", etc.
        # These are stored in both root state and mode_context depending on the tool.
        from agent.state.helpers import get_current_state

        # Get full state from context (set by modes before tool execution)
        current_state = get_current_state()

        # Build validation state by merging root state + mode_context
        # This ensures validators can check both state["user_id"] and state["categoria_slug"]
        validation_state: dict[str, Any] = {}
        if current_state:
            validation_state.update(current_state)
            # Also merge mode_context keys to root level for easier validation
            mode_context = current_state.get("mode_context", {})
            if mode_context:
                validation_state.update(mode_context)

        # Phase 3: Validation now returns failed layer
        is_valid, errors, failed_layer = await validator.validate(
            tool=tool_fn,
            params=tool_args,
            state=validation_state,
        )

        if not is_valid:
            self._logger.warning(
                "tool_parameter_validation_failed",
                tool=tool_name,
                errors=errors,
                validation_layer=failed_layer,  # Phase 3: log which layer failed
                provided_params=list(tool_args.keys()),
            )

            # Return structured error to LLM
            from agent.utils.tool_helpers import structured_validation_error

            required_params = self._get_required_params(tool_fn)
            suggestion = self._generate_fix_suggestion(tool_fn, errors)

            error_response = structured_validation_error(
                tool_name=tool_name,
                validation_errors=errors,
                validation_layer=failed_layer,  # Phase 3: include layer in error
                provided_params=list(tool_args.keys()),
                required_params=required_params,
                suggestion=suggestion,
            )

            # Log failed validation — always "error" result_type
            validation_error_str = _json.dumps(error_response, ensure_ascii=False)
            await self._log_tool_call(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=tool_args,
                result_summary=validation_error_str[:500],
                execution_time_ms=0,
                iteration=iteration,
                result_type="error",
                error_message=error_response.get(
                    "validation_errors", ["parameter_validation"]
                )[0]
                if isinstance(error_response.get("validation_errors"), list)
                else "parameter_validation",
            )

            return validation_error_str

        # ================================================================
        # END VALIDATION - Proceed with execution
        # ================================================================

        # ================================================================
        # PER-TURN DEDUP GUARD
        # Prevents the same (tool_name, args) pair from executing twice in
        # a single _process_message() call.  Tools in TOOL_DEDUP_EXCLUDED
        # are always executed regardless of prior calls.
        # ================================================================
        import json as _json_dedup

        _dedup_active = (
            self._tool_dedup_cache is not None and tool_name not in TOOL_DEDUP_EXCLUDED
        )
        _dedup_key: str = ""
        if _dedup_active:
            _dedup_key = f"{tool_name}:{_json_dedup.dumps(tool_args, sort_keys=True, default=str)}"
            if _dedup_key in self._tool_dedup_cache:  # type: ignore[operator]
                self._logger.info(
                    "tool_call_dedup_hit",
                    tool=tool_name,
                    conversation_id=conversation_id,
                    iteration=iteration,
                )
                return self._tool_dedup_cache[_dedup_key]  # type: ignore[index]
        # ================================================================
        # END DEDUP GUARD
        # ================================================================

        start = _time.time()
        result = await self._execute_tool(tool_name, tool_args, tools)
        elapsed_ms = int((_time.time() - start) * 1000)

        # Store result in dedup cache (if guard is active for this turn)
        if _dedup_active:
            self._tool_dedup_cache[_dedup_key] = result  # type: ignore[index]

        # Classify result for observability
        result_type, error_message = self._classify_tool_result(result)

        # Fire-and-forget persistent logging
        await self._log_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            parameters=tool_args,
            result_summary=result[:500]
            if isinstance(result, str)
            else str(result)[:500],
            execution_time_ms=elapsed_ms,
            iteration=iteration,
            result_type=result_type,
            error_message=error_message,
        )

        return result

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _get_required_params(self, tool) -> list[str]:
        """
        Extract required parameter names from tool schema.

        Args:
            tool: LangChain tool instance

        Returns:
            List of required parameter names
        """
        if not tool.args_schema:
            return []

        required = []
        for field_name, field_info in tool.args_schema.model_fields.items():
            if field_info.is_required():
                required.append(field_name)

        return required

    def _generate_fix_suggestion(self, tool, errors: list[str]) -> str:
        """
        Generate helpful suggestion for LLM to fix parameters.

        Analyzes validation errors and provides context-aware hints
        on where to find missing parameters.

        Args:
            tool: LangChain tool instance
            errors: List of validation error messages

        Returns:
            Helpful suggestion string for the LLM

        Example:
            "Please provide the categoria_slug parameter.
             You can extract it from mode_context['categoria_slug']."
        """
        # Extract missing param names from errors
        missing_params = []
        for error in errors:
            if "Missing required parameter:" in error:
                param_name = error.split(":")[-1].strip()
                missing_params.append(param_name)

        if not missing_params:
            return "Please check the parameter values and try again."

        # Generate context extraction hints
        hints = {
            "categoria_slug": "Extract from mode_context['categoria_slug']",
            "tarifa_calculada": "Extract from mode_context['tarifa_calculada']['datos']['price']",
            "tier_id": "Extract from mode_context['tarifa_calculada']['datos']['tier_id']",
            "case_id": "Extract from state or mode_context['case_id']",
            "user_id": "Extract from state['user_id']",
            "current_element_index": "Extract from mode_context['current_element_index']",
            "precio_comunicado": "Check mode_context['precio_comunicado'] flag",
        }

        suggestions = []
        for param in missing_params:
            hint = hints.get(param, f"Provide {param}")
            suggestions.append(f"- {param}: {hint}")

        return "Please provide the following parameters:\n" + "\n".join(suggestions)

    # ------------------------------------------------------------------
    # Error handling (shared logic)
    # ------------------------------------------------------------------

    def _handle_error(
        self,
        error: Exception,
        retry_state: RetryStateData,
        state: ConversationState,
    ) -> dict[str, Any]:
        """Handle an error from _process_message."""
        error_type = self._fallback.classify_error(error)
        error_msg = str(error)

        self._logger.warning(
            "mode_processing_error",
            error_type=error_type.value,
            error=error_msg,
            retry_count=retry_state.get("retry_count", 0),
        )

        # Increment retry counter
        updated_retry = self._fallback.record_error(
            retry_state,
            error_type,
            error_msg,
        )

        # Check if we hit the limit
        if self._fallback.should_fallback(updated_retry, self._policy):
            # Execute fallback action (escalate, reset, etc.)
            fallback_result = self._fallback.execute_fallback(
                self._policy,
                state,
                updated_retry,
            )
            fallback_result["last_node"] = f"{self.mode_name}_fallback"
            return fallback_result

        # Not at limit yet: send reprompt
        reprompt = self._fallback.get_reprompt(updated_retry, self._policy)

        return {
            "ai_response": reprompt,
            "retry_state": updated_retry,
            "last_node": f"{self.mode_name}_retry",
            "updated_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # Immediate escalation (fallback path)
    # ------------------------------------------------------------------

    async def _perform_immediate_escalation(
        self,
        fallback_result: dict[str, Any],
        state: ConversationState,
    ) -> dict[str, Any]:
        """
        Perform the Chatwoot + DB escalation immediately when fallback
        triggers ESCALATE_TO_HUMAN.

        Without this, the escalation only happens on the NEXT user message
        (when the router routes to escalation_node), which may never come
        because the user was told "Espera un momento...".

        The escalation_node will still fire on next message (if any) but
        the duplicate-prevention window (5 min) in escalation_service
        will prevent double-escalation.
        """
        from agent.services.escalation_service import perform_escalation

        conversation_id = state.get("conversation_id", "")
        user_id = state.get("user_id")
        user_phone = state.get("user_phone", "desconocido")
        reason = fallback_result.get("escalation_reason", "fallback_escalation")

        try:
            result = await perform_escalation(
                conversation_id=str(conversation_id),
                user_id=str(user_id) if user_id else None,
                user_phone=str(user_phone),
                reason=str(reason),
                source="fallback",
                is_technical_error=True,
            )
            # Use the service's user-facing message
            if result.get("message"):
                fallback_result["ai_response"] = result["message"]
        except Exception as e:
            self._logger.error(
                "immediate_escalation_failed",
                error=str(e),
                conversation_id=conversation_id,
                exc_info=True,
            )
            # Don't crash — the fallback_result still has the original message

        return fallback_result

    # ------------------------------------------------------------------
    # Phase 3: Validation error retry helpers
    # ------------------------------------------------------------------

    def _is_validation_error(
        self, tool_result: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Check if tool result is a validation error (Phase 3).

        Args:
            tool_result: JSON string result from _execute_and_log_tool()

        Returns:
            Tuple of (is_validation_error, parsed_error_dict)
            - If validation error: (True, error_dict)
            - Otherwise: (False, None)
        """
        import json as _json

        try:
            result_dict = (
                _json.loads(tool_result)
                if isinstance(tool_result, str)
                else tool_result
            )

            if not isinstance(result_dict, dict):
                return (False, None)

            is_error = not result_dict.get("success", True)
            is_validation = result_dict.get("error_type") == "parameter_validation"

            if is_error and is_validation:
                return (True, result_dict)

            return (False, None)

        except Exception:
            return (False, None)

    def _handle_validation_retry(
        self,
        tool_name: str,
        error_dict: dict[str, Any],
        retry_state: RetryStateData,
        llm_messages: list[dict[str, Any]],
    ) -> tuple[bool, RetryStateData]:
        """
        Handle validation error with retry logic (Phase 3).

        This method:
        1. Records the validation error in retry_state
        2. Checks if we should retry or escalate
        3. If retry: adds reprompt message to llm_messages and returns (True, updated_retry_state)
        4. If escalate: returns (False, updated_retry_state) - caller should escalate

        Args:
            tool_name: Name of the tool that failed validation
            error_dict: Parsed validation error dict
            retry_state: Current retry state
            llm_messages: LLM messages list (will be modified to add reprompt if retrying)

        Returns:
            Tuple of (should_retry, updated_retry_state)
            - should_retry=True: Continue LLM loop with reprompt
            - should_retry=False: Escalate to human (max retries reached)
        """
        validation_errors = error_dict.get("validation_errors", [])
        validation_layer = error_dict.get("validation_layer", "unknown")

        # Record validation error
        updated_retry = self._fallback.record_validation_error(
            retry_state,
            tool_name,
            validation_errors,
            validation_layer,
        )

        # Check if we hit the limit
        if self._fallback.should_fallback(updated_retry, self._policy):
            # Max retries reached - caller should escalate
            self._logger.warning(
                "validation_max_retries_reached",
                tool=tool_name,
                retry_count=updated_retry.get("retry_count"),
                max_retries=self._policy.max_retries,
                validation_layer=validation_layer,
            )
            return (False, updated_retry)

        # Not at limit yet: retry with reprompt
        reprompt = self._fallback.get_validation_reprompt(
            updated_retry, self._policy, error_dict=error_dict
        )

        self._logger.info(
            "validation_error_retry",
            tool=tool_name,
            layer=validation_layer,
            retry_count=updated_retry.get("retry_count"),
            reprompt_preview=reprompt[:100],
        )

        # Add reprompt to llm_messages as system message
        llm_messages.append(
            {
                "role": "system",
                "content": f"[VALIDATION ERROR]: {reprompt}",
            }
        )

        return (True, updated_retry)
