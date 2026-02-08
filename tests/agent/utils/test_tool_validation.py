"""
Tests for tool parameter validation system.

Covers:
- SyntaxValidator (required params, types)
- StateValidator (state dependencies)
- ToolValidationService (integration)

Phase 1: Core validation infrastructure
See: docs/plans/defensive-parameter-validation-system.md
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.utils.tool_validation import (
    SyntaxValidator,
    StateValidator,
    ToolValidationService,
    get_tool_validator,
)


# ==============================================================================
# TEST HELPERS - Mock Tools
# ==============================================================================

class SimpleToolArgs(BaseModel):
    """Simple tool args schema with required and optional params."""
    param1: str = Field(..., description="Required string param")
    param2: int = Field(..., description="Required int param")
    param3: str | None = Field(None, description="Optional string param")


class ComplexToolArgs(BaseModel):
    """Complex tool args with multiple types."""
    text_field: str
    number_field: int
    float_field: float
    bool_field: bool
    optional_field: str | None = None


def create_mock_tool(
    name: str,
    args_schema: type[BaseModel] | None = SimpleToolArgs,
) -> MagicMock:
    """Create a mock LangChain tool with schema."""
    mock_tool = MagicMock()
    mock_tool.name = name
    mock_tool.args_schema = args_schema
    
    # Mock __fields__ for Pydantic schema introspection
    if args_schema:
        mock_tool.args_schema.__fields__ = args_schema.__fields__
    
    return mock_tool


# ==============================================================================
# SyntaxValidator Tests (~10 tests)
# ==============================================================================

class TestSyntaxValidator:
    """Tests for SyntaxValidator."""
    
    @pytest.mark.asyncio
    async def test_missing_required_param(self):
        """Test syntax validator catches missing required parameter."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # Missing param2
        params = {"param1": "value1"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "param2" in errors[0]
        assert "Missing required parameter" in errors[0]
    
    @pytest.mark.asyncio
    async def test_all_required_params_present(self):
        """Test validation passes when all required params present."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # All required params
        params = {"param1": "value1", "param2": 42}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_optional_param_missing(self):
        """Test validation passes when optional param missing."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # Missing optional param3 (should pass)
        params = {"param1": "value1", "param2": 42}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_wrong_parameter_type(self):
        """Test validation catches wrong parameter type."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # param2 should be int, not str
        params = {"param1": "value1", "param2": "not_an_int"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "param2" in errors[0]
        assert "must be int" in errors[0]
    
    @pytest.mark.asyncio
    async def test_tool_with_no_schema(self):
        """Test validation passes with warning when tool has no schema."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool", args_schema=None)
        
        params = {"any": "params"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        # Should pass but log warning
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_empty_parameters_dict(self):
        """Test validation fails with empty params when required params exist."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        params = {}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        # Should report both missing params
        assert len(errors) == 2
        assert any("param1" in err for err in errors)
        assert any("param2" in err for err in errors)
    
    @pytest.mark.asyncio
    async def test_extra_parameters(self):
        """Test validation passes with extra parameters (not validated)."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # Extra param4 not in schema
        params = {"param1": "value1", "param2": 42, "param4": "extra"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        # Should pass - extra params not validated
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_none_value_for_required_param(self):
        """Test validation allows None for required param (Pydantic will catch)."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # param1 present but None
        params = {"param1": None, "param2": 42}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        # SyntaxValidator checks presence, not None
        # Pydantic will validate None values later
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_missing_parameters(self):
        """Test validation reports all missing required parameters."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool")
        
        # Both required params missing
        params = {"param3": "optional"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 2
        assert any("param1" in err for err in errors)
        assert any("param2" in err for err in errors)
    
    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_parameters(self):
        """Test validation with mix of valid/invalid parameters."""
        validator = SyntaxValidator()
        tool = create_mock_tool("test_tool", args_schema=ComplexToolArgs)
        
        # Some correct, some wrong types
        params = {
            "text_field": "correct",
            "number_field": "wrong_type",  # Should be int
            "float_field": 3.14,
            "bool_field": "not_bool",  # Should be bool
        }
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        # Should report both type errors
        assert len(errors) == 2
        assert any("number_field" in err and "int" in err for err in errors)
        assert any("bool_field" in err and "bool" in err for err in errors)


# ==============================================================================
# StateValidator Tests (~10 tests)
# ==============================================================================

class TestStateValidator:
    """Tests for StateValidator."""
    
    @pytest.mark.asyncio
    async def test_missing_required_state_key(self):
        """Test state validator catches missing required state key."""
        validator = StateValidator()
        tool = create_mock_tool("actualizar_datos_personales")
        
        params = {"nombre": "Juan"}
        state = {}  # Missing case_id
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "case_id" in errors[0]
    
    @pytest.mark.asyncio
    async def test_all_required_state_keys_present(self):
        """Test validation passes when all required state keys present."""
        validator = StateValidator()
        tool = create_mock_tool("actualizar_datos_personales")
        
        params = {"nombre": "Juan"}
        state = {"case_id": "123e4567-e89b-12d3-a456-426614174000"}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_tool_not_in_state_requirements(self):
        """Test validation passes for tool without state requirements."""
        validator = StateValidator()
        tool = create_mock_tool("listar_categorias")  # Not in STATE_REQUIREMENTS
        
        params = {}
        state = {}  # Empty state OK
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_state_key_is_none(self):
        """Test validation fails when required state key is None."""
        validator = StateValidator()
        tool = create_mock_tool("actualizar_datos_personales")
        
        params = {"nombre": "Juan"}
        state = {"case_id": None}  # Present but None
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "case_id" in errors[0]
    
    @pytest.mark.asyncio
    async def test_empty_state_dict_for_tool_needing_state(self):
        """Test validation fails with empty state for tool requiring state."""
        validator = StateValidator()
        tool = create_mock_tool("actualizar_datos_personales")
        
        params = {"nombre": "Juan"}
        state = {}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "case_id" in errors[0]
    
    @pytest.mark.asyncio
    async def test_iniciar_expediente_requires_categoria_and_user(self):
        """Test iniciar_expediente requires both categoria_slug and user_id."""
        validator = StateValidator()
        tool = create_mock_tool("iniciar_expediente")
        
        # Missing user_id
        params = {}
        state = {"categoria_slug": "motos-part"}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "user_id" in errors[0]
    
    @pytest.mark.asyncio
    async def test_completar_elemento_requires_case_and_index(self):
        """Test completar_elemento_actual requires case_id and current_element_index."""
        validator = StateValidator()
        tool = create_mock_tool("completar_elemento_actual")
        
        # Missing current_element_index
        params = {}
        state = {"case_id": "123"}
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "current_element_index" in errors[0]
    
    @pytest.mark.asyncio
    async def test_enviar_imagenes_requires_precio_comunicado(self):
        """Test enviar_imagenes_ejemplo requires precio_comunicado state."""
        validator = StateValidator()
        tool = create_mock_tool("enviar_imagenes_ejemplo")
        
        params = {}
        state = {}  # Missing precio_comunicado
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "precio_comunicado" in errors[0]
    
    @pytest.mark.asyncio
    async def test_calcular_tarifa_requires_categoria_slug(self):
        """Test calcular_tarifa_con_elementos requires categoria_slug."""
        validator = StateValidator()
        tool = create_mock_tool("calcular_tarifa_con_elementos")
        
        params = {"elementos": ["ESCAPE"]}
        state = {}  # Missing categoria_slug
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "categoria_slug" in errors[0]
    
    @pytest.mark.asyncio
    async def test_multiple_missing_state_keys(self):
        """Test validation reports all missing state keys."""
        validator = StateValidator()
        tool = create_mock_tool("iniciar_expediente")
        
        params = {}
        state = {}  # Missing both categoria_slug and user_id
        
        is_valid, errors = await validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 2
        assert any("categoria_slug" in err for err in errors)
        assert any("user_id" in err for err in errors)


# ==============================================================================
# ToolValidationService Tests (~10 tests)
# ==============================================================================

class TestToolValidationService:
    """Tests for ToolValidationService integration."""
    
    @pytest.mark.asyncio
    async def test_syntax_error_caught(self):
        """Test service catches syntax errors."""
        service = ToolValidationService()
        tool = create_mock_tool("test_tool")
        
        # Missing required param
        params = {"param1": "value1"}  # Missing param2
        state = {}
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "param2" in errors[0]
    
    @pytest.mark.asyncio
    async def test_state_error_caught(self):
        """Test service catches state errors."""
        service = ToolValidationService()
        tool = create_mock_tool("actualizar_datos_personales")
        
        # Valid params but missing state
        params = {"nombre": "Juan"}
        state = {}  # Missing case_id
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "case_id" in errors[0]
    
    @pytest.mark.asyncio
    async def test_both_syntax_and_state_errors(self):
        """Test service reports both syntax and state errors."""
        service = ToolValidationService()
        
        # Tool requiring both params and state
        class CombinedArgs(BaseModel):
            nombre: str
        
        tool = create_mock_tool("actualizar_datos_personales", args_schema=CombinedArgs)
        
        # Missing param AND missing state
        params = {}  # Missing nombre
        state = {}  # Missing case_id
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 2
        assert any("nombre" in err for err in errors)
        assert any("case_id" in err for err in errors)
    
    @pytest.mark.asyncio
    async def test_all_validations_pass(self):
        """Test service passes when all validations succeed."""
        service = ToolValidationService()
        tool = create_mock_tool("actualizar_datos_personales")
        
        # Valid params and state
        params = {"nombre": "Juan"}
        state = {"case_id": "123"}
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """Test get_tool_validator returns singleton instance."""
        validator1 = get_tool_validator()
        validator2 = get_tool_validator()
        
        assert validator1 is validator2
    
    @pytest.mark.asyncio
    async def test_no_fast_fail_collects_all_errors(self):
        """Test service collects errors from all validators (no fast-fail)."""
        service = ToolValidationService()
        
        class RequiresStateArgs(BaseModel):
            param1: str
            param2: int
        
        tool = create_mock_tool("actualizar_datos_personales", args_schema=RequiresStateArgs)
        
        # Multiple errors from both validators
        params = {"param1": "value"}  # Missing param2
        state = {}  # Missing case_id
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is False
        # Should have errors from BOTH validators
        assert len(errors) == 2
        assert any("param2" in err for err in errors)
        assert any("case_id" in err for err in errors)
    
    @pytest.mark.asyncio
    async def test_error_aggregation(self):
        """Test multiple errors are aggregated correctly."""
        service = ToolValidationService()
        
        # Tool with multiple required params and state
        class MultiArgs(BaseModel):
            field1: str
            field2: int
            field3: bool
        
        tool = create_mock_tool("completar_elemento_actual", args_schema=MultiArgs)
        
        # Missing multiple params and state
        params = {}  # Missing field1, field2, field3
        state = {}  # Missing case_id, current_element_index
        
        is_valid, errors = await service.validate(tool, params, state)
        
        assert is_valid is False
        # Should have 3 syntax errors + 2 state errors = 5 total
        assert len(errors) == 5
    
    @pytest.mark.asyncio
    async def test_logging_verification_on_error(self):
        """Test errors are logged correctly."""
        service = ToolValidationService()
        tool = create_mock_tool("test_tool")
        
        params = {}  # Missing params
        state = {}
        
        with patch("agent.utils.tool_validation.logger") as mock_logger:
            is_valid, errors = await service.validate(tool, params, state)
            
            # Should log warning about validation failure
            assert mock_logger.warning.called
            call_args = mock_logger.warning.call_args
            assert "tool_validation_failed" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_logging_verification_on_success(self):
        """Test success is logged correctly."""
        service = ToolValidationService()
        tool = create_mock_tool("test_tool")
        
        params = {"param1": "value", "param2": 42}
        state = {}
        
        with patch("agent.utils.tool_validation.logger") as mock_logger:
            is_valid, errors = await service.validate(tool, params, state)
            
            # Should log info about validation success
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args
            assert "tool_validation_passed" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_validator_coordination(self):
        """Test validators run in correct order (syntax then state)."""
        service = ToolValidationService()
        
        # Mock validators to track call order
        call_order = []
        
        async def mock_syntax_validate(*args, **kwargs):
            call_order.append("syntax")
            return (True, [])
        
        async def mock_state_validate(*args, **kwargs):
            call_order.append("state")
            return (True, [])
        
        service.syntax_validator.validate = mock_syntax_validate
        service.state_validator.validate = mock_state_validate
        
        tool = create_mock_tool("test_tool")
        await service.validate(tool, {}, {})
        
        # Syntax should run before state
        assert call_order == ["syntax", "state"]


# ==============================================================================
# Integration Tests
# ==============================================================================

class TestValidationIntegration:
    """Integration tests with real agent tools."""
    
    @pytest.mark.asyncio
    async def test_real_tool_iniciar_expediente(self):
        """Test validation with real iniciar_expediente tool."""
        from agent.tools.case_tools import iniciar_expediente
        
        validator = get_tool_validator()
        
        # Valid call
        params = {
            "codigos_elementos": ["ESCAPE"],
            "tarifa_calculada": {"datos": {"price": 100}},
            "tier_id": "123",
        }
        state = {
            "categoria_slug": "motos-part",
            "user_id": "456",
        }
        
        is_valid, errors = await validator.validate(iniciar_expediente, params, state)
        
        # Should pass all validations
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_real_tool_missing_state(self):
        """Test validation fails with missing state for real tool."""
        from agent.tools.case_tools import iniciar_expediente
        
        validator = get_tool_validator()
        
        # Valid params but missing state
        params = {
            "codigos_elementos": ["ESCAPE"],
            "tarifa_calculada": {"datos": {"price": 100}},
            "tier_id": "123",
        }
        state = {}  # Missing categoria_slug and user_id
        
        is_valid, errors = await validator.validate(iniciar_expediente, params, state)
        
        assert is_valid is False
        assert any("categoria_slug" in err for err in errors)
        assert any("user_id" in err for err in errors)
