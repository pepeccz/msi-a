"""
MSI Automotive - Ollama Client Helper.

Utilities for checking Ollama availability and handling graceful degradation.
"""

import logging
import httpx

from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def is_ollama_available() -> bool:
    """
    Check if Ollama is running and responding.
    
    Returns:
        True if Ollama is available, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                logger.debug("Ollama is available")
                return True
            logger.debug(f"Ollama responded with status {response.status_code}")
            return False
    except httpx.ConnectError:
        logger.debug("Ollama is not available (connection refused)")
        return False
    except httpx.TimeoutException:
        logger.debug("Ollama is not available (timeout)")
        return False
    except Exception as e:
        logger.debug(f"Ollama availability check failed: {e}")
        return False


async def check_ollama_model(model_name: str) -> bool:
    """
    Check if a specific model is available in Ollama.
    
    Args:
        model_name: Name of the model to check (e.g., "qwen2.5:3b")
    
    Returns:
        True if model is available, False otherwise.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                available_names = [model.get("name") for model in models]
                return model_name in available_names
            return False
    except Exception as e:
        logger.debug(f"Ollama model check failed for {model_name}: {e}")
        return False
