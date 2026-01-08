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
        Split document into semantic chunks with heading hierarchy.

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
                - heading_hierarchy: List of parent section titles
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

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

        # Process chunks with metadata extraction and hierarchy
        chunks = []
        current_position = 0

        for idx, chunk_text in enumerate(chunks_text):
            # Find chunk position in original content for hierarchy extraction
            chunk_start = content.find(chunk_text, current_position)
            if chunk_start == -1:
                # Fallback: use current position if exact match not found
                chunk_start = current_position

            # Extract heading hierarchy up to this chunk
            heading_hierarchy = self._extract_heading_hierarchy(content, chunk_start)

            chunk_data = {
                "content": chunk_text,
                "content_hash": hashlib.sha256(chunk_text.encode()).hexdigest(),
                "char_count": len(chunk_text),
                "chunk_index": idx,
                "page_numbers": self._extract_page_numbers(chunk_text),
                "article_number": self._extract_article_number(chunk_text),
                "section_title": self._extract_section_title(chunk_text),
                "heading_hierarchy": heading_hierarchy,
            }
            chunks.append(chunk_data)

            # Update position for next search
            current_position = chunk_start + len(chunk_text)

        logger.info(f"Created {len(chunks)} chunks with heading hierarchy")
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

    def _extract_heading_hierarchy(
        self,
        full_content: str,
        chunk_start: int
    ) -> list[str]:
        """
        Extract heading hierarchy up to the chunk position.

        Analyzes both markdown headers (#, ##, ###, ####) AND numbered sections
        in list format (- 6.2. Title) commonly produced by Docling.

        Args:
            full_content: Complete document content
            chunk_start: Starting position of the chunk in the document

        Returns:
            List of section titles representing the hierarchy,
            e.g., ['6. Alumbrado', '6.2. Luces de cruce']
        """
        # Analyze only content before the chunk
        content_before = full_content[:chunk_start]

        hierarchy_stack: list[tuple[int, str]] = []

        # Pattern 1: Markdown headers (# to ####)
        md_header_pattern = r'^(#{1,4})\s+(.+?)$'

        # Pattern 2: Numbered sections in list format (- 6.2. Title or 6.2. Title)
        # Captures section number (e.g., "6.2.") and title
        # Tolerates leading whitespace and optional dash
        numbered_section_pattern = r'^\s*(?:-\s+)?(\d+(?:\.\d+)*\.?)\s+([A-ZÁÉÍÓÚÑ][^\n]{3,100})$'

        # Collect all matches with their positions
        all_matches: list[tuple[int, int, str]] = []  # (position, level, title)

        # Find markdown headers
        for match in re.finditer(md_header_pattern, content_before, re.MULTILINE):
            level = len(match.group(1))  # 1-4 based on # count
            title = match.group(2).strip()
            all_matches.append((match.start(), level, title))

        # Find numbered sections (level based on depth: 6.=1, 6.2.=2, 6.2.2.=3)
        for match in re.finditer(numbered_section_pattern, content_before, re.MULTILINE):
            section_num = match.group(1)
            title = match.group(2).strip()
            # Count dots to determine level (6. -> 1, 6.2. -> 2, 6.2.2. -> 3)
            level = section_num.count('.')
            if not section_num.endswith('.'):
                level += 1
            # Include section number in title for context
            full_title = f"{section_num} {title}"
            all_matches.append((match.start(), level, full_title))

        # Sort by position and build hierarchy
        all_matches.sort(key=lambda x: x[0])

        for _, level, title in all_matches:
            # Remove levels that are equal or lower than current
            while hierarchy_stack and hierarchy_stack[-1][0] >= level:
                hierarchy_stack.pop()
            hierarchy_stack.append((level, title))

        # Return only the titles (without level numbers)
        return [title for _, title in hierarchy_stack]

    async def extract_section_mappings_with_llm(
        self,
        chunks: list[dict[str, Any]],
        document_title: str | None = None
    ) -> dict[str, str]:
        """
        Use LLM to extract section number → description mappings.

        Analyzes the first chunks with heading_hierarchy to build a mapping
        of section numbers to their descriptive titles. This mapping is used
        to enrich RAG search results with semantic context.

        Args:
            chunks: List of chunks with heading_hierarchy and section_title
            document_title: Document title for context

        Returns:
            Dict mapping section numbers to descriptions,
            e.g., {"6.1": "Luces de carretera", "6.2": "Luces de cruce"}
        """
        import json

        import httpx

        # Select chunks with section info (max 20 for context)
        relevant_chunks = []
        for chunk in chunks[:50]:
            if chunk.get("heading_hierarchy") or chunk.get("section_title"):
                relevant_chunks.append({
                    "hierarchy": chunk.get("heading_hierarchy", []),
                    "section": chunk.get("section_title"),
                    "preview": chunk["content"][:200]
                })
            if len(relevant_chunks) >= 20:
                break

        if not relevant_chunks:
            logger.info("No relevant chunks found for section mapping extraction")
            return {}

        system_prompt = """Eres un experto en análisis de documentos normativos.
Tu tarea es extraer un mapeo de números de sección a sus títulos descriptivos.

REGLAS:
1. Solo extrae secciones principales (ej: 6.1, 6.2, no subsecciones como 6.1.2.3)
2. El título debe ser descriptivo y corto (máx 50 caracteres)
3. Responde SOLO con JSON válido, sin explicaciones adicionales
4. Si no hay secciones claras, responde {}

EJEMPLO de salida esperada:
{
  "6.1": "Luces de carretera",
  "6.2": "Luces de cruce",
  "6.3": "Luces antiniebla delanteras"
}"""

        user_message = f"""Documento: {document_title or 'Normativa'}

Estructura detectada en los primeros chunks:
{json.dumps(relevant_chunks, indent=2, ensure_ascii=False)}

Extrae el mapeo de secciones principales (número → título descriptivo):"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                        "HTTP-Referer": self.settings.SITE_URL or "https://msi-automotive.com",
                    },
                    json={
                        "model": self.settings.LLM_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.1  # Low temperature for consistency
                    }
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]

                # Parse JSON from response, handling markdown code blocks
                if "```" in content:
                    # Extract content between code blocks
                    parts = content.split("```")
                    if len(parts) >= 2:
                        content = parts[1]
                        if content.startswith("json"):
                            content = content[4:]

                result = json.loads(content.strip())
                logger.info(f"LLM extracted {len(result)} section mappings")
                return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return {}
        except httpx.HTTPStatusError as e:
            logger.warning(f"LLM API error: {e.response.status_code} - {e.response.text}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to extract section mappings with LLM: {e}")
            return {}

    def calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA256 hash of file content."""
        return hashlib.sha256(file_content).hexdigest()


@lru_cache
def get_document_processor() -> DocumentProcessor:
    """Get singleton DocumentProcessor instance."""
    return DocumentProcessor()
