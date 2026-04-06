"""
Verification Script: Element-Warning Associations

Verifies that element warnings are correctly stored via the M2M
element_warning_associations table (unified system after migration 042).

Usage:
    python -m database.seeds.verify_warning_sync
"""

import asyncio
import logging
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import (
    Element,
    Warning,
    ElementWarningAssociation,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_sync() -> None:
    """Verify element warning associations."""

    async with get_async_session() as session:
        logger.info("=" * 70)
        logger.info("VERIFICATION: Element-Warning Associations (M2M system)")
        logger.info("=" * 70)

        # 1. Count all warnings
        result = await session.execute(select(func.count(Warning.id)))
        total_warnings = result.scalar()
        logger.info(f"\n✓ Total warnings in warnings table: {total_warnings}")

        # 2. Count association entries
        result = await session.execute(
            select(func.count(ElementWarningAssociation.id))
        )
        assoc_count = result.scalar()
        logger.info(f"✓ Element-warning associations (element_warning_associations): {assoc_count}")

        if assoc_count == 0:
            logger.warning("\n⚠️  WARNING: No element-warning associations found")
        else:
            logger.info(f"\n✅ {assoc_count} element-warning associations present")

        # 3. Count distinct elements that have warnings
        result = await session.execute(
            select(func.count(ElementWarningAssociation.element_id.distinct()))
        )
        elements_with_warnings = result.scalar()
        logger.info(f"✓ Elements with at least one warning: {elements_with_warnings}")

        # 4. Sample verification: list first 5 elements with warning counts
        logger.info("\n" + "-" * 70)
        logger.info("Sample Data Verification (first 5 elements with warnings)")
        logger.info("-" * 70)

        result = await session.execute(
            select(Element)
            .join(
                ElementWarningAssociation,
                ElementWarningAssociation.element_id == Element.id,
            )
            .options(selectinload(Element.category))
            .distinct()
            .limit(5)
        )
        elements = result.scalars().unique().all()

        for element in elements:
            assoc_result = await session.execute(
                select(func.count(ElementWarningAssociation.id)).where(
                    ElementWarningAssociation.element_id == element.id
                )
            )
            assoc_w_count = assoc_result.scalar()
            logger.info(
                f"✅ {element.code:20} | Category: {element.category.slug:20} | "
                f"Associations: {assoc_w_count}"
            )

        # 5. Check for orphaned associations (pointing to non-existent warnings)
        logger.info("\n" + "-" * 70)
        logger.info("Checking for orphaned associations (invalid warning_id)...")
        logger.info("-" * 70)

        result = await session.execute(
            select(ElementWarningAssociation)
            .outerjoin(Warning, Warning.id == ElementWarningAssociation.warning_id)
            .where(Warning.id.is_(None))
        )
        orphaned = result.scalars().all()

        if orphaned:
            logger.warning(f"⚠️  Found {len(orphaned)} orphaned associations (no matching warning)")
            for assoc in orphaned[:5]:
                logger.warning(f"   - Association ID: {assoc.id}, Warning ID: {assoc.warning_id}")
        else:
            logger.info("✅ No orphaned associations found")

        # 6. SQL verification query for manual use
        logger.info("\n" + "-" * 70)
        logger.info("SQL Verification Query (can be run manually)")
        logger.info("-" * 70)
        logger.info("""
SELECT
    e.code AS element_code,
    w.code AS warning_code,
    ewa.show_condition
FROM element_warning_associations ewa
JOIN elements e ON e.id = ewa.element_id
JOIN warnings w ON w.id = ewa.warning_id
LIMIT 10;
        """)

        logger.info("\n" + "=" * 70)
        logger.info("Verification Complete")
        logger.info("=" * 70 + "\n")


async def main() -> None:
    """Main entry point."""
    try:
        await verify_sync()
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
