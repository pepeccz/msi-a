"""
Tests de integración para la fusión VIABILIDAD → PRESUPUESTO.

Verifica flujos completos end-to-end:
1. "Quiero homologar X" → precio → imágenes → expediente
2. "Quiero homologar X" → precio → expediente directo (sin imágenes)
3. VIABILIDAD_MODE no existe en transiciones
"""

import pytest
from typing import Any


# =============================================================================
# TEST 1: Flujo completo con imágenes
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_flow_quiero_homologar_to_images():
    """
    Test E2E: Usuario dice "Quiero homologar X" → precio → "ver fotos" → imágenes → "abrir expediente".
    
    Flujo esperado:
    1. "Quiero homologar escape" → PRESUPUESTO_MODE
    2. PRESUPUESTO identifica elemento, calcula precio
    3. PRESUPUESTO responde con precio + 2 opciones
    4. Usuario: "Ver fotos"
    5. PRESUPUESTO llama enviar_imagenes_ejemplo
    6. PRESUPUESTO pregunta: "¿Abrir expediente?"
    7. Usuario: "Sí"
    8. Transición a EVALUACION_GATEWAY
    
    TODO: Implementar cuando framework de E2E esté listo
    """
    pytest.skip("E2E framework not implemented yet - requires full conversation mock")
    
    # Pseudo-código del flujo:
    # state = create_initial_state(...)
    # 
    # # Turn 1: "Quiero homologar escape"
    # result = await graph.ainvoke({"user_message": "Quiero homologar escape"}, state)
    # assert result["current_mode"] == "PRESUPUESTO_MODE"
    # assert "precio" in result["ai_response"].lower()
    # 
    # # Turn 2: "Ver fotos"
    # result = await graph.ainvoke({"user_message": "Ver fotos"}, result)
    # assert result["mode_context"]["imagenes_enviadas"] == True
    # assert result["pending_images"] is not None
    # 
    # # Turn 3: "Sí, abrir expediente"
    # result = await graph.ainvoke({"user_message": "Sí, abrir expediente"}, result)
    # assert result["current_mode"] == "EVALUACION_GATEWAY"


# =============================================================================
# TEST 2: Flujo directo a expediente
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_flow_direct_to_expediente():
    """
    Test E2E: Usuario dice "Quiero homologar X" → precio → "abrir expediente" directo.
    
    Flujo esperado:
    1. "Quiero homologar escape" → PRESUPUESTO_MODE
    2. PRESUPUESTO identifica, calcula precio
    3. PRESUPUESTO responde con precio + 2 opciones
    4. Usuario: "Abrir expediente"
    5. Transición directa a EVALUACION_GATEWAY (sin imágenes)
    
    TODO: Implementar cuando framework de E2E esté listo
    """
    pytest.skip("E2E framework not implemented yet - requires full conversation mock")
    
    # Pseudo-código del flujo:
    # state = create_initial_state(...)
    # 
    # # Turn 1: "Quiero homologar escape"
    # result = await graph.ainvoke({"user_message": "Quiero homologar escape"}, state)
    # assert result["current_mode"] == "PRESUPUESTO_MODE"
    # assert "precio" in result["ai_response"].lower()
    # 
    # # Turn 2: "Abrir expediente" (sin pedir imágenes)
    # result = await graph.ainvoke({"user_message": "Abrir expediente"}, result)
    # assert result["current_mode"] == "EVALUACION_GATEWAY"
    # assert result["mode_context"].get("imagenes_enviadas") != True


# =============================================================================
# TEST 3: VIABILIDAD_MODE no existe en transiciones
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_viabilidad_mode_in_transitions():
    """
    Verifica que VIABILIDAD_MODE ha sido eliminado de TODAS las estructuras de transición.
    """
    from agent.router.mode_transitions import (
        ALLOWED_TRANSITIONS,
        CONTEXT_PRESERVE_RULES,
    )
    from agent.state.conversation_state import ConversationMode
    import typing
    
    # 1. Verificar que VIABILIDAD no está en ConversationMode enum
    mode_literals = typing.get_args(ConversationMode)
    assert "VIABILIDAD_MODE" not in mode_literals, (
        "VIABILIDAD_MODE todavía existe en ConversationMode Literal"
    )
    
    # 2. Verificar que VIABILIDAD no está en ALLOWED_TRANSITIONS (como source)
    assert "VIABILIDAD_MODE" not in ALLOWED_TRANSITIONS, (
        "VIABILIDAD_MODE todavía existe en ALLOWED_TRANSITIONS como source"
    )
    
    # 3. Verificar que VIABILIDAD no está en ALLOWED_TRANSITIONS (como target)
    for source, targets in ALLOWED_TRANSITIONS.items():
        assert "VIABILIDAD_MODE" not in targets, (
            f"VIABILIDAD_MODE todavía está en ALLOWED_TRANSITIONS['{source}'] como target"
        )
    
    # 4. Verificar que VIABILIDAD no está en CONTEXT_PRESERVE_RULES
    assert "VIABILIDAD_MODE" not in CONTEXT_PRESERVE_RULES, (
        "VIABILIDAD_MODE todavía existe en CONTEXT_PRESERVE_RULES como source"
    )
    
    for source, targets_dict in CONTEXT_PRESERVE_RULES.items():
        for target in targets_dict:
            assert target != "VIABILIDAD_MODE", (
                f"VIABILIDAD_MODE todavía está en CONTEXT_PRESERVE_RULES['{source}'] como target"
            )
    
    print("✅ VIABILIDAD_MODE correctamente eliminado de:")
    print(f"  - ConversationMode Literal: ✓")
    print(f"  - ALLOWED_TRANSITIONS: ✓")
    print(f"  - CONTEXT_PRESERVE_RULES: ✓")


# =============================================================================
# TEST 4: EXTRA - Verificar que prompts NO existen para VIABILIDAD
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_viabilidad_prompt_file():
    """
    Verifica que el archivo de prompt de VIABILIDAD_MODE no existe (o está archivado).
    """
    import os
    
    viabilidad_prompt_path = "/home/autohomologacion/msi-a/agent/prompts/modes/viabilidad_mode.md"
    
    # El archivo NO debe existir en prompts/modes/
    assert not os.path.exists(viabilidad_prompt_path), (
        f"Archivo de prompt VIABILIDAD todavía existe en: {viabilidad_prompt_path}"
    )
    
    # Verificar que SÍ existe el prompt de PRESUPUESTO
    presupuesto_prompt_path = "/home/autohomologacion/msi-a/agent/prompts/modes/presupuesto_mode.md"
    assert os.path.exists(presupuesto_prompt_path), (
        f"Archivo de prompt PRESUPUESTO no existe en: {presupuesto_prompt_path}"
    )
    
    print("✅ Archivos de prompts correctos:")
    print(f"  - viabilidad_mode.md: NO existe ✓")
    print(f"  - presupuesto_mode.md: SÍ existe ✓")


# =============================================================================
# TEST 5: EXTRA - Verificar que el archivo viabilidad_mode.py no existe
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_viabilidad_mode_file():
    """
    Verifica que el archivo viabilidad_mode.py NO existe (archivado).
    """
    import os
    
    viabilidad_file_path = "/home/autohomologacion/msi-a/agent/modes/viabilidad_mode.py"
    
    # El archivo NO debe existir en modes/
    assert not os.path.exists(viabilidad_file_path), (
        f"Archivo viabilidad_mode.py todavía existe en: {viabilidad_file_path}"
    )
    
    # Verificar que SÍ existe en archive
    archived_path = "/home/autohomologacion/msi-a/archive/fusion-viabilidad-presupuesto/viabilidad_mode.py"
    # Este test es opcional - el archivo puede estar archivado o no
    if os.path.exists(archived_path):
        print("✅ viabilidad_mode.py correctamente archivado")
    else:
        print("ℹ️  viabilidad_mode.py no encontrado en archive (puede haber sido eliminado)")
    
    print(f"✅ viabilidad_mode.py NO existe en agent/modes/")


# =============================================================================
# TEST 6: EXTRA - Verificar transición desde START a PRESUPUESTO
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_start_to_presupuesto_transition_allowed():
    """
    Verifica que la transición START → PRESUPUESTO_MODE está permitida.
    """
    from agent.router.mode_transitions import is_transition_allowed
    
    # START → PRESUPUESTO debe estar permitido
    assert is_transition_allowed("START", "PRESUPUESTO_MODE"), (
        "Transición START → PRESUPUESTO_MODE NO está permitida"
    )
    
    # PRESUPUESTO → EVALUACION_GATEWAY debe estar permitido
    assert is_transition_allowed("PRESUPUESTO_MODE", "EVALUACION_GATEWAY"), (
        "Transición PRESUPUESTO_MODE → EVALUACION_GATEWAY NO está permitida"
    )
    
    # PRESUPUESTO → EXPEDIENTE_MODE NO debe estar permitido directamente
    # (debe pasar por EVALUACION_GATEWAY)
    assert not is_transition_allowed("PRESUPUESTO_MODE", "EXPEDIENTE_MODE"), (
        "Transición PRESUPUESTO_MODE → EXPEDIENTE_MODE está permitida (debe pasar por EVALUACION_GATEWAY)"
    )
    
    print("✅ Transiciones de PRESUPUESTO_MODE correctas:")
    print(f"  - START → PRESUPUESTO_MODE: ✓")
    print(f"  - PRESUPUESTO_MODE → EVALUACION_GATEWAY: ✓")
    print(f"  - PRESUPUESTO_MODE → EXPEDIENTE_MODE: ✗ (correcto, debe pasar por EVALUACION_GATEWAY)")


# =============================================================================
# TEST 7: EXTRA - Verificar que PRESUPUESTO preserva contexto correcto
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_presupuesto_context_preservation():
    """
    Verifica que PRESUPUESTO_MODE preserva el contexto correcto en transiciones.
    """
    from agent.router.mode_transitions import CONTEXT_PRESERVE_RULES
    
    # PRESUPUESTO → EVALUACION_GATEWAY debe preservar elementos y tarifa
    preserved = CONTEXT_PRESERVE_RULES.get("PRESUPUESTO_MODE", {}).get("EVALUACION_GATEWAY", [])
    
    expected_keys = [
        "categoria_slug",
        "elementos_confirmados",
        "element_codes",
        "tarifa_calculada",
    ]
    
    for key in expected_keys:
        assert key in preserved, (
            f"Clave '{key}' NO se preserva en PRESUPUESTO → EVALUACION_GATEWAY"
        )
    
    # Verificar que NO se preservan claves obsoletas
    obsolete_keys = ["estimacion_precio", "viabilidad_resultado"]
    for key in obsolete_keys:
        assert key not in preserved, (
            f"Clave obsoleta '{key}' todavía se preserva en transición"
        )
    
    print("✅ Contexto de PRESUPUESTO_MODE correctamente preservado:")
    print(f"  - Claves preservadas: {len(preserved)}")
    print(f"  - Incluye: {', '.join(preserved)}")
    print(f"  - Claves obsoletas eliminadas: ✓")
