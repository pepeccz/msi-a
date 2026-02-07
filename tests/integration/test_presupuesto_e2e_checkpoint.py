"""
Test E2E: PRESUPUESTO Full Flow with Checkpoint Reload.

This test verifies the CRITICAL bug fix for precio_comunicado persistence:
1. User asks for price → Agent calculates (410€)
2. Save checkpoint to Redis
3. Reload conversation from checkpoint
4. User asks for images → Agent sends images WITHOUT re-sending price
5. CRITICAL: precio_comunicado=True MUST persist after checkpoint reload

This is the safety net for REFACTOR-001.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import AIMessage, ToolMessage

from agent.modes.presupuesto_mode import PresupuestoModeNode
from agent.state.conversation_state import ConversationState, create_initial_state
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes
from langgraph.graph import StateGraph


@pytest.mark.asyncio
@pytest.mark.integration
async def test_presupuesto_full_flow_with_checkpoint_reload():
    """
    E2E test: Full PRESUPUESTO flow with checkpoint persistence.
    
    Simulates:
    1. User: "Quiero homologar el escape de mi moto"
    2. Agent: Identifies ESCAPE, calculates 410€, communicates price
    3. Checkpoint saves to Redis (precio_comunicado=True in mode_context)
    4. Reload from checkpoint
    5. User: "Envíame las fotos"
    6. Agent: Sends images WITHOUT recalculating or re-stating price
    
    CRITICAL ASSERTION:
    - precio_comunicado=True MUST persist after checkpoint reload
    - Agent must NOT repeat price when sending images
    """
    # Setup: Create unique thread_id for this test
    thread_id = f"test-e2e-{uuid.uuid4()}"
    
    # Create initial state
    state = create_initial_state(
        conversation_id=thread_id,
        phone="+34600000001",
        user_name="Test User",
        client_type="particular",
    )
    
    # Set mode to PRESUPUESTO_MODE
    state["current_mode"] = "PRESUPUESTO_MODE"
    state["mode_context"] = {
        "categoria_slug": "motos-part",
        "elementos_confirmados": [],
        "precio_comunicado": False,
        "imagenes_enviadas": False,
    }
    
    # Get Redis checkpointer
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    
    # Config for this thread
    config = {"configurable": {"thread_id": thread_id}}
    
    # ================================================================
    # TURN 1: User asks for price → Agent calculates and communicates
    # ================================================================
    
    # Mock LLM response with tool call to calcular_tarifa
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock()
    
    # First LLM call: Identifies element and calls calcular_tarifa
    mock_llm.ainvoke.side_effect = [
        # First response: Tool call to calcular_tarifa
        AIMessage(
            content="",
            tool_calls=[{
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "elementos": ["ESCAPE"],
                    "categoria": "motos-part",
                    "skip_validation": False,
                },
                "id": "call_1",
            }]
        ),
        # Second response: After tool execution, communicates price
        AIMessage(
            content="El presupuesto para homologar el escape es de 410€ +IVA. Te envío las fotos de ejemplo:",
        ),
    ]
    
    # Mock the tool result
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.tarifa_tools.calcular_tarifa_con_elementos") as mock_tarifa_tool:
            # Configure mock tool to return success
            mock_tarifa_tool.return_value = AsyncMock(return_value={
                "success": True,
                "precio_final": 410.0,
                "precio_base": 350.0,
                "precio_iva": 496.1,
                "elementos": ["ESCAPE"],
                "categoria": "motos-part",
                "imagenes_ejemplo": [
                    {"url": "https://example.com/escape1.jpg", "tipo": "frontal"},
                    {"url": "https://example.com/escape2.jpg", "tipo": "lateral"},
                ],
            })
            
            # Process message
            mode_node = PresupuestoModeNode()
            state["user_message"] = "Quiero homologar el escape de mi moto"
            
            result = await mode_node.process(state)
    
    # Verify price was communicated
    assert "ai_response" in result
    assert "410" in result["ai_response"] or "410€" in result["ai_response"], \
        "Agent must communicate price in response"
    
    # Update state with result
    state.update(result)
    
    # CRITICAL: Verify precio_comunicado flag is set
    mode_context = state.get("mode_context", {})
    assert mode_context.get("precio_comunicado") is True, \
        "precio_comunicado flag must be True after price communication"
    
    # ================================================================
    # CHECKPOINT SAVE: Persist state to Redis
    # ================================================================
    
    # Save checkpoint (this is what LangGraph does automatically)
    await checkpointer.aput(config, state, metadata={}, new_versions={})
    
    # ================================================================
    # CHECKPOINT RELOAD: Simulate crash recovery
    # ================================================================
    
    # Clear local state (simulate fresh start)
    loaded_state = await checkpointer.aget(config)
    
    # Verify checkpoint was loaded successfully
    assert loaded_state is not None, "Checkpoint should exist in Redis"
    
    # CRITICAL ASSERTION #1: precio_comunicado persists
    loaded_mode_context = loaded_state.get("mode_context", {})
    assert loaded_mode_context.get("precio_comunicado") is True, \
        "CRITICAL BUG: precio_comunicado=True must persist after checkpoint reload!"
    
    # CRITICAL ASSERTION #2: Other flags persist too
    assert loaded_mode_context.get("categoria_slug") == "motos-part", \
        "categoria_slug must persist"
    assert loaded_mode_context.get("imagenes_enviadas") is False, \
        "imagenes_enviadas must persist (still False)"
    
    # ================================================================
    # TURN 2: User asks for images → Agent sends WITHOUT repeating price
    # ================================================================
    
    # Reset mock for second turn
    mock_llm.ainvoke.side_effect = [
        # First response: Tool call to enviar_imagenes_ejemplo
        AIMessage(
            content="",
            tool_calls=[{
                "name": "enviar_imagenes_ejemplo",
                "args": {
                    "tipo": "presupuesto",
                },
                "id": "call_2",
            }]
        ),
        # Second response: After images sent
        AIMessage(
            content="Te he enviado las fotos de ejemplo del escape. ¿Quieres que abramos un expediente?",
        ),
    ]
    
    with patch.object(PresupuestoModeNode, "_get_llm", return_value=mock_llm):
        with patch("agent.tools.image_tools.enviar_imagenes_ejemplo") as mock_image_tool:
            # Configure mock tool
            mock_image_tool.return_value = AsyncMock(return_value={
                "success": True,
                "images": [
                    {"url": "https://example.com/escape1.jpg"},
                    {"url": "https://example.com/escape2.jpg"},
                ],
            })
            
            # Process message with loaded state
            loaded_state["user_message"] = "Envíame las fotos"
            
            result = await mode_node.process(loaded_state)
    
    # CRITICAL ASSERTION #3: Agent does NOT repeat price
    ai_response = result.get("ai_response", "")
    assert "410" not in ai_response and "410€" not in ai_response, \
        "Agent must NOT repeat price when sending images (price already communicated)"
    
    # Verify images were sent
    assert "fotos" in ai_response.lower() or "imágenes" in ai_response.lower(), \
        "Agent must confirm images were sent"
    
    # Verify imagenes_enviadas flag is now True
    final_mode_context = result.get("mode_context", {})
    assert final_mode_context.get("imagenes_enviadas") is True, \
        "imagenes_enviadas flag must be True after sending images"
    
    # Verify precio_comunicado is STILL True
    assert final_mode_context.get("precio_comunicado") is True, \
        "precio_comunicado must remain True after sending images"
    
    print("✅ E2E Test PASSED: precio_comunicado persists through checkpoint reload")
