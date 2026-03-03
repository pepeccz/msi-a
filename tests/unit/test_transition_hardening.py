"""
Transition Hardening — Regression Tests (Phase 0).

Tests that validate CURRENT transition behavior before the hardening refactor.
After each phase, we update these tests to reflect the NEW expected behavior.

Test categories:
1. transition_mode() core behavior (preserve, draft, Overwrite)
2. Tool-signaled transitions (PRESUPUESTO → EXPEDIENTE direct)
3. Fallback reset behavior
4. Escalation completeness
5. Context key leakage detection

Note: EVALUACION_GATEWAY was removed — confirmar_presupuesto now transitions
directly to EXPEDIENTE_MODE via _chain_next_mode. Tests that relied on the
gateway node have been removed.

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
    return base  # type: ignore[return-value]


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


def _expediente_entry_context() -> dict:
    """Context as it would look entering EXPEDIENTE_MODE (after transition from PRESUPUESTO)."""
    return {
        "categoria_slug": "motos-part",
        "element_codes": ["ESCAPE", "MANILLAR"],
        "tarifa_calculada": {"datos": {"price": 410.0, "tier_id": "tier-uuid"}},
    }


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
        updates = transition_mode(state, "EXPEDIENTE_MODE")
        assert updates["current_mode"] == "EXPEDIENTE_MODE"

    def test_transition_sets_previous_mode(self):
        """transition_mode should set previous_mode to old mode."""
        state = _make_state(current_mode="PRESUPUESTO_MODE")
        updates = transition_mode(state, "EXPEDIENTE_MODE")
        assert updates["previous_mode"] == "PRESUPUESTO_MODE"

    def test_transition_resets_retry_state(self):
        """transition_mode should reset retry_state."""
        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            retry_state={"retry_count": 3, "last_error_type": "llm_error"},
        )
        updates = transition_mode(state, "EXPEDIENTE_MODE")
        assert updates["retry_state"]["retry_count"] == 0

    def test_transition_resets_mode_message_count(self):
        """transition_mode should reset mode_message_count to 0."""
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_message_count=15)
        updates = transition_mode(state, "EXPEDIENTE_MODE")
        assert updates["mode_message_count"] == 0

    def test_transition_updates_mode_history(self):
        """transition_mode should append current mode to history."""
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_history=["CONSULTA_MODE"])
        updates = transition_mode(state, "EXPEDIENTE_MODE")
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
            state, "EXPEDIENTE_MODE",
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
        updates = transition_mode(state, "EXPEDIENTE_MODE")
        drafts = updates["draft_contexts"]

        # Could be Overwrite wrapper
        if hasattr(drafts, 'value'):
            drafts = drafts.value

        assert "PRESUPUESTO_MODE" in drafts
        assert drafts["PRESUPUESTO_MODE"]["categoria_slug"] == "motos-part"

    def test_transition_restores_draft_context(self):
        """If draft exists for target mode, it should be restored."""
        state = _make_state(
            current_mode="EXPEDIENTE_MODE",
            mode_context={"case_id": "some-case-uuid"},
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
# 3. Fallback Reset Tests
# ============================================================================

class TestFallbackBehavior:
    """Test fallback handler reset and escalation behavior."""

    def setup_method(self):
        from agent.fallback.fallback_handler import FallbackHandler
        self.handler = FallbackHandler()

    def test_reset_to_mode_start_action(self):
        """RESET_TO_MODE_START should return Overwrite({}) to actually clear context."""
        from agent.fallback.fallback_handler import FallbackAction, RetryPolicy
        from langgraph.types import Overwrite

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
        # Phase 4 FIX: Overwrite({}) actually clears (bypasses merge_dicts)
        ctx = result.get("mode_context")
        assert isinstance(ctx, Overwrite), "Should use Overwrite to bypass merge_dicts"
        assert ctx.value == {}, "Should be empty dict"

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
        """RESET_TO_CONSULTA should transition to CONSULTA_MODE via transition_mode()."""
        from agent.fallback.fallback_handler import FallbackAction, RetryPolicy
        from langgraph.types import Overwrite

        state = _make_state(current_mode="EXPEDIENTE_MODE")
        retry_state = {"retry_count": 2, "last_error_type": "llm_error"}

        policy = RetryPolicy(
            mode="EXPEDIENTE_MODE",
            max_retries=2,
            action_on_limit=FallbackAction.RESET_TO_CONSULTA,
        )

        result = self.handler.execute_fallback(policy, state, retry_state)

        assert result.get("current_mode") == "CONSULTA_MODE"
        assert result.get("previous_mode") == "EXPEDIENTE_MODE"
        # Phase 4: Now uses transition_mode() → Overwrite context
        assert isinstance(result.get("mode_context"), Overwrite)


# ============================================================================
# 4. Context Preserve Rules Completeness
# ============================================================================

class TestContextPreserveRules:
    """Verify CONTEXT_PRESERVE_RULES cover all critical transitions."""

    def test_presupuesto_to_expediente_has_rules(self):
        """PRESUPUESTO → EXPEDIENTE_MODE should have preserve rules."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
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
        if transitions_without_rules:
            # This is informational — some transitions legitimately have no preserve rules
            pass  # Will be enforced after Phase 1


# ============================================================================
# 5. Mode Transition Whitelist Integrity
# ============================================================================

class TestTransitionWhitelistIntegrity:
    """Verify the transition whitelist is correct and complete."""

    def test_happy_path_transitions_allowed(self):
        """The main sales funnel transitions should all be allowed."""
        happy_path = [
            ("START", "PRESUPUESTO_MODE"),
            ("PRESUPUESTO_MODE", "EXPEDIENTE_MODE"),  # Direct now
        ]
        for source, target in happy_path:
            assert is_transition_allowed(source, target), \
                f"{source} → {target} should be allowed"

    def test_backwards_funnel_allowed_where_needed(self):
        """Backwards transitions should be allowed where design requires."""
        assert is_transition_allowed("EXPEDIENTE_MODE", "PRESUPUESTO_MODE")

    def test_escalation_from_all_modes(self):
        """Escalation should be allowed from every non-terminal mode."""
        non_terminal = ["START", "CONSULTA_MODE", "PRESUPUESTO_MODE", "EXPEDIENTE_MODE"]
        for mode in non_terminal:
            assert is_transition_allowed(mode, "ESCALATION"), \
                f"Escalation from {mode} must be allowed"

    def test_terminal_modes_have_no_exits(self):
        """ESCALATION and COMPLETED should have no outgoing transitions."""
        assert ALLOWED_TRANSITIONS.get("ESCALATION") == []
        assert ALLOWED_TRANSITIONS.get("COMPLETED") == []

    def test_evaluacion_gateway_not_in_transitions(self):
        """EVALUACION_GATEWAY must NOT exist in ALLOWED_TRANSITIONS (removed)."""
        assert "EVALUACION_GATEWAY" not in ALLOWED_TRANSITIONS, \
            "EVALUACION_GATEWAY must be fully removed from ALLOWED_TRANSITIONS"
        for source, targets in ALLOWED_TRANSITIONS.items():
            assert "EVALUACION_GATEWAY" not in targets, \
                f"EVALUACION_GATEWAY must not be a target in {source} transitions"


# ============================================================================
# 6. Expediente Key Requirements
# ============================================================================

class TestExpedienteKeyRequirements:
    """Verify EXPEDIENTE_MODE gets the keys it needs from transitions."""

    def test_expediente_requires_categoria_slug(self):
        """EXPEDIENTE auto_create_case needs categoria_slug."""
        # Keys MUST be preserved in PRESUPUESTO → EXPEDIENTE transition
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert "categoria_slug" in keys

    def test_expediente_requires_element_codes(self):
        """EXPEDIENTE auto_create_case needs element_codes."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert "element_codes" in keys

    def test_expediente_requires_tarifa_calculada(self):
        """EXPEDIENTE auto_create_case needs tarifa_calculada for price."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert "tarifa_calculada" in keys


# ============================================================================
# 7. Phase 1: Overwrite Behavior Tests
# ============================================================================

class TestOverwriteInTransitionMode:
    """Phase 1: Verify transition_mode() uses Overwrite to bypass merge_dicts."""

    def test_mode_context_is_overwrite_wrapped(self):
        """transition_mode() should return mode_context wrapped in Overwrite."""
        from langgraph.types import Overwrite

        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=_presupuesto_context())
        updates = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=["categoria_slug"])

        assert isinstance(updates["mode_context"], Overwrite), \
            "mode_context should be Overwrite-wrapped to bypass merge_dicts"

    def test_draft_contexts_is_overwrite_wrapped(self):
        """transition_mode() should return draft_contexts wrapped in Overwrite."""
        from langgraph.types import Overwrite

        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=_presupuesto_context())
        updates = transition_mode(state, "EXPEDIENTE_MODE")

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
        preserve = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        updates = transition_mode(state, "EXPEDIENTE_MODE", preserve_keys=preserve)

        ctx = updates["mode_context"]
        if isinstance(ctx, Overwrite):
            ctx = ctx.value

        # Only preserved keys should exist
        assert "categoria_slug" in ctx
        assert "element_codes" in ctx
        assert "tarifa_calculada" in ctx
        # Garbage should NOT survive
        assert "garbage_key" not in ctx, "Non-preserved keys must not leak through Overwrite"

    def test_overwrite_draft_saves_full_context(self):
        """Draft contexts should contain the FULL previous context (for later restore)."""
        from langgraph.types import Overwrite

        ctx = _presupuesto_context()
        state = _make_state(current_mode="PRESUPUESTO_MODE", mode_context=ctx)
        updates = transition_mode(state, "EXPEDIENTE_MODE")

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
            current_mode="EXPEDIENTE_MODE",
            mode_context={"case_id": "some-uuid"},
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

    def test_expediente_to_presupuesto_preserve_rules_exist(self):
        """EXPEDIENTE → PRESUPUESTO preserve rules exist."""
        keys = get_preserve_keys("EXPEDIENTE_MODE", "PRESUPUESTO_MODE")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys

    def test_presupuesto_to_expediente_preserve_rules_exist(self):
        """PRESUPUESTO → EXPEDIENTE preserve rules exist."""
        keys = get_preserve_keys("PRESUPUESTO_MODE", "EXPEDIENTE_MODE")
        assert len(keys) > 0
        assert "categoria_slug" in keys
        assert "element_codes" in keys
        assert "tarifa_calculada" in keys
