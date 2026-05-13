"""
MSI Automotive — Escalation Pydantic schemas.

Schemas for the escalation assignment lifecycle:
  - EscalationAssignRequest    : request body for POST /assign
  - AssignedToSummary          : embedded admin-user summary (read-only)
  - EscalationResponse         : single escalation (list + detail responses)
  - EscalationListResponse     : paginated list response
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssignedToSummary(BaseModel):
    """
    Compact read-only summary of the AdminUser assigned to or who resolved
    an escalation. Populated via selectinload on the relationship.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str | None = None
    role: str


class EscalationResponse(BaseModel):
    """
    Full representation of an Escalation record.

    The ``metadata_`` field is stored under the database column name
    ``metadata`` (alias), so callers receive the field as ``metadata``.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    conversation_id: str
    user_id: uuid.UUID | None = None
    reason: str
    source: str
    status: Literal["pending", "assigned", "resolved"]
    triggered_at: datetime

    # Assignment fields (added in Migration A)
    assigned_to_user_id: uuid.UUID | None = None
    assigned_to: AssignedToSummary | None = None
    assigned_at: datetime | None = None

    # Resolution fields
    resolved_at: datetime | None = None
    resolved_by_user_id: uuid.UUID | None = None

    # Extra metadata stored in JSONB (column aliased as "metadata" in DB)
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata_")


class EscalationAssignRequest(BaseModel):
    """Request body for POST /escalations/{id}/assign."""

    assignee_user_id: uuid.UUID = Field(
        ...,
        description="UUID of the AdminUser to assign this escalation to",
    )


class EscalationListResponse(BaseModel):
    """Paginated list of escalations."""

    items: list[EscalationResponse]
    total: int
