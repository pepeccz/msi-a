"""
Tests for root-expediente-ux fixes.

Fix A: Code-driven kickoff confirmation
  - confirmar_presupuesto returns expediente_kickoff_pending: True
  - expediente_mode injects "Perfecto, abrimos el expediente." prefix (via hook output)

Fix B: Warning state tracking
  - post_tool_hook extracts warning codes after calcular_tarifa
  - format_mode_context shows warnings in EXPEDIENTE_MODE and PRE_EXPEDIENTE_MODE
  - identificar_y_resolver_elementos resets advertencias_comunicadas

All tests are pure unit tests — no DB, no Redis, no LLM, no network.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook_state(
    tool_name: str,
    tool_args: dict,
    mode_context: dict | None = None,
) -> dict:
    """Build a minimal hook state dict as passed by post_tool_node."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_001",
                "name": tool_name,
                "args": tool_args,
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [ai_msg],
        "_mode_context": mode_context or {},
        "_conversation_id": "conv_test",
        "pending_state_updates": {},
    }


# ===========================================================================
# Fix A — confirmar_presupuesto returns expediente_kickoff_pending
# ===========================================================================


class TestConfirmarPresupuestoKickoffFlag:
    """A1: confirmar_presupuesto must include expediente_kickoff_pending: True."""

    @pytest.mark.asyncio
    async def test_kickoff_pending_in_state_update(self):
        """confirmar_presupuesto._state_update contains expediente_kickoff_pending=True."""
        from agent.state.helpers import get_tool_state

        mock_state = {
            "conversation_id": "conv_test",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {"datos": {"price": 410}},
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "furgonetas-part",
            },
        }

        with patch("agent.tools.transition_tools.get_tool_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto

            result = await confirmar_presupuesto.ainvoke({})

        assert result["success"] is True
        state_update = result.get("_state_update", {})
        assert state_update.get("expediente_kickoff_pending") is True, (
            "confirmar_presupuesto must set expediente_kickoff_pending=True in _state_update"
        )

    @pytest.mark.asyncio
    async def test_transition_still_present(self):
        """_transition_to: EXPEDIENTE_MODE must still be in _state_update."""
        mock_state = {
            "conversation_id": "conv_test",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {"datos": {"price": 410}},
                "element_codes": ["SUBCHASIS"],
                "categoria_slug": "furgonetas-part",
            },
        }

        with patch("agent.tools.transition_tools.get_tool_state", return_value=mock_state):
            from agent.tools.transition_tools import confirmar_presupuesto

            result = await confirmar_presupuesto.ainvoke({})

        assert result["_state_update"]["_transition_to"] == "EXPEDIENTE_MODE"


# ===========================================================================
# Fix B — Warning code extraction in post_tool_hook
# ===========================================================================


class TestPostToolHookWarningExtraction:
    """B1: pre_expediente_post_tool_hook extracts warning codes after calcular_tarifa."""

    @pytest.mark.asyncio
    async def test_warnings_extracted_from_calcular_tarifa(self):
        """Warnings list → advertencias_comunicadas in mode_context."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [
                {"code": "SUBCHASIS_REQUIRES_SPECIALIST", "message": "Requiere especialista"},
                {"code": "CERT_REQUIRED", "message": "Certificado requerido"},
            ],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
            mode_context={"precio_comunicado": False},
        )

        # Patch at source module (imported locally inside hook function)
        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert "advertencias_comunicadas" in mc, "advertencias_comunicadas must be in mode_context"
        adv = mc["advertencias_comunicadas"]
        assert "SUBCHASIS_REQUIRES_SPECIALIST" in adv
        assert "CERT_REQUIRED" in adv

    @pytest.mark.asyncio
    async def test_warnings_also_in_shared_context(self):
        """Warning codes must also be propagated to shared_context."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [
                {"code": "CERT_REQUIRED", "message": "Certificado requerido"},
            ],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
            mode_context={"precio_comunicado": False},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        sc = updates.get("shared_context", {})
        assert "advertencias_comunicadas" in sc, "advertencias_comunicadas must be in shared_context"

    @pytest.mark.asyncio
    async def test_no_warnings_no_key_injected(self):
        """If no warnings, advertencias_comunicadas is not injected."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "datos": {"price": 410},
            "warnings": [],
        }
        state = _make_hook_state(
            "calcular_tarifa_con_elementos",
            {"element_codes": ["SUBCHASIS"]},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(return_value={})
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "calcular_tarifa_con_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert mc.get("advertencias_comunicadas") is None or "advertencias_comunicadas" not in mc

    @pytest.mark.asyncio
    async def test_identificar_resets_advertencias(self):
        """identificar_y_resolver_elementos resets advertencias_comunicadas to []."""
        from agent.modes.post_tool_hooks import pre_expediente_post_tool_hook

        result_dict = {
            "success": True,
            "element_codes": ["TOLDO_GALIBO"],
            "elementos_confirmados": [{"code": "TOLDO_GALIBO"}],
        }
        state = _make_hook_state(
            "identificar_y_resolver_elementos",
            {"descripcion": "toldo galibo"},
            mode_context={"advertencias_comunicadas": ["CERT_REQUIRED"]},
        )

        mock_node = MagicMock()
        mock_node._extract_context_from_tool = MagicMock(
            return_value={"element_codes": ["TOLDO_GALIBO"]}
        )
        with patch(
            "agent.modes.pre_expediente_mode.PreExpedienteModeNode",
            mock_node,
        ):
            updates = await pre_expediente_post_tool_hook(
                "identificar_y_resolver_elementos", result_dict, state
            )

        mc = updates.get("mode_context", {})
        assert mc.get("advertencias_comunicadas") == [], (
            "advertencias_comunicadas must be reset to [] when identificar changes elements"
        )


# ===========================================================================
# Fix B — format_mode_context injects warning list
# ===========================================================================


class TestFormatModeContextWarnings:
    """B2: format_mode_context shows advertencias_comunicadas in EXPEDIENTE and PRE_EXPEDIENTE."""

    def test_expediente_mode_shows_warnings(self):
        """EXPEDIENTE_MODE: advertencias_comunicadas appears in context string."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "advertencias_comunicadas": ["SUBCHASIS_REQUIRES_SPECIALIST", "CERT_REQUIRED"],
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" in result, (
            "format_mode_context must inject advertencias_comunicadas in EXPEDIENTE_MODE"
        )
        assert "SUBCHASIS_REQUIRES_SPECIALIST" in result
        assert "CERT_REQUIRED" in result

    def test_pre_expediente_mode_shows_warnings(self):
        """PRE_EXPEDIENTE_MODE: advertencias_comunicadas appears in context string."""
        from agent.prompts.loader import format_mode_context

        context = {
            "precio_comunicado": True,
            "element_codes": ["SUBCHASIS"],
            "categoria_slug": "furgonetas-part",
            "advertencias_comunicadas": ["CERT_REQUIRED"],
        }
        result = format_mode_context("PRE_EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" in result, (
            "format_mode_context must inject advertencias_comunicadas in PRE_EXPEDIENTE_MODE"
        )
        assert "CERT_REQUIRED" in result

    def test_empty_warnings_not_shown(self):
        """Empty advertencias_comunicadas list → no injection."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
            "advertencias_comunicadas": [],
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" not in result

    def test_missing_warnings_not_shown(self):
        """advertencias_comunicadas absent → no injection."""
        from agent.prompts.loader import format_mode_context

        context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["SUBCHASIS"],
            "current_element_index": 0,
            "element_phase": "photos",
        }
        result = format_mode_context("EXPEDIENTE_MODE", context)

        assert "Advertencias YA comunicadas" not in result


# ===========================================================================
# Fix A — expediente_kickoff_pending registered in key sets
# ===========================================================================


class TestKeyRegistration:
    """A3/B3: Both new keys must appear in canonical key sets."""

    def test_kickoff_pending_in_canonical_keys(self):
        """expediente_kickoff_pending must be in CANONICAL_MODE_CONTEXT_KEYS."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "expediente_kickoff_pending" in CANONICAL_MODE_CONTEXT_KEYS

    def test_advertencias_comunicadas_in_canonical_keys(self):
        """advertencias_comunicadas must be in CANONICAL_MODE_CONTEXT_KEYS."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "advertencias_comunicadas" in CANONICAL_MODE_CONTEXT_KEYS

    def test_kickoff_pending_in_expediente_mc_keys(self):
        """expediente_kickoff_pending must be in _EXPEDIENTE_MC_KEYS (survives boundary)."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "expediente_kickoff_pending" in _EXPEDIENTE_MC_KEYS

    def test_advertencias_comunicadas_in_expediente_mc_keys(self):
        """advertencias_comunicadas must be in _EXPEDIENTE_MC_KEYS (survives boundary)."""
        from agent.modes.expediente_state import _EXPEDIENTE_MC_KEYS

        assert "advertencias_comunicadas" in _EXPEDIENTE_MC_KEYS
