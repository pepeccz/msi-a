"""
MSI-a Inclusion Seeder.

Seeds tier-element inclusion relationships.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    TariffTier,
    Element,
    TierElementInclusion,
)
from database.seeds.seed_utils import (
    deterministic_tier_inclusion_uuid,
    deterministic_tier_to_tier_uuid,
)
from database.seeds.seeders.base import BaseSeeder
from database.seeds.data.tier_mappings import get_tier_mapping

logger = logging.getLogger(__name__)


class InclusionSeeder(BaseSeeder):
    """
    Seeder for tier-element inclusion relationships.
    
    Creates TierElementInclusion records that define which elements
    are available in each tariff tier.
    """

    async def seed(
        self,
        tiers: dict[str, TariffTier],
        elements: dict[str, Element],
    ) -> None:
        """
        Seed tier-element inclusions based on category mapping.
        
        Args:
            tiers: Dictionary mapping tier code to TariffTier instance
            elements: Dictionary mapping element code to Element instance
        """
        logger.info(f"Seeding tier inclusions for: {self.category_slug}")
        self.reset_stats()

        if self.category_slug == "motos-part":
            await self._seed_motos_inclusions(tiers, elements)
        elif self.category_slug == "aseicars-prof":
            await self._seed_aseicars_inclusions(tiers, elements)
        else:
            logger.warning(f"No inclusion mapping defined for {self.category_slug}")
            return

        self.log_summary("Tier Inclusions")

    async def _ensure_inclusion(
        self,
        tier: TariffTier,
        element: Element | None = None,
        included_tier: TariffTier | None = None,
        min_qty: int | None = None,
        max_qty: int | None = None,
        notes: str | None = None,
    ) -> bool:
        """
        Create or update a tier-element inclusion.
        
        Returns True if created, False if updated/skipped.
        """
        if element:
            inc_id = deterministic_tier_inclusion_uuid(
                self.category_slug, tier.code, element.code
            )
            data = {
                "tier_id": tier.id,
                "element_id": element.id,
                "included_tier_id": None,
                "min_quantity": min_qty,
                "max_quantity": max_qty,
                "notes": notes,
            }
        elif included_tier:
            inc_id = deterministic_tier_to_tier_uuid(
                self.category_slug, tier.code, included_tier.code
            )
            data = {
                "tier_id": tier.id,
                "element_id": None,
                "included_tier_id": included_tier.id,
                "min_quantity": min_qty,
                "max_quantity": max_qty,
                "notes": notes,
            }
        else:
            return False

        existing = await self.session.get(TierElementInclusion, inc_id)
        
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            self.stats["updated"] += 1
            return False
        else:
            inc = TierElementInclusion(id=inc_id, **data)
            self.session.add(inc)
            self.stats["created"] += 1
            return True

    async def _seed_motos_inclusions(
        self,
        tiers: dict[str, TariffTier],
        elements: dict[str, Element],
    ) -> None:
        """Seed inclusions for motos-part category."""
        mapping = get_tier_mapping("motos-part")
        
        t1_only = mapping.get("T1_ONLY_ELEMENTS", [])
        t3_elements = mapping.get("T3_ELEMENTS", [])
        t4_base = mapping.get("T4_BASE_ELEMENTS", [])
        all_element_codes = list(elements.keys())

        # T6 (140EUR): 1 elemento de cualquier tipo
        if "T6" in tiers:
            logger.info("  T6: All elements (max 1)")
            for code in all_element_codes:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T6"],
                        element=elements[code],
                        max_qty=1,
                        notes="T6 allows 1 element",
                    )

        # T5 (175EUR): Hasta 2 elementos
        if "T5" in tiers:
            logger.info("  T5: All elements (max 2)")
            for code in all_element_codes:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T5"],
                        element=elements[code],
                        max_qty=2,
                        notes="T5 allows up to 2 elements",
                    )

        # T4 (220EUR): 3+ elementos (sin proyecto)
        if "T4" in tiers:
            logger.info("  T4: Base elements (3+ without project)")
            for code in all_element_codes:
                if code in elements and code not in t1_only and code not in t3_elements:
                    await self._ensure_inclusion(
                        tier=tiers["T4"],
                        element=elements[code],
                        min_qty=3,
                        max_qty=None,
                        notes="T4 allows 3+ elements",
                    )

        # T3 (280EUR): Proyecto sencillo
        if "T3" in tiers:
            logger.info("  T3: Project elements")
            for code in all_element_codes:
                if code in elements and code not in t1_only:
                    await self._ensure_inclusion(
                        tier=tiers["T3"],
                        element=elements[code],
                        max_qty=None,
                        notes="T3 proyecto sencillo",
                    )

        # T2 (325EUR): Proyecto medio
        if "T2" in tiers:
            logger.info("  T2: Medium project (all elements)")
            for code in all_element_codes:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T2"],
                        element=elements[code],
                        max_qty=None,
                        notes="T2 proyecto medio",
                    )

        # T1 (410EUR): Proyecto completo - todo ilimitado
        if "T1" in tiers:
            logger.info("  T1: Complete project (unlimited)")
            # All elements
            for code in all_element_codes:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T1"],
                        element=elements[code],
                        max_qty=None,
                        notes="T1 proyecto completo - unlimited",
                    )
            
            # T1 includes all lower tiers
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    await self._ensure_inclusion(
                        tier=tiers["T1"],
                        included_tier=tiers[ref_tier_code],
                        notes=f"T1 includes all of {ref_tier_code}",
                    )

    async def _seed_aseicars_inclusions(
        self,
        tiers: dict[str, TariffTier],
        elements: dict[str, Element],
    ) -> None:
        """Seed inclusions for aseicars-prof category."""
        mapping = get_tier_mapping("aseicars-prof")
        
        t6_elements = mapping.get("T6_ELEMENTS", [])
        t4_elements = mapping.get("T4_ELEMENTS", [])
        t3_elements = mapping.get("T3_ELEMENTS", [])
        t2_elements = mapping.get("T2_ELEMENTS", [])
        t1_elements = mapping.get("T1_ELEMENTS", [])

        # T6 (59EUR): 1 elemento sin proyecto
        if "T6" in tiers:
            logger.info("  T6: Basic elements (max 1)")
            for code in t6_elements:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T6"],
                        element=elements[code],
                        max_qty=1,
                        notes="T6 allows 1 basic element",
                    )

        # T5 (65EUR): Hasta 3 elementos T6
        if "T5" in tiers:
            logger.info("  T5: Basic elements (max 3)")
            for code in t6_elements:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T5"],
                        element=elements[code],
                        max_qty=3,
                        notes="T5 allows up to 3 T6 elements",
                    )

        # T4 (135EUR): Sin limite T6 + elementos adicionales
        if "T4" in tiers:
            logger.info("  T4: Multiple elements without project")
            for code in t6_elements + t4_elements:
                if code in elements:
                    await self._ensure_inclusion(
                        tier=tiers["T4"],
                        element=elements[code],
                        max_qty=None,
                        notes="T4 regularizacion varios",
                    )

        # T3 (180EUR): Proyecto basico
        if "T3" in tiers:
            logger.info("  T3: Basic project elements")
            for code in t6_elements + t4_elements + t3_elements:
                if code in elements:
                    max_qty = 1 if code in t3_elements else None
                    await self._ensure_inclusion(
                        tier=tiers["T3"],
                        element=elements[code],
                        max_qty=max_qty,
                        notes="T3 proyecto basico",
                    )
            
            # Include T6
            if "T6" in tiers:
                await self._ensure_inclusion(
                    tier=tiers["T3"],
                    included_tier=tiers["T6"],
                    notes="T3 includes T6",
                )

        # T2 (230EUR): Proyecto medio
        if "T2" in tiers:
            logger.info("  T2: Medium project elements")
            for code in t6_elements + t4_elements + t3_elements + t2_elements:
                if code in elements:
                    if code in t2_elements:
                        max_qty = 1
                    elif code in t3_elements:
                        max_qty = 2
                    else:
                        max_qty = None
                    await self._ensure_inclusion(
                        tier=tiers["T2"],
                        element=elements[code],
                        max_qty=max_qty,
                        notes="T2 proyecto medio",
                    )
            
            # Include T3 and T6
            for ref_tier_code in ["T3", "T6"]:
                if ref_tier_code in tiers:
                    await self._ensure_inclusion(
                        tier=tiers["T2"],
                        included_tier=tiers[ref_tier_code],
                        notes=f"T2 includes {ref_tier_code}",
                    )

        # T1 (270EUR): Proyecto completo
        if "T1" in tiers:
            logger.info("  T1: Complete project (unlimited)")
            # All elements
            for code in elements.keys():
                await self._ensure_inclusion(
                    tier=tiers["T1"],
                    element=elements[code],
                    max_qty=None,
                    notes="T1 proyecto completo - unlimited",
                )
            
            # T1 includes all lower tiers
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    await self._ensure_inclusion(
                        tier=tiers["T1"],
                        included_tier=tiers[ref_tier_code],
                        notes=f"T1 includes all of {ref_tier_code}",
                    )
