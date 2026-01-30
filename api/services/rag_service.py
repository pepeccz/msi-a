"""
RAG Service - Orchestrates the complete RAG query pipeline.

This is the main service that coordinates:
- Query embedding generation
- Vector search in Qdrant
- Result re-ranking with BGE
- LLM response generation with citations
- Query logging and caching
"""

__all__ = ["RAGService", "get_rag_service"]

import asyncio
import hashlib
import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Any

import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from shared.config import get_settings
from shared.redis_client import get_redis_client
from database.connection import get_async_session
from database.models import DocumentChunk, RegulatoryDocument, RAGQuery, QueryCitation
from api.services.embedding_service import get_embedding_service
from api.services.qdrant_service import get_qdrant_service
from api.services.reranker_service import get_reranker_service
from api.services.query_classifier import classify_query, QueryComplexity, should_use_local_model

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

        # 1. Expand query for better retrieval
        expanded_query = self._expand_query(query_text)

        # 2. Generate query embedding
        t0 = time.time()
        query_embedding = await self.embedding_service.generate_embedding(expanded_query)
        embedding_ms = int((time.time() - t0) * 1000)

        # 3. Hybrid search: Vector (Qdrant) + Keywords (PostgreSQL) in parallel
        t1 = time.time()
        vector_task = self.qdrant_service.search(
            query_embedding,
            top_k=self.settings.RAG_TOP_K,
            filter_active_only=True
        )
        keyword_task = self._keyword_search_db(query_text, limit=60)

        vector_results, keyword_results = await asyncio.gather(
            vector_task, keyword_task
        )
        retrieval_ms = int((time.time() - t1) * 1000)

        logger.info(
            f"Hybrid search: {len(vector_results)} vector + {len(keyword_results)} keyword results"
        )

        # 4. Merge results using Reciprocal Rank Fusion
        merged_results = self._merge_results(vector_results, keyword_results)

        if not merged_results:
            logger.warning(f"No search results for query: {query_text[:50]}...")
            return self._build_no_results_response(start_time)

        # 5. Apply keyword boost to improve ranking
        search_results = self._boost_keyword_matches(merged_results, query_text)

        # 6. Re-rank results
        t2 = time.time()
        reranked = await self.reranker_service.rerank(
            query_text,
            search_results,
            top_k=self.settings.RAG_RERANK_TOP_K
        )
        rerank_ms = int((time.time() - t2) * 1000)

        # 7. Fetch chunk details from DB
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

            # 8. Generate LLM response
            t3 = time.time()
            answer = await self._generate_answer(query_text, context)
            llm_ms = int((time.time() - t3) * 1000)

            # 9. Build citations
            citations = self._build_citations(ordered_chunks, reranked)

            # Calculate total time
            total_ms = int((time.time() - start_time) * 1000)

            # 10. Store query in DB (async, don't block response)
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
                logger.error(
                    f"Failed to store query: {e}",
                    exc_info=True,
                    extra={"query_hash": query_hash, "user_id": user_id}
                )

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

    def _expand_query(self, query: str) -> str:
        """Expand query with technical terms for better retrieval."""
        query_lower = query.lower()
        expansions = []

        # Términos de cantidad
        if any(t in query_lower for t in ["cuantas", "cuantos", "cantidad", "número"]):
            expansions.append("Número cantidad especificaciones")

        # Términos de requisitos
        if any(t in query_lower for t in ["puede llevar", "permitido", "obligatorio"]):
            expansions.append("Presencia obligatorio prohibido requisitos")

        # Términos de ubicación
        if any(t in query_lower for t in ["donde", "posición", "instalación", "colocar"]):
            expansions.append("Disposición situación posición instalación")

        if expansions:
            expanded = f"{query} {' '.join(expansions)}"
            logger.debug(f"Query expanded: {query} -> {expanded}")
            return expanded
        return query

    def _boost_keyword_matches(
        self,
        results: list[dict],
        query: str
    ) -> list[dict]:
        """Boost results containing query keywords."""
        keywords = []
        query_lower = query.lower()

        # Extraer keywords según el tipo de pregunta
        if "luz" in query_lower or "luces" in query_lower:
            keywords.extend(["número", "6.2", "6.1", "presencia"])
        if "cruce" in query_lower:
            keywords.extend(["cruce", "6.2.2", "6.2.1"])
        if "carretera" in query_lower:
            keywords.extend(["carretera", "6.1.1", "6.1.2"])
        if "antiniebla" in query_lower:
            keywords.extend(["antiniebla", "6.3", "niebla"])
        if "posición" in query_lower or "posicion" in query_lower:
            keywords.extend(["posición", "6.9", "6.10"])

        if not keywords:
            return results

        # Aplicar boost
        for result in results:
            content_lower = result["content"].lower()
            matches = sum(1 for kw in keywords if kw.lower() in content_lower)
            original_score = result.get("score", 0)
            result["boosted_score"] = original_score + (matches * 0.05)

        # Re-ordenar por score boosteado
        results.sort(key=lambda x: x.get("boosted_score", x.get("score", 0)), reverse=True)
        logger.debug(f"Applied keyword boost with keywords: {keywords}")
        return results

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords for database search."""
        keywords = []
        query_lower = query.lower()

        # Mapeo de términos de usuario a términos de documento
        keyword_mappings = {
            # Cantidad
            ("cuantas", "cuantos", "cantidad", "número"): ["Número", "cantidad"],
            # Luces específicas
            ("cruce",): ["cruce", "6.2.2", "6.2.1"],
            ("carretera",): ["carretera", "6.1.1", "6.1.2"],
            ("antiniebla",): ["antiniebla", "6.3", "niebla"],
            ("posición", "posicion"): ["posición", "6.9", "6.10"],
            ("marcha atrás", "marcha atras"): ["marcha atrás", "6.11"],
            ("indicadores", "intermitentes"): ["indicadores", "6.5"],
            ("freno", "frenado"): ["freno", "6.7", "6.8"],
            ("matricula", "placa"): ["matrícula", "6.12", "placa"],
            # Presencia/requisitos
            ("obligatorio", "obligatoria", "puede llevar"): ["Presencia", "obligatorio"],
            # Ubicación
            ("donde", "ubicación", "ubicacion"): ["Disposición", "situación"],
        }

        for triggers, mapped_keywords in keyword_mappings.items():
            if any(t in query_lower for t in triggers):
                keywords.extend(mapped_keywords)

        return list(set(keywords))  # Eliminar duplicados

    async def _keyword_search_db(
        self,
        query: str,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search chunks by keywords in PostgreSQL with hierarchy enrichment."""
        from sqlalchemy import case, literal

        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        async with get_async_session() as session:
            # Construir condiciones ILIKE para cada keyword
            conditions = []
            for kw in keywords:
                conditions.append(DocumentChunk.content.ilike(f"%{kw}%"))

            # Calcular score basado en número de keywords que coinciden
            score_cases = []
            for kw in keywords:
                score_cases.append(
                    case((DocumentChunk.content.ilike(f"%{kw}%"), 1), else_=0)
                )

            # Sumar todos los scores (más keywords = mayor score)
            match_score = sum(score_cases) if score_cases else literal(0)

            stmt = (
                select(DocumentChunk)
                .join(RegulatoryDocument)
                .where(
                    RegulatoryDocument.is_active == True,
                    or_(*conditions)
                )
                .order_by(match_score.desc(), DocumentChunk.chunk_index)
                .limit(limit)
            )

            result = await session.execute(stmt)
            chunks = result.scalars().all()

            # Load section_mappings from documents (dynamic, not hardcoded)
            doc_ids = {c.document_id for c in chunks}
            doc_mappings: dict[str, dict[str, str]] = {}

            for doc_id in doc_ids:
                doc_result = await session.execute(
                    select(RegulatoryDocument.section_mappings)
                    .where(RegulatoryDocument.id == doc_id)
                )
                mappings = doc_result.scalar_one_or_none()
                if mappings:
                    doc_mappings[str(doc_id)] = mappings

            enriched_results = []
            for c in chunks:
                # Enriquecer contenido con contexto para mejor reranking
                content = c.content
                context_parts = []

                # 1. Usar jerarquía si existe
                if c.heading_hierarchy:
                    hierarchy_context = " > ".join(c.heading_hierarchy[-2:])
                    context_parts.append(hierarchy_context)

                # 2. Usar section_mappings del documento (dinámico)
                mappings = doc_mappings.get(str(c.document_id), {})
                section_context = self._get_section_context_dynamic(
                    c.content, c.section_title, mappings
                )
                if section_context and section_context not in str(context_parts):
                    context_parts.append(section_context)

                if context_parts:
                    content = f"[{' | '.join(context_parts)}] {content}"

                enriched_results.append({
                    "chunk_id": str(c.id),
                    "content": content,  # Contenido enriquecido para reranking
                    "original_content": c.content,  # Contenido original para LLM
                    "score": 0.5,  # Score base para keyword matches
                    "source": "keyword"
                })

            return enriched_results

    def _get_section_context_dynamic(
        self,
        content: str,
        section_title: str | None,
        mappings: dict[str, str]
    ) -> str | None:
        """
        Extract section context using document-specific mappings.

        This method uses dynamically loaded section mappings from the document
        rather than hardcoded values, making it work with any regulatory document.

        Args:
            content: Chunk text content
            section_title: Detected section title (may contain section number)
            mappings: Document-specific section number to description mappings

        Returns:
            Section description if a matching section number is found, None otherwise
        """
        import re

        if not mappings:
            return None

        text_to_search = f"{section_title or ''} {content[:200]}"

        # Search for any section number from the mappings
        for section_num, description in mappings.items():
            # Pattern matches section number and any subsections (e.g., 6.2 matches 6.2.1.2)
            pattern = rf'\b{re.escape(section_num)}(?:\.\d+)*\b'
            if re.search(pattern, text_to_search):
                return description

        return None

    def _merge_results(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        k: int = 60
    ) -> list[dict]:
        """Merge vector and keyword results using Reciprocal Rank Fusion."""
        scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        # Procesar resultados vectoriales
        for rank, result in enumerate(vector_results, 1):
            chunk_id = result["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
            chunk_data[chunk_id] = result.copy()
            chunk_data[chunk_id]["source"] = "vector"
            # Vector results no tienen original_content, usar content
            if "original_content" not in chunk_data[chunk_id]:
                chunk_data[chunk_id]["original_content"] = result["content"]

        # Procesar resultados de keywords (con boost adicional)
        for rank, result in enumerate(keyword_results, 1):
            chunk_id = result["chunk_id"]
            # Boost extra para keyword matches
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank) + 0.02
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = result.copy()
            else:
                chunk_data[chunk_id]["source"] = "hybrid"
                # IMPORTANTE: Usar contenido enriquecido del keyword search para reranking
                # El keyword search agrega contexto como "[Luces de cruce]" que mejora reranking
                if "original_content" in result:
                    chunk_data[chunk_id]["original_content"] = result["original_content"]
                    # Reemplazar content con versión enriquecida del keyword search
                    chunk_data[chunk_id]["content"] = result["content"]

        # Ordenar por score fusionado
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        merged = []
        for chunk_id in sorted_ids:
            result = chunk_data[chunk_id].copy()
            result["fusion_score"] = scores[chunk_id]
            merged.append(result)

        logger.debug(
            f"Merged {len(vector_results)} vector + {len(keyword_results)} keyword "
            f"results into {len(merged)} unique chunks"
        )
        return merged

    async def _generate_answer(self, query: str, context: str) -> str:
        """
        Generate answer using LLM with intelligent routing.
        
        Implements hybrid architecture:
        - Simple queries → Ollama local (RAG_PRIMARY_MODEL)
        - Complex queries → OpenRouter (LLM_MODEL)
        - Fallback chain for resilience
        """
        system_prompt = """Eres un experto en normativas de homologacion de vehiculos en Espana.

INSTRUCCIONES:
1. Responde basandote UNICAMENTE en los documentos proporcionados
2. Cuando pregunten "cuantos/cuantas", busca secciones tituladas "Número", "Cantidad" o listas numeradas
3. Para preguntas sobre requisitos, busca secciones de "Presencia", "Obligatorio/Prohibido"
4. Cita SIEMPRE el articulo exacto (ej: "Segun el punto 6.2.2 del Reglamento 48...")
5. Si la informacion aparece en formato de lista o tabla, transcribela completa
6. Si no encuentras la respuesta EXACTA en los documentos, indicalo claramente
7. NO inventes ni extrapoles - solo responde con lo que esta escrito

FORMATO DE CITAS:
- Usa formato: [Documento, punto X.X.X]
- Ejemplo: [Reglamento 48, punto 6.2.2]
- Responde en espanol con formato markdown si ayuda a la claridad"""

        user_message = f"""Documentos de referencia:
{context}

---
Pregunta del usuario: {query}"""

        # Determine routing based on query complexity
        use_local = (
            self.settings.USE_HYBRID_LLM and 
            self.settings.USE_LOCAL_FOR_SIMPLE_RAG and
            should_use_local_model(query, context_length=len(context))
        )
        
        complexity = classify_query(query)
        logger.debug(
            f"RAG query routing: complexity={complexity.value}, use_local={use_local}",
            extra={"query_preview": query[:50], "context_length": len(context)}
        )

        if use_local:
            # Try local model first for simple queries
            try:
                return await self._call_ollama_primary(system_prompt, user_message)
            except Exception as e:
                logger.warning(f"Ollama primary failed, falling back to OpenRouter: {e}")
                # Fall through to OpenRouter
        
        # Use OpenRouter for complex queries or as fallback
        try:
            return await self._call_openrouter(system_prompt, user_message)
        except Exception as e:
            logger.warning(f"OpenRouter failed, using Ollama fallback: {e}")
            return await self._call_ollama_fallback(system_prompt, user_message)

    async def _call_ollama_primary(self, system_prompt: str, user_message: str) -> str:
        """
        Call local Ollama with primary model (Tier 2: Capable).
        
        Uses RAG_PRIMARY_MODEL (default: llama3:8b) for simple RAG queries.
        """
        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": self.settings.RAG_PRIMARY_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 2000,
                    }
                }
            )
            response.raise_for_status()
            
            latency_ms = int((time.time() - start_time) * 1000)
            logger.debug(
                f"Ollama primary RAG completed in {latency_ms}ms",
                extra={
                    "model": self.settings.RAG_PRIMARY_MODEL,
                    "latency_ms": latency_ms,
                    "provider": "ollama",
                    "tier": "primary"
                }
            )
            
            return response.json()["message"]["content"]

    async def _call_openrouter(self, system_prompt: str, user_message: str) -> str:
        """Call OpenRouter API (Tier 3: Cloud)."""
        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
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
            
            latency_ms = int((time.time() - start_time) * 1000)
            logger.debug(
                f"OpenRouter RAG completed in {latency_ms}ms",
                extra={
                    "model": self.settings.LLM_MODEL,
                    "latency_ms": latency_ms,
                    "provider": "openrouter"
                }
            )
            
            return response.json()["choices"][0]["message"]["content"]

    async def _call_ollama_fallback(self, system_prompt: str, user_message: str) -> str:
        """
        Call local Ollama as fallback (Tier 1: Fast).
        
        Uses RAG_LLM_FALLBACK_MODEL (default: qwen2.5:3b) when all else fails.
        """
        start_time = time.time()
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
            
            latency_ms = int((time.time() - start_time) * 1000)
            logger.debug(
                f"Ollama fallback RAG completed in {latency_ms}ms",
                extra={
                    "model": self.settings.RAG_LLM_FALLBACK_MODEL,
                    "latency_ms": latency_ms,
                    "provider": "ollama",
                    "tier": "fallback"
                }
            )
            
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
        session: Any,
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
    ) -> None:
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
            logger.error(f"Failed to clear cache: {e}", exc_info=True)
            return 0


@lru_cache
def get_rag_service() -> RAGService:
    """Get singleton RAGService instance."""
    return RAGService()
