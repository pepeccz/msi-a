"""
Element system Pydantic models.

Schemas for validating and serializing Element, ElementImage, TierElementInclusion,
and ElementWarningAssociation data in API requests/responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ElementImage Models
# =============================================================================


class ElementImageBase(BaseModel):
    """Base fields for ElementImage."""

    image_url: str = Field(..., min_length=1, max_length=500)
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    image_type: str = Field(..., description="Type: 'example', 'required_document', 'warning', 'step', or 'calculation'")
    sort_order: int = Field(default=0, ge=0)
    is_required: bool = Field(default=False)
    status: str = Field(default="placeholder", description="Image status: 'active', 'placeholder', 'unavailable'")
    user_instruction: str | None = Field(None, description="Human-readable instruction for the user about this photo/document")

    @field_validator("image_type")
    @classmethod
    def validate_image_type(cls, v):
        """Validate image_type is one of allowed values."""
        allowed = {"example", "required_document", "warning", "step", "calculation"}
        if v not in allowed:
            raise ValueError(f"image_type must be one of {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        """Validate status is one of allowed values."""
        allowed = {"active", "placeholder", "unavailable"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class ElementImageCreate(ElementImageBase):
    """Schema for creating an ElementImage."""

    pass


class ElementImageUpdate(BaseModel):
    """Schema for updating an ElementImage."""

    image_url: str | None = Field(None, min_length=1, max_length=500)
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    image_type: str | None = None
    sort_order: int | None = None
    is_required: bool | None = None
    status: str | None = None
    user_instruction: str | None = None

    @field_validator("image_type")
    @classmethod
    def validate_image_type(cls, v):
        """Validate image_type if provided."""
        if v is None:
            return v
        allowed = {"example", "required_document", "warning", "step", "calculation"}
        if v not in allowed:
            raise ValueError(f"image_type must be one of {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        """Validate status if provided."""
        if v is None:
            return v
        allowed = {"active", "placeholder", "unavailable"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class ElementImageResponse(ElementImageBase):
    """Schema for ElementImage response."""

    id: UUID
    element_id: UUID
    validated_at: datetime | None = None

    class Config:
        from_attributes = True


# =============================================================================
# Element Models
# =============================================================================


class ElementBase(BaseModel):
    """Base fields for Element."""

    code: str = Field(..., min_length=1, max_length=50, description="Unique element code")
    name: str = Field(..., min_length=1, max_length=200, description="Display name")
    description: str | None = None
    keywords: list[str] = Field(..., description="Keywords for matching")
    aliases: list[str] | None = Field(None, description="Alternative names")
    is_active: bool = Field(default=True)
    sort_order: int = Field(default=0, ge=0)
    # Hierarchy fields
    parent_element_id: UUID | None = Field(
        None, description="Parent element ID for variants/sub-elements"
    )
    variant_type: str | None = Field(
        None,
        max_length=50,
        description="Type of variant: mmr_option, installation_type, suspension_type, etc.",
    )
    variant_code: str | None = Field(
        None,
        max_length=50,
        description="Short code for variant: SIN_MMR, CON_MMR, FULL_AIR, etc.",
    )
    question_hint: str | None = Field(
        None,
        max_length=500,
        description="Question to ask user to determine which variant they need (only for base elements with variants)",
    )
    multi_select_keywords: list[str] | None = Field(
        None,
        description="Keywords that select ALL variants at once (e.g., 'ambos', 'todos'). Data-driven multi-select.",
    )
    inherit_parent_data: bool = Field(
        default=True,
        description="If True, child element inherits parent's warnings and images in agent responses",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v):
        """Ensure keywords is not empty."""
        if not v:
            raise ValueError("At least one keyword is required")
        return v


class ElementCreate(ElementBase):
    """Schema for creating an Element."""

    category_id: UUID


class ElementUpdate(BaseModel):
    """Schema for updating an Element."""

    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    keywords: list[str] | None = None
    aliases: list[str] | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    # Hierarchy fields
    parent_element_id: UUID | None = None
    variant_type: str | None = Field(None, max_length=50)
    variant_code: str | None = Field(None, max_length=50)
    question_hint: str | None = Field(None, max_length=500)
    multi_select_keywords: list[str] | None = None
    inherit_parent_data: bool | None = None

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v):
        """Ensure keywords is not empty if provided."""
        if v is not None and not v:
            raise ValueError("At least one keyword is required")
        return v


class ElementResponse(ElementBase):
    """Schema for Element response (without images)."""

    id: UUID
    category_id: UUID
    created_at: datetime
    updated_at: datetime

    # Contadores de relaciones (agregados en queries)
    image_count: int = Field(default=0, description="Number of images for this element")
    warning_count: int = Field(default=0, description="Number of warnings associated")
    child_count: int = Field(default=0, description="Number of child elements")

    class Config:
        from_attributes = True


class ElementWithImagesResponse(ElementResponse):
    """Schema for Element response with images."""

    images: list[ElementImageResponse] = Field(default_factory=list)


class ElementWithChildrenResponse(ElementResponse):
    """Schema for Element response with children (for hierarchical queries)."""

    children: list["ElementResponse"] = Field(default_factory=list)


class ElementWithImagesAndChildrenResponse(ElementWithImagesResponse):
    """Schema for Element response with images and children."""

    children: list["ElementWithImagesResponse"] = Field(default_factory=list)


# =============================================================================
# TierElementInclusion Models
# =============================================================================


class TierElementInclusionBase(BaseModel):
    """Base fields for TierElementInclusion."""

    element_id: UUID | None = None
    included_tier_id: UUID | None = None
    min_quantity: int | None = Field(None, ge=0)
    max_quantity: int | None = Field(None, ge=0)
    notes: str | None = None

    @field_validator("max_quantity")
    @classmethod
    def validate_quantities(cls, v, info):
        """Ensure min_quantity <= max_quantity."""
        min_qty = info.data.get("min_quantity")
        if min_qty is not None and v is not None and v < min_qty:
            raise ValueError("max_quantity must be >= min_quantity")
        return v


class TierElementInclusionCreate(TierElementInclusionBase):
    """Schema for creating a TierElementInclusion."""

    tier_id: UUID

    @field_validator("element_id", "included_tier_id")
    @classmethod
    def validate_xor(cls, v, info):
        """Ensure either element_id OR included_tier_id is set, not both."""
        # This will be checked at the root level with mode='after'
        return v

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override to add XOR validation."""
        instance = super().model_validate(obj, **kwargs)
        if instance.element_id and instance.included_tier_id:
            raise ValueError("Cannot set both element_id and included_tier_id")
        if not instance.element_id and not instance.included_tier_id:
            raise ValueError("Must set either element_id or included_tier_id")
        return instance


class TierElementInclusionUpdate(BaseModel):
    """Schema for updating a TierElementInclusion."""

    element_id: UUID | None = None
    included_tier_id: UUID | None = None
    min_quantity: int | None = Field(None, ge=0)
    max_quantity: int | None = Field(None, ge=0)
    notes: str | None = None


class TierElementInclusionResponse(TierElementInclusionBase):
    """Schema for TierElementInclusion response."""

    id: UUID
    tier_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# ElementWarningAssociation Models
# =============================================================================


class ElementWarningAssociationCreate(BaseModel):
    """Schema for creating an ElementWarningAssociation."""

    element_id: UUID
    warning_id: UUID
    show_condition: str = Field(..., description="When to show: 'always' or 'if_selected'")
    threshold_quantity: int | None = Field(None, ge=1, description="Show if quantity >= this value")

    @field_validator("show_condition")
    @classmethod
    def validate_show_condition(cls, v):
        """Validate show_condition."""
        allowed = {"always", "if_selected"}
        if v not in allowed:
            raise ValueError(f"show_condition must be one of {allowed}")
        return v


class ElementWarningAssociationResponse(ElementWarningAssociationCreate):
    """Schema for ElementWarningAssociation response."""

    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Batch Operations
# =============================================================================


class BatchTierInclusionCreate(BaseModel):
    """Schema for batch creating tier inclusions."""

    tier_id: UUID
    inclusions: list[TierElementInclusionCreate] = Field(..., min_items=1, max_items=100)


class TierElementsPreview(BaseModel):
    """Schema for previewing resolved tier elements."""

    tier_id: UUID
    tier_code: str
    tier_name: str
    total_elements: int
    elements: dict[str, int | None] = Field(..., description="element_id -> max_quantity")


# =============================================================================
# Error Responses
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
    code: str | None = None
