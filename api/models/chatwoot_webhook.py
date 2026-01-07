"""
MSI Automotive - Pydantic models for Chatwoot webhook payloads.
"""

import phonenumbers
from pydantic import BaseModel, ConfigDict, field_validator


class ChatwootSender(BaseModel):
    """Chatwoot message sender information."""

    model_config = ConfigDict(extra="allow")

    phone_number: str | None = None
    name: str | None = None


class ChatwootAttachment(BaseModel):
    """Chatwoot message attachment (audio, video, image, file)."""

    model_config = ConfigDict(extra="allow")

    id: int
    file_type: str  # "audio", "video", "image", "file"
    data_url: str  # URL to download the attachment


class ChatwootMessage(BaseModel):
    """Single message within a Chatwoot conversation."""

    model_config = ConfigDict(extra="allow")

    id: int
    content: str | None = None
    message_type: int  # 0 = incoming, 1 = outgoing
    content_type: str | None = None  # "text", "audio", etc.
    attachments: list[ChatwootAttachment] = []
    sender: ChatwootSender | None = None
    created_at: int  # Unix timestamp
    conversation_id: int


class ChatwootConversation(BaseModel):
    """Chatwoot conversation object."""

    model_config = ConfigDict(extra="allow")

    id: int  # conversation_id
    inbox_id: int
    messages: list[ChatwootMessage]
    custom_attributes: dict[str, bool | str | int | float | None] = {}


class ChatwootWebhookPayload(BaseModel):
    """
    Chatwoot webhook payload.

    Format: {
        "event": "message_created",
        "conversation": {...},
        "sender": {...},
        "attachments": [...],
        ...
    }
    """

    model_config = ConfigDict(extra="allow")

    event: str  # "message_created", etc.
    conversation: ChatwootConversation
    sender: ChatwootSender
    attachments: list[ChatwootAttachment] = []


class ChatwootMessageEvent(BaseModel):
    """Parsed Chatwoot message event for Redis pub/sub."""

    conversation_id: str
    customer_phone: str
    message_text: str
    customer_name: str | None = None
    user_id: str | None = None

    @field_validator("customer_phone")
    @classmethod
    def validate_phone_e164(cls, v: str) -> str:
        """Validate and normalize phone number to E.164 format."""
        try:
            # Parse with default region Spain
            parsed = phonenumbers.parse(v, "ES")
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError(f"Invalid phone number: {v}")
            # Format to E.164 standard
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        except phonenumbers.NumberParseException as e:
            raise ValueError(f"Cannot parse phone number {v}: {e}") from e
