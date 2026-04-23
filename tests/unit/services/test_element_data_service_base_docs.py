"""
Phase 1 (fix-base-docs-transition-guard): service emits `_transition_to`.

Strict TDD — RED tests written BEFORE the implementation.

Covers the requirement: `confirm_base_documentation` must emit
`_state_update._transition_to = "collect_personal"` (the value of
`CollectionStep.COLLECT_PERSONAL`) on success paths that advance the FSM
from `collect_base_docs` to `collect_personal`, AND must NOT emit it on
idempotent / insufficient / escalation paths (spec: "No re-emission once
already in personal").
"""

from __future__ import annotations

import pytest
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock, patch as _patch


BASE_MODE_CONTEXT = {
    "expediente_sub_mode": "collect_base_docs",
    "fsm_state": {},
    "base_doc_descriptions": ["Ficha técnica", "Permiso circulación", "DNI", "Fotos"],
    "category_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "user_phone": "+34600000000",
}


def _make_batch_service():
    batch_service = MagicMock()
    batch_service.resolve_for_scope = AsyncMock(
        return_value=MagicMock(batch_id="batch-1")
    )
    batch_service.finalize_for_scope = AsyncMock(return_value=None)
    return batch_service


def _patch_stack(
    *,
    image_count: int,
    min_required: int = 4,
    has_pdf: bool = False,
    poller_result_count: int | None = None,
    poller_phase_reached: int = 2,
):
    """
    Patch all collaborators of `confirm_base_documentation` so the
    function runs without touching DB, Redis, or network.
    """
    from agent.services.element_data_service import TwoPhasePollingResult

    poller_count = (
        poller_result_count if poller_result_count is not None else image_count
    )
    poller_result = TwoPhasePollingResult(
        count=poller_count,
        phase_reached=poller_phase_reached,
        feedback_sent=True,
    )

    class _PatchStack:
        def __init__(self):
            self._patches: list = []
            self.mocks: dict = {}

        def __enter__(self):
            batch_service = _make_batch_service()
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
                    "agent.services.element_data_service._has_pdf_in_base_docs",
                    new_callable=AsyncMock,
                    return_value=has_pdf,
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
                _patch(
                    "agent.services.element_data_service.set_collection_step",
                    side_effect=lambda fsm, step: {
                        **(fsm or {}),
                        "step": step.value if hasattr(step, "value") else step,
                    },
                ),
                _patch(
                    "agent.services.element_data_service.build_case_update",
                    side_effect=lambda fsm, patch_: {**(fsm or {}), **(patch_ or {})},
                ),
            ]

            active = [p.__enter__() for p in self._patches]
            (
                self.mocks["image_count"],
                self.mocks["min_required"],
                self.mocks["has_pdf"],
                self.mocks["batch_svc_factory"],
                self.mocks["build_scope"],
                self.mocks["PollerClass"],
                self.mocks["escalate"],
                self.mocks["set_step"],
                self.mocks["build_update"],
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
# Phase 1 — transition emission assertions
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfirmBaseDocsEmitsTransition:
    """Spec: success paths MUST emit `_state_update._transition_to = "collect_personal"`."""

    async def test_confirm_base_docs_happy_emits_transition(self) -> None:
        """image_count >= min → success path returns `_transition_to` in envelope."""
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(image_count=4, min_required=4) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=None,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is True
        state_update = result.get("_state_update") or {}
        assert state_update.get("_transition_to") == "collect_personal", (
            "Success path must emit _state_update._transition_to='collect_personal' "
            "per ADR-005 / spec fix-base-docs-transition-guard"
        )
        mocks["escalate"].assert_not_called()

    async def test_confirm_base_docs_polymorphic_pdf_emits_transition(self) -> None:
        """
        One PDF present (polymorphic path) advances unconditionally → must
        still surface `_transition_to` in `_state_update`.
        """
        from agent.services.element_data_service import confirm_base_documentation

        # image_count = 1, but has_pdf → polymorphic path
        with _patch_stack(
            image_count=1, min_required=4, has_pdf=True
        ) as mocks:
            result = await confirm_base_documentation(
                usuario_confirma=None,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        assert result.get("success") is True
        state_update = result.get("_state_update") or {}
        assert state_update.get("_transition_to") == "collect_personal"
        mocks["escalate"].assert_not_called()

    async def test_confirm_base_docs_poll_success_emits_transition(self) -> None:
        """Poller recovers to >= min on phase1 → still emits `_transition_to`."""
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
        state_update = result.get("_state_update") or {}
        assert state_update.get("_transition_to") == "collect_personal"

    async def test_confirm_base_docs_idempotent_no_transition(self) -> None:
        """
        FSM already past (`collect_personal`): envelope returns success+already_confirmed
        BUT `_state_update` must NOT contain `_transition_to` (AD-2: no re-emission
        once already in personal).
        """
        from agent.services.element_data_service import confirm_base_documentation

        past_ctx = {**BASE_MODE_CONTEXT, "expediente_sub_mode": "collect_personal"}
        with _patch_stack(image_count=0, min_required=4):
            result = await confirm_base_documentation(
                usuario_confirma=True,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=past_ctx,
            )

        assert result.get("already_confirmed") is True
        state_update = result.get("_state_update") or {}
        assert "_transition_to" not in state_update, (
            "Idempotent branch must NOT emit _transition_to (FSM already past)"
        )

    async def test_confirm_base_docs_insufficient_no_transition(self) -> None:
        """
        Insufficient docs + user not confirming → envelope lacks `_transition_to`.
        """
        from agent.services.element_data_service import confirm_base_documentation

        with _patch_stack(image_count=0, min_required=4):
            result = await confirm_base_documentation(
                usuario_confirma=False,
                case_id="case-1",
                conversation_id="conv-1",
                mode_context=BASE_MODE_CONTEXT,
            )

        state_update = result.get("_state_update") or {}
        assert "_transition_to" not in state_update
        assert result.get("success") is False

    async def test_confirm_base_docs_escalation_no_transition(self) -> None:
        """
        Both polling phases fail → escalation branch, envelope MUST NOT emit
        `_transition_to`.
        """
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

        assert result.get("success") is False
        assert result.get("escalated") is True
        state_update = result.get("_state_update") or {}
        assert "_transition_to" not in state_update
        mocks["escalate"].assert_called_once()
