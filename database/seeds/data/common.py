"""
MSI-a Seed Data - Common Types and Shared Constants.

This module defines TypedDict types for seed data and shared constants
used across multiple categories.
"""

from decimal import Decimal
from typing import TypedDict, NotRequired


# =============================================================================
# Type Definitions
# =============================================================================

class CategoryData(TypedDict):
    """Vehicle category data structure."""
    slug: str
    name: str
    description: str
    icon: str
    client_type: str  # "particular" | "professional"


class TierData(TypedDict):
    """Tariff tier data structure."""
    code: str
    name: str
    description: str
    price: Decimal
    conditions: str
    classification_rules: dict
    sort_order: int
    min_elements: NotRequired[int]
    max_elements: NotRequired[int]


class ElementImageData(TypedDict):
    """Element image data structure."""
    title: str
    description: str
    image_type: str  # "example" | "required_document" | "step" | "calculation"
    sort_order: int


class WarningData(TypedDict):
    """Warning data structure."""
    code: str
    message: str
    severity: str  # "info" | "warning" | "error"
    trigger_conditions: NotRequired[dict]


class ElementData(TypedDict):
    """Element data structure."""
    code: str
    name: str
    description: str
    keywords: list[str]
    aliases: list[str]
    sort_order: int
    images: NotRequired[list[ElementImageData]]
    warnings: NotRequired[list[WarningData]]
    # Variant support
    is_base: NotRequired[bool]
    is_active: NotRequired[bool]
    parent_code: NotRequired[str]
    variant_type: NotRequired[str]
    variant_code: NotRequired[str]
    question_hint: NotRequired[str]  # Question to ask user when selecting variant


class AdditionalServiceData(TypedDict):
    """Additional service data structure."""
    code: str
    name: str
    price: Decimal
    sort_order: int


class BaseDocumentationData(TypedDict):
    """Base documentation data structure."""
    code: str
    description: str
    sort_order: int


class PromptSectionData(TypedDict):
    """Prompt section data structure."""
    code: str
    section_type: str
    content: str
    is_active: bool


# =============================================================================
# Shared Constants
# =============================================================================

BASE_DOCUMENTATION_COMMON: list[BaseDocumentationData] = [
    {
        "code": "documentos_vehiculo",
        "description": "Ficha tecnica del vehiculo (ambas caras, legible) y Permiso de circulacion por la cara escrita",
        "sort_order": 1,
    },
    {
        "code": "fotos_vehiculo",
        "description": "Foto lateral derecha, izquierda, frontal y trasera completa del vehiculo",
        "sort_order": 2,
    },
]


def get_placeholder_image_url(element_code: str, image_title: str) -> str:
    """Generate a placeholder image URL for an element image."""
    safe_title = image_title.lower().replace(" ", "_")
    return f"https://via.placeholder.com/400x300?text={element_code}_{safe_title}"
