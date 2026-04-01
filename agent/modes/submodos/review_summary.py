"""
Handler for EXPEDIENTE REVIEW_SUMMARY sub-mode.

Present summary of all collected data.
User confirms → finalizar_expediente()
User rejects  → editar_expediente()

Pre-call: obtener_estado_expediente() is called deterministically before the
LLM loop so the summary is always based on DB truth, even when stale prices
exist in conversation history.  See ADR-010.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Coroutine

import structlog

from agent.modes.submodos._shared import _get_review_tools
from agent.state.conversation_state import ConversationState
from agent.state.helpers import set_current_state
from agent.tools.image_tools import set_current_state_for_image_tools

logger = structlog.get_logger(__name__)


class ReviewHandler:
    """Handler for REVIEW_SUMMARY sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to REVIEW_SUMMARY."""
        return _get_review_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle REVIEW_SUMMARY sub-mode.

        Deterministic pre-call pattern (ADR-010, rule 13):
          1. Call obtener_estado_expediente() unconditionally before the LLM loop.
          2. If the call falls back to mode_context (stale data), block and retry;
             escalate after 2 consecutive failures.
          3. On success, pass the JSON result via pre_call_tool_result / pre_call_tool_name
             kwargs to llm_loop_fn so the LLM sees authoritative DB data before responding.
        """
        from agent.tools.case_tools import obtener_estado_expediente

        tools = self.get_tools()

        # ── Deterministic pre-call: set ContextVars so the tool can read state ──
        # _run_llm_loop will call set_current_state again with the same values,
        # which is harmless.
        full_state_for_precall = dict(state)  # type: ignore[arg-type]
        full_state_for_precall["mode_context"] = mode_context
        set_current_state(full_state_for_precall)  # type: ignore[arg-type]
        set_current_state_for_image_tools(full_state_for_precall)  # type: ignore[arg-type]

        conversation_id = state.get("conversation_id", "unknown")
        pre_call_json: str | None = None
        pre_call_result: dict[str, Any] = {}
        try:
            pre_call_result = await obtener_estado_expediente.ainvoke({})
            pre_call_json = json.dumps(pre_call_result, ensure_ascii=False)
            logger.info(
                "review_pre_call_obtener_estado",
                conversation_id=conversation_id,
                has_active_case=pre_call_result.get("has_active_case"),
                precio_total=pre_call_result.get("precio_total"),
            )
        except Exception as exc:
            logger.warning(
                "review_pre_call_failed",
                conversation_id=conversation_id,
                error=str(exc),
            )
            # Treat a failed pre-call as fallback data to trigger the guard below
            pre_call_result = {"data_source": "fallback"}

        # ── Fallback guard: block review if state came from stale mode_context ──
        # If obtener_estado_expediente() fell back to mode_context (DB unavailable
        # or case_id missing), the precio_total may be stale — do NOT render the
        # review summary. Block and retry (escalate after 2 consecutive failures).
        if pre_call_result.get("data_source") == "fallback":
            fallback_count = mode_context.get("_review_fallback_count", 0) + 1
            logger.warning(
                "review_blocked_fallback_data",
                conversation_id=conversation_id,
                fallback_count=fallback_count,
            )
            if fallback_count >= 2:
                # Escalate after 2 consecutive fallback blocks
                from agent.tools.shared_tools import escalar_a_humano as _escalar

                await _escalar.ainvoke(
                    {
                        "motivo": (
                            "Review blocked: obtener_estado_expediente returned fallback "
                            f"data {fallback_count} consecutive times. "
                            "Possible DB connectivity issue."
                        ),
                        "es_error_tecnico": True,
                    }
                )
                logger.warning(
                    "review_fallback_escalated",
                    conversation_id=conversation_id,
                    fallback_count=fallback_count,
                )
                # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint;
                # never use pop() alone
                mode_context.pop("_review_fallback_count", None)
                mode_context["_review_fallback_count"] = None  # TOMBSTONE
                return {
                    "ai_response": (
                        "Estoy teniendo dificultades para verificar los datos de tu expediente. "
                        "Voy a pasarte con un agente de MSI que podrá ayudarte directamente."
                    ),
                    "mode_context": {
                        **mode_context,
                        "_review_fallback_count": None,  # TOMBSTONE
                        "review_blocked_reason": "stale_data",
                    },
                }
            else:
                # Block and ask user to retry
                return {
                    "ai_response": (
                        "Estoy verificando los datos de tu expediente. "
                        "¿Puedes repetir tu mensaje en unos segundos?"
                    ),
                    "mode_context": {
                        **mode_context,
                        "_review_fallback_count": fallback_count,
                        "review_blocked_reason": "stale_data",
                    },
                }

        # DB read succeeded — tombstone the fallback counter if it was previously set
        if mode_context.get("_review_fallback_count") is not None:
            # TOMBSTONE: assign None after pop so merge_dicts overwrites checkpoint;
            # never use pop() alone
            mode_context.pop("_review_fallback_count", None)
            mode_context["_review_fallback_count"] = None  # TOMBSTONE

        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="REVIEW_SUMMARY",
            pre_call_tool_result=pre_call_json,
            pre_call_tool_name="obtener_estado_expediente",
        )
