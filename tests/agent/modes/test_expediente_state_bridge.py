"""
Unit tests for parent_to_expediente state bridge.

fix-expediente-context-gaps Phase 3: verifies that presupuesto_images_shown
is correctly bridged from shared_context into the expediente subgraph state.

Pure unit tests (no DB, no Redis, no LLM).
"""

import pytest

from agent.modes.expediente_state import parent_to_expediente


# =============================================================================
# Phase 3 — Task 3.1: presupuesto_images_shown bridging
# =============================================================================


class TestPresupuestoImagesShownBridge:
    """parent_to_expediente must bridge presupuesto_images_shown correctly."""

    def test_shared_context_has_flag_true(self):
        """
        S1: shared_context has presupuesto_images_shown=True, mode_context empty
        → result has presupuesto_images_shown=True.
        """
        parent_state = {
            "shared_context": {"presupuesto_images_shown": True},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        assert result["presupuesto_images_shown"] is True

    def test_mode_context_fallback(self):
        """
        S2: shared_context missing key, mode_context has it
        → result has it (backward compat).
        """
        parent_state = {
            "shared_context": {},
            "mode_context": {"presupuesto_images_shown": True},
        }

        result = parent_to_expediente(parent_state)

        assert result["presupuesto_images_shown"] is True

    def test_shared_context_wins_over_mode_context(self):
        """
        S3: shared_context has it=True, mode_context has it=False
        → shared_context wins (True).
        """
        parent_state = {
            "shared_context": {"presupuesto_images_shown": True},
            "mode_context": {"presupuesto_images_shown": False},
        }

        result = parent_to_expediente(parent_state)

        assert result["presupuesto_images_shown"] is True

    def test_neither_has_flag(self):
        """
        S4: Neither shared_context nor mode_context has the key
        → key absent from result.
        """
        parent_state = {
            "shared_context": {},
            "mode_context": {},
        }

        result = parent_to_expediente(parent_state)

        assert "presupuesto_images_shown" not in result
