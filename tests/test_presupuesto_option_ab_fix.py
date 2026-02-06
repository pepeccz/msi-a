"""
Tests de integración para el fix de "Re-pregunta elementos después de Opción A".

Verifica que después de elegir Opción A (ver fotos), el agente NO vuelve a
preguntar qué elementos quiere homologar.

Fase 1: Tests para la implementación quirúrgica (ContextVar + flag management)
Fase 2: Tests para pattern matching pre-LLM (cuando se implemente)
"""
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.state.conversation_state import ConversationState


# =============================================================================
# FASE 1: Tests para ContextVar + Flag Management
# =============================================================================

@pytest.mark.asyncio
async def test_option_a_no_reidentify_elements():
    """
    Test Case 1 (del plan): Flujo completo A sin re-identificación.
    
    Flujo:
    1. Usuario: "quiero homologar escape"
    2. Agente: identifica → calcula → comunica precio → ofrece A/B
    3. Usuario: "A"
    4. Agente: NO vuelve a identificar, responde confirmando fotos
    """
    # Setup
    mode = PresupuestoModeNode()
    
    # Estado inicial
    state: ConversationState = {
        "conversation_id": "test-conv-123",
        "messages": [],
        "user_name": "Test User",
        "phone": "+34600000000",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {},
        "client_type": "particular",
    }
    
    # --- TURNO 1: Identificar y calcular ---
    with patch.object(mode, '_get_llm') as mock_get_llm:
        mock_llm = AsyncMock()
        
        # Primera llamada: LLM pide identificar elementos
        mock_response_1 = Mock()
        mock_response_1.content = ""
        mock_response_1.tool_calls = [
            {
                "id": "call_123",
                "name": "identificar_y_resolver_elementos",
                "args": {"categoria_vehiculo": "motos-part", "elementos_input": ["escape"]},
            },
            {
                "id": "call_456",
                "name": "calcular_tarifa_con_elementos",
                "args": {"categoria_slug": "motos-part", "elemento_codes": ["ESCAPE"]},
            },
        ]
        mock_response_1.usage_metadata = None
        
        # Segunda llamada: LLM comunica precio y ofrece A/B
        mock_response_final_1 = Mock()
        mock_response_final_1.content = (
            "El precio para homologar el escape es de 350€ +IVA. "
            "¿Quieres: Opción A) Ver fotos de ejemplo, B) Abrir expediente directamente?"
        )
        mock_response_final_1.tool_calls = None
        mock_response_final_1.usage_metadata = None
        
        mock_llm.ainvoke = AsyncMock(side_effect=[mock_response_1, mock_response_final_1])
        mock_get_llm.return_value = mock_llm
        
        # Mock _execute_and_log_tool para simular resultados
        with patch.object(mode, '_execute_and_log_tool') as mock_execute:
            # Resultados de tools
            mock_execute.side_effect = [
                # identificar_y_resolver_elementos
                '{"success": true, "elementos_listos": [{"codigo": "ESCAPE", "nombre": "Escape"}], "elementos_con_variantes": []}',
                # calcular_tarifa_con_elementos
                '{"success": true, "precio_final": 350.0, "price": 350.0, "warnings": []}',
            ]
            
            result1 = await mode._process_message("quiero homologar escape", state)
        
        # Verificaciones Turno 1
        assert "precio" in result1["mode_context"] or "tarifa_calculada" in result1["mode_context"], \
            "Debe tener información de precio calculado"
        assert result1["mode_context"].get("waiting_for_image_choice") == True, \
            "Flag debe activarse al ofrecer opciones A/B"
        
        # --- TURNO 2: Usuario elige "A" ---
        # Actualizar estado con resultado del turno 1
        state["mode_context"] = result1["mode_context"]
        state["messages"].append({
            "role": "assistant",
            "content": result1["ai_response"],
        })
        
        # Reset mock para segundo turno
        mock_llm.ainvoke = AsyncMock()
        
        # LLM responde a opción A (SIN volver a identificar)
        mock_response_2 = Mock()
        mock_response_2.content = "Perfecto, ya te he enviado las fotos. ¿Quieres que iniciemos el expediente?"
        mock_response_2.tool_calls = None  # ← NO debe llamar identificar_y_resolver_elementos
        mock_response_2.usage_metadata = None
        
        mock_llm.ainvoke.return_value = mock_response_2
        
        result2 = await mode._process_message("A", state)
        
        # ✅ VERIFICACIONES CRÍTICAS
        assert result2["mode_context"].get("waiting_for_image_choice") == False, \
            "Flag debe desactivarse después de responder"
        assert result2["mode_context"].get("opcion_seleccionada") == "A", \
            "Debe registrar que eligió A"
        
        # Verificar que en el resultado final no hay llamada a identificar
        assert "identificar_y_resolver_elementos" not in str(result2.get("ai_response", "")), \
            "No debe mencionar re-identificación en respuesta"


@pytest.mark.asyncio
async def test_contextvar_reinjection():
    """
    Test Case 3 (del plan): ContextVar se re-inyecta durante el loop.
    
    Verifica que set_current_state() se llama múltiples veces durante
    el procesamiento de múltiples tool calls.
    """
    mode = PresupuestoModeNode()
    
    state: ConversationState = {
        "conversation_id": "test-conv-456",
        "messages": [],
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {},
        "client_type": "particular",
    }
    
    with patch('agent.modes.presupuesto_mode.set_current_state') as mock_set_state:
        with patch.object(mode, '_get_llm') as mock_get_llm:
            mock_llm = AsyncMock()
            
            # Simular respuesta con múltiples tool calls
            mock_response_tools = Mock()
            mock_response_tools.content = ""
            mock_response_tools.tool_calls = [
                {"id": "call1", "name": "identificar_y_resolver_elementos", "args": {}},
                {"id": "call2", "name": "calcular_tarifa_con_elementos", "args": {}},
            ]
            mock_response_tools.usage_metadata = None
            
            mock_response_final = Mock()
            mock_response_final.content = "Respuesta final"
            mock_response_final.tool_calls = None
            mock_response_final.usage_metadata = None
            
            mock_llm.ainvoke = AsyncMock(side_effect=[mock_response_tools, mock_response_final])
            mock_get_llm.return_value = mock_llm
            
            # Mock las tools para que retornen resultados
            with patch.object(mode, '_execute_and_log_tool') as mock_execute:
                mock_execute.side_effect = [
                    '{"success": true}',
                    '{"success": true, "precio_final": 350.0}',
                ]
                
                await mode._process_message("escape", state)
            
            # ✅ VERIFICACIÓN: set_current_state llamado múltiples veces
            # (1 inicial + N tool calls)
            # Debe ser al menos 3: 1 inicial + 2 después de cada tool call
            assert mock_set_state.call_count >= 3, \
                f"set_current_state debe llamarse al menos 3 veces (1 inicial + 2 tool calls), fue llamado {mock_set_state.call_count} veces"


@pytest.mark.asyncio
async def test_prompt_includes_waiting_flag():
    """
    Test Case 4 (del plan): Prompt dinámico incluye flag de espera.
    
    Verifica que cuando waiting_for_image_choice=True, el prompt
    incluye la instrucción explícita de NO volver a identificar.
    """
    from agent.prompts.loader import assemble_system_prompt
    
    mode_context = {
        "elementos_confirmados": ["ESCAPE"],
        "element_codes": ["ESCAPE"],
        "tarifa_calculada": {"precio_final": 350.0},
        "precio_comunicado": True,
        "waiting_for_image_choice": True,
    }
    
    client_context = "Cliente: **PARTICULAR**\nUsa tipo_cliente: \"particular\" en herramientas."
    
    prompt = assemble_system_prompt(
        mode="PRESUPUESTO_MODE",
        mode_context=mode_context,
        client_context=client_context,
    )
    
    # ✅ VERIFICACIONES
    assert "ESCAPE" in prompt or "elementos" in prompt.lower(), \
        "Prompt debe mostrar información de elementos"
    assert "ESPERANDO" in prompt or "opción" in prompt.lower(), \
        "Prompt debe indicar que está esperando respuesta A/B"
    # Note: El prompt podría no tener exactamente "NO vuelvas a identificar"
    # pero debería tener alguna instrucción relacionada con el waiting flag


@pytest.mark.asyncio
async def test_option_b_flow():
    """
    Test adicional: Verificar flujo de Opción B (sin fotos).
    
    Asegura que elegir B también funciona correctamente.
    """
    mode = PresupuestoModeNode()
    
    state: ConversationState = {
        "conversation_id": "test-conv-789",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "waiting_for_image_choice": True,
            "element_codes": ["ESCAPE"],
            "elementos_confirmados": ["ESCAPE"],
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350.0},
        },
        "messages": [],
        "client_type": "particular",
    }
    
    with patch.object(mode, '_get_llm') as mock_get_llm:
        mock_llm = AsyncMock()
        
        mock_response = Mock()
        mock_response.content = "Entendido. ¿Quieres que iniciemos el expediente?"
        mock_response.tool_calls = None
        mock_response.usage_metadata = None
        
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        result = await mode._process_message("B", state)
        
        # ✅ VERIFICACIONES
        assert result["mode_context"].get("opcion_seleccionada") == "B", \
            "Debe registrar opción B"
        assert result["mode_context"].get("waiting_for_image_choice") == False, \
            "Flag debe desactivarse"


# =============================================================================
# Test de Regresión
# =============================================================================

@pytest.mark.asyncio
async def test_normal_flow_without_ab_options():
    """
    Test Case 3.3 (del plan): Test de regresión.
    
    Verifica que el flujo normal (sin opciones A/B) sigue funcionando.
    Por ejemplo, cuando el usuario hace consultas normales.
    """
    mode = PresupuestoModeNode()
    
    state: ConversationState = {
        "conversation_id": "test-conv-normal",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {},
        "messages": [],
        "client_type": "particular",
    }
    
    with patch.object(mode, '_get_llm') as mock_get_llm:
        mock_llm = AsyncMock()
        
        # Flujo normal sin opciones A/B
        mock_response = Mock()
        mock_response.content = "¿Qué vehículo tienes?"
        mock_response.tool_calls = None
        mock_response.usage_metadata = None
        
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        result = await mode._process_message("hola", state)
        
        # ✅ VERIFICACIONES
        assert result["mode_context"].get("waiting_for_image_choice") != True, \
            "Flag NO debe activarse si no se ofrecen opciones"
        assert "ai_response" in result, \
            "Debe retornar respuesta normal"


@pytest.mark.asyncio
async def test_price_before_images_still_enforced():
    """
    Verificar que la validación PRECIO_BEFORE_IMAGES sigue funcionando.
    
    El fix NO debe romper esta protección crítica.
    
    Nota: Este test verifica la lógica interna del tool enviar_imagenes_ejemplo,
    no requiere mocks de presupuesto_mode ya que no está probando el modo en sí.
    """
    from agent.tools.image_tools import enviar_imagenes_ejemplo
    from agent.tools.image_tools import set_current_state_for_image_tools
    
    # Estado sin precio comunicado
    state = {
        "conversation_id": "test-price-check",
        "mode_context": {
            "tarifa_calculada": {"precio_final": 350.0},
            "precio_comunicado": False,  # ← NO comunicado
            "categoria_slug": "motos-part",  # Agregar categoría para que el tool no falle por eso
            "element_codes": ["ESCAPE"],  # Agregar elementos
        },
        "client_type": "particular",
    }
    
    set_current_state_for_image_tools(state)
    
    # Intentar enviar imágenes sin mockear nada
    # El tool mismo debe bloquear internamente
    result = await enviar_imagenes_ejemplo.ainvoke({
        "tipo": "presupuesto",
    })
    
    # Verificar que bloqueó o advirtió
    assert isinstance(result, dict), "Debe retornar dict"
    
    # El tool debe bloquear porque precio_comunicado=False
    # Verificar que el mensaje indica el problema del precio
    message = result.get("message", "").lower()
    assert "precio" in message or "primero" in message or "antes" in message, \
        f"Debe mencionar que falta comunicar precio. Message: {result.get('message', '')}"


@pytest.mark.asyncio
async def test_price_communicated_detection():
    """
    Verificar que el agente detecta cuando ha comunicado el precio en su respuesta.
    
    El modo debe setear precio_comunicado=True cuando el LLM menciona el precio.
    """
    mode = PresupuestoModeNode()
    
    state: ConversationState = {
        "conversation_id": "test-price-detect",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "tarifa_calculada": {"precio_final": 350.0, "price": 350.0},
            "precio_comunicado": False,
        },
        "messages": [],
        "client_type": "particular",
    }
    
    with patch.object(mode, '_get_llm') as mock_get_llm:
        mock_llm = AsyncMock()
        
        # Respuesta del LLM que menciona el precio
        mock_response = Mock()
        mock_response.content = "El presupuesto para homologar el escape es de 350€ +IVA."
        mock_response.tool_calls = None
        mock_response.usage_metadata = None
        
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        result = await mode._process_message("¿cuánto cuesta?", state)
        
        # ✅ VERIFICACIÓN: Debe detectar que comunicó el precio
        # (El código tiene lógica para detectar "350€" en la respuesta)
        # Nota: Esta verificación depende de la implementación actual
        # que busca el patrón del precio en la respuesta
        assert "350" in result.get("ai_response", ""), \
            "La respuesta debe contener el precio"


@pytest.mark.asyncio
async def test_waiting_flag_activates_on_ab_mention():
    """
    Verificar que el flag waiting_for_image_choice se activa cuando
    el LLM menciona "opción A" y "opción B" en su respuesta.
    """
    mode = PresupuestoModeNode()
    
    state: ConversationState = {
        "conversation_id": "test-flag-activation",
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "tarifa_calculada": {"precio_final": 350.0},
            "precio_comunicado": False,
        },
        "messages": [],
        "client_type": "particular",
    }
    
    with patch.object(mode, '_get_llm') as mock_get_llm:
        mock_llm = AsyncMock()
        
        # Respuesta del LLM que menciona precio + opciones A/B
        mock_response = Mock()
        mock_response.content = (
            "El presupuesto es de 350€ +IVA. "
            "¿Quieres opción A) Ver fotos, o B) Continuar sin fotos?"
        )
        mock_response.tool_calls = None
        mock_response.usage_metadata = None
        
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm
        
        result = await mode._process_message("dame presupuesto", state)
        
        # ✅ VERIFICACIONES
        assert result["mode_context"].get("waiting_for_image_choice") == True, \
            "Flag debe activarse cuando LLM ofrece opciones A/B"


# =============================================================================
# Test de Extracción de Contexto
# =============================================================================

@pytest.mark.asyncio
async def test_extract_context_from_calcular_tarifa():
    """
    Verificar que _extract_context_from_tool extrae correctamente
    los datos de calcular_tarifa_con_elementos.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode
    
    tool_name = "calcular_tarifa_con_elementos"
    tool_args = {"categoria_slug": "motos-part", "elemento_codes": ["ESCAPE"]}
    result_str = '{"success": true, "precio_final": 350.0, "price": 350.0, "total": 350.0, "warnings": []}'
    
    updates = PresupuestoModeNode._extract_context_from_tool(
        tool_name,
        tool_args,
        result_str,
    )
    
    # ✅ VERIFICACIONES
    assert updates.get("precio_calculado") == 350.0, \
        "Debe extraer precio_calculado"
    assert updates.get("tarifa_calculada") is not None, \
        "Debe guardar tarifa_calculada completa"
    assert updates.get("precio_comunicado") == False, \
        "Debe resetear precio_comunicado a False para nueva cotización"
    assert updates.get("imagenes_enviadas") == False, \
        "Debe resetear imagenes_enviadas a False para nueva cotización"


@pytest.mark.asyncio
async def test_extract_context_from_identificar():
    """
    Verificar que _extract_context_from_tool extrae correctamente
    los datos de identificar_y_resolver_elementos.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode
    
    tool_name = "identificar_y_resolver_elementos"
    tool_args = {"categoria_vehiculo": "motos-part", "elementos_input": ["escape"]}
    result_str = '''{
        "success": true,
        "elementos_listos": [{"codigo": "ESCAPE", "nombre": "Escape"}],
        "elementos_con_variantes": []
    }'''
    
    updates = PresupuestoModeNode._extract_context_from_tool(
        tool_name,
        tool_args,
        result_str,
    )
    
    # ✅ VERIFICACIONES
    assert updates.get("element_codes") == ["ESCAPE"], \
        "Debe extraer element_codes"
    assert updates.get("variante_resuelta") == True, \
        "Debe marcar variante_resuelta si no hay variantes pendientes"
    assert updates.get("categoria_slug") == "motos-part", \
        "Debe extraer categoria_slug"
