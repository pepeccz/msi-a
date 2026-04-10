"""
Unit tests for entry_router synthetic user_message injection.

When the photo_guard fires and transitions to a DIFFERENT sub-mode
(e.g. collect_element_data → collect_base_docs), the original user_message
(typically "listo") must be replaced with a synthetic "[Sistema: ...]" message
to prevent the destination node from misinterpreting it as a confirmation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from agent.modes.expediente_nodes import entry_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_state(
    *,
    case_id: str = "test-case-id",
    sub_mode: str = "collect_element_data",
    element_phase: str = "photos",
    user_message: str = "listo",
    conversation_id: str = "1",
    current_element_code: str | None = None,
    element_data_status: dict | None = None,
) -> dict:
    """Build a minimal ExpedienteState-like dict for entry_router."""
    return {
        "case_id": case_id,
        "expediente_sub_mode": sub_mode,
        "element_phase": element_phase,
        "user_message": user_message,
        "conversation_id": conversation_id,
        "current_element_code": current_element_code,
        "element_data_status": element_data_status or {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEntryRouterGuardSyntheticMessage:
    """Guard fires AND changes sub-mode → synthetic user_message injected."""

    @pytest.mark.asyncio
    async def test_guard_changes_sub_mode_injects_synthetic_message(self):
        """When guard transitions to collect_base_docs, user_message must
        be replaced with a [Sistema:...] synthetic message."""
        state = _make_state(user_message="listo")

        guard_result = {
            "expediente_sub_mode": "collect_base_docs",
            "fotos_elemento_registered": True,
            "all_elements_complete": True,
        }

        with patch(
            "agent.services.expediente_guards.guard_photo_completion",
            new_callable=AsyncMock,
            side_effect=lambda s, u: (u.update(guard_result), True)[-1],
        ):
            cmd = await entry_router(state)

        assert cmd.update is not None
        assert "user_message" in cmd.update
        assert cmd.update["user_message"].startswith("[Sistema:")
        assert cmd.goto == "collect_base_docs_node"

    @pytest.mark.asyncio
    async def test_guard_same_sub_mode_preserves_user_message(self):
        """When guard fires but stays in collect_element_data (e.g. element
        has required fields), user_message must NOT be injected."""
        state = _make_state(user_message="listo")

        guard_result = {
            "expediente_sub_mode": "collect_element_data",
            "fotos_elemento_registered": True,
            "all_elements_complete": False,
        }

        with patch(
            "agent.services.expediente_guards.guard_photo_completion",
            new_callable=AsyncMock,
            side_effect=lambda s, u: (u.update(guard_result), True)[-1],
        ):
            cmd = await entry_router(state)

        assert cmd.update is not None
        assert "user_message" not in cmd.update
        assert cmd.goto == "collect_element_data_node"

    @pytest.mark.asyncio
    async def test_guard_not_fired_preserves_original_flow(self):
        """When guard does NOT fire (e.g. user message is not a completion
        signal), entry_router routes normally without touching user_message."""
        state = _make_state(user_message="tengo una duda")

        with patch(
            "agent.services.expediente_guards.guard_photo_completion",
            new_callable=AsyncMock,
            return_value=False,
        ):
            cmd = await entry_router(state)

        # Guard didn't fire → no update, just routing
        assert cmd.goto == "collect_element_data_node"
        if cmd.update:
            assert "user_message" not in cmd.update
