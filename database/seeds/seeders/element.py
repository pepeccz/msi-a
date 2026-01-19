"""
MSI-a Element Seeder.

Seeds element-level data:
- Elements (with parent/child hierarchy support)
- Element Images
- Element-scoped Warnings
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Element,
    ElementImage,
    Warning,
)
from database.seeds.seed_utils import (
    deterministic_element_uuid,
    deterministic_element_image_uuid,
    deterministic_warning_uuid,
)
from database.seeds.seeders.base import BaseSeeder
from database.seeds.data.common import (
    ElementData,
    get_placeholder_image_url,
)

logger = logging.getLogger(__name__)


class ElementSeeder(BaseSeeder):
    """
    Seeder for element data.
    
    Seeds:
    - Elements (with variant/hierarchy support)
    - Element Images
    - Element-scoped Warnings
    """

    async def seed(
        self,
        category_id: UUID,
        elements: list[ElementData],
    ) -> dict[str, Element]:
        """
        Seed all elements for a category.
        
        Args:
            category_id: The UUID of the parent category
            elements: List of element data dictionaries
        
        Returns:
            Dictionary mapping element code to Element instance
        """
        logger.info(f"Seeding elements for category: {self.category_slug}")

        # First pass: Create/update all elements (without parent relationships)
        elements_dict = await self._seed_elements_first_pass(category_id, elements)
        await self.session.flush()

        # Second pass: Resolve parent_element_id for variants
        await self._resolve_parent_relationships(elements, elements_dict)
        await self.session.flush()

        logger.info(f"Elements seeded: {len(elements_dict)} total")
        return elements_dict

    async def _seed_elements_first_pass(
        self,
        category_id: UUID,
        elements: list[ElementData],
    ) -> dict[str, Element]:
        """First pass: create/update elements without parent relationships."""
        self.reset_stats()
        elements_dict = {}
        elements_with_parent = []
        warnings_stats = {"created": 0, "updated": 0}

        for elem_data in elements:
            element_id = deterministic_element_uuid(self.category_slug, elem_data["code"])
            
            existing = await self.session.get(Element, element_id)
            
            if existing:
                # Update existing element
                existing.name = elem_data["name"]
                existing.description = elem_data["description"]
                existing.keywords = elem_data["keywords"]
                existing.aliases = elem_data.get("aliases", [])
                existing.sort_order = elem_data["sort_order"]
                existing.is_active = True
                existing.variant_type = elem_data.get("variant_type")
                existing.variant_code = elem_data.get("variant_code")
                
                elements_dict[elem_data["code"]] = existing
                element = existing
                self.log_updated("Element", elem_data["code"])
            else:
                # Create new element
                element = Element(
                    id=element_id,
                    category_id=category_id,
                    code=elem_data["code"],
                    name=elem_data["name"],
                    description=elem_data["description"],
                    keywords=elem_data["keywords"],
                    aliases=elem_data.get("aliases", []),
                    is_active=True,
                    sort_order=elem_data["sort_order"],
                    variant_type=elem_data.get("variant_type"),
                    variant_code=elem_data.get("variant_code"),
                )
                self.session.add(element)
                await self.session.flush()
                
                # Create images for new elements
                await self._seed_element_images(element, elem_data)
                
                elements_dict[elem_data["code"]] = element
                self.log_created("Element", elem_data["code"])

            # Track elements with parent for second pass
            if "parent_code" in elem_data:
                elements_with_parent.append((elem_data["code"], elem_data["parent_code"]))

            # Upsert inline warnings
            w_created, w_updated = await self._seed_element_warnings(element, elem_data)
            warnings_stats["created"] += w_created
            warnings_stats["updated"] += w_updated

        self.log_summary("Elements")
        logger.info(
            f"  Element Warnings: {warnings_stats['created']} created, "
            f"{warnings_stats['updated']} updated"
        )

        # Store for second pass
        self._elements_with_parent = elements_with_parent
        return elements_dict

    async def _seed_element_images(
        self,
        element: Element,
        elem_data: ElementData,
    ) -> None:
        """Seed images for a new element."""
        images = elem_data.get("images", [])
        
        for idx, img_data in enumerate(images):
            image_id = deterministic_element_image_uuid(
                self.category_slug,
                elem_data["code"],
                f"img_{idx + 1}"
            )
            
            # Check if image already exists
            existing_img = await self.session.get(ElementImage, image_id)
            if existing_img:
                continue
            
            image = ElementImage(
                id=image_id,
                element_id=element.id,
                image_url=get_placeholder_image_url(elem_data["code"], img_data["title"]),
                title=img_data["title"],
                description=img_data["description"],
                image_type=img_data["image_type"],
                sort_order=img_data["sort_order"],
            )
            self.session.add(image)

    async def _seed_element_warnings(
        self,
        element: Element,
        elem_data: ElementData,
    ) -> tuple[int, int]:
        """Seed inline warnings for an element."""
        created = 0
        updated = 0
        
        for warn_data in elem_data.get("warnings", []):
            warning_id = deterministic_warning_uuid(self.category_slug, warn_data["code"])
            existing_warning = await self.session.get(Warning, warning_id)
            
            if existing_warning:
                existing_warning.message = warn_data["message"]
                existing_warning.severity = warn_data.get("severity", "warning")
                existing_warning.element_id = element.id
                existing_warning.category_id = None
                existing_warning.trigger_conditions = warn_data.get("trigger_conditions")
                updated += 1
            else:
                warning = Warning(
                    id=warning_id,
                    code=warn_data["code"],
                    message=warn_data["message"],
                    severity=warn_data.get("severity", "warning"),
                    element_id=element.id,
                    category_id=None,
                    trigger_conditions=warn_data.get("trigger_conditions"),
                )
                self.session.add(warning)
                created += 1
        
        return created, updated

    async def _resolve_parent_relationships(
        self,
        elements: list[ElementData],
        elements_dict: dict[str, Element],
    ) -> None:
        """Second pass: resolve parent_element_id for variants."""
        elements_with_parent = getattr(self, "_elements_with_parent", [])
        
        if not elements_with_parent:
            return
        
        logger.info("  Resolving parent relationships...")
        resolved = 0
        
        for child_code, parent_code in elements_with_parent:
            child_element = elements_dict.get(child_code)
            parent_element = elements_dict.get(parent_code)
            
            if child_element and parent_element:
                child_element.parent_element_id = parent_element.id
                resolved += 1
                logger.info(f"    {child_code} -> parent: {parent_code}")
            else:
                logger.warning(f"    Could not resolve parent for {child_code} (parent: {parent_code})")
        
        logger.info(f"  Resolved {resolved} parent relationships")
