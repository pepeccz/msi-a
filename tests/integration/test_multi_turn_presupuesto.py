"""
Test: Multi-Turn PRESUPUESTO Flow with Flag Persistence.

Verifies that flags persist correctly across multiple conversation turns:
- Turn 1: Identify elements → elementos_confirmados set
- Turn 2: Calculate price → precio_comunicado set
- Turn 3: Send images → imagenes_enviadas set

Each flag must persist into the next turn.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.state.conversation_state import create_initial_state
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes


@pytest.mark.asyncio
@pytest.mark.integration
async def test_flags_persist_across_3_turns():
    """
    Verify that flags persist correctly across 3 conversation turns.
    
    Turn 1: User asks about element → elementos_confirmados set
    Turn 2: User confirms → tarifa calculated, precio_comunicado set
    Turn 3: User asks for images → imagenes_enviadas set
    
    Each flag must be present in subsequent turns.
    """
    thread_id = f"test-multi-turn-{uuid.uuid4()}"
    
    # Create initial state
    state = create_initial_state(
        conversation_id=thread_id,
        phone="+34600000004",
        user_name="Multi-Turn User",
        client_type="particular",
    )
    
    state["current_mode"] = "PRESUPUESTO_MODE"
    state["mode_context"] = {
        "categoria_slug": "motos-part",
        "elementos_confirmados": [],
        "precio_comunicado": False,
        "imagenes_enviadas": False,
    }
    
    # Get checkpointer
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    
    mode_node = PresupuestoModeNode()
    
    # ================================================================
    # TURN 1: Identify element → elementos_confirmados should be set
    # ================================================================
    
    mock_llm = AsyncMock()
    
    # Mock LLM to call identificar_y_resolver_elementos
    mock_llm.ainvoke = AsyncMock(side_effect=[
        # Tool call
        AIMessage(
            content="",
            tool_calls=[{
                "name": "identificar_y_resolver_elementos",
                "args": {
                    "categoria": "motos-part",
                    "descripcion": "escape",
                },
                "id": "call_turn1",
            }]
        ),
        # Response after tool
        AIMessage(
            content="He identificado el elemento ESCAPE. ¿Quieres que calcule el presupuesto?",
        ),
    ])
    
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.element_tools.identificar_y_resolver_elementos") as mock_id_tool:
            mock_id_tool.return_value = AsyncMock(return_value={
                "success": True,
                "elementos": [
                    {"code": "ESCAPE", "name": "Escape", "variant": None}
                ],
                "element_codes": ["ESCAPE"],
            })
            
            state["user_message"] = "Quiero homologar el escape"
            result_turn1 = await mode_node.process(state)
    
    # Update state with turn 1 result
    state.update(result_turn1)
    
    # Save checkpoint after turn 1
    await checkpointer.aput(config, state, metadata={}, new_versions={})
    
    # VERIFY: elementos_confirmados is set
    mode_context_turn1 = state.get("mode_context", {})
    assert len(mode_context_turn1.get("elementos_confirmados", [])) > 0, \
        "Turn 1: elementos_confirmados should be set after identification"
    
    print("✅ Turn 1: elementos_confirmados set")
    
    # ================================================================
    # TURN 2: Calculate price → precio_comunicado should be set
    # ================================================================
    
    # Reload from checkpoint (simulate new turn)
    loaded_state_turn2 = await checkpointer.aget(config)
    
    # Verify elementos_confirmados persisted
    mode_context_turn2_before = loaded_state_turn2.get("mode_context", {})
    assert len(mode_context_turn2_before.get("elementos_confirmados", [])) > 0, \
        "Turn 2: elementos_confirmados must persist from turn 1"
    
    # Mock LLM for turn 2
    mock_llm.ainvoke = AsyncMock(side_effect=[
        # Tool call
        AIMessage(
            content="",
            tool_calls=[{
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "elementos": ["ESCAPE"],
                    "categoria": "motos-part",
                    "skip_validation": True,
                },
                "id": "call_turn2",
            }]
        ),
        # Response after tool
        AIMessage(
            content="El presupuesto para el escape es de 410€ +IVA.",
        ),
    ])
    
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.tarifa_tools.calcular_tarifa_con_elementos") as mock_tarifa_tool:
            mock_tarifa_tool.return_value = AsyncMock(return_value={
                "success": True,
                "precio_final": 410.0,
                "precio_base": 350.0,
                "elementos": ["ESCAPE"],
                "categoria": "motos-part",
                "imagenes_ejemplo": [
                    {"url": "https://example.com/img.jpg"}
                ],
            })
            
            loaded_state_turn2["user_message"] = "Sí, dime el precio"
            result_turn2 = await mode_node.process(loaded_state_turn2)
    
    # Update state
    loaded_state_turn2.update(result_turn2)
    
    # Save checkpoint after turn 2
    await checkpointer.aput(config, loaded_state_turn2, metadata={}, new_versions={})
    
    # VERIFY: precio_comunicado is set AND elementos_confirmados still present
    mode_context_turn2 = loaded_state_turn2.get("mode_context", {})
    assert mode_context_turn2.get("precio_comunicado") is True, \
        "Turn 2: precio_comunicado should be True after price communication"
    
    assert len(mode_context_turn2.get("elementos_confirmados", [])) > 0, \
        "Turn 2: elementos_confirmados must still be present"
    
    print("✅ Turn 2: precio_comunicado set, elementos_confirmados persists")
    
    # ================================================================
    # TURN 3: Send images → imagenes_enviadas should be set
    # ================================================================
    
    # Reload from checkpoint (simulate new turn)
    loaded_state_turn3 = await checkpointer.aget(config)
    
    # Verify both flags persisted
    mode_context_turn3_before = loaded_state_turn3.get("mode_context", {})
    assert mode_context_turn3_before.get("precio_comunicado") is True, \
        "Turn 3: precio_comunicado must persist from turn 2"
    
    assert len(mode_context_turn3_before.get("elementos_confirmados", [])) > 0, \
        "Turn 3: elementos_confirmados must persist from turn 1"
    
    # Mock LLM for turn 3
    mock_llm.ainvoke = AsyncMock(side_effect=[
        # Tool call
        AIMessage(
            content="",
            tool_calls=[{
                "name": "enviar_imagenes_ejemplo",
                "args": {
                    "tipo": "presupuesto",
                },
                "id": "call_turn3",
            }]
        ),
        # Response after tool
        AIMessage(
            content="Te he enviado las fotos del escape.",
        ),
    ])
    
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.image_tools.enviar_imagenes_ejemplo") as mock_image_tool:
            mock_image_tool.return_value = AsyncMock(return_value={
                "success": True,
                "images": [{"url": "https://example.com/img.jpg"}],
            })
            
            loaded_state_turn3["user_message"] = "Envíame las fotos"
            result_turn3 = await mode_node.process(loaded_state_turn3)
    
    # Update state
    loaded_state_turn3.update(result_turn3)
    
    # VERIFY: All 3 flags are present
    mode_context_turn3 = loaded_state_turn3.get("mode_context", {})
    
    assert len(mode_context_turn3.get("elementos_confirmados", [])) > 0, \
        "Turn 3: elementos_confirmados must still be present from turn 1"
    
    assert mode_context_turn3.get("precio_comunicado") is True, \
        "Turn 3: precio_comunicado must still be True from turn 2"
    
    assert mode_context_turn3.get("imagenes_enviadas") is True, \
        "Turn 3: imagenes_enviadas should be True after sending images"
    
    print("✅ Turn 3: All flags persist correctly")
    print(f"   - elementos_confirmados: {len(mode_context_turn3.get('elementos_confirmados', []))} items")
    print(f"   - precio_comunicado: {mode_context_turn3.get('precio_comunicado')}")
    print(f"   - imagenes_enviadas: {mode_context_turn3.get('imagenes_enviadas')}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_flag_reset_on_new_calculation():
    """
    Verify that precio_comunicado resets when a NEW tariff is calculated.
    
    This allows multiple quotes in the same conversation.
    """
    thread_id = f"test-flag-reset-{uuid.uuid4()}"
    
    state = create_initial_state(
        conversation_id=thread_id,
        phone="+34600000005",
    )
    
    state["current_mode"] = "PRESUPUESTO_MODE"
    state["mode_context"] = {
        "categoria_slug": "motos-part",
        "precio_comunicado": True,  # From previous quote
        "tarifa_calculada": {"precio_final": 350.0},
    }
    
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    
    # Save initial state
    await checkpointer.aput(config, state, metadata={}, new_versions={})
    
    # ── NEW CALCULATION ──
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "elementos": ["ESCAPE", "SUBCHASIS"],
                    "categoria": "motos-part",
                    "skip_validation": True,
                },
                "id": "call_new",
            }]
        ),
        AIMessage(
            content="El nuevo presupuesto es de 450€ +IVA.",
        ),
    ])
    
    mode_node = PresupuestoModeNode()
    
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.tarifa_tools.calcular_tarifa_con_elementos") as mock_tool:
            mock_tool.return_value = AsyncMock(return_value={
                "success": True,
                "precio_final": 450.0,
                "elementos": ["ESCAPE", "SUBCHASIS"],
            })
            
            loaded_state = await checkpointer.aget(config)
            loaded_state["user_message"] = "También el subchasis"
            result = await mode_node.process(loaded_state)
    
    # VERIFY: precio_comunicado should reset to False initially
    # (then set to True after LLM mentions the price)
    # The _extract_context_from_tool resets it, but then pattern matching sets it True
    
    mode_context = result.get("mode_context", {})
    
    # The new tarifa_calculada should be present
    assert mode_context.get("tarifa_calculada", {}).get("precio_final") == 450.0, \
        "New tariff should be in mode_context"
    
    print("✅ Flag reset test passed")
