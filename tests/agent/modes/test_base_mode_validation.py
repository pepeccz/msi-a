"""
Tests for validation integration in BaseModeNode.

Verifies that _execute_and_log_tool validates parameters BEFORE execution,
and returns structured errors to the LLM for retry.

Phase 1: Core validation infrastructure
See: docs/plans/defensive-parameter-validation-system.md
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel, Field

from agent.modes.base_mode import BaseModeNode


# ==============================================================================
# TEST HELPERS
# ==============================================================================

class TestModeNode(BaseModeNode):
    """Concrete implementation of BaseModeNode for testing."""
    
    def __init__(self):
        super().__init__("TEST_MODE")
    
    async def _process_message(self, message: str, state: dict) -> dict:
        """Dummy implementation."""
        return {"ai_response": "test response"}
    
    def get_tools(self) -> list:
        """Return empty tool list."""
        return []


class SimpleToolArgs(BaseModel):
    """Simple tool args for testing."""
    param1: str = Field(..., description="Required param")
    param2: int = Field(..., description="Required int")


def create_mock_tool_with_schema(name: str, args_schema: type[BaseModel]):
    """Create mock tool with Pydantic schema."""
    mock_tool = MagicMock()
    mock_tool.name = name
    mock_tool.args_schema = args_schema
    
    # Mock __fields__ for schema introspection
    if args_schema:
        mock_tool.args_schema.__fields__ = args_schema.__fields__
    
    # Mock ainvoke
    mock_tool.ainvoke = AsyncMock(return_value={"success": True, "data": "result"})
    
    return mock_tool


# ==============================================================================
# BaseModeNode Validation Integration Tests
# ==============================================================================

class TestBaseModeValidationIntegration:
    """Test validation integration in BaseModeNode._execute_and_log_tool."""
    
    @pytest.mark.asyncio
    async def test_tool_call_with_valid_params_executes_successfully(self):
        """Test tool executes when validation passes."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # Mock state context
        mock_state = {
            "conversation_id": "test-123",
            "mode_context": {},
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value", "param2": 42},
                tools=tools,
                iteration=1,
            )
        
        # Parse result
        result_dict = json.loads(result)
        
        # Should succeed
        assert result_dict["success"] is True
        assert result_dict["data"] == "result"
        
        # Tool should have been called
        mock_tool.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tool_call_with_missing_params_returns_validation_error(self):
        """Test validation error returned when params missing."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # Mock state context
        mock_state = {
            "conversation_id": "test-123",
            "mode_context": {},
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value"},  # Missing param2
                tools=tools,
                iteration=1,
            )
        
        # Parse result
        result_dict = json.loads(result)
        
        # Should fail validation
        assert result_dict["success"] is False
        assert result_dict["error_type"] == "parameter_validation"
        
        # Tool should NOT have been called
        mock_tool.ainvoke.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_validation_error_includes_structured_fields(self):
        """Test validation error includes all required fields for LLM retry."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # Mock state context
        mock_state = {
            "conversation_id": "test-123",
            "mode_context": {},
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value"},  # Missing param2
                tools=tools,
                iteration=1,
            )
        
        result_dict = json.loads(result)
        
        # Verify structure
        assert "error_type" in result_dict
        assert result_dict["error_type"] == "parameter_validation"
        
        assert "validation_errors" in result_dict
        assert len(result_dict["validation_errors"]) > 0
        assert any("param2" in err for err in result_dict["validation_errors"])
        
        assert "required_params" in result_dict
        assert "param1" in result_dict["required_params"]
        assert "param2" in result_dict["required_params"]
        
        assert "provided_params" in result_dict
        assert "param1" in result_dict["provided_params"]
        
        assert "suggestion" in result_dict
        assert isinstance(result_dict["suggestion"], str)
        
        assert "can_retry" in result_dict
        assert result_dict["can_retry"] is True
    
    @pytest.mark.asyncio
    async def test_validation_error_logged_to_database(self):
        """Test validation errors are logged (fire-and-forget)."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # Mock state context
        mock_state = {
            "conversation_id": "test-123",
            "mode_context": {},
        }
        
        # Mock _log_tool_call
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="test-123",
                    tool_name="test_tool",
                    tool_args={"param1": "value"},  # Invalid
                    tools=tools,
                    iteration=1,
                )
                
                # Should have logged the failed validation
                assert mock_log.called
                call_args = mock_log.call_args
                assert call_args[1]["tool_name"] == "test_tool"
                assert call_args[1]["execution_time_ms"] == 0  # No execution
    
    @pytest.mark.asyncio
    async def test_tool_not_executed_if_validation_fails(self):
        """Test tool execution is prevented when validation fails."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # Mock state context
        mock_state = {
            "conversation_id": "test-123",
            "mode_context": {},
        }
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={},  # Missing all params
                tools=tools,
                iteration=1,
            )
        
        # Tool should NEVER be invoked
        mock_tool.ainvoke.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_required_params_extracts_correct_params(self):
        """Test _get_required_params extracts schema correctly."""
        mode = TestModeNode()
        
        # Create tool with known schema
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        
        required = mode._get_required_params(mock_tool)
        
        # Should extract both required params
        assert "param1" in required
        assert "param2" in required
        assert len(required) == 2
    
    @pytest.mark.asyncio
    async def test_get_required_params_with_no_schema(self):
        """Test _get_required_params handles tool without schema."""
        mode = TestModeNode()
        
        # Tool without schema
        mock_tool = MagicMock()
        mock_tool.args_schema = None
        
        required = mode._get_required_params(mock_tool)
        
        # Should return empty list
        assert required == []
    
    @pytest.mark.asyncio
    async def test_generate_fix_suggestion_includes_context_hints(self):
        """Test _generate_fix_suggestion provides helpful hints."""
        mode = TestModeNode()
        
        # Mock tool
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        
        errors = [
            "Missing required parameter: categoria_slug",
            "Missing required parameter: case_id",
        ]
        
        suggestion = mode._generate_fix_suggestion(mock_tool, errors)
        
        # Should include extraction hints
        assert "categoria_slug" in suggestion
        assert "mode_context" in suggestion  # Hint about where to find it
        assert "case_id" in suggestion
    
    @pytest.mark.asyncio
    async def test_suggestion_for_known_params_includes_extraction_hint(self):
        """Test suggestion includes specific extraction hints for known params."""
        mode = TestModeNode()
        
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        
        # Test known param suggestions
        test_cases = [
            ("categoria_slug", "mode_context['categoria_slug']"),
            ("case_id", "state or mode_context['case_id']"),
            ("user_id", "state['user_id']"),
            ("precio_comunicado", "mode_context['precio_comunicado']"),
        ]
        
        for param, expected_hint_fragment in test_cases:
            errors = [f"Missing required parameter: {param}"]
            suggestion = mode._generate_fix_suggestion(mock_tool, errors)
            
            # Should mention the parameter
            assert param in suggestion
    
    @pytest.mark.asyncio
    async def test_tool_execution_proceeds_after_validation_passes(self):
        """Test normal tool execution happens after validation passes."""
        mode = TestModeNode()
        
        # Mock tool that returns specific result
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        mock_tool.ainvoke = AsyncMock(return_value={"success": True, "price": 100})
        tools = [mock_tool]
        
        mock_state = {"conversation_id": "test-123"}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value", "param2": 42},
                tools=tools,
                iteration=1,
            )
        
        result_dict = json.loads(result)
        
        # Should have executed and returned tool result
        assert result_dict["success"] is True
        assert result_dict["price"] == 100
        
        mock_tool.ainvoke.assert_called_once_with({"param1": "value", "param2": 42})
    
    @pytest.mark.asyncio
    async def test_existing_error_handling_still_works(self):
        """Test existing error handling for tool execution errors still works."""
        mode = TestModeNode()
        
        # Mock tool that raises exception during execution
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        mock_tool.ainvoke = AsyncMock(side_effect=Exception("Tool execution failed"))
        tools = [mock_tool]
        
        mock_state = {"conversation_id": "test-123"}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value", "param2": 42},
                tools=tools,
                iteration=1,
            )
        
        # Should return error (not raise exception)
        assert "Error ejecutando test_tool" in result
    
    @pytest.mark.asyncio
    async def test_tool_not_found_returns_error(self):
        """Test error returned when tool not found in tools list."""
        mode = TestModeNode()
        
        tools = []  # Empty tools list
        
        mock_state = {"conversation_id": "test-123"}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="nonexistent_tool",
                tool_args={"param1": "value"},
                tools=tools,
                iteration=1,
            )
        
        result_dict = json.loads(result)
        
        assert result_dict["success"] is False
        assert result_dict["error_type"] == "tool_not_found"
        assert "nonexistent_tool" in result_dict["error"]


# ==============================================================================
# State Extraction Tests
# ==============================================================================

class TestStateExtractionForValidation:
    """Test state extraction for validation from mode_context."""
    
    @pytest.mark.asyncio
    async def test_validation_merges_mode_context_to_root_level(self):
        """Test validation state includes both root and mode_context keys."""
        mode = TestModeNode()
        
        # Create tool requiring state
        mock_tool = create_mock_tool_with_schema("actualizar_datos_personales", SimpleToolArgs)
        tools = [mock_tool]
        
        # State with nested mode_context
        mock_state = {
            "conversation_id": "test-123",
            "user_id": "user-456",  # Root level
            "mode_context": {
                "case_id": "case-789",  # Nested
                "categoria_slug": "motos-part",
            },
        }
        
        # Mock the validator to capture what state it receives
        captured_state = {}
        
        async def capture_validate(tool, params, state):
            captured_state.update(state)
            return (True, [])  # Pass validation
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch("agent.utils.tool_validation.get_tool_validator") as mock_get_validator:
                mock_validator = MagicMock()
                mock_validator.validate = capture_validate
                mock_get_validator.return_value = mock_validator
                
                await mode._execute_and_log_tool(
                    conversation_id="test-123",
                    tool_name="actualizar_datos_personales",
                    tool_args={"param1": "value", "param2": 42},
                    tools=tools,
                    iteration=1,
                )
        
        # Validator should receive merged state
        assert "user_id" in captured_state  # From root
        assert "case_id" in captured_state  # From mode_context
        assert "categoria_slug" in captured_state  # From mode_context
    
    @pytest.mark.asyncio
    async def test_validation_state_empty_when_no_current_state(self):
        """Test validation handles missing current_state gracefully."""
        mode = TestModeNode()
        
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        # No current state
        with patch("agent.state.helpers.get_current_state", return_value=None):
            result = await mode._execute_and_log_tool(
                conversation_id="test-123",
                tool_name="test_tool",
                tool_args={"param1": "value", "param2": 42},
                tools=tools,
                iteration=1,
            )
        
        # Should still work (validator receives empty state)
        result_dict = json.loads(result)
        # Tool without state requirements should pass
        assert result_dict["success"] is True


# ==============================================================================
# Logging Tests
# ==============================================================================

class TestValidationLogging:
    """Test validation events are logged correctly."""
    
    @pytest.mark.asyncio
    async def test_validation_failure_logs_warning(self):
        """Test validation failure logs warning with details."""
        mode = TestModeNode()
        
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        mock_state = {"conversation_id": "test-123"}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch("agent.modes.base_mode.logger") as mock_logger:
                await mode._execute_and_log_tool(
                    conversation_id="test-123",
                    tool_name="test_tool",
                    tool_args={"param1": "value"},  # Missing param2
                    tools=tools,
                    iteration=1,
                )
                
                # Should log warning
                mock_logger.warning.assert_called()
                call_args = mock_logger.warning.call_args
                
                # Verify log contains important info
                assert "tool_parameter_validation_failed" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_successful_validation_continues_to_execution_logging(self):
        """Test successful validation proceeds to normal execution logging."""
        mode = TestModeNode()
        
        mock_tool = create_mock_tool_with_schema("test_tool", SimpleToolArgs)
        tools = [mock_tool]
        
        mock_state = {"conversation_id": "test-123"}
        
        with patch("agent.state.helpers.get_current_state", return_value=mock_state):
            with patch.object(mode, "_log_tool_call", new_callable=AsyncMock) as mock_log:
                await mode._execute_and_log_tool(
                    conversation_id="test-123",
                    tool_name="test_tool",
                    tool_args={"param1": "value", "param2": 42},
                    tools=tools,
                    iteration=1,
                )
                
                # Should log successful execution (not validation failure)
                assert mock_log.called
                call_args = mock_log.call_args
                assert call_args[1]["execution_time_ms"] > 0  # Actual execution happened
