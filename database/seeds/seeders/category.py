"""
MSI-a Category Seeder.

Seeds category-level data:
- VehicleCategory
- TariffTiers
- Category-scoped Warnings
- AdditionalServices
- BaseDocumentation
- TariffPromptSections
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    VehicleCategory,
    TariffTier,
    Warning,
    Element,
    ElementWarningAssociation,
    AdditionalService,
    BaseDocumentation,
    TariffPromptSection,
)
from database.seeds.seed_utils import (
    deterministic_category_uuid,
    deterministic_tier_uuid,
    deterministic_warning_uuid,
    deterministic_additional_service_uuid,
    deterministic_base_doc_uuid,
    deterministic_prompt_section_uuid,
    deterministic_category_warning_assoc_uuid,
    deterministic_element_uuid,
)
from database.seeds.seeders.base import BaseSeeder
from database.seeds.data.common import (
    CategoryData,
    TierData,
    WarningData,
    AdditionalServiceData,
    BaseDocumentationData,
    PromptSectionData,
)

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


class CategorySeeder(BaseSeeder):
    """
    Seeder for category-level data.
    
    Seeds:
    - VehicleCategory
    - TariffTiers (T1-T6)
    - Category-scoped Warnings
    - AdditionalServices
    - BaseDocumentation
    - TariffPromptSections
    """

    async def seed(
        self,
        category: CategoryData,
        tiers: list[TierData],
        category_warnings: list[WarningData],
        services: list[AdditionalServiceData],
        base_docs: list[BaseDocumentationData],
        prompt_sections: list[PromptSectionData],
        skip_associations: bool = False,
    ) -> tuple[VehicleCategory, dict[str, TariffTier]]:
        """
        Seed all category-level data.

        Args:
            category: Category data dictionary
            tiers: List of tier data dictionaries
            category_warnings: List of category-scoped warning data
            services: List of additional service data
            base_docs: List of base documentation data
            prompt_sections: List of prompt section data
            skip_associations: If True, skip creating ElementWarningAssociations
                (useful when elements haven't been seeded yet)

        Returns:
            Tuple of (category_instance, tiers_dict)
        """
        logger.info(f"Seeding category: {self.category_slug}")

        # 1. Upsert Category
        category_instance = await self._seed_category(category)
        await self.session.flush()

        # 2. Upsert Tiers
        tiers_dict = await self._seed_tiers(tiers, category_instance.id)
        await self.session.flush()

        # 3. Upsert Category Warnings (optionally without associations)
        await self._seed_warnings(
            category_warnings, category_instance.id,
            skip_associations=skip_associations,
        )
        await self.session.flush()

        # 4. Upsert Additional Services
        await self._seed_services(services, category_instance.id)
        await self.session.flush()

        # 5. Upsert Base Documentation
        await self._seed_base_docs(base_docs, category_instance.id)
        await self.session.flush()

        # 6. Upsert Prompt Sections
        await self._seed_prompt_sections(prompt_sections, category_instance.id)
        await self.session.flush()

        logger.info(f"Category {self.category_slug} seeded successfully")
        return category_instance, tiers_dict

    async def _seed_category(self, data: CategoryData) -> VehicleCategory:
        """Seed the vehicle category."""
        category_id = deterministic_category_uuid(self.category_slug)
        
        instance, action = await self.upsert(
            model_class=VehicleCategory,
            deterministic_id=category_id,
            data=dict(data),
            entity_type="Category",
            code=self.category_slug,
        )
        
        return instance

    async def _seed_tiers(
        self,
        tiers: list[TierData],
        category_id: UUID,
    ) -> dict[str, TariffTier]:
        """Seed tariff tiers."""
        self.reset_stats()
        tiers_dict = {}

        for tier_data in tiers:
            tier_id = deterministic_tier_uuid(self.category_slug, tier_data["code"])
            
            # Prepare data with category_id
            data = dict(tier_data)
            data["category_id"] = category_id
            
            instance, action = await self.upsert(
                model_class=TariffTier,
                deterministic_id=tier_id,
                data=data,
                entity_type="Tier",
                code=tier_data["code"],
            )
            
            tiers_dict[tier_data["code"]] = instance

        self.log_summary("Tiers")
        return tiers_dict

    async def _seed_warnings(
        self,
        warnings: list[WarningData],
        category_id: UUID,
        skip_associations: bool = False,
    ) -> None:
        """Seed category-scoped warnings and optionally their element associations."""
        if not warnings:
            return

        self.reset_stats()

        for warning_data in warnings:
            warning_id = deterministic_warning_uuid(self.category_slug, warning_data["code"])

            # Prepare data — strip 'associations' key (not a model field)
            data = {k: v for k, v in warning_data.items() if k != "associations"}
            data["category_id"] = category_id

            await self.upsert(
                model_class=Warning,
                deterministic_id=warning_id,
                data=data,
                entity_type="Warning",
                code=warning_data["code"],
            )

            if not skip_associations:
                await self._seed_warning_associations_for(warning_data, warning_id)

        self.log_summary("Category Warnings")

    async def seed_warning_associations(
        self,
        warnings: list[WarningData],
    ) -> None:
        """
        Seed ElementWarningAssociations for category-level warnings.

        Call this AFTER elements have been seeded so FK references are valid.
        """
        self.reset_stats()

        for warning_data in warnings:
            warning_id = deterministic_warning_uuid(self.category_slug, warning_data["code"])
            await self._seed_warning_associations_for(warning_data, warning_id)

        self.log_summary("Category Warning Associations")

    async def _resolve_element_id(self, element_code: str) -> UUID | None:
        """Resolve element UUID, handling legacy non-deterministic IDs."""
        # Try deterministic UUID first
        det_id = deterministic_element_uuid(self.category_slug, element_code)
        existing = await self.session.get(Element, det_id)
        if existing:
            return det_id

        # Fallback: lookup by (category_id, code)
        category_id = deterministic_category_uuid(self.category_slug)
        result = (await self.session.execute(
            select(Element.id).where(
                and_(
                    Element.category_id == category_id,
                    Element.code == element_code,
                )
            )
        )).scalar_one_or_none()

        # Also try with legacy category UUID
        if result is None:
            result = (await self.session.execute(
                select(Element.id).where(Element.code == element_code).join(
                    VehicleCategory,
                    and_(
                        VehicleCategory.id == Element.category_id,
                        VehicleCategory.slug == self.category_slug,
                    ),
                )
            )).scalar_one_or_none()

        return result

    async def _seed_warning_associations_for(
        self,
        warning_data: WarningData,
        warning_id: UUID,
    ) -> None:
        """Create ElementWarningAssociations for a single category warning."""
        element_codes: list[str] = warning_data.get("associations", [])  # type: ignore[assignment]
        for element_code in element_codes:
            element_id = await self._resolve_element_id(element_code)
            if not element_id:
                logger.warning(
                    f"  ⚠ Element {element_code} not found for association "
                    f"with warning {warning_data['code']}, skipping"
                )
                continue

            assoc_id = deterministic_category_warning_assoc_uuid(
                self.category_slug, warning_data["code"], element_code
            )

            # Check by unique pair first (handles legacy non-deterministic IDs)
            existing_by_pair = (await self.session.execute(
                select(ElementWarningAssociation).where(
                    and_(
                        ElementWarningAssociation.element_id == element_id,
                        ElementWarningAssociation.warning_id == warning_id,
                    )
                )
            )).scalar_one_or_none()

            if existing_by_pair:
                existing_by_pair.show_condition = "always"
                existing_by_pair.threshold_quantity = None
                self.log_updated(
                    "CategoryWarningAssoc",
                    f"{warning_data['code']}:{element_code}",
                )
            else:
                await self.upsert(
                    model_class=ElementWarningAssociation,
                    deterministic_id=assoc_id,
                    data={
                        "element_id": element_id,
                        "warning_id": warning_id,
                        "show_condition": "always",
                        "threshold_quantity": None,
                    },
                    entity_type="CategoryWarningAssoc",
                    code=f"{warning_data['code']}:{element_code}",
                )

    async def _seed_services(
        self,
        services: list[AdditionalServiceData],
        category_id: UUID,
    ) -> None:
        """Seed additional services."""
        if not services:
            return

        self.reset_stats()

        for svc_data in services:
            svc_id = deterministic_additional_service_uuid(self.category_slug, svc_data["code"])
            
            # Prepare data
            data = dict(svc_data)
            data["category_id"] = category_id
            
            await self.upsert(
                model_class=AdditionalService,
                deterministic_id=svc_id,
                data=data,
                entity_type="Service",
                code=svc_data["code"],
            )

        self.log_summary("Services")

    async def _seed_base_docs(
        self,
        docs: list[BaseDocumentationData],
        category_id: UUID,
    ) -> None:
        """Seed base documentation."""
        if not docs:
            return

        self.reset_stats()

        for doc_data in docs:
            doc_id = deterministic_base_doc_uuid(self.category_slug, doc_data["code"])
            
            # Prepare data without code (not a model field)
            data = {k: v for k, v in doc_data.items() if k != "code"}
            data["category_id"] = category_id
            
            await self.upsert(
                model_class=BaseDocumentation,
                deterministic_id=doc_id,
                data=data,
                entity_type="BaseDoc",
                code=doc_data["code"],
            )

        self.log_summary("Base Documentation")

    async def _seed_prompt_sections(
        self,
        sections: list[PromptSectionData],
        category_id: UUID,
    ) -> None:
        """Seed prompt sections."""
        if not sections:
            return

        self.reset_stats()

        for section_data in sections:
            section_id = deterministic_prompt_section_uuid(self.category_slug, section_data["code"])
            
            # Prepare data without code (not a model field)
            data = {k: v for k, v in section_data.items() if k != "code"}
            data["category_id"] = category_id
            
            await self.upsert(
                model_class=TariffPromptSection,
                deterministic_id=section_id,
                data=data,
                entity_type="PromptSection",
                code=section_data["code"],
            )

        self.log_summary("Prompt Sections")
