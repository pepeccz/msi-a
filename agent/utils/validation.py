"""Input validation utilities for security."""

import re
from typing import Pattern

# Regex pattern for valid category slugs (lowercase alphanumeric + hyphens)
SLUG_PATTERN: Pattern = re.compile(r'^[a-z0-9-]+$')

# ---------------------------------------------------------------------------
# Photo-completion intent detection (shared between expediente_mode and
# image_handling — single canonical source of truth)
# ---------------------------------------------------------------------------
#
# V1 PATH ONLY — deprecated in V2 as primary classifier, use IntentClassifier instead.
#
# In V2 (EXPEDIENTE_V2_ENABLED=True):
#   - IntentClassifier is the PRIMARY classifier (context-aware LLM)
#   - This regex is used as a FALLBACK when:
#       a) IntentClassifier returns a non-COMPLETION_SIGNAL intent (fall-through arbiter)
#       b) IntentClassifier raises an exception (graceful degradation)
#       c) IntentClassifier is unavailable (_get_intent_classifier_svc() returns None)
#   - image_handling.is_completion_message() still uses this regex directly (webhook path)
#
# In V1 (EXPEDIENTE_V2_ENABLED=False): this is the sole classifier.
#
# Do NOT remove this export until image_handling.py is also migrated to IntentClassifier.
#
# Matches past/present completion expressions: the user confirms they have
# already sent or finished sending photos.
#
# Matches:   "listo", "Listo", "LISTO", "ya te las envié", "enviadas",
#            "ya las mandé", "ahí van", "ya están", "listas ya", "hecho",
#            "terminado", "ya", "done", "eso es todo", "nada más", etc.
#
# Does NOT match future intent (the pattern requires past/completion aspect):
#   "las voy a enviar", "te las mando luego", "mañana las mando"
#   (none of those contain the matched tokens at word boundaries)
#
PHOTO_COMPLETION_INTENT_RE: re.Pattern[str] = re.compile(
    r"\b("
    # Simple one-word completions
    r"listo|lista|listos|listas"
    r"|ya"
    r"|done"
    r"|hecho|hechos|hecha|hechas"
    r"|terminado|terminada|terminados|terminadas"
    r"|fin"
    # "enviadas/enviados" (past participle — they *have been* sent)
    r"|enviadas?|enviados?"
    # "mandadas/mandados" — synonyms for sent
    r"|mandadas?|mandados?"
    # "ya están" — "they are already (there)"
    r"|ya\s+est[aá]n"
    # "ya te las envié / ya las envié / ya los envié"
    r"|ya\s+(te\s+)?(las?|los?)\s+env[ií][eé]?"
    # "ya las mandé / ya te las mandé"
    r"|ya\s+(te\s+)?(las?|los?)\s+mand[eé]"
    # "ahí van" — "here they go / they're on their way"
    r"|ah[ií]\s+van"
    # "ya están" duplicate guard covered above; also "ya está" singular
    r"|ya\s+est[aá]"
    # "eso es todo" / "nada más" / "nada mas"
    r"|eso\s+es\s+todo"
    r"|nada\s+m[aá]s"
    r")\b",
    re.IGNORECASE,
)

# Maximum length for category slugs to prevent buffer overflow attacks
MAX_SLUG_LENGTH = 50


def validate_category_slug(slug: str) -> str:
    """
    Validate category slug format to prevent SQL injection and other attacks.
    
    This function enforces a strict whitelist of allowed characters:
    - Lowercase letters (a-z)
    - Numbers (0-9)
    - Hyphens (-)
    
    This prevents:
    - SQL injection attacks (e.g., "'; DROP TABLE--")
    - Path traversal attacks (e.g., "../../etc/passwd")
    - XSS attacks (e.g., "<script>alert('xss')</script>")
    - Null byte injection (e.g., "slug\x00malicious")
    - Other injection vectors
    
    Args:
        slug: Category slug to validate (e.g., "motos-part")
        
    Returns:
        Validated slug (unchanged if valid)
        
    Raises:
        ValueError: If slug format is invalid or security check fails
        
    Examples:
        >>> validate_category_slug("motos-part")
        'motos-part'
        >>> validate_category_slug("'; DROP TABLE--")
        Traceback (most recent call last):
        ...
        ValueError: Invalid category slug format: '; DROP TABLE--. Only lowercase letters, numbers, and hyphens allowed.
    """
    if not slug:
        raise ValueError("Category slug cannot be empty")
    
    if len(slug) > MAX_SLUG_LENGTH:
        raise ValueError(
            f"Category slug too long: {len(slug)} > {MAX_SLUG_LENGTH}"
        )
    
    if not SLUG_PATTERN.match(slug):
        raise ValueError(
            f"Invalid category slug format: {slug}. "
            "Only lowercase letters, numbers, and hyphens allowed."
        )
    
    return slug
