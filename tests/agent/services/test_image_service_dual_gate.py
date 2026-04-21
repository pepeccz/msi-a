"""
RED tests for Batch 2 — Dual-Mode Image Gate.

Spec domain: example-image-gate-dual-mode
Design: Layer B (image_service.py + image_tools.py)

These tests are written FIRST (TDD RED phase). They fail before implementation
of the dual-mode gate and pass after.

Scenarios:
  A (B2-T1): PRE mode + already sent → error (preserve d0fc986 behavior)
  B (B2-T2): EXPEDIENTE mode + already sent + NOT in elementos_descripciones_entregadas
             → descriptions_only=True, message has INSTRUCCIONES DE FOTOS, no images queued
  C (B2-T3): EXPEDIENTE mode + already sent + IN elementos_descripciones_entregadas
             → error (no re-send)
  D (B2-T4): tool wrapper short-circuits on descriptions_only=True — no _pending_images key
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATEGORY_ID = "cat-uuid-001"
_ELEMENT_ID = "elem-uuid-001"
_ELEMENT_CODE = "SUBCHASIS"


def _make_state(
    *,
    current_mode: str = "PRE_EXPEDIENTE_MODE",
    imagenes_enviadas_codigos: list[str] | None = None,
    elementos_descripciones_entregadas: list[str] | None = None,
    categoria_slug: str = "motos",
    conversation_id: str = "test-conv-dual",
) -> dict:
    """Build a minimal ConversationState dict for dual-gate testing."""
    mc: dict = {
        "categoria_slug": categoria_slug,
        "imagenes_enviadas_codigos": imagenes_enviadas_codigos or [],
    }
    if elementos_descripciones_entregadas is not None:
        mc["elementos_descripciones_entregadas"] = elementos_descripciones_entregadas
    return {
        "conversation_id": conversation_id,
        "current_mode": current_mode,
        "mode_context": mc,
        "shared_context": {
            "categoria_slug": categoria_slug,
            "imagenes_enviadas_codigos": imagenes_enviadas_codigos or [],
        },
    }


def _make_elements_list(code: str = _ELEMENT_CODE) -> list[dict]:
    return [{"id": _ELEMENT_ID, "name": "Subchasis", "code": code.upper()}]


def _make_element_details(code: str = _ELEMENT_CODE) -> dict:
    return {
        "id": _ELEMENT_ID,
        "name": "Subchasis",
        "description": "Foto del subchasis",
        "images": [
            {
                "image_url": "https://example.com/img1.jpg",
                "image_type": "ejemplo",
                "title": "Subchasis frontal",
                "description": "Vista frontal del subchasis",
                "user_instruction": "Foto frontal del subchasis con matrícula visible",
                "status": "active",
            },
            {
                "image_url": "https://example.com/img2.jpg",
                "image_type": "ejemplo",
                "title": "Subchasis lateral",
                "description": "Vista lateral del subchasis",
                "user_instruction": "Foto lateral del subchasis completo",
                "status": "active",
            },
        ],
    }


def _make_tool_config(state: dict) -> dict:
    return {"configurable": {"state": state}}


def _make_element_service_mock(elements: list[dict], element_details: dict | None = None) -> MagicMock:
    """Build a mock ElementService."""
    svc = MagicMock()
    svc.get_elements_by_category = AsyncMock(return_value=elements)
    if element_details is not None:
        svc.get_element_with_images = AsyncMock(return_value=element_details)
    return svc


# ---------------------------------------------------------------------------
# B2-T1: PRE mode + already sent → error (d0fc986 behavior preserved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_B2T1_pre_mode_already_sent_returns_error():
    """
    Scenario A: PRE_EXPEDIENTE_MODE, code already in imagenes_enviadas_codigos.
    Gate MUST return error string (existing behavior). No descriptions_only key.
    """
    from agent.services.image_service import ImageService

    svc = ImageService()
    elements = _make_elements_list()
    mock_elem_svc = _make_element_service_mock(elements)

    state = _make_state(
        current_mode="PRE_EXPEDIENTE_MODE",
        imagenes_enviadas_codigos=["SUBCHASIS"],
    )

    with (
        patch(
            "agent.services.element_service.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=_CATEGORY_ID,
        ),
        patch(
            "agent.services.element_service.get_element_service",
            return_value=mock_elem_svc,
        ),
        patch(
            "agent.services.element_service.normalize_element_code",
            return_value=(_ELEMENT_CODE, False),
        ),
    ):
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="SUBCHASIS",
            categoria="motos",
            follow_up_message=None,
            state_context=state,
        )

    assert result["success"] is False, f"PRE mode + already sent must return error, got: {result}"
    assert "descriptions_only" not in result, "No descriptions_only in PRE mode"
    # Must have some indication of already-sent
    msg_lower = result["message"].lower()
    assert any(kw in msg_lower for kw in ("ya", "mostr", "envi", "already")), (
        f"Message must indicate already-sent, got: {result['message']}"
    )


# ---------------------------------------------------------------------------
# B2-T2: EXPEDIENTE mode + already sent + NOT in elementos_descripciones_entregadas
#         → descriptions_only + INSTRUCCIONES DE FOTOS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_B2T2_expediente_mode_first_turn_returns_descriptions_only():
    """
    Scenario B: EXPEDIENTE_MODE, code in imagenes_enviadas_codigos,
    code NOT in elementos_descripciones_entregadas.
    Gate MUST return descriptions_only=True and message with INSTRUCCIONES DE FOTOS.
    images_to_queue MUST be empty. _state_update must set elementos_descripciones_entregadas.
    """
    from agent.services.image_service import ImageService

    svc = ImageService()
    elements = _make_elements_list()
    element_details = _make_element_details()
    mock_elem_svc = _make_element_service_mock(elements, element_details)

    state = _make_state(
        current_mode="EXPEDIENTE_MODE",
        imagenes_enviadas_codigos=["SUBCHASIS"],
        elementos_descripciones_entregadas=[],  # NOT yet delivered
    )

    with (
        patch(
            "agent.services.element_service.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=_CATEGORY_ID,
        ),
        patch(
            "agent.services.element_service.get_element_service",
            return_value=mock_elem_svc,
        ),
        patch(
            "agent.services.element_service.normalize_element_code",
            return_value=(_ELEMENT_CODE, False),
        ),
    ):
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="SUBCHASIS",
            categoria="motos",
            follow_up_message=None,
            state_context=state,
        )

    assert result["success"] is True, f"Should succeed with descriptions, got: {result}"
    assert result.get("descriptions_only") is True, (
        f"Must signal descriptions_only=True, got: {result}"
    )
    assert "INSTRUCCIONES DE FOTOS" in result["message"], (
        f"message must contain INSTRUCCIONES DE FOTOS, got: {result['message']}"
    )
    assert result.get("images_to_queue") == [], (
        f"images_to_queue must be empty, got: {result.get('images_to_queue')}"
    )
    # State update must tombstone this element code
    state_update = result.get("_state_update", {})
    entregadas = state_update.get("elementos_descripciones_entregadas", [])
    assert "SUBCHASIS" in entregadas, (
        f"_state_update must include SUBCHASIS in elementos_descripciones_entregadas, got: {state_update}"
    )
    # Must NOT have _pending_images or delivery contract (descriptions only)
    assert "_pending_images" not in result, "descriptions_only must not queue images"


# ---------------------------------------------------------------------------
# B2-T3: EXPEDIENTE mode + already sent + IN elementos_descripciones_entregadas → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_B2T3_expediente_mode_second_turn_returns_error():
    """
    Scenario C: EXPEDIENTE_MODE, code in imagenes_enviadas_codigos AND in
    elementos_descripciones_entregadas (already gave descriptions once).
    Gate MUST return error (no re-send of descriptions either).
    """
    from agent.services.image_service import ImageService

    svc = ImageService()
    elements = _make_elements_list()
    mock_elem_svc = _make_element_service_mock(elements)

    state = _make_state(
        current_mode="EXPEDIENTE_MODE",
        imagenes_enviadas_codigos=["SUBCHASIS"],
        elementos_descripciones_entregadas=["SUBCHASIS"],  # already delivered once
    )

    with (
        patch(
            "agent.services.element_service.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value=_CATEGORY_ID,
        ),
        patch(
            "agent.services.element_service.get_element_service",
            return_value=mock_elem_svc,
        ),
        patch(
            "agent.services.element_service.normalize_element_code",
            return_value=(_ELEMENT_CODE, False),
        ),
    ):
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="SUBCHASIS",
            categoria="motos",
            follow_up_message=None,
            state_context=state,
        )

    assert result["success"] is False, (
        f"EXPEDIENTE second re-ask must return error, got: {result}"
    )
    assert result.get("descriptions_only") is not True, (
        "descriptions_only must NOT be True on second re-ask"
    )


# ---------------------------------------------------------------------------
# B2-T4: Tool wrapper short-circuits on descriptions_only=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_B2T4_tool_wrapper_short_circuits_on_descriptions_only():
    """
    When service returns descriptions_only=True, the tool wrapper (image_tools.py)
    MUST return early with success=True + message, and MUST NOT include _pending_images.
    """
    from agent.tools.image_tools import enviar_imagenes_ejemplo, clear_image_tools_state

    clear_image_tools_state()

    descriptions_only_result = {
        "success": True,
        "descriptions_only": True,
        "message": (
            "INSTRUCCIONES DE FOTOS (usa ESTAS descripciones literalmente, no inventes): "
            "Foto frontal del subchasis con matrícula visible | Foto lateral del subchasis completo"
        ),
        "images_to_queue": [],
        "follow_up_message": None,
        "_state_update": {
            "elementos_descripciones_entregadas": ["SUBCHASIS"],
        },
    }

    state = _make_state(
        current_mode="EXPEDIENTE_MODE",
        imagenes_enviadas_codigos=["SUBCHASIS"],
    )

    # The tool imports `get_image_service` locally inside the function body via:
    #   from agent.services.image_service import get_image_service
    # Patching the source module attribute is the correct strategy.
    mock_svc = MagicMock()
    mock_svc.queue_example_images = AsyncMock(return_value=descriptions_only_result)

    with (
        patch(
            "agent.services.image_service.get_image_service",
            return_value=mock_svc,
        ),
        patch(
            "agent.tools.image_tools.get_tool_state",
            return_value=state,
        ),
    ):
        raw = await enviar_imagenes_ejemplo.ainvoke(
            {
                "tipo": "elemento",
                "codigo_elemento": "SUBCHASIS",
                "categoria": "motos",
            },
            config=_make_tool_config(state),
        )

    result = json.loads(raw) if isinstance(raw, str) else raw

    assert result["success"] is True, f"Tool must succeed: {result}"
    assert "INSTRUCCIONES DE FOTOS" in result["message"], (
        f"Tool message must contain INSTRUCCIONES DE FOTOS: {result}"
    )
    assert "_pending_images" not in result, (
        "descriptions_only path must NOT set _pending_images"
    )
