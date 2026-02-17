"""
MSI Automotive - Run all seeds.

This script seeds all categories using the refactored architecture:
- data/: Contains all seed data definitions (constants)
- seeders/: Contains reusable seeding logic

Categories seeded:
- motos-part: Motocicletas para particulares (39 elements)
- aseicars-prof: Autocaravanas para profesionales (~30 elements)
- aseicars-part: Autocaravanas para particulares (~47 elements)

Run with: python -m database.seeds.run_all_seeds
"""

import asyncio
import logging
from types import ModuleType

from database.connection import get_async_session
from database.models import ResponseConstraint
from database.seeds.data import motos_part, aseicars_prof, aseicars_part
from database.seeds.seed_utils import deterministic_constraint_uuid
from database.seeds.seeders import CategorySeeder, ElementSeeder, InclusionSeeder, RequiredFieldSeeder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Global response constraints (anti-hallucination rules)
# =============================================================================
# These are global (category_id=NULL) and apply to all conversations.
# Moved from migration 027 to seeds for idempotent recreation.

RESPONSE_CONSTRAINTS = [
    {
        "constraint_type": "price_requires_tool",
        "detection_pattern": r"\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA",
        "required_tool": "calcular_tarifa_con_elementos",
        "error_injection": (
            "CORRECCION OBLIGATORIA: Has mencionado un precio sin haber llamado a "
            "calcular_tarifa_con_elementos. NUNCA inventes precios. Llama PRIMERO a "
            "calcular_tarifa_con_elementos con los codigos de elementos resueltos, y "
            "usa el precio que devuelve la herramienta. Si no tienes codigos resueltos, "
            "llama primero a identificar_y_resolver_elementos."
        ),
        "is_active": True,
        "priority": 100,
    },
    {
        "constraint_type": "images_narration_blocked",
        "detection_pattern": (
            r"\[.*[Ll]lamando.*herramienta|imagenes.*se.*enviaran.*a.*continuacion"
            r"|fotos.*adjunt|ejemplo.*imagenes.*adjunt"
        ),
        "required_tool": "enviar_imagenes_ejemplo",
        "error_injection": (
            "CORRECCION OBLIGATORIA: Estas NARRANDO el envio de imagenes en texto en "
            "lugar de llamar a la herramienta. NUNCA describas que vas a enviar imagenes. "
            "Llama a enviar_imagenes_ejemplo() directamente. Si ya la llamaste y fallo, "
            "informa al usuario que las imagenes no estan disponibles en este momento."
        ),
        "is_active": True,
        "priority": 95,
    },
    {
        "constraint_type": "variant_requires_tool",
        "detection_pattern": (
            r"¿.*tipo.*\:|¿.*estandar.*full|¿.*variante"
            r"|¿.*cual.*prefer|¿.*instalad[oa].*en"
        ),
        "required_tool": "identificar_y_resolver_elementos|seleccionar_variante_por_respuesta",
        "error_injection": (
            "CORRECCION OBLIGATORIA: Estas haciendo una pregunta de variante que NO "
            "viene de la base de datos. NUNCA inventes preguntas de clasificacion. "
            "Llama a identificar_y_resolver_elementos y usa EXACTAMENTE la question_hint "
            "que devuelve la herramienta para preguntar al usuario."
        ),
        "is_active": True,
        "priority": 90,
    },
    {
        "constraint_type": "docs_from_tool_only",
        "detection_pattern": (
            r"certificado.*(resistencia|anclaje|instalacion)|normativa.*UNE"
            r"|homologacion.*requiere.*(proyecto|boletin)"
            r"|documentacion.*(necesaria|requerida|obligatoria).*\:"
        ),
        "required_tool": "calcular_tarifa_con_elementos|obtener_documentacion_elemento",
        "error_injection": (
            "CORRECCION OBLIGATORIA: Estas describiendo requisitos de documentacion que "
            "NO vienen de las herramientas. NUNCA inventes requisitos documentales. La "
            "documentacion requerida viene SOLO del campo \"documentacion\" en la respuesta "
            "de calcular_tarifa_con_elementos o de obtener_documentacion_elemento. Usa esos "
            "datos exactos."
        ),
        "is_active": True,
        "priority": 80,
    },
]


async def seed_response_constraints() -> bool:
    """
    Seed global response constraints (anti-hallucination rules).

    These are global (no category_id) and apply to all conversations.
    Uses delete-then-insert by constraint_type for clean idempotency,
    replacing any old random-UUID rows from migration 027.

    Returns:
        True if successful, False otherwise.
    """
    logger.info("Seeding global response constraints...")

    try:
        async with get_async_session() as session:
            known_types = [c["constraint_type"] for c in RESPONSE_CONSTRAINTS]

            # Delete existing rows matching these constraint types
            # (handles both old random UUIDs from migration 027 and previous seed runs)
            from sqlalchemy import delete, select

            del_result = await session.execute(
                delete(ResponseConstraint).where(
                    ResponseConstraint.constraint_type.in_(known_types)
                )
            )
            deleted = del_result.rowcount  # type: ignore[attr-defined]
            if deleted:
                logger.info(f"  Deleted {deleted} existing constraint(s)")

            # Insert fresh with deterministic UUIDs
            for data in RESPONSE_CONSTRAINTS:
                constraint_id = deterministic_constraint_uuid(data["constraint_type"])
                constraint = ResponseConstraint(
                    id=constraint_id,
                    constraint_type=data["constraint_type"],
                    detection_pattern=data["detection_pattern"],
                    required_tool=data["required_tool"],
                    error_injection=data["error_injection"],
                    is_active=data["is_active"],
                    priority=data["priority"],
                    category_id=None,  # Global constraints
                )
                session.add(constraint)
                logger.info(f"  ✅ {data['constraint_type']} (priority {data['priority']})")

            await session.commit()
            logger.info(f"Response constraints seeded: {len(RESPONSE_CONSTRAINTS)} constraints")
            return True

    except Exception as e:
        logger.error(f"Error seeding response constraints: {e}", exc_info=True)
        return False


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

            # 3. Seed required fields for elements
            logger.info("\n[STEP 3] Seeding required fields...")
            field_seeder = RequiredFieldSeeder(category_slug, session)
            await field_seeder.seed(
                elements=data_module.ELEMENTS,
                elements_dict={code: elem.id for code, elem in elements.items()},
            )

            # 4. Seed tier-element inclusions
            logger.info("\n[STEP 4] Seeding tier inclusions...")
            inc_seeder = InclusionSeeder(category_slug, session)
            await inc_seeder.seed(
                tiers=tiers,
                elements=elements,
            )

            # Commit all changes
            logger.info("\n[STEP 5] Committing changes...")
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

    # Seed global infrastructure first (constraints are category-independent)
    logger.info("\n[0/4] Seeding global response constraints...")
    results["response-constraints"] = await seed_response_constraints()

    # Seed motos-part
    logger.info("\n[1/4] Seeding motos-part (Motocicletas Particular)...")
    results["motos-part"] = await seed_category(motos_part)

    # Seed aseicars-part
    logger.info("\n[2/4] Seeding aseicars-part (Autocaravanas Particular)...")
    results["aseicars-part"] = await seed_category(aseicars_part)

    # Seed aseicars-prof
    logger.info("\n[3/4] Seeding aseicars-prof (Autocaravanas Profesional)...")
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
        logger.info(f"  - aseicars-part: {len(aseicars_part.ELEMENTS)} elements, {len(aseicars_part.TIERS)} tiers")
        logger.info(f"  - aseicars-prof: {len(aseicars_prof.ELEMENTS)} elements, {len(aseicars_prof.TIERS)} tiers")
    else:
        logger.error("\nSome seeds failed. Check logs above for details.")


if __name__ == "__main__":
    asyncio.run(run_all_seeds())
