"""
MSI Automotive - Element System API routes.

Provides CRUD endpoints for managing homologable elements and their inclusions
in the hierarchical tariff system.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, aliased

from api.models.element import (
    ElementCreate,
    ElementUpdate,
    ElementResponse,
    ElementWithImagesResponse,
    ElementImageCreate,
    ElementImageResponse,
    TierElementInclusionCreate,
    TierElementInclusionUpdate,
    TierElementInclusionResponse,
    TierElementsPreview,
    BatchTierInclusionCreate,
    ElementWarningAssociationCreate,
    ElementWarningAssociationResponse,
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
    ElementWarningAssociation,
    Warning,
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
    limit: int = Query(50, ge=1, le=1000),
    is_active: bool | None = Query(None),
    include_children: bool = Query(
        False,
        description="If true, includes all elements. If false (default), only returns base elements (parent_element_id=NULL)",
    ),
    only_base: bool = Query(
        True,
        description="If true (default), only returns base elements. Set to false to get all elements flat.",
    ),
    _: AdminUser = Depends(get_current_user),
):
    """List elements for a category.

    By default, returns only base elements (those without parent_element_id).
    Use include_children=true to load children relationships for hierarchical display.
    Use only_base=false to get a flat list of all elements including variants.
    """
    async with get_async_session() as session:
        try:
            query = select(Element).where(Element.category_id == category_id)

            if is_active is not None:
                query = query.where(Element.is_active == is_active)

            # Filter for base elements only (no parent) unless include_children or not only_base
            if only_base and not include_children:
                query = query.where(Element.parent_element_id.is_(None))

            # Load children if requested
            if include_children:
                query = query.options(selectinload(Element.children))
                # Only get top-level elements when including children
                query = query.where(Element.parent_element_id.is_(None))

            # Get total count with same filters
            count_query = select(Element).where(Element.category_id == category_id)
            if is_active is not None:
                count_query = count_query.where(Element.is_active == is_active)
            if only_base or include_children:
                count_query = count_query.where(Element.parent_element_id.is_(None))
            count_result = await session.execute(count_query)
            total = len(count_result.scalars().all())

            # Get paginated results
            query = query.order_by(Element.sort_order, Element.name).offset(skip).limit(limit)
            result = await session.execute(query)
            elements = result.unique().scalars().all()

            # Get counts for each element efficiently (3 queries instead of 3N)
            element_ids = [e.id for e in elements]

            # Image counts
            image_counts = {}
            if element_ids:
                image_counts_query = (
                    select(ElementImage.element_id, func.count(ElementImage.id).label("count"))
                    .where(ElementImage.element_id.in_(element_ids))
                    .group_by(ElementImage.element_id)
                )
                image_counts_result = await session.execute(image_counts_query)
                image_counts = {row.element_id: row.count for row in image_counts_result}

            # Warning counts
            warning_counts = {}
            if element_ids:
                warning_counts_query = (
                    select(ElementWarningAssociation.element_id, func.count(ElementWarningAssociation.id).label("count"))
                    .where(ElementWarningAssociation.element_id.in_(element_ids))
                    .group_by(ElementWarningAssociation.element_id)
                )
                warning_counts_result = await session.execute(warning_counts_query)
                warning_counts = {row.element_id: row.count for row in warning_counts_result}

            # Child counts
            child_counts = {}
            if element_ids:
                child_counts_query = (
                    select(Element.parent_element_id, func.count(Element.id).label("count"))
                    .where(Element.parent_element_id.in_(element_ids))
                    .group_by(Element.parent_element_id)
                )
                child_counts_result = await session.execute(child_counts_query)
                child_counts = {row.parent_element_id: row.count for row in child_counts_result}

            # Build response items with counts
            def build_element_response(element):
                data = {
                    "id": element.id,
                    "category_id": element.category_id,
                    "code": element.code,
                    "name": element.name,
                    "description": element.description,
                    "keywords": element.keywords,
                    "aliases": element.aliases,
                    "is_active": element.is_active,
                    "sort_order": element.sort_order,
                    "parent_element_id": element.parent_element_id,
                    "variant_type": element.variant_type,
                    "variant_code": element.variant_code,
                    "created_at": element.created_at,
                    "updated_at": element.updated_at,
                    "image_count": image_counts.get(element.id, 0),
                    "warning_count": warning_counts.get(element.id, 0),
                    "child_count": child_counts.get(element.id, 0),
                }
                return data

            if include_children:
                from api.models.element import ElementWithChildrenResponse
                items = []
                for e in elements:
                    data = build_element_response(e)
                    data["children"] = [ElementResponse.model_validate(child) for child in e.children]
                    items.append(ElementWithChildrenResponse.model_validate(data))
                return {
                    "items": items,
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                }
            else:
                return {
                    "items": [ElementResponse.model_validate(build_element_response(e)) for e in elements],
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
):
    """Create a new homologable element."""
    async with get_async_session() as session:
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
            await session.commit()
            await session.refresh(element)

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
    response_model=dict,
    summary="Get element details with images and hierarchy",
)
async def get_element(
    element_id: UUID,
    include_children: bool = Query(
        True,
        description="If true (default), includes children elements",
    ),
    _: AdminUser = Depends(get_current_user),
):
    """Get element details with all associated images, parent and children."""
    async with get_async_session() as session:
        try:
            query = (
                select(Element)
                .where(Element.id == element_id)
                .options(selectinload(Element.images))
                .options(selectinload(Element.parent))
            )

            if include_children:
                query = query.options(
                    selectinload(Element.children).selectinload(Element.images)
                )

            result = await session.execute(query)
            element = result.unique().scalar_one_or_none()

            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

            # Build response with hierarchy info
            response = ElementWithImagesResponse.model_validate(element).model_dump()

            # Add parent info if exists
            if element.parent:
                response["parent"] = {
                    "id": str(element.parent.id),
                    "code": element.parent.code,
                    "name": element.parent.name,
                }

            # Add children if requested
            if include_children and element.children:
                from api.models.element import ElementWithImagesResponse as ElemImgResp
                response["children"] = [
                    ElemImgResp.model_validate(child).model_dump()
                    for child in sorted(element.children, key=lambda x: x.sort_order)
                ]
            else:
                response["children"] = []

            return response
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
):
    """Update an element's properties."""
    async with get_async_session() as session:
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

            await session.commit()
            await session.refresh(element)

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
):
    """Delete an element (soft delete via is_active flag)."""
    async with get_async_session() as session:
        try:
            element = await session.get(Element, element_id)
            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

            element.is_active = False
            await session.commit()

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
):
    """Create a new image for an element."""
    async with get_async_session() as session:
        try:
            element = await session.get(Element, element_id)
            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

            image = ElementImage(element_id=element_id, **data.model_dump())
            session.add(image)
            await session.commit()
            await session.refresh(image)

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
):
    """Get all images for an element."""
    async with get_async_session() as session:
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
):
    """Delete an element image."""
    async with get_async_session() as session:
        try:
            image = await session.get(ElementImage, image_id)
            if not image:
                raise HTTPException(status_code=404, detail="Image not found")

            element_id = image.element_id
            await session.delete(image)
            await session.commit()

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
):
    """Create a new tier element inclusion."""
    async with get_async_session() as session:
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
            await session.commit()
            await session.refresh(inclusion)

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


@router.get(
    "/tariff-tiers/{tier_id}/inclusions",
    response_model=list[TierElementInclusionResponse],
    summary="List inclusions for a tier",
)
async def list_tier_inclusions(
    tier_id: UUID,
    _: AdminUser = Depends(get_current_user),
):
    """List all element/tier inclusions for a tariff tier."""
    async with get_async_session() as session:
        try:
            # Verify tier exists
            tier = await session.get(TariffTier, tier_id)
            if not tier:
                raise HTTPException(status_code=404, detail="Tariff tier not found")

            result = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier_id)
                .order_by(TierElementInclusion.created_at)
            )
            inclusions = result.scalars().all()

            return [TierElementInclusionResponse.model_validate(inc) for inc in inclusions]
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing inclusions: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/tariff-tiers/{tier_id}/inclusions/{inclusion_id}",
    response_model=TierElementInclusionResponse,
    summary="Update a tier inclusion",
)
async def update_tier_inclusion(
    tier_id: UUID,
    inclusion_id: UUID,
    data: TierElementInclusionUpdate,
    _: AdminUser = Depends(get_current_user),
):
    """Update an existing tier element inclusion."""
    async with get_async_session() as session:
        try:
            inclusion = await session.get(TierElementInclusion, inclusion_id)
            if not inclusion:
                raise HTTPException(status_code=404, detail="Inclusion not found")

            if inclusion.tier_id != tier_id:
                raise HTTPException(status_code=400, detail="Inclusion does not belong to this tier")

            # Update fields
            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(inclusion, field, value)

            await session.commit()
            await session.refresh(inclusion)

            # Invalidate cache
            redis = get_redis_client()
            try:
                await redis.delete(f"tier_elements:{tier_id}")
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {e}")

            return TierElementInclusionResponse.model_validate(inclusion)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating inclusion: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/tariff-tiers/{tier_id}/inclusions/{inclusion_id}",
    status_code=204,
    summary="Delete a tier inclusion",
)
async def delete_tier_inclusion(
    tier_id: UUID,
    inclusion_id: UUID,
    _: AdminUser = Depends(get_current_user),
):
    """Delete a tier element inclusion."""
    async with get_async_session() as session:
        try:
            inclusion = await session.get(TierElementInclusion, inclusion_id)
            if not inclusion:
                raise HTTPException(status_code=404, detail="Inclusion not found")

            if inclusion.tier_id != tier_id:
                raise HTTPException(status_code=400, detail="Inclusion does not belong to this tier")

            await session.delete(inclusion)
            await session.commit()

            # Invalidate cache
            redis = get_redis_client()
            try:
                await redis.delete(f"tier_elements:{tier_id}")
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {e}")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting inclusion: {e}")
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
):
    """Create multiple tier inclusions in a single request."""
    async with get_async_session() as session:
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

            await session.commit()
            for inc in created:
                await session.refresh(inc)

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
):
    """Get preview of elements resolved for a tier."""
    async with get_async_session() as session:
        try:
            # Get tier
            tier = await session.get(TariffTier, tier_id)
            if not tier:
                raise HTTPException(status_code=404, detail="Tariff tier not found")

            # Resolve elements
            tarifa_service = get_tarifa_service()
            tier_elements = await tarifa_service.resolve_tier_elements(str(tier_id))

            # Transform list[dict] to dict[str, int|None] for schema
            elements_dict = {
                elem["id"]: elem.get("max_quantity")
                for elem in tier_elements
            }

            return TierElementsPreview(
                tier_id=tier_id,
                tier_code=tier.code,
                tier_name=tier.name,
                total_elements=len(tier_elements),
                elements=elements_dict,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resolving tier elements: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Element Warning Association Endpoints
# =============================================================================


@router.get(
    "/elements/{element_id}/warnings",
    response_model=list[ElementWarningAssociationResponse],
    summary="List warnings associated with an element",
)
async def list_element_warnings(
    element_id: UUID,
    _: AdminUser = Depends(get_current_user),
):
    """Get all warnings associated with a specific element."""
    async with get_async_session() as session:
        try:
            element = await session.get(Element, element_id)
            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.element_id == element_id)
                .order_by(ElementWarningAssociation.created_at)
            )
            associations = result.scalars().all()

            return [ElementWarningAssociationResponse.model_validate(a) for a in associations]
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing element warnings: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/elements/{element_id}/warnings",
    response_model=ElementWarningAssociationResponse,
    status_code=201,
    summary="Associate a warning with an element",
)
async def create_element_warning_association(
    element_id: UUID,
    data: ElementWarningAssociationCreate,
    _: AdminUser = Depends(get_current_user),
):
    """Create a new association between an element and a warning."""
    async with get_async_session() as session:
        try:
            # Verify element exists
            element = await session.get(Element, element_id)
            if not element:
                raise HTTPException(status_code=404, detail="Element not found")

            # Verify warning exists
            warning = await session.get(Warning, data.warning_id)
            if not warning:
                raise HTTPException(status_code=404, detail="Warning not found")

            # Check if association already exists
            existing = await session.execute(
                select(ElementWarningAssociation).where(
                    ElementWarningAssociation.element_id == element_id,
                    ElementWarningAssociation.warning_id == data.warning_id,
                )
            )
            if existing.scalar():
                raise HTTPException(
                    status_code=409,
                    detail="This warning is already associated with this element",
                )

            association = ElementWarningAssociation(
                element_id=element_id,
                warning_id=data.warning_id,
                show_condition=data.show_condition,
                threshold_quantity=data.threshold_quantity,
            )
            session.add(association)
            await session.commit()
            await session.refresh(association)

            logger.info(f"Created element-warning association: element={element_id}, warning={data.warning_id}")
            return ElementWarningAssociationResponse.model_validate(association)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating element-warning association: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/elements/{element_id}/warnings/{warning_id}",
    status_code=204,
    summary="Remove a warning association from an element",
)
async def delete_element_warning_association(
    element_id: UUID,
    warning_id: UUID,
    _: AdminUser = Depends(get_current_user),
):
    """Delete an association between an element and a warning."""
    async with get_async_session() as session:
        try:
            result = await session.execute(
                select(ElementWarningAssociation).where(
                    ElementWarningAssociation.element_id == element_id,
                    ElementWarningAssociation.warning_id == warning_id,
                )
            )
            association = result.scalar_one_or_none()

            if not association:
                raise HTTPException(
                    status_code=404,
                    detail="Association not found",
                )

            await session.delete(association)
            await session.commit()

            logger.info(f"Deleted element-warning association: element={element_id}, warning={warning_id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting element-warning association: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/warnings/{warning_id}/elements",
    response_model=list[ElementWarningAssociationResponse],
    summary="List elements associated with a warning",
)
async def list_warning_elements(
    warning_id: UUID,
    _: AdminUser = Depends(get_current_user),
):
    """Get all elements associated with a specific warning."""
    async with get_async_session() as session:
        try:
            warning = await session.get(Warning, warning_id)
            if not warning:
                raise HTTPException(status_code=404, detail="Warning not found")

            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.warning_id == warning_id)
                .order_by(ElementWarningAssociation.created_at)
            )
            associations = result.scalars().all()

            return [ElementWarningAssociationResponse.model_validate(a) for a in associations]
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing warning elements: {e}")
            raise HTTPException(status_code=500, detail=str(e))