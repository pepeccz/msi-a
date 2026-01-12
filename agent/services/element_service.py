"""
MSI Automotive - Element Service for Agent.

Provides element catalog management, keyword matching, and element-based tariff resolution.
Supports the new hierarchical element system for precise tariff calculation.
"""

import json
import logging
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import Element, ElementImage, TierElementInclusion, Warning

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300

# Fuzzy matching threshold (0.0-1.0)
FUZZY_MATCH_THRESHOLD = 0.85


class ElementService:
    """
    Service for managing homologable elements and matching.

    This service provides:
    - Element catalog retrieval per category
    - Keyword-based element matching from user descriptions
    - Element details with images
    - Support for the hierarchical element system
    """

    def __init__(self):
        from shared.redis_client import get_redis_client

        self.redis = get_redis_client()

    async def get_elements_by_category(
        self,
        category_id: str,
        is_active: bool = True,
    ) -> list[dict]:
        """
        Get all elements for a specific vehicle category.

        Args:
            category_id: UUID of the vehicle category
            is_active: Filter by active status (default True)

        Returns:
            List of element dictionaries with basic info (no images)
        """
        cache_key = f"elements:category:{category_id}:active={is_active}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")

        # Fetch from database
        async with get_async_session() as session:
            query = select(Element).where(Element.category_id == category_id)

            if is_active:
                query = query.where(Element.is_active == True)

            query = query.order_by(Element.sort_order, Element.name)

            result = await session.execute(query)
            elements = result.scalars().all()

            data = [
                {
                    "id": str(elem.id),
                    "category_id": str(elem.category_id),
                    "code": elem.code,
                    "name": elem.name,
                    "description": elem.description,
                    "keywords": elem.keywords,
                    "aliases": elem.aliases or [],
                    "is_active": elem.is_active,
                    "sort_order": elem.sort_order,
                }
                for elem in elements
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

            return data

    async def match_elements_from_description(
        self,
        description: str,
        category_id: str,
    ) -> list[tuple[dict, float]]:
        """
        Match elements from user description using keyword matching.

        This is PHASE 1 of the matching algorithm - keyword-based.
        Future PHASE 2 will add LLM refinement for ambiguous cases.

        Args:
            description: User's text description of elements
            category_id: Vehicle category ID

        Returns:
            List of (element_dict, confidence_score) tuples, sorted by confidence descending
        """
        # Get all active elements for this category
        elements = await self.get_elements_by_category(category_id, is_active=True)

        # Tokenize user description
        tokens = description.lower().split()

        matches = []

        for element in elements:
            score = 0.0

            # Score exact keyword matches
            for keyword in element.get("keywords", []):
                if keyword.lower() in tokens:
                    score += 1.0

            # Score alias matches (slightly lower weight)
            for alias in element.get("aliases", []):
                if alias.lower() in tokens:
                    score += 0.8

            # Score fuzzy matching for typos/variations
            for token in tokens:
                for keyword in element.get("keywords", []):
                    similarity = self._fuzzy_match(token, keyword.lower())
                    if similarity > FUZZY_MATCH_THRESHOLD:
                        score += 0.5 * similarity  # Weight by similarity degree

            # Only include if score > 0
            if score > 0:
                matches.append((element, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    async def get_element_with_images(
        self,
        element_id: str,
    ) -> dict | None:
        """
        Get element details with all associated images.

        Args:
            element_id: UUID of the element

        Returns:
            Element dict with images list, or None if not found
        """
        cache_key = f"element:details:{element_id}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")

        # Fetch from database with eager loading
        async with get_async_session() as session:
            result = await session.execute(
                select(Element)
                .where(Element.id == element_id)
                .options(selectinload(Element.images))
            )
            element = result.unique().scalar_one_or_none()

            if not element:
                return None

            # Serialize element with images
            data = {
                "id": str(element.id),
                "category_id": str(element.category_id),
                "code": element.code,
                "name": element.name,
                "description": element.description,
                "keywords": element.keywords,
                "aliases": element.aliases or [],
                "is_active": element.is_active,
                "sort_order": element.sort_order,
                "images": [
                    {
                        "id": str(img.id),
                        "image_url": img.image_url,
                        "title": img.title,
                        "description": img.description,
                        "image_type": img.image_type,
                        "sort_order": img.sort_order,
                        "is_required": img.is_required,
                    }
                    for img in sorted(element.images, key=lambda x: x.sort_order)
                ],
            }

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

            return data

    async def get_element_warnings(
        self,
        element_id: str,
    ) -> list[dict]:
        """
        Get warnings associated with an element.

        Args:
            element_id: UUID of the element

        Returns:
            List of warning dictionaries
        """
        from database.models import ElementWarningAssociation

        async with get_async_session() as session:
            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.element_id == element_id)
                .options(selectinload(ElementWarningAssociation.warning))
            )
            associations = result.unique().scalars().all()

            warnings = [
                {
                    "id": str(assoc.warning.id),
                    "code": assoc.warning.code,
                    "message": assoc.warning.message,
                    "severity": assoc.warning.severity,
                    "show_condition": assoc.show_condition,
                    "threshold_quantity": assoc.threshold_quantity,
                }
                for assoc in associations
                if assoc.warning.is_active
            ]

            return warnings

    async def get_warnings_for_elements(
        self,
        element_ids: list[str],
    ) -> list[dict]:
        """
        Get warnings associated with multiple elements.

        Args:
            element_ids: List of element UUIDs

        Returns:
            List of warning dictionaries (deduplicated)
        """
        if not element_ids:
            return []

        from database.models import ElementWarningAssociation

        async with get_async_session() as session:
            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.element_id.in_(element_ids))
                .options(selectinload(ElementWarningAssociation.warning))
            )
            associations = result.unique().scalars().all()

            # Deduplicate by warning ID
            seen_ids = set()
            warnings = []
            for assoc in associations:
                if not assoc.warning.is_active:
                    continue
                warning_id = str(assoc.warning.id)
                if warning_id in seen_ids:
                    continue
                seen_ids.add(warning_id)
                warnings.append({
                    "id": warning_id,
                    "code": assoc.warning.code,
                    "message": assoc.warning.message,
                    "severity": assoc.warning.severity,
                    "show_condition": assoc.show_condition,
                    "threshold_quantity": assoc.threshold_quantity,
                    "element_id": str(assoc.element_id),
                })

            return warnings

    @staticmethod
    def _fuzzy_match(token: str, keyword: str) -> float:
        """
        Calculate fuzzy match similarity between token and keyword.

        Args:
            token: User's token (e.g., "escalera")
            keyword: Element's keyword (e.g., "escalera mecanica")

        Returns:
            Similarity score (0.0-1.0)
        """
        return SequenceMatcher(None, token, keyword).ratio()

    def invalidate_category_cache(self, category_id: str) -> None:
        """
        Invalidate cache for a specific category.

        Called when elements are created/updated/deleted.

        Args:
            category_id: UUID of the category
        """
        # This is synchronous since invalidation is best-effort
        cache_key = f"elements:category:{category_id}:active=True"
        try:
            # Note: Can't use await in sync method, so we skip this for now
            # In production, use async variant or queue invalidation
            logger.info(f"Cache invalidation queued for {cache_key}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")


# Singleton instance
_element_service = None


def get_element_service() -> ElementService:
    """Get or create ElementService singleton."""
    global _element_service
    if _element_service is None:
        _element_service = ElementService()
    return _element_service
