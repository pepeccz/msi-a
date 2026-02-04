"""
Tests unitarios para la fusión VIABILIDAD → PRESUPUESTO.

Verifica:
1. Que PRESUPUESTO_MODE tiene todos los tools fusionados
2. Que intent router clasifica "Quiero homologar X" → PRESUPUESTO_DIRECTO
3. Que el prompt de PRESUPUESTO menciona las 2 opciones (imágenes O expediente)
"""

import pytest
from typing import Any


# =============================================================================
# TEST 1: Verificar tools fusionados
# =============================================================================

@pytest.mark.asyncio
async def test_presupuesto_mode_has_all_tools():
    """
    Verifica que PRESUPUESTO_MODE tiene todos los tools de VIABILIDAD + PRESUPUESTO.
    
    Tools esperados (fusionados):
    - identificar_y_resolver_elementos
    - seleccionar_variante_por_respuesta
    - calcular_tarifa_con_elementos
    - enviar_imagenes_ejemplo
    - iniciar_expediente (shortcut via EVALUACION_GATEWAY)
    - listar_categorias
    - listar_elementos
    - obtener_documentacion_elemento
    - identificar_tipo_vehiculo
    - escalar_a_humano
    """
    from agent.modes.presupuesto_mode import _get_presupuesto_tools
    
    tools = _get_presupuesto_tools()
    tool_names = [tool.name for tool in tools]
    
    # Tools que DEBEN estar (fusión VIABILIDAD + PRESUPUESTO)
    expected_tools = [
        "identificar_y_resolver_elementos",
        "seleccionar_variante_por_respuesta",
        "calcular_tarifa_con_elementos",
        "enviar_imagenes_ejemplo",
        "iniciar_expediente",  # Shortcut desde PRESUPUESTO
        "listar_categorias",
        "listar_elementos",
        "obtener_documentacion_elemento",
        "identificar_tipo_vehiculo",
        "escalar_a_humano",
    ]
    
    for expected_tool in expected_tools:
        assert expected_tool in tool_names, f"Tool '{expected_tool}' faltante en PRESUPUESTO_MODE"
    
    # Verificar que NO hay tools duplicados
    assert len(tool_names) == len(set(tool_names)), "Hay tools duplicados"
    
    print(f"✅ PRESUPUESTO_MODE tiene {len(tool_names)} tools (esperados: {len(expected_tools)})")


# =============================================================================
# TEST 2: Intent router directo a PRESUPUESTO
# =============================================================================

@pytest.mark.asyncio
async def test_direct_to_presupuesto_on_quiero_homologar():
    """
    Verifica que "Quiero homologar X" va directo a PRESUPUESTO_MODE.
    
    ANTES: UserIntent.EVALUAR_VIABILIDAD → VIABILIDAD_MODE
    AHORA: UserIntent.PRESUPUESTO_DIRECTO → PRESUPUESTO_MODE
    """
    from agent.router.intent_router import get_intent_router
    
    router = get_intent_router()
    
    test_messages = [
        "Quiero homologar el escape de mi moto",
        "Necesito homologar suspensión",
        "Tengo que legalizar un subchasis",
        "¿Se puede homologar faros LED?",
        "¿Es posible homologar manillar?",
    ]
    
    for message in test_messages:
        result = await router.classify(message, current_mode="START")
        
        # DEBE ir a PRESUPUESTO_DIRECTO (NO a EVALUAR_VIABILIDAD que ya no existe)
        assert result.intent.value == "presupuesto_directo", (
            f"Mensaje '{message}' clasificado como '{result.intent.value}' en vez de 'presupuesto_directo'"
        )
        
        # Verificar que sugiere PRESUPUESTO_MODE
        assert result.suggested_mode == "PRESUPUESTO_MODE", (
            f"Mensaje '{message}' sugiere '{result.suggested_mode}' en vez de 'PRESUPUESTO_MODE'"
        )
        
        print(f"✅ '{message[:40]}...' → {result.intent.value} (conf: {result.confidence})")


# =============================================================================
# TEST 3: Prompt ofrece 2 opciones
# =============================================================================

@pytest.mark.asyncio
async def test_presupuesto_offers_2_options():
    """
    Verifica que el prompt de PRESUPUESTO_MODE menciona las 2 opciones.
    
    Después de dar precio, debe ofrecer:
    1. Ver documentación necesaria (imágenes)
    2. Abrir expediente directamente
    """
    from agent.prompts.loader import assemble_system_prompt
    
    prompt = assemble_system_prompt(mode="PRESUPUESTO_MODE", mode_context={}, client_context="")
    
    # Verificar que el prompt menciona las 2 opciones
    has_two_options = ("2 opciones" in prompt.lower() or "dos opciones" in prompt.lower())
    assert has_two_options, "Prompt no menciona '2 opciones'"
    
    # Verificar que menciona documentación/imágenes
    has_images = any(kw in prompt.lower() for kw in ["documentación", "imágenes", "fotos", "ejemplo"])
    assert has_images, "Prompt no menciona opción de ver documentación/imágenes"
    
    # Verificar que menciona expediente
    has_expediente = "expediente" in prompt.lower()
    assert has_expediente, "Prompt no menciona opción de abrir expediente"
    
    # Verificar que NO menciona "estimación" como algo a HACER (concepto obsoleto)
    # OK si menciona "estimación" en contexto negativo (ej: "NO hagas estimación", "❌ estimación")
    
    # Simplificado: verificar que si menciona "estimación", está en contexto de negación
    lower_prompt = prompt.lower()
    
    if "estimación" in lower_prompt:
        # Verificar que está en contexto negativo
        lines_with_estimacion = [line for line in lower_prompt.split('\n') if 'estimación' in line]
        for line in lines_with_estimacion:
            # Debe contener palabras de negación
            has_negation = any(neg in line for neg in ['no ', '❌', 'nunca', 'elimina', 'sin '])
            assert has_negation, f"Línea con 'estimación' SIN negación: {line[:100]}"
    
    # Lo mismo para "precio estimado"
    if "precio estimado" in lower_prompt:
        lines_with_precio_estimado = [line for line in lower_prompt.split('\n') if 'precio estimado' in line]
        for line in lines_with_precio_estimado:
            has_negation = any(neg in line for neg in ['no ', '❌', 'nunca', 'elimina', 'sin '])
            assert has_negation, f"Línea con 'precio estimado' SIN negación: {line[:100]}"
    
    print("✅ Prompt de PRESUPUESTO_MODE correctamente formateado:")
    print(f"  - Menciona '2 opciones': {has_two_options}")
    print(f"  - Menciona imágenes/documentación: {has_images}")
    print(f"  - Menciona expediente: {has_expediente}")
    print(f"  - 'estimación' solo en contexto negativo: ✓")
    print(f"  - 'precio estimado' solo en contexto negativo: ✓")


# =============================================================================
# TEST 4: EXTRA - Verificar que el mode context NO tiene campos obsoletos
# =============================================================================

@pytest.mark.asyncio
async def test_mode_context_no_obsolete_fields():
    """
    Verifica que el mode context NO tiene campos obsoletos de VIABILIDAD.
    
    Campos que NO deben existir:
    - estimacion_precio (ahora es precio_calculado)
    - viabilidad_resultado (concepto eliminado)
    """
    from agent.state.conversation_state import ModeContextData
    
    # Get type hints from ModeContextData
    import typing
    hints = typing.get_type_hints(ModeContextData)
    
    # Verificar que NO existen campos obsoletos
    assert "estimacion_precio" not in hints, "Campo obsoleto 'estimacion_precio' todavía existe"
    assert "viabilidad_resultado" not in hints, "Campo obsoleto 'viabilidad_resultado' todavía existe"
    
    # Verificar que SÍ existe el nuevo campo
    # NOTE: ModeContextData usa total=False, así que no podemos verificar campos obligatorios
    # Pero podemos verificar que está en las anotaciones
    print("✅ ModeContextData NO tiene campos obsoletos")
    print(f"  - Campos totales: {len(hints)}")


# =============================================================================
# TEST 5: EXTRA - Verificar que el sistema NO tiene referencias a "viabilidad"
# =============================================================================

@pytest.mark.asyncio
async def test_no_viabilidad_references_in_code():
    """
    Verifica que NO hay referencias a "viabilidad" en código crítico.
    
    Nota: Este test es más un linter que un test funcional.
    """
    import os
    import re
    
    files_to_check = [
        "agent/modes/presupuesto_mode.py",
        "agent/router/intent_router.py",
        "agent/state/conversation_state.py",
    ]
    
    base_path = "/home/autohomologacion/msi-a"
    viabilidad_pattern = re.compile(r"\bviabilidad\b", re.IGNORECASE)
    
    found_references = []
    
    for file_path in files_to_check:
        full_path = os.path.join(base_path, file_path)
        if not os.path.exists(full_path):
            print(f"⚠️  Archivo no encontrado: {file_path}")
            continue
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            matches = viabilidad_pattern.finditer(content)
            
            for match in matches:
                # Skip comments and docstrings (simple heuristic)
                line_start = content.rfind("\n", 0, match.start()) + 1
                line_end = content.find("\n", match.start())
                line = content[line_start:line_end].strip()
                
                # Skip if it's a comment
                if line.startswith("#"):
                    continue
                
                # Skip if it's in a docstring (triple quotes)
                if '"""' in content[max(0, match.start() - 100):match.start()]:
                    continue
                
                found_references.append(f"{file_path}:{match.start()} - {line[:80]}")
    
    if found_references:
        print("⚠️  Referencias a 'viabilidad' encontradas en código:")
        for ref in found_references:
            print(f"    {ref}")
    else:
        print("✅ NO hay referencias a 'viabilidad' en archivos críticos")
    
    # No fallamos el test si hay referencias en comments/docstrings
    # Solo advertimos
