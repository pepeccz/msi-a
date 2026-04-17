"""
T4 — Concern D3: pending_outbound_messages channel dispatch.

Spec: PendingOutboundMessagesChannel
  Tests _build_intro_emission and _build_intro_emission_from_state shape
  when using the dedicated pending_outbound_messages state field (D3).

Strategy:
  - Unit-test _build_intro_emission for the correct output shape
  - Both helpers must populate pending_outbound_messages[] instead of messages[]
  - Tombstone flags must be set atomically in the same dict
  - Idempotency: second call (expediente_intro_sent=True) returns {}
"""

from __future__ import annotations

import pytest

from agent.modes.expediente_nodes import (
    _build_intro_emission,
    _build_intro_emission_from_state,
)


# ---------------------------------------------------------------------------
# Tests — _build_intro_emission (D3 shape)
# ---------------------------------------------------------------------------


class TestBuildIntroEmissionD3:
    """
    _build_intro_emission must populate pending_outbound_messages, NOT messages[].
    Tombstone flags (expediente_intro_sent=True, expediente_intro_message=None)
    must be in the same returned dict.
    """

    def test_populates_pending_outbound_messages(self):
        """
        When expediente_intro_sent is False and expediente_intro_message is set,
        the returned dict must contain pending_outbound_messages=[intro_text].
        """
        update: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Bienvenido al expediente",
        }
        result = _build_intro_emission(update)

        assert "pending_outbound_messages" in result
        assert result["pending_outbound_messages"] == ["Bienvenido al expediente"]

    def test_does_not_append_to_messages_list(self):
        """
        D3 contract: AIMessage must NOT be appended to messages[].
        """
        update: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Intro text",
        }
        result = _build_intro_emission(update)

        # messages key must not be present (or must be empty if it was already there)
        messages = result.get("messages", [])
        assert messages == [], f"messages[] must be empty in D3, got: {messages}"

    def test_tombstone_flags_set_atomically(self):
        """
        expediente_intro_sent=True and expediente_intro_message=None
        must be in the same returned dict as pending_outbound_messages.
        """
        update: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Hello",
        }
        result = _build_intro_emission(update)

        assert result.get("expediente_intro_sent") is True
        assert result.get("expediente_intro_message") is None

    def test_idempotent_when_already_sent(self):
        """
        If expediente_intro_sent is already True, return {} (no-op).
        No pending_outbound_messages, no tombstone mutation.
        """
        update: dict = {
            "expediente_intro_sent": True,
            "expediente_intro_message": "Should be ignored",
        }
        result = _build_intro_emission(update)

        assert result.get("pending_outbound_messages") is None or result.get("pending_outbound_messages") == []
        # No message should be emitted
        assert "pending_outbound_messages" not in result or result["pending_outbound_messages"] == []

    def test_no_op_when_no_intro_message(self):
        """
        If expediente_intro_message is absent/None, do nothing (no emission).
        """
        update: dict = {"expediente_intro_sent": False}
        result = _build_intro_emission(update)

        assert result.get("pending_outbound_messages") is None or result.get("pending_outbound_messages") == []

    def test_full_dict_shape(self):
        """
        Full shape assertion: all three keys must coexist in result.
        """
        intro_text = "Vamos a recopilar los datos de tu expediente."
        update: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": intro_text,
        }
        result = _build_intro_emission(update)

        assert result["pending_outbound_messages"] == [intro_text]
        assert result["expediente_intro_sent"] is True
        assert result["expediente_intro_message"] is None


# ---------------------------------------------------------------------------
# Tests — _build_intro_emission_from_state (D3 shape)
# ---------------------------------------------------------------------------


class TestBuildIntroEmissionFromStateD3:
    """
    _build_intro_emission_from_state follows the same D3 contract but reads
    intro fields from state when absent from update (resumed-expediente path).
    """

    def test_reads_from_state_when_absent_from_update(self):
        """
        When expediente_intro_message is not in update but is in state,
        must still emit pending_outbound_messages.
        """
        update: dict = {}
        state: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "From state",
        }
        result = _build_intro_emission_from_state(update, state)

        assert result["pending_outbound_messages"] == ["From state"]
        assert result["expediente_intro_sent"] is True
        assert result["expediente_intro_message"] is None

    def test_idempotent_when_state_already_sent(self):
        """
        If state has expediente_intro_sent=True, no emission should occur.
        """
        update: dict = {}
        state: dict = {
            "expediente_intro_sent": True,
            "expediente_intro_message": "Should be ignored",
        }
        result = _build_intro_emission_from_state(update, state)

        assert "pending_outbound_messages" not in result or result.get("pending_outbound_messages", []) == []

    def test_does_not_append_to_messages_list(self):
        """
        D3 contract also applies to from_state variant.
        """
        update: dict = {}
        state: dict = {
            "expediente_intro_sent": False,
            "expediente_intro_message": "Intro from state",
        }
        result = _build_intro_emission_from_state(update, state)

        messages = result.get("messages", [])
        assert messages == [], f"messages[] must be empty in D3 (from_state), got: {messages}"
