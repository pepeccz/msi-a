"""Optional Chatwoot cleanup executor for conversation reset pipeline."""

from __future__ import annotations

import logging
from typing import Literal

from api.models.conversation_reset import ResetDomainResult
from api.services.conversation_reset_coordinator import ResetExecutionContext
from shared.chatwoot_client import ChatwootClient

logger = logging.getLogger(__name__)


class ConversationResetChatwootExecutor:
    """Best-effort Chatwoot annotation cleanup that never blocks local reset."""

    domain: Literal["chatwoot"] = "chatwoot"

    def __init__(self, client: ChatwootClient | None = None) -> None:
        self._client = client or ChatwootClient()

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        try:
            conversation_id = int(context.conversation_id)
        except ValueError:
            return ResetDomainResult(
                domain=self.domain,
                status="skipped",
                details={"reason": "invalid_chatwoot_conversation_id"},
            )

        operations_ok = 0
        errors: list[str] = []

        try:
            note_ok = await self._client.add_private_note(
                conversation_id,
                "Reset administrativo ejecutado: conversación reiniciada en MSI-a.",
            )
            operations_ok += int(bool(note_ok))
        except Exception as exc:  # pragma: no cover - external dependency branch
            errors.append(f"add_private_note={exc}")

        try:
            labels_ok = await self._client.add_labels(
                conversation_id,
                ["reset-msia"],
            )
            operations_ok += int(bool(labels_ok))
        except Exception as exc:  # pragma: no cover - external dependency branch
            errors.append(f"add_labels={exc}")

        if errors:
            logger.warning(
                "conversation_reset_chatwoot_partial",
                extra={
                    "conversation_id": context.conversation_id,
                    "errors": errors,
                },
            )
            return ResetDomainResult(
                domain=self.domain,
                status="partial",
                details={"operations_ok": operations_ok, "operations_total": 2},
                error="; ".join(errors),
            )

        return ResetDomainResult(
            domain=self.domain,
            status="success",
            details={"operations_ok": operations_ok, "operations_total": 2},
        )
