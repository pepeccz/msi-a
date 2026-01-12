"""
MSI Automotive - Element System API routes.

Provides CRUD endpoints for managing homologable elements and their inclusions
in the hierarchical tariff system.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.models.element import (
    ElementCreate,
    ElementUpdate,
    ElementResponse,
    ElementWithImagesResponse,
    ElementImageCreate,
    ElementImageResponse,
    TierElementInclusionCreate,
    TierElementInclusionResponse,
    TierElementsPreview,
    BatchTierInclusionCreate,
    ErrorResponse,
)
from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import (
    AdminUser,
    VehicleCategory,
    Element,
    ElementImage,
    TierElementInclusion,
    TariffTier,
)
from agent.services.element_service import get_element_service
from agent.services.tarifa_service import get_tarifa_service
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Elements"])


# =============================================================================
# Element CRUD Endpoints
# =============================================================================


@router.get(
    "/elements",
    response_model=dict,
    summary="List all elements for a category",
    description="Get all active elements for a specific vehicle category with optional pagination",
)
async def list_elements(
    category_id: UUID = Query(..., description="Vehicle category ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: bool | None = Query(None),
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """List elements for a category."""
    try:
        query = select(Element).where(Element.category_id == category_id)

        if is_active is not None:
            query = query.where(Element.is_active == is_active)

        # Get total count
        count_result = await session.execute(
            select(Element)
            .where(Element.category_id == category_id)
            if is_active is None
            else select(Element).where(Element.category_id == category_id, Element.is_active == is_active)
        )
        total = len(count_result.scalars().all())

        # Get paginated results
        query = query.order_by(Element.sort_order, Element.name).offset(skip).limit(limit)
        result = await session.execute(query)
        elements = result.scalars().all()

        return {
            "items": [ElementResponse.model_validate(e) for e in elements],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"Error listing elements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/elements",
    response_model=ElementResponse,
    status_code=201,
    summary="Create a new element",
)
async def create_element(
    data: ElementCreate,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Create a new homologable element."""
    try:
        # Check category exists
        category = await session.get(VehicleCategory, data.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check code uniqueness in category
        existing = await session.execute(
            select(Element).where(
                Element.category_id == data.category_id,
                Element.code == data.code,
            )
        )
        if existing.scalar():
            raise HTTPException(
                status_code=409,
                detail=f"Element with code '{data.code}' already exists in this category",
            )

        element = Element(**data.model_dump())
        session.add(element)
        await session.flush()

        # Invalidate cache
        redis = get_redis_client()
        try:
            await redis.delete(f"elements:category:{data.category_id}:active=True")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

        return ElementResponse.model_validate(element)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating element: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/elements/{element_id}",
    response_model=ElementWithImagesResponse,
    summary="Get element details with images",
)
async def get_element(
    element_id: UUID,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Get element details with all associated images."""
    try:
        result = await session.execute(
            select(Element)
            .where(Element.id == element_id)
            .options(selectinload(Element.images))
        )
        element = result.unique().scalar_one_or_none()

        if not element:
            raise HTTPException(status_code=404, detail="Element not found")

        return ElementWithImagesResponse.model_validate(element)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting element: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/elements/{element_id}",
    response_model=ElementResponse,
    summary="Update an element",
)
async def update_element(
    element_id: UUID,
    data: ElementUpdate,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Update an element's properties."""
    try:
        element = await session.get(Element, element_id)
        if not element:
            raise HTTPException(status_code=404, detail="Element not found")

        # Check code uniqueness if code is being updated
        if data.code and data.code != element.code:
            existing = await session.execute(
                select(Element).where(
                    Element.category_id == element.category_id,
                    Element.code == data.code,
                )
            )
            if existing.scalar():
                raise HTTPException(
                    status_code=409,
                    detail=f"Element with code '{data.code}' already exists in this category",
                )

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(element, field, value)

        # Invalidate cache
        redis = get_redis_client()
        try:
            await redis.delete(f"elements:category:{element.category_id}:active=True")
            await redis.delete(f"element:details:{element_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

        return ElementResponse.model_validate(element)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating element: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/elements/{element_id}", status_code=204, summary="Delete an element")
async def delete_element(
    element_id: UUID,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Delete an element (soft delete via is_active flag)."""
    try:
        element = await session.get(Element, element_id)
        if not element:
            raise HTTPException(status_code=404, detail="Element not found")

        element.is_active = False

        # Invalidate cache
        redis = get_redis_client()
        try:
            await redis.delete(f"elements:category:{element.category_id}:active=True")
            await redis.delete(f"element:details:{element_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting element: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ElementImage CRUD Endpoints
# =============================================================================


@router.post(
    "/elements/{element_id}/images",
    response_model=ElementImageResponse,
    status_code=201,
    summary="Upload image for an element",
)
async def create_element_image(
    element_id: UUID,
    data: ElementImageCreate,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Create a new image for an element."""
    try:
        element = await session.get(Element, element_id)
        if not element:
            raise HTTPException(status_code=404, detail="Element not found")

        image = ElementImage(element_id=element_id, **data.model_dump())
        session.add(image)
        await session.flush()

        # Invalidate cache
        redis = get_redis_client()
        try:
            await redis.delete(f"element:details:{element_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

        return ElementImageResponse.model_validate(image)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/elements/{element_id}/images",
    response_model=dict,
    summary="List images for an element",
)
async def list_element_images(
    element_id: UUID,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Get all images for an element."""
    try:
        element = await session.get(Element, element_id)
        if not element:
            raise HTTPException(status_code=404, detail="Element not found")

        result = await session.execute(
            select(ElementImage)
            .where(ElementImage.element_id == element_id)
            .order_by(ElementImage.sort_order)
        )
        images = result.scalars().all()

        return {
            "element_id": str(element_id),
            "images": [ElementImageResponse.model_validate(img) for img in images],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing images: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/element-images/{image_id}", status_code=204, summary="Delete an image")
async def delete_element_image(
    image_id: UUID,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Delete an element image."""
    try:
        image = await session.get(ElementImage, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        element_id = image.element_id
        await session.delete(image)

        # Invalidate cache
        redis = get_redis_client()
        try:
            await redis.delete(f"element:details:{element_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Tier Element Inclusion Endpoints
# =============================================================================


@router.post(
    "/tariff-tiers/{tier_id}/inclusions",
    response_model=TierElementInclusionResponse,
    status_code=201,
    summary="Add element/tier inclusion to a tariff",
)
async def create_tier_inclusion(
    tier_id: UUID,
    data: TierElementInclusionCreate,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Create a new tier element inclusion."""
    try:
        # Verify tier exists
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tariff tier not found")

        # Validate XOR constraint
        if data.element_id and data.included_tier_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot set both element_id and included_tier_id",
            )
        if not data.element_id and not data.included_tier_id:
            raise HTTPException(
                status_code=400,
                detail="Must set either element_id or included_tier_id",
            )

        # If element_id, verify element exists
        if data.element_id:
            element = await session.get(Element, data.element_id)
            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

        # If included_tier_id, verify tier exists
        if data.included_tier_id:
            included_tier = await session.get(TariffTier, data.included_tier_id)
            if not included_tier:
                raise HTTPException(status_code=404, detail="Included tier not found")

        inclusion = TierElementInclusion(tier_id=tier_id, **data.model_dump())
        session.add(inclusion)
        await session.flush()

        # Invalidate tier cache
        redis = get_redis_client()
        try:
            await redis.delete(f"tier_elements:{tier_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

        return TierElementInclusionResponse.model_validate(inclusion)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating inclusion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tariff-tiers/{tier_id}/inclusions/batch",
    response_model=dict,
    status_code=201,
    summary="Batch create tier inclusions",
)
async def batch_create_tier_inclusions(
    tier_id: UUID,
    data: BatchTierInclusionCreate,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Create multiple tier inclusions in a single request."""
    try:
        # Verify tier exists
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tariff tier not found")

        created = []

        for inc_data in data.inclusions:
            # Validate XOR
            if inc_data.element_id and inc_data.included_tier_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot set both element_id and included_tier_id in one inclusion",
                )
            if not inc_data.element_id and not inc_data.included_tier_id:
                raise HTTPException(
                    status_code=400,
                    detail="Must set either element_id or included_tier_id in one inclusion",
                )

            # Verify referenced resources exist
            if inc_data.element_id:
                element = await session.get(Element, inc_data.element_id)
                if not element:
                    raise HTTPException(status_code=404, detail=f"Element not found")

            if inc_data.included_tier_id:
                included_tier = await session.get(TariffTier, inc_data.included_tier_id)
                if not included_tier:
                    raise HTTPException(status_code=404, detail="Included tier not found")

            inclusion = TierElementInclusion(tier_id=tier_id, **inc_data.model_dump())
            session.add(inclusion)
            created.append(inclusion)

        await session.flush()

        # Invalidate tier cache
        redis = get_redis_client()
        try:
            await redis.delete(f"tier_elements:{tier_id}")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

        return {
            "tier_id": str(tier_id),
            "created_count": len(created),
            "inclusions": [TierElementInclusionResponse.model_validate(inc) for inc in created],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch creating inclusions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Tier Resolution Preview Endpoint
# =============================================================================


@router.get(
    "/tariff-tiers/{tier_id}/resolved-elements",
    response_model=TierElementsPreview,
    summary="Preview resolved elements for a tier",
    description="Get all elements that a tier includes (resolving recursive references)",
)
async def get_tier_resolved_elements(
    tier_id: UUID,
    _: AdminUser = Depends(get_current_user),
    session=Depends(get_async_session),
):
    """Get preview of elements resolved for a tier."""
    try:
        # Get tier
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tariff tier not found")

        # Resolve elements
        tarifa_service = get_tarifa_service()
        tier_elements = await tarifa_service.resolve_tier_elements(str(tier_id))

        return TierElementsPreview(
            tier_id=tier_id,
            tier_code=tier.code,
            tier_name=tier.name,
            total_elements=len(tier_elements),
            elements=tier_elements,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving tier elements: {e}")
        raise HTTPException(status_code=500, detail=str(e))
