"""
Tests for auto-emission of review_summary when the last collection section
completes within a single turn (spec escenario 9 + reglas duras 11 y 12).

Anti-pattern (escenario 9.bis): the LLM emits a promise ("En el siguiente
mensaje te muestro el resumen...") instead of the actual summary.

Expected behaviour: when one of actualizar_datos_personales |
actualizar_datos_vehiculo | actualizar_datos_taller returns success AND with
that success the trio (personal + vehicle + workshop-or-skipped) is fully
closed, the ai_response of THAT SAME TURN must be the full review_summary
content — not a promise.

Scope:
- _trio_complete helper (pure function)
- _auto_emit_review_summary helper (async, calls review_summary_node)
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Pre-patch structlog and langgraph.checkpoint.redis before agent imports
# ---------------------------------------------------------------------------

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

for _redis_mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _redis_mod not in sys.modules:
        _stub = types.ModuleType(_redis_mod)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod] = _stub

import pytest

import agent.modes.expediente_nodes as _enodes_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_expediente_state(
    *,
    personal_collected: bool = False,
    vehicle_collected: bool = False,
    workshop_collected: bool = False,
    taller_propio: bool | None = None,
    sub_mode: str = "collect_workshop",
    ai_response: str = "",
    **extra: Any,
) -> dict:
    """Build a minimal ExpedienteState-like dict."""
    return {
        "case_id": "case-abc",
        "conversation_id": "conv-123",
        "expediente_sub_mode": sub_mode,
        "user_message": "listo con el taller",
        "element_phase": None,
        "current_element_code": None,
        "element_data_status": {},
        "personal_collected": personal_collected,
        "vehicle_collected": vehicle_collected,
        "workshop_collected": workshop_collected,
        "taller_propio": taller_propio,
        "messages": [],
        "ai_response": ai_response,
        "pending_images": None,
        **extra,
    }


# ---------------------------------------------------------------------------
# _trio_complete helper
# ---------------------------------------------------------------------------


class TestTrioComplete:
    """_trio_complete must return True iff all 3 sections are done."""

    def test_all_true_returns_true(self):
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "personal_collected": True,
            "vehicle_collected": True,
            "workshop_collected": True,
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=True,
        )
        assert _trio_complete(update, state) is True

    def test_missing_vehicle_returns_false(self):
        from agent.modes.expediente_nodes import _trio_complete

        update = {"personal_collected": True, "workshop_collected": True}
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=False,
            workshop_collected=True,
        )
        assert _trio_complete(update, state) is False

    def test_workshop_skipped_via_taller_propio_false(self):
        """workshop_collected may be False when taller_propio=False — still complete."""
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "personal_collected": True,
            "vehicle_collected": True,
            # workshop_collected NOT in update — state has False
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,
            taller_propio=False,
        )
        assert _trio_complete(update, state) is True

    def test_workshop_skipped_and_update_has_workshop_false(self):
        """update has workshop_collected=False but taller_propio=False → complete."""
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "personal_collected": True,
            "vehicle_collected": True,
            "workshop_collected": False,
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,
            taller_propio=False,
        )
        assert _trio_complete(update, state) is True

    def test_none_collected_returns_false(self):
        from agent.modes.expediente_nodes import _trio_complete

        update = {}
        state = _make_expediente_state()
        assert _trio_complete(update, state) is False

    def test_only_personal_done_returns_false(self):
        from agent.modes.expediente_nodes import _trio_complete

        update = {"personal_collected": True}
        state = _make_expediente_state(personal_collected=True)
        assert _trio_complete(update, state) is False

    def test_update_overrides_state_flags(self):
        """
        update dict wins over state when deciding flags.
        State might have workshop_collected=False but update has True.
        """
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "personal_collected": True,
            "vehicle_collected": True,
            "workshop_collected": True,
        }
        state = _make_expediente_state(
            personal_collected=False,  # stale state
            vehicle_collected=False,
            workshop_collected=False,
        )
        assert _trio_complete(update, state) is True


# ---------------------------------------------------------------------------
# _auto_emit_review_summary — direct unit tests
# ---------------------------------------------------------------------------


class TestAutoEmitReviewSummary:
    """
    _auto_emit_review_summary must:
    1. Call review_summary_node with a state that has sub_mode=review_summary
       and all completion flags set.
    2. Merge the review Command.update into the update dict (ai_response wins).
    3. On failure, return update unchanged (fail-open).
    """

    @pytest.mark.asyncio
    async def test_case1_taller_closes_trio_gets_summary_not_promise(self):
        """
        Case 1 (spec escenario 9): turno donde actualizar_datos_taller cierra el
        trío (personal + vehicle already done) → ai_response es el resumen de
        review_summary, NO una promesa. sub_mode == review_summary al final.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        review_text = "RESUMEN REAL: Datos personales ✓, Vehículo ✓, Taller ✓"

        fake_review_cmd = MagicMock()
        fake_review_cmd.update = {
            "ai_response": review_text,
            "exit_reason": "response",
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
        }
        fake_review_node = AsyncMock(return_value=fake_review_cmd)

        # update reflects: workshop just completed, sub_mode → review_summary
        update = {
            "workshop_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": "En el siguiente mensaje te muestro el resumen.",  # LLM promise
            "exit_reason": "response",
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,  # not yet in state — just set in update
            taller_propio=None,
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
        )

        with patch("agent.modes.expediente_nodes.review_summary_node", fake_review_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
                conversation_id="conv-123",
            )

        # The final ai_response MUST be the summary, not the promise
        assert result["ai_response"] == review_text, (
            f"Expected review summary, got: {result['ai_response']!r}"
        )
        # sub_mode must be review_summary
        assert result.get("expediente_sub_mode") == CollectionStep.REVIEW_SUMMARY.value
        # review_summary_node was called
        fake_review_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_case2_vehicle_closes_trio_workshop_skipped(self):
        """
        Case 2: taller_propio=False (workshop skipped) and actualizar_datos_vehiculo
        closes the trio → same invariant: ai_response is the real summary.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        review_text = "RESUMEN: Personal ✓, Vehículo ✓ (Sin taller propio)"

        fake_review_cmd = MagicMock()
        fake_review_cmd.update = {
            "ai_response": review_text,
            "exit_reason": "response",
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
        }
        fake_review_node = AsyncMock(return_value=fake_review_cmd)

        update = {
            "vehicle_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": "Ahora te preparo el resumen...",  # LLM promise
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=False,
            workshop_collected=False,
            taller_propio=False,  # workshop skipped
            sub_mode=CollectionStep.COLLECT_VEHICLE.value,
        )

        with patch("agent.modes.expediente_nodes.review_summary_node", fake_review_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_VEHICLE",
                conversation_id="conv-123",
            )

        assert result["ai_response"] == review_text
        assert result.get("expediente_sub_mode") == CollectionStep.REVIEW_SUMMARY.value
        fake_review_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_case4_antipattern_promise_is_replaced_by_summary(self):
        """
        Case 4 (escenario 9.bis anti-pattern): the LLM intentionally emits a
        promise string. The routing determinism must override it with the real
        summary when the trio is complete.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        # Classic anti-pattern strings from the spec
        llm_promise = "En el siguiente mensaje te muestro el resumen completo."
        review_text = "📋 RESUMEN FINAL DE TU EXPEDIENTE — confirme para enviar a revisión."

        fake_review_cmd = MagicMock()
        fake_review_cmd.update = {
            "ai_response": review_text,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
        }
        fake_review_node = AsyncMock(return_value=fake_review_cmd)

        update = {
            "workshop_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": llm_promise,
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,
            taller_propio=None,
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
        )

        with patch("agent.modes.expediente_nodes.review_summary_node", fake_review_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
                conversation_id="conv-123",
            )

        # Promise MUST be replaced
        assert result["ai_response"] != llm_promise, (
            "Promise leaked through — auto-emit failed to override it"
        )
        assert result["ai_response"] == review_text
        fake_review_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_summary_called_with_updated_state(self):
        """
        When review_summary_node is auto-invoked, it must receive a state dict
        that has the completion flags already set (personal_collected=True, etc.)
        and expediente_sub_mode=review_summary.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        captured_state: dict = {}

        async def _capturing_review_node(state: dict, config: Any = None) -> MagicMock:
            captured_state.update(state)
            cmd = MagicMock()
            cmd.update = {
                "ai_response": "Resumen capturado",
                "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            }
            return cmd

        update = {
            "workshop_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": "Dame un segundo...",
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,
            taller_propio=None,
            sub_mode=CollectionStep.COLLECT_WORKSHOP.value,
        )

        with patch("agent.modes.expediente_nodes.review_summary_node", _capturing_review_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
                conversation_id="conv-123",
            )

        # The state passed to review_summary_node should have all flags True
        assert captured_state.get("personal_collected") is True
        assert captured_state.get("vehicle_collected") is True
        assert captured_state.get("workshop_collected") is True
        assert captured_state.get("expediente_sub_mode") == CollectionStep.REVIEW_SUMMARY.value
        assert result["ai_response"] == "Resumen capturado"

    @pytest.mark.asyncio
    async def test_fail_open_on_review_node_exception(self):
        """
        When review_summary_node raises, _auto_emit_review_summary returns
        the update unchanged (fail-open) so the next turn can retry.
        """
        from agent.modes.expediente_nodes import _auto_emit_review_summary
        from agent.utils.expediente_types import CollectionStep

        failing_review_node = AsyncMock(side_effect=RuntimeError("DB down"))

        update = {
            "workshop_collected": True,
            "expediente_sub_mode": CollectionStep.REVIEW_SUMMARY.value,
            "ai_response": "Comprendido, procesando...",
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=True,
            workshop_collected=False,
        )

        with patch("agent.modes.expediente_nodes.review_summary_node", failing_review_node):
            result = await _auto_emit_review_summary(
                update=update,
                state=state,
                mode_name="EXPEDIENTE_COLLECT_WORKSHOP",
                conversation_id="conv-123",
            )

        # Fail-open: update is unchanged
        assert result == update


# ---------------------------------------------------------------------------
# Case 3: trio NOT complete → _auto_emit_review_summary must NOT be called
# ---------------------------------------------------------------------------


class TestNoAutoEmitWhenTrioIncomplete:
    """
    When the trio is NOT complete (only one or two sections done),
    _auto_emit_review_summary must not be reached.
    This is verified by _trio_complete returning False.
    """

    def test_case3_only_personal_trio_not_complete(self):
        """
        Case 3: only personal done, vehicle + workshop still pending →
        _trio_complete returns False → no auto-emit.
        """
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "personal_collected": True,
            "expediente_sub_mode": "collect_vehicle",
        }
        state = _make_expediente_state(
            personal_collected=False,
            vehicle_collected=False,
            workshop_collected=False,
        )
        # Guard: if trio is NOT complete, auto-emit is skipped
        assert _trio_complete(update, state) is False

    def test_case3_personal_and_vehicle_but_no_workshop(self):
        """
        personal + vehicle done but workshop pending and taller_propio=True →
        trio incomplete.
        """
        from agent.modes.expediente_nodes import _trio_complete

        update = {
            "vehicle_collected": True,
            "expediente_sub_mode": "collect_workshop",
        }
        state = _make_expediente_state(
            personal_collected=True,
            vehicle_collected=False,
            workshop_collected=False,
            taller_propio=True,  # has workshop, not skipped
        )
        assert _trio_complete(update, state) is False
