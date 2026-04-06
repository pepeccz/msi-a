"""Database cleanup executor for conversation reset pipeline."""

from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import delete, select

from api.models.conversation_reset import ResetDomainResult
from api.services.conversation_reset_coordinator import ResetExecutionContext
from database.connection import get_async_session
from database.models import (
    Case,
    CaseElementData,
    CaseImage,
    ConversationHistory,
    Escalation,
    RAGQuery,
)

logger = logging.getLogger(__name__)


class ConversationResetDatabaseExecutor:
    """Transactional DB cleanup for a single conversation reset."""

    domain: Literal["database"] = "database"

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        deleted_counts: dict[str, int | str | bool | None] = {
            "conversation_history": 0,
            "conversation_messages": 0,
            "cases": 0,
            "case_images": 0,
            "case_element_data": 0,
            "escalations": 0,
            "rag_queries": 0,
        }

        try:
            async with get_async_session() as session:
                conversation = await session.get(ConversationHistory, context.conversation_uuid)
                if not conversation:
                    return ResetDomainResult(
                        domain=self.domain,
                        status="failed",
                        details={"reason": "conversation_not_found"},
                        error="Conversation history record not found",
                    )

                conversation_id = conversation.conversation_id
                context.conversation_id = conversation_id

                image_filename_rows = await session.execute(
                    select(CaseImage.stored_filename)
                    .join(Case, Case.id == CaseImage.case_id)
                    .where(Case.conversation_id == conversation_id)
                )
                context.case_image_filenames = [
                    filename for filename in image_filename_rows.scalars().all() if filename
                ]

                case_id_rows = await session.execute(
                    select(Case.id).where(Case.conversation_id == conversation_id)
                )
                case_ids = list(case_id_rows.scalars().all())

                if case_ids:
                    case_image_result = await session.execute(
                        delete(CaseImage).where(CaseImage.case_id.in_(case_ids))
                    )
                    deleted_counts["case_images"] = getattr(case_image_result, "rowcount", 0) or 0

                    case_element_data_result = await session.execute(
                        delete(CaseElementData).where(CaseElementData.case_id.in_(case_ids))
                    )
                    deleted_counts["case_element_data"] = (
                        getattr(case_element_data_result, "rowcount", 0) or 0
                    )

                    case_result = await session.execute(
                        delete(Case).where(Case.id.in_(case_ids))
                    )
                    deleted_counts["cases"] = getattr(case_result, "rowcount", 0) or 0

                escalation_result = await session.execute(
                    delete(Escalation).where(Escalation.conversation_id == conversation_id)
                )
                deleted_counts["escalations"] = getattr(escalation_result, "rowcount", 0) or 0

                rag_query_result = await session.execute(
                    delete(RAGQuery).where(RAGQuery.conversation_id == conversation_id)
                )
                deleted_counts["rag_queries"] = getattr(rag_query_result, "rowcount", 0) or 0

                deleted_counts["conversation_messages"] = len(conversation.messages)
                await session.delete(conversation)
                deleted_counts["conversation_history"] = 1

                await session.commit()

            return ResetDomainResult(
                domain=self.domain,
                status="success",
                details={
                    **deleted_counts,
                    "case_image_filenames": len(context.case_image_filenames or []),
                },
            )

        except Exception as exc:  # pragma: no cover - defensive branch
            logger.error(
                "conversation_reset_db_cleanup_failed",
                extra={
                    "conversation_uuid": str(context.conversation_uuid),
                    "conversation_id": context.conversation_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return ResetDomainResult(
                domain=self.domain,
                status="failed",
                details=deleted_counts,
                error=str(exc),
            )
