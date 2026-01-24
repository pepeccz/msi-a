"""
MSI Automotive - Response Constraints API routes.

Provides CRUD endpoints for managing anti-hallucination response constraints.
These constraints are database-driven rules that validate LLM responses and
force retries when the agent attempts to respond without using required tools.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete

from api.routes.admin import get_current_user
from database.connection import get_async_session
from database.models import AdminUser, ResponseConstraint, VehicleCategory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/response-constraints")


# =============================================================================
# Pydantic Schemas
# =============================================================================


class ConstraintCreate(BaseModel):
    """Schema for creating a ResponseConstraint."""

    category_id: UUID | None = Field(None, description="If null, applies to all categories")
    constraint_type: str = Field(..., max_length=50)
    detection_pattern: str = Field(..., max_length=500, description="Regex pattern to detect violations")
    required_tool: str = Field(..., max_length=200, description="Required tool(s), pipe-separated")
    error_injection: str = Field(..., description="Correction message injected on violation")
    is_active: bool = Field(default=True)
    priority: int = Field(default=0, description="Higher priority = checked first")


class ConstraintUpdate(BaseModel):
    """Schema for updating a ResponseConstraint."""

    category_id: UUID | None = None
    constraint_type: str | None = None
    detection_pattern: str | None = None
    required_tool: str | None = None
    error_injection: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class ConstraintResponse(BaseModel):
    """Schema for ResponseConstraint response."""

    id: UUID
    category_id: UUID | None
    category_name: str | None = None
    constraint_type: str
    detection_pattern: str
    required_tool: str
    error_injection: str
    is_active: bool
    priority: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
async def list_constraints(
    category_id: UUID | None = Query(None, description="Filter by category"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    _: AdminUser = Depends(get_current_user),
) -> list[ConstraintResponse]:
    """List all response constraints, optionally filtered."""
    async with get_async_session() as session:
        query = select(ResponseConstraint).order_by(
            ResponseConstraint.priority.desc(),
            ResponseConstraint.created_at.desc(),
        )

        if category_id is not None:
            query = query.where(ResponseConstraint.category_id == category_id)
        if is_active is not None:
            query = query.where(ResponseConstraint.is_active == is_active)

        result = await session.execute(query)
        constraints = result.scalars().all()

        # Get category names for display
        category_ids = {c.category_id for c in constraints if c.category_id}
        category_names: dict[UUID, str] = {}
        if category_ids:
            cat_result = await session.execute(
                select(VehicleCategory.id, VehicleCategory.name)
                .where(VehicleCategory.id.in_(category_ids))
            )
            category_names = {row.id: row.name for row in cat_result.all()}

        return [
            ConstraintResponse(
                id=c.id,
                category_id=c.category_id,
                category_name=category_names.get(c.category_id) if c.category_id else None,
                constraint_type=c.constraint_type,
                detection_pattern=c.detection_pattern,
                required_tool=c.required_tool,
                error_injection=c.error_injection,
                is_active=c.is_active,
                priority=c.priority,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
            )
            for c in constraints
        ]


@router.post("", status_code=201)
async def create_constraint(
    data: ConstraintCreate,
    _: AdminUser = Depends(get_current_user),
) -> ConstraintResponse:
    """Create a new response constraint."""
    # Validate category exists if provided
    async with get_async_session() as session:
        if data.category_id:
            cat = await session.get(VehicleCategory, data.category_id)
            if not cat:
                raise HTTPException(status_code=404, detail="Category not found")

        constraint = ResponseConstraint(
            category_id=data.category_id,
            constraint_type=data.constraint_type,
            detection_pattern=data.detection_pattern,
            required_tool=data.required_tool,
            error_injection=data.error_injection,
            is_active=data.is_active,
            priority=data.priority,
        )
        session.add(constraint)
        await session.commit()
        await session.refresh(constraint)

        # Invalidate agent cache
        _invalidate_constraint_cache()

        return ConstraintResponse(
            id=constraint.id,
            category_id=constraint.category_id,
            category_name=None,
            constraint_type=constraint.constraint_type,
            detection_pattern=constraint.detection_pattern,
            required_tool=constraint.required_tool,
            error_injection=constraint.error_injection,
            is_active=constraint.is_active,
            priority=constraint.priority,
            created_at=constraint.created_at.isoformat(),
            updated_at=constraint.updated_at.isoformat(),
        )


@router.put("/{constraint_id}")
async def update_constraint(
    constraint_id: UUID,
    data: ConstraintUpdate,
    _: AdminUser = Depends(get_current_user),
) -> ConstraintResponse:
    """Update an existing response constraint."""
    async with get_async_session() as session:
        constraint = await session.get(ResponseConstraint, constraint_id)
        if not constraint:
            raise HTTPException(status_code=404, detail="Constraint not found")

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(constraint, field, value)

        await session.commit()
        await session.refresh(constraint)

        # Invalidate agent cache
        _invalidate_constraint_cache()

        return ConstraintResponse(
            id=constraint.id,
            category_id=constraint.category_id,
            category_name=None,
            constraint_type=constraint.constraint_type,
            detection_pattern=constraint.detection_pattern,
            required_tool=constraint.required_tool,
            error_injection=constraint.error_injection,
            is_active=constraint.is_active,
            priority=constraint.priority,
            created_at=constraint.created_at.isoformat(),
            updated_at=constraint.updated_at.isoformat(),
        )


@router.delete("/{constraint_id}", status_code=204)
async def delete_constraint(
    constraint_id: UUID,
    _: AdminUser = Depends(get_current_user),
) -> None:
    """Delete a response constraint."""
    async with get_async_session() as session:
        constraint = await session.get(ResponseConstraint, constraint_id)
        if not constraint:
            raise HTTPException(status_code=404, detail="Constraint not found")

        await session.delete(constraint)
        await session.commit()

        # Invalidate agent cache
        _invalidate_constraint_cache()


def _invalidate_constraint_cache() -> None:
    """Invalidate the agent's constraint cache after DB changes."""
    try:
        from agent.services.constraint_service import invalidate_cache
        invalidate_cache()
    except Exception:
        # Agent may not be running in same process
        pass
