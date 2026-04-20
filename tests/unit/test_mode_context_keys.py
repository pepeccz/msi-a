"""
T0.1 — last_cta_emitted registered in CANONICAL_MODE_CONTEXT_KEYS.

Spec: last_cta_emitted Flag Lifecycle
  - GIVEN the canonical key registry
  - THEN "last_cta_emitted" MUST be a member of CANONICAL_MODE_CONTEXT_KEYS
    so the validation helper does not warn-log on legitimate writes.
"""

from __future__ import annotations

import pytest


class TestLastCtaEmittedRegistered:
    """Registry membership for last_cta_emitted."""

    def test_last_cta_emitted_registered_in_canonical_keys(self) -> None:
        """
        T0.1 — GREEN assertion:
        "last_cta_emitted" must be in CANONICAL_MODE_CONTEXT_KEYS.
        """
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert "last_cta_emitted" in CANONICAL_MODE_CONTEXT_KEYS, (
            "'last_cta_emitted' missing from CANONICAL_MODE_CONTEXT_KEYS. "
            "Add it to _MODE_RUNTIME_KEYS in agent/state/mode_context_keys.py."
        )

    def test_canonical_keys_is_frozenset(self) -> None:
        """Triangulation: canonical set must remain a frozenset (structural contract)."""
        from agent.state.mode_context_keys import CANONICAL_MODE_CONTEXT_KEYS

        assert isinstance(CANONICAL_MODE_CONTEXT_KEYS, frozenset), (
            "CANONICAL_MODE_CONTEXT_KEYS must be a frozenset."
        )
