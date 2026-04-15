"""
T-08: Tests for enviar_imagenes_ejemplo post_tool_hook code-aware append.

Verifies:
- S13: imagenes_enviadas_codigos appended (not replaced) on success
- S14: existing codes preserved when merging new codes
- bool imagenes_enviadas computed correctly from merged codes
- Empty pending codes → imagenes_enviadas = False, codigos = []
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enviar_result(
    pending_codes: list[str] | None = None,
    success: bool = True,
) -> dict:
    """Build a result dict for enviar_imagenes_ejemplo."""
    return {
        "success": success,
        "message": "OK: 2 imagenes encoladas.",
        "data": {"images_count": 2, "has_follow_up": False},
        "tool_name": "enviar_imagenes_ejemplo",
        "_pending_images": {
            "images": [],
            "delivery_contract": {"version": 1, "delivery_scope": "presupuesto"},
        },
        "_state_update": {
            "shared_context": {
                "imagenes_enviadas": False,
                "imagenes_enviadas_codigos_pending": pending_codes or [],
            },
            "imagenes_envio_intent_creado": True,
            "delivery_intent_created": True,
            "delivery_scope": "presupuesto",
            "delivery_outcome_status": "pending",
            "can_narrate_delivery_success": False,
        },
    }


def _make_hook_state(mode_context: dict | None = None) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_001",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [HumanMessage(content="Envía fotos"), ai_msg],
        "_mode_context": mode_context or {},
        "_conversation_id": "test-conv-001",
    }


# ===========================================================================
# Tests
# ===========================================================================


class TestEnviarImagenesHookCodes:
    """T-08: enviar_imagenes hook appends codes instead of replacing."""

    @pytest.mark.asyncio
    async def test_s13_codes_appended_not_replaced(self):
        """
        S13: When existing codes = ["ESCAPE"] and new pending = ["SUSPENSION"],
        merged result must be ["ESCAPE", "SUSPENSION"] (not just ["SUSPENSION"]).
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        existing_codes = ["ESCAPE"]
        result_dict = _make_enviar_result(pending_codes=["SUSPENSION"])
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": existing_codes})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        merged = sc.get("imagenes_enviadas_codigos", [])
        assert "ESCAPE" in merged, f"Existing code 'ESCAPE' must be preserved, got: {merged}"
        assert "SUSPENSION" in merged, f"New code 'SUSPENSION' must be added, got: {merged}"
        assert len(merged) == 2, f"Should have exactly 2 codes, got: {merged}"

    @pytest.mark.asyncio
    async def test_s14_existing_codes_preserved(self):
        """
        S14: Multiple existing codes are all preserved after merging new codes.
        """
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        existing_codes = ["ESCAPE", "_BASE_DOCS"]
        result_dict = _make_enviar_result(pending_codes=["SUSPENSION"])
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": existing_codes})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        merged = sc.get("imagenes_enviadas_codigos", [])
        for code in ["ESCAPE", "_BASE_DOCS", "SUSPENSION"]:
            assert code in merged, f"Code '{code}' must be in merged list, got: {merged}"

    @pytest.mark.asyncio
    async def test_dedup_same_code_not_duplicated(self):
        """If pending code already exists in existing, it must not be duplicated."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        existing_codes = ["ESCAPE"]
        result_dict = _make_enviar_result(pending_codes=["ESCAPE"])  # same code
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": existing_codes})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        merged = sc.get("imagenes_enviadas_codigos", [])
        escape_count = merged.count("ESCAPE")
        assert escape_count == 1, f"ESCAPE must appear exactly once, got count={escape_count} in {merged}"

    @pytest.mark.asyncio
    async def test_bool_computed_from_merged_codes(self):
        """imagenes_enviadas bool must be True when merged codes is non-empty."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _make_enviar_result(pending_codes=["ESCAPE"])
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": []})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        assert sc.get("imagenes_enviadas") is True, (
            f"imagenes_enviadas must be True when merged codes non-empty, got: {sc.get('imagenes_enviadas')}"
        )

    @pytest.mark.asyncio
    async def test_bool_false_when_no_codes(self):
        """imagenes_enviadas bool must be False when no codes (pending + existing = empty)."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _make_enviar_result(pending_codes=[])
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": []})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        assert sc.get("imagenes_enviadas") is False, (
            f"imagenes_enviadas must be False when no codes, got: {sc.get('imagenes_enviadas')}"
        )

    @pytest.mark.asyncio
    async def test_error_result_no_codes_written(self):
        """On error result, imagenes_enviadas_codigos must NOT be written."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = {"success": False, "message": "Error: no tarifa", "data": None}
        state = _make_hook_state(mode_context={"imagenes_enviadas_codigos": ["ESCAPE"]})

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        # On error, we must NOT overwrite existing codes
        assert "imagenes_enviadas_codigos" not in sc, (
            "On error, imagenes_enviadas_codigos must NOT be written to shared_context"
        )

    @pytest.mark.asyncio
    async def test_first_send_no_existing_codes(self):
        """First send (no existing codes) — pending codes become the new list."""
        from agent.modes.post_tool_hooks import presupuesto_post_tool_hook

        result_dict = _make_enviar_result(pending_codes=["ESCAPE", "_BASE_DOCS"])
        state = _make_hook_state(mode_context={})  # no existing codes

        updates = await presupuesto_post_tool_hook(
            "enviar_imagenes_ejemplo", result_dict, state
        )

        sc = updates.get("shared_context", {})
        merged = sc.get("imagenes_enviadas_codigos", [])
        assert "ESCAPE" in merged
        assert "_BASE_DOCS" in merged
        assert sc.get("imagenes_enviadas") is True
