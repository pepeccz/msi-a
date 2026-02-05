"""
Tests unitarios para la detección de intents VER_IMAGENES y ABRIR_EXPEDIENTE.

FASE 3 del plan de fix de sistema de imágenes.
Verifica que el intent_router detecte correctamente respuestas A/B.
"""

import pytest
from agent.router.intent_router import get_intent_router, UserIntent


@pytest.mark.parametrize("user_input,expected_intent,min_confidence", [
    # Opción A - Ultra-short
    ("A", UserIntent.VER_IMAGENES, 0.90),
    ("a", UserIntent.VER_IMAGENES, 0.90),
    ("Opción A", UserIntent.VER_IMAGENES, 0.90),
    ("opción a", UserIntent.VER_IMAGENES, 0.90),
    ("la a", UserIntent.VER_IMAGENES, 0.90),
    ("La A", UserIntent.VER_IMAGENES, 0.90),
    
    # Opción A - Natural language
    ("ver fotos", UserIntent.VER_IMAGENES, 0.85),
    ("Ver las fotos", UserIntent.VER_IMAGENES, 0.85),
    ("mostrame las imágenes", UserIntent.VER_IMAGENES, 0.85),
    ("Mostrá las fotos", UserIntent.VER_IMAGENES, 0.85),
    ("envía las fotos", UserIntent.VER_IMAGENES, 0.85),
    ("Envía las imágenes", UserIntent.VER_IMAGENES, 0.85),
    ("quiero ver las fotos", UserIntent.VER_IMAGENES, 0.85),
    ("dame las imágenes", UserIntent.VER_IMAGENES, 0.85),
    ("mostrar ejemplos", UserIntent.VER_IMAGENES, 0.85),
    
    # Opción B - Ultra-short
    ("B", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ("b", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ("Opción B", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ("opción b", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ("la b", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ("La B", UserIntent.ABRIR_EXPEDIENTE, 0.90),
])
@pytest.mark.asyncio
async def test_option_ab_detection(user_input, expected_intent, min_confidence):
    """Verifica detección de opciones A/B."""
    router = get_intent_router()
    result = await router.classify(user_input, current_mode="PRESUPUESTO_MODE")
    
    assert result.intent == expected_intent, (
        f"Expected {expected_intent} for '{user_input}', got {result.intent}"
    )
    assert result.confidence >= min_confidence, (
        f"Confidence {result.confidence} below {min_confidence} for '{user_input}'"
    )
    
    print(f"✅ '{user_input}' → {result.intent} (confidence: {result.confidence:.2f})")


@pytest.mark.asyncio
async def test_all_patterns_pass():
    """Run all parametrized tests (smoke test)."""
    router = get_intent_router()
    
    test_cases = [
        ("A", UserIntent.VER_IMAGENES),
        ("Opción A", UserIntent.VER_IMAGENES),
        ("ver fotos", UserIntent.VER_IMAGENES),
        ("mostrame las imágenes", UserIntent.VER_IMAGENES),
        ("B", UserIntent.ABRIR_EXPEDIENTE),
        ("Opción B", UserIntent.ABRIR_EXPEDIENTE),
        ("la b", UserIntent.ABRIR_EXPEDIENTE),
    ]
    
    for user_input, expected in test_cases:
        result = await router.classify(user_input, current_mode="PRESUPUESTO_MODE")
        assert result.intent == expected, (
            f"Failed for '{user_input}': expected {expected}, got {result.intent}"
        )
    
    print(f"\n✅ FASE 3 Test: Todos los patrones A/B detectados correctamente ({len(test_cases)} casos)")


@pytest.mark.asyncio
async def test_ambiguous_responses_not_detected_as_ab():
    """
    Verifica que respuestas ambiguas NO se detecten como A/B.
    Deberían ser CONFIRMACION o AMBIGUO.
    """
    router = get_intent_router()
    
    # Estas respuestas NO deberían detectarse como VER_IMAGENES o ABRIR_EXPEDIENTE
    # cuando NO hay contexto waiting_for_image_choice
    ambiguous_inputs = [
        "sí",
        "ok",
        "dale",
        "vale",
        "perfecto",
    ]
    
    for user_input in ambiguous_inputs:
        result = await router.classify(user_input, current_mode="PRESUPUESTO_MODE")
        
        # Estas deberían ser CONFIRMACION, no VER_IMAGENES/ABRIR_EXPEDIENTE
        assert result.intent in (UserIntent.CONFIRMACION, UserIntent.AMBIGUO), (
            f"'{user_input}' should be CONFIRMACION or AMBIGUO, got {result.intent}"
        )
    
    print("✅ Respuestas ambiguas NO detectadas erróneamente como A/B")


@pytest.mark.asyncio
async def test_confidence_levels():
    """
    Verifica que las respuestas ultra-cortas tengan mayor confianza
    que las respuestas en lenguaje natural.
    """
    router = get_intent_router()
    
    # Ultra-short debería tener confianza >= 0.95
    result_ultra = await router.classify("A", current_mode="PRESUPUESTO_MODE")
    assert result_ultra.confidence >= 0.95, (
        f"Ultra-short 'A' should have confidence >= 0.95, got {result_ultra.confidence}"
    )
    
    # Natural language debería tener confianza >= 0.85
    result_natural = await router.classify("ver fotos", current_mode="PRESUPUESTO_MODE")
    assert result_natural.confidence >= 0.85, (
        f"Natural 'ver fotos' should have confidence >= 0.85, got {result_natural.confidence}"
    )
    
    print("✅ Niveles de confianza correctos (ultra-short > natural)")


if __name__ == "__main__":
    import asyncio
    
    async def main():
        print("=== FASE 3: Test de Detección de Opciones A/B ===\n")
        
        # Run smoke test
        await test_all_patterns_pass()
        
        print("\n=== Tests completos ===")
        print("Ejecuta: pytest tests/unit/test_intent_router_images.py -v")
    
    asyncio.run(main())
