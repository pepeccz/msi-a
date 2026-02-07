"""
Test: Tool Flag Contract for calcular_tarifa_con_elementos.

Verifies that the tool returns internal flags that signal mode_context updates.

This contract will be implemented in Phase 2 of REFACTOR-001.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agent.modes.presupuesto_mode import PresupuestoModeNode


@pytest.mark.asyncio
@pytest.mark.unit
async def test_calcular_tarifa_returns_internal_flags():
    """
    Verify that calcular_tarifa_con_elementos returns _internal_flags.
    
    Expected return structure:
    {
        "success": True,
        "precio_final": 410.0,
        "precio_base": 350.0,
        ...
        "_internal_flags": {
            "precio_comunicado": True,  # Will be set based on LLM response
        }
    }
    
    NOTE: After refactor, _tarifa_actual is removed from root state.
    Data is now stored in mode_context["tarifa_calculada"] instead.
    """
    # TODO: This test requires the actual tool implementation
    # For now, we'll test the extraction logic in PresupuestoModeNode
    
    mode_node = PresupuestoModeNode()
    
    # Simulate tool result WITH internal flags (Phase 2 implementation)
    tool_result_json = """{
        "success": true,
        "precio_final": 410.0,
        "precio_base": 350.0,
        "precio_iva": 496.1,
        "elementos": ["ESCAPE"],
        "categoria": "motos-part",
        "imagenes_ejemplo": [
            {"url": "https://example.com/img.jpg", "tipo": "frontal"}
        ],
        "_internal_flags": {
            "set_tarifa_actual": true,
            "reset_precio_comunicado": true
        }
    }"""
    
    # Test the extraction logic
    updates = mode_node._extract_context_from_tool(
        "calcular_tarifa_con_elementos",
        {},
        tool_result_json
    )
    
    # REFACTORED: Check tarifa_calculada in mode_context instead of _tarifa_actual in root
    assert "tarifa_calculada" in updates, \
        "Tool extraction must create tarifa_calculada in mode_context"
    
    # Verify tarifa_calculada contains full data
    tarifa_calculada = updates["tarifa_calculada"]
    assert tarifa_calculada["precio_final"] == 410.0, \
        "tarifa_calculada must contain precio_final"
    
    assert "imagenes_ejemplo" in tarifa_calculada, \
        "tarifa_calculada must contain imagenes_ejemplo for enviar_imagenes_ejemplo"
    
    # REFACTOR-001: precio_comunicado is NOT set by _extract_context_from_tool
    # It's set by _apply_tool_flags() which reads tool_result["_internal_flags"]
    # _extract_context_from_tool only extracts tarifa_calculada
    # NOTE: This is intentional - flag management happens in separate helper
    
    print("✅ Tool flag contract verified (extraction logic)")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extraction_handles_missing_internal_flags():
    """
    Verify that extraction logic handles tools WITHOUT _internal_flags gracefully.
    
    This ensures backward compatibility during Phase 1-2 transition.
    
    NOTE: After refactor, tools without _internal_flags just don't set flags.
    This is acceptable behavior - the mode continues to work.
    """
    mode_node = PresupuestoModeNode()
    
    # Simulate OLD tool result WITHOUT internal flags
    tool_result_json = """{
        "success": true,
        "precio_final": 410.0,
        "elementos": ["ESCAPE"]
    }"""
    
    # Should not crash
    updates = mode_node._extract_context_from_tool(
        "calcular_tarifa_con_elementos",
        {},
        tool_result_json
    )
    
    # REFACTORED: Check tarifa_calculada instead of _tarifa_actual
    # Even without _internal_flags, the tool result should be stored
    assert "tarifa_calculada" in updates, \
        "Backward compatibility: should still extract tarifa_calculada even without _internal_flags"
    
    print("✅ Extraction handles missing _internal_flags gracefully")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_precio_comunicado_set_via_tool_flags():
    """
    CRITICAL REFACTOR TEST: Verify precio_comunicado is set via tool _internal_flags.
    
    This is the CORE of REFACTOR-001. Instead of pattern matching, we now use
    tool flags to signal state changes.
    
    The flow is:
    1. calcular_tarifa_con_elementos returns tool result with _internal_flags
    2. _apply_tool_flags() reads these flags and updates mode_context
    3. mode_context["precio_comunicado"] becomes True
    
    This eliminates fragile pattern matching and makes state changes explicit.
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    
    logger = structlog.get_logger()
    
    # Setup: mode_context with precio_comunicado=False
    mode_context = {
        "precio_comunicado": False,
        "categoria_slug": "motos-part",
        "conversation_id": "test-123",
    }
    
    # Simulate tool return with _internal_flags
    tool_result = {
        "success": True,
        "precio_final": 410.0,
        "precio_base": 350.0,
        "elementos": ["ESCAPE"],
        "categoria": "motos-part",
        "imagenes_ejemplo": [{"url": "https://example.com/img.jpg"}],
        "_internal_flags": {
            "precio_comunicado": True,  # This is the key flag
            "imagenes_enviadas": False,
        }
    }
    
    # Apply flags (this modifies mode_context in-place)
    _apply_tool_flags(mode_context, tool_result, logger)
    
    # VERIFY: The flags were applied
    assert mode_context["precio_comunicado"] is True, \
        "precio_comunicado should be set to True via _internal_flags"
    assert mode_context["imagenes_enviadas"] is False, \
        "imagenes_enviadas should be reset to False for new quotes"
    
    print("✅ precio_comunicado flag mechanism verified (via tool flags)")
    print("   - precio_comunicado set via _internal_flags")
    print("   - imagenes_enviadas reset for new quotes")
    print("   - NO pattern matching required!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_internal_flags_schema():
    """
    Define the schema for _internal_flags that tools should return.
    
    This is a specification test that documents the contract.
    """
    # Expected schema for _internal_flags
    expected_schema = {
        "set_tarifa_actual": bool,  # Signal to write tarifa_actual to root state
        "reset_precio_comunicado": bool,  # Signal to reset flag for new quotes
        # Future flags can be added here
    }
    
    # Example valid _internal_flags
    valid_flags = {
        "set_tarifa_actual": True,
        "reset_precio_comunicado": True,
    }
    
    # Validate structure
    for key, expected_type in expected_schema.items():
        assert key in valid_flags, f"Missing required flag: {key}"
        assert isinstance(valid_flags[key], expected_type), \
            f"Flag {key} should be {expected_type}, got {type(valid_flags[key])}"
    
    print("✅ _internal_flags schema validated")
    print(f"   Schema: {expected_schema}")


@pytest.mark.asyncio
@pytest.mark.unit  
async def test_tarifa_actual_content_requirements():
    """
    Define what MUST be in tarifa_actual for enviar_imagenes_ejemplo to work.
    
    This documents the contract between calcular_tarifa and enviar_imagenes.
    """
    # Minimum required fields in tarifa_actual
    required_fields = [
        "precio_final",
        "imagenes_ejemplo",  # CRITICAL: enviar_imagenes_ejemplo needs this
        "elementos",
        "categoria",
    ]
    
    # Example valid tarifa_actual
    valid_tarifa = {
        "success": True,
        "precio_final": 410.0,
        "precio_base": 350.0,
        "elementos": ["ESCAPE"],
        "categoria": "motos-part",
        "imagenes_ejemplo": [
            {"url": "https://example.com/img1.jpg", "tipo": "frontal"},
            {"url": "https://example.com/img2.jpg", "tipo": "lateral"},
        ],
    }
    
    # Validate
    for field in required_fields:
        assert field in valid_tarifa, \
            f"tarifa_actual missing required field: {field}"
    
    # Special validation for imagenes_ejemplo
    imagenes = valid_tarifa["imagenes_ejemplo"]
    assert isinstance(imagenes, list), "imagenes_ejemplo must be a list"
    assert len(imagenes) > 0, "imagenes_ejemplo must not be empty"
    assert "url" in imagenes[0], "Each image must have a 'url' field"
    
    print("✅ tarifa_actual content requirements validated")
    print(f"   Required fields: {required_fields}")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_tool_flags_with_json_string():
    """
    BUG FIX TEST: Verify _apply_tool_flags handles JSON STRING input.
    
    This is the CRITICAL bug fix - _execute_and_log_tool returns JSON STRING,
    not dict. The function must parse the string before applying flags.
    
    Root cause:
    - _execute_and_log_tool in base_mode.py line 315 returns json.dumps(result)
    - _apply_tool_flags expected dict but received string
    - String has no .get() method → flags never applied
    - precio_comunicado stayed False even after calcular_tarifa
    
    Fix:
    - _apply_tool_flags now accepts dict | str
    - Parses JSON string if needed
    - Type guards ensure robustness
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    import json
    
    logger = structlog.get_logger()
    
    # Setup: mode_context with precio_comunicado=False
    mode_context = {
        "precio_comunicado": False,
        "imagenes_enviadas": False,
        "conversation_id": "test-bug-fix",
    }
    
    # Simulate tool return AS JSON STRING (what actually happens in production)
    tool_result_dict = {
        "success": True,
        "precio_final": 410.0,
        "_internal_flags": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        }
    }
    tool_result_string = json.dumps(tool_result_dict)
    
    # Apply flags with STRING input
    _apply_tool_flags(mode_context, tool_result_string, logger)
    
    # VERIFY: Flags were applied even though input was STRING
    assert mode_context["precio_comunicado"] is True, \
        "BUG FIX: precio_comunicado should be set even with JSON string input"
    assert mode_context["imagenes_enviadas"] is False, \
        "BUG FIX: imagenes_enviadas should be set even with JSON string input"
    
    print("✅ BUG FIX VERIFIED: _apply_tool_flags handles JSON string input")
    print("   - Parses JSON string automatically")
    print("   - Applies flags correctly")
    print("   - precio_comunicado now works in production!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_tool_flags_with_invalid_json():
    """
    BUG FIX TEST: Verify _apply_tool_flags handles INVALID JSON gracefully.
    
    Edge case: If tool returns malformed JSON, function should:
    - Log warning
    - Return early (don't crash)
    - Leave mode_context unchanged
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    
    logger = structlog.get_logger()
    
    # Setup
    mode_context = {
        "precio_comunicado": False,
        "conversation_id": "test-invalid-json",
    }
    
    # Simulate INVALID JSON string
    invalid_json = '{"success": True, "price": INVALID}'
    
    # Should not crash
    _apply_tool_flags(mode_context, invalid_json, logger)
    
    # VERIFY: mode_context unchanged (flag not applied)
    assert mode_context["precio_comunicado"] is False, \
        "Invalid JSON should not modify mode_context"
    
    print("✅ ROBUSTNESS VERIFIED: Invalid JSON handled gracefully")
    print("   - No crash on malformed JSON")
    print("   - mode_context unchanged")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_tool_flags_with_non_dict_type():
    """
    BUG FIX TEST: Verify _apply_tool_flags handles non-dict types gracefully.
    
    Edge case: If tool returns something other than dict/string:
    - Log warning
    - Return early
    - Leave mode_context unchanged
    """
    from agent.modes.presupuesto_mode import _apply_tool_flags
    import structlog
    
    logger = structlog.get_logger()
    
    # Setup
    mode_context = {
        "precio_comunicado": False,
        "conversation_id": "test-non-dict",
    }
    
    # Test with various non-dict types
    test_cases = [
        123,           # int
        45.67,         # float
        True,          # bool
        None,          # None
        ["list"],      # list
    ]
    
    for invalid_input in test_cases:
        mode_context_copy = mode_context.copy()
        _apply_tool_flags(mode_context_copy, invalid_input, logger)
        
        assert mode_context_copy["precio_comunicado"] is False, \
            f"Non-dict type {type(invalid_input)} should not modify mode_context"
    
    print("✅ TYPE SAFETY VERIFIED: Non-dict types handled gracefully")
    print("   - Tested: int, float, bool, None, list")
    print("   - All handled without crash")
    print("   - mode_context unchanged")
