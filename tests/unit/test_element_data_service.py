"""
Tests for confirm_base_documentation() with TwoPhasePoller refactor.

T-07: Replaces hardcoded sleep(4) + single retry with TwoPhasePoller.
      Verifies escalation only after BOTH phases fail, feedback before wait,
      and correct behaviour for all user-confirm combinations.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

BASE_MODE_CONTEXT = {
    "expediente_sub_mode": "collect_base_docs",
    "fsm_state": {},
    "base_doc_descriptions": ["Ficha técnica", "Permiso circulación", "DNI", "Fotos"],
    "category_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "user_phone": "+34600000000",
}


def _make_advance_mocks():
    """Mocks for batch_service and FSM helpers."""
    batch_service = MagicMock()
    batch_service.resolve_for_scope = AsyncMock(return_value=MagicMock(batch_id="batch-1"))
    batch_service.finalize_for_scope = AsyncMock(return_value=None)
    return batch_service


def _patch_stack(
    *,
    image_count: int,
    min_required: int = 4,
    poller_result_count: int | None = None,
    poller_phase_reached: int = 2,
):
    """Build a context manager that patches the key collaborators."""
    from contextlib import AsyncExitStack
    from unittest.mock import patch as _patch

    poller_count = poller_result_count if poller_result_count is not None else image_count

    from agent.services.element_data_service import TwoPhasePollingResult

    poller_result = TwoPhasePollingResult(
        count=poller_count,
        phase_reached=poller_phase_reached,
        feedback_sent=True,
    )

    class _PatchStack:
        def __init__(self):
            self._patches = []
            self.mocks = {}

        def __enter__(self):
            batch_service = _make_advance_mocks()
            self.mocks["batch_service"] = batch_service

            self._patches = [
                _patch(
                    "agent.services.element_data_service._get_case_image_count",
                    new_callable=AsyncMock,
                    return_value=image_count,
                ),
                _patch(
                    "agent.services.element_data_service._get_base_docs_min_required",
                    new_callable=AsyncMock,
                    return_value=min_required,
                ),
                _patch(
                    "agent.services.case_image_batch_service.get_case_image_batch_service",
                    return_value=batch_service,
                ),
                _patch(
                    "agent.services.case_image_batch_service.build_upload_scope",
                    return_value="scope-key",
                ),
                _patch(
                    "agent.services.element_data_service.TwoPhasePoller",
                ),
                _patch(
                    "agent.services.element_data_service.perform_escalation",
                    new_callable=AsyncMock,
                ),
            ]

            active = [p.__enter__() for p in self._patches]
            (
                self.mocks["image_count"],
                self.mocks["min_required"],
                self.mocks["batch_svc_factory"],
                self.mocks["build_scope"],
                self.mocks["PollerClass"],
                self.mocks["escalate"],
            ) = active

            mock_poller_instance = MagicMock()
            mock_poller_instance.poll = AsyncMock(return_value=poller_result)
            self.mocks["PollerClass"].return_value = mock_poller_instance
            self.mocks["poller_instance"] = mock_poller_instance

            return self.mocks

        def __exit__(self, *args):
            for p in reversed(self._patches):
                p.__exit__(*args)

    return _PatchStack()


# ─────────────────────────────────────────────────────────────────────────────
# T-07: confirm_base_documentation() scenarios
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfirmBaseDocumentationTwoPhase:
    """T-07: confirm_base_documentation() uses TwoPhasePoller, not sleep(4)."""

    async def test_no_hardcoded_sleep_4_in_source(self) -> None:
        """AC1: asyncio.sleep(4) must not appear in confirm_base_documentation source."""
        import inspect
        import agent.services.element_data_service as mod

        source = inspect.getsource(mod.confirm_base_documentation)
        assert "asyncio.sleep(4)" not in source, (
            "Found hardcoded asyncio.sleep(4) in confirm_base_documentation — "
            "must be replaced with TwoPhasePoller"
        )

    async def test_scenario_d1002_d_user_not_confirmed_no_polling(self) -> None:
        """SCENARIO D1-002-D: usuario_confirma=False → no polling, returns needs_docs=True."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(image_count=0, min_required=4) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=False,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is False
        assert result.get("needs_confirmation") is True
        mocks["PollerClass"].assert_not_called()
        mocks["escalate"].assert_not_called()

    async def test_scenario_d1002_e_count_sufficient_no_wait(self) -> None:
        """SCENARIO D1-002-E: count >= min on first check → no poller, advances immediately."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(image_count=4, min_required=4) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=None,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is True
        assert result.get("base_docs_confirmed") is True
        assert result.get("next_step") == "COLLECT_PERSONAL"
        mocks["PollerClass"].assert_not_called()
        mocks["escalate"].assert_not_called()

    async def test_scenario_d1002_a_count_after_phase1_advances(self) -> None:
        """SCENARIO D1-002-A: count=0 → poller → phase1 finds >= min → advances, no escalation."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=0,
            min_required=4,
            poller_result_count=4,
            poller_phase_reached=1,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is True
        assert result.get("base_docs_confirmed") is True
        mocks["PollerClass"].assert_called_once()
        mocks["poller_instance"].poll.assert_called_once_with(min_required=4)
        mocks["escalate"].assert_not_called()

    async def test_scenario_d1002_b_count_after_phase2_advances(self) -> None:
        """SCENARIO D1-002-B: count=0 → poller → only phase2 finds >= min → advances."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=0,
            min_required=4,
            poller_result_count=4,
            poller_phase_reached=2,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is True
        assert result.get("base_docs_confirmed") is True
        mocks["escalate"].assert_not_called()

    async def test_scenario_d1002_c_both_phases_fail_escalates(self) -> None:
        """SCENARIO D1-002-C: count=0 through both phases → perform_escalation called."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=0,
            min_required=4,
            poller_result_count=0,
            poller_phase_reached=2,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        mocks["escalate"].assert_called_once()
        # escalation call must include is_technical_error=True
        call_kwargs = mocks["escalate"].call_args.kwargs
        assert call_kwargs.get("is_technical_error") is True
        assert "reason" in call_kwargs
        assert len(call_kwargs["reason"]) > 0

    async def test_escalation_not_called_on_first_count_check(self) -> None:
        """Escalation NEVER called on the initial count check — only after both phases fail."""
        from agent.services.element_data_service import confirm_base_documentation

        # count = 0 but user has NOT confirmed yet → no escalation
        with _patch_stack(image_count=0, min_required=4) as mocks:
            await confirm_base_documentation(
                usuario_confirma=False,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        mocks["escalate"].assert_not_called()

    async def test_scenario_d1003_a_procesando_message_before_wait(self) -> None:
        """SCENARIO D1-003-A: TwoPhasePoller receives 'Procesando...' feedback message."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=0,
            min_required=4,
            poller_result_count=4,
            poller_phase_reached=1,
        ) as mocks:
            await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        poller_kwargs = mocks["PollerClass"].call_args.kwargs
        assert "Procesando" in poller_kwargs.get("feedback_message", ""), (
            "TwoPhasePoller must receive a feedback_message containing 'Procesando'"
        )

    async def test_uses_get_base_docs_min_required_helper(self) -> None:
        """AC7: _get_base_docs_min_required() is called (not the old max(len, 2) formula)."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(image_count=2, min_required=4) as mocks:
            await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        mocks["min_required"].assert_called_once()

    async def test_idempotent_when_already_past_base_docs_step(self) -> None:
        """Already past COLLECT_BASE_DOCS → returns already_confirmed=True, no poller."""
        from agent.services.element_data_service import confirm_base_documentation

        past_mode_ctx = {
            **BASE_MODE_CONTEXT,
            "expediente_sub_mode": "collect_personal",
        }

        with _patch_stack(image_count=0, min_required=4) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=past_mode_ctx,
            )

        assert result.get("already_confirmed") is True
        mocks["PollerClass"].assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T-22: Mid-expediente floor safety (D5-002)
# ─────────────────────────────────────────────────────────────────────────────


class TestMidExpedienteFloorSafety:
    """
    T-22 [RED] — Mid-expediente conversation safety.

    REQ-D5-002 AC1-AC4, SCENARIOS D5-002-A through D5-002-B
    """

    async def test_scenario_d5002_a_existing_photos_below_new_min_waits(self) -> None:
        """
        SCENARIO D5-002-A: 3 photos already in DB, new min_required=4
        → count=3 < 4 → enters wait (TwoPhasePoller called),
        if photos arrive to reach 4 → advances normally.
        """
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=3,
            min_required=4,
            poller_result_count=4,
            poller_phase_reached=1,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        # count 3 < min 4 → poller should be called (waits for more)
        mocks["PollerClass"].assert_called_once()
        # After poller returns 4 → advances
        assert result.get("success") is True
        assert result.get("base_docs_confirmed") is True
        mocks["escalate"].assert_not_called()

    async def test_scenario_d5002_b_existing_photos_above_min_advances_immediately(
        self,
    ) -> None:
        """
        SCENARIO D5-002-B: 5 photos already in DB, min_required=4
        → count=5 >= 4 → advances immediately, no wait.
        """
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(
            image_count=5,
            min_required=4,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        # count 5 >= min 4 → no poller
        mocks["PollerClass"].assert_not_called()
        assert result.get("success") is True
        assert result.get("base_docs_confirmed") is True
        mocks["escalate"].assert_not_called()

    async def test_ac1_min_required_not_cached(self) -> None:
        """AC1: _get_base_docs_min_required() is NOT cached — each call is fresh."""
        from agent.services.element_data_service import _get_base_docs_min_required

        # Verify no lru_cache decorator (not a cached function)
        import inspect

        assert not hasattr(_get_base_docs_min_required, "__wrapped__"), (
            "_get_base_docs_min_required must NOT be decorated with lru_cache"
        )
        # Confirm it is a coroutine function (async)
        assert inspect.iscoroutinefunction(_get_base_docs_min_required)

    async def test_ac4_escalation_only_after_both_phases_fail(self) -> None:
        """AC4: Escalation only fires after BOTH polling phases fail."""
        from agent.services.element_data_service import confirm_base_documentation

        # 3 photos + min=4: poller phase1 returns 3 (still not enough), phase2 returns 3
        with _patch_stack(
            image_count=3,
            min_required=4,
            poller_result_count=3,
            poller_phase_reached=2,
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        # Escalation called because count still < min after both phases
        mocks["escalate"].assert_called_once()
        call_kwargs = mocks["escalate"].call_args.kwargs
        assert call_kwargs.get("is_technical_error") is True
