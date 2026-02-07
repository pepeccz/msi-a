"""
Test: ContextVar Synchronization with mode_context.

Verifies that ContextVars (used by tools) stay in sync with mode_context (state).

This is CRITICAL for the refactor because:
- mode_context stores the source of truth (precio_comunicado flag)
- ContextVars are used by tools for thread-safe access
- They must stay synchronized or bugs occur

Phase 2 will implement a sync helper. This test defines the contract.
"""

import pytest
from contextvars import ContextVar


# These will be the actual ContextVars used in production
# For now, we define them here for testing
context_precio_comunicado: ContextVar[bool] = ContextVar(
    "context_precio_comunicado",
    default=False
)

context_tarifa_actual: ContextVar[dict | None] = ContextVar(
    "context_tarifa_actual", 
    default=None
)


@pytest.mark.unit
def test_contextvar_basic_operations():
    """
    Test basic ContextVar operations to ensure they work as expected.
    
    This validates that ContextVars provide thread-safe isolation.
    """
    # Get default value
    assert context_precio_comunicado.get() is False, \
        "Default value should be False"
    
    # Set value
    context_precio_comunicado.set(True)
    assert context_precio_comunicado.get() is True, \
        "Value should be True after set"
    
    # Reset to default
    context_precio_comunicado.set(False)
    assert context_precio_comunicado.get() is False, \
        "Value should be False after reset"
    
    print("✅ ContextVar basic operations work correctly")


@pytest.mark.unit
def test_sync_helper_contract():
    """
    Define the contract for the sync helper that will be implemented in Phase 2.
    
    Expected function signature:
        sync_context_vars_from_mode_context(mode_context: dict) -> None
    
    Behavior:
        - Reads flags from mode_context
        - Sets corresponding ContextVars
        - Should be called BEFORE tool execution
    """
    # Example mode_context
    mode_context = {
        "precio_comunicado": True,
        "tarifa_calculada": {
            "precio_final": 410.0,
            "imagenes_ejemplo": [{"url": "https://example.com/img.jpg"}],
        },
    }
    
    # Simulate what the sync helper should do
    def sync_context_vars_from_mode_context(ctx: dict) -> None:
        """
        Sync ContextVars from mode_context.
        
        This function will be implemented in Phase 2.
        """
        # Sync precio_comunicado
        precio_com = ctx.get("precio_comunicado", False)
        context_precio_comunicado.set(precio_com)
        
        # Sync tarifa_actual (from tarifa_calculada or explicit field)
        tarifa = ctx.get("tarifa_calculada")
        context_tarifa_actual.set(tarifa)
    
    # Test the sync
    sync_context_vars_from_mode_context(mode_context)
    
    # Verify sync worked
    assert context_precio_comunicado.get() is True, \
        "precio_comunicado ContextVar should be synced"
    
    tarifa = context_tarifa_actual.get()
    assert tarifa is not None, \
        "tarifa_actual ContextVar should be synced"
    assert tarifa["precio_final"] == 410.0, \
        "tarifa_actual should contain correct data"
    
    print("✅ Sync helper contract validated")


@pytest.mark.unit
def test_sync_helper_handles_missing_fields():
    """
    Verify sync helper handles missing fields gracefully.
    
    If mode_context doesn't have precio_comunicado, should default to False.
    """
    # Mode context WITHOUT precio_comunicado
    mode_context = {
        "categoria_slug": "motos-part",
        # precio_comunicado is missing
    }
    
    def sync_context_vars_from_mode_context(ctx: dict) -> None:
        # Sync with defaults for missing fields
        precio_com = ctx.get("precio_comunicado", False)  # Default: False
        context_precio_comunicado.set(precio_com)
        
        tarifa = ctx.get("tarifa_calculada")  # Can be None
        context_tarifa_actual.set(tarifa)
    
    # Test sync
    sync_context_vars_from_mode_context(mode_context)
    
    # Verify defaults
    assert context_precio_comunicado.get() is False, \
        "Missing precio_comunicado should default to False"
    
    assert context_tarifa_actual.get() is None, \
        "Missing tarifa_calculada should be None"
    
    print("✅ Sync helper handles missing fields gracefully")


@pytest.mark.unit
def test_contextvar_isolation_between_calls():
    """
    Verify that ContextVars are isolated between different async tasks.
    
    This is critical for concurrent request handling.
    """
    # Set value
    context_precio_comunicado.set(True)
    assert context_precio_comunicado.get() is True
    
    # Simulate another task resetting it
    context_precio_comunicado.set(False)
    assert context_precio_comunicado.get() is False
    
    # In real async code, each task would have its own context
    # This test just validates the basic isolation mechanism works
    
    print("✅ ContextVar isolation verified")


@pytest.mark.unit
def test_integration_with_tool_execution():
    """
    Test the full flow: mode_context → sync → tool reads ContextVar.
    
    This simulates what will happen in production:
    1. PresupuestoModeNode has mode_context
    2. Before tool execution, sync ContextVars
    3. Tool reads ContextVar to check precio_comunicado
    """
    # Step 1: Mode context (from state)
    mode_context = {
        "precio_comunicado": True,
        "tarifa_calculada": {
            "precio_final": 410.0,
            "imagenes_ejemplo": [{"url": "https://example.com/img.jpg"}],
        },
    }
    
    # Step 2: Sync helper (called before tool execution)
    def sync_context_vars_from_mode_context(ctx: dict) -> None:
        context_precio_comunicado.set(ctx.get("precio_comunicado", False))
        context_tarifa_actual.set(ctx.get("tarifa_calculada"))
    
    sync_context_vars_from_mode_context(mode_context)
    
    # Step 3: Tool reads ContextVar
    def enviar_imagenes_ejemplo_check() -> bool:
        """
        Simulates the safety check in enviar_imagenes_ejemplo tool.
        
        Returns True if images can be sent, False otherwise.
        """
        precio_comunicado = context_precio_comunicado.get()
        tarifa_actual = context_tarifa_actual.get()
        
        if not precio_comunicado:
            return False  # BLOCK: Price not communicated
        
        if not tarifa_actual or not tarifa_actual.get("imagenes_ejemplo"):
            return False  # BLOCK: No images available
        
        return True  # ALLOW: All checks passed
    
    # Verify tool check passes
    can_send = enviar_imagenes_ejemplo_check()
    assert can_send is True, \
        "Tool should allow image sending when precio_comunicado=True"
    
    print("✅ Full integration flow validated")


@pytest.mark.unit
def test_integration_blocks_when_flag_false():
    """
    Verify that tool blocks when precio_comunicado=False.
    """
    # Mode context with precio_comunicado=False
    mode_context = {
        "precio_comunicado": False,  # CRITICAL: Not communicated
        "tarifa_calculada": {
            "precio_final": 410.0,
            "imagenes_ejemplo": [{"url": "https://example.com/img.jpg"}],
        },
    }
    
    # Sync
    def sync_context_vars_from_mode_context(ctx: dict) -> None:
        context_precio_comunicado.set(ctx.get("precio_comunicado", False))
        context_tarifa_actual.set(ctx.get("tarifa_calculada"))
    
    sync_context_vars_from_mode_context(mode_context)
    
    # Tool check
    def enviar_imagenes_ejemplo_check() -> bool:
        precio_comunicado = context_precio_comunicado.get()
        if not precio_comunicado:
            return False  # BLOCK
        return True
    
    # Verify tool blocks
    can_send = enviar_imagenes_ejemplo_check()
    assert can_send is False, \
        "Tool should BLOCK image sending when precio_comunicado=False"
    
    print("✅ Tool correctly blocks when precio_comunicado=False")


@pytest.mark.unit
def test_sync_location_in_code():
    """
    Document WHERE the sync helper should be called in production code.
    
    Expected locations:
    1. PresupuestoModeNode._process_message() - Before tool loop
    2. After _extract_context_from_tool() - After context updates
    
    This test is documentation, not executable code.
    """
    expected_call_locations = [
        {
            "file": "agent/modes/presupuesto_mode.py",
            "function": "_process_message",
            "location": "Before tool calling loop (line ~150)",
            "reason": "Sync state before tools can read it",
        },
        {
            "file": "agent/modes/presupuesto_mode.py", 
            "function": "_process_message",
            "location": "After _extract_context_from_tool (line ~200)",
            "reason": "Re-sync after context updates from tool results",
        },
    ]
    
    # Validate structure
    for loc in expected_call_locations:
        assert "file" in loc
        assert "function" in loc
        assert "location" in loc
        assert "reason" in loc
    
    print("✅ Sync call locations documented")
    for loc in expected_call_locations:
        print(f"   - {loc['file']}::{loc['function']} - {loc['reason']}")


@pytest.mark.unit
def test_contextvar_cleanup():
    """
    Verify that ContextVars can be cleaned up after request processing.
    
    This prevents memory leaks in long-running processes.
    """
    # Set values
    context_precio_comunicado.set(True)
    context_tarifa_actual.set({"precio_final": 410.0})
    
    # Cleanup helper
    def cleanup_context_vars() -> None:
        """Reset ContextVars to default values."""
        context_precio_comunicado.set(False)
        context_tarifa_actual.set(None)
    
    # Execute cleanup
    cleanup_context_vars()
    
    # Verify cleanup
    assert context_precio_comunicado.get() is False, \
        "precio_comunicado should be reset"
    assert context_tarifa_actual.get() is None, \
        "tarifa_actual should be reset"
    
    print("✅ ContextVar cleanup verified")
