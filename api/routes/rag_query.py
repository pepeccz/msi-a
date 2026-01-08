"""
RAG Query API Routes.

Provides endpoints for querying regulatory documents using RAG
and managing the query cache.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from api.routes.admin import get_current_user
from api.services.rag_service import get_rag_service
from database.connection import get_async_session
from database.models import RAGQuery, QueryCitation, AdminUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/rag", tags=["rag"])


# =============================================================================
# Request/Response Models
# =============================================================================


class QueryRequest(BaseModel):
    """RAG query request."""
    query: str = Field(..., min_length=3, max_length=2000, description="The question to ask")
    conversation_id: str | None = Field(None, description="Optional conversation ID for context grouping")


class CitationResponse(BaseModel):
    """Citation information in query response."""
    document_id: str
    document_title: str
    document_number: str | None
    chunk_id: str
    article_number: str | None
    section_title: str | None
    page_numbers: list[int]
    similarity_score: float
    rerank_score: float
    content_preview: str


class QueryResponse(BaseModel):
    """RAG query response."""
    answer: str
    citations: list[CitationResponse]
    performance: dict


# =============================================================================
# Query Endpoint
# =============================================================================


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    request: QueryRequest,
    current_user: AdminUser = Depends(get_current_user),
) -> QueryResponse:
    """
    Execute a RAG query against regulatory documents.

    The query goes through the following pipeline:
    1. Query embedding generation
    2. Vector search in Qdrant
    3. Result re-ranking with BGE
    4. LLM response generation with citations

    Args:
        request: Query request with question text
        current_user: Authenticated admin user

    Returns:
        Answer with citations and performance metrics
    """
    logger.info(f"RAG query from {current_user.username}: {request.query[:50]}...")

    try:
        rag_service = get_rag_service()
        result = await rag_service.query(
            query_text=request.query,
            user_id=str(current_user.id),
            conversation_id=request.conversation_id
        )

        return QueryResponse(
            answer=result["answer"],
            citations=[
                CitationResponse(
                    document_id=c["document_id"],
                    document_title=c["document_title"],
                    document_number=c.get("document_number"),
                    chunk_id=c["chunk_id"],
                    article_number=c.get("article_number"),
                    section_title=c.get("section_title"),
                    page_numbers=c["page_numbers"],
                    similarity_score=c["similarity_score"],
                    rerank_score=c["rerank_score"],
                    content_preview=c["content_preview"]
                )
                for c in result["citations"]
            ],
            performance=result["performance"]
        )

    except Exception as e:
        logger.exception(f"RAG query failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {str(e)}"
        )


# =============================================================================
# Cache Management
# =============================================================================


@router.post("/cache/clear")
async def clear_cache(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Clear the RAG query cache.

    This forces all future queries to be processed fresh
    without using cached results.

    Args:
        current_user: Authenticated admin user

    Returns:
        Number of cache entries cleared
    """
    try:
        rag_service = get_rag_service()
        cleared = await rag_service.clear_cache()

        logger.info(f"RAG cache cleared by {current_user.username}: {cleared} entries")

        return JSONResponse(
            content={
                "message": "Cache cleared successfully",
                "entries_cleared": cleared
            }
        )

    except Exception as e:
        logger.exception(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


# =============================================================================
# Query History
# =============================================================================


@router.get("/queries")
async def list_queries(
    limit: int = 50,
    offset: int = 0,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    List RAG query history.

    Args:
        limit: Maximum items to return
        offset: Number of items to skip
        current_user: Authenticated admin user

    Returns:
        Paginated list of queries with metrics
    """
    async with get_async_session() as session:
        # Get total count
        total = await session.scalar(
            select(func.count(RAGQuery.id))
        ) or 0

        # Get queries
        result = await session.execute(
            select(RAGQuery)
            .order_by(RAGQuery.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        queries = result.scalars().all()

        return JSONResponse(
            content={
                "items": [
                    {
                        "id": str(q.id),
                        "query_text": q.query_text[:200] + "..." if len(q.query_text) > 200 else q.query_text,
                        "user_id": str(q.user_id) if q.user_id else None,
                        "conversation_id": q.conversation_id,
                        "retrieval_ms": q.retrieval_ms,
                        "rerank_ms": q.rerank_ms,
                        "llm_ms": q.llm_ms,
                        "total_ms": q.total_ms,
                        "num_results_retrieved": q.num_results_retrieved,
                        "num_results_reranked": q.num_results_reranked,
                        "num_results_used": q.num_results_used,
                        "cache_hit": q.cache_hit,
                        "llm_model": q.llm_model,
                        "created_at": q.created_at.isoformat(),
                    }
                    for q in queries
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(queries) < total,
            }
        )


@router.get("/queries/{query_id}")
async def get_query_details(
    query_id: uuid.UUID,
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get detailed information about a specific query.

    Includes full query text and all citations.

    Args:
        query_id: Query UUID
        current_user: Authenticated admin user

    Returns:
        Query details with citations
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(RAGQuery).where(RAGQuery.id == query_id)
        )
        query = result.scalar_one_or_none()

        if not query:
            raise HTTPException(status_code=404, detail="Query not found")

        # Get citations
        citations_result = await session.execute(
            select(QueryCitation).where(
                QueryCitation.query_id == query_id
            ).order_by(QueryCitation.rank)
        )
        citations = citations_result.scalars().all()

        return JSONResponse(
            content={
                "id": str(query.id),
                "query_text": query.query_text,
                "query_hash": query.query_hash,
                "user_id": str(query.user_id) if query.user_id else None,
                "conversation_id": query.conversation_id,
                "performance": {
                    "retrieval_ms": query.retrieval_ms,
                    "rerank_ms": query.rerank_ms,
                    "llm_ms": query.llm_ms,
                    "total_ms": query.total_ms,
                },
                "results": {
                    "num_retrieved": query.num_results_retrieved,
                    "num_reranked": query.num_results_reranked,
                    "num_used": query.num_results_used,
                },
                "reranker_used": query.reranker_used,
                "response_generated": query.response_generated,
                "llm_model": query.llm_model,
                "cache_hit": query.cache_hit,
                "created_at": query.created_at.isoformat(),
                "citations": [
                    {
                        "document_id": str(c.document_id),
                        "chunk_id": str(c.chunk_id),
                        "rank": c.rank,
                        "similarity_score": float(c.similarity_score) if c.similarity_score else None,
                        "rerank_score": float(c.rerank_score) if c.rerank_score else None,
                        "used_in_context": c.used_in_context,
                    }
                    for c in citations
                ],
            }
        )


# =============================================================================
# Analytics
# =============================================================================


@router.get("/analytics/summary")
async def get_analytics_summary(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Get RAG query analytics summary.

    Returns:
        Query statistics and performance averages
    """
    async with get_async_session() as session:
        # Total queries
        total_queries = await session.scalar(
            select(func.count(RAGQuery.id))
        ) or 0

        # Cache hit rate
        cache_hits = await session.scalar(
            select(func.count(RAGQuery.id)).where(RAGQuery.cache_hit == True)
        ) or 0

        # Average performance metrics
        avg_retrieval = await session.scalar(
            select(func.avg(RAGQuery.retrieval_ms)).where(RAGQuery.cache_hit == False)
        )
        avg_rerank = await session.scalar(
            select(func.avg(RAGQuery.rerank_ms)).where(RAGQuery.cache_hit == False)
        )
        avg_llm = await session.scalar(
            select(func.avg(RAGQuery.llm_ms)).where(RAGQuery.cache_hit == False)
        )
        avg_total = await session.scalar(
            select(func.avg(RAGQuery.total_ms)).where(RAGQuery.cache_hit == False)
        )

        # Queries in last 24h
        from datetime import datetime, timedelta, UTC
        day_ago = datetime.now(UTC) - timedelta(hours=24)
        queries_24h = await session.scalar(
            select(func.count(RAGQuery.id)).where(RAGQuery.created_at >= day_ago)
        ) or 0

        return JSONResponse(
            content={
                "total_queries": total_queries,
                "queries_last_24h": queries_24h,
                "cache_hit_rate": round(cache_hits / total_queries * 100, 1) if total_queries > 0 else 0,
                "avg_performance_ms": {
                    "retrieval": round(avg_retrieval, 1) if avg_retrieval else 0,
                    "rerank": round(avg_rerank, 1) if avg_rerank else 0,
                    "llm": round(avg_llm, 1) if avg_llm else 0,
                    "total": round(avg_total, 1) if avg_total else 0,
                },
            }
        )


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def health_check(
    current_user: AdminUser = Depends(get_current_user),
) -> JSONResponse:
    """
    Check health status of RAG system components.

    Returns:
        Health status of each component
    """
    from api.services.embedding_service import get_embedding_service
    from api.services.qdrant_service import get_qdrant_service
    from api.services.reranker_service import get_reranker_service

    results = {}

    # Check embedding service (Ollama)
    try:
        embedding_service = get_embedding_service()
        results["embedding_service"] = await embedding_service.health_check()
    except Exception as e:
        results["embedding_service"] = False
        logger.error(f"Embedding service health check failed: {e}")

    # Check Qdrant
    try:
        qdrant_service = get_qdrant_service()
        results["qdrant"] = await qdrant_service.health_check()
        if results["qdrant"]:
            collection_info = await qdrant_service.get_collection_info()
            results["qdrant_collection"] = collection_info
    except Exception as e:
        results["qdrant"] = False
        logger.error(f"Qdrant health check failed: {e}")

    # Check reranker
    try:
        reranker_service = get_reranker_service()
        results["reranker"] = await reranker_service.health_check()
    except Exception as e:
        results["reranker"] = False
        logger.error(f"Reranker health check failed: {e}")

    # Overall health
    all_healthy = all([
        results.get("embedding_service", False),
        results.get("qdrant", False),
        results.get("reranker", False),
    ])

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "components": results,
        }
    )
