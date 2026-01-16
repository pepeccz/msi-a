"""
MSI Automotive - Seed data for Autocaravanas Professional category.

Tarifas para profesionales (talleres concertados).
Architecture update: client_type now in VehicleCategory, not TariffTier.

Uses deterministic UUIDs for idempotent seeding.

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
from database.seeds.seed_utils import (
    deterministic_category_uuid,
    deterministic_tier_uuid,
    deterministic_base_doc_uuid,
    deterministic_warning_uuid,
    deterministic_additional_service_uuid,
    deterministic_prompt_section_uuid,
    deterministic_element_uuid,
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
# Base Documentation (code added for deterministic UUIDs)
# =============================================================================

BASE_DOCUMENTATION_DATA = [
    {"code": "ficha_tecnica", "description": "Ficha tecnica del vehiculo (ambas caras, legible)", "sort_order": 1},
    {"code": "permiso_circulacion", "description": "Permiso de circulacion por la cara escrita", "sort_order": 2},
    {"code": "foto_lateral_derecha", "description": "Foto lateral derecha completa del vehiculo", "sort_order": 3},
    {"code": "foto_lateral_izquierda", "description": "Foto lateral izquierda completa del vehiculo", "sort_order": 4},
    {"code": "foto_frontal", "description": "Foto frontal del vehiculo", "sort_order": 5},
    {"code": "foto_trasera", "description": "Foto trasera del vehiculo", "sort_order": 6},
]

# =============================================================================
# Warnings (category-scoped and element-scoped)
# =============================================================================

WARNINGS_DATA = [
    # --- Advertencias de CATEGORÍA (aplican a toda la categoría) ---
    {
        "code": "mmta_aseicars_prof",
        "message": "Modificaciones de MMTA requieren proyecto completo y verificacion tecnica.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["mmta", "masa maxima", "aumento plazas"],
        },
        "_scope": "category",
    },
    {
        "code": "gas_aseicars_prof",
        "message": "Instalaciones de gas requieren certificacion especifica (+65 EUR certificado).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["gas", "instalacion gas", "butano", "propano", "glp"],
        },
        "_scope": "category",
    },
    {
        "code": "electricos_aseicars_prof",
        "message": "Instalaciones electricas de alta potencia pueden requerir proyecto y boletin electrico.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electricos", "instalacion electrica", "inversor"],
        },
        "_scope": "category",
    },
    {
        "code": "reformas_adicionales_itv",
        "message": "Si en ITV se detectan reformas no declaradas, se cobrara la tarifa correspondiente adicional.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "category",
    },
    {
        "code": "boletin_electrico_aseicars",
        "message": "Certificado combinado de instalacion/revision electricas 12v y 230v: 65 EUR.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electrico", "aire acondicionado", "escalon"],
        },
        "_scope": "category",
    },
    # --- Advertencias vinculadas a ELEMENTOS específicos ---
    {
        "code": "aumento_plazas_consulta",
        "message": "Aumento de plazas requiere consulta previa (+115 EUR adicionales).",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "AUMENTO_PLAZAS",
    },
    {
        "code": "mmta_sin_ensayo",
        "message": "Aumento de MMTA sin ensayo de frenada: +300 EUR (previo consulta).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "AUMENTO_MMTA",
    },
    {
        "code": "mmta_con_ensayo",
        "message": "Aumento de MMTA con ensayo de frenada: +500 EUR (previo consulta).",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "AUMENTO_MMTA",
    },
    {
        "code": "kit_elevacion_mando",
        "message": "Kit de elevacion hidraulica/electrica: solo con mando interior fijo.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "KIT_ESTAB",
    },
    {
        "code": "bola_sin_mmr_warning",
        "message": "Bola sin MMR: NO apta para remolcar, solo portaequipajes. Necesario reparto de cargas.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "BOLA_SIN_MMR",
    },
    {
        "code": "portamotos_soportes",
        "message": "Solo se legaliza los soportes, no el portamotos en si. Necesario reparto de cargas.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "PORTAMOTOS",
    },
    {
        "code": "placas_regulador_ubicacion",
        "message": "El regulador debe estar en interior de zona maletero o dentro de portones exteriores. Sujeto a boletin de baja tension.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "PLACA_200W",
    },
    {
        "code": "escalon_boletin",
        "message": "Escalones electricos requieren Boletin Electrico.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ESC_MEC",
    },
    {
        "code": "cerraduras_apertura",
        "message": "La cerradura de acceso a vivienda ha de tener apertura desde el interior.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "CIERRES_EXT",
    },
    {
        "code": "aire_boletin",
        "message": "Aire acondicionado sujeto a boletin electrico.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "AIRE_ACONDI",
    },
    {
        "code": "toldo_galibo",
        "message": "Especial atencion con luz de galibo. Medir nuevo ancho del vehiculo.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "TOLDO_LAT",
    },
    {
        "code": "susp_neum_proyecto",
        "message": "Suspension neumatica requiere proyecto medio (T2).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "SUSP_NEUM",
    },
    {
        "code": "glp_certificacion",
        "message": "Instalaciones de GLP requieren certificado de instalacion/revision de gas (+65 EUR).",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "GLP_INSTALACION",
    },
    {
        "code": "bola_remolque_proyecto",
        "message": "Bola de remolque con extensores de chasis o con proyecto requiere T2.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "BOLA_REMOLQUE",
    },
    {
        "code": "antena_no_tv",
        "message": "No confundir antena parabolica con antenas normales de TV que no son reforma.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ANTENA_PAR",
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
# Prompt Sections (code added for deterministic UUIDs)
# =============================================================================

PROMPT_SECTIONS_DATA = [
    {
        "code": "recognition_table",
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
        "code": "special_cases",
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES AUTOCARAVANAS PROFESIONALES:
1. Instalaciones de gas requieren certificacion
2. MMTA requiere proyecto completo
3. Bola remolque puede o no requerir proyecto segun capacidad""",
        "is_active": True,
    },
]


async def seed_aseicars_professional():
    """Seed the database with aseicars professional data using deterministic UUIDs."""
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
        # 3. Upsert Category-scoped Warnings ONLY
        # (Element-scoped warnings are created later after elements exist)
        # =====================================================================
        for warning_data in WARNINGS_DATA:
            # Skip element-scoped warnings - they'll be created later
            if warning_data.get("_scope") == "element":
                continue

            warning_id = deterministic_warning_uuid(category_slug, warning_data["code"])
            existing_warning = await session.get(Warning, warning_id)

            # Prepare data without internal fields
            data = {k: v for k, v in warning_data.items() if not k.startswith("_")}
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


async def seed_aseicars_element_warnings():
    """
    Seed element-scoped warnings for aseicars-prof.
    Must be called AFTER seed_aseicars_elements() to ensure elements exist.
    """
    from database.models import Element
    category_slug = CATEGORY_DATA["slug"]
    category_id = deterministic_category_uuid(category_slug)

    async with get_async_session() as session:
        logger.info(f"Seeding element-scoped warnings for {category_slug}...")

        for warning_data in WARNINGS_DATA:
            # Only process element-scoped warnings
            if warning_data.get("_scope") != "element":
                continue

            element_code = warning_data.get("_element_code")
            if not element_code:
                continue

            # Find the element by code (not deterministic UUID since elements may have random UUIDs)
            result = await session.execute(
                select(Element).where(
                    Element.category_id == category_id,
                    Element.code == element_code
                )
            )
            element = result.scalar()
            if not element:
                logger.warning(f"  ! Element {element_code} not found, skipping warning {warning_data['code']}")
                continue

            warning_id = deterministic_warning_uuid(category_slug, warning_data["code"])
            existing_warning = await session.get(Warning, warning_id)

            # Prepare data without internal fields
            data = {k: v for k, v in warning_data.items() if not k.startswith("_")}
            data["element_id"] = element.id
            data["category_id"] = None

            if existing_warning:
                for key, value in data.items():
                    setattr(existing_warning, key, value)
                logger.info(f"  ~ Warning {warning_data['code']}: Updated (element: {element_code})")
            else:
                warning = Warning(id=warning_id, **data)
                session.add(warning)
                logger.info(f"  + Warning {warning_data['code']}: Created (element: {element_code})")

        await session.commit()
        logger.info(f"Element warnings for {category_slug} completed!")


if __name__ == "__main__":
    asyncio.run(seed_aseicars_professional())
