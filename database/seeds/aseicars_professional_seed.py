"""
MSI Automotive - Seed data for Autocaravanas Professional category.

Tarifas para profesionales (talleres concertados).
Architecture update: client_type now in VehicleCategory, not TariffTier.

Run with: python -m database.seeds.aseicars_professional_seed
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    Warning,
    AdditionalService,
    TariffPromptSection,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Category Data - NOW INCLUDES client_type
# =============================================================================

CATEGORY_DATA = {
    "slug": "aseicars-prof",
    "name": "Autocaravanas (32xx, 33xx)",
    "description": "Regularizacion de elementos en autocaravanas y campers (profesionales)",
    "icon": "caravan",
    "client_type": "professional",  # NEW: client_type at category level
}

# =============================================================================
# Tariff Tiers - NO client_type (category determines it)
# =============================================================================

TIERS_DATA = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "description": "Sin limite de elementos + reformas estructurales",
        "price": Decimal("270.00"),
        "conditions": "Incluye refuerzos suspensiones, aumento plazas, MMTA",
        "classification_rules": {
            "applies_if_any": [
                "refuerzo suspension", "refuerzo suspensiones",
                "aumento plazas", "aumento de plazas",
                "mmta", "masa maxima",
                "proyecto completo",
            ],
            "priority": 1,
            "requires_project": True,
        },
        "sort_order": 1,
    },
    {
        "code": "T2",
        "name": "Proyecto Medio",
        "description": "Combinaciones especificas con proyecto",
        "price": Decimal("230.00"),
        "conditions": "Hasta 2 elementos T3 + elementos T6 + kit elevacion/suspension neumatica/bola remolque con proyecto",
        "classification_rules": {
            "applies_if_any": [
                "kit elevacion", "elevacion hidraulica",
                "suspension neumatica",
                "bola remolque proyecto", "enganche con proyecto",
            ],
            "priority": 2,
            "requires_project": True,
        },
        "sort_order": 2,
    },
    {
        "code": "T3",
        "name": "Proyecto Basico",
        "description": "Elementos que requieren proyecto sencillo",
        "price": Decimal("180.00"),
        "conditions": "Placas interior, mobiliario, electricos, llantas aletines, gas, cerraduras + elementos T6",
        "classification_rules": {
            "applies_if_any": [
                "placas interior", "placas interiores",
                "mobiliario", "muebles",
                "electricos", "instalacion electrica",
                "llantas aletines", "aletines",
                "gas", "instalacion gas",
                "cerraduras", "cerradura",
            ],
            "priority": 3,
            "requires_project": True,
        },
        "sort_order": 3,
    },
    {
        "code": "T4",
        "name": "Regularizacion varios",
        "description": "Multiples elementos sin proyecto",
        "price": Decimal("135.00"),
        "conditions": "Sin limite T6 + neumaticos no equiv, bola sin proyecto, aire acondicionado, ventanas/claraboyas",
        "classification_rules": {
            "applies_if_any": [
                "neumaticos no equivalentes",
                "bola remolque", "enganche remolque",
                "aire acondicionado", "climatizador",
                "ventana", "ventanas", "claraboya", "claraboyas",
            ],
            "priority": 4,
            "requires_project": False,
        },
        "min_elements": 4,
        "sort_order": 4,
    },
    {
        "code": "T5",
        "name": "Hasta 3 elementos",
        "description": "Regularizacion de 1-3 elementos simples",
        "price": Decimal("65.00"),
        "conditions": "Hasta 3 elementos T6 + placas solares en maletero",
        "classification_rules": {
            "applies_if_any": [
                "placas solares maletero",
            ],
            "priority": 5,
            "requires_project": False,
        },
        "min_elements": 1,
        "max_elements": 3,
        "sort_order": 5,
    },
    {
        "code": "T6",
        "name": "1 elemento",
        "description": "Elemento unico simple",
        "price": Decimal("59.00"),
        "conditions": "Placas solares, toldos, antenas parabolicas",
        "classification_rules": {
            "applies_if_any": [
                "placas solares", "panel solar", "paneles solares",
                "toldo", "toldos", "toldo lateral",
                "antena parabolica", "antena", "parabola",
            ],
            "priority": 6,
            "requires_project": False,
        },
        "min_elements": 1,
        "max_elements": 1,
        "sort_order": 6,
    },
]

# =============================================================================
# Base Documentation
# =============================================================================

BASE_DOCUMENTATION_DATA = [
    {"description": "Ficha tecnica del vehiculo (ambas caras, legible)", "sort_order": 1},
    {"description": "Permiso de circulacion por la cara escrita", "sort_order": 2},
    {"description": "Foto lateral derecha completa del vehiculo", "sort_order": 3},
    {"description": "Foto lateral izquierda completa del vehiculo", "sort_order": 4},
    {"description": "Foto frontal del vehiculo", "sort_order": 5},
    {"description": "Foto trasera del vehiculo", "sort_order": 6},
]

# =============================================================================
# Warnings (category-scoped - linked to aseicars-prof)
# =============================================================================

WARNINGS_DATA = [
    {
        "code": "mmta_aseicars_prof",
        "message": "Modificaciones de MMTA requieren proyecto completo y verificacion tecnica.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["mmta", "masa maxima", "aumento plazas"],
        },
        "_scope": "category",  # Will be linked to category during seed
    },
    {
        "code": "gas_aseicars_prof",
        "message": "Instalaciones de gas requieren certificacion especifica.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["gas", "instalacion gas", "butano", "propano"],
        },
        "_scope": "category",
    },
    {
        "code": "electricos_aseicars_prof",
        "message": "Instalaciones electricas de alta potencia pueden requerir proyecto.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electricos", "instalacion electrica", "inversor"],
        },
        "_scope": "category",
    },
]

# =============================================================================
# Additional Services
# =============================================================================

ADDITIONAL_SERVICES_DATA = [
    {"code": "cert_taller_aseicars", "name": "Certificado taller concertado", "price": Decimal("85.00"), "sort_order": 1},
    {"code": "urgencia_aseicars", "name": "Tramitacion urgente", "price": Decimal("100.00"), "sort_order": 2},
    {"code": "plus_lab_simple_aseicars", "name": "Plus laboratorio simple", "price": Decimal("25.00"), "sort_order": 3},
    {"code": "gestion_itv", "name": "Gestion cita ITV", "price": Decimal("30.00"), "sort_order": 4},
]

# =============================================================================
# Prompt Sections
# =============================================================================

PROMPT_SECTIONS_DATA = [
    {
        "section_type": "recognition_table",
        "content": """| Elemento | Tarifa tipica |
|----------|---------------|
| Placas solares | T6 (1 elem) / T5 (2-3) |
| Toldo lateral | T6 (1 elem) |
| Antena parabolica | T6 (1 elem) |
| Mobiliario | T3 (con proyecto) |
| Bola remolque | T4 (sin proyecto) / T2 (con proyecto) |
| Gas | T3 (requiere proyecto) |""",
        "is_active": True,
    },
    {
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES AUTOCARAVANAS PROFESIONALES:
1. Instalaciones de gas requieren certificacion
2. MMTA requiere proyecto completo
3. Bola remolque puede o no requerir proyecto segun capacidad""",
        "is_active": True,
    },
]


async def seed_aseicars_professional():
    """Seed the database with aseicars professional data."""
    async with get_async_session() as session:
        existing = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == CATEGORY_DATA["slug"])
        )
        if existing.scalar():
            logger.info(f"Category {CATEGORY_DATA['slug']} already exists, skipping")
            return

        logger.info(f"Creating {CATEGORY_DATA['slug']} category...")

        # Create category (now with client_type)
        category = VehicleCategory(**CATEGORY_DATA)
        session.add(category)
        await session.flush()

        # Create warnings (with category scope)
        for warning_data in WARNINGS_DATA:
            existing_w = await session.execute(
                select(Warning).where(Warning.code == warning_data["code"])
            )
            if not existing_w.scalar():
                # Extract scope indicator and prepare data
                data = {k: v for k, v in warning_data.items() if not k.startswith("_")}
                if warning_data.get("_scope") == "category":
                    data["category_id"] = category.id
                session.add(Warning(**data))

        # Create tiers (NO client_type)
        for tier_data in TIERS_DATA:
            session.add(TariffTier(category_id=category.id, **tier_data))

        # Create base documentation
        for doc_data in BASE_DOCUMENTATION_DATA:
            session.add(BaseDocumentation(category_id=category.id, **doc_data))

        # Create additional services
        for svc_data in ADDITIONAL_SERVICES_DATA:
            session.add(AdditionalService(category_id=category.id, **svc_data))

        # Create prompt sections
        for section_data in PROMPT_SECTIONS_DATA:
            session.add(TariffPromptSection(category_id=category.id, **section_data))

        await session.commit()
        logger.info(f"Seed {CATEGORY_DATA['slug']} completed!")


if __name__ == "__main__":
    asyncio.run(seed_aseicars_professional())
