"""
MSI Automotive - Seed data for Element System (Hierarchical Tariffs).

This script populates the database with:
1. Element catalog (homologable elements)
2. Element images (multiple per element with different types)
3. Tier element inclusions (references between tiers and elements)

Based on the PDF structure for "Autocaravanas Profesional" (aseicars-prof).

Run with: python -m database.seeds.elements_from_pdf_seed
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    ElementImage,
    TierElementInclusion,
)
from database.seeds.seed_utils import (
    deterministic_element_uuid,
    deterministic_element_image_uuid,
    deterministic_tier_inclusion_uuid,
    deterministic_tier_to_tier_uuid,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Category slug for this seed
CATEGORY_SLUG = "aseicars-prof"

# =============================================================================
# Element Definitions - Autocaravanas Profesional
# =============================================================================
# Based on PDF tariff structure for aseicars-prof category

ELEMENTS = [
    {
        "code": "ESC_MEC",
        "name": "Escalera mecánica trasera",
        "description": "Escalera retráctil de accionamiento hidráulico instalada en parte trasera del vehículo",
        "keywords": ["escalera", "escalera mecánica", "escalera trasera", "escalera retráctil", "escalerilla"],
        "aliases": ["peldaños", "acceso techo"],
        "sort_order": 10,
        "images": [
            {
                "title": "Vista trasera cerrada",
                "description": "Escalera en posición de transporte, cerrada",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Vista trasera abierta",
                "description": "Escalera completamente desplegada",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto con matrícula",
                "description": "Foto con matrícula visible y escalera desplegada",
                "image_type": "required_document",
                "sort_order": 3,
                            },
            {
                "title": "Placa del fabricante",
                "description": "Placa del fabricante con número de serie y especificaciones",
                "image_type": "required_document",
                "sort_order": 4,
                            },
        ],
    },
    {
        "code": "TOLDO_LAT",
        "name": "Toldo lateral",
        "description": "Toldo retráctil instalado en lateral del vehículo",
        "keywords": ["toldo", "toldo lateral", "toldo retráctil", "lona"],
        "aliases": ["tolva", "parasol lateral"],
        "sort_order": 20,
        "images": [
            {
                "title": "Toldo cerrado",
                "description": "Toldo recogido en su posición de transporte",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Toldo extendido",
                "description": "Toldo completamente desplegado",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto extensión completa",
                "description": "Toldo completamente extendido con soportes",
                "image_type": "required_document",
                "sort_order": 3,
                            },
            {
                "title": "Placa identificativa",
                "description": "Placa del fabricante del toldo",
                "image_type": "required_document",
                "sort_order": 4,
                            },
        ],
    },
    {
        "code": "PLACA_200W",
        "name": "Placa solar >200W",
        "description": "Placa solar fotovoltaica de más de 200 vatios instalada en techo",
        "keywords": ["placa solar", "placa fotovoltaica", "solar", "panel solar", "200w"],
        "aliases": ["módulo solar", "panel"],
        "sort_order": 30,
        "images": [
            {
                "title": "Vista superior",
                "description": "Placa solar instalada en techo",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Detalle conexión",
                "description": "Detalle de la conexión eléctrica de la placa",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto con matrícula visible",
                "description": "Foto general del vehículo con placa visible y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
                            },
            {
                "title": "Certificado de especificaciones",
                "description": "Especificaciones técnicas de la placa (vatios, fabricante, etc)",
                "image_type": "required_document",
                "sort_order": 4,
                            },
        ],
    },
    {
        "code": "ANTENA_PAR",
        "name": "Antena parabólica",
        "description": "Antena parabólica para recepción de satélite",
        "keywords": ["antena", "antena parabólica", "parabólica", "satélite"],
        "aliases": ["dish", "receptor satélite"],
        "sort_order": 40,
        "images": [
            {
                "title": "Antena instalada",
                "description": "Antena parabólica instalada en techo",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto frontal",
                "description": "Foto frontal del vehículo con antena visible",
                "image_type": "required_document",
                "sort_order": 2,
                            },
        ],
    },
    {
        "code": "PORTABICIS",
        "name": "Portabicis trasero",
        "description": "Portabicis montado en la parte trasera del vehículo",
        "keywords": ["portabicis", "portabike", "bicicletas", "bike rack"],
        "aliases": ["soportebicis", "rack bicicletas"],
        "sort_order": 50,
        "images": [
            {
                "title": "Portabicis vacío",
                "description": "Portabicis sin bicicletas",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Con bicicletas",
                "description": "Portabicis con bicicletas instaladas",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto trasera con matrícula",
                "description": "Foto trasera del vehículo con portabicis y matrícula visible",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "CLARABOYA",
        "name": "Claraboya adicional",
        "description": "Claraboya o ventana cenital adicional en techo",
        "keywords": ["claraboya", "ventana techo", "lucernario", "ventilación"],
        "aliases": ["skylight", "ventana cenital"],
        "sort_order": 60,
        "images": [
            {
                "title": "Claraboya cerrada",
                "description": "Claraboya en posición cerrada",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto interior",
                "description": "Foto del interior mostrando la claraboya",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto exterior",
                "description": "Foto exterior del techo con claraboya visible",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "BACA_TECHO",
        "name": "Baca portaequipajes",
        "description": "Baca metálica para portaequipajes en techo",
        "keywords": ["baca", "portaequipajes", "roof rack", "rack techo"],
        "aliases": ["jaula techo", "soporte techo"],
        "sort_order": 70,
        "images": [
            {
                "title": "Baca vacía",
                "description": "Baca sin carga",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Detalle montaje",
                "description": "Detalle de cómo está montada la baca",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general del vehículo con baca visible y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "BOLA_REMOLQUE",
        "name": "Bola de remolque",
        "description": "Enganche de remolque tipo bola instalado en vehículo",
        "keywords": ["bola remolque", "enganche", "bola", "remolque"],
        "aliases": ["coupling", "tow ball"],
        "sort_order": 80,
        "images": [
            {
                "title": "Bola remolque",
                "description": "Bola de remolque instalada",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto trasera",
                "description": "Foto trasera del vehículo mostrando la bola de remolque",
                "image_type": "required_document",
                "sort_order": 2,
                            },
        ],
    },
    {
        "code": "NEVERA_COMPRESOR",
        "name": "Nevera de compresor",
        "description": "Nevera portátil con compresor de corriente continua",
        "keywords": ["nevera", "frigorífico", "compresor", "congelador"],
        "aliases": ["cooling box", "fridge"],
        "sort_order": 90,
        "images": [
            {
                "title": "Nevera instalada",
                "description": "Nevera de compresor instalada en interior",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto interior",
                "description": "Foto del interior mostrando la nevera",
                "image_type": "required_document",
                "sort_order": 2,
                            },
        ],
    },
    {
        "code": "DEPOSITO_AGUA",
        "name": "Depósito de agua adicional",
        "description": "Depósito de agua dulce adicional instalado en vehículo",
        "keywords": ["depósito agua", "tanque agua", "agua dulce", "depósito"],
        "aliases": ["water tank", "fresh water"],
        "sort_order": 100,
        "images": [
            {
                "title": "Depósito instalado",
                "description": "Depósito de agua adicional en exterior",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Placa identificativa",
                "description": "Placa con especificaciones del depósito",
                "image_type": "required_document",
                "sort_order": 2,
                            },
        ],
    },
]

# =============================================================================
# Placeholder Image URLs (replace with real URLs later)
# =============================================================================

def get_placeholder_image_url(element_code: str, image_title: str) -> str:
    """Generate a placeholder image URL."""
    # In production, these would be real S3/CDN URLs
    safe_title = image_title.lower().replace(" ", "_")
    return f"https://via.placeholder.com/400x300?text={element_code}_{safe_title}"


async def seed_elements():
    """Seed element system data."""
    logger.info("=" * 80)
    logger.info("Starting Element System Seed")
    logger.info("=" * 80)

    async with get_async_session() as session:
        # Step 1: Get or verify category exists
        logger.info("\n[STEP 1] Getting category: aseicars-prof")
        category_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "aseicars-prof")
            .where(VehicleCategory.is_active == True)
        )
        category = category_result.scalar()

        if not category:
            logger.error("Category 'aseicars-prof' not found. Run aseicars-prof_seed.py first!")
            return False

        logger.info(f"✓ Found category: {category.name} (ID: {category.id})")

        # Step 2: Get all tiers for this category
        logger.info("\n[STEP 2] Getting tiers for category")
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .where(TariffTier.is_active == True)
            .order_by(TariffTier.sort_order)
        )
        tiers = {t.code: t for t in tiers_result.scalars().all()}

        if not tiers:
            logger.error("No active tiers found for this category!")
            return False

        logger.info(f"✓ Found {len(tiers)} tiers:")
        for code, tier in tiers.items():
            logger.info(f"  - {code}: {tier.name} ({tier.price}€)")

        # Step 3: Upsert elements (create or update with deterministic UUIDs)
        logger.info("\n[STEP 3] Upserting elements")
        created_elements = {}
        created_count = 0
        updated_count = 0

        for elem_data in ELEMENTS:
            # Generar UUID determinístico basado en categoría y código
            element_id = deterministic_element_uuid("aseicars-prof", elem_data["code"])

            # Verificar si ya existe por UUID determinístico
            existing_element = await session.get(Element, element_id)

            if existing_element:
                # UPDATE: Actualizar campos de seed (preservar relaciones del usuario)
                existing_element.name = elem_data["name"]
                existing_element.description = elem_data["description"]
                existing_element.keywords = elem_data["keywords"]
                existing_element.aliases = elem_data["aliases"]
                existing_element.sort_order = elem_data["sort_order"]
                existing_element.is_active = True
                created_elements[elem_data["code"]] = existing_element
                updated_count += 1
                logger.info(f"  ~ {elem_data['code']}: Updated")
            else:
                # INSERT: Crear con UUID determinístico
                element = Element(
                    id=element_id,
                    category_id=category.id,
                    code=elem_data["code"],
                    name=elem_data["name"],
                    description=elem_data["description"],
                    keywords=elem_data["keywords"],
                    aliases=elem_data["aliases"],
                    is_active=True,
                    sort_order=elem_data["sort_order"],
                )
                session.add(element)
                await session.flush()

                # Crear imágenes para este elemento con UUIDs determinísticos
                for idx, img_data in enumerate(elem_data.get("images", [])):
                    image_id = deterministic_element_image_uuid(
                        "aseicars-prof",
                        elem_data["code"],
                        f"img_{idx + 1}"
                    )

                    # Verificar si la imagen ya existe
                    existing_img = await session.get(ElementImage, image_id)
                    if not existing_img:
                        image = ElementImage(
                            id=image_id,
                            element_id=element.id,
                            image_url=get_placeholder_image_url(
                                elem_data["code"],
                                img_data["title"]
                            ),
                            title=img_data["title"],
                            description=img_data["description"],
                            image_type=img_data["image_type"],
                            sort_order=img_data["sort_order"],
                        )
                        session.add(image)

                created_elements[elem_data["code"]] = element
                created_count += 1
                logger.info(f"  + {elem_data['code']}: Created with {len(elem_data.get('images', []))} images")

        await session.flush()
        logger.info(f"  Elements: {created_count} created, {updated_count} updated")

        # Step 4: Upsert tier element inclusions based on PDF structure
        # NOTA: Ya no borramos, verificamos existencia antes de crear
        logger.info("\n[STEP 4] Upserting tier element inclusions")
        logger.info("  According to PDF structure:")
        inclusions_created = 0
        inclusions_skipped = 0

        async def ensure_inclusion(tier_code, element_code=None, included_tier_code=None,
                                   max_qty=None, notes=None):
            """Crea o actualiza inclusión con UUID determinístico."""
            nonlocal inclusions_created, inclusions_skipped

            tier_id = tiers[tier_code].id

            if element_code:
                # Tier-element inclusion
                element_id = created_elements[element_code].id
                inc_id = deterministic_tier_inclusion_uuid(CATEGORY_SLUG, tier_code, element_code)

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
                inc_id = deterministic_tier_to_tier_uuid(CATEGORY_SLUG, tier_code, included_tier_code)

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

        # T6: Contains ANTENA_PAR, PORTABICIS (max 1 total)
        if "T6" in tiers:
            logger.info("  T6 (59€): ANTENA_PAR, PORTABICIS (max 1 each)")
            for code in ["ANTENA_PAR", "PORTABICIS"]:
                if code in created_elements:
                    await ensure_inclusion(
                        tier_code="T6",
                        element_code=code,
                        max_qty=None,
                        notes=f"T6 includes {code}",
                    )

        # T3: ESC_MEC (max 1), TOLDO_LAT (max 1), PLACA_200W (max 1), + unlimited T6
        if "T3" in tiers:
            logger.info("  T3 (180€): ESC_MEC, TOLDO_LAT, PLACA_200W (max 1 each) + T6 unlimited")
            for code, max_qty in [("ESC_MEC", 1), ("TOLDO_LAT", 1), ("PLACA_200W", 1)]:
                if code in created_elements:
                    await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=max_qty,
                        notes=f"T3 includes up to {max_qty} {code}",
                    )

            # T3 includes all of T6
            await ensure_inclusion(
                tier_code="T3",
                included_tier_code="T6",
                max_qty=None,
                notes="T3 includes all elements of T6 unlimited",
            )

        # T2: Up to 2 elements from T3 + unlimited T6
        if "T2" in tiers:
            logger.info("  T2 (230€): Up to 2 elements from T3 + T6 unlimited")
            await ensure_inclusion(
                tier_code="T2",
                included_tier_code="T3",
                max_qty=2,
                notes="T2 includes up to 2 elements from T3",
            )

            # T2 also includes T6 directly
            await ensure_inclusion(
                tier_code="T2",
                included_tier_code="T6",
                max_qty=None,
                notes="T2 includes all elements of T6 unlimited",
            )

        # T1: Unlimited everything (includes T2, T3, T4, T5, T6)
        if "T1" in tiers:
            logger.info("  T1 (270€): Unlimited everything (includes T2, T3, T4, T5, T6)")
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    await ensure_inclusion(
                        tier_code="T1",
                        included_tier_code=ref_tier_code,
                        max_qty=None,
                        notes=f"T1 includes all elements of {ref_tier_code} unlimited",
                    )

        logger.info(f"  Tier inclusions: {inclusions_created} created, {inclusions_skipped} already existed")

        # Step 5: Commit all changes
        logger.info("\n[STEP 5] Committing changes to database")
        try:
            await session.commit()
            logger.info("✓ Committed successfully")
        except Exception as e:
            logger.error(f"✗ Commit failed: {e}")
            await session.rollback()
            return False

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✓ SEED COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info(f"Created {len(created_elements)} elements")
    logger.info("Configured tier inclusions according to PDF structure")
    logger.info("\nNext steps:")
    logger.info("1. Verify in admin panel: /elementos")
    logger.info("2. Test element matching: /api/admin/elements")
    logger.info("3. Test tier resolution: /api/admin/tariff-tiers/{tier_id}/resolved-elements")
    logger.info("4. Run tests: pytest tests/test_element_system.py")

    return True


async def main():
    """Main entry point."""
    try:
        success = await seed_elements()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
