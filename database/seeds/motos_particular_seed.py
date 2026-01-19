"""
MSI Automotive - Seed data for Motos Particular category.

Tarifas REV2026 para usuarios finales (particulares).
Architecture update: client_type now in VehicleCategory, not TariffTier.

Uses deterministic UUIDs for idempotent seeding.

Run with: python -m database.seeds.motos_particular_seed
"""

import asyncio
import logging
from decimal import Decimal

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    BaseDocumentation,
    Warning,
    AdditionalService,
    TariffPromptSection,
)
from database.seeds.seed_utils import (
    deterministic_category_uuid,
    deterministic_tier_uuid,
    deterministic_base_doc_uuid,
    deterministic_warning_uuid,
    deterministic_additional_service_uuid,
    deterministic_prompt_section_uuid,
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
# Base Documentation (code added for deterministic UUIDs)
# =============================================================================

BASE_DOCUMENTATION_DATA = [
    {"code": "documentos_vehiculo", "description": "Ficha tecnica del vehiculo (ambas caras, legible) y Permiso de circulacion por la cara escrita", "sort_order": 1},
    {"code": "fotos_vehiculo", "description": "Foto lateral derecha, izquierda, frontal y trasera completa de la moto", "sort_order": 2},
]

# =============================================================================
# Warnings (category-scoped only - element warnings are in motos_elements_seed.py)
# =============================================================================

WARNINGS_DATA = [
    {
        "code": "marcado_homologacion_motos_part",
        "message": "Este elemento requiere marcado de homologacion visible (numero E).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["escape", "faros", "retrovisores", "intermitentes", "pilotos", "neumaticos", "llantas"],
        },
    },
    {
        "code": "consultar_ingeniero_motos_part",
        "message": "Esta modificacion es compleja. Se recomienda consultar viabilidad con el ingeniero.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["subchasis", "aumento plazas", "motor", "horquilla completa"],
        },
    },
    {
        "code": "alumbrado_general_motos_part",
        "message": "Todo alumbrado debe tener marcado de homologacion y montarse a alturas y angulos correctos.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["alumbrado", "faros", "intermitentes", "pilotos", "luces"],
        },
    },
    {
        "code": "ensayo_direccion_motos_part",
        "message": "Modificaciones en distancia entre ejes pueden requerir ensayo de direccion (+400 EUR).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["distancia ejes", "horquilla completa", "tren delantero"],
        },
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
# Prompt Sections (code added for deterministic UUIDs)
# =============================================================================

PROMPT_SECTIONS_DATA = [
    {
        "code": "recognition_table",
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
        "code": "special_cases",
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES MOTOS PARTICULARES:
1. Matricula lateral desde julio 2025
2. Escape homologado para el modelo NO es reforma
3. Subchasis puede implicar perdida de 2a plaza""",
        "is_active": True,
    },
]


async def seed_motos_particular():
    """Seed the database with motos particular data using deterministic UUIDs."""
    category_slug = CATEGORY_DATA["slug"]

    async with get_async_session() as session:
        logger.info(f"Seeding {category_slug} category (idempotent with deterministic UUIDs)...")

        # =====================================================================
        # 1. Upsert Category
        # =====================================================================
        category_id = deterministic_category_uuid(category_slug)
        existing_cat = await session.get(VehicleCategory, category_id)

        if existing_cat:
            # Update existing
            for key, value in CATEGORY_DATA.items():
                setattr(existing_cat, key, value)
            category = existing_cat
            logger.info(f"  ~ Category {category_slug}: Updated")
        else:
            # Create new with deterministic UUID
            category = VehicleCategory(id=category_id, **CATEGORY_DATA)
            session.add(category)
            logger.info(f"  + Category {category_slug}: Created")

        await session.flush()

        # =====================================================================
        # 2. Upsert Tiers
        # =====================================================================
        for tier_data in TIERS_DATA:
            tier_id = deterministic_tier_uuid(category_slug, tier_data["code"])
            existing_tier = await session.get(TariffTier, tier_id)

            if existing_tier:
                for key, value in tier_data.items():
                    setattr(existing_tier, key, value)
                existing_tier.category_id = category.id
                logger.info(f"  ~ Tier {tier_data['code']}: Updated")
            else:
                tier = TariffTier(id=tier_id, category_id=category.id, **tier_data)
                session.add(tier)
                logger.info(f"  + Tier {tier_data['code']}: Created")

        # =====================================================================
        # 3. Upsert Category-scoped Warnings
        # (Element-scoped warnings are defined inline in motos_elements_seed.py)
        # =====================================================================
        for warning_data in WARNINGS_DATA:
            warning_id = deterministic_warning_uuid(category_slug, warning_data["code"])
            existing_warning = await session.get(Warning, warning_id)

            data = dict(warning_data)
            data["category_id"] = category.id
            data["element_id"] = None

            if existing_warning:
                for key, value in data.items():
                    setattr(existing_warning, key, value)
                logger.info(f"  ~ Warning {warning_data['code']}: Updated")
            else:
                warning = Warning(id=warning_id, **data)
                session.add(warning)
                logger.info(f"  + Warning {warning_data['code']}: Created")

        # =====================================================================
        # 4. Upsert Base Documentation
        # =====================================================================
        for doc_data in BASE_DOCUMENTATION_DATA:
            doc_id = deterministic_base_doc_uuid(category_slug, doc_data["code"])
            existing_doc = await session.get(BaseDocumentation, doc_id)

            # Prepare data without code (not a model field)
            data = {k: v for k, v in doc_data.items() if k != "code"}
            data["category_id"] = category.id

            if existing_doc:
                for key, value in data.items():
                    setattr(existing_doc, key, value)
                logger.info(f"  ~ BaseDoc {doc_data['code']}: Updated")
            else:
                doc = BaseDocumentation(id=doc_id, **data)
                session.add(doc)
                logger.info(f"  + BaseDoc {doc_data['code']}: Created")

        # =====================================================================
        # 5. Upsert Additional Services
        # =====================================================================
        for svc_data in ADDITIONAL_SERVICES_DATA:
            svc_id = deterministic_additional_service_uuid(category_slug, svc_data["code"])
            existing_svc = await session.get(AdditionalService, svc_id)

            if existing_svc:
                for key, value in svc_data.items():
                    setattr(existing_svc, key, value)
                existing_svc.category_id = category.id
                logger.info(f"  ~ Service {svc_data['code']}: Updated")
            else:
                svc = AdditionalService(id=svc_id, category_id=category.id, **svc_data)
                session.add(svc)
                logger.info(f"  + Service {svc_data['code']}: Created")

        # =====================================================================
        # 6. Upsert Prompt Sections
        # =====================================================================
        for section_data in PROMPT_SECTIONS_DATA:
            section_id = deterministic_prompt_section_uuid(category_slug, section_data["code"])
            existing_section = await session.get(TariffPromptSection, section_id)

            # Prepare data without code (not a model field)
            data = {k: v for k, v in section_data.items() if k != "code"}
            data["category_id"] = category.id

            if existing_section:
                for key, value in data.items():
                    setattr(existing_section, key, value)
                logger.info(f"  ~ PromptSection {section_data['code']}: Updated")
            else:
                section = TariffPromptSection(id=section_id, **data)
                session.add(section)
                logger.info(f"  + PromptSection {section_data['code']}: Created")

        await session.commit()
        logger.info(f"Seed {category_slug} completed!")


if __name__ == "__main__":
    asyncio.run(seed_motos_particular())
