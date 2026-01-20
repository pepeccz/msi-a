"""
MSI Automotive - Vehicle Type Identification Tool.

Uses LLM knowledge to identify vehicle types from brand/model names.
Results are cached in Redis for performance (30 days TTL).
"""

import json
import logging
from typing import Any, Literal

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agent.services.token_tracking import record_token_usage
from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cache TTL: 30 days (vehicle types don't change)
VEHICLE_TYPE_CACHE_TTL = 30 * 24 * 60 * 60

# Valid vehicle categories matching VehicleCategory slugs
VehicleType = Literal[
    "moto", "tuning", "aseicars", "camper", "4x4", "importaciones", "desconocido"
]

# Map from vehicle type to category slug prefix
# Categories are further qualified by client type (e.g., motos-part, motos-prof)
VEHICLE_TYPE_TO_CATEGORY_SLUG = {
    "moto": "motos",
    "tuning": "tuning",
    "aseicars": "aseicars",
    "camper": "camper",
    "4x4": "4x4",
    "importaciones": "import",
}


@tool
async def identificar_tipo_vehiculo(marca: str, modelo: str) -> dict[str, Any]:
    """
    Identifica el tipo de vehiculo a partir de su marca y modelo.

    Usa esta herramienta cuando el usuario mencione un vehiculo especifico
    (como "Honda CBF600", "Mercedes Sprinter", "Hymer B-Klasse") y necesites
    determinar a que categoria pertenece para poder usar las herramientas
    de tarifas correctas.

    Args:
        marca: Marca del vehiculo (ej: "Honda", "Mercedes", "Hymer", "Yamaha")
        modelo: Modelo del vehiculo (ej: "CBF600", "Sprinter", "B-Klasse", "MT-07")

    Returns:
        Dict con:
        - tipo: Tipo identificado (moto, tuning, aseicars, camper, 4x4, importaciones, desconocido)
        - confianza: Nivel de confianza (alta, media, baja)
        - categoria_sugerida: Slug de categoria para usar en otras herramientas
        - descripcion: Breve descripcion del vehiculo
        - pedir_confirmacion: True si se debe confirmar con el usuario antes de proceder
    """
    settings = get_settings()
    redis = get_redis_client()

    # Normalize input
    marca_norm = marca.strip().title()
    modelo_norm = modelo.strip().upper()
    cache_key = f"vehicle_type:{marca_norm}:{modelo_norm}"

    # Try cache first
    try:
        cached = await redis.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for vehicle type: {marca_norm} {modelo_norm}")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Cache read failed: {e}")

    # Query LLM for vehicle classification
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0,  # Deterministic for classification
        max_tokens=200,
    )

    prompt = f"""Clasifica el siguiente vehiculo en UNA de estas categorias:
- moto: Motocicletas, ciclomotores, scooters, quads, triciclos
- tuning: Turismos (coches normales) con modificaciones
- aseicars: Autocaravanas (motorhomes, RVs con motor propio)
- camper: Caravanas, campers, furgonetas camperizadas
- 4x4: Todoterrenos, SUVs con modificaciones off-road
- importaciones: Vehiculos importados sin homologar en Espana
- desconocido: Si no puedes determinar el tipo con certeza

Vehiculo: {marca_norm} {modelo_norm}

Responde SOLO con un JSON valido (sin markdown, sin explicaciones):
{{"tipo": "categoria", "confianza": "alta|media|baja", "descripcion": "breve descripcion del vehiculo"}}
"""

    try:
        response = await llm.ainvoke(prompt)

        # Track token usage
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata:
            await record_token_usage(
                input_tokens=usage_metadata.get("input_tokens", 0),
                output_tokens=usage_metadata.get("output_tokens", 0),
            )

        content = response.content.strip()

        # Handle markdown code blocks if LLM adds them
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (``` markers)
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        data = json.loads(content)

        tipo = data.get("tipo", "desconocido")
        confianza = data.get("confianza", "baja")
        descripcion = data.get("descripcion", "")

        # Validate tipo is in our known types
        if tipo not in VEHICLE_TYPE_TO_CATEGORY_SLUG and tipo != "desconocido":
            logger.warning(f"LLM returned unknown tipo: {tipo}, treating as desconocido")
            tipo = "desconocido"
            confianza = "baja"

        # Map to category slug
        categoria_sugerida = VEHICLE_TYPE_TO_CATEGORY_SLUG.get(tipo)

        result = {
            "tipo": tipo,
            "confianza": confianza,
            "categoria_sugerida": categoria_sugerida,
            "descripcion": descripcion,
            "marca": marca_norm,
            "modelo": modelo_norm,
            "pedir_confirmacion": confianza in ["baja", "media"] or tipo == "desconocido",
        }

        # Cache result (even "desconocido" to avoid repeated queries)
        try:
            await redis.setex(cache_key, VEHICLE_TYPE_CACHE_TTL, json.dumps(result))
            logger.debug(f"Cached vehicle type for {marca_norm} {modelo_norm}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

        logger.info(
            f"Vehicle identified: {marca_norm} {modelo_norm} -> {tipo} ({confianza})",
            extra={
                "marca": marca_norm,
                "modelo": modelo_norm,
                "tipo": tipo,
                "confianza": confianza,
            },
        )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response for {marca_norm} {modelo_norm}: {e}")
        return {
            "tipo": "desconocido",
            "confianza": "baja",
            "categoria_sugerida": None,
            "descripcion": f"No se pudo clasificar {marca_norm} {modelo_norm}",
            "marca": marca_norm,
            "modelo": modelo_norm,
            "pedir_confirmacion": True,
        }
    except Exception as e:
        logger.error(
            f"Vehicle identification failed for {marca_norm} {modelo_norm}: {e}",
            exc_info=True,
        )
        return {
            "tipo": "desconocido",
            "confianza": "baja",
            "categoria_sugerida": None,
            "descripcion": f"Error al identificar {marca_norm} {modelo_norm}",
            "marca": marca_norm,
            "modelo": modelo_norm,
            "pedir_confirmacion": True,
        }


# Export tools list
VEHICLE_TOOLS = [identificar_tipo_vehiculo]


def get_vehicle_tools() -> list:
    """Get all vehicle identification tools."""
    return VEHICLE_TOOLS
