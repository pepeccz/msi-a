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
        2. Delegate to ``_process_message`` (mode-specific)
        3. On success → reset consecutive error counter
        4. On error  → increment counter, check fallback

        Returns:
            Dict with state updates to merge into the graph state.
        """
        message = cast(str, state.get("user_message", ""))
        retry_state: RetryStateData = state.get("retry_state", create_empty_retry_state())

        try:
            # Mode-specific processing
            result = await self._process_message(message, state)

            # Success: reset consecutive errors
            updated_retry = self._fallback.record_success(retry_state, self._policy)

            # Merge retry update into result
            result["retry_state"] = updated_retry
            result["last_node"] = self.mode_name
            result["updated_at"] = datetime.now(UTC).isoformat()
            result["last_activity_at"] = datetime.now(UTC).isoformat()

            return result

        except Exception as exc:
            return self._handle_error(exc, retry_state, state)

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
    # Constraint validation (anti-hallucination)
    # ------------------------------------------------------------------

    async def _validate_response_constraints(
        self,
        ai_content: str,
        tools_called: list[str],
        state: ConversationState,
    ) -> tuple[bool, str | None]:
        """
        Validate LLM response against database-driven constraints.
        
        This prevents hallucinations like mentioning prices without calling
        calcular_tarifa, or sending images without tools.
        
        Args:
            ai_content: LLM response text
            tools_called: List of tool names called in this turn
            state: Current conversation state
        
        Returns:
            Tuple of (is_valid, error_injection_message)
            - If valid: (True, None)
            - If invalid: (False, "Error message to inject")
        """
        from agent.services.constraint_service import (
            get_constraints_for_category,
            validate_response,
        )
        
        # Extract category_slug from mode_context or context
        mode_context = state.get("mode_context", {})
        category_slug = mode_context.get("category_slug")
        # Note: category_slug can be None — global constraints still apply
        
        try:
            constraints = await get_constraints_for_category(category_slug)
            if not constraints:
                return True, None
            
            # Validate response
            is_valid, error_injection = validate_response(
                ai_content,
                set(tools_called) if isinstance(tools_called, list) else tools_called,
                constraints,
                fsm_state=dict(state.get("mode_context", {})),  # Pass mode_context for FSM compatibility
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
            usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
            if not usage:
                return
            
            input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
            
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

    async def _log_tool_call(
        self,
        conversation_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        execution_time_ms: int | None = None,
        iteration: int = 0,
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
        
        is_valid, errors = await validator.validate(
            tool=tool_fn,
            params=tool_args,
            state=validation_state,
        )

        if not is_valid:
            self._logger.warning(
                "tool_parameter_validation_failed",
                tool=tool_name,
                errors=errors,
                provided_params=list(tool_args.keys()),
            )

            # Return structured error to LLM
            from agent.utils.tool_helpers import structured_validation_error

            required_params = self._get_required_params(tool_fn)
            suggestion = self._generate_fix_suggestion(tool_fn, errors)

            error_response = structured_validation_error(
                tool_name=tool_name,
                validation_errors=errors,
                provided_params=list(tool_args.keys()),
                required_params=required_params,
                suggestion=suggestion,
            )

            # Log failed validation
            await self._log_tool_call(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=tool_args,
                result_summary=_json.dumps(error_response, ensure_ascii=False)[:500],
                execution_time_ms=0,
                iteration=iteration,
            )

            return _json.dumps(error_response, ensure_ascii=False)

        # ================================================================
        # END VALIDATION - Proceed with execution
        # ================================================================

        start = _time.time()
        result = await self._execute_tool(tool_name, tool_args, tools)
        elapsed_ms = int((_time.time() - start) * 1000)

        # Fire-and-forget persistent logging
        await self._log_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            parameters=tool_args,
            result_summary=result[:500] if isinstance(result, str) else str(result)[:500],
            execution_time_ms=elapsed_ms,
            iteration=iteration,
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
            retry_state, error_type, error_msg,
        )

        # Check if we hit the limit
        if self._fallback.should_fallback(updated_retry, self._policy):
            # Execute fallback action (escalate, reset, etc.)
            fallback_result = self._fallback.execute_fallback(
                self._policy, state, updated_retry,
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
