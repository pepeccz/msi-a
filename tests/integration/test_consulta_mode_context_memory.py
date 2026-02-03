"""Integration test for CONSULTA_MODE context memory (Fix #3)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.modes.consulta_mode import ConsultaModeNode
from agent.state.conversation_state import ConversationState


@pytest.mark.asyncio
class TestConsultaModeContextMemory:
    """Test that CONSULTA_MODE remembers entities from history."""
    
    def setup_method(self):
        self.mode_node = ConsultaModeNode()
    
    async def test_remembers_elemento_from_previous_message(self):
        """Test that agent remembers 'subchasis' when user mentions it."""
        state: ConversationState = {
            "conversation_id": "test-123",
            "user_phone": "+34600000000",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "quiero modificar el subchasis"},
                {"role": "assistant", "content": "¿de qué vehículo?"},
            ],
            "mode_context": {},
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        # Mock the LLM and tools to avoid actual API calls
        mock_response = MagicMock()
        mock_response.content = "Perfecto, el subchasis se puede homologar."
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result = await self.mode_node._process_message("tengo una BMW R1200", state)
        
        # Check that entities were extracted and stored
        mode_context = result.get("mode_context", {})
        assert "remembered_elementos" in mode_context
        assert isinstance(mode_context["remembered_elementos"], list)
        # Check if subchasis or bastidor was extracted (both are valid)
        elementos_str = " ".join(mode_context["remembered_elementos"])
        assert "subchasis" in elementos_str or "bastidor" in elementos_str
    
    async def test_remembers_marca_modelo(self):
        """Test that marca and modelo are extracted and remembered."""
        state: ConversationState = {
            "conversation_id": "test-456",
            "user_phone": "+34600000001",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "tengo una BMW R1200"},
            ],
            "mode_context": {},
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        # Mock LLM
        mock_response = MagicMock()
        mock_response.content = "Entiendo, tienes una BMW R1200."
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result = await self.mode_node._process_message("¿se puede homologar?", state)
        
        mode_context = result.get("mode_context", {})
        assert mode_context.get("remembered_marca") == "BMW"
        assert mode_context.get("remembered_modelo") == "R1200"
    
    async def test_context_injected_into_prompt(self):
        """Test that remembered context is injected into system prompt."""
        state: ConversationState = {
            "conversation_id": "test-789",
            "user_phone": "+34600000002",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "quiero modificar el subchasis"},
                {"role": "assistant", "content": "¿de qué vehículo?"},
                {"role": "user", "content": "tengo una BMW R1200"},
            ],
            "mode_context": {
                "remembered_elementos": ["subchasis"],
                "remembered_marca": "BMW",
                "remembered_modelo": "R1200",
            },
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        # Mock LLM to capture the prompt
        mock_response = MagicMock()
        mock_response.content = "El presupuesto para homologar el subchasis es..."
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            await self.mode_node._process_message("¿cuánto cuesta?", state)
        
        # Check that LLM was called with context in prompt
        call_args = mock_llm.ainvoke.call_args
        messages = call_args[0][0]
        
        # Find system message
        system_message = next((m for m in messages if m["role"] == "system"), None)
        assert system_message is not None
        
        # Check that context was injected
        system_content = system_message["content"]
        assert "subchasis" in system_content.lower()
        assert "BMW" in system_content
        assert "R1200" in system_content
    
    async def test_no_context_when_history_empty(self):
        """Test that no context is added when history is empty."""
        state: ConversationState = {
            "conversation_id": "test-empty",
            "user_phone": "+34600000003",
            "current_mode": "CONSULTA_MODE",
            "message_history": [],
            "mode_context": {},
            "messages": [],
            "is_first_interaction": True,
            "client_type": "particular",
            "user_name": None,
        }
        
        mock_response = MagicMock()
        mock_response.content = "Hola, ¿en qué puedo ayudarte?"
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result = await self.mode_node._process_message("hola", state)
        
        mode_context = result.get("mode_context", {})
        assert mode_context.get("remembered_elementos", []) == []
        assert mode_context.get("remembered_marca") is None
        assert mode_context.get("remembered_modelo") is None
    
    async def test_multiple_elementos_remembered(self):
        """Test that multiple elementos are remembered."""
        state: ConversationState = {
            "conversation_id": "test-multi",
            "user_phone": "+34600000004",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "quiero cambiar el escape y la suspensión"},
            ],
            "mode_context": {},
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        mock_response = MagicMock()
        mock_response.content = "Ambos elementos se pueden homologar."
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result = await self.mode_node._process_message("¿cuánto costaría?", state)
        
        mode_context = result.get("mode_context", {})
        elementos = mode_context.get("remembered_elementos", [])
        
        # Check that at least one of the elementos was captured
        elementos_str = " ".join(elementos)
        assert len(elementos) >= 1
        # Should contain at least one of the mentioned elements
        has_escape = "escape" in elementos_str or "escapes" in elementos_str
        has_suspension = "suspensión" in elementos_str or "suspension" in elementos_str
        assert has_escape or has_suspension


@pytest.mark.asyncio
class TestConsultaModeContextPersistence:
    """Test that context persists across multiple turns."""
    
    def setup_method(self):
        self.mode_node = ConsultaModeNode()
    
    async def test_context_persists_across_turns(self):
        """Test that remembered entities persist across conversation turns."""
        # First turn: User mentions elemento
        state_turn1: ConversationState = {
            "conversation_id": "test-persist",
            "user_phone": "+34600000005",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "quiero modificar el subchasis"},
            ],
            "mode_context": {},
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        mock_response = MagicMock()
        mock_response.content = "¿De qué vehículo?"
        mock_response.tool_calls = None
        
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result_turn1 = await self.mode_node._process_message("quiero modificar el subchasis", state_turn1)
        
        # Second turn: User mentions vehicle (context should include elemento from turn 1)
        state_turn2: ConversationState = {
            "conversation_id": "test-persist",
            "user_phone": "+34600000005",
            "current_mode": "CONSULTA_MODE",
            "message_history": [
                {"role": "user", "content": "quiero modificar el subchasis"},
                {"role": "assistant", "content": "¿De qué vehículo?"},
                {"role": "user", "content": "tengo una BMW R1200"},
            ],
            "mode_context": result_turn1.get("mode_context", {}),  # Persist from turn 1
            "messages": [],
            "is_first_interaction": False,
            "client_type": "particular",
            "user_name": None,
        }
        
        with patch.object(self.mode_node, '_get_llm', return_value=mock_llm):
            result_turn2 = await self.mode_node._process_message("tengo una BMW R1200", state_turn2)
        
        mode_context = result_turn2.get("mode_context", {})
        
        # Should have both elemento and vehicle info
        elementos_str = " ".join(mode_context.get("remembered_elementos", []))
        assert "subchasis" in elementos_str or "bastidor" in elementos_str
        assert mode_context.get("remembered_marca") == "BMW"
        assert mode_context.get("remembered_modelo") == "R1200"
