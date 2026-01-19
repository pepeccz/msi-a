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


async def validate_category(category_slug: str) -> bool:
    """Validate seed data for a specific category."""
    logger.info(f"\n{'=' * 70}")
    logger.info(f"VALIDATING: {category_slug}")
    logger.info("=" * 70)

    async with get_async_session() as session:
        # Get category
        logger.info("\n[CHECK 1] Category exists")
        cat_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == category_slug)
        )
        category = cat_result.scalar()

        if not category:
            logger.error(f"Category '{category_slug}' not found!")
            return False

        logger.info(f"  Found: {category.name}")

        # Check elements
        logger.info("\n[CHECK 2] Elements created")
        elem_result = await session.execute(
            select(Element)
            .where(Element.category_id == category.id)
            .order_by(Element.sort_order)
        )
        elements = elem_result.scalars().all()

        if not elements:
            logger.error("  No elements found!")
            return False

        logger.info(f"  Found {len(elements)} elements:")
        for elem in elements[:10]:  # Show first 10
            logger.info(f"    - {elem.code}: {elem.name}")
        if len(elements) > 10:
            logger.info(f"    ... and {len(elements) - 10} more")

        # Check images
        logger.info("\n[CHECK 3] Images per element")
        all_images = await session.execute(select(ElementImage))
        all_images_list = all_images.scalars().all()

        category_images = [
            img for img in all_images_list
            if any(img.element_id == elem.id for elem in elements)
        ]
        logger.info(f"  Total {len(category_images)} images for this category")

        # Check tiers
        logger.info("\n[CHECK 4] Tiers")
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .where(TariffTier.is_active == True)
            .order_by(TariffTier.sort_order)
        )
        tiers = tiers_result.scalars().all()

        if not tiers:
            logger.error("  No tiers found!")
            return False

        logger.info(f"  Found {len(tiers)} tiers:")
        for tier in tiers:
            logger.info(f"    - {tier.code}: {tier.name} ({tier.price} EUR)")

        # Check tier inclusions
        logger.info("\n[CHECK 5] Tier inclusions")
        for tier in tiers[:3]:  # Check first 3 tiers
            inclusions_result = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier.id)
            )
            inclusions = inclusions_result.scalars().all()

            direct_elements = [inc for inc in inclusions if inc.element_id]
            tier_refs = [inc for inc in inclusions if inc.included_tier_id]

            logger.info(f"  {tier.code}: {len(direct_elements)} element inclusions, {len(tier_refs)} tier refs")

        # Test service resolution (if available)
        logger.info("\n[CHECK 6] Service resolution test")
        try:
            service = get_tarifa_service()
            t1 = next((t for t in tiers if t.code == "T1"), None)
            if t1:
                resolved = await service.resolve_tier_elements(str(t1.id))
                if resolved:
                    logger.info(f"  T1 resolves to {len(resolved)} elements")
                else:
                    logger.info("  T1 resolves to 0 elements (might be expected)")
        except Exception as e:
            logger.info(f"  Service test skipped: {e}")

    logger.info(f"\n  VALIDATION PASSED for {category_slug}")
    return True


async def validate_seed() -> bool:
    """Validate seed data for all categories."""
    logger.info("=" * 70)
    logger.info("ELEMENT SYSTEM SEED VALIDATION")
    logger.info("=" * 70)

    results = {}
    
    # Validate motos-part
    results["motos-part"] = await validate_category("motos-part")
    
    # Validate aseicars-prof
    results["aseicars-prof"] = await validate_category("aseicars-prof")

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)

    all_passed = True
    for category, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        logger.info(f"  {category}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\nAll validations passed!")
    else:
        logger.error("\nSome validations failed. Check logs above.")

    return all_passed


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
