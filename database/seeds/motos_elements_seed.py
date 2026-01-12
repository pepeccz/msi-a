"""
MSI Automotive - Seed data for Element System (Motocicletas Particular).

This script populates the database with:
1. Element catalog (homologable elements for motorcycles)
2. Element images (multiple per element with different types)
3. Tier element inclusions (references between tiers and elements)

Based on the PDF structure for "Motocicletas Usuario Final" (motos-part).
PDF: 2026 TARIFAS USUARIOS FINALES MOTO.pdf

Tier Structure from PDF:
- T1 (410€): Proyecto completo - cualquier número de elementos
- T2 (325€): Proyecto medio - 1-2 de T3, hasta 4 de T4
- T3 (280€): Proyecto sencillo - 1 elemento principal + hasta 2 de T4
- T4 (220€): Sin proyecto varios elementos - 2+ elementos de lista
- T5 (175€): Sin proyecto 2 elementos - hasta 2 elementos
- T6 (140€): Sin proyecto 1 elemento - solo 1 elemento

Run with: python -m database.seeds.motos_elements_seed
"""

import asyncio
import logging

from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    ElementImage,
    TierElementInclusion,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Element Definitions - Motocicletas Particular
# =============================================================================
# Based on PDF tariff structure for motos-part category (2026 TARIFAS USUARIOS FINALES MOTO)

ELEMENTS = [
    {
        "code": "ESCAPE",
        "name": "Escape / Sistema de escape",
        "description": "Sistema de escape modificado, colector o silenciador aftermarket",
        "keywords": ["escape", "tubo de escape", "colector", "silenciador", "silencioso", "deportivo", "akrapovic", "yoshimura", "arrow", "termignoni", "sc project"],
        "aliases": ["exhaust", "muffler", "sistema escape"],
        "sort_order": 10,
        "images": [
            {
                "title": "Vista lateral escape",
                "description": "Escape instalado visto desde el lateral",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del escape con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
            {
                "title": "Homologación escape",
                "description": "Etiqueta o certificado de homologación del escape",
                "image_type": "required_document",
                "sort_order": 3,
                "is_required": True,
            },
        ],
    },
    {
        "code": "SUSPENSION_DEL",
        "name": "Suspensión delantera",
        "description": "Horquilla delantera modificada o aftermarket",
        "keywords": ["suspensión delantera", "horquilla", "suspensión", "amortiguador delantero", "fork", "ohlins", "showa", "wp"],
        "aliases": ["front suspension", "horquillas"],
        "sort_order": 20,
        "images": [
            {
                "title": "Vista frontal suspensión",
                "description": "Suspensión delantera vista de frente",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula visible",
                "description": "Foto general con suspensión y matrícula",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "SUSPENSION_TRAS",
        "name": "Suspensión trasera",
        "description": "Amortiguador trasero o mono modificado",
        "keywords": ["suspensión trasera", "amortiguador", "mono", "amortiguador trasero", "shock", "ohlins", "showa", "wp"],
        "aliases": ["rear suspension", "mono amortiguador"],
        "sort_order": 30,
        "images": [
            {
                "title": "Vista lateral suspensión",
                "description": "Amortiguador trasero visto desde el lateral",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general con suspensión trasera y matrícula",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "FRENADO",
        "name": "Sistema de frenado",
        "description": "Discos de freno, pinzas o latiguillos modificados",
        "keywords": ["frenos", "frenado", "disco", "discos", "pinza", "pinzas", "latiguillo", "latiguillos", "brembo", "galfer"],
        "aliases": ["brakes", "brake system"],
        "sort_order": 40,
        "images": [
            {
                "title": "Vista disco delantero",
                "description": "Disco de freno delantero",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto de frenos con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "CARROCERIA",
        "name": "Carrocería / Carenado",
        "description": "Carenado, semicarenado, guardabarros o colín modificados",
        "keywords": ["carrocería", "carenado", "semicarenado", "guardabarros", "colín", "colin", "cúpula", "cupula", "cubierta"],
        "aliases": ["bodywork", "fairing"],
        "sort_order": 50,
        "images": [
            {
                "title": "Vista general carenado",
                "description": "Carenado o carrocería instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general con carrocería y matrícula",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "MANILLAR",
        "name": "Manillar",
        "description": "Manillar modificado, guidón, clip-on o semimanillar",
        "keywords": ["manillar", "guidon", "guidón", "clip-on", "clipon", "semimanillar", "manillas", "puños"],
        "aliases": ["handlebar", "handlebars"],
        "sort_order": 60,
        "images": [
            {
                "title": "Vista frontal manillar",
                "description": "Manillar visto desde el frente",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del manillar con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "ALUMBRADO",
        "name": "Alumbrado / Faros",
        "description": "Faros delanteros, traseros o luces LED modificadas",
        "keywords": ["alumbrado", "faros", "luces", "led", "faro", "piloto", "antiniebla", "luz delantera", "luz trasera"],
        "aliases": ["lights", "lighting", "headlight"],
        "sort_order": 70,
        "images": [
            {
                "title": "Vista faros encendidos",
                "description": "Faros o luces encendidas",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto de luces con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "INTERMITENTES",
        "name": "Intermitentes",
        "description": "Intermitentes LED o aftermarket modificados",
        "keywords": ["intermitentes", "indicadores", "direccionales", "flashers", "led", "intermitente"],
        "aliases": ["turn signals", "indicators"],
        "sort_order": 80,
        "images": [
            {
                "title": "Vista intermitentes",
                "description": "Intermitentes instalados",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto con intermitentes y matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "ESPEJOS",
        "name": "Espejos / Retrovisores",
        "description": "Retrovisores modificados, aftermarket o eliminados",
        "keywords": ["espejos", "retrovisores", "retrovisor", "mirrors", "espejo"],
        "aliases": ["mirrors", "rearview"],
        "sort_order": 90,
        "images": [
            {
                "title": "Vista retrovisores",
                "description": "Retrovisores instalados",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto con retrovisores y matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "LLANTAS",
        "name": "Llantas",
        "description": "Llantas modificadas o de diferente tamaño",
        "keywords": ["llantas", "llanta", "ruedas", "rines", "rin", "wheels"],
        "aliases": ["wheels", "rims"],
        "sort_order": 100,
        "images": [
            {
                "title": "Vista llantas",
                "description": "Llantas instaladas",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto con llantas y matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "NEUMATICOS",
        "name": "Neumáticos",
        "description": "Neumáticos de diferente medida a la homologada",
        "keywords": ["neumáticos", "neumaticos", "ruedas", "cubiertas", "gomas", "tires"],
        "aliases": ["tires", "tyres"],
        "sort_order": 110,
        "images": [
            {
                "title": "Vista neumáticos",
                "description": "Neumáticos instalados",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto etiqueta neumático",
                "description": "Etiqueta del neumático con medidas",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "DEPOSITO",
        "name": "Depósito de combustible",
        "description": "Depósito de gasolina modificado o aftermarket",
        "keywords": ["depósito", "deposito", "tanque", "gasolina", "combustible", "fuel tank"],
        "aliases": ["fuel tank", "gas tank"],
        "sort_order": 120,
        "images": [
            {
                "title": "Vista depósito",
                "description": "Depósito de combustible instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del depósito con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "VELOCIMETRO",
        "name": "Velocímetro / Cuadro",
        "description": "Velocímetro, cuentakilómetros o cuadro de instrumentos modificado",
        "keywords": ["velocímetro", "velocimetro", "cuadro", "instrumentos", "cuentakilómetros", "cuentakilometros", "tacómetro", "tacometro"],
        "aliases": ["speedometer", "dashboard", "instruments"],
        "sort_order": 130,
        "images": [
            {
                "title": "Vista cuadro",
                "description": "Cuadro de instrumentos",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del velocímetro con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "CABALLETE",
        "name": "Caballete",
        "description": "Caballete central o lateral modificado",
        "keywords": ["caballete", "pata de cabra", "caballete central", "caballete lateral", "stand"],
        "aliases": ["kickstand", "center stand"],
        "sort_order": 140,
        "images": [
            {
                "title": "Vista caballete",
                "description": "Caballete instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del caballete con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "MATRICULA",
        "name": "Soporte de matrícula",
        "description": "Portamatrículas o soporte de matrícula modificado",
        "keywords": ["matrícula", "matricula", "portamatrícula", "portamatriculas", "soporte matrícula", "rabillo"],
        "aliases": ["license plate holder", "plate bracket"],
        "sort_order": 150,
        "images": [
            {
                "title": "Vista soporte matrícula",
                "description": "Soporte de matrícula instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto trasera",
                "description": "Foto trasera con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "FILTRO",
        "name": "Filtro de aire",
        "description": "Filtro de aire modificado o de alto rendimiento",
        "keywords": ["filtro", "filtro aire", "filtro de aire", "k&n", "bmc", "dna"],
        "aliases": ["air filter", "intake"],
        "sort_order": 160,
        "images": [
            {
                "title": "Vista filtro",
                "description": "Filtro de aire instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del filtro con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "ASIENTO",
        "name": "Asiento / Sillín",
        "description": "Asiento monoplaza, biplaza modificado o tapizado custom",
        "keywords": ["asiento", "sillín", "sillin", "monoplaza", "biplaza", "tapizado", "asiento custom"],
        "aliases": ["seat", "saddle"],
        "sort_order": 170,
        "images": [
            {
                "title": "Vista asiento",
                "description": "Asiento instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto del asiento con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
    {
        "code": "MALETAS",
        "name": "Maletas / Baúl",
        "description": "Maletas laterales, top case o alforjas",
        "keywords": ["maletas", "baúl", "baul", "topcase", "top case", "alforjas", "maleta", "cofre"],
        "aliases": ["luggage", "panniers", "saddlebags"],
        "sort_order": 180,
        "images": [
            {
                "title": "Vista maletas",
                "description": "Maletas o baúl instalado",
                "image_type": "example",
                "sort_order": 1,
                "is_required": False,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto de maletas con matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
                "is_required": True,
            },
        ],
    },
]


# =============================================================================
# Placeholder Image URLs (replace with real URLs later)
# =============================================================================

def get_placeholder_image_url(element_code: str, image_title: str) -> str:
    """Generate a placeholder image URL."""
    safe_title = image_title.lower().replace(" ", "_").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return f"https://via.placeholder.com/400x300?text={element_code}_{safe_title}"


async def seed_motos_elements():
    """Seed element system data for motos-part category."""
    logger.info("=" * 80)
    logger.info("Starting Motos Element System Seed")
    logger.info("=" * 80)

    async with get_async_session() as session:
        # Step 1: Get or verify category exists
        logger.info("\n[STEP 1] Getting category: motos-part")
        category_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "motos-part")
            .where(VehicleCategory.is_active == True)
        )
        category = category_result.scalar()

        if not category:
            logger.error("Category 'motos-part' not found. Run motos_particular_seed.py first!")
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

        # Step 3: Create elements
        logger.info("\n[STEP 3] Creating elements")
        created_elements = {}

        for elem_data in ELEMENTS:
            # Check if element already exists
            existing_result = await session.execute(
                select(Element)
                .where(Element.category_id == category.id)
                .where(Element.code == elem_data["code"])
            )
            existing = existing_result.scalar()
            if existing:
                logger.info(f"  ⊘ {elem_data['code']}: Already exists, skipping")
                created_elements[elem_data["code"]] = existing
                continue

            # Create element
            element = Element(
                category_id=category.id,
                code=elem_data["code"],
                name=elem_data["name"],
                description=elem_data["description"],
                keywords=elem_data["keywords"],
                aliases=elem_data.get("aliases", []),
                is_active=True,
                sort_order=elem_data["sort_order"],
            )
            session.add(element)
            await session.flush()  # Get the ID

            # Create images for this element
            for img_data in elem_data.get("images", []):
                image = ElementImage(
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
            logger.info(f"  ✓ {elem_data['code']}: Created with {len(elem_data.get('images', []))} images")

        await session.flush()

        # Step 4: Create tier element inclusions based on PDF structure
        # =================================================================
        # PDF Structure (2026 TARIFAS USUARIOS FINALES MOTO):
        # - T6 (140€): 1 elemento máximo
        # - T5 (175€): hasta 2 elementos
        # - T4 (220€): 2+ elementos de la lista base
        # - T3 (280€): 1 elemento principal + hasta 2 de T4
        # - T2 (325€): 1-2 de T3 + hasta 4 de T4
        # - T1 (410€): proyecto completo, cualquier número
        # =================================================================
        logger.info("\n[STEP 4] Creating tier element inclusions")
        logger.info("  According to PDF structure (2026 TARIFAS USUARIOS FINALES MOTO):")

        # Clear existing inclusions for this category's tiers
        for tier in tiers.values():
            existing_inclusions = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier.id)
            )
            for inc in existing_inclusions.scalars().all():
                await session.delete(inc)
        await session.flush()

        # All elements are available for motos tariffs
        all_element_codes = list(created_elements.keys())

        # T6 (140€): 1 elemento de cualquier tipo
        if "T6" in tiers:
            logger.info("  T6 (140€): Cualquier 1 elemento de la lista")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T6"].id,
                    element_id=created_elements[code].id,
                    max_quantity=1,
                    notes=f"T6 allows 1 {code} (or any single element)",
                )
                session.add(inc)

        # T5 (175€): Hasta 2 elementos
        if "T5" in tiers:
            logger.info("  T5 (175€): Hasta 2 elementos de la lista")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T5"].id,
                    element_id=created_elements[code].id,
                    max_quantity=2,
                    notes=f"T5 allows up to 2 {code}",
                )
                session.add(inc)

        # T4 (220€): 2+ elementos (varios elementos sin proyecto)
        if "T4" in tiers:
            logger.info("  T4 (220€): 2+ elementos de la lista base")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T4"].id,
                    element_id=created_elements[code].id,
                    max_quantity=5,  # Reasonable max for "varios elementos"
                    notes=f"T4 allows multiple {code}",
                )
                session.add(inc)

        # T3 (280€): Proyecto sencillo - elementos más complejos + hasta 2 de T4
        if "T3" in tiers:
            logger.info("  T3 (280€): Proyecto sencillo - elementos principales + hasta 2 de lista T4")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T3"].id,
                    element_id=created_elements[code].id,
                    max_quantity=None,  # Unlimited within project scope
                    notes=f"T3 proyecto sencillo includes {code}",
                )
                session.add(inc)

        # T2 (325€): Proyecto medio - más elementos que T3
        if "T2" in tiers:
            logger.info("  T2 (325€): Proyecto medio - múltiples elementos")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T2"].id,
                    element_id=created_elements[code].id,
                    max_quantity=None,
                    notes=f"T2 proyecto medio includes {code}",
                )
                session.add(inc)

        # T1 (410€): Proyecto completo - todo ilimitado
        if "T1" in tiers:
            logger.info("  T1 (410€): Proyecto completo - cualquier combinación")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T1"].id,
                    element_id=created_elements[code].id,
                    max_quantity=None,
                    notes=f"T1 proyecto completo includes {code} unlimited",
                )
                session.add(inc)

            # T1 also includes all lower tiers
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    inc = TierElementInclusion(
                        tier_id=tiers["T1"].id,
                        included_tier_id=tiers[ref_tier_code].id,
                        max_quantity=None,
                        notes=f"T1 includes all elements of {ref_tier_code} unlimited",
                    )
                    session.add(inc)

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
    logger.info("✓ MOTOS ELEMENT SEED COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info(f"Created {len(created_elements)} elements for motos-part")
    logger.info("Configured tier inclusions according to PDF structure")
    logger.info("\nElements created:")
    for code in created_elements:
        logger.info(f"  - {code}")
    logger.info("\nNext steps:")
    logger.info("1. Verify in admin panel: /reformas/[motos-part-id]")
    logger.info("2. Test element matching via agent")
    logger.info("3. Run tests: pytest tests/test_element_system.py")

    return True


async def main():
    """Main entry point."""
    try:
        success = await seed_motos_elements()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
