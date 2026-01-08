"""
Document Processor - PDF extraction and semantic chunking.

This service handles document processing for the RAG system,
including PDF extraction with Docling and semantic chunking.
"""

import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.config import get_settings

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Service for processing PDF documents for RAG indexing."""

    def __init__(self):
        self.settings = get_settings()

    async def extract_pdf(self, pdf_path: Path) -> dict[str, Any]:
        """
        Extract content from PDF using Docling (with PyMuPDF fallback).

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary containing:
                - method: Extraction method used
                - content: Extracted text content (markdown format)
                - metadata: Document metadata
                - pages: Total page count
        """
        logger.info(f"Extracting PDF: {pdf_path}")

        try:
            # Try Docling first (AI-powered extraction)
            return await self._extract_with_docling(pdf_path)
        except Exception as e:
            logger.warning(f"Docling extraction failed, falling back to PyMuPDF: {e}")
            return await self._extract_with_pymupdf(pdf_path)

    async def _extract_with_docling(self, pdf_path: Path) -> dict[str, Any]:
        """Extract PDF using Docling."""
        from docling.document_converter import DocumentConverter

        logger.debug("Using Docling for extraction")
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))

        # Get markdown content
        content = result.document.export_to_markdown()

        # Get metadata
        json_output = result.document.export_to_dict()
        metadata = json_output.get("metadata", {})

        # Count pages
        pages = len(result.document.pages) if hasattr(result.document, "pages") else None

        logger.info(f"Docling extracted {len(content)} characters, {pages} pages")

        return {
            "method": "docling",
            "content": content,
            "metadata": metadata,
            "pages": pages
        }

    async def _extract_with_pymupdf(self, pdf_path: Path) -> dict[str, Any]:
        """Extract PDF using PyMuPDF (fallback)."""
        import pymupdf

        logger.debug("Using PyMuPDF for extraction")
        doc = pymupdf.open(str(pdf_path))

        content_parts = []
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                content_parts.append(f"# Page {page_num}\n\n{text}")

        content = "\n\n".join(content_parts)

        logger.info(f"PyMuPDF extracted {len(content)} characters, {doc.page_count} pages")

        return {
            "method": "pymupdf",
            "content": content,
            "metadata": dict(doc.metadata) if doc.metadata else {},
            "pages": doc.page_count
        }

    async def chunk_document(
        self,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Split document into semantic chunks.

        Args:
            content: Document content (markdown format)
            metadata: Optional document metadata

        Returns:
            List of chunk dictionaries containing:
                - content: Chunk text
                - content_hash: SHA256 hash
                - char_count: Character count
                - chunk_index: Sequential index
                - page_numbers: Detected page numbers
                - article_number: Detected article reference
                - section_title: Detected section title
        """
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        logger.info(f"Chunking document ({len(content)} characters)")

        # Create splitter with semantic separators
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.RAG_CHUNK_SIZE,
            chunk_overlap=self.settings.RAG_CHUNK_OVERLAP,
            separators=[
                "\n## ",  # H2 headers
                "\n### ",  # H3 headers
                "\n#### ",  # H4 headers
                "\n# ",  # H1 headers
                "\n\n",  # Paragraphs
                "\n",  # Lines
                ". ",  # Sentences
                " ",  # Words
                ""
            ]
        )

        # Split content
        chunks_text = splitter.split_text(content)

        # Process chunks with metadata extraction
        chunks = []
        for idx, chunk_text in enumerate(chunks_text):
            chunk_data = {
                "content": chunk_text,
                "content_hash": hashlib.sha256(chunk_text.encode()).hexdigest(),
                "char_count": len(chunk_text),
                "chunk_index": idx,
                "page_numbers": self._extract_page_numbers(chunk_text),
                "article_number": self._extract_article_number(chunk_text),
                "section_title": self._extract_section_title(chunk_text),
            }
            chunks.append(chunk_data)

        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    def _extract_page_numbers(self, text: str) -> list[int]:
        """Extract page numbers from chunk text."""
        # Look for "# Page N" markers from PyMuPDF
        page_pattern = r"# Page (\d+)"
        matches = re.findall(page_pattern, text)
        if matches:
            return [int(m) for m in matches]

        # Default to page 1 if no markers found
        return [1]

    def _extract_article_number(self, text: str) -> str | None:
        """Extract article/section number from chunk text."""
        # Common Spanish regulatory article patterns
        patterns = [
            r"Artículo\s+(\d+(?:\.\d+)?)",
            r"Art\.\s*(\d+(?:\.\d+)?)",
            r"Sección\s+(\d+(?:\.\d+)?)",
            r"Capítulo\s+([IVXLCDM]+|\d+)",
            r"Anexo\s+([IVXLCDM]+|\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get the full match with context
                full_match = re.search(pattern.replace(r"(\d+(?:\.\d+)?)", r".{0,50}"), text, re.IGNORECASE)
                if full_match:
                    return full_match.group(0)[:50]
                return f"Art. {match.group(1)}"

        return None

    def _extract_section_title(self, text: str) -> str | None:
        """Extract section title from chunk text."""
        # Look for markdown headers
        header_pattern = r"^#+\s+(.+)$"
        match = re.search(header_pattern, text, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Clean up and truncate
            title = re.sub(r"\s+", " ", title)
            return title[:200] if len(title) > 200 else title

        # Look for first line that looks like a title
        lines = text.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            if len(first_line) < 100 and not first_line.endswith("."):
                return first_line

        return None

    def calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA256 hash of file content."""
        return hashlib.sha256(file_content).hexdigest()


@lru_cache
def get_document_processor() -> DocumentProcessor:
    """Get singleton DocumentProcessor instance."""
    return DocumentProcessor()
