"""
Tests: Cross-Mode Image Dedup Removal (Spec 3 / Batch 3 — FIXED)

These tests verify that:
1. When element images were sent in PRESUPUESTO_MODE, calling
   enviar_imagenes_ejemplo(tipo="elemento") in EXPEDIENTE_MODE MUST
   still send the images (cross-mode dedup guard was removed, Batch 3).
2. Same-mode intra-turn dedup still works (prevent duplicate sends
   within the SAME turn — that guard is intentional and must stay).

BUG REFERENCE: Bug #2 from production incident 2026-04-02
  - `enviar_imagenes_ejemplo` previously tracked `images_shown_for_elements`
    across ALL modes.
  - When images were sent in PRESUPUESTO, the guard blocked the SAME element's
    images in EXPEDIENTE — but these are semantically DIFFERENT images:
      * PRESUPUESTO = "here's an example of what a homologated element looks like"
      * EXPEDIENTE  = "here's how to photograph THIS element for the technicians"
  - Fix (Batch 3): Removed the cross-mode dedup guard from image_tools.py.
    `images_shown_for_elements` is no longer propagated on mode transitions
    (conversation_state.py IMAGE_TRACKING_KEYS only contains presupuesto_images_shown).

ADR Reference: sdd/agent-architecture-refactor design doc, AD-2
Spec Reference: REQ-P1-2 in delta spec

Status: Cross-mode fix is applied. Both tests should PASS against current code.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.tools.image_tools import (
    _clear_element_images_sent_this_turn,
    clear_image_tools_state,
    enviar_imagenes_ejemplo,
)


def _make_tool_config(state: dict) -> dict:
    """Build a RunnableConfig that passes state to tool via get_tool_state(config)."""
    return {"configurable": {"state": state}}

# ---------------------------------------------------------------------------
# Helpers: build state dicts that simulate mode transitions
# ---------------------------------------------------------------------------


def _make_presupuesto_state_with_images_shown(
    element_code: str = "PLACA_SOLAR_REGULADOR_INTERIOR",
    conversation_id: str = "dedup-test-001",
) -> dict:
    """
    State that simulates what PRESUPUESTO_MODE looks like AFTER it sent
    example images for an element.

    `images_shown_for_elements` is set to [element_code.upper()] — this is
    the cross-mode dedup guard's trigger key.
    """
    code = element_code.upper()
    return {
        "conversation_id": conversation_id,
        "current_mode": "PRESUPUESTO_MODE",
        "mode_context": {
            "precio_comunicado": True,
            "imagenes_enviadas": True,
            "presupuesto_images_shown": True,
            "element_codes": [code],
            "images_shown_for_elements": [code],  # ← trigger for cross-mode block
            "tarifa_calculada": {
                "datos": {"element_codes": [code]},
                "imagenes_ejemplo": [],
            },
        },
    }


def _make_expediente_state_with_prior_presupuesto(
    element_code: str = "PLACA_SOLAR_REGULADOR_INTERIOR",
    conversation_id: str = "dedup-test-001",
) -> dict:
    """
    State that simulates EXPEDIENTE_MODE after transitioning from PRESUPUESTO.

    The `images_shown_for_elements` key is preserved across the mode transition
    (it lives in mode_context which persists via Redis checkpoint).
    This is the exact scenario that triggers Bug #2.
    """
    code = element_code.upper()
    return {
        "conversation_id": conversation_id,
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "precio_comunicado": True,
            "imagenes_enviadas": True,
            "presupuesto_images_shown": True,
            "element_codes": [code],
            # Cross-mode dedup trigger: these codes were set when PRESUPUESTO sent images
            "images_shown_for_elements": [code],
            "expediente_sub_mode": "collect_element_data",
            "case_id": "817d4914-test",
        },
    }


# ---------------------------------------------------------------------------
# T1.5-A: test_expediente_images_not_blocked_by_presupuesto
#
# When element images were sent in PRESUPUESTO_MODE, calling
# enviar_imagenes_ejemplo(tipo="elemento") in EXPEDIENTE_MODE MUST
# still send the images (i.e., NOT return cross_mode_dedup_blocked).
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expediente_images_not_blocked_by_presupuesto():
    """
    SPEC REQ-P1-2 / Bug #2 (FIXED — Batch 3):
    When images were sent in PRESUPUESTO_MODE (images_shown_for_elements is set),
    calling enviar_imagenes_ejemplo(tipo="elemento") in EXPEDIENTE_MODE MUST
    still send the images.

    The cross-mode dedup guard that incorrectly blocked this has been removed:
        images_shown_for_elements = ["PLACA_SOLAR_REGULADOR_INTERIOR"]
        → was: call in EXPEDIENTE_MODE returned already_shown=True, images NOT sent
        → now: guard is gone; the tool proceeds to send images normally.

    Assertions:
        → result["already_shown"] must NOT be True
        → result must NOT contain the key "cross_mode_dedup_blocked" in logs
          (verified by checking the result dict does not signal dedup)

    This test PASSES against current (fixed) code.
    """
    element_code = "PLACA_SOLAR_REGULADOR_INTERIOR"
    categoria = "aseicars-prof"
    conversation_id = "expediente-cross-mode-test-001"

    # State simulates EXPEDIENTE_MODE with images_shown_for_elements already set
    # (populated when PRESUPUESTO sent images earlier in the conversation)
    state = _make_expediente_state_with_prior_presupuesto(
        element_code=element_code,
        conversation_id=conversation_id,
    )

    # Mock element service to return a valid element with images
    mock_element = {
        "id": "elem-placa-001",
        "code": element_code,
        "name": "Placa Solar con Regulador Interior",
        "images": [
            {
                "url": "/datos/Imagenes/aseicars/placa_solar.png",
                "status": "active",
                "descripcion": "Placa solar instalada",
                "instruccion_usuario": "Fotografía la placa solar con matrícula visible",
            }
        ],
    }

    _clear_element_images_sent_this_turn()
    clear_image_tools_state()

    try:
        with (
            patch(
                "agent.services.element_service.get_element_service"
            ) as mock_get_element_service,
            patch(
                "agent.services.element_service.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-aseicars-prof-uuid",
            ),
        ):
            mock_element_service = MagicMock()
            mock_element_service.get_elements_by_category = AsyncMock(
                return_value=[mock_element]
            )
            mock_element_service.get_element_images = AsyncMock(
                return_value=mock_element["images"]
            )
            mock_get_element_service.return_value = mock_element_service

            result_raw = await enviar_imagenes_ejemplo.ainvoke(
                {
                    "tipo": "elemento",
                    "codigo_elemento": element_code,
                    "categoria": categoria,
                },
                config=_make_tool_config(state),
            )
    finally:
        clear_image_tools_state()
        _clear_element_images_sent_this_turn()

    result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw

    # The cross-mode dedup guard (before the fix) returns:
    #   {"success": True, "already_shown": True, "images_already_shown": True, ...}
    # After the fix, the tool must NOT return already_shown=True for an expediente call.
    assert result.get("already_shown") is not True, (
        "BUG #2: cross-mode dedup guard blocked EXPEDIENTE images because "
        "PRESUPUESTO previously sent images for this element. "
        "images_shown_for_elements should NOT block expediente imagen sends. "
        f"Got result: {result}"
    )

    # Additional check: the result must not explicitly signal the dedup block
    assert result.get("images_already_shown") is not True, (
        "BUG #2: images_already_shown=True means the cross-mode guard is still active. "
        "It must be removed so EXPEDIENTE can send technical photo instructions."
    )


# ---------------------------------------------------------------------------
# T1.5-B: test_same_mode_dedup_still_works
#
# The INTRA-TURN dedup guard (prevents sending the same element images twice
# within a single agent turn) must still work after the cross-mode guard is removed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_same_mode_dedup_still_works():
    """
    SPEC: Intra-turn dedup behavior must be preserved.

    Within the SAME TURN, if the LLM calls enviar_imagenes_ejemplo twice for
    the same element (e.g., due to a constraint retry), the second call should
    be handled gracefully by the _element_images_sent_this_turn set.

    This test verifies that the intra-turn dedup (_element_images_sent_this_turn)
    still fires on the second call within the same turn — that guard is
    intentional and must NOT be removed.

    The intra-turn guard returns success=False with a message telling the LLM
    "images were already sent this turn, proceed with next step."

    This test must PASS both before and after the T1.5 fix.
    """
    element_code = "PLACA_SOLAR_REGULADOR_INTERIOR"
    categoria = "aseicars-prof"
    conversation_id = "same-mode-dedup-test-001"

    # State WITHOUT images_shown_for_elements (fresh turn in EXPEDIENTE_MODE)
    state = {
        "conversation_id": conversation_id,
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {
            "element_codes": [element_code.upper()],
            "expediente_sub_mode": "collect_element_data",
            # No images_shown_for_elements — this is a fresh state
        },
    }

    mock_element = {
        "id": "elem-placa-002",
        "code": element_code,
        "name": "Placa Solar con Regulador Interior",
        "images": [
            {
                "url": "/datos/Imagenes/aseicars/placa_solar.png",
                "status": "active",
                "descripcion": "Placa solar instalada",
                "instruccion_usuario": "Fotografía la placa solar con matrícula visible",
            }
        ],
    }

    try:
        with (
            patch(
                "agent.services.element_service.get_element_service"
            ) as mock_get_element_service,
            patch(
                "agent.services.element_service.get_or_fetch_category_id",
                new_callable=AsyncMock,
                return_value="cat-aseicars-prof-uuid",
            ),
        ):
            mock_element_service = MagicMock()
            mock_element_service.get_elements_by_category = AsyncMock(
                return_value=[mock_element]
            )
            mock_element_service.get_element_images = AsyncMock(
                return_value=mock_element["images"]
            )
            mock_get_element_service.return_value = mock_element_service

            # Reset per-turn state (simulates start of a new agent turn)
            _clear_element_images_sent_this_turn()
            clear_image_tools_state()

            # First call within the same turn — should proceed (or reach image delivery)
            result1_raw = await enviar_imagenes_ejemplo.ainvoke(
                {
                    "tipo": "elemento",
                    "codigo_elemento": element_code,
                    "categoria": categoria,
                },
                config=_make_tool_config(state),
            )
            result1 = (
                json.loads(result1_raw) if isinstance(result1_raw, str) else result1_raw
            )

            # Second call within the SAME TURN (same element, same turn)
            # The intra-turn dedup guard should block this
            result2_raw = await enviar_imagenes_ejemplo.ainvoke(
                {
                    "tipo": "elemento",
                    "codigo_elemento": element_code,
                    "categoria": categoria,
                },
                config=_make_tool_config(state),
            )
            result2 = (
                json.loads(result2_raw) if isinstance(result2_raw, str) else result2_raw
            )
    finally:
        clear_image_tools_state()
        _clear_element_images_sent_this_turn()

    # The second call should be blocked by the intra-turn dedup guard
    # (success=False, message about "ya fueron enviadas en este turno")
    assert result2.get("success") is False, (
        "The intra-turn dedup guard must block the second call within the same turn. "
        "result2 should have success=False. "
        f"Got: {result2}"
    )
    assert (
        "turno" in (result2.get("message") or "").lower()
        or "turn" in (result2.get("message") or "").lower()
    ), (
        "The intra-turn dedup message should mention 'turno' (turn). "
        f"Got message: {result2.get('message')}"
    )

    # First call should NOT have been blocked by dedup (it was the first this turn)
    # It can be blocked for other reasons (e.g. no images in DB), but not dedup
    # We just verify it doesn't have the intra-turn duplicate message
    if result1.get("success") is False:
        msg = (result1.get("message") or "").lower()
        assert "turno" not in msg and "duplicate" not in msg, (
            "The FIRST call within a turn must not be blocked by intra-turn dedup. "
            f"Got: {result1}"
        )
