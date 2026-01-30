"""
MSI Automotive - Pagination Utilities.

Provides standardized pagination helpers for API routes.
"""

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema.
    
    Standardizes pagination across all API endpoints.
    
    Attributes:
        items: List of items for current page
        total: Total number of items across all pages
        offset: Number of items skipped
        limit: Maximum items per page
        has_more: Whether there are more items beyond current page
    """

    items: list[T]
    total: int
    offset: int
    limit: int
    has_more: bool


async def paginate_query(
    query: Select,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list, int, bool]:
    """
    Execute a paginated query and return results with pagination metadata.
    
    This is a low-level helper that returns raw SQLAlchemy results.
    Use this when you need to transform results before creating a PaginatedResponse.
    
    Args:
        query: SQLAlchemy select query (without limit/offset applied)
        session: Async database session
        offset: Number of items to skip
        limit: Maximum items to return
        
    Returns:
        Tuple of (items, total_count, has_more)
        
    Example:
        ```python
        query = select(User).where(User.is_active == True).order_by(User.created_at.desc())
        items, total, has_more = await paginate_query(query, session, offset=0, limit=50)
        
        return PaginatedResponse(
            items=[UserResponse.model_validate(u) for u in items],
            total=total,
            offset=0,
            limit=50,
            has_more=has_more
        )
        ```
    """
    # Get total count (without limit/offset)
    count_query = select(func.count()).select_from(query.alias())
    total = (await session.execute(count_query)).scalar() or 0
    
    # Apply pagination
    paginated_query = query.offset(offset).limit(limit)
    result = await session.execute(paginated_query)
    items = result.scalars().all()
    
    # Calculate has_more
    has_more = offset + len(items) < total
    
    return list(items), total, has_more


async def create_paginated_response(
    query: Select,
    session: AsyncSession,
    response_model: type[T],
    offset: int = 0,
    limit: int = 50,
) -> PaginatedResponse[T]:
    """
    Execute a paginated query and return a standardized PaginatedResponse.
    
    This is a high-level helper that automatically transforms results using
    the provided Pydantic model.
    
    Args:
        query: SQLAlchemy select query (without limit/offset applied)
        session: Async database session
        response_model: Pydantic model to transform each result
        offset: Number of items to skip
        limit: Maximum items to return
        
    Returns:
        PaginatedResponse with typed items
        
    Example:
        ```python
        query = select(User).where(User.is_active == True).order_by(User.created_at.desc())
        return await create_paginated_response(
            query=query,
            session=session,
            response_model=UserResponse,
            offset=0,
            limit=50
        )
        ```
    """
    items, total, has_more = await paginate_query(query, session, offset, limit)
    
    return PaginatedResponse(
        items=[response_model.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
        has_more=has_more,
    )


def create_manual_paginated_response(
    items: list[T],
    total: int,
    offset: int,
    limit: int,
) -> PaginatedResponse[T]:
    """
    Create a PaginatedResponse from pre-fetched items.
    
    Use this when pagination logic is handled manually or when working
    with non-database sources.
    
    Args:
        items: List of items for current page
        total: Total number of items across all pages
        offset: Number of items skipped
        limit: Maximum items per page
        
    Returns:
        PaginatedResponse with provided items
        
    Example:
        ```python
        # When you already have the items and total
        return create_manual_paginated_response(
            items=transformed_items,
            total=total_count,
            offset=0,
            limit=50
        )
        ```
    """
    has_more = offset + len(items) < total
    
    return PaginatedResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=has_more,
    )
