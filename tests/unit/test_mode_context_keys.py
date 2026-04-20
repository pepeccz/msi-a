"""
Tests for mode_context_keys registry.

Spec coverage: key registration for last_cta_emitted.
"""

from __future__ import annotations


class TestLastCTAEmittedRegistered:
    """T0.1 — last_cta_emitted must be in CANONICAL_MODE_CONTEXT_KEYS."""

    def test_last_cta_emitted_registered(self):
        """
        RED: 'last_cta_emitted' MUST appear in CANONICAL_MODE_CONTEXT_KEYS
        so the runtime validator does not emit unknown-key warnings for it.
        """
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "last_cta_emitted" in CANONICAL_MODE_CONTEXT_KEYS, (
            "'last_cta_emitted' is not registered in CANONICAL_MODE_CONTEXT_KEYS. "
            "Add it to _MODE_RUNTIME_KEYS in agent/state/mode_context_keys.py."
        )

    def test_canonical_keys_is_frozenset(self):
        """Triangulation: CANONICAL_MODE_CONTEXT_KEYS remains a frozenset (immutable)."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert isinstance(CANONICAL_MODE_CONTEXT_KEYS, frozenset), (
            "CANONICAL_MODE_CONTEXT_KEYS must be a frozenset, got "
            f"{type(CANONICAL_MODE_CONTEXT_KEYS)}"
        )
