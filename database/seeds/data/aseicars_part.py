"""
MSI-a Seed Data - Autocaravanas Particular (aseicars-part).

Complete data definitions for motorhome homologations for particular clients.
Based on: 2026 TARIFAS PARTICULARES REGULARIZACION ELEMENTOS AUTOCARAVANAS.pdf
"""

from decimal import Decimal

from database.seeds.data.common import (
    CategoryData,
    TierData,
    ElementData,
    WarningData,
    AdditionalServiceData,
    BaseDocumentationData,
    PromptSectionData,
    BASE_DOCUMENTATION_COMMON,
)

# =============================================================================
# Category Identifier
# =============================================================================

CATEGORY_SLUG = "aseicars-part"

# =============================================================================
# Category Definition
# =============================================================================

CATEGORY: CategoryData = {
    "slug": CATEGORY_SLUG,
    "name": "Autocaravanas (32xx, 33xx)",
    "description": "Regularizacion de elementos en autocaravanas y campers (particulares)",
    "icon": "caravan",
    "client_type": "particular",
}

# =============================================================================
# Tariff Tiers (T1-T6)
# =============================================================================

TIERS: list[TierData] = [
    {
        "code": "T1",
        "name": "Proyecto Completo",
        "description": "Sin limite de elementos + reformas estructurales",
        "price": Decimal("300.00"),
        "conditions": "Incluye refuerzos suspensiones, aumento plazas, MMTA, proyectos complejos",
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
        "price": Decimal("265.00"),
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
        "price": Decimal("225.00"),
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
        "price": Decimal("195.00"),
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
        "sort_order": 4,
        "min_elements": 4,
    },
    {
        "code": "T5",
        "name": "Hasta 3 elementos",
        "description": "Regularizacion de 1-3 elementos simples",
        "price": Decimal("145.00"),
        "conditions": "Hasta 3 elementos T6 + placas solares en maletero",
        "classification_rules": {
            "applies_if_any": [
                "placas solares maletero",
            ],
            "priority": 5,
            "requires_project": False,
        },
        "sort_order": 5,
        "min_elements": 1,
        "max_elements": 3,
    },
    {
        "code": "T6",
        "name": "1 elemento",
        "description": "Elemento unico simple",
        "price": Decimal("75.00"),
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
        "sort_order": 6,
        "min_elements": 1,
        "max_elements": 1,
    },
]

# =============================================================================
# Elements
# =============================================================================

ELEMENTS: list[ElementData] = [
    # =========================================================================
    # ELEMENTOS BASE (20 elementos copiados de aseicars_prof)
    # =========================================================================
    {
        "code": "ESCALON_ELEC",
        "name": "Escalon electrico",
        "description": "Escalon electrico retractil instalado en parte trasera del vehiculo",
        "keywords": ["escalon", "escalon electrico", "peldano electrico", "escalera", "escalera electrica"],
        "aliases": ["peldanos", "acceso techo", "escalerilla"],
        "sort_order": 10,
        "images": [
            {"title": "Vista trasera cerrada", "description": "Escalon en posicion de transporte, cerrado", "image_type": "example", "sort_order": 1},
            {"title": "Vista trasera abierta", "description": "Escalon completamente desplegado", "image_type": "example", "sort_order": 2},
            {"title": "Foto con matricula", "description": "Foto con matricula visible y escalon desplegado", "image_type": "required_document", "sort_order": 3},
            {"title": "Placa del fabricante", "description": "Placa del fabricante con numero de serie y especificaciones", "image_type": "required_document", "sort_order": 4},
        ],
        "warnings": [
            {"code": "escalon_boletin_part", "message": "Escalones electricos requieren Boletin Electrico.", "severity": "warning"},
        ],
    },
    {
        "code": "TOLDO_LAT",
        "name": "Toldo lateral",
        "description": "Toldo retractil instalado en lateral del vehiculo. Selecciona la variante segun si afecta al galibo.",
        "keywords": ["toldo", "toldo lateral", "toldo retractil", "lona"],
        "aliases": ["tolva", "parasol lateral"],
        "sort_order": 20,
        "is_base": True,
        "question_hint": "¿El toldo afecta a la luz de galibo del vehiculo (aumenta el ancho)?",
        "images": [
            {"title": "Toldo cerrado", "description": "Toldo recogido en su posicion de transporte", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "toldo_galibo_info_part", "message": "La documentacion varia segun si el toldo afecta a la luz de galibo del vehiculo.", "severity": "info"},
        ],
    },
    {
        "code": "PLACA_SOLAR",
        "name": "Placa solar",
        "description": "Placa solar fotovoltaica instalada en techo. Selecciona la variante segun la ubicacion del regulador.",
        "keywords": ["placa solar", "placa fotovoltaica", "solar", "panel solar", "200w", "placas solares"],
        "aliases": ["modulo solar", "panel"],
        "sort_order": 30,
        "is_base": True,
        "question_hint": "¿El regulador de la placa solar esta en el interior del vehiculo o en zona de maletero/porton exterior?",
        "images": [
            {"title": "Placa solar", "description": "Placa solar instalada en techo", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "placas_regulador_info_part", "message": "La documentacion varia segun donde este ubicado el regulador (interior o maletero/porton).", "severity": "info"},
        ],
    },
    {
        "code": "ANTENA_PAR",
        "name": "Antena parabolica",
        "description": "Antena parabolica para recepcion de satelite",
        "keywords": ["antena", "antena parabolica", "parabolica", "satelite"],
        "aliases": ["dish", "receptor satelite"],
        "sort_order": 40,
        "images": [
            {"title": "Antena instalada", "description": "Antena parabolica instalada en techo", "image_type": "example", "sort_order": 1},
            {"title": "Foto frontal", "description": "Foto frontal del vehiculo con antena visible", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "antena_no_tv_part", "message": "No confundir antena parabolica con antenas normales de TV que no son reforma.", "severity": "info"},
        ],
    },
    {
        "code": "PORTABICIS",
        "name": "Portabicis trasero",
        "description": "Portabicis montado en la parte trasera del vehiculo",
        "keywords": ["portabicis", "portabike", "bicicletas", "bike rack"],
        "aliases": ["soportebicis", "rack bicicletas"],
        "sort_order": 50,
        "images": [
            {"title": "Portabicis vacio", "description": "Portabicis sin bicicletas", "image_type": "example", "sort_order": 1},
            {"title": "Con bicicletas", "description": "Portabicis con bicicletas instaladas", "image_type": "example", "sort_order": 2},
            {"title": "Foto trasera con matricula", "description": "Foto trasera del vehiculo con portabicis y matricula visible", "image_type": "required_document", "sort_order": 3},
        ],
    },
    {
        "code": "CLARABOYA",
        "name": "Claraboya adicional",
        "description": "Claraboya o ventana cenital adicional en techo. Tambien incluye ventanas y portones.",
        "keywords": ["claraboya", "ventana techo", "lucernario", "ventilacion", "ventana", "ventanas", "porton", "portones"],
        "aliases": ["skylight", "ventana cenital"],
        "sort_order": 60,
        "images": [
            {"title": "Claraboya cerrada", "description": "Claraboya en posicion cerrada", "image_type": "example", "sort_order": 1},
            {"title": "Foto interior", "description": "Foto del interior mostrando la claraboya", "image_type": "example", "sort_order": 2},
            {"title": "Foto exterior", "description": "Foto exterior del techo con claraboya visible", "image_type": "required_document", "sort_order": 3},
        ],
    },
    {
        "code": "BACA_TECHO",
        "name": "Baca portaequipajes",
        "description": "Baca metalica para portaequipajes en techo",
        "keywords": ["baca", "portaequipajes", "roof rack", "rack techo"],
        "aliases": ["jaula techo", "soporte techo"],
        "sort_order": 70,
        "images": [
            {"title": "Baca vacia", "description": "Baca sin carga", "image_type": "example", "sort_order": 1},
            {"title": "Detalle montaje", "description": "Detalle de como esta montada la baca", "image_type": "example", "sort_order": 2},
            {"title": "Foto con matricula", "description": "Foto general del vehiculo con baca visible y matricula", "image_type": "required_document", "sort_order": 3},
        ],
    },
    {
        "code": "BOLA_REMOLQUE",
        "name": "Bola de remolque",
        "description": "Enganche de remolque tipo bola. Selecciona la variante segun si aumenta o no la MMR.",
        "keywords": ["bola remolque", "enganche", "bola", "remolque", "mmr"],
        "aliases": ["coupling", "tow ball"],
        "sort_order": 80,
        "is_base": True,
        "question_hint": "¿La instalacion aumenta la masa maxima del remolque (MMR) o no?",
        "images": [
            {"title": "Bola remolque", "description": "Bola de remolque instalada", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "bola_remolque_proyecto_part", "message": "Bola de remolque con extensores de chasis o con proyecto requiere T2.", "severity": "info"},
        ],
    },
    {
        "code": "NEVERA_COMPRESOR",
        "name": "Nevera de compresor",
        "description": "Nevera portatil con compresor de corriente continua",
        "keywords": ["nevera", "frigorifico", "compresor", "congelador"],
        "aliases": ["cooling box", "fridge"],
        "sort_order": 90,
        "images": [
            {"title": "Nevera instalada", "description": "Nevera de compresor instalada en interior", "image_type": "example", "sort_order": 1},
            {"title": "Foto interior", "description": "Foto del interior mostrando la nevera", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "DEPOSITO_AGUA",
        "name": "Deposito de agua adicional",
        "description": "Deposito de agua dulce adicional instalado en vehiculo",
        "keywords": ["deposito agua", "tanque agua", "agua dulce", "deposito"],
        "aliases": ["water tank", "fresh water"],
        "sort_order": 100,
        "images": [
            {"title": "Deposito instalado", "description": "Deposito de agua adicional en exterior", "image_type": "example", "sort_order": 1},
            {"title": "Placa identificativa", "description": "Placa con especificaciones del deposito", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "AIRE_ACONDI",
        "name": "Aire acondicionado",
        "description": "Sistema de aire acondicionado instalado en el vehiculo. Requiere boletin electrico.",
        "keywords": ["aire acondicionado", "ac", "climatizador", "clima", "aire"],
        "aliases": ["air conditioning", "climatizacion"],
        "sort_order": 110,
        "is_active": True,
        "images": [
            {"title": "Unidad exterior", "description": "Unidad de aire acondicionado instalada en techo", "image_type": "example", "sort_order": 1},
            {"title": "Panel de control", "description": "Panel de control interior del aire acondicionado", "image_type": "example", "sort_order": 2},
            {"title": "Foto con matricula", "description": "Foto general del vehiculo con AC visible y matricula", "image_type": "required_document", "sort_order": 3},
        ],
        "warnings": [
            {"code": "placa_boletin_bt_part", "message": "Requiere Boletin de Baja Tension (+65 EUR).", "severity": "warning"},
        ],
    },
    {
        "code": "TOLDO_SIMPLE",
        "name": "Toldo lateral (sin afectar galibo)",
        "description": "Toldo lateral que NO afecta a la luz de galibo del vehiculo (no aumenta el ancho).",
        "keywords": ["sin galibo", "no afecta", "mismo ancho", "no aumenta ancho", "no", "sin", "igual ancho", "no cambia"],
        "aliases": [],
        "sort_order": 21,
        "parent_code": "TOLDO_LAT",
        "variant_type": "galibo_impact",
        "variant_code": "SIN_GALIBO",
        "images": [
            {"title": "Toldo cerrado", "description": "Toldo recogido en su posicion de transporte", "image_type": "example", "sort_order": 1},
            {"title": "Toldo extendido", "description": "Toldo completamente desplegado", "image_type": "example", "sort_order": 2},
            {"title": "Foto extension completa", "description": "Toldo completamente extendido con soportes", "image_type": "required_document", "sort_order": 3},
            {"title": "Placa identificativa", "description": "Placa del fabricante del toldo", "image_type": "required_document", "sort_order": 4},
        ],
    },
    {
        "code": "TOLDO_GALIBO",
        "name": "Toldo lateral (afecta galibo)",
        "description": "Toldo lateral que SI afecta a la luz de galibo del vehiculo (aumenta el ancho). Requiere documentacion adicional de medidas.",
        "keywords": ["con galibo", "afecta galibo", "mas ancho", "aumenta ancho", "si", "afecta", "mayor ancho", "sobresale"],
        "aliases": [],
        "sort_order": 22,
        "parent_code": "TOLDO_LAT",
        "variant_type": "galibo_impact",
        "variant_code": "CON_GALIBO",
        "images": [
            {"title": "Toldo cerrado", "description": "Toldo recogido en su posicion de transporte", "image_type": "example", "sort_order": 1},
            {"title": "Toldo extendido", "description": "Toldo completamente desplegado", "image_type": "example", "sort_order": 2},
            {"title": "Medidas galibo", "description": "Documentacion con las medidas del nuevo galibo (ancho vehiculo)", "image_type": "required_document", "sort_order": 3},
            {"title": "Posicion galibo", "description": "Foto mostrando la posicion de la luz de galibo", "image_type": "required_document", "sort_order": 4},
            {"title": "Foto extension completa", "description": "Toldo completamente extendido con soportes", "image_type": "required_document", "sort_order": 5},
            {"title": "Placa identificativa", "description": "Placa del fabricante del toldo", "image_type": "required_document", "sort_order": 6},
        ],
        "warnings": [
            {"code": "cambio_clasif_proyecto_part", "message": "Cambio de clasificacion requiere proyecto completo (T1).", "severity": "warning"},
        ],
    },

    # =========================================================================
    # VARIANTES DE BOLA_REMOLQUE (3 variantes)
    # =========================================================================
    # VARIANTES DE CAMBIO_CLASIF (2 variantes nuevas)
    # =========================================================================
    {
        "code": "CAMBIO_CLASIF_CON",
        "name": "Cambio de clasificacion CON ITV industrial",
        "description": "Cambio de clasificacion del vehiculo manteniendo el ITV industrial vigente",
        "keywords": ["con itv", "mantiene itv", "itv industrial", "si", "con", "mantener"],
        "aliases": [],
        "sort_order": 301,
        "parent_code": "CAMBIO_CLASIF",
        "variant_type": "itv_option",
        "variant_code": "CON_ITV",
        "images": [
            {"title": "Ficha tecnica", "description": "Ficha tecnica con nueva clasificacion", "image_type": "example", "sort_order": 1},
            {"title": "ITV vigente", "description": "Documentacion del ITV industrial vigente", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "cambio_clasif_con_itv_part", "message": "Mantener ITV industrial puede tener requisitos adicionales.", "severity": "info"},
        ],
    },
    {
        "code": "CAMBIO_CLASIF_SIN",
        "name": "Cambio de clasificacion SIN ITV industrial",
        "description": "Cambio de clasificacion del vehiculo eliminando el ITV industrial",
        "keywords": ["sin itv", "elimina itv", "no itv", "no mantiene", "sin", "eliminar"],
        "aliases": [],
        "sort_order": 302,
        "parent_code": "CAMBIO_CLASIF",
        "variant_type": "itv_option",
        "variant_code": "SIN_ITV",
        "images": [
            {"title": "Ficha tecnica", "description": "Ficha tecnica con nueva clasificacion", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion cambio", "description": "Documentacion del cambio de clasificacion", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "cambio_clasif_sin_itv_part", "message": "Eliminar ITV industrial simplifica el proceso pero puede afectar al uso del vehiculo.", "severity": "info"},
        ],
    },
]

# =============================================================================
# Category-Scoped Warnings
# =============================================================================

CATEGORY_WARNINGS: list[WarningData] = [
    {
        "code": "mmta_aseicars_part",
        "message": "Modificaciones de MMTA requieren proyecto completo y verificacion tecnica.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["mmta", "masa maxima", "aumento plazas"],
        },
    },
    {
        "code": "gas_aseicars_part",
        "message": "Instalaciones de gas requieren certificacion especifica (+65 EUR certificado).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["gas", "instalacion gas", "butano", "propano", "glp"],
        },
    },
    {
        "code": "electricos_aseicars_part",
        "message": "Instalaciones electricas de alta potencia pueden requerir proyecto y boletin electrico.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electricos", "instalacion electrica", "inversor"],
        },
    },
    {
        "code": "reformas_adicionales_itv_part",
        "message": "Si en ITV se detectan reformas no declaradas, se cobrara la tarifa correspondiente adicional.",
        "severity": "warning",
    },
]

# =============================================================================
# Additional Services
# =============================================================================

ADDITIONAL_SERVICES: list[AdditionalServiceData] = [
    {"code": "cert_taller_aseicars", "name": "Certificado taller concertado", "price": Decimal("85.00"), "sort_order": 1},
    {"code": "urgencia_aseicars", "name": "Tramitacion urgente", "price": Decimal("100.00"), "sort_order": 2},
    {"code": "plus_lab_simple_aseicars", "name": "Plus laboratorio simple", "price": Decimal("25.00"), "sort_order": 3},
    {"code": "gestion_itv", "name": "Gestion cita ITV", "price": Decimal("30.00"), "sort_order": 4},
    {"code": "boletin_electrico", "name": "Boletin electrico", "price": Decimal("65.00"), "sort_order": 5},
    {"code": "certificado_gas", "name": "Certificado instalacion gas", "price": Decimal("65.00"), "sort_order": 6},
    {"code": "envio_documentacion", "name": "Envio documentacion postal", "price": Decimal("15.00"), "sort_order": 7},
]

# =============================================================================
# Base Documentation
# =============================================================================

BASE_DOCUMENTATION: list[BaseDocumentationData] = BASE_DOCUMENTATION_COMMON

# =============================================================================
# Prompt Sections
# =============================================================================

PROMPT_SECTIONS: list[PromptSectionData] = [
    {
        "code": "recognition_table",
        "section_type": "recognition_table",
        "content": """| Elemento | Tarifa tipica |
|----------|---------------|
| Placas solares | T6 (1 elem) / T5 (2-3) |
| Toldo lateral | T6 (1 elem) |
| Antena parabolica | T6 (1 elem) |
| Mobiliario interior | T3 (con proyecto) |
| Electricos interior | T3 (con proyecto) |
| Llantas y aletines | T3 (con proyecto) |
| Bola remolque | T4 (sin proyecto) / T2 (con proyecto) |
| Gas | T3 (requiere proyecto) |
| Cambio clasificacion | T1 (proyecto completo) |
| Neumaticos no equiv | T4 (sin proyecto) |""",
        "is_active": True,
    },
    {
        "code": "special_cases",
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES AUTOCARAVANAS PARTICULARES:
1. Instalaciones de gas requieren certificacion (+65 EUR)
2. MMTA requiere proyecto completo
3. Bola remolque puede o no requerir proyecto segun capacidad
4. Placa solar en maletero requiere boletin de baja tension
5. Toldo que afecta galibo requiere medidas del nuevo ancho
6. Cambio de clasificacion requiere proyecto completo""",
        "is_active": True,
    },
]
