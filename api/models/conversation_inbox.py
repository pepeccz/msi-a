"""
Pydantic schemas for the unified inbox API endpoints (PR4).

Covers request/response models for T11–T20 endpoints:
- SendMessageRequest, SendTemplateRequest, PauseRequest, EscalateRequest, MarkReadRequest
- ConversationMessageResponse, ConversationHistoryResponse, EscalationResponse
- WindowStatusResponse, TemplateResponse
- InboxItemResponse, InboxListResponse, MessagesPageResponse
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    """Request body for POST /conversations/{id}/send-message."""

    content: str = Field(..., min_length=1, max_length=4096, description="Message text to send")


class SendTemplateRequest(BaseModel):
    """Request body for POST /conversations/{id}/send-template."""

    template_name: str = Field(..., min_length=1, max_length=512)
    params: dict[str, str] = Field(default_factory=dict, description="Template parameter substitutions")
    language: str = Field(..., min_length=2, max_length=10, description="BCP47 language code, e.g. es, es_ES")

    @field_validator("params")
    @classmethod
    def validate_params_values(cls, v: dict[str, str]) -> dict[str, str]:
        for key, val in v.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise ValueError("All template param keys and values must be strings")
        return v


class PauseRequest(BaseModel):
    """Request body for POST /conversations/{id}/pause."""

    reason: str | None = Field(None, max_length=500, description="Optional human-readable pause reason")


class ResumeRequest(BaseModel):
    """Request body for POST /conversations/{id}/resume."""

    pass


class EscalateRequest(BaseModel):
    """Request body for POST /conversations/{id}/escalate."""

    reason: str = Field(..., min_length=1, max_length=1000, description="Reason for escalation")
    priority: str | None = Field(None, description="Escalation priority: low, medium, high")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in ("low", "medium", "high"):
            raise ValueError("priority must be one of: low, medium, high")
        return v


class MarkReadRequest(BaseModel):
    """Request body for POST /conversations/{id}/mark-read."""

    message_ids: list[UUID] | None = Field(
        None,
        description="Specific message IDs to mark read; None marks ALL unread messages",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class MessageAttachmentResponse(BaseModel):
    """Single message attachment (image) response."""

    id: UUID
    url: str
    kind: str
    content_type: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationMessageResponse(BaseModel):
    """Single message response."""

    id: UUID
    conversation_history_id: UUID
    role: str
    author_type: str
    author_user_id: UUID | None = None
    author_user_name: str | None = None
    content: str
    created_at: datetime
    is_read: bool
    has_images: bool
    image_count: int = 0
    chatwoot_message_id: int | None = None
    delivery_failed: bool = False
    attachments: list[MessageAttachmentResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConversationHistoryResponse(BaseModel):
    """Conversation history state response (used for pause/resume results)."""

    id: UUID
    conversation_id: str
    bot_paused_at: datetime | None = None
    bot_resumed_at: datetime | None = None
    bot_paused_by_user_id: UUID | None = None
    bot_pause_reason: str | None = None
    last_inbound_at: datetime | None = None
    last_message_at: datetime | None = None

    model_config = {"from_attributes": True}


class EscalationResponse(BaseModel):
    """Escalation creation response."""

    id: UUID
    escalation_id: UUID
    conversation_id: str
    reason: str
    status: str
    source: str
    triggered_at: datetime
    priority: str | None = None

    model_config = {"from_attributes": True}


class WindowStatusResponse(BaseModel):
    """24h window status response."""

    within_24h: bool
    last_inbound_at: datetime | None = None
    expires_at: datetime | None = None
    seconds_remaining: int | None = None


class TemplateComponentResponse(BaseModel):
    """Single template component."""

    type: str
    text: str | None = None
    parameters: list[dict[str, Any]] | None = None


class TemplateResponse(BaseModel):
    """WhatsApp template response."""

    name: str
    language: str
    status: str
    category: str
    components: list[TemplateComponentResponse] = Field(default_factory=list)


class MarkReadResponse(BaseModel):
    """Response for mark-read endpoint."""

    marked_count: int


class InboxStatsResponse(BaseModel):
    """Aggregated escalation stats for the current day."""

    pending: int
    in_progress: int
    resolved_today: int
    total_today: int


class InboxItemResponse(BaseModel):
    """Single inbox item (conversation summary row)."""

    conversation_history_id: UUID
    user_name: str | None = None
    user_phone: str | None = None
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    bot_status: str = "active"
    unread_count: int = 0
    escalation_status: str = "none"
    escalation_source: str | None = None
    escalation_id: UUID | None = None
    paused_by_user_name: str | None = None


class InboxListResponse(BaseModel):
    """Paginated inbox listing response."""

    items: list[InboxItemResponse]
    total: int
    page: int
    page_size: int
    stats: InboxStatsResponse


class MessagesPageResponse(BaseModel):
    """Cursor-paginated messages response."""

    messages: list[ConversationMessageResponse]
    next_cursor: UUID | None = None


class UploadAttachmentsResponse(BaseModel):
    """Response for POST /conversations/{id}/attachments (admin upload)."""

    message: ConversationMessageResponse
    attachments: list[MessageAttachmentResponse]


# ---------------------------------------------------------------------------
# Inbox sidebar schemas (inbox-enrichment)
# ---------------------------------------------------------------------------


class ClientSummaryResponse(BaseModel):
    """Summary of the WhatsApp user linked to a conversation."""

    user_id: UUID
    name: str | None = None
    phone: str | None = None
    created_at: datetime | None = None
    cases_count: int = 0
    billed_total_eur: float = 0.0
    last_activity_at: datetime | None = None

    model_config = {"from_attributes": True}


class ActiveCaseResponse(BaseModel):
    """Summary of the user's active homologation case."""

    id: UUID
    case_number_short: str
    status: str
    category_name: str | None = None
    client_type_label: str | None = None
    tier_code: str | None = None
    tier_price_eur: float | None = None
    elements_total: int = 0
    elements_complete: int = 0
    progress_percent: int = 0

    model_config = {"from_attributes": True}


class NoteResponse(BaseModel):
    """A single internal conversation note."""

    id: UUID
    author_name: str | None = None
    content: str
    created_at: datetime
    can_delete: bool

    model_config = {"from_attributes": True}


class SidebarResponse(BaseModel):
    """Combined right-sidebar payload for a conversation."""

    client: ClientSummaryResponse | None = None
    active_case: ActiveCaseResponse | None = None
    notes: list[NoteResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CreateNoteRequest(BaseModel):
    """Request body for POST /conversations/{id}/notes."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Note body text (1–2000 characters)",
    )
