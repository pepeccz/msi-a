"""
Document Processor Worker - Processes documents asynchronously via Redis Streams.

This worker listens to the document_processing_stream and processes
documents through the complete pipeline:
1. PDF extraction (Docling or PyMuPDF fallback)
2. Semantic chunking
3. Embedding generation
4. Qdrant indexing
"""

import asyncio
import logging
import uuid
from datetime import datetime, UTC
from pathlib import Path

from sqlalchemy import select

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.redis_client import (
    get_redis_client,
    create_consumer_group,
    read_from_stream,
    acknowledge_message,
)
from database.connection import get_async_session
from database.models import RegulatoryDocument, DocumentChunk
from api.services.document_processor import get_document_processor
from api.services.embedding_service import get_embedding_service
from api.services.qdrant_service import get_qdrant_service, reset_qdrant_service

logger = logging.getLogger(__name__)

PROCESSING_STREAM = "document_processing_stream"
CONSUMER_GROUP = "document_workers"
MAX_BACKOFF_SECONDS = 60


async def wait_for_services(max_attempts: int = 10) -> bool:
    """
    Wait for Qdrant and Redis to be available with exponential backoff.

    This function ensures all required services are reachable before
    the worker starts processing messages.

    Args:
        max_attempts: Maximum number of connection attempts

    Returns:
        True if all services are ready, False if max attempts reached
    """
    for attempt in range(max_attempts):
        try:
            # Test Redis connection
            redis = get_redis_client()
            await redis.ping()
            logger.debug("Redis connection OK")

            # Test Qdrant connection (includes retry internally)
            qdrant = get_qdrant_service()
            health_ok = await qdrant.health_check()
            if not health_ok:
                raise ConnectionError("Qdrant health check returned False")

            logger.info("All services are ready")
            return True

        except Exception as e:
            backoff = min(5 * (2 ** attempt), MAX_BACKOFF_SECONDS)
            logger.warning(
                f"Services not ready (attempt {attempt + 1}/{max_attempts}): {e}. "
                f"Retrying in {backoff}s..."
            )
            # Reset Qdrant service to force fresh connection on next attempt
            reset_qdrant_service()
            await asyncio.sleep(backoff)

    logger.error("Services did not become available after max attempts")
    return False


async def process_document(document_id: str):
    """
    Process a single document through the complete pipeline.

    Pipeline steps:
    1. Extract PDF content (0% -> 20%)
    2. Chunk document (20% -> 40%)
    3. Generate embeddings (40% -> 70%)
    4. Index in Qdrant (70% -> 90%)
    5. Save chunks to DB (90% -> 100%)

    Args:
        document_id: UUID of the document to process
    """
    settings = get_settings()

    async with get_async_session() as session:
        # Fetch document
        result = await session.execute(
            select(RegulatoryDocument).where(RegulatoryDocument.id == uuid.UUID(document_id))
        )
        doc = result.scalar_one_or_none()

        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        try:
            # Update status to processing
            doc.status = "processing"
            doc.processing_progress = 0
            doc.error_message = None
            await session.commit()

            logger.info(f"Starting processing of document {document_id}: {doc.title}")

            processor = get_document_processor()
            embedding_service = get_embedding_service()
            qdrant_service = get_qdrant_service()

            # 1. Extract PDF content
            logger.info(f"[{document_id}] Step 1: Extracting PDF...")
            pdf_path = Path(settings.DOCUMENT_UPLOAD_DIR) / doc.stored_filename

            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            extraction = await processor.extract_pdf(pdf_path)
            doc.extraction_method = extraction["method"]
            doc.total_pages = extraction["pages"]
            doc.processing_progress = 20
            await session.commit()

            logger.info(
                f"[{document_id}] PDF extracted with {extraction['method']}: "
                f"{len(extraction['content'])} chars, {extraction['pages']} pages"
            )

            # 2. Chunk document
            logger.info(f"[{document_id}] Step 2: Chunking document...")
            chunks = await processor.chunk_document(
                extraction["content"],
                extraction.get("metadata")
            )
            doc.total_chunks = len(chunks)
            doc.processing_progress = 40
            await session.commit()

            logger.info(f"[{document_id}] Created {len(chunks)} chunks")

            # 2.5 Extract section mappings with LLM
            logger.info(f"[{document_id}] Step 2.5: Extracting section mappings with LLM...")
            try:
                section_mappings = await processor.extract_section_mappings_with_llm(
                    chunks=chunks,
                    document_title=doc.title
                )
                doc.section_mappings = section_mappings
                doc.processing_progress = 50
                await session.commit()
                logger.info(f"[{document_id}] Extracted {len(section_mappings)} section mappings")
            except Exception as e:
                logger.warning(f"[{document_id}] Section mapping extraction failed (non-blocking): {e}")
                # Don't block the pipeline if LLM extraction fails

            # 3. Generate embeddings (batch)
            logger.info(f"[{document_id}] Step 3: Generating embeddings...")
            texts = [chunk["content"] for chunk in chunks]
            embeddings = await embedding_service.generate_batch_embeddings(texts)
            doc.processing_progress = 70
            await session.commit()

            logger.info(f"[{document_id}] Generated {len(embeddings)} embeddings")

            # 4. Prepare chunks for Qdrant and DB
            qdrant_chunks = []
            db_chunks = []

            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = uuid.uuid4()
                qdrant_point_id = str(uuid.uuid4())

                # Qdrant payload
                qdrant_chunks.append({
                    "chunk_id": chunk_id,
                    "document_id": doc.id,
                    "qdrant_point_id": qdrant_point_id,
                    "embedding": embedding,
                    "content": chunk["content"],
                    "page_numbers": chunk.get("page_numbers", [1]),
                    "article_number": chunk.get("article_number"),
                    "section_title": chunk.get("section_title"),
                    "is_active": doc.is_active
                })

                # DB record
                db_chunks.append(DocumentChunk(
                    id=chunk_id,
                    document_id=doc.id,
                    chunk_index=idx,
                    qdrant_point_id=qdrant_point_id,
                    content=chunk["content"],
                    content_hash=chunk["content_hash"],
                    page_numbers=chunk.get("page_numbers", [1]),
                    article_number=chunk.get("article_number"),
                    section_title=chunk.get("section_title"),
                    heading_hierarchy=chunk.get("heading_hierarchy", []),
                    char_count=chunk["char_count"],
                    chunk_type="content"
                ))

            # 5. Index in Qdrant
            logger.info(f"[{document_id}] Step 4: Indexing in Qdrant...")
            await qdrant_service.upsert_chunks(qdrant_chunks)
            doc.processing_progress = 90
            await session.commit()

            logger.info(f"[{document_id}] Indexed {len(qdrant_chunks)} chunks in Qdrant")

            # 6. Save chunks to DB
            logger.info(f"[{document_id}] Step 5: Saving chunks to database...")
            session.add_all(db_chunks)
            doc.status = "indexed"
            doc.processing_progress = 100
            doc.indexed_at = datetime.now(UTC)
            await session.commit()

            logger.info(
                f"Document {document_id} processed successfully: "
                f"{len(chunks)} chunks, method={extraction['method']}"
            )

        except Exception as e:
            logger.exception(f"Error processing document {document_id}")
            doc.status = "failed"
            doc.error_message = str(e)[:1000]  # Truncate long errors
            await session.commit()


async def main():
    """Main worker loop - listens to Redis Streams and processes documents."""
    # Configure logging first
    configure_logging()

    logger.info("Document processor worker starting...")

    # Wait for all required services to be available
    if not await wait_for_services():
        logger.error("Could not connect to required services after max attempts, exiting")
        return

    settings = get_settings()
    redis = get_redis_client()

    logger.info(f"Stream: {PROCESSING_STREAM}, Group: {CONSUMER_GROUP}")

    # Create consumer group using robust helper (handles BUSYGROUP automatically)
    try:
        await create_consumer_group(PROCESSING_STREAM, CONSUMER_GROUP)
        logger.info(f"Consumer group ready: {CONSUMER_GROUP}")
    except Exception as e:
        # Helper will auto-create group on first read_from_stream if needed
        logger.warning(f"Initial consumer group creation failed, will retry on first message: {e}")

    consumer_name = f"worker-{uuid.uuid4().hex[:8]}"
    logger.info(f"Consumer name: {consumer_name}")

    # Process pending messages first (in case of worker restart)
    await process_pending_messages(redis, consumer_name)

    # Main loop with exponential backoff on errors
    consecutive_errors = 0

    while True:
        try:
            # Read from stream with automatic NOGROUP handling
            # read_from_stream will auto-create the group if it doesn't exist
            raw_messages = await read_from_stream(
                stream=PROCESSING_STREAM,
                group=CONSUMER_GROUP,
                consumer=consumer_name,
                count=1,
                block_ms=5000
            )

            # Reset error counter on successful stream read
            consecutive_errors = 0

            for message_id, message_data in raw_messages:
                document_id = message_data.get("document_id")

                if not document_id:
                    logger.warning(f"Message {message_id} missing document_id")
                    await acknowledge_message(PROCESSING_STREAM, CONSUMER_GROUP, message_id)
                    continue

                logger.info(f"Processing message {message_id}: document {document_id}")

                try:
                    await process_document(document_id)
                except Exception as e:
                    logger.exception(f"Failed to process document {document_id}: {e}")

                # Acknowledge message regardless of success/failure
                # (failure is recorded in DB, message shouldn't be reprocessed)
                await acknowledge_message(PROCESSING_STREAM, CONSUMER_GROUP, message_id)

        except Exception as e:
            consecutive_errors += 1
            # Exponential backoff: 5s, 10s, 20s, 40s, 60s (capped)
            backoff = min(5 * (2 ** min(consecutive_errors - 1, 4)), MAX_BACKOFF_SECONDS)

            error_msg = str(e).lower()
            is_connection_error = "connection" in error_msg or "resolution" in error_msg

            logger.exception(
                f"Worker error (attempt {consecutive_errors}, retry in {backoff}s): {e}"
            )

            # Reset Qdrant service on connection errors to force reconnection
            if is_connection_error:
                logger.info("Connection error detected, resetting Qdrant service...")
                reset_qdrant_service()

            await asyncio.sleep(backoff)


async def process_pending_messages(redis, consumer_name: str):
    """Process any pending messages from previous worker runs."""
    logger.info("Checking for pending messages...")

    try:
        # Get pending messages for this consumer group
        pending = await redis.xpending_range(
            PROCESSING_STREAM,
            CONSUMER_GROUP,
            min="-",
            max="+",
            count=100
        )

        if not pending:
            logger.info("No pending messages found")
            return

        logger.info(f"Found {len(pending)} pending messages")

        for entry in pending:
            message_id = entry["message_id"]
            idle_time = entry.get("time_since_delivered", 0)

            # Only claim messages that have been pending for > 30 seconds
            if idle_time > 30000:  # 30 seconds in milliseconds
                # Claim the message
                claimed = await redis.xclaim(
                    PROCESSING_STREAM,
                    CONSUMER_GROUP,
                    consumer_name,
                    min_idle_time=30000,
                    message_ids=[message_id]
                )

                for msg_id, msg_data in claimed:
                    document_id = msg_data.get("document_id")
                    if document_id:
                        logger.info(f"Reprocessing claimed message {msg_id}: document {document_id}")
                        try:
                            await process_document(document_id)
                        except Exception as e:
                            logger.exception(f"Failed to reprocess document {document_id}")

                        await acknowledge_message(PROCESSING_STREAM, CONSUMER_GROUP, msg_id)

    except Exception as e:
        logger.warning(f"Error processing pending messages: {e}")


if __name__ == "__main__":
    asyncio.run(main())
