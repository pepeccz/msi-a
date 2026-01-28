"""
RAG Query Classifier - Determines query complexity for LLM routing.

Classifies incoming RAG queries as SIMPLE or COMPLEX to route them
to the appropriate LLM tier (local Ollama vs cloud OpenRouter).

Simple queries can be handled by faster/cheaper local models.
Complex queries require more capable cloud models.
"""

import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity levels for LLM routing."""
    SIMPLE = "simple"    # Can use local model (Tier 1-2)
    COMPLEX = "complex"  # Requires cloud model (Tier 3)


# Patterns indicating SIMPLE factual queries
SIMPLE_PATTERNS = [
    # Direct factual questions (Spanish)
    r"^¿cuánt[oa]s?\s",           # ¿Cuántos/Cuántas...?
    r"^¿qué (es|son|significa)\s",  # ¿Qué es/son/significa...?
    r"^¿cuál (es|son)\s",         # ¿Cuál es/son...?
    r"^¿dónde\s",                 # ¿Dónde...?
    r"^¿cuándo\s",                # ¿Cuándo...?
    
    # List/enumeration requests
    r"^list[ae]\s",               # Lista de...
    r"^enumera\s",                # Enumera...
    r"^menciona\s",               # Menciona...
    
    # Requirement queries
    r"requisitos\s+(para|de)\s",  # Requisitos para/de...
    r"documentos?\s+necesari",    # Documentos necesarios...
    r"qué\s+necesito\s+(para)?\s",  # ¿Qué necesito para...?
    
    # Specific lookups
    r"número\s+de\s",             # Número de...
    r"cantidad\s+de\s",           # Cantidad de...
    r"límite\s+de\s",             # Límite de...
    r"máximo\s+de\s",             # Máximo de...
    r"mínimo\s+de\s",             # Mínimo de...
    
    # Direct article/section references
    r"artículo\s+\d+",            # Artículo 5...
    r"punto\s+\d+",               # Punto 6.2...
    r"sección\s+\d+",             # Sección 3...
    r"anexo\s+[IVXLCDM\d]+",      # Anexo II...
]

# Patterns indicating COMPLEX analytical queries
COMPLEX_PATTERNS = [
    # Comparative questions
    r"diferencia\s+entre",        # Diferencia entre...
    r"compar[ae]\s",              # Compara/Compare...
    r"versus|vs\.?",              # X versus Y
    r"mejor\s+opción",            # Mejor opción...
    
    # Analytical/reasoning questions
    r"¿por\s+qué\s",              # ¿Por qué...?
    r"¿cómo\s+afecta",            # ¿Cómo afecta...?
    r"¿cómo\s+se\s+relaciona",    # ¿Cómo se relaciona...?
    r"explica\s+(el\s+)?porqué",  # Explica el porqué...
    r"analiza\s",                 # Analiza...
    
    # Multi-step reasoning
    r"ventajas\s+y\s+desventajas", # Ventajas y desventajas...
    r"pros\s+y\s+contras",        # Pros y contras...
    r"consecuencias\s+de",        # Consecuencias de...
    r"implicaciones\s+de",        # Implicaciones de...
    
    # Synthesis requests
    r"resume\s+(el|la|los|las)?\s*\w+\s+y",  # Resume X y Y
    r"integra\s",                 # Integra...
    r"sintetiza\s",               # Sintetiza...
    
    # Hypothetical/conditional
    r"¿qué\s+pasaría\s+si",       # ¿Qué pasaría si...?
    r"en\s+caso\s+de\s+que",      # En caso de que...
    r"si\s+\w+\s+entonces",       # Si X entonces...
    
    # Opinion/interpretation
    r"¿es\s+recomendable",        # ¿Es recomendable...?
    r"¿debería\s",                # ¿Debería...?
    r"interpreta\s",              # Interpreta...
]

# Keywords that add complexity
COMPLEXITY_KEYWORDS = {
    "high": [
        "comparar", "comparativa", "diferencias", "similitudes",
        "analizar", "análisis", "evaluar", "evaluación",
        "interpretar", "interpretación", "explicar", "explicación",
        "ventajas", "desventajas", "pros", "contras",
        "consecuencias", "implicaciones", "impacto",
        "hipotético", "supongamos", "imaginemos",
        "recomendación", "sugerencia", "consejo",
    ],
    "medium": [
        "relacionar", "conexión", "vínculo",
        "proceso", "procedimiento", "pasos",
        "excepciones", "casos especiales", "particularidades",
    ],
}

# Length thresholds
MAX_SIMPLE_QUERY_LENGTH = 150  # Queries longer than this tend to be complex


def classify_query(query: str) -> QueryComplexity:
    """
    Classify a RAG query as SIMPLE or COMPLEX.
    
    Uses pattern matching and heuristics to determine if a query
    can be handled by a local model or requires a cloud model.
    
    Args:
        query: The user's RAG query text
        
    Returns:
        QueryComplexity.SIMPLE or QueryComplexity.COMPLEX
    """
    query_lower = query.lower().strip()
    
    # Check for explicit complex patterns first (higher priority)
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            logger.debug(f"Query classified as COMPLEX (matched pattern: {pattern})")
            return QueryComplexity.COMPLEX
    
    # Check for high complexity keywords
    for keyword in COMPLEXITY_KEYWORDS["high"]:
        if keyword in query_lower:
            logger.debug(f"Query classified as COMPLEX (keyword: {keyword})")
            return QueryComplexity.COMPLEX
    
    # Check for simple patterns
    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            logger.debug(f"Query classified as SIMPLE (matched pattern: {pattern})")
            return QueryComplexity.SIMPLE
    
    # Length heuristic: very long queries tend to be complex
    if len(query) > MAX_SIMPLE_QUERY_LENGTH:
        # But check if it's just a long list of items
        if query.count(",") < 3 and query.count(" y ") < 2:
            logger.debug(f"Query classified as COMPLEX (length: {len(query)})")
            return QueryComplexity.COMPLEX
    
    # Check for medium complexity keywords (only if no simple patterns matched)
    medium_keyword_count = sum(
        1 for keyword in COMPLEXITY_KEYWORDS["medium"]
        if keyword in query_lower
    )
    if medium_keyword_count >= 2:
        logger.debug(f"Query classified as COMPLEX (multiple medium keywords)")
        return QueryComplexity.COMPLEX
    
    # Check for multiple question marks (compound questions)
    if query.count("?") > 1:
        logger.debug("Query classified as COMPLEX (multiple questions)")
        return QueryComplexity.COMPLEX
    
    # Check for conjunctions that indicate multiple topics
    conjunction_count = sum([
        query_lower.count(" y "),
        query_lower.count(" o "),
        query_lower.count(", además"),
        query_lower.count(", también"),
    ])
    if conjunction_count >= 3:
        logger.debug(f"Query classified as COMPLEX (many conjunctions: {conjunction_count})")
        return QueryComplexity.COMPLEX
    
    # Default to SIMPLE for short, straightforward queries
    if len(query) <= 80:
        logger.debug(f"Query classified as SIMPLE (short query: {len(query)} chars)")
        return QueryComplexity.SIMPLE
    
    # Default fallback: SIMPLE (prefer local when uncertain)
    # This is intentional to maximize cost savings while maintaining fallback
    logger.debug("Query classified as SIMPLE (default fallback)")
    return QueryComplexity.SIMPLE


def get_query_complexity_score(query: str) -> float:
    """
    Get a numeric complexity score for a query (0.0 to 1.0).
    
    Useful for metrics and fine-tuning routing thresholds.
    
    Args:
        query: The user's RAG query text
        
    Returns:
        Float from 0.0 (simple) to 1.0 (complex)
    """
    score = 0.0
    query_lower = query.lower().strip()
    
    # Complex pattern matches (high weight)
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            score += 0.3
    
    # High complexity keywords
    for keyword in COMPLEXITY_KEYWORDS["high"]:
        if keyword in query_lower:
            score += 0.15
    
    # Medium complexity keywords
    for keyword in COMPLEXITY_KEYWORDS["medium"]:
        if keyword in query_lower:
            score += 0.08
    
    # Length factor
    length_factor = min(len(query) / 300, 0.2)
    score += length_factor
    
    # Multiple questions
    if query.count("?") > 1:
        score += 0.15
    
    # Conjunctions
    conjunction_count = query_lower.count(" y ") + query_lower.count(" o ")
    score += min(conjunction_count * 0.05, 0.15)
    
    # Simple pattern matches reduce score
    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            score -= 0.1
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))


def should_use_local_model(
    query: str,
    context_length: int | None = None,
    force_cloud: bool = False
) -> bool:
    """
    Determine if a query should use a local model.
    
    Combines complexity classification with additional factors
    like context length and override flags.
    
    Args:
        query: The user's RAG query text
        context_length: Optional length of retrieved context
        force_cloud: If True, always use cloud model
        
    Returns:
        True if local model should be used
    """
    if force_cloud:
        return False
    
    complexity = classify_query(query)
    
    # If query is complex, use cloud
    if complexity == QueryComplexity.COMPLEX:
        return False
    
    # If context is very large, prefer cloud (better at long context)
    if context_length and context_length > 8000:
        logger.debug(f"Using cloud due to large context: {context_length} chars")
        return False
    
    # Otherwise, use local
    return True
