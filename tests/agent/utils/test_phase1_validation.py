"""
Tests for Phase 1: Syntax and State Validation

Tests the syntactic and state-based parameter validation layers.

Coverage:
- SyntaxValidator: Required params, type validation
- StateValidator: State dependencies (categoria_slug, case_id)
- ToolValidationService: Integration of all layers
- Validation error formatting
"""

import pytest
from unittest.mock import Mock
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from agent.utils.tool_validation import (
    SyntaxValidator,
    StateValidator,
    ToolValidationService,
)


# =============================================================================
# HELPER FUNCTIONS - Mock Tool Creation
# =============================================================================

def create_mock_tool(
    name: str,
    required_params: dict[str, type] | None = None,
    optional_params: dict[str, type] | None = None,
) -> BaseTool:
    """
    Create a mock LangChain tool with Pydantic schema.
    
    Args:
        name: Tool name
        required_params: Dict of {param_name: type} for required params
        optional_params: Dict of {param_name: type} for optional params
    
    Returns:
        Mock BaseTool with proper args_schema
    """
    # Build Pydantic model fields dictionary
    fields_dict = {}
    annotations = {}
    
    if required_params:
        for param_name, param_type in required_params.items():
            annotations[param_name] = param_type
            fields_dict[param_name] = Field(..., description=f"Required {param_name}")
    
    if optional_params:
        for param_name, param_type in optional_params.items():
            annotations[param_name] = param_type
            fields_dict[param_name] = Field(None, description=f"Optional {param_name}")
    
    # Create Pydantic model dynamically
    ToolArgsSchema = type(
        f"{name}Args",
        (BaseModel,),
        {
            "__annotations__": annotations,
            **fields_dict
        }
    )
    
    # Create mock tool
    tool = Mock(spec=BaseTool)
    tool.name = name
    tool.args_schema = ToolArgsSchema
    
    return tool


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def syntax_validator():
    """Create a SyntaxValidator instance."""
    return SyntaxValidator()


@pytest.fixture
def state_validator():
    """Create a StateValidator instance."""
    return StateValidator()


@pytest.fixture
def full_validator():
    """Create a ToolValidationService with all layers."""
    return ToolValidationService()


# =============================================================================
# TESTS: SyntaxValidator - Required Parameters
# =============================================================================

class TestSyntaxValidatorRequired:
    """Test required parameter validation."""
    
    async def test_all_required_params_present(self, syntax_validator):
        """Should pass when all required params are present."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "elementos": list}
        )
        params = {
            "categoria_slug": "motos-part",
            "elementos": ["ESCAPE"]
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_missing_required_param(self, syntax_validator):
        """Should fail when required param is missing."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "elementos": list}
        )
        params = {
            "elementos": ["ESCAPE"]
            # Missing categoria_slug
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "categoria_slug" in errors[0]
        assert "required" in errors[0].lower()
    
    async def test_multiple_missing_params(self, syntax_validator):
        """Should report all missing required params."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "elementos": list, "case_id": str}
        )
        params = {}
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 3
    
    async def test_no_schema_skips_validation(self, syntax_validator):
        """Should skip validation when tool has no schema."""
        tool = Mock(spec=BaseTool)
        tool.name = "test_tool"
        tool.args_schema = None  # No schema
        
        params = {}
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        # Should pass (can't validate without schema)
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_optional_params_can_be_missing(self, syntax_validator):
        """Should pass when optional params are missing."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str},
            optional_params={"skip_validation": bool}
        )
        params = {
            "categoria_slug": "motos-part"
            # skip_validation is optional, can be missing
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0


# =============================================================================
# TESTS: SyntaxValidator - Type Validation
# =============================================================================

class TestSyntaxValidatorTypes:
    """Test type validation."""
    
    async def test_valid_types(self, syntax_validator):
        """Should pass when types match."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "count": int}
        )
        params = {
            "categoria_slug": "motos-part",
            "count": 5
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_wrong_type_str_expected(self, syntax_validator):
        """Should fail when type doesn't match (str expected)."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str}
        )
        params = {
            "categoria_slug": 123  # Wrong type (int instead of str)
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "categoria_slug" in errors[0]
        assert "str" in errors[0]
    
    async def test_wrong_type_int_expected(self, syntax_validator):
        """Should fail when type doesn't match (int expected)."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"count": int}
        )
        params = {
            "count": "5"  # Wrong type (str instead of int)
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "count" in errors[0]
        assert "int" in errors[0]
    
    async def test_none_value_skipped_in_type_check(self, syntax_validator):
        """Should skip type check for None values (optional params)."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str},
            optional_params={"tier_id": str}
        )
        params = {
            "categoria_slug": "motos-part",
            "tier_id": None  # None is valid for optional
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        # Type check is skipped for None values (line 90 in tool_validation.py)
        assert is_valid is True
        assert len(errors) == 0


# =============================================================================
# TESTS: StateValidator - State Dependencies
# =============================================================================

class TestStateValidatorDependencies:
    """Test state dependency validation."""
    
    async def test_required_state_present(self, state_validator):
        """Should pass when required state is present."""
        tool = Mock(spec=BaseTool)
        tool.name = "iniciar_expediente"
        
        params = {}
        state = {
            "categoria_slug": "motos-part",
            "user_id": "user-123"
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_required_state_missing(self, state_validator):
        """Should fail when required state is missing."""
        tool = Mock(spec=BaseTool)
        tool.name = "iniciar_expediente"
        
        params = {}
        state = {
            "categoria_slug": "motos-part"
            # Missing user_id
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "user_id" in errors[0]
    
    async def test_multiple_state_missing(self, state_validator):
        """Should report all missing state dependencies."""
        tool = Mock(spec=BaseTool)
        tool.name = "iniciar_expediente"
        
        params = {}
        state = {}  # Both categoria_slug and user_id missing
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 2
    
    async def test_none_value_treated_as_missing(self, state_validator):
        """Should treat None as missing."""
        tool = Mock(spec=BaseTool)
        tool.name = "iniciar_expediente"
        
        params = {}
        state = {
            "categoria_slug": "motos-part",
            "user_id": None  # None is invalid
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "user_id" in errors[0]
    
    async def test_tool_with_no_state_requirements(self, state_validator):
        """Should pass for tools without state requirements."""
        tool = Mock(spec=BaseTool)
        tool.name = "some_tool_without_state_deps"
        
        params = {}
        state = {}
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        # Tool not in STATE_REQUIREMENTS dict → no validation
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_case_id_dependency(self, state_validator):
        """Should validate case_id dependency for case tools."""
        tool = Mock(spec=BaseTool)
        tool.name = "actualizar_datos_personales"
        
        params = {}
        state = {
            "case_id": "case-123"
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_precio_comunicado_dependency(self, state_validator):
        """Should validate precio_comunicado for enviar_imagenes_ejemplo."""
        tool = Mock(spec=BaseTool)
        tool.name = "enviar_imagenes_ejemplo"
        
        params = {}
        state = {
            "precio_comunicado": True
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_calcular_tarifa_needs_categoria(self, state_validator):
        """Should validate categoria_slug for calcular_tarifa_con_elementos."""
        tool = Mock(spec=BaseTool)
        tool.name = "calcular_tarifa_con_elementos"
        
        params = {}
        state = {
            "categoria_slug": "motos-part"
        }
        
        is_valid, errors = await state_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0


# =============================================================================
# TESTS: ToolValidationService - Integration
# =============================================================================

class TestToolValidationServiceIntegration:
    """Test full validation pipeline (syntax + state + semantic)."""
    
    async def test_valid_params_all_layers_pass(self, full_validator):
        """Should pass when all layers validate."""
        tool = create_mock_tool(
            "listar_categorias",  # Tool with no state deps
            required_params={}
        )
        params = {}
        state = {}
        
        is_valid, errors, layer = await full_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
        assert layer == "none"  # No layer failed
    
    async def test_syntax_layer_fails_fast(self, full_validator):
        """Should fail at syntax layer and not check state/semantic."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str}
        )
        params = {}  # Missing required param
        state = {}
        
        is_valid, errors, layer = await full_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) >= 1
        assert layer == "syntax"
    
    async def test_state_layer_fails_after_syntax_passes(self, full_validator):
        """Should fail at state layer if syntax passes."""
        tool = create_mock_tool(
            "iniciar_expediente",
            required_params={}
        )
        # Override tool.name for state validator
        tool.name = "iniciar_expediente"
        
        params = {}
        state = {}  # Missing required state (categoria_slug, user_id)
        
        is_valid, errors, layer = await full_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) >= 1
        assert layer == "state"
    
    async def test_all_errors_collected_per_layer(self, full_validator):
        """Should collect all errors from the failing layer."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "elementos": list}
        )
        params = {}  # Both params missing
        state = {}
        
        is_valid, errors, layer = await full_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 2  # Both missing params reported
        assert layer == "syntax"


# =============================================================================
# TESTS: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    async def test_empty_params_empty_state_no_requirements(self, full_validator):
        """Should pass when no validation is needed."""
        tool = create_mock_tool("test_tool", required_params={})
        params = {}
        state = {}
        
        is_valid, errors, layer = await full_validator.validate(tool, params, state)
        
        assert is_valid is True
        assert len(errors) == 0
        assert layer == "none"
    
    async def test_extra_params_ignored(self, syntax_validator):
        """Should ignore extra params not in schema."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str}
        )
        params = {
            "categoria_slug": "motos-part",
            "extra_param": "ignored"  # Not in schema
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        # Extra params are ignored
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_complex_types_skipped(self, syntax_validator):
        """Should skip validation for complex types (Pydantic does it)."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"elementos": list}  # list is not str/int/float/bool
        )
        params = {
            "elementos": ["ESCAPE", "MANILLAR"]
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        # Complex types (list, dict, etc.) are skipped (line 96-98)
        assert is_valid is True
        assert len(errors) == 0
    
    async def test_mixed_valid_invalid_params(self, syntax_validator):
        """Should report only invalid params."""
        tool = create_mock_tool(
            "test_tool",
            required_params={"categoria_slug": str, "count": int}
        )
        params = {
            "categoria_slug": "motos-part",  # Valid
            "count": "not-a-number"  # Invalid (str instead of int)
        }
        state = {}
        
        is_valid, errors = await syntax_validator.validate(tool, params, state)
        
        assert is_valid is False
        assert len(errors) == 1
        assert "count" in errors[0]
    
    async def test_state_validator_different_tools_different_requirements(self, state_validator):
        """Should apply correct state requirements per tool."""
        # Tool 1: Requires case_id
        tool1 = Mock(spec=BaseTool)
        tool1.name = "actualizar_datos_personales"
        state1 = {"case_id": "case-123"}
        
        is_valid1, _ = await state_validator.validate(tool1, {}, state1)
        assert is_valid1 is True
        
        # Tool 2: Requires categoria_slug + user_id
        tool2 = Mock(spec=BaseTool)
        tool2.name = "iniciar_expediente"
        state2 = {"categoria_slug": "motos-part", "user_id": "user-123"}
        
        is_valid2, _ = await state_validator.validate(tool2, {}, state2)
        assert is_valid2 is True
        
        # Tool 2 with tool 1's state → should fail
        is_valid3, errors3 = await state_validator.validate(tool2, {}, state1)
        assert is_valid3 is False  # Missing categoria_slug, user_id
    
    async def test_validator_reusable(self, full_validator):
        """Should be reusable across multiple validations."""
        tool = create_mock_tool("test_tool", required_params={"param": str})
        
        # First validation
        is_valid1, _, _ = await full_validator.validate(tool, {"param": "val1"}, {})
        assert is_valid1 is True
        
        # Second validation (different params)
        is_valid2, _, _ = await full_validator.validate(tool, {"param": "val2"}, {})
        assert is_valid2 is True
        
        # Third validation (invalid)
        is_valid3, _, _ = await full_validator.validate(tool, {}, {})
        assert is_valid3 is False
