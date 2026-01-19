"""
Verification Script: Element-Warning Synchronization

Verifies that inline warnings (warnings.element_id) are properly synced
with association warnings (element_warning_associations).

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
    VehicleCategory,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_sync() -> None:
    """Verify warning synchronization between inline and association systems."""

    async with get_async_session() as session:
        logger.info("=" * 70)
        logger.info("VERIFICATION: Element-Warning Synchronization")
        logger.info("=" * 70)

        # 1. Count inline warnings (warnings.element_id)
        result = await session.execute(
            select(func.count(Warning.id)).where(Warning.element_id.isnot(None))
        )
        inline_count = result.scalar()
        logger.info(f"\n✓ Inline warnings (warnings.element_id IS NOT NULL): {inline_count}")

        # 2. Count association warnings
        result = await session.execute(
            select(func.count(ElementWarningAssociation.id))
        )
        assoc_count = result.scalar()
        logger.info(f"✓ Association warnings (element_warning_associations): {assoc_count}")

        # 3. Check if counts match
        if inline_count == assoc_count and inline_count > 0:
            logger.info(f"\n✅ SUCCESS: Both systems have {inline_count} warnings (SYNCED)")
        elif inline_count == 0 and assoc_count == 0:
            logger.warning("\n⚠️  WARNING: No warnings found in either system")
        else:
            logger.error(
                f"\n❌ MISMATCH: Inline has {inline_count}, "
                f"Associations has {assoc_count}"
            )

        # 4. Verify data consistency (sample check)
        logger.info("\n" + "-" * 70)
        logger.info("Sample Data Verification (first 5 elements with warnings)")
        logger.info("-" * 70)

        result = await session.execute(
            select(Element)
            .join(Warning, Warning.element_id == Element.id)
            .options(selectinload(Element.category))
            .limit(5)
        )
        elements = result.scalars().unique().all()

        for element in elements:
            # Count inline warnings
            inline_result = await session.execute(
                select(func.count(Warning.id)).where(Warning.element_id == element.id)
            )
            inline_w_count = inline_result.scalar()

            # Count association warnings
            assoc_result = await session.execute(
                select(func.count(ElementWarningAssociation.id))
                .where(ElementWarningAssociation.element_id == element.id)
            )
            assoc_w_count = assoc_result.scalar()

            status = "✅" if inline_w_count == assoc_w_count else "❌"
            logger.info(
                f"{status} {element.code:20} | Category: {element.category.slug:20} | "
                f"Inline: {inline_w_count} | Associations: {assoc_w_count}"
            )

        # 5. Find orphaned warnings (in associations but not inline)
        logger.info("\n" + "-" * 70)
        logger.info("Checking for orphaned associations...")
        logger.info("-" * 70)

        result = await session.execute(
            select(ElementWarningAssociation)
            .outerjoin(Warning, Warning.id == ElementWarningAssociation.warning_id)
            .where(Warning.element_id.is_(None))
        )
        orphaned = result.scalars().all()

        if orphaned:
            logger.warning(f"⚠️  Found {len(orphaned)} orphaned associations (no inline warning)")
            for assoc in orphaned[:5]:  # Show first 5
                logger.warning(f"   - Association ID: {assoc.id}, Warning ID: {assoc.warning_id}")
        else:
            logger.info("✅ No orphaned associations found")

        # 6. SQL Verification Query
        logger.info("\n" + "-" * 70)
        logger.info("SQL Verification Query (can be run manually)")
        logger.info("-" * 70)
        logger.info("""
SELECT
    e.code AS element_code,
    w.code AS warning_code,
    CASE
        WHEN w.element_id IS NOT NULL THEN '✓'
        ELSE '✗'
    END AS inline,
    CASE
        WHEN ewa.id IS NOT NULL THEN '✓'
        ELSE '✗'
    END AS association
FROM elements e
LEFT JOIN warnings w ON w.element_id = e.id
LEFT JOIN element_warning_associations ewa ON ewa.element_id = e.id AND ewa.warning_id = w.id
WHERE w.id IS NOT NULL
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
