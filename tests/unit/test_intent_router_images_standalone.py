"""
Test standalone (sin pytest) para verificar detección A/B.
FASE 3 del plan de fix de sistema de imágenes.
"""

import asyncio
import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agent.router.intent_router import get_intent_router, UserIntent


async def test_option_detection():
    """Verifica detección de opciones A/B."""
    router = get_intent_router()
    
    test_cases = [
        # Opción A - Ultra-short
        ("A", UserIntent.VER_IMAGENES, 0.90),
        ("Opción A", UserIntent.VER_IMAGENES, 0.90),
        ("la a", UserIntent.VER_IMAGENES, 0.90),
        
        # Opción A - Natural
        ("ver fotos", UserIntent.VER_IMAGENES, 0.85),
        ("mostrame las imágenes", UserIntent.VER_IMAGENES, 0.85),
        ("envía las fotos", UserIntent.VER_IMAGENES, 0.85),
        ("quiero ver las fotos", UserIntent.VER_IMAGENES, 0.85),
        
        # Opción B - Ultra-short
        ("B", UserIntent.ABRIR_EXPEDIENTE, 0.90),
        ("Opción B", UserIntent.ABRIR_EXPEDIENTE, 0.90),
        ("la b", UserIntent.ABRIR_EXPEDIENTE, 0.90),
    ]
    
    passed = 0
    failed = 0
    
    print("=== FASE 3: Test de Detección de Opciones A/B ===\n")
    
    for user_input, expected_intent, min_confidence in test_cases:
        result = await router.classify(user_input, current_mode="PRESUPUESTO_MODE")
        
        if result.intent == expected_intent and result.confidence >= min_confidence:
            print(f"✅ '{user_input}' → {result.intent.value} (confidence: {result.confidence:.2f})")
            passed += 1
        else:
            print(f"❌ '{user_input}' → Expected {expected_intent.value}, got {result.intent.value} (confidence: {result.confidence:.2f})")
            failed += 1
    
    print(f"\n=== Resultados ===")
    print(f"✅ Passed: {passed}/{len(test_cases)}")
    print(f"❌ Failed: {failed}/{len(test_cases)}")
    
    if failed == 0:
        print("\n🎉 FASE 3 Test: Todos los patrones A/B detectados correctamente")
        return True
    else:
        print("\n⚠️  Algunos tests fallaron")
        return False


async def test_ambiguous_not_detected():
    """Verifica que respuestas ambiguas NO se detecten como A/B."""
    router = get_intent_router()
    
    ambiguous_inputs = ["sí", "ok", "dale", "vale", "perfecto"]
    
    print("\n=== Test de Respuestas Ambiguas ===\n")
    
    all_correct = True
    for user_input in ambiguous_inputs:
        result = await router.classify(user_input, current_mode="PRESUPUESTO_MODE")
        
        # Deberían ser CONFIRMACION, no VER_IMAGENES/ABRIR_EXPEDIENTE
        if result.intent in (UserIntent.CONFIRMACION, UserIntent.AMBIGUO):
            print(f"✅ '{user_input}' → {result.intent.value} (correcto, no es A/B)")
        else:
            print(f"❌ '{user_input}' → {result.intent.value} (ERROR: detectado como A/B)")
            all_correct = False
    
    if all_correct:
        print("\n✅ Respuestas ambiguas NO detectadas erróneamente como A/B")
    else:
        print("\n⚠️  Algunas respuestas ambiguas fueron detectadas erróneamente como A/B")
    
    return all_correct


async def main():
    print("=" * 70)
    print("FASE 3: Verificación de Detección de Opciones A/B")
    print("=" * 70)
    print()
    
    test1 = await test_option_detection()
    test2 = await test_ambiguous_not_detected()
    
    print("\n" + "=" * 70)
    if test1 and test2:
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        return 0
    else:
        print("⚠️  ALGUNOS TESTS FALLARON")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
