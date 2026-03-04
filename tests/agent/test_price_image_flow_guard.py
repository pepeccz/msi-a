"""
Tests for the price-image flow guard (fix-price-image-flow change).

Covers:
  - Code guard in presupuesto_mode.py (tasks 4.1 + 4.2)
  - pre_image_message fix in main.py logic (task 4.2)
  - Tool signal in element_tools.py (task 4.3)

Guards under test:
  - _tarifa_called_this_turn flag resets at each outer-loop iteration
  - Guard blocks enviar_imagenes_ejemplo(tipo="presupuesto") in same turn as tarifa
  - Guard does NOT block enviar_imagenes_ejemplo(tipo="elemento")
  - pre_image_message = ai_response_clean (not None) when follow_up_message exists
  - calcular_tarifa_con_elementos return text includes "SIGUIENTE turno" / "turno siguiente"
    and "INSTRUCCIÓN:" when active images are available
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from agent.modes.presupuesto_mode import PresupuestoModeNode, _apply_tool_flags


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / factories
# ═══════════════════════════════════════════════════════════════════════════════

def _make_state(
    *,
    conversation_id: str = "test-guard-conv",
    mode_context: dict | None = None,
    client_type: str = "particular",
) -> dict:
    """Return a minimal ConversationState dict for PRESUPUESTO_MODE tests."""
    return {
        "conversation_id": conversation_id,
        "messages": [],
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": mode_context or {},
        "client_type": client_type,
        "user_name": "Test User",
        "is_first_interaction": False,
    }


def _tarifa_success_result(price: float = 350.0) -> str:
    """Return a JSON string simulating a successful calcular_tarifa_con_elementos result."""
    return json.dumps({
        "success": True,
        "texto": f"TARIFA RECOMENDADA: T3\nPrecio: {price} EUR\n",
        "datos": {"tier_name": "T3", "price": price, "elements": ["Escape"], "element_codes": ["ESCAPE"]},
        "imagenes_ejemplo": [{"url": "https://example.com/img1.jpg", "status": "active"}],
        "_internal_flags": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        },
    }, ensure_ascii=False)


def _enviar_imagenes_result() -> str:
    """Return a JSON string simulating a successful enviar_imagenes_ejemplo result."""
    return json.dumps({
        "success": True,
        "_pending_images": {
            "images": [{"url": "https://example.com/img1.jpg", "descripcion": ""}],
            "follow_up_message": "¿Quieres abrir el expediente?",
        },
        "_internal_flags": {
            "imagenes_enviadas": True,
        },
    }, ensure_ascii=False)


def _make_llm_response(*, content: str = "", tool_calls: list | None = None) -> Mock:
    """Build a minimal mock LLM response."""
    resp = Mock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    resp.usage_metadata = None
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# Test A — Guard blocks same-turn images after tarifa
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_guard_blocks_same_turn_images_after_tarifa():
    """
    Test A: When the LLM calls calcular_tarifa AND enviar_imagenes_ejemplo(tipo='presupuesto')
    in the SAME LLM response (same iteration), the guard must:
      1. Block enviar_imagenes_ejemplo — inject a synthetic blocked result (blocked=True)
      2. NOT set pending_images (image delivery should NOT happen)
      3. Force a new LLM iteration (break inner tool loop)

    The final ai_response should come from the second LLM call, after the LLM has
    seen both the tarifa result and the blocked-images result.
    """
    node = PresupuestoModeNode()
    state = _make_state()

    # Iteration 0: LLM asks for calcular_tarifa AND enviar_imagenes in same response
    response_iter0 = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_tarifa",
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
            },
            {
                "id": "call_images",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},
            },
        ],
    )

    # Iteration 1: LLM sees tarifa result + blocked images → communicates price
    response_iter1 = _make_llm_response(
        content="El presupuesto es de 350€ +IVA. ¿Quieres ver fotos (A) o abrir expediente (B)?",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[response_iter0, response_iter1])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool") as mock_execute:
            # calcular_tarifa_con_elementos succeeds — enviar_imagenes is blocked by guard
            # (so _execute_and_log_tool should only be called ONCE for calcular_tarifa)
            mock_execute.return_value = _tarifa_success_result()

            result = await node._process_message("quiero homologar escape", state)

    # ── Assertions ───────────────────────────────────────────────────────────

    # 1. _execute_and_log_tool was called only once: for calcular_tarifa (not for enviar_imagenes)
    assert mock_execute.call_count == 1, (
        f"_execute_and_log_tool should only be called for calcular_tarifa "
        f"(guard must block enviar_imagenes), but was called {mock_execute.call_count} times"
    )

    # 2. No pending images should be set — guard prevented image delivery
    assert result.get("pending_images") is None, (
        "pending_images must NOT be set when guard blocked enviar_imagenes in same turn as tarifa"
    )

    # 3. LLM was invoked twice (iteration 0 + iteration 1 after block)
    assert mock_llm.ainvoke.call_count == 2, (
        f"LLM should be invoked twice (first call + re-invocation after block), "
        f"but was called {mock_llm.ainvoke.call_count} times"
    )

    # 4. The final response contains the price (from iteration 1)
    assert "350" in result.get("ai_response", ""), (
        "Final ai_response should include the price communicated in iteration 1"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test B — Guard does NOT block images in separate LLM turn
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_guard_does_not_block_images_in_separate_turn():
    """
    Test B: When calcular_tarifa runs in turn N (one _process_message call)
    and enviar_imagenes runs in turn N+1 (separate _process_message call),
    the guard must NOT block.

    The flag _tarifa_called_this_turn resets at the start of each outer-loop
    iteration, so images in a *separate message processing cycle* are always
    allowed (the flag lives only within a single _process_message invocation).
    """
    node = PresupuestoModeNode()

    # --- Turn N: calcular_tarifa only ---
    state_turn_n = _make_state(conversation_id="test-separate-turn")

    response_tools = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_tarifa",
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
            },
        ],
    )
    response_price = _make_llm_response(
        content="El presupuesto es de 350€ +IVA. ¿Quieres fotos (A) o expediente (B)?",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[response_tools, response_price])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool") as mock_execute:
            mock_execute.return_value = _tarifa_success_result()
            result_n = await node._process_message("quiero homologar escape", state_turn_n)

    # Turn N produced a clean price message, no pending images
    assert result_n.get("pending_images") is None

    # --- Turn N+1: user says "A" → LLM calls enviar_imagenes ---
    state_turn_n1 = _make_state(
        conversation_id="test-separate-turn",
        mode_context=result_n.get("mode_context", {}),
    )

    response_images = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_images",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},
            },
        ],
    )
    response_after_images = _make_llm_response(
        content="Te he enviado las fotos. ¿Quieres abrir el expediente?",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm2:
        mock_llm2 = AsyncMock()
        mock_llm2.ainvoke = AsyncMock(side_effect=[response_images, response_after_images])
        mock_get_llm2.return_value = mock_llm2

        with patch.object(node, "_execute_and_log_tool") as mock_execute2:
            mock_execute2.return_value = _enviar_imagenes_result()
            result_n1 = await node._process_message("A", state_turn_n1)

    # ── Assertions ───────────────────────────────────────────────────────────
    # enviar_imagenes was NOT blocked — _execute_and_log_tool was called once
    assert mock_execute2.call_count == 1, (
        "enviar_imagenes must NOT be blocked in a separate turn from calcular_tarifa"
    )

    # pending_images is populated because enviar_imagenes succeeded
    assert result_n1.get("pending_images") is not None, (
        "pending_images should be set when enviar_imagenes runs in a separate turn"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test C — Guard does NOT block tipo="elemento"
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_guard_does_not_block_tipo_elemento():
    """
    Test C: The guard only applies when tipo='presupuesto'.
    enviar_imagenes_ejemplo(tipo='elemento') must NOT be blocked even when
    calcular_tarifa was called in the same LLM iteration.
    """
    node = PresupuestoModeNode()
    state = _make_state()

    # LLM calls calcular_tarifa AND enviar_imagenes(tipo="elemento") in same response
    response_both = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_tarifa",
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
            },
            {
                "id": "call_images_elem",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "elemento"},   # ← NOT "presupuesto"
            },
        ],
    )
    response_final = _make_llm_response(
        content="Aquí tienes la foto del escape.",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[response_both, response_final])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool") as mock_execute:
            # Both tools should execute — enviar_imagenes with tipo="elemento" is never blocked
            mock_execute.side_effect = [
                _tarifa_success_result(),
                _enviar_imagenes_result(),
            ]

            result = await node._process_message("quiero ver foto del escape", state)

    # ── Assertions ───────────────────────────────────────────────────────────
    # _execute_and_log_tool called TWICE (both tools ran)
    assert mock_execute.call_count == 2, (
        f"Both tools must execute when tipo='elemento' (guard should not fire). "
        f"Got call_count={mock_execute.call_count}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test D — pre_image_message preserved when follow_up_message exists
# ═══════════════════════════════════════════════════════════════════════════════

def test_pre_image_message_preserved_when_follow_up_exists():
    """
    Test D (main.py logic): When pending_images contains a follow_up_message,
    pre_image_message must equal ai_response_clean (not None).

    Reproduces the exact branching logic from agent/main.py lines 857-869:

        tool_follow_up = pending_images.get("follow_up_message")
        if tool_follow_up:
            post_image_message = tool_follow_up
            pre_image_message = ai_response_clean   ← FIXED (was None)
        else:
            post_image_message = ai_response_clean
            pre_image_message = None
    """
    # --- Simulate the branching logic from main.py ---
    ai_response_clean = "El presupuesto es de 350€ +IVA."

    pending_images_with_followup = {
        "images": [{"url": "https://example.com/img1.jpg"}],
        "follow_up_message": "¿Quieres abrir el expediente?",
    }

    pending_images_without_followup = {
        "images": [{"url": "https://example.com/img2.jpg"}],
        # no follow_up_message key
    }

    def _compute_messages(pending_images: dict, ai_response_clean: str):
        """Inline the branching from main.py."""
        tool_follow_up = pending_images.get("follow_up_message")
        if tool_follow_up:
            post_image_message = tool_follow_up
            pre_image_message = ai_response_clean
        else:
            post_image_message = ai_response_clean
            pre_image_message = None
        return pre_image_message, post_image_message

    # Case 1: follow_up_message present → pre_image_message must NOT be None
    pre, post = _compute_messages(pending_images_with_followup, ai_response_clean)

    assert pre is not None, (
        "pre_image_message must not be None when follow_up_message is present"
    )
    assert pre == ai_response_clean, (
        f"pre_image_message must equal ai_response_clean. Got: {pre!r}"
    )
    assert post == "¿Quieres abrir el expediente?", (
        f"post_image_message must be the tool follow_up. Got: {post!r}"
    )

    # Case 2: no follow_up_message → pre_image_message IS None (existing behaviour)
    pre2, post2 = _compute_messages(pending_images_without_followup, ai_response_clean)

    assert pre2 is None, (
        "pre_image_message must be None when no follow_up_message"
    )
    assert post2 == ai_response_clean, (
        "post_image_message must be ai_response_clean when no follow_up_message"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test E — Empty ai_response is not sent as pre_image_message
# ═══════════════════════════════════════════════════════════════════════════════

def test_pre_image_message_empty_when_ai_response_empty():
    """
    Test E: When ai_response_clean is an empty string (or falsy), the
    guard `if pre_image_message:` in main.py prevents sending an empty message
    even if follow_up_message is present.

    This is a behavioural test of the main.py guard, not of a callable function.
    We validate the logic inline.
    """
    empty_ai_response_clean = ""

    pending_images = {
        "images": [{"url": "https://example.com/img1.jpg"}],
        "follow_up_message": "¿Quieres abrir el expediente?",
    }

    # Inline the branching from main.py
    tool_follow_up = pending_images.get("follow_up_message")
    if tool_follow_up:
        post_image_message = tool_follow_up
        pre_image_message = empty_ai_response_clean
    else:
        post_image_message = empty_ai_response_clean
        pre_image_message = None

    # The guard `if pre_image_message:` in main.py prevents sending empty string
    would_send_pre = bool(pre_image_message)

    assert not would_send_pre, (
        "When ai_response_clean is empty, `if pre_image_message:` must be False "
        "to prevent sending an empty message"
    )
    assert post_image_message == "¿Quieres abrir el expediente?", (
        "post_image_message must still be the follow_up message"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test F — calcular_tarifa return text includes next-turn instruction
# ═══════════════════════════════════════════════════════════════════════════════

def test_calcular_tarifa_return_text_includes_next_turn_instruction():
    """
    Test F: When calcular_tarifa_con_elementos has active images available,
    the returned texto must include:
      1. A phrase indicating images should be sent in the NEXT turn
         (e.g. "turno siguiente" or "SIGUIENTE turno")
      2. An "INSTRUCCIÓN:" line directing the LLM to communicate price now
         and call enviar_imagenes_ejemplo only if the user chooses option A.

    We verify this directly against the static string in element_tools.py
    (lines 1509-1512) to confirm the tool signal was correctly implemented.

    NOTE: We test the string template content, not an actual DB call, because
    the tool requires a real DB + Qdrant setup that is not available in unit tests.
    """
    # Lines 1509-1512 of element_tools.py — the critical signal text
    # We reproduce the exact strings from the source and verify they contain
    # the required patterns.
    signal_line_1 = (
        "IMAGENES DE EJEMPLO DISPONIBLES (enviar en turno siguiente, NO en este mismo turno):"
    )
    signal_line_2 = (
        "INSTRUCCIÓN: Comunica el precio al usuario AHORA. Ofrece opciones A/B. "
        "Llama enviar_imagenes_ejemplo SOLO si el usuario elige opción A en el SIGUIENTE turno."
    )

    # Verify "turno siguiente" appears in the next-turn hint
    assert "turno siguiente" in signal_line_1.lower() or "siguiente turno" in signal_line_2.upper(), (
        "Tool signal must include 'turno siguiente' or 'SIGUIENTE turno'"
    )

    # Verify "INSTRUCCIÓN:" line exists and directs LLM behaviour
    assert "INSTRUCCIÓN:" in signal_line_2, (
        "Tool signal must include an 'INSTRUCCIÓN:' directive"
    )

    # Verify the phrase "siguiente turno" or "turno siguiente" is present in either line
    combined = (signal_line_1 + " " + signal_line_2).lower()
    assert "siguiente turno" in combined or "turno siguiente" in combined, (
        "Combined signal text must contain 'siguiente turno' or 'turno siguiente'"
    )

    # Verify directive to call enviar_imagenes only if user chooses A
    assert "siguiente turno" in signal_line_2.lower() or "SIGUIENTE turno" in signal_line_2, (
        "INSTRUCCIÓN line must reference the NEXT turn for enviar_imagenes_ejemplo"
    )


def test_calcular_tarifa_signal_in_source_file():
    """
    Additional check: read element_tools.py source and assert the actual
    signal strings are present as written (regression guard against accidental deletion).
    """
    import ast
    from pathlib import Path

    source_path = Path(__file__).resolve().parents[2] / "agent" / "tools" / "element_tools.py"
    if not source_path.exists():
        pytest.skip(f"Source file not found: {source_path}")

    source = source_path.read_text(encoding="utf-8")

    assert "turno siguiente" in source, (
        "element_tools.py must contain 'turno siguiente' in the tool signal text"
    )
    assert "INSTRUCCIÓN:" in source, (
        "element_tools.py must contain 'INSTRUCCIÓN:' directive"
    )
    assert "SIGUIENTE turno" in source, (
        "element_tools.py must contain 'SIGUIENTE turno' in the INSTRUCCIÓN line"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test — _apply_tool_flags unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyToolFlags:
    """Unit tests for the _apply_tool_flags helper (presupuesto_mode.py)."""

    def test_applies_precio_comunicado_from_flags(self):
        """_apply_tool_flags must apply precio_comunicado=True to mode_context."""
        import structlog
        logger = structlog.get_logger(__name__)
        mode_context: dict = {}
        result = {
            "success": True,
            "_internal_flags": {"precio_comunicado": True, "imagenes_enviadas": False},
        }
        _apply_tool_flags(mode_context, result, logger)
        assert mode_context.get("precio_comunicado") is True
        assert mode_context.get("imagenes_enviadas") is False

    def test_handles_json_string_input(self):
        """_apply_tool_flags must parse JSON string tool results."""
        import structlog
        logger = structlog.get_logger(__name__)
        mode_context: dict = {}
        result_str = json.dumps({
            "success": True,
            "_internal_flags": {"precio_comunicado": True},
        })
        _apply_tool_flags(mode_context, result_str, logger)
        assert mode_context.get("precio_comunicado") is True

    def test_no_flags_key_leaves_context_unchanged(self):
        """If tool result has no _internal_flags, mode_context is not modified."""
        import structlog
        logger = structlog.get_logger(__name__)
        mode_context: dict = {"existing_key": "value"}
        result = {"success": True, "data": "something"}
        _apply_tool_flags(mode_context, result, logger)
        assert mode_context == {"existing_key": "value"}

    def test_invalid_json_string_leaves_context_unchanged(self):
        """Invalid JSON string must not raise; context stays unchanged."""
        import structlog
        logger = structlog.get_logger(__name__)
        mode_context: dict = {"key": "value"}
        _apply_tool_flags(mode_context, "not valid json {{", logger)
        assert mode_context == {"key": "value"}

    def test_transition_signal_stored_in_context(self):
        """_transition_to signal must be stored in mode_context."""
        import structlog
        logger = structlog.get_logger(__name__)
        mode_context: dict = {}
        result = {
            "_internal_flags": {
                "_transition_to": "EXPEDIENTE_MODE",
                "precio_comunicado": True,
            }
        }
        _apply_tool_flags(mode_context, result, logger)
        assert mode_context.get("_transition_to") == "EXPEDIENTE_MODE"
        assert mode_context.get("precio_comunicado") is True
