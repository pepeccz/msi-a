"""
Handler for EXPEDIENTE COLLECT_BASE_DOCS sub-mode.

User sends base documentation (ficha técnica, permiso, vistas).
Tool: confirmar_documentacion_base()
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

import structlog

from agent.modes.submodos._shared import _get_base_docs_tools
from agent.services.element_data_service import confirm_base_documentation
from agent.state.conversation_state import ConversationState
from agent.utils.text_utils import normalize_text

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Deterministic completion-token helper (fix-base-docs-transition-guard · Ph2)
# ──────────────────────────────────────────────────────────────────────────

_COMPLETION_EXACT: frozenset[str] = frozenset(
    {"ok", "dale", "ya", "termine", "terminado", "finalizado", "fin"}
)
_LISTO_CANONICAL: str = "listo"
_LISTO_MIN_LEN: int = 3
_LISTO_MAX_LEN: int = 6  # rejects "listado" (len 7)


def _levenshtein_le1(a: str, b: str) -> bool:
    """Return True iff Damerau-Levenshtein distance between a and b is <= 1.

    Handles: single insertion, deletion, substitution, OR a single adjacent
    transposition (e.g. "lisot" vs "listo"). O(len) scan.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    # Adjacent transposition of two equal-length strings counts as 1 edit.
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        ):
            return True
        return False
    if abs(la - lb) > 1:
        return False
    # la != lb — exactly one insertion / deletion allowed.
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


def _strip_trailing_punct(text: str) -> str:
    """Drop trailing punctuation (!?. ,;:) that users append to completion tokens."""
    return text.rstrip("!?.,;: ").lstrip()


def is_completion_token(raw: str) -> bool:
    """Return True iff the user input normalizes to a base-docs completion token.

    Rules:
      * Exact match (after `normalize_text` + trailing-punct strip) against
        `_COMPLETION_EXACT`.
      * For "listo" only: Levenshtein <= 1 with length guard
        `_LISTO_MIN_LEN <= len(norm) <= _LISTO_MAX_LEN`.
        Excludes "listado" (len 7) by length.
    """
    if not raw:
        return False
    norm = normalize_text(raw)
    if not norm:
        return False
    norm = _strip_trailing_punct(norm)
    if not norm:
        return False
    if norm in _COMPLETION_EXACT:
        return True
    if norm == _LISTO_CANONICAL:
        return True
    if _LISTO_MIN_LEN <= len(norm) <= _LISTO_MAX_LEN and _levenshtein_le1(
        norm, _LISTO_CANONICAL
    ):
        return True
    return False


class BaseDocsHandler:
    """Handler for COLLECT_BASE_DOCS sub-mode."""

    def get_tools(self) -> list:
        """Return tools scoped to COLLECT_BASE_DOCS."""
        return _get_base_docs_tools()

    async def handle(
        self,
        message: str,
        state: ConversationState,
        mode_context: dict[str, Any],
        llm_loop_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Handle COLLECT_BASE_DOCS sub-mode.

        Guards (in order):
          1. Attachment-only turns (no text) — deterministic ACK.
          2. Completion-token guard — when text normalizes to "listo"/"ok"/
             etc. and docs are sufficient, call `confirm_base_documentation`
             directly and surface `_state_update._transition_to` without a
             roundtrip to the LLM.
        Otherwise delegate to the coordinator's LLM loop.
        """
        # ── Guard 1: attachment-only turns (no text) ───────────────────────
        incoming_attachments = state.get("incoming_attachments", [])
        if not message.strip() and incoming_attachments:
            img_count = sum(
                1 for a in incoming_attachments if a.get("type") == "image"
            )
            doc_count = sum(
                1 for a in incoming_attachments if a.get("type") == "document"
            )
            parts: list[str] = []
            if img_count:
                parts.append(f"{img_count} foto(s)")
            if doc_count:
                parts.append(f"{doc_count} documento(s)")
            received_label = " y ".join(parts) if parts else f"{len(incoming_attachments)} archivo(s)"
            ack = (
                f"Recibidos: {received_label} de documentación base. "
                'Cuando hayas terminado de enviar documentos, escribe "listo".'
            )
            logger.info(
                "attachment_only_turn_ack",
                conversation_id=state.get("conversation_id", "unknown"),
                image_count=img_count,
                document_count=doc_count,
                sub_mode="COLLECT_BASE_DOCS",
            )
            return {
                "ai_response": ack,
                "mode_context": mode_context,
            }

        # ── Guard 2: deterministic completion-token close ──────────────────
        text = message.strip() if message else ""
        if text and is_completion_token(text):
            case_id = state.get("case_id")
            conversation_id = state.get("conversation_id")
            if case_id:
                try:
                    result = await confirm_base_documentation(
                        usuario_confirma=True,
                        case_id=case_id,
                        conversation_id=conversation_id,
                        mode_context=mode_context,
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        "base_docs.deterministic_close_fallthrough",
                        conversation_id=conversation_id,
                        reason="exception",
                        error=str(exc),
                    )
                    result = None
                if (
                    result
                    and result.get("success")
                    and result.get("_state_update", {}).get("_transition_to")
                ):
                    state_update = result.get("_state_update", {})
                    logger.info(
                        "base_docs.deterministic_close",
                        conversation_id=conversation_id,
                        case_id=case_id,
                        token=text,
                        normalized=normalize_text(text),
                    )
                    merged_context = {**mode_context, **state_update}
                    return {
                        "ai_response": result.get("message", ""),
                        "mode_context": merged_context,
                        "pending_state_updates": state_update,
                    }
                # Fall-through: insufficient / escalation / idempotent / error
                logger.info(
                    "base_docs.deterministic_close_fallthrough",
                    conversation_id=conversation_id,
                    case_id=case_id,
                    reason=(
                        "insufficient"
                        if result and not result.get("success")
                        else "no_transition"
                    ),
                )

        tools = self.get_tools()
        return await llm_loop_fn(
            message=message,
            state=state,
            mode_context=mode_context,
            tools=tools,
            sub_mode_name="COLLECT_BASE_DOCS",
        )
