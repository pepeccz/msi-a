"""
Tests for Phase 4: Tool Decorators (Defensive Hardening)

Tests the defensive validation decorators for tool hardening.

Coverage:
- Format validators (email, phone, DNI)
- Decorator integration
- Error handling
- Edge cases
"""

import pytest
from agent.utils.tool_decorators import (
    validate_email,
    validate_phone,
    validate_dni,
    validate_email_format,
    validate_phone_format,
    validate_dni_format,
    validate_required_fields,
    validate_state_completeness,
)


# =============================================================================
# TESTS: Format Validators
# =============================================================================

class TestEmailValidator:
    """Test email format validation."""
    
    def test_valid_email(self):
        """Should accept valid email formats."""
        is_valid, _ = validate_email("user@example.com")
        assert is_valid is True
        is_valid, _ = validate_email("test.user@domain.co.uk")
        assert is_valid is True
        is_valid, _ = validate_email("user+tag@example.com")
        assert is_valid is True
    
    def test_invalid_email(self):
        """Should reject invalid email formats."""
        is_valid, error = validate_email("notanemail")
        assert is_valid is False
        assert "formato" in error.lower() or "inválido" in error.lower()
        is_valid, _ = validate_email("@example.com")
        assert is_valid is False
        is_valid, _ = validate_email("user@")
        assert is_valid is False
        is_valid, _ = validate_email("user @example.com")
        assert is_valid is False  # Space
    
    def test_empty_email(self):
        """Should reject empty/None email."""
        is_valid, error = validate_email("")
        assert is_valid is False
        assert "vacío" in error.lower()
        is_valid, _ = validate_email(None)
        assert is_valid is False
    
    def test_email_with_whitespace(self):
        """Should handle whitespace (strips it)."""
        is_valid, _ = validate_email("  user@example.com  ")
        assert is_valid is True


class TestPhoneValidator:
    """Test Spanish phone format validation."""
    
    def test_valid_phone_formats(self):
        """Should accept valid Spanish phone formats."""
        is_valid, _ = validate_phone("+34600000000")
        assert is_valid is True  # International
        is_valid, _ = validate_phone("600000000")
        assert is_valid is True     # National
        is_valid, _ = validate_phone("+34 600 000 000")
        assert is_valid is True  # With spaces
        is_valid, _ = validate_phone("+34-600-000-000")
        assert is_valid is True  # With dashes
    
    def test_valid_mobile_prefixes(self):
        """Should accept all valid Spanish mobile prefixes (6/7/8/9)."""
        for prefix in ['6', '7', '8', '9']:
            is_valid, _ = validate_phone(f"{prefix}00000000")
            assert is_valid is True
    
    def test_invalid_phone_formats(self):
        """Should reject invalid phone formats."""
        is_valid, error = validate_phone("500000000")
        assert is_valid is False    # Invalid prefix (5)
        assert "inválido" in error.lower()
        is_valid, _ = validate_phone("12345")
        assert is_valid is False        # Too short
        is_valid, _ = validate_phone("+34500000000")
        assert is_valid is False # Invalid prefix with +34
    
    def test_empty_phone(self):
        """Should reject empty/None phone."""
        is_valid, error = validate_phone("")
        assert is_valid is False
        assert "vacío" in error.lower()
        is_valid, _ = validate_phone(None)
        assert is_valid is False


class TestDNIValidator:
    """Test Spanish DNI/NIE format validation."""
    
    def test_valid_dni(self):
        """Should accept valid DNI format."""
        is_valid, _ = validate_dni("12345678Z")
        assert is_valid is True  # Valid DNI with check letter
    
    def test_valid_nie(self):
        """Should accept valid NIE formats."""
        is_valid, _ = validate_dni("X1234567L")
        assert is_valid is True  # NIE with X
        is_valid, _ = validate_dni("Y1234567X")
        assert is_valid is True  # NIE with Y
        is_valid, _ = validate_dni("Z1234567R")
        assert is_valid is True  # NIE with Z
    
    def test_invalid_dni_format(self):
        """Should reject invalid DNI/NIE formats."""
        is_valid, error = validate_dni("1234567A")
        assert is_valid is False   # Too short
        assert "formato" in error.lower() or "inválido" in error.lower()
        is_valid, _ = validate_dni("123456789A")
        assert is_valid is False # Too long
        is_valid, _ = validate_dni("ABCDEFGHA")
        assert is_valid is False  # All letters
    
    def test_invalid_check_letter(self):
        """Should reject DNI/NIE with wrong check letter."""
        is_valid, error = validate_dni("12345678A")
        assert is_valid is False  # Wrong letter (should be Z)
        assert "letra" in error.lower() or "control" in error.lower()
    
    def test_empty_dni(self):
        """Should reject empty/None DNI."""
        is_valid, error = validate_dni("")
        assert is_valid is False
        assert "vacío" in error.lower()
        is_valid, _ = validate_dni(None)
        assert is_valid is False
    
    def test_case_insensitive(self):
        """Should accept lowercase DNI/NIE."""
        is_valid, _ = validate_dni("12345678z")
        assert is_valid is True  # Lowercase
        is_valid, _ = validate_dni("x1234567l")
        assert is_valid is True  # Lowercase NIE


# =============================================================================
# TESTS: Decorators
# =============================================================================

class TestEmailFormatDecorator:
    """Test @validate_email_format decorator."""
    
    async def test_valid_email_passes(self):
        """Should pass through valid email."""
        @validate_email_format(param="email")
        async def mock_tool(email: str):
            return {"success": True, "email": email}
        
        result = await mock_tool(email="user@example.com")
        
        assert result["success"] is True
        assert result["email"] == "user@example.com"
    
    async def test_invalid_email_blocks(self):
        """Should block invalid email and return error."""
        @validate_email_format(param="email")
        async def mock_tool(email: str):
            return {"success": True, "email": email}
        
        result = await mock_tool(email="notanemail")
        
        assert result["success"] is False
        assert "error" in result
        assert "error_type" in result
        assert result["error_type"] == "validation_error"
        assert "validation_errors" in result
    
    async def test_empty_email_allowed(self):
        """Should allow empty email (optional param)."""
        @validate_email_format(param="email")
        async def mock_tool(email: str = None):
            return {"success": True}
        
        result = await mock_tool(email=None)
        
        # Empty/None is allowed (optional param)
        assert result["success"] is True


class TestPhoneFormatDecorator:
    """Test @validate_phone_format decorator."""
    
    async def test_valid_phone_passes(self):
        """Should pass through valid phone."""
        @validate_phone_format(param="telefono")
        async def mock_tool(telefono: str):
            return {"success": True, "telefono": telefono}
        
        result = await mock_tool(telefono="+34600000000")
        
        assert result["success"] is True
        assert result["telefono"] == "+34600000000"
    
    async def test_invalid_phone_blocks(self):
        """Should block invalid phone and return error."""
        @validate_phone_format(param="telefono")
        async def mock_tool(telefono: str):
            return {"success": True}
        
        result = await mock_tool(telefono="12345")
        
        assert result["success"] is False
        assert "error" in result
        assert result["error_type"] == "validation_error"


class TestDNIFormatDecorator:
    """Test @validate_dni_format decorator."""
    
    async def test_valid_dni_passes(self):
        """Should pass through valid DNI."""
        @validate_dni_format(param="dni")
        async def mock_tool(dni: str):
            return {"success": True, "dni": dni}
        
        result = await mock_tool(dni="12345678Z")
        
        assert result["success"] is True
        assert result["dni"] == "12345678Z"
    
    async def test_invalid_dni_blocks(self):
        """Should block invalid DNI and return error."""
        @validate_dni_format(param="dni")
        async def mock_tool(dni: str):
            return {"success": True}
        
        result = await mock_tool(dni="INVALID")
        
        assert result["success"] is False
        assert "error" in result
        assert result["error_type"] == "validation_error"


class TestRequiredFieldsDecorator:
    """Test @validate_required_fields decorator."""
    
    async def test_all_fields_present_passes(self):
        """Should pass when all required fields present."""
        def get_required(kwargs):
            return ["field1", "field2"]
        
        @validate_required_fields(get_required_fields=get_required)
        async def mock_tool(field1: str, field2: str):
            return {"success": True}
        
        result = await mock_tool(field1="val1", field2="val2")
        
        assert result["success"] is True
    
    async def test_missing_field_blocks(self):
        """Should block when required field missing."""
        def get_required(kwargs):
            return ["field1", "field2"]
        
        @validate_required_fields(get_required_fields=get_required)
        async def mock_tool(field1: str = None, field2: str = None):
            return {"success": True}
        
        result = await mock_tool(field1="val1")  # Missing field2
        
        assert result["success"] is False
        assert "missing_fields" in result
        assert "field2" in result["missing_fields"]
    
    async def test_empty_string_treated_as_missing(self):
        """Should treat empty string as missing."""
        def get_required(kwargs):
            return ["field1"]
        
        @validate_required_fields(get_required_fields=get_required)
        async def mock_tool(field1: str = ""):
            return {"success": True}
        
        result = await mock_tool(field1="")
        
        assert result["success"] is False
        assert "field1" in result["missing_fields"]
    
    async def test_dynamic_required_fields(self):
        """Should handle dynamic required fields based on other params."""
        def get_required(kwargs):
            # Dynamic: If needs_photos=True, require "fotos"
            if kwargs.get("needs_photos"):
                return ["fotos"]
            return []
        
        @validate_required_fields(get_required_fields=get_required)
        async def mock_tool(needs_photos: bool = False, fotos: list = None):
            return {"success": True}
        
        # Case 1: needs_photos=False → fotos not required
        result1 = await mock_tool(needs_photos=False)
        assert result1["success"] is True
        
        # Case 2: needs_photos=True, fotos missing → should fail
        result2 = await mock_tool(needs_photos=True)
        assert result2["success"] is False
        assert "fotos" in result2["missing_fields"]
        
        # Case 3: needs_photos=True, fotos present → should pass
        result3 = await mock_tool(needs_photos=True, fotos=["foto1.jpg"])
        assert result3["success"] is True


class TestStateCompletenessDecorator:
    """Test @validate_state_completeness decorator."""
    
    async def test_complete_state_passes(self):
        """Should pass when state is complete."""
        def check_complete(state):
            missing = []
            if not state.get("datos_personales"):
                missing.append("Datos personales")
            return (len(missing) == 0, missing)
        
        @validate_state_completeness(check_completeness=check_complete)
        async def mock_tool(state: dict):
            return {"success": True}
        
        result = await mock_tool(state={"datos_personales": {"nombre": "Test"}})
        
        assert result["success"] is True
    
    async def test_incomplete_state_blocks(self):
        """Should block when state incomplete."""
        def check_complete(state):
            missing = []
            if not state.get("datos_personales"):
                missing.append("Datos personales")
            if not state.get("datos_vehiculo"):
                missing.append("Datos del vehículo")
            return (len(missing) == 0, missing)
        
        @validate_state_completeness(check_completeness=check_complete)
        async def mock_tool(state: dict):
            return {"success": True}
        
        result = await mock_tool(state={"datos_personales": {"nombre": "Test"}})
        
        assert result["success"] is False
        assert "missing_items" in result
        assert "Datos del vehículo" in result["missing_items"]


# =============================================================================
# TESTS: Decorator Stacking
# =============================================================================

class TestDecoratorStacking:
    """Test multiple decorators on same function."""
    
    async def test_multiple_format_validators(self):
        """Should stack multiple format validators."""
        @validate_email_format(param="email")
        @validate_phone_format(param="telefono")
        @validate_dni_format(param="dni")
        async def mock_tool(email: str, telefono: str, dni: str):
            return {"success": True}
        
        # All valid → should pass
        result1 = await mock_tool(
            email="user@example.com",
            telefono="+34600000000",
            dni="12345678Z"
        )
        assert result1["success"] is True
        
        # Invalid email → should fail at first decorator
        result2 = await mock_tool(
            email="invalid",
            telefono="+34600000000",
            dni="12345678Z"
        )
        assert result2["success"] is False
        assert "email" in result2["error"].lower()
    
    async def test_format_and_required_fields(self):
        """Should stack format validators with required fields."""
        def get_required(kwargs):
            return ["email", "telefono"]
        
        @validate_required_fields(get_required_fields=get_required)
        @validate_email_format(param="email")
        @validate_phone_format(param="telefono")
        async def mock_tool(email: str = None, telefono: str = None):
            return {"success": True}
        
        # All present and valid → pass
        result1 = await mock_tool(email="user@example.com", telefono="+34600000000")
        assert result1["success"] is True
        
        # Missing email → fail at required fields
        result2 = await mock_tool(telefono="+34600000000")
        assert result2["success"] is False
        assert "missing_fields" in result2


# =============================================================================
# TESTS: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    async def test_decorator_with_no_matching_param(self):
        """Should pass through when param not in kwargs."""
        @validate_email_format(param="email")
        async def mock_tool(other_param: str):
            return {"success": True}
        
        # email not in kwargs → decorator should pass through
        result = await mock_tool(other_param="value")
        assert result["success"] is True
    
    async def test_unicode_characters(self):
        """Should handle unicode characters."""
        # Unicode in domain is not supported (correct for Spanish use case)
        is_valid, _ = validate_email("user@domäin.com")
        assert is_valid is False  # Unicode domain not allowed
        is_valid, _ = validate_dni("12345678Z")
        assert is_valid is True  # ASCII only DNI valid
    
    async def test_very_long_inputs(self):
        """Should handle very long inputs gracefully."""
        long_email = "a" * 1000 + "@example.com"
        is_valid, _ = validate_email(long_email)
        assert is_valid is True  # Still valid format
        
        long_phone = "6" + "0" * 1000
        is_valid, _ = validate_phone(long_phone)
        assert is_valid is False  # Too long
