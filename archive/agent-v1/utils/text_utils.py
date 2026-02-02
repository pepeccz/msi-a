"""Text normalization and matching utilities for the agent."""

import logging
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.
    
    Performs:
    - Unicode normalization (decompose accents)
    - Lowercase conversion
    - Stripping whitespace
    
    Args:
        text: Input text to normalize
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    
    # Normalize unicode (decompose accents)
    normalized = unicodedata.normalize('NFD', text.lower())
    # Remove combining characters (accents)
    ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Strip whitespace
    return ascii_text.strip()


def normalize_field_key(key: str) -> str:
    """
    Normalize a field key for matching.
    
    Handles common variations:
    - ñ -> n
    - accented vowels -> plain vowels
    - spaces -> underscores
    - lowercase
    
    This allows the LLM to use natural Spanish (contraseña) while
    the DB uses ASCII-safe keys (contrasena).
    
    Args:
        key: Field key to normalize
        
    Returns:
        Normalized field key in snake_case
    """
    if not key:
        return ""
    
    # Normalize unicode (decompose accents)
    normalized = unicodedata.normalize('NFKD', key)
    # Remove combining characters (accents)
    ascii_key = ''.join(c for c in normalized if not unicodedata.combining(c))
    # Replace ñ explicitly (it doesn't decompose)
    ascii_key = ascii_key.replace('ñ', 'n').replace('Ñ', 'N')
    # Lowercase and replace spaces
    return ascii_key.lower().replace(' ', '_')


def fuzzy_match(query: str, candidates: list[str], threshold: float = 0.6) -> str | None:
    """
    Find the best matching candidate for a query using simple string similarity.
    
    Args:
        query: The search query
        candidates: List of candidate strings to match against
        threshold: Minimum similarity score (0.0-1.0) to consider a match
        
    Returns:
        The best matching candidate, or None if no match above threshold
    """
    if not query or not candidates:
        return None
    
    normalized_query = normalize_text(query)
    if not normalized_query:
        return None
    
    best_match: str | None = None
    best_score: float = 0.0
    
    for candidate in candidates:
        if not candidate:
            continue
            
        normalized_candidate = normalize_text(candidate)
        if not normalized_candidate:
            continue
        
        # Calculate simple word overlap score
        query_words = set(normalized_query.split())
        candidate_words = set(normalized_candidate.split())
        
        if not query_words or not candidate_words:
            continue
        
        # Jaccard similarity: intersection / union
        intersection = len(query_words & candidate_words)
        union = len(query_words | candidate_words)
        
        if union > 0:
            score = intersection / union
        else:
            score = 0.0
        
        # Boost score for exact substring match
        if normalized_query in normalized_candidate or normalized_candidate in normalized_query:
            score = max(score, 0.8)
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    
    return best_match


def fuzzy_match_with_scores(query: str, candidates: list[str]) -> list[tuple[str, float]]:
    """
    Find all candidates with their similarity scores.
    
    Args:
        query: The search query
        candidates: List of candidate strings to match against
        
    Returns:
        List of tuples (candidate, score) sorted by score descending
    """
    if not query or not candidates:
        return []
    
    normalized_query = normalize_text(query)
    if not normalized_query:
        return []
    
    results: list[tuple[str, float]] = []
    query_words = set(normalized_query.split())
    
    for candidate in candidates:
        if not candidate:
            continue
            
        normalized_candidate = normalize_text(candidate)
        if not normalized_candidate:
            continue
        
        candidate_words = set(normalized_candidate.split())
        
        if not query_words or not candidate_words:
            continue
        
        # Jaccard similarity
        intersection = len(query_words & candidate_words)
        union = len(query_words | candidate_words)
        
        if union > 0:
            score = intersection / union
        else:
            score = 0.0
        
        # Boost for substring match
        if normalized_query in normalized_candidate or normalized_candidate in normalized_query:
            score = max(score, 0.8)
        
        results.append((candidate, score))
    
    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results
