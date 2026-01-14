"""
MSI Automotive - Seed data for Element System (Motocicletas Particular).

This script populates the database with:
1. Element catalog (homologable elements for motorcycles)
2. Base documentation requirements
3. Warnings and alerts
4. Tier element inclusions (references between tiers and elements)

Based on the official MSI form: "FORMULARIO DATOS MOTO MSI REV 2023-01-17"
Tariffs: 2026 TARIFAS USUARIOS FINALES MOTO.pdf

Tier Structure from PDF:
- T1 (410EUR): Proyecto completo - cualquier numero de elementos
- T2 (325EUR): Proyecto medio - 1-2 de T3, hasta 4 de T4
- T3 (280EUR): Proyecto sencillo - 1 elemento principal + hasta 2 de T4
- T4 (220EUR): Sin proyecto varios elementos - 3+ elementos de lista
- T5 (175EUR): Sin proyecto 2 elementos - hasta 2 elementos
- T6 (140EUR): Sin proyecto 1 elemento - solo 1 elemento

Run with: python -m database.seeds.motos_elements_seed
"""

import asyncio
import logging

from sqlalchemy import select, delete

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    TierElementInclusion,
    BaseDocumentation,
    Warning,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Element Definitions - Motocicletas Particular (39 elementos)
# =============================================================================
# Based on official MSI form: FORMULARIO DATOS MOTO MSI REV 2023-01-17

ELEMENTS = [
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T1",
        "requires_project": True,
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
        "tier_level": "T6",
        "requires_project": False,
    },

    # =========================================================================
    # GRUPO 3: SUSPENSION
    # =========================================================================
    {
        "code": "SUSPENSION_DEL",
        "name": "Suspension delantera (barras/muelles)",
        "description": "Modificacion de barras o muelles de la suspension delantera. Para cambio de horquilla completa usar elemento HORQUILLA.",
        "keywords": [
            "suspension delantera", "barras suspension", "muelles barras",
            "barras de horquilla", "muelles suspension", "fork springs",
            "ohlins", "showa", "wp", "kayaba", "marzocchi"
        ],
        "aliases": ["front suspension", "fork springs", "suspension bars"],
        "sort_order": 20,
        "tier_level": "T3",
        "requires_project": True,
    },
    {
        "code": "SUSPENSION_TRAS",
        "name": "Suspension trasera",
        "description": "Amortiguador trasero o mono modificado. Incluye muelle (marca, modelo, longitud, grosor espira, diametro) y amortiguador.",
        "keywords": [
            "suspension trasera", "amortiguador", "amortiguador trasero",
            "mono", "muelle trasero", "shock", "mono shock",
            "ohlins", "showa", "wp", "yss", "bitubo", "hagon",
            "muelles traseros", "amortiguadores"
        ],
        "aliases": ["rear suspension", "rear shock", "mono amortiguador"],
        "sort_order": 30,
        "tier_level": "T3",
        "requires_project": True,
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
        "tier_level": "T1",
        "requires_project": True,
    },

    # =========================================================================
    # GRUPO 4: SISTEMA DE FRENADO (5 elementos)
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T3",
        "requires_project": True,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T3",
        "requires_project": True,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
    },

    # =========================================================================
    # GRUPO 7: ALUMBRADO Y SENALIZACION (7 elementos)
    # =========================================================================
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
        "tier_level": "T6",
        "requires_project": False,
    },
    {
        "code": "INTERMITENTES_DEL",
        "name": "Intermitentes delanteros",
        "description": "Intermitentes delanteros. Distancia minima entre bordes interiores: 240mm. Requiere foto de marcado homologacion, distancia entre bordes, angulos y distancia al faro principal.",
        "keywords": [
            "intermitentes delanteros", "indicadores delanteros",
            "intermitente delantero", "direccionales delanteros",
            "intermitentes frontales", "leds delanteros"
        ],
        "aliases": ["front turn signals", "front indicators"],
        "sort_order": 82,
        "tier_level": "T6",
        "requires_project": False,
    },
    {
        "code": "INTERMITENTES_TRAS",
        "name": "Intermitentes traseros",
        "description": "Intermitentes traseros. Distancia minima entre bordes exteriores: 75mm. Angulo interior: 20 grados (50 grados si lleva luz de freno integrada). Distancia maxima al final: 30cm.",
        "keywords": [
            "intermitentes traseros", "indicadores traseros",
            "intermitente trasero", "direccionales traseros",
            "intermitentes posteriores", "leds traseros",
            "piloto integrado", "intermitente con freno"
        ],
        "aliases": ["rear turn signals", "rear indicators"],
        "sort_order": 84,
        "tier_level": "T6",
        "requires_project": False,
    },
    {
        "code": "PILOTO_FRENO",
        "name": "Piloto freno trasero",
        "description": "Piloto de freno trasero (luz de stop). Si combinado con intermitentes, el angulo es de 50 grados. Requiere foto de altura y angulos de visibilidad.",
        "keywords": [
            "piloto freno", "luz freno", "piloto trasero",
            "stop", "luz stop", "brake light", "piloto led",
            "luz de freno", "tercera luz freno"
        ],
        "aliases": ["brake light", "stop light", "tail light"],
        "sort_order": 86,
        "tier_level": "T6",
        "requires_project": False,
    },
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
        "tier_level": "T6",
        "requires_project": False,
    },
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
        "tier_level": "T6",
        "requires_project": False,
    },
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
    },

    # =========================================================================
    # GRUPO 14: EXTRAS (mantenidos de seed anterior)
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
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
        "tier_level": "T6",
        "requires_project": False,
    },
]


# =============================================================================
# Base Documentation - Documentacion requerida para todas las motos
# =============================================================================

BASE_DOCUMENTATION = [
    {
        "description": "Ficha tecnica del vehiculo (ambas caras, legible) y Permiso de circulacion por la cara escrita",
        "image_url": "/images/ce971fe3-51a2-41ef-adc6-eee779a7deee.png",
        "sort_order": 1,
    },
    {
        "description": "Foto lateral derecha, izquierda, frontal y trasera completa de la moto",
        "image_url": "/images/3675deb6-b0dc-4fd4-9b1a-f02acbad48d6.png",
        "sort_order": 2,
    },
]


# =============================================================================
# Warnings - Advertencias para la categoria motos
# =============================================================================

WARNINGS = [
    {
        "code": "consultar_ingeniero_motos_part",
        "message": "Esta modificacion es compleja. Se recomienda consultar viabilidad con el ingeniero.",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["subchasis", "aumento plazas", "motor", "horquilla completa"]
        },
    },
    {
        "code": "ensayo_frenada_motos_part",
        "message": "Modificaciones en sistema de frenado pueden requerir ensayo de frenada adicional (375 EUR).",
        "severity": "info",
        "trigger_conditions": {
            "element_keywords": ["frenos", "disco freno", "pinza freno", "bomba freno", "sistema de frenado"]
        },
    },
    {
        "code": "marcado_homologacion_motos_part",
        "message": "Este elemento requiere marcado de homologacion visible (numero E).",
        "severity": "warning",
        "trigger_conditions": {
            "element_keywords": ["escape", "faros", "retrovisores", "intermitentes", "pilotos", "neumaticos", "llantas"]
        },
    },
]


# =============================================================================
# Tier Configuration - Based on PDF 2026 TARIFAS USUARIOS FINALES MOTO
# =============================================================================

# Elementos que requieren T1 (Proyecto Completo - 410EUR)
T1_ELEMENTS = ["SUBCHASIS", "HORQUILLA"]

# Elementos que van en T3 (Proyecto Sencillo - 280EUR) cuando son el principal
T3_ELEMENTS = ["SUSPENSION_DEL", "SUSPENSION_TRAS", "FRENADO_LATIGUILLOS", "CARENADO"]

# El resto de elementos van en T4-T6 segun cantidad


async def seed_motos_elements():
    """Seed element system data for motos-part category."""
    logger.info("=" * 80)
    logger.info("Starting Motos Element System Seed (39 elements)")
    logger.info("=" * 80)

    async with get_async_session() as session:
        # Step 1: Get or verify category exists
        logger.info("\n[STEP 1] Getting category: motos-part")
        category_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "motos-part")
            .where(VehicleCategory.is_active == True)
        )
        category = category_result.scalar()

        if not category:
            logger.error("Category 'motos-part' not found. Run motos_particular_seed.py first!")
            return False

        logger.info(f"Found category: {category.name} (ID: {category.id})")

        # Step 2: Get all tiers for this category
        logger.info("\n[STEP 2] Getting tiers for category")
        tiers_result = await session.execute(
            select(TariffTier)
            .where(TariffTier.category_id == category.id)
            .where(TariffTier.is_active == True)
            .order_by(TariffTier.sort_order)
        )
        tiers = {t.code: t for t in tiers_result.scalars().all()}

        if not tiers:
            logger.error("No active tiers found for this category!")
            return False

        logger.info(f"Found {len(tiers)} tiers:")
        for code, tier in tiers.items():
            logger.info(f"  - {code}: {tier.name} ({tier.price}EUR)")

        # Step 3: Delete existing elements for this category (clean slate)
        logger.info("\n[STEP 3] Removing existing elements for clean slate")
        existing_elements = await session.execute(
            select(Element).where(Element.category_id == category.id)
        )
        deleted_count = 0
        for elem in existing_elements.scalars().all():
            await session.delete(elem)
            deleted_count += 1
        await session.flush()
        logger.info(f"  Deleted {deleted_count} existing elements")

        # Step 4: Delete existing base documentation for this category
        logger.info("\n[STEP 4] Removing existing base documentation")
        await session.execute(
            delete(BaseDocumentation).where(BaseDocumentation.category_id == category.id)
        )
        await session.flush()
        logger.info("  Deleted existing base documentation")

        # Step 5: Delete existing warnings for this category
        logger.info("\n[STEP 5] Removing existing warnings for category")
        await session.execute(
            delete(Warning).where(Warning.category_id == category.id)
        )
        await session.flush()
        logger.info("  Deleted existing warnings")

        # Step 6: Create new elements
        logger.info("\n[STEP 6] Creating 39 new elements")
        created_elements = {}

        for elem_data in ELEMENTS:
            element = Element(
                category_id=category.id,
                code=elem_data["code"],
                name=elem_data["name"],
                description=elem_data["description"],
                keywords=elem_data["keywords"],
                aliases=elem_data.get("aliases", []),
                is_active=True,
                sort_order=elem_data["sort_order"],
            )
            session.add(element)
            await session.flush()
            created_elements[elem_data["code"]] = element
            logger.info(f"  + {elem_data['code']}: {elem_data['name']}")

        # Step 7: Create base documentation
        logger.info("\n[STEP 7] Creating base documentation")
        for doc_data in BASE_DOCUMENTATION:
            doc = BaseDocumentation(
                category_id=category.id,
                description=doc_data["description"],
                image_url=doc_data.get("image_url"),
                sort_order=doc_data["sort_order"],
            )
            session.add(doc)
            logger.info(f"  + Doc {doc_data['sort_order']}: {doc_data['description'][:50]}...")
        await session.flush()

        # Step 8: Create warnings
        logger.info("\n[STEP 8] Creating warnings")
        for warn_data in WARNINGS:
            warning = Warning(
                code=warn_data["code"],
                message=warn_data["message"],
                severity=warn_data["severity"],
                category_id=category.id,
                trigger_conditions=warn_data.get("trigger_conditions"),
                is_active=True,
            )
            session.add(warning)
            logger.info(f"  + {warn_data['code']}: {warn_data['message'][:50]}...")
        await session.flush()

        # Step 9: Create tier element inclusions
        logger.info("\n[STEP 9] Creating tier element inclusions")

        # Clear existing inclusions
        for tier in tiers.values():
            existing_inclusions = await session.execute(
                select(TierElementInclusion)
                .where(TierElementInclusion.tier_id == tier.id)
            )
            for inc in existing_inclusions.scalars().all():
                await session.delete(inc)
        await session.flush()

        all_element_codes = list(created_elements.keys())

        # T6 (140EUR): 1 elemento de cualquier tipo
        if "T6" in tiers:
            logger.info("  T6 (140EUR): Any 1 element")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T6"].id,
                    element_id=created_elements[code].id,
                    max_quantity=1,
                    notes=f"T6 allows 1 {code}",
                )
                session.add(inc)

        # T5 (175EUR): Hasta 2 elementos
        if "T5" in tiers:
            logger.info("  T5 (175EUR): Up to 2 elements")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T5"].id,
                    element_id=created_elements[code].id,
                    max_quantity=2,
                    notes=f"T5 allows up to 2 {code}",
                )
                session.add(inc)

        # T4 (220EUR): 3+ elementos
        if "T4" in tiers:
            logger.info("  T4 (220EUR): 3+ elements (no project)")
            for code in all_element_codes:
                if code not in T1_ELEMENTS and code not in T3_ELEMENTS:
                    inc = TierElementInclusion(
                        tier_id=tiers["T4"].id,
                        element_id=created_elements[code].id,
                        max_quantity=10,
                        notes=f"T4 allows multiple {code}",
                    )
                    session.add(inc)

        # T3 (280EUR): Proyecto sencillo
        if "T3" in tiers:
            logger.info("  T3 (280EUR): Simple project elements")
            for code in all_element_codes:
                if code not in T1_ELEMENTS:
                    inc = TierElementInclusion(
                        tier_id=tiers["T3"].id,
                        element_id=created_elements[code].id,
                        max_quantity=None,
                        notes=f"T3 proyecto sencillo - {code}",
                    )
                    session.add(inc)

        # T2 (325EUR): Proyecto medio
        if "T2" in tiers:
            logger.info("  T2 (325EUR): Medium project")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T2"].id,
                    element_id=created_elements[code].id,
                    max_quantity=None,
                    notes=f"T2 proyecto medio - {code}",
                )
                session.add(inc)

        # T1 (410EUR): Proyecto completo - todo ilimitado
        if "T1" in tiers:
            logger.info("  T1 (410EUR): Complete project - all unlimited")
            for code in all_element_codes:
                inc = TierElementInclusion(
                    tier_id=tiers["T1"].id,
                    element_id=created_elements[code].id,
                    max_quantity=None,
                    notes=f"T1 proyecto completo - {code} unlimited",
                )
                session.add(inc)

            # T1 also includes all lower tiers
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    inc = TierElementInclusion(
                        tier_id=tiers["T1"].id,
                        included_tier_id=tiers[ref_tier_code].id,
                        max_quantity=None,
                        notes=f"T1 includes all of {ref_tier_code}",
                    )
                    session.add(inc)

        # Step 10: Commit all changes
        logger.info("\n[STEP 10] Committing changes to database")
        try:
            await session.commit()
            logger.info("Committed successfully!")
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            await session.rollback()
            return False

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("MOTOS ELEMENT SEED COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info(f"Created {len(created_elements)} elements for motos-part")
    logger.info(f"Created {len(BASE_DOCUMENTATION)} base documentation items")
    logger.info(f"Created {len(WARNINGS)} warnings")
    logger.info("\nElements by group:")
    logger.info("  - Escape: 1")
    logger.info("  - Chasis/Estructura: 2 (SUBCHASIS, ASIDEROS)")
    logger.info("  - Suspension: 3 (DEL, TRAS, HORQUILLA)")
    logger.info("  - Frenado: 5 (DISCOS, PINZAS, BOMBAS, LATIGUILLOS, DEPOSITO)")
    logger.info("  - Carroceria: 4 (CARENADO, GUARDABARROS_DEL, GUARDABARROS_TRAS, CARROCERIA)")
    logger.info("  - Direccion/Manillar: 4 (MANILLAR, TIJAS, ESPEJOS, MANDOS_AVANZADOS)")
    logger.info("  - Alumbrado: 7 (FARO, INTERMIT_DEL/TRAS, PILOTO, LUZ_MAT, CATADIOP, ANTINIEBLAS)")
    logger.info("  - Mandos/Controles: 3 (MANDOS_MANILLAR, CLAUSOR, STARTER)")
    logger.info("  - Ruedas: 2 (LLANTAS, NEUMATICOS)")
    logger.info("  - Combustible: 1 (DEPOSITO)")
    logger.info("  - Instrumentacion: 1 (VELOCIMETRO)")
    logger.info("  - Matricula: 1")
    logger.info("  - Conductor: 1 (ESTRIBERAS)")
    logger.info("  - Extras: 4 (CABALLETE, FILTRO, ASIENTO, MALETAS)")
    logger.info("\nTotal: 39 elements")

    return True


async def main():
    """Main entry point."""
    try:
        success = await seed_motos_elements()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
