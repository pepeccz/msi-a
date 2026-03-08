"""
Tests for the fix-expediente-context-preservation change (Phase 2).

Covers two related changes:

1. agent/router/mode_transitions.py
   CONTEXT_PRESERVE_RULES["PRESUPUESTO_MODE"]["EXPEDIENTE_MODE"] now includes
   "precio_comunicado" and "imagenes_enviadas" in addition to the original three keys.

2. agent/tools/image_tools.py
   enviar_imagenes_ejemplo() has a new guard at the TOP of the `tipo=="presupuesto"`
   branch that returns success=False with EXPEDIENTE_MODE guidance when
   state["current_mode"] == "EXPEDIENTE_MODE".

Test inventory
--------------
Test 2.1  get_preserve_keys() returns both new keys
Test 2.2  transition_mode() carries precio_comunicado into new context
Test 2.3  EXPEDIENTE_MODE guard fires for tipo="presupuesto"
Test 2.4  PRESUPUESTO_MODE with precio_comunicado=True is NOT blocked by new guard
Test 2.5  Existing precio_comunicado guard still fires in PRESUPUESTO_MODE
Test 2.6  Full integration: transition carries both precio_comunicado and imagenes_enviadas
"""

from __future__ import annotations

import pytest

from agent.router.mode_transitions import get_preserve_keys
from agent.state.conversation_state import transition_mode
from agent.tools.image_tools import (
    enviar_imagenes_ejemplo,
    set_current_state_for_image_tools,
    clear_image_tools_state,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_presupuesto_state(
    *,
    conversation_id: str = "test-exp-pres-conv",
    precio_comunicado: bool = True,
    imagenes_enviadas: bool = True,
    element_codes: list[str] | None = None,
    tarifa_calculada: dict | None = None,
    categoria_slug: str = "motos-part",
) -> dict:
    """Return a minimal PRESUPUESTO_MODE state dict."""
    return {
        "conversation_id": conversation_id,
        "current_mode": "PRESUPUESTO_MODE",
        "previous_mode": "START",
        "mode_history": ["START"],
        "messages": [],
        "mode_context": {
            "precio_comunicado": precio_comunicado,
            "imagenes_enviadas": imagenes_enviadas,
            "element_codes": element_codes or ["ESCAPE"],
            "tarifa_calculada": tarifa_calculada or {"precio": 350.0},
            "categoria_slug": categoria_slug,
        },
        "draft_contexts": {},
        "retry_state": {},
        "pending_images": None,
        "user_phone": "+34600000000",
        "user_name": "Test User",
        "is_first_interaction": False,
        "client_type": "particular",
    }


def _make_expediente_state(
    *,
    conversation_id: str = "test-exp-conv",
    precio_comunicado: bool = True,
    imagenes_enviadas: bool = True,
) -> dict:
    """Return a minimal EXPEDIENTE_MODE state dict."""
    return {
        "conversation_id": conversation_id,
        "current_mode": "EXPEDIENTE_MODE",
        "previous_mode": "PRESUPUESTO_MODE",
        "mode_history": ["START", "PRESUPUESTO_MODE"],
        "messages": [],
        "mode_context": {
            "precio_comunicado": precio_comunicado,
            "imagenes_enviadas": imagenes_enviadas,
            "element_codes": ["ESCAPE"],
            "tarifa_calculada": {"precio": 350.0},
            "categoria_slug": "motos-part",
        },
        "draft_contexts": {},
        "retry_state": {},
        "pending_images": None,
        "user_phone": "+34600000000",
        "user_name": "Test User",
        "is_first_interaction": False,
        "client_type": "particular",
    }


# ===========================================================================
# Test 2.1 — Preserve keys contain the two new fields
# ===========================================================================

def test_presupuesto_to_expediente_preserve_keys_include_precio_comunicado():
    """
    get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE") must return a list
    that includes both "precio_comunicado" AND "imagenes_enviadas", in addition
    to the original keys.

    This validates Change 1 in mode_transitions.py.
    """
    keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")

    # Both new fields must be present
    assert "precio_comunicado" in keys, (
        f"Expected 'precio_comunicado' in preserve keys for PRESUPUESTO→EXPEDIENTE, "
        f"got: {keys}"
    )
    assert "imagenes_enviadas" in keys, (
        f"Expected 'imagenes_enviadas' in preserve keys for PRESUPUESTO→EXPEDIENTE, "
        f"got: {keys}"
    )

    # The original keys must still be there (no regression)
    for original_key in ("element_codes", "tarifa_calculada", "categoria_slug"):
        assert original_key in keys, (
            f"Original key '{original_key}' must still be in preserve keys, got: {keys}"
        )


# ===========================================================================
# Test 2.2 — transition_mode copies precio_comunicado into new context
# ===========================================================================

def test_transition_mode_preserves_precio_comunicado():
    """
    When transitioning from PRESUPUESTO_MODE to EXPEDIENTE_MODE,
    transition_mode() must copy precio_comunicado=True from the old context
    into the new mode_context.

    This validates that Change 1 is actually used correctly by callers.
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=False,  # Only checking precio_comunicado here
    )

    preserve_keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
    result = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=preserve_keys)

    # The returned dict must have mode_context
    assert "mode_context" in result, "transition_mode must return 'mode_context' key"

    new_ctx = result["mode_context"]
    # Unwrap Overwrite wrapper if needed (LangGraph internal wrapper)
    if hasattr(new_ctx, "__wrapped__") or hasattr(new_ctx, "value"):
        # Handle LangGraph Overwrite annotation
        ctx_dict = getattr(new_ctx, "value", new_ctx)
    else:
        ctx_dict = new_ctx

    assert ctx_dict.get("precio_comunicado") is True, (
        f"precio_comunicado must be True in the new EXPEDIENTE_MODE context, "
        f"got mode_context={dict(ctx_dict)}"
    )
    assert result["current_mode"] == "EXPEDIENTE_MODE", (
        "transition_mode must set current_mode to EXPEDIENTE_MODE"
    )


# ===========================================================================
# Test 2.3 — EXPEDIENTE_MODE guard fires for tipo="presupuesto"
# ===========================================================================

@pytest.mark.asyncio
async def test_enviar_imagenes_blocked_from_expediente_mode():
    """
    When the tool is called with tipo='presupuesto' while in EXPEDIENTE_MODE,
    the new guard must return success=False with guidance referencing
    either 'EXPEDIENTE_MODE' or 'iniciar_expediente'.

    This validates Change 2 in image_tools.py.
    """
    state = _make_expediente_state(
        precio_comunicado=True,
        imagenes_enviadas=True,
    )

    try:
        set_current_state_for_image_tools(state)
        # Invoke the tool directly (unwrap the @tool decorator)
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"}
        )
    finally:
        clear_image_tools_state()

    assert result.get("success") is False, (
        f"enviar_imagenes_ejemplo must return success=False when called from "
        f"EXPEDIENTE_MODE with tipo='presupuesto'. Got: {result}"
    )

    message = result.get("message", "")
    # The message must reference EXPEDIENTE_MODE or iniciar_expediente
    assert "EXPEDIENTE_MODE" in message or "iniciar_expediente" in message, (
        f"Message must reference 'EXPEDIENTE_MODE' or 'iniciar_expediente' "
        f"to guide the LLM. Got message: {message!r}"
    )


# ===========================================================================
# Test 2.4 — PRESUPUESTO_MODE with precio_comunicado=True is NOT blocked
# ===========================================================================

@pytest.mark.asyncio
async def test_enviar_imagenes_presupuesto_mode_not_blocked_by_new_guard():
    """
    When in PRESUPUESTO_MODE (NOT EXPEDIENTE_MODE), the new EXPEDIENTE_MODE guard
    must NOT fire, even if precio_comunicado=True.

    The call may fail for other reasons (e.g., no tarifa_calculada with active images),
    but the failure message must NOT reference the EXPEDIENTE_MODE guidance.

    This ensures the guard is narrow: it only fires for EXPEDIENTE_MODE.
    """
    # State: PRESUPUESTO_MODE, precio_comunicado=True — eligible for images
    # but no actual tarifa_calculada with active images, so it will fail
    # at a LATER guard (not the new EXPEDIENTE_MODE one).
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=False,
        tarifa_calculada=None,  # Will fail later, not at the new guard
    )

    try:
        set_current_state_for_image_tools(state)
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"}
        )
    finally:
        clear_image_tools_state()

    # The EXPEDIENTE_MODE guard-specific message must NOT appear
    message = result.get("message", "")
    assert "EXPEDIENTE_MODE" not in message or "iniciar_expediente" not in message, (
        "The new EXPEDIENTE_MODE guard must NOT fire when current_mode=PRESUPUESTO_MODE. "
        f"Got message: {message!r}"
    )

    # More specifically: the guard-specific phrase "Estás en EXPEDIENTE_MODE" must be absent
    assert "Estás en EXPEDIENTE_MODE" not in message, (
        f"EXPEDIENTE_MODE guard phrase must not appear in PRESUPUESTO_MODE call. "
        f"Got: {message!r}"
    )


# ===========================================================================
# Test 2.5 — Existing precio_comunicado guard still fires in PRESUPUESTO_MODE
# ===========================================================================

@pytest.mark.asyncio
async def test_enviar_imagenes_existing_guard_still_fires_in_presupuesto():
    """
    When in PRESUPUESTO_MODE with precio_comunicado=False, the EXISTING
    precio_comunicado guard (NOT the new EXPEDIENTE_MODE guard) must fire.

    Regression guard: the new guard must not replace or shadow the original one.
    The original guard message does NOT mention "EXPEDIENTE_MODE".
    """
    state = _make_presupuesto_state(
        precio_comunicado=False,  # The original guard should fire
        imagenes_enviadas=False,
    )

    try:
        set_current_state_for_image_tools(state)
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"}
        )
    finally:
        clear_image_tools_state()

    # Must fail (price not communicated)
    assert result.get("success") is False, (
        f"enviar_imagenes_ejemplo must return success=False when precio_comunicado=False. "
        f"Got: {result}"
    )

    message = result.get("message", "")

    # The original guard message must reference price communication
    assert "precio" in message.lower(), (
        f"Original precio_comunicado guard message must mention 'precio'. Got: {message!r}"
    )

    # It must NOT reference EXPEDIENTE_MODE (that's the new guard's message)
    assert "EXPEDIENTE_MODE" not in message, (
        f"The old precio_comunicado guard must NOT mention 'EXPEDIENTE_MODE'. "
        f"(That would indicate the new guard fired instead of the old one.) "
        f"Got: {message!r}"
    )


# ===========================================================================
# Test 2.6 — Integration: full transition preserves both flags
# ===========================================================================

def test_transition_mode_integration_presupuesto_to_expediente():
    """
    Full integration test:

    Build a PRESUPUESTO_MODE state with precio_comunicado=True and
    imagenes_enviadas=True (both flags set after successful quote + image flow).

    Use get_preserve_keys() to get the official key list, call transition_mode(),
    and assert that BOTH flags are preserved in the resulting EXPEDIENTE_MODE context.

    This is the end-to-end validation that Changes 1 and 2 work together:
    - Change 1 ensures keys are in the preserve list
    - The transition carries them
    - Change 2 can then read current_mode + imagenes_enviadas to guard correctly
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=True,
        element_codes=["ESCAPE", "SUBCHASIS"],
        tarifa_calculada={"precio": 450.0, "tier": "T2"},
        categoria_slug="motos-part",
    )

    preserve_keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
    result = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=preserve_keys)

    assert "mode_context" in result, "transition_mode must return a 'mode_context'"

    new_ctx = result["mode_context"]
    # Unwrap LangGraph Overwrite if needed
    if hasattr(new_ctx, "value"):
        ctx_dict = new_ctx.value
    else:
        ctx_dict = dict(new_ctx)

    # Both new flags must be preserved
    assert ctx_dict.get("precio_comunicado") is True, (
        f"precio_comunicado must be True after transition. Got ctx: {ctx_dict}"
    )
    assert ctx_dict.get("imagenes_enviadas") is True, (
        f"imagenes_enviadas must be True after transition. Got ctx: {ctx_dict}"
    )

    # Existing keys must also be preserved (no regression)
    assert ctx_dict.get("element_codes") == ["ESCAPE", "SUBCHASIS"], (
        f"element_codes must be preserved. Got: {ctx_dict.get('element_codes')}"
    )
    assert ctx_dict.get("categoria_slug") == "motos-part", (
        f"categoria_slug must be preserved. Got: {ctx_dict.get('categoria_slug')}"
    )
    assert ctx_dict.get("tarifa_calculada") == {"precio": 450.0, "tier": "T2"}, (
        f"tarifa_calculada must be preserved. Got: {ctx_dict.get('tarifa_calculada')}"
    )

    # Mode must have transitioned
    assert result["current_mode"] == "EXPEDIENTE_MODE"
    assert result["previous_mode"] == "PRESUPUESTO_MODE"
