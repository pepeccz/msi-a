"""
Tests for image security validation module.

Tests cover:
- Path traversal prevention
- SSRF (Server-Side Request Forgery) prevention
- Magic number validation
- Image content validation
- Filename sanitization
"""

import pytest
from io import BytesIO
from PIL import Image

from shared.image_security import (
    ImageSecurityError,
    validate_filename,
    validate_url,
    validate_magic_number,
    validate_image_content,
    sanitize_filename,
    validate_image_full,
    detect_mime_from_magic,
    get_extension_for_mime,
)


# =============================================================================
# Path Traversal Tests
# =============================================================================


class TestValidateFilename:
    """Tests for validate_filename function."""

    def test_valid_filename(self):
        """Valid filenames should pass."""
        assert validate_filename("image.jpg") == "image.jpg"
        assert validate_filename("my-photo.png") == "my-photo.png"
        assert validate_filename("photo_001.webp") == "photo_001.webp"
        assert validate_filename("123.gif") == "123.gif"

    def test_path_traversal_unix(self):
        """Unix path traversal attempts should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename("../../../etc/passwd")

        with pytest.raises(ImageSecurityError):
            validate_filename("../../secret.jpg")

        with pytest.raises(ImageSecurityError):
            validate_filename("/etc/passwd")

    def test_path_traversal_windows(self):
        """Windows path traversal attempts should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename("..\\..\\..\\windows\\system32\\config\\sam")

        with pytest.raises(ImageSecurityError):
            validate_filename("C:\\Windows\\system.ini")

    def test_hidden_files_blocked(self):
        """Hidden files (starting with dot) should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename(".htaccess")

        with pytest.raises(ImageSecurityError):
            validate_filename(".env")

    def test_invalid_extension(self):
        """Invalid file extensions should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename("malware.exe")

        with pytest.raises(ImageSecurityError):
            validate_filename("script.php")

        with pytest.raises(ImageSecurityError):
            validate_filename("script.sh")

    def test_empty_filename(self):
        """Empty filename should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename("")

    def test_special_characters_blocked(self):
        """Special characters should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_filename("image<script>.jpg")

        with pytest.raises(ImageSecurityError):
            validate_filename("photo|command.png")


# =============================================================================
# SSRF Prevention Tests
# =============================================================================


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_valid_external_url(self):
        """Valid external URLs should pass."""
        # Should not raise
        validate_url("https://example.com/image.jpg", [])
        validate_url("https://cdn.example.com/photos/1.png", [])

    def test_localhost_blocked(self):
        """Localhost variants should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_url("http://localhost/admin", [])

        with pytest.raises(ImageSecurityError):
            validate_url("http://127.0.0.1/secret", [])

        with pytest.raises(ImageSecurityError):
            validate_url("http://0.0.0.0/", [])

    def test_private_ips_blocked(self):
        """Private IP addresses should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_url("http://192.168.1.1/", [])

        with pytest.raises(ImageSecurityError):
            validate_url("http://10.0.0.1/internal", [])

        with pytest.raises(ImageSecurityError):
            validate_url("http://172.16.0.1/", [])

    def test_aws_metadata_blocked(self):
        """AWS/cloud metadata endpoints should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_url("http://169.254.169.254/latest/meta-data/", [])

        with pytest.raises(ImageSecurityError):
            validate_url("http://169.254.169.254/latest/meta-data/iam/security-credentials/", [])

    def test_invalid_scheme_blocked(self):
        """Non-HTTP schemes should be blocked."""
        with pytest.raises(ImageSecurityError):
            validate_url("file:///etc/passwd", [])

        with pytest.raises(ImageSecurityError):
            validate_url("ftp://server.com/file", [])

    def test_domain_whitelist(self):
        """Domain whitelist should be enforced when provided."""
        allowed = ["cdn.mycompany.com"]

        # Should pass
        validate_url("https://cdn.mycompany.com/image.jpg", allowed)

        # Should fail - not in whitelist
        with pytest.raises(ImageSecurityError):
            validate_url("https://evil.com/image.jpg", allowed)


# =============================================================================
# Magic Number Validation Tests
# =============================================================================


class TestValidateMagicNumber:
    """Tests for validate_magic_number function."""

    def test_valid_jpeg(self):
        """Valid JPEG should be detected."""
        # Create a minimal valid JPEG
        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        content = buffer.getvalue()

        result = validate_magic_number(content, "image/jpeg")
        assert result == "image/jpeg"

    def test_valid_png(self):
        """Valid PNG should be detected."""
        img = Image.new("RGBA", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        content = buffer.getvalue()

        result = validate_magic_number(content, "image/png")
        assert result == "image/png"

    def test_fake_image_blocked(self):
        """Fake images (wrong magic numbers) should be blocked."""
        # PHP disguised as JPEG
        fake_content = b"<?php system($_GET['cmd']); ?>"

        with pytest.raises(ImageSecurityError):
            validate_magic_number(fake_content, "image/jpeg")

    def test_executable_blocked(self):
        """Executable files should be blocked."""
        # ELF header (Linux executable)
        elf_header = b"\x7fELF" + b"\x00" * 100

        with pytest.raises(ImageSecurityError):
            validate_magic_number(elf_header, "image/jpeg")

    def test_too_small_file(self):
        """Files that are too small should be blocked."""
        tiny_content = b"\xff\xd8"  # Just 2 bytes

        with pytest.raises(ImageSecurityError):
            validate_magic_number(tiny_content, "image/jpeg")


# =============================================================================
# Image Content Validation Tests
# =============================================================================


class TestValidateImageContent:
    """Tests for validate_image_content function."""

    def test_valid_image(self):
        """Valid image should pass validation."""
        img = Image.new("RGB", (200, 300), color="green")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        content = buffer.getvalue()

        width, height = validate_image_content(content)
        assert width == 200
        assert height == 300

    def test_oversized_dimensions_blocked(self):
        """Images with dimensions too large should be blocked."""
        # Create a large image
        img = Image.new("RGB", (10000, 10000), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        content = buffer.getvalue()

        with pytest.raises(ImageSecurityError):
            validate_image_content(content)

    def test_corrupted_image_blocked(self):
        """Corrupted image data should be blocked."""
        # Start with valid header, then garbage
        corrupted = b"\xff\xd8\xff\xe0" + b"\x00" * 50 + b"corrupted data here"

        with pytest.raises(ImageSecurityError):
            validate_image_content(corrupted)


# =============================================================================
# Filename Sanitization Tests
# =============================================================================


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_basic_sanitization(self):
        """Basic filenames should be sanitized."""
        assert sanitize_filename("image.jpg") == "image.jpg"
        assert sanitize_filename("my photo.png") == "my_photo.png"

    def test_path_components_removed(self):
        """Path components should be removed."""
        assert sanitize_filename("/etc/passwd") == "passwd"
        assert sanitize_filename("../../../secret.jpg") == "secret.jpg"

    def test_special_chars_replaced(self):
        """Special characters should be replaced."""
        result = sanitize_filename("image<script>.jpg")
        assert "<" not in result
        assert ">" not in result

    def test_empty_returns_default(self):
        """Empty filename should return default."""
        assert sanitize_filename("") == "image"
        assert sanitize_filename(None) == "image"  # type: ignore

    def test_hidden_file_prefix_removed(self):
        """Leading dots should be removed."""
        assert not sanitize_filename(".hidden.jpg").startswith(".")


# =============================================================================
# Full Validation Tests
# =============================================================================


class TestValidateImageFull:
    """Tests for validate_image_full function."""

    def test_full_validation_success(self):
        """Complete validation should pass for valid image."""
        img = Image.new("RGB", (400, 300), color="purple")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        content = buffer.getvalue()

        result = validate_image_full(
            content=content,
            declared_mime="image/png",
        )

        assert result["valid"] is True
        assert result["detected_mime"] == "image/png"
        assert result["width"] == 400
        assert result["height"] == 300
        assert result["file_size"] == len(content)

    def test_full_validation_with_url(self):
        """Validation with URL should check SSRF."""
        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        content = buffer.getvalue()

        # Should fail due to localhost URL
        with pytest.raises(ImageSecurityError):
            validate_image_full(
                content=content,
                declared_mime="image/jpeg",
                url="http://localhost/image.jpg",
                allowed_domains=["example.com"],
            )

    def test_full_validation_mime_mismatch(self):
        """Validation should use detected MIME type, not declared."""
        # Create PNG but declare as JPEG
        img = Image.new("RGBA", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        content = buffer.getvalue()

        result = validate_image_full(
            content=content,
            declared_mime="image/jpeg",  # Wrong!
        )

        # Should detect actual type
        assert result["detected_mime"] == "image/png"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_detect_mime_jpeg(self):
        """JPEG detection should work."""
        img = Image.new("RGB", (50, 50))
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        content = buffer.getvalue()

        assert detect_mime_from_magic(content) == "image/jpeg"

    def test_detect_mime_png(self):
        """PNG detection should work."""
        img = Image.new("RGBA", (50, 50))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        content = buffer.getvalue()

        assert detect_mime_from_magic(content) == "image/png"

    def test_get_extension(self):
        """Extension mapping should work."""
        assert get_extension_for_mime("image/jpeg") == "jpg"
        assert get_extension_for_mime("image/png") == "png"
        assert get_extension_for_mime("image/gif") == "gif"
        assert get_extension_for_mime("image/webp") == "webp"
        assert get_extension_for_mime("unknown/type") == "jpg"  # Default


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestRateLimiter:
    """Tests for rate limiting functionality."""

    def test_under_limit(self):
        """Requests under limit should pass."""
        from api.middleware.rate_limit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()

        # First 5 requests should pass
        for i in range(5):
            assert limiter.check_rate_limit("test_key", max_requests=10, window_seconds=60)

    def test_over_limit(self):
        """Requests over limit should be blocked."""
        from api.middleware.rate_limit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()

        # Fill up the limit
        for i in range(10):
            limiter.check_rate_limit("test_key2", max_requests=10, window_seconds=60)

        # 11th request should fail
        assert not limiter.check_rate_limit("test_key2", max_requests=10, window_seconds=60)

    def test_different_keys_independent(self):
        """Different keys should have independent limits."""
        from api.middleware.rate_limit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()

        # Fill up key1
        for i in range(10):
            limiter.check_rate_limit("key1", max_requests=10, window_seconds=60)

        # key2 should still work
        assert limiter.check_rate_limit("key2", max_requests=10, window_seconds=60)

    def test_reset_clears_limit(self):
        """Reset should clear the limit for a key."""
        from api.middleware.rate_limit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter()

        # Fill up the limit
        for i in range(10):
            limiter.check_rate_limit("reset_key", max_requests=10, window_seconds=60)

        # Should be blocked
        assert not limiter.check_rate_limit("reset_key", max_requests=10, window_seconds=60)

        # Reset
        limiter.reset("reset_key")

        # Should work again
        assert limiter.check_rate_limit("reset_key", max_requests=10, window_seconds=60)
