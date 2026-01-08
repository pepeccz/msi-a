"""Add RAG system tables for regulatory documents

Revision ID: 007_rag_system
Revises: 006_admin_users
Create Date: 2026-01-08 00:00:00.000000

Changes:
- Add regulatory_documents table for PDF metadata
- Add document_chunks table for semantic chunks indexed in Qdrant
- Add rag_queries table for query analytics and caching
- Add query_citations table for linking queries to chunks
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_rag_system"
down_revision: Union[str, None] = "006_admin_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create regulatory_documents table
    # =========================================================================
    op.create_table(
        "regulatory_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Metadata
        sa.Column(
            "title",
            sa.String(500),
            nullable=False,
            comment="Document title",
        ),
        sa.Column(
            "document_type",
            sa.String(100),
            nullable=False,
            index=True,
            comment="Type: reglamento, directiva, orden, etc.",
        ),
        sa.Column(
            "document_number",
            sa.String(100),
            nullable=True,
            comment="Official document number (e.g., RD 2822/1998)",
        ),
        # Storage
        sa.Column(
            "filename",
            sa.String(255),
            nullable=False,
            comment="Original filename",
        ),
        sa.Column(
            "stored_filename",
            sa.String(255),
            unique=True,
            nullable=False,
            comment="UUID-based stored filename",
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=False,
            comment="File size in bytes",
        ),
        sa.Column(
            "file_hash",
            sa.String(64),
            unique=True,
            nullable=False,
            comment="SHA256 hash for deduplication",
        ),
        # Processing status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="Status: pending, processing, indexed, failed",
        ),
        sa.Column(
            "processing_progress",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Processing progress 0-100",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if processing failed",
        ),
        # Processing results
        sa.Column(
            "total_pages",
            sa.Integer(),
            nullable=True,
            comment="Total pages in document",
        ),
        sa.Column(
            "total_chunks",
            sa.Integer(),
            nullable=True,
            comment="Total chunks created",
        ),
        sa.Column(
            "extraction_method",
            sa.String(50),
            nullable=True,
            comment="Extraction method: docling or pymupdf",
        ),
        # Additional metadata
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Document description",
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=True,
            comment="Tags for categorization",
        ),
        sa.Column(
            "publication_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Official publication date",
        ),
        # Activation control
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether document is active for RAG queries",
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When document was activated",
        ),
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When document was deactivated",
        ),
        # Versioning
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Document version number",
        ),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id", ondelete="SET NULL"),
            nullable=True,
            comment="Previous version this document supersedes",
        ),
        # Audit
        sa.Column(
            "uploaded_by",
            sa.String(100),
            nullable=True,
            comment="Username who uploaded the document",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When document was successfully indexed",
        ),
    )

    # Create composite index for common queries
    op.create_index(
        "ix_regulatory_documents_status_active",
        "regulatory_documents",
        ["status", "is_active"],
    )

    # =========================================================================
    # 2. Create document_chunks table
    # =========================================================================
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Identification
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            comment="Sequential index within document",
        ),
        sa.Column(
            "qdrant_point_id",
            sa.String(100),
            unique=True,
            nullable=False,
            comment="Unique point ID in Qdrant",
        ),
        # Content
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Chunk text content",
        ),
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
            comment="SHA256 hash of content",
        ),
        # Position metadata
        sa.Column(
            "page_numbers",
            postgresql.JSONB(),
            nullable=False,
            comment="Array of page numbers this chunk spans",
        ),
        sa.Column(
            "section_title",
            sa.String(500),
            nullable=True,
            comment="Section title if detected",
        ),
        sa.Column(
            "article_number",
            sa.String(50),
            nullable=True,
            comment="Article number if detected",
        ),
        sa.Column(
            "heading_hierarchy",
            postgresql.JSONB(),
            nullable=True,
            comment="Heading hierarchy for context",
        ),
        # Statistics
        sa.Column(
            "char_count",
            sa.Integer(),
            nullable=False,
            comment="Character count",
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=True,
            comment="Token count (estimated)",
        ),
        sa.Column(
            "chunk_type",
            sa.String(50),
            nullable=False,
            server_default="content",
            comment="Chunk type: content, header, table, etc.",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            comment="Additional metadata",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Unique constraint for document + chunk index
    op.create_unique_constraint(
        "uq_document_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )

    # =========================================================================
    # 3. Create rag_queries table
    # =========================================================================
    op.create_table(
        "rag_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "query_text",
            sa.Text(),
            nullable=False,
            comment="User's query text",
        ),
        sa.Column(
            "query_hash",
            sa.String(64),
            nullable=False,
            index=True,
            comment="SHA256 hash for cache lookup",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who made the query",
        ),
        sa.Column(
            "conversation_id",
            sa.String(100),
            nullable=True,
            comment="Conversation ID for grouping",
        ),
        # Performance metrics
        sa.Column(
            "retrieval_ms",
            sa.Integer(),
            nullable=True,
            comment="Vector retrieval time in ms",
        ),
        sa.Column(
            "rerank_ms",
            sa.Integer(),
            nullable=True,
            comment="Re-ranking time in ms",
        ),
        sa.Column(
            "llm_ms",
            sa.Integer(),
            nullable=True,
            comment="LLM generation time in ms",
        ),
        sa.Column(
            "total_ms",
            sa.Integer(),
            nullable=False,
            comment="Total pipeline time in ms",
        ),
        # Results
        sa.Column(
            "num_results_retrieved",
            sa.Integer(),
            nullable=False,
            comment="Number of chunks retrieved from Qdrant",
        ),
        sa.Column(
            "num_results_reranked",
            sa.Integer(),
            nullable=False,
            comment="Number of chunks after re-ranking",
        ),
        sa.Column(
            "num_results_used",
            sa.Integer(),
            nullable=False,
            comment="Number of chunks sent to LLM",
        ),
        sa.Column(
            "reranker_used",
            sa.String(50),
            nullable=True,
            comment="Reranker model used",
        ),
        sa.Column(
            "response_generated",
            sa.Boolean(),
            nullable=False,
            comment="Whether a response was generated",
        ),
        sa.Column(
            "llm_model",
            sa.String(100),
            nullable=True,
            comment="LLM model used for generation",
        ),
        # Caching
        sa.Column(
            "cache_hit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether result was from cache",
        ),
        sa.Column(
            "cache_key",
            sa.String(100),
            nullable=True,
            comment="Redis cache key if cached",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )

    # =========================================================================
    # 4. Create query_citations table
    # =========================================================================
    op.create_table(
        "query_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "query_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rag_queries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "rank",
            sa.Integer(),
            nullable=False,
            comment="Rank position in results",
        ),
        sa.Column(
            "similarity_score",
            sa.Numeric(5, 4),
            nullable=True,
            comment="Vector similarity score",
        ),
        sa.Column(
            "rerank_score",
            sa.Numeric(5, 4),
            nullable=True,
            comment="Re-ranking score",
        ),
        sa.Column(
            "used_in_context",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether chunk was sent to LLM",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # =========================================================================
    # Drop tables in reverse order (respecting foreign keys)
    # =========================================================================
    op.drop_table("query_citations")
    op.drop_table("rag_queries")
    op.drop_index("ix_regulatory_documents_status_active", table_name="regulatory_documents")
    op.drop_constraint("uq_document_chunk_index", "document_chunks", type_="unique")
    op.drop_table("document_chunks")
    op.drop_table("regulatory_documents")
