"""
T1.1 — 16-case truth table for _should_force_tool_choice helper.

Spec coverage:
  - Requirement: POST_PRICE LLM Invocation Contract
  - ONLY the (True, non-None, non-empty, "cta_5") combination → "required"
  - All other 15 combinations → None

Design reference: D2 — Lambda location in pre_expediente_mode.py
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Truth-table helpers
# ---------------------------------------------------------------------------

def _mc(
    precio_comunicado: bool | None,
    tarifa_calculada: dict | None,
    imagenes_enviadas_codigos: list | None,
    last_cta_emitted: str | None,
) -> dict:
    """Build a minimal mode_context dict for lambda evaluation."""
    mc: dict = {}
    if precio_comunicado is not None:
        mc["precio_comunicado"] = precio_comunicado
    if tarifa_calculada is not None:
        mc["tarifa_calculada"] = tarifa_calculada
    if imagenes_enviadas_codigos is not None:
        mc["imagenes_enviadas_codigos"] = imagenes_enviadas_codigos
    if last_cta_emitted is not None:
        mc["last_cta_emitted"] = last_cta_emitted
    return mc


# Truth-table: (precio_comunicado, tarifa, imagenes, last_cta, expected)
# Only one row → "required"; all others → None
_TRUTH_TABLE = [
    # --- The one "required" case ---
    (True, {"datos": {"price": 100}}, ["T01"], "cta_5", "required"),
    # --- precio_comunicado False/absent ---
    (False, {"datos": {"price": 100}}, ["T01"], "cta_5", None),
    (None, {"datos": {"price": 100}}, ["T01"], "cta_5", None),
    # --- tarifa_calculada falsy ---
    (True, None, ["T01"], "cta_5", None),
    (True, {}, ["T01"], "cta_5", None),
    # --- imagenes_enviadas_codigos empty/absent ---
    (True, {"datos": {"price": 100}}, [], "cta_5", None),
    (True, {"datos": {"price": 100}}, None, "cta_5", None),
    # --- last_cta_emitted wrong/absent ---
    (True, {"datos": {"price": 100}}, ["T01"], None, None),
    (True, {"datos": {"price": 100}}, ["T01"], "other_cta", None),
    (True, {"datos": {"price": 100}}, ["T01"], "", None),
    # --- Multiple conditions False ---
    (False, None, [], None, None),
    (False, None, ["T01"], "cta_5", None),
    (False, {"datos": {"price": 100}}, [], "cta_5", None),
    (True, None, ["T01"], None, None),
    (True, {"datos": {"price": 100}}, [], None, None),
    (False, None, [], "cta_5", None),
]


class TestShouldForceToolChoice:
    """16-case truth table for _should_force_tool_choice."""

    @pytest.mark.parametrize(
        "precio_comunicado,tarifa_calculada,imagenes,last_cta,expected",
        _TRUTH_TABLE,
        ids=[
            "all_true_required",
            "precio_false",
            "precio_absent",
            "tarifa_none",
            "tarifa_empty",
            "imagenes_empty",
            "imagenes_none",
            "last_cta_none",
            "last_cta_other",
            "last_cta_empty_string",
            "all_false",
            "precio_false_tarifa_none",
            "precio_false_imagenes_empty",
            "precio_true_tarifa_none_cta_none",
            "precio_true_imagenes_empty_cta_none",
            "precio_false_tarifa_none_imagenes_empty",
        ],
    )
    def test_truth_table(
        self,
        precio_comunicado,
        tarifa_calculada,
        imagenes,
        last_cta,
        expected,
    ):
        """
        _should_force_tool_choice must return 'required' IFF all 4 conditions hold.
        All other 15 combinations must return None.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mc = _mc(precio_comunicado, tarifa_calculada, imagenes, last_cta)
        result = _should_force_tool_choice(mc)
        assert result == expected, (
            f"Expected {expected!r} for "
            f"(precio={precio_comunicado}, tarifa={bool(tarifa_calculada)}, "
            f"imagenes={imagenes!r}, last_cta={last_cta!r}), "
            f"got {result!r}"
        )


class TestToolChoiceForcedLogEmitted:
    """T1.3 — Observability: INFO log emitted when returning 'required'."""

    def test_tool_choice_forced_log_emitted(self):
        """
        When _should_force_tool_choice returns 'required',
        it must emit a structlog INFO event 'tool_choice_forced_required'.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mock_logger = MagicMock()
        with patch("agent.modes.pre_expediente_mode.logger", mock_logger):
            mc = _mc(True, {"datos": {"price": 100}}, ["T01"], "cta_5")
            result = _should_force_tool_choice(mc)

        assert result == "required"
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        # First positional arg is the event name
        assert call_args[0][0] == "tool_choice_forced_required", (
            f"Expected event 'tool_choice_forced_required', got {call_args[0][0]!r}"
        )

    def test_tool_choice_no_log_when_not_required(self):
        """
        When _should_force_tool_choice returns None,
        no INFO log should be emitted (avoid noise on every non-CTA-5 turn).
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mock_logger = MagicMock()
        with patch("agent.modes.pre_expediente_mode.logger", mock_logger):
            mc = _mc(False, None, [], None)
            result = _should_force_tool_choice(mc)

        assert result is None
        mock_logger.info.assert_not_called()
