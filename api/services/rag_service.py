"""
RAG Service - Orchestrates the complete RAG query pipeline.

This is the main service that coordinates:
- Query embedding generation
- Vector search in Qdrant
- Result re-ranking with BGE
- LLM response generation with citations
- Query logging and caching
"""

import hashlib
import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.config import get_settings
from shared.redis_client import get_redis_client
from database.connection import get_async_session
from database.models import DocumentChunk, RegulatoryDocument, RAGQuery, QueryCitation
from api.services.embedding_service import get_embedding_service
from api.services.qdrant_service import get_qdrant_service
from api.services.reranker_service import get_reranker_service

logger = logging.getLogger(__name__)


class RAGService:
    """Main service for RAG query orchestration."""

    def __init__(self):
        self.settings = get_settings()
        self.redis = get_redis_client()
        self.embedding_service = get_embedding_service()
        self.qdrant_service = get_qdrant_service()
        self.reranker_service = get_reranker_service()

    async def query(
        self,
        query_text: str,
        user_id: str | None = None,
        conversation_id: str | None = None
    ) -> dict[str, Any]:
        """
        Execute the full RAG query pipeline.

        Args:
            query_text: The user's query
            user_id: Optional user ID for logging
            conversation_id: Optional conversation ID for logging

        Returns:
            Dictionary containing:
                - answer: LLM-generated response
                - citations: List of source citations
                - performance: Timing metrics
        """
        start_time = time.time()

        # Check cache
        query_hash = hashlib.sha256(query_text.encode()).hexdigest()
        cache_key = f"rag:query:{query_hash}"

        try:
            cached = await self.redis.get(cache_key)
            if cached:
                result = json.loads(cached)
                result["performance"]["cache_hit"] = True
                logger.info(f"RAG query cache hit for: {query_text[:50]}...")
                return result
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        # 1. Generate query embedding
        t0 = time.time()
        query_embedding = await self.embedding_service.generate_embedding(query_text)
        embedding_ms = int((time.time() - t0) * 1000)

        # 2. Vector search in Qdrant
        t1 = time.time()
        search_results = await self.qdrant_service.search(
            query_embedding,
            top_k=self.settings.RAG_TOP_K,
            filter_active_only=True
        )
        retrieval_ms = int((time.time() - t1) * 1000)

        if not search_results:
            logger.warning(f"No search results for query: {query_text[:50]}...")
            return self._build_no_results_response(start_time)

        # 3. Re-rank results
        t2 = time.time()
        reranked = await self.reranker_service.rerank(
            query_text,
            search_results,
            top_k=self.settings.RAG_RERANK_TOP_K
        )
        rerank_ms = int((time.time() - t2) * 1000)

        # 4. Fetch chunk details from DB
        async with get_async_session() as session:
            chunk_ids = [r["chunk_id"] for r in reranked]
            stmt = select(DocumentChunk).where(
                DocumentChunk.id.in_([uuid.UUID(cid) for cid in chunk_ids])
            ).options(selectinload(DocumentChunk.document))
            result = await session.execute(stmt)
            chunks = result.scalars().all()

            # Create mapping for ordering
            chunk_map = {str(c.id): c for c in chunks}

            # Build context maintaining rerank order
            ordered_chunks = [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]

            # Build LLM context
            context = self._build_context(ordered_chunks, reranked)

            # 5. Generate LLM response
            t3 = time.time()
            answer = await self._generate_answer(query_text, context)
            llm_ms = int((time.time() - t3) * 1000)

            # 6. Build citations
            citations = self._build_citations(ordered_chunks, reranked)

            # Calculate total time
            total_ms = int((time.time() - start_time) * 1000)

            # 7. Store query in DB (async, don't block response)
            try:
                await self._store_query(
                    session=session,
                    query_text=query_text,
                    query_hash=query_hash,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    retrieval_ms=retrieval_ms,
                    rerank_ms=rerank_ms,
                    llm_ms=llm_ms,
                    total_ms=total_ms,
                    num_retrieved=len(search_results),
                    num_reranked=len(reranked),
                    num_used=len(ordered_chunks),
                    citations=citations
                )
            except Exception as e:
                logger.error(f"Failed to store query: {e}")

            # Build response
            response = {
                "answer": answer,
                "citations": citations,
                "performance": {
                    "embedding_ms": embedding_ms,
                    "retrieval_ms": retrieval_ms,
                    "rerank_ms": rerank_ms,
                    "llm_ms": llm_ms,
                    "total_ms": total_ms,
                    "cache_hit": False
                }
            }

            # Cache for configured TTL
            try:
                await self.redis.setex(
                    cache_key,
                    self.settings.RAG_CACHE_TTL,
                    json.dumps(response)
                )
            except Exception as e:
                logger.warning(f"Cache write error: {e}")

            logger.info(
                f"RAG query completed in {total_ms}ms "
                f"(embedding: {embedding_ms}ms, retrieval: {retrieval_ms}ms, "
                f"rerank: {rerank_ms}ms, llm: {llm_ms}ms)"
            )

            return response

    def _build_context(
        self,
        chunks: list[DocumentChunk],
        reranked: list[dict[str, Any]]
    ) -> str:
        """Build LLM context from chunks."""
        context_parts = []

        for chunk_model in chunks:
            # Find corresponding reranked result
            reranked_data = next(
                (r for r in reranked if r["chunk_id"] == str(chunk_model.id)),
                None
            )

            relevance = f"{reranked_data['rerank_score']:.2f}" if reranked_data else "N/A"

            context_parts.append(f"""
---
Documento: {chunk_model.document.title}
Numero: {chunk_model.document.document_number or 'N/A'}
Articulo: {chunk_model.article_number or 'N/A'}
Seccion: {chunk_model.section_title or 'N/A'}
Paginas: {', '.join(map(str, chunk_model.page_numbers))}
Relevancia: {relevance}

{chunk_model.content}
""")

        return "\n".join(context_parts)

    async def _generate_answer(self, query: str, context: str) -> str:
        """Generate answer using LLM (GPT-4o-mini primary, qwen2.5:3b fallback)."""
        system_prompt = """Eres un experto en normativas de homologacion de vehiculos en Espana.

INSTRUCCIONES:
1. Responde basandote UNICAMENTE en los documentos proporcionados
2. Cita siempre el articulo y documento de referencia cuando uses informacion especifica
3. Si no encuentras la respuesta en los documentos, indicalo claramente
4. Usa un tono profesional pero accesible
5. Estructura la respuesta de forma clara y concisa
6. Si hay informacion contradictoria entre documentos, menciona ambas versiones

FORMATO:
- Responde en espanol
- Usa formato markdown si es necesario para claridad
- Incluye referencias como [Documento, Art. X] cuando cites"""

        user_message = f"""Documentos de referencia:
{context}

---
Pregunta del usuario: {query}"""

        try:
            # Try GPT-4o-mini via OpenRouter
            return await self._call_openrouter(system_prompt, user_message)
        except Exception as e:
            logger.warning(f"OpenRouter failed, using fallback: {e}")
            return await self._call_ollama_fallback(system_prompt, user_message)

    async def _call_openrouter(self, system_prompt: str, user_message: str) -> str:
        """Call OpenRouter API."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": self.settings.SITE_URL,
                    "X-Title": self.settings.SITE_NAME,
                },
                json={
                    "model": self.settings.LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                }
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def _call_ollama_fallback(self, system_prompt: str, user_message: str) -> str:
        """Call local Ollama as fallback."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": self.settings.RAG_LLM_FALLBACK_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _build_citations(
        self,
        chunks: list[DocumentChunk],
        reranked: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build citation objects for response."""
        citations = []

        for chunk_model in chunks:
            reranked_data = next(
                (r for r in reranked if r["chunk_id"] == str(chunk_model.id)),
                None
            )

            citations.append({
                "document_id": str(chunk_model.document_id),
                "document_title": chunk_model.document.title,
                "document_number": chunk_model.document.document_number,
                "chunk_id": str(chunk_model.id),
                "article_number": chunk_model.article_number,
                "section_title": chunk_model.section_title,
                "page_numbers": chunk_model.page_numbers,
                "similarity_score": reranked_data["score"] if reranked_data else 0,
                "rerank_score": reranked_data["rerank_score"] if reranked_data else 0,
                "content_preview": chunk_model.content[:300] + "..." if len(chunk_model.content) > 300 else chunk_model.content
            })

        return citations

    async def _store_query(
        self,
        session,
        query_text: str,
        query_hash: str,
        user_id: str | None,
        conversation_id: str | None,
        retrieval_ms: int,
        rerank_ms: int,
        llm_ms: int,
        total_ms: int,
        num_retrieved: int,
        num_reranked: int,
        num_used: int,
        citations: list[dict[str, Any]]
    ):
        """Store query and citations in database."""
        query_record = RAGQuery(
            query_text=query_text,
            query_hash=query_hash,
            user_id=uuid.UUID(user_id) if user_id else None,
            conversation_id=conversation_id,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            num_results_retrieved=num_retrieved,
            num_results_reranked=num_reranked,
            num_results_used=num_used,
            reranker_used="bge",
            response_generated=True,
            llm_model=self.settings.LLM_MODEL
        )
        session.add(query_record)
        await session.flush()

        for rank, citation in enumerate(citations, 1):
            citation_record = QueryCitation(
                query_id=query_record.id,
                document_id=uuid.UUID(citation["document_id"]),
                chunk_id=uuid.UUID(citation["chunk_id"]),
                rank=rank,
                similarity_score=citation["similarity_score"],
                rerank_score=citation["rerank_score"],
                used_in_context=True
            )
            session.add(citation_record)

        await session.commit()

    def _build_no_results_response(self, start_time: float) -> dict[str, Any]:
        """Build response when no search results found."""
        total_ms = int((time.time() - start_time) * 1000)
        return {
            "answer": "No he encontrado informacion relevante en los documentos indexados para responder a tu pregunta. Por favor, verifica que los documentos necesarios estan activos en el sistema o reformula tu pregunta.",
            "citations": [],
            "performance": {
                "embedding_ms": 0,
                "retrieval_ms": 0,
                "rerank_ms": 0,
                "llm_ms": 0,
                "total_ms": total_ms,
                "cache_hit": False
            }
        }

    async def clear_cache(self) -> int:
        """Clear all RAG query cache entries."""
        try:
            pattern = "rag:query:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)

            logger.info(f"Cleared {len(keys)} RAG cache entries")
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0


@lru_cache
def get_rag_service() -> RAGService:
    """Get singleton RAGService instance."""
    return RAGService()
