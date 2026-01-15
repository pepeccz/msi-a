"""
MSI Automotive - Image Security Validation.

Multi-layer security validation for user-uploaded images.
Protects against:
- Path traversal attacks
- SSRF (Server-Side Request Forgery)
- Fake images (malicious files with image headers)
- Image bombs (decompression attacks)
"""

import logging
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

logger = logging.getLogger(__name__)

# Magic number signatures for allowed image types
MAGIC_SIGNATURES = {
    "image/jpeg": [
        b"\xff\xd8\xff\xe0",  # JPEG JFIF
        b"\xff\xd8\xff\xe1",  # JPEG Exif
        b"\xff\xd8\xff\xe2",  # JPEG CIFF
        b"\xff\xd8\xff\xe8",  # JPEG SPIFF
        b"\xff\xd8\xff\xee",  # JPEG Adobe
        b"\xff\xd8\xff\xdb",  # JPEG raw
    ],
    "image/png": [b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"],  # PNG
    "image/gif": [
        b"\x47\x49\x46\x38\x37\x61",  # GIF87a
        b"\x47\x49\x46\x38\x39\x61",  # GIF89a
    ],
    "image/webp": [b"\x52\x49\x46\x46"],  # RIFF (WebP starts with RIFF)
    "image/heic": [b"\x00\x00\x00"],  # HEIC/HEIF (ftyp box)
    "image/heif": [b"\x00\x00\x00"],  # HEIC/HEIF (ftyp box)
}

# Allowed MIME types
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}

# Security limits
MAX_IMAGE_PIXELS = 89_478_485  # PIL default: ~89MP (prevents decompression bombs)
MIN_IMAGE_SIZE = 100  # bytes (too small = suspicious)
MAX_IMAGE_DIMENSION = 8192  # pixels (4K * 2)

# Private IP ranges for SSRF check
PRIVATE_IP_PREFIXES = [
    "10.",
    "192.168.",
    "127.",
    "0.",
    "169.254.",  # Link-local
]


class ImageSecurityError(Exception):
    """Exception raised for image security validation failures."""

    pass


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize a filename to prevent path traversal.

    Args:
        filename: User-provided filename

    Returns:
        Sanitized filename (basename only)

    Raises:
        ImageSecurityError: If filename is invalid
    """
    if not filename:
        raise ImageSecurityError("Filename cannot be empty")

    # Remove any directory components (path traversal prevention)
    safe_name = Path(filename).name

    # Check for path traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        logger.warning(f"Path traversal attempt detected: {filename}")
        # Still use the safe name but log the attempt

    # Additional validation: only allow alphanumeric, dash, underscore, dot
    if not re.match(r"^[\w\-\.]+$", safe_name):
        raise ImageSecurityError(
            f"Invalid filename: {filename}. "
            "Only alphanumeric, dash, underscore, and dot allowed."
        )

    # Prevent hidden files
    if safe_name.startswith("."):
        raise ImageSecurityError("Hidden files not allowed")

    # Validate extension
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ImageSecurityError(f"Invalid file extension: {ext}")

    return safe_name


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname is a private/local IP address."""
    # Check localhost variants
    if hostname.lower() in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:
        return True

    # Check private IP ranges
    for prefix in PRIVATE_IP_PREFIXES:
        if hostname.startswith(prefix):
            return True

    # Check 172.16.0.0 - 172.31.255.255 range
    if hostname.startswith("172."):
        parts = hostname.split(".")
        if len(parts) >= 2:
            try:
                second_octet = int(parts[1])
                if 16 <= second_octet <= 31:
                    return True
            except ValueError:
                pass

    return False


def validate_url(url: str, allowed_domains: list[str] | None = None) -> None:
    """
    Validate that URL is from an allowed domain (SSRF prevention).

    Args:
        url: URL to validate
        allowed_domains: List of allowed domain names (if empty, only blocks private IPs)

    Raises:
        ImageSecurityError: If URL is not from allowed domain or is a private IP
    """
    parsed = urlparse(url)

    # Block non-HTTP protocols
    if parsed.scheme not in ["http", "https"]:
        raise ImageSecurityError(f"Invalid URL scheme: {parsed.scheme}")

    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        raise ImageSecurityError("Invalid URL: no hostname")

    # Block private IPs (SSRF prevention)
    if _is_private_ip(hostname):
        logger.warning(f"SSRF attempt blocked: {url}")
        raise ImageSecurityError("Private/local addresses not allowed")

    # Block cloud metadata endpoints
    metadata_hosts = [
        "169.254.169.254",  # AWS/Azure metadata
        "metadata.google.internal",  # GCP metadata
        "metadata.google.com",
    ]
    if hostname in metadata_hosts:
        logger.warning(f"Metadata endpoint access blocked: {url}")
        raise ImageSecurityError("Metadata endpoints not allowed")

    # Whitelist check (if domains provided)
    if allowed_domains:
        if not any(hostname.endswith(domain) for domain in allowed_domains):
            raise ImageSecurityError(
                f"Domain not allowed: {hostname}. "
                f"Allowed: {', '.join(allowed_domains)}"
            )


def detect_mime_from_magic(content: bytes) -> str | None:
    """
    Detect MIME type from file magic numbers.

    Args:
        content: Raw file bytes (at least first 12 bytes needed)

    Returns:
        Detected MIME type or None if not recognized
    """
    if len(content) < 8:
        return None

    # Check each signature
    for mime_type, signatures in MAGIC_SIGNATURES.items():
        for sig in signatures:
            if content[: len(sig)] == sig:
                # Special case for WebP: verify it has WEBP after RIFF
                if mime_type == "image/webp":
                    if len(content) >= 12 and content[8:12] == b"WEBP":
                        return mime_type
                else:
                    return mime_type

    return None


def validate_magic_number(content: bytes, declared_mime: str | None = None) -> str:
    """
    Validate file content using magic numbers (file signature).

    Args:
        content: Raw file bytes
        declared_mime: MIME type declared by client/server (optional)

    Returns:
        Actual MIME type detected

    Raises:
        ImageSecurityError: If file type doesn't match or is not allowed
    """
    if len(content) < MIN_IMAGE_SIZE:
        raise ImageSecurityError(f"File too small: {len(content)} bytes")

    # Detect actual type from magic numbers
    detected_mime = detect_mime_from_magic(content)

    if detected_mime is None:
        # Try using PIL as fallback
        try:
            img = Image.open(BytesIO(content))
            pil_format = img.format
            if pil_format:
                format_to_mime = {
                    "JPEG": "image/jpeg",
                    "PNG": "image/png",
                    "GIF": "image/gif",
                    "WEBP": "image/webp",
                    "HEIC": "image/heic",
                    "HEIF": "image/heif",
                }
                detected_mime = format_to_mime.get(pil_format.upper())
        except Exception:
            pass

    if detected_mime is None:
        raise ImageSecurityError(
            "Could not detect file type. File may not be a valid image."
        )

    # Validate detected type is an allowed image type
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ImageSecurityError(
            f"File type not allowed: {detected_mime}. "
            f"Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
        )

    # Warn if declared MIME doesn't match detected (but don't fail)
    if declared_mime and declared_mime != detected_mime:
        # Normalize for comparison (jpeg vs jpg)
        declared_normalized = declared_mime.replace("jpg", "jpeg")
        detected_normalized = detected_mime.replace("jpg", "jpeg")
        if declared_normalized != detected_normalized:
            logger.warning(
                f"MIME type mismatch: declared={declared_mime}, "
                f"detected={detected_mime}. Using detected type."
            )

    return detected_mime


def validate_image_content(content: bytes) -> tuple[int, int]:
    """
    Validate image content using PIL (checks if valid image + dimensions).

    Args:
        content: Raw image bytes

    Returns:
        Tuple of (width, height)

    Raises:
        ImageSecurityError: If image is invalid or dimensions exceed limits
    """
    try:
        # Configure PIL security limits BEFORE opening
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        # Try to open the image
        img = Image.open(BytesIO(content))

        # Verify it's a valid image (catches truncated/corrupted files)
        img.verify()

        # Re-open for size check (verify() invalidates the image object)
        img = Image.open(BytesIO(content))
        width, height = img.size

        # Validate dimensions
        if width <= 0 or height <= 0:
            raise ImageSecurityError(f"Invalid image dimensions: {width}x{height}")

        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            raise ImageSecurityError(
                f"Image dimensions too large: {width}x{height}. "
                f"Max: {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
            )

        # Check total pixels (additional decompression bomb protection)
        total_pixels = width * height
        if total_pixels > MAX_IMAGE_PIXELS:
            raise ImageSecurityError(
                f"Image has too many pixels: {total_pixels}. "
                f"Max: {MAX_IMAGE_PIXELS}"
            )

        logger.debug(f"Image validated: {width}x{height} pixels, {len(content)} bytes")
        return width, height

    except ImageSecurityError:
        raise
    except Image.DecompressionBombError as e:
        logger.warning(f"Decompression bomb detected: {e}")
        raise ImageSecurityError("Image appears to be a decompression bomb")
    except Exception as e:
        logger.warning(f"Image validation failed: {e}")
        raise ImageSecurityError(f"Invalid image file: {str(e)}")


def sanitize_filename(original: str) -> str:
    """
    Sanitize a filename for safe storage.

    Args:
        original: Original filename from user

    Returns:
        Sanitized filename safe for filesystem storage
    """
    if not original:
        return "image"

    # Remove directory components
    safe = Path(original).name

    # Replace unsafe characters with underscore
    safe = re.sub(r"[^\w\-\.]", "_", safe)

    # Remove leading dots (hidden files)
    safe = safe.lstrip(".")

    # Ensure not empty after sanitization
    if not safe:
        return "image"

    # Limit length (preserve extension)
    if len(safe) > 255:
        if "." in safe:
            name_part, ext = safe.rsplit(".", 1)
            max_name_len = 255 - len(ext) - 1
            safe = name_part[:max_name_len] + "." + ext
        else:
            safe = safe[:255]

    return safe


def validate_image_full(
    content: bytes,
    declared_mime: str | None = None,
    url: str | None = None,
    allowed_domains: list[str] | None = None,
) -> dict:
    """
    Perform full multi-layer validation on an image.

    This is the main entry point for image validation, combining all security checks.

    Args:
        content: Raw image bytes
        declared_mime: MIME type declared by client/server
        url: Optional source URL (for SSRF check)
        allowed_domains: Optional list of allowed domains for URL validation

    Returns:
        Dict with validation results:
        {
            "valid": True,
            "detected_mime": str,
            "width": int,
            "height": int,
            "file_size": int
        }

    Raises:
        ImageSecurityError: If any validation fails
    """
    # Layer 1: URL validation (if provided)
    if url:
        validate_url(url, allowed_domains)

    # Layer 2: Magic number validation
    detected_mime = validate_magic_number(content, declared_mime)

    # Layer 3: Image content validation (PIL)
    width, height = validate_image_content(content)

    logger.info(
        f"Image security validation passed: "
        f"{width}x{height}, {len(content)} bytes, {detected_mime}"
    )

    return {
        "valid": True,
        "detected_mime": detected_mime,
        "width": width,
        "height": height,
        "file_size": len(content),
    }


def get_extension_for_mime(mime_type: str) -> str:
    """
    Get file extension for a MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        File extension without dot (e.g., "jpg", "png")
    """
    mime_to_ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }
    return mime_to_ext.get(mime_type, "jpg")
