"""
MSI Automotive - Tariff Admin API routes.

Provides CRUD endpoints for managing vehicle categories, tariffs,
prompt sections, documentation, warnings, and additional services.

Note: HomologationElement has been removed in favor of AI-driven
classification using classification_rules in TariffTier.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from api.models.tariff_schemas import (
    # Vehicle Category
    VehicleCategoryCreate,
    VehicleCategoryUpdate,
    VehicleCategoryResponse,
    VehicleCategoryWithRelations,
    # Tariff Tier
    TariffTierCreate,
    TariffTierUpdate,
    TariffTierResponse,
    # Base Documentation
    BaseDocumentationCreate,
    BaseDocumentationUpdate,
    BaseDocumentationResponse,
    # Warning
    WarningCreate,
    WarningUpdate,
    WarningResponse,
    # Additional Service
    AdditionalServiceCreate,
    AdditionalServiceUpdate,
    AdditionalServiceResponse,
    # Tariff Prompt Section
    TariffPromptSectionCreate,
    TariffPromptSectionUpdate,
    TariffPromptSectionResponse,
    # Element Documentation
    ElementDocumentationCreate,
    ElementDocumentationUpdate,
    ElementDocumentationResponse,
    # Audit Log
    AuditLogResponse,
    # API Responses
    PromptPreviewResponse,
)
from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import (
    AdminUser,
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    Warning,
    AdditionalService,
    TariffPromptSection,
    AuditLog,
    ElementDocumentation,
)
from shared.redis_client import get_redis_client
from agent.services.prompt_service import get_prompt_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin")


# =============================================================================
# Audit Log Helper
# =============================================================================


async def create_audit_log(
    session,
    entity_type: str,
    entity_id: UUID,
    action: str,
    changes: dict[str, Any] | None,
    user: str | None,
) -> None:
    """Create an audit log entry."""
    audit = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes,
        user=user,
    )
    session.add(audit)


async def invalidate_tariff_cache(category_slug: str) -> None:
    """Invalidate Redis cache for a category."""
    try:
        redis = get_redis_client()
        # Invalidate both client types
        await redis.delete(f"tariffs:{category_slug}:particular")
        await redis.delete(f"tariffs:{category_slug}:professional")
        # Also invalidate prompt cache
        await redis.delete(f"prompt:calculator:{category_slug}:particular")
        await redis.delete(f"prompt:calculator:{category_slug}:professional")
        logger.info(f"Cache invalidated for category: {category_slug}")
    except Exception as e:
        logger.warning(f"Failed to invalidate cache: {e}")


# =============================================================================
# Vehicle Category Routes
# =============================================================================


@router.get("/vehicle-categories")
async def list_vehicle_categories(
    user: AdminUser = Depends(get_current_user),
    include_inactive: bool = Query(False, description="Include inactive categories"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all vehicle categories with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(VehicleCategory.id))
        if not include_inactive:
            count_query = count_query.where(VehicleCategory.is_active == True)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch items
        query = select(VehicleCategory).order_by(VehicleCategory.sort_order)
        if not include_inactive:
            query = query.where(VehicleCategory.is_active == True)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        categories = result.scalars().all()

        return {
            "items": [VehicleCategoryResponse.model_validate(c) for c in categories],
            "total": total,
            "has_more": offset + len(categories) < total,
        }


@router.post("/vehicle-categories", response_model=VehicleCategoryResponse, status_code=201)
async def create_vehicle_category(
    data: VehicleCategoryCreate,
    user: AdminUser = Depends(get_current_user),
) -> VehicleCategoryResponse:
    """Create a new vehicle category."""
    async with get_async_session() as session:
        # Check if slug already exists
        existing = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == data.slug)
        )
        if existing.scalar():
            raise HTTPException(status_code=400, detail="Slug already exists")

        category = VehicleCategory(**data.model_dump())
        session.add(category)

        # Audit log
        await create_audit_log(
            session,
            "vehicle_category",
            category.id,
            "create",
            data.model_dump(),
            user.username,
        )

        await session.commit()
        await session.refresh(category)

        logger.info(f"Created vehicle category: {category.slug}")
        return VehicleCategoryResponse.model_validate(category)


@router.get("/vehicle-categories/{category_id}", response_model=VehicleCategoryWithRelations)
async def get_vehicle_category(
    category_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> VehicleCategoryWithRelations:
    """Get a vehicle category by ID with all relations loaded."""
    async with get_async_session() as session:
        result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.id == category_id)
            .options(
                selectinload(VehicleCategory.tariff_tiers),
                selectinload(VehicleCategory.base_documentation),
                selectinload(VehicleCategory.additional_services),
                selectinload(VehicleCategory.prompt_sections),
                selectinload(VehicleCategory.element_documentation),
            )
        )
        category = result.scalar()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        return VehicleCategoryWithRelations.model_validate(category)


@router.put("/vehicle-categories/{category_id}", response_model=VehicleCategoryResponse)
async def update_vehicle_category(
    category_id: UUID,
    data: VehicleCategoryUpdate,
    user: AdminUser = Depends(get_current_user),
) -> VehicleCategoryResponse:
    """Update a vehicle category."""
    async with get_async_session() as session:
        category = await session.get(VehicleCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        old_slug = category.slug
        changes = {}

        for field, value in data.model_dump(exclude_unset=True).items():
            if getattr(category, field) != value:
                changes[field] = {"old": getattr(category, field), "new": value}
                setattr(category, field, value)

        if changes:
            await create_audit_log(
                session,
                "vehicle_category",
                category_id,
                "update",
                changes,
                user.username,
            )
            await session.commit()
            await session.refresh(category)

            # Invalidate cache
            await invalidate_tariff_cache(old_slug)
            if category.slug != old_slug:
                await invalidate_tariff_cache(category.slug)

        logger.info(f"Updated vehicle category: {category.slug}")
        return VehicleCategoryResponse.model_validate(category)


@router.delete("/vehicle-categories/{category_id}", status_code=204)
async def delete_vehicle_category(
    category_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete a vehicle category."""
    async with get_async_session() as session:
        category = await session.get(VehicleCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        slug = category.slug
        await create_audit_log(
            session,
            "vehicle_category",
            category_id,
            "delete",
            {"slug": slug, "name": category.name},
            user.username,
        )

        await session.delete(category)
        await session.commit()

        # Invalidate cache
        await invalidate_tariff_cache(slug)

        logger.info(f"Deleted vehicle category: {slug}")


# =============================================================================
# Tariff Tier Routes
# =============================================================================


@router.get("/tariff-tiers")
async def list_tariff_tiers(
    user: AdminUser = Depends(get_current_user),
    category_id: UUID | None = Query(None, description="Filter by category ID"),
    client_type: str | None = Query(None, description="Filter by client type"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all tariff tiers with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(TariffTier.id))
        if category_id:
            count_query = count_query.where(TariffTier.category_id == category_id)
        if client_type:
            count_query = count_query.where(TariffTier.client_type == client_type)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch items
        query = select(TariffTier).order_by(TariffTier.sort_order)
        if category_id:
            query = query.where(TariffTier.category_id == category_id)
        if client_type:
            query = query.where(TariffTier.client_type == client_type)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        tiers = result.scalars().all()

        return {
            "items": [TariffTierResponse.model_validate(t) for t in tiers],
            "total": total,
            "has_more": offset + len(tiers) < total,
        }


@router.post("/tariff-tiers", response_model=TariffTierResponse, status_code=201)
async def create_tariff_tier(
    data: TariffTierCreate,
    user: AdminUser = Depends(get_current_user),
) -> TariffTierResponse:
    """Create a new tariff tier."""
    async with get_async_session() as session:
        # Verify category exists
        category = await session.get(VehicleCategory, data.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check for duplicate code in category with same client_type
        existing = await session.execute(
            select(TariffTier).where(
                TariffTier.category_id == data.category_id,
                TariffTier.code == data.code,
                TariffTier.client_type == data.client_type,
            )
        )
        if existing.scalar():
            raise HTTPException(
                status_code=400,
                detail="Tier code already exists for this category and client type"
            )

        tier = TariffTier(**data.model_dump())
        session.add(tier)

        await create_audit_log(
            session,
            "tariff_tier",
            tier.id,
            "create",
            data.model_dump(mode="json"),
            user.username,
        )

        await session.commit()
        await session.refresh(tier)

        # Invalidate cache
        await invalidate_tariff_cache(category.slug)

        logger.info(f"Created tariff tier: {tier.code} for {category.slug}")
        return TariffTierResponse.model_validate(tier)


@router.get("/tariff-tiers/{tier_id}", response_model=TariffTierResponse)
async def get_tariff_tier(
    tier_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> TariffTierResponse:
    """Get a tariff tier by ID."""
    async with get_async_session() as session:
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tier not found")
        return TariffTierResponse.model_validate(tier)


@router.put("/tariff-tiers/{tier_id}", response_model=TariffTierResponse)
async def update_tariff_tier(
    tier_id: UUID,
    data: TariffTierUpdate,
    user: AdminUser = Depends(get_current_user),
) -> TariffTierResponse:
    """Update a tariff tier."""
    async with get_async_session() as session:
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tier not found")

        changes = {}
        for field, value in data.model_dump(exclude_unset=True).items():
            old_val = getattr(tier, field)
            if old_val != value:
                changes[field] = {"old": str(old_val), "new": str(value)}
                setattr(tier, field, value)

        if changes:
            await create_audit_log(
                session, "tariff_tier", tier_id, "update", changes, user.username
            )
            await session.commit()
            await session.refresh(tier)

            # Get category for cache invalidation
            category = await session.get(VehicleCategory, tier.category_id)
            if category:
                await invalidate_tariff_cache(category.slug)

        logger.info(f"Updated tariff tier: {tier.code}")
        return TariffTierResponse.model_validate(tier)


@router.delete("/tariff-tiers/{tier_id}", status_code=204)
async def delete_tariff_tier(
    tier_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete a tariff tier."""
    async with get_async_session() as session:
        tier = await session.get(TariffTier, tier_id)
        if not tier:
            raise HTTPException(status_code=404, detail="Tier not found")

        category = await session.get(VehicleCategory, tier.category_id)

        await create_audit_log(
            session,
            "tariff_tier",
            tier_id,
            "delete",
            {"code": tier.code, "name": tier.name},
            user.username,
        )

        await session.delete(tier)
        await session.commit()

        if category:
            await invalidate_tariff_cache(category.slug)

        logger.info(f"Deleted tariff tier: {tier.code}")


# =============================================================================
# Tariff Prompt Section Routes
# =============================================================================


@router.get("/prompt-sections")
async def list_prompt_sections(
    user: AdminUser = Depends(get_current_user),
    category_id: UUID | None = Query(None, description="Filter by category ID"),
    section_type: str | None = Query(None, description="Filter by section type"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all prompt sections with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(TariffPromptSection.id))
        if category_id:
            count_query = count_query.where(TariffPromptSection.category_id == category_id)
        if section_type:
            count_query = count_query.where(TariffPromptSection.section_type == section_type)
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch items
        query = select(TariffPromptSection).order_by(
            TariffPromptSection.category_id,
            TariffPromptSection.section_type
        )
        if category_id:
            query = query.where(TariffPromptSection.category_id == category_id)
        if section_type:
            query = query.where(TariffPromptSection.section_type == section_type)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        sections = result.scalars().all()

        return {
            "items": [TariffPromptSectionResponse.model_validate(s) for s in sections],
            "total": total,
            "has_more": offset + len(sections) < total,
        }


@router.post("/prompt-sections", response_model=TariffPromptSectionResponse, status_code=201)
async def create_prompt_section(
    data: TariffPromptSectionCreate,
    user: AdminUser = Depends(get_current_user),
) -> TariffPromptSectionResponse:
    """Create a new prompt section."""
    async with get_async_session() as session:
        # Verify category exists
        category = await session.get(VehicleCategory, data.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        # Check for duplicate section type in category
        existing = await session.execute(
            select(TariffPromptSection).where(
                TariffPromptSection.category_id == data.category_id,
                TariffPromptSection.section_type == data.section_type,
            )
        )
        if existing.scalar():
            raise HTTPException(
                status_code=400,
                detail="Section type already exists for this category"
            )

        section = TariffPromptSection(**data.model_dump())
        session.add(section)

        await create_audit_log(
            session,
            "tariff_prompt_section",
            section.id,
            "create",
            {"section_type": data.section_type, "category_id": str(data.category_id)},
            user.username,
        )

        await session.commit()
        await session.refresh(section)

        # Invalidate prompt cache
        await invalidate_tariff_cache(category.slug)

        logger.info(f"Created prompt section: {section.section_type} for {category.slug}")
        return TariffPromptSectionResponse.model_validate(section)


@router.get("/prompt-sections/{section_id}", response_model=TariffPromptSectionResponse)
async def get_prompt_section(
    section_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> TariffPromptSectionResponse:
    """Get a prompt section by ID."""
    async with get_async_session() as session:
        section = await session.get(TariffPromptSection, section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Prompt section not found")
        return TariffPromptSectionResponse.model_validate(section)


@router.put("/prompt-sections/{section_id}", response_model=TariffPromptSectionResponse)
async def update_prompt_section(
    section_id: UUID,
    data: TariffPromptSectionUpdate,
    user: AdminUser = Depends(get_current_user),
) -> TariffPromptSectionResponse:
    """Update a prompt section."""
    async with get_async_session() as session:
        section = await session.get(TariffPromptSection, section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Prompt section not found")

        changes = {}
        for field, value in data.model_dump(exclude_unset=True).items():
            old_val = getattr(section, field)
            if old_val != value:
                if field == "content":
                    # Don't log full content, just note it changed
                    changes[field] = {"changed": True, "length": len(value) if value else 0}
                else:
                    changes[field] = {"old": str(old_val), "new": str(value)}
                setattr(section, field, value)

        if changes:
            # Increment version
            section.version += 1
            changes["version"] = {"old": section.version - 1, "new": section.version}

            await create_audit_log(
                session, "tariff_prompt_section", section_id, "update", changes, user.username
            )
            await session.commit()
            await session.refresh(section)

            # Invalidate cache
            category = await session.get(VehicleCategory, section.category_id)
            if category:
                await invalidate_tariff_cache(category.slug)

        logger.info(f"Updated prompt section: {section.section_type} (v{section.version})")
        return TariffPromptSectionResponse.model_validate(section)


@router.delete("/prompt-sections/{section_id}", status_code=204)
async def delete_prompt_section(
    section_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete a prompt section."""
    async with get_async_session() as session:
        section = await session.get(TariffPromptSection, section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Prompt section not found")

        category = await session.get(VehicleCategory, section.category_id)

        await create_audit_log(
            session,
            "tariff_prompt_section",
            section_id,
            "delete",
            {"section_type": section.section_type},
            user.username,
        )

        await session.delete(section)
        await session.commit()

        if category:
            await invalidate_tariff_cache(category.slug)

        logger.info(f"Deleted prompt section: {section.section_type}")


@router.get("/categories/{category_id}/preview-prompt")
async def preview_category_prompt(
    category_id: UUID,
    client_type: str = Query("particular", description="Client type for prompt"),
    user: AdminUser = Depends(get_current_user),
) -> dict:
    """Preview the generated prompt for a category."""
    async with get_async_session() as session:
        category = await session.get(VehicleCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        prompt_service = get_prompt_service()
        preview = await prompt_service.get_prompt_preview(category.slug, client_type)

        return preview


# =============================================================================
# Base Documentation Routes
# =============================================================================


@router.get("/base-documentation")
async def list_base_documentation(
    user: AdminUser = Depends(get_current_user),
    category_id: UUID | None = Query(None, description="Filter by category ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List base documentation with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(BaseDocumentation.id))
        if category_id:
            count_query = count_query.where(BaseDocumentation.category_id == category_id)
        total = (await session.execute(count_query)).scalar() or 0

        # Fetch items
        query = select(BaseDocumentation).order_by(BaseDocumentation.sort_order)
        if category_id:
            query = query.where(BaseDocumentation.category_id == category_id)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        docs = result.scalars().all()

        return {
            "items": [BaseDocumentationResponse.model_validate(d) for d in docs],
            "total": total,
            "has_more": offset + len(docs) < total,
        }


@router.post("/base-documentation", response_model=BaseDocumentationResponse, status_code=201)
async def create_base_documentation(
    data: BaseDocumentationCreate,
    user: AdminUser = Depends(get_current_user),
) -> BaseDocumentationResponse:
    """Create base documentation."""
    async with get_async_session() as session:
        category = await session.get(VehicleCategory, data.category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        doc = BaseDocumentation(**data.model_dump())
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        await invalidate_tariff_cache(category.slug)

        return BaseDocumentationResponse.model_validate(doc)


@router.put("/base-documentation/{doc_id}", response_model=BaseDocumentationResponse)
async def update_base_documentation(
    doc_id: UUID,
    data: BaseDocumentationUpdate,
    user: AdminUser = Depends(get_current_user),
) -> BaseDocumentationResponse:
    """Update base documentation."""
    async with get_async_session() as session:
        doc = await session.get(BaseDocumentation, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Documentation not found")

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(doc, field, value)

        await session.commit()
        await session.refresh(doc)

        category = await session.get(VehicleCategory, doc.category_id)
        if category:
            await invalidate_tariff_cache(category.slug)

        return BaseDocumentationResponse.model_validate(doc)


@router.delete("/base-documentation/{doc_id}", status_code=204)
async def delete_base_documentation(
    doc_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete base documentation."""
    async with get_async_session() as session:
        doc = await session.get(BaseDocumentation, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Documentation not found")

        category = await session.get(VehicleCategory, doc.category_id)

        await session.delete(doc)
        await session.commit()

        if category:
            await invalidate_tariff_cache(category.slug)


# =============================================================================
# Warning Routes
# =============================================================================


@router.get("/warnings")
async def list_warnings(
    user: AdminUser = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all warnings with pagination."""
    async with get_async_session() as session:
        # Count total
        total = (await session.execute(select(func.count(Warning.id)))).scalar() or 0

        # Fetch items
        query = select(Warning).order_by(Warning.code).offset(offset).limit(limit)
        result = await session.execute(query)
        warnings = result.scalars().all()

        return {
            "items": [WarningResponse.model_validate(w) for w in warnings],
            "total": total,
            "has_more": offset + len(warnings) < total,
        }


@router.post("/warnings", response_model=WarningResponse, status_code=201)
async def create_warning(
    data: WarningCreate,
    user: AdminUser = Depends(get_current_user),
) -> WarningResponse:
    """Create a new warning."""
    async with get_async_session() as session:
        # Check for duplicate code
        existing = await session.execute(
            select(Warning).where(Warning.code == data.code)
        )
        if existing.scalar():
            raise HTTPException(status_code=400, detail="Warning code already exists")

        warning = Warning(**data.model_dump())
        session.add(warning)

        await create_audit_log(
            session,
            "warning",
            warning.id,
            "create",
            {"code": data.code, "severity": data.severity},
            user.username,
        )

        await session.commit()
        await session.refresh(warning)

        logger.info(f"Created warning: {warning.code}")
        return WarningResponse.model_validate(warning)


@router.get("/warnings/{warning_id}", response_model=WarningResponse)
async def get_warning(
    warning_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> WarningResponse:
    """Get a warning by ID."""
    async with get_async_session() as session:
        warning = await session.get(Warning, warning_id)
        if not warning:
            raise HTTPException(status_code=404, detail="Warning not found")
        return WarningResponse.model_validate(warning)


@router.put("/warnings/{warning_id}", response_model=WarningResponse)
async def update_warning(
    warning_id: UUID,
    data: WarningUpdate,
    user: AdminUser = Depends(get_current_user),
) -> WarningResponse:
    """Update a warning."""
    async with get_async_session() as session:
        warning = await session.get(Warning, warning_id)
        if not warning:
            raise HTTPException(status_code=404, detail="Warning not found")

        changes = {}
        for field, value in data.model_dump(exclude_unset=True).items():
            old_val = getattr(warning, field)
            if old_val != value:
                if field == "trigger_conditions":
                    changes[field] = {"changed": True}
                else:
                    changes[field] = {"old": old_val, "new": value}
                setattr(warning, field, value)

        if changes:
            await create_audit_log(
                session, "warning", warning_id, "update", changes, user.username
            )
            await session.commit()
            await session.refresh(warning)

        logger.info(f"Updated warning: {warning.code}")
        return WarningResponse.model_validate(warning)


@router.delete("/warnings/{warning_id}", status_code=204)
async def delete_warning(
    warning_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete a warning."""
    async with get_async_session() as session:
        warning = await session.get(Warning, warning_id)
        if not warning:
            raise HTTPException(status_code=404, detail="Warning not found")

        await create_audit_log(
            session,
            "warning",
            warning_id,
            "delete",
            {"code": warning.code},
            user.username,
        )

        await session.delete(warning)
        await session.commit()

        logger.info(f"Deleted warning: {warning.code}")


# =============================================================================
# Additional Service Routes
# =============================================================================


@router.get("/additional-services")
async def list_additional_services(
    user: AdminUser = Depends(get_current_user),
    category_id: UUID | None = Query(None, description="Filter by category"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List additional services with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(AdditionalService.id))
        if category_id:
            count_query = count_query.where(AdditionalService.category_id == category_id)
        total = (await session.execute(count_query)).scalar() or 0

        # Fetch items
        query = select(AdditionalService).order_by(AdditionalService.sort_order)
        if category_id:
            query = query.where(AdditionalService.category_id == category_id)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        services = result.scalars().all()

        return {
            "items": [AdditionalServiceResponse.model_validate(s) for s in services],
            "total": total,
            "has_more": offset + len(services) < total,
        }


@router.get("/additional-services/{service_id}", response_model=AdditionalServiceResponse)
async def get_additional_service(
    service_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> AdditionalServiceResponse:
    """Get an additional service by ID."""
    async with get_async_session() as session:
        service = await session.get(AdditionalService, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        return AdditionalServiceResponse.model_validate(service)


@router.post("/additional-services", response_model=AdditionalServiceResponse, status_code=201)
async def create_additional_service(
    data: AdditionalServiceCreate,
    user: AdminUser = Depends(get_current_user),
) -> AdditionalServiceResponse:
    """Create an additional service."""
    async with get_async_session() as session:
        # Verify category if provided
        if data.category_id:
            category = await session.get(VehicleCategory, data.category_id)
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

        service = AdditionalService(**data.model_dump())
        session.add(service)

        await create_audit_log(
            session,
            "additional_service",
            service.id,
            "create",
            data.model_dump(mode="json"),
            user.username,
        )

        await session.commit()
        await session.refresh(service)

        # Invalidate cache for affected categories
        if service.category_id:
            category = await session.get(VehicleCategory, service.category_id)
            if category:
                await invalidate_tariff_cache(category.slug)
        else:
            # Global service - invalidate all categories
            result = await session.execute(select(VehicleCategory))
            for cat in result.scalars():
                await invalidate_tariff_cache(cat.slug)

        logger.info(f"Created additional service: {service.code}")
        return AdditionalServiceResponse.model_validate(service)


@router.put("/additional-services/{service_id}", response_model=AdditionalServiceResponse)
async def update_additional_service(
    service_id: UUID,
    data: AdditionalServiceUpdate,
    user: AdminUser = Depends(get_current_user),
) -> AdditionalServiceResponse:
    """Update an additional service."""
    async with get_async_session() as session:
        service = await session.get(AdditionalService, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Track old category for cache invalidation
        old_category_id = service.category_id

        # Verify new category if provided
        if data.category_id is not None and data.category_id != old_category_id:
            if data.category_id:
                category = await session.get(VehicleCategory, data.category_id)
                if not category:
                    raise HTTPException(status_code=404, detail="Category not found")

        changes = {}
        for field, value in data.model_dump(exclude_unset=True).items():
            old_val = getattr(service, field)
            if old_val != value:
                changes[field] = {"old": str(old_val), "new": str(value)}
                setattr(service, field, value)

        if changes:
            await create_audit_log(
                session, "additional_service", service_id, "update", changes, user.username
            )
            await session.commit()
            await session.refresh(service)

            # Invalidate cache for affected categories
            categories_to_invalidate: set[str] = set()
            if old_category_id:
                old_cat = await session.get(VehicleCategory, old_category_id)
                if old_cat:
                    categories_to_invalidate.add(old_cat.slug)
            if service.category_id:
                new_cat = await session.get(VehicleCategory, service.category_id)
                if new_cat:
                    categories_to_invalidate.add(new_cat.slug)
            if not old_category_id or not service.category_id:
                # Was or is global - invalidate all
                result = await session.execute(select(VehicleCategory))
                categories_to_invalidate.update(cat.slug for cat in result.scalars())

            for slug in categories_to_invalidate:
                await invalidate_tariff_cache(slug)

        logger.info(f"Updated additional service: {service.code}")
        return AdditionalServiceResponse.model_validate(service)


@router.delete("/additional-services/{service_id}", status_code=204)
async def delete_additional_service(
    service_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete an additional service."""
    async with get_async_session() as session:
        service = await session.get(AdditionalService, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Store category info for cache invalidation
        category_id = service.category_id

        await create_audit_log(
            session,
            "additional_service",
            service_id,
            "delete",
            {"code": service.code, "name": service.name},
            user.username,
        )

        await session.delete(service)
        await session.commit()

        # Invalidate cache for affected categories
        if category_id:
            category = await session.get(VehicleCategory, category_id)
            if category:
                await invalidate_tariff_cache(category.slug)
        else:
            # Was global service - invalidate all categories
            result = await session.execute(select(VehicleCategory))
            for cat in result.scalars():
                await invalidate_tariff_cache(cat.slug)

        logger.info(f"Deleted additional service: {service.code}")


# =============================================================================
# Audit Log Routes
# =============================================================================


@router.get("/audit-log")
async def list_audit_log(
    user: AdminUser = Depends(get_current_user),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    entity_id: UUID | None = Query(None, description="Filter by entity ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List audit log entries."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(AuditLog.id))
        if entity_type:
            count_query = count_query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            count_query = count_query.where(AuditLog.entity_id == entity_id)
        total = (await session.execute(count_query)).scalar() or 0

        # Fetch items
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        logs = result.scalars().all()

        return {
            "items": [AuditLogResponse.model_validate(log) for log in logs],
            "total": total,
            "has_more": offset + len(logs) < total,
        }


# =============================================================================
# Element Documentation Routes
# =============================================================================


@router.get("/element-documentation")
async def list_element_documentation(
    user: AdminUser = Depends(get_current_user),
    category_id: UUID | None = Query(None, description="Filter by category ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List element documentation with pagination."""
    async with get_async_session() as session:
        # Count total
        count_query = select(func.count(ElementDocumentation.id))
        if category_id:
            count_query = count_query.where(ElementDocumentation.category_id == category_id)
        if is_active is not None:
            count_query = count_query.where(ElementDocumentation.is_active == is_active)
        total = (await session.execute(count_query)).scalar() or 0

        # Fetch items
        query = select(ElementDocumentation).order_by(ElementDocumentation.sort_order)
        if category_id:
            query = query.where(ElementDocumentation.category_id == category_id)
        if is_active is not None:
            query = query.where(ElementDocumentation.is_active == is_active)
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        docs = result.scalars().all()

        return {
            "items": [ElementDocumentationResponse.model_validate(d) for d in docs],
            "total": total,
            "has_more": offset + len(docs) < total,
        }


@router.post("/element-documentation", response_model=ElementDocumentationResponse, status_code=201)
async def create_element_documentation(
    data: ElementDocumentationCreate,
    user: AdminUser = Depends(get_current_user),
) -> ElementDocumentationResponse:
    """Create element documentation."""
    async with get_async_session() as session:
        # Verify category if provided
        if data.category_id:
            category = await session.get(VehicleCategory, data.category_id)
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

        doc = ElementDocumentation(**data.model_dump())
        session.add(doc)

        await create_audit_log(
            session,
            "element_documentation",
            doc.id,
            "create",
            {"keywords": data.element_keywords, "description": data.description[:100]},
            user.username,
        )

        await session.commit()
        await session.refresh(doc)

        # Invalidate cache if category specified
        if data.category_id:
            category = await session.get(VehicleCategory, data.category_id)
            if category:
                await invalidate_tariff_cache(category.slug)

        logger.info(f"Created element documentation: {data.element_keywords}")
        return ElementDocumentationResponse.model_validate(doc)


@router.get("/element-documentation/{doc_id}", response_model=ElementDocumentationResponse)
async def get_element_documentation(
    doc_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> ElementDocumentationResponse:
    """Get element documentation by ID."""
    async with get_async_session() as session:
        doc = await session.get(ElementDocumentation, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Element documentation not found")
        return ElementDocumentationResponse.model_validate(doc)


@router.put("/element-documentation/{doc_id}", response_model=ElementDocumentationResponse)
async def update_element_documentation(
    doc_id: UUID,
    data: ElementDocumentationUpdate,
    user: AdminUser = Depends(get_current_user),
) -> ElementDocumentationResponse:
    """Update element documentation."""
    async with get_async_session() as session:
        doc = await session.get(ElementDocumentation, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Element documentation not found")

        changes = {}
        for field, value in data.model_dump(exclude_unset=True).items():
            old_val = getattr(doc, field)
            if old_val != value:
                if field in ("description",):
                    changes[field] = {"changed": True}
                else:
                    changes[field] = {"old": str(old_val), "new": str(value)}
                setattr(doc, field, value)

        if changes:
            await create_audit_log(
                session, "element_documentation", doc_id, "update", changes, user.username
            )
            await session.commit()
            await session.refresh(doc)

            # Invalidate cache
            if doc.category_id:
                category = await session.get(VehicleCategory, doc.category_id)
                if category:
                    await invalidate_tariff_cache(category.slug)

        logger.info(f"Updated element documentation: {doc_id}")
        return ElementDocumentationResponse.model_validate(doc)


@router.delete("/element-documentation/{doc_id}", status_code=204)
async def delete_element_documentation(
    doc_id: UUID,
    user: AdminUser = Depends(get_current_user),
) -> None:
    """Delete element documentation."""
    async with get_async_session() as session:
        doc = await session.get(ElementDocumentation, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Element documentation not found")

        category = None
        if doc.category_id:
            category = await session.get(VehicleCategory, doc.category_id)

        await create_audit_log(
            session,
            "element_documentation",
            doc_id,
            "delete",
            {"keywords": doc.element_keywords},
            user.username,
        )

        await session.delete(doc)
        await session.commit()

        if category:
            await invalidate_tariff_cache(category.slug)

        logger.info(f"Deleted element documentation: {doc_id}")
