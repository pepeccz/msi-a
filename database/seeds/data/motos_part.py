"""
MSI-a Seed Data - Motocicletas Particular (motos-part).

Complete data definitions for motorcycle homologations for end users.
Based on: 2026 TARIFAS USUARIOS FINALES MOTO.pdf
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
    RequiredFieldData,
)

# =============================================================================
# Category Identifier
# =============================================================================

CATEGORY_SLUG = "motos-part"

# =============================================================================
# Category Definition
# =============================================================================

CATEGORY: CategoryData = {
    "slug": CATEGORY_SLUG,
    "name": "Motocicletas",
    "description": "Homologacion de reformas en motocicletas (particulares)",
    "icon": "motorcycle",
    "client_type": "particular",
}

# =============================================================================
# Tariff Tiers (T1-T6)
# =============================================================================

TIERS: list[TierData] = [
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
        "sort_order": 4,
        "min_elements": 3,
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
        "sort_order": 5,
        "min_elements": 2,
        "max_elements": 2,
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
        "sort_order": 6,
        "min_elements": 1,
        "max_elements": 1,
    },
]

# =============================================================================
# Elements (39 elementos)
# =============================================================================

ELEMENTS: list[ElementData] = [
    # =========================================================================
    # GRUPO 1: ESCAPE
    # =========================================================================
    {
        "code": "ESCAPE",
        "name": "Escape / Sistema de escape",
        "description": "Sistema de escape modificado, colector o silenciador aftermarket. Requiere homologacion visible (numero E).",
        "keywords": [
            "escape", "tubo de escape", "colector", "silenciador", "silencioso",
            "deportivo", "akrapovic", "yoshimura", "arrow", "termignoni",
            "sc project", "leovince", "mivv", "remus", "scorpion",
            "linea de escape", "escape completo", "sistema escape"
        ],
        "aliases": ["exhaust", "muffler", "sistema escape"],
        "sort_order": 10,
        "warnings": [
            {
                "code": "escape_homologacion",
                "message": "Debe disponer de homologacion para el vehiculo. El silencioso no es reforma si esta homologado para dicho vehiculo.",
                "severity": "info",
            },
        ],
    },

    # =========================================================================
    # GRUPO 2: CHASIS Y ESTRUCTURA
    # =========================================================================
    {
        "code": "SUBCHASIS",
        "name": "Subchasis",
        "description": "Modificacion del subchasis trasero. IMPORTANTE: No es posible cortar el subchasis por delante del sistema de amortiguacion sin perdida de plaza. Puede implicar cambio de longitud total.",
        "keywords": [
            "subchasis", "corte subchasis", "modificacion subchasis",
            "subchasis trasero", "acortar subchasis", "recorte subchasis",
            "chasis trasero", "estructura trasera"
        ],
        "aliases": ["subframe", "rear subframe"],
        "sort_order": 15,
        "warnings": [
            {
                "code": "subchasis_perdida_plaza",
                "message": "Posible perdida de 2a plaza. Consultar con ingeniero el tipo de modificacion. No es posible cortar por delante del sistema de amortiguacion sin perdida de plaza.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "descripcion_modificacion",
                "field_label": "En qué consiste la modificación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Recorte de 15cm del subchasis trasero",
                "llm_instruction": "Pregunta al usuario en qué consiste exactamente la modificación del subchasis (recorte, sustitución, refuerzo, etc.)",
            },
            {
                "field_key": "medida_desde_tanque",
                "field_label": "Nueva medida desde el tanque (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "450",
                "llm_instruction": "Solicita la nueva medida en milímetros desde el tanque de combustible hasta el final del subchasis",
                "validation_rules": {"min_value": 100, "max_value": 1500},
            },
            {
                "field_key": "nueva_longitud_total",
                "field_label": "Nueva longitud total del vehículo (mm)",
                "field_type": "number",
                "sort_order": 3,
                "is_required": False,
                "example_value": "2100",
                "llm_instruction": "Si la modificación afecta a la longitud total del vehículo, solicita la nueva medida en milímetros",
                "validation_rules": {"min_value": 1500, "max_value": 3000},
            },
        ],
    },
    {
        "code": "ASIDEROS",
        "name": "Asideros / Agarraderas",
        "description": "Sustitucion de asideros por otros de piel o metalicos. IMPORTANTE: De no disponer de asideros, se perderia la plaza trasera.",
        "keywords": [
            "asideros", "agarraderas", "asidero", "agarradera",
            "asidero piel", "asidero metalico", "asidero pasajero",
            "sujecion pasajero", "agarre trasero"
        ],
        "aliases": ["grab rails", "pillion handles", "passenger handles"],
        "sort_order": 17,
        "warnings": [
            {
                "code": "asideros_plaza",
                "message": "De no disponer de asideros, se perderia la plaza trasera.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "tipo_sustitucion",
                "field_label": "Tipo de sustitución",
                "field_type": "select",
                "options": ["Piel", "Metálico"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si los nuevos asideros son de piel o metálicos",
            },
        ],
    },

    # =========================================================================
    # GRUPO 3: SUSPENSION
    # =========================================================================
    # BASE: Elemento generico para suspension (detecta variantes)
    {
        "code": "SUSPENSION",
        "name": "Suspension",
        "description": "Modificacion de suspension. Selecciona la variante segun sea delantera o trasera.",
        "keywords": [
            "suspension", "amortiguador", "amortiguadores",
            "ohlins", "showa", "wp", "kayaba", "yss", "bitubo", "hagon", "marzocchi"
        ],
        "aliases": ["suspension"],
        "sort_order": 19,
        "is_base": True,
        "question_hint": "¿Es la suspension delantera o la trasera?",
        "multi_select_keywords": [
            "ambas", "las dos", "delantera y trasera", "trasera y delantera",
            "ambos amortiguadores", "los dos amortiguadores",
        ],
    },
    # VARIANTE: Suspension delantera
    {
        "code": "SUSPENSION_DEL",
        "name": "Suspension delantera (barras/muelles)",
        "description": "Modificacion de barras o muelles de la suspension delantera. Para cambio de horquilla completa usar elemento HORQUILLA.",
        "keywords": [
            "suspension delantera", "barras suspension", "muelles barras",
            "barras de horquilla", "muelles suspension", "fork springs",
            "delantera", "frontal", "delante"
        ],
        "aliases": ["front suspension", "fork springs", "suspension bars"],
        "sort_order": 20,
        "parent_code": "SUSPENSION",
        "variant_type": "position",
        "variant_code": "DEL",
        "warnings": [
            {
                "code": "suspension_del_barras",
                "message": "Solo barras o muelles interiores de barras para proyecto sencillo.",
                "severity": "info",
            },
        ],
    },
    # VARIANTE: Suspension trasera
    {
        "code": "SUSPENSION_TRAS",
        "name": "Suspension trasera",
        "description": "Amortiguador trasero o mono modificado. Incluye muelle (marca, modelo, longitud, grosor espira, diametro) y amortiguador.",
        "keywords": [
            "suspension trasera", "amortiguador trasero",
            "mono", "muelle trasero", "shock", "mono shock",
            "muelles traseros", "trasera", "detras", "posterior"
        ],
        "aliases": ["rear suspension", "rear shock", "mono amortiguador"],
        "sort_order": 30,
        "parent_code": "SUSPENSION",
        "variant_type": "position",
        "variant_code": "TRAS",
        "required_fields": [
            {
                "field_key": "marca_muelle",
                "field_label": "Marca del muelle",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Ohlins",
                "llm_instruction": "Solicita la marca del muelle de la suspensión trasera",
            },
            {
                "field_key": "modelo_muelle",
                "field_label": "Modelo del muelle",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "S46DR1",
                "llm_instruction": "Solicita el modelo específico del muelle",
            },
            {
                "field_key": "longitud_muelle",
                "field_label": "Longitud del muelle (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "280",
                "llm_instruction": "Solicita la longitud del muelle en milímetros",
                "validation_rules": {"min_value": 100, "max_value": 500},
            },
            {
                "field_key": "grosor_espira",
                "field_label": "Grosor de espira (mm)",
                "field_type": "number",
                "sort_order": 4,
                "example_value": "12",
                "llm_instruction": "Solicita el grosor de la espira del muelle en milímetros",
                "validation_rules": {"min_value": 5, "max_value": 30},
            },
            {
                "field_key": "diametro_muelle",
                "field_label": "Diámetro del muelle (mm)",
                "field_type": "number",
                "sort_order": 5,
                "example_value": "46",
                "llm_instruction": "Solicita el diámetro exterior del muelle en milímetros",
                "validation_rules": {"min_value": 30, "max_value": 100},
            },
            {
                "field_key": "cambio_amortiguador",
                "field_label": "¿Se cambia también el amortiguador?",
                "field_type": "boolean",
                "sort_order": 6,
                "llm_instruction": "Pregunta si además del muelle también se sustituye el amortiguador",
            },
            {
                "field_key": "marca_amortiguador",
                "field_label": "Marca del amortiguador",
                "field_type": "text",
                "sort_order": 7,
                "is_required": False,
                "example_value": "Ohlins",
                "llm_instruction": "Si se cambia el amortiguador, solicita la marca",
                "condition_field_key": "cambio_amortiguador",
                "condition_operator": "equals",
                "condition_value": "true",
            },
            {
                "field_key": "modelo_amortiguador",
                "field_label": "Modelo del amortiguador",
                "field_type": "text",
                "sort_order": 8,
                "is_required": False,
                "example_value": "TTX GP",
                "llm_instruction": "Si se cambia el amortiguador, solicita el modelo",
                "condition_field_key": "cambio_amortiguador",
                "condition_operator": "equals",
                "condition_value": "true",
            },
        ],
    },
    {
        "code": "HORQUILLA",
        "name": "Horquilla completa / Tren delantero",
        "description": "Sustitucion de horquilla completa. Requiere medicion de nueva distancia entre ejes y nueva longitud. PUEDE REQUERIR ENSAYO DE FRENADA.",
        "keywords": [
            "horquilla completa", "horquilla", "tren delantero",
            "tren delantero completo", "cambio horquilla",
            "distancia entre ejes", "distancia ejes",
            "horquilla de otra moto", "horquilla nueva"
        ],
        "aliases": ["complete fork", "front end", "fork assembly"],
        "sort_order": 35,
        "warnings": [
            {
                "code": "horquilla_ensayo_frenada",
                "message": "Cambio de horquilla/tren delantero puede requerir ensayo de frenada (+375 EUR).",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "procedencia",
                "field_label": "Procedencia de la horquilla",
                "field_type": "select",
                "options": ["Otra moto", "Nueva"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si la horquilla es nueva o procede de otra motocicleta",
            },
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "Showa",
                "llm_instruction": "Solicita la marca de la horquilla",
            },
            {
                "field_key": "tipo",
                "field_label": "Tipo (si procede de otra moto)",
                "field_type": "text",
                "sort_order": 3,
                "is_required": False,
                "example_value": "USD invertida",
                "llm_instruction": "Si procede de otra moto, solicita el tipo de horquilla",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Otra moto",
            },
            {
                "field_key": "denominacion",
                "field_label": "Denominación (si procede de otra moto)",
                "field_type": "text",
                "sort_order": 4,
                "is_required": False,
                "example_value": "CBR600RR",
                "llm_instruction": "Si procede de otra moto, solicita la denominación del modelo de origen",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Otra moto",
            },
            {
                "field_key": "contrasena",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 5,
                "is_required": False,
                "example_value": "e4*2002/24*0123",
                "llm_instruction": "Si procede de otra moto, solicita la contraseña de homologación",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Otra moto",
            },
            {
                "field_key": "modelo",
                "field_label": "Modelo (si es nueva)",
                "field_type": "text",
                "sort_order": 6,
                "is_required": False,
                "example_value": "BPF",
                "llm_instruction": "Si es horquilla nueva, solicita el modelo",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Nueva",
            },
            {
                "field_key": "distancia_entre_ejes",
                "field_label": "Nueva distancia entre ejes (mm)",
                "field_type": "number",
                "sort_order": 7,
                "example_value": "1450",
                "llm_instruction": "Solicita la nueva distancia entre ejes en milímetros (medir con cinta métrica)",
                "validation_rules": {"min_value": 1000, "max_value": 2000},
            },
            {
                "field_key": "nueva_longitud",
                "field_label": "Nueva longitud total (mm)",
                "field_type": "number",
                "sort_order": 8,
                "example_value": "2100",
                "llm_instruction": "Solicita la nueva longitud total del vehículo en milímetros",
                "validation_rules": {"min_value": 1500, "max_value": 3000},
            },
        ],
    },

    # =========================================================================
    # GRUPO 4: SISTEMA DE FRENADO
    # =========================================================================
    {
        "code": "FRENADO_DISCOS",
        "name": "Discos de freno",
        "description": "Discos de freno delanteros o traseros. Datos requeridos: marca/modelo, diametro, grosor. PUEDE REQUERIR ENSAYO DE FRENADA.",
        "keywords": [
            "disco", "discos", "disco freno", "discos freno",
            "disco delantero", "disco trasero", "disco flotante",
            "brembo", "galfer", "ng brakes", "ebc", "braking"
        ],
        "aliases": ["brake discs", "rotors", "brake rotors"],
        "sort_order": 40,
        "warnings": [
            {
                "code": "frenado_discos_ensayo",
                "message": "Puede requerir ensayo de frenada (+375 EUR).",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "marca_modelo",
                "field_label": "Marca/Modelo del disco",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Brembo T-Drive",
                "llm_instruction": "Solicita la marca y modelo del disco de freno",
            },
            {
                "field_key": "diametro",
                "field_label": "Diámetro (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "320",
                "llm_instruction": "Solicita el diámetro del disco en milímetros",
                "validation_rules": {"min_value": 150, "max_value": 400},
            },
            {
                "field_key": "grosor",
                "field_label": "Grosor (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "5",
                "llm_instruction": "Solicita el grosor del disco en milímetros",
                "validation_rules": {"min_value": 2, "max_value": 15},
            },
        ],
    },
    {
        "code": "FRENADO_PINZAS",
        "name": "Pinzas de freno",
        "description": "Pinzas de freno delanteras o traseras. Datos requeridos: marca, numero de pistones. PUEDE REQUERIR ENSAYO DE FRENADA.",
        "keywords": [
            "pinza", "pinzas", "pinza freno", "pinzas freno",
            "caliper", "calipers", "pinza delantera", "pinza trasera",
            "brembo", "nissin", "tokico", "beringer"
        ],
        "aliases": ["brake calipers", "calipers"],
        "sort_order": 42,
        "warnings": [
            {
                "code": "frenado_pinzas_ensayo",
                "message": "Puede requerir ensayo de frenada (+375 EUR).",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Brembo",
                "llm_instruction": "Solicita la marca de las pinzas de freno",
            },
            {
                "field_key": "num_pistones",
                "field_label": "Número de pistones",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "4",
                "llm_instruction": "Solicita el número de pistones de la pinza",
                "validation_rules": {"min_value": 1, "max_value": 8},
            },
        ],
    },
    {
        "code": "FRENADO_BOMBAS",
        "name": "Bombas de freno",
        "description": "Bombas de freno delantera o trasera. Datos requeridos: marca (delantera/trasera), grosor. PUEDE REQUERIR ENSAYO DE FRENADA.",
        "keywords": [
            "bomba freno", "bomba de freno", "bombas freno",
            "bomba delantera", "bomba trasera", "master cylinder",
            "brembo", "nissin", "magura", "beringer", "accossato"
        ],
        "aliases": ["brake master cylinder", "master cylinder"],
        "sort_order": 44,
        "warnings": [
            {
                "code": "frenado_bombas_ensayo",
                "message": "Puede requerir ensayo de frenada (+375 EUR).",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "delantera_marca",
                "field_label": "Marca bomba delantera",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Brembo RCS",
                "llm_instruction": "Solicita la marca de la bomba de freno delantera",
            },
            {
                "field_key": "trasera_marca",
                "field_label": "Marca bomba trasera",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "Brembo PS13",
                "llm_instruction": "Si se cambia también la trasera, solicita la marca",
            },
            {
                "field_key": "grosor",
                "field_label": "Grosor",
                "field_type": "text",
                "sort_order": 3,
                "is_required": False,
                "example_value": "19x18",
                "llm_instruction": "Solicita el grosor o dimensiones de la bomba si lo conoce",
            },
        ],
    },
    {
        "code": "FRENADO_LATIGUILLOS",
        "name": "Latiguillos metalicos",
        "description": "Latiguillos de freno metalicos (aviacion) delanteros o traseros. Sustituyen a los de goma originales.",
        "keywords": [
            "latiguillos", "latiguillo", "latiguillos metalicos",
            "latiguillo metalico", "latiguillos aviacion", "aviacion",
            "latiguillo freno", "manguera freno", "hel", "goodridge",
            "spiegler", "galfer"
        ],
        "aliases": ["braided brake lines", "steel brake lines"],
        "sort_order": 46,
        "required_fields": [
            {
                "field_key": "delantera_marca",
                "field_label": "Marca latiguillo delantero",
                "field_type": "text",
                "sort_order": 1,
                "is_required": False,
                "example_value": "Goodridge",
                "llm_instruction": "Solicita la marca del latiguillo delantero si aplica",
            },
            {
                "field_key": "trasera_marca",
                "field_label": "Marca latiguillo trasero",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "HEL Performance",
                "llm_instruction": "Solicita la marca del latiguillo trasero si aplica",
            },
        ],
    },
    {
        "code": "FRENADO_DEPOSITO",
        "name": "Deposito liquido frenos",
        "description": "Deposito de liquido de frenos delantero o trasero. Vaso de expansion.",
        "keywords": [
            "deposito liquido freno", "deposito freno", "vaso expansion",
            "deposito liquido", "reservorio freno", "deposito bomba",
            "deposito delantero", "deposito trasero"
        ],
        "aliases": ["brake fluid reservoir", "brake reservoir"],
        "sort_order": 48,
        "required_fields": [
            {
                "field_key": "delantera_marca",
                "field_label": "Marca depósito delantero",
                "field_type": "text",
                "sort_order": 1,
                "is_required": False,
                "example_value": "Rizoma",
                "llm_instruction": "Solicita la marca del depósito de líquido de frenos delantero",
            },
            {
                "field_key": "trasera_marca",
                "field_label": "Marca depósito trasero",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "Brembo",
                "llm_instruction": "Solicita la marca del depósito de líquido de frenos trasero si aplica",
            },
        ],
    },

    # =========================================================================
    # GRUPO 5: CARROCERIA
    # =========================================================================
    {
        "code": "CARENADO",
        "name": "Carenado / Semicarenado",
        "description": "Carenado completo o semicarenado. Incluye desmontaje, sustitucion o instalacion. Datos requeridos: medidas y material de cada pieza instalada.",
        "keywords": [
            "carenado", "semicarenado", "carenado completo",
            "cupula", "cupula racing", "cubierta", "carena",
            "tapas laterales", "colin", "colin trasero"
        ],
        "aliases": ["fairing", "bodywork", "cowling"],
        "sort_order": 50,
        "warnings": [
            {
                "code": "carenado_material",
                "message": "Indicar material del carenado sustituido/instalado. Minimo ancho del guardabarros igual al del neumatico.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "tipo_modificacion",
                "field_label": "Tipo de modificación",
                "field_type": "select",
                "options": ["Desmontaje", "Sustitución", "Instalación"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se trata de desmontaje de carenado existente, sustitución por otro o instalación de carenado nuevo",
            },
            {
                "field_key": "pieza1_descripcion",
                "field_label": "Pieza 1 - Descripción",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "Cúpula delantera",
                "llm_instruction": "Solicita descripción de la primera pieza del carenado (cúpula, tapa lateral, colín, etc.)",
            },
            {
                "field_key": "pieza1_medidas",
                "field_label": "Pieza 1 - Medidas (mm)",
                "field_type": "text",
                "sort_order": 3,
                "example_value": "450x300",
                "llm_instruction": "Solicita las medidas aproximadas de la pieza en milímetros (largo x ancho)",
            },
            {
                "field_key": "pieza1_material",
                "field_label": "Pieza 1 - Material",
                "field_type": "select",
                "options": ["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"],
                "sort_order": 4,
                "llm_instruction": "Pregunta el material de la pieza (ABS, fibra de vidrio, fibra de carbono, etc.)",
            },
            {
                "field_key": "mas_piezas",
                "field_label": "¿Hay más piezas?",
                "field_type": "boolean",
                "sort_order": 5,
                "llm_instruction": "Pregunta si hay más piezas de carenado a incluir en la reforma",
            },
            {
                "field_key": "pieza2_descripcion",
                "field_label": "Pieza 2 - Descripción",
                "field_type": "text",
                "sort_order": 6,
                "is_required": False,
                "example_value": "Tapa lateral izquierda",
                "llm_instruction": "Si hay más piezas, solicita la descripción de la segunda",
                "condition_field_key": "mas_piezas",
                "condition_operator": "equals",
                "condition_value": "true",
            },
            {
                "field_key": "pieza2_medidas",
                "field_label": "Pieza 2 - Medidas (mm)",
                "field_type": "text",
                "sort_order": 7,
                "is_required": False,
                "example_value": "300x200",
                "llm_instruction": "Si hay más piezas, solicita las medidas de la segunda",
                "condition_field_key": "mas_piezas",
                "condition_operator": "equals",
                "condition_value": "true",
            },
            {
                "field_key": "pieza2_material",
                "field_label": "Pieza 2 - Material",
                "field_type": "select",
                "options": ["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"],
                "sort_order": 8,
                "is_required": False,
                "llm_instruction": "Si hay más piezas, pregunta el material de la segunda",
                "condition_field_key": "mas_piezas",
                "condition_operator": "equals",
                "condition_value": "true",
            },
        ],
    },
    {
        "code": "GUARDABARROS_DEL",
        "name": "Guardabarros delantero",
        "description": "Guardabarros delantero: sustitucion, recorte o eliminacion. El ancho minimo debe ser igual al del neumatico.",
        "keywords": [
            "guardabarros delantero", "guardabarros frontal",
            "recorte guardabarros", "guardabarros corto",
            "guardabarros delantero corto", "fender delantero"
        ],
        "aliases": ["front fender", "front mudguard"],
        "sort_order": 52,
        "required_fields": [
            {
                "field_key": "tipo_modificacion",
                "field_label": "Tipo de modificación",
                "field_type": "select",
                "options": ["Sustitución", "Recorte", "Eliminación"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se trata de sustitución, recorte o eliminación del guardabarros delantero",
            },
            {
                "field_key": "material",
                "field_label": "Material (si sustitución)",
                "field_type": "select",
                "options": ["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"],
                "sort_order": 2,
                "is_required": False,
                "llm_instruction": "Si es sustitución, pregunta el material del nuevo guardabarros",
                "condition_field_key": "tipo_modificacion",
                "condition_operator": "equals",
                "condition_value": "Sustitución",
            },
            {
                "field_key": "ancho_mm",
                "field_label": "Ancho del guardabarros (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "120",
                "llm_instruction": "Solicita el ancho del guardabarros en milímetros (debe ser igual o mayor que el ancho del neumático)",
                "validation_rules": {"min_value": 50, "max_value": 300},
            },
        ],
    },
    {
        "code": "GUARDABARROS_TRAS",
        "name": "Guardabarros trasero",
        "description": "Guardabarros trasero: sustitucion, recorte o eliminacion. El ancho minimo debe ser igual al del neumatico.",
        "keywords": [
            "guardabarros trasero", "guardabarros posterior",
            "recorte guardabarros trasero", "eliminacion guardabarros",
            "guardabarros corto trasero", "fender trasero", "rabillo"
        ],
        "aliases": ["rear fender", "rear mudguard"],
        "sort_order": 54,
        "required_fields": [
            {
                "field_key": "tipo_modificacion",
                "field_label": "Tipo de modificación",
                "field_type": "select",
                "options": ["Sustitución", "Recorte", "Eliminación"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se trata de sustitución, recorte o eliminación del guardabarros trasero",
            },
            {
                "field_key": "material",
                "field_label": "Material (si sustitución)",
                "field_type": "select",
                "options": ["ABS", "Fibra de vidrio", "Fibra de carbono", "Polipropileno", "Otro"],
                "sort_order": 2,
                "is_required": False,
                "llm_instruction": "Si es sustitución, pregunta el material del nuevo guardabarros",
                "condition_field_key": "tipo_modificacion",
                "condition_operator": "equals",
                "condition_value": "Sustitución",
            },
            {
                "field_key": "ancho_mm",
                "field_label": "Ancho del guardabarros (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "180",
                "llm_instruction": "Solicita el ancho del guardabarros en milímetros (debe ser igual o mayor que el ancho del neumático)",
                "validation_rules": {"min_value": 50, "max_value": 350},
            },
        ],
    },
    {
        "code": "CARROCERIA",
        "name": "Carroceria general",
        "description": "Otras piezas de carroceria no especificadas: cubiertas, tapas, protectores, etc.",
        "keywords": [
            "carroceria", "cubiertas", "cubierta lateral",
            "tapa lateral", "protector", "cubre carter",
            "quilla", "panza", "belly pan"
        ],
        "aliases": ["bodywork", "body panels"],
        "sort_order": 56,
    },

    # =========================================================================
    # GRUPO 6: DIRECCION Y MANILLAR
    # =========================================================================
    {
        "code": "MANILLAR",
        "name": "Manillar",
        "description": "Manillar completo o semimanillares. Datos requeridos: marca, modelo, material, diametro, nuevo ancho, nueva altura. Medir a manetas o punos (la medida mas ancha). En motos 168/2013 (desde 2016) la medida maxima es 380mm.",
        "keywords": [
            "manillar", "semimanillares", "semi manillares", "guidon",
            "clip-on", "clipon", "clip on", "manillar alto",
            "manillar bajo", "manillar racing", "renthal", "rizoma",
            "lsl", "tarozzi", "tommaselli"
        ],
        "aliases": ["handlebar", "handlebars", "clip-ons"],
        "sort_order": 60,
        "warnings": [
            {
                "code": "manillar_dimensiones",
                "message": "Consultar dimensiones de cuelgamonos en vehiculos modernos y aristas cortantes en manillares Z. En motos 168/2013 (desde 2016), medida maxima 380mm.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Renthal",
                "llm_instruction": "Solicita la marca del manillar",
            },
            {
                "field_key": "modelo",
                "field_label": "Modelo",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "Fatbar 28mm",
                "llm_instruction": "Solicita el modelo específico del manillar",
            },
            {
                "field_key": "material",
                "field_label": "Material",
                "field_type": "select",
                "options": ["Aluminio", "Acero", "Titanio", "Fibra de carbono"],
                "sort_order": 3,
                "llm_instruction": "Pregunta el material del manillar (aluminio, acero, titanio, etc.)",
            },
            {
                "field_key": "diametro_mm",
                "field_label": "Diámetro (mm)",
                "field_type": "number",
                "sort_order": 4,
                "example_value": "28",
                "llm_instruction": "Solicita el diámetro del tubo del manillar en milímetros (típico: 22mm o 28mm)",
                "validation_rules": {"min_value": 18, "max_value": 35},
            },
            {
                "field_key": "nuevo_ancho_mm",
                "field_label": "Nuevo ancho total (mm)",
                "field_type": "number",
                "sort_order": 5,
                "example_value": "760",
                "llm_instruction": "Solicita el nuevo ancho total del manillar en milímetros, medido de extremo a extremo (en manetas o puños, la medida más ancha). En motos desde 2016 (168/2013) máximo 380mm desde el eje",
                "validation_rules": {"min_value": 500, "max_value": 900},
            },
            {
                "field_key": "nueva_altura_mm",
                "field_label": "Nueva altura (mm)",
                "field_type": "number",
                "sort_order": 6,
                "example_value": "85",
                "llm_instruction": "Solicita la nueva altura del manillar respecto a las tijas en milímetros",
                "validation_rules": {"min_value": 0, "max_value": 300},
            },
        ],
    },
    {
        "code": "TIJAS",
        "name": "Tijas / Torretas de manillar",
        "description": "Tijas o torretas de manillar. Datos requeridos: marca, material, altura (para torretas).",
        "keywords": [
            "tija", "tijas", "torreta", "torretas", "arana",
            "triple tree", "tija superior", "tija inferior",
            "elevador manillar", "riser"
        ],
        "aliases": ["triple clamp", "yokes", "risers"],
        "sort_order": 62,
        "required_fields": [
            {
                "field_key": "tipo",
                "field_label": "Tipo de modificación",
                "field_type": "select",
                "options": ["Tijas completas", "Torretas/Risers"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se trata de sustitución de tijas completas o solo instalación de torretas/risers elevadores",
            },
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "ABM",
                "llm_instruction": "Solicita la marca de las tijas o torretas",
            },
            {
                "field_key": "material",
                "field_label": "Material",
                "field_type": "select",
                "options": ["Aluminio", "Acero", "Aluminio CNC"],
                "sort_order": 3,
                "llm_instruction": "Pregunta el material de las tijas o torretas",
            },
            {
                "field_key": "altura_mm",
                "field_label": "Altura de elevación (mm)",
                "field_type": "number",
                "sort_order": 4,
                "is_required": False,
                "example_value": "30",
                "llm_instruction": "Si son torretas/risers, solicita la altura de elevación en milímetros",
                "condition_field_key": "tipo",
                "condition_operator": "equals",
                "condition_value": "Torretas/Risers",
                "validation_rules": {"min_value": 10, "max_value": 100},
            },
        ],
    },
    {
        "code": "ESPEJOS",
        "name": "Espejos / Retrovisores",
        "description": "Retrovisores modificados o aftermarket. La medida entre centros de espejos debe ser igual o superior a 560mm. La contrasena de ambos espejos ha de ser IGUAL.",
        "keywords": [
            "espejos", "retrovisores", "retrovisor", "espejo",
            "espejo homologado", "retrovisor homologado",
            "espejos bar end", "espejos extremo manillar",
            "rizoma", "puig", "lightech", "barracuda"
        ],
        "aliases": ["mirrors", "rearview mirrors"],
        "sort_order": 70,
        "warnings": [
            {
                "code": "espejos_requisitos",
                "message": "Requieren homologacion y correcta ubicacion. Distancia minima 560mm entre centros. La contrasena de ambos espejos ha de ser IGUAL.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación (ambos espejos)",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*2003/97*0123",
                "llm_instruction": "Solicita la contraseña de homologación de los espejos. IMPORTANTE: Debe ser IGUAL en ambos retrovisores",
            },
        ],
    },
    {
        "code": "MANDOS_AVANZADOS",
        "name": "Mandos avanzados",
        "description": "Mandos avanzados de freno y marchas (pedales reposicionados). Datos requeridos: marca y material de cada mando.",
        "keywords": [
            "mando avanzado", "mandos avanzados", "pedal avanzado",
            "pedal freno avanzado", "pedal marchas avanzado",
            "rearsets", "estriberas racing", "commandes reculees"
        ],
        "aliases": ["rearsets", "rear sets", "racing controls"],
        "sort_order": 75,
        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Gilles Tooling",
                "llm_instruction": "Solicita la marca de los mandos avanzados",
            },
            {
                "field_key": "material",
                "field_label": "Material",
                "field_type": "select",
                "options": ["Aluminio", "Aluminio CNC", "Acero", "Titanio"],
                "sort_order": 2,
                "llm_instruction": "Pregunta el material de los mandos avanzados",
            },
        ],
    },

    # =========================================================================
    # GRUPO 7: ALUMBRADO Y SENALIZACION
    # =========================================================================
    # BASE: Elemento generico para luces (detecta variantes)
    {
        "code": "LUCES",
        "name": "Luces / Alumbrado",
        "description": "Modificacion de luces o alumbrado. Selecciona el tipo especifico de luz a homologar.",
        "keywords": [
            "luces", "luz", "iluminacion", "alumbrado"
        ],
        "aliases": ["lights", "lighting"],
        "sort_order": 79,
        "is_base": True,
        "question_hint": "¿Que tipo de luces? Faro delantero, piloto trasero (luz de freno), luz de matricula, catadrioptricos u otro tipo?",
        "multi_select_keywords": ["todas", "todas las luces", "todo el alumbrado", "todos los tipos de luces", "todos"],
    },
    # VARIANTE: Faro delantero
    {
        "code": "FARO_DELANTERO",
        "name": "Faro delantero",
        "description": "Faro delantero modificado o sustituido. Requiere contrasena de homologacion y foto de altura.",
        "keywords": [
            "faro", "faro delantero", "optica", "faro principal",
            "headlight", "faro led", "faro xenon", "faro auxiliar",
            "luz delantera", "luz principal"
        ],
        "aliases": ["headlight", "front light", "main beam"],
        "sort_order": 80,
        "parent_code": "LUCES",
        "variant_type": "light_type",
        "variant_code": "FARO_DEL",
        "warnings": [
            {
                "code": "faro_largo_alcance",
                "message": "Dependiendo del tipo de faros, se podria anular el largo alcance del faro principal.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*2012/19*0456",
                "llm_instruction": "Solicita la contraseña de homologación del faro (número E visible en el cristal o carcasa)",
            },
        ],
    },
    # BASE: Elemento generico para intermitentes (detecta variantes)
    {
        "code": "INTERMITENTES",
        "name": "Intermitentes",
        "description": "Intermitentes modificados. Selecciona la variante segun sean delanteros o traseros.",
        "keywords": [
            "intermitentes", "intermitente", "indicadores", "direccionales"
        ],
        "aliases": ["turn signals", "indicators", "blinkers"],
        "sort_order": 81,
        "is_base": True,
        "question_hint": "¿Son los intermitentes delanteros, traseros o ambos?",
        "multi_select_keywords": [
            "ambos", "todos", "los dos", "las dos",
            "delanteros y traseros", "traseros y delanteros",
        ],
    },
    # VARIANTE: Intermitentes delanteros
    {
        "code": "INTERMITENTES_DEL",
        "name": "Intermitentes delanteros",
        "description": "Intermitentes delanteros. Distancia minima entre bordes interiores: 240mm. Requiere foto de marcado homologacion, distancia entre bordes, angulos y distancia al faro principal.",
        "keywords": [
            "intermitentes delanteros", "indicadores delanteros",
            "intermitente delantero", "direccionales delanteros",
            "intermitentes frontales", "leds delanteros",
            "delanteros", "delantero", "frontales",
        ],
        "aliases": ["front turn signals", "front indicators"],
        "sort_order": 82,
        "parent_code": "INTERMITENTES",
        "variant_type": "position",
        "variant_code": "DEL",
        "warnings": [
            {
                "code": "intermitentes_del_distancia",
                "message": "Minima distancia 240mm entre bordes interiores.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*76/756*0012",
                "llm_instruction": "Solicita la contraseña de homologación de los intermitentes delanteros",
            },
            {
                "field_key": "distancia_bordes_mm",
                "field_label": "Distancia entre bordes interiores (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "280",
                "llm_instruction": "Solicita la distancia en milímetros entre los bordes interiores de ambos intermitentes (mínimo 240mm)",
                "validation_rules": {"min_value": 200, "max_value": 600},
            },
            {
                "field_key": "distancia_faro_mm",
                "field_label": "Distancia al faro principal (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "100",
                "llm_instruction": "Solicita la distancia en milímetros desde el intermitente al faro principal",
                "validation_rules": {"min_value": 0, "max_value": 500},
            },
        ],
    },
    # VARIANTE: Intermitentes traseros
    {
        "code": "INTERMITENTES_TRAS",
        "name": "Intermitentes traseros",
        "description": "Intermitentes traseros. Distancia minima entre bordes exteriores: 75mm. Angulo interior: 20 grados (50 grados si lleva luz de freno integrada). Distancia maxima al final: 30cm.",
        "keywords": [
            "intermitentes traseros", "indicadores traseros",
            "intermitente trasero", "direccionales traseros",
            "intermitentes posteriores", "leds traseros",
            "piloto integrado", "intermitente con freno",
            "traseros", "trasero", "posteriores",
        ],
        "aliases": ["rear turn signals", "rear indicators"],
        "sort_order": 84,
        "parent_code": "INTERMITENTES",
        "variant_type": "position",
        "variant_code": "TRAS",
        "warnings": [
            {
                "code": "intermitentes_tras_angulo",
                "message": "Minima distancia 7.5cm entre bordes exteriores. Angulo interior 20 grados (50 grados si lleva luz de freno).",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*76/756*0012",
                "llm_instruction": "Solicita la contraseña de homologación de los intermitentes traseros",
            },
            {
                "field_key": "distancia_bordes_mm",
                "field_label": "Distancia entre bordes exteriores (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "150",
                "llm_instruction": "Solicita la distancia en milímetros entre los bordes exteriores de ambos intermitentes (mínimo 75mm)",
                "validation_rules": {"min_value": 50, "max_value": 500},
            },
            {
                "field_key": "distancia_final_mm",
                "field_label": "Distancia al final del vehículo (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "250",
                "llm_instruction": "Solicita la distancia en milímetros desde el intermitente hasta el final del vehículo (máximo 300mm)",
                "validation_rules": {"min_value": 0, "max_value": 400},
            },
            {
                "field_key": "integra_luz_freno",
                "field_label": "¿Integra luz de freno?",
                "field_type": "boolean",
                "sort_order": 4,
                "llm_instruction": "Pregunta si los intermitentes traseros integran la luz de freno (cambia el ángulo requerido de 20 a 50 grados)",
            },
        ],
    },
    # VARIANTE: Piloto freno trasero
    {
        "code": "PILOTO_FRENO",
        "name": "Piloto freno trasero",
        "description": "Piloto de freno trasero (luz de stop). Si combinado con intermitentes, el angulo es de 50 grados. Requiere foto de altura y angulos de visibilidad.",
        "keywords": [
            "piloto freno", "luz freno", "piloto trasero",
            "stop", "luz stop", "brake light", "piloto led",
            "luz de freno", "tercera luz freno", "piloto"
        ],
        "aliases": ["brake light", "stop light", "tail light"],
        "sort_order": 86,
        "parent_code": "LUCES",
        "variant_type": "light_type",
        "variant_code": "PILOTO",
        "warnings": [
            {
                "code": "piloto_freno_angulo",
                "message": "Si combinado con intermitentes, angulo de visibilidad 50 grados.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*2008/89*0034",
                "llm_instruction": "Solicita la contraseña de homologación del piloto de freno",
            },
            {
                "field_key": "altura_mm",
                "field_label": "Altura desde el suelo (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "750",
                "llm_instruction": "Solicita la altura del piloto de freno desde el suelo en milímetros",
                "validation_rules": {"min_value": 250, "max_value": 1500},
            },
            {
                "field_key": "integra_intermitentes",
                "field_label": "¿Integra intermitentes?",
                "field_type": "boolean",
                "sort_order": 3,
                "llm_instruction": "Pregunta si el piloto de freno integra los intermitentes traseros",
            },
        ],
    },
    # VARIANTE: Luz de matricula
    {
        "code": "LUZ_MATRICULA",
        "name": "Luz de matricula",
        "description": "Luz de matricula. La luz no debe obstaculizar la visibilidad de la matricula. Requiere foto de homologacion.",
        "keywords": [
            "luz matricula", "iluminacion matricula",
            "luz placa", "luz de placa", "license plate light",
            "iluminador matricula"
        ],
        "aliases": ["license plate light", "number plate light"],
        "sort_order": 88,
        "parent_code": "LUCES",
        "variant_type": "light_type",
        "variant_code": "LUZ_MAT",
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*2012/19*0045",
                "llm_instruction": "Solicita la contraseña de homologación de la luz de matrícula",
            },
            {
                "field_key": "altura_mm",
                "field_label": "Altura desde el suelo (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "600",
                "llm_instruction": "Solicita la altura de la luz de matrícula desde el suelo en milímetros",
                "validation_rules": {"min_value": 200, "max_value": 1200},
            },
            {
                "field_key": "posicion",
                "field_label": "Posición respecto a matrícula",
                "field_type": "select",
                "options": ["Superior", "Lateral", "Integrada en piloto"],
                "sort_order": 3,
                "llm_instruction": "Pregunta la posición de la luz respecto a la matrícula",
            },
        ],
    },
    # VARIANTE: Catadioptrico trasero
    {
        "code": "CATADIOPTRICO",
        "name": "Catadioptrico trasero",
        "description": "Catadioptrico (reflector) trasero. Debe estar perpendicular al suelo. Altura maxima 900mm, minima 250mm.",
        "keywords": [
            "catadioptrico", "reflector", "reflectante",
            "catadioptrico trasero", "reflector trasero",
            "catafotos", "catafaro"
        ],
        "aliases": ["reflector", "rear reflector"],
        "sort_order": 90,
        "parent_code": "LUCES",
        "variant_type": "light_type",
        "variant_code": "CATADIO",
        "warnings": [
            {
                "code": "catadioptrico_altura",
                "message": "Debe estar perpendicular al suelo. Altura: min 250mm, max 900mm.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*3*0012",
                "llm_instruction": "Solicita la contraseña de homologación del catadióptrico",
            },
            {
                "field_key": "altura_mm",
                "field_label": "Altura desde el suelo (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "500",
                "llm_instruction": "Solicita la altura del catadióptrico desde el suelo en milímetros (mínimo 250mm, máximo 900mm)",
                "validation_rules": {"min_value": 200, "max_value": 1000},
            },
            {
                "field_key": "perpendicular",
                "field_label": "¿Está perpendicular al suelo?",
                "field_type": "boolean",
                "sort_order": 3,
                "llm_instruction": "Confirma si el catadióptrico está montado perpendicular al suelo (requisito obligatorio)",
            },
        ],
    },
    # VARIANTE: Luces antiniebla
    {
        "code": "ANTINIEBLAS",
        "name": "Luces antiniebla",
        "description": "Luces antiniebla. Requiere foto de altura, angulos, mando con pictograma homologado y contrasena.",
        "keywords": [
            "antiniebla", "antinieblas", "luz antiniebla",
            "luces antiniebla", "faros auxiliares", "fog light",
            "niebla", "foco auxiliar"
        ],
        "aliases": ["fog lights", "auxiliary lights"],
        "sort_order": 92,
        "parent_code": "LUCES",
        "variant_type": "light_type",
        "variant_code": "ANTINIEBLA",
        "warnings": [
            {
                "code": "antinieblas_pictograma",
                "message": "Necesario pictograma homologado en el boton de encendido.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "e4*2019/144*0123",
                "llm_instruction": "Solicita la contraseña de homologación de las luces antiniebla",
            },
            {
                "field_key": "tiene_pictograma",
                "field_label": "¿El mando tiene pictograma homologado?",
                "field_type": "boolean",
                "sort_order": 2,
                "llm_instruction": "Confirma si el botón de encendido tiene el pictograma homologado de niebla (requisito obligatorio)",
            },
        ],
    },

    # =========================================================================
    # GRUPO 8: MANDOS Y CONTROLES
    # =========================================================================
    {
        "code": "MANDOS_MANILLAR",
        "name": "Mandos / Pinas de manillar",
        "description": "Mandos y pinas de manillar (izquierda y derecha). Deben tener pictogramas homologados segun su funcion. Incluye testigos independientes.",
        "keywords": [
            "pina", "pinas", "mandos manillar", "conmutadores",
            "pina izquierda", "pina derecha", "switch",
            "testigos", "mando luces", "mando intermitentes"
        ],
        "aliases": ["handlebar switches", "controls"],
        "sort_order": 95,
        "warnings": [
            {
                "code": "mandos_pictogramas",
                "message": "Los nuevos mandos deben disponer de pictogramas homologados segun su funcion.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "pina_izquierda",
                "field_label": "¿Se cambia piña izquierda?",
                "field_type": "boolean",
                "sort_order": 1,
                "llm_instruction": "Pregunta si se sustituye la piña izquierda del manillar (luces, intermitentes, claxon)",
            },
            {
                "field_key": "pina_izquierda_marca",
                "field_label": "Marca piña izquierda",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "Domino",
                "llm_instruction": "Si se cambia la piña izquierda, solicita la marca",
                "condition_field_key": "pina_izquierda",
                "condition_operator": "equals",
                "condition_value": "true",
            },
            {
                "field_key": "pina_derecha",
                "field_label": "¿Se cambia piña derecha?",
                "field_type": "boolean",
                "sort_order": 3,
                "llm_instruction": "Pregunta si se sustituye la piña derecha del manillar (arranque, paro motor)",
            },
            {
                "field_key": "pina_derecha_marca",
                "field_label": "Marca piña derecha",
                "field_type": "text",
                "sort_order": 4,
                "is_required": False,
                "example_value": "Domino",
                "llm_instruction": "Si se cambia la piña derecha, solicita la marca",
                "condition_field_key": "pina_derecha",
                "condition_operator": "equals",
                "condition_value": "true",
            },
            {
                "field_key": "testigos_independientes",
                "field_label": "¿Se añaden testigos independientes?",
                "field_type": "boolean",
                "sort_order": 5,
                "llm_instruction": "Pregunta si se instalan testigos luminosos independientes",
            },
            {
                "field_key": "pictogramas_homologados",
                "field_label": "¿Los mandos tienen pictogramas homologados?",
                "field_type": "boolean",
                "sort_order": 6,
                "llm_instruction": "Confirma si los nuevos mandos disponen de pictogramas homologados según su función (requisito obligatorio)",
            },
        ],
    },
    {
        "code": "CLAUSOR",
        "name": "Clausor / Llave de arranque",
        "description": "Clausor o llave de arranque reubicada. Foto de nueva ubicacion requerida.",
        "keywords": [
            "clausor", "llave arranque", "interruptor arranque",
            "llave contacto", "ignition", "cerradura",
            "contacto", "switch arranque"
        ],
        "aliases": ["ignition switch", "key switch"],
        "sort_order": 97,
        "required_fields": [
            {
                "field_key": "nueva_ubicacion",
                "field_label": "Nueva ubicación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Lateral izquierdo del depósito",
                "llm_instruction": "Solicita la descripción de la nueva ubicación del clausor/llave de arranque",
            },
        ],
    },
    {
        "code": "STARTER",
        "name": "Starter",
        "description": "Sistema de starter (cebador) reubicado. Foto de nueva ubicacion requerida.",
        "keywords": [
            "starter", "cebador", "arranque en frio",
            "estarter", "choke", "sistema arranque"
        ],
        "aliases": ["choke", "starter"],
        "sort_order": 98,
        "required_fields": [
            {
                "field_key": "nueva_ubicacion",
                "field_label": "Nueva ubicación",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "En el manillar",
                "llm_instruction": "Solicita la descripción de la nueva ubicación del starter/cebador",
            },
        ],
    },

    # =========================================================================
    # GRUPO 9: RUEDAS Y NEUMATICOS
    # =========================================================================
    {
        "code": "LLANTAS",
        "name": "Llantas",
        "description": "Llantas modificadas o de diferente tamano. Si el neumatico delantero supera el 10% en diametro, puede requerir ensayo de frenada.",
        "keywords": [
            "llantas", "llanta", "ruedas", "rines", "rin",
            "llanta delantera", "llanta trasera", "wheels",
            "llanta forjada", "llanta aluminio", "marchesini",
            "oz racing", "bst", "dymag"
        ],
        "aliases": ["wheels", "rims"],
        "sort_order": 100,
        "warnings": [
            {
                "code": "llantas_sin_ensayo",
                "message": "Sustitucion sin ensayo. Verificar compatibilidad con neumaticos.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "posicion",
                "field_label": "Posición",
                "field_type": "select",
                "options": ["Delantera", "Trasera", "Ambas"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se cambia la llanta delantera, trasera o ambas",
            },
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "Marchesini",
                "llm_instruction": "Solicita la marca de las llantas",
            },
            {
                "field_key": "medidas_del",
                "field_label": "Medidas llanta delantera",
                "field_type": "text",
                "sort_order": 3,
                "is_required": False,
                "example_value": "3.50x17",
                "llm_instruction": "Si se cambia la llanta delantera, solicita las medidas (ancho x diámetro)",
            },
            {
                "field_key": "medidas_tras",
                "field_label": "Medidas llanta trasera",
                "field_type": "text",
                "sort_order": 4,
                "is_required": False,
                "example_value": "5.50x17",
                "llm_instruction": "Si se cambia la llanta trasera, solicita las medidas (ancho x diámetro)",
            },
        ],
    },
    {
        "code": "NEUMATICOS",
        "name": "Neumaticos",
        "description": "Neumaticos de diferente medida. Datos: medidas, indice de carga, indice de velocidad, M+S. Si supera 10% (del) u 8% (tras) en diametro, puede requerir ensayo de frenada.",
        "keywords": [
            "neumaticos", "neumatico", "cubiertas", "cubierta",
            "gomas", "ruedas", "neumatico delantero", "neumatico trasero",
            "michelin", "pirelli", "bridgestone", "dunlop", "metzeler",
            "m+s", "mixto"
        ],
        "aliases": ["tires", "tyres"],
        "sort_order": 110,
        "warnings": [
            {
                "code": "neumaticos_ensayo",
                "message": "Si el neumatico DELANTERO supera 10% en diametro o TRASERO supera 8%, posible ensayo de frenada.",
                "severity": "warning",
            },
        ],
        "required_fields": [
            {
                "field_key": "posicion",
                "field_label": "Posición",
                "field_type": "select",
                "options": ["Delantero", "Trasero", "Ambos"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si se cambia el neumático delantero, trasero o ambos",
            },
            {
                "field_key": "medidas_del",
                "field_label": "Medidas neumático delantero",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "120/70-17",
                "llm_instruction": "Si se cambia el neumático delantero, solicita las medidas (ancho/perfil-diámetro)",
            },
            {
                "field_key": "indice_carga_del",
                "field_label": "Índice de carga delantero",
                "field_type": "text",
                "sort_order": 3,
                "is_required": False,
                "example_value": "58",
                "llm_instruction": "Si se cambia el delantero, solicita el índice de carga",
            },
            {
                "field_key": "indice_velocidad_del",
                "field_label": "Índice de velocidad delantero",
                "field_type": "text",
                "sort_order": 4,
                "is_required": False,
                "example_value": "W",
                "llm_instruction": "Si se cambia el delantero, solicita el índice de velocidad (letra)",
            },
            {
                "field_key": "medidas_tras",
                "field_label": "Medidas neumático trasero",
                "field_type": "text",
                "sort_order": 5,
                "is_required": False,
                "example_value": "180/55-17",
                "llm_instruction": "Si se cambia el neumático trasero, solicita las medidas (ancho/perfil-diámetro)",
            },
            {
                "field_key": "indice_carga_tras",
                "field_label": "Índice de carga trasero",
                "field_type": "text",
                "sort_order": 6,
                "is_required": False,
                "example_value": "73",
                "llm_instruction": "Si se cambia el trasero, solicita el índice de carga",
            },
            {
                "field_key": "indice_velocidad_tras",
                "field_label": "Índice de velocidad trasero",
                "field_type": "text",
                "sort_order": 7,
                "is_required": False,
                "example_value": "W",
                "llm_instruction": "Si se cambia el trasero, solicita el índice de velocidad (letra)",
            },
            {
                "field_key": "ms_mixto",
                "field_label": "¿Es neumático M+S (mixto/trail)?",
                "field_type": "boolean",
                "sort_order": 8,
                "llm_instruction": "Pregunta si los neumáticos son M+S (uso mixto/trail)",
            },
        ],
    },

    # =========================================================================
    # GRUPO 10: COMBUSTIBLE
    # =========================================================================
    {
        "code": "DEPOSITO",
        "name": "Deposito de combustible",
        "description": "Deposito de gasolina modificado, nuevo o procedente de otro vehiculo. Si es nuevo, requiere foto de etiqueta con contrasena de homologacion.",
        "keywords": [
            "deposito", "tanque", "gasolina", "combustible",
            "deposito combustible", "tanque gasolina", "fuel tank",
            "deposito nuevo", "deposito otra moto"
        ],
        "aliases": ["fuel tank", "gas tank", "petrol tank"],
        "sort_order": 120,
        "warnings": [
            {
                "code": "deposito_homologacion",
                "message": "Si deposito nuevo, necesaria foto de la etiqueta con contrasena de homologacion.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "procedencia",
                "field_label": "Procedencia del depósito",
                "field_type": "select",
                "options": ["Nuevo", "De otra moto", "Modificado"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si el depósito es nuevo, procede de otra moto o es el original modificado",
            },
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 2,
                "is_required": False,
                "example_value": "e4*2015/136*0078",
                "llm_instruction": "Si es depósito nuevo, solicita la contraseña de homologación de la etiqueta",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Nuevo",
            },
            {
                "field_key": "capacidad_litros",
                "field_label": "Capacidad (litros)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "18",
                "llm_instruction": "Solicita la capacidad del depósito en litros",
                "validation_rules": {"min_value": 3, "max_value": 50},
            },
            {
                "field_key": "descripcion_modificacion",
                "field_label": "Descripción de la modificación",
                "field_type": "text",
                "sort_order": 4,
                "is_required": False,
                "example_value": "Modificación del soporte de fijación",
                "llm_instruction": "Si es depósito modificado, describe en qué consiste la modificación",
                "condition_field_key": "procedencia",
                "condition_operator": "equals",
                "condition_value": "Modificado",
            },
        ],
    },

    # =========================================================================
    # GRUPO 11: INSTRUMENTACION
    # =========================================================================
    {
        "code": "VELOCIMETRO",
        "name": "Velocimetro / Cuadro de instrumentos",
        "description": "Velocimetro o cuadro de instrumentos modificado. Datos: marca, modelo, contrasena, testigos luminosos, captador (mantener o nuevo).",
        "keywords": [
            "velocimetro", "cuadro", "instrumentos", "cuentakilometros",
            "tacometro", "cuenta revoluciones", "dashboard",
            "cuadro digital", "cuadro analogico", "koso", "daytona",
            "acewell", "motogadget"
        ],
        "aliases": ["speedometer", "dashboard", "instrument cluster"],
        "sort_order": 130,
        "warnings": [
            {
                "code": "velocimetro_recargo_lab",
                "message": "Si el velocimetro no es digital, llevara recargo de laboratorio (+25/75 EUR). No se homologa la posicion sino el soporte.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Koso",
                "llm_instruction": "Solicita la marca del velocímetro/cuadro de instrumentos",
            },
            {
                "field_key": "modelo",
                "field_label": "Modelo",
                "field_type": "text",
                "sort_order": 2,
                "example_value": "RX2N",
                "llm_instruction": "Solicita el modelo específico del velocímetro",
            },
            {
                "field_key": "contrasena_homologacion",
                "field_label": "Contraseña de homologación",
                "field_type": "text",
                "sort_order": 3,
                "example_value": "e4*2000/7*0456",
                "llm_instruction": "Solicita la contraseña de homologación del velocímetro",
            },
            {
                "field_key": "tipo_display",
                "field_label": "Tipo de display",
                "field_type": "select",
                "options": ["Digital", "Analógico"],
                "sort_order": 4,
                "llm_instruction": "Pregunta si el velocímetro es digital o analógico (analógico puede llevar recargo de laboratorio)",
            },
            {
                "field_key": "testigos_luminosos",
                "field_label": "¿Incluye todos los testigos luminosos?",
                "field_type": "boolean",
                "sort_order": 5,
                "llm_instruction": "Confirma si el velocímetro incluye los testigos luminosos obligatorios (intermitentes, luces largas, neutro, etc.)",
            },
            {
                "field_key": "captador",
                "field_label": "Captador de velocidad",
                "field_type": "select",
                "options": ["Se mantiene el original", "Nuevo captador"],
                "sort_order": 6,
                "llm_instruction": "Pregunta si se mantiene el captador de velocidad original o se instala uno nuevo",
            },
        ],
    },

    # =========================================================================
    # GRUPO 12: MATRICULA
    # =========================================================================
    {
        "code": "MATRICULA",
        "name": "Emplazamiento de matricula",
        "description": "Cambio de ubicacion de matricula: sin brazo o con brazo lateral. Nueva longitud desde rueda delantera hasta parte mas trasera (no escapes). Si matricula antigua, asegurar burlete de goma o portamatriculas.",
        "keywords": [
            "matricula", "portamatriculas", "soporte matricula",
            "brazo lateral", "emplazamiento matricula", "rabillo",
            "portamatriculas corto", "matricula lateral",
            "eliminador", "fender eliminator"
        ],
        "aliases": ["license plate holder", "plate bracket", "tail tidy"],
        "sort_order": 140,
        "warnings": [
            {
                "code": "matricula_luz_asociada",
                "message": "Desde julio 2025 es posible matricula lateral. Lleva asociado cambio de luz de matricula como minimo. Distancia max 30cm al final.",
                "severity": "info",
            },
        ],
        "required_fields": [
            {
                "field_key": "tipo_montaje",
                "field_label": "Tipo de montaje",
                "field_type": "select",
                "options": ["Sin brazo (portamatrículas corto)", "Con brazo lateral"],
                "sort_order": 1,
                "llm_instruction": "Pregunta si el nuevo emplazamiento es sin brazo (portamatrículas corto bajo el colín) o con brazo lateral",
            },
            {
                "field_key": "nueva_longitud_mm",
                "field_label": "Nueva longitud total del vehículo (mm)",
                "field_type": "number",
                "sort_order": 2,
                "example_value": "2050",
                "llm_instruction": "Solicita la nueva longitud desde la rueda delantera hasta la parte más trasera del vehículo (sin contar escapes) en milímetros",
                "validation_rules": {"min_value": 1500, "max_value": 3000},
            },
            {
                "field_key": "distancia_final_mm",
                "field_label": "Distancia matrícula al final (mm)",
                "field_type": "number",
                "sort_order": 3,
                "example_value": "250",
                "llm_instruction": "Solicita la distancia en milímetros desde la matrícula hasta el final del vehículo (máximo 300mm)",
                "validation_rules": {"min_value": 0, "max_value": 400},
            },
            {
                "field_key": "matricula_antigua",
                "field_label": "¿Es matrícula antigua (larga)?",
                "field_type": "boolean",
                "sort_order": 4,
                "llm_instruction": "Pregunta si el vehículo tiene matrícula antigua (formato largo)",
            },
            {
                "field_key": "burlete_goma",
                "field_label": "¿Tiene burlete de goma o portamatrículas protector?",
                "field_type": "boolean",
                "sort_order": 5,
                "is_required": False,
                "llm_instruction": "Si es matrícula antigua, confirma si tiene burlete de goma o portamatrículas para proteger los bordes",
                "condition_field_key": "matricula_antigua",
                "condition_operator": "equals",
                "condition_value": "true",
            },
        ],
    },

    # =========================================================================
    # GRUPO 13: ELEMENTOS CONDUCTOR
    # =========================================================================
    {
        "code": "ESTRIBERAS",
        "name": "Estriberas",
        "description": "Estriberas (reposapies) del conductor. Datos: marca, material, ubicacion (delantera/trasera).",
        "keywords": [
            "estriberas", "estribera", "reposapies", "pedales",
            "footpegs", "estriberas aluminio", "estriberas racing",
            "rizoma", "lightech", "gilles", "lsl", "vortex"
        ],
        "aliases": ["footpegs", "foot pegs", "rider pegs"],
        "sort_order": 145,
        "required_fields": [
            {
                "field_key": "marca",
                "field_label": "Marca",
                "field_type": "text",
                "sort_order": 1,
                "example_value": "Rizoma",
                "llm_instruction": "Solicita la marca de las estriberas",
            },
            {
                "field_key": "material",
                "field_label": "Material",
                "field_type": "select",
                "options": ["Aluminio", "Aluminio CNC", "Acero", "Titanio"],
                "sort_order": 2,
                "llm_instruction": "Pregunta el material de las estriberas",
            },
            {
                "field_key": "ubicacion",
                "field_label": "Ubicación",
                "field_type": "select",
                "options": ["Conductor", "Pasajero", "Ambas"],
                "sort_order": 3,
                "llm_instruction": "Pregunta si las estriberas son del conductor, pasajero o ambas",
            },
        ],
    },

    # =========================================================================
    # GRUPO 14: EXTRAS
    # =========================================================================
    {
        "code": "CABALLETE",
        "name": "Caballete",
        "description": "Caballete central o lateral modificado o eliminado.",
        "keywords": [
            "caballete", "pata de cabra", "caballete central",
            "caballete lateral", "stand", "kickstand",
            "anulacion caballete", "eliminacion caballete"
        ],
        "aliases": ["kickstand", "center stand", "side stand"],
        "sort_order": 150,
    },
    {
        "code": "FILTRO",
        "name": "Filtro de aire",
        "description": "Filtro de aire modificado o de alto rendimiento.",
        "keywords": [
            "filtro", "filtro aire", "filtro de aire",
            "k&n", "bmc", "dna", "sprint filter",
            "filtro conico", "filtro racing", "airbox"
        ],
        "aliases": ["air filter", "intake filter"],
        "sort_order": 160,
        "warnings": [
            {
                "code": "filtro_recargo_lab",
                "message": "Puede llevar recargo de laboratorio. Solo se puede hacer esta reforma en la moto - CONSULTAR.",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "ASIENTO",
        "name": "Asiento / Sillin",
        "description": "Asiento monoplaza, biplaza modificado o tapizado custom.",
        "keywords": [
            "asiento", "sillin", "monoplaza", "biplaza",
            "tapizado", "asiento custom", "asiento cafe racer",
            "asiento racing", "colchoneta", "gel seat"
        ],
        "aliases": ["seat", "saddle"],
        "sort_order": 170,
    },
    {
        "code": "MALETAS",
        "name": "Maletas / Baul",
        "description": "Maletas laterales, top case o alforjas.",
        "keywords": [
            "maletas", "baul", "topcase", "top case",
            "alforjas", "maleta", "cofre", "panniers",
            "givi", "shad", "kappa", "sw-motech"
        ],
        "aliases": ["luggage", "panniers", "saddlebags", "top case"],
        "sort_order": 180,
    },
]

# =============================================================================
# Category-Scoped Warnings
# =============================================================================

CATEGORY_WARNINGS: list[WarningData] = [
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

ADDITIONAL_SERVICES: list[AdditionalServiceData] = [
    {"code": "cert_taller_motos", "name": "Certificado taller concertado", "price": Decimal("85.00"), "sort_order": 1},
    {"code": "urgencia_motos", "name": "Tramitacion urgente", "price": Decimal("100.00"), "sort_order": 2},
    {"code": "plus_lab_simple", "name": "Plus laboratorio simple", "price": Decimal("25.00"), "sort_order": 3},
    {"code": "plus_lab_complejo", "name": "Plus laboratorio complejo", "price": Decimal("75.00"), "sort_order": 4},
    {"code": "ensayo_frenada", "name": "Ensayo dinamico de frenada", "price": Decimal("375.00"), "sort_order": 5},
    {"code": "ensayo_direccion", "name": "Ensayo de direccion", "price": Decimal("400.00"), "sort_order": 6},
]

# =============================================================================
# Base Documentation
# =============================================================================

BASE_DOCUMENTATION: list[BaseDocumentationData] = [
    {
        "code": "documentos_vehiculo",
        "description": "Ficha tecnica del vehiculo (ambas caras, legible) y Permiso de circulacion por la cara escrita",
        "sort_order": 1,
    },
    {
        "code": "fotos_vehiculo",
        "description": "Foto lateral derecha, izquierda, frontal y trasera completa de la moto",
        "sort_order": 2,
    },
]

# =============================================================================
# Prompt Sections
# =============================================================================

PROMPT_SECTIONS: list[PromptSectionData] = [
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
