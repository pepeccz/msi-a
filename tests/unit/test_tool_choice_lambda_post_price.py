"""
T1.1 — _should_force_tool_choice truth table (16 combos + log observability).

Spec: POST_PRICE LLM Invocation Contract
  The lambda returns "required" if and only if ALL four conditions hold:
    - precio_comunicado is True
    - tarifa_calculada is a non-None value
    - imagenes_enviadas_codigos is non-empty (at least one element)
    - mode_context["last_cta_emitted"] == "cta_5"
  All other combinations MUST return None.

Design D2: module-level helper _should_force_tool_choice(mc: dict) -> str | None
  in agent/modes/pre_expediente_mode.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Truth-table parametrize
# ---------------------------------------------------------------------------

_TARIFA = {"datos": {"price": 450.0}}
_IMAGES = ["T01"]

_TRUTH_TABLE = [
    # (precio_comunicado, tarifa_calculada, imagenes, last_cta_emitted, expected)
    # Only (T, non-None, non-empty, "cta_5") → "required"
    (True,  _TARIFA, _IMAGES, "cta_5", "required"),
    # All other 15 combos → None
    (False, _TARIFA, _IMAGES, "cta_5", None),        # precio_comunicado=False
    (None,  _TARIFA, _IMAGES, "cta_5", None),        # precio_comunicado=None
    (True,  None,   _IMAGES, "cta_5", None),         # tarifa=None
    (True,  {},     _IMAGES, "cta_5", None),         # tarifa empty dict
    (True,  _TARIFA, [],    "cta_5", None),           # imagenes empty list
    (True,  _TARIFA, None,  "cta_5", None),           # imagenes None
    (True,  _TARIFA, _IMAGES, None,  None),           # last_cta_emitted=None
    (True,  _TARIFA, _IMAGES, "cta_3", None),         # wrong cta value
    (True,  _TARIFA, _IMAGES, "",    None),           # empty string
    (False, None,   [],    None,    None),             # all False
    (True,  None,   _IMAGES, "cta_5", None),          # tarifa None, cta_5 set
    (True,  _TARIFA, [],    "cta_5", None),            # images empty, cta_5 set
    (False, _TARIFA, _IMAGES, None,  None),            # precio false, cta absent
    (True,  _TARIFA, _IMAGES, "cta_4", None),          # adjacent cta value
    (True,  _TARIFA, ["A", "B", "C"], "cta_5", "required"),  # multiple images still required
    # additional edge: tarifa as truthy string (should still work per bool() check)
    (True,  "some_tarifa_string", _IMAGES, "cta_5", "required"),
    # additional edge: imagenes_enviadas_codigos with one empty-string element
    (True,  _TARIFA, [""], "cta_5", "required"),
]


@pytest.mark.parametrize(
    "precio_comunicado,tarifa_calculada,imagenes,last_cta_emitted,expected",
    _TRUTH_TABLE,
    ids=[f"case_{i:02d}" for i in range(len(_TRUTH_TABLE))],
)
def test_should_force_tool_choice_truth_table(
    precio_comunicado: bool | None,
    tarifa_calculada: dict | None,
    imagenes: list | None,
    last_cta_emitted: str | None,
    expected: str | None,
) -> None:
    """
    T1.1 + T1.2 — 18-case truth table for _should_force_tool_choice.

    Only the one combination where ALL 4 conditions hold returns "required".
    """
    from agent.modes.pre_expediente_mode import _should_force_tool_choice

    mc: dict = {
        "precio_comunicado": precio_comunicado,
        "tarifa_calculada": tarifa_calculada,
        "imagenes_enviadas_codigos": imagenes,
        "last_cta_emitted": last_cta_emitted,
    }

    result = _should_force_tool_choice(mc)

    assert result == expected, (
        f"_should_force_tool_choice({mc!r}) → got {result!r}, expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# T1.3 — Observability log emitted
# ---------------------------------------------------------------------------


class TestToolChoiceForcedLogEmitted:
    """T1.3 — When the helper returns 'required', structlog.info must be called."""

    def test_tool_choice_forced_log_emitted(self) -> None:
        """
        T1.3 — GREEN assertion:
        When all 4 conditions are met, structlog.info must be called with
        event='tool_choice_forced_required'.
        """
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mc = {
            "precio_comunicado": True,
            "tarifa_calculada": {"datos": {"price": 450.0}},
            "imagenes_enviadas_codigos": ["T01"],
            "last_cta_emitted": "cta_5",
        }

        mock_logger = MagicMock()
        with patch("agent.modes.pre_expediente_mode.logger", mock_logger):
            result = _should_force_tool_choice(mc)

        assert result == "required"
        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args
        # First positional arg is the event name
        event_name = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("event", "")
        assert event_name == "tool_choice_forced_required", (
            f"Expected log event 'tool_choice_forced_required', got: {event_name!r}"
        )

    def test_no_log_emitted_when_returning_none(self) -> None:
        """Triangulation: when conditions NOT met, logger.info must NOT be called with the event."""
        from agent.modes.pre_expediente_mode import _should_force_tool_choice

        mc = {
            "precio_comunicado": False,
            "tarifa_calculada": {"datos": {"price": 450.0}},
            "imagenes_enviadas_codigos": ["T01"],
            "last_cta_emitted": "cta_5",
        }

        mock_logger = MagicMock()
        with patch("agent.modes.pre_expediente_mode.logger", mock_logger):
            result = _should_force_tool_choice(mc)

        assert result is None
        # info should NOT have been called with tool_choice_forced_required
        for call in mock_logger.info.call_args_list:
            event = call[0][0] if call[0] else ""
            assert event != "tool_choice_forced_required", (
                "logger.info('tool_choice_forced_required') must not be called when returning None"
            )
