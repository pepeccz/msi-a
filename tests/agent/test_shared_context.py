"""
WS4 — Context Persistence Between Modes: shared_context tests.

These tests were written FIRST (TDD) and MUST FAIL before implementation.
After WS4 is implemented they should all pass.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub minimal dependencies so we can import agent.state.* without the full
# service stack (Redis, DB, etc.).
# ---------------------------------------------------------------------------

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["structlog"] = _structlog

for _redis_mod in ("langgraph.checkpoint.redis", "langgraph.checkpoint.redis.aio"):
    if _redis_mod not in sys.modules:
        _stub = types.ModuleType(_redis_mod)
        _stub.AsyncRedisSaver = MagicMock()  # type: ignore[attr-defined]
        sys.modules[_redis_mod] = _stub

# ---------------------------------------------------------------------------

import pytest


# ---------------------------------------------------------------------------
# Test 1: shared_context field exists in ConversationState annotations
# ---------------------------------------------------------------------------


def test_shared_context_field_on_conversation_state():
    """ConversationState must declare a shared_context field with merge_dicts reducer."""
    from agent.state.conversation_state import ConversationState

    annotations = ConversationState.__annotations__
    assert "shared_context" in annotations, (
        "shared_context field is missing from ConversationState"
    )


# ---------------------------------------------------------------------------
# Test 2: transition_mode does NOT alter shared_context
# ---------------------------------------------------------------------------


def test_transition_mode_does_not_alter_shared_context():
    """transition_mode() must never touch shared_context — merge_dicts handles persistence."""
    from agent.state.conversation_state import transition_mode

    state = {
        "current_mode": "PRESUPUESTO_MODE",
        "previous_mode": None,
        "mode_history": [],
        "mode_context": {"precio_comunicado": True},
        "draft_contexts": {},
        "retry_state": {},
        "shared_context": {
            "element_codes": ["ESCAPE", "MANILLAR"],
            "precio_comunicado": True,
        },
    }

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # shared_context must NOT appear in the result dict
    assert "shared_context" not in result, (
        "transition_mode() must not set shared_context — "
        "merge_dicts reducer handles persistence automatically"
    )


# ---------------------------------------------------------------------------
# Test 3: All SharedContext keys survive PRESUPUESTO → EXPEDIENTE transition
# ---------------------------------------------------------------------------


def test_all_shared_context_keys_survive_presupuesto_to_expediente():
    """
    Every key in SharedContext must be absent from the transition_mode() return
    dict so they are preserved by the merge_dicts reducer (not overwritten).
    """
    from agent.state.context_models import SharedContext
    from agent.state.conversation_state import transition_mode

    sc_data: SharedContext = {
        "element_codes": ["ESCAPE"],
        "tarifa_calculada": {"price": 410.0},
        "categoria_slug": "motos-part",
        "precio_comunicado": True,
        "imagenes_enviadas": True,
        "vehiculo": {"marca": "Honda", "modelo": "CBF600"},
        "elementos_confirmados": [{"codigo": "ESCAPE", "nombre": "Escape"}],
        "presupuesto_images_shown": True,
    }

    state = {
        "current_mode": "PRESUPUESTO_MODE",
        "previous_mode": None,
        "mode_history": [],
        "mode_context": {},
        "draft_contexts": {},
        "retry_state": {},
        "shared_context": sc_data,
    }

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # shared_context must NOT appear in the result at all
    assert "shared_context" not in result, (
        "transition_mode() must not include shared_context in its return dict"
    )

    # And the result should NOT contain any of the cross-mode keys at the top level
    cross_mode_keys = list(SharedContext.__annotations__.keys())
    for key in cross_mode_keys:
        assert key not in result, (
            f"transition_mode() wrote '{key}' at top level — "
            "cross-mode keys must live in shared_context, not be propagated by transition_mode()"
        )


# ---------------------------------------------------------------------------
# Test 4: Mode-private keys are wiped on transition
# ---------------------------------------------------------------------------


def test_mode_private_keys_wiped_on_transition():
    """
    Keys inside mode_context that are NOT in shared_context must be wiped
    when transitioning to a new mode (Overwrite semantics).
    """
    from agent.state.conversation_state import transition_mode
    from langgraph.types import Overwrite

    state = {
        "current_mode": "PRESUPUESTO_MODE",
        "previous_mode": None,
        "mode_history": [],
        "mode_context": {
            "elemento_tentativo": {"codigo": "ESCAPE"},  # mode-private key
            "precio_comunicado": True,
        },
        "draft_contexts": {},
        "retry_state": {},
    }

    result = transition_mode(state, "EXPEDIENTE_MODE")

    # mode_context in the result must be wrapped in Overwrite
    mc = result.get("mode_context")
    assert isinstance(mc, Overwrite), (
        "mode_context in transition result must be wrapped in Overwrite()"
    )

    # The private key must not be in the new mode_context
    mc_value = mc.value if hasattr(mc, "value") else {}
    assert "elemento_tentativo" not in mc_value, (
        "Mode-private key 'elemento_tentativo' must be wiped on transition"
    )


# ---------------------------------------------------------------------------
# Test 5: Old checkpoint without shared_context defaults to {}
# ---------------------------------------------------------------------------


def test_old_checkpoint_without_shared_context_defaults():
    """
    A state dict from an old checkpoint (no shared_context key) must
    return {} when accessed via .get("shared_context"), ensuring backward compat.
    """
    # Simulate an old checkpoint that predates WS4
    old_state = {
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {"precio_comunicado": True},
        # NOTE: no "shared_context" key at all
    }

    # TypedDict with total=False makes all fields optional, so accessing a missing
    # key via .get() should return None (and we default to {})
    sc = old_state.get("shared_context") or {}
    assert sc == {}, (
        "Old checkpoint without shared_context must gracefully default to {}"
    )


# ---------------------------------------------------------------------------
# Test 6: CONTEXT_PRESERVE_RULES is deleted from mode_transitions
# ---------------------------------------------------------------------------


def test_context_preserve_rules_deleted():
    """
    CONTEXT_PRESERVE_RULES and get_preserve_keys must NOT exist on
    agent.router.mode_transitions after WS4 is implemented.
    """
    import agent.router.mode_transitions as mt

    assert not hasattr(mt, "CONTEXT_PRESERVE_RULES"), (
        "CONTEXT_PRESERVE_RULES must be deleted from mode_transitions — "
        "context preservation is now handled by shared_context + merge_dicts"
    )

    assert not hasattr(mt, "get_preserve_keys"), (
        "get_preserve_keys() must be deleted from mode_transitions"
    )
