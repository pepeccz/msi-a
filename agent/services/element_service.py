"""
MSI Automotive - Element Service for Agent.

Provides element catalog management, keyword matching, and element-based tariff resolution.
Supports the new hierarchical element system for precise tariff calculation.
"""

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import Element, ElementImage, TierElementInclusion, Warning
from shared.config import QUANTITY_PATTERNS, NEGATION_PATTERNS

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300

# Fuzzy matching threshold (0.0-1.0)
FUZZY_MATCH_THRESHOLD = 0.85


class ElementService:
    """
    Service for managing homologable elements and matching.

    This service provides:
    - Element catalog retrieval per category
    - Keyword-based element matching from user descriptions
    - Element details with images
    - Support for the hierarchical element system
    """

    def __init__(self):
        from shared.redis_client import get_redis_client

        self.redis = get_redis_client()

    async def get_elements_by_category(
        self,
        category_id: str,
        is_active: bool = True,
    ) -> list[dict]:
        """
        Get all elements for a specific vehicle category.

        Args:
            category_id: UUID of the vehicle category
            is_active: Filter by active status (default True)

        Returns:
            List of element dictionaries with basic info (no images)
        """
        cache_key = f"elements:category:{category_id}:active={is_active}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")

        # Fetch from database
        async with get_async_session() as session:
            query = select(Element).where(Element.category_id == category_id)

            if is_active:
                query = query.where(Element.is_active == True)

            query = query.order_by(Element.sort_order, Element.name)

            result = await session.execute(query)
            elements = result.scalars().all()

            data = [
                {
                    "id": str(elem.id),
                    "category_id": str(elem.category_id),
                    "parent_element_id": str(elem.parent_element_id) if elem.parent_element_id else None,
                    "code": elem.code,
                    "name": elem.name,
                    "description": elem.description,
                    "keywords": elem.keywords,
                    "aliases": elem.aliases or [],
                    "is_active": elem.is_active,
                    "sort_order": elem.sort_order,
                }
                for elem in elements
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

            return data

    async def get_base_elements_by_category(
        self,
        category_id: str,
        is_active: bool = True,
    ) -> list[dict]:
        """
        Get only BASE elements (without parent) for a specific vehicle category.

        Base elements are those with parent_element_id = NULL.
        Useful for initial matching without confusing with specific variants.

        Args:
            category_id: UUID of the vehicle category
            is_active: Filter by active status (default True)

        Returns:
            List of base element dictionaries (no variants included)
        """
        cache_key = f"elements:base:category:{category_id}:active={is_active}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")

        # Fetch from database - only elements without parent
        async with get_async_session() as session:
            query = (
                select(Element)
                .where(Element.category_id == category_id)
                .where(Element.parent_element_id.is_(None))  # Only base elements
            )

            if is_active:
                query = query.where(Element.is_active == True)

            query = query.order_by(Element.sort_order, Element.name)

            result = await session.execute(query)
            elements = result.scalars().all()

            data = [
                {
                    "id": str(elem.id),
                    "category_id": str(elem.category_id),
                    "parent_element_id": None,  # Base elements never have a parent
                    "code": elem.code,
                    "name": elem.name,
                    "description": elem.description,
                    "keywords": elem.keywords,
                    "aliases": elem.aliases or [],
                    "is_active": elem.is_active,
                    "sort_order": elem.sort_order,
                }
                for elem in elements
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

            return data

    async def get_element_variants(
        self,
        element_id: str | None = None,
        element_code: str | None = None,
        category_id: str | None = None,
    ) -> list[dict]:
        """
        Get variants (children) of a base element.

        Args:
            element_id: UUID of the parent element
            element_code: Code of the parent element (alternative to element_id)
            category_id: Filter by category (required if using element_code)

        Returns:
            List of variant dictionaries with variant-specific info:
            [
                {
                    "id": "uuid",
                    "code": "BOLA_SIN_MMR",
                    "name": "Bola de remolque sin aumento MMR",
                    "variant_type": "mmr_option",
                    "variant_code": "SIN_MMR",
                    "description": "..."
                },
                ...
            ]
        """
        # Build cache key based on provided identifiers
        cache_key = f"elements:variants:{element_code or element_id}:{category_id}"

        # Try cache first
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(f"Variants cache hit for: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Variants cache read failed for {cache_key}: {e}")

        async with get_async_session() as session:
            # If element_code provided, find parent element first
            if element_code and category_id:
                parent_query = select(Element).where(
                    Element.code == element_code,
                    Element.category_id == category_id,
                )
                parent_result = await session.execute(parent_query)
                parent = parent_result.scalar_one_or_none()

                if not parent:
                    # Cache empty result to avoid repeated lookups
                    try:
                        await self.redis.setex(cache_key, CACHE_TTL, json.dumps([]))
                    except Exception as e:
                        logger.warning(f"Variants cache write failed: {e}")
                    return []

                element_id = str(parent.id)

            if not element_id:
                return []

            # Find variants (elements with parent_element_id = element_id)
            query = (
                select(Element)
                .where(Element.parent_element_id == element_id)
                .where(Element.is_active == True)
                .order_by(Element.sort_order)
            )

            result = await session.execute(query)
            variants = result.scalars().all()

            data = [
                {
                    "id": str(variant.id),
                    "code": variant.code,
                    "name": variant.name,
                    "variant_type": variant.variant_type,
                    "variant_code": variant.variant_code,
                    "description": variant.description or "",
                    "keywords": variant.keywords or [],
                }
                for variant in variants
            ]

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
                logger.debug(f"Variants cached for: {cache_key}")
            except Exception as e:
                logger.warning(f"Variants cache write failed for {cache_key}: {e}")

            return data

    async def get_element_by_code(
        self,
        element_code: str,
        category_id: str,
    ) -> dict | None:
        """
        Get an element by its code and category.

        Args:
            element_code: Code of the element (e.g., "BOLA_REMOLQUE")
            category_id: UUID of the vehicle category

        Returns:
            Element dict with question_hint, or None if not found
        """
        async with get_async_session() as session:
            query = select(Element).where(
                Element.code == element_code,
                Element.category_id == category_id,
            )
            result = await session.execute(query)
            element = result.scalar_one_or_none()

            if not element:
                return None

            return {
                "id": str(element.id),
                "code": element.code,
                "name": element.name,
                "description": element.description or "",
                "keywords": element.keywords or [],
                "question_hint": element.question_hint,
                "is_active": element.is_active,
            }

    async def match_elements_from_description(
        self,
        description: str,
        category_id: str,
        only_base_elements: bool = True,
    ) -> list[tuple[dict, float]]:
        """
        Match elements from user description using hybrid algorithm.

        Matching phases:
        - Phase 1: Exact single-word keyword match (1.0 pts)
        - Phase 2: Multi-word keyword partial/full match (0.4-0.8 pts)
        - Phase 3: Alias match (0.6 pts)
        - Phase 4: N-gram fuzzy matching for typos (0.0-0.4 pts)

        Args:
            description: User's text description of elements
            category_id: Vehicle category ID
            only_base_elements: If True, only match base elements (without parent).
                               Useful to avoid matching specific variants directly.
                               Default True for initial user matching.

        Returns:
            List of (element_dict, confidence_score) tuples, sorted by confidence descending
        """
        result = await self.match_elements_with_unmatched(
            description=description,
            category_id=category_id,
            only_base_elements=only_base_elements,
        )
        return result["matches"]

    def _extract_quantities(
        self,
        description: str,
        tokens: list[str],
    ) -> dict[str, int]:
        """
        Extract quantity indicators from description.

        Data-driven: patterns from QUANTITY_PATTERNS config.
        Detects patterns like "2 escapes", "tres faros", "par de retrovisores".

        Args:
            description: Original user description
            tokens: Normalized tokens from description

        Returns:
            Dict mapping element terms to quantities, e.g., {"escape": 2, "faro": 3}
        """
        quantities: dict[str, int] = {}
        desc_lower = description.lower()
        desc_normalized = self._normalize_text(description)

        # Phase 1: Extract digit + element patterns (e.g., "2 escapes")
        digit_pattern = QUANTITY_PATTERNS.get("digit_pattern", r"(\d+)\s+(\w+)")
        if isinstance(digit_pattern, str):
            for match in re.finditer(digit_pattern, desc_normalized):
                qty = int(match.group(1))
                term = match.group(2)
                if qty > 0 and len(term) >= 3:  # Ignore very short terms
                    # Store singular form (remove trailing 's' for Spanish plurals)
                    term_singular = term.rstrip("s") if term.endswith("s") and len(term) > 3 else term
                    quantities[term_singular] = qty
                    logger.debug(f"[_extract_quantities] Digit pattern: {qty} x '{term_singular}'")

        # Phase 2: Extract written number + element patterns (e.g., "dos escapes", "par de faros")
        for word, qty in QUANTITY_PATTERNS.items():
            if word == "digit_pattern" or not isinstance(qty, int):
                continue

            # Pattern: word + optional "de" + element term
            pattern = rf"\b{word}\s+(?:de\s+)?(\w{{3,}})"
            for match in re.finditer(pattern, desc_normalized):
                term = match.group(1)
                term_singular = term.rstrip("s") if term.endswith("s") and len(term) > 3 else term
                # Don't overwrite if already detected with higher precision (digit)
                if term_singular not in quantities:
                    quantities[term_singular] = qty
                    logger.debug(f"[_extract_quantities] Word pattern '{word}': {qty} x '{term_singular}'")

        return quantities

    def _extract_negations(
        self,
        description: str,
        tokens: list[str],
    ) -> dict[str, Any]:
        """
        Detect negation patterns in description.

        Data-driven from NEGATION_PATTERNS config.
        Detects patterns like "todo menos escape", "sin faros", "excepto intermitentes".

        Args:
            description: Original user description
            tokens: Normalized tokens from description

        Returns:
            Dict with:
            - has_negation: bool - Whether negation was detected
            - excluded_terms: list[str] - Terms to exclude
            - negation_type: str - "all_except" | "specific" | None
        """
        result: dict[str, Any] = {
            "has_negation": False,
            "excluded_terms": [],
            "negation_type": None,
        }

        desc_lower = description.lower()
        desc_normalized = self._normalize_text(description)

        # Phase 1: Check for "all except" patterns (highest priority)
        all_except_patterns = NEGATION_PATTERNS.get("all_except", [])
        for pattern in all_except_patterns:
            match = re.search(pattern, desc_normalized)
            if match:
                result["has_negation"] = True
                result["negation_type"] = "all_except"

                # Extract terms after the negation phrase
                remaining = desc_normalized[match.end():]
                # Extract element-like words (3+ chars, not stopwords)
                excluded = self._extract_element_terms_from_text(remaining)
                result["excluded_terms"].extend(excluded)

                logger.info(
                    f"[_extract_negations] all_except pattern detected",
                    extra={
                        "pattern": pattern,
                        "excluded_terms": excluded,
                    }
                )
                break  # Only match first pattern

        # Phase 2: Check for specific exclusion patterns (if no all_except match)
        if not result["has_negation"]:
            specific_patterns = NEGATION_PATTERNS.get("specific_exclude", [])
            for pattern in specific_patterns:
                for match in re.finditer(pattern, desc_normalized):
                    result["has_negation"] = True
                    result["negation_type"] = "specific"

                    # Extract the term immediately after the negation
                    remaining = desc_normalized[match.end():]
                    # Get first element-like word
                    word_match = re.match(r"(\w{3,})", remaining)
                    if word_match:
                        term = word_match.group(1)
                        if term not in result["excluded_terms"]:
                            result["excluded_terms"].append(term)

                            logger.debug(
                                f"[_extract_negations] specific exclusion: '{term}'"
                            )

        # Phase 3: Keyword-based detection (fallback check)
        if not result["has_negation"]:
            keywords = NEGATION_PATTERNS.get("keywords", [])
            for kw in keywords:
                kw_normalized = self._normalize_text(kw)
                if kw_normalized in tokens:
                    # Check if followed by element-like term
                    idx = tokens.index(kw_normalized)
                    if idx + 1 < len(tokens):
                        next_term = tokens[idx + 1]
                        if len(next_term) >= 3:
                            result["has_negation"] = True
                            result["negation_type"] = "specific"
                            if next_term not in result["excluded_terms"]:
                                result["excluded_terms"].append(next_term)

        # Deduplicate and clean excluded terms
        result["excluded_terms"] = list(set(result["excluded_terms"]))

        return result

    def _extract_element_terms_from_text(self, text: str) -> list[str]:
        """
        Extract potential element terms from text.

        Filters out stopwords and common non-element words.

        Args:
            text: Text to extract terms from

        Returns:
            List of potential element terms
        """
        # Simple stopwords for filtering
        stopwords = {
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            "de", "del", "en", "con", "por", "para", "a", "al",
            "y", "e", "o", "u", "pero", "que", "como",
        }

        terms = []
        words = re.findall(r"\b(\w{3,})\b", text)
        for word in words:
            word_lower = word.lower()
            if word_lower not in stopwords:
                terms.append(word_lower)

        return terms

    async def match_elements_with_unmatched(
        self,
        description: str,
        category_id: str,
        only_base_elements: bool = True,
    ) -> dict:
        """
        Match elements from user description and identify unmatched terms.

        This extended version returns both matched elements AND terms that
        the user mentioned but couldn't be matched to any element. This allows
        the agent to ask clarifying questions about ambiguous terms.

        HYBRID MATCHING: When only_base_elements=True, we still attempt to match
        variants first. If a variant matches with high confidence (e.g., user said
        "faro delantero"), we use the variant directly instead of asking about
        the base element.

        Matching phases:
        - Phase 1: Exact single-word keyword match (1.0 pts)
        - Phase 2: Multi-word keyword partial/full match (0.4-0.8 pts)
        - Phase 3: Alias match (0.6 pts)
        - Phase 4: N-gram fuzzy matching for typos (0.0-0.4 pts)

        Args:
            description: User's text description of elements
            category_id: Vehicle category ID
            only_base_elements: If True, prefer base elements but allow high-confidence
                               variant matches. Default True for initial user matching.

        Returns:
            Dict with:
            - matches: List of (element_dict, confidence_score) tuples
            - unmatched_terms: List of terms that might be element references but didn't match
            - matched_tokens: Set of tokens that were used in matching
        """
        # Tokenize with normalization (accents removed)
        desc_normalized = self._normalize_text(description)
        tokens = desc_normalized.split()

        # === Extract quantities and negations BEFORE matching ===
        raw_quantities = self._extract_quantities(description, tokens)
        negations = self._extract_negations(description, tokens)

        logger.debug(
            f"[match_elements_with_unmatched] Pre-match extraction",
            extra={
                "raw_quantities": raw_quantities,
                "negations": negations,
            }
        )

        # === HYBRID MATCHING: Load ALL elements and match variants first ===
        all_elements = await self.get_elements_by_category(category_id, is_active=True)

        # Match against ALL elements (base + variants)
        all_matches = self._match_against_elements(all_elements, tokens, desc_normalized)

        # Threshold for high-confidence variant match (user specified variant directly)
        # e.g., "faro delantero" → FARO_DELANTERO with score >= 1.2
        # Lowered from 1.6 to 1.2 to better catch variant specifications in clarification responses
        HIGH_VARIANT_THRESHOLD = 1.2

        # Separate variant matches with high confidence from base matches
        variant_matches: list[tuple[dict, float, set[str]]] = []
        base_matches: list[tuple[dict, float, set[str]]] = []

        for element, score, elem_matched_tokens in all_matches:
            is_variant = element.get("parent_element_id") is not None
            if is_variant and score >= HIGH_VARIANT_THRESHOLD:
                variant_matches.append((element, score, elem_matched_tokens))
            elif not is_variant:
                base_matches.append((element, score, elem_matched_tokens))

        # === Decision: Use high-confidence variants directly or fall back to bases ===
        matches: list[tuple[dict, float]] = []
        matched_tokens: set[str] = set()

        if variant_matches:
            # User specified variants directly (e.g., "faro delantero", "amortiguador trasero")
            # Filter out base elements whose variants already matched
            matched_parent_ids = {
                elem.get("parent_element_id") for elem, _, _ in variant_matches
            }

            # Add high-confidence variant matches
            for element, score, elem_matched_tokens in variant_matches:
                matches.append((element, score))
                matched_tokens.update(elem_matched_tokens)

            logger.info(
                f"[match_elements_with_unmatched] High-confidence variant matches",
                extra={
                    "variant_codes": [e["code"] for e, _, _ in variant_matches],
                    "matched_parent_ids": list(matched_parent_ids),
                }
            )

            # Add base matches ONLY if their children didn't match
            for element, score, elem_matched_tokens in base_matches:
                elem_id = element.get("id")
                if elem_id not in matched_parent_ids:
                    matches.append((element, score))
                    matched_tokens.update(elem_matched_tokens)
        else:
            # No high-confidence variant matches → use base elements only
            for element, score, elem_matched_tokens in base_matches:
                matches.append((element, score))
                matched_tokens.update(elem_matched_tokens)

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        # Detect ambiguous candidates (elements with similar scores)
        # This helps the agent ask clarifying questions when multiple elements
        # have scores close to the top match
        ambiguous_candidates = []
        if matches:
            top_score = matches[0][1]
            # Threshold: elements with score >= 80% of the top score
            similarity_threshold = top_score * 0.8

            for element, score in matches:
                if score >= similarity_threshold and score > 0:
                    ambiguous_candidates.append({
                        "code": element["code"],
                        "name": element["name"],
                        "score": score
                    })
                else:
                    # Already sorted DESC, can exit early
                    break

        # Identify unmatched terms that look like potential element references
        unmatched_terms = self._identify_unmatched_terms(
            tokens=tokens,
            matched_tokens=matched_tokens,
            description=description,
        )

        # === Apply negation filtering to matches ===
        excluded_codes: set[str] = set()
        if negations.get("has_negation") and negations.get("excluded_terms"):
            excluded_terms_normalized = {
                self._normalize_text(t) for t in negations["excluded_terms"]
            }

            # Find matches that should be excluded
            filtered_matches = []
            for element, score in matches:
                elem_code = element["code"]
                elem_name_normalized = self._normalize_text(element["name"])
                elem_keywords = [self._normalize_text(k) for k in element.get("keywords", [])]

                # Check if this element matches any excluded term
                is_excluded = False
                for excl_term in excluded_terms_normalized:
                    # Check name match
                    if excl_term in elem_name_normalized or elem_name_normalized in excl_term:
                        is_excluded = True
                        break
                    # Check keyword match
                    if any(excl_term in kw or kw in excl_term for kw in elem_keywords):
                        is_excluded = True
                        break

                if is_excluded:
                    excluded_codes.add(elem_code)
                    logger.info(
                        f"[match_elements_with_unmatched] Excluded element due to negation",
                        extra={"code": elem_code, "name": element["name"]}
                    )
                else:
                    filtered_matches.append((element, score))

            matches = filtered_matches

        # === Map raw quantities to matched element codes ===
        quantities: dict[str, int] = {}
        for element, score in matches:
            elem_code = element["code"]
            elem_name_normalized = self._normalize_text(element["name"])
            elem_keywords = [self._normalize_text(k) for k in element.get("keywords", [])]

            # Check if any raw quantity term matches this element
            for term, qty in raw_quantities.items():
                term_normalized = self._normalize_text(term)
                # Match against name or keywords
                if term_normalized in elem_name_normalized:
                    quantities[elem_code] = qty
                    break
                if any(term_normalized in kw for kw in elem_keywords):
                    quantities[elem_code] = qty
                    break

        if quantities:
            logger.info(
                f"[match_elements_with_unmatched] Quantities mapped to elements",
                extra={"quantities": quantities}
            )

        return {
            "matches": matches,
            "unmatched_terms": unmatched_terms,
            "matched_tokens": matched_tokens,
            # Only include ambiguous candidates if there's more than one
            "ambiguous_candidates": ambiguous_candidates if len(ambiguous_candidates) > 1 else [],
            # NEW: quantities mapped to element codes
            "quantities": quantities,
            # NEW: negation detection results
            "negations": negations,
            # NEW: elements excluded due to negation
            "excluded_codes": list(excluded_codes),
        }

    def _identify_unmatched_terms(
        self,
        tokens: list[str],
        matched_tokens: set[str],
        description: str,
    ) -> list[str]:
        """
        Identify tokens that might be element references but didn't match.

        Filters out common stopwords and prepositions to focus on
        potentially meaningful unmatched terms.

        Args:
            tokens: All tokens from user description (normalized)
            matched_tokens: Tokens that matched elements
            description: Original description (for case reconstruction)

        Returns:
            List of unmatched terms that might be element references
        """
        # Spanish stopwords and common words that aren't element references
        stopwords = {
            # Articles
            "el", "la", "los", "las", "un", "una", "unos", "unas",
            # Prepositions
            "de", "del", "en", "con", "por", "para", "a", "al",
            "sin", "sobre", "desde", "hacia", "hasta",
            # Conjunctions
            "y", "e", "o", "u", "pero", "que", "como", "porque",
            # Pronouns
            "mi", "tu", "su", "mis", "tus", "sus", "me", "te", "se",
            "le", "lo", "les", "esto", "eso", "este", "ese", "esta",
            # Common verbs (infinitives and conjugations)
            "quiero", "quisiera", "necesito", "tengo", "tiene", "tener",
            "he", "ha", "hecho", "puesto", "cambiado", "instalado",
            "poner", "cambiar", "instalar", "homologar",
            "recortado", "recorte", "recortar", "cortado", "cortar",
            "cambio", "cambiarle", "cambiarlo", "cambiale",
            "sustituido", "sustituir", "sustitucion", "sustituto",
            "mantener", "mantengo", "mantiene", "mantenerlo",
            "precio", "tendria", "saber", "saben", "cuenta",
            "hola", "buenas", "buenos", "dias", "tardes",
            "seria", "podria", "podrias", "puedo", "puede", "pueden",
            "queria", "querria", "gustaria", "haria",
            "soy", "son", "somos", "estar", "estoy", "esta",
            # Vehicle brands (filtered separately, not elements)
            "honda", "yamaha", "kawasaki", "suzuki", "bmw", "mercedes",
            "ducati", "triumph", "ktm", "aprilia", "harley", "davidson",
            "ford", "seat", "renault", "peugeot", "citroen", "volkswagen",
            "audi", "toyota", "nissan", "hyundai", "kia", "fiat",
            # Vehicle types (already handled by category)
            "moto", "motomat", "motocicleta", "coche", "vehiculo",
            "autocaravana", "furgoneta", "camioneta", "camion",
            # Common non-element words
            "plazas", "plaza", "parte", "partes", "zona", "zonas",
            "completo", "completa", "total", "totalmente",
            "tipo", "tipos", "modelo", "modelos", "version",
            "doble", "simple", "solo", "sola", "unico", "unica",
            "original", "originales", "stock", "serie",
            "bien", "mal", "mejor", "peor", "mucho", "poco",
            "grande", "pequeno", "largo", "corto", "alto", "bajo",
            "izquierdo", "derecho", "izquierda", "derecha",
            # General words
            "etc", "tambien", "ademas", "mas", "muy", "todo", "toda",
            "todos", "nuevo", "nueva", "nuevos", "nuevas",
            "otro", "otra", "otros", "otras", "mismo", "misma",
            "cosa", "cosas", "algo", "nada", "algun", "alguno",
            # Numbers
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "uno", "dos", "tres", "cuatro", "cinco",
            # Model numbers/codes (alphanumeric patterns are often models)
            "cbf600", "cbr600", "mt07", "mt09", "z900", "r1", "r6",
        }

        # Potential element-like words to consider (GENUINELY AMBIGUOUS terms)
        # These are terms where we MUST ask the user which specific element they mean
        # because the same word could refer to DIFFERENT elements with DIFFERENT prices
        element_hint_words = {
            # Lighting (ambiguous - could be FARO_DELANTERO, PILOTO_FRENO, INTERMITENTES, etc.)
            "luces", "luz", "iluminacion", "alumbrado",
            # Suspension (ambiguous - could be SUSPENSION_DEL or SUSPENSION_TRAS)
            "suspension", "amortiguadores", "amortiguador",
            # Brakes (ambiguous - could be front or rear)
            "frenos", "freno",
            # Intermitentes (ambiguous - could be INTERMITENTES_DEL or INTERMITENTES_TRAS)
            "intermitentes", "intermitente",
            # NOTE: We do NOT include qualifiers like "delantero"/"trasero" alone
            # because they only clarify an element, they are not elements themselves
        }

        unmatched = []

        for token in tokens:
            # Skip if already matched
            if token in matched_tokens:
                continue

            # Skip stopwords
            if token in stopwords:
                continue

            # Skip very short tokens (likely not element names)
            if len(token) < 4:
                continue

            # Include ONLY if it's in element_hint_words (specific ambiguous terms)
            # We do NOT flag arbitrary long words - that causes too many false positives
            if token in element_hint_words:
                # Try to recover original casing from description
                original_word = self._recover_original_word(token, description)
                unmatched.append(original_word)

        # Remove duplicates while preserving order
        seen = set()
        unique_unmatched = []
        for term in unmatched:
            term_lower = term.lower()
            if term_lower not in seen:
                seen.add(term_lower)
                unique_unmatched.append(term)

        return unique_unmatched

    def _recover_original_word(self, normalized_token: str, original_text: str) -> str:
        """
        Try to recover the original word with proper casing from the description.

        Args:
            normalized_token: Normalized (lowercase, no accents) token
            original_text: Original description text

        Returns:
            Original word if found, otherwise the normalized token
        """
        import re

        # Split original text into words
        words = re.findall(r'\b\w+\b', original_text)

        for word in words:
            if self._normalize_text(word) == normalized_token:
                return word

        return normalized_token

    async def get_element_with_images(
        self,
        element_id: str,
    ) -> dict | None:
        """
        Get element details with all associated images.

        Args:
            element_id: UUID of the element

        Returns:
            Element dict with images list, or None if not found
        """
        cache_key = f"element:details:{element_id}"

        # Try cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")

        # Fetch from database with eager loading
        async with get_async_session() as session:
            result = await session.execute(
                select(Element)
                .where(Element.id == element_id)
                .options(selectinload(Element.images))
            )
            element = result.unique().scalar_one_or_none()

            if not element:
                return None

            # Serialize element with images
            data = {
                "id": str(element.id),
                "category_id": str(element.category_id),
                "code": element.code,
                "name": element.name,
                "description": element.description,
                "keywords": element.keywords,
                "aliases": element.aliases or [],
                "is_active": element.is_active,
                "sort_order": element.sort_order,
                "images": [
                    {
                        "id": str(img.id),
                        "image_url": img.image_url,
                        "title": img.title,
                        "description": img.description,
                        "image_type": img.image_type,
                        "sort_order": img.sort_order,
                        "is_required": img.is_required,
                    }
                    for img in sorted(element.images, key=lambda x: x.sort_order)
                ],
            }

            # Cache the result
            try:
                await self.redis.setex(cache_key, CACHE_TTL, json.dumps(data))
            except Exception as e:
                logger.warning(f"Cache write failed for {cache_key}: {e}")

            return data

    async def get_element_warnings(
        self,
        element_id: str,
    ) -> list[dict]:
        """
        Get warnings associated with an element.

        Args:
            element_id: UUID of the element

        Returns:
            List of warning dictionaries
        """
        from database.models import ElementWarningAssociation

        async with get_async_session() as session:
            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.element_id == element_id)
                .options(selectinload(ElementWarningAssociation.warning))
            )
            associations = result.unique().scalars().all()

            warnings = [
                {
                    "id": str(assoc.warning.id),
                    "code": assoc.warning.code,
                    "message": assoc.warning.message,
                    "severity": assoc.warning.severity,
                    "show_condition": assoc.show_condition,
                    "threshold_quantity": assoc.threshold_quantity,
                }
                for assoc in associations
                if assoc.warning.is_active
            ]

            return warnings

    async def get_warnings_for_elements(
        self,
        element_ids: list[str],
    ) -> list[dict]:
        """
        Get warnings associated with multiple elements.

        Args:
            element_ids: List of element UUIDs

        Returns:
            List of warning dictionaries (deduplicated)
        """
        if not element_ids:
            return []

        from database.models import ElementWarningAssociation

        async with get_async_session() as session:
            result = await session.execute(
                select(ElementWarningAssociation)
                .where(ElementWarningAssociation.element_id.in_(element_ids))
                .options(selectinload(ElementWarningAssociation.warning))
            )
            associations = result.unique().scalars().all()

            # Deduplicate by warning ID
            seen_ids = set()
            warnings = []
            for assoc in associations:
                if not assoc.warning.is_active:
                    continue
                warning_id = str(assoc.warning.id)
                if warning_id in seen_ids:
                    continue
                seen_ids.add(warning_id)
                warnings.append({
                    "id": warning_id,
                    "code": assoc.warning.code,
                    "message": assoc.warning.message,
                    "severity": assoc.warning.severity,
                    "show_condition": assoc.show_condition,
                    "threshold_quantity": assoc.threshold_quantity,
                    "element_id": str(assoc.element_id),
                })

            return warnings

    @staticmethod
    def _fuzzy_match(token: str, keyword: str) -> float:
        """
        Calculate fuzzy match similarity between token and keyword.

        Args:
            token: User's token (e.g., "escalera")
            keyword: Element's keyword (e.g., "escalera mecanica")

        Returns:
            Similarity score (0.0-1.0)
        """
        return SequenceMatcher(None, token, keyword).ratio()

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text: lowercase and remove accents.

        Args:
            text: Input text

        Returns:
            Normalized text without accents
        """
        text = unicodedata.normalize('NFD', text.lower())
        return ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    @staticmethod
    def _generate_char_ngrams(text: str, n: int = 3) -> set[str]:
        """
        Generate character n-grams for fuzzy matching.

        Args:
            text: Input text
            n: N-gram size (default 3 for trigrams)

        Returns:
            Set of character n-grams
        """
        text = ElementService._normalize_text(text)
        text = f"#{text}#"  # Boundary markers
        return {text[i:i+n] for i in range(len(text) - n + 1)}

    def _ngram_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Jaccard similarity between character trigrams.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0-1.0)
        """
        ngrams1 = self._generate_char_ngrams(text1)
        ngrams2 = self._generate_char_ngrams(text2)
        if not ngrams1 or not ngrams2:
            return 0.0
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        return intersection / union

    def _word_overlap_score(self, tokens: list[str], keyword: str) -> float:
        """
        Calculate word overlap score for multi-word keywords.

        Args:
            tokens: User's tokenized input (already normalized)
            keyword: Multi-word keyword

        Returns:
            Overlap score (0.0-1.0)
        """
        keyword_words = set(self._normalize_text(keyword).split())
        token_set = set(tokens)
        if not keyword_words:
            return 0.0
        overlap = len(keyword_words & token_set)
        return overlap / len(keyword_words)

    def _match_against_elements(
        self,
        elements: list[dict],
        tokens: list[str],
        desc_normalized: str,
    ) -> list[tuple[dict, float, set[str]]]:
        """
        Match tokens against a list of elements.

        Performs multi-phase matching:
        - Phase 1: Exact single-word keyword match (1.0 pts)
        - Phase 2: Multi-word keyword partial/full match (0.4-0.8 pts)
        - Phase 3: Alias match (0.6 pts)
        - Phase 4: N-gram fuzzy matching for typos (0.0-0.4 pts)

        Args:
            elements: List of element dicts to match against
            tokens: Normalized tokens from user description
            desc_normalized: Full normalized description string

        Returns:
            List of (element_dict, score, matched_tokens) tuples
        """
        matches = []

        for element in elements:
            score = 0.0
            keywords = element.get("keywords", [])
            aliases = element.get("aliases", [])
            element_matched_tokens: set[str] = set()

            # === PHASE 1: Exact single-word keyword matches ===
            for keyword in keywords:
                kw_normalized = self._normalize_text(keyword)
                if kw_normalized in tokens:
                    score += 1.0
                    element_matched_tokens.add(kw_normalized)

            # === PHASE 2: Multi-word keyword partial/full matching ===
            for keyword in keywords:
                if " " in keyword:  # Multi-word keyword
                    word_overlap = self._word_overlap_score(tokens, keyword)
                    if word_overlap > 0.5:  # At least 50% of words match
                        # Bonus: if full phrase is in description
                        kw_normalized = self._normalize_text(keyword)
                        if kw_normalized in desc_normalized:
                            score += 0.8  # Full phrase match
                        else:
                            score += 0.4 * word_overlap  # Partial match
                        # Add matched words from multi-word keyword
                        kw_words = set(kw_normalized.split())
                        for token in tokens:
                            if token in kw_words:
                                element_matched_tokens.add(token)

            # === PHASE 3: Alias matches ===
            for alias in aliases:
                alias_normalized = self._normalize_text(alias)
                if alias_normalized in tokens:
                    score += 0.6
                    element_matched_tokens.add(alias_normalized)
                elif alias_normalized in desc_normalized:
                    score += 0.6
                    # Add tokens that are part of the alias
                    alias_words = set(alias_normalized.split())
                    for token in tokens:
                        if token in alias_words:
                            element_matched_tokens.add(token)

            # === PHASE 4: N-gram fuzzy matching for typos ===
            for token in tokens:
                if len(token) >= 4:  # Only tokens with sufficient length
                    for keyword in keywords:
                        kw_normalized = self._normalize_text(keyword)
                        # Only compare with single-word keywords
                        if " " not in keyword:
                            ngram_sim = self._ngram_similarity(token, kw_normalized)
                            if ngram_sim > 0.5:  # Lower threshold than SequenceMatcher
                                score += 0.4 * ngram_sim
                                element_matched_tokens.add(token)

            if score > 0:
                matches.append((element, score, element_matched_tokens))

        return matches

    async def invalidate_category_cache(self, category_id: str) -> None:
        """
        Invalidate cache for a specific category.

        Called when elements are created/updated/deleted.
        Invalidates all related cache keys including variants.

        Args:
            category_id: UUID of the category
        """
        patterns = [
            f"elements:category:{category_id}:*",
            f"elements:base:category:{category_id}:*",
            f"elements:variants:*:{category_id}",
            f"element:details:*",  # Element details may reference this category
        ]

        invalidated_count = 0
        try:
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis.delete(*keys)
                        invalidated_count += len(keys)
                    if cursor == 0:
                        break

            logger.info(
                f"Cache invalidation completed for category {category_id}",
                extra={"invalidated_keys": invalidated_count, "patterns": patterns}
            )
        except Exception as e:
            logger.warning(f"Cache invalidation failed for category {category_id}: {e}")


# Singleton instance
_element_service = None


def get_element_service() -> ElementService:
    """Get or create ElementService singleton."""
    global _element_service
    if _element_service is None:
        _element_service = ElementService()
    return _element_service
