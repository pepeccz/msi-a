"""
MSI-a Base Seeder.

Provides common functionality for all seeders:
- Uniform logging format
- Generic upsert operations
- Statistics tracking
"""

import logging
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BaseSeeder:
    """
    Base class for all seeders with common functionality.
    
    Provides:
    - Consistent logging format
    - Statistics tracking (created, updated, skipped)
    - Generic upsert operation
    """

    def __init__(self, category_slug: str, session: AsyncSession):
        """
        Initialize the seeder.
        
        Args:
            category_slug: The category identifier (e.g., "motos-part")
            session: The async database session
        """
        self.category_slug = category_slug
        self.session = session
        self.stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.stats = {"created": 0, "updated": 0, "skipped": 0}

    def log_created(self, entity_type: str, code: str) -> None:
        """Log a created entity."""
        self.stats["created"] += 1
        logger.info(f"  + {entity_type} {code}: Created")

    def log_updated(self, entity_type: str, code: str) -> None:
        """Log an updated entity."""
        self.stats["updated"] += 1
        logger.info(f"  ~ {entity_type} {code}: Updated")

    def log_skipped(self, entity_type: str, code: str) -> None:
        """Log a skipped entity."""
        self.stats["skipped"] += 1

    def log_summary(self, entity_type: str) -> None:
        """Log a summary of operations."""
        logger.info(
            f"  {entity_type}: {self.stats['created']} created, "
            f"{self.stats['updated']} updated, {self.stats['skipped']} skipped"
        )

    async def upsert(
        self,
        model_class: type,
        deterministic_id: UUID,
        data: dict[str, Any],
        entity_type: str = "Entity",
        code: str | None = None,
    ) -> tuple[Any, str]:
        """
        Generic upsert operation with deterministic UUID.
        
        Args:
            model_class: The SQLAlchemy model class
            deterministic_id: The deterministic UUID for this entity
            data: Dictionary of field values to set
            entity_type: Name for logging (e.g., "Category", "Tier")
            code: Identifier for logging
        
        Returns:
            Tuple of (instance, action) where action is "created" or "updated"
        """
        log_code = code or data.get("code", str(deterministic_id)[:8])
        
        existing = await self.session.get(model_class, deterministic_id)
        
        if existing:
            # Update existing entity
            for key, value in data.items():
                setattr(existing, key, value)
            self.log_updated(entity_type, log_code)
            return existing, "updated"
        else:
            # Create new entity with deterministic UUID
            instance = model_class(id=deterministic_id, **data)
            self.session.add(instance)
            self.log_created(entity_type, log_code)
            return instance, "created"

    async def upsert_with_uuid_fn(
        self,
        model_class: type,
        uuid_fn: Callable[..., UUID],
        uuid_args: tuple,
        data: dict[str, Any],
        entity_type: str = "Entity",
        code: str | None = None,
    ) -> tuple[Any, str]:
        """
        Upsert using a UUID generation function.
        
        Args:
            model_class: The SQLAlchemy model class
            uuid_fn: Function to generate deterministic UUID
            uuid_args: Arguments to pass to uuid_fn
            data: Dictionary of field values to set
            entity_type: Name for logging
            code: Identifier for logging
        
        Returns:
            Tuple of (instance, action)
        """
        deterministic_id = uuid_fn(*uuid_args)
        return await self.upsert(model_class, deterministic_id, data, entity_type, code)
