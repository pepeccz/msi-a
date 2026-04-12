"""
Tests for context preservation across mode transitions.

Updated for WS4: context preservation now uses shared_context (merge_dicts)
instead of CONTEXT_PRESERVE_RULES whitelist. Cross-mode keys live in
shared_context and survive ALL transitions automatically.

Test inventory
--------------
Test 2.1  shared_context survives PRESUPUESTO → EXPEDIENTE transition
Test 2.2  transition_mode does NOT wipe shared_context
Test 2.3  EXPEDIENTE_MODE guard fires for tipo="presupuesto"
Test 2.4  PRESUPUESTO_MODE with precio_comunicado=True is NOT blocked by new guard
Test 2.5  Existing precio_comunicado guard still fires in PRESUPUESTO_MODE
Test 2.6  Full integration: shared_context carries both precio_comunicado and imagenes_enviadas
"""

from __future__ import annotations

import pytest

from agent.state.conversation_state import transition_mode
from agent.tools.image_tools import (
    enviar_imagenes_ejemplo,
    clear_image_tools_state,
)


def _make_tool_config(state: dict) -> dict:
    """Build a RunnableConfig that passes state to tool via get_tool_state(config)."""
    return {"configurable": {"state": state}}


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
    """Return a minimal PRESUPUESTO_MODE state dict with shared_context populated."""
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
        "shared_context": {
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
    """Return a minimal EXPEDIENTE_MODE state dict with shared_context populated."""
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
        "shared_context": {
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
# Test 2.1 — WS4: shared_context survives PRESUPUESTO → EXPEDIENTE
# ===========================================================================

def test_shared_context_survives_presupuesto_to_expediente():
    """
    After transition_mode(state, "EXPEDIENTE_MODE"), shared_context is NOT
    in the return dict (so merge_dicts preserves it from the checkpoint).

    This is the WS4 replacement for the old get_preserve_keys test.
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=True,
    )

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # shared_context must NOT be in result — merge_dicts preserves it
    assert "shared_context" not in result, (
        "transition_mode() must not overwrite shared_context — "
        "merge_dicts reducer keeps it alive automatically"
    )

    # The old cross-mode keys are NOT in mode_context of the result
    new_ctx = result.get("mode_context")
    if hasattr(new_ctx, "value"):
        ctx_dict = new_ctx.value
    else:
        ctx_dict = dict(new_ctx) if new_ctx else {}

    # mode_context (new empty) must not contain the cross-mode keys
    # (they live in shared_context now)
    assert result["current_mode"] == "EXPEDIENTE_MODE"
    assert result["previous_mode"] == "PRESUPUESTO_MODE"


# ===========================================================================
# Test 2.2 — transition_mode copies precio_comunicado into new context
# ===========================================================================

def test_transition_mode_preserves_precio_comunicado():
    """
    WS4: precio_comunicado now lives in shared_context (not mode_context).
    transition_mode() must NOT touch shared_context, so it's preserved by
    the merge_dicts reducer at the parent graph level.
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=False,
    )

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # shared_context NOT in result means it's preserved by reducer
    assert "shared_context" not in result, (
        "transition_mode must not include shared_context — merge_dicts handles persistence"
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
    the guard must return success=False with guidance referencing
    either 'EXPEDIENTE_MODE' or 'iniciar_expediente'.
    """
    state = _make_expediente_state(
        precio_comunicado=True,
        imagenes_enviadas=True,
    )

    try:
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"},
            config=_make_tool_config(state),
        )
    finally:
        clear_image_tools_state()

    assert result.get("success") is False, (
        f"enviar_imagenes_ejemplo must return success=False when called from "
        f"EXPEDIENTE_MODE with tipo='presupuesto'. Got: {result}"
    )

    message = result.get("message", "")
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
    When in PRESUPUESTO_MODE (NOT EXPEDIENTE_MODE), the EXPEDIENTE_MODE guard
    must NOT fire, even if precio_comunicado=True.
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=False,
        tarifa_calculada=None,  # Will fail later, not at the EXPEDIENTE_MODE guard
    )

    try:
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"},
            config=_make_tool_config(state),
        )
    finally:
        clear_image_tools_state()

    message = result.get("message", "")
    # The EXPEDIENTE_MODE guard-specific phrase must NOT appear
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
    """
    state = _make_presupuesto_state(
        precio_comunicado=False,
        imagenes_enviadas=False,
    )
    # Also clear precio_comunicado from shared_context so the guard sees it
    state["shared_context"]["precio_comunicado"] = False

    try:
        result = await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"},
            config=_make_tool_config(state),
        )
    finally:
        clear_image_tools_state()

    assert result.get("success") is False, (
        f"enviar_imagenes_ejemplo must return success=False when precio_comunicado=False. "
        f"Got: {result}"
    )

    message = result.get("message", "")
    assert "precio" in message.lower(), (
        f"Original precio_comunicado guard message must mention 'precio'. Got: {message!r}"
    )
    assert "EXPEDIENTE_MODE" not in message, (
        f"The old precio_comunicado guard must NOT mention 'EXPEDIENTE_MODE'. "
        f"Got: {message!r}"
    )


# ===========================================================================
# Test 2.6 — Integration: full transition preserves both flags via shared_context
# ===========================================================================

def test_transition_mode_integration_presupuesto_to_expediente():
    """
    WS4 integration test:

    Build a PRESUPUESTO_MODE state with shared_context populated.
    Call transition_mode() and verify shared_context is NOT in the result
    (meaning it will be preserved by merge_dicts at the graph level).
    """
    state = _make_presupuesto_state(
        precio_comunicado=True,
        imagenes_enviadas=True,
        element_codes=["ESCAPE", "SUBCHASIS"],
        tarifa_calculada={"precio": 450.0, "tier": "T2"},
        categoria_slug="motos-part",
    )

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # WS4: shared_context is preserved by merge_dicts, NOT set in result
    assert "shared_context" not in result, (
        "transition_mode must not include shared_context in result — "
        "merge_dicts reducer preserves it automatically"
    )

    # Mode must have transitioned
    assert result["current_mode"] == "EXPEDIENTE_MODE"
    assert result["previous_mode"] == "PRESUPUESTO_MODE"
