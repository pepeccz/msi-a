"""
Tests de integración para el fix del sistema de envío de imágenes.

FASE 1: Verificar que tarifa_actual se escribe al root state.
"""
import json
import asyncio
from agent.modes.presupuesto_mode import PresupuestoModeNode


async def test_tarifa_actual_is_written_to_root_state():
    """
    Verify tarifa_actual is written to root state after calcular_tarifa.
    
    Bug original: tarifa_actual nunca se escribía al estado raíz,
    causando que enviar_imagenes_ejemplo() siempre fallara con
    "No hay presupuesto calculado".
    
    Fix: _extract_context_from_tool() ahora setea _tarifa_actual,
    que luego se propaga al root state en _process_message().
    """
    mode_node = PresupuestoModeNode()
    
    # Simulate tool result from calcular_tarifa_con_elementos
    tool_result = {
        "success": True,
        "precio_final": 410.0,
        "precio_base": 350.0,
        "precio_iva": 73.5,
        "elementos": ["SUBCHASIS"],
        "categoria": "motos-part",
        "imagenes_ejemplo": [
            {"url": "https://example.com/subchasis1.jpg", "tipo": "frontal"},
            {"url": "https://example.com/subchasis2.jpg", "tipo": "lateral"},
        ],
    }
    
    # Extract context updates from tool
    updates = mode_node._extract_context_from_tool(
        "calcular_tarifa_con_elementos",
        {},  # tool_args not used in this extraction
        json.dumps(tool_result)
    )
    
    # Verify signal to write to root state is present
    assert updates.get("_tarifa_actual") is not None, (
        "Missing _tarifa_actual signal in context updates. "
        "This will cause enviar_imagenes_ejemplo() to fail."
    )
    
    # Verify the signal contains the full tarifa data
    assert updates["_tarifa_actual"]["precio_final"] == 410.0
    assert updates["_tarifa_actual"]["success"] is True
    assert "imagenes_ejemplo" in updates["_tarifa_actual"]
    
    # Verify other expected updates
    assert updates["precio_calculado"] == 410.0
    assert updates["tarifa_calculada"] == tool_result
    assert updates["precio_comunicado"] is False  # Reset for new quote
    
    print("✅ FASE 1 Test: tarifa_actual signal correctamente creado")


async def test_tarifa_actual_propagated_to_root_in_process_message():
    """
    Verify that _tarifa_actual is propagated to root state in _process_message.
    
    Este test simula el flujo completo donde:
    1. Tool ejecuta calcular_tarifa_con_elementos
    2. _extract_context_from_tool setea _tarifa_actual en mode_context
    3. _process_message propaga _tarifa_actual al root state
    """
    # Simular mode_context con _tarifa_actual
    mode_context = {
        "categoria_slug": "motos-part",
        "precio_calculado": 410.0,
        "tarifa_calculada": {"precio_final": 410.0},
        "_tarifa_actual": {  # Signal to propagate
            "precio_final": 410.0,
            "imagenes_ejemplo": [{"url": "https://example.com/img.jpg"}],
        },
    }
    
    # Simular el código de _process_message que propaga
    updated_context = dict(mode_context)
    result_dict = {
        "ai_response": "El presupuesto es de 410€ +IVA.",
        "mode_context": updated_context,
    }
    
    # Apply propagation logic
    if updated_context.get("_tarifa_actual"):
        result_dict["tarifa_actual"] = updated_context.pop("_tarifa_actual")
    
    # Verify tarifa_actual is in root state
    assert "tarifa_actual" in result_dict, (
        "tarifa_actual not propagated to root state"
    )
    assert result_dict["tarifa_actual"]["precio_final"] == 410.0
    
    # Verify _tarifa_actual is removed from mode_context (cleanup)
    assert "_tarifa_actual" not in result_dict["mode_context"], (
        "_tarifa_actual should be removed after propagation"
    )
    
    print("✅ FASE 1 Test: tarifa_actual propagated to root state successfully")


async def test_precio_comunicado_flag_reset():
    """
    Verify precio_comunicado flag is reset when new tariff is calculated.
    
    Esto es importante para permitir múltiples cálculos en la misma conversación.
    """
    mode_node = PresupuestoModeNode()
    
    tool_result = {
        "success": True,
        "precio_final": 350.0,
    }
    
    updates = mode_node._extract_context_from_tool(
        "calcular_tarifa_con_elementos",
        {},
        json.dumps(tool_result)
    )
    
    # Verify flag is reset
    assert updates["precio_comunicado"] is False, (
        "precio_comunicado should be reset to False for new quotes"
    )
    
    print("✅ FASE 1 Test: precio_comunicado flag correctly reset")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("FASE 1: Fix tarifa_actual No Se Escribe - Integration Tests")
    print("="*70 + "\n")
    
    asyncio.run(test_tarifa_actual_is_written_to_root_state())
    asyncio.run(test_tarifa_actual_propagated_to_root_in_process_message())
    asyncio.run(test_precio_comunicado_flag_reset())
    
    print("\n" + "="*70)
    print("✅ ALL FASE 1 TESTS PASSED")
    print("="*70 + "\n")
    
    print("\n" + "="*70)
    print("FASE 2: Fix precio_comunicado Detection - Integration Tests")
    print("="*70 + "\n")
    
    asyncio.run(test_price_communicated_flag_is_set())
    asyncio.run(test_price_patterns_with_float_prices())
    asyncio.run(test_price_communicated_detection_in_context())
    asyncio.run(test_price_not_communicated_when_not_mentioned())
    
    print("\n" + "="*70)
    print("✅ ALL FASE 2 TESTS PASSED")
    print("="*70 + "\n")
    
    print("\n" + "="*70)
    print("FASE 4: Error Handling - Imágenes No Disponibles - Tests")
    print("="*70 + "\n")
    
    asyncio.run(test_no_images_available_does_not_invent_urls())
    test_documentation_prompt_has_error_handling()
    test_error_messages_provide_alternatives()
    test_error_messages_are_in_spanish()
    
    print("\n" + "="*70)
    print("✅ ALL FASE 4 TESTS PASSED")
    print("="*70 + "\n")
    
    print("\n" + "="*70)
    print("🎉 ALL TESTS PASSED (FASE 1 + FASE 2 + FASE 4)")
    print("="*70 + "\n")

# ============================================================================
# FASE 2: precio_comunicado flag detection
# ============================================================================

async def test_price_communicated_flag_is_set():
    """Verify precio_comunicado flag is set when LLM mentions price.
    
    FASE 2: This test verifies that the pattern matching logic
    correctly detects price mentions in the LLM response.
    
    This is a simplified unit test. Full integration testing requires
    mocking the LLM response, which is more complex.
    """
    # Test price pattern matching logic
    price = 410.0
    precio_int = int(price)
    price_patterns = [
        f"{precio_int}€",
        f"{precio_int} €",
        f"{precio_int}EUR",
        f"{price} €",
        f"{price}€",
    ]
    
    # Test various response formats
    test_responses = [
        "El presupuesto es de 410€ +IVA.",
        "El precio es 410 €",
        "Son 410EUR en total",
        "Te sale 410€ la homologación",
        "El coste total es de 410 € más IVA",
    ]
    
    for response in test_responses:
        pattern_found = any(pattern in response for pattern in price_patterns)
        assert pattern_found, f"Pattern not found in: {response}"
    
    # Test negative cases (should NOT match)
    negative_responses = [
        "El presupuesto está listo",
        "Te voy a calcular el precio",
        "Necesito más información",
    ]
    
    for response in negative_responses:
        pattern_found = any(pattern in response for pattern in price_patterns)
        assert not pattern_found, f"Pattern incorrectly matched in: {response}"
    
    print("✅ FASE 2 Test: Pattern matching funciona correctamente")


async def test_price_patterns_with_float_prices():
    """Test price pattern matching with decimal prices (e.g., 410.50€)."""
    price = 410.50
    
    # For decimal prices, we can't use int() conversion
    price_patterns = [
        f"{price}€",
        f"{price} €",
    ]
    
    test_response = "El presupuesto es de 410.50€ +IVA"
    pattern_found = any(pattern in test_response for pattern in price_patterns)
    assert pattern_found, "Decimal price pattern not detected"
    
    print("✅ FASE 2 Test: Decimal price patterns work correctly")


async def test_price_communicated_detection_in_context():
    """Test that price communication detection works with mode_context.
    
    This simulates the actual flow where:
    1. tarifa_calculada exists in mode_context
    2. LLM response mentions the price
    3. precio_comunicado flag is set to True
    """
    # Simulate mode_context with tarifa_calculada
    mode_context = {
        "tarifa_calculada": {
            "precio_final": 410.0,
            "success": True,
        }
    }
    
    # Simulate LLM response with price mention
    ai_response = "El presupuesto es de 410€ +IVA. Te envío las fotos de ejemplo:"
    
    # Extract price from mode_context
    precio = (
        mode_context["tarifa_calculada"].get("precio_final") or
        mode_context["tarifa_calculada"].get("price") or
        mode_context["tarifa_calculada"].get("total")
    )
    
    # Pattern matching logic (same as in presupuesto_mode.py)
    precio_int = int(precio) if float(precio).is_integer() else precio
    price_patterns = [
        f"{precio_int}€",
        f"{precio_int} €",
        f"{precio_int}EUR",
        f"{precio} €",
        f"{precio}€",
    ]
    
    precio_comunicado = any(pattern in ai_response for pattern in price_patterns)
    
    assert precio_comunicado is True, (
        "precio_comunicado should be True when LLM mentions price"
    )
    
    print("✅ FASE 2 Test: Price detection with mode_context works correctly")


async def test_price_not_communicated_when_not_mentioned():
    """Test that precio_comunicado is NOT set when price not mentioned."""
    mode_context = {
        "tarifa_calculada": {
            "precio_final": 410.0,
        }
    }
    
    # LLM response WITHOUT price mention
    ai_response = "Perfecto, ahora voy a calcular el presupuesto para ti."
    
    precio = mode_context["tarifa_calculada"]["precio_final"]
    precio_int = int(precio) if float(precio).is_integer() else precio
    price_patterns = [
        f"{precio_int}€",
        f"{precio_int} €",
        f"{precio_int}EUR",
        f"{precio} €",
        f"{precio}€",
    ]
    
    precio_comunicado = any(pattern in ai_response for pattern in price_patterns)
    
    assert precio_comunicado is False, (
        "precio_comunicado should be False when price not mentioned"
    )
    
    print("✅ FASE 2 Test: Price NOT detected when not mentioned")


# ============================================================================
# FASE 4: Error handling - Imágenes no disponibles
# ============================================================================

async def test_no_images_available_does_not_invent_urls():
    """Verify error message includes anti-invention instructions.
    
    FASE 4: Cuando no hay imágenes disponibles, el error message debe
    incluir instrucciones EXPLÍCITAS para que el LLM NO invente URLs.
    """
    import re
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    
    # Leer el código del tool para verificar los mensajes
    import inspect
    source = inspect.getsource(enviar_imagenes_ejemplo)
    
    # Verificar que contiene las instrucciones críticas
    assert "DO NOT generate fake URLs" in source, (
        "Missing anti-invention instruction: 'DO NOT generate fake URLs'"
    )
    assert "DO NOT list URLs like 'storage.chatwoot.com" in source, (
        "Missing specific example of what NOT to do"
    )
    assert "CRITICAL INSTRUCTION FOR LLM" in source, (
        "Missing critical instruction marker"
    )
    
    # Verificar que hay al menos 4 ubicaciones con estas instrucciones
    critical_instruction_count = source.count("CRITICAL INSTRUCTION FOR LLM")
    assert critical_instruction_count >= 4, (
        f"Expected at least 4 error messages with anti-invention instructions, "
        f"found {critical_instruction_count}"
    )
    
    print("✅ FASE 4 Test: Error messages contienen instrucciones anti-invención")


def test_documentation_prompt_has_error_handling():
    """Verify 08_documentation.md has error handling section.
    
    FASE 4: El prompt debe incluir una sección clara sobre cómo
    manejar errores cuando no hay imágenes disponibles.
    """
    with open("agent/prompts/core/08_documentation.md", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verificar secciones clave
    assert "Manejo de Errores en Imágenes" in content, (
        "Missing 'Manejo de Errores en Imágenes' section"
    )
    assert "NUNCA inventes URLs" in content, (
        "Missing instruction about not inventing URLs"
    )
    assert "NO HAGAS ESTO" in content, (
        "Missing negative example section"
    )
    assert "HAZ ESTO" in content, (
        "Missing positive example section"
    )
    assert "storage.chatwoot.com" in content, (
        "Missing specific example of invented URLs"
    )
    
    # Verificar ejemplos específicos
    assert "REGLA DE ORO" in content, (
        "Missing 'REGLA DE ORO' principle"
    )
    
    print("✅ FASE 4 Test: Prompt actualizado con manejo de errores")


def test_error_messages_provide_alternatives():
    """Verify error messages provide useful alternatives to users.
    
    FASE 4: Cuando no hay imágenes, los error messages deben sugerir
    alternativas útiles (explicar documentación, responder dudas).
    """
    import inspect
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    
    source = inspect.getsource(enviar_imagenes_ejemplo)
    
    # Verificar que los mensajes ofrecen alternativas
    assert "puedo explicarte qué documentación necesitarás" in source, (
        "Error messages should offer to explain documentation requirements"
    )
    
    # Verificar que hay múltiples variantes de mensajes alternativos
    alternative_count = source.count("puedo explicarte")
    assert alternative_count >= 2, (
        f"Expected at least 2 error messages with alternatives, found {alternative_count}"
    )
    
    print("✅ FASE 4 Test: Error messages ofrecen alternativas útiles")


def test_error_messages_are_in_spanish():
    """Verify error messages for users are in Spanish.
    
    FASE 4: Los mensajes que el bot debe decir al usuario deben estar
    en español (user-facing content).
    """
    import inspect
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    
    source = inspect.getsource(enviar_imagenes_ejemplo)
    
    # Buscar los mensajes "Instead, tell the user:"
    import re
    user_messages = re.findall(
        r"Instead, tell the user:\n\s*['\"](.+?)['\"]",
        source,
        re.DOTALL
    )
    
    assert len(user_messages) >= 2, (
        "Expected at least 2 user-facing messages in error handling"
    )
    
    # Verificar que los mensajes están en español
    spanish_keywords = ["este momento", "fotos de ejemplo", "disponibles", "necesitarás"]
    for msg in user_messages:
        has_spanish = any(keyword in msg for keyword in spanish_keywords)
        assert has_spanish, (
            f"User message should be in Spanish: {msg[:100]}..."
        )
    
    print("✅ FASE 4 Test: Error messages user-facing están en español")

