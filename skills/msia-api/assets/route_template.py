"""
Template for MSI-a FastAPI route.

Usage:
1. Copy this file to api/routes/
2. Rename to your_resource.py
3. Update the router prefix and tags
4. Implement the endpoints
5. Register in api/main.py
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from database.models import MyModel  # Replace with actual model

router = APIRouter(prefix="/api/my-resource", tags=["my-resource"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class MyResourceBase(BaseModel):
    """Base schema with shared fields."""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True


class MyResourceCreate(MyResourceBase):
    """Schema for creating a resource."""
    
    # Add create-only fields here
    category_id: UUID


class MyResourceUpdate(BaseModel):
    """Schema for updating a resource (all fields optional)."""
    
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None


class MyResourceResponse(MyResourceBase):
    """Schema for API response."""
    
    id: UUID
    category_id: UUID
    created_at: str
    updated_at: str
    
    model_config = {"from_attributes": True}


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/", response_model=list[MyResourceResponse])
async def list_resources(
    session: AsyncSession = Depends(get_session),
    category_id: UUID | None = Query(None, description="Filter by category"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    List all resources with optional filtering.
    
    - **category_id**: Filter by category UUID
    - **is_active**: Filter by active status
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum records to return
    """
    query = select(MyModel)
    
    if category_id:
        query = query.where(MyModel.category_id == category_id)
    if is_active is not None:
        query = query.where(MyModel.is_active == is_active)
    
    query = query.offset(skip).limit(limit).order_by(MyModel.sort_order)
    
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{resource_id}", response_model=MyResourceResponse)
async def get_resource(
    resource_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get a single resource by ID."""
    result = await session.execute(
        select(MyModel).where(MyModel.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    
    return resource


@router.post("/", response_model=MyResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: MyResourceCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new resource."""
    # Check for duplicates if needed
    existing = await session.execute(
        select(MyModel).where(
            MyModel.category_id == data.category_id,
            MyModel.name == data.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource with this name already exists in category",
        )
    
    resource = MyModel(**data.model_dump())
    session.add(resource)
    await session.flush()
    
    return resource


@router.put("/{resource_id}", response_model=MyResourceResponse)
async def update_resource(
    resource_id: UUID,
    data: MyResourceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing resource."""
    result = await session.execute(
        select(MyModel).where(MyModel.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    
    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(resource, field, value)
    
    await session.flush()
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a resource."""
    result = await session.execute(
        select(MyModel).where(MyModel.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    
    await session.delete(resource)
