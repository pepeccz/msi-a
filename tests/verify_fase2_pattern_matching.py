#!/usr/bin/env python3
"""
Verificación simple de pattern matching de FASE 2 (sin imports pesados).

Este script verifica la lógica de detección de precio implementada en
presupuesto_mode.py sin requerir el entorno completo de Docker.
"""


def test_price_pattern_matching():
    """Test pattern matching logic for price detection."""
    print("=" * 70)
    print("FASE 2: Verificación de Pattern Matching")
    print("=" * 70)
    print()
    
    # Test case 1: Integer price
    print("Test 1: Integer price (410€)")
    price = 410.0
    precio_float = float(price)
    if precio_float.is_integer():
        precio_int = int(precio_float)
        price_patterns = [
            f"{precio_int}€",
            f"{precio_int} €",
            f"{precio_int}EUR",
        ]
    else:
        price_patterns = [
            f"{precio_float}€",
            f"{precio_float} €",
            f"{precio_float:.2f}€",
            f"{precio_float:.2f} €",
        ]
    
    test_responses = [
        ("El presupuesto es de 410€ +IVA.", True),
        ("El precio es 410 €", True),
        ("Son 410EUR en total", True),
        ("Te sale 410€ la homologación", True),
        ("El presupuesto está listo", False),
        ("Te voy a calcular el precio", False),
    ]
    
    all_passed = True
    for response, should_match in test_responses:
        pattern_found = any(pattern in response for pattern in price_patterns)
        status = "✅" if pattern_found == should_match else "❌"
        print(f"{status} '{response[:50]}...' → {pattern_found} (esperado: {should_match})")
        if pattern_found != should_match:
            all_passed = False
    
    print()
    
    # Test case 2: Decimal price
    print("Test 2: Decimal price (410.50€)")
    price_decimal = 410.50
    precio_float_decimal = float(price_decimal)
    if precio_float_decimal.is_integer():
        precio_int_decimal = int(precio_float_decimal)
        price_patterns_decimal = [
            f"{precio_int_decimal}€",
            f"{precio_int_decimal} €",
            f"{precio_int_decimal}EUR",
        ]
    else:
        price_patterns_decimal = [
            f"{precio_float_decimal}€",
            f"{precio_float_decimal} €",
            f"{precio_float_decimal:.2f}€",
            f"{precio_float_decimal:.2f} €",
        ]
    
    test_response_decimal = "El presupuesto es de 410.50€ +IVA"
    pattern_found_decimal = any(pattern in test_response_decimal for pattern in price_patterns_decimal)
    status_decimal = "✅" if pattern_found_decimal else "❌"
    print(f"{status_decimal} '{test_response_decimal}' → {pattern_found_decimal} (esperado: True)")
    if not pattern_found_decimal:
        all_passed = False
    
    print()
    
    # Test case 3: Mode context simulation
    print("Test 3: Mode context simulation")
    mode_context = {
        "tarifa_calculada": {
            "precio_final": 410.0,
            "success": True,
        }
    }
    
    ai_response = "El presupuesto es de 410€ +IVA. Te envío las fotos:"
    
    # Simulate the code from presupuesto_mode.py
    precio = (
        mode_context["tarifa_calculada"].get("precio_final") or
        mode_context["tarifa_calculada"].get("price") or
        mode_context["tarifa_calculada"].get("total")
    )
    
    if precio:
        precio_float_ctx = float(precio)
        if precio_float_ctx.is_integer():
            precio_int_ctx = int(precio_float_ctx)
            price_patterns_ctx = [
                f"{precio_int_ctx}€",
                f"{precio_int_ctx} €",
                f"{precio_int_ctx}EUR",
            ]
        else:
            price_patterns_ctx = [
                f"{precio_float_ctx}€",
                f"{precio_float_ctx} €",
                f"{precio_float_ctx:.2f}€",
                f"{precio_float_ctx:.2f} €",
            ]
        
        precio_comunicado = any(pattern in ai_response for pattern in price_patterns_ctx)
        status_ctx = "✅" if precio_comunicado else "❌"
        print(f"{status_ctx} Price detected in context → {precio_comunicado} (esperado: True)")
        if not precio_comunicado:
            all_passed = False
    
    print()
    print("=" * 70)
    if all_passed:
        print("✅ TODOS LOS TESTS DE FASE 2 PASARON")
    else:
        print("❌ ALGUNOS TESTS FALLARON")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = test_price_pattern_matching()
    exit(0 if success else 1)
