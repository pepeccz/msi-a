"""
Entity Extraction Service for Context Memory.

Extracts mentions of vehicle elements, brands, and models from conversation history.
Uses local LLM (qwen2.5:3b) for fast, cheap extraction.
"""

import json
import re
from typing import Any

import structlog

from shared.llm_router import TaskType, get_llm_router

logger = structlog.get_logger(__name__)


EXTRACTION_PROMPT = '''Extrae del siguiente historial de conversación:

1. ELEMENTOS mencionados (ej: escape, suspensión, subchasis, luces, etc.)
2. MARCA del vehículo (ej: Honda, BMW, Mercedes)
3. MODELO del vehículo (ej: CBF600, R1200, Sprinter)

Historial:
{history}

Responde SOLO con JSON (sin markdown):
{{"elementos": ["elemento1", "elemento2"], "marca": "...", "modelo": "..."}}

Si no encuentras algo, usa null.
'''


class EntityExtractionService:
    """Extract entities from conversation history for context memory."""
    
    def __init__(self):
        self._llm_router = None
    
    async def extract_entities(
        self,
        message_history: list[dict[str, Any]],
        max_messages: int = 5,
    ) -> dict[str, Any]:
        """
        Extract entities from recent message history.
        
        Args:
            message_history: List of messages (role, content)
            max_messages: How many recent messages to analyze
        
        Returns:
            Dict with elementos, marca, modelo (or None if not found)
        """
        if not message_history:
            return {"elementos": [], "marca": None, "modelo": None}
        
        # Take last N messages
        recent = message_history[-max_messages:]
        history_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in recent
        ])
        
        # Try LLM extraction first
        llm_result = await self._extract_with_llm(history_text)
        if llm_result:
            logger.info(
                "entity_extraction_llm_success",
                elementos=llm_result.get("elementos", []),
                marca=llm_result.get("marca"),
                modelo=llm_result.get("modelo"),
            )
            return llm_result
        
        # Fallback to regex patterns
        fallback_result = self._extract_with_regex(history_text)
        logger.info(
            "entity_extraction_fallback",
            elementos=fallback_result.get("elementos", []),
            marca=fallback_result.get("marca"),
            modelo=fallback_result.get("modelo"),
        )
        return fallback_result
    
    async def _extract_with_llm(self, history_text: str) -> dict[str, Any] | None:
        """Extract using local LLM (Tier 1 - fast)."""
        try:
            if self._llm_router is None:
                self._llm_router = get_llm_router()
            
            prompt = EXTRACTION_PROMPT.format(history=history_text[:1000])  # Limit context
            
            response = await self._llm_router.invoke(
                task_type=TaskType.EXTRACTION,
                messages=[{"role": "user", "content": prompt}],
            )
            
            content = response.content.strip()
            
            # Remove markdown if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                if content.startswith("json"):
                    content = content[4:].strip()
            
            data = json.loads(content)
            
            # Normalize
            elementos = data.get("elementos") or []
            marca = data.get("marca")
            modelo = data.get("modelo")
            
            return {
                "elementos": [e.lower().strip() for e in elementos if e],
                "marca": marca.strip() if marca else None,
                "modelo": modelo.strip().upper() if modelo else None,
            }
            
        except Exception as e:
            logger.warning("entity_extraction_llm_failed", error=str(e))
            return None
    
    def _extract_with_regex(self, history_text: str) -> dict[str, Any]:
        """Fallback regex extraction (basic)."""
        # Common elements
        element_patterns = [
            r"\b(escape|escapes)\b",
            r"\b(suspensión|suspension)\b",
            r"\b(subchasis|bastidor)\b",
            r"\b(faro|faros|luces|luz)\b",
            r"\b(manillar|manillares)\b",
            r"\b(retrovisores?|espejo)\b",
            r"\b(sillin|asiento)\b",
            r"\b(rueda|ruedas|llanta|llantas)\b",
        ]
        
        elementos = []
        for pattern in element_patterns:
            matches = re.findall(pattern, history_text.lower())
            if matches:
                elementos.extend(matches)
        
        # Deduplicate
        elementos = list(set(elementos))
        
        # Basic marca/modelo detection (very naive)
        marca_match = re.search(r"\b(Honda|BMW|Yamaha|Kawasaki|Suzuki|Mercedes|Hymer)\b", history_text, re.I)
        marca = marca_match.group(1).strip() if marca_match else None
        
        modelo_match = re.search(r"\b([A-Z]{2,}[\d]{2,}[A-Z]*)\b", history_text)
        modelo = modelo_match.group(1).strip().upper() if modelo_match else None
        
        return {
            "elementos": elementos,
            "marca": marca,
            "modelo": modelo,
        }


# Singleton
_service: EntityExtractionService | None = None


def get_entity_extraction_service() -> EntityExtractionService:
    """Get singleton EntityExtractionService instance."""
    global _service
    if _service is None:
        _service = EntityExtractionService()
    return _service
