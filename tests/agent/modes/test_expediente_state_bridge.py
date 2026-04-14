"""
Unit tests for parent_to_expediente state bridge.

fix-expediente-context-gaps Phase 3: verifies that presupuesto_images_shown
is correctly bridged from shared_context into the expediente subgraph state.

Pure unit tests (no DB, no Redis, no LLM).
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent.modes.expediente_state import expediente_to_parent_updates, parent_to_expediente


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


# =============================================================================
# fix-expediente-message-propagation: expediente_to_parent_updates messages
# =============================================================================


class TestExpedienteToParentUpdatesMessages:
    """Tests for message propagation in expediente_to_parent_updates."""

    def test_both_user_and_ai_messages(self):
        """Happy path: both user_message and ai_response present."""
        exp_state = {"user_message": "Fiat Ducato", "ai_response": "Datos guardados."}
        result = expediente_to_parent_updates(exp_state)
        assert len(result["messages"]) == 2
        assert isinstance(result["messages"][0], HumanMessage)
        assert isinstance(result["messages"][1], AIMessage)
        assert "<USER_MESSAGE>" in result["messages"][0].content
        assert result["messages"][1].content == "Datos guardados."

    def test_only_user_message(self):
        """Tool-only turn: no ai_response."""
        exp_state = {"user_message": "listo", "ai_response": ""}
        result = expediente_to_parent_updates(exp_state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], HumanMessage)

    def test_only_ai_response(self):
        """Edge case: ai_response without user_message."""
        exp_state = {"user_message": "", "ai_response": "Necesito tus datos."}
        result = expediente_to_parent_updates(exp_state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)

    def test_both_empty(self):
        """Error path: both empty."""
        exp_state = {"user_message": "", "ai_response": ""}
        result = expediente_to_parent_updates(exp_state)
        assert result["messages"] == []

    def test_whitespace_only_user_message(self):
        """Whitespace-only treated as empty."""
        exp_state = {"user_message": "   \n  ", "ai_response": "Response"}
        result = expediente_to_parent_updates(exp_state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)

    def test_none_values(self):
        """None user_message and ai_response."""
        exp_state = {"user_message": None, "ai_response": None}
        result = expediente_to_parent_updates(exp_state)
        assert result["messages"] == []

    def test_human_message_has_security_tags(self):
        """HumanMessage must be wrapped in USER_MESSAGE tags."""
        exp_state = {"user_message": "test data", "ai_response": "ok"}
        result = expediente_to_parent_updates(exp_state)
        content = result["messages"][0].content
        assert content.startswith("<USER_MESSAGE>")
        assert content.endswith("</USER_MESSAGE>")
        assert "test data" in content
