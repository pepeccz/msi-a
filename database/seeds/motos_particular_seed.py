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
    {"code": "ficha_tecnica", "description": "Ficha tecnica del vehiculo (ambas caras, legible)", "sort_order": 1},
    {"code": "permiso_circulacion", "description": "Permiso de circulacion por la cara escrita", "sort_order": 2},
    {"code": "foto_lateral_derecha", "description": "Foto lateral derecha completa de la moto", "sort_order": 3},
    {"code": "foto_lateral_izquierda", "description": "Foto lateral izquierda completa de la moto", "sort_order": 4},
    {"code": "foto_frontal", "description": "Foto frontal de la moto", "sort_order": 5},
    {"code": "foto_trasera", "description": "Foto trasera de la moto", "sort_order": 6},
]

# =============================================================================
# Warnings (category-scoped and element-scoped)
# =============================================================================

WARNINGS_DATA = [
    # --- Advertencias de CATEGORÍA (aplican a toda la categoría) ---
    {
        "code": "marcado_homologacion_motos_part",
        "message": "Este elemento requiere marcado de homologacion visible (numero E).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["escape", "faros", "retrovisores", "intermitentes", "pilotos", "neumaticos", "llantas"],
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
    {
        "code": "alumbrado_general_motos_part",
        "message": "Todo alumbrado debe tener marcado de homologacion y montarse a alturas y angulos correctos.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["alumbrado", "faros", "intermitentes", "pilotos", "luces"],
        },
        "_scope": "category",
    },
    {
        "code": "ensayo_direccion_motos_part",
        "message": "Modificaciones en distancia entre ejes pueden requerir ensayo de direccion (+400 EUR).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["distancia ejes", "horquilla completa", "tren delantero"],
        },
        "_scope": "category",
    },
    # --- Advertencias vinculadas a ELEMENTOS específicos ---
    {
        "code": "subchasis_perdida_plaza",
        "message": "Posible perdida de 2a plaza. Consultar con ingeniero el tipo de modificacion. No es posible cortar por delante del sistema de amortiguacion sin perdida de plaza.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "SUBCHASIS",
    },
    {
        "code": "horquilla_ensayo_frenada",
        "message": "Cambio de horquilla/tren delantero puede requerir ensayo de frenada (+375 EUR).",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "HORQUILLA",
    },
    {
        "code": "frenado_discos_ensayo",
        "message": "Puede requerir ensayo de frenada (+375 EUR).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "FRENADO_DISCOS",
    },
    {
        "code": "frenado_pinzas_ensayo",
        "message": "Puede requerir ensayo de frenada (+375 EUR).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "FRENADO_PINZAS",
    },
    {
        "code": "frenado_bombas_ensayo",
        "message": "Puede requerir ensayo de frenada (+375 EUR).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "FRENADO_BOMBAS",
    },
    {
        "code": "escape_homologacion",
        "message": "Debe disponer de homologacion para el vehiculo. El silencioso no es reforma si esta homologado para dicho vehiculo.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ESCAPE",
    },
    {
        "code": "filtro_recargo_lab",
        "message": "Puede llevar recargo de laboratorio. Solo se puede hacer esta reforma en la moto - CONSULTAR.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "FILTRO",
    },
    {
        "code": "velocimetro_recargo",
        "message": "Si el velocimetro no es digital, llevara recargo de laboratorio (+25/75 EUR). No se homologa la posicion sino el soporte.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "VELOCIMETRO",
    },
    {
        "code": "matricula_luz_asociada",
        "message": "Desde julio 2025 es posible matricula lateral. Lleva asociado cambio de luz de matricula como minimo. Distancia max 30cm al final.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "MATRICULA",
    },
    {
        "code": "manillar_dimensiones",
        "message": "Consultar dimensiones de cuelgamonos en vehiculos modernos y aristas cortantes en manillares Z. En motos 168/2013 (desde 2016), medida maxima 380mm.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "MANILLAR",
    },
    {
        "code": "espejos_requisitos",
        "message": "Requieren homologacion y correcta ubicacion. Distancia minima 560mm entre centros. La contrasena de ambos espejos ha de ser IGUAL.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ESPEJOS",
    },
    {
        "code": "faro_largo_alcance",
        "message": "Dependiendo del tipo de faros, se podria anular el largo alcance del faro principal.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "FARO_DELANTERO",
    },
    {
        "code": "intermitentes_del_distancia",
        "message": "Minima distancia 240mm entre bordes interiores.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "INTERMITENTES_DEL",
    },
    {
        "code": "intermitentes_tras_angulo",
        "message": "Minima distancia 7.5cm entre bordes exteriores. Angulo interior 20 grados (50 grados si lleva luz de freno).",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "INTERMITENTES_TRAS",
    },
    {
        "code": "piloto_freno_angulo",
        "message": "Si combinado con intermitentes, angulo de visibilidad 50 grados.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "PILOTO_FRENO",
    },
    {
        "code": "catadioptrico_altura",
        "message": "Debe estar perpendicular al suelo. Altura: min 250mm, max 900mm.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "CATADIOPTRICO",
    },
    {
        "code": "antinieblas_pictograma",
        "message": "Necesario pictograma homologado en el boton de encendido.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ANTINIEBLAS",
    },
    {
        "code": "mandos_pictogramas",
        "message": "Los nuevos mandos deben disponer de pictogramas homologados segun su funcion.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "MANDOS_MANILLAR",
    },
    {
        "code": "neumaticos_ensayo",
        "message": "Si el neumatico DELANTERO supera 10% en diametro o TRASERO supera 8%, posible ensayo de frenada.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "NEUMATICOS",
    },
    {
        "code": "llantas_sin_ensayo",
        "message": "Sustitucion sin ensayo. Verificar compatibilidad con neumaticos.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "LLANTAS",
    },
    {
        "code": "asideros_plaza",
        "message": "De no disponer de asideros, se perderia la plaza trasera.",
        "severity": "warning",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "ASIDEROS",
    },
    {
        "code": "suspension_del_barras",
        "message": "Solo barras o muelles interiores de barras para proyecto sencillo.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "SUSPENSION_DEL",
    },
    {
        "code": "carenado_material",
        "message": "Indicar material del carenado sustituido/instalado. Minimo ancho del guardabarros igual al del neumatico.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "CARENADO",
    },
    {
        "code": "deposito_homologacion",
        "message": "Si deposito nuevo, necesaria foto de la etiqueta con contrasena de homologacion.",
        "severity": "info",
        "trigger_conditions": {},
        "_scope": "element",
        "_element_code": "DEPOSITO",
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


async def seed_motos_element_warnings():
    """
    Seed element-scoped warnings for motos-part.
    Must be called AFTER seed_motos_elements() to ensure elements exist.
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
    asyncio.run(seed_motos_particular())
