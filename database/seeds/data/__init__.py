"""
MSI-a Seed Data Module.

This module contains all seed data definitions separated from seeding logic.
Each category has its own module with CATEGORY, TIERS, ELEMENTS, etc.
"""

from database.seeds.data.common import (
    CategoryData,
    TierData,
    ElementData,
    ElementImageData,
    WarningData,
    AdditionalServiceData,
    BaseDocumentationData,
    PromptSectionData,
    BASE_DOCUMENTATION_COMMON,
)
from database.seeds.data import motos_part
from database.seeds.data import aseicars_prof
from database.seeds.data import tier_mappings

__all__ = [
    # Type definitions
    "CategoryData",
    "TierData",
    "ElementData",
    "ElementImageData",
    "WarningData",
    "AdditionalServiceData",
    "BaseDocumentationData",
    "PromptSectionData",
    # Common data
    "BASE_DOCUMENTATION_COMMON",
    # Category modules
    "motos_part",
    "aseicars_prof",
    # Tier mappings
    "tier_mappings",
]
