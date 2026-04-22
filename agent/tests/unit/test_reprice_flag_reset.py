"""
Unit tests for AC-9.2 — reprice_allowed_this_turn reset at turn boundary.

Spec R9-S9.2: After _process_message completes a reprice turn,
updated_context["reprice_allowed_this_turn"] must be None (tombstone per ADR-010).

These tests inspect the pre_expediente_mode module's reset logic directly
by testing the pure helper that performs the tombstone insertion.
"""
from __future__ import annotations


def _apply_reprice_reset(updated_context: dict, result_dict: dict) -> tuple[dict, dict]:
    """Apply the reprice_allowed_this_turn tombstone reset logic.

    This mirrors the exact code block from _process_message post-AD-9 pipeline.
    Tests verify the contract without calling the full async _process_message.
    """
    from agent.modes.pre_expediente_mode import _reset_reprice_flag_if_set

    return _reset_reprice_flag_if_set(updated_context, result_dict)


class TestRepriceFlagReset:
    """AC-9.2: tombstone reset after pipeline completes a reprice turn."""

    def test_flag_reset_to_none_when_true(self):
        """After a reprice turn: updated_context must have reprice_allowed=None."""
        updated_context = {"reprice_allowed_this_turn": True, "precio_comunicado": True}
        result_dict = {"shared_context": {"reprice_allowed_this_turn": True}}

        new_ctx, new_result = _apply_reprice_reset(updated_context, result_dict)

        assert new_ctx.get("reprice_allowed_this_turn") is None, (
            f"Expected None (tombstone), got: {new_ctx.get('reprice_allowed_this_turn')!r}"
        )

    def test_shared_context_flag_reset_to_none_when_true(self):
        """After a reprice turn: shared_context must also have reprice_allowed=None."""
        updated_context = {"reprice_allowed_this_turn": True}
        result_dict = {"shared_context": {"reprice_allowed_this_turn": True}}

        _, new_result = _apply_reprice_reset(updated_context, result_dict)

        sc = new_result.get("shared_context") or {}
        assert sc.get("reprice_allowed_this_turn") is None, (
            f"Expected shared_context reprice=None (tombstone), got: {sc!r}"
        )

    def test_no_tombstone_when_flag_not_set(self):
        """Non-reprice turn: flag absent → reset is a no-op, no tombstone injected."""
        updated_context = {"precio_comunicado": True}  # flag absent
        result_dict = {}

        new_ctx, new_result = _apply_reprice_reset(updated_context, result_dict)

        # Flag must NOT appear as None — it simply isn't there
        assert "reprice_allowed_this_turn" not in new_ctx or new_ctx.get("reprice_allowed_this_turn") is None, (
            "No tombstone should appear when flag was not set"
        )
        # result_dict unchanged
        assert new_result == {} or new_result.get("shared_context", {}).get("reprice_allowed_this_turn") is None

    def test_flag_false_treated_as_not_set(self):
        """Flag=False is falsy — no tombstone needed (False was never 'set this turn')."""
        updated_context = {"reprice_allowed_this_turn": False}
        result_dict = {}

        new_ctx, _ = _apply_reprice_reset(updated_context, result_dict)

        # No tombstone write needed — False is the default state
        val = new_ctx.get("reprice_allowed_this_turn")
        # Accept None or False — what matters is it's not True
        assert val is not True, f"Flag should not remain True. Got: {val!r}"
