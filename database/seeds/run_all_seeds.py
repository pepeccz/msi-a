"""
MSI Automotive - Run all seeds for the new architecture.

This script seeds all categories with the updated architecture where
client_type is at the VehicleCategory level (not TariffTier).

Categories created:
- motos-part: Motocicletas para particulares
- aseicars-prof: Autocaravanas para profesionales

Elements created (from PDFs):
- aseicars elements: 10 elements from autocaravanas PDF
- motos elements: 18 elements from motos PDF

Run with: python -m database.seeds.run_all_seeds
"""

import asyncio
import logging

from database.seeds.motos_particular_seed import seed_motos_particular
from database.seeds.aseicars_professional_seed import seed_aseicars_professional
from database.seeds.elements_from_pdf_seed import seed_elements as seed_aseicars_elements
from database.seeds.motos_elements_seed import seed_motos_elements

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_all_seeds():
    """Run all seed scripts."""
    logger.info("=" * 60)
    logger.info("Starting MSI-a database seeding (new architecture)")
    logger.info("=" * 60)

    # Seed motos particular (category + tiers)
    logger.info("\n[1/4] Seeding motos-part (Motocicletas Particular)...")
    await seed_motos_particular()

    # Seed aseicars professional (category + tiers)
    logger.info("\n[2/4] Seeding aseicars-prof (Autocaravanas Profesional)...")
    await seed_aseicars_professional()

    # Seed aseicars elements (from PDF)
    logger.info("\n[3/4] Seeding aseicars elements (from PDF)...")
    await seed_aseicars_elements()

    # Seed motos elements (from PDF)
    logger.info("\n[4/4] Seeding motos elements (from PDF)...")
    await seed_motos_elements()

    logger.info("\n" + "=" * 60)
    logger.info("All seeds completed successfully!")
    logger.info("=" * 60)
    logger.info("\nCategories created:")
    logger.info("  - motos-part (Motocicletas - Particular)")
    logger.info("  - aseicars-prof (Autocaravanas - Profesional)")
    logger.info("\nElements created:")
    logger.info("  - aseicars: 10 elements (escalera, toldo, placa solar, etc.)")
    logger.info("  - motos: 18 elements (escape, suspension, frenos, etc.)")
    logger.info("\nNote: To add more categories (motos-prof, aseicars-part),")
    logger.info("create new seed files following the same pattern.")


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
