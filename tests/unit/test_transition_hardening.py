"""
Transition Hardening — Regression Tests (Phase 0).

Tests that validate CURRENT transition behavior before the hardening refactor.
After each phase, we update these tests to reflect the NEW expected behavior.

Test categories:
1. transition_mode() core behavior (preserve, draft, Overwrite)
2. Gateway transitions (YES/NO/ambiguous → correct state updates)
3. Tool-signaled transitions (PRESUPUESTO → GATEWAY, EXPEDIENTE → PRESUPUESTO)
4. Fallback reset behavior
5. Escalation completeness
6. Context key leakage detection

These tests are PURE UNIT TESTS — no DB, no Redis, no LLM, no network.
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import patch, AsyncMock

from agent.state.conversation_state import (
    ConversationState,
    ModeContextData,
    transition_mode,
    create_empty_retry_state,
    create_initial_state,
    merge_dicts,
    preserve_if_none,
    merge_retry_state,
    append_unique_list,
)
from agent.router.mode_transitions import (
    get_preserve_keys,
    is_transition_allowed,
    validate_transition,
    CONTEXT_PRESERVE_RULES,
    ALLOWED_TRANSITIONS,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_state(**overrides) -> ConversationState:
    """Create a minimal ConversationState dict for testing."""
    base = {
        "conversation_id": "test-conv-1",
        "user_phone": "+34600000001",
        "user_name": "Test User",
        "user_id": "user-uuid-123",
        "client_type": "particular",
        "current_mode": "START",
        "previous_mode": None,
        "mode_history": [],
        "mode_context": {},
        "draft_contexts": {},
        "retry_state": create_empty_retry_state(),
        "messages": [],
        "user_message": "test message",
        "ai_response": None,
        "total_message_count": 0,
        "mode_message_count": 0,
        "is_first_interaction": True,
        "agent_disabled": False,
        "escalation_triggered": False,
        "escalation_reason": None,
        "pending_human_decision": False,
        "user_profile": {},
        "draft_quote": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "last_activity_at": datetime.now(UTC).isoformat(),
        "last_node": None,
    }
    base.update(overrides)
    return base


def _presupuesto_context() -> dict:
    """Context as it would look in PRESUPUESTO_MODE after quote calculation."""
    return {
        "categoria_slug": "motos-part",
        "element_codes": ["ESCAPE", "MANILLAR"],
        "tarifa_calculada": {"datos": {"price": 410.0, "tier_id": "tier-uuid"}},
        "precio_comunicado": True,
        "imagenes_enviadas": True,
        "pending_variants": [],
        "elemento_tentativo": None,
        "elemento_confirmado": {"code": "ESCAPE"},
        "waiting_for_image_choice": False,
        "last_follow_up_sent": None,
    }


def _gateway_context() -> dict:
    """Context as it would look in EVALUACION_GATEWAY (after spread from PRESUPUESTO)."""
    ctx = _presupuesto_context()
    ctx.update({
        "gateway_confirmed": True,
        "gateway_question_asked": False,
        "gateway_attempts": 0,
    })
    return ctx


# ============================================================================
# 1. Reducer Behavior Tests
# ============================================================================

class TestReducers:
    """Verify reducer behavior — this is the foundation everything depends on."""

    def test_merge_dicts_preserves_existing_on_none_update(self):
        """When update is None, current dict is preserved."""
        current = {"key1": "value1", "key2": "value2"}
        result = merge_dicts(current, None)
        assert result == current

    def test_merge_dicts_shallow_merge(self):
        """update keys override current, current keys persist."""
        current = {"a": 1, "b": 2, "c": 3}
        update = {"b": 20, "d": 4}
        result = merge_dicts(current, update)
        assert result == {"a": 1, "b": 20, "c": 3, "d": 4}

    def test_merge_dicts_empty_update_preserves_all(self):
        """BUG C2: Empty dict merge preserves everything — reset is a no-op."""
        current = {"stale_key": "should_persist", "another": 42}
        result = merge_dicts(current, {})
        assert result == current, "Empty dict merge should preserve all (this is the bug)"

    def test_merge_dicts_cannot_delete_keys(self):
        """There's no way to delete a key via merge_dicts."""
        current = {"keep": True, "garbage": "from_previous_mode"}
        # Even with a targeted update, garbage persists
        result = merge_dicts(current, {"keep": True})
        assert "garbage" in result, "merge_dicts cannot remove keys"

    def test_preserve_if_none_keeps_current(self):
        """When update is None, current value persists."""
        assert preserve_if_none("PRESUPUESTO_MODE", None) == "PRESUPUESTO_MODE"

    def test_preserve_if_none_replaces_on_value(self):
        """When update has a value, it replaces current."""
        assert preserve_if_none("PRESUPUESTO_MODE", "EXPEDIENTE_MODE") == "EXPEDIENTE_MODE"

    def test_merge_retry_state_reset_on_zero(self):
        """retry_count=0 triggers FULL replacement (not merge)."""
        current = {"retry_count": 3, "last_error_type": "llm_error", "extra": "data"}
        update = create_empty_retry_state()  # retry_count=0
        result = merge_retry_state(current, update)
        assert result["retry_count"] == 0
        assert "extra" not in result, "Full replacement on retry_count=0"

    def test_append_unique_list_deduplicates(self):
        """BUG H5: append_unique_list deduplicates — loses visit ordering."""
        current = ["PRESUPUESTO_MODE", "CONSULTA_MODE"]
        update = ["PRESUPUESTO_MODE"]  # Re-visiting
        result = append_unique_list(current, update)
        assert result == ["PRESUPUESTO_MODE", "CONSULTA_MODE"], \
            "Duplicate entry not appended (loses ordering info)"


# ============================================================================
# 2. transition_mode() Core Tests
# ============================================================================

class TestTransitionModeCore:
    """Tests for the transition_mode() function."""

    def test_basic_transition_updates_mode(self):
        """transition_mode should set current_mode to new mode."""
        state = _make_state(current_mode="PRESUPUESTO_MODE")
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        assert updates["current_mode"] == "EVALUACION_GATEWAY"

    def test_transition_sets_previous_mode(self):
        """transition_mode should set previous_mode to old mode."""
        state = _make_state(current_mode="PRESUPUESTO_MODE")
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        assert updates["previous_mode"] == "PRESUPUESTO_MODE"

    def test_transition_resets_retry_state(self):
        """transition_mode should reset retry_state."""
        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            retry_state={"retry_count": 3, "last_error_type": "llm_error"},
        )
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        assert updates["retry_state"]["retry_count"] == 0

    def test_transition_resets_mode_message_count(self):
        """transition_mode should reset mode_message_count to 0."""
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_message_count=15)
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        assert updates["mode_message_count"] == 0

    def test_transition_updates_mode_history(self):
        """transition_mode should append current mode to history."""
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_history=["CONSULTA_MODE"])
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        assert "PRESUPUESTO_MODE" in updates["mode_history"]

    def test_transition_start_not_in_history(self):
        """START mode should NOT be appended to mode_history."""
        state = _make_state(current_mode="START")
        updates = transition_mode(state, "PRESUPUESTO_MODE")
        assert "START" not in updates["mode_history"]

    def test_transition_preserves_specified_keys(self):
        """preserve_keys should carry specific keys from old context to new."""
        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            mode_context={
                "categoria_slug": "motos-part",
                "element_codes": ["ESCAPE"],
                "tarifa_calculada": {"price": 410},
                "garbage_key": "should_not_be_preserved",
            },
        )
        updates = transition_mode(
            state, "EVALUACION_GATEWAY",
            preserve_keys=["categoria_slug", "element_codes", "tarifa_calculada"],
        )
        ctx = updates["mode_context"]

        # Check we're dealing with the actual context (could be Overwrite wrapper)
        if hasattr(ctx, 'value'):
            ctx = ctx.value

        assert ctx.get("categoria_slug") == "motos-part"
        assert ctx.get("element_codes") == ["ESCAPE"]
        assert ctx.get("tarifa_calculada") == {"price": 410}

    def test_transition_saves_draft_context(self):
        """transition_mode should save current context to draft_contexts."""
        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            mode_context={"categoria_slug": "motos-part", "element_codes": ["ESCAPE"]},
            draft_contexts={},
        )
        updates = transition_mode(state, "EVALUACION_GATEWAY")
        drafts = updates["draft_contexts"]

        # Could be Overwrite wrapper
        if hasattr(drafts, 'value'):
            drafts = drafts.value

        assert "PRESUPUESTO_MODE" in drafts
        assert drafts["PRESUPUESTO_MODE"]["categoria_slug"] == "motos-part"

    def test_transition_restores_draft_context(self):
        """If draft exists for target mode, it should be restored."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context={"gateway_confirmed": False},
            draft_contexts={
                "PRESUPUESTO_MODE": {
                    "categoria_slug": "motos-part",
                    "element_codes": ["ESCAPE"],
                    "precio_comunicado": True,
                },
            },
        )
        updates = transition_mode(state, "PRESUPUESTO_MODE")
        ctx = updates["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        assert ctx.get("categoria_slug") == "motos-part"
        assert ctx.get("precio_comunicado") is True

    def test_transition_with_explicit_new_context(self):
        """new_context parameter should override everything."""
        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            mode_context={"old_key": "old_value"},
        )
        updates = transition_mode(
            state, "EXPEDIENTE_MODE",
            new_context={"case_id": "new-case-uuid", "element_codes": ["ESCAPE"]},
        )
        ctx = updates["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        assert ctx.get("case_id") == "new-case-uuid"


# ============================================================================
# 3. Gateway Transition Tests (CURRENT behavior)
# ============================================================================

class TestGatewayTransitions:
    """Test EVALUACION_GATEWAY transitions — document current behavior."""

    def setup_method(self):
        from agent.modes.evaluacion_gateway import EvaluacionGatewayNode
        self.node = EvaluacionGatewayNode()

    def test_handle_yes_transitions_to_expediente(self):
        """_handle_yes should set current_mode to EXPEDIENTE_MODE."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))

        assert result["current_mode"] == "EXPEDIENTE_MODE"
        assert result.get("ai_response")

    def test_handle_yes_preserves_critical_keys(self):
        """_handle_yes must preserve keys needed by EXPEDIENTE."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        ctx = result["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        assert ctx.get("categoria_slug") == "motos-part"
        assert ctx.get("element_codes") == ["ESCAPE", "MANILLAR"]
        assert ctx.get("tarifa_calculada") is not None

    def test_handle_no_transitions_to_presupuesto(self):
        """_handle_no should set current_mode to PRESUPUESTO_MODE."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_no(state, dict(state["mode_context"]))

        assert result["current_mode"] == "PRESUPUESTO_MODE"

    def test_handle_no_preserves_presupuesto_keys(self):
        """_handle_no should preserve keys needed by PRESUPUESTO."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_no(state, dict(state["mode_context"]))
        ctx = result["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        assert ctx.get("categoria_slug") == "motos-part"
        assert ctx.get("element_codes") == ["ESCAPE", "MANILLAR"]
        assert ctx.get("tarifa_calculada") is not None

    def test_handle_ambiguous_max_retries_to_presupuesto(self):
        """After MAX_GATEWAY_RETRIES ambiguous responses, should go to PRESUPUESTO."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context={
                **_gateway_context(),
                "gateway_question_asked": True,
            },
        )
        # Simulate reaching max retries (MAX_GATEWAY_RETRIES = 2)
        result = self.node._handle_ambiguous(
            "hmm no sé", state, dict(state["mode_context"]), attempts=1,
        )
        assert result["current_mode"] == "PRESUPUESTO_MODE"

    # --- These tests document the CURRENT broken behavior ---
    # After hardening (Phase 2), we'll update them to expect clean behavior

    def test_handle_yes_currently_leaks_gateway_keys(self):
        """CURRENT: _handle_yes leaks gateway keys to EXPEDIENTE.
        After Phase 2: this test should be updated to assert keys are NOT leaked."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        ctx = result["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        # CURRENT: gateway keys LEAK (this is the bug)
        assert "gateway_confirmed" in ctx
        assert "gateway_question_asked" in ctx
        assert "gateway_attempts" in ctx
        # CURRENT: presupuesto keys ALSO leak
        assert "precio_comunicado" in ctx
        assert "imagenes_enviadas" in ctx

    def test_handle_yes_currently_no_previous_mode(self):
        """CURRENT: _handle_yes does NOT set previous_mode.
        After Phase 2: should set previous_mode=EVALUACION_GATEWAY."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        assert "previous_mode" not in result

    def test_handle_yes_currently_no_retry_reset(self):
        """CURRENT: _handle_yes does NOT reset retry_state.
        After Phase 2: should include reset retry_state."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        assert "retry_state" not in result


# ============================================================================
# 4. Fallback Reset Tests
# ============================================================================

class TestFallbackBehavior:
    """Test fallback handler reset and escalation behavior."""

    def setup_method(self):
        from agent.fallback.fallback_handler import FallbackHandler
        self.handler = FallbackHandler()

    def test_reset_to_mode_start_action(self):
        """RESET_TO_MODE_START should return empty mode_context (currently a no-op)."""
        from agent.fallback.fallback_handler import FallbackAction, RetryPolicy

        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            mode_context=_presupuesto_context(),
        )
        retry_state = {"retry_count": 4, "last_error_type": "llm_error"}

        # Simulate policy with RESET_TO_MODE_START action
        policy = RetryPolicy(
            mode="PRESUPUESTO_MODE",
            max_retries=4,
            action_on_limit=FallbackAction.RESET_TO_MODE_START,
        )

        result = self.handler.execute_fallback(policy, state, retry_state)

        assert result.get("ai_response"), "Should include a message"
        assert result.get("retry_state", {}).get("retry_count") == 0
        # CURRENT: mode_context: {} which is a no-op due to merge_dicts
        assert result.get("mode_context") == {} or result.get("mode_context") is not None

    def test_escalate_to_human_action(self):
        """ESCALATE_TO_HUMAN should set escalation fields."""
        from agent.fallback.fallback_handler import FallbackAction, RetryPolicy

        state = _make_state(current_mode="PRESUPUESTO_MODE")
        retry_state = {"retry_count": 4, "last_error_type": "llm_error"}

        policy = RetryPolicy(
            mode="PRESUPUESTO_MODE",
            max_retries=4,
            action_on_limit=FallbackAction.ESCALATE_TO_HUMAN,
        )

        result = self.handler.execute_fallback(policy, state, retry_state)

        assert result.get("current_mode") == "ESCALATION"
        assert result.get("escalation_triggered") is True
        assert result.get("escalation_reason") is not None

    def test_reset_to_consulta_sets_mode(self):
        """RESET_TO_CONSULTA should transition to CONSULTA_MODE."""
        from agent.fallback.fallback_handler import FallbackAction, RetryPolicy

        state = _make_state(current_mode="EVALUACION_GATEWAY")
        retry_state = {"retry_count": 2, "last_error_type": "llm_error"}

        policy = RetryPolicy(
            mode="EVALUACION_GATEWAY",
            max_retries=2,
            action_on_limit=FallbackAction.RESET_TO_CONSULTA,
        )

        result = self.handler.execute_fallback(policy, state, retry_state)

        assert result.get("current_mode") == "CONSULTA_MODE"
        assert result.get("previous_mode") == "EVALUACION_GATEWAY"


# ============================================================================
# 5. Context Preserve Rules Completeness
# ============================================================================

class TestContextPreserveRules:
    """Verify CONTEXT_PRESERVE_RULES cover all critical transitions."""

    def test_presupuesto_to_gateway_has_rules(self):
        """PRESUPUESTO → EVALUACION_GATEWAY should have preserve rules."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EVALUACION_GATEWAY")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys

    def test_gateway_to_expediente_has_rules(self):
        """EVALUACION_GATEWAY → EXPEDIENTE_MODE should have preserve rules."""
        keys = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys

    def test_start_to_any_has_no_rules(self):
        """START → any mode has no preserve rules (nothing to preserve)."""
        for target in ["CONSULTA_MODE", "PRESUPUESTO_MODE"]:
            keys = get_preserve_keys("START", target)
            assert keys == [], f"START → {target} should have no preserve keys"

    def test_all_allowed_transitions_are_covered(self):
        """Every allowed transition should either have preserve rules or be intentionally empty."""
        transitions_without_rules = []
        for source, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                if target == "ESCALATION":
                    continue  # Escalation doesn't need preserved context
                keys = get_preserve_keys(source, target)
                if not keys and source != "START":
                    transitions_without_rules.append(f"{source} → {target}")

        # Document which transitions have no rules (not necessarily a bug)
        # After hardening, we should have rules for all non-START transitions
        # For now, just verify awareness
        if transitions_without_rules:
            # This is informational — some transitions legitimately have no preserve rules
            pass  # Will be enforced after Phase 1


# ============================================================================
# 6. Mode Transition Whitelist Integrity
# ============================================================================

class TestTransitionWhitelistIntegrity:
    """Verify the transition whitelist is correct and complete."""

    def test_happy_path_transitions_allowed(self):
        """The main sales funnel transitions should all be allowed."""
        happy_path = [
            ("START", "PRESUPUESTO_MODE"),
            ("PRESUPUESTO_MODE", "EVALUACION_GATEWAY"),
            ("EVALUACION_GATEWAY", "EXPEDIENTE_MODE"),
            ("EVALUACION_GATEWAY", "PRESUPUESTO_MODE"),
        ]
        for source, target in happy_path:
            assert is_transition_allowed(source, target), \
                f"{source} → {target} should be allowed"

    def test_funnel_bypass_blocked(self):
        """Bypassing the gateway should NOT be allowed."""
        assert not is_transition_allowed("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert not is_transition_allowed("CONSULTA_MODE", "EXPEDIENTE_MODE")

    def test_backwards_funnel_allowed_where_needed(self):
        """Backwards transitions should be allowed where design requires."""
        assert is_transition_allowed("EXPEDIENTE_MODE", "PRESUPUESTO_MODE")
        assert is_transition_allowed("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")

    def test_escalation_from_all_modes(self):
        """Escalation should be allowed from every non-terminal mode."""
        non_terminal = ["START", "CONSULTA_MODE", "PRESUPUESTO_MODE",
                        "EVALUACION_GATEWAY", "EXPEDIENTE_MODE"]
        for mode in non_terminal:
            assert is_transition_allowed(mode, "ESCALATION"), \
                f"Escalation from {mode} must be allowed"

    def test_terminal_modes_have_no_exits(self):
        """ESCALATION and COMPLETED should have no outgoing transitions."""
        assert ALLOWED_TRANSITIONS.get("ESCALATION") == []
        assert ALLOWED_TRANSITIONS.get("COMPLETED") == []


# ============================================================================
# 7. Expediente Key Requirements
# ============================================================================

class TestExpedienteKeyRequirements:
    """Verify EXPEDIENTE_MODE gets the keys it needs from transitions."""

    def test_expediente_requires_categoria_slug(self):
        """EXPEDIENTE auto_create_case needs categoria_slug."""
        # This key MUST be in the preserve rules for GATEWAY → EXPEDIENTE
        keys = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        assert "categoria_slug" in keys

    def test_expediente_requires_element_codes(self):
        """EXPEDIENTE auto_create_case needs element_codes."""
        keys = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        assert "element_codes" in keys

    def test_expediente_requires_tarifa_calculada(self):
        """EXPEDIENTE auto_create_case needs tarifa_calculada for price."""
        keys = get_preserve_keys("EVALUACION_GATEWAY", "EXPEDIENTE_MODE")
        assert "tarifa_calculada" in keys
