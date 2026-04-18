---
titulo: RAG regulatorio — pipeline (estado parcial)
ambito: modulos
ultima_verificacion_commit:
ultima_verificacion_fecha: 2026-04-17
---

# Pipeline RAG sobre documentación oficial

## Resumen

MSI-a tiene un sistema RAG **diseñado e implementado en migraciones de BD** para retrieval de documentación regulatoria (PDFs de homologación, RDs, directivas EU), pero el código de servicios fue eliminado del repositorio. Las tablas de BD existen (migraciones `007_rag_system.py` y `008_fix_rag_queries_fk.py`), pero los archivos de código del pipeline no.

> **Estado real (2026-04-17)**: Los archivos `api/services/qdrant_service.py`, `rag_service.py`, `embedding_service.py`, `reranker_service.py`, `query_classifier.py`, `document_processor.py`, `api/workers/document_processor_worker.py`, `api/routes/rag_query.py` y `api/routes/regulatory_documents.py` **no existen en el repositorio**. `docker/Dockerfile.worker` también fue eliminado (obsoleto, nunca referenciado por docker-compose.yml). El RAG fue implementado y luego eliminado en un paso de simplificación de infraestructura.

**Estado actual por capa**:
- **Capa API** (`api/`): **ELIMINADA** — los archivos de servicio no existen. Las migraciones de BD sí (tablas `RegulatoryDocument`, `DocumentChunk`, `RAGQuery`, `QueryCitation`) pero sin código que las use.
- **Capa Agent** (`agent/`): **NO INTEGRADA** — el agente conversacional NO usa RAG en ningún modo activo. Esto es trabajo futuro.

Este documento sirve como especificación de lo que se debe reimplementar si se decide reactivar el RAG.

## Escenarios

### 1. Admin sube documento regulatorio → queda indexado

- DADO que el admin tiene el PDF "RD_2822_1998.pdf" listo para subir
- CUANDO el admin usa el panel en `/regulatory-documents` y sube el archivo
- ENTONCES: `POST /api/admin/regulatory-documents/upload` → valida MIME type (PDF) → calcula SHA256 → comprueba dedup (mismo hash ya indexado → error) → crea `RegulatoryDocument` con `status="pending"` → encola mensaje en Redis Stream (`document_processing_queue`) → responde inmediatamente al admin.
- En segundo plano: `document_processor_worker` consume el Stream → extrae texto (Docling primario, PyMuPDF fallback) → chunking semántico (~500 tokens, overlap ~100) → extrae sección/artículo vía LLM → genera embeddings batch (Ollama `nomic-embed-text`, con caché Redis 24h) → indexa en Qdrant (batch de 100 chunks) → persiste `DocumentChunk` rows en PostgreSQL → actualiza `status="indexed"`. Progreso: 0% → 20% → 40% → 50% → 70% → 90% → 100%.

### 2. Endpoint /api/admin/rag/query recibe una pregunta → retorna chunks relevantes

- DADO que hay documentos indexados en Qdrant
- CUANDO un cliente (admin panel o integración) hace `POST /api/admin/rag/query` con `{"query": "¿qué documentación necesito para homologar una suspensión?", "force_cloud": false}`
- ENTONCES: expansión de query → búsqueda híbrida en paralelo (vector search en Qdrant + keyword search en PostgreSQL ILIKE) → fusión RRF (Reciprocal Rank Fusion) → keyword boosting (términos de dominio: "homologación", "reglamento", "RD") → reranking BGE (`sentence_transformers CrossEncoder`) → top 5 chunks → clasificación de complejidad de query (SIMPLE → Ollama local, COMPLEX → OpenRouter cloud) → generación de respuesta LLM con contexto → citaciones → respuesta con `citations[]` indicando artículo y score → log en `RAGQuery` + caché Redis (para queries repetidas: ~500ms → ~50ms).

### 3. Estado actual de integración con el agente conversacional

- CUANDO un usuario de WhatsApp pregunta "¿Qué documentación necesita una suspensión delantera?"
- ENTONCES: el agente responde desde su conocimiento en los prompts y las herramientas de tarifa/elementos — **NO consulta Qdrant ni el pipeline RAG**. El pipeline RAG existe en la API pero el agente (`agent/modes/`) no tiene ningún nodo o tool que lo invoque.
- Esto es por diseño: la integración RAG en el agent está marcada como trabajo futuro. El admin puede usar los endpoints RAG directamente para investigación.

### 4. Fallo de componente — Qdrant o embeddings caídos

- CUANDO Qdrant está offline durante una query
- ENTONCES: `qdrant_service.py` detecta el fallo → `rag_service.py` captura la excepción → retorna error controlado (no 500 genérico) → el endpoint reporta componente unhealthy en `GET /api/admin/rag/health` → el fallo se loguea con structlog.
- El worker de ingesta hace crash recovery: reclama mensajes idle >30s de workers muertos, siempre hace ACK (incluso en fallo) para no bloquear el Stream.

## Reglas duras

1. **Pipeline API eliminado del repo**: `qdrant_service.py`, `rag_service.py`, `embedding_service.py`, `reranker_service.py`, `document_processor_worker.py` **no existen** en el repositorio actual. Las migraciones de BD sí existen. Para reactivar el RAG se deben restaurar estos archivos y agregar Qdrant al docker-compose.

2. **Integración con el agent = futuro**: NUNCA declarar en specs que el agente usa RAG hasta que se implemente explícitamente en `agent/modes/`. Hoy el pipeline solo está disponible vía API REST para uso directo del admin.

3. **Mismo modelo embedding para ingesta y query**: actualmente Ollama `nomic-embed-text`. No cambiar el modelo sin re-indexar toda la colección en Qdrant (cambio de modelo = incompatibilidad vectorial).

4. **Dedup por SHA256**: si el mismo PDF se sube dos veces, el segundo upload falla con error controlado. `RegulatoryDocument` tiene índice único sobre `sha256_hash`. (`api/routes/regulatory_documents.py`)

5. **is_active controla visibilidad en queries**: documentos con `is_active=False` se excluyen del vector search. El admin puede desactivar versiones supersedidas sin borrar los chunks. (`api/services/qdrant_service.py` — filtro `active=True` en búsquedas)

6. **Crash recovery en el worker**: el `document_processor_worker` usa consumer groups de Redis Streams (`document_workers`). Si el worker muere a mitad de un documento, el siguiente worker reclama el mensaje idle >30s y lo reprocesa desde cero.

7. **Caché de embeddings Redis 24h**: key `emb:{sha256(texto)}`. El mismo chunk en documentos distintos reutiliza el embedding cacheado. Reduce llamadas a Ollama significativamente en documentos con secciones repetidas.

8. **QueryCitation obligatorio para audit trail**: cada `RAGQuery` genera `QueryCitation` por chunk usado, con `similarity_score` y `rerank_score`. Permite trazar "de dónde sacó el sistema esta respuesta".

## Mapeo al código

### Capa API — ELIMINADA (código no existe en repo)

> Todos los archivos de esta sección fueron eliminados del repositorio. Se documentan como referencia para una eventual reimplementación.

| Archivo | Qué hacía |
|---------|----------|
| ~~`api/services/qdrant_service.py`~~ | Colección `msia-qdrant`, 5 reintentos en create, batch upsert 100 chunks, vector search con filtro `active=True`, delete by document, health check |
| ~~`api/services/rag_service.py`~~ | Orquestador completo: query expansion → hybrid search → RRF merge → keyword boosting → BGE reranking → routing LLM → citaciones → logging → caché Redis |
| ~~`api/services/embedding_service.py`~~ | Ollama `nomic-embed-text`, caché Redis 24h (`emb:{sha256}`), generación batch en paralelo, 3 reintentos |
| ~~`api/services/reranker_service.py`~~ | CrossEncoder BGE (`sentence_transformers`), carga lazy, fallback graceful (retorna orden original si falla) |
| ~~`api/services/query_classifier.py`~~ | Clasifica query SIMPLE vs COMPLEX (regex + keywords + longitud + conjunciones). Determina si va a Ollama o OpenRouter |
| ~~`api/services/document_processor.py`~~ | Extracción PDF: Docling (IA, markdown) como primario, PyMuPDF como fallback. Chunking con `RecursiveCharacterTextSplitter`. SHA256 |
| ~~`api/workers/document_processor_worker.py`~~ | Worker Redis Streams con consumer group `document_workers`. Crash recovery (reclama idle >30s). Siempre ACK. Pipeline 0%→100% con progreso |
| ~~`api/routes/rag_query.py`~~ | 6 endpoints: `POST /query`, `GET /queries` (historial), `GET /analytics`, `GET /health`, `GET /cache-stats`, `DELETE /cache` |
| ~~`api/routes/regulatory_documents.py`~~ | 9 endpoints: upload PDF, listar, detalle, activar/desactivar, borrar (3 capas: Qdrant → archivo → BD), reprocesar |

### Capa DB — modelos

| Modelo | Propósito |
|--------|-----------|
| `RegulatoryDocument` | Metadata del PDF (nombre, tipo, SHA256, status, is_active, section_mappings) |
| `DocumentChunk` | Fragmento indexado (chunk_index, qdrant_point_id, content, article_number, heading_hierarchy) |
| `RAGQuery` | Log de cada query: texto, hash, tiempos (retrieval_ms, rerank_ms, llm_ms), was_cache_hit |
| `QueryCitation` | Chunk usado en una query: rank, similarity_score, rerank_score, used_in_context |

### Capa Agent — NO INTEGRADA

| Archivo | Estado |
|---------|--------|
| `agent/modes/pre_expediente_mode.py` | No usa RAG. Trabajo futuro. |
| `agent/modes/expediente_nodes.py` | No usa RAG. Trabajo futuro. |
| `agent/services/` | No existe `rag_retrieval_service.py`. No creado aún. |

## Fuera de alcance

- **Integración del agent con RAG hoy**: el pipeline API existe pero el agente NO lo invoca. No asumir que el agente usa documentación regulatoria en sus respuestas.
- **Seeds de documentos regulatorios**: no existen seeds predefinidos. El admin carga manualmente los PDFs.
- **Múltiples colecciones Qdrant por tipo de documento**: hoy hay una sola colección. La separación por `document_type` es roadmap.
- **PII en documentos**: no hay sanitización automática de datos personales en PDFs antes de indexar. El admin es responsable de subir solo documentación pública.
- `agent/prompts/**` — los prompts del agente no incluyen contexto RAG (porque el agent no usa RAG).
- `admin-panel/src/` — frontend del panel (otro scope).
- `database/alembic/` — migraciones ya existentes (otro scope).
