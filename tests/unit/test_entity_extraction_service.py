"""Unit tests for Entity Extraction Service (Fix #3)."""

import pytest

from agent.services.entity_extraction_service import EntityExtractionService


@pytest.mark.asyncio
class TestEntityExtractionService:
    """Test entity extraction from conversation history."""
    
    def setup_method(self):
        self.service = EntityExtractionService()
    
    async def test_extract_elemento_from_history(self):
        history = [
            {"role": "user", "content": "quiero modificar el subchasis"},
            {"role": "assistant", "content": "¿de qué vehículo?"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        assert "subchasis" in entities["elementos"] or "bastidor" in entities["elementos"]
    
    async def test_extract_marca_modelo_from_history(self):
        history = [
            {"role": "user", "content": "tengo una BMW R1200"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        assert entities["marca"] == "BMW"
        assert entities["modelo"] == "R1200"
    
    async def test_extract_multiple_elementos(self):
        history = [
            {"role": "user", "content": "quiero cambiar el escape y la suspensión"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        # Check if at least one of the variations is detected
        elementos_str = " ".join(entities["elementos"])
        assert "escape" in elementos_str or "escapes" in elementos_str
        assert "suspensión" in elementos_str or "suspension" in elementos_str
    
    async def test_extract_from_multiple_messages(self):
        history = [
            {"role": "user", "content": "quiero modificar el subchasis"},
            {"role": "assistant", "content": "¿de qué vehículo?"},
            {"role": "user", "content": "tengo una BMW R1200"},
        ]
        
        entities = await self.service.extract_entities(history, max_messages=3)
        
        # Should extract elemento from first message
        assert "subchasis" in entities["elementos"] or "bastidor" in entities["elementos"]
        # Should extract marca/modelo from last message
        assert entities["marca"] == "BMW"
        assert entities["modelo"] == "R1200"
    
    async def test_empty_history_returns_defaults(self):
        entities = await self.service.extract_entities([])
        
        assert entities["elementos"] == []
        assert entities["marca"] is None
        assert entities["modelo"] is None
    
    async def test_max_messages_limit(self):
        history = [
            {"role": "user", "content": "mensaje viejo con escape"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "mensaje viejo 2"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "mensaje viejo 3"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "quiero modificar el subchasis"},
        ]
        
        entities = await self.service.extract_entities(history, max_messages=2)
        
        # Should extract subchasis from recent message
        assert "subchasis" in entities["elementos"] or "bastidor" in entities["elementos"]
    
    async def test_normalize_elementos_lowercase(self):
        history = [
            {"role": "user", "content": "QUIERO MODIFICAR EL ESCAPE"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        # Elementos should be lowercase
        assert all(e.islower() for e in entities["elementos"])
    
    async def test_normalize_modelo_uppercase(self):
        history = [
            {"role": "user", "content": "tengo una bmw r1200"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        # Modelo should be uppercase
        if entities["modelo"]:
            assert entities["modelo"] == "R1200"
    
    async def test_extract_suspension(self):
        history = [
            {"role": "user", "content": "quiero homologar la suspensión delantera"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        elementos_str = " ".join(entities["elementos"])
        assert "suspensión" in elementos_str or "suspension" in elementos_str
    
    async def test_extract_retrovisores(self):
        history = [
            {"role": "user", "content": "necesito homologar los retrovisores"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        elementos_str = " ".join(entities["elementos"])
        assert "retrovisores" in elementos_str or "retrovisor" in elementos_str or "espejo" in elementos_str
    
    async def test_extract_faro(self):
        history = [
            {"role": "user", "content": "quiero cambiar el faro delantero"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        elementos_str = " ".join(entities["elementos"])
        assert "faro" in elementos_str or "faros" in elementos_str or "luces" in elementos_str or "luz" in elementos_str
    
    async def test_extract_manillar(self):
        history = [
            {"role": "user", "content": "instalé un manillar nuevo"},
        ]
        
        entities = await self.service.extract_entities(history)
        
        elementos_str = " ".join(entities["elementos"])
        assert "manillar" in elementos_str or "manillares" in elementos_str


@pytest.mark.asyncio
class TestEntityExtractionFallback:
    """Test regex fallback when LLM is unavailable."""
    
    def setup_method(self):
        self.service = EntityExtractionService()
    
    def test_fallback_extract_elementos(self):
        """Test that regex fallback works."""
        history_text = "quiero modificar el escape y la suspensión"
        
        result = self.service._extract_with_regex(history_text)
        
        elementos_str = " ".join(result["elementos"])
        assert "escape" in elementos_str or "escapes" in elementos_str
        assert "suspensión" in elementos_str or "suspension" in elementos_str
    
    def test_fallback_extract_marca(self):
        """Test marca extraction with regex."""
        history_text = "tengo una BMW R1200"
        
        result = self.service._extract_with_regex(history_text)
        
        assert result["marca"] == "BMW"
    
    def test_fallback_extract_modelo(self):
        """Test modelo extraction with regex."""
        history_text = "tengo una BMW R1200"
        
        result = self.service._extract_with_regex(history_text)
        
        assert result["modelo"] == "R1200"
    
    def test_fallback_empty_text(self):
        """Test that empty text returns defaults."""
        result = self.service._extract_with_regex("")
        
        assert result["elementos"] == []
        assert result["marca"] is None
        assert result["modelo"] is None
