"""
Tests for fix-photo-guard-premature-state-advance

Bug: After confirmar_fotos_elemento returns with element advancement (current_element_index
incremented), the photo_guard's post-call state update was re-deriving the element code
from the MUTATED mode_context, targeting the NEXT element instead of the one just confirmed.

Scenarios:
  1. Photo guard targets pre-call element (not next) after context advancement
  2. Photo guard targets pre-call element when all_elements_complete
  3. Defense-in-depth: confirmar_fotos_elemento rejects LLM calls on awaiting_photos with 0 images
  4. Zero-photos error response includes element_code
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode
from agent.modes.submodos._shared import (
    ELEMENT_STATE_AWAITING_PHOTOS,
    ELEMENT_STATE_CONFIRMING_PHOTOS,
    ELEMENT_STATE_PHOTOS_CONFIRMED,
    _set_element_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONVERSATION_ID = "test-conv-state-advance-001"


def _make_state(mode_context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "conversation_id": CONVERSATION_ID,
        "user_id": "user-test-001",
        "messages": [],
        "mode_context": mode_context or {},
        "current_mode": "EXPEDIENTE_MODE",
        "fsm_state": {
            "case_collection": {
                "step": "collect_element_data",
                "case_id": "case-test-123",
                "category_slug": "aseicars-prof",
                "element_codes": ["TOLDO_GALIBO", "PLACA_SOLAR_REGULADOR_INTERIOR"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {
                    "TOLDO_GALIBO": "pending_photos",
                    "PLACA_SOLAR_REGULADOR_INTERIOR": "pending_photos",
                },
            }
        },
        "incoming_attachments": [],
    }


def _make_confirmar_fotos_result_with_advancement() -> dict[str, Any]:
    """Simulate confirmar_fotos_elemento returning with element advancement.

    This is what happens when the confirmed element has NO required fields:
    the tool advances current_element_index to the next element.
    """
    return {
        "success": True,
        "element_code": "TOLDO_GALIBO",
        "photos_confirmed": True,
        "has_required_fields": False,
        "element_complete": True,
        "all_elements_complete": False,
        "next_element": "PLACA_SOLAR_REGULADOR_INTERIOR",
        "element_phase": "photos",
        "current_element_index": 1,  # Advanced to next element
        "photos_count": 4,
        "_internal_flags": {
            "fotos_elemento_registered": True,
            "can_narrate_next_element": True,
            "all_elements_complete": False,
            "delivery_outcome_status": "not_requested",
        },
    }


def _make_confirmar_fotos_result_with_data_phase() -> dict[str, Any]:
    """Simulate confirmar_fotos_elemento returning with data phase (has required fields)."""
    return {
        "success": True,
        "element_code": "TOLDO_GALIBO",
        "photos_confirmed": True,
        "has_required_fields": True,
        "element_phase": "data",
        "current_element_index": 0,  # Same element, entering data phase
        "photos_count": 4,
        "_internal_flags": {
            "fotos_elemento_registered": True,
            "can_narrate_next_element": False,
            "all_elements_complete": False,
            "delivery_outcome_status": "not_requested",
        },
    }


def _make_mock_confirmar_fotos(return_value: dict[str, Any]) -> MagicMock:
    mock_tool = MagicMock()
    mock_tool.ainvoke = AsyncMock(return_value=json.dumps(return_value))
    return mock_tool


def _make_node() -> ExpedienteModeNode:
    return ExpedienteModeNode()


# ---------------------------------------------------------------------------
# Test: photo_guard targets pre-call element after context advancement
# ---------------------------------------------------------------------------


class TestPhotoGuardStateTargeting:
    """Verify the photo_guard's post-call state update targets the correct element."""

    @pytest.mark.asyncio
    async def test_guard_targets_pre_call_element_not_next_after_advancement(self):
        """
        GIVEN 2 elements: TOLDO_GALIBO (index 0), PLACA_SOLAR (index 1)
        AND   confirmar_fotos_elemento returns current_element_index=1 (advanced)
        WHEN  photo_guard completes
        THEN  TOLDO_GALIBO state is updated (photos_confirmed or element_complete)
        AND   PLACA_SOLAR state remains awaiting_photos (untouched)
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "TOLDO_GALIBO",
            "case_id": "case-test-123",
            "category_slug": "aseicars-prof",
            "category_id": "cat-test-123",
            "element_codes": ["TOLDO_GALIBO", "PLACA_SOLAR_REGULADOR_INTERIOR"],
            "element_states": {
                "TOLDO_GALIBO": {
                    "state": ELEMENT_STATE_AWAITING_PHOTOS,
                    "photos_count": 0,
                    "data_complete": False,
                },
                "PLACA_SOLAR_REGULADOR_INTERIOR": {
                    "state": ELEMENT_STATE_AWAITING_PHOTOS,
                    "photos_count": 0,
                    "data_complete": False,
                },
            },
        }
        state = _make_state(mode_context)

        # Tool returns with advancement to next element
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_result_with_advancement()
        )

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool
            ),
        ):
            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True

        # CRITICAL: PLACA_SOLAR must NOT have been touched by the guard
        placa_state = mode_context["element_states"]["PLACA_SOLAR_REGULADOR_INTERIOR"]
        assert placa_state["state"] == ELEMENT_STATE_AWAITING_PHOTOS, (
            f"PLACA_SOLAR should remain 'awaiting_photos' but got '{placa_state['state']}'. "
            f"The photo_guard is targeting the wrong element after context advancement."
        )

    @pytest.mark.asyncio
    async def test_guard_targets_pre_call_element_with_data_phase(self):
        """
        GIVEN confirmar_fotos_elemento returns element_phase="data" (has required fields)
        AND   current_element_index stays at 0 (no advancement)
        WHEN  photo_guard completes
        THEN  TOLDO_GALIBO state is photos_confirmed
        AND   PLACA_SOLAR state remains awaiting_photos
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "TOLDO_GALIBO",
            "case_id": "case-test-123",
            "category_slug": "aseicars-prof",
            "category_id": "cat-test-123",
            "element_codes": ["TOLDO_GALIBO", "PLACA_SOLAR_REGULADOR_INTERIOR"],
            "element_states": {
                "TOLDO_GALIBO": {
                    "state": ELEMENT_STATE_AWAITING_PHOTOS,
                    "photos_count": 0,
                    "data_complete": False,
                },
                "PLACA_SOLAR_REGULADOR_INTERIOR": {
                    "state": ELEMENT_STATE_AWAITING_PHOTOS,
                    "photos_count": 0,
                    "data_complete": False,
                },
            },
        }
        state = _make_state(mode_context)

        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_result_with_data_phase()
        )

        with (
            patch("agent.modes.expediente_mode.set_current_state"),
            patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
            patch(
                "agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool
            ),
        ):
            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True

        # TOLDO should be in photos_confirmed (transitioning to data phase)
        toldo_state = mode_context["element_states"]["TOLDO_GALIBO"]
        assert toldo_state["state"] == ELEMENT_STATE_PHOTOS_CONFIRMED, (
            f"TOLDO_GALIBO should be 'photos_confirmed' but got '{toldo_state['state']}'"
        )

        # PLACA_SOLAR must remain untouched
        placa_state = mode_context["element_states"]["PLACA_SOLAR_REGULADOR_INTERIOR"]
        assert placa_state["state"] == ELEMENT_STATE_AWAITING_PHOTOS, (
            f"PLACA_SOLAR should remain 'awaiting_photos' but got '{placa_state['state']}'"
        )


# ---------------------------------------------------------------------------
# Test: defense-in-depth guard in confirmar_fotos_elemento
# ---------------------------------------------------------------------------


class TestConfirmarFotosAwaitingPhotosGuard:
    """Verify confirmar_fotos_elemento rejects LLM calls on awaiting_photos elements."""

    @pytest.fixture(autouse=True)
    def _clear_idempotency_set(self):
        """Clear the module-level idempotency set between tests."""
        from agent.tools.element_data_tools import _photos_confirmed_this_turn
        _photos_confirmed_this_turn.clear()
        yield
        _photos_confirmed_this_turn.clear()

    @pytest.mark.asyncio
    async def test_rejects_call_on_awaiting_photos_with_zero_images(self):
        """
        GIVEN element is in 'awaiting_photos' state with 0 images
        WHEN  confirmar_fotos_elemento is called (from LLM loop, not photo_guard)
        THEN  returns success=False with rejected=True
        AND   does NOT enter the 16-second polling path
        """
        from agent.tools.element_data_tools import confirmar_fotos_elemento

        mock_state = {
            "conversation_id": "1",
            "user_phone": "+34600000000",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": "case-test-456",
                "category_id": "cat-test-123",
                "category_slug": "aseicars-prof",
                "element_codes": ["TOLDO_GALIBO", "PLACA_SOLAR_REGULADOR_INTERIOR"],
                "current_element_index": 1,
                "element_phase": "photos",
                "element_data_status": {
                    "TOLDO_GALIBO": "completed",
                    "PLACA_SOLAR_REGULADOR_INTERIOR": "pending_photos",
                },
                "element_states": {
                    "TOLDO_GALIBO": {
                        "state": "element_complete",
                        "photos_count": 4,
                        "data_complete": True,
                    },
                    "PLACA_SOLAR_REGULADOR_INTERIOR": {
                        "state": "awaiting_photos",
                        "photos_count": 0,
                        "data_complete": False,
                    },
                },
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": "case-test-456",
                    "category_slug": "aseicars-prof",
                    "element_codes": [
                        "TOLDO_GALIBO",
                        "PLACA_SOLAR_REGULADOR_INTERIOR",
                    ],
                    "current_element_index": 1,
                    "element_phase": "photos",
                    "element_data_status": {
                        "TOLDO_GALIBO": "completed",
                        "PLACA_SOLAR_REGULADOR_INTERIOR": "pending_photos",
                    },
                }
            },
        }

        with (
            patch(
                "agent.tools.element_data_tools.get_current_state",
                return_value=mock_state,
            ),
            patch(
                "agent.tools.element_data_tools._get_element_image_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "agent.tools.element_data_tools.get_case_image_batch_service"
            ) as mock_batch_svc,
            patch(
                "agent.tools.element_data_tools.build_upload_scope",
                return_value=None,
            ),
        ):
            mock_batch_svc.return_value.resolve_for_scope = AsyncMock(
                return_value=None
            )

            result = await confirmar_fotos_elemento.ainvoke(
                {"usuario_confirma": True}
            )

        result_dict = json.loads(result) if isinstance(result, str) else result
        assert result_dict["success"] is False
        assert result_dict.get("rejected") is True
        assert "PLACA_SOLAR_REGULADOR_INTERIOR" in result_dict.get("element_code", "")

    @pytest.mark.asyncio
    async def test_zero_photos_error_includes_element_code(self):
        """
        GIVEN element is in 'confirming_photos' state (photo_guard set it)
        AND   element_image_count is 0 after both polling phases
        WHEN  confirmar_fotos_elemento returns the zero-photos error
        THEN  response includes element_code field
        AND   message includes the element code string
        """
        from agent.tools.element_data_tools import confirmar_fotos_elemento

        mock_state = {
            "conversation_id": "1",
            "user_phone": "+34600000000",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "expediente_sub_mode": "collect_element_data",
                "case_id": "case-test-789",
                "category_id": "cat-test-123",
                "category_slug": "aseicars-prof",
                "element_codes": ["TOLDO_GALIBO"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {"TOLDO_GALIBO": "pending_photos"},
                "element_states": {
                    "TOLDO_GALIBO": {
                        "state": "confirming_photos",
                        "photos_count": 0,
                        "data_complete": False,
                    },
                },
            },
            "fsm_state": {
                "case_collection": {
                    "step": "collect_element_data",
                    "case_id": "case-test-789",
                    "category_slug": "aseicars-prof",
                    "element_codes": ["TOLDO_GALIBO"],
                    "current_element_index": 0,
                    "element_phase": "photos",
                    "element_data_status": {"TOLDO_GALIBO": "pending_photos"},
                }
            },
        }

        mock_settings = MagicMock()
        mock_settings.PHOTO_COMPLETION_WAIT_SECONDS = 0
        mock_settings.PHOTO_COMPLETION_RETRY_WAIT_SECONDS = 0

        mock_chatwoot = MagicMock()
        mock_chatwoot.send_message = AsyncMock()

        with (
            patch(
                "agent.tools.element_data_tools.get_current_state",
                return_value=mock_state,
            ),
            patch(
                "agent.tools.element_data_tools._get_element_image_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "agent.tools.element_data_tools.get_case_image_batch_service"
            ) as mock_batch_svc,
            patch(
                "agent.tools.element_data_tools.build_upload_scope",
                return_value=None,
            ),
            patch(
                "shared.config.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "shared.chatwoot_client.ChatwootClient",
                return_value=mock_chatwoot,
            ),
        ):
            mock_batch_svc.return_value.resolve_for_scope = AsyncMock(
                return_value=None
            )

            result = await confirmar_fotos_elemento.ainvoke(
                {"usuario_confirma": True}
            )

        result_dict = json.loads(result) if isinstance(result, str) else result
        assert result_dict["success"] is False
        assert result_dict.get("element_code") == "TOLDO_GALIBO"
        assert "TOLDO_GALIBO" in result_dict.get("message", "")
