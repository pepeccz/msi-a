"""
MSI Automotive - Seed data for Motos category.

Tarifas REV2026 para usuarios finales (particulares).

Run with: python -m database.seeds.motos_seed_v2
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
# Category Data
# =============================================================================

CATEGORY_DATA = {
    "slug": "motos",
    "name": "Motocicletas",
    "description": "Homologacion de reformas en motocicletas",
    "icon": "motorcycle",
}

# =============================================================================
# Tariff Tiers - PARTICULARES (REV2026 - precios SIN IVA)
# =============================================================================

TIERS_PARTICULAR = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "description": "Transformacion completa con proyectos complejos",
        "price": Decimal("410.00"),
        "conditions": "Modificacion distancia ejes, subchasis, horquilla/tren delantero, sistema frenado (bomba, pinzas, discos), cambio motor, llantas/neumaticos con ensayo",
        "client_type": "particular",
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
        "client_type": "particular",
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
        "client_type": "particular",
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
        "client_type": "particular",
        "classification_rules": {
            "applies_if_any": [
                # Este tier se activa por conteo de elementos (min_elements: 3)
            ],
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
        "client_type": "particular",
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
        "client_type": "particular",
        "classification_rules": {
            "applies_if_any": [
                # Elementos simples que activan T6 directamente
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
# Base Documentation (required for all motorcycle homologations)
# =============================================================================

BASE_DOCUMENTATION_DATA = [
    {
        "description": "Ficha tecnica del vehiculo (ambas caras, legible)",
        "image_url": None,
        "sort_order": 1,
    },
    {
        "description": "Permiso de circulacion por la cara escrita",
        "image_url": None,
        "sort_order": 2,
    },
    {
        "description": "Foto lateral derecha completa de la moto",
        "image_url": None,
        "sort_order": 3,
    },
    {
        "description": "Foto lateral izquierda completa de la moto",
        "image_url": None,
        "sort_order": 4,
    },
    {
        "description": "Foto frontal de la moto",
        "image_url": None,
        "sort_order": 5,
    },
    {
        "description": "Foto trasera de la moto",
        "image_url": None,
        "sort_order": 6,
    },
]

# =============================================================================
# Element Documentation (keyword-based, triggered by AI)
# =============================================================================

ELEMENT_DOCUMENTATION_DATA = [
    {
        "element_keywords": ["escape", "linea de escape", "silenciador", "colector"],
        "description": "Foto del escape instalado mostrando el marcado de homologacion (numero E visible). El silencioso debe estar homologado para dicho vehiculo.",
        "image_url": None,
        "sort_order": 1,
    },
    {
        "element_keywords": ["faros", "faro", "faro led", "faro delantero", "optica"],
        "description": "Foto del faro instalado mostrando el marcado de homologacion",
        "image_url": None,
        "sort_order": 2,
    },
    {
        "element_keywords": ["retrovisores", "retrovisor", "espejos", "espejo"],
        "description": "Foto de los retrovisores instalados mostrando el marcado de homologacion (numero E) y correcta ubicacion",
        "image_url": None,
        "sort_order": 3,
    },
    {
        "element_keywords": ["intermitentes", "intermitente", "indicadores"],
        "description": "Foto de los intermitentes instalados mostrando el marcado de homologacion, montados a alturas y angulos correctos",
        "image_url": None,
        "sort_order": 4,
    },
    {
        "element_keywords": ["pilotos", "piloto", "luz trasera", "faro trasero"],
        "description": "Foto del piloto trasero instalado mostrando el marcado de homologacion",
        "image_url": None,
        "sort_order": 5,
    },
    {
        "element_keywords": ["neumaticos", "neumatico", "ruedas", "rueda"],
        "description": "Foto de los neumaticos mostrando marca, modelo y medidas visibles",
        "image_url": None,
        "sort_order": 6,
    },
    {
        "element_keywords": ["llantas", "llanta"],
        "description": "Foto de las llantas mostrando el marcado de homologacion y medidas",
        "image_url": None,
        "sort_order": 7,
    },
    {
        "element_keywords": ["suspension", "amortiguadores", "amortiguador", "barras", "muelles"],
        "description": "Foto de la suspension/amortiguadores instalados",
        "image_url": None,
        "sort_order": 8,
    },
    {
        "element_keywords": ["manillar", "semi manillares", "semimanillares"],
        "description": "Foto del manillar instalado. Consultar dimensiones de cuelgamonos en vehiculos modernos y aristas cortantes en manillares tipo Z",
        "image_url": None,
        "sort_order": 9,
    },
    {
        "element_keywords": ["matricula", "emplazamiento matricula", "brazo lateral"],
        "description": "Foto del nuevo emplazamiento de matricula. Desde julio 2025 es posible matricula lateral. Incluye cambio de luz de matricula",
        "image_url": None,
        "sort_order": 10,
    },
    {
        "element_keywords": ["velocimetro", "cuentakilometros"],
        "description": "Foto del velocimetro instalado. Si no es digital, puede llevar recargo de laboratorio",
        "image_url": None,
        "sort_order": 11,
    },
    {
        "element_keywords": ["deposito", "deposito combustible"],
        "description": "Foto del deposito de combustible instalado/reubicado",
        "image_url": None,
        "sort_order": 12,
    },
    {
        "element_keywords": ["carroceria", "carenado", "carenados", "colin", "tapas laterales"],
        "description": "Fotos de la carroceria exterior modificada (carenados, tapas laterales, colin, etc.)",
        "image_url": None,
        "sort_order": 13,
    },
]

# =============================================================================
# Warnings (element-specific, triggered by keywords)
# =============================================================================

WARNINGS_DATA = [
    {
        "code": "marcado_homologacion_motos",
        "message": "Este elemento requiere marcado de homologacion visible (numero E). Asegurate de que tu pieza lo tenga antes de proceder.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": [
                "escape", "silenciador", "faros", "faro", "retrovisores", "retrovisor",
                "intermitentes", "pilotos", "piloto", "luz freno",
                "neumaticos", "llantas", "catadiptricos",
            ],
        },
    },
    {
        "code": "ensayo_frenada_motos",
        "message": "Modificaciones en sistema de frenado pueden requerir ensayo de frenada adicional (375 EUR). Consultar con ingeniero.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "frenos", "disco freno", "pinza freno", "bomba freno",
                "sistema de frenado", "discos", "pinzas",
            ],
        },
    },
    {
        "code": "ensayo_direccion_motos",
        "message": "Modificacion de distancia entre ejes puede requerir ensayo de direccion (400 EUR). Consultar con ingeniero.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "distancia ejes", "distancia entre ejes",
            ],
        },
    },
    {
        "code": "consultar_ingeniero_motos",
        "message": "Esta modificacion es compleja. Se recomienda consultar viabilidad con el ingeniero antes de proceder.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": [
                "subchasis", "aumento plazas", "motor", "horquilla completa",
            ],
        },
    },
    {
        "code": "recargo_laboratorio_motos",
        "message": "Esta modificacion puede llevar recargo de laboratorio (25-75 EUR) por complejidad o velocimetro no digital.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "velocimetro", "filtro",
            ],
        },
    },
    {
        "code": "perdida_plaza_motos",
        "message": "IMPORTANTE: Esta modificacion puede implicar la perdida de la 2a plaza. Debe consultarse con el ingeniero antes de proceder.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": [
                "subchasis", "modificacion subchasis",
            ],
        },
    },
    {
        "code": "suspension_delantera_motos",
        "message": "Para suspension delantera, solo se homologan barras o muelles interiores de barras (no la horquilla completa).",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "suspension delantera", "barras suspension",
            ],
        },
    },
    {
        "code": "velocimetro_soporte_motos",
        "message": "NOTA: No se homologa la posicion del velocimetro, sino unicamente el soporte para su reubicacion.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "velocimetro", "emplazamiento velocimetro", "soporte velocimetro",
            ],
        },
    },
    {
        "code": "matricula_luz_motos",
        "message": "El cambio de emplazamiento de matricula lleva asociado obligatoriamente el cambio de luz de matricula. Desde julio de 2025 es posible matricula lateral.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "matricula", "emplazamiento matricula", "brazo lateral",
            ],
        },
    },
    {
        "code": "escape_homologado_motos",
        "message": "El escape debe tener homologacion especifica para tu modelo de moto. Si el silencioso ya esta homologado para dicho vehiculo, NO es reforma.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": [
                "escape", "silenciador", "linea escape",
            ],
        },
    },
    {
        "code": "manillar_restricciones_motos",
        "message": "Para manillares: consultar dimensiones de cuelgamonos en vehiculos modernos y evitar aristas cortantes (especialmente manillares tipo Z).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": [
                "manillar", "semimanillares", "semi manillares",
            ],
        },
    },
    {
        "code": "antiniebla_pictograma_motos",
        "message": "Los faros antiniebla requieren pictograma obligatorio en el boton de encendido.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": [
                "antiniebla", "faros antiniebla",
            ],
        },
    },
]

# =============================================================================
# Additional Services (REV2026 - precios SIN IVA)
# =============================================================================

ADDITIONAL_SERVICES_DATA = [
    {
        "code": "certificado_taller_motos",
        "name": "Certificado taller concertado",
        "description": "Certificado si la instalacion la realiza un taller concertado",
        "price": Decimal("85.00"),
        "sort_order": 1,
    },
    {
        "code": "urgencia_motos",
        "name": "Tramitacion urgente",
        "description": "Tramitacion urgente 24/36h. Requiere documentacion completa",
        "price": Decimal("100.00"),
        "sort_order": 2,
    },
    {
        "code": "plus_lab_simple_motos",
        "name": "Plus laboratorio simple",
        "description": "Recargo por envio a laboratorio habitual",
        "price": Decimal("25.00"),
        "sort_order": 3,
    },
    {
        "code": "plus_lab_complejo_motos",
        "name": "Plus laboratorio complejo",
        "description": "Recargo por envio a laboratorios premium o diferente al habitual",
        "price": Decimal("75.00"),
        "sort_order": 4,
    },
    {
        "code": "ayudas_digitales_motos",
        "name": "Ayudas digitales",
        "description": "Asistencia digital para completar expedientes (precio por hora)",
        "price": Decimal("30.00"),
        "sort_order": 5,
    },
    {
        "code": "ensayo_frenada_motos",
        "name": "Ensayo dinamico de frenada",
        "description": "Ensayo dinamico de frenada en laboratorio",
        "price": Decimal("375.00"),
        "sort_order": 6,
    },
    {
        "code": "ensayo_direccion_motos",
        "name": "Ensayo de direccion",
        "description": "Ensayo de direccion en laboratorio",
        "price": Decimal("400.00"),
        "sort_order": 7,
    },
    {
        "code": "ensayo_combinado_motos",
        "name": "Ensayo combinado",
        "description": "Ensayo combinado de direccion y frenada",
        "price": Decimal("725.00"),
        "sort_order": 8,
    },
    {
        "code": "coord_ensayo_motos",
        "name": "Coordinacion de ensayo",
        "description": "Incremento por coordinacion del ensayo (con o sin proyecto)",
        "price": Decimal("50.00"),
        "sort_order": 9,
    },
]

# =============================================================================
# Prompt Sections (Dynamic prompt content for AI)
# =============================================================================

PROMPT_SECTIONS_DATA = [
    {
        "section_type": "recognition_table",
        "content": """| Elemento | Keywords de reconocimiento | Tarifa tipica |
|----------|---------------------------|---------------|
| Escape completo | escape, silenciador, colector | T6 (1 elem) / T4 (>=2) |
| Retrovisores | retrovisores, espejos | T6 (1 elem) / T4 (>=2) |
| Faros LED | faros, faro led, optica | T6 (1 elem) / T4 (>=2) |
| Suspension | suspension, amortiguadores | T3 (con proyecto) |
| Manillar | manillar, semimanillares | T6 (1 elem) / T4 (>=2) |
| Sistema frenado | bomba freno, pinzas, discos | T1 (requiere ensayo) |
| Cambio motor | motor, cambio motor | T1 (proyecto completo) |
| Matricula | matricula, brazo lateral | T6 (1 elem) / T4 (>=2) |
| Aumento plazas | aumento plazas, segunda plaza | T2 (proyecto medio) |

**IMPORTANTE:** Elementos que requieren marcado de homologacion (numero E): escape, faros, retrovisores, intermitentes, pilotos.""",
        "is_active": True,
        "version": 1,
    },
    {
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES MOTOS (REV2026):

1. **Matricula lateral**: Desde julio 2025 es posible matricula lateral. Siempre lleva cambio de luz de matricula asociado.

2. **Escape homologado**: Si el silencioso ya esta homologado especificamente para el modelo de moto, NO es reforma.

3. **Velocimetro**: No se homologa la posicion del velocimetro, sino el soporte para su reubicacion.

4. **Subchasis**: Puede implicar perdida de 2a plaza. Siempre consultar con ingeniero.

5. **Ensayos obligatorios**:
   - Modificacion distancia entre ejes -> Ensayo direccion (400 EUR)
   - Cambio sistema frenado (bomba/pinzas/discos) -> Ensayo frenada (375 EUR)
   - Llantas/neumaticos con ensayo -> segun caso""",
        "is_active": True,
        "version": 1,
    },
]


async def seed_motos_data():
    """Seed the database with motorcycle tariff data (REV2026)."""
    async with get_async_session() as session:
        # Check if category already exists
        existing = await session.execute(
            select(VehicleCategory).where(VehicleCategory.slug == CATEGORY_DATA["slug"])
        )
        if existing.scalar():
            logger.info("Motos category already exists, skipping seed")
            return

        logger.info("Creating motos (motorcycles) category...")

        # Create category
        category = VehicleCategory(**CATEGORY_DATA)
        session.add(category)
        await session.flush()  # Get the category ID

        # Create warnings (only if they don't exist)
        logger.info("Creating warnings...")
        for warning_data in WARNINGS_DATA:
            existing_warning = await session.execute(
                select(Warning).where(Warning.code == warning_data["code"])
            )
            if not existing_warning.scalar():
                warning = Warning(**warning_data)
                session.add(warning)

        # Create tiers for particulars
        logger.info("Creating particular tariff tiers...")
        for tier_data in TIERS_PARTICULAR:
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

        # Create additional services
        logger.info("Creating additional services...")
        for service_data in ADDITIONAL_SERVICES_DATA:
            service = AdditionalService(category_id=category.id, **service_data)
            session.add(service)

        # Create prompt sections
        logger.info("Creating prompt sections...")
        for section_data in PROMPT_SECTIONS_DATA:
            section = TariffPromptSection(category_id=category.id, **section_data)
            session.add(section)

        await session.commit()
        logger.info("Motos seed data created successfully! (REV2026 tariffs)")


async def main():
    """Run the seed script."""
    await seed_motos_data()


if __name__ == "__main__":
    asyncio.run(main())
