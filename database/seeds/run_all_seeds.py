"""
MSI Automotive - Run all seeds.

This script seeds all categories using the refactored architecture:
- data/: Contains all seed data definitions (constants)
- seeders/: Contains reusable seeding logic

Categories seeded:
- motos-part: Motocicletas para particulares (39 elements)
- aseicars-prof: Autocaravanas para profesionales (~30 elements)

Run with: python -m database.seeds.run_all_seeds
"""

import asyncio
import logging
from types import ModuleType

from database.connection import get_async_session
from database.seeds.data import motos_part, aseicars_prof
from database.seeds.seeders import CategorySeeder, ElementSeeder, InclusionSeeder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_category(data_module: ModuleType) -> bool:
    """
    Seed a complete category with all its data.
    
    Args:
        data_module: Module containing CATEGORY, TIERS, ELEMENTS, etc.
    
    Returns:
        True if successful, False otherwise.
    """
    category_slug = data_module.CATEGORY_SLUG
    
    logger.info("=" * 70)
    logger.info(f"Seeding category: {category_slug}")
    logger.info("=" * 70)

    try:
        async with get_async_session() as session:
            # 1. Seed category-level data (category, tiers, warnings, services, docs, prompts)
            logger.info("\n[STEP 1] Seeding category-level data...")
            cat_seeder = CategorySeeder(category_slug, session)
            category, tiers = await cat_seeder.seed(
                category=data_module.CATEGORY,
                tiers=data_module.TIERS,
                category_warnings=data_module.CATEGORY_WARNINGS,
                services=data_module.ADDITIONAL_SERVICES,
                base_docs=data_module.BASE_DOCUMENTATION,
                prompt_sections=data_module.PROMPT_SECTIONS,
            )

            # 2. Seed elements (with inline warnings and images)
            logger.info("\n[STEP 2] Seeding elements...")
            elem_seeder = ElementSeeder(category_slug, session)
            elements = await elem_seeder.seed(
                category_id=category.id,
                elements=data_module.ELEMENTS,
            )

            # 3. Seed tier-element inclusions
            logger.info("\n[STEP 3] Seeding tier inclusions...")
            inc_seeder = InclusionSeeder(category_slug, session)
            await inc_seeder.seed(
                tiers=tiers,
                elements=elements,
            )

            # Commit all changes
            logger.info("\n[STEP 4] Committing changes...")
            await session.commit()
            logger.info(f"Category {category_slug} seeded successfully!")
            return True

    except Exception as e:
        logger.error(f"Error seeding {category_slug}: {e}", exc_info=True)
        return False


async def run_all_seeds() -> None:
    """Run all seed scripts."""
    logger.info("=" * 70)
    logger.info("MSI-a Database Seeding")
    logger.info("=" * 70)

    results = {}

    # Seed motos-part
    logger.info("\n[1/2] Seeding motos-part (Motocicletas Particular)...")
    results["motos-part"] = await seed_category(motos_part)

    # Seed aseicars-prof
    logger.info("\n[2/2] Seeding aseicars-prof (Autocaravanas Profesional)...")
    results["aseicars-prof"] = await seed_category(aseicars_prof)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SEEDING SUMMARY")
    logger.info("=" * 70)

    all_success = True
    for category, success in results.items():
        status = "OK" if success else "FAILED"
        logger.info(f"  {category}: {status}")
        if not success:
            all_success = False

    if all_success:
        logger.info("\nAll seeds completed successfully!")
        logger.info("\nCategories seeded:")
        logger.info(f"  - motos-part: {len(motos_part.ELEMENTS)} elements, {len(motos_part.TIERS)} tiers")
        logger.info(f"  - aseicars-prof: {len(aseicars_prof.ELEMENTS)} elements, {len(aseicars_prof.TIERS)} tiers")
    else:
        logger.error("\nSome seeds failed. Check logs above for details.")


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
