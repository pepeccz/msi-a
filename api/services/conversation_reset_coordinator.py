"""Coordinator skeleton for ordered conversation reset pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from api.models.conversation_reset import (
    ConversationResetResponse,
    ResetDomain,
    ResetDomainResult,
    ResetScope,
)


@dataclass(slots=True)
class ResetExecutionContext:
    """Normalized reset context shared by all domain executors."""

    conversation_uuid: UUID
    conversation_id: str
    scope: ResetScope = "standard"
    include_chatwoot: bool = False
    case_image_filenames: list[str] | None = None


class ResetDomainExecutor(Protocol):
    """Interface for a reset stage executor."""

    domain: ResetDomain

    async def execute(self, context: ResetExecutionContext) -> ResetDomainResult:
        """Run domain-specific cleanup and report status."""
        raise NotImplementedError


class ConversationResetCoordinator:
    """Coordinates ordered reset execution across cleanup domains."""

    PIPELINE_ORDER: tuple[ResetDomain, ...] = ("database", "redis", "files")
    OPTIONAL_ORDER: tuple[ResetDomain, ...] = ("chatwoot",)

    def __init__(self, executors: dict[ResetDomain, ResetDomainExecutor]) -> None:
        self._executors = executors

    async def run(self, context: ResetExecutionContext) -> ConversationResetResponse:
        """Execute reset pipeline with DB-first ordering contract."""
        started_at = datetime.now(UTC)
        domain_results: list[ResetDomainResult] = []

        db_result = await self._execute_domain("database", context)
        domain_results.append(db_result)

        if db_result.status == "failed":
            completed_at = datetime.now(UTC)
            return ConversationResetResponse(
                success=False,
                message="Reset aborted: database cleanup failed",
                conversation_uuid=context.conversation_uuid,
                conversation_id=context.conversation_id,
                scope=context.scope,
                include_chatwoot=context.include_chatwoot,
                requested_at=started_at,
                completed_at=completed_at,
                partial_failure=False,
                domains=domain_results,
            )

        for domain in self.PIPELINE_ORDER[1:]:
            domain_results.append(await self._execute_domain(domain, context))

        for domain in self.OPTIONAL_ORDER:
            if domain == "chatwoot" and not context.include_chatwoot:
                domain_results.append(
                    ResetDomainResult(
                        domain=domain,
                        status="skipped",
                        details={"reason": "include_chatwoot=false"},
                    )
                )
                continue

            domain_results.append(await self._execute_domain(domain, context))

        failed_domains = [result for result in domain_results if result.status == "failed"]
        required_failures = [
            result
            for result in failed_domains
            if result.domain in self.PIPELINE_ORDER
        ]
        has_partial_domains = any(
            result.status in {"failed", "partial"}
            for result in domain_results
            if result.domain in (*self.PIPELINE_ORDER[1:], *self.OPTIONAL_ORDER)
        )
        completed_at = datetime.now(UTC)
        return ConversationResetResponse(
            success=not required_failures,
            message=(
                "Conversation reset completed"
                if not has_partial_domains
                else "Conversation reset completed with partial failures"
            ),
            conversation_uuid=context.conversation_uuid,
            conversation_id=context.conversation_id,
            scope=context.scope,
            include_chatwoot=context.include_chatwoot,
            requested_at=started_at,
            completed_at=completed_at,
            partial_failure=has_partial_domains,
            domains=domain_results,
        )

    async def _execute_domain(
        self,
        domain: ResetDomain,
        context: ResetExecutionContext,
    ) -> ResetDomainResult:
        """Execute one domain or report skipped when no executor is registered."""
        executor = self._executors.get(domain)
        if not executor:
            return ResetDomainResult(
                domain=domain,
                status="skipped",
                details={"reason": "executor_not_registered"},
            )

        return await executor.execute(context)
