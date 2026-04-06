"""
Unit tests: ToolStateUpdate TypedDict contract.

Verifies that:
1. ToolStateUpdate declares all keys that generic_loop.py reads from _internal_flags
   (via _apply_state_updates → _apply_internal_flags).
2. ToolStateUpdate covers the _MODE_CONTEXT_PROPAGATION_KEYS set defined in
   generic_loop.py.
3. The legacy _internal_flags sub-types (PricingFlags, ImageFlags, etc.) are
   subsets of ToolStateUpdate — no key in a sub-type is absent from the union.
4. _apply_state_updates prefers _state_update over _internal_flags.
5. _apply_state_updates logs a deprecation warning when falling back to
   _internal_flags.

No database, Redis, or LLM access — pure static / behavioural tests.
"""

from __future__ import annotations

import inspect
import logging

import pytest

from agent.tools.types import (
    ExpedienteFlags,
    ImageFlags,
    PricingFlags,
    ToolStateUpdate,
    TransitionFlags,
    VariantFlags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _typed_dict_keys(td_cls) -> set[str]:
    """Return the set of field names declared on a TypedDict class."""
    return set(td_cls.__annotations__.keys())


# ---------------------------------------------------------------------------
# T0.2-A: _MODE_CONTEXT_PROPAGATION_KEYS coverage
# ---------------------------------------------------------------------------


class TestModeContextPropagationKeysCoverage:
    """
    generic_loop._MODE_CONTEXT_PROPAGATION_KEYS names keys that are propagated
    into mode_context at the end of each iteration.  All of those keys MUST
    appear in ToolStateUpdate so the typed contract is complete.
    """

    def test_all_propagation_keys_in_tool_state_update(self):
        from agent.modes.generic_loop import _MODE_CONTEXT_PROPAGATION_KEYS

        tsu_keys = _typed_dict_keys(ToolStateUpdate)
        missing = _MODE_CONTEXT_PROPAGATION_KEYS - tsu_keys
        assert not missing, (
            f"ToolStateUpdate is missing keys from _MODE_CONTEXT_PROPAGATION_KEYS: {missing}"
        )


# ---------------------------------------------------------------------------
# T0.2-B: Legacy sub-types ⊆ ToolStateUpdate
# ---------------------------------------------------------------------------


class TestLegacySubtypesCoverage:
    """
    Every key declared in a legacy InternalFlags sub-type must appear in
    ToolStateUpdate (the new canonical contract).
    """

    @pytest.mark.parametrize(
        "sub_type",
        [PricingFlags, ImageFlags, VariantFlags, ExpedienteFlags, TransitionFlags],
        ids=["PricingFlags", "ImageFlags", "VariantFlags", "ExpedienteFlags", "TransitionFlags"],
    )
    def test_sub_type_keys_in_tool_state_update(self, sub_type):
        tsu_keys = _typed_dict_keys(ToolStateUpdate)
        sub_keys = _typed_dict_keys(sub_type)
        missing = sub_keys - tsu_keys
        assert not missing, (
            f"{sub_type.__name__} has keys not in ToolStateUpdate: {missing}"
        )


# ---------------------------------------------------------------------------
# T0.2-C: _transition_to and _chain_next_mode always present
# ---------------------------------------------------------------------------


class TestTransitionKeysPresent:
    """Mode runners rely on _transition_to; it must be in ToolStateUpdate."""

    def test_transition_to_present(self):
        assert "_transition_to" in _typed_dict_keys(ToolStateUpdate)

    def test_chain_next_mode_present(self):
        assert "_chain_next_mode" in _typed_dict_keys(ToolStateUpdate)


# ---------------------------------------------------------------------------
# T0.2-D: Case-collection legacy keys present
# ---------------------------------------------------------------------------


class TestCaseCollectionLegacyKeys:
    """
    case_tools.py and element_data_tools.py return case_collection_update /
    case_collection — these are read by expediente_mode.py and must be
    documented in ToolStateUpdate.
    """

    def test_case_collection_update_present(self):
        assert "case_collection_update" in _typed_dict_keys(ToolStateUpdate)

    def test_case_collection_present(self):
        assert "case_collection" in _typed_dict_keys(ToolStateUpdate)


# ---------------------------------------------------------------------------
# T0.3: _apply_state_updates behaviour tests
# ---------------------------------------------------------------------------


class TestApplyStateUpdates:
    """
    Behavioural tests for generic_loop._apply_state_updates().
    No LLM or DB needed — pure dict manipulation.
    """

    def setup_method(self):
        from agent.modes.generic_loop import _apply_state_updates

        self._fn = _apply_state_updates

    # ── Prefers _state_update over _internal_flags ────────────────────────

    def test_prefers_state_update_channel(self):
        """When both keys are present, _state_update wins."""
        context = {}
        result_dict = {
            "_state_update": {"precio_comunicado": True},
            "_internal_flags": {"precio_comunicado": False},
        }
        self._fn(context, result_dict)
        assert context["precio_comunicado"] is True

    def test_state_update_channel_merges_all_keys(self):
        context = {}
        result_dict = {
            "_state_update": {
                "precio_comunicado": True,
                "imagenes_enviadas": True,
            }
        }
        self._fn(context, result_dict)
        assert context["precio_comunicado"] is True
        assert context["imagenes_enviadas"] is True

    def test_state_update_extracts_transition_to(self):
        """_transition_to must be a top-level key, not buried in _state_update."""
        context = {}
        result_dict = {
            "_state_update": {
                "_transition_to": "EXPEDIENTE_MODE",
                "_chain_next_mode": True,
            }
        }
        self._fn(context, result_dict)
        assert context["_transition_to"] == "EXPEDIENTE_MODE"
        assert context["_chain_next_mode"] is True

    # ── Fallback to _internal_flags ───────────────────────────────────────

    def test_fallback_to_internal_flags(self):
        """When _state_update absent, reads _internal_flags."""
        context = {}
        result_dict = {
            "_internal_flags": {"precio_comunicado": True}
        }
        self._fn(context, result_dict)
        assert context["precio_comunicado"] is True

    def test_internal_flags_transition_preserved(self):
        """_transition_to in _internal_flags must reach context as top-level key."""
        context = {}
        result_dict = {
            "_internal_flags": {
                "_transition_to": "CONSULTA_MODE",
                "extra_flag": "hello",
            }
        }
        self._fn(context, result_dict)
        assert context["_transition_to"] == "CONSULTA_MODE"
        assert context["extra_flag"] == "hello"

    def test_deprecation_warning_logged_for_internal_flags(self, caplog):
        """A DEBUG log entry should appear when _internal_flags fallback is used."""
        with caplog.at_level(logging.DEBUG, logger="agent.modes.generic_loop"):
            context = {}
            result_dict = {"_internal_flags": {"precio_comunicado": True}}
            self._fn(context, result_dict)

        log_text = caplog.text.lower()
        assert "deprecated" in log_text or "internal_flags" in log_text

    # ── No-op scenarios ───────────────────────────────────────────────────

    def test_no_update_key_is_noop(self):
        """When neither key is present, context is unchanged."""
        context = {"existing": 1}
        self._fn(context, {"success": True})
        assert context == {"existing": 1}

    def test_empty_state_update_is_noop(self):
        context = {}
        self._fn(context, {"_state_update": {}})
        assert context == {}

    def test_none_state_update_is_noop(self):
        context = {}
        self._fn(context, {"_state_update": None})
        assert context == {}

    def test_non_dict_state_update_is_noop(self):
        context = {}
        self._fn(context, {"_state_update": "invalid"})
        assert context == {}
