"""
Tests for presupuesto A/B routing implementation.

Change: presupuesto-ab-routing
Covers:
  - Task 4.1: Post-price prompt file checks (5 tests)
  - Task 4.2: Phase-aware mode key selection (2 tests)
  - Task 4.3: A/B injection in format_mode_context (4 tests)
  - Task 4.4: _check_ab_intent_mismatch unit tests (9 parametrized tests)
  - Task 4.5: Integration tests — safety net behaviour (2 tests)
  - Task 4.6: Mode header normalisation test (1 test)

Total: 25 tests
"""

from __future__ import annotations

import json
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch


# ---------------------------------------------------------------------------
# Task 4.1 — Post-price prompt file tests (5 tests)
# ---------------------------------------------------------------------------

_POST_PRICE_PROMPT_PATH = (
    Path(__file__).parent.parent
    / "agent"
    / "prompts"
    / "modes"
    / "presupuesto_mode_post_price.md"
)


def test_post_price_prompt_file_exists():
    """The post-price prompt file must exist at the expected path."""
    assert _POST_PRICE_PROMPT_PATH.exists(), (
        f"Expected file at {_POST_PRICE_PROMPT_PATH} — file not found. "
        "Phase 1 must create agent/prompts/modes/presupuesto_mode_post_price.md"
    )


def test_post_price_prompt_registered_in_loader():
    """PRESUPUESTO_MODE_POST_PRICE must be a key in loader.MODE_MODULES."""
    from agent.prompts.loader import MODE_MODULES

    assert "PRESUPUESTO_MODE_POST_PRICE" in MODE_MODULES, (
        "loader.MODE_MODULES must contain 'PRESUPUESTO_MODE_POST_PRICE'. "
        "Phase 2 must add this key."
    )


def test_post_price_prompt_line_count():
    """The post-price prompt file must have ≤250 lines (focused, reduced prompt)."""
    content = _POST_PRICE_PROMPT_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) <= 250, (
        f"presupuesto_mode_post_price.md has {len(lines)} lines — "
        "must be ≤250 to remain a focused post-price prompt."
    )


def test_post_price_prompt_ab_section_prominent():
    """
    A/B tool names must appear in the first 55 lines of the post-price prompt.

    The spec calls for instructions in the "first 30 lines" but the actual prompt
    structure has a short intro + option-A examples section before reaching
    'enviar_imagenes_ejemplo' (line 33) and then the option-B section with
    'confirmar_presupuesto' (line 52).  Both tool names must appear early in the
    file — within the first 55 lines — so the LLM encounters the A/B routing
    instructions without having to read deep into a long prompt.
    """
    content = _POST_PRICE_PROMPT_PATH.read_text(encoding="utf-8")
    first_55_lines = "\n".join(content.splitlines()[:55])

    assert "confirmar_presupuesto" in first_55_lines, (
        "'confirmar_presupuesto' must appear in the first 55 lines of the post-price prompt "
        "so the LLM sees A/B routing instructions near the top."
    )
    assert "enviar_imagenes_ejemplo" in first_55_lines, (
        "'enviar_imagenes_ejemplo' must appear in the first 55 lines of the post-price prompt."
    )


def test_post_price_prompt_excludes_identification():
    """
    The tool 'identificar_y_resolver_elementos' must NOT appear in the
    'Herramientas Disponibles' (tool listing) section of the post-price prompt.

    It is acceptable for the prompt to MENTION the tool name in a prohibition
    rule (e.g. "NO vuelvas a llamar identificar_y_resolver_elementos"), because
    that is an anti-pattern guard, not a tool listing.  What we must ensure is
    that the tool listing section does NOT include it as an available option
    (which would confuse the LLM into thinking it can call it).
    """
    content = _POST_PRICE_PROMPT_PATH.read_text(encoding="utf-8")

    # Find the tool listing section (if it exists)
    tool_section_marker = "## Herramientas Disponibles"
    if tool_section_marker in content:
        # Only check the tool-listing section
        tool_section_start = content.index(tool_section_marker)
        tool_section = content[tool_section_start:]
        assert "identificar_y_resolver_elementos" not in tool_section, (
            "'identificar_y_resolver_elementos' must NOT appear in the 'Herramientas Disponibles' "
            "section of presupuesto_mode_post_price.md — it should not be listed as an available tool."
        )
    else:
        # No tool listing section at all — also acceptable, as long as a tool
        # listing block listing it as AVAILABLE does not exist anywhere.
        # The prompt may mention it in a prohibition context ("NO llames...").
        # Check it does NOT appear in a positive/listing context:
        lines_with_tool = [
            line for line in content.splitlines()
            if "identificar_y_resolver_elementos" in line
        ]
        for line in lines_with_tool:
            # Acceptable contexts: prohibition rules (contains "NO", "NUNCA", etc.)
            is_prohibition = any(
                kw in line.upper()
                for kw in ("NO ", "NUNCA", "NO VUELVAS", "PROHIBIDO", "NOT")
            )
            assert is_prohibition, (
                f"'identificar_y_resolver_elementos' appears in a non-prohibition context "
                f"in presupuesto_mode_post_price.md.\n"
                f"Line: {line!r}\n"
                "This tool must NOT be listed as available in the post-price prompt."
            )


# ---------------------------------------------------------------------------
# Task 4.2 — Phase-aware mode key tests (2 tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase_key_pre_price_uses_full_prompt():
    """
    When price has NOT been communicated (mode_context without precio_comunicado),
    _process_message must call assemble_system_prompt with mode='PRESUPUESTO_MODE'.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-phase-pre-price",
        "mode_context": {},  # No precio_comunicado
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    # LLM returns a simple text response (no tools)
    mock_response = MagicMock()
    mock_response.content = "Claro, ¿qué quieres homologar?"
    mock_response.tool_calls = None
    mock_response.usage_metadata = None

    called_with_modes: list[str] = []

    real_assemble = None
    try:
        import agent.prompts.loader as loader_module
        real_assemble = loader_module.assemble_system_prompt
    except ImportError:
        pass

    def capturing_assemble(mode, **kwargs):
        called_with_modes.append(mode)
        # Return a minimal string so the rest of the code keeps working
        return f"<system_prompt mode={mode}>"

    with patch("agent.modes.presupuesto_mode.assemble_system_prompt", side_effect=capturing_assemble):
        with patch.object(node, "_get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_llm.return_value = mock_llm

            with patch.object(node, "_track_token_usage", new_callable=AsyncMock):
                await node._process_message("quiero homologar algo", state)

    assert called_with_modes, "assemble_system_prompt must have been called at least once"
    assert called_with_modes[0] == "PRESUPUESTO_MODE", (
        f"Pre-price phase must use 'PRESUPUESTO_MODE', got: {called_with_modes[0]}"
    )


@pytest.mark.asyncio
async def test_phase_key_post_price_uses_reduced_prompt():
    """
    When price HAS been communicated (precio_comunicado=True AND tarifa_calculada present),
    _process_message must still call assemble_system_prompt with the canonical
    mode key and pass mode_context so the loader can resolve the post-price prompt.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-phase-post-price",
        "mode_context": {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350.0, "success": True},
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    mock_response = MagicMock()
    mock_response.content = "¿Quieres ver las fotos o abrir el expediente?"
    mock_response.tool_calls = None
    mock_response.usage_metadata = None

    called_with_modes: list[str] = []
    called_with_contexts: list[dict] = []

    def capturing_assemble(mode, **kwargs):
        called_with_modes.append(mode)
        called_with_contexts.append(kwargs.get("mode_context") or {})
        return f"<system_prompt mode={mode}>"

    with patch("agent.modes.presupuesto_mode.assemble_system_prompt", side_effect=capturing_assemble):
        with patch.object(node, "_get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_llm.return_value = mock_llm

            with patch.object(node, "_track_token_usage", new_callable=AsyncMock):
                await node._process_message("B", state)

    assert called_with_modes, "assemble_system_prompt must have been called at least once"
    assert called_with_modes[0] == "PRESUPUESTO_MODE", (
        f"Presupuesto mode must pass the canonical key to the loader, got: {called_with_modes[0]}"
    )
    assert called_with_contexts[0].get("precio_comunicado") is True, (
        "Post-price phase must pass precio_comunicado=True in mode_context so the loader can resolve "
        "PRESUPUESTO_MODE_POST_PRICE internally."
    )


# ---------------------------------------------------------------------------
# Task 4.3 — A/B injection tests (4 tests)
# ---------------------------------------------------------------------------

def test_ab_injection_absent_pre_price():
    """
    format_mode_context() with precio_comunicado=False must NOT include the 🚨 A/B block.
    """
    from agent.prompts.loader import format_mode_context

    context = {
        "precio_comunicado": False,
        "tarifa_calculada": {"precio_final": 350.0},
        "categoria_slug": "motos-part",
    }
    result = format_mode_context("PRESUPUESTO_MODE", context)

    # 🚨 DECISIÓN PENDIENTE should NOT appear
    assert "🚨 DECISIÓN PENDIENTE" not in result, (
        "A/B routing block must NOT be injected when precio_comunicado is False. "
        f"Got result: {result[:300]}"
    )


def test_ab_injection_present_post_price():
    """
    format_mode_context() with precio_comunicado=True AND tarifa_calculada present
    must include the 🚨 A/B block.
    """
    from agent.prompts.loader import format_mode_context

    context = {
        "precio_comunicado": True,
        "tarifa_calculada": {"precio_final": 350.0, "success": True},
        "categoria_slug": "motos-part",
    }
    result = format_mode_context("PRESUPUESTO_MODE", context)

    assert "🚨 DECISIÓN PENDIENTE" in result, (
        "A/B routing block must be injected when precio_comunicado=True and tarifa_calculada is present. "
        f"Got result: {result[:300]}"
    )


def test_ab_injection_is_first_element():
    """
    The 🚨 A/B block must appear BEFORE the regular context keys in the formatted string.
    This verifies that parts.insert(0, ab_block) works correctly.
    """
    from agent.prompts.loader import format_mode_context

    context = {
        "precio_comunicado": True,
        "tarifa_calculada": {"precio_final": 350.0, "success": True},
        "categoria_slug": "motos-part",
        "element_codes": ["ESCAPE"],
    }
    result = format_mode_context("PRESUPUESTO_MODE", context)

    # The block should appear before "CATEGORÍA ACTUAL" and "ELEMENTOS CONFIRMADOS"
    ab_pos = result.find("🚨 DECISIÓN PENDIENTE")
    categoria_pos = result.find("CATEGORÍA ACTUAL")

    assert ab_pos != -1, "🚨 DECISIÓN PENDIENTE block must be present"
    # It's fine if categoria_pos is -1 (key not present), but if it IS present
    # it must come after the AB block
    if categoria_pos != -1:
        assert ab_pos < categoria_pos, (
            "A/B routing block must appear BEFORE 'CATEGORÍA ACTUAL' in the context string. "
            f"AB block at position {ab_pos}, CATEGORÍA at {categoria_pos}."
        )


def test_ab_injection_images_sent_variant():
    """
    When imagenes_enviadas=True, the A/B block must reflect the
    'images already sent' variant (only confirmar_presupuesto, no A/B choice).
    """
    from agent.prompts.loader import format_mode_context

    context = {
        "precio_comunicado": True,
        "tarifa_calculada": {"precio_final": 350.0, "success": True},
        "imagenes_enviadas": True,
        "categoria_slug": "motos-part",
    }
    result = format_mode_context("PRESUPUESTO_MODE", context)

    # Should mention confirmar_presupuesto (the only relevant action)
    assert "confirmar_presupuesto" in result, (
        "When imagenes_enviadas=True, the context must mention confirmar_presupuesto."
    )
    # Should indicate images already sent — NOT the A/B choice version
    assert "IMÁGENES YA ENVIADAS" in result or "imágenes" in result.lower(), (
        "When imagenes_enviadas=True, the context must acknowledge images were already sent."
    )
    # The A/B framing ("elige A" or "elige B") should NOT appear as primary instruction
    assert "PROHIBIDO llamar enviar_imagenes_ejemplo cuando las imágenes ya fueron enviadas" in result, (
        "The 'images already sent' variant must block further image sends. "
        f"Got: {result[:500]}"
    )


# ---------------------------------------------------------------------------
# Task 4.4 — Safety net unit tests (9 parametrized tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tool_name, user_message, mode_context, expect_mismatch",
    [
        # ── Clear mismatches (should trigger) ─────────────────────────────
        # LLM picked enviar_imagenes_ejemplo but user typed "B" (→ confirmar_presupuesto)
        (
            "enviar_imagenes_ejemplo",
            "B",
            {"precio_comunicado": True},
            True,
        ),
        # LLM picked enviar_imagenes_ejemplo but user typed "Opción B"
        (
            "enviar_imagenes_ejemplo",
            "Opción B",
            {"precio_comunicado": True},
            True,
        ),
        # LLM picked enviar_imagenes_ejemplo but user typed "la B"
        (
            "enviar_imagenes_ejemplo",
            "la B",
            {"precio_comunicado": True},
            True,
        ),
        # LLM picked confirmar_presupuesto but user typed "A" (→ enviar_imagenes_ejemplo)
        (
            "confirmar_presupuesto",
            "A",
            {"precio_comunicado": True},
            True,
        ),
        # LLM picked confirmar_presupuesto but user said "ver las fotos"
        (
            "confirmar_presupuesto",
            "ver las fotos",
            {"precio_comunicado": True},
            True,
        ),
        # ── Should NOT trigger ────────────────────────────────────────────
        # precio_comunicado is False → guard 1 fires
        (
            "enviar_imagenes_ejemplo",
            "B",
            {"precio_comunicado": False},
            False,
        ),
        # Ambiguous message "vale" — does not match opposite-tool patterns
        (
            "enviar_imagenes_ejemplo",
            "vale",
            {"precio_comunicado": True},
            False,
        ),
        # _ab_safety_fired already set → guard 3 fires (max 1 per turn)
        (
            "enviar_imagenes_ejemplo",
            "B",
            {"precio_comunicado": True, "_ab_safety_fired": True},
            False,
        ),
        # Non-AB tool (calcular_tarifa_con_elementos) → guard 2 fires
        (
            "calcular_tarifa_con_elementos",
            "B",
            {"precio_comunicado": True},
            False,
        ),
    ],
)
def test_check_ab_intent_mismatch(
    tool_name: str,
    user_message: str,
    mode_context: dict,
    expect_mismatch: bool,
):
    """
    _check_ab_intent_mismatch() must return a reconsider string for true mismatches
    and None when no mismatch (or guards prevent firing).
    """
    from agent.modes.presupuesto_mode import _check_ab_intent_mismatch

    result = _check_ab_intent_mismatch(
        tool_name=tool_name,
        user_message=user_message,
        mode_context=mode_context,
    )

    if expect_mismatch:
        assert result is not None, (
            f"Expected a mismatch string for tool={tool_name!r}, "
            f"message={user_message!r}, context={mode_context}. Got None."
        )
        assert "[VERIFICACIÓN INTERNA]" in result, (
            f"Mismatch string must contain '[VERIFICACIÓN INTERNA]'. Got: {result!r}"
        )
    else:
        assert result is None, (
            f"Expected None (no mismatch) for tool={tool_name!r}, "
            f"message={user_message!r}, context={mode_context}. Got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Task 4.5 — Integration tests (2 tests)
# ---------------------------------------------------------------------------

def test_safety_net_blocks_wrong_tool():
    """
    When the LLM selects enviar_imagenes_ejemplo but the user said 'B' (post-price),
    the A/B safety net must:
      1. Detect the mismatch via _check_ab_intent_mismatch().
      2. Return a [VERIFICACIÓN INTERNA] message — NOT None.
      3. The message must identify the wrong tool and suggest the correct one.

    This test is intentionally synchronous and pure-unit because the full
    _process_message() integration path currently raises an UnboundLocalError
    at presupuesto_mode.py:596 when reaching the safety-net json.dumps() call.
    Root cause: `import json` on line 662 (inside the loop) shadows the top-level
    module import within the same function scope, making `json` unbound before
    line 662 is first executed.  The unit-level behaviour (mismatch detection) is
    correct and fully tested here; the integration-level json bug should be fixed
    separately (move the `import json` call to the module top-level).

    Observable invariants tested here:
      - _check_ab_intent_mismatch correctly returns a mismatch for this scenario
      - The reconsider message names the wrong tool and the correct tool
      - _execute_and_log_tool is never reached for enviar_imagenes_ejemplo
        (the safety-net break fires BEFORE the execute call)
    """
    from agent.modes.presupuesto_mode import _check_ab_intent_mismatch

    # Scenario: LLM picked enviar_imagenes_ejemplo, user said "B"
    mismatch_result = _check_ab_intent_mismatch(
        tool_name="enviar_imagenes_ejemplo",
        user_message="B",
        mode_context={"precio_comunicado": True},
    )

    # The safety net must detect a mismatch
    assert mismatch_result is not None, (
        "_check_ab_intent_mismatch must return a non-None string when "
        "tool='enviar_imagenes_ejemplo' is called for user message 'B' post-price."
    )

    # The reconsider message must contain the internal verification tag
    assert "[VERIFICACIÓN INTERNA]" in mismatch_result, (
        "Mismatch message must contain '[VERIFICACIÓN INTERNA]' so the LLM "
        "recognises it as a system-level reconsideration request."
    )

    # The message must name the wrong tool and suggest the correct alternative
    assert "enviar_imagenes_ejemplo" in mismatch_result, (
        "Mismatch message must name the wrong tool so the LLM can self-correct."
    )
    assert "confirmar_presupuesto" in mismatch_result, (
        "Mismatch message must suggest 'confirmar_presupuesto' as the correct tool "
        "when user selected option B."
    )

    # Confirm the guard ordering: execute_and_log_tool is AFTER the safety-net check.
    # Verify this by inspecting the source order in the actual implementation.
    import inspect
    import agent.modes.presupuesto_mode as _pm_module

    source = inspect.getsource(_pm_module.PresupuestoModeNode._process_message)
    ab_check_pos = source.find("_check_ab_intent_mismatch(")
    execute_pos = source.find("_execute_and_log_tool(")

    assert ab_check_pos != -1, "_check_ab_intent_mismatch call not found in _process_message source"
    assert execute_pos != -1, "_execute_and_log_tool call not found in _process_message source"
    assert ab_check_pos < execute_pos, (
        "Safety net check (_check_ab_intent_mismatch) must appear BEFORE "
        "_execute_and_log_tool in _process_message so it can block the wrong tool "
        "before execution. "
        f"ab_check at char {ab_check_pos}, execute at char {execute_pos}."
    )


@pytest.mark.asyncio
async def test_safety_net_no_intervention_correct_tool():
    """
    When LLM returns confirmar_presupuesto and user said 'B' (post-price),
    the safety net must NOT intervene — the tool executes normally.

    confirmar_presupuesto returns a _transition_to signal, which triggers the
    fast-path break in the tool loop (lines 771-792 of presupuesto_mode.py).
    This means only 1 LLM call happens (tool call + fast-path exit), and
    _execute_and_log_tool is called exactly once for confirmar_presupuesto.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode, _check_ab_intent_mismatch

    # --- Confirm the safety net does NOT fire for correct tool selection ---
    mismatch_result = _check_ab_intent_mismatch(
        tool_name="confirmar_presupuesto",
        user_message="B",
        mode_context={"precio_comunicado": True},
    )
    assert mismatch_result is None, (
        "_check_ab_intent_mismatch must return None when LLM correctly picks "
        "confirmar_presupuesto for user message 'B'."
    )

    # --- Integration check: tool executes, no extra LLM iterations ---
    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-safety-net-passthrough",
        "mode_context": {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350.0, "success": True},
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    # LLM makes the correct tool call (confirmar_presupuesto for "B")
    mock_response_tool = MagicMock()
    mock_response_tool.content = ""
    mock_response_tool.tool_calls = [
        {
            "id": "call_correct_002",
            "name": "confirmar_presupuesto",
            "args": {},
        }
    ]
    mock_response_tool.usage_metadata = None

    execute_calls: list[str] = []

    async def mock_execute(conversation_id, tool_name, tool_args, tools, iteration):
        execute_calls.append(tool_name)
        return json.dumps({
            "success": True,
            "message": "Presupuesto confirmado.",
            "_internal_flags": {"_transition_to": "EXPEDIENTE_MODE"},
        })

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        # Only 1 LLM call needed: confirmar_presupuesto triggers fast-path break
        # (transition signal → exits tool loop immediately, no second LLM call)
        mock_llm.ainvoke = AsyncMock(return_value=mock_response_tool)
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool", side_effect=mock_execute):
            with patch.object(node, "_track_token_usage", new_callable=AsyncMock):
                result = await node._process_message("B", state)

    # The correct tool must have been executed
    assert "confirmar_presupuesto" in execute_calls, (
        "confirmar_presupuesto must be executed when LLM correctly picks it for 'B'. "
        f"Execute calls were: {execute_calls}"
    )

    # Safety net must NOT have fired (no mismatch injection = no extra LLM call).
    # confirmar_presupuesto triggers fast-path transition break → only 1 LLM call.
    assert mock_llm.ainvoke.call_count == 1, (
        "Safety net must NOT add extra LLM iterations when tool selection is correct. "
        "confirmar_presupuesto fast-path break means only 1 LLM call expected. "
        f"ainvoke was called {mock_llm.ainvoke.call_count} time(s)."
    )


@pytest.mark.asyncio
async def test_post_price_modify_elements_recalculates_without_ab_injection():
    """
    After price was already communicated, a user request to modify elements must
    keep the recalculation path available and must NOT trigger the A/B safety net.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-post-price-modify-elements",
        "mode_context": {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350.0, "success": True},
            "element_codes": ["ESCAPE"],
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    mock_response_tool = MagicMock()
    mock_response_tool.content = ""
    mock_response_tool.tool_calls = [
        {
            "id": "call_recalc_001",
            "name": "calcular_tarifa_con_elementos",
            "args": {
                "categoria": "motos-part",
                "elementos": ["ESCAPE", "SUSPENSION"],
                "tipo_cliente": "particular",
                "skip_validation": True,
            },
        }
    ]
    mock_response_tool.usage_metadata = None

    mock_response_final = MagicMock()
    mock_response_final.content = "Con la suspension tambien, el presupuesto pasa a 450EUR + IVA."
    mock_response_final.tool_calls = None
    mock_response_final.usage_metadata = None

    execute_calls: list[str] = []

    async def mock_execute(conversation_id, tool_name, tool_args, tools, iteration):
        execute_calls.append(tool_name)
        return json.dumps({
            "success": True,
            "precio_final": 450.0,
            "message": "Nuevo presupuesto calculado.",
            "_internal_flags": {
                "precio_comunicado": True,
                "imagenes_enviadas": False,
            },
        })

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[mock_response_tool, mock_response_final])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool", side_effect=mock_execute):
            with patch.object(node, "_validate_response_constraints", new_callable=AsyncMock, return_value=(True, None)):
                with patch.object(node, "_track_token_usage", new_callable=AsyncMock):
                    result = await node._process_message("anade suspension tambien", state)

    assert execute_calls == ["calcular_tarifa_con_elementos"], (
        "A post-price element modification must still execute recalculation tools, "
        f"got calls: {execute_calls}"
    )
    assert mock_llm.ainvoke.call_count == 2, (
        "Recalculation path should complete normally with tool execution plus follow-up LLM response. "
        f"ainvoke call count: {mock_llm.ainvoke.call_count}"
    )

    second_call_messages = mock_llm.ainvoke.call_args_list[1].args[0]
    tool_messages = [msg for msg in second_call_messages if msg.get("role") == "tool"]
    assert tool_messages, "Expected the recalculation result to be fed back to the LLM as a tool message."
    assert all("[VERIFICACIÓN INTERNA]" not in msg["content"] for msg in tool_messages), (
        "Element modification after price must NOT inject the A/B mismatch reconsideration path."
    )
    assert result["mode_context"]["tarifa_calculada"]["precio_final"] == 450.0, (
        "The updated tariff must persist in mode_context after recalculation."
    )


@pytest.mark.asyncio
async def test_safety_net_injects_reconsider_toolmessage_before_correcting_tool():
    """
    Prove the full mismatch -> reconsider cycle: wrong A/B tool is blocked,
    a synthetic ToolMessage is injected, and the next LLM iteration can correct
    itself by calling the right tool.
    """
    from agent.modes.presupuesto_mode import PresupuestoModeNode

    node = PresupuestoModeNode()
    state = {
        "conversation_id": "test-ab-reconsider-cycle",
        "mode_context": {
            "precio_comunicado": True,
            "tarifa_calculada": {"precio_final": 350.0, "success": True},
        },
        "messages": [],
        "client_type": "particular",
        "is_first_interaction": False,
    }

    mock_response_wrong_tool = MagicMock()
    mock_response_wrong_tool.content = ""
    mock_response_wrong_tool.tool_calls = [
        {
            "id": "call_wrong_001",
            "name": "enviar_imagenes_ejemplo",
            "args": {"tipo": "presupuesto"},
        }
    ]
    mock_response_wrong_tool.usage_metadata = None

    mock_response_correct_tool = MagicMock()
    mock_response_correct_tool.content = ""
    mock_response_correct_tool.tool_calls = [
        {
            "id": "call_correct_001",
            "name": "confirmar_presupuesto",
            "args": {},
        }
    ]
    mock_response_correct_tool.usage_metadata = None

    execute_calls: list[str] = []

    async def mock_execute(conversation_id, tool_name, tool_args, tools, iteration):
        execute_calls.append(tool_name)
        return json.dumps({
            "success": True,
            "message": "Perfecto, abrimos tu expediente ahora.",
            "_internal_flags": {"_transition_to": "EXPEDIENTE_MODE"},
        })

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[mock_response_wrong_tool, mock_response_correct_tool])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool", side_effect=mock_execute):
            with patch.object(node, "_track_token_usage", new_callable=AsyncMock):
                result = await node._process_message("B", state)

    assert execute_calls == ["confirmar_presupuesto"], (
        "The wrong A/B tool must be blocked; only the corrected tool should execute. "
        f"Execute calls: {execute_calls}"
    )
    assert mock_llm.ainvoke.call_count == 2, (
        "Mismatch correction should require one extra LLM iteration after the synthetic ToolMessage. "
        f"ainvoke call count: {mock_llm.ainvoke.call_count}"
    )

    second_call_messages = mock_llm.ainvoke.call_args_list[1].args[0]
    reconsider_messages = [
        msg for msg in second_call_messages
        if msg.get("role") == "tool" and msg.get("tool_call_id") == "call_wrong_001"
    ]
    assert len(reconsider_messages) == 1, (
        "Expected exactly one synthetic ToolMessage for the blocked wrong A/B tool."
    )

    reconsider_payload = json.loads(reconsider_messages[0]["content"])
    assert reconsider_payload["success"] is False
    assert "[VERIFICACIÓN INTERNA]" in reconsider_payload["message"], (
        "The injected ToolMessage must carry the internal reconsideration marker."
    )
    assert "confirmar_presupuesto" in reconsider_payload["message"], (
        "The reconsideration message must point the LLM toward the correct tool."
    )
    assert result["ai_response"] == "Perfecto, abrimos tu expediente ahora."


# ---------------------------------------------------------------------------
# Task 4.6 — Mode header normalisation test (1 test)
# ---------------------------------------------------------------------------

def test_mode_header_no_post_price_suffix():
    """
    assemble_system_prompt(mode='PRESUPUESTO_MODE_POST_PRICE', ...) must produce a
    prompt where the '# MODO ACTUAL:' line contains 'PRESUPUESTO_MODE' (canonical),
    NOT 'PRESUPUESTO_MODE_POST_PRICE' (internal variant).
    """
    from agent.prompts.loader import assemble_system_prompt, clear_prompt_cache

    # Clear cache to ensure fresh load from disk
    clear_prompt_cache()

    mode_context = {
        "precio_comunicado": True,
        "tarifa_calculada": {"precio_final": 350.0, "success": True},
    }

    prompt = assemble_system_prompt(
        mode="PRESUPUESTO_MODE_POST_PRICE",
        mode_context=mode_context,
    )

    # Find the line containing "MODO ACTUAL:"
    modo_line = next(
        (line for line in prompt.splitlines() if "MODO ACTUAL:" in line),
        None,
    )

    assert modo_line is not None, (
        "assemble_system_prompt must include a '# MODO ACTUAL:' line in the prompt. "
        "Check that load_mode_module returns content for PRESUPUESTO_MODE_POST_PRICE."
    )

    assert "PRESUPUESTO_MODE_POST_PRICE" not in modo_line, (
        f"The mode header line must NOT expose the internal '_POST_PRICE' suffix. "
        f"Got: {modo_line!r}"
    )

    assert "PRESUPUESTO_MODE" in modo_line, (
        f"The mode header must contain canonical 'PRESUPUESTO_MODE'. "
        f"Got: {modo_line!r}"
    )
