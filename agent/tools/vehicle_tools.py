"""
MSI Automotive - Vehicle Type Identification Tool.

Uses LLM knowledge to identify vehicle types from brand/model names.
Implements hybrid architecture: Ollama local (primary) + OpenRouter (fallback).
Results are cached in Redis for performance (30 days TTL).
"""

import json
import logging
import time
from typing import Any, Literal

import httpx
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agent.services.token_tracking import record_token_usage
from agent.utils.errors import ErrorCategory, handle_tool_errors
from agent.utils.tool_helpers import tool_error_response
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

# Classification prompt template
CLASSIFICATION_PROMPT = """Clasifica el siguiente vehiculo en UNA de estas categorias:
- moto: Motocicletas, ciclomotores, scooters, quads, triciclos
- tuning: Turismos (coches normales) con modificaciones
- aseicars: Autocaravanas (motorhomes, RVs con motor propio)
- camper: Caravanas, campers, furgonetas camperizadas
- 4x4: Todoterrenos, SUVs con modificaciones off-road
- importaciones: Vehiculos importados sin homologar en Espana
- desconocido: Si no puedes determinar el tipo con certeza

Vehiculo: {marca} {modelo}

Responde SOLO con un JSON valido (sin markdown, sin explicaciones):
{{"tipo": "categoria", "confianza": "alta|media|baja", "descripcion": "breve descripcion del vehiculo"}}
"""


async def _resolve_full_category_slug(
    category_prefix: str,
    client_type: str,
) -> str | None:
    """
    Resolve a category prefix + client_type into a full category slug.
    
    Tries in order:
    1. "{prefix}-part" or "{prefix}-prof" (based on client_type)
    2. "{prefix}" alone (for categories without client_type suffix)
    3. Opposite suffix as last resort
    4. None if nothing found in DB
    
    Args:
        category_prefix: Category prefix (e.g., "motos", "aseicars")
        client_type: Client type ("particular" or "professional")
    
    Returns:
        Full category slug or None if not found
    """
    from agent.tools.element_tools import get_or_fetch_category_id
    
    suffix = "part" if client_type == "particular" else "prof"
    
    # Try with suffix first
    full_slug = f"{category_prefix}-{suffix}"
    category_id = await get_or_fetch_category_id(full_slug)
    if category_id:
        return full_slug
    
    # Try without suffix (some categories don't have -part/-prof)
    category_id = await get_or_fetch_category_id(category_prefix)
    if category_id:
        return category_prefix
    
    # Try opposite suffix as last resort
    opposite_suffix = "prof" if suffix == "part" else "part"
    opposite_slug = f"{category_prefix}-{opposite_suffix}"
    category_id = await get_or_fetch_category_id(opposite_slug)
    if category_id:
        logger.warning(
            "category_slug_fallback_opposite",
            extra={
                "prefix": category_prefix,
                "client_type": client_type,
                "expected": full_slug,
                "used": opposite_slug,
            },
        )
        return opposite_slug
    
    return None


async def _classify_with_ollama(marca: str, modelo: str, settings: Any) -> dict | None:
    """
    Classify vehicle using local Ollama model (Tier 1 - fast).
    
    Args:
        marca: Vehicle brand (normalized)
        modelo: Vehicle model (normalized)
        settings: Application settings
        
    Returns:
        Classification dict or None if failed (Ollama not available or error)
    """
    prompt = CLASSIFICATION_PROMPT.format(marca=marca, modelo=modelo)
    
    try:
        # Use shorter timeout to quickly detect Ollama unavailability
        async with httpx.AsyncClient(timeout=5.0) as client:
            start_time = time.time()
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": "qwen2.5:3b",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
            
            response.raise_for_status()
            latency_ms = int((time.time() - start_time) * 1000)
            
            response_data = response.json()
            content = response_data["message"]["content"].strip()
            
            # Track token usage from Ollama response (prompt_eval_count / eval_count)
            # These tokens are $0 cost but important for accurate request counting.
            input_tokens = response_data.get("prompt_eval_count") or 0
            output_tokens = response_data.get("eval_count") or 0
            if input_tokens > 0 or output_tokens > 0:
                await record_token_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            
            logger.debug(
                f"Ollama classification completed in {latency_ms}ms",
                extra={
                    "model": "qwen2.5:3b",
                    "latency_ms": latency_ms,
                    "provider": "ollama"
                }
            )
            
            return _parse_classification_response(content)
            
    except httpx.ConnectError:
        logger.debug("Ollama not available (connection refused) - using fallback")
        return None
    except httpx.TimeoutException:
        logger.debug("Ollama timed out - using fallback")
        return None
    except httpx.HTTPStatusError as e:
        logger.debug(f"Ollama HTTP error {e.response.status_code} - using fallback")
        return None
    except Exception as e:
        logger.debug(f"Ollama classification failed: {e} - using fallback")
        return None


async def _classify_with_openrouter(marca: str, modelo: str, settings: Any) -> dict | None:
    """
    Classify vehicle using OpenRouter cloud model (fallback).
    
    Args:
        marca: Vehicle brand (normalized)
        modelo: Vehicle model (normalized)
        settings: Application settings
        
    Returns:
        Classification dict or None if failed
    """
    prompt = CLASSIFICATION_PROMPT.format(marca=marca, modelo=modelo)
    
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_tokens=200,
        request_timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )
    
    start_time = time.time()
    try:
        response = await llm.ainvoke(prompt)
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Track token usage for cloud calls
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata:
            await record_token_usage(
                input_tokens=usage_metadata.get("input_tokens", 0),
                output_tokens=usage_metadata.get("output_tokens", 0),
            )
        
        logger.debug(
            f"OpenRouter classification completed in {latency_ms}ms",
            extra={
                "model": settings.LLM_MODEL,
                "latency_ms": latency_ms,
                "provider": "openrouter"
            }
        )
        
        return _parse_classification_response(response.content.strip())
        
    except Exception as e:
        logger.warning(f"OpenRouter classification failed: {e}")
        return None


def _parse_classification_response(content: str) -> dict | None:
    """
    Parse LLM response to extract classification data.
    
    Handles markdown code blocks if present.
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Parsed dict with tipo, confianza, descripcion or None
    """
    try:
        # Handle markdown code blocks if LLM adds them
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        data = json.loads(content)
        
        tipo = data.get("tipo", "desconocido")
        confianza = data.get("confianza", "baja")
        descripcion = data.get("descripcion", "")
        
        # Validate tipo is in known types
        if tipo not in VEHICLE_TYPE_TO_CATEGORY_SLUG and tipo != "desconocido":
            logger.warning(f"LLM returned unknown tipo: {tipo}, treating as desconocido")
            tipo = "desconocido"
            confianza = "baja"
        
        return {
            "tipo": tipo,
            "confianza": confianza,
            "descripcion": descripcion,
        }
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return None


@tool
@handle_tool_errors(
    error_category=ErrorCategory.LLM_ERROR,
    error_code="VEHICLE_CLASSIFICATION_FAILED",
    user_message="Lo siento, no pude identificar el tipo de vehículo. ¿Podrías confirmarme qué tipo de vehículo tienes?",
)
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
        - success: bool
        - message: str (user-facing message)
        - data: dict with tipo, confianza, categoria_sugerida, descripcion, pedir_confirmacion
        - tool_name: str
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
            cached_data = json.loads(cached)
            return {
                "success": True,
                "message": f"Vehículo identificado: {cached_data.get('tipo', 'desconocido')}",
                "data": cached_data,
                "tool_name": "identificar_tipo_vehiculo",
            }
    except Exception as e:
        logger.warning(f"Cache read failed: {e}")

    # Hybrid LLM Classification
    classification_data = None
    provider_used = None
    
    # Try local Ollama first if hybrid mode is enabled
    if settings.USE_HYBRID_LLM and settings.USE_LOCAL_VEHICLE_CLASSIFICATION:
        classification_data = await _classify_with_ollama(marca_norm, modelo_norm, settings)
        if classification_data:
            provider_used = "ollama"
    
    # Fallback to OpenRouter if local failed or disabled
    if classification_data is None:
        classification_data = await _classify_with_openrouter(marca_norm, modelo_norm, settings)
        if classification_data:
            provider_used = "openrouter"
    
    # Build result
    if classification_data:
        tipo = classification_data["tipo"]
        confianza = classification_data["confianza"]
        descripcion = classification_data["descripcion"]
        category_prefix = VEHICLE_TYPE_TO_CATEGORY_SLUG.get(tipo)
        
        # Resolve full slug using client_type from state
        from agent.state.helpers import get_current_state
        state = get_current_state()
        client_type = state.get("client_type", "particular") if state else "particular"
        
        categoria_sugerida = None
        if category_prefix:
            categoria_sugerida = await _resolve_full_category_slug(
                category_prefix, client_type
            )
        
        result_data = {
            "tipo": tipo,
            "confianza": confianza,
            "categoria_sugerida": categoria_sugerida,  # Full slug (e.g., "motos-part")
            "categoria_prefix": category_prefix,         # Prefix for reference
            "descripcion": descripcion,
            "marca": marca_norm,
            "modelo": modelo_norm,
            "client_type_used": client_type,
            "pedir_confirmacion": confianza in ["baja", "media"] or tipo == "desconocido",
            "_provider": provider_used,  # Internal field for debugging/metrics
        }
        
        # Cache result
        try:
            await redis.setex(cache_key, VEHICLE_TYPE_CACHE_TTL, json.dumps(result_data))
            logger.debug(f"Cached vehicle type for {marca_norm} {modelo_norm}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
        
        logger.info(
            f"Vehicle identified: {marca_norm} {modelo_norm} -> {tipo} ({confianza}) via {provider_used}",
            extra={
                "marca": marca_norm,
                "modelo": modelo_norm,
                "tipo": tipo,
                "confianza": confianza,
                "provider": provider_used,
            },
        )
        
        return {
            "success": True,
            "message": f"Vehículo identificado como {tipo} ({confianza})",
            "data": result_data,
            "tool_name": "identificar_tipo_vehiculo",
        }
    
    # Both providers failed - return error response
    logger.error(f"All LLM providers failed for {marca_norm} {modelo_norm}")
    
    # Read client_type for error case (not set above since classification_data was None)
    from agent.state.helpers import get_current_state
    error_state = get_current_state()
    error_client_type = error_state.get("client_type", "particular") if error_state else "particular"
    
    return {
        "success": False,
        "message": f"No pude identificar el tipo de vehículo {marca_norm} {modelo_norm}. Por favor, indícame qué tipo de vehículo es.",
        "data": {
            "tipo": "desconocido",
            "confianza": "baja",
            "categoria_sugerida": None,
            "categoria_prefix": None,
            "descripcion": f"Error al identificar {marca_norm} {modelo_norm}",
            "marca": marca_norm,
            "modelo": modelo_norm,
            "client_type_used": error_client_type,
            "pedir_confirmacion": True,
            "_provider": "none",
        },
        "tool_name": "identificar_tipo_vehiculo",
    }


# Export tools list
VEHICLE_TOOLS = [identificar_tipo_vehiculo]


def get_vehicle_tools() -> list:
    """Get all vehicle identification tools."""
    return VEHICLE_TOOLS


__all__ = [
    "identificar_tipo_vehiculo",
    "get_vehicle_tools",
    "VEHICLE_TOOLS",
]
