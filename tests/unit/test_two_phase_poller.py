"""
Tests for TwoPhasePoller and TwoPhasePollingResult.

T-05: Class behaviours — phased polling, feedback messages, chatwoot errors swallowed.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ─────────────────────────────────────────────────────────────────────────────
# T-05: TwoPhasePoller class
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestTwoPhasePoller:
    """T-05: TwoPhasePoller phased polling behaviour."""

    def _make_settings(
        self,
        phase1: int = 1,
        phase2: int = 1,
    ) -> MagicMock:
        """Small wait values for fast tests."""
        return MagicMock(
            PHOTO_COMPLETION_WAIT_SECONDS=phase1,
            PHOTO_COMPLETION_RETRY_WAIT_SECONDS=phase2,
        )

    async def test_count_sufficient_before_polling_phase_zero(self) -> None:
        """When initial count >= min_required, phase_reached=0, no sleep, no feedback."""
        from agent.services.element_data_service import TwoPhasePoller

        count_fn = AsyncMock(return_value=5)
        mock_settings = self._make_settings()

        with (
            patch("asyncio.sleep") as mock_sleep,
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_send,
        ):
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Procesando...",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )
            result = await poller.poll(min_required=5)

        assert result.count == 5
        assert result.phase_reached == 0
        assert result.feedback_sent is False
        mock_sleep.assert_not_called()
        mock_send.assert_not_called()

    async def test_count_sufficient_after_phase1(self) -> None:
        """count=0 initially, >= min after phase 1 → phase_reached=1, one sleep."""
        from agent.services.element_data_service import TwoPhasePoller

        # initial check → 0 (< 3), phase1 recheck → 3 (>= 3)
        count_fn = AsyncMock(side_effect=[0, 3])
        mock_settings = self._make_settings(phase1=1, phase2=1)

        with (
            patch("asyncio.sleep") as mock_sleep,
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send,
        ):
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Procesando...",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )
            result = await poller.poll(min_required=3)

        assert result.count == 3
        assert result.phase_reached == 1
        assert result.feedback_sent is True
        # exactly one sleep (phase 1 only)
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args == call(1)
        mock_send.assert_called_once()

    async def test_count_sufficient_after_phase2(self) -> None:
        """count=0 after phase 1, >= min after phase 2 → phase_reached=2, two sleeps."""
        from agent.services.element_data_service import TwoPhasePoller

        # initial → 0 (< 3), phase1 → 1 (< 3), phase2 → 3 (>= 3)
        count_fn = AsyncMock(side_effect=[0, 1, 3])
        mock_settings = self._make_settings(phase1=1, phase2=2)

        with (
            patch("asyncio.sleep") as mock_sleep,
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Procesando...",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )
            result = await poller.poll(min_required=3)

        assert result.count == 3
        assert result.phase_reached == 2
        assert mock_sleep.call_count == 2
        # phase1 wait then phase2 wait
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    async def test_both_phases_fail_returns_phase2_count(self) -> None:
        """count stays 0 through both phases → phase_reached=2, count=0."""
        from agent.services.element_data_service import TwoPhasePoller

        # initial=0, phase1=0, phase2=0
        count_fn = AsyncMock(side_effect=[0, 0, 0])
        mock_settings = self._make_settings()

        with (
            patch("asyncio.sleep"),
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Procesando...",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )
            result = await poller.poll(min_required=3)

        assert result.count == 0
        assert result.phase_reached == 2

    async def test_feedback_sent_via_send_poller_feedback(self) -> None:
        """_send_poller_feedback is called with correct args when polling starts."""
        from agent.services.element_data_service import TwoPhasePoller

        count_fn = AsyncMock(return_value=5)
        mock_settings = self._make_settings()

        with (
            patch("asyncio.sleep"),
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send,
        ):
            # count_fn: initial=5 (< 6), phase1 check also needs a value
            count_fn = AsyncMock(side_effect=[5, 6])
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Procesando tus imágenes, un momento... ⏳",
                conversation_id="42",
                user_phone="+34600111222",
            )
            await poller.poll(min_required=6)

        mock_send.assert_called_once_with(
            message="Procesando tus imágenes, un momento... ⏳",
            conversation_id="42",
            user_phone="+34600111222",
        )

    async def test_chatwoot_exception_swallowed_non_fatal(self) -> None:
        """Chatwoot exception in _send_poller_feedback returns False, does not propagate."""
        from agent.services.element_data_service import _send_poller_feedback

        with patch(
            "agent.services.element_data_service._get_chatwoot_client",
            side_effect=Exception("Chatwoot unavailable"),
        ):
            # Must not raise
            result = await _send_poller_feedback(
                message="Procesando...",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )

        assert result is False

    async def test_result_dataclass_fields(self) -> None:
        """TwoPhasePollingResult has count, phase_reached, feedback_sent fields."""
        from agent.services.element_data_service import TwoPhasePollingResult

        result = TwoPhasePollingResult(count=3, phase_reached=1, feedback_sent=True)
        assert result.count == 3
        assert result.phase_reached == 1
        assert result.feedback_sent is True

    async def test_uses_settings_wait_values(self) -> None:
        """Poller reads PHOTO_COMPLETION_WAIT_SECONDS and PHOTO_COMPLETION_RETRY_WAIT_SECONDS."""
        from agent.services.element_data_service import TwoPhasePoller

        # phase1=5, phase2=3
        mock_settings = self._make_settings(phase1=5, phase2=3)
        # initial=0, phase1=0, phase2=0 — all fail so both sleeps are called
        count_fn = AsyncMock(side_effect=[0, 0, 0])

        with (
            patch("asyncio.sleep") as mock_sleep,
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=mock_settings,
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            poller = TwoPhasePoller(
                count_fn=count_fn,
                feedback_message="Msg",
                conversation_id="conv-1",
                user_phone="+34600000000",
            )
            await poller.poll(min_required=1)

        calls = mock_sleep.call_args_list
        assert calls[0] == call(5)
        assert calls[1] == call(3)
