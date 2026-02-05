"""
Verificación de regex patterns para FASE 3.
No requiere dependencias externas.
"""

import re

# Patterns from intent_router.py
patterns = [
    # VER_IMAGENES: Ultra-short
    (re.compile(r"^\s*([Aa]|opci[oó]n\s*[Aa]|la\s*[Aa])\s*[.!?]?\s*$", re.I),
     "VER_IMAGENES", 0.95),
    
    # VER_IMAGENES: Natural language
    (re.compile(r"\b(ver|mostrar|enviar|quiero|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b", re.I),
     "VER_IMAGENES", 0.90),
    
    (re.compile(r"\b(s[ií],?\s*)?(mostr[aá]|env[ií]a|manda)\s+(las\s+)?(fotos?|im[aá]genes?)\b", re.I),
     "VER_IMAGENES", 0.90),
    
    # VER_IMAGENES: Imperativos con pronombres enclíticos
    (re.compile(r"\b(mostr[aá]me|env[ií]ame|mandame|dame)\s+(las\s+)?(fotos?|im[aá]genes?|ejemplos?)\b", re.I),
     "VER_IMAGENES", 0.90),
    
    # ABRIR_EXPEDIENTE: Ultra-short
    (re.compile(r"^\s*([Bb]|opci[oó]n\s*[Bb]|la\s*[Bb])\s*[.!?]?\s*$", re.I),
     "ABRIR_EXPEDIENTE", 0.95),
]

test_cases = [
    # VER_IMAGENES - Ultra-short
    ("A", "VER_IMAGENES"),
    ("a", "VER_IMAGENES"),
    ("Opción A", "VER_IMAGENES"),
    ("opción a", "VER_IMAGENES"),
    ("la a", "VER_IMAGENES"),
    ("La A", "VER_IMAGENES"),
    ("A.", "VER_IMAGENES"),
    
    # VER_IMAGENES - Natural
    ("ver fotos", "VER_IMAGENES"),
    ("Ver las fotos", "VER_IMAGENES"),
    ("mostrame las imágenes", "VER_IMAGENES"),
    ("Mostrá las fotos", "VER_IMAGENES"),
    ("envía las fotos", "VER_IMAGENES"),
    ("Envía las imágenes", "VER_IMAGENES"),
    ("quiero ver las fotos", "VER_IMAGENES"),
    ("dame las imágenes", "VER_IMAGENES"),
    ("mostrar ejemplos", "VER_IMAGENES"),
    ("sí, mostrá las fotos", "VER_IMAGENES"),
    ("Si, envía las imágenes", "VER_IMAGENES"),
    
    # ABRIR_EXPEDIENTE - Ultra-short
    ("B", "ABRIR_EXPEDIENTE"),
    ("b", "ABRIR_EXPEDIENTE"),
    ("Opción B", "ABRIR_EXPEDIENTE"),
    ("opción b", "ABRIR_EXPEDIENTE"),
    ("la b", "ABRIR_EXPEDIENTE"),
    ("La B", "ABRIR_EXPEDIENTE"),
    ("B.", "ABRIR_EXPEDIENTE"),
]

# Respuestas que NO deberían matchear A/B (deberían ser CONFIRMACION)
non_matching = [
    "sí",
    "si",
    "ok",
    "dale",
    "vale",
    "perfecto",
    "Hola quiero homologar escape",  # No debería ser VER_IMAGENES
]


def test_patterns():
    """Test regex patterns."""
    print("=" * 70)
    print("FASE 3: Verificación de Regex Patterns")
    print("=" * 70)
    print()
    
    passed = 0
    failed = 0
    
    print("=== Tests Positivos (deberían matchear) ===\n")
    
    for text, expected_intent in test_cases:
        matched = False
        matched_intent = None
        
        for pattern, intent, confidence in patterns:
            if pattern.search(text):
                matched = True
                matched_intent = intent
                break
        
        if matched and matched_intent == expected_intent:
            print(f"✅ '{text}' → {matched_intent}")
            passed += 1
        elif matched:
            print(f"⚠️  '{text}' → Expected {expected_intent}, got {matched_intent}")
            failed += 1
        else:
            print(f"❌ '{text}' → No match (expected {expected_intent})")
            failed += 1
    
    print(f"\n=== Tests Negativos (NO deberían matchear A/B) ===\n")
    
    for text in non_matching:
        matched_ab = False
        
        for pattern, intent, confidence in patterns:
            if pattern.search(text):
                matched_ab = True
                print(f"❌ '{text}' → Matched {intent} (ERROR: debería ser CONFIRMACION)")
                failed += 1
                break
        
        if not matched_ab:
            print(f"✅ '{text}' → No match A/B (correcto)")
            passed += 1
    
    print(f"\n{'=' * 70}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"{'=' * 70}")
    
    if failed == 0:
        print("\n🎉 TODOS LOS PATTERNS FUNCIONAN CORRECTAMENTE")
        return True
    else:
        print(f"\n⚠️  {failed} patterns fallaron")
        return False


if __name__ == "__main__":
    import sys
    success = test_patterns()
    sys.exit(0 if success else 1)
