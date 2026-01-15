"""
MSI Automotive - Tier Element Inclusions Seed

Creates the TierElementInclusion relationships based on the official
2026 tariff PDFs:
- 2026 TARIFAS USUARIOS FINALES MOTO.pdf
- 2026 TARIFAS PROFESIONALES REGULARIZACION ELEMENTOS AUTOCARAVANAS.pdf

This seed maps which elements are available in each tariff tier,
following the hierarchical structure defined in the PDFs.
"""

import asyncio
import logging
from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    TierElementInclusion,
)
from database.seeds.seed_utils import (
    deterministic_tier_inclusion_uuid,
    deterministic_tier_to_tier_uuid,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# MOTOS-PART: Element-Tier Mapping based on PDF
# =============================================================================
# Structure from "2026 TARIFAS USUARIOS FINALES MOTO":
#
# T6 (€140): 1 elemento de lista T4
# T5 (€175): Hasta 2 elementos de T4
# T4 (€220): 2+ elementos sin proyecto (lista base)
# T3 (€280): 1 elemento T3 + hasta 2 de T4 (proyecto sencillo)
# T2 (€325): 1-2 elementos T3 + hasta 4 de T4 (proyecto medio)
# T1 (€410): Proyecto completo - todo incluido
# =============================================================================

MOTOS_TIER_STRUCTURE = {
    # T4/T5/T6 elements (sin proyecto - lista base)
    "T4_ELEMENTS": [
        "MATRICULA",       # Cambio emplazamiento de matrícula
        "FILTRO",          # Modificación de filtro
        "ESCAPE",          # Sustitución línea completa escape
        "DEPOSITO",        # Sustitución/reubicación depósito combustible
        "NEUMATICOS",      # Sustitución neumáticos (sin ensayo)
        "LLANTAS",         # Sustitución llantas (sin ensayo)
        "MANILLAR",        # Sustitución manillar/semimanillares
        "VELOCIMETRO",     # Sustitución de velocímetro
        "CABALLETE",       # Anulación o sustitución caballete
        "ESPEJOS",         # Sustitución espejos retrovisores
        "ALUMBRADO",       # Instalación nuevo alumbrado, faros
        "INTERMITENTES",   # Sustitución intermitentes, piloto trasero
    ],

    # T3 elements (proyecto sencillo - requieren proyecto)
    "T3_ELEMENTS": [
        "SUSPENSION_DEL",  # Cambio suspensión delantera (barras/muelles)
        "SUSPENSION_TRAS", # Cambio suspensión trasera
        "FRENADO",         # Cambios frenado por equivalentes (sin ensayo)
        "CARROCERIA",      # Eliminación/sustitución/adición carrocería
        # VELOCIMETRO también en T3 para "soporte velocímetro"
        # ALUMBRADO también en T3 para "soporte faro"
    ],

    # T1 elements (proyecto completo - requieren ensayos/proyecto complejo)
    # Estos elementos cuando son complejos van a T1:
    # - FRENADO con cambio de bomba/pinzas/discos
    # - LLANTAS/NEUMATICOS con ensayo
    # - Distancia entre ejes, subchasis, horquilla completa, cambio motor
    # Los elementos básicos no están en la seed aún (distancia_ejes, subchasis, motor)
}


# =============================================================================
# ASEICARS-PROF: Element-Tier Mapping based on PDF
# =============================================================================
# Structure from "2026 TARIFAS PROFESIONALES REGULARIZACION ELEMENTOS AUTOCARAVANAS":
#
# T6 (€59):  1 elemento (placas solares sin regulador, toldos, antenas)
# T5 (€65):  Hasta 3 elementos de T6 + placas con regulador en maletero
# T4 (€135): Sin límite T6 + ventanas/claraboyas/bola remolque sin proyecto
# T3 (€180): Todos T6 + 1 elemento (placas regulador interior, mobiliario, etc.)
# T2 (€230): Hasta 2 de T3 + todos T6 + 1 de (elevación, suspensión neumática, etc.)
# T1 (€270): Proyecto completo - sin límite de T2-T6 + suspensiones complejas
# =============================================================================

ASEICARS_TIER_STRUCTURE = {
    # T6 elements (1 elemento sin proyecto)
    "T6_ELEMENTS": [
        "PLACA_200W",      # Placas solares (hasta 2 uds sin regulador interior)
        "TOLDO_LAT",       # Toldos
        "ANTENA_PAR",      # Antenas parabólicas
    ],

    # T4 elements (regularización varios elementos sin proyecto)
    "T4_ELEMENTS": [
        "CLARABOYA",       # Incorporación/sustitución ventanas/claraboyas/portones
        "BOLA_REMOLQUE",   # Bola de remolque sin proyecto
        # Otros elementos T4 no están en seed actual:
        # - Neumáticos no equivalentes
        # - Aire acondicionado
        # - Galibos
        # - Luces adicionales
        # - Tomas externas gas/ducha
    ],

    # T3 elements (proyecto básico)
    "T3_ELEMENTS": [
        "PLACA_200W",      # Placas con regulador interior diferente a maletero
        "NEVERA_COMPRESOR", # Elementos eléctricos interior (inversor/batería)
        "DEPOSITO_AGUA",   # Podría requerir proyecto según instalación
        # Otros elementos T3 no están en seed actual:
        # - Mobiliario interior
        # - Sistema de gas interior
        # - Cerraduras exteriores
        # - Escalones eléctricos
        # - Cambio de clasificación
    ],

    # T2 elements (proyecto medio)
    "T2_ELEMENTS": [
        "BOLA_REMOLQUE",   # Bola con extensores de chasis o con proyecto
        "ESC_MEC",         # Escalera mecánica (kit elevación similar)
        "PORTABICIS",      # Soportes (similar a portamotos)
        "BACA_TECHO",      # Podría requerir refuerzos de suspensión
        # Otros elementos T2 no están en seed actual:
        # - Kit elevación hidráulica/eléctrica
        # - Suspensión neumática
        # - Refuerzos/sustitución sencillos suspensión
    ],
}


async def create_motos_inclusions():
    """Create tier-element inclusions for motos-part category."""
    logger.info("\n" + "=" * 70)
    logger.info("Creating MOTOS-PART Tier Inclusions")
    logger.info("=" * 70)

    async with get_async_session() as session:
        # Get category
        cat_result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "motos-part")
        )
        category = cat_result.scalar()
        if not category:
            logger.error("Category 'motos-part' not found!")
            return False

        # Get all tiers
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .order_by(TariffTier.sort_order)
        )
        tiers = {t.code: t for t in tiers_result.scalars().all()}

        # Get all elements
        elements_result = await session.execute(
            select(Element).where(Element.category_id == category.id)
        )
        elements = {e.code: e for e in elements_result.scalars().all()}

        if not elements:
            logger.error("No elements found for motos-part!")
            return False

        logger.info(f"Found {len(elements)} elements and {len(tiers)} tiers")

        # NOTA: Usamos UUIDs determinísticos para idempotencia
        inclusions_created = 0
        inclusions_skipped = 0
        category_slug = "motos-part"

        async def ensure_inclusion(tier_code, element_code=None, included_tier_code=None,
                                   min_qty=None, max_qty=None, notes=None):
            """Crea o actualiza inclusión con UUID determinístico."""
            nonlocal inclusions_created, inclusions_skipped

            tier_id = tiers[tier_code].id

            if element_code:
                # Tier-element inclusion
                element_id = elements[element_code].id
                inc_id = deterministic_tier_inclusion_uuid(category_slug, tier_code, element_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.element_id = element_id
                    existing.min_quantity = min_qty
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        element_id=element_id,
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True
            elif included_tier_code:
                # Tier-to-tier inclusion
                included_tier_id = tiers[included_tier_code].id
                inc_id = deterministic_tier_to_tier_uuid(category_slug, tier_code, included_tier_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.included_tier_id = included_tier_id
                    existing.min_quantity = min_qty
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        included_tier_id=included_tier_id,
                        min_quantity=min_qty,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True

            return False

        t4_elements = MOTOS_TIER_STRUCTURE["T4_ELEMENTS"]
        t3_elements = MOTOS_TIER_STRUCTURE["T3_ELEMENTS"]

        # T6 (€140): 1 elemento de lista T4
        if "T6" in tiers:
            logger.info("\nT6 (€140) - 1 elemento sin proyecto:")
            for code in t4_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T6",
                        element_code=code,
                        max_qty=1,
                        notes="Solo 1 elemento de esta lista",
                    )
                    if created:
                        logger.info(f"  + {code}")

        # T5 (€175): Hasta 2 elementos de T4
        if "T5" in tiers:
            logger.info("\nT5 (€175) - Hasta 2 elementos sin proyecto:")
            for code in t4_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T5",
                        element_code=code,
                        max_qty=2,
                        notes="Hasta 2 elementos de la lista T4",
                    )
                    if created:
                        logger.info(f"  + {code} (max 2)")

        # T4 (€220): 2+ elementos sin proyecto
        if "T4" in tiers:
            logger.info("\nT4 (€220) - Varios elementos sin proyecto (2+):")
            for code in t4_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T4",
                        element_code=code,
                        min_qty=2,
                        max_qty=10,
                        notes="A partir de 2 elementos sin proyecto",
                    )
                    if created:
                        logger.info(f"  + {code} (min 2)")

        # T3 (€280): 1 elemento T3 + hasta 2 de T4 (proyecto sencillo)
        if "T3" in tiers:
            logger.info("\nT3 (€280) - Proyecto sencillo:")
            # Elementos específicos de T3 (requieren proyecto)
            for code in t3_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=1,
                        notes="1 elemento con proyecto sencillo",
                    )
                    if created:
                        logger.info(f"  + {code} (proyecto sencillo)")

            # También puede incluir hasta 2 de T4
            for code in t4_elements:
                if code in elements and code not in t3_elements:
                    created = await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=2,
                        notes="Hasta 2 elementos adicionales de T4",
                    )
                    if created:
                        logger.info(f"  + {code} (adicional T4, max 2)")

        # T2 (€325): 1-2 de T3 + hasta 4 de T4 (proyecto medio)
        if "T2" in tiers:
            logger.info("\nT2 (€325) - Proyecto medio:")
            # Hasta 2 elementos de T3
            for code in t3_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T2",
                        element_code=code,
                        max_qty=2,
                        notes="Hasta 2 elementos con proyecto",
                    )
                    if created:
                        logger.info(f"  + {code} (proyecto, max 2)")

            # Hasta 4 elementos de T4
            for code in t4_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T2",
                        element_code=code,
                        max_qty=4,
                        notes="Hasta 4 elementos sin proyecto",
                    )
                    if created:
                        logger.info(f"  + {code} (sin proyecto, max 4)")

        # T1 (€410): Proyecto completo - todos los elementos sin límite
        if "T1" in tiers:
            logger.info("\nT1 (€410) - Proyecto completo:")
            # Incluye T2 (que ya incluye T3 y T4)
            if "T2" in tiers:
                created = await ensure_inclusion(
                    tier_code="T1",
                    included_tier_code="T2",
                    notes="Incluye todos los elementos de T2 y inferiores",
                )
                if created:
                    logger.info(f"  + Incluye tier T2 (y por extensión T3, T4)")

            # Todos los elementos sin límite
            all_elements = set(t3_elements + t4_elements)
            for code in all_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T1",
                        element_code=code,
                        max_qty=None,
                        notes="Proyecto completo - sin límite de elementos",
                    )
                    if created:
                        logger.info(f"  + {code} (sin límite)")

        await session.commit()
        logger.info(f"\nMotos inclusions: {inclusions_created} created, {inclusions_skipped} already existed")
        return True


async def create_aseicars_inclusions():
    """Create tier-element inclusions for aseicars-prof category."""
    logger.info("\n" + "=" * 70)
    logger.info("Creating ASEICARS-PROF Tier Inclusions")
    logger.info("=" * 70)

    async with get_async_session() as session:
        # Get category
        cat_result = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == "aseicars-prof")
        )
        category = cat_result.scalar()
        if not category:
            logger.error("Category 'aseicars-prof' not found!")
            return False

        # Get all tiers
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .order_by(TariffTier.sort_order)
        )
        tiers = {t.code: t for t in tiers_result.scalars().all()}

        # Get all elements
        elements_result = await session.execute(
            select(Element).where(Element.category_id == category.id)
        )
        elements = {e.code: e for e in elements_result.scalars().all()}

        if not elements:
            logger.error("No elements found for aseicars-prof!")
            return False

        logger.info(f"Found {len(elements)} elements and {len(tiers)} tiers")

        # NOTA: Usamos UUIDs determinísticos para idempotencia
        inclusions_created = 0
        inclusions_skipped = 0
        category_slug = "aseicars-prof"

        async def ensure_inclusion(tier_code, element_code=None, included_tier_code=None,
                                   max_qty=None, notes=None):
            """Crea o actualiza inclusión con UUID determinístico."""
            nonlocal inclusions_created, inclusions_skipped

            tier_id = tiers[tier_code].id

            if element_code:
                # Tier-element inclusion
                element_id = elements[element_code].id
                inc_id = deterministic_tier_inclusion_uuid(category_slug, tier_code, element_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.element_id = element_id
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        element_id=element_id,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True
            elif included_tier_code:
                # Tier-to-tier inclusion
                included_tier_id = tiers[included_tier_code].id
                inc_id = deterministic_tier_to_tier_uuid(category_slug, tier_code, included_tier_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.included_tier_id = included_tier_id
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        included_tier_id=included_tier_id,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True

            return False

        t6_elements = ASEICARS_TIER_STRUCTURE["T6_ELEMENTS"]
        t4_elements = ASEICARS_TIER_STRUCTURE["T4_ELEMENTS"]
        t3_elements = ASEICARS_TIER_STRUCTURE["T3_ELEMENTS"]
        t2_elements = ASEICARS_TIER_STRUCTURE["T2_ELEMENTS"]

        # T6 (€59): 1 elemento sin proyecto
        if "T6" in tiers:
            logger.info("\nT6 (€59) - 1 elemento sin proyecto:")
            for code in t6_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T6",
                        element_code=code,
                        max_qty=1,
                        notes="Solo 1 elemento (placas sin regulador, toldo, antena)",
                    )
                    if created:
                        logger.info(f"  + {code}")

        # T5 (€65): Hasta 3 elementos de T6
        if "T5" in tiers:
            logger.info("\nT5 (€65) - Hasta 3 elementos:")
            for code in t6_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T5",
                        element_code=code,
                        max_qty=3,
                        notes="Hasta 3 elementos de T6 + placas con regulador en maletero",
                    )
                    if created:
                        logger.info(f"  + {code} (max 3)")

        # T4 (€135): Sin límite T6 + elementos adicionales
        if "T4" in tiers:
            logger.info("\nT4 (€135) - Varios elementos sin proyecto:")
            # Todos los de T6 sin límite
            for code in t6_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T4",
                        element_code=code,
                        max_qty=None,
                        notes="Sin límite de elementos T6",
                    )
                    if created:
                        logger.info(f"  + {code} (sin límite)")

            # Elementos específicos de T4
            for code in t4_elements:
                if code in elements and code not in t6_elements:
                    created = await ensure_inclusion(
                        tier_code="T4",
                        element_code=code,
                        max_qty=None,
                        notes="Elemento adicional T4 (ventanas, bola remolque, etc.)",
                    )
                    if created:
                        logger.info(f"  + {code} (T4 específico)")

        # T3 (€180): Proyecto básico
        if "T3" in tiers:
            logger.info("\nT3 (€180) - Proyecto básico:")
            # Todos los de T6
            for code in t6_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=None,
                        notes="Todos los elementos de T6",
                    )
                    if created:
                        logger.info(f"  + {code} (T6)")

            # Hasta 1 elemento T3 específico
            for code in t3_elements:
                if code in elements and code not in t6_elements:
                    created = await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=1,
                        notes="Hasta 1 elemento con proyecto básico",
                    )
                    if created:
                        logger.info(f"  + {code} (proyecto básico, max 1)")

        # T2 (€230): Proyecto medio
        if "T2" in tiers:
            logger.info("\nT2 (€230) - Proyecto medio:")
            # Todos los de T6 sin límite
            for code in t6_elements:
                if code in elements:
                    created = await ensure_inclusion(
                        tier_code="T2",
                        element_code=code,
                        max_qty=None,
                        notes="Todos los elementos de T6",
                    )
                    if created:
                        logger.info(f"  + {code} (T6)")

            # Hasta 2 elementos de T3
            for code in t3_elements:
                if code in elements and code not in t6_elements:
                    created = await ensure_inclusion(
                        tier_code="T2",
                        element_code=code,
                        max_qty=2,
                        notes="Hasta 2 elementos de T3",
                    )
                    if created:
                        logger.info(f"  + {code} (T3, max 2)")

            # 1 elemento específico de T2
            for code in t2_elements:
                if code in elements and code not in t3_elements and code not in t6_elements:
                    created = await ensure_inclusion(
                        tier_code="T2",
                        element_code=code,
                        max_qty=1,
                        notes="1 elemento proyecto medio (elevación, suspensión, etc.)",
                    )
                    if created:
                        logger.info(f"  + {code} (T2 específico, max 1)")

        # T1 (€270): Proyecto completo
        if "T1" in tiers:
            logger.info("\nT1 (€270) - Proyecto completo:")
            # Incluye T2
            if "T2" in tiers:
                created = await ensure_inclusion(
                    tier_code="T1",
                    included_tier_code="T2",
                    notes="Incluye todos los elementos de T2 y inferiores",
                )
                if created:
                    logger.info(f"  + Incluye tier T2")

            # Todos los elementos sin límite
            for code in elements.keys():
                created = await ensure_inclusion(
                    tier_code="T1",
                    element_code=code,
                    max_qty=None,
                    notes="Proyecto completo - sin límite",
                )
                if created:
                    logger.info(f"  + {code} (sin límite)")

        await session.commit()
        logger.info(f"\nAseicars inclusions: {inclusions_created} created, {inclusions_skipped} already existed")
        return True


async def seed_tier_inclusions():
    """Main function to seed all tier-element inclusions."""
    logger.info("\n" + "=" * 80)
    logger.info("TIER ELEMENT INCLUSIONS SEED")
    logger.info("Based on 2026 Official Tariff PDFs")
    logger.info("=" * 80)

    motos_ok = await create_motos_inclusions()
    aseicars_ok = await create_aseicars_inclusions()

    if motos_ok and aseicars_ok:
        logger.info("\n" + "=" * 80)
        logger.info("✓ ALL TIER INCLUSIONS SEEDED SUCCESSFULLY")
        logger.info("=" * 80)
        logger.info("\nSummary:")
        logger.info("  - motos-part: T1-T6 inclusions based on PDF")
        logger.info("  - aseicars-prof: T1-T6 inclusions based on PDF")
        logger.info("\nStructure:")
        logger.info("  MOTOS:")
        logger.info("    T6 (€140): 1 elem | T5 (€175): 2 elem | T4 (€220): 2+ elem")
        logger.info("    T3 (€280): proyecto sencillo | T2 (€325): proyecto medio")
        logger.info("    T1 (€410): proyecto completo")
        logger.info("  ASEICARS:")
        logger.info("    T6 (€59): 1 elem | T5 (€65): 3 elem | T4 (€135): varios")
        logger.info("    T3 (€180): básico | T2 (€230): medio | T1 (€270): completo")
        return True

    return False


if __name__ == "__main__":
    asyncio.run(seed_tier_inclusions())
