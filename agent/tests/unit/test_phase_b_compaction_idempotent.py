"""
Unit tests for AC-10 — Idempotent start-of-turn Phase B compaction.

Spec R10: At POST_PRICE tool-loop entry (precio_comunicado=True), the system MUST
scan recent message history for verbose calcular_tarifa ToolMessages and compact
them in place. Idempotent: already-compact messages are not touched.

Tests the pure helper functions directly — no mocking needed.
"""
from __future__ import annotations

import json
import pytest

# Helpers to build ToolMessage-like objects
from langchain_core.messages import ToolMessage


def _make_verbose_toolmessage(content: str | None = None) -> ToolMessage:
    """Build a 'calcular_tarifa' ToolMessage with verbose content."""
    if content is None:
        # Default: verbose content with € sign and >500 chars
        content = json.dumps(
            {
                "success": True,
                "precio": 410.0,
                "texto": "El presupuesto es de *410€ +IVA*.",
                "texto_narrativo": "A" * 450,  # push over 500 total
                "datos": {"tier_id": "t1", "price": 410.0},
            },
            ensure_ascii=False,
        )
    return ToolMessage(
        content=content,
        tool_call_id="call-abc123",
        name="calcular_tarifa_con_elementos",
        id="msg-id-verbose",
    )


def _make_compact_toolmessage() -> ToolMessage:
    """Build an already-compact ToolMessage (≤200 chars, no €)."""
    content = json.dumps(
        {
            "success": True,
            "precio": 410.0,
            "elementos": ["escape"],
            "ya_comunicado": True,
            "note": "Narración comunicada — no re-narrar.",
        },
        ensure_ascii=False,
    )
    # Must be ≤200 chars and no €
    assert len(content) <= 200
    assert "€" not in content
    return ToolMessage(
        content=content,
        tool_call_id="call-abc123",
        name="calcular_tarifa_con_elementos",
        id="msg-id-compact",
    )


def _mc_compaction_on(**overrides) -> dict:
    """mc that triggers compaction predicate."""
    mc = {"precio_comunicado": True, "reprice_allowed_this_turn": False}
    mc.update(overrides)
    return mc


def _mc_compaction_off(**overrides) -> dict:
    """mc that suppresses compaction predicate."""
    mc = {"precio_comunicado": False}
    mc.update(overrides)
    return mc


class TestCompactionPredicate:
    """_should_compact_this_turn() predicate logic."""

    def test_predicate_true_when_precio_true_and_reprice_false(self):
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        mc = _mc_compaction_on()
        sc: dict = {}
        assert _should_compact_this_turn(mc, sc) is True

    def test_predicate_false_when_precio_false(self):
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        mc = _mc_compaction_off()
        sc: dict = {}
        assert _should_compact_this_turn(mc, sc) is False

    def test_predicate_false_when_reprice_allowed_true(self):
        """AC-10.3: compaction skipped when reprice_allowed_this_turn=True."""
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        mc = _mc_compaction_on(reprice_allowed_this_turn=True)
        sc: dict = {}
        assert _should_compact_this_turn(mc, sc) is False

    def test_predicate_false_when_both_absent(self):
        from agent.modes.pre_expediente_mode import _should_compact_this_turn

        assert _should_compact_this_turn({}, {}) is False


class TestCompactionScanner:
    """_compact_stale_tarifa_messages() scanner logic."""

    def test_verbose_toolmessage_compacted(self):
        """AC-10.1: verbose ToolMessage (>500 chars, contains €) → compacted."""
        from agent.modes.pre_expediente_mode import _compact_stale_tarifa_messages

        verbose_msg = _make_verbose_toolmessage()
        assert len(verbose_msg.content) > 500 or "€" in verbose_msg.content

        replacements = _compact_stale_tarifa_messages([verbose_msg])

        assert len(replacements) == 1, "Should produce exactly one replacement"
        replacement = replacements[0]
        assert len(replacement.content) <= 200, (
            f"Compact content must be ≤200 chars, got {len(replacement.content)}"
        )
        assert replacement.tool_call_id == verbose_msg.tool_call_id, (
            "tool_call_id must be preserved"
        )

    def test_already_compact_toolmessage_noop(self):
        """AC-10.2: compact ToolMessage (≤200 chars, no €) → unchanged, not replaced."""
        from agent.modes.pre_expediente_mode import _compact_stale_tarifa_messages

        compact_msg = _make_compact_toolmessage()
        replacements = _compact_stale_tarifa_messages([compact_msg])

        assert len(replacements) == 0, (
            "Already-compact message must NOT be replaced (idempotent)"
        )

    def test_non_tarifa_toolmessage_ignored(self):
        """Non-calcular_tarifa ToolMessages must be skipped."""
        from agent.modes.pre_expediente_mode import _compact_stale_tarifa_messages

        other_msg = ToolMessage(
            content="some long content with €" * 50,
            tool_call_id="call-other",
            name="enviar_imagenes_ejemplo",
            id="msg-other",
        )
        replacements = _compact_stale_tarifa_messages([other_msg])
        assert len(replacements) == 0

    def test_mixed_messages_only_verbose_tarifa_compacted(self):
        """Only verbose calcular_tarifa messages are replaced."""
        from agent.modes.pre_expediente_mode import _compact_stale_tarifa_messages

        verbose = _make_verbose_toolmessage()
        compact = _make_compact_toolmessage()
        other = ToolMessage(
            content="x" * 600,
            tool_call_id="call-other",
            name="enviar_imagenes_ejemplo",
            id="msg-other",
        )

        replacements = _compact_stale_tarifa_messages([verbose, compact, other])
        # Only the verbose calcular_tarifa message gets replaced
        assert len(replacements) == 1
        assert replacements[0].tool_call_id == verbose.tool_call_id

    def test_tool_call_id_preserved_in_replacement(self):
        """AC-10.1: replacement must preserve original tool_call_id."""
        from agent.modes.pre_expediente_mode import _compact_stale_tarifa_messages

        verbose = _make_verbose_toolmessage()
        original_call_id = verbose.tool_call_id

        replacements = _compact_stale_tarifa_messages([verbose])
        assert replacements[0].tool_call_id == original_call_id
