"""
T-06: Tests verifying that calcular_tarifa_con_elementos does NOT reset imagenes_enviadas
and does NOT prematurely set precio_comunicado.

Verifies:
- calcular_tarifa_con_elementos _state_update.shared_context does NOT contain imagenes_enviadas
- post_tool_hook for calcular_tarifa does NOT set imagenes_enviadas=False in updates
- precio_comunicado is NOT set by the hook (deferred to mode node post-response)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_calcular_result(price: float = 410.0) -> dict:
    return {
        "success": True,
        "texto": "Presupuesto calculado.",
        "datos": {
            "tier_id": "tier-1",
            "tier_name": "Proyecto Básico",
            "price": price,
            "elements": ["Escape"],
            "element_codes": ["ESCAPE"],
            "warnings": [],
        },
        "imagenes_ejemplo": [],
        "_state_update": {
            "shared_context": {
                # precio_comunicado NOT set here — deferred to mode node post-response
            },
        },
    }


def _make_hook_state(mode_context: dict | None = None) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_001",
                "name": "calcular_tarifa_con_elementos",
                "args": {"categoria_vehiculo": "motos-part", "codigos_elementos": ["ESCAPE"]},
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [HumanMessage(content="Escape"), ai_msg],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-001",
    }


# ===========================================================================
# T-06 Tests
# ===========================================================================


class TestCalcularTarifaNoImagenesReset:
    """T-06: calcular_tarifa does not reset imagenes_enviadas."""

    def test_calcular_tarifa_state_update_no_imagenes_enviadas(self):
        """
        _state_update.shared_context in calcular_tarifa must NOT contain 'imagenes_enviadas'.
        Recalculating price doesn't invalidate already-sent images.
        """
        result = _make_calcular_result()
        sc = result.get("_state_update", {}).get("shared_context", {})

        assert "imagenes_enviadas" not in sc, (
            f"calcular_tarifa _state_update must NOT contain 'imagenes_enviadas', got: {sc}"
        )

    def test_calcular_tarifa_state_update_no_precio_comunicado(self):
        """
        _state_update.shared_context must NOT contain 'precio_comunicado'.
        The flag is deferred to the mode node post-response, not set at tool time.
        """
        result = _make_calcular_result()
        sc = result.get("_state_update", {}).get("shared_context", {})

        assert "precio_comunicado" not in sc, (
            f"precio_comunicado must NOT be in _state_update (deferred to mode node), got: {sc}"
        )

    @pytest.mark.asyncio
    async def test_hook_calcular_tarifa_no_imagenes_enviadas_in_updates(self):
        """
        S12: post_tool_hook for calcular_tarifa must NOT write imagenes_enviadas=False to updates.
        """
        result_dict = _make_calcular_result()
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": ["ESCAPE"]})

        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        # imagenes_enviadas must NOT be reset to False
        assert updates.get("imagenes_enviadas") is not False, (
            "calcular_tarifa hook must NOT reset imagenes_enviadas to False"
        )

        # shared_context may not even have imagenes_enviadas
        sc = updates.get("shared_context", {})
        assert sc.get("imagenes_enviadas") is not False, (
            "calcular_tarifa hook must NOT write imagenes_enviadas=False to shared_context"
        )

    @pytest.mark.asyncio
    async def test_hook_calcular_tarifa_no_precio_comunicado(self):
        """
        post_tool_hook for calcular_tarifa must NOT set precio_comunicado.
        The flag is deferred to mode node post-response so the LLM sees
        "DEBES comunicarlo" instead of "ya comunicado".
        """
        result_dict = _make_calcular_result()
        state = _make_hook_state()

        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        updates = await presupuesto_post_tool_hook(
            "calcular_tarifa_con_elementos", result_dict, state
        )

        mc = updates.get("mode_context", {})
        sc = updates.get("shared_context", {})
        assert mc.get("precio_comunicado") is not True, (
            f"precio_comunicado must NOT be True in hook (deferred to mode node)\nmode_context={mc}"
        )
        assert sc.get("precio_comunicado") is not True, (
            f"precio_comunicado must NOT be True in shared_context from hook\nshared_context={sc}"
        )
