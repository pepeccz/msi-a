-- MSI-a RAG Data Cleanup
-- Date: 2026-02-06
-- Purpose: Delete all RAG data while preserving table structure
-- Reason: RAG system temporarily disabled, will be redesigned

-- ============================================
-- CLEANUP ORDER (respects FK constraints)
-- ============================================

BEGIN;

-- 1. Delete query citations (depends on rag_queries + document_chunks)
DELETE FROM query_citations;

-- 2. Delete RAG queries (depends on admin_users)
DELETE FROM rag_queries;

-- 3. Delete document chunks (depends on regulatory_documents)
DELETE FROM document_chunks;

-- 4. Delete regulatory documents (top-level)
DELETE FROM regulatory_documents;

-- ============================================
-- VERIFICATION
-- ============================================

-- Check all tables are empty
SELECT 'regulatory_documents' as table_name, COUNT(*) as remaining_rows FROM regulatory_documents
UNION ALL
SELECT 'document_chunks', COUNT(*) FROM document_chunks
UNION ALL
SELECT 'rag_queries', COUNT(*) FROM rag_queries
UNION ALL
SELECT 'query_citations', COUNT(*) FROM query_citations;

COMMIT;

-- ============================================
-- NOTES
-- ============================================
-- Tables are NOT dropped (preserved for future use)
-- Migrations are NOT rolled back (preserve schema)
-- Qdrant vectors should be deleted separately via API/CLI
-- ============================================
