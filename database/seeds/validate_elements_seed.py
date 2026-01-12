"""
MSI Automotive - Validation script for Element System Seed Data.

Verifies that the seed data was created correctly and follows the PDF structure.

Run with: python -m database.seeds.validate_elements_seed
"""

import asyncio
import logging

from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    Element,
    ElementImage,
    TierElementInclusion,
    TariffTier,
)
from agent.services.tarifa_service import get_tarifa_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def validate_seed():
    """Validate seed data completeness and correctness."""
    logger.info("=" * 80)
    logger.info("VALIDATING ELEMENT SYSTEM SEED DATA")
    logger.info("=" * 80)

    async with get_async_session() as session:
        # Get category
        logger.info("\n[CHECK 1] Category exists")
        cat_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "aseicars-prof")
        )
        category = cat_result.scalar()

        if not category:
            logger.error("✗ Category 'aseicars-prof' not found!")
            return False

        logger.info(f"✓ Category found: {category.name}")

        # Check elements
        logger.info("\n[CHECK 2] Elements created")
        elem_result = await session.execute(
            select(Element)
            .where(Element.category_id == category.id)
            .order_by(Element.sort_order)
        )
        elements = elem_result.scalars().all()

        if not elements:
            logger.error("✗ No elements found!")
            return False

        logger.info(f"✓ Found {len(elements)} elements:")
        for elem in elements:
            logger.info(f"  • {elem.code}: {elem.name}")

        # Check images per element
        logger.info("\n[CHECK 3] Images per element")
        all_images = await session.execute(
            select(ElementImage)
        )
        all_images_list = all_images.scalars().all()

        logger.info(f"✓ Total {len(all_images_list)} images across all elements:")
        for elem in elements:
            images = [img for img in all_images_list if img.element_id == elem.id]
            required = [img for img in images if img.is_required]
            logger.info(
                f"  • {elem.code}: {len(images)} images "
                f"({len(required)} required, {len(images) - len(required)} examples)"
            )

        # Check tier inclusions
        logger.info("\n[CHECK 4] Tier inclusions (according to PDF)")
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .where(TariffTier.is_active == True)
            .order_by(TariffTier.sort_order)
        )
        tiers = tiers_result.scalars().all()

        logger.info(f"✓ Found {len(tiers)} tiers")

        for tier in tiers:
            inclusions_result = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier.id)
            )
            inclusions = inclusions_result.scalars().all()

            logger.info(f"\n  {tier.code} ({tier.name}) - {tier.price}€:")

            direct_elements = [
                inc for inc in inclusions if inc.element_id
            ]
            tier_refs = [inc for inc in inclusions if inc.included_tier_id]

            if direct_elements:
                logger.info(f"    Direct elements ({len(direct_elements)}):")
                for inc in direct_elements:
                    max_q = inc.max_quantity if inc.max_quantity else "unlimited"
                    logger.info(f"      • {inc.element.code}: max {max_q}")

            if tier_refs:
                logger.info(f"    Tier references ({len(tier_refs)}):")
                for inc in tier_refs:
                    max_q = inc.max_quantity if inc.max_quantity else "unlimited"
                    logger.info(
                        f"      • {inc.included_tier.code}: max {max_q}"
                    )

        # Test resolve_tier_elements algorithm
        logger.info("\n[CHECK 5] Testing tier element resolution")
        service = get_tarifa_service()

        for tier in tiers[:3]:  # Test first 3 tiers
            resolved = await service.resolve_tier_elements(str(tier.id))
            logger.info(f"\n  {tier.code} resolves to:")
            if resolved:
                for elem_id, max_qty in list(resolved.items())[:5]:
                    elem = next(
                        (e for e in elements if str(e.id) == elem_id),
                        None
                    )
                    if elem:
                        max_q = max_qty if max_qty else "unlimited"
                        logger.info(f"    • {elem.code}: max {max_q}")
                if len(resolved) > 5:
                    logger.info(f"    ... and {len(resolved) - 5} more")
            else:
                logger.info("    (no elements)")

        # Check that T1 includes all elements
        logger.info("\n[CHECK 6] PDF Structure Compliance")
        t1 = next((t for t in tiers if t.code == "T1"), None)
        if t1:
            t1_resolved = await service.resolve_tier_elements(str(t1.id))
            # T1 should include most elements
            expected_min = 8  # At least the main elements
            if len(t1_resolved) >= expected_min:
                logger.info(
                    f"✓ T1 includes {len(t1_resolved)} elements "
                    f"(expected >= {expected_min})"
                )
            else:
                logger.warning(
                    f"⚠ T1 includes {len(t1_resolved)} elements "
                    f"(expected >= {expected_min})"
                )

    logger.info("\n" + "=" * 80)
    logger.info("✓ VALIDATION COMPLETE")
    logger.info("=" * 80)
    logger.info("\nNext: Test in admin panel or API")
    logger.info("  Admin: http://localhost:3000/elementos")
    logger.info("  API: GET /api/admin/elements")

    return True


async def main():
    """Main entry point."""
    try:
        success = await validate_seed()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
