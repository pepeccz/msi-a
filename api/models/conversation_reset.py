"""API schemas for conversation reset/delete contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ResetScope = Literal["minimal", "standard", "full"]
ResetDomain = Literal["database", "redis", "files", "chatwoot"]
ResetDomainStatus = Literal["success", "failed", "partial", "skipped"]


class ResetDomainResult(BaseModel):
    """Outcome for a single reset domain."""

    domain: ResetDomain
    status: ResetDomainStatus
    details: dict[str, int | str | bool | None] = Field(default_factory=dict)
    error: str | None = None


class ConversationResetOptions(BaseModel):
    """Reset execution options coming from API layer."""

    scope: ResetScope = "standard"
    include_chatwoot: bool = False


class ConversationResetResponse(BaseModel):
    """Canonical API response for conversation reset/delete operation."""

    success: bool
    message: str
    conversation_uuid: UUID
    conversation_id: str
    scope: ResetScope
    include_chatwoot: bool
    requested_at: datetime
    completed_at: datetime
    partial_failure: bool = False
    details: dict[str, int | str | bool | None] = Field(default_factory=dict)
    domains: list[ResetDomainResult] = Field(default_factory=list)
