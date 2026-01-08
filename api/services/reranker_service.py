"""
Reranker Service - Re-ranks search results using BGE cross-encoder.

This service improves search relevance by re-ranking initial vector
search results using a cross-encoder model.
"""

import logging
from functools import lru_cache
from typing import Any

from shared.config import get_settings

logger = logging.getLogger(__name__)

# Global model instance (lazy loaded)
_reranker_model = None


def _get_reranker_model():
    """Lazy load the reranker model."""
    global _reranker_model
    if _reranker_model is None:
        from sentence_transformers import CrossEncoder
        settings = get_settings()
        logger.info(f"Loading reranker model: {settings.BGE_RERANKER_MODEL}")
        _reranker_model = CrossEncoder(settings.BGE_RERANKER_MODEL)
        logger.info("Reranker model loaded successfully")
    return _reranker_model


class RerankerService:
    """Service for re-ranking search results using cross-encoder."""

    def __init__(self):
        self.settings = get_settings()

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Re-rank documents using BGE cross-encoder.

        Args:
            query: The search query
            documents: List of document dictionaries with 'content' field
            top_k: Number of top results to return (None = all)

        Returns:
            Re-ranked list of documents with added 'rerank_score' field
        """
        if not documents:
            return []

        if top_k is None:
            top_k = self.settings.RAG_RERANK_TOP_K

        logger.debug(f"Re-ranking {len(documents)} documents for query: {query[:50]}...")

        try:
            model = _get_reranker_model()

            # Prepare query-document pairs
            pairs = [[query, doc["content"]] for doc in documents]

            # Get scores from cross-encoder
            scores = model.predict(pairs)

            # Add scores to documents
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = float(score)

            # Sort by rerank score (descending)
            documents.sort(key=lambda x: x["rerank_score"], reverse=True)

            # Return top_k results
            result = documents[:top_k]

            logger.debug(
                f"Re-ranking complete. Top score: {result[0]['rerank_score']:.4f}, "
                f"Bottom score: {result[-1]['rerank_score']:.4f}"
            )

            return result

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            # Return original documents without reranking
            for doc in documents:
                doc["rerank_score"] = doc.get("score", 0.0)
            return documents[:top_k]

    async def rerank_with_scores_only(
        self,
        query: str,
        contents: list[str]
    ) -> list[float]:
        """
        Get rerank scores for a list of contents.

        Args:
            query: The search query
            contents: List of text contents

        Returns:
            List of rerank scores
        """
        if not contents:
            return []

        try:
            model = _get_reranker_model()
            pairs = [[query, content] for content in contents]
            scores = model.predict(pairs)
            return [float(s) for s in scores]
        except Exception as e:
            logger.error(f"Score calculation failed: {e}")
            return [0.0] * len(contents)

    async def health_check(self) -> bool:
        """Check if reranker model is available."""
        try:
            model = _get_reranker_model()
            # Test with a simple pair
            _ = model.predict([["test query", "test document"]])
            return True
        except Exception as e:
            logger.error(f"Reranker health check failed: {e}")
            return False


@lru_cache
def get_reranker_service() -> RerankerService:
    """Get singleton RerankerService instance."""
    return RerankerService()
