"""
MSI Automotive - Database models.

This module defines SQLAlchemy ORM models for the application.
All models use UUIDs as primary keys and include timestamps.
"""

import uuid
from datetime import datetime, UTC
from typing import Any

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class User(Base):
    """
    User model - Stores user information.

    Users are identified by phone number (E.164 format).
    Users can be 'particular' (individual) or 'professional' (business/workshop).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    phone: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="E.164 format phone number",
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nif_cif: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Spanish NIF/CIF tax ID",
    )
    company_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Company name for B2B customers",
    )
    client_type: Mapped[str] = mapped_column(
        String(20),
        default="particular",
        nullable=False,
        comment="Client type: particular or professional",
    )
    # Address fields
    domicilio_calle: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Street address",
    )
    domicilio_localidad: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="City/town",
    )
    domicilio_provincia: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Province",
    )
    domicilio_cp: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Postal code",
    )
    chatwoot_contact_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Chatwoot contact ID for synchronization",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Additional customer data (whatsapp_name, etc.)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    conversations: Mapped[list["ConversationHistory"]] = relationship(
        "ConversationHistory",
        back_populates="user",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, phone={self.phone}, name={self.first_name})>"


class ConversationHistory(Base):
    """
    Conversation history model - Stores conversation metadata.

    Each conversation is identified by a Chatwoot conversation ID.
    """

    __tablename__ = "conversation_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Chatwoot conversation ID",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated conversation summary",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment=(
            "Additional conversation data. "
            # JSONB conventions — keys written by the system:
            #   whatsapp_name: str           — WhatsApp display name at first contact
            #   backfilled_by_migration_b: bool
            #                                — Migration B set bot_paused_at from Chatwoot scan
            #   backfilled_at: str (ISO)     — When Migration B wrote this row
            "See ConversationHistory.metadata_ conventions in database/models.py."
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Bot pause / resume / snapshot fields
    bot_paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when bot was paused; NULL means bot is active",
    )
    bot_resumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent bot resume",
    )
    bot_paused_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="AdminUser who triggered the pause",
    )
    bot_pause_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional reason for pausing",
    )
    state_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Versioned LangGraph ConversationState snapshot (v1 schema)",
    )
    state_snapshot_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Schema version of state_snapshot payload",
    )

    # Activity timestamps
    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent inbound message from client",
    )
    last_human_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent human-agent outbound message",
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent message from any author",
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="conversations",
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ConversationMessage.created_at",
    )
    paused_by_user: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[bot_paused_by_user_id],
        lazy="selectin",
    )
    notes: Mapped[list["ConversationNote"]] = relationship(
        "ConversationNote",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ConversationNote.created_at.desc()",
    )

    __table_args__ = (
        Index(
            "ix_conversation_history_conversation_started",
            "conversation_id",
            "started_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<ConversationHistory(id={self.id}, conversation_id={self.conversation_id})>"


class ConversationMessage(Base):
    """
    ConversationMessage model - Stores individual messages in conversations.

    Each message is linked to a ConversationHistory and stores the role
    (user or assistant), content, and optional metadata like images.
    Messages are automatically deleted when the parent conversation is deleted.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # FK to ConversationHistory
    conversation_history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Message content
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Message role: user, assistant",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message text content",
    )

    # Optional metadata
    chatwoot_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Chatwoot message ID for correlation",
    )

    # Image metadata (for messages with attachments)
    has_images: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    image_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Attribution fields
    author_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="bot",
        comment="Message author type: bot, human_agent, system, user",
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="AdminUser FK; only set when author_type = human_agent",
    )

    # Read tracking
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether an agent has read this message",
    )
    is_legacy: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True for messages created before the attribution migration",
    )

    # Relationships
    conversation: Mapped["ConversationHistory"] = relationship(
        "ConversationHistory",
        back_populates="messages",
    )
    author_user: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[author_user_id],
        lazy="selectin",
    )
    attachments: Mapped[list["MessageAttachment"]] = relationship(
        "MessageAttachment",
        back_populates="message",
        lazy="selectin",
        order_by="MessageAttachment.position",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_conversation_messages_conv_created",
            "conversation_history_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage(id={self.id}, role={self.role}, conversation={self.conversation_history_id})>"


class MessageAttachment(Base):
    """
    MessageAttachment model - Stores image attachments for conversation messages.

    Each row represents one image linked to a ConversationMessage.
    Inbound (user-sent) attachments are downloaded from Chatwoot via an async worker
    and stored locally at uploads/conversation_images/{conv_id}/{uuid}.{ext}.
    Outbound (bot-sent) attachments store only the URL (no local copy needed).
    Admin-uploaded attachments are validated and stored locally.
    """

    __tablename__ = "message_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # FK to the ConversationMessage that owns this attachment
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Attachment kind — only "image" is actively used; column is future-proof
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="image",
        comment="Attachment kind: image (only supported kind for now)",
    )

    # Relative URL path: /conversation-images/{conv_id}/{uuid}.{ext}
    # Proxied same-origin via Next.js rewrite
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Relative URL path served by GET /conversation-images/{conv_id}/{filename}",
    )

    # Original Chatwoot source URL — populated for inbound messages only
    chatwoot_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Original Chatwoot data_url — only set on inbound (user-sent) attachments",
    )

    # MIME type detected during validation
    content_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Detected MIME type (e.g. image/jpeg)",
    )

    # Original filename from Chatwoot or upload
    filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original filename from Chatwoot or admin upload",
    )

    # File size in bytes
    size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="File size in bytes",
    )

    # Image dimensions — populated from validate_image_full on inbound + admin uploads
    # Left null for outbound bot images (URL only, no download)
    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Image width in pixels; null for bot-outbound attachments",
    )
    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Image height in pixels; null for bot-outbound attachments",
    )

    # Order within the message (0-indexed)
    position: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="0-indexed position within the message attachments",
    )

    # Admin user who uploaded this attachment — only set for admin-uploaded rows
    uploaded_by_admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="AdminUser who uploaded; null for inbound and bot-outbound",
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    message: Mapped["ConversationMessage"] = relationship(
        "ConversationMessage",
        back_populates="attachments",
    )
    uploaded_by: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[uploaded_by_admin_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_message_attachments_message_position",
            "message_id",
            "position",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MessageAttachment(id={self.id}, message_id={self.message_id}, "
            f"position={self.position}, kind={self.kind})>"
        )


class DraftQuote(Base):
    """
    DraftQuote model - Stores the most recent price quote for a conversation.

    Used to recover pricing context after agent restart. At most one
    is_active=True row exists per conversation at any time.

    The write happens as a fire-and-forget after every successful
    calcular_tarifa_con_elementos call. DB failures never surface to the LLM.
    """

    __tablename__ = "draft_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK to conversation_history (the agent's conversation)",
    )
    category_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Vehicle category slug (e.g., 'motos-part')",
    )
    elements: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of element codes included in this quote",
    )
    tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_tiers.id", ondelete="SET NULL"),
        nullable=True,
        comment="Resolved tariff tier ID (nullable)",
    )
    precio_final: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Final price without VAT",
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="When this quote was calculated",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this is the current active quote for the conversation",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<DraftQuote(id={self.id}, conversation_id={self.conversation_id}, "
            f"precio={self.precio_final}, is_active={self.is_active})>"
        )


class Policy(Base):
    """
    Policy model - Stores business policies and FAQ content.

    Policies are key-value pairs with categories for organization.
    """

    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique policy identifier (e.g., 'horario', 'proceso_homologacion')",
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Policy content (markdown supported)",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Policy category (e.g., 'general', 'precios', 'proceso')",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Policy(id={self.id}, key={self.key}, category={self.category})>"


class SystemSetting(Base):
    """
    System settings model - Stores application configuration.

    Settings are key-value pairs with type information.
    """

    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Setting key (e.g., 'max_message_length')",
    )
    value: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Setting value",
    )
    value_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="string",
        comment="Value type: string, integer, boolean, json",
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Human-readable description",
    )
    is_mutable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the setting can be changed at runtime",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SystemSetting(id={self.id}, key={self.key}, value={self.value})>"


# =============================================================================
# Tariff System Models - Sistema de Tarifas de Homologaciones
# =============================================================================


class VehicleCategory(Base):
    """
    Vehicle Category model - Stores vehicle categories for homologation.

    Categories are SEPARATED by client type. Each (name, client_type) combination
    is a distinct category with its own elements, tariffs, and documentation.

    Examples:
    - "Motocicletas" (slug: motos-part, client_type: particular)
    - "Motocicletas" (slug: motos-prof, client_type: professional)
    - "Autocaravanas" (slug: aseicars-part, client_type: particular)
    - "Autocaravanas" (slug: aseicars-prof, client_type: professional)
    """

    __tablename__ = "vehicle_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-friendly identifier including type suffix (e.g., 'motos-part', 'motos-prof')",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name (e.g., 'Motocicletas') - same for both client types",
    )
    client_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Client type: particular or professional",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Category description",
    )
    icon: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Lucide icon name (e.g., 'bike', 'caravan')",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    tariff_tiers: Mapped[list["TariffTier"]] = relationship(
        "TariffTier",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    base_documentation: Mapped[list["BaseDocumentation"]] = relationship(
        "BaseDocumentation",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    additional_services: Mapped[list["AdditionalService"]] = relationship(
        "AdditionalService",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    prompt_sections: Mapped[list["TariffPromptSection"]] = relationship(
        "TariffPromptSection",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    warnings: Mapped[list["Warning"]] = relationship(
        "Warning",
        back_populates="category",
        foreign_keys="[Warning.category_id]",
        lazy="selectin",
    )
    elements: Mapped[list["Element"]] = relationship(
        "Element",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<VehicleCategory(id={self.id}, slug={self.slug}, name={self.name})>"


class TariffTier(Base):
    """
    Tariff Tier model - Stores pricing tiers (T1-T6) for homologations.

    Each tier has a specific price and conditions.
    Client type differentiation is now handled at the VehicleCategory level,
    so tiers are unique by (category_id, code) only.
    """

    __tablename__ = "tariff_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tier code (e.g., 'T1', 'T2')",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Tier name (e.g., 'Proyecto Completo')",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed tier description",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Tier price in EUR",
    )
    conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Conditions for this tier (e.g., '1-2 elementos T3 + 3-4 elementos T4')",
    )
    classification_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON rules for AI classification (applies_if_any, priority, etc.)",
    )
    min_elements: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum number of elements for this tier",
    )
    max_elements: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum number of elements for this tier (NULL = unlimited)",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory"] = relationship(
        "VehicleCategory",
        back_populates="tariff_tiers",
    )
    warnings: Mapped[list["Warning"]] = relationship(
        "Warning",
        back_populates="tier",
        foreign_keys="[Warning.tier_id]",
        lazy="selectin",
    )
    element_inclusions: Mapped[list["TierElementInclusion"]] = relationship(
        "TierElementInclusion",
        back_populates="tier",
        foreign_keys="[TierElementInclusion.tier_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_category_tier_code"),
    )

    def __repr__(self) -> str:
        return f"<TariffTier(id={self.id}, code={self.code}, price={self.price})>"


class BaseDocumentation(Base):
    """
    Base Documentation model - Stores base documentation required for all vehicles in a category.

    This includes documents like ficha técnica, permiso de circulación, etc.
    """

    __tablename__ = "base_documentation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Documentation requirement description",
    )
    image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="URL of example image",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory"] = relationship(
        "VehicleCategory",
        back_populates="base_documentation",
    )

    def __repr__(self) -> str:
        return f"<BaseDocumentation(id={self.id}, category_id={self.category_id})>"


class Element(Base):
    """
    Element model - Catalog of homologable elements per category.

    Each element represents something that can be homologated (e.g., ladder, awning, etc.)
    and belongs to exactly one vehicle category.
    """

    __tablename__ = "elements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Unique element code (e.g., 'ESC_MEC', 'TOLDO_LAT')",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Element display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description",
    )
    keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Keywords for matching (e.g., ['escalera', 'escalera mecanica'])",
    )
    aliases: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Alternative names for the element",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Display order in admin panel",
    )

    # Hierarchy fields for variants/sub-elements
    parent_element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Parent element for variants/sub-elements. NULL = base element.",
    )
    variant_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Type of variant: mmr_option, installation_type, suspension_type, etc.",
    )
    variant_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Short code for this variant: SIN_MMR, CON_MMR, FULL_AIR, etc.",
    )
    question_hint: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Question to ask user when selecting variant (for base elements with variants)",
    )
    variant_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Canonical presentation order for this variant (1=A, 2=B, 3=C...). "
            "NULL for base elements. Auto-assigned on creation, used by agent for "
            "positional mapping of user responses."
        ),
    )
    multi_select_keywords: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Keywords that select ALL variants (e.g., 'ambos', 'todos'). Data-driven multi-select.",
    )

    # Inheritance control for child elements
    inherit_parent_data: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true",
        comment="If True, child element inherits parent's warnings and images in agent responses",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory"] = relationship(
        "VehicleCategory",
        back_populates="elements",
    )
    images: Mapped[list["ElementImage"]] = relationship(
        "ElementImage",
        back_populates="element",
        cascade="all, delete-orphan",
    )
    required_fields: Mapped[list["ElementRequiredField"]] = relationship(
        "ElementRequiredField",
        back_populates="element",
        foreign_keys="[ElementRequiredField.element_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Self-referential relationships for hierarchy
    children: Mapped[list["Element"]] = relationship(
        "Element",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_element_id],
    )
    parent: Mapped["Element | None"] = relationship(
        "Element",
        back_populates="children",
        remote_side="Element.id",
        foreign_keys=[parent_element_id],
    )

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_category_element_code"),
    )

    def __repr__(self) -> str:
        return f"<Element(id={self.id}, code={self.code}, name={self.name})>"


class ElementImage(Base):
    """
    ElementImage model - Stores images for elements.

    Each element can have multiple images showing examples or required documentation.
    """

    __tablename__ = "element_images"
    __table_args__ = (
        UniqueConstraint("element_id", "image_url", name="uq_element_images_element_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="URL to image",
    )
    image_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="example",
        comment="Type: example, required_document, warning, step, calculation",
    )
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this image/document is required from client",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="placeholder",
        nullable=False,
        comment="Image status: active, placeholder, unavailable",
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this image URL was validated as accessible",
    )
    user_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable instruction for the user about this document/photo requirement",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    element: Mapped["Element"] = relationship(
        "Element",
        back_populates="images",
    )

    def __repr__(self) -> str:
        return f"<ElementImage(id={self.id}, element_id={self.element_id}, status={self.status})>"


class ElementRequiredField(Base):
    """
    ElementRequiredField model - Defines required data fields for each element.

    Each element can have multiple required fields that the agent must collect
    during case creation. These are element-specific technical data like
    "suspension spring brand", "spring length", etc.

    Supports:
    - Different field types: text, number, boolean, select
    - Validation rules (min, max, pattern)
    - Conditional fields (only show if another field has a specific value)
    - LLM instructions for how to ask the question
    """

    __tablename__ = "element_required_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Field identification
    field_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Unique key within element (e.g., 'marca_muelle', 'longitud')",
    )
    field_label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable label in Spanish (e.g., 'Marca del muelle')",
    )

    # Field type and options
    field_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="text",
        comment="Field type: text, number, boolean, select",
    )
    options: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Options for select type (e.g., ['Opcion 1', 'Opcion 2'])",
    )

    # Validation
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this field is mandatory",
    )
    validation_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validation rules: {min, max, pattern, min_length, max_length}",
    )

    # LLM instructions
    example_value: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Example value to show in prompts (e.g., 'Ohlins')",
    )
    llm_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Instruction for LLM on how to ask this question",
    )

    # Conditional display
    condition_field_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("element_required_fields.id", ondelete="SET NULL"),
        nullable=True,
        comment="Only show this field if condition_field matches condition_value",
    )
    condition_operator: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Operator: equals, not_equals, exists, not_exists",
    )
    condition_value: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Value to compare against for conditional display",
    )

    # Ordering and status
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Order in which to ask this field",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    element: Mapped["Element"] = relationship(
        "Element",
        back_populates="required_fields",
        foreign_keys=[element_id],
    )
    condition_field: Mapped["ElementRequiredField | None"] = relationship(
        "ElementRequiredField",
        remote_side="ElementRequiredField.id",
        foreign_keys=[condition_field_id],
    )

    __table_args__ = (
        UniqueConstraint("element_id", "field_key", name="uq_element_field_key"),
        Index("ix_element_required_fields_element_active", "element_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ElementRequiredField(id={self.id}, element_id={self.element_id}, field_key={self.field_key})>"


class TierElementInclusion(Base):
    """
    TierElementInclusion model - Links tiers to elements or other tiers.

    Allows defining which elements are included in each tier, with optional
    quantity constraints. Can also reference another tier to inherit its elements.
    """

    __tablename__ = "tier_element_inclusions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Direct element inclusion",
    )
    included_tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Include all elements from another tier",
    )
    min_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum quantity (NULL = no minimum)",
    )
    max_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum quantity (NULL = unlimited)",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes about this inclusion",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    tier: Mapped["TariffTier"] = relationship(
        "TariffTier",
        foreign_keys=[tier_id],
        back_populates="element_inclusions",
    )
    element: Mapped["Element | None"] = relationship(
        "Element",
        foreign_keys=[element_id],
    )
    included_tier: Mapped["TariffTier | None"] = relationship(
        "TariffTier",
        foreign_keys=[included_tier_id],
    )

    def __repr__(self) -> str:
        return f"<TierElementInclusion(id={self.id}, tier_id={self.tier_id})>"


class ElementWarningAssociation(Base):
    """
    ElementWarningAssociation model - Links warnings to specific elements.

    Allows showing warnings when specific elements are matched, with configurable
    conditions like quantity thresholds.
    """

    __tablename__ = "element_warning_associations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warnings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    show_condition: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="always",
        comment="When to show: always, on_exceed_max, on_below_min",
    )
    threshold_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Quantity threshold for condition",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    element: Mapped["Element"] = relationship("Element")
    warning: Mapped["Warning"] = relationship("Warning")

    def __repr__(self) -> str:
        return f"<ElementWarningAssociation(id={self.id}, element_id={self.element_id}, warning_id={self.warning_id})>"


class Warning(Base):
    """
    Warning model - Stores reusable warnings for elements, tiers, or categories.

    Warnings can be:
    - Global (all scope fields NULL): Apply everywhere based on trigger_conditions
    - Category-specific: Only show for a specific category
    - Tier-specific: Only show when a specific tariff tier is selected
    - Element-specific: Expressed exclusively via ElementWarningAssociation (M2M)

    Only ONE scope field can be set at a time (enforced by DB constraint).
    """

    __tablename__ = "warnings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Warning code (e.g., 'antiniebla_sin_marcado')",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Warning message to display",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="warning",
        nullable=False,
        comment="Severity level: info, warning, error",
    )

    # SCOPE FIELDS (optional - NULL = global warning)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="If set, warning only applies to this category",
    )
    tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_tiers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="If set, warning only shows when this tier is selected",
    )

    trigger_conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON conditions that trigger this warning (element_keywords, always_show, etc.)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory | None"] = relationship(
        "VehicleCategory",
        back_populates="warnings",
        foreign_keys=[category_id],
    )
    tier: Mapped["TariffTier | None"] = relationship(
        "TariffTier",
        back_populates="warnings",
        foreign_keys=[tier_id],
    )

    def __repr__(self) -> str:
        scope = "global"
        if self.category_id:
            scope = f"category:{self.category_id}"
        elif self.tier_id:
            scope = f"tier:{self.tier_id}"
        return f"<Warning(code={self.code}, scope={scope})>"


class AdditionalService(Base):
    """
    Additional Service model - Stores extra services like expediente urgente, certificado taller.

    Services can be global (category_id=NULL) or specific to a category.
    """

    __tablename__ = "additional_services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL means global service for all categories",
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Service code (e.g., 'certificado_taller', 'expediente_urgente')",
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Service description",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Service price in EUR",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory | None"] = relationship(
        "VehicleCategory",
        back_populates="additional_services",
    )

    def __repr__(self) -> str:
        return (
            f"<AdditionalService(id={self.id}, code={self.code}, price={self.price})>"
        )


class AuditLog(Base):
    """
    Audit Log model - Stores change history for auditing.

    Tracks all changes to tariff-related entities.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Entity type (e.g., 'tariff_tier', 'element')",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="ID of the modified entity",
    )
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Action: create, update, delete",
    )
    changes: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON object with old/new values",
    )
    user: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Username who made the change",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, entity_type={self.entity_type}, action={self.action})>"


class TariffPromptSection(Base):
    """
    Tariff Prompt Section model - Stores editable prompt sections for AI.

    The prompt system is hybrid: base prompt in code + editable sections in DB.
    Section types: algorithm, recognition_table, special_cases, footer, etc.
    """

    __tablename__ = "tariff_prompt_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Section type: algorithm, recognition_table, special_cases, footer",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Section content (markdown supported)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Version number for tracking changes",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category: Mapped["VehicleCategory"] = relationship(
        "VehicleCategory",
        back_populates="prompt_sections",
    )

    __table_args__ = (
        UniqueConstraint("category_id", "section_type", name="uq_category_section"),
    )

    def __repr__(self) -> str:
        return f"<TariffPromptSection(id={self.id}, category_id={self.category_id}, type={self.section_type})>"


# =============================================================================
# Admin User System - Sistema de Usuarios Administrativos
# =============================================================================


class AdminUser(Base):
    """
    Admin User model - Stores administrative users for the admin panel.

    Supports two roles: 'admin' (full access) and 'agent' (limited access).
    Uses soft delete via is_active flag.
    """

    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique username for login",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt password hash",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="agent",
        comment="User role: admin or agent",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Display name for UI",
    )
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Email address (required for Chatwoot agent sync)",
    )
    chatwoot_agent_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Chatwoot agent ID (system-managed, read-only)",
    )
    chatwoot_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Chatwoot Platform API user ID (system-managed)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Soft delete flag",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin user who created this user",
    )

    # Relationships
    access_logs: Mapped[list["AdminAccessLog"]] = relationship(
        "AdminAccessLog",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AdminUser(id={self.id}, username={self.username}, role={self.role})>"


class AdminAccessLog(Base):
    """
    Admin Access Log model - Tracks login/logout activity for admin users.

    Stores IP address, user agent, and action (login, logout, login_failed).
    """

    __tablename__ = "admin_access_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Action: login, logout, login_failed",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv4 or IPv6)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Client user agent string",
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional details (error messages, etc.)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["AdminUser"] = relationship(
        "AdminUser",
        back_populates="access_logs",
    )

    def __repr__(self) -> str:
        return f"<AdminAccessLog(id={self.id}, user_id={self.user_id}, action={self.action})>"


# =============================================================================
# Image Storage
# =============================================================================


class UploadedImage(Base):
    """
    Uploaded Image model - Stores metadata for uploaded images.

    Images are stored locally in a configured directory.
    This model tracks metadata for management and retrieval.
    """

    __tablename__ = "uploaded_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="UUID-based stored filename",
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME type (image/jpeg, image/png, etc.)",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Image width in pixels",
    )
    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Image height in pixels",
    )
    category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Image category (documentation, example, etc.)",
    )
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Image description for admin",
    )
    uploaded_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Username who uploaded",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UploadedImage(id={self.id}, filename={self.filename})>"


# =============================================================================
# RAG System Models - Sistema de Consulta de Normativas
# =============================================================================


class RegulatoryDocument(Base):
    """
    Regulatory Document model - Stores uploaded regulatory PDFs.

    Tracks document metadata, processing status, and versions.
    Used for RAG (Retrieval-Augmented Generation) queries.
    """

    __tablename__ = "regulatory_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Document metadata
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Document title",
    )
    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Type: reglamento, directiva, orden, resolucion, etc.",
    )
    document_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Official document number (e.g., 'RD 2822/1998')",
    )

    # File storage
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="UUID-based stored filename",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )
    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="SHA256 hash for deduplication",
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, processing, indexed, failed, inactive",
    )
    processing_progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Progress percentage (0-100)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if processing failed",
    )

    # Processing results
    total_pages: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total pages in document",
    )
    total_chunks: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total chunks created",
    )
    extraction_method: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Method used: docling, pymupdf",
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Document description",
    )
    tags: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Tags for categorization",
    )
    section_mappings: Mapped[dict[str, str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="AI-extracted section number to description mappings (e.g., {'6.2': 'Luces de cruce'})",
    )
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Official publication date",
    )

    # Version control
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Document version",
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Previous version of this document",
    )

    # Activation control
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Only active documents are used in RAG queries",
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Audit
    uploaded_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Username who uploaded",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When indexing completed",
    )

    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_regulatory_documents_status_active", "status", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<RegulatoryDocument(id={self.id}, title={self.title[:50]}, status={self.status})>"


class DocumentChunk(Base):
    """
    Document Chunk model - Stores semantic chunks from documents.

    Each chunk is a self-contained piece of regulatory text with metadata.
    Embeddings are stored in Qdrant, metadata here for traceability.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign keys
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Chunk identification
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sequential index within document (0-based)",
    )
    qdrant_point_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="UUID used as point ID in Qdrant",
    )

    # Content
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Chunk text content",
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 hash of content",
    )

    # Position metadata
    page_numbers: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Page numbers this chunk spans (e.g., [5, 6])",
    )
    section_title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Section title extracted from document",
    )
    article_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Article/section number (e.g., 'Art. 23.1')",
    )
    heading_hierarchy: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Breadcrumb of headings (e.g., ['Titulo II', 'Capitulo 3', 'Art. 23'])",
    )

    # Chunk statistics
    char_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Character count",
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Approximate token count",
    )

    # Metadata
    chunk_type: Mapped[str] = mapped_column(
        String(50),
        default="content",
        nullable=False,
        comment="Type: content, table, list, definition",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional metadata from Docling",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    document: Mapped["RegulatoryDocument"] = relationship(
        "RegulatoryDocument",
        back_populates="chunks",
    )

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index("ix_document_chunks_article", "article_number"),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"


class RAGQuery(Base):
    """
    RAG Query model - Stores user queries for analytics and caching.

    Tracks query patterns, performance metrics, and enables result caching.
    """

    __tablename__ = "rag_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Query details
    query_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="User query text",
    )
    query_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA256 hash for deduplication",
    )

    # User context (references admin_users for panel queries)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Chatwoot conversation ID",
    )

    # Performance metrics
    retrieval_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Vector search time in milliseconds",
    )
    rerank_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Re-ranking time in milliseconds",
    )
    llm_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="LLM generation time in milliseconds",
    )
    total_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total query time in milliseconds",
    )

    # Retrieval details
    num_results_retrieved: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of results from vector search",
    )
    num_results_reranked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of results after re-ranking",
    )
    num_results_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of results sent to LLM",
    )
    reranker_used: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Reranker: bge, cohere, none",
    )

    # Response metadata
    response_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Whether LLM response was generated",
    )
    llm_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="LLM model used",
    )

    # Cache control
    cache_hit: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether result was from cache",
    )
    cache_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Redis cache key",
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Relationships
    citations: Mapped[list["QueryCitation"]] = relationship(
        "QueryCitation",
        back_populates="query",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_rag_queries_hash", "query_hash"),)

    def __repr__(self) -> str:
        return f"<RAGQuery(id={self.id}, query_text={self.query_text[:50]})>"


class QueryCitation(Base):
    """
    Query Citation model - Links queries to document chunks used in responses.

    Tracks which chunks were cited in each response for traceability.
    """

    __tablename__ = "query_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign keys
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rag_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ranking details
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Rank in results (1-based)",
    )
    similarity_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Vector similarity score (0-1)",
    )
    rerank_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Re-ranker score (0-1)",
    )
    used_in_context: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether chunk was sent to LLM",
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    query: Mapped["RAGQuery"] = relationship(
        "RAGQuery",
        back_populates="citations",
    )
    document: Mapped["RegulatoryDocument"] = relationship(
        "RegulatoryDocument",
    )
    chunk: Mapped["DocumentChunk"] = relationship(
        "DocumentChunk",
    )

    def __repr__(self) -> str:
        return (
            f"<QueryCitation(id={self.id}, query_id={self.query_id}, rank={self.rank})>"
        )


class Escalation(Base):
    """
    Escalation model - Tracks escalation events to human agents.

    When the bot escalates a conversation (user request or auto-escalation),
    a record is created here for tracking and analytics.
    """

    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Chatwoot conversation ID",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for escalation provided by agent or system",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="tool_call",
        comment="Source: tool_call | auto | panic | fallback | case_completion",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Status: pending | assigned | resolved",
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="AdminUser FK for the agent the escalation is assigned to",
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the escalation was assigned",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Legacy: name of agent who resolved the escalation (string)",
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="AdminUser FK for the agent who resolved the escalation",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment=(
            "Additional escalation data. "
            # JSONB conventions — keys written by the system:
            #   priority: str                    — urgency level (low/medium/high)
            #   user_phone: str                  — customer phone at escalation time
            #   context: str                     — additional context snippet
            #   auto_resolved_via_case: bool     — Rule 7: resolved when Case was resolved
            #   bot_pause_reason: str            — reason passed to ConversationHistory
            "See Escalation.metadata_ conventions in database/models.py."
        ),
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        lazy="selectin",
    )
    assigned_to_user: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[assigned_to_user_id],
        lazy="selectin",
    )
    resolved_by_user: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[resolved_by_user_id],
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_escalations_status_triggered", "status", "triggered_at"),
        Index("ix_escalations_status_assigned", "status", "assigned_to_user_id"),
    )

    def __repr__(self) -> str:
        return f"<Escalation(id={self.id}, conversation_id={self.conversation_id}, status={self.status})>"


class Case(Base):
    """
    Case model - Expediente de homologación.

    Tracks the complete data collection process for vehicle homologation.
    Each case collects personal data, vehicle info, elements to homologate,
    and required images before being sent for human review.
    """

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Chatwoot conversation ID",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="collecting",
        index=True,
        comment="Status: collecting, pending_images, pending_review, in_progress, resolved, cancelled, abandoned",
    )

    # Datos del vehículo
    vehiculo_marca: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vehiculo_modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vehiculo_anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehiculo_matricula: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="License plate (optional for new vehicles)",
    )
    vehiculo_bastidor: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="VIN / Chassis number",
    )

    # Categoría y elementos
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicle_categories.id", ondelete="SET NULL"),
        nullable=True,
        comment="Vehicle category (motos, autocaravanas, etc.)",
    )
    element_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Element codes to homologate",
    )

    # Tarifa calculada
    tariff_tier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tariff_tiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    tariff_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Calculated price",
    )

    # Datos de la ITV
    itv_nombre: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Name of the ITV station",
    )

    # Datos del taller
    taller_propio: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
        comment="True if client uses their own workshop, False if MSI provides certificate, None if not yet specified",
    )
    taller_nombre: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Workshop name (only if taller_propio=True)",
    )
    taller_responsable: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Workshop responsible person",
    )
    taller_domicilio: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Workshop street address",
    )
    taller_provincia: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Workshop province",
    )
    taller_ciudad: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Workshop city",
    )
    taller_telefono: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Workshop phone",
    )
    taller_registro_industrial: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Workshop industrial registration number",
    )
    taller_actividad: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Workshop activity description",
    )

    # Cambios dimensionales (condicional según reforma)
    cambio_plazas: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if there is a change in number of seats",
    )
    plazas_iniciales: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Initial number of seats",
    )
    plazas_finales: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Final number of seats",
    )
    cambio_altura: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if there is a height change",
    )
    altura_final: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Final height in mm",
    )
    cambio_ancho: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if there is a width change",
    )
    ancho_final: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Final width in mm",
    )
    cambio_longitud: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if there is a length change",
    )
    longitud_final: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Final length in mm",
    )

    # Escalación automática al completar
    escalation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("escalations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Escalation created when case is complete",
    )

    # Metadata y notas
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes from human agent",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Additional metadata",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When all data + images were collected",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of agent who resolved the case",
    )

    # Lifecycle tracking
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time the user sent a message while in expediente flow",
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the lifecycle worker sent the inactivity reminder",
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the worker marked the case as abandoned",
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        lazy="selectin",
    )
    category: Mapped["VehicleCategory | None"] = relationship(
        "VehicleCategory",
        lazy="selectin",
    )
    tariff_tier: Mapped["TariffTier | None"] = relationship(
        "TariffTier",
        lazy="selectin",
    )
    escalation: Mapped["Escalation | None"] = relationship(
        "Escalation",
        lazy="selectin",
    )
    images: Mapped[list["CaseImage"]] = relationship(
        "CaseImage",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    element_data: Mapped[list["CaseElementData"]] = relationship(
        "CaseElementData",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_cases_status_created", "status", "created_at"),
        Index("ix_cases_user_status", "user_id", "status"),
        Index("ix_cases_lifecycle", "status", "last_activity_at"),
    )

    def __repr__(self) -> str:
        return f"<Case(id={self.id}, status={self.status}, user_id={self.user_id})>"


class CaseImageUploadBatch(Base):
    """Persisted expediente photo upload batch/session ownership."""

    __tablename__ = "case_image_upload_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    batch_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        comment="Public batch/session identifier used by the agent runtime",
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_scope_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Deterministic expediente ownership scope for this batch",
    )
    owner_scope: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Ownership scope: element_photo or base_documentation",
    )
    owner_element_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Element code when the batch belongs to one expediente element",
    )
    expediente_sub_mode: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Expediente sub-mode that opened the batch",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="open",
        comment="Lifecycle status: open, confirmed, reconciled, superseded",
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this batch stopped accepting new uploads",
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time reconciliation completed for this batch",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Additional runtime metadata for ownership/reconciliation",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    case: Mapped["Case"] = relationship(
        "Case",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_case_image_upload_batches_case_scope", "case_id", "upload_scope_key"),
        Index("ix_case_image_upload_batches_case_status", "case_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<CaseImageUploadBatch(batch_id={self.batch_id}, case_id={self.case_id}, "
            f"scope={self.upload_scope_key})>"
        )


class CaseImage(Base):
    """
    CaseImage model - Images uploaded by users for cases.

    Each image has a descriptive name indicating what it shows,
    linked to the case and optionally to a specific element.
    """

    __tablename__ = "case_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File storage
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="UUID-based stored filename",
    )
    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original filename from Chatwoot",
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="image/jpeg",
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="File size in bytes",
    )

    # Descriptive metadata
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Descriptive name (e.g., 'escape_vista_lateral', 'ficha_tecnica')",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional description",
    )
    element_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Related element code if applicable",
    )
    image_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="documentation",
        comment="Type: base_documentation, element_photo, other",
    )

    # Chatwoot correlation (for reconciliation/dedup)
    chatwoot_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Chatwoot message ID for deduplication during image reconciliation",
    )
    attachment_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Attachment-level fingerprint for replay/reconciliation deduplication",
    )
    upload_scope_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Logical upload scope identity for this expediente image batch",
    )
    upload_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("case_image_upload_batches.batch_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Persisted upload batch/session identifier for scoped confirmations",
    )

    # Validation by human agent
    is_valid: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="NULL=not reviewed, True=valid, False=needs replacement",
    )
    validation_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Notes from human agent about the image",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="images",
    )

    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "attachment_fingerprint",
            name="uq_case_images_case_attachment_fingerprint",
        ),
        Index("ix_case_images_case_batch", "case_id", "upload_batch_id"),
    )

    def __repr__(self) -> str:
        return f"<CaseImage(id={self.id}, case_id={self.case_id}, display_name={self.display_name})>"


class CaseElementData(Base):
    """
    CaseElementData model - Stores collected data for each element in a case.

    Tracks the photos and required field values collected for each element
    during the case creation process. This enables:
    - Element-by-element data collection flow
    - Per-element status tracking (photos received, data collected)
    - Structured storage of element-specific technical data
    """

    __tablename__ = "case_element_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Element code (e.g., 'SUSP_TRAS', 'ESCAPE')",
    )

    # Collection status
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_photos",
        comment="Status: pending_photos, pending_data, completed",
    )

    # Collected field values
    field_values: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Collected field values: {field_key: value}",
    )

    # Timestamps for each phase
    photos_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When photos for this element were marked complete",
    )
    data_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When all required data for this element was collected",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="element_data",
    )

    __table_args__ = (
        UniqueConstraint("case_id", "element_code", name="uq_case_element_code"),
        Index("ix_case_element_data_case_status", "case_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<CaseElementData(id={self.id}, case_id={self.case_id}, element_code={self.element_code}, status={self.status})>"


# =============================================================================
# Token Usage Tracking
# =============================================================================


class TokenUsage(Base):
    """
    Token Usage model - Monthly aggregated LLM token consumption.

    Stores aggregated token usage per month for cost tracking and billing.
    Updated atomically using UPSERT pattern to ensure data consistency.
    """

    __tablename__ = "token_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Year (e.g., 2025)",
    )
    month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Month (1-12)",
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total input/prompt tokens consumed",
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        comment="Total output/completion tokens consumed",
    )
    total_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of LLM requests made",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_token_usage_year_month"),
        Index("ix_token_usage_year_month", "year", "month"),
    )

    def __repr__(self) -> str:
        total = self.input_tokens + self.output_tokens
        return f"<TokenUsage(year={self.year}, month={self.month}, total={total})>"



# =============================================================================
# Billing System (Invoices + Payments)
# =============================================================================


class Invoice(Base):
    """
    Invoice model - Monthly billing invoices for MSI Automotive service.

    Tracks monthly charges composed of a flat maintenance fee plus
    variable token-usage costs. Integrates with Stripe for payment
    processing and stores a snapshot of token counts at issuance time
    for audit purposes.
    """

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        comment="Human-readable invoice number (e.g. MSI-2025-001)",
    )
    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Billing year (e.g. 2025)",
    )
    month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Billing month (1-12)",
    )
    maintenance_amount_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Flat monthly maintenance fee in EUR",
    )
    token_amount_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Variable token-usage charge in EUR",
    )
    subtotal_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Subtotal before IVA (maintenance + token)",
    )
    iva_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("21.00"),
        comment="IVA percentage applied (default 21%)",
    )
    iva_amount_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="IVA amount in EUR",
    )
    total_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Total amount due including IVA",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="issued",
        comment="Invoice status: issued, paid, void, overdue",
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Stripe invoice object ID (in_...)",
    )
    stripe_hosted_invoice_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Stripe-hosted invoice URL for customer viewing",
    )
    stripe_pdf_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Stripe-generated PDF download URL",
    )
    pdf_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Local filesystem path to generated PDF",
    )
    due_date: Mapped[Any | None] = mapped_column(
        Date,
        nullable=True,
        comment="Payment due date",
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when invoice was issued",
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when invoice was paid",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes or adjustment explanations",
    )
    token_usage_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of token counts at invoice issuance for audit",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_invoices_year_month", "year", "month"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_stripe_invoice_id", "stripe_invoice_id"),
    )

    def __repr__(self) -> str:
        return f"<Invoice(number={self.invoice_number!r}, year={self.year}, month={self.month}, status={self.status!r})>"


class Payment(Base):
    """
    Payment model - Individual payment attempts for an Invoice.

    Tracks Stripe payment intents and charges. An invoice may have
    multiple payment records if initial attempts fail and are retried.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent invoice",
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Stripe PaymentIntent ID (pi_...)",
    )
    stripe_charge_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Stripe Charge ID (ch_...)",
    )
    amount_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Amount charged in EUR",
    )
    fee_eur: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Stripe processing fee in EUR (populated after charge)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Payment status: pending, succeeded, failed, refunded",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Stripe failure message when status is 'failed'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        back_populates="payments",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_payments_invoice_id", "invoice_id"),
        Index("ix_payments_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, invoice_id={self.invoice_id}, amount={self.amount_eur}, status={self.status!r})>"


class ConversationNote(Base):
    """
    ConversationNote model — Internal admin notes linked to a conversation.

    Notes are admin-only handoff context, never sent to WhatsApp customers.
    Designed for cross-agent coordination during escalations.

    Authorship semantics:
    - admin_user_id is SET NULL when the author is deleted — the note content
      is preserved so handoff context is not lost.
    - Author display falls back to "Eliminado" when admin_user_id is NULL.
    - Hard delete only (no soft delete) — audit trail via structlog.
    """

    __tablename__ = "conversation_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID v4 primary key",
    )
    conversation_history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK to conversation_history — CASCADE on delete",
    )
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK to admin_users — SET NULL when author deleted; content preserved",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Note body text (1–2000 chars, enforced at service layer)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Row creation timestamp",
    )

    # Relationships
    conversation: Mapped["ConversationHistory"] = relationship(
        "ConversationHistory",
        back_populates="notes",
    )
    author: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        foreign_keys=[admin_user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "idx_conversation_notes_conv_id_created_desc",
            "conversation_history_id",
            text("created_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ConversationNote(id={self.id}, conversation_history_id={self.conversation_history_id})>"


