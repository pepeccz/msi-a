"""
MSI Automotive - Seed data for Autocaravanas (aseicars) category.

This script populates the database with initial tariff data for motorhomes/campers,
including tiers with classification_rules, element documentation, and base documentation.

Uses the new architecture with AI-driven tier classification via keywords.

Run with: python -m database.seeds.aseicars_seed
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
    ElementDocumentation,
    Warning,
    AdditionalService,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Category Data
# =============================================================================

CATEGORY_DATA = {
    "slug": "aseicars",
    "name": "Autocaravanas (32xx, 33xx)",
    "description": "Regularizacion de elementos en autocaravanas y campers",
    "icon": "caravan",
}

# =============================================================================
# Tariff Tiers - PROFESIONALES (precios SIN IVA)
# =============================================================================

TIERS_PROFESSIONAL = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "description": "Sin limite de elementos + reformas estructurales",
        "price": Decimal("270.00"),
        "conditions": "Incluye refuerzos suspensiones, aumento plazas, MMTA",
        "client_type": "professional",
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
        "client_type": "professional",
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
        "client_type": "professional",
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
        "client_type": "professional",
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
        "client_type": "professional",
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
        "client_type": "professional",
        "classification_rules": {
            "applies_if_any": [
                "placa solar", "placas solares", "panel solar", "paneles solares",
                "toldo", "toldos", "marquesina",
                "antena", "antena parabolica", "parabolica",
                "escalera", "escalerilla",
                "portabicicletas", "porta bicicletas", "soporte bicicletas",
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
# Base Documentation (required for all homologations)
# =============================================================================

BASE_DOCUMENTATION_DATA = [
    {
        "description": "Ficha tecnica completa por ambas caras (legible, buena resolucion)",
        "image_url": None,
        "sort_order": 1,
    },
    {
        "description": "Permiso de circulacion por la cara escrita",
        "image_url": None,
        "sort_order": 2,
    },
    {
        "description": "Vista exterior frontal completa del vehiculo",
        "image_url": None,
        "sort_order": 3,
    },
    {
        "description": "Vista exterior trasera completa del vehiculo",
        "image_url": None,
        "sort_order": 4,
    },
    {
        "description": "Vista exterior lateral derecha",
        "image_url": None,
        "sort_order": 5,
    },
    {
        "description": "Vista exterior lateral izquierda",
        "image_url": None,
        "sort_order": 6,
    },
]

# =============================================================================
# Element Documentation (keyword-based, triggered by AI)
# =============================================================================

ELEMENT_DOCUMENTATION_DATA = [
    {
        "element_keywords": ["escalera", "escalerilla", "escalera mecanica"],
        "description": "Foto de la escalera instalada y desplegada, mostrando el nuevo ancho total del vehiculo con metro visible",
        "image_url": None,
        "sort_order": 1,
    },
    {
        "element_keywords": ["toldo", "toldos", "marquesina"],
        "description": "Foto del toldo desplegado mostrando el nuevo ancho total del vehiculo con metro visible",
        "image_url": None,
        "sort_order": 2,
    },
    {
        "element_keywords": ["portabicicletas", "porta bicicletas", "soporte bicicletas", "bicicletas"],
        "description": "Foto del portabicicletas instalado con carga (bicicletas colocadas)",
        "image_url": None,
        "sort_order": 3,
    },
    {
        "element_keywords": ["placa solar", "placas solares", "panel solar", "paneles solares"],
        "description": "Foto del techo mostrando las placas solares instaladas y su distribucion",
        "image_url": None,
        "sort_order": 4,
    },
    {
        "element_keywords": ["aire acondicionado", "climatizador", "aire"],
        "description": "Foto del equipo de aire acondicionado instalado y boletin electrico de la instalacion",
        "image_url": None,
        "sort_order": 5,
    },
    {
        "element_keywords": ["claraboya", "claraboyas", "tragaluz"],
        "description": "Foto de la claraboya instalada desde el interior y exterior",
        "image_url": None,
        "sort_order": 6,
    },
    {
        "element_keywords": ["ventana", "ventanas"],
        "description": "Foto de la ventana instalada desde el interior y exterior con medidas",
        "image_url": None,
        "sort_order": 7,
    },
    {
        "element_keywords": ["bola remolque", "enganche remolque", "enganche", "bola"],
        "description": "Foto de la bola de remolque instalada, con y sin extensores si los tiene",
        "image_url": None,
        "sort_order": 8,
    },
    {
        "element_keywords": ["kit elevacion", "elevacion hidraulica", "elevacion"],
        "description": "Foto del sistema de elevacion instalado y foto del mando interior",
        "image_url": None,
        "sort_order": 9,
    },
    {
        "element_keywords": ["antena", "antena parabolica", "parabolica"],
        "description": "Foto de la antena instalada en el techo",
        "image_url": None,
        "sort_order": 10,
    },
    {
        "element_keywords": ["mobiliario", "muebles", "interior"],
        "description": "Fotos del mobiliario interior instalado desde varios angulos",
        "image_url": None,
        "sort_order": 11,
    },
    {
        "element_keywords": ["gas", "instalacion gas", "bombona", "cocina gas"],
        "description": "Certificado de instalacion de gas y foto del compartimento de bombonas",
        "image_url": None,
        "sort_order": 12,
    },
]

# =============================================================================
# Warnings
# =============================================================================

WARNINGS_DATA = [
    {
        "code": "proyecto_obligatorio",
        "message": "Esta modificacion requiere proyecto tecnico. El precio incluye el proyecto.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "refuerzo", "mmta", "plazas", "mobiliario",
                "placas interior", "electricos", "gas",
            ],
        },
    },
    {
        "code": "boletin_electrico",
        "message": "Necesario boletin electrico para instalaciones de 12V y 230V.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["aire acondicionado", "electricos", "230v"],
        },
    },
    {
        "code": "boletin_gas",
        "message": "Necesario certificado de instalacion de gas.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["gas", "cocina", "bombona"],
        },
    },
    {
        "code": "consultar_ingeniero",
        "message": "Modificacion compleja. Consultar viabilidad con el ingeniero antes de proceder.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["mmta", "plazas", "estructura"],
        },
    },
]

# =============================================================================
# Additional Services (precios SIN IVA)
# =============================================================================

ADDITIONAL_SERVICES_DATA = [
    {
        "code": "certificado_taller",
        "name": "Certificado de taller",
        "description": "Certificado si la instalacion no la realizo un taller autorizado",
        "price": Decimal("70.00"),
        "sort_order": 1,
    },
    {
        "code": "certificado_electrico",
        "name": "Certificado electrico",
        "description": "Boletin electrico para instalaciones 12V y 230V",
        "price": Decimal("65.00"),
        "sort_order": 2,
    },
    {
        "code": "certificado_gas",
        "name": "Certificado de gas",
        "description": "Certificado de instalacion de gas",
        "price": Decimal("65.00"),
        "sort_order": 3,
    },
    {
        "code": "plus_laboratorio_sin_proyecto",
        "name": "Plus laboratorio (sin proyecto)",
        "description": "Recargo de laboratorio para tramites sin proyecto",
        "price": Decimal("25.00"),
        "sort_order": 4,
    },
    {
        "code": "plus_laboratorio_con_proyecto",
        "name": "Plus laboratorio (con proyecto)",
        "description": "Recargo de laboratorio para tramites con proyecto",
        "price": Decimal("75.00"),
        "sort_order": 5,
    },
    {
        "code": "ayudas_digitales",
        "name": "Ayudas digitales",
        "description": "Asistencia digital para preparacion de documentacion",
        "price": Decimal("20.00"),
        "sort_order": 6,
    },
    {
        "code": "redaccion_certificado",
        "name": "Redaccion de certificado",
        "description": "Redaccion de certificado tecnico adicional",
        "price": Decimal("10.00"),
        "sort_order": 7,
    },
]


async def seed_aseicars_data():
    """Seed the database with autocaravanas (aseicars) tariff data."""
    async with get_async_session() as session:
        # Check if category already exists
        existing = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == CATEGORY_DATA["slug"])
        )
        if existing.scalar():
            logger.info("Aseicars category already exists, skipping seed")
            return

        logger.info("Creating aseicars (autocaravanas) category...")

        # Create category
        category = VehicleCategory(**CATEGORY_DATA)
        session.add(category)
        await session.flush()  # Get the category ID

        # Create warnings
        logger.info("Creating warnings...")
        for warning_data in WARNINGS_DATA:
            warning = Warning(**warning_data)
            session.add(warning)

        # Create tiers for professionals only (aseicars is professional-only)
        logger.info("Creating professional tariff tiers...")
        for tier_data in TIERS_PROFESSIONAL:
            tier = TariffTier(category_id=category.id, **tier_data)
            session.add(tier)

        # Create base documentation
        logger.info("Creating base documentation...")
        for doc_data in BASE_DOCUMENTATION_DATA:
            doc = BaseDocumentation(category_id=category.id, **doc_data)
            session.add(doc)

        # Create element documentation (keyword-based)
        logger.info("Creating element documentation...")
        for elem_doc_data in ELEMENT_DOCUMENTATION_DATA:
            elem_doc = ElementDocumentation(category_id=category.id, **elem_doc_data)
            session.add(elem_doc)

        # Create additional services (specific to aseicars)
        logger.info("Creating additional services...")
        for service_data in ADDITIONAL_SERVICES_DATA:
            service = AdditionalService(category_id=category.id, **service_data)
            session.add(service)

        await session.commit()
        logger.info("Aseicars seed data created successfully!")


async def main():
    """Run the seed script."""
    await seed_aseicars_data()


if __name__ == "__main__":
    asyncio.run(main())
