"""
MSI-a Required Fields Seeder.

Seeds element required fields from data modules.
"""

import logging
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ElementRequiredField
from database.seeds.seed_utils import deterministic_required_field_uuid
from database.seeds.seeders.base import BaseSeeder
from database.seeds.data.common import ElementData

logger = logging.getLogger(__name__)


class RequiredFieldSeeder(BaseSeeder):
    """
    Seeder for element required fields.
    
    Seeds:
    - ElementRequiredField records from element data definitions
    """

    def __init__(self, category_slug: str, session: AsyncSession):
        super().__init__(category_slug, session)

    async def seed(
        self,
        elements: list[ElementData],
        elements_dict: dict[str, UUID],
    ) -> None:
        """
        Seed all required fields for elements.
        
        Args:
            elements: List of element data dictionaries
            elements_dict: Mapping of element code to element UUID
        """
        logger.info(f"Seeding required fields for category: {self.category_slug}")
        
        self.reset_stats()
        
        for elem_data in elements:
            element_code = elem_data["code"]
            element_id = elements_dict.get(element_code)
            
            if not element_id:
                logger.warning(f"  Element {element_code} not found in elements_dict, skipping fields")
                continue
            
            # Seed required fields
            for field_data in elem_data.get("required_fields", []):
                await self._seed_required_field(element_id, element_code, field_data)
                # Flush after each field to detect uniqueness issues early
                await self.session.flush()
        
        self.log_summary("Required Fields")

    async def _seed_required_field(
        self,
        element_id: UUID,
        element_code: str,
        field_data: dict,
    ) -> None:
        """Seed a single required field."""
        field_key = field_data["field_key"]
        field_id = deterministic_required_field_uuid(
            self.category_slug,
            element_code,
            field_key
        )
        
        # Try deterministic ID first, then fallback to unique pair
        existing = await self.session.get(ElementRequiredField, field_id)
        if not existing:
            existing = (await self.session.execute(
                select(ElementRequiredField).where(
                    and_(
                        ElementRequiredField.element_id == element_id,
                        ElementRequiredField.field_key == field_key,
                    )
                )
            )).scalar_one_or_none()

        if existing:
            # Update existing field
            existing.field_key = field_key
            existing.field_label = field_data.get("field_label", field_key)
            existing.field_type = field_data.get("field_type", "text")
            existing.sort_order = field_data.get("sort_order", 999)
            existing.is_required = field_data.get("is_required", False)
            existing.validation_rules = field_data.get("validation_rules")
            existing.example_value = field_data.get("example_value")
            existing.options = field_data.get("options")
            existing.llm_instruction = field_data.get("llm_instruction")
            existing.condition_operator = field_data.get("condition_operator")
            existing.condition_value = field_data.get("condition_value")
            # Note: condition_field_id requires resolving field_key to UUID (TODO for future)
            
            self.log_updated("RequiredField", f"{element_code}.{field_key}")
        else:
            # Create new field
            field = ElementRequiredField(
                id=field_id,
                element_id=element_id,
                field_key=field_key,
                field_label=field_data.get("field_label", field_key),
                field_type=field_data.get("field_type", "text"),
                sort_order=field_data.get("sort_order", 999),
                is_required=field_data.get("is_required", False),
                validation_rules=field_data.get("validation_rules"),
                example_value=field_data.get("example_value"),
                options=field_data.get("options"),
                llm_instruction=field_data.get("llm_instruction"),
                condition_operator=field_data.get("condition_operator"),
                condition_value=field_data.get("condition_value"),
                # Note: condition_field_id requires resolving field_key to UUID (TODO for future)
            )
            self.session.add(field)
            self.log_created("RequiredField", f"{element_code}.{field_key}")
