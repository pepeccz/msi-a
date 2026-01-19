"""
MSI Automotive - Run all seeds for the new architecture.

This script seeds all categories with the updated architecture where
client_type is at the VehicleCategory level (not TariffTier).

Categories created:
- motos-part: Motocicletas para particulares
- aseicars-prof: Autocaravanas para profesionales

Elements created (from PDFs):
- aseicars elements: ~30 elements from autocaravanas PDF (with inline warnings)
- motos elements: 39 elements from motos PDF (with inline warnings)

Warnings:
- Category-scoped warnings are created with the category seed
- Element-scoped warnings are created inline with each element

Tier Inclusions:
- Maps elements to tiers based on 2026 tariff PDFs
- Defines quantities and constraints per tier level

IMPORTANT: Seeds are now MANUAL only.
Run with: python -m database.seeds.run_all_seeds
"""

import asyncio
import logging

from database.seeds.motos_particular_seed import seed_motos_particular
from database.seeds.aseicars_professional_seed import seed_aseicars_professional
from database.seeds.elements_from_pdf_seed import seed_elements as seed_aseicars_elements
from database.seeds.motos_elements_seed import seed_motos_elements
from database.seeds.tier_inclusions_seed import seed_tier_inclusions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_all_seeds():
    """Run all seed scripts."""
    logger.info("=" * 60)
    logger.info("Starting MSI-a database seeding (manual execution)")
    logger.info("=" * 60)

    # Seed motos particular (category + tiers + category warnings)
    logger.info("\n[1/5] Seeding motos-part (Motocicletas Particular)...")
    await seed_motos_particular()

    # Seed aseicars professional (category + tiers + category warnings)
    logger.info("\n[2/5] Seeding aseicars-prof (Autocaravanas Profesional)...")
    await seed_aseicars_professional()

    # Seed aseicars elements (from PDF) - includes inline element warnings
    logger.info("\n[3/5] Seeding aseicars elements + warnings (from PDF)...")
    await seed_aseicars_elements()

    # Seed motos elements (from PDF) - includes inline element warnings
    logger.info("\n[4/5] Seeding motos elements + warnings (from PDF)...")
    await seed_motos_elements()

    # Seed tier-element inclusions (based on 2026 tariff PDFs)
    logger.info("\n[5/5] Seeding tier-element inclusions (from tariff PDFs)...")
    await seed_tier_inclusions()

    logger.info("\n" + "=" * 60)
    logger.info("All seeds completed successfully!")
    logger.info("=" * 60)
    logger.info("\nCategories created:")
    logger.info("  - motos-part (Motocicletas - Particular)")
    logger.info("  - aseicars-prof (Autocaravanas - Profesional)")
    logger.info("\nElements created (with inline warnings):")
    logger.info("  - aseicars: ~30 elements (escalera, toldo, placa solar, etc.)")
    logger.info("  - motos: 39 elements (escape, suspension, frenos, etc.)")
    logger.info("\nWarnings:")
    logger.info("  - Category-scoped: created with category seeds")
    logger.info("  - Element-scoped: created inline with element seeds")
    logger.info("\nTier Inclusions (from 2026 tariff PDFs):")
    logger.info("  - motos-part: T1-T6 element mappings with quantity limits")
    logger.info("  - aseicars-prof: T1-T6 element mappings with quantity limits")


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
