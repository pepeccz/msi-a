"""
T02: Failing tests for _queue_elemento cross-turn dedup gate.

Spec scenarios covered:
  Scenario 1 — element code already in imagenes_enviadas_codigos → gate fires
  Scenario 3 — element NOT previously sent → gate silent, images queued
  Scenario 4 — stale checkpoint (missing field) → gate silent, sends normally
  Scenario 5 — case normalization ("subchasis" blocked by "SUBCHASIS")

Response shape when gate fires (load-bearing for LLM routing):
  {
    "success": False,
    "already_sent": True,
    "tool_name": "enviar_imagenes_ejemplo",
    "message": <Spanish instructional text>,
    "images_to_queue": None,
    "follow_up_message": None,
  }

Mirror pattern from test_delta_image_sending_e2e.py — tests call
_queue_elemento directly, mocking element_service dependencies.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_element(code: str, name: str = "Elemento Test") -> dict:
    return {
        "id": f"elem-{code.lower()}-uuid",
        "code": code.upper(),
        "name": name,
        "description": "Descripción de prueba",
    }


def _make_element_details(name: str = "Elemento Test") -> dict:
    return {
        "name": name,
        "description": "Foto del elemento con matrícula visible",
        "images": [
            {
                "image_url": "https://cdn.example.com/elem1.jpg",
                "image_type": "elemento",
                "description": "Foto frontal",
                "user_instruction": "Fotografía el elemento con matrícula visible",
                "status": "active",
            }
        ],
    }


def _make_state(
    imagenes_enviadas_codigos: list[str] | None = None,
    include_field: bool = True,
    current_mode: str = "PRE_EXPEDIENTE_MODE",
) -> dict:
    """Build a minimal state_context that _queue_elemento reads.

    Default is PRE_EXPEDIENTE_MODE — this file tests the error-path gate
    (already sent → instruct LLM to ask for client photos). EXPEDIENTE_MODE
    has different behavior (descriptions_only first-turn); see
    tests/agent/services/test_image_service_dual_gate.py.
    """
    mc: dict = {}
    if include_field and imagenes_enviadas_codigos is not None:
        mc["imagenes_enviadas_codigos"] = imagenes_enviadas_codigos
    return {
        "mode_context": mc,
        "current_mode": current_mode,
    }


def _patch_element_service(elements: list[dict], element_details: dict):
    """Context manager that patches element_service functions for _queue_elemento."""
    mock_svc = MagicMock()
    mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
    mock_svc.get_element_with_images = AsyncMock(return_value=element_details)

    return (
        patch(
            "agent.services.element_service.get_element_service",
            return_value=mock_svc,
        ),
        patch(
            "agent.services.element_service.get_or_fetch_category_id",
            new_callable=AsyncMock,
            return_value="cat-uuid-test",
        ),
        patch(
            "agent.services.element_service.normalize_element_code",
            side_effect=lambda code, valid: (code.upper() if code.upper() in valid else None, False),
        ),
    )


# ===========================================================================
# Scenario 1: Gate fires — code already in imagenes_enviadas_codigos
# ===========================================================================


class TestQueueElementoDedupGate:
    """Cross-turn dedup gate for _queue_elemento."""

    @pytest.mark.asyncio
    async def test_gate_fires_when_code_already_sent(self):
        """
        Spec Scenario 1: SUBCHASIS is in imagenes_enviadas_codigos →
        gate fires, returns already_sent=True, no images queued.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("SUBCHASIS", "Subchasis")]
        details = _make_element_details("Subchasis")
        state = _make_state(imagenes_enviadas_codigos=["SUBCHASIS"])

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="SUBCHASIS",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-001",
            )

        assert result["success"] is False
        assert result.get("already_sent") is True
        assert result.get("tool_name") == "enviar_imagenes_ejemplo"
        assert result.get("images_to_queue") is None
        assert result.get("follow_up_message") is None
        assert "reenviar_imagenes_elemento" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_gate_response_has_spanish_instructional_message(self):
        """
        Spec Scenario 9: already-sent response must be informational, not a hard error.
        Message must mention 'fotos' and guide the LLM.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("ESCAPE", "Escape")]
        details = _make_element_details("Escape")
        state = _make_state(imagenes_enviadas_codigos=["ESCAPE"])

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="ESCAPE",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-002",
            )

        msg = result.get("message", "")
        assert "fotos" in msg.lower() or "foto" in msg.lower(), (
            f"Message should mention 'fotos'. Got: {msg}"
        )
        assert result["success"] is False
        assert result.get("already_sent") is True

    # ===========================================================================
    # Scenario 3: Gate silent — code NOT previously sent
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_gate_silent_when_code_not_sent(self):
        """
        Spec Scenario 3: FRENOS is NOT in imagenes_enviadas_codigos →
        gate is silent, normal image delivery proceeds.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("FRENOS", "Frenos")]
        details = _make_element_details("Frenos")
        state = _make_state(imagenes_enviadas_codigos=["ESCAPE"])  # FRENOS not present

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="FRENOS",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-003",
            )

        assert result["success"] is True
        assert result.get("images_to_queue") is not None
        assert len(result["images_to_queue"]) > 0
        assert result.get("already_sent") is not True

    @pytest.mark.asyncio
    async def test_gate_silent_when_codigos_list_empty(self):
        """
        Empty imagenes_enviadas_codigos list → gate does not fire.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("MOTOR", "Motor")]
        details = _make_element_details("Motor")
        state = _make_state(imagenes_enviadas_codigos=[])

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="MOTOR",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-004",
            )

        assert result["success"] is True
        assert result.get("already_sent") is not True

    # ===========================================================================
    # Scenario 4: Stale checkpoint — missing field → gate silent
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_gate_silent_on_stale_checkpoint_missing_field(self):
        """
        Spec Scenario 4: imagenes_enviadas_codigos field absent (old checkpoint) →
        gate treats as empty set, images delivered normally.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("LUCES", "Luces")]
        details = _make_element_details("Luces")
        # include_field=False → no imagenes_enviadas_codigos key in mode_context
        state = _make_state(include_field=False)

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="LUCES",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-005",
            )

        assert result["success"] is True, (
            f"Gate must NOT fire on stale checkpoint with missing field. Got: {result}"
        )
        assert result.get("already_sent") is not True

    @pytest.mark.asyncio
    async def test_gate_silent_when_mode_context_missing(self):
        """
        state_context has no mode_context at all → gate treats as empty set, silent.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("LUCES", "Luces")]
        details = _make_element_details("Luces")
        state = {"current_mode": "EXPEDIENTE_MODE"}  # no mode_context key

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="LUCES",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-006",
            )

        assert result["success"] is True
        assert result.get("already_sent") is not True

    # ===========================================================================
    # Scenario 5: Case normalization — "subchasis" blocked by "SUBCHASIS"
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_gate_fires_case_insensitive_lowercase_input(self):
        """
        Spec Scenario 5: imagenes_enviadas_codigos contains "SUBCHASIS" (uppercase),
        incoming codigo_elemento is "subchasis" (lowercase).
        Gate must normalize and block.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("SUBCHASIS", "Subchasis")]
        details = _make_element_details("Subchasis")
        state = _make_state(imagenes_enviadas_codigos=["SUBCHASIS"])

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="subchasis",  # lowercase input
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-007",
            )

        assert result["success"] is False, (
            "Gate must fire even when input code is lowercase and stored code is uppercase"
        )
        assert result.get("already_sent") is True

    @pytest.mark.asyncio
    async def test_gate_fires_mixed_case_in_stored_set(self):
        """
        imagenes_enviadas_codigos contains mixed-case entry "Escape" →
        gate must normalize to ESCAPE and block when input is "ESCAPE".
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("ESCAPE", "Escape")]
        details = _make_element_details("Escape")
        # Stored with wrong case (shouldn't happen but gate must handle it)
        state = _make_state(imagenes_enviadas_codigos=["Escape"])

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="ESCAPE",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-008",
            )

        assert result["success"] is False
        assert result.get("already_sent") is True

    # ===========================================================================
    # Different code — gate does NOT fire
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_gate_silent_for_different_element_code(self):
        """
        imagenes_enviadas_codigos has ESCAPE; requesting MOTOR → gate does not fire.
        """
        from agent.services.image_service import ImageService

        elements = [_make_element("MOTOR", "Motor")]
        details = _make_element_details("Motor")
        state = _make_state(imagenes_enviadas_codigos=["ESCAPE"])  # MOTOR not in set

        svc = ImageService()
        p1, p2, p3 = _patch_element_service(elements, details)
        with p1, p2, p3:
            result = await svc._queue_elemento(
                codigo_elemento="MOTOR",
                categoria="motos-part",
                follow_up_message=None,
                state_context=state,
                conversation_id="dedup-gate-009",
            )

        assert result["success"] is True
        assert result.get("already_sent") is not True
