"""
MSI Automotive - Seed data for Element System (Hierarchical Tariffs).

This script populates the database with:
1. Element catalog (homologable elements) with parent/child hierarchy support
2. Element images (multiple per element with different types)
3. Tier element inclusions (references between tiers and elements)

Hierarchy support (v2):
- Elements can have parent_element_id for variants/sub-elements
- variant_type: Type of variant (mmr_option, installation_type, etc.)
- variant_code: Short code for the variant (SIN_MMR, CON_MMR, etc.)

Based on the PDF structure for "Autocaravanas Profesional" (aseicars-prof).

Run with: python -m database.seeds.elements_from_pdf_seed
"""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from database.connection import get_async_session
from database.models import (
    VehicleCategory,
    TariffTier,
    Element,
    ElementImage,
    TierElementInclusion,
    Warning,
)
from database.seeds.seed_utils import (
    deterministic_element_uuid,
    deterministic_element_image_uuid,
    deterministic_tier_inclusion_uuid,
    deterministic_tier_to_tier_uuid,
    deterministic_warning_uuid,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Category slug for this seed
CATEGORY_SLUG = "aseicars-prof"

# =============================================================================
# Element Definitions - Autocaravanas Profesional
# =============================================================================
# Based on PDF tariff structure for aseicars-prof category

ELEMENTS = [
    {
        "code": "ESC_MEC",
        "name": "Escalera mecánica trasera",
        "description": "Escalera retráctil de accionamiento hidráulico instalada en parte trasera del vehículo",
        "keywords": ["escalera", "escalera mecánica", "escalera trasera", "escalera retráctil", "escalerilla"],
        "aliases": ["peldaños", "acceso techo"],
        "sort_order": 10,
        "images": [
            {
                "title": "Vista trasera cerrada",
                "description": "Escalera en posición de transporte, cerrada",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Vista trasera abierta",
                "description": "Escalera completamente desplegada",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto con matrícula visible y escalera desplegada",
                "image_type": "required_document",
                "sort_order": 3,
            },
            {
                "title": "Placa del fabricante",
                "description": "Placa del fabricante con número de serie y especificaciones",
                "image_type": "required_document",
                "sort_order": 4,
            },
        ],
        "warnings": [
            {
                "code": "escalon_boletin",
                "message": "Escalones electricos requieren Boletin Electrico.",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "TOLDO_LAT",
        "name": "Toldo lateral",
        "description": "Toldo retráctil instalado en lateral del vehículo",
        "keywords": ["toldo", "toldo lateral", "toldo retráctil", "lona"],
        "aliases": ["tolva", "parasol lateral"],
        "sort_order": 20,
        "images": [
            {
                "title": "Toldo cerrado",
                "description": "Toldo recogido en su posición de transporte",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Toldo extendido",
                "description": "Toldo completamente desplegado",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Foto extensión completa",
                "description": "Toldo completamente extendido con soportes",
                "image_type": "required_document",
                "sort_order": 3,
            },
            {
                "title": "Placa identificativa",
                "description": "Placa del fabricante del toldo",
                "image_type": "required_document",
                "sort_order": 4,
            },
        ],
        "warnings": [
            {
                "code": "toldo_galibo",
                "message": "Especial atencion con luz de galibo. Medir nuevo ancho del vehiculo.",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "PLACA_200W",
        "name": "Placa solar >200W",
        "description": "Placa solar fotovoltaica de más de 200 vatios instalada en techo",
        "keywords": ["placa solar", "placa fotovoltaica", "solar", "panel solar", "200w"],
        "aliases": ["módulo solar", "panel"],
        "sort_order": 30,
        "images": [
            {
                "title": "Vista superior",
                "description": "Placa solar instalada en techo",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Detalle conexión",
                "description": "Detalle de la conexión eléctrica de la placa",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Foto con matrícula visible",
                "description": "Foto general del vehículo con placa visible y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
            },
            {
                "title": "Certificado de especificaciones",
                "description": "Especificaciones técnicas de la placa (vatios, fabricante, etc)",
                "image_type": "required_document",
                "sort_order": 4,
            },
        ],
        "warnings": [
            {
                "code": "placas_regulador_ubicacion",
                "message": "El regulador debe estar en interior de zona maletero o dentro de portones exteriores. Sujeto a boletin de baja tension.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "ANTENA_PAR",
        "name": "Antena parabólica",
        "description": "Antena parabólica para recepción de satélite",
        "keywords": ["antena", "antena parabólica", "parabólica", "satélite"],
        "aliases": ["dish", "receptor satélite"],
        "sort_order": 40,
        "images": [
            {
                "title": "Antena instalada",
                "description": "Antena parabólica instalada en techo",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Foto frontal",
                "description": "Foto frontal del vehículo con antena visible",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
        "warnings": [
            {
                "code": "antena_no_tv",
                "message": "No confundir antena parabolica con antenas normales de TV que no son reforma.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "PORTABICIS",
        "name": "Portabicis trasero",
        "description": "Portabicis montado en la parte trasera del vehículo",
        "keywords": ["portabicis", "portabike", "bicicletas", "bike rack"],
        "aliases": ["soportebicis", "rack bicicletas"],
        "sort_order": 50,
        "images": [
            {
                "title": "Portabicis vacío",
                "description": "Portabicis sin bicicletas",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Con bicicletas",
                "description": "Portabicis con bicicletas instaladas",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto trasera con matrícula",
                "description": "Foto trasera del vehículo con portabicis y matrícula visible",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "CLARABOYA",
        "name": "Claraboya adicional",
        "description": "Claraboya o ventana cenital adicional en techo",
        "keywords": ["claraboya", "ventana techo", "lucernario", "ventilación"],
        "aliases": ["skylight", "ventana cenital"],
        "sort_order": 60,
        "images": [
            {
                "title": "Claraboya cerrada",
                "description": "Claraboya en posición cerrada",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto interior",
                "description": "Foto del interior mostrando la claraboya",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto exterior",
                "description": "Foto exterior del techo con claraboya visible",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "BACA_TECHO",
        "name": "Baca portaequipajes",
        "description": "Baca metálica para portaequipajes en techo",
        "keywords": ["baca", "portaequipajes", "roof rack", "rack techo"],
        "aliases": ["jaula techo", "soporte techo"],
        "sort_order": 70,
        "images": [
            {
                "title": "Baca vacía",
                "description": "Baca sin carga",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Detalle montaje",
                "description": "Detalle de cómo está montada la baca",
                "image_type": "example",
                "sort_order": 2,
                            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general del vehículo con baca visible y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
                            },
        ],
    },
    {
        "code": "BOLA_REMOLQUE",
        "name": "Bola de remolque",
        "description": "Enganche de remolque tipo bola. Selecciona la variante según si aumenta o no la MMR.",
        "keywords": ["bola remolque", "enganche", "bola", "remolque", "mmr"],
        "aliases": ["coupling", "tow ball"],
        "sort_order": 80,
        "is_base": True,  # Elemento base con variantes
        "images": [
            {
                "title": "Bola remolque",
                "description": "Bola de remolque instalada",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
        "warnings": [
            {
                "code": "bola_remolque_proyecto",
                "message": "Bola de remolque con extensores de chasis o con proyecto requiere T2.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "NEVERA_COMPRESOR",
        "name": "Nevera de compresor",
        "description": "Nevera portátil con compresor de corriente continua",
        "keywords": ["nevera", "frigorífico", "compresor", "congelador"],
        "aliases": ["cooling box", "fridge"],
        "sort_order": 90,
        "images": [
            {
                "title": "Nevera instalada",
                "description": "Nevera de compresor instalada en interior",
                "image_type": "example",
                "sort_order": 1,
                            },
            {
                "title": "Foto interior",
                "description": "Foto del interior mostrando la nevera",
                "image_type": "required_document",
                "sort_order": 2,
                            },
        ],
    },
    {
        "code": "DEPOSITO_AGUA",
        "name": "Depósito de agua adicional",
        "description": "Depósito de agua dulce adicional instalado en vehículo",
        "keywords": ["depósito agua", "tanque agua", "agua dulce", "depósito"],
        "aliases": ["water tank", "fresh water"],
        "sort_order": 100,
        "images": [
            {
                "title": "Depósito instalado",
                "description": "Depósito de agua adicional en exterior",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Placa identificativa",
                "description": "Placa con especificaciones del depósito",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    # =========================================================================
    # NUEVOS ELEMENTOS BASE - Carpetas con imágenes sin representación previa
    # =========================================================================
    {
        "code": "AIRE_ACONDI",
        "name": "Aire acondicionado",
        "description": "Sistema de aire acondicionado instalado en el vehículo",
        "keywords": ["aire acondicionado", "ac", "climatizador", "clima", "aire"],
        "aliases": ["air conditioning", "climatización"],
        "sort_order": 110,
        "images": [
            {
                "title": "Unidad exterior",
                "description": "Unidad de aire acondicionado instalada en techo",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Panel de control",
                "description": "Panel de control interior del aire acondicionado",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general del vehículo con AC visible y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
            },
        ],
        "warnings": [
            {
                "code": "aire_boletin",
                "message": "Aire acondicionado sujeto a boletin electrico.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "PORTAMOTOS",
        "name": "Portamotos / Soporte motos",
        "description": "Soporte trasero para transportar motos. Incluye cálculos de carga.",
        "keywords": ["portamotos", "soporte motos", "moto", "motocicleta", "porta moto"],
        "aliases": ["motorcycle carrier", "bike rack moto"],
        "sort_order": 120,
        "images": [
            {
                "title": "Portamotos instalado",
                "description": "Soporte portamotos instalado en trasera",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Cálculos positivos",
                "description": "Ejemplo de cálculos con resultado positivo",
                "image_type": "calculation",
                "sort_order": 2,
            },
            {
                "title": "Cálculos negativos",
                "description": "Ejemplo de cálculos con resultado negativo (no viable)",
                "image_type": "calculation",
                "sort_order": 3,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto trasera con portamotos y matrícula visible",
                "image_type": "required_document",
                "sort_order": 4,
            },
        ],
        "warnings": [
            {
                "code": "portamotos_soportes",
                "message": "Solo se legaliza los soportes, no el portamotos en si. Necesario reparto de cargas.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "SUSP_NEUM",
        "name": "Suspensión neumática",
        "description": "Sistema de suspensión neumática. Selecciona el tipo de instalación.",
        "keywords": ["suspensión neumática", "neumática", "air suspension", "suspensión aire"],
        "aliases": ["air ride", "suspensión"],
        "sort_order": 130,
        "is_base": True,  # Elemento base con variantes
        "images": [
            {
                "title": "Sistema suspensión",
                "description": "Vista general del sistema de suspensión neumática",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
        "warnings": [
            {
                "code": "susp_neum_proyecto",
                "message": "Suspension neumatica requiere proyecto medio (T2).",
                "severity": "info",
            },
        ],
    },
    {
        "code": "KIT_ESTAB",
        "name": "Kit elevación / Patas estabilizadoras",
        "description": "Kit de elevación o patas estabilizadoras hidráulicas",
        "keywords": ["kit elevación", "patas estabilizadoras", "estabilizadoras", "nivelación", "patas"],
        "aliases": ["leveling jacks", "stabilizers"],
        "sort_order": 140,
        "images": [
            {
                "title": "Patas desplegadas",
                "description": "Sistema de patas estabilizadoras en funcionamiento",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Panel de control",
                "description": "Panel de control del sistema de nivelación",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Foto con matrícula",
                "description": "Foto general del vehículo con patas visibles y matrícula",
                "image_type": "required_document",
                "sort_order": 3,
            },
        ],
        "warnings": [
            {
                "code": "kit_elevacion_mando",
                "message": "Kit de elevacion hidraulica/electrica: solo con mando interior fijo.",
                "severity": "info",
            },
        ],
    },
    {
        "code": "AUMENTO_MMTA",
        "name": "Aumento de MMTA",
        "description": "Aumento de la Masa Máxima Técnica Autorizada del vehículo",
        "keywords": ["aumento mmta", "mmta", "masa máxima", "incremento peso", "aumento peso"],
        "aliases": ["weight increase", "gross weight"],
        "sort_order": 150,
        "images": [
            {
                "title": "Documentación MMTA",
                "description": "Ejemplo de documentación para aumento de MMTA",
                "image_type": "required_document",
                "sort_order": 1,
            },
            {
                "title": "Ficha técnica",
                "description": "Ficha técnica con MMTA modificada",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
        "warnings": [
            {
                "code": "mmta_sin_ensayo",
                "message": "Aumento de MMTA sin ensayo de frenada: +300 EUR (previo consulta).",
                "severity": "info",
            },
            {
                "code": "mmta_con_ensayo",
                "message": "Aumento de MMTA con ensayo de frenada: +500 EUR (previo consulta).",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "GLP_INSTALACION",
        "name": "Instalación GLP / Gas",
        "description": "Instalación de sistema de gas GLP. Selecciona el tipo de instalación.",
        "keywords": ["glp", "gas", "instalación gas", "bombona", "depósito glp", "autogas"],
        "aliases": ["lpg", "propane"],
        "sort_order": 160,
        "is_base": True,  # Elemento base con variantes
        "images": [
            {
                "title": "Sistema GLP",
                "description": "Vista general de instalación GLP",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
        "warnings": [
            {
                "code": "glp_certificacion",
                "message": "Instalaciones de GLP requieren certificado de instalacion/revision de gas (+65 EUR).",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "AUMENTO_PLAZAS",
        "name": "Aumento de plazas",
        "description": "Aumento del número de plazas homologadas en el vehículo",
        "keywords": ["aumento plazas", "más plazas", "plazas adicionales", "asientos"],
        "aliases": ["seat increase", "additional seats"],
        "sort_order": 170,
        "images": [
            {
                "title": "Configuración asientos",
                "description": "Disposición de asientos adicionales",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación plazas",
                "description": "Documentación requerida para aumento de plazas",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
        "warnings": [
            {
                "code": "aumento_plazas_consulta",
                "message": "Aumento de plazas requiere consulta previa (+115 EUR adicionales).",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "CIERRES_EXT",
        "name": "Cierres exteriores",
        "description": "Cierres y cerraduras exteriores del vehículo",
        "keywords": ["cierres exteriores", "cerraduras", "cierres", "locks"],
        "aliases": ["external locks", "door locks"],
        "sort_order": 180,
        "images": [
            {
                "title": "Cierres instalados",
                "description": "Vista de cierres exteriores instalados",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
        "warnings": [
            {
                "code": "cerraduras_apertura",
                "message": "La cerradura de acceso a vivienda ha de tener apertura desde el interior.",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "FAROS_LA",
        "name": "Faros de largo alcance",
        "description": "Faros auxiliares de largo alcance. Selecciona la configuración.",
        "keywords": ["faros largo alcance", "faros auxiliares", "faros", "luces auxiliares"],
        "aliases": ["spotlights", "driving lights"],
        "sort_order": 190,
        "is_base": True,  # Elemento base con variantes
        "images": [
            {
                "title": "Faros instalados",
                "description": "Faros de largo alcance instalados",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
    },
    {
        "code": "DEFENSAS_DEL",
        "name": "Defensas delanteras",
        "description": "Defensa o bullbar delantero instalado en el vehículo",
        "keywords": ["defensas delanteras", "bullbar", "defensa", "parachoques reforzado"],
        "aliases": ["bull bar", "front guard"],
        "sort_order": 200,
        "images": [
            {
                "title": "Defensa instalada",
                "description": "Defensa delantera instalada en vehículo",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Foto frontal con matrícula",
                "description": "Foto frontal del vehículo con defensa y matrícula visible",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    # =========================================================================
    # VARIANTES DE BOLA_REMOLQUE (parent_code: BOLA_REMOLQUE)
    # =========================================================================
    {
        "code": "BOLA_SIN_MMR",
        "name": "Bola de remolque SIN aumento MMR",
        "description": "Enganche de remolque sin aumento de la Masa Máxima Remolcable",
        "keywords": ["bola sin mmr", "enganche sin mmr", "bola remolque básica"],
        "aliases": [],
        "sort_order": 81,
        "parent_code": "BOLA_REMOLQUE",
        "variant_type": "mmr_option",
        "variant_code": "SIN_MMR",
        "images": [
            {
                "title": "Bola instalada",
                "description": "Bola de remolque instalada sin aumento MMR",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación",
                "description": "Documentación requerida para bola sin MMR",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
        "warnings": [
            {
                "code": "bola_sin_mmr_warning",
                "message": "Bola sin MMR: NO apta para remolcar, solo portaequipajes. Necesario reparto de cargas.",
                "severity": "warning",
            },
        ],
    },
    {
        "code": "BOLA_CON_MMR",
        "name": "Bola de remolque CON aumento MMR",
        "description": "Enganche de remolque con aumento de la Masa Máxima Remolcable. Requiere documentación adicional.",
        "keywords": ["bola con mmr", "enganche con mmr", "aumento mmr", "bola remolque mmr"],
        "aliases": [],
        "sort_order": 82,
        "parent_code": "BOLA_REMOLQUE",
        "variant_type": "mmr_option",
        "variant_code": "CON_MMR",
        "images": [
            {
                "title": "Paso 1 - Bola instalada",
                "description": "Primer paso: bola de remolque instalada",
                "image_type": "step",
                "sort_order": 1,
            },
            {
                "title": "Paso 2 - Carga positiva",
                "description": "Segundo paso: verificación de carga positiva",
                "image_type": "step",
                "sort_order": 2,
            },
            {
                "title": "Paso 3 - Ficha nueva",
                "description": "Tercer paso: obtención de ficha técnica nueva",
                "image_type": "step",
                "sort_order": 3,
            },
            {
                "title": "Paso 4 - Ficha antigua",
                "description": "Cuarto paso: comparación con ficha antigua",
                "image_type": "step",
                "sort_order": 4,
            },
        ],
    },
    {
        "code": "BRAZO_PORTA",
        "name": "Brazo portaequipajes",
        "description": "Brazo portaequipajes asociado a bola de remolque sin MMR",
        "keywords": ["brazo portaequipajes", "portaequipajes bola", "brazo"],
        "aliases": [],
        "sort_order": 811,
        "parent_code": "BOLA_SIN_MMR",
        "variant_type": "accessory",
        "variant_code": "BRAZO",
        "images": [
            {
                "title": "Brazo instalado",
                "description": "Brazo portaequipajes instalado en bola de remolque",
                "image_type": "example",
                "sort_order": 1,
            },
        ],
    },
    # =========================================================================
    # VARIANTES DE SUSP_NEUM (parent_code: SUSP_NEUM)
    # =========================================================================
    {
        "code": "SUSP_NEUM_EST",
        "name": "Suspensión neumática estándar",
        "description": "Suspensión neumática con configuración estándar",
        "keywords": ["suspensión estándar", "neumática estándar", "suspensión básica"],
        "aliases": [],
        "sort_order": 131,
        "parent_code": "SUSP_NEUM",
        "variant_type": "suspension_type",
        "variant_code": "ESTANDAR",
        "images": [
            {
                "title": "Configuración estándar",
                "description": "Sistema de suspensión neumática estándar",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación",
                "description": "Documentación requerida para suspensión estándar",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    {
        "code": "SUSP_NEUM_FULL",
        "name": "Suspensión neumática FULL AIR",
        "description": "Suspensión neumática completa (FULL AIR) en todos los ejes",
        "keywords": ["suspensión full air", "full air", "neumática completa", "suspensión total"],
        "aliases": [],
        "sort_order": 132,
        "parent_code": "SUSP_NEUM",
        "variant_type": "suspension_type",
        "variant_code": "FULL_AIR",
        "images": [
            {
                "title": "Sistema FULL AIR",
                "description": "Sistema de suspensión FULL AIR completo",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Panel de control",
                "description": "Panel de control del sistema FULL AIR",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Documentación FULL AIR",
                "description": "Documentación específica para sistema FULL AIR",
                "image_type": "required_document",
                "sort_order": 3,
            },
        ],
    },
    # =========================================================================
    # VARIANTES DE GLP_INSTALACION (parent_code: GLP_INSTALACION)
    # =========================================================================
    {
        "code": "GLP_KIT_BOMB",
        "name": "Kit bombona GLP",
        "description": "Instalación de kit de bombona de GLP",
        "keywords": ["kit bombona", "bombona glp", "kit glp bombona"],
        "aliases": [],
        "sort_order": 161,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "KIT_BOMBONA",
        "images": [
            {
                "title": "Kit bombona instalado",
                "description": "Kit de bombona GLP instalado",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación bombona",
                "description": "Documentación requerida para kit bombona",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    {
        "code": "GLP_DEPOSITO",
        "name": "Depósito GLP",
        "description": "Instalación de depósito fijo de GLP",
        "keywords": ["depósito glp", "tanque glp", "depósito gas"],
        "aliases": [],
        "sort_order": 162,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "DEPOSITO",
        "images": [
            {
                "title": "Depósito instalado",
                "description": "Depósito fijo de GLP instalado",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Boca de carga",
                "description": "Boca de carga del depósito GLP",
                "image_type": "example",
                "sort_order": 2,
            },
            {
                "title": "Documentación depósito",
                "description": "Documentación requerida para depósito GLP",
                "image_type": "required_document",
                "sort_order": 3,
            },
        ],
    },
    {
        "code": "GLP_DUOCONTROL",
        "name": "Duocontrol GLP",
        "description": "Sistema Duocontrol para gestión de GLP",
        "keywords": ["duocontrol", "duocontrol glp", "control gas"],
        "aliases": [],
        "sort_order": 163,
        "parent_code": "GLP_INSTALACION",
        "variant_type": "installation_type",
        "variant_code": "DUOCONTROL",
        "images": [
            {
                "title": "Sistema Duocontrol",
                "description": "Sistema Duocontrol instalado",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación Duocontrol",
                "description": "Documentación requerida para Duocontrol",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    # =========================================================================
    # VARIANTES DE FAROS_LA (parent_code: FAROS_LA)
    # =========================================================================
    {
        "code": "FAROS_LA_2F",
        "name": "2 Faros de largo alcance",
        "description": "Instalación de 2 faros de largo alcance independientes",
        "keywords": ["2 faros", "dos faros", "faros independientes"],
        "aliases": [],
        "sort_order": 191,
        "parent_code": "FAROS_LA",
        "variant_type": "installation_config",
        "variant_code": "2FAROS",
        "images": [
            {
                "title": "2 faros instalados",
                "description": "Dos faros de largo alcance instalados",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación 2 faros",
                "description": "Documentación para instalación de 2 faros",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
    {
        "code": "FAROS_LA_1D",
        "name": "1 Faro doble largo alcance",
        "description": "Instalación de 1 faro doble (barra LED) de largo alcance",
        "keywords": ["faro doble", "barra led", "faro único doble"],
        "aliases": [],
        "sort_order": 192,
        "parent_code": "FAROS_LA",
        "variant_type": "installation_config",
        "variant_code": "1DOBLE",
        "images": [
            {
                "title": "Faro doble instalado",
                "description": "Faro doble de largo alcance instalado",
                "image_type": "example",
                "sort_order": 1,
            },
            {
                "title": "Documentación faro doble",
                "description": "Documentación para instalación de faro doble",
                "image_type": "required_document",
                "sort_order": 2,
            },
        ],
    },
]

# =============================================================================
# Placeholder Image URLs (replace with real URLs later)
# =============================================================================

def get_placeholder_image_url(element_code: str, image_title: str) -> str:
    """Generate a placeholder image URL."""
    # In production, these would be real S3/CDN URLs
    safe_title = image_title.lower().replace(" ", "_")
    return f"https://via.placeholder.com/400x300?text={element_code}_{safe_title}"


async def seed_elements():
    """Seed element system data."""
    logger.info("=" * 80)
    logger.info("Starting Element System Seed")
    logger.info("=" * 80)

    async with get_async_session() as session:
        # Step 1: Get or verify category exists
        logger.info("\n[STEP 1] Getting category: aseicars-prof")
        category_result = await session.execute(
            select(VehicleCategory)
            .where(VehicleCategory.slug == "aseicars-prof")
            .where(VehicleCategory.is_active == True)
        )
        category = category_result.scalar()

        if not category:
            logger.error("Category 'aseicars-prof' not found. Run aseicars-prof_seed.py first!")
            return False

        logger.info(f"✓ Found category: {category.name} (ID: {category.id})")

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

        logger.info(f"✓ Found {len(tiers)} tiers:")
        for code, tier in tiers.items():
            logger.info(f"  - {code}: {tier.name} ({tier.price}€)")

        # Step 3: Upsert elements (create or update with deterministic UUIDs)
        # NOTA: Procesamos en dos pasadas para resolver parent_element_id
        logger.info("\n[STEP 3] Upserting elements and their warnings")
        created_elements = {}
        elements_with_parent = []  # Para segunda pasada
        created_count = 0
        updated_count = 0
        warnings_created = 0
        warnings_updated = 0

        for elem_data in ELEMENTS:
            # Generar UUID determinístico basado en categoría y código
            element_id = deterministic_element_uuid("aseicars-prof", elem_data["code"])

            # Verificar si ya existe por UUID determinístico
            existing_element = await session.get(Element, element_id)

            if existing_element:
                # UPDATE: Actualizar campos de seed (preservar relaciones del usuario)
                existing_element.name = elem_data["name"]
                existing_element.description = elem_data["description"]
                existing_element.keywords = elem_data["keywords"]
                existing_element.aliases = elem_data["aliases"]
                existing_element.sort_order = elem_data["sort_order"]
                existing_element.is_active = True
                # Actualizar campos de variante si existen
                existing_element.variant_type = elem_data.get("variant_type")
                existing_element.variant_code = elem_data.get("variant_code")
                created_elements[elem_data["code"]] = existing_element
                element = existing_element
                updated_count += 1
                # Guardar para segunda pasada si tiene parent_code
                if "parent_code" in elem_data:
                    elements_with_parent.append((elem_data["code"], elem_data["parent_code"]))
                logger.info(f"  ~ {elem_data['code']}: Updated")
            else:
                # INSERT: Crear con UUID determinístico
                element = Element(
                    id=element_id,
                    category_id=category.id,
                    code=elem_data["code"],
                    name=elem_data["name"],
                    description=elem_data["description"],
                    keywords=elem_data["keywords"],
                    aliases=elem_data["aliases"],
                    is_active=True,
                    sort_order=elem_data["sort_order"],
                    # Campos de variante
                    variant_type=elem_data.get("variant_type"),
                    variant_code=elem_data.get("variant_code"),
                    # parent_element_id se resuelve en segunda pasada
                )
                session.add(element)
                await session.flush()

                # Crear imágenes para este elemento con UUIDs determinísticos
                for idx, img_data in enumerate(elem_data.get("images", [])):
                    image_id = deterministic_element_image_uuid(
                        "aseicars-prof",
                        elem_data["code"],
                        f"img_{idx + 1}"
                    )

                    # Verificar si la imagen ya existe
                    existing_img = await session.get(ElementImage, image_id)
                    if not existing_img:
                        image = ElementImage(
                            id=image_id,
                            element_id=element.id,
                            image_url=get_placeholder_image_url(
                                elem_data["code"],
                                img_data["title"]
                            ),
                            title=img_data["title"],
                            description=img_data["description"],
                            image_type=img_data["image_type"],
                            sort_order=img_data["sort_order"],
                        )
                        session.add(image)

                created_elements[elem_data["code"]] = element
                created_count += 1
                # Guardar para segunda pasada si tiene parent_code
                if "parent_code" in elem_data:
                    elements_with_parent.append((elem_data["code"], elem_data["parent_code"]))
                logger.info(f"  + {elem_data['code']}: Created with {len(elem_data.get('images', []))} images")

            # Upsert inline warnings for this element
            for warn_data in elem_data.get("warnings", []):
                warning_id = deterministic_warning_uuid("aseicars-prof", warn_data["code"])
                existing_warning = await session.get(Warning, warning_id)

                if existing_warning:
                    existing_warning.message = warn_data["message"]
                    existing_warning.severity = warn_data.get("severity", "warning")
                    existing_warning.element_id = element.id
                    existing_warning.category_id = None
                    existing_warning.trigger_conditions = warn_data.get("trigger_conditions")
                    warnings_updated += 1
                else:
                    warning = Warning(
                        id=warning_id,
                        code=warn_data["code"],
                        message=warn_data["message"],
                        severity=warn_data.get("severity", "warning"),
                        element_id=element.id,
                        category_id=None,
                        trigger_conditions=warn_data.get("trigger_conditions"),
                    )
                    session.add(warning)
                    warnings_created += 1

        await session.flush()
        logger.info(f"  Elements: {created_count} created, {updated_count} updated")
        logger.info(f"  Warnings: {warnings_created} created, {warnings_updated} updated")

        # Step 3b: Segunda pasada - Resolver parent_element_id
        if elements_with_parent:
            logger.info("\n[STEP 3b] Resolving parent_element_id for variants")
            for child_code, parent_code in elements_with_parent:
                child_element = created_elements.get(child_code)
                parent_element = created_elements.get(parent_code)
                if child_element and parent_element:
                    child_element.parent_element_id = parent_element.id
                    logger.info(f"  → {child_code} -> parent: {parent_code}")
                else:
                    logger.warning(f"  ⚠ Could not resolve parent for {child_code} (parent: {parent_code})")
            await session.flush()
            logger.info(f"  Resolved {len(elements_with_parent)} parent relationships")

        # Step 4: Upsert tier element inclusions based on PDF structure
        # NOTA: Ya no borramos, verificamos existencia antes de crear
        logger.info("\n[STEP 4] Upserting tier element inclusions")
        logger.info("  According to PDF structure:")
        inclusions_created = 0
        inclusions_skipped = 0

        async def ensure_inclusion(tier_code, element_code=None, included_tier_code=None,
                                   max_qty=None, notes=None):
            """Crea o actualiza inclusión con UUID determinístico."""
            nonlocal inclusions_created, inclusions_skipped

            tier_id = tiers[tier_code].id

            if element_code:
                # Tier-element inclusion
                element_id = created_elements[element_code].id
                inc_id = deterministic_tier_inclusion_uuid(CATEGORY_SLUG, tier_code, element_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.element_id = element_id
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        element_id=element_id,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True
            elif included_tier_code:
                # Tier-to-tier inclusion
                included_tier_id = tiers[included_tier_code].id
                inc_id = deterministic_tier_to_tier_uuid(CATEGORY_SLUG, tier_code, included_tier_code)

                existing = await session.get(TierElementInclusion, inc_id)
                if existing:
                    # Update existing
                    existing.tier_id = tier_id
                    existing.included_tier_id = included_tier_id
                    existing.max_quantity = max_qty
                    existing.notes = notes
                    inclusions_skipped += 1
                    return False
                else:
                    inc = TierElementInclusion(
                        id=inc_id,
                        tier_id=tier_id,
                        included_tier_id=included_tier_id,
                        max_quantity=max_qty,
                        notes=notes,
                    )
                    session.add(inc)
                    inclusions_created += 1
                    return True

            return False

        # T6: Contains ANTENA_PAR, PORTABICIS (max 1 total)
        if "T6" in tiers:
            logger.info("  T6 (59€): ANTENA_PAR, PORTABICIS (max 1 each)")
            for code in ["ANTENA_PAR", "PORTABICIS"]:
                if code in created_elements:
                    await ensure_inclusion(
                        tier_code="T6",
                        element_code=code,
                        max_qty=None,
                        notes=f"T6 includes {code}",
                    )

        # T3: ESC_MEC (max 1), TOLDO_LAT (max 1), PLACA_200W (max 1), + unlimited T6
        if "T3" in tiers:
            logger.info("  T3 (180€): ESC_MEC, TOLDO_LAT, PLACA_200W (max 1 each) + T6 unlimited")
            for code, max_qty in [("ESC_MEC", 1), ("TOLDO_LAT", 1), ("PLACA_200W", 1)]:
                if code in created_elements:
                    await ensure_inclusion(
                        tier_code="T3",
                        element_code=code,
                        max_qty=max_qty,
                        notes=f"T3 includes up to {max_qty} {code}",
                    )

            # T3 includes all of T6
            await ensure_inclusion(
                tier_code="T3",
                included_tier_code="T6",
                max_qty=None,
                notes="T3 includes all elements of T6 unlimited",
            )

        # T2: Up to 2 elements from T3 + unlimited T6
        if "T2" in tiers:
            logger.info("  T2 (230€): Up to 2 elements from T3 + T6 unlimited")
            await ensure_inclusion(
                tier_code="T2",
                included_tier_code="T3",
                max_qty=2,
                notes="T2 includes up to 2 elements from T3",
            )

            # T2 also includes T6 directly
            await ensure_inclusion(
                tier_code="T2",
                included_tier_code="T6",
                max_qty=None,
                notes="T2 includes all elements of T6 unlimited",
            )

        # T1: Unlimited everything (includes T2, T3, T4, T5, T6)
        if "T1" in tiers:
            logger.info("  T1 (270€): Unlimited everything (includes T2, T3, T4, T5, T6)")
            for ref_tier_code in ["T2", "T3", "T4", "T5", "T6"]:
                if ref_tier_code in tiers:
                    await ensure_inclusion(
                        tier_code="T1",
                        included_tier_code=ref_tier_code,
                        max_qty=None,
                        notes=f"T1 includes all elements of {ref_tier_code} unlimited",
                    )

        logger.info(f"  Tier inclusions: {inclusions_created} created, {inclusions_skipped} already existed")

        # Step 5: Commit all changes
        logger.info("\n[STEP 5] Committing changes to database")
        try:
            await session.commit()
            logger.info("✓ Committed successfully")
        except Exception as e:
            logger.error(f"✗ Commit failed: {e}")
            await session.rollback()
            return False

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✓ SEED COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info(f"Created {len(created_elements)} elements")
    logger.info("Configured tier inclusions according to PDF structure")
    logger.info("\nNext steps:")
    logger.info("1. Verify in admin panel: /elementos")
    logger.info("2. Test element matching: /api/admin/elements")
    logger.info("3. Test tier resolution: /api/admin/tariff-tiers/{tier_id}/resolved-elements")
    logger.info("4. Run tests: pytest tests/test_element_system.py")

    return True


async def main():
    """Main entry point."""
    try:
        success = await seed_elements()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
