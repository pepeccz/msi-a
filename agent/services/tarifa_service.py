"""
MSI Automotive - Tarifa Service for Agent.

Provides tariff calculation and documentation retrieval for the LangGraph agent.
Uses Redis caching for performance and classification_rules for AI-driven tariff selection.
"""

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    AdditionalService,
    Warning,
    Element,
    TierElementInclusion,
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

    Architecture:
    - Categories are separated by client_type (e.g., motos-part, motos-prof)
    - Tiers belong to a category and don't have client_type
    - classification_rules in TariffTier allow AI-driven classification
    """

    def __init__(self):
        self.redis = get_redis_client()

    async def get_active_categories(
        self,
        client_type: str | None = None,
    ) -> list[dict]:
        """
        Get list of active vehicle categories.

        Args:
            client_type: Optional filter by client type ("particular" or "professional")

        Returns:
            List of category dicts
        """
        cache_key = f"tariffs:categories:{client_type or 'all'}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

        # Fetch from database
        async with get_async_session() as session:
            query = (
                select(VehicleCategory)
                .where(VehicleCategory.is_active == True)
                .order_by(VehicleCategory.sort_order)
            )

            if client_type:
                query = query.where(VehicleCategory.client_type == client_type)

            result = await session.execute(query)
            categories = result.scalars().all()

            data = [
                {
                    "id": str(c.id),
                    "slug": c.slug,
                    "name": c.name,
                    "description": c.description,
                    "icon": c.icon,
                    "client_type": c.client_type,
                }
                for c in categories
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")

            return data

    async def get_supported_categories_for_client(
        self,
        client_type: str = "particular",
    ) -> list[dict]:
        """
        Get categories that have active tariffs for the given client type.

        Categories are now separated by client_type, so we filter categories
        directly instead of filtering by tier's client_type.

        Args:
            client_type: "particular" or "professional"

        Returns:
            List of category dicts with slug, name, description
        """
        cache_key = f"tariffs:supported:{client_type}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for supported categories: {client_type}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

        # Fetch from database
        logger.debug(f"Cache miss for supported categories: {client_type}")

        async with get_async_session() as session:
            # Query: Get categories for this client_type that have active tiers
            result = await session.execute(
                select(VehicleCategory)
                .distinct()
                .join(TariffTier, TariffTier.category_id == VehicleCategory.id)
                .where(VehicleCategory.is_active == True)
                .where(VehicleCategory.client_type == client_type)
                .where(TariffTier.is_active == True)
                .order_by(VehicleCategory.sort_order)
            )
            categories = result.scalars().all()

            data = [
                {
                    "slug": c.slug,
                    "name": c.name,
                    "description": c.description,
                    "client_type": c.client_type,
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
    ) -> dict | None:
        """
        Get complete data for a vehicle category.

        Returns all tiers, documentation, and services.
        Uses Redis caching.

        Note: client_type is now part of the category (in the slug),
        so no separate filtering is needed.

        Args:
            category_slug: The category slug (e.g., "motos-part", "motos-prof")
        """
        cache_key = f"tariffs:{category_slug}"

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
        data = await self._fetch_category_from_db(category_slug)

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
                    selectinload(VehicleCategory.additional_services),
                )
            )
            category = result.scalar()

            if not category:
                return None

            # Get all active tiers for this category (no client_type filter needed)
            active_tiers = [t for t in category.tariff_tiers if t.is_active]

            # Get warnings: global (no scope) + category-scoped
            warnings_result = await session.execute(
                select(Warning)
                .where(Warning.is_active == True)
                .where(
                    (Warning.category_id == None) & (Warning.tier_id == None) & (Warning.element_id == None)  # Global
                    | (Warning.category_id == category.id)  # Category-scoped
                )
            )
            warnings = warnings_result.scalars().all()

            # Build response
            data = {
                "category": {
                    "id": str(category.id),
                    "slug": category.slug,
                    "name": category.name,
                    "description": category.description,
                    "client_type": category.client_type,
                },
                "tiers": [
                    {
                        "id": str(t.id),
                        "code": t.code,
                        "name": t.name,
                        "description": t.description,
                        "price": float(t.price),
                        "conditions": t.conditions,
                        "classification_rules": t.classification_rules,
                        "min_elements": t.min_elements,
                        "max_elements": t.max_elements,
                    }
                    for t in sorted(active_tiers, key=lambda x: x.sort_order)
                ],
                "warnings": [
                    {
                        "id": str(w.id),
                        "code": w.code,
                        "message": w.message,
                        "severity": w.severity,
                        "trigger_conditions": w.trigger_conditions,
                        "category_id": str(w.category_id) if w.category_id else None,
                        "tier_id": str(w.tier_id) if w.tier_id else None,
                        "element_id": str(w.element_id) if w.element_id else None,
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
        element_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Select the appropriate tariff using classification_rules.

        This method is designed to be called by the AI agent to determine
        which tariff applies based on the elements described by the user.

        Args:
            category_slug: Vehicle category (e.g., "motos-part", "motos-prof")
            elements_description: Natural language description of elements
            element_count: Number of elements identified
            element_codes: Optional list of element codes for tier validation

        Returns:
            Dict with selected tier, price, applicable warnings, and element_validation
        """
        data = await self.get_category_data(category_slug)
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
                        # Verificar que el conteo de elementos esté en el rango del tier
                        min_elem = tier.get("min_elements")
                        max_elem = tier.get("max_elements")

                        in_range = True
                        if min_elem is not None and element_count < min_elem:
                            in_range = False
                        if max_elem is not None and element_count > max_elem:
                            in_range = False

                        if in_range:
                            selected_tier = tier
                    break

        # If no tier with keywords matched the element range, fall back to count logic
        if selected_tier is None:
            selected_tier = self._select_tier_by_count(tiers, element_count)

        # Find applicable warnings (pass tier_id for tier-scoped warnings)
        applicable_warnings = self._find_applicable_warnings(
            data["warnings"],
            description_lower,
            selected_tier_id=selected_tier.get("id"),
        )

        # Validate elements in tier (if element_codes provided)
        element_validation: dict[str, Any] = {"valid": True}
        if element_codes and selected_tier.get("id"):
            element_validation = await self.validate_elements_in_tier(
                tier_id=selected_tier["id"],
                element_codes=element_codes,
                category_id=data["category"]["id"],
            )

        return {
            "tier_code": selected_tier["code"],
            "tier_name": selected_tier["name"],
            "tier_id": selected_tier.get("id"),
            "price": selected_tier["price"],
            "conditions": selected_tier.get("conditions"),
            "element_count": element_count,
            "matched_rules": matched_rules,
            "warnings": applicable_warnings,
            "additional_services": data["additional_services"],
            "requires_project": (selected_tier.get("classification_rules") or {}).get("requires_project", False),
            "element_validation": element_validation,
        }

    async def validate_elements_in_tier(
        self,
        tier_id: str,
        element_codes: list[str],
        category_id: str,
    ) -> dict[str, Any]:
        """
        Validate that elements are included in the selected tier.

        This method checks TierElementInclusion to verify that the requested
        elements are actually covered by the selected tier. This prevents
        calculating a price for elements not included in the tier.

        Args:
            tier_id: UUID of the selected tier
            element_codes: List of element codes to validate
            category_id: UUID of the vehicle category

        Returns:
            Dict with:
            - valid: bool - True if all elements are in tier or tier has no restrictions
            - missing_elements: list[str] - Elements not included in the tier
            - tier_elements: list[str] - All element codes included in the tier
            - quantity_conflicts: list[dict] - Elements exceeding max_quantity
        """
        result: dict[str, Any] = {
            "valid": True,
            "missing_elements": [],
            "tier_elements": [],
            "quantity_conflicts": [],
        }

        try:
            # Get all elements included in this tier (using resolve_tier_elements)
            tier_elements = await self.resolve_tier_elements(tier_id)

            if not tier_elements:
                # If tier has no element inclusions defined, treat as "all elements allowed"
                logger.debug(
                    f"[validate_elements_in_tier] Tier has no element restrictions",
                    extra={"tier_id": tier_id}
                )
                return result

            # Build lookup for tier elements
            tier_element_codes = {elem["code"].upper() for elem in tier_elements}
            tier_element_by_code = {elem["code"].upper(): elem for elem in tier_elements}
            result["tier_elements"] = list(tier_element_codes)

            # Check each requested element
            for code in element_codes:
                code_upper = code.upper()
                if code_upper not in tier_element_codes:
                    result["missing_elements"].append(code_upper)
                    result["valid"] = False

            if result["missing_elements"]:
                logger.info(
                    f"[validate_elements_in_tier] Elements not in tier",
                    extra={
                        "tier_id": tier_id,
                        "missing_elements": result["missing_elements"],
                        "tier_elements": result["tier_elements"],
                    }
                )

        except Exception as e:
            logger.warning(
                f"[validate_elements_in_tier] Error validating elements: {e}",
                extra={"tier_id": tier_id, "element_codes": element_codes}
            )
            # On error, don't block - return valid=True with empty data
            result["valid"] = True

        return result

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
        selected_tier_id: str | None = None,
    ) -> list[dict]:
        """
        Find warnings that should be shown based on trigger_conditions and scope.

        Warning scoping:
        - Global warnings (no scope): Apply based on trigger_conditions only
        - Category-scoped: Already filtered in query, apply based on trigger_conditions
        - Tier-scoped: Only apply if selected_tier_id matches
        - Element-scoped: Apply based on element matching (future)

        Args:
            warnings: List of warning dicts with trigger_conditions and scope fields
            description_lower: Lowercased element description
            selected_tier_id: ID of the selected tier (to filter tier-scoped warnings)

        Returns:
            List of applicable warnings
        """
        applicable = []
        seen_codes = set()  # Avoid duplicates

        for warning in warnings:
            code = warning["code"]
            if code in seen_codes:
                continue

            # Check tier scope - if warning has tier_id, only apply if it matches selected tier
            warning_tier_id = warning.get("tier_id")
            if warning_tier_id and warning_tier_id != selected_tier_id:
                continue

            conditions = warning.get("trigger_conditions")

            # Scoped warnings (category or tier) without conditions: always show
            is_scoped = warning.get("category_id") or warning.get("tier_id") or warning.get("element_id")
            if is_scoped and not conditions:
                applicable.append({
                    "code": code,
                    "message": warning["message"],
                    "severity": warning["severity"],
                    "scope": "category" if warning.get("category_id") else "tier" if warning.get("tier_id") else "element",
                })
                seen_codes.add(code)
                continue

            # If no conditions for global warning, skip (explicit trigger required)
            if not conditions:
                continue

            # Check "always_show"
            if conditions.get("always_show"):
                applicable.append({
                    "code": code,
                    "message": warning["message"],
                    "severity": warning["severity"],
                })
                seen_codes.add(code)
                continue

            # Check "element_keywords"
            keywords = conditions.get("element_keywords", [])
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    applicable.append({
                        "code": code,
                        "message": warning["message"],
                        "severity": warning["severity"],
                        "triggered_by": keyword,
                    })
                    seen_codes.add(code)
                    break

        return applicable

    async def get_warnings_by_scope(
        self,
        category_id: str | None = None,
        tier_id: str | None = None,
        element_id: str | None = None,
        include_global: bool = True,
    ) -> list[dict]:
        """
        Get warnings filtered by scope.

        This method retrieves warnings that match any of the provided scope filters.
        Used to get tier-specific or element-specific warnings.

        Args:
            category_id: Filter by category ID
            tier_id: Filter by tier ID
            element_id: Filter by element ID
            include_global: Whether to include global (unscoped) warnings

        Returns:
            List of warning dicts
        """
        async with get_async_session() as session:
            # Build OR conditions for scope filtering
            conditions = [Warning.is_active == True]
            scope_conditions = []

            if include_global:
                # Global warnings: all scope fields are NULL
                scope_conditions.append(
                    (Warning.category_id == None) & (Warning.tier_id == None) & (Warning.element_id == None)
                )

            if category_id:
                scope_conditions.append(Warning.category_id == PyUUID(category_id))

            if tier_id:
                scope_conditions.append(Warning.tier_id == PyUUID(tier_id))

            if element_id:
                scope_conditions.append(Warning.element_id == PyUUID(element_id))

            if scope_conditions:
                conditions.append(or_(*scope_conditions))

            result = await session.execute(
                select(Warning).where(*conditions)
            )
            warnings = result.scalars().all()

            return [
                {
                    "id": str(w.id),
                    "code": w.code,
                    "message": w.message,
                    "severity": w.severity,
                    "trigger_conditions": w.trigger_conditions,
                    "category_id": str(w.category_id) if w.category_id else None,
                    "tier_id": str(w.tier_id) if w.tier_id else None,
                    "element_id": str(w.element_id) if w.element_id else None,
                }
                for w in warnings
            ]

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

    async def resolve_tier_elements(
        self,
        tier_id: str,
        visited_tiers: set[str] | None = None,
    ) -> list[dict]:
        """
        Resolve all elements that a tier includes (recursively).

        This method resolves TierElementInclusion records, following
        included_tier_id references to build a complete list of elements.

        Uses Redis caching with longer TTL since tier structure rarely changes.

        Args:
            tier_id: The tier UUID as string
            visited_tiers: Set of already visited tier IDs (to prevent cycles)

        Returns:
            List of element dicts with code, name, max_quantity, notes
        """
        # Only check cache for top-level calls (not recursive calls)
        is_top_level = visited_tiers is None
        cache_key = f"tier:elements:{tier_id}"

        if is_top_level:
            # Try cache first
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    logger.debug(f"Tier elements cache hit for: {tier_id}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Tier elements cache read failed for {cache_key}: {e}")

        if visited_tiers is None:
            visited_tiers = set()

        # Prevent infinite recursion
        if tier_id in visited_tiers:
            return []
        visited_tiers.add(tier_id)

        elements = []
        seen_element_ids = set()

        async with get_async_session() as session:
            # Get all inclusions for this tier
            result = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == PyUUID(tier_id))
                .options(
                    selectinload(TierElementInclusion.element),
                    selectinload(TierElementInclusion.included_tier),
                )
            )
            inclusions = result.scalars().all()

            for inc in inclusions:
                # If inclusion references an element directly
                if inc.element_id and inc.element:
                    if inc.element_id not in seen_element_ids:
                        seen_element_ids.add(inc.element_id)
                        elements.append({
                            "id": str(inc.element.id),
                            "code": inc.element.code,
                            "name": inc.element.name,
                            "description": inc.element.description,
                            "min_quantity": inc.min_quantity,
                            "max_quantity": inc.max_quantity,
                            "notes": inc.notes,
                            "source_tier": tier_id,
                        })

                # If inclusion references another tier (recursive)
                elif inc.included_tier_id:
                    nested_elements = await self.resolve_tier_elements(
                        str(inc.included_tier_id),
                        visited_tiers.copy(),
                    )
                    for elem in nested_elements:
                        elem_id = elem.get("id")
                        if elem_id and elem_id not in seen_element_ids:
                            seen_element_ids.add(PyUUID(elem_id))
                            # Update notes to indicate inherited
                            elem["notes"] = f"Heredado de {inc.included_tier.code if inc.included_tier else 'tier'}: {elem.get('notes', '')}"
                            elements.append(elem)

        # Cache result for top-level calls (tier structure rarely changes, use longer TTL)
        if is_top_level and elements:
            try:
                # Use 2x normal TTL since tier structure is more stable
                await self.redis.setex(cache_key, CACHE_TTL * 2, json.dumps(elements, cls=DecimalEncoder))
                logger.debug(f"Tier elements cached for: {tier_id}")
            except Exception as e:
                logger.warning(f"Tier elements cache write failed for {cache_key}: {e}")

        return elements

    async def invalidate_cache(self, category_slug: str | None = None) -> None:
        """
        Invalidate cached tariff data.

        Args:
            category_slug: Specific category to invalidate, or None for all
        """
        try:
            if category_slug:
                # Invalidate specific category
                await self.redis.delete(f"tariffs:{category_slug}")
                logger.info(f"Invalidated tariff cache for category: {category_slug}")

            # ALWAYS invalidate supported categories cache when any tariff changes
            await self.redis.delete("tariffs:supported:particular")
            await self.redis.delete("tariffs:supported:professional")
            await self.redis.delete("tariffs:categories:all")
            await self.redis.delete("tariffs:categories:particular")
            await self.redis.delete("tariffs:categories:professional")

            if category_slug is None:
                # Invalidate all tariff caches
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
