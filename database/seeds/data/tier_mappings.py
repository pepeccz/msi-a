"""
MSI-a Seed Data - Tier Element Mappings.

Single source of truth for tier-element relationships.
Defines which elements belong to which tier levels for each category.

Based on official 2026 tariff PDFs:
- 2026 TARIFAS USUARIOS FINALES MOTO.pdf
- 2026 TARIFAS PROFESIONALES REGULARIZACION ELEMENTOS AUTOCARAVANAS.pdf
"""

from typing import TypedDict, NotRequired


class TierMappingConfig(TypedDict):
    """Configuration for tier element inclusion."""
    min_qty: NotRequired[int]
    max_qty: NotRequired[int]
    notes: str


# =============================================================================
# MOTOS-PART: Element-Tier Mapping
# =============================================================================
# Structure from "2026 TARIFAS USUARIOS FINALES MOTO":
#
# T6 (140EUR): 1 elemento de lista T4
# T5 (175EUR): Hasta 2 elementos de T4
# T4 (220EUR): 2+ elementos sin proyecto (lista base)
# T3 (280EUR): 1 elemento T3 + hasta 2 de T4 (proyecto sencillo)
# T2 (325EUR): 1-2 elementos T3 + hasta 4 de T4 (proyecto medio)
# T1 (410EUR): Proyecto completo - todo incluido
# =============================================================================

MOTOS_PART_MAPPINGS = {
    # Elementos que SIEMPRE requieren T1 (Proyecto Completo)
    "T1_ONLY_ELEMENTS": [
        "SUBCHASIS",
        "HORQUILLA",
    ],

    # Elementos que requieren T3 (Proyecto Sencillo) como minimo
    "T3_ELEMENTS": [
        "SUSPENSION_DEL",
        "SUSPENSION_TRAS",
        "FRENADO_LATIGUILLOS",
        "CARENADO",
    ],

    # Elementos base para T4-T6 (sin proyecto)
    "T4_BASE_ELEMENTS": [
        "MATRICULA",
        "FILTRO",
        "ESCAPE",
        "DEPOSITO",
        "NEUMATICOS",
        "LLANTAS",
        "MANILLAR",
        "VELOCIMETRO",
        "CABALLETE",
        "ESPEJOS",
        "FARO_DELANTERO",
        "INTERMITENTES_DEL",
        "INTERMITENTES_TRAS",
        "PILOTO_FRENO",
        "LUZ_MATRICULA",
        "CATADIOPTRICO",
        "ANTINIEBLAS",
        "TIJAS",
        "MANDOS_AVANZADOS",
        "MANDOS_MANILLAR",
        "CLAUSOR",
        "STARTER",
        "ESTRIBERAS",
        "ASIENTO",
        "MALETAS",
        "GUARDABARROS_DEL",
        "GUARDABARROS_TRAS",
        "CARROCERIA",
        "ASIDEROS",
        "FRENADO_DISCOS",
        "FRENADO_PINZAS",
        "FRENADO_BOMBAS",
        "FRENADO_DEPOSITO",
    ],

    # Configuracion por tier
    "TIER_CONFIGS": {
        "T6": {
            "max_elements": 1,
            "includes_t4_elements": True,
            "notes": "Solo 1 elemento de la lista base",
        },
        "T5": {
            "max_elements": 2,
            "includes_t4_elements": True,
            "notes": "Hasta 2 elementos de la lista base",
        },
        "T4": {
            "min_elements": 3,
            "max_elements": None,
            "includes_t4_elements": True,
            "notes": "A partir de 3 elementos sin proyecto",
        },
        "T3": {
            "max_t3_elements": 1,
            "max_t4_elements": 2,
            "requires_project": True,
            "notes": "1 elemento T3 + hasta 2 de T4",
        },
        "T2": {
            "max_t3_elements": 2,
            "max_t4_elements": 4,
            "requires_project": True,
            "notes": "1-2 elementos T3 + hasta 4 de T4",
        },
        "T1": {
            "max_elements": None,
            "includes_all": True,
            "requires_project": True,
            "notes": "Proyecto completo - sin limite",
        },
    },
}


# =============================================================================
# ASEICARS-PROF: Element-Tier Mapping
# =============================================================================
# Structure from "2026 TARIFAS PROFESIONALES REGULARIZACION ELEMENTOS AUTOCARAVANAS":
#
# T6 (59EUR):  1 elemento (placas solares sin regulador, toldos, antenas)
# T5 (65EUR):  Hasta 3 elementos de T6 + placas con regulador en maletero
# T4 (135EUR): Sin limite T6 + ventanas/claraboyas/bola remolque sin proyecto
# T3 (180EUR): Todos T6 + 1 elemento (placas regulador interior, mobiliario, etc.)
# T2 (230EUR): Hasta 2 de T3 + todos T6 + 1 de (elevacion, suspension neumatica, etc.)
# T1 (270EUR): Proyecto completo - sin limite de T2-T6 + suspensiones complejas
# =============================================================================

ASEICARS_PROF_MAPPINGS = {
    # Elementos T6 (1 elemento sin proyecto)
    "T6_ELEMENTS": [
        "PLACA_200W",
        "TOLDO_LAT",
        "ANTENA_PAR",
    ],

    # Elementos T4 (regularizacion varios sin proyecto)
    "T4_ELEMENTS": [
        "CLARABOYA",
        "BOLA_REMOLQUE",
        "BOLA_SIN_MMR",
        "AIRE_ACONDI",
        "PORTABICIS",
    ],

    # Elementos T3 (proyecto basico)
    "T3_ELEMENTS": [
        "NEVERA_COMPRESOR",
        "DEPOSITO_AGUA",
        "ESC_MEC",
        "CIERRES_EXT",
    ],

    # Elementos T2 (proyecto medio)
    "T2_ELEMENTS": [
        "BOLA_CON_MMR",
        "BRAZO_PORTA",
        "PORTAMOTOS",
        "BACA_TECHO",
        "SUSP_NEUM",
        "SUSP_NEUM_EST",
        "SUSP_NEUM_FULL",
        "KIT_ESTAB",
        "FAROS_LA",
        "FAROS_LA_2F",
        "FAROS_LA_1D",
        "DEFENSAS_DEL",
    ],

    # Elementos T1 (proyecto completo)
    "T1_ELEMENTS": [
        "AUMENTO_MMTA",
        "GLP_INSTALACION",
        "GLP_KIT_BOMB",
        "GLP_DEPOSITO",
        "GLP_DUOCONTROL",
        "AUMENTO_PLAZAS",
    ],

    # Configuracion por tier
    "TIER_CONFIGS": {
        "T6": {
            "max_elements": 1,
            "element_list": "T6_ELEMENTS",
            "notes": "Solo 1 elemento (placas sin regulador, toldo, antena)",
        },
        "T5": {
            "max_elements": 3,
            "element_list": "T6_ELEMENTS",
            "notes": "Hasta 3 elementos de T6 + placas con regulador en maletero",
        },
        "T4": {
            "max_elements": None,
            "element_lists": ["T6_ELEMENTS", "T4_ELEMENTS"],
            "notes": "Sin limite T6 + elementos adicionales T4",
        },
        "T3": {
            "max_t3_elements": 1,
            "includes_t6": True,
            "requires_project": True,
            "notes": "Todos T6 + 1 elemento T3",
        },
        "T2": {
            "max_t3_elements": 2,
            "max_t2_elements": 1,
            "includes_t6": True,
            "requires_project": True,
            "notes": "Hasta 2 de T3 + todos T6 + 1 de T2",
        },
        "T1": {
            "max_elements": None,
            "includes_all": True,
            "requires_project": True,
            "notes": "Proyecto completo - sin limite",
        },
    },
}


def get_tier_mapping(category_slug: str) -> dict:
    """Get tier mapping configuration for a category."""
    mappings = {
        "motos-part": MOTOS_PART_MAPPINGS,
        "aseicars-prof": ASEICARS_PROF_MAPPINGS,
    }
    return mappings.get(category_slug, {})


def get_element_tier_level(category_slug: str, element_code: str) -> str | None:
    """
    Determine the minimum tier level for an element.
    
    Returns the tier code (T1, T2, etc.) or None if element not found.
    """
    mapping = get_tier_mapping(category_slug)
    if not mapping:
        return None

    if category_slug == "motos-part":
        if element_code in mapping.get("T1_ONLY_ELEMENTS", []):
            return "T1"
        if element_code in mapping.get("T3_ELEMENTS", []):
            return "T3"
        if element_code in mapping.get("T4_BASE_ELEMENTS", []):
            return "T6"  # Can be used in T6 (single element)
        return None

    elif category_slug == "aseicars-prof":
        if element_code in mapping.get("T1_ELEMENTS", []):
            return "T1"
        if element_code in mapping.get("T2_ELEMENTS", []):
            return "T2"
        if element_code in mapping.get("T3_ELEMENTS", []):
            return "T3"
        if element_code in mapping.get("T4_ELEMENTS", []):
            return "T4"
        if element_code in mapping.get("T6_ELEMENTS", []):
            return "T6"
        return None

    return None
