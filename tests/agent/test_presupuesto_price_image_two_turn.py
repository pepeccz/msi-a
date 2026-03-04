"""
Integration-style tests for the two-turn price → image flow.

Verifies the end-to-end scenario where:
  - Turn 1: agent calculates price, communicates it, offers A/B options (NO images)
  - Turn 2A: user picks "A" → agent sends example images
  - Turn 2B: user picks "B" → agent offers expediente directly (NO images)

These tests mock the LLM but exercise the real PresupuestoModeNode loop,
including the code guard that blocks images in the same turn as tarifa.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent.modes.presupuesto_mode import PresupuestoModeNode


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / factories
# ═══════════════════════════════════════════════════════════════════════════════

def _make_state(
    *,
    conversation_id: str = "test-two-turn-conv",
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


def _make_llm_response(*, content: str = "", tool_calls: list | None = None) -> Mock:
    """Build a minimal mock LLM response."""
    resp = Mock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    resp.usage_metadata = None
    return resp


def _tarifa_success_result(price: float = 350.0) -> str:
    """JSON string from a successful calcular_tarifa_con_elementos."""
    return json.dumps({
        "success": True,
        "texto": (
            f"TARIFA RECOMENDADA: T3\n"
            f"Precio: {price} EUR (IVA no incluido)\n\n"
            f"IMAGENES DE EJEMPLO DISPONIBLES (enviar en turno siguiente, NO en este mismo turno): 2\n"
            f"INSTRUCCIÓN: Comunica el precio al usuario AHORA. Ofrece opciones A/B. "
            f"Llama enviar_imagenes_ejemplo SOLO si el usuario elige opción A en el SIGUIENTE turno.\n"
        ),
        "datos": {
            "tier_id": "tier-uuid-1",
            "tier_name": "T3",
            "price": price,
            "elements": ["Escape"],
            "element_codes": ["ESCAPE"],
            "warnings": [],
        },
        "imagenes_ejemplo": [
            {"url": "https://example.com/img1.jpg", "status": "active"},
            {"url": "https://example.com/img2.jpg", "status": "active"},
        ],
        "_internal_flags": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
        },
    }, ensure_ascii=False)


def _enviar_imagenes_success_result() -> str:
    """JSON string from a successful enviar_imagenes_ejemplo."""
    return json.dumps({
        "success": True,
        "message": "Imágenes enviadas.",
        "_pending_images": {
            "images": [
                {"url": "https://example.com/img1.jpg", "descripcion": "Escape deportivo"},
                {"url": "https://example.com/img2.jpg", "descripcion": "Escape homologado"},
            ],
            "follow_up_message": "¿Quieres que abramos el expediente?",
        },
        "_internal_flags": {
            "imagenes_enviadas": True,
        },
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Test G — Full flow: price in turn 1, user picks "A" → images in turn 2
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_flow_price_then_option_a_images():
    """
    Test G: End-to-end two-turn flow.

    Turn 1: User describes modification → LLM identifies element, calculates
            price, guard blocks same-turn images → LLM communicates price + A/B.
    Turn 2: User says "A" → LLM calls enviar_imagenes_ejemplo → images sent.

    Verifications:
      - Turn 1 response contains the price.
      - Turn 1 does NOT contain pending_images (images NOT sent in turn 1).
      - Turn 2 calls enviar_imagenes_ejemplo (mock invoked).
      - Turn 2 result has pending_images populated.
    """
    node = PresupuestoModeNode()

    # ── Turn 1 ──────────────────────────────────────────────────────────────
    state_t1 = _make_state(conversation_id="test-two-turn-g")

    # Iteration 0: LLM calls calcular_tarifa AND enviar_imagenes in same response
    # (this is the bad pattern the guard must catch)
    llm_t1_iter0 = _make_llm_response(
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
                "id": "call_images_0",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},  # ← guard must block this
            },
        ],
    )
    # Iteration 1: LLM sees tarifa + blocked-images → produces price message
    llm_t1_iter1 = _make_llm_response(
        content=(
            "El presupuesto para homologar el escape es de 350€ +IVA.\n"
            "¿Quieres: A) Ver fotos de ejemplo, o B) Abrir el expediente directamente?"
        ),
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm_t1:
        mock_llm_t1 = AsyncMock()
        mock_llm_t1.ainvoke = AsyncMock(side_effect=[llm_t1_iter0, llm_t1_iter1])
        mock_get_llm_t1.return_value = mock_llm_t1

        with patch.object(node, "_execute_and_log_tool") as mock_exec_t1:
            # calcular_tarifa succeeds; enviar_imagenes is blocked by guard (never reaches execute)
            mock_exec_t1.return_value = _tarifa_success_result()

            result_t1 = await node._process_message(
                "quiero homologar el escape de mi moto", state_t1
            )

    # ── Turn 1 Assertions ────────────────────────────────────────────────────

    ai_response_t1 = result_t1.get("ai_response", "")

    # The response must mention the price
    assert "350" in ai_response_t1, (
        f"Turn 1 response must include the price (350). Got: {ai_response_t1!r}"
    )

    # NO pending images in turn 1 (guard prevented same-turn delivery)
    assert result_t1.get("pending_images") is None, (
        "Turn 1 must NOT have pending_images — guard must block same-turn images"
    )

    # ── Turn 2: user says "A" → LLM sends images ────────────────────────────
    state_t2 = _make_state(
        conversation_id="test-two-turn-g",
        mode_context=result_t1.get("mode_context", {}),
    )

    # LLM now calls enviar_imagenes correctly (no tarifa in same turn)
    llm_t2_iter0 = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_images_t2",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},
            },
        ],
    )
    llm_t2_iter1 = _make_llm_response(
        content="Aquí tienes las fotos de ejemplo del escape. ¿Quieres abrir el expediente?",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm_t2:
        mock_llm_t2 = AsyncMock()
        mock_llm_t2.ainvoke = AsyncMock(side_effect=[llm_t2_iter0, llm_t2_iter1])
        mock_get_llm_t2.return_value = mock_llm_t2

        with patch.object(node, "_execute_and_log_tool") as mock_exec_t2:
            mock_exec_t2.return_value = _enviar_imagenes_success_result()

            result_t2 = await node._process_message("A", state_t2)

    # ── Turn 2 Assertions ────────────────────────────────────────────────────

    # enviar_imagenes_ejemplo was actually called (not blocked)
    assert mock_exec_t2.call_count == 1, (
        "enviar_imagenes_ejemplo must be called exactly once in turn 2"
    )
    called_tool_name = mock_exec_t2.call_args[1].get("tool_name") or (
        mock_exec_t2.call_args[0][1] if mock_exec_t2.call_args[0] else ""
    )
    assert called_tool_name == "enviar_imagenes_ejemplo", (
        f"The tool called in turn 2 must be enviar_imagenes_ejemplo. Got: {called_tool_name!r}"
    )

    # pending_images populated in turn 2
    assert result_t2.get("pending_images") is not None, (
        "Turn 2 must have pending_images after enviar_imagenes_ejemplo succeeds"
    )
    images = result_t2["pending_images"].get("images", [])
    assert len(images) >= 1, "pending_images must contain at least one image URL"


# ═══════════════════════════════════════════════════════════════════════════════
# Test H — Full flow: price then user picks "B" → expediente (NO images)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_flow_price_then_option_b_expediente():
    """
    Test H: Two-turn flow where user selects option B (expediente directly).

    Turn 1: Same as Test G — price communicated, guard blocks same-turn images.
    Turn 2: User says "B" → LLM does NOT call enviar_imagenes_ejemplo.
            Agent offers expediente directly without sending images.

    Verifications:
      - Turn 1: price in response, no pending_images.
      - Turn 2: enviar_imagenes_ejemplo NOT called.
      - Turn 2: no pending_images.
      - Turn 2: response mentions expediente or case opening.
    """
    node = PresupuestoModeNode()

    # ── Turn 1: same setup as Test G ────────────────────────────────────────
    state_t1 = _make_state(conversation_id="test-two-turn-h")

    llm_t1_iter0 = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_tarifa_h",
                "name": "calcular_tarifa_con_elementos",
                "args": {
                    "categoria_vehiculo": "motos-part",
                    "codigos_elementos": ["ESCAPE"],
                    "skip_validation": True,
                },
            },
            {
                "id": "call_images_h0",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},  # ← guard blocks
            },
        ],
    )
    llm_t1_iter1 = _make_llm_response(
        content=(
            "El presupuesto es de 350€ +IVA.\n"
            "¿Quieres: A) Ver fotos, o B) Abrir expediente directamente?"
        ),
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm_t1:
        mock_llm_t1 = AsyncMock()
        mock_llm_t1.ainvoke = AsyncMock(side_effect=[llm_t1_iter0, llm_t1_iter1])
        mock_get_llm_t1.return_value = mock_llm_t1

        with patch.object(node, "_execute_and_log_tool") as mock_exec_t1:
            mock_exec_t1.return_value = _tarifa_success_result()
            result_t1 = await node._process_message(
                "quiero homologar el escape", state_t1
            )

    # Turn 1 sanity checks
    assert result_t1.get("pending_images") is None, "Turn 1 must not have pending_images"
    assert "350" in result_t1.get("ai_response", ""), "Turn 1 must mention price"

    # ── Turn 2: user says "B" → LLM does NOT call enviar_imagenes ───────────
    state_t2 = _make_state(
        conversation_id="test-two-turn-h",
        mode_context=result_t1.get("mode_context", {}),
    )

    # LLM responds to "B" by offering expediente — no image tool call
    llm_t2 = _make_llm_response(
        content=(
            "Perfecto. Vamos a abrir el expediente directamente. "
            "Para ello necesito algunos datos. ¿Cuál es tu nombre completo?"
        ),
        tool_calls=[],  # ← NO enviar_imagenes_ejemplo
    )

    with patch.object(node, "_get_llm") as mock_get_llm_t2:
        mock_llm_t2 = AsyncMock()
        mock_llm_t2.ainvoke = AsyncMock(return_value=llm_t2)
        mock_get_llm_t2.return_value = mock_llm_t2

        with patch.object(node, "_execute_and_log_tool") as mock_exec_t2:
            result_t2 = await node._process_message("B", state_t2)

    # ── Turn 2 Assertions ────────────────────────────────────────────────────

    # enviar_imagenes_ejemplo must NOT have been called
    assert mock_exec_t2.call_count == 0, (
        "When user picks 'B', enviar_imagenes_ejemplo must NOT be called. "
        f"Got call_count={mock_exec_t2.call_count}"
    )

    # No pending images
    assert result_t2.get("pending_images") is None, (
        "Turn 2 (option B) must NOT have pending_images"
    )

    # Response should mention expediente or case
    response_t2 = result_t2.get("ai_response", "").lower()
    assert any(kw in response_t2 for kw in ["expediente", "abrir", "datos", "nombre"]), (
        f"Turn 2 (option B) response should mention expediente or data collection. "
        f"Got: {response_t2!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test — Guard flag resets correctly between outer loop iterations
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tarifa_flag_resets_between_outer_iterations():
    """
    Regression test: _tarifa_called_this_turn resets at the START of each
    outer-loop iteration (line 295 of presupuesto_mode.py).

    Scenario:
      - Iteration 0: LLM calls calcular_tarifa only → flag set to True
      - Iteration 1: LLM calls enviar_imagenes only → flag is False (reset) → NOT blocked

    This verifies the flag truly resets between iterations (not just within inner loop).
    """
    node = PresupuestoModeNode()
    state = _make_state(
        mode_context={
            "precio_comunicado": True,  # Price already communicated (from a prior turn)
        }
    )

    # Iteration 0: calcular_tarifa only (flag becomes True)
    llm_iter0 = _make_llm_response(
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
    # Iteration 1: enviar_imagenes only (flag is False after reset) → NOT blocked
    llm_iter1 = _make_llm_response(
        content="",
        tool_calls=[
            {
                "id": "call_images",
                "name": "enviar_imagenes_ejemplo",
                "args": {"tipo": "presupuesto"},
            },
        ],
    )
    # Iteration 2: final text response
    llm_iter2 = _make_llm_response(
        content="Te he enviado las fotos del escape.",
        tool_calls=[],
    )

    with patch.object(node, "_get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[llm_iter0, llm_iter1, llm_iter2])
        mock_get_llm.return_value = mock_llm

        with patch.object(node, "_execute_and_log_tool") as mock_exec:
            # Both tools execute — no guard fires because they're in different iterations
            mock_exec.side_effect = [
                _tarifa_success_result(),       # calcular_tarifa
                _enviar_imagenes_success_result(),  # enviar_imagenes (NOT blocked)
            ]

            result = await node._process_message(
                "A, mándame las fotos", state
            )

    # Both tools were executed (guard did NOT fire in iteration 1)
    assert mock_exec.call_count == 2, (
        f"Both calcular_tarifa and enviar_imagenes must execute in separate iterations. "
        f"Got call_count={mock_exec.call_count}"
    )

    # pending_images set correctly
    assert result.get("pending_images") is not None, (
        "pending_images must be set when enviar_imagenes runs in a different iteration"
    )
