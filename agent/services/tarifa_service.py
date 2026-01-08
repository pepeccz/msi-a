"""
MSI Automotive - Tarifa Service for Agent.

Provides tariff calculation and documentation retrieval for the LangGraph agent.
Uses Redis caching for performance and classification_rules for AI-driven tariff selection.
"""

import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    ElementDocumentation,
    AdditionalService,
    Warning,
)
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class TarifaService:
    """
    Service for calculating tariffs and retrieving documentation.

    This service is used by LangGraph tools to provide pricing information
    and documentation requirements to customers.

    The new architecture uses classification_rules in TariffTier instead of
    a fixed HomologationElement catalog, allowing AI-driven classification.
    """

    def __init__(self):
        self.redis = get_redis_client()

    async def get_active_categories(self) -> list[dict]:
        """Get list of active vehicle categories."""
        cache_key = "tariffs:categories"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

        # Fetch from database
        async with get_async_session() as session:
            result = await session.execute(
                select(VehicleCategory)
                .where(VehicleCategory.is_active == True)
                .order_by(VehicleCategory.sort_order)
            )
            categories = result.scalars().all()

            data = [
                {
                    "slug": c.slug,
                    "name": c.name,
                    "description": c.description,
                    "icon": c.icon,
                }
                for c in categories
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")

            return data

    async def get_category_data(
        self,
        category_slug: str,
        client_type: str = "particular",
    ) -> dict | None:
        """
        Get complete data for a vehicle category.

        Returns all tiers (filtered by client_type), documentation, and services.
        Uses Redis caching.

        Args:
            category_slug: The category slug (e.g., "moto")
            client_type: Client type for filtering tiers ("particular" or "professional")
        """
        cache_key = f"tariffs:{category_slug}:{client_type}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for category: {category_slug}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

        # Fetch from database
        logger.debug(f"Cache miss for category: {category_slug}")
        data = await self._fetch_category_from_db(category_slug, client_type)

        if data:
            # Cache the result
            try:
                await self.redis.setex(
                    cache_key,
                    CACHE_TTL,
                    json.dumps(data, cls=DecimalEncoder),
                )
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")

        return data

    async def _fetch_category_from_db(
        self,
        category_slug: str,
        client_type: str = "particular",
    ) -> dict | None:
        """Fetch category data from database."""
        async with get_async_session() as session:
            # Get category with relations
            result = await session.execute(
                select(VehicleCategory)
                .where(VehicleCategory.slug == category_slug)
                .where(VehicleCategory.is_active == True)
                .options(
                    selectinload(VehicleCategory.tariff_tiers),
                    selectinload(VehicleCategory.base_documentation),
                    selectinload(VehicleCategory.element_documentation),
                    selectinload(VehicleCategory.additional_services),
                )
            )
            category = result.scalar()

            if not category:
                return None

            # Filter tiers by client_type (include "all" tiers too)
            filtered_tiers = [
                t for t in category.tariff_tiers
                if t.is_active and t.client_type in (client_type, "all")
            ]

            # Get all active warnings
            warnings_result = await session.execute(
                select(Warning).where(Warning.is_active == True)
            )
            warnings = warnings_result.scalars().all()

            # Build response
            data = {
                "category": {
                    "id": str(category.id),
                    "slug": category.slug,
                    "name": category.name,
                    "description": category.description,
                },
                "client_type": client_type,
                "tiers": [
                    {
                        "id": str(t.id),
                        "code": t.code,
                        "name": t.name,
                        "description": t.description,
                        "price": float(t.price),
                        "conditions": t.conditions,
                        "client_type": t.client_type,
                        "classification_rules": t.classification_rules,
                        "min_elements": t.min_elements,
                        "max_elements": t.max_elements,
                    }
                    for t in sorted(filtered_tiers, key=lambda x: x.sort_order)
                ],
                "warnings": [
                    {
                        "id": str(w.id),
                        "code": w.code,
                        "message": w.message,
                        "severity": w.severity,
                        "trigger_conditions": w.trigger_conditions,
                    }
                    for w in warnings
                ],
                "base_documentation": [
                    {
                        "description": bd.description,
                        "image_url": bd.image_url,
                    }
                    for bd in sorted(category.base_documentation, key=lambda x: x.sort_order)
                ],
                "element_documentation": [
                    {
                        "element_keywords": ed.element_keywords,
                        "description": ed.description,
                        "image_url": ed.image_url,
                    }
                    for ed in sorted(category.element_documentation, key=lambda x: x.sort_order)
                    if ed.is_active
                ],
                "additional_services": [
                    {
                        "code": s.code,
                        "name": s.name,
                        "description": s.description,
                        "price": float(s.price),
                    }
                    for s in sorted(category.additional_services, key=lambda x: x.sort_order)
                    if s.is_active
                ],
            }

            # Also get global additional services
            global_services_result = await session.execute(
                select(AdditionalService)
                .where(AdditionalService.category_id == None)
                .where(AdditionalService.is_active == True)
                .order_by(AdditionalService.sort_order)
            )
            for s in global_services_result.scalars():
                data["additional_services"].append({
                    "code": s.code,
                    "name": s.name,
                    "description": s.description,
                    "price": float(s.price),
                })

            return data

    async def select_tariff_by_rules(
        self,
        category_slug: str,
        elements_description: str,
        element_count: int,
        client_type: str = "particular",
    ) -> dict[str, Any]:
        """
        Select the appropriate tariff using classification_rules.

        This method is designed to be called by the AI agent to determine
        which tariff applies based on the elements described by the user.

        Args:
            category_slug: Vehicle category (e.g., "moto")
            elements_description: Natural language description of elements
            element_count: Number of elements identified
            client_type: Client type ("particular" or "professional")

        Returns:
            Dict with selected tier, price, and applicable warnings
        """
        data = await self.get_category_data(category_slug, client_type)
        if not data:
            return {
                "error": f"Categoria '{category_slug}' no encontrada",
                "available_categories": [c["slug"] for c in await self.get_active_categories()],
            }

        tiers = data["tiers"]
        if not tiers:
            return {
                "error": f"No hay tarifas configuradas para '{category_slug}'",
            }

        # Normalize description for matching
        description_lower = elements_description.lower()

        # Find matching tier using classification_rules
        selected_tier = None
        matched_rules = []

        # Sort tiers by priority (from classification_rules) if available
        def get_priority(tier):
            rules = tier.get("classification_rules") or {}
            return rules.get("priority", 999)

        sorted_tiers = sorted(tiers, key=get_priority)

        for tier in sorted_tiers:
            rules = tier.get("classification_rules")
            if not rules:
                continue

            # Check "applies_if_any" keywords
            keywords = rules.get("applies_if_any", [])
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    matched_rules.append({
                        "tier_code": tier["code"],
                        "matched_keyword": keyword,
                    })
                    if selected_tier is None:
                        selected_tier = tier
                    break

        # If no rule matched, fall back to element count logic
        if selected_tier is None:
            selected_tier = self._select_tier_by_count(tiers, element_count)

        # Find applicable warnings
        applicable_warnings = self._find_applicable_warnings(
            data["warnings"],
            description_lower,
        )

        return {
            "tier_code": selected_tier["code"],
            "tier_name": selected_tier["name"],
            "price": selected_tier["price"],
            "conditions": selected_tier.get("conditions"),
            "element_count": element_count,
            "matched_rules": matched_rules,
            "warnings": applicable_warnings,
            "additional_services": data["additional_services"],
            "requires_project": (selected_tier.get("classification_rules") or {}).get("requires_project", False),
        }

    def _select_tier_by_count(
        self,
        tiers: list[dict],
        element_count: int,
    ) -> dict:
        """
        Fallback: select tier based on element count ranges.

        Uses min_elements and max_elements from tier configuration.
        """
        for tier in tiers:
            min_elem = tier.get("min_elements")
            max_elem = tier.get("max_elements")

            # Check if element count falls in range
            if min_elem is not None and element_count < min_elem:
                continue
            if max_elem is not None and element_count > max_elem:
                continue

            return tier

        # If no range matches, return the tier with highest max_elements or last tier
        return tiers[-1] if tiers else {
            "code": "T6",
            "name": "Sin proyecto",
            "price": 140,
        }

    def _find_applicable_warnings(
        self,
        warnings: list[dict],
        description_lower: str,
    ) -> list[dict]:
        """
        Find warnings that should be shown based on trigger_conditions.

        Args:
            warnings: List of warning dicts with trigger_conditions
            description_lower: Lowercased element description

        Returns:
            List of applicable warnings
        """
        applicable = []

        for warning in warnings:
            conditions = warning.get("trigger_conditions")

            # If no conditions, skip (explicit trigger required)
            if not conditions:
                continue

            # Check "always_show"
            if conditions.get("always_show"):
                applicable.append({
                    "code": warning["code"],
                    "message": warning["message"],
                    "severity": warning["severity"],
                })
                continue

            # Check "element_keywords"
            keywords = conditions.get("element_keywords", [])
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    applicable.append({
                        "code": warning["code"],
                        "message": warning["message"],
                        "severity": warning["severity"],
                        "triggered_by": keyword,
                    })
                    break

        return applicable

    async def get_documentation(
        self,
        category_slug: str,
        elements_description: str | None = None,
    ) -> dict[str, Any]:
        """
        Get documentation requirements for a category.

        Args:
            category_slug: Vehicle category
            elements_description: Optional description of elements to match element docs

        Returns:
            Dict with base and element-specific documentation
        """
        data = await self.get_category_data(category_slug)
        if not data:
            return {
                "error": f"Categoria '{category_slug}' no encontrada",
            }

        result = {
            "category": data["category"]["name"],
            "base_documentation": data["base_documentation"],
            "element_documentation": [],
        }

        # If elements_description provided, find matching element documentation
        if elements_description:
            matched_docs = self._match_element_documentation(
                data.get("element_documentation", []),
                elements_description,
            )
            result["element_documentation"] = matched_docs

        return result

    def _match_element_documentation(
        self,
        element_docs: list[dict],
        description: str,
    ) -> list[dict]:
        """
        Match element documentation based on keywords.

        Args:
            element_docs: List of element documentation with keywords
            description: User's element description to match against

        Returns:
            List of matching documentation items
        """
        description_lower = description.lower()
        matched = []

        for doc in element_docs:
            keywords = doc.get("element_keywords", [])
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    matched.append({
                        "description": doc["description"],
                        "image_url": doc.get("image_url"),
                        "matched_keyword": keyword,
                    })
                    break  # Only add once per doc

        return matched

    def format_tariff_response(self, result: dict) -> str:
        """Format tariff calculation result as readable text."""
        if "error" in result:
            return f"Error: {result['error']}"

        lines = [
            f"**Tarifa aplicada: {result['tier_name']} ({result['tier_code']})**",
            f"**Precio: {result['price']}EUR** (IVA no incluido)",
        ]

        if result.get("conditions"):
            lines.append(f"Condiciones: {result['conditions']}")

        if result.get("element_count"):
            lines.append(f"Elementos identificados: {result['element_count']}")

        if result.get("matched_rules"):
            lines.append("")
            lines.append("Reglas aplicadas:")
            for rule in result["matched_rules"]:
                lines.append(f"  - {rule['tier_code']}: coincide con '{rule['matched_keyword']}'")

        if result.get("warnings"):
            lines.append("")
            lines.append("**Advertencias:**")
            for w in result["warnings"]:
                severity_icon = "🔴" if w["severity"] == "error" else "⚠️" if w["severity"] == "warning" else "ℹ️"
                lines.append(f"{severity_icon} {w['message']}")

        if result.get("additional_services"):
            lines.append("")
            lines.append("Servicios adicionales disponibles:")
            for s in result["additional_services"]:
                lines.append(f"  - {s['name']}: {s['price']}EUR")

        return "\n".join(lines)

    def format_documentation_response(
        self, result: dict
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Format documentation result as text and images with metadata.

        Returns:
            Tuple of (text_response, list_of_image_metadata)
            Each image dict contains: {"url": str, "tipo": str, "descripcion": str}
            tipo: "base" for base documentation, "elemento" for element-specific
        """
        if "error" in result:
            return f"Error: {result['error']}", []

        lines = [
            f"**Documentacion necesaria para {result['category']}**",
            "",
            "**Documentacion base (siempre requerida):**",
        ]

        all_images: list[dict[str, Any]] = []
        for doc in result.get("base_documentation", []):
            lines.append(f"  - {doc['description']}")
            if doc.get("image_url"):
                all_images.append({
                    "url": doc["image_url"],
                    "tipo": "base",
                    "descripcion": doc["description"],
                })

        # Add element-specific documentation if present
        element_docs = result.get("element_documentation", [])
        if element_docs:
            lines.append("")
            lines.append("**Documentacion especifica por elemento:**")
            for doc in element_docs:
                lines.append(f"  - {doc['description']}")
                if doc.get("image_url"):
                    all_images.append({
                        "url": doc["image_url"],
                        "tipo": "elemento",
                        "descripcion": doc["description"],
                    })

        return "\n".join(lines), all_images

    async def invalidate_cache(self, category_slug: str | None = None) -> None:
        """
        Invalidate cached tariff data.

        Args:
            category_slug: Specific category to invalidate, or None for all
        """
        try:
            if category_slug:
                # Invalidate specific category (both client types)
                keys = [
                    f"tariffs:{category_slug}:particular",
                    f"tariffs:{category_slug}:professional",
                ]
                for key in keys:
                    await self.redis.delete(key)
                logger.info(f"Invalidated tariff cache for category: {category_slug}")
            else:
                # Invalidate all tariff caches
                await self.redis.delete("tariffs:categories")
                pattern = "tariffs:*"
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info("Invalidated all tariff caches")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")


# Singleton instance
_tarifa_service: TarifaService | None = None


def get_tarifa_service() -> TarifaService:
    """Get or create the TarifaService singleton."""
    global _tarifa_service
    if _tarifa_service is None:
        _tarifa_service = TarifaService()
    return _tarifa_service
