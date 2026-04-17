---
titulo: Pipeline RAG sobre documentación oficial
ambito: rag-retrieval
ultima_verificacion_commit:
ultima_verificacion_fecha:
---

# Pipeline RAG sobre documentación oficial

## Resumen

MSI-a implementa un **sistema RAG** para retrieval de documentación regulatoria (PDFs de homologación, RDs, directivas EU).

> **ESTADO: PARCIALMENTE IMPLEMENTADO** — los modelos de BD existen (`RegulatoryDocument`, `DocumentChunk`, `RAGQuery`, `QueryCitation`) y la migración Alembic existe, pero **el consumer code (retrieval en runtime) no está completamente integrado** en modos del agent. Qdrant service **no está configurado en docker-compose.yml** actualmente. El embedding model no está elegido. Los seeds de documentos regulatorios no existen aún.

**Arquitectura esperada**:
1. **Ingesta**: admin carga PDF → extraído con Docling/PyMuPDF → chunking semantic (~500 tokens/chunk con overlap) → generación de embeddings vía OpenRouter → almacenamiento en Qdrant (vector DB)
2. **Almacenamiento**: PostgreSQL almacena metadata (`RegulatoryDocument`, `DocumentChunk`); Qdrant almacena embeddings + payload
3. **Retrieval en runtime**: cliente pregunta → embedding de query → Qdrant similarity search → top K chunks → reranking (opcional) → LLM usa chunks en respuesta
4. **Analytics**: `RAGQuery` + `QueryCitation` registran qué chunks se usaron, hit rates, latencias

## Escenarios

### 1. Documento regulatorio cargado al sistema
- CUANDO el admin sube "RD_2822_1998.pdf" vía admin panel upload endpoint
- ENTONCES: `POST /admin/documents/upload` → valida MIME type (PDF) → compute SHA256 hash → chequea dedup → crea `RegulatoryDocument` row (`status="pending"`) → encola ingest task.

### 2. Documento extraído y chunkeado
- CUANDO background task procesa `RegulatoryDocument` (`status="pending"`)
- ENTONCES: Docling/PyMuPDF extrae texto + estructura → semantic chunking (~500 tokens, overlap ~100) → genera `article_number`, `section_title`, `heading_hierarchy` vía LLM → crea `DocumentChunk` rows → status "processing" → "indexed". Salida: 50-200 chunks creados.

### 3. Chunks embeddeados en Qdrant
- CUANDO `DocumentChunk` creado
- ENTONCES: ingest task llama al embedding service → vector ~1536D → `Qdrant.upsert(point_id=chunk.qdrant_point_id, vector=embedding, payload={chunk_id, content, article_number, ...})`. Precondición: Qdrant service healthy.

### 4. Query del cliente activa RAG retrieval
- CUANDO el agent decide usar RAG (ej. cliente pregunta *"¿qué documentación necesito para suspensión?"*)
- ENTONCES: query → embedding (mismo modelo que ingest) → `Qdrant.search(vector=query_emb, limit=5)` → `similarity_score + payload` → crea `RAGQuery` row → crea `QueryCitation` rows. Top 5 chunks relevantes stored para analytics.

### 5. Retrieval devuelve chunks relevantes
- CUANDO `Qdrant.search()` retorna 5 chunks con scores [0.92, 0.87, 0.76, 0.65, 0.51]
- ENTONCES: filter score > 0.6 threshold (4 chunks pasan) → optional reranking → LLM system prompt incluye `context_from_rag: chunks`. LLM ve contexto oficial en prompt, reduce hallucinations.

### 6. LLM usa chunks en respuesta
- CUANDO LLM responde con chunks en contexto
- ENTONCES: respuesta cita artículos/secciones (ej. *"Según el RD 2822/1998, Art. 23.1, ..."*) → cliente ve sourced information → `QueryCitation` registra `used_in_context=True` para cada chunk citado.

### 7. Error de retrieval (Qdrant offline, embedding fail)
- CUANDO `Qdrant.search()` timeout o embedding service down
- ENTONCES: graceful fallback → agent continúa sin RAG context → logs warning *"RAG retrieval failed, continuing without context"* → `QueryCitation` marca `similarity_score=NULL`. RAG NO es bloqueante.

### 8. Query cacheado en RAGQuery
- CUANDO la misma query ejecutada 2 veces (`query_hash` match)
- ENTONCES: `RAGQuery` detects duplicate vía query_hash → reutiliza chunks previos → latencia cae de ~500ms a ~50ms. `was_cache_hit=True`.

## Reglas duras

1. **Qdrant service mandatory para RAG en producción** (actualmente TODO): `docker-compose.yml` DEBE tener Qdrant service con healthcheck. Vector DB no puede ser PostgreSQL (lento para similarity search).

2. **Chunking strategy fijo**: ~500 tokens/chunk, ~100 tokens overlap, semantic boundaries (respeta capítulos/artículos). No cambiar en runtime. Config via `CHUNK_SIZE` y `CHUNK_OVERLAP` env vars.

3. **Embedding model determinístico**: same query text → same embedding vector ALWAYS. Implica modelo fixed. No cambiar embedding model sin re-indexing (expensive).

4. **Qdrant collection por document_type**: ej. "reglamentos" collection, "directivas" collection. Evita mezclar docs de distinto contexto. Nombres: `{document_type}_{version}`.

5. **No indexing de contenido sensible**: si documento contiene PII (NIF, direcciones), sanitizar/redactar ANTES de chunk + embed. RAG DEBE usar solo documentación pública.

6. **`RegulatoryDocument.is_active` controla ingesta**: solo docs con `is_active=True` se usan en RAG queries. Admin puede deactivate superseded docs → se excluyen de búsquedas.

7. **`QueryCitation` mandatory para audit trail**: cada `RAGQuery` DEBE crear `QueryCitation` para cada chunk usado. Permite re-trace "de dónde sacó esto el agent".

8. **Reranking opcional, scoring obligatorio**: Qdrant `similarity_score` ALWAYS calculado. Si reranking enabled, `rerank_score` additionally computed. Both stored in `QueryCitation`.

9. **Performance metrics**: `retrieval_ms`, `rerank_ms`, `llm_ms`. Agregados en `RAGQuery` para analytics dashboard.

10. **Error handling graceful**: si RAG falla en cualquier etapa, system NO throws. Agent continúa sin RAG context. Logs warning + metrics registran failure.

## Mapeo al código

### Database Models (existen)
- `database/models.py:1802-1984` — `RegulatoryDocument` (metadata, status, is_active, section_mappings)
- `database/models.py:1987-2104` — `DocumentChunk` (chunk_index, qdrant_point_id, content, article_number, heading_hierarchy, chunk_type)
- `database/models.py:2106-2200+` — `RAGQuery` (query_text, query_hash, retrieval_ms, rerank_ms, llm_ms, was_cache_hit)
- `database/models.py:2200+` — `QueryCitation` (query_id → chunk_id, rank, similarity_score, rerank_score, used_in_context)

### Migrations (existen)
- `database/alembic/versions/007_rag_system.py:1-502` — crea tablas `regulatory_documents`, `document_chunks`, `rag_queries`, `query_citations`
- `database/alembic/versions/008_fix_rag_queries_fk.py:1-58` — fix FK constraints

### Admin Panel Upload (parcial)
- `api/routes/admin.py` — endpoint `POST /admin/documents/upload` (TBD: implementation)
- `api/services/document_ingestion_service.py` (TBD: create) — Docling integration, chunking logic

### Retrieval Integration (NO IMPLEMENTADO)
- `agent/services/rag_retrieval_service.py` (TBD: create) — `LLMRouter.invoke(task_type=RAG_COMPLEX, ...)`, Qdrant client, chunk ranking
- `agent/modes/pre_expediente_mode.py` — FUTURO: integración RAG en fases
- `agent/modes/expediente_mode.py` — FUTURO: integración RAG para COLLECT_PERSONAL, COLLECT_VEHICLE

### Shared Utilities (TBD)
- `shared/qdrant_client.py` (TBD: create) — Qdrant async client, healthcheck, upsert, search
- `shared/embedding_service.py` (TBD: create) — OpenRouter embedding calls

### Configuration (parcial)
- `shared/config.py` (TBD: add) — `QDRANT_URL`, `QDRANT_API_KEY`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RAG_RERANK_ENABLED`, `RAG_SIMILARITY_THRESHOLD`

### Docker Compose (TBD)
- `docker-compose.yml` — (NO YET ADDED) Qdrant service definition + healthcheck

### Seeds (NO IMPLEMENTADO)
- `database/seeds/regulatory_documents_seed.py` (TBD: create) — Load regulatory PDFs from fixtures or URL

## Fuera de alcance

- `agent/modes/pre_expediente_mode.py`, `expediente_mode.py` — modo agent logic (otro scope) — cambios aquí solo cuando se integra RAG retrieval explícitamente
- `agent/prompts/**` — system prompts (otro scope) — RAG prompt injection happens via context, no cambiar prompts
- `agent/tools/**` — tool definitions (otro scope) — RAG NO es tool, es contexto
- `database/models.py` excepto para extensiones de RAG models — use migrations
- `shared/llm_router.py` excepto para `TaskType.RAG_COMPLEX` routing — router es infra LLM
- `api/routes/` excepto `/admin/documents/upload` — scope distinto
- `admin-panel/src` — frontend (otro scope)
- Test suite `tests/` — scope distinto
