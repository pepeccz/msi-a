"""
MSI-a Seed Data - Autocaravanas Particular (aseicars-part).

Complete data definitions for motorhome homologations for particular clients.
Based on: 2026 TARIFAS PARTICULARES REGULARIZACION ELEMENTOS AUTOCARAVANAS.pdf

NOTE: This category is a mirror of aseicars-prof with different prices and
some particularities:
- CAMBIO_CLASIF variants use ITV-based logic (not contrasena)
- AIRE_ACONDI is active (is_active=True)
- Additional services include boletin_electrico, certificado_gas, envio_documentacion
- Warning codes are suffixed with _part to avoid collision with prof
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
# NOTE: Prices are different from aseicars-prof (particulares pay more)
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
# NOTE: Mirror of aseicars-prof with these differences:
#   - Warning codes suffixed with _part
#   - AIRE_ACONDI is_active=True (active for particulares)
#   - CAMBIO_CLASIF uses ITV-based variant logic (not contrasena)
#   - CAMBIO_CLASIF_CON/SIN use itv_option / CON_ITV / SIN_ITV
# =============================================================================

ELEMENTS: list[ElementData] = [
    # =========================================================================
    # ELEMENTOS BASE
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
        # NOTE: is_active=True for particulares (different from aseicars-prof where it's False)
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
        "code": "PORTAMOTOS",
        "name": "Portamotos / Soporte motos",
        "description": "Soporte trasero para transportar motos. Incluye calculos de carga.",
        "keywords": ["portamotos", "soporte motos", "moto", "motocicleta", "porta moto"],
        "aliases": ["motorcycle carrier", "bike rack moto"],
        "sort_order": 120,
        "images": [
            {"title": "Portamotos instalado", "description": "Soporte portamotos instalado en trasera", "image_type": "example", "sort_order": 1},
            {"title": "Calculos positivos", "description": "Ejemplo de calculos con resultado positivo", "image_type": "calculation", "sort_order": 2},
            {"title": "Calculos negativos", "description": "Ejemplo de calculos con resultado negativo (no viable)", "image_type": "calculation", "sort_order": 3},
            {"title": "Foto con matricula", "description": "Foto trasera con portamotos y matricula visible", "image_type": "required_document", "sort_order": 4},
        ],
        "warnings": [
            {"code": "portamotos_soportes_part", "message": "Solo se legaliza los soportes, no el portamotos en si. Necesario reparto de cargas.", "severity": "info"},
        ],
    },
    {
        "code": "SUSP_NEUM",
        "name": "Suspension neumatica",
        "description": "Sistema de suspension neumatica. Selecciona el tipo de instalacion.",
        "keywords": ["suspension neumatica", "neumatica", "air suspension", "suspension aire"],
        "aliases": ["air ride", "suspension"],
        "sort_order": 130,
        "is_base": True,
        "question_hint": "¿Que tipo de suspension neumatica: estandar o Full Air?",
        "images": [
            {"title": "Sistema suspension", "description": "Vista general del sistema de suspension neumatica", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "susp_neum_proyecto_part", "message": "Suspension neumatica requiere proyecto medio (T2).", "severity": "info"},
        ],
    },
    {
        "code": "KIT_ESTAB",
        "name": "Kit elevacion / Patas estabilizadoras",
        "description": "Kit de elevacion o patas estabilizadoras hidraulicas",
        "keywords": ["kit elevacion", "patas estabilizadoras", "estabilizadoras", "nivelacion", "patas"],
        "aliases": ["leveling jacks", "stabilizers"],
        "sort_order": 140,
        "images": [
            {"title": "Patas desplegadas", "description": "Sistema de patas estabilizadoras en funcionamiento", "image_type": "example", "sort_order": 1},
            {"title": "Panel de control", "description": "Panel de control del sistema de nivelacion", "image_type": "example", "sort_order": 2},
            {"title": "Foto con matricula", "description": "Foto general del vehiculo con patas visibles y matricula", "image_type": "required_document", "sort_order": 3},
        ],
        "warnings": [
            {"code": "kit_elevacion_mando_part", "message": "Kit de elevacion hidraulica/electrica: solo con mando interior fijo.", "severity": "info"},
        ],
    },
    {
        "code": "AUMENTO_MMTA",
        "name": "Aumento de MMTA",
        "description": "Aumento de la Masa Maxima Tecnica Autorizada del vehiculo",
        "keywords": ["aumento mmta", "mmta", "masa maxima", "incremento peso", "aumento peso"],
        "aliases": ["weight increase", "gross weight"],
        "sort_order": 150,
        "images": [
            {"title": "Documentacion MMTA", "description": "Ejemplo de documentacion para aumento de MMTA", "image_type": "required_document", "sort_order": 1},
            {"title": "Ficha tecnica", "description": "Ficha tecnica con MMTA modificada", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "mmta_sin_ensayo_part", "message": "Aumento de MMTA sin ensayo de frenada: +300 EUR (previo consulta).", "severity": "info"},
            {"code": "mmta_con_ensayo_part", "message": "Aumento de MMTA con ensayo de frenada: +500 EUR (previo consulta).", "severity": "warning"},
        ],
    },
    {
        "code": "GLP_INSTALACION",
        "name": "Instalacion GLP / Gas",
        "description": "Instalacion de sistema de gas GLP. Selecciona el tipo de instalacion.",
        "keywords": ["glp", "gas", "instalacion gas", "bombona", "deposito glp", "autogas"],
        "aliases": ["lpg", "propane"],
        "sort_order": 160,
        "is_base": True,
        "question_hint": "¿Que tipo de instalacion de gas: kit bombona, deposito fijo o duocontrol?",
        "images": [
            {"title": "Sistema GLP", "description": "Vista general de instalacion GLP", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "glp_certificacion_part", "message": "Instalaciones de GLP requieren certificado de instalacion/revision de gas (+65 EUR).", "severity": "warning"},
        ],
    },
    {
        "code": "AUMENTO_PLAZAS",
        "name": "Aumento de plazas",
        "description": "Aumento del numero de plazas homologadas en el vehiculo",
        "keywords": ["aumento plazas", "mas plazas", "plazas adicionales", "asientos"],
        "aliases": ["seat increase", "additional seats"],
        "sort_order": 170,
        "images": [
            {"title": "Configuracion asientos", "description": "Disposicion de asientos adicionales", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion plazas", "description": "Documentacion requerida para aumento de plazas", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "aumento_plazas_consulta_part", "message": "Aumento de plazas requiere consulta previa (+115 EUR adicionales).", "severity": "warning"},
        ],
    },
    {
        "code": "CIERRES_EXT",
        "name": "Cierres exteriores",
        "description": "Cierres y cerraduras exteriores del vehiculo",
        "keywords": ["cierres exteriores", "cerraduras", "cierres", "locks"],
        "aliases": ["external locks", "door locks"],
        "sort_order": 180,
        "images": [
            {"title": "Cierres instalados", "description": "Vista de cierres exteriores instalados", "image_type": "example", "sort_order": 1},
        ],
        "warnings": [
            {"code": "cerraduras_apertura_part", "message": "La cerradura de acceso a vivienda ha de tener apertura desde el interior.", "severity": "warning"},
        ],
    },
    {
        "code": "FAROS_LA",
        "name": "Faros de largo alcance",
        "description": "Faros auxiliares de largo alcance. Selecciona la configuracion.",
        "keywords": ["faros largo alcance", "faros auxiliares", "faros", "luces auxiliares"],
        "aliases": ["spotlights", "driving lights"],
        "sort_order": 190,
        "is_base": True,
        "question_hint": "¿Cuantos faros de largo alcance: 2 faros independientes o 1 barra LED doble?",
        "images": [
            {"title": "Faros instalados", "description": "Faros de largo alcance instalados", "image_type": "example", "sort_order": 1},
        ],
    },
    {
        "code": "DEFENSAS_DEL",
        "name": "Defensas delanteras",
        "description": "Defensa o bullbar delantero instalado en el vehiculo",
        "keywords": ["defensas delanteras", "bullbar", "defensa", "parachoques reforzado"],
        "aliases": ["bull bar", "front guard"],
        "sort_order": 200,
        "images": [
            {"title": "Defensa instalada", "description": "Defensa delantera instalada en vehiculo", "image_type": "example", "sort_order": 1},
            {"title": "Foto frontal con matricula", "description": "Foto frontal del vehiculo con defensa y matricula visible", "image_type": "required_document", "sort_order": 2},
        ],
    },

    # =========================================================================
    # NUEVOS ELEMENTOS (añadidos en 2026, identicos a aseicars-prof)
    # =========================================================================
    {
        "code": "MOBILIARIO_INT",
        "name": "Modificacion del mobiliario interior",
        "description": "Cambios en el mobiliario interior del vehiculo (cocina, armarios, muebles)",
        "keywords": ["mobiliario", "muebles", "interior", "cocina", "armario"],
        "aliases": ["mueble interior"],
        "sort_order": 210,
        "images": [
            {"title": "Mobiliario instalado", "description": "Vista del mobiliario interior modificado", "image_type": "example", "sort_order": 1},
            {"title": "Foto interior general", "description": "Foto general del interior mostrando el mobiliario", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "ELECTRICOS_INT",
        "name": "Elementos electricos interiores",
        "description": "Instalaciones electricas interiores como inversores, baterias adicionales o cargadores",
        "keywords": ["electricos", "inversor", "bateria", "cargador"],
        "aliases": ["sistema electrico"],
        "sort_order": 220,
        "images": [
            {"title": "Instalacion electrica", "description": "Vista de la instalacion electrica interior", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion electrica", "description": "Documentacion de la instalacion electrica", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "electricos_boletin_part", "message": "Elementos electricos interiores requieren Boletin Electrico.", "severity": "warning"},
        ],
    },
    {
        "code": "LLANTAS_ALETINES",
        "name": "Llantas con aletines",
        "description": "Llantas con aletines o guardabarros adicionales",
        "keywords": ["llantas", "aletines", "guardabarros"],
        "aliases": ["llanta con aletin"],
        "sort_order": 230,
        "images": [
            {"title": "Llantas instaladas", "description": "Vista de las llantas con aletines", "image_type": "example", "sort_order": 1},
            {"title": "Foto lateral", "description": "Foto lateral del vehiculo mostrando las llantas", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "TOMA_GAS_EXT",
        "name": "Toma de gas exterior",
        "description": "Toma de gas instalada en el exterior del vehiculo",
        "keywords": ["toma gas", "gas exterior", "conexion gas"],
        "aliases": ["salida de gas"],
        "sort_order": 240,
        "images": [
            {"title": "Toma de gas", "description": "Toma de gas exterior instalada", "image_type": "example", "sort_order": 1},
            {"title": "Detalle toma", "description": "Detalle de la toma de gas con tapa", "image_type": "example", "sort_order": 2},
            {"title": "Documentacion gas", "description": "Documentacion de la instalacion de gas", "image_type": "required_document", "sort_order": 3},
        ],
    },
    {
        "code": "LUCES_CORTESIA_EXT",
        "name": "Luces de cortesia exterior",
        "description": "Luces decorativas o de cortesia instaladas en el exterior del vehiculo",
        "keywords": ["luces cortesia", "cortesia", "luces decorativas"],
        "aliases": ["luz de cortesia"],
        "sort_order": 250,
        "images": [
            {"title": "Luces instaladas", "description": "Luces de cortesia exteriores instaladas", "image_type": "example", "sort_order": 1},
            {"title": "Foto con matricula", "description": "Foto del vehiculo con luces visibles y matricula", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        # NOTE: CAMBIO_CLASIF for aseicars-part uses ITV-based variant logic.
        # The DB has CON_ITV / SIN_ITV variants (different from prof which uses
        # CON_CONTRASENA / SIN_CONTRASENA). This is the correct behaviour for particulares.
        "code": "CAMBIO_CLASIF",
        "name": "Cambio de clasificacion",
        "description": "Cambio de clasificacion del vehiculo. Selecciona si tienes ITV industrial vigente.",
        "keywords": ["cambio clasificacion", "clasificacion", "reclasificacion"],
        "aliases": ["cambiar clasificacion"],
        "sort_order": 260,
        "is_base": True,
        "question_hint": "¿Dispones de ITV industrial vigente para el cambio de clasificacion?",
        "images": [
            {"title": "Documentacion clasificacion", "description": "Documentacion para cambio de clasificacion", "image_type": "example", "sort_order": 1},
        ],
    },
    {
        "code": "CAMBIO_CLASIF_CON",
        "name": "Cambio de clasificacion CON ITV industrial",
        "description": "Cambio de clasificacion del vehiculo manteniendo el ITV industrial vigente",
        "keywords": ["con itv", "mantiene itv", "itv industrial", "si", "con", "mantener"],
        "aliases": [],
        "sort_order": 261,
        "variant_position": 1,
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
        "sort_order": 262,
        "variant_position": 2,
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
    {
        "code": "NEUMATICOS_NO_EQUIV",
        "name": "Neumaticos no equivalentes",
        "description": "Neumaticos con medidas diferentes a las homologadas originalmente",
        "keywords": ["neumaticos", "ruedas", "no equivalente"],
        "aliases": ["neumatico diferente"],
        "sort_order": 270,
        "images": [
            {"title": "Neumaticos instalados", "description": "Neumaticos no equivalentes instalados", "image_type": "example", "sort_order": 1},
            {"title": "Medidas neumatico", "description": "Foto mostrando las medidas del neumatico", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "GALIBOS",
        "name": "Instalacion/reubicacion de galibos",
        "description": "Instalacion o reubicacion de luces de galibo en el vehiculo",
        "keywords": ["galibos", "galibo", "luces galibo"],
        "aliases": ["luz de galibo"],
        "sort_order": 280,
        "images": [
            {"title": "Galibos instalados", "description": "Luces de galibo instaladas en el vehiculo", "image_type": "example", "sort_order": 1},
            {"title": "Foto lateral galibo", "description": "Foto lateral mostrando la posicion de los galibos", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "LUCES_ADICIONALES",
        "name": "Luces adicionales homologadas",
        "description": "Luces adicionales homologadas instaladas en el vehiculo (faros, luces auxiliares)",
        "keywords": ["luces adicionales", "faros adicionales", "luces homologadas"],
        "aliases": ["luz extra"],
        "sort_order": 290,
        "images": [
            {"title": "Luces adicionales", "description": "Luces adicionales homologadas instaladas", "image_type": "example", "sort_order": 1},
            {"title": "Homologacion luces", "description": "Documento de homologacion de las luces", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "TOMAS_EXT_GAS_DUCHA",
        "name": "Tomas externas gas/ducha",
        "description": "Tomas externas para gas y/o ducha instaladas en el vehiculo",
        "keywords": ["tomas externas", "toma gas exterior", "toma ducha"],
        "aliases": ["salida gas y ducha"],
        "sort_order": 300,
        "images": [
            {"title": "Tomas externas", "description": "Tomas externas de gas y ducha instaladas", "image_type": "example", "sort_order": 1},
            {"title": "Detalle tomas", "description": "Detalle de las tomas con tapas", "image_type": "example", "sort_order": 2},
            {"title": "Documentacion", "description": "Documentacion de las instalaciones", "image_type": "required_document", "sort_order": 3},
        ],
    },

    # =========================================================================
    # VARIANTES DE BOLA_REMOLQUE
    # =========================================================================
    {
        "code": "BOLA_SIN_MMR",
        "name": "Bola de remolque SIN aumento MMR",
        "description": "Enganche de remolque sin aumento de la Masa Maxima Remolcable",
        "keywords": ["sin mmr", "no aumenta mmr", "sin aumento", "mismo mmr", "no", "sin", "no aumenta", "no cambia", "igual"],
        "aliases": [],
        "sort_order": 81,
        "variant_position": 1,
        "parent_code": "BOLA_REMOLQUE",
        "variant_type": "mmr_option",
        "variant_code": "SIN_MMR",
        "images": [
            {"title": "Bola instalada", "description": "Bola de remolque instalada sin aumento MMR", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion", "description": "Documentacion requerida para bola sin MMR", "image_type": "required_document", "sort_order": 2},
        ],
        "warnings": [
            {"code": "bola_sin_mmr_warning_part", "message": "Bola sin MMR: NO apta para remolcar, solo portaequipajes. Necesario reparto de cargas.", "severity": "warning"},
        ],
    },
    {
        "code": "BOLA_CON_MMR",
        "name": "Bola de remolque CON aumento MMR",
        "description": "Enganche de remolque con aumento de la Masa Maxima Remolcable. Requiere documentacion adicional.",
        "keywords": ["con mmr", "aumenta mmr", "aumento mmr", "mayor mmr", "si", "si aumenta", "incrementa", "mas mmr"],
        "aliases": [],
        "sort_order": 82,
        "variant_position": 2,
        "parent_code": "BOLA_REMOLQUE",
        "variant_type": "mmr_option",
        "variant_code": "CON_MMR",
        "images": [
            {"title": "Paso 1: Bola instalada", "description": "Foto de la bola de remolque instalada en el vehiculo", "image_type": "step", "sort_order": 1},
            {"title": "Paso 2: Placa fabricante", "description": "Foto de la placa del fabricante de la bola con especificaciones", "image_type": "step", "sort_order": 2},
            {"title": "Paso 3: Carga vertical", "description": "Foto o documento mostrando la carga vertical homologada", "image_type": "step", "sort_order": 3},
            {"title": "Paso 4: Ficha tecnica", "description": "Ficha tecnica actual del vehiculo (ambas caras)", "image_type": "step", "sort_order": 4},
            {"title": "Paso 5: Doc MMR nueva", "description": "Documentacion de la nueva MMR (del fabricante de la bola o ficha reducida)", "image_type": "step", "sort_order": 5},
        ],
    },
    {
        "code": "BRAZO_PORTA",
        "name": "Brazo portaequipajes",
        "description": "Brazo portaequipajes asociado a bola de remolque sin MMR",
        "keywords": ["brazo portaequipajes", "portaequipajes bola", "brazo"],
        "aliases": [],
        "sort_order": 811,
        "variant_position": 1,
        "parent_code": "BOLA_SIN_MMR",
        "variant_type": "accessory",
        "variant_code": "BRAZO",
        "images": [
            {"title": "Brazo instalado", "description": "Brazo portaequipajes instalado en bola de remolque", "image_type": "example", "sort_order": 1},
        ],
    },

    # =========================================================================
    # VARIANTES DE SUSP_NEUM
    # =========================================================================
    {
        "code": "SUSP_NEUM_EST",
        "name": "Suspension neumatica estandar",
        "description": "Suspension neumatica con configuracion estandar",
        "keywords": ["estandar", "normal", "basica", "simple", "standard", "parcial", "trasera"],
        "aliases": [],
        "sort_order": 131,
        "variant_position": 1,
        "parent_code": "SUSP_NEUM",
        "variant_type": "suspension_type",
        "variant_code": "ESTANDAR",
        "images": [
            {"title": "Configuracion estandar", "description": "Sistema de suspension neumatica estandar", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion", "description": "Documentacion requerida para suspension estandar", "image_type": "required_document", "is_required": True, "sort_order": 2, "user_instruction": "Certificado de instalacion del taller autorizado que realizo el montaje de la suspension neumatica, con sello del taller y datos del vehiculo."},
        ],
    },
    {
        "code": "SUSP_NEUM_FULL",
        "name": "Suspension neumatica FULL AIR",
        "description": "Suspension neumatica completa (FULL AIR) en todos los ejes",
        "keywords": ["full air", "full", "completa", "total", "todos los ejes", "ambos ejes", "delantera y trasera"],
        "aliases": [],
        "sort_order": 132,
        "variant_position": 2,
        "parent_code": "SUSP_NEUM",
        "variant_type": "suspension_type",
        "variant_code": "FULL_AIR",
        "images": [
            {"title": "Sistema FULL AIR", "description": "Sistema de suspension FULL AIR completo", "image_type": "example", "sort_order": 1},
            {"title": "Panel de control", "description": "Panel de control del sistema FULL AIR", "image_type": "example", "sort_order": 2},
            {"title": "Documentacion FULL AIR", "description": "Documentacion especifica para sistema FULL AIR", "image_type": "required_document", "is_required": True, "sort_order": 3, "user_instruction": "Certificado de instalacion del taller autorizado que realizo el montaje del sistema FULL AIR, incluyendo datos del vehiculo, sello del taller y documentacion tecnica del fabricante."},
        ],
    },

    # =========================================================================
    # VARIANTES DE GLP_INSTALACION
    # =========================================================================
    {
        "code": "GLP_KIT_BOMB",
        "name": "Kit bombona GLP",
        "description": "Instalacion de kit de bombona de GLP",
        "keywords": ["kit bombona", "bombona", "kit", "portatil", "portable", "cambiable", "intercambiable"],
        "aliases": [],
        "sort_order": 161,
        "variant_position": 1,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "KIT_BOMBONA",
        "images": [
            {"title": "Kit bombona instalado", "description": "Kit de bombona GLP instalado", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion bombona", "description": "Documentacion requerida para kit bombona", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "GLP_DEPOSITO",
        "name": "Deposito GLP",
        "description": "Instalacion de deposito fijo de GLP",
        "keywords": ["deposito", "deposito fijo", "tanque", "fijo", "permanente", "instalado"],
        "aliases": [],
        "sort_order": 162,
        "variant_position": 2,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "DEPOSITO",
        "images": [
            {"title": "Deposito instalado", "description": "Deposito fijo de GLP instalado", "image_type": "example", "sort_order": 1},
            {"title": "Boca de carga", "description": "Boca de carga del deposito GLP", "image_type": "example", "sort_order": 2},
            {"title": "Documentacion deposito", "description": "Documentacion requerida para deposito GLP", "image_type": "required_document", "sort_order": 3},
        ],
    },
    {
        "code": "GLP_DUOCONTROL",
        "name": "Duocontrol GLP",
        "description": "Sistema Duocontrol para gestion de GLP",
        "keywords": ["duocontrol", "duo control", "doble control", "automatico", "regulador automatico"],
        "aliases": [],
        "sort_order": 163,
        "variant_position": 3,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "DUOCONTROL",
        "images": [
            {"title": "Sistema Duocontrol", "description": "Sistema Duocontrol instalado", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion Duocontrol", "description": "Documentacion requerida para Duocontrol", "image_type": "required_document", "sort_order": 2},
        ],
    },

    # =========================================================================
    # VARIANTES DE FAROS_LA
    # =========================================================================
    {
        "code": "FAROS_LA_2F",
        "name": "2 Faros de largo alcance",
        "description": "Instalacion de 2 faros de largo alcance independientes",
        "keywords": ["2 faros", "dos faros", "2", "dos", "par", "ambos", "independientes", "separados"],
        "aliases": [],
        "sort_order": 191,
        "variant_position": 1,
        "parent_code": "FAROS_LA",
        "variant_type": "installation_config",
        "variant_code": "2FAROS",
        "images": [
            {"title": "2 faros instalados", "description": "Dos faros de largo alcance instalados", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion 2 faros", "description": "Documentacion para instalacion de 2 faros", "image_type": "required_document", "sort_order": 2},
        ],
    },
    {
        "code": "FAROS_LA_1D",
        "name": "1 Faro doble largo alcance",
        "description": "Instalacion de 1 faro doble (barra LED) de largo alcance",
        "keywords": ["1 faro", "uno", "barra led", "doble", "barra", "led", "unico", "single"],
        "aliases": [],
        "sort_order": 192,
        "variant_position": 2,
        "parent_code": "FAROS_LA",
        "variant_type": "installation_config",
        "variant_code": "1DOBLE",
        "images": [
            {"title": "Faro doble instalado", "description": "Faro doble de largo alcance instalado", "image_type": "example", "sort_order": 1},
            {"title": "Documentacion faro doble", "description": "Documentacion para instalacion de faro doble", "image_type": "required_document", "sort_order": 2},
        ],
    },

    # =========================================================================
    # VARIANTES DE PLACA_SOLAR
    # =========================================================================
    {
        "code": "PLACA_SOLAR_SIMPLE",
        "name": "Placa solar (con regulador existente)",
        "description": "Placa solar conectada a instalacion preexistente, es decir, conectada a regulador existente en el vehiculo. Como maximo se pueden conectar dos placas a un mismo regulador.",
        "keywords": ["placa solar sin regulador", "sin regulador", "conectada a regulador existente", "ya tiene regulador"],
        "aliases": [],
        "sort_order": 31,
        "variant_position": 1,
        "parent_code": "PLACA_SOLAR",
        "variant_type": "placa_solar_conectada_regulador_existente",
        "variant_code": "PLACA_SOLAR_CONECTADA_REGULADOR_EXISTENTE",
        "images": [
            {
                "title": "PLACA SOLAR CONECTADA A REGULADOR PREEXISTENTE",
                "description": "Foto de la placa solar ubicada en el techo, asi como foto de la pegatina de la placa. En caso de no haber realizado la foto antes de colocarla decir Marca y POTENCIA. \n\n(*)Esta opcion solo es posible hasta 2 placas solares conectadas a un mismo regulador existente.\n\n(*)En algunas ITVs suelen exigir las medidas de la misma (largo x ancho x alto de la placa)",
                "image_type": "example",
                "sort_order": 0,
            },
        ],
    },
    {
        "code": "PLACA_SOLAR_REGULADOR_INTERIOR",
        "name": "Placa solar con regulador oculto (interior de armarios o tras la ultima fila de asientos)",
        "description": "Foto del techo en el que se vea la placa solar y foto de la etiqueta. Si la etiqueta no es visible definir marca de la placa y Potencia. (En algunas ITV´s requieren si no se ve las dimensiones largo x ancho x alto)\n\nFoto del regulador donde se aprecie la marca, el modelo y la Contraseña de homologacion, asi como la ubicacion del mismo, para comprobar que esta en el interior de un mueble o en la zona de maleteros posterior a la ultima fila de asientos.",
        "keywords": ["regulador en armario", "armario", "regulador oculto", "tras ultima fila", "detras asientos", "mueble cocina", "regulador en mueble", "regulador en maletero"],
        "aliases": [],
        "sort_order": 32,
        "variant_position": 2,
        "parent_code": "PLACA_SOLAR",
        "variant_type": "regulator_location",
        "variant_code": "REGULADOR_OCULTO",
        "images": [
            {
                "title": "PLACA SOLAR CON REGULADOR INTERIOR",
                "description": "Foto del techo en el que se vea la placa solar y foto de la etiqueta. Si la etiqueta no es visible definir marca de la placa y Potencia. (En algunas ITV´s requieren si no se ve las dimensiones largo x ancho x alto)\n\nFoto del regulador donde se aprecie la marca, el modelo y la Contraseña de homologacion, asi como la ubicacion del mismo, para comprobar que esta en el interior de un mueble o en la zona de maleteros posterior a la ultima fila de asientos.",
                "image_type": "example",
                "sort_order": 0,
            },
        ],
    },
    {
        "code": "PLACA_SOLAR_REGULADOR_VISIBLE",
        "name": "Placa solar con regulador visible en zona de pasajeros",
        "description": "Foto de la placa solar ubicada en el techo, asi como foto de la pegatina de la placa.  En caso de no haber realizado la foto antes de colocarla decir Marca y POTENCIA.\n\nEn la foto del regulador que se vea correctamente la ubicacion del mismo, asi como la marca, el modelo y la contraseña de homologacion.\n\n(*)Solo es posible hasta 2 placas solares conectadas a un mismo regulador.\n\n(*)En algunas ITVs suelen exigir las medidas de la misma (largo x ancho x alto de la placa)",
        "keywords": ["regulador visible", "a la vista", "visible en habitaculo", "regulador en zona pasajeros", "se ve el regulador", "regulador a la vista", "zona pasajeros", "salon"],
        "aliases": [],
        "sort_order": 33,
        "variant_position": 3,
        "parent_code": "PLACA_SOLAR",
        "variant_type": "regulator_location",
        "variant_code": "REGULADOR_VISIBLE",
        "images": [
            {
                "title": "PLACA SOLAR REGULADOR VISIBLE",
                "description": "Foto de la placa solar ubicada en el techo, asi como foto de la pegatina de la placa. En caso de no haber realizado la foto antes de colocarla decir Marca y POTENCIA. En la foto del regulador que se vea correctamente la ubicacion del mismo, asi como la marca, el modelo y la contraseña de homologacion.\n\n(*)Solo es posible hasta 2 placas solares conectadas a un mismo regulador.\n\n(*)En algunas ITVs suelen exigir las medidas de la misma (largo x ancho x alto de la placa)",
                "image_type": "example",
                "sort_order": 0,
            },
        ],
    },

    # =========================================================================
    # VARIANTES DE TOLDO_LAT
    # =========================================================================
    {
        "code": "TOLDO_SIMPLE",
        "name": "Toldo lateral (sin afectar galibo)",
        "description": "Toldo lateral que NO afecta a la luz de galibo del vehiculo (no aumenta el ancho).",
        "keywords": ["sin galibo", "no afecta", "mismo ancho", "no aumenta ancho", "no", "sin", "igual ancho", "no cambia"],
        "aliases": [],
        "sort_order": 21,
        "variant_position": 1,
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
        "variant_position": 2,
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
            {"code": "toldo_galibo_medidas_part", "message": "Especial atencion con luz de galibo. Medir nuevo ancho del vehiculo. Aportar medidas.", "severity": "warning"},
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
        "associations": ["AUMENTO_MMTA", "AUMENTO_PLAZAS"],
    },
    {
        "code": "gas_aseicars_part",
        "message": "Instalaciones de gas requieren certificacion especifica (+65 EUR certificado).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["gas", "instalacion gas", "butano", "propano", "glp"],
        },
        "associations": ["GLP_INSTALACION", "TOMA_GAS_EXT", "TOMAS_EXT_GAS_DUCHA"],
    },
    {
        "code": "electricos_aseicars_part",
        "message": "Instalaciones electricas de alta potencia pueden requerir proyecto y boletin electrico.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electricos", "instalacion electrica", "inversor"],
        },
        "associations": ["ELECTRICOS_INT", "ESCALON_ELEC"],
    },
    {
        "code": "reformas_adicionales_itv_part",
        "message": "Si en ITV se detectan reformas no declaradas, se cobrara la tarifa correspondiente adicional.",
        "severity": "warning",
        # No associations: trigger_conditions=None → always shown, not element-specific
    },
    {
        "code": "boletin_electrico_aseicars_part",
        "message": "Certificado combinado de instalacion/revision electricas 12v y 230v: 65 EUR.",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["electrico", "aire acondicionado", "escalon", "regulador"],
        },
        "associations": [
            "AIRE_ACONDI", "ELECTRICOS_INT", "ESCALON_ELEC", "GLP_DUOCONTROL",
            "PLACA_SOLAR_REGULADOR_INTERIOR", "PLACA_SOLAR_REGULADOR_VISIBLE", "PLACA_SOLAR_SIMPLE",
        ],
    },
]

# =============================================================================
# Additional Services
# NOTE: aseicars-part has more services than prof (includes gas and electrical certs)
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

BASE_DOCUMENTATION: list[BaseDocumentationData] = [
    {
        "code": "ficha_tecnica",
        "description": "Ficha tecnica del vehiculo (ambas caras, legible)",
        "sort_order": 1,
    },
    {
        "code": "permiso_circulacion",
        "description": "Permiso de circulacion (cara escrita)",
        "sort_order": 2,
    },
    {
        "code": "dni_titular",
        "description": "DNI/NIE del titular (ambas caras)",
        "sort_order": 3,
    },
    {
        "code": "fotos_vehiculo",
        "description": "Foto lateral derecha, izquierda, frontal y trasera completa del vehiculo",
        "sort_order": 4,
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
| Placas solares | T6 (1 elem) / T5 (2-3) |
| Toldo lateral | T6 (1 elem) |
| Antena parabolica | T6 (1 elem) |
| Mobiliario interior | T3 (con proyecto) |
| Electricos interior | T3 (con proyecto) |
| Llantas y aletines | T3 (con proyecto) |
| Bola remolque | T4 (sin proyecto) / T2 (con proyecto) |
| Gas | T3 (requiere proyecto) |
| Cambio clasificacion | T3 (proyecto basico) |
| Neumaticos no equiv | T4 (sin proyecto) |""",
        "is_active": True,
    },
    {
        "code": "special_cases",
        "section_type": "special_cases",
        "content": """### CASOS ESPECIALES AUTOCARAVANAS PARTICULARES:
1. Instalaciones de gas requieren certificacion (+65 EUR)
2. MMTA requiere proyecto completo (T1)
3. Bola remolque puede o no requerir proyecto segun capacidad MMR
4. Placa solar: variantes segun ubicacion del regulador
5. Toldo que afecta galibo requiere medidas del nuevo ancho
6. Cambio de clasificacion con/sin ITV industrial (T3)""",
        "is_active": True,
    },
]
