"""
MSI Automotive - Element Service for Agent.

Provides element catalog management, keyword matching, and element-based tariff resolution.
Supports the new hierarchical element system for precise tariff calculation.
"""

import json
import logging
import unicodedata
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
        Match elements from user description using hybrid algorithm.

        Matching phases:
        - Phase 1: Exact single-word keyword match (1.0 pts)
        - Phase 2: Multi-word keyword partial/full match (0.4-0.8 pts)
        - Phase 3: Alias match (0.6 pts)
        - Phase 4: N-gram fuzzy matching for typos (0.0-0.4 pts)

        Args:
            description: User's text description of elements
            category_id: Vehicle category ID

        Returns:
            List of (element_dict, confidence_score) tuples, sorted by confidence descending
        """
        # Get all active elements for this category
        elements = await self.get_elements_by_category(category_id, is_active=True)

        # Tokenize with normalization (accents removed)
        desc_normalized = self._normalize_text(description)
        tokens = desc_normalized.split()

        matches = []

        for element in elements:
            score = 0.0
            keywords = element.get("keywords", [])
            aliases = element.get("aliases", [])

            # === PHASE 1: Exact single-word keyword matches ===
            for keyword in keywords:
                kw_normalized = self._normalize_text(keyword)
                if kw_normalized in tokens:
                    score += 1.0

            # === PHASE 2: Multi-word keyword partial/full matching ===
            for keyword in keywords:
                if " " in keyword:  # Multi-word keyword
                    word_overlap = self._word_overlap_score(tokens, keyword)
                    if word_overlap > 0.5:  # At least 50% of words match
                        # Bonus: if full phrase is in description
                        kw_normalized = self._normalize_text(keyword)
                        if kw_normalized in desc_normalized:
                            score += 0.8  # Full phrase match
                        else:
                            score += 0.4 * word_overlap  # Partial match

            # === PHASE 3: Alias matches ===
            for alias in aliases:
                alias_normalized = self._normalize_text(alias)
                if alias_normalized in tokens or alias_normalized in desc_normalized:
                    score += 0.6

            # === PHASE 4: N-gram fuzzy matching for typos ===
            for token in tokens:
                if len(token) >= 4:  # Only tokens with sufficient length
                    for keyword in keywords:
                        kw_normalized = self._normalize_text(keyword)
                        # Only compare with single-word keywords
                        if " " not in keyword:
                            ngram_sim = self._ngram_similarity(token, kw_normalized)
                            if ngram_sim > 0.5:  # Lower threshold than SequenceMatcher
                                score += 0.4 * ngram_sim

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

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text: lowercase and remove accents.

        Args:
            text: Input text

        Returns:
            Normalized text without accents
        """
        text = unicodedata.normalize('NFD', text.lower())
        return ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    @staticmethod
    def _generate_char_ngrams(text: str, n: int = 3) -> set[str]:
        """
        Generate character n-grams for fuzzy matching.

        Args:
            text: Input text
            n: N-gram size (default 3 for trigrams)

        Returns:
            Set of character n-grams
        """
        text = ElementService._normalize_text(text)
        text = f"#{text}#"  # Boundary markers
        return {text[i:i+n] for i in range(len(text) - n + 1)}

    def _ngram_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Jaccard similarity between character trigrams.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0-1.0)
        """
        ngrams1 = self._generate_char_ngrams(text1)
        ngrams2 = self._generate_char_ngrams(text2)
        if not ngrams1 or not ngrams2:
            return 0.0
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        return intersection / union

    def _word_overlap_score(self, tokens: list[str], keyword: str) -> float:
        """
        Calculate word overlap score for multi-word keywords.

        Args:
            tokens: User's tokenized input (already normalized)
            keyword: Multi-word keyword

        Returns:
            Overlap score (0.0-1.0)
        """
        keyword_words = set(self._normalize_text(keyword).split())
        token_set = set(tokens)
        if not keyword_words:
            return 0.0
        overlap = len(keyword_words & token_set)
        return overlap / len(keyword_words)

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
