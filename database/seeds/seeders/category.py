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

        # 3. Upsert Category Warnings
        await self._seed_warnings(category_warnings, category_instance.id)
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
    ) -> None:
        """Seed category-scoped warnings."""
        if not warnings:
            return

        self.reset_stats()

        for warning_data in warnings:
            warning_id = deterministic_warning_uuid(self.category_slug, warning_data["code"])
            
            # Prepare data
            data = dict(warning_data)
            data["category_id"] = category_id
            data["element_id"] = None  # Category-scoped, not element-scoped
            
            await self.upsert(
                model_class=Warning,
                deterministic_id=warning_id,
                data=data,
                entity_type="Warning",
                code=warning_data["code"],
            )

        self.log_summary("Category Warnings")

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
