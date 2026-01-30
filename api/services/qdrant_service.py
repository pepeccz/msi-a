"""
Qdrant Service - Manages vector database operations.

This service handles all interactions with Qdrant for vector storage
and retrieval in the RAG system.
"""

__all__ = ["QdrantService", "get_qdrant_service"]

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    UpdateStatus,
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.config import get_settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for managing Qdrant vector database operations."""

    def __init__(self):
        self.settings = get_settings()
        self.client = QdrantClient(
            url=self.settings.QDRANT_URL,
            api_key=self.settings.QDRANT_API_KEY,
            timeout=60
        )
        self.collection_name = self.settings.QDRANT_COLLECTION_NAME
        self._ensure_collection()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ResponseHandlingException, ConnectionError, OSError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Qdrant connection failed, retrying in {retry_state.next_action.sleep:.1f}s... "
            f"(attempt {retry_state.attempt_number}/5)"
        )
    )
    def _ensure_collection(self):
        """Create collection if it doesn't exist (with retry on connection errors)."""
        try:
            collections = self.client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collection {self.collection_name} created successfully")
            else:
                logger.debug(f"Collection {self.collection_name} already exists")
        except (ResponseHandlingException, ConnectionError, OSError):
            raise
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """
        Insert or update document chunks in Qdrant.

        Args:
            chunks: List of chunk dictionaries containing:
                - chunk_id: UUID of the chunk
                - document_id: UUID of the parent document
                - qdrant_point_id: Unique point ID for Qdrant
                - embedding: Vector embedding
                - content: Text content
                - page_numbers: List of page numbers
                - article_number: Optional article reference
                - section_title: Optional section title
                - is_active: Whether document is active

        Returns:
            Number of points upserted
        """
        points = [
            PointStruct(
                id=chunk["qdrant_point_id"],
                vector=chunk["embedding"],
                payload={
                    "chunk_id": str(chunk["chunk_id"]),
                    "document_id": str(chunk["document_id"]),
                    "content": chunk["content"],
                    "page_numbers": chunk["page_numbers"],
                    "article_number": chunk.get("article_number"),
                    "section_title": chunk.get("section_title"),
                    "is_active": chunk["is_active"]
                }
            )
            for chunk in chunks
        ]

        # Batch upsert (100 at a time)
        batch_size = 100
        total_upserted = 0

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            result = self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            if result.status == UpdateStatus.COMPLETED:
                total_upserted += len(batch)

        logger.info(f"Upserted {total_upserted} chunks to Qdrant")
        return total_upserted

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        filter_active_only: bool = True
    ) -> list[dict[str, Any]]:
        """
        Perform vector search in Qdrant.

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filter_active_only: Only return results from active documents

        Returns:
            List of search results with metadata
        """
        query_filter = None
        if filter_active_only:
            query_filter = Filter(
                must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
            )

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True
        )

        return [
            {
                "chunk_id": hit.payload["chunk_id"],
                "document_id": hit.payload["document_id"],
                "content": hit.payload["content"],
                "page_numbers": hit.payload["page_numbers"],
                "article_number": hit.payload.get("article_number"),
                "section_title": hit.payload.get("section_title"),
                "score": hit.score
            }
            for hit in results
        ]

    async def delete_document_chunks(self, document_id: str) -> int:
        """
        Delete all chunks for a document.

        Args:
            document_id: UUID of the document

        Returns:
            Number of points deleted
        """
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            )
        )
        logger.info(f"Deleted chunks for document {document_id}")
        return result

    async def update_document_active_status(self, document_id: str, is_active: bool):
        """
        Update the is_active status for all chunks of a document.

        Args:
            document_id: UUID of the document
            is_active: New active status
        """
        # Get all points for this document
        scroll_result = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
            with_payload=True,
            with_vectors=False
        )

        points_to_update = []
        for point in scroll_result[0]:
            point.payload["is_active"] = is_active
            points_to_update.append(
                PointStruct(
                    id=point.id,
                    vector=[],  # We don't update the vector
                    payload=point.payload
                )
            )

        # Update payloads
        if points_to_update:
            for point in points_to_update:
                self.client.set_payload(
                    collection_name=self.collection_name,
                    payload={"is_active": is_active},
                    points=[point.id]
                )

        logger.info(f"Updated is_active={is_active} for {len(points_to_update)} chunks of document {document_id}")

    async def get_collection_info(self) -> dict[str, Any]:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {"error": str(e)}

    async def health_check(self) -> bool:
        """Check if Qdrant is available."""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False


# Singleton instance with reset capability
_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    """
    Get QdrantService instance with lazy initialization.

    Unlike @lru_cache, this allows resetting the instance on connection failures.
    """
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service


def reset_qdrant_service() -> None:
    """
    Reset service instance to force reconnection on next call.

    Use this when connection errors occur to allow fresh connection attempts.
    """
    global _qdrant_service
    _qdrant_service = None
    logger.info("Qdrant service instance reset, will reconnect on next call")
