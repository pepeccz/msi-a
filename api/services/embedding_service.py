"""
Embedding Service - Generates embeddings via Ollama with Redis caching.

This service provides embedding generation for RAG queries using the
nomic-embed-text model running locally in Ollama.
"""

__all__ = ["EmbeddingService", "get_embedding_service"]

import hashlib
import json
import logging
from functools import lru_cache

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.config import get_settings
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings via Ollama."""

    def __init__(self):
        self.settings = get_settings()
        self.redis = get_redis_client()
        self.base_url = self.settings.OLLAMA_BASE_URL
        self.model = self.settings.EMBEDDING_MODEL

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text hash."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"emb:{text_hash}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a single embedding with Redis caching.

        Args:
            text: The text to embed

        Returns:
            List of floats representing the embedding vector
        """
        cache_key = self._get_cache_key(text)

        # Check cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Embedding cache hit for key {cache_key[:20]}...")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")

        # Generate via Ollama
        logger.debug(f"Generating embedding for text: {text[:50]}...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text}
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]

        # Cache for 24h
        try:
            await self.redis.setex(cache_key, 86400, json.dumps(embedding))
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")

        return embedding

    async def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate multiple embeddings in parallel.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        import asyncio

        logger.info(f"Generating batch embeddings for {len(texts)} texts")
        tasks = [self.generate_embedding(text) for text in texts]
        return await asyncio.gather(*tasks)

    async def health_check(self) -> bool:
        """Check if Ollama embedding service is available."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return any(m.get("name", "").startswith(self.model) for m in models)
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
        return False


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Get singleton EmbeddingService instance."""
    return EmbeddingService()
