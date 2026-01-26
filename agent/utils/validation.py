"""Input validation utilities for security."""

import re
from typing import Pattern

# Regex pattern for valid category slugs (lowercase alphanumeric + hyphens)
SLUG_PATTERN: Pattern = re.compile(r'^[a-z0-9-]+$')

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
