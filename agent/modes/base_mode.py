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
from typing import Any

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
        message = state.get("user_message", "")
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
