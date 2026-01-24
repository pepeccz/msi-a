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
                "code": "velocimetro_recargo",
                "message": "Si el velocimetro no es digital, llevara recargo de laboratorio (+25/75 EUR). No se homologa la posicion sino el soporte.",
                "severity": "info",
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
