"""
MSI Automotive - Public Tariff API routes.

Provides public endpoints for the LangGraph agent to query tariff data.
These endpoints are cached in Redis for performance.

Note: HomologationElement has been removed in favor of AI-driven
classification using classification_rules in TariffTier.
"""

import json
import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.models.tariff_schemas import (
    CategoryFullDataResponse,
    TariffSelectionRequest,
    TariffSelectionResponse,
    DocumentationResponse,
    VehicleCategoryResponse,
    TariffTierResponse,
    BaseDocumentationResponse,
    AdditionalServiceResponse,
    WarningResponse,
)
from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    AdditionalService,
    Warning,
)
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tariffs")

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300


# =============================================================================
# Helper Functions
# =============================================================================


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


async def get_cached_category_data(category_slug: str, client_type: str = "all") -> dict | None:
    """Get category data from Redis cache."""
    try:
        redis = get_redis_client()
        cached = await redis.get(f"tariffs:{category_slug}:{client_type}")
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Cache read failed: {e}")
    return None


async def set_cached_category_data(category_slug: str, data: dict, client_type: str = "all") -> None:
    """Store category data in Redis cache."""
    try:
        redis = get_redis_client()
        await redis.setex(
            f"tariffs:{category_slug}:{client_type}",
            CACHE_TTL,
            json.dumps(data, cls=DecimalEncoder),
        )
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")


async def fetch_category_from_db(category_slug: str, client_type: str = "all") -> dict:
    """
    Fetch complete category data from database.

    Args:
        category_slug: Category slug (e.g., "motos")
        client_type: Filter tiers by client type ("particular", "professional", "all")

    Returns:
        Dict with category, tiers, warnings, documentation, and services
    """
    async with get_async_session() as session:
        # Get category with all relations
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
            raise HTTPException(status_code=404, detail="Category not found")

        # Get all active warnings
        warnings_result = await session.execute(
            select(Warning)
            .where(Warning.is_active == True)
        )
        all_warnings = warnings_result.scalars().all()

        # Filter tiers by client_type
        filtered_tiers = [
            t for t in category.tariff_tiers
            if t.is_active and (
                client_type == "all" or
                t.client_type == "all" or
                t.client_type == client_type
            )
        ]

        # Build response data
        data = {
            "category": {
                "id": str(category.id),
                "slug": category.slug,
                "name": category.name,
                "description": category.description,
                "icon": category.icon,
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
                    "sort_order": t.sort_order,
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
                for w in all_warnings
            ],
            "base_documentation": [
                {
                    "id": str(bd.id),
                    "description": bd.description,
                    "image_url": bd.image_url,
                    "sort_order": bd.sort_order,
                }
                for bd in sorted(category.base_documentation, key=lambda x: x.sort_order)
            ],
            "additional_services": [
                {
                    "id": str(s.id),
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
        global_services = global_services_result.scalars().all()
        for s in global_services:
            data["additional_services"].append({
                "id": str(s.id),
                "code": s.code,
                "name": s.name,
                "description": s.description,
                "price": float(s.price),
            })

        return data


# =============================================================================
# Public Routes
# =============================================================================


@router.get("/categories")
async def list_categories() -> JSONResponse:
    """
    List all active vehicle categories.

    This endpoint is used by the agent to know which categories are available.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.is_active == True)
            .order_by(VehicleCategory.sort_order)
        )
        categories = result.scalars().all()

        return JSONResponse(
            content={
                "categories": [
                    {
                        "slug": c.slug,
                        "name": c.name,
                        "description": c.description,
                        "icon": c.icon,
                    }
                    for c in categories
                ]
            }
        )


@router.get("/{category_slug}")
async def get_category_data(
    category_slug: str,
    client_type: str = Query("all", description="Client type filter: particular, professional, or all"),
) -> JSONResponse:
    """
    Get complete data for a vehicle category.

    Returns all tiers (with classification_rules), warnings, documentation,
    and additional services. Data is cached in Redis for performance.

    The agent uses this data along with classification_rules to determine
    the appropriate tier based on the customer's description.
    """
    # Validate client_type
    if client_type not in ("particular", "professional", "all"):
        client_type = "all"

    # Try cache first
    cached = await get_cached_category_data(category_slug, client_type)
    if cached:
        logger.debug(f"Cache hit for category: {category_slug} ({client_type})")
        return JSONResponse(content=cached)

    # Fetch from database
    logger.debug(f"Cache miss for category: {category_slug} ({client_type})")
    data = await fetch_category_from_db(category_slug, client_type)

    # Store in cache
    await set_cached_category_data(category_slug, data, client_type)

    return JSONResponse(content=data)


@router.get("/{category_slug}/tiers")
async def get_category_tiers(
    category_slug: str,
    client_type: str = Query("all", description="Client type filter"),
) -> JSONResponse:
    """
    Get all tiers for a vehicle category with their classification rules.

    This endpoint provides the AI agent with the data needed to determine
    which tier applies based on the customer's description.
    """
    # Validate client_type
    if client_type not in ("particular", "professional", "all"):
        client_type = "all"

    # Get full category data (will use cache if available)
    cached = await get_cached_category_data(category_slug, client_type)
    if not cached:
        cached = await fetch_category_from_db(category_slug, client_type)
        await set_cached_category_data(category_slug, cached, client_type)

    return JSONResponse(
        content={
            "category": cached["category"]["name"],
            "client_type": client_type,
            "tiers": cached["tiers"],
        }
    )


@router.post("/{category_slug}/select-tier")
async def select_tier(
    category_slug: str,
    request: TariffSelectionRequest,
) -> JSONResponse:
    """
    Select the appropriate tier based on element description.

    This endpoint uses the classification_rules to help determine
    which tier best matches the customer's homologation needs.

    The AI agent provides a natural language description of the elements
    and the number of elements, and this endpoint returns matching tiers
    along with any applicable warnings.

    Args:
        category_slug: Vehicle category (e.g., "motos")
        request: Element description and count

    Returns:
        Matching tiers ranked by priority, warnings, and additional services
    """
    # Get category data
    cached = await get_cached_category_data(category_slug, request.client_type)
    if not cached:
        cached = await fetch_category_from_db(category_slug, request.client_type)
        await set_cached_category_data(category_slug, cached, request.client_type)

    description_lower = request.elements_description.lower()
    element_count = request.element_count

    # Match tiers based on classification_rules
    matched_tiers = []
    for tier in cached["tiers"]:
        rules = tier.get("classification_rules") or {}
        applies_if_any = rules.get("applies_if_any", [])
        priority = rules.get("priority", 999)
        requires_project = rules.get("requires_project", False)

        # Check keyword matches
        keyword_match = any(
            keyword.lower() in description_lower
            for keyword in applies_if_any
        ) if applies_if_any else False

        # Check element count constraints
        min_elements = tier.get("min_elements")
        max_elements = tier.get("max_elements")
        count_match = True
        if min_elements is not None and element_count < min_elements:
            count_match = False
        if max_elements is not None and element_count > max_elements:
            count_match = False

        # Add to matches if applicable
        if keyword_match or (count_match and not applies_if_any):
            matched_tiers.append({
                "tier_code": tier["code"],
                "tier_name": tier["name"],
                "price": tier["price"],
                "conditions": tier["conditions"],
                "priority": priority,
                "requires_project": requires_project,
                "match_type": "keyword" if keyword_match else "element_count",
            })

    # Sort by priority (lower = higher priority)
    matched_tiers.sort(key=lambda x: x["priority"])

    # If no matches, use element count heuristic
    if not matched_tiers:
        # Default tier selection based on element count
        for tier in cached["tiers"]:
            min_elements = tier.get("min_elements")
            max_elements = tier.get("max_elements")
            if min_elements is not None and max_elements is not None:
                if min_elements <= element_count <= max_elements:
                    matched_tiers.append({
                        "tier_code": tier["code"],
                        "tier_name": tier["name"],
                        "price": tier["price"],
                        "conditions": tier["conditions"],
                        "priority": 999,
                        "requires_project": False,
                        "match_type": "element_count_fallback",
                    })

    # Get best match
    best_match = matched_tiers[0] if matched_tiers else {
        "tier_code": "UNKNOWN",
        "tier_name": "Consultar",
        "price": 0,
        "conditions": "Requiere consulta personalizada",
        "priority": 999,
        "requires_project": False,
        "match_type": "no_match",
    }

    # Collect applicable warnings based on trigger_conditions
    applicable_warnings = []
    for warning in cached["warnings"]:
        trigger = warning.get("trigger_conditions") or {}
        always_show = trigger.get("always_show", False)
        element_keywords = trigger.get("element_keywords", [])

        should_show = always_show or any(
            kw.lower() in description_lower
            for kw in element_keywords
        )

        if should_show:
            applicable_warnings.append({
                "code": warning["code"],
                "message": warning["message"],
                "severity": warning["severity"],
            })

    return JSONResponse(
        content={
            "tier_code": best_match["tier_code"],
            "tier_name": best_match["tier_name"],
            "price": best_match["price"],
            "conditions": best_match["conditions"],
            "element_count": element_count,
            "matched_rules": matched_tiers,
            "warnings": applicable_warnings,
            "additional_services": cached["additional_services"],
            "requires_project": best_match["requires_project"],
        }
    )


@router.get("/{category_slug}/documentation")
async def get_documentation(category_slug: str) -> JSONResponse:
    """
    Get base documentation requirements for a category.

    Returns the standard documentation needed for any homologation
    in this vehicle category.
    """
    # Get category data
    cached = await get_cached_category_data(category_slug)
    if not cached:
        cached = await fetch_category_from_db(category_slug)
        await set_cached_category_data(category_slug, cached)

    # Collect image URLs
    all_images = [
        doc["image_url"]
        for doc in cached["base_documentation"]
        if doc.get("image_url")
    ]

    return JSONResponse(
        content={
            "category": cached["category"]["name"],
            "base_documentation": cached["base_documentation"],
            "all_images": list(set(all_images)),
        }
    )


@router.get("/{category_slug}/warnings")
async def get_warnings(
    category_slug: str,
    elements_description: str = Query(None, description="Description to match against trigger conditions"),
) -> JSONResponse:
    """
    Get warnings for a category, optionally filtered by element description.

    If elements_description is provided, only returns warnings whose
    trigger_conditions match the description.
    """
    # Get category data
    cached = await get_cached_category_data(category_slug)
    if not cached:
        cached = await fetch_category_from_db(category_slug)
        await set_cached_category_data(category_slug, cached)

    warnings = cached["warnings"]

    # Filter if description provided
    if elements_description:
        description_lower = elements_description.lower()
        filtered_warnings = []
        for warning in warnings:
            trigger = warning.get("trigger_conditions") or {}
            always_show = trigger.get("always_show", False)
            element_keywords = trigger.get("element_keywords", [])

            should_show = always_show or any(
                kw.lower() in description_lower
                for kw in element_keywords
            )

            if should_show:
                filtered_warnings.append(warning)
        warnings = filtered_warnings

    return JSONResponse(
        content={
            "category": cached["category"]["name"],
            "warnings": warnings,
        }
    )
