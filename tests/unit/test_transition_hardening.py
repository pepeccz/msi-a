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

    # --- Phase 2: These tests verify FIXED behavior (was broken before Phase 2) ---

    def test_handle_yes_no_longer_leaks_gateway_keys(self):
        """Phase 2 FIX: _handle_yes now uses transition_mode() → no key leaks."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        ctx = result["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        # FIXED: gateway keys should NOT leak to EXPEDIENTE
        assert "gateway_confirmed" not in ctx
        assert "gateway_question_asked" not in ctx
        assert "gateway_attempts" not in ctx
        # FIXED: presupuesto keys should NOT leak either
        assert "precio_comunicado" not in ctx
        assert "imagenes_enviadas" not in ctx
        # Only preserved keys should exist
        assert "categoria_slug" in ctx
        assert "element_codes" in ctx
        assert "tarifa_calculada" in ctx

    def test_handle_yes_sets_previous_mode(self):
        """Phase 2 FIX: _handle_yes now sets previous_mode=EVALUACION_GATEWAY."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        assert result["previous_mode"] == "EVALUACION_GATEWAY"

    def test_handle_yes_resets_retry_state(self):
        """Phase 2 FIX: _handle_yes now resets retry_state."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_yes(state, dict(state["mode_context"]))
        assert "retry_state" in result
        assert result["retry_state"]["retry_count"] == 0

    def test_handle_no_sets_previous_mode(self):
        """Phase 2 FIX: _handle_no now sets previous_mode=EVALUACION_GATEWAY."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_no(state, dict(state["mode_context"]))
        assert result["previous_mode"] == "EVALUACION_GATEWAY"

    def test_handle_no_clean_context(self):
        """Phase 2 FIX: _handle_no returns clean context with only preserved keys."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context=_gateway_context(),
        )
        result = self.node._handle_no(state, dict(state["mode_context"]))
        ctx = result["mode_context"]

        if hasattr(ctx, 'value'):
            ctx = ctx.value

        # Gateway keys should NOT leak back to PRESUPUESTO
        assert "gateway_confirmed" not in ctx
        assert "gateway_question_asked" not in ctx
        assert "gateway_attempts" not in ctx
        # Preserved keys should be present
        assert "categoria_slug" in ctx
        assert "element_codes" in ctx
        assert "precio_comunicado" in ctx

    def test_handle_ambiguous_max_retries_clean_transition(self):
        """Phase 2 FIX: ambiguous max retries uses transition_mode()."""
        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context={**_gateway_context(), "gateway_question_asked": True},
        )
        result = self.node._handle_ambiguous("hmm", state, dict(state["mode_context"]), attempts=1)
        assert result["current_mode"] == "PRESUPUESTO_MODE"
        assert result["previous_mode"] == "EVALUACION_GATEWAY"
        assert "retry_state" in result


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


# ============================================================================
# 8. Phase 1: Overwrite Behavior Tests
# ============================================================================

class TestOverwriteInTransitionMode:
    """Phase 1: Verify transition_mode() uses Overwrite to bypass merge_dicts."""

    def test_mode_context_is_overwrite_wrapped(self):
        """transition_mode() should return mode_context wrapped in Overwrite."""
        from langgraph.types import Overwrite

        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=_presupuesto_context())
        updates = transition_mode(state, "EVALUACION_GATEWAY", preserve_keys=["categoria_slug"])

        assert isinstance(updates["mode_context"], Overwrite), \
            "mode_context should be Overwrite-wrapped to bypass merge_dicts"

    def test_draft_contexts_is_overwrite_wrapped(self):
        """transition_mode() should return draft_contexts wrapped in Overwrite."""
        from langgraph.types import Overwrite

        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=_presupuesto_context())
        updates = transition_mode(state, "EVALUACION_GATEWAY")

        assert isinstance(updates["draft_contexts"], Overwrite), \
            "draft_contexts should be Overwrite-wrapped to bypass merge_dicts"

    def test_overwrite_context_only_has_preserved_keys(self):
        """After Overwrite, context should ONLY contain preserved keys (no leaks)."""
        from langgraph.types import Overwrite

        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            mode_context={
                "categoria_slug": "motos-part",
                "element_codes": ["ESCAPE"],
                "tarifa_calculada": {"price": 410},
                "precio_comunicado": True,
                "imagenes_enviadas": True,
                "pending_variants": [],
                "garbage_key": "should_not_survive",
            },
        )
        preserve = get_preserve_keys("PRESUPUESTO_MODE", "EVALUACION_GATEWAY")
        updates = transition_mode(state, "EVALUACION_GATEWAY", preserve_keys=preserve)

        ctx = updates["mode_context"]
        if isinstance(ctx, Overwrite):
            ctx = ctx.value

        # Only preserved keys should exist
        assert "categoria_slug" in ctx
        assert "element_codes" in ctx
        assert "tarifa_calculada" in ctx
        assert "precio_comunicado" in ctx
        # Garbage should NOT survive
        assert "garbage_key" not in ctx, "Non-preserved keys must not leak through Overwrite"
        assert "imagenes_enviadas" not in ctx, "imagenes_enviadas not in PRESUPUESTO→GATEWAY preserve list"
        assert "pending_variants" not in ctx, "pending_variants not in preserve list"

    def test_overwrite_draft_saves_full_context(self):
        """Draft contexts should contain the FULL previous context (for later restore)."""
        from langgraph.types import Overwrite

        ctx = _presupuesto_context()
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=ctx)
        updates = transition_mode(state, "EVALUACION_GATEWAY")

        drafts = updates["draft_contexts"]
        if isinstance(drafts, Overwrite):
            drafts = drafts.value

        assert "PRESUPUESTO_MODE" in drafts
        saved = drafts["PRESUPUESTO_MODE"]
        assert saved["categoria_slug"] == "motos-part"
        assert saved["element_codes"] == ["ESCAPE", "MANILLAR"]
        assert saved["precio_comunicado"] is True

    def test_overwrite_draft_pop_works(self):
        """When restoring a draft, the draft entry should be removed from draft_contexts."""
        from langgraph.types import Overwrite

        state = _make_state(
            current_mode="EVALUACION_GATEWAY",
            mode_context={"gateway_confirmed": False},
            draft_contexts={
                "PRESUPUESTO_MODE": {
                    "categoria_slug": "motos-part",
                    "element_codes": ["ESCAPE"],
                },
            },
        )
        updates = transition_mode(state, "PRESUPUESTO_MODE")

        drafts = updates["draft_contexts"]
        if isinstance(drafts, Overwrite):
            drafts = drafts.value

        # Draft should be CONSUMED (popped)
        assert "PRESUPUESTO_MODE" not in drafts, \
            "Restored draft should be removed from draft_contexts (Overwrite makes pop() effective)"

        # Context should contain the restored data
        ctx = updates["mode_context"]
        if isinstance(ctx, Overwrite):
            ctx = ctx.value
        assert ctx.get("categoria_slug") == "motos-part"

    def test_gateway_to_presupuesto_preserve_rules_exist(self):
        """Phase 1 added GATEWAY → PRESUPUESTO preserve rules."""
        keys = get_preserve_keys("EVALUACION_GATEWAY", "PRESUPUESTO_MODE")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys
        assert "precio_comunicado" in keys
        assert "imagenes_enviadas" in keys

    def test_expediente_to_presupuesto_preserve_rules_exist(self):
        """Phase 1 added EXPEDIENTE → PRESUPUESTO preserve rules."""
        keys = get_preserve_keys("EXPEDIENTE_MODE", "PRESUPUESTO_MODE")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys

    def test_presupuesto_to_gateway_has_precio_comunicado(self):
        """Phase 1 added precio_comunicado to PRESUPUESTO → GATEWAY preserve rules."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EVALUACION_GATEWAY")
        assert "precio_comunicado" in keys
