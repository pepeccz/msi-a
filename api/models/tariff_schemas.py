"""
MSI Automotive - Tariff System Pydantic Schemas.

This module defines request/response schemas for the tariff API endpoints.
Updated for the new architecture that uses classification_rules instead of
HomologationElement catalog.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Vehicle Category Schemas
# =============================================================================


class VehicleCategoryBase(BaseModel):
    """Base schema for vehicle category."""

    slug: str = Field(..., min_length=1, max_length=50, description="URL-friendly identifier (includes type suffix: motos-part, motos-prof)")
    name: str = Field(..., min_length=1, max_length=100, description="Display name")
    description: str | None = Field(None, description="Category description")
    icon: str | None = Field(None, max_length=50, description="Lucide icon name")
    client_type: Literal["particular", "professional"] = Field(
        ...,
        description="Client type this category is for"
    )
    is_active: bool = Field(True, description="Whether category is active")
    sort_order: int = Field(0, description="Sort order")


class VehicleCategoryCreate(VehicleCategoryBase):
    """Schema for creating a vehicle category."""

    pass


class VehicleCategoryUpdate(BaseModel):
    """Schema for updating a vehicle category."""

    slug: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    client_type: Literal["particular", "professional"] | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class VehicleCategoryResponse(VehicleCategoryBase):
    """Schema for vehicle category response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class VehicleCategoryWithRelations(VehicleCategoryResponse):
    """Schema for vehicle category with all relations."""

    tariff_tiers: list["TariffTierResponse"] = []
    base_documentation: list["BaseDocumentationResponse"] = []
    element_documentation: list["ElementDocumentationResponse"] = []
    additional_services: list["AdditionalServiceResponse"] = []
    prompt_sections: list["TariffPromptSectionResponse"] = []


# =============================================================================
# Tariff Tier Schemas
# =============================================================================


class ClassificationRules(BaseModel):
    """Schema for classification rules JSON structure."""

    applies_if_any: list[str] = Field(
        default_factory=list,
        description="Keywords that trigger this tier (if any matches)"
    )
    priority: int = Field(
        default=999,
        description="Priority for rule matching (lower = higher priority)"
    )
    requires_project: bool = Field(
        default=False,
        description="Whether this tier requires a technical project"
    )
    notes: str | None = Field(
        None,
        description="Internal notes about this tier"
    )


class TariffTierBase(BaseModel):
    """Base schema for tariff tier.

    Note: client_type differentiation is now at the VehicleCategory level.
    Tiers are unique by (category_id, code) only.
    """

    code: str = Field(..., min_length=1, max_length=20, description="Tier code (T1, T2, etc.)")
    name: str = Field(..., min_length=1, max_length=100, description="Tier name")
    description: str | None = Field(None, description="Tier description")
    price: Decimal = Field(..., ge=0, description="Price in EUR")
    conditions: str | None = Field(None, description="Tier conditions (human readable)")
    classification_rules: dict[str, Any] | None = Field(
        None,
        description="JSON rules for AI classification"
    )
    min_elements: int | None = Field(None, ge=0, description="Minimum elements")
    max_elements: int | None = Field(None, ge=0, description="Maximum elements")
    is_active: bool = Field(True, description="Whether tier is active")
    sort_order: int = Field(0, description="Sort order")


class TariffTierCreate(TariffTierBase):
    """Schema for creating a tariff tier."""

    category_id: UUID = Field(..., description="Vehicle category ID")


class TariffTierUpdate(BaseModel):
    """Schema for updating a tariff tier."""

    code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    conditions: str | None = None
    classification_rules: dict[str, Any] | None = None
    min_elements: int | None = None
    max_elements: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class TariffTierResponse(TariffTierBase):
    """Schema for tariff tier response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Base Documentation Schemas
# =============================================================================


class BaseDocumentationBase(BaseModel):
    """Base schema for base documentation."""

    description: str = Field(..., min_length=1, description="Documentation requirement")
    image_url: str | None = Field(None, max_length=500, description="Example image URL")
    sort_order: int = Field(0, description="Sort order")


class BaseDocumentationCreate(BaseDocumentationBase):
    """Schema for creating base documentation."""

    category_id: UUID = Field(..., description="Vehicle category ID")


class BaseDocumentationUpdate(BaseModel):
    """Schema for updating base documentation."""

    description: str | None = None
    image_url: str | None = None
    sort_order: int | None = None


class BaseDocumentationResponse(BaseDocumentationBase):
    """Schema for base documentation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    created_at: datetime


# =============================================================================
# Warning Schemas
# =============================================================================


class TriggerConditions(BaseModel):
    """Schema for warning trigger conditions JSON structure."""

    element_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords that trigger this warning"
    )
    show_with_elements: list[str] = Field(
        default_factory=list,
        description="Show when these elements are also present"
    )
    always_show: bool = Field(
        default=False,
        description="Always show this warning regardless of elements"
    )


class WarningBase(BaseModel):
    """Base schema for warning."""

    code: str = Field(..., min_length=1, max_length=50, description="Warning code")
    message: str = Field(..., min_length=1, description="Warning message")
    severity: Literal["info", "warning", "error"] = Field(
        "warning",
        description="Severity level"
    )
    trigger_conditions: dict[str, Any] | None = Field(
        None,
        description="JSON conditions that trigger this warning"
    )
    is_active: bool = Field(True, description="Whether warning is active")


class WarningCreate(WarningBase):
    """Schema for creating a warning."""

    pass


class WarningUpdate(BaseModel):
    """Schema for updating a warning."""

    code: str | None = Field(None, min_length=1, max_length=50)
    message: str | None = None
    severity: Literal["info", "warning", "error"] | None = None
    trigger_conditions: dict[str, Any] | None = None
    is_active: bool | None = None


class WarningResponse(WarningBase):
    """Schema for warning response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Additional Service Schemas
# =============================================================================


class AdditionalServiceBase(BaseModel):
    """Base schema for additional service."""

    code: str = Field(..., min_length=1, max_length=50, description="Service code")
    name: str = Field(..., min_length=1, max_length=150, description="Display name")
    description: str | None = Field(None, description="Service description")
    price: Decimal = Field(..., ge=0, description="Price in EUR")
    is_active: bool = Field(True, description="Whether service is active")
    sort_order: int = Field(0, description="Sort order")


class AdditionalServiceCreate(AdditionalServiceBase):
    """Schema for creating an additional service."""

    category_id: UUID | None = Field(None, description="Vehicle category ID (NULL = global)")


class AdditionalServiceUpdate(BaseModel):
    """Schema for updating an additional service."""

    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    category_id: UUID | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class AdditionalServiceResponse(AdditionalServiceBase):
    """Schema for additional service response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID | None
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Element Documentation Schemas
# =============================================================================


class ElementDocumentationBase(BaseModel):
    """Base schema for element documentation (keyword-based)."""

    element_keywords: list[str] = Field(
        ...,
        min_length=1,
        description="Keywords that trigger this documentation"
    )
    description: str = Field(..., min_length=1, description="Documentation requirement")
    image_url: str | None = Field(None, max_length=500, description="Example image URL")
    sort_order: int = Field(0, description="Sort order")
    is_active: bool = Field(True, description="Whether documentation is active")


class ElementDocumentationCreate(ElementDocumentationBase):
    """Schema for creating element documentation."""

    category_id: UUID | None = Field(None, description="Vehicle category ID (NULL = global)")


class ElementDocumentationUpdate(BaseModel):
    """Schema for updating element documentation."""

    element_keywords: list[str] | None = None
    description: str | None = None
    image_url: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ElementDocumentationResponse(ElementDocumentationBase):
    """Schema for element documentation response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID | None
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Uploaded Image Schemas
# =============================================================================


class UploadedImageResponse(BaseModel):
    """Schema for uploaded image response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    stored_filename: str
    mime_type: str
    file_size: int
    width: int | None
    height: int | None
    category: str | None
    description: str | None
    uploaded_by: str | None
    url: str = Field(..., description="Public URL to access the image")
    created_at: datetime


class UploadedImageListResponse(BaseModel):
    """Schema for paginated image list response."""

    items: list[UploadedImageResponse]
    total: int
    has_more: bool


# =============================================================================
# Tariff Prompt Section Schemas
# =============================================================================


class TariffPromptSectionBase(BaseModel):
    """Base schema for tariff prompt section."""

    section_type: Literal["algorithm", "recognition_table", "special_cases", "footer"] = Field(
        ...,
        description="Section type"
    )
    content: str = Field(..., min_length=1, description="Section content (markdown supported)")
    is_active: bool = Field(True, description="Whether section is active")


class TariffPromptSectionCreate(TariffPromptSectionBase):
    """Schema for creating a prompt section."""

    category_id: UUID = Field(..., description="Vehicle category ID")


class TariffPromptSectionUpdate(BaseModel):
    """Schema for updating a prompt section."""

    section_type: Literal["algorithm", "recognition_table", "special_cases", "footer"] | None = None
    content: str | None = None
    is_active: bool | None = None


class TariffPromptSectionResponse(TariffPromptSectionBase):
    """Schema for prompt section response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Customer Schemas (for client_type support)
# =============================================================================


class CustomerBase(BaseModel):
    """Base schema for customer."""

    phone: str = Field(..., min_length=1, max_length=20, description="E.164 phone number")
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    nif_cif: str | None = Field(None, max_length=20, description="Spanish tax ID")
    company_name: str | None = Field(None, max_length=200)
    client_type: Literal["particular", "professional"] = Field(
        "particular",
        description="Client type for tariff selection"
    )


class CustomerCreate(CustomerBase):
    """Schema for creating a customer."""

    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class CustomerUpdate(BaseModel):
    """Schema for updating a customer."""

    phone: str | None = Field(None, min_length=1, max_length=20)
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    nif_cif: str | None = None
    company_name: str | None = None
    client_type: Literal["particular", "professional"] | None = None
    metadata: dict[str, Any] | None = None


class CustomerResponse(CustomerBase):
    """Schema for customer response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Audit Log Schemas
# =============================================================================


class AuditLogResponse(BaseModel):
    """Schema for audit log response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    changes: dict[str, Any] | None
    user: str | None
    created_at: datetime


# =============================================================================
# Public API Schemas (for Agent)
# =============================================================================


class TariffSelectionRequest(BaseModel):
    """Schema for AI-driven tariff selection request."""

    elements_description: str = Field(
        ...,
        min_length=1,
        description="Natural language description of elements to homologate"
    )
    element_count: int = Field(
        ...,
        ge=1,
        description="Number of elements identified"
    )
    client_type: Literal["particular", "professional"] = Field(
        "particular",
        description="Client type"
    )


class TariffSelectionResponse(BaseModel):
    """Schema for tariff selection response."""

    tier_code: str
    tier_name: str
    price: Decimal
    conditions: str | None
    element_count: int
    matched_rules: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    additional_services: list[dict[str, Any]]
    requires_project: bool


class DocumentationResponse(BaseModel):
    """Schema for documentation response."""

    category: str
    base_documentation: list[BaseDocumentationResponse]


class PromptPreviewResponse(BaseModel):
    """Schema for prompt preview response."""

    category: dict[str, Any] | None
    sections: dict[str, str]
    warnings_count: int
    tiers_count: int
    prompt_length: int
    full_prompt: str


class CategoryFullDataResponse(BaseModel):
    """Schema for full category data response (for agent).

    Note: client_type is now part of category, not a separate field.
    """

    category: VehicleCategoryResponse
    tiers: list[TariffTierResponse]
    warnings: list[WarningResponse]
    base_documentation: list[BaseDocumentationResponse]
    additional_services: list[AdditionalServiceResponse]


# =============================================================================
# List Response Schemas
# =============================================================================


class ListResponse(BaseModel):
    """Generic list response with pagination info."""

    items: list[Any]
    total: int
    has_more: bool


# Update forward references
VehicleCategoryWithRelations.model_rebuild()
