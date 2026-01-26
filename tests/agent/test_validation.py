"""Security tests for input validation."""

import pytest
from agent.utils.validation import validate_category_slug


class TestCategorySlugValidation:
    """Test category slug validation against injection attacks."""
    
    @pytest.mark.parametrize("malicious_input,attack_type", [
        ("'; DROP TABLE vehicle_category; --", "SQL Injection"),
        ("admin' OR '1'='1", "SQL Injection Boolean"),
        ("../../../etc/passwd", "Path Traversal"),
        ("<script>alert('xss')</script>", "XSS"),
        ("motos%20OR%201=1", "URL Encoded Injection"),
        ("../../", "Directory Traversal"),
        ("motos\x00part", "Null Byte Injection"),
        ("MOTOS-PART", "Case Bypass Attempt"),
        ("motos_part", "Underscore Bypass"),
        ("motos part", "Space Injection"),
        ("a" * 100, "Buffer Overflow"),
        ("motos--part", "Double Hyphen"),
        ("-motos-part", "Leading Hyphen"),
        ("motos-part-", "Trailing Hyphen"),
        ("motos\npart", "Newline Injection"),
        ("motos\tpart", "Tab Injection"),
    ])
    def test_rejects_malicious_slugs(self, malicious_input, attack_type):
        """Verify malicious input is rejected."""
        with pytest.raises(ValueError, match="Invalid category slug"):
            validate_category_slug(malicious_input)
    
    @pytest.mark.parametrize("valid_slug", [
        "motos-part",
        "aseicars-prof",
        "turismos-2024",
        "a",
        "test-123-abc",
        "categoria-con-muchos-guiones-separados",
        "abc123",
        "123",
        "a-b-c-d-e-f",
    ])
    def test_accepts_valid_slugs(self, valid_slug):
        """Verify valid slugs pass validation."""
        assert validate_category_slug(valid_slug) == valid_slug
    
    def test_rejects_empty_slug(self):
        """Empty slug should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_category_slug("")
    
    def test_rejects_long_slug(self):
        """Excessively long slug should raise ValueError."""
        long_slug = "a" * 51  # MAX_SLUG_LENGTH = 50
        with pytest.raises(ValueError, match="too long"):
            validate_category_slug(long_slug)
    
    def test_accepts_max_length_slug(self):
        """Slug at exactly max length should be accepted."""
        max_slug = "a" * 50  # MAX_SLUG_LENGTH = 50
        assert validate_category_slug(max_slug) == max_slug
    
    def test_error_message_includes_slug(self):
        """Error message should include the invalid slug for debugging."""
        invalid_slug = "INVALID_SLUG"
        with pytest.raises(ValueError) as exc_info:
            validate_category_slug(invalid_slug)
        
        assert invalid_slug in str(exc_info.value)
    
    def test_error_message_helpful(self):
        """Error message should explain what characters are allowed."""
        with pytest.raises(ValueError) as exc_info:
            validate_category_slug("INVALID")
        
        assert "lowercase" in str(exc_info.value)
        assert "numbers" in str(exc_info.value)
        assert "hyphens" in str(exc_info.value)
