"""
Template for MSI-a service class.

Usage:
1. Copy this file to api/services/ or agent/services/
2. Rename to your_service.py
3. Update the class name and methods
4. Import where needed
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import MyModel, RelatedModel  # Replace with actual models

logger = logging.getLogger(__name__)


class MyService:
    """
    Service for handling MyModel business logic.
    
    Services contain business logic that:
    - Spans multiple database operations
    - Requires complex validation
    - Needs to be reused across routes/tools
    """
    
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        resource_id: UUID,
        *,
        include_related: bool = False,
    ) -> MyModel | None:
        """
        Get a resource by ID.
        
        Args:
            session: Database session
            resource_id: Resource UUID
            include_related: Whether to eagerly load relationships
            
        Returns:
            Resource or None if not found
        """
        query = select(MyModel).where(MyModel.id == resource_id)
        
        if include_related:
            query = query.options(selectinload(MyModel.related_items))
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(
        session: AsyncSession,
        *,
        category_id: UUID | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MyModel]:
        """
        Get all resources with optional filtering.
        
        Args:
            session: Database session
            category_id: Filter by category
            is_active: Filter by active status
            skip: Pagination offset
            limit: Max results
            
        Returns:
            List of resources
        """
        query = select(MyModel)
        
        if category_id:
            query = query.where(MyModel.category_id == category_id)
        if is_active is not None:
            query = query.where(MyModel.is_active == is_active)
        
        query = query.offset(skip).limit(limit).order_by(MyModel.sort_order)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        name: str,
        category_id: UUID,
        description: str | None = None,
    ) -> MyModel:
        """
        Create a new resource.
        
        Args:
            session: Database session
            name: Resource name
            category_id: Parent category
            description: Optional description
            
        Returns:
            Created resource
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not name.strip():
            raise ValueError("Name cannot be empty")
        
        # Check for duplicates
        existing = await session.execute(
            select(MyModel).where(
                MyModel.category_id == category_id,
                MyModel.name == name,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Resource '{name}' already exists in category")
        
        # Create
        resource = MyModel(
            name=name,
            category_id=category_id,
            description=description,
        )
        session.add(resource)
        await session.flush()
        
        logger.info(
            f"Created resource: {resource.id}",
            extra={"resource_id": str(resource.id), "name": name},
        )
        
        return resource
    
    @staticmethod
    async def update(
        session: AsyncSession,
        resource_id: UUID,
        **kwargs,
    ) -> MyModel | None:
        """
        Update a resource.
        
        Args:
            session: Database session
            resource_id: Resource to update
            **kwargs: Fields to update
            
        Returns:
            Updated resource or None if not found
        """
        resource = await MyService.get_by_id(session, resource_id)
        if not resource:
            return None
        
        for field, value in kwargs.items():
            if hasattr(resource, field) and value is not None:
                setattr(resource, field, value)
        
        await session.flush()
        
        logger.info(
            f"Updated resource: {resource_id}",
            extra={"resource_id": str(resource_id), "fields": list(kwargs.keys())},
        )
        
        return resource
    
    @staticmethod
    async def delete(
        session: AsyncSession,
        resource_id: UUID,
    ) -> bool:
        """
        Delete a resource.
        
        Args:
            session: Database session
            resource_id: Resource to delete
            
        Returns:
            True if deleted, False if not found
        """
        resource = await MyService.get_by_id(session, resource_id)
        if not resource:
            return False
        
        await session.delete(resource)
        
        logger.info(
            f"Deleted resource: {resource_id}",
            extra={"resource_id": str(resource_id)},
        )
        
        return True
    
    @staticmethod
    async def process_complex_operation(
        session: AsyncSession,
        resource_id: UUID,
        data: dict,
    ) -> dict:
        """
        Example of a complex business operation.
        
        This method demonstrates how to handle operations that
        span multiple models or require complex logic.
        """
        # Get main resource
        resource = await MyService.get_by_id(
            session, resource_id, include_related=True
        )
        if not resource:
            raise ValueError(f"Resource {resource_id} not found")
        
        # Get related data
        related = await session.execute(
            select(RelatedModel).where(
                RelatedModel.parent_id == resource_id
            )
        )
        related_items = related.scalars().all()
        
        # Process
        result = {
            "resource": resource,
            "related_count": len(related_items),
            "processed_data": data,
        }
        
        return result
