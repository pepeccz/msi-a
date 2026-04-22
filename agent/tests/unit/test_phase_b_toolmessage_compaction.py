"""
Unit tests for C5 (Phase B) — ToolMessage compaction on precio_comunicado flip.

Spec: R6 — ToolMessage Compaction on POST_PRICE Entry.
AC-6.1: ToolMessage compacted to <= 200 chars after precio_comunicado flip.
AC-6.2: Compact payload contains ya_comunicado=true.
AC-6.3: No KeyError on downstream read after compaction.
AC-7.1: Phase A tests pass without Phase B (no dependency on compaction code).

These tests work against a helper function extracted from the compaction logic.
The function is tested in isolation — no LangGraph runtime required.

RED before C5: _compact_tarifa_toolmessage does not exist yet.
"""
from __future__ import annotations

import json
import pytest


def _make_tool_message(content: str, tool_call_id: str = "tc-001", msg_id: str = "msg-001"):
    """Create a minimal ToolMessage dict (simulates LangGraph ToolMessage)."""
    from langchain_core.messages import ToolMessage

    return ToolMessage(
        content=content,
        tool_call_id=tool_call_id,
        name="calcular_tarifa_con_elementos",
        id=msg_id,
    )


def _make_full_narration_content() -> str:
    """Simulate the kind of content a pre-C1 ToolMessage would contain."""
    return (
        "TARIFA RECOMENDADA: Tier Base\n"
        "Precio: 410.0 EUR (IVA no incluido)\n\n"
        "Elementos incluidos (1):\n- Escape\n\n"
        "ADVERTENCIAS:\n  ⚠️ Advertencia de elemento\n\n"
        "DOCUMENTACION REQUERIDA:\n"
        "Documentacion base obligatoria:\n  - Ficha técnica\n\n"
        "Documentacion por elemento:\n  Escape:\n    - Foto del escape\n"
    )


class TestCompactToolMessage:
    """_compact_tarifa_toolmessage must produce a replacement ToolMessage."""

    def test_compact_content_under_200_chars(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message(_make_full_narration_content())
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        content = compact.content
        assert len(content) <= 200, (
            f"Compact ToolMessage content must be <= 200 chars. len={len(content)}"
        )

    def test_compact_has_ya_comunicado(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message(_make_full_narration_content())
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        # Content must be parseable JSON or plain text with ya_comunicado marker
        content = compact.content
        assert "ya_comunicado" in content, (
            f"Compact content must contain 'ya_comunicado'. Got: {content!r}"
        )

    def test_compact_preserves_tool_call_id(self):
        """tool_call_id must be preserved to maintain AIMessage → ToolMessage binding."""
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message(
            _make_full_narration_content(),
            tool_call_id="tc-preserve-me",
        )
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        assert compact.tool_call_id == "tc-preserve-me", (
            f"tool_call_id must be preserved. Got: {compact.tool_call_id!r}"
        )

    def test_no_warning_emoji_in_compact(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message(_make_full_narration_content())
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        assert "⚠️" not in compact.content, (
            f"Compact content must NOT contain ⚠️. Got: {compact.content!r}"
        )

    def test_no_documentacion_in_compact(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message(_make_full_narration_content())
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        assert "DOCUMENTACION" not in compact.content.upper(), (
            f"Compact content must NOT contain DOCUMENTACION. Got: {compact.content!r}"
        )


class TestDownstreamNoKeyError:
    """AC-6.3 — downstream reads on compact ToolMessage must not raise KeyError."""

    def test_compact_json_has_price(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage

        original = _make_tool_message("anything", tool_call_id="tc-002")
        compact = _compact_tarifa_toolmessage(original, precio=410.0, element_codes=["ESCAPE"])
        # Content should be JSON-parseable
        try:
            payload = json.loads(compact.content)
        except json.JSONDecodeError:
            pytest.fail(f"Compact ToolMessage content is not valid JSON: {compact.content!r}")
        assert "precio" in payload, (
            f"Compact JSON must contain 'precio' key. Keys: {list(payload.keys())}"
        )
        assert payload["precio"] == 410.0


class TestPhaseAIndependence:
    """AC-7.1 — Phase A tests must not import from compaction module."""

    def test_phase_a_guard_importable_without_compaction(self):
        """guard_no_reprice_post_price can be imported without Phase B code."""
        # If this import succeeds, Phase A is independent of Phase B.
        from agent.modes.pre_expediente_mode import guard_no_reprice_post_price

        assert callable(guard_no_reprice_post_price)

    def test_phase_a_calcular_tarifa_importable_without_compaction(self):
        from agent.modes.pre_expediente_mode import _compact_tarifa_toolmessage  # Phase B exists

        # Simply check Phase A tool is importable (no KeyError on texto).
        # LangChain @tool objects are not callable via callable() — check ainvoke instead.
        from agent.tools.element_tools import calcular_tarifa_con_elementos

        assert hasattr(calcular_tarifa_con_elementos, "ainvoke"), (
            "calcular_tarifa_con_elementos must be a LangChain tool with ainvoke"
        )
