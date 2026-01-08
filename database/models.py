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
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
        comment="Additional conversation data",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="conversations",
    )

    __table_args__ = (
        Index("ix_conversation_history_conversation_started", "conversation_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<ConversationHistory(id={self.id}, conversation_id={self.conversation_id})>"


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

    Categories include: motos, autocaravanas, campers, 4x4, comerciales, etc.
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
        comment="URL-friendly identifier (e.g., 'moto', 'autocaravana')",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name (e.g., 'Motocicletas')",
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
    element_documentation: Mapped[list["ElementDocumentation"]] = relationship(
        "ElementDocumentation",
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
    client_type: Mapped[str] = mapped_column(
        String(20),
        default="all",
        nullable=False,
        comment="Client type: particular, professional, or all",
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

    __table_args__ = (
        UniqueConstraint("category_id", "code", "client_type", name="uq_category_tier_code_client"),
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


class Warning(Base):
    """
    Warning model - Stores reusable warnings for elements.

    Warnings can be assigned to multiple elements.
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
    trigger_conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON conditions that trigger this warning (element_keywords, show_with_elements, etc.)",
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
        return f"<Warning(id={self.id}, code={self.code})>"


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
        return f"<AdditionalService(id={self.id}, code={self.code}, price={self.price})>"


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

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

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


class ElementDocumentation(Base):
    """
    Element Documentation model - Stores documentation specific to elements.

    Unlike BaseDocumentation (which is per category), this stores
    documentation requirements for specific elements identified by keywords.
    When a user mentions certain keywords, the matching documentation is shown.
    """

    __tablename__ = "element_documentation"

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
        comment="NULL means applies to all categories",
    )
    element_keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Keywords that trigger this documentation (e.g., ['escalera', 'escalera mecanica'])",
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
        back_populates="element_documentation",
    )

    def __repr__(self) -> str:
        return f"<ElementDocumentation(id={self.id}, keywords={self.element_keywords[:2]}...)>"


# =============================================================================
# Admin User System - Sistema de Usuarios Administrativos
# =============================================================================


class AdminUser(Base):
    """
    Admin User model - Stores administrative users for the admin panel.

    Supports two roles: 'admin' (full access) and 'user' (limited access).
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
        default="user",
        comment="User role: admin or user",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Display name for UI",
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

    __table_args__ = (
        Index("ix_rag_queries_hash", "query_hash"),
    )

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
        return f"<QueryCitation(id={self.id}, query_id={self.query_id}, rank={self.rank})>"


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
        comment="Escalation source: tool_call, auto_escalation, error",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Status: pending, in_progress, resolved",
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of agent who resolved the escalation",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Additional data: priority, user_phone, context, etc.",
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User",
        lazy="selectin",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_escalations_status_triggered", "status", "triggered_at"),
    )

    def __repr__(self) -> str:
        return f"<Escalation(id={self.id}, conversation_id={self.conversation_id}, status={self.status})>"