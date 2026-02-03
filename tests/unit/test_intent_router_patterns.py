"""Unit tests for Intent Router keyword patterns (Fix #2)."""

import pytest

from agent.router.intent_router import IntentRouter, UserIntent


@pytest.mark.asyncio
class TestIntentRouterKeywordPatterns:
    """Test improved keyword patterns for EVALUAR_VIABILIDAD."""
    
    def setup_method(self):
        self.router = IntentRouter()
    
    # Test "quiero modificar X"
    async def test_quiero_modificar_subchasis(self):
        result = await self.router.classify("quiero modificar el subchasis")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    async def test_necesito_cambiar_suspension(self):
        result = await self.router.classify("necesito cambiar la suspensión")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    async def test_voy_a_instalar_escape(self):
        result = await self.router.classify("voy a instalar un escape nuevo")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    # Test "tengo una modificación en X"
    async def test_tengo_modificacion_en_escape(self):
        result = await self.router.classify("tengo una modificación en el escape")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    async def test_hice_cambio_en_motor(self):
        result = await self.router.classify("hice un cambio en el motor")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    # Test "modificar el X" (sin verbo querer)
    async def test_modificar_el_escape(self):
        result = await self.router.classify("modificar el escape")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.70
    
    async def test_instalar_una_suspension(self):
        result = await self.router.classify("instalar una suspensión nueva")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.70
    
    # Test that old patterns still work
    async def test_quiero_homologar_still_works(self):
        result = await self.router.classify("quiero homologar el escape")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.85
    
    async def test_se_puede_homologar_still_works(self):
        result = await self.router.classify("¿se puede homologar el subchasis?")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.85
    
    # Test edge cases
    async def test_partial_match_low_confidence(self):
        result = await self.router.classify("modificación")
        # Should not match with high confidence (needs more context)
        assert result.confidence < 0.75 or result.intent != UserIntent.EVALUAR_VIABILIDAD
    
    async def test_montar_escape(self):
        result = await self.router.classify("montar un escape")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.70
    
    async def test_puse_una_suspension(self):
        result = await self.router.classify("puse una suspensión nueva")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    async def test_instale_un_subchasis(self):
        result = await self.router.classify("instalé un subchasis")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75
    
    async def test_monte_luces(self):
        result = await self.router.classify("monté unas luces LED")
        assert result.intent == UserIntent.EVALUAR_VIABILIDAD
        assert result.confidence >= 0.75


@pytest.mark.asyncio
class TestIntentRouterOtherIntents:
    """Test that other intents still work correctly."""
    
    def setup_method(self):
        self.router = IntentRouter()
    
    async def test_presupuesto_directo(self):
        result = await self.router.classify("¿cuánto cuesta homologar un escape?")
        assert result.intent == UserIntent.PRESUPUESTO_DIRECTO
        assert result.confidence >= 0.80
    
    async def test_consulta_general(self):
        result = await self.router.classify("¿qué es la homologación?")
        assert result.intent == UserIntent.CONSULTA_GENERAL
        assert result.confidence >= 0.80
    
    async def test_confirmacion(self):
        result = await self.router.classify("sí")
        assert result.intent == UserIntent.CONFIRMACION
        assert result.confidence >= 0.80
    
    async def test_rechazo(self):
        result = await self.router.classify("no")
        assert result.intent == UserIntent.RECHAZO
        assert result.confidence >= 0.80
    
    async def test_escalar(self):
        result = await self.router.classify("quiero hablar con una persona")
        assert result.intent == UserIntent.ESCALAR
        assert result.confidence >= 0.80
