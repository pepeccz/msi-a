"""
Handler for EXPEDIENTE COLLECT_ELEMENT_DATA sub-mode.

Per-element flow:
  1. Send example images (enviar_imagenes_ejemplo)
  2. User sends photos → confirmar_fotos_elemento()
  3. Ask for technical data → guardar_datos_elemento()
  4. completar_elemento_actual() → next element or COLLECT_BASE_DOCS

Notes:
  - _guard_photo_completion_intent stays in coordinator (ExpedienteModeNode)
    because it calls self.* methods. The guard's result is passed via
    mode_context["_guard_photo_fired_this_turn"] before calling handle().
  - _apply_tool_flags is imported DIRECTLY from presupuesto_mode to avoid
    a circular import via expediente_mode (coordinator).
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

import structlog

from agent.modes.submodos._shared import (
    _get_element_data_tools,
    _initialize_element_states,
)

# Import directly from presupuesto_mode to avoid circular import
# (expediente_mode imports presupuesto_mode; importing from expediente_mode
# here would create a circular dependency).
from agent.modes.presupuesto_mode import _apply_tool_flags  # noqa: F401 — re-used by callers
from agent.state.conversation_state import ConversationState
from shared.config import get_settings

logger = structlog.get_logger(__name__)


class ElementDataHandler:
    """Handler for COLLECT_ELEMENT_DATA sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to COLLECT_ELEMENT_DATA."""
        return _get_element_data_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_ELEMENT_DATA sub-mode.

        Pre-loop steps (deterministic):
          1. Reset intra-turn dedup set for element example images.
          2. (V2) Initialize per-element 7-state machine (idempotent).
          3. Photo guard: coordinator calls _guard_photo_completion_intent() and
             sets mode_context["_guard_photo_fired_this_turn"] = True if it fired.
             This handler reads that flag — it does NOT call the guard itself.
          4. (V2) Fetch fresh CollectionContext from DB for prompt injection.
          5. Image-only turn guard: acknowledge without LLM when user sends photos
             without text.

        Then delegates to the coordinator's LLM loop with element-data tools.
        """
        from agent.tools.image_tools import _clear_element_images_sent_this_turn

        # 1. Reset intra-turn dedup set for element example images
        _clear_element_images_sent_this_turn()

        conversation_id = state.get("conversation_id", "unknown")

        # 2. (V2) Initialize per-element 7-state machine (idempotent)
        _v2_settings = get_settings()
        if _v2_settings.EXPEDIENTE_V2_ENABLED:
            _el_codes: list[str] = mode_context.get("element_codes") or []
            if _el_codes:
                _initialize_element_states(mode_context, _el_codes)
                logger.debug(
                    "element_states_ready",
                    conversation_id=conversation_id,
                    element_count=len(_el_codes),
                )

        # 3. Photo guard result — already set by coordinator before calling handle()
        # The coordinator calls self._guard_photo_completion_intent() and sets
        # mode_context["_guard_photo_fired_this_turn"] = True if it fired.
        # Nothing to do here; the flag is already in mode_context for the LLM loop.

        # 4. (V2) Pre-populate collection context for prompt injection
        if _v2_settings.EXPEDIENTE_V2_ENABLED:
            _case_id_v2: str | None = mode_context.get("case_id")
            _el_codes_v2: list[str] = mode_context.get("element_codes") or []
            _cat_id_v2: str | None = mode_context.get("category_id")
            if _case_id_v2 and _el_codes_v2:
                try:
                    from agent.services.element_state_service import (
                        get_element_state_service as _get_ess_handle,
                    )

                    _ess_handle = _get_ess_handle()
                    _collection_ctx = await _ess_handle.get_collection_context(
                        _case_id_v2, _el_codes_v2, _cat_id_v2
                    )
                    mode_context["v2_collection_context"] = _collection_ctx.to_dict()
                    logger.debug(
                        "element_data_collection_context_populated",
                        conversation_id=conversation_id,
                        current_element=(
                            (_collection_ctx.current_element or {}).get("code")
                        ),
                        completed=_collection_ctx.progress.get("completed", 0),
                        total=_collection_ctx.progress.get("total", 0),
                    )
                except Exception as _ctx_err:
                    # Non-fatal: prompt will show fallback placeholder text
                    logger.warning(
                        "element_data_collection_context_failed",
                        conversation_id=conversation_id,
                        error=str(_ctx_err),
                    )

        # 5. Guard: image-only turns (no text)
        # Photos are already saved by main.py. If the user sent images without
        # text, acknowledge deterministically without invoking the LLM.
        incoming_attachments = state.get("incoming_attachments", [])
        if not message.strip() and incoming_attachments:
            element_codes = mode_context.get("element_codes", [])
            current_idx = mode_context.get("current_element_index", 0)
            display_names = mode_context.get("element_display_names", {})
            if element_codes and current_idx < len(element_codes):
                current_code = element_codes[current_idx]
                current_name = display_names.get(current_code, current_code)
                ack = (
                    f"Recibidas {len(incoming_attachments)} foto(s) para {current_name}. "
                    'Cuando hayas terminado de enviar fotos, escribe "listo".'
                )
            else:
                ack = (
                    f"Recibidas {len(incoming_attachments)} foto(s). "
                    'Cuando hayas terminado de enviar fotos, escribe "listo".'
                )
            logger.info(
                "image_only_turn_ack",
                conversation_id=conversation_id,
                image_count=len(incoming_attachments),
                sub_mode="COLLECT_ELEMENT_DATA",
            )
            return {
                "ai_response": ack,
                "mode_context": mode_context,
            }

        tools = self.get_tools()
        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_ELEMENT_DATA",
        )
