"""
Test: Checkpoint Persistence for mode_context Flags.

Verifies that ALL flags in mode_context persist correctly through
Redis checkpoint save/load cycles.

This is the unit test that validates the reducer functions work correctly.
"""

import pytest
import uuid
from agent.state.conversation_state import ConversationState, create_initial_state
from agent.state.checkpointer import get_redis_checkpointer, initialize_redis_indexes


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mode_context_flags_persist_to_redis():
    """
    Verify that mode_context flags persist correctly to Redis checkpoint.
    
    This test creates a state with multiple flags set, saves to Redis,
    loads from Redis, and verifies ALL flags are identical.
    
    CRITICAL FLAGS TO TEST:
    - precio_comunicado (bool)
    - imagenes_enviadas (bool)
    - elementos_confirmados (list)
    - tarifa_calculada (dict)
    - categoria_slug (str)
    - pending_variants (list)
    - waiting_for_image_choice (bool)
    """
    # Create unique thread_id
    thread_id = f"test-checkpoint-{uuid.uuid4()}"
    
    # Create initial state
    state = create_initial_state(
        conversation_id=thread_id,
        phone="+34600000002",
        user_name="Checkpoint Test User",
        client_type="particular",
    )
    
    # Set current mode
    state["current_mode"] = "PRESUPUESTO_MODE"
    
    # Set comprehensive mode_context with ALL critical flags
    state["mode_context"] = {
        # Basic info
        "categoria_slug": "motos-part",
        
        # Element tracking
        "elementos_confirmados": [
            {"code": "ESCAPE", "name": "Escape", "variant": None},
            {"code": "SUBCHASIS", "name": "Subchasis", "variant": None},
        ],
        "element_codes": ["ESCAPE", "SUBCHASIS"],
        "pending_variants": [
            {"element_code": "SUSPENSION", "variant_type": "posicion"}
        ],
        
        # Pricing state
        "tarifa_calculada": {
            "precio_final": 410.0,
            "precio_base": 350.0,
            "elementos": ["ESCAPE"],
            "categoria": "motos-part",
        },
        "precio_comunicado": True,  # CRITICAL FLAG
        
        # Image state
        "imagenes_enviadas": False,  # CRITICAL FLAG
        "waiting_for_image_choice": True,  # CRITICAL FLAG
        
        # Vehicle info
        "vehiculo": {
            "marca": "Honda",
            "modelo": "CB500X",
        },
        
        # Variant resolution
        "variante_resuelta": True,
        "elemento_tentativo": None,
        "elemento_confirmado": {
            "code": "ESCAPE",
            "name": "Escape",
        },
    }
    
    # Also set other important state fields
    state["tarifa_actual"] = {
        "precio_final": 410.0,
        "imagenes_ejemplo": [
            {"url": "https://example.com/img1.jpg"},
        ],
    }
    
    state["messages"] = [
        {"role": "user", "content": "Quiero homologar el escape"},
        {"role": "assistant", "content": "El presupuesto es de 410€ +IVA"},
    ]
    
    state["total_message_count"] = 2
    state["is_first_interaction"] = False
    
    # Get Redis checkpointer
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    
    # Config for this thread
    config = {"configurable": {"thread_id": thread_id}}
    
    # ================================================================
    # SAVE: Persist state to Redis
    # ================================================================
    
    await checkpointer.aput(config, state, metadata={}, new_versions={})
    
    print("✅ Checkpoint saved to Redis")
    
    # ================================================================
    # LOAD: Retrieve state from Redis
    # ================================================================
    
    loaded_state = await checkpointer.aget(config)
    
    # Verify checkpoint exists
    assert loaded_state is not None, "Checkpoint should exist in Redis"
    
    print("✅ Checkpoint loaded from Redis")
    
    # ================================================================
    # VERIFY: All mode_context flags are identical
    # ================================================================
    
    original_context = state["mode_context"]
    loaded_context = loaded_state.get("mode_context", {})
    
    # CRITICAL FLAGS
    assert loaded_context.get("precio_comunicado") is True, \
        "precio_comunicado flag must persist (CRITICAL BUG FIX)"
    
    assert loaded_context.get("imagenes_enviadas") is False, \
        "imagenes_enviadas flag must persist"
    
    assert loaded_context.get("waiting_for_image_choice") is True, \
        "waiting_for_image_choice flag must persist"
    
    # CATEGORIA
    assert loaded_context.get("categoria_slug") == "motos-part", \
        "categoria_slug must persist"
    
    # ELEMENTOS CONFIRMADOS (list comparison)
    loaded_elementos = loaded_context.get("elementos_confirmados", [])
    assert len(loaded_elementos) == 2, \
        "elementos_confirmados list length must persist"
    assert loaded_elementos[0]["code"] == "ESCAPE", \
        "First element code must persist"
    assert loaded_elementos[1]["code"] == "SUBCHASIS", \
        "Second element code must persist"
    
    # ELEMENT CODES
    loaded_codes = loaded_context.get("element_codes", [])
    assert loaded_codes == ["ESCAPE", "SUBCHASIS"], \
        "element_codes list must persist"
    
    # PENDING VARIANTS
    loaded_variants = loaded_context.get("pending_variants", [])
    assert len(loaded_variants) == 1, \
        "pending_variants list must persist"
    assert loaded_variants[0]["element_code"] == "SUSPENSION", \
        "pending_variant element_code must persist"
    
    # TARIFA CALCULADA (nested dict)
    loaded_tarifa = loaded_context.get("tarifa_calculada", {})
    assert loaded_tarifa.get("precio_final") == 410.0, \
        "tarifa_calculada.precio_final must persist"
    assert loaded_tarifa.get("categoria") == "motos-part", \
        "tarifa_calculada.categoria must persist"
    
    # VEHICULO (nested dict)
    loaded_vehiculo = loaded_context.get("vehiculo", {})
    assert loaded_vehiculo.get("marca") == "Honda", \
        "vehiculo.marca must persist"
    assert loaded_vehiculo.get("modelo") == "CB500X", \
        "vehiculo.modelo must persist"
    
    # BOOLEAN FLAGS
    assert loaded_context.get("variante_resuelta") is True, \
        "variante_resuelta flag must persist"
    
    # NULLABLE FIELDS
    assert loaded_context.get("elemento_tentativo") is None, \
        "elemento_tentativo (None) must persist"
    
    loaded_confirmado = loaded_context.get("elemento_confirmado", {})
    assert loaded_confirmado.get("code") == "ESCAPE", \
        "elemento_confirmado must persist"
    
    # ================================================================
    # VERIFY: Root state fields also persist
    # ================================================================
    
    assert loaded_state.get("current_mode") == "PRESUPUESTO_MODE", \
        "current_mode must persist"
    
    assert loaded_state.get("total_message_count") == 2, \
        "total_message_count must persist"
    
    assert loaded_state.get("is_first_interaction") is False, \
        "is_first_interaction flag must persist"
    
    # Messages list
    loaded_messages = loaded_state.get("messages", [])
    assert len(loaded_messages) == 2, \
        "messages list length must persist"
    
    # tarifa_actual (root level)
    loaded_tarifa_actual = loaded_state.get("tarifa_actual", {})
    assert loaded_tarifa_actual.get("precio_final") == 410.0, \
        "tarifa_actual (root level) must persist"
    
    print("✅ All flags persisted correctly through Redis checkpoint!")
    print(f"   - precio_comunicado: {loaded_context.get('precio_comunicado')}")
    print(f"   - imagenes_enviadas: {loaded_context.get('imagenes_enviadas')}")
    print(f"   - elementos_confirmados: {len(loaded_elementos)} items")
    print(f"   - tarifa_calculada.precio_final: {loaded_tarifa.get('precio_final')}")
    print(f"   - categoria_slug: {loaded_context.get('categoria_slug')}")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_multiple_checkpoint_updates():
    """
    Verify that multiple checkpoint saves/loads preserve cumulative state.
    
    Simulates:
    1. Save with precio_comunicado=False
    2. Load and update to precio_comunicado=True
    3. Save again
    4. Load and verify precio_comunicado=True persists
    """
    thread_id = f"test-multi-checkpoint-{uuid.uuid4()}"
    
    state = create_initial_state(
        conversation_id=thread_id,
        phone="+34600000003",
    )
    
    state["current_mode"] = "PRESUPUESTO_MODE"
    state["mode_context"] = {
        "precio_comunicado": False,
        "categoria_slug": "motos-part",
    }
    
    checkpointer = get_redis_checkpointer()
    await initialize_redis_indexes(checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    
    # ── SAVE #1: precio_comunicado=False ──
    await checkpointer.aput(config, state, metadata={}, new_versions={})
    
    # ── LOAD #1 ──
    loaded_state_1 = await checkpointer.aget(config)
    assert loaded_state_1["mode_context"]["precio_comunicado"] is False
    
    # ── UPDATE: Set precio_comunicado=True ──
    loaded_state_1["mode_context"]["precio_comunicado"] = True
    loaded_state_1["mode_context"]["tarifa_calculada"] = {"precio_final": 410.0}
    
    # ── SAVE #2: precio_comunicado=True ──
    await checkpointer.aput(config, loaded_state_1, metadata={}, new_versions={})
    
    # ── LOAD #2 ──
    loaded_state_2 = await checkpointer.aget(config)
    
    # VERIFY: precio_comunicado=True persists
    assert loaded_state_2["mode_context"]["precio_comunicado"] is True, \
        "precio_comunicado=True must persist after second save"
    
    assert loaded_state_2["mode_context"]["tarifa_calculada"]["precio_final"] == 410.0, \
        "tarifa_calculada must persist"
    
    assert loaded_state_2["mode_context"]["categoria_slug"] == "motos-part", \
        "categoria_slug must still persist"
    
    print("✅ Multiple checkpoint updates preserve cumulative state")
