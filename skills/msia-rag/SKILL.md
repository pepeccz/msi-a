---
name: msia-rag
description: >
  MSI-a RAG (Retrieval-Augmented Generation) system patterns.
  Trigger: When working with document processing, embeddings, vector search, or RAG queries.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api]
  auto_invoke: "Working with RAG system or documents"
---

## Overview

The RAG system enables MSI-a to answer questions about vehicle homologation regulations by retrieving relevant chunks from uploaded regulatory documents.

## Architecture

```
Document Upload → Redis Stream → Document Processor Worker
                                         ↓
                            PDF Extraction (Docling/PyMuPDF)
                                         ↓
                               Semantic Chunking
                                         ↓
                    Ollama Embeddings (nomic-embed-text)
                                         ↓
                      Qdrant (vectors) + PostgreSQL (metadata)

Query → Expansion → Hybrid Search → RRF Merge → Rerank → LLM → Response
                   (Vector + KW)              (BGE)    (GPT-4o-mini)
```

## Key Components

```
api/
├── routes/
│   ├── regulatory_documents.py  # Document upload/management
│   └── rag_query.py             # RAG query endpoint
├── services/
│   ├── rag_service.py           # Main RAG orchestrator
│   ├── embedding_service.py     # Ollama embedding generation
│   ├── qdrant_service.py        # Vector storage/search
│   ├── reranker_service.py      # BGE reranking
│   └── document_processor.py    # PDF extraction/chunking
└── workers/
    └── document_processor_worker.py  # Async processing worker

database/models.py:
├── RegulatoryDocument           # Document metadata
├── DocumentChunk                # Semantic chunks
├── RAGQuery                     # Query history/analytics
└── QueryCitation                # Chunk citations in responses
```

## Document Processing Pipeline

### 1. Upload Document

```python
from fastapi import UploadFile
from shared.redis_client import RedisClient

async def upload_document(
    file: UploadFile,
    title: str,
    document_type: str,
    session: AsyncSession,
):
    # Validate PDF
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files allowed")
    
    # Save file
    content = await file.read()
    stored_filename = f"{uuid4()}.pdf"
    file_path = UPLOAD_DIR / stored_filename
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    # Create record
    doc = RegulatoryDocument(
        title=title,
        document_type=document_type,
        filename=file.filename,
        stored_filename=stored_filename,
        file_hash=hashlib.sha256(content).hexdigest(),
        status="pending",
    )
    session.add(doc)
    await session.flush()
    
    # Queue for processing
    await RedisClient.xadd(
        "document_processing",
        {"document_id": str(doc.id)}
    )
    
    return doc
```

### 2. Process Document (Worker)

```python
from api.services.document_processor import DocumentProcessor
from api.services.embedding_service import EmbeddingService
from api.services.qdrant_service import QdrantService

async def process_document(document_id: str):
    async with get_session() as session:
        doc = await session.get(RegulatoryDocument, document_id)
        doc.status = "processing"
        await session.commit()
        
        try:
            # Extract text from PDF
            processor = DocumentProcessor()
            pages = await processor.extract_pdf(doc.stored_filename)
            
            # Create semantic chunks
            chunks = processor.create_chunks(
                pages,
                chunk_size=1000,
                chunk_overlap=200,
            )
            
            # Generate embeddings
            embeddings = await EmbeddingService.embed_texts(
                [c.content for c in chunks]
            )
            
            # Store in Qdrant
            point_ids = await QdrantService.upsert_points(
                collection="regulatory_docs",
                vectors=embeddings,
                payloads=[c.to_payload() for c in chunks],
            )
            
            # Save chunks to PostgreSQL
            for i, chunk in enumerate(chunks):
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    qdrant_point_id=point_ids[i],
                    content=chunk.content,
                    page_numbers=chunk.page_numbers,
                    section_title=chunk.section_title,
                    article_number=chunk.article_number,
                )
                session.add(db_chunk)
            
            doc.status = "indexed"
            doc.total_chunks = len(chunks)
            await session.commit()
            
        except Exception as e:
            doc.status = "failed"
            doc.error_message = str(e)
            await session.commit()
            raise
```

## Query Pipeline

### RAG Service (Main Orchestrator)

```python
from api.services.rag_service import RAGService

class RAGService:
    """Main RAG query orchestrator."""
    
    async def query(
        self,
        query_text: str,
        session: AsyncSession,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> RAGResponse:
        """Execute RAG query with full pipeline."""
        start_time = time.time()
        
        # Check cache
        query_hash = hashlib.sha256(query_text.encode()).hexdigest()
        cached = await self._check_cache(query_hash)
        if cached:
            return cached
        
        # 1. Query expansion
        expanded_queries = await self._expand_query(query_text)
        
        # 2. Hybrid search (parallel)
        vector_results, keyword_results = await asyncio.gather(
            self._vector_search(expanded_queries),
            self._keyword_search(query_text, session),
        )
        
        # 3. Reciprocal Rank Fusion
        merged = self._rrf_merge(vector_results, keyword_results)
        
        # 4. Rerank with BGE
        reranked = await self._rerank(query_text, merged)
        
        # 5. Build context
        context = self._build_context(reranked[:5])
        
        # 6. Generate response with LLM
        response = await self._generate_response(query_text, context)
        
        # 7. Build citations
        citations = self._build_citations(reranked[:5])
        
        # 8. Log query
        await self._log_query(
            session,
            query_text=query_text,
            query_hash=query_hash,
            response=response,
            citations=citations,
            timings={
                "retrieval_ms": ...,
                "rerank_ms": ...,
                "llm_ms": ...,
                "total_ms": (time.time() - start_time) * 1000,
            },
        )
        
        # 9. Cache response
        await self._cache_response(query_hash, response, citations)
        
        return RAGResponse(
            answer=response,
            citations=citations,
            query_id=...,
        )
```

### Vector Search (Qdrant)

```python
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

class QdrantService:
    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
    
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filter_conditions: dict | None = None,
    ) -> list[ScoredPoint]:
        """Search for similar vectors."""
        qdrant_filter = None
        if filter_conditions:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key=k,
                        match=MatchValue(value=v)
                    )
                    for k, v in filter_conditions.items()
                ]
            )
        
        results = await self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        
        return results
```

### Embedding Service (Ollama)

```python
import httpx

class EmbeddingService:
    """Generate embeddings using Ollama."""
    
    MODEL = "nomic-embed-text"
    
    @classmethod
    async def embed_texts(cls, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        async with httpx.AsyncClient() as client:
            embeddings = []
            for text in texts:
                response = await client.post(
                    f"{settings.OLLAMA_HOST}/api/embeddings",
                    json={"model": cls.MODEL, "prompt": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                embeddings.append(response.json()["embedding"])
            return embeddings
    
    @classmethod
    async def embed_query(cls, query: str) -> list[float]:
        """Generate embedding for a single query."""
        result = await cls.embed_texts([query])
        return result[0]
```

### Reranker Service (BGE)

```python
class RerankerService:
    """Rerank results using BGE model via Ollama."""
    
    MODEL = "bge-reranker-base"
    
    @classmethod
    async def rerank(
        cls,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        """Rerank documents by relevance to query."""
        # Score each document
        scores = []
        for i, doc in enumerate(documents):
            score = await cls._score_pair(query, doc)
            scores.append((i, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
```

## Database Models

### RegulatoryDocument

```python
class RegulatoryDocument(Base):
    __tablename__ = "regulatory_documents"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str]
    document_type: Mapped[str]  # "reglamento", "orden", "real_decreto"
    document_number: Mapped[str | None]
    filename: Mapped[str]
    stored_filename: Mapped[str]
    file_hash: Mapped[str]
    status: Mapped[str]  # pending, processing, indexed, failed, inactive
    processing_progress: Mapped[int] = mapped_column(default=0)
    total_pages: Mapped[int | None]
    total_chunks: Mapped[int | None]
    extraction_method: Mapped[str | None]  # docling, pymupdf
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    section_mappings: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")
```

### DocumentChunk

```python
class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("regulatory_documents.id"))
    chunk_index: Mapped[int]
    qdrant_point_id: Mapped[str]  # UUID stored in Qdrant
    content: Mapped[str]
    content_hash: Mapped[str]
    page_numbers: Mapped[list[int]] = mapped_column(JSONB)
    section_title: Mapped[str | None]
    article_number: Mapped[str | None]
    heading_hierarchy: Mapped[list[str]] = mapped_column(JSONB, default=list)
    char_count: Mapped[int]
    token_count: Mapped[int | None]
    chunk_type: Mapped[str] = mapped_column(default="content")
    
    # Relationships
    document: Mapped["RegulatoryDocument"] = relationship(back_populates="chunks")
```

## API Endpoints

### Document Management

```python
# Upload document
POST /api/admin/regulatory-documents
Content-Type: multipart/form-data
- file: PDF file
- title: Document title
- document_type: reglamento | orden | real_decreto

# List documents
GET /api/admin/regulatory-documents
Response: list of documents with status

# Get document details
GET /api/admin/regulatory-documents/{id}

# Reprocess document
POST /api/admin/regulatory-documents/{id}/reprocess

# Deactivate document
DELETE /api/admin/regulatory-documents/{id}
```

### RAG Query

```python
# Execute query
POST /api/admin/rag/query
{
    "query": "Que documentacion necesito para homologar un enganche?",
    "user_id": "optional",
    "conversation_id": "optional"
}

Response:
{
    "answer": "Para homologar un enganche necesitas...",
    "citations": [
        {
            "document_title": "Reglamento 55",
            "article": "Art. 12",
            "section": "12.1",
            "relevance_score": 0.92
        }
    ],
    "query_id": "uuid"
}

# Get query history
GET /api/admin/rag/queries?limit=50

# Clear cache
POST /api/admin/rag/cache/clear
```

## Configuration

```env
# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Ollama (embeddings)
OLLAMA_HOST=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text
RERANKER_MODEL=bge-reranker-base

# RAG Settings
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=200
RAG_TOP_K=10
RAG_RERANK_TOP_K=5
RAG_CACHE_TTL=3600
```

## Critical Rules

- ALWAYS use async/await for all I/O operations
- ALWAYS validate PDF files before processing
- ALWAYS store embeddings in Qdrant AND metadata in PostgreSQL
- ALWAYS log queries for analytics
- ALWAYS include citations in responses
- NEVER block the main thread during PDF processing
- NEVER store raw PDFs in the database (use filesystem)
- ALWAYS use chunking with overlap for better retrieval
- ALWAYS cache frequent queries in Redis

## Chunking Strategy

```python
def create_chunks(
    pages: list[Page],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Chunk]:
    """Create semantic chunks respecting document structure."""
    chunks = []
    
    for page in pages:
        # Split by articles/sections when possible
        sections = extract_sections(page.content)
        
        for section in sections:
            if len(section.content) <= chunk_size:
                # Keep small sections as single chunk
                chunks.append(Chunk(
                    content=section.content,
                    page_numbers=[page.number],
                    section_title=section.title,
                    article_number=section.article,
                ))
            else:
                # Split large sections with overlap
                for i in range(0, len(section.content), chunk_size - chunk_overlap):
                    chunk_text = section.content[i:i + chunk_size]
                    chunks.append(Chunk(
                        content=chunk_text,
                        page_numbers=[page.number],
                        section_title=section.title,
                        article_number=section.article,
                    ))
    
    return chunks
```

## Resources

- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Ollama Embedding API](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings)
- [Docling PDF Extraction](https://github.com/DS4SD/docling)
- [msia-api skill](../msia-api/SKILL.md) - FastAPI patterns
- [msia-database skill](../msia-database/SKILL.md) - SQLAlchemy patterns
