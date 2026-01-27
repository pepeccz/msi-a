"""
Tests to verify all tools are properly registered for execution.

These tests ensure that every tool in ALL_TOOLS is also registered
in execute_tool_call's tool_map, preventing "Unknown tool" errors.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.tools import ALL_TOOLS


class TestToolRegistration:
    """Verify all exported tools can be executed."""

    def test_all_tools_have_names(self):
        """Every tool should have a name attribute."""
        for tool in ALL_TOOLS:
            assert hasattr(tool, "name"), f"Tool {tool} missing 'name' attribute"
            assert tool.name, f"Tool has empty name"

    def test_element_data_tools_in_all_tools(self):
        """Element data tools should be in ALL_TOOLS."""
        tool_names = [t.name for t in ALL_TOOLS]
        
        expected_tools = [
            "obtener_campos_elemento",
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
            "completar_elemento_actual",
            "obtener_progreso_elementos",
            "confirmar_documentacion_base",
            "reenviar_imagenes_elemento",
        ]
        
        for expected in expected_tools:
            assert expected in tool_names, f"Tool '{expected}' not found in ALL_TOOLS"

    def test_no_duplicate_tool_names(self):
        """Tool names should be unique."""
        tool_names = [t.name for t in ALL_TOOLS]
        duplicates = [name for name in tool_names if tool_names.count(name) > 1]
        assert not duplicates, f"Duplicate tool names found: {set(duplicates)}"


class TestExecuteToolCall:
    """Test that execute_tool_call can find all tools."""

    @pytest.fixture
    def mock_state(self):
        """Create a minimal mock state."""
        return {
            "conversation_id": "test-123",
            "messages": [],
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": "test-case-id",
                    "category_id": "test-category-id",
                    "element_codes": ["TEST_ELEMENT"],
                    "current_element_index": 0,
                    "element_phase": "photos",
                }
            }
        }

    @pytest.mark.asyncio
    async def test_element_data_tools_registered_in_execute_tool_call(self, mock_state):
        """
        Element data tools should be registered in execute_tool_call's tool_map.
        
        This test imports the function and checks the tool_map directly.
        """
        # Import the module to access execute_tool_call
        from agent.nodes import conversational_agent
        
        # Get the source code and verify tools are in tool_map
        # This is a static check - we verify the imports and tool_map entries exist
        import inspect
        source = inspect.getsource(conversational_agent.execute_tool_call)
        
        expected_tools = [
            "obtener_campos_elemento",
            "guardar_datos_elemento",
            "confirmar_fotos_elemento",
            "completar_elemento_actual",
            "obtener_progreso_elementos",
            "confirmar_documentacion_base",
            "reenviar_imagenes_elemento",
        ]
        
        for tool_name in expected_tools:
            # Check tool is in tool_map definition
            assert f'"{tool_name}"' in source, \
                f"Tool '{tool_name}' not found in execute_tool_call's tool_map"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Calling an unknown tool should return an error dict."""
        from agent.nodes.conversational_agent import execute_tool_call
        
        result = await execute_tool_call(
            {"name": "nonexistent_tool_xyz", "args": {}},
            state=None,
        )
        
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_known_tool_does_not_return_unknown_error(self):
        """
        Calling a known tool should not return "Unknown tool" error.
        
        The tool might fail for other reasons (missing args, state, etc.)
        but should not fail because it's not found in the tool_map.
        """
        from agent.nodes.conversational_agent import execute_tool_call
        
        # Test with a tool that doesn't require complex state
        result = await execute_tool_call(
            {"name": "listar_categorias", "args": {}},
            state=None,
        )
        
        # Should not have "Unknown tool" error
        # (might have other errors due to missing DB connection, etc.)
        if "error" in result:
            assert "Unknown tool" not in result["error"], \
                "listar_categorias should be registered in tool_map"


class TestToolMapCompleteness:
    """
    Comprehensive test to verify tool_map matches ALL_TOOLS.
    
    This catches cases where a tool is exported in __init__.py
    but not added to execute_tool_call's tool_map.
    """

    @pytest.mark.asyncio
    async def test_tool_map_contains_all_tools(self):
        """Every tool in ALL_TOOLS should be in execute_tool_call's tool_map."""
        from agent.nodes.conversational_agent import execute_tool_call
        import inspect
        
        source = inspect.getsource(execute_tool_call)
        
        missing_tools = []
        for tool in ALL_TOOLS:
            tool_name = tool.name
            # Check if tool_name is in the tool_map definition
            if f'"{tool_name}":' not in source and f"'{tool_name}':" not in source:
                missing_tools.append(tool_name)
        
        assert not missing_tools, \
            f"Tools missing from execute_tool_call's tool_map: {missing_tools}"
