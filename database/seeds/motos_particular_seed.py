"""
MSI Automotive - Seed data for Motos Particular category.

Tarifas REV2026 para usuarios finales (particulares).
Architecture update: client_type now in VehicleCategory, not TariffTier.

Run with: python -m database.seeds.motos_particular_seed
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
    TariffPromptSection,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Category Data - NOW INCLUDES client_type
# =============================================================================

CATEGORY_DATA = {
    "slug": "motos-part",
    "name": "Motocicletas",
    "description": "Homologacion de reformas en motocicletas (particulares)",
    "icon": "motorcycle",
    "client_type": "particular",  # NEW: client_type at category level
}

# =============================================================================
# Tariff Tiers - NO client_type (category determines it)
# =============================================================================

TIERS_DATA = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "description": "Transformacion completa con proyectos complejos",
        "price": Decimal("410.00"),
        "conditions": "Modificacion distancia ejes, subchasis, horquilla/tren delantero, sistema frenado (bomba, pinzas, discos), cambio motor, llantas/neumaticos con ensayo",
        "classification_rules": {
            "applies_if_any": [
                "distancia entre ejes", "distancia ejes",
                "subchasis", "modificacion subchasis",
                "horquilla completa", "tren delantero completo", "tren delantero",
                "sistema de frenado", "bomba de freno", "bomba freno",
                "pinzas de freno", "pinzas freno", "discos de freno", "discos freno",
                "cambio de motor", "cambio motor", "motor nuevo",
                "llantas con ensayo", "neumaticos con ensayo",
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
        "description": "1-2 elementos T3 + hasta 4 elementos T4, aumento plazas",
        "price": Decimal("325.00"),
        "conditions": "Combinacion de elementos con proyecto medio, aumento de plazas (verificar viabilidad)",
        "classification_rules": {
            "applies_if_any": [
                "aumento de plazas", "aumento plazas",
                "proyecto medio",
            ],
            "priority": 2,
            "requires_project": True,
        },
        "sort_order": 2,
    },
    {
        "code": "T3",
        "name": "Proyecto Sencillo",
        "description": "1 elemento con proyecto + hasta 2 elementos T4",
        "price": Decimal("280.00"),
        "conditions": "Suspension delantera (barras/muelles), suspension trasera, frenos equivalentes, latiguillos, carroceria, velocimetro soporte, faro soporte",
        "classification_rules": {
            "applies_if_any": [
                "suspension delantera", "barras de suspension", "muelles de barras",
                "suspension trasera", "amortiguador trasero",
                "frenos equivalentes", "frenos por equivalentes",
                "latiguillos de freno", "latiguillos freno", "latiguillos",
                "carroceria exterior", "carenados", "tapas laterales", "colin",
                "soporte velocimetro", "emplazamiento velocimetro",
                "soporte faro", "reubicacion faro",
                "proyecto sencillo",
            ],
            "priority": 3,
            "requires_project": True,
        },
        "sort_order": 3,
    },
    {
        "code": "T4",
        "name": "Sin Proyecto - Varios Elementos",
        "description": "A partir de 2 elementos sin proyecto",
        "price": Decimal("220.00"),
        "conditions": "Matricula, filtro, escape, deposito, neumaticos, llantas, manillar, velocimetro, caballete, retrovisores, alumbrado (todo con homologacion)",
        "classification_rules": {
            "applies_if_any": [],
            "priority": 4,
            "requires_project": False,
        },
        "min_elements": 3,
        "sort_order": 4,
    },
    {
        "code": "T5",
        "name": "Sin Proyecto - 2 Elementos",
        "description": "Hasta 2 elementos de la lista T4",
        "price": Decimal("175.00"),
        "conditions": "Hasta 2 elementos sin proyecto",
        "classification_rules": {
            "applies_if_any": [],
            "priority": 5,
            "requires_project": False,
        },
        "min_elements": 2,
        "max_elements": 2,
        "sort_order": 5,
    },
    {
        "code": "T6",
        "name": "Sin Proyecto - 1 Elemento",
        "description": "Solo 1 elemento de la lista",
        "price": Decimal("140.00"),
        "conditions": "1 solo elemento: escape, retrovisores, alumbrado, matricula, etc.",
        "classification_rules": {
            "applies_if_any": [
                "escape", "escape completo", "linea de escape", "silenciador",
                "retrovisores", "retrovisor", "espejos", "espejo",
                "intermitentes", "intermitente", "indicadores",
                "piloto trasero", "piloto", "luz trasera",
                "faros", "faro", "faro delantero", "optica",
                "faros antiniebla", "antiniebla",
                "luz de freno", "catadiptricos",
                "matricula", "emplazamiento matricula", "brazo lateral",
                "neumaticos", "neumatico", "ruedas",
                "llantas", "llanta",
                "manillar", "semimanillares", "semi manillares",
                "velocimetro", "cuentakilometros",
                "caballete", "anulacion caballete",
                "deposito", "deposito combustible",
                "filtro", "filtro aire",
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
    {"description": "Foto lateral derecha completa de la moto", "sort_order": 3},
    {"description": "Foto lateral izquierda completa de la moto", "sort_order": 4},
    {"description": "Foto frontal de la moto", "sort_order": 5},
    {"description": "Foto trasera de la moto", "sort_order": 6},
]

# =============================================================================
# Element Documentation
# =============================================================================

ELEMENT_DOCUMENTATION_DATA = [
    {
        "element_keywords": ["escape", "linea de escape", "silenciador", "colector"],
        "description": "Foto del escape instalado mostrando el marcado de homologacion (numero E visible)",
        "sort_order": 1,
    },
    {
        "element_keywords": ["faros", "faro", "faro led", "faro delantero", "optica"],
        "description": "Foto del faro instalado mostrando el marcado de homologacion",
        "sort_order": 2,
    },
    {
        "element_keywords": ["retrovisores", "retrovisor", "espejos", "espejo"],
        "description": "Foto de los retrovisores instalados mostrando el marcado de homologacion",
        "sort_order": 3,
    },
    {
        "element_keywords": ["intermitentes", "intermitente", "indicadores"],
        "description": "Foto de los intermitentes instalados mostrando el marcado de homologacion",
        "sort_order": 4,
    },
    {
        "element_keywords": ["neumaticos", "neumatico", "ruedas", "rueda"],
        "description": "Foto de los neumaticos mostrando marca, modelo y medidas visibles",
        "sort_order": 5,
    },
    {
        "element_keywords": ["llantas", "llanta"],
        "description": "Foto de las llantas mostrando el marcado de homologacion y medidas",
        "sort_order": 6,
    },
    {
        "element_keywords": ["suspension", "amortiguadores", "amortiguador", "barras"],
        "description": "Foto de la suspension/amortiguadores instalados",
        "sort_order": 7,
    },
    {
        "element_keywords": ["manillar", "semi manillares", "semimanillares"],
        "description": "Foto del manillar instalado",
        "sort_order": 8,
    },
    {
        "element_keywords": ["matricula", "emplazamiento matricula", "brazo lateral"],
        "description": "Foto del nuevo emplazamiento de matricula",
        "sort_order": 9,
    },
]

# =============================================================================
# Warnings (category-scoped - linked to motos-part)
# =============================================================================

WARNINGS_DATA = [
    {
        "code": "marcado_homologacion_motos_part",
        "message": "Este elemento requiere marcado de homologacion visible (numero E).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["escape", "faros", "retrovisores", "intermitentes", "pilotos", "neumaticos", "llantas"],
        },
        "_scope": "category",  # Will be linked to category during seed
    },
    {
        "code": "ensayo_frenada_motos_part",
        "message": "Modificaciones en sistema de frenado pueden requerir ensayo de frenada adicional (375 EUR).",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["frenos", "disco freno", "pinza freno", "bomba freno", "sistema de frenado"],
        },
        "_scope": "category",
    },
    {
        "code": "consultar_ingeniero_motos_part",
        "message": "Esta modificacion es compleja. Se recomienda consultar viabilidad con el ingeniero.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["subchasis", "aumento plazas", "motor", "horquilla completa"],
        },
        "_scope": "category",
    },
]

# =============================================================================
# Additional Services
# =============================================================================

ADDITIONAL_SERVICES_DATA = [
    {"code": "cert_taller_motos", "name": "Certificado taller concertado", "price": Decimal("85.00"), "sort_order": 1},
    {"code": "urgencia_motos", "name": "Tramitacion urgente", "price": Decimal("100.00"), "sort_order": 2},
    {"code": "plus_lab_simple", "name": "Plus laboratorio simple", "price": Decimal("25.00"), "sort_order": 3},
    {"code": "plus_lab_complejo", "name": "Plus laboratorio complejo", "price": Decimal("75.00"), "sort_order": 4},
    {"code": "ensayo_frenada", "name": "Ensayo dinamico de frenada", "price": Decimal("375.00"), "sort_order": 5},
    {"code": "ensayo_direccion", "name": "Ensayo de direccion", "price": Decimal("400.00"), "sort_order": 6},
]

# =============================================================================
# Prompt Sections
# =============================================================================

PROMPT_SECTIONS_DATA = [
    {
        "section_type": "recognition_table",
        "content": """| Elemento | Tarifa tipica |
|----------|---------------|
| Escape completo | T6 (1 elem) / T4 (>=2) |
| Retrovisores | T6 (1 elem) / T4 (>=2) |
| Sistema frenado | T1 (requiere ensayo) |
| Cambio motor | T1 (proyecto completo) |
| Aumento plazas | T2 (proyecto medio) |""",
        "is_active": True,
    },
    {
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES MOTOS PARTICULARES:
1. Matricula lateral desde julio 2025
2. Escape homologado para el modelo NO es reforma
3. Subchasis puede implicar perdida de 2a plaza""",
        "is_active": True,
    },
]


async def seed_motos_particular():
    """Seed the database with motos particular data."""
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

        # Create element documentation
        for elem_data in ELEMENT_DOCUMENTATION_DATA:
            session.add(ElementDocumentation(category_id=category.id, **elem_data))

        # Create additional services
        for svc_data in ADDITIONAL_SERVICES_DATA:
            session.add(AdditionalService(category_id=category.id, **svc_data))

        # Create prompt sections
        for section_data in PROMPT_SECTIONS_DATA:
            session.add(TariffPromptSection(category_id=category.id, **section_data))

        await session.commit()
        logger.info(f"Seed {CATEGORY_DATA['slug']} completed!")


if __name__ == "__main__":
    asyncio.run(seed_motos_particular())
