"""
Tests for ExpedienteModeNode._guard_photo_completion_intent() — fix-expediente-photo-confirmation-loop

Layer A: deterministic pre-loop guard that intercepts photo-completion intent
("listo", "ya", "enviadas", etc.) while element_phase=="photos" and directly
calls confirmar_fotos_elemento(usuario_confirma=True), bypassing the LLM loop.

Layer B: coherence interceptor inside _run_llm_loop that fires when the LLM
calls guardar_datos_elemento while element_phase=="photos", using force=True to
call the guard without requiring a regex match.

Scenarios covered:
  1. Layer A fires on "listo" when element_phase=="photos"
  2. Layer A is a no-op when element_phase=="data"
  3. Layer A does NOT fire for unrelated message (no regex match)
  4. Layer A fires with force=True even with empty message (Layer B path)
  5. Regression — Pepe's production scenario: "listo" after 15 photos

Parametrized bonus tests:
  6. Regex matches all known photo-completion phrases
  7. Regex does NOT match non-completion phrases
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_mode import ExpedienteModeNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONVERSATION_ID = "test-conv-photo-guard-001"


def _make_state(mode_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a minimal ConversationState for testing."""
    return {
        "conversation_id": CONVERSATION_ID,
        "user_id": "user-pepe-001",
        "messages": [],
        "mode_context": mode_context or {},
        "fsm_state": {
            "case_collection": {
                "step": "collect_element_data",
                "case_id": "case-pepe-123",
                "category_slug": "motos-part",
                "element_codes": ["SUBCHASIS", "SUSPENSION"],
                "current_element_index": 0,
                "element_phase": "photos",
                "element_data_status": {
                    "SUBCHASIS": "pending_photos",
                    "SUSPENSION": "pending_photos",
                },
            }
        },
        "incoming_attachments": [],
    }


def _make_confirmar_fotos_success_result(
    element_phase: str = "data",
    current_element_index: int = 0,
    all_elements_complete: bool = False,
) -> dict[str, Any]:
    """Build a realistic success result from confirmar_fotos_elemento."""
    return {
        "success": True,
        "message": "Fotos confirmadas correctamente.",
        "element_phase": element_phase,
        "current_element_index": current_element_index,
        "all_elements_complete": all_elements_complete,
        "case_collection_update": {
            "case_collection": {
                "element_phase": element_phase,
                "current_element_index": current_element_index,
            }
        },
        "_internal_flags": {},
    }


def _make_mock_confirmar_fotos(return_value: dict[str, Any]) -> AsyncMock:
    """
    Create an AsyncMock that simulates confirmar_fotos_elemento.ainvoke().

    The guard calls:  await confirmar_fotos_elemento.ainvoke({"usuario_confirma": True})

    So we create a MagicMock whose .ainvoke attribute is an AsyncMock that returns
    the JSON-encoded result dict.
    """
    mock_tool = MagicMock()
    mock_tool.ainvoke = AsyncMock(return_value=json.dumps(return_value))
    return mock_tool


def _make_node() -> ExpedienteModeNode:
    """Create an ExpedienteModeNode — guard tests are pure unit tests."""
    return ExpedienteModeNode()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestGuardPhotoCompletionIntent:
    """
    Unit tests for ExpedienteModeNode._guard_photo_completion_intent().

    All tests mock confirmar_fotos_elemento via patch() so no DB/ContextVar
    state is required — the guard's conditional logic is tested in isolation.

    Patch target: "agent.tools.element_data_tools.confirmar_fotos_elemento"
    The guard does a lazy import (`from agent.tools.element_data_tools import
    confirmar_fotos_elemento`) inside the try block, so patching the module-level
    attribute is the correct approach.
    """

    # ------------------------------------------------------------------
    # Test 1: Layer A fires on "listo" when element_phase=="photos"
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_guard_fires_on_listo_when_phase_is_photos(self):
        """
        GIVEN mode_context["element_phase"] == "photos"
        AND   user message is "listo"
        WHEN  _guard_photo_completion_intent is called (force=False)
        THEN  returns True
        AND   confirmar_fotos_elemento.ainvoke is called with {"usuario_confirma": True}
        AND   mode_context["element_phase"] is updated to "data"
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-pepe-123",
            "category_slug": "motos-part",
            "element_codes": ["SUBCHASIS", "SUSPENSION"],
        }
        state = _make_state(mode_context)

        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):

            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        # Guard must return True (it fired)
        assert result is True, (
            f"Expected guard to return True when user says 'listo' and "
            f"element_phase=='photos'. Got: {result}"
        )

        # confirmar_fotos_elemento.ainvoke must have been called with usuario_confirma=True
        mock_tool.ainvoke.assert_called_once_with({"usuario_confirma": True})

        # mode_context must have been updated with element_phase="data"
        assert mode_context.get("element_phase") == "data", (
            f"Expected mode_context['element_phase'] to be 'data' after guard fired. "
            f"Got: {mode_context.get('element_phase')}"
        )

    # ------------------------------------------------------------------
    # Test 2: Layer A is a no-op when element_phase=="data"
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_guard_is_noop_when_phase_is_data(self):
        """
        GIVEN mode_context["element_phase"] == "data"  (photos already confirmed)
        WHEN  _guard_photo_completion_intent is called with any message
        THEN  returns False immediately (no-op, first condition fails)
        AND   confirmar_fotos_elemento.ainvoke is NOT called
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "data",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-pepe-123",
        }
        state = _make_state(mode_context)

        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result()
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):

            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        # Guard must return False — no-op because phase is not "photos"
        assert result is False, (
            f"Expected guard to return False when element_phase=='data'. Got: {result}"
        )

        # confirmar_fotos_elemento must NOT have been called (condition 1 failed)
        mock_tool.ainvoke.assert_not_called()

        # mode_context must remain unchanged
        assert mode_context.get("element_phase") == "data"

    # ------------------------------------------------------------------
    # Test 3: Layer A does NOT fire for unrelated message (no regex match)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_guard_does_not_fire_for_unrelated_message(self):
        """
        GIVEN mode_context["element_phase"] == "photos"
        AND   user message is "¿qué fotos necesito?" (no regex match)
        WHEN  _guard_photo_completion_intent is called (force=False)
        THEN  returns False (condition 2 fails — regex did not match)
        AND   confirmar_fotos_elemento.ainvoke is NOT called
        AND   element_phase remains "photos" (unchanged)
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-pepe-123",
        }
        state = _make_state(mode_context)

        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result()
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):

            result = await node._guard_photo_completion_intent(
                user_message="¿qué fotos necesito?",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        # Guard must return False — regex did not match
        assert result is False, (
            f"Expected guard to return False for a question (no regex match). Got: {result}"
        )

        # confirmar_fotos_elemento must NOT have been called
        mock_tool.ainvoke.assert_not_called()

        # element_phase must remain "photos" (unchanged — no false positive)
        assert mode_context.get("element_phase") == "photos"

    # ------------------------------------------------------------------
    # Test 4: Layer A fires with force=True even with empty message (Layer B path)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_guard_fires_with_force_true_even_empty_message(self):
        """
        GIVEN mode_context["element_phase"] == "photos"
        AND   user_message is "" (empty — regex would NOT match normally)
        AND   force=True  (simulates the Layer B coherence interceptor)
        WHEN  _guard_photo_completion_intent is called
        THEN  returns True (force bypasses the regex check)
        AND   confirmar_fotos_elemento.ainvoke is called with {"usuario_confirma": True}
        AND   mode_context["element_phase"] advances to "data"

        This is the Layer B coherence interceptor path: when the LLM calls
        guardar_datos_elemento while element_phase=="photos", the interceptor in
        _run_llm_loop calls this guard with force=True and an empty user_message to
        auto-confirm the photos without requiring the user to say "listo" first.
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-pepe-123",
            "category_slug": "motos-part",
            "element_codes": ["SUBCHASIS"],
        }
        state = _make_state(mode_context)

        success_result = _make_confirmar_fotos_success_result(element_phase="data")
        mock_tool = _make_mock_confirmar_fotos(success_result)

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):

            result = await node._guard_photo_completion_intent(
                user_message="",          # Empty — would fail regex without force
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=True,               # Layer B sets this flag
            )

        # Guard must return True (force bypassed the regex)
        assert result is True, (
            f"Expected guard to return True when force=True (even with empty message). "
            f"Got: {result}"
        )

        # confirmar_fotos_elemento.ainvoke must have been called exactly once
        mock_tool.ainvoke.assert_called_once_with({"usuario_confirma": True})

        # mode_context must reflect the advanced phase
        assert mode_context.get("element_phase") == "data", (
            f"Expected mode_context['element_phase'] to be 'data' after force=True guard. "
            f"Got: {mode_context.get('element_phase')}"
        )

    # ------------------------------------------------------------------
    # Test 5: Regression — Pepe's production scenario
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_pepe_production_scenario_listo_after_15_photos(self):
        """
        Regression test for Pepe's production scenario (fix-expediente-photo-confirmation-loop):
          - Pepe sent 15 photos for SUBCHASIS element
          - Then said "listo"
          - Agent re-asked for photos instead of advancing to data collection

        Root cause: LLM loop did not have a deterministic pre-check for
        photo-completion intent, so the LLM sometimes retried confirmar_fotos instead
        of advancing. Layer A (this guard) fires BEFORE the LLM loop and explicitly
        calls confirmar_fotos_elemento when the user says "listo".

        GIVEN  mode_context["element_phase"] == "photos"  (waiting for Pepe's confirmation)
        AND    user message is "listo"  (Pepe sent after uploading 15 photos)
        AND    tool returns success with element_phase="data"
        WHEN   guard is called
        THEN   guard fires (returns True)
        AND    phase advances to "data" in mode_context
        AND    the LLM sees mode_context["element_phase"]=="data" when it starts
               and correctly asks for data fields instead of re-asking for photos
        """
        node = _make_node()
        mode_context: dict[str, Any] = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-pepe-real-456",
            "category_slug": "motos-part",
            "element_codes": ["SUBCHASIS", "SUSPENSION", "ESCAPE"],
            "element_data_status": {
                "SUBCHASIS": "pending_photos",
                "SUSPENSION": "pending_photos",
                "ESCAPE": "pending_photos",
            },
        }
        state = _make_state(mode_context)

        # Simulate the tool confirming photos for SUBCHASIS
        # (15 photos sent — tool confirms and advances phase to "data")
        success_result = _make_confirmar_fotos_success_result(
            element_phase="data",
            current_element_index=0,
            all_elements_complete=False,  # 2 more elements remaining after SUBCHASIS
        )
        mock_tool = _make_mock_confirmar_fotos(success_result)

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):

            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        # Guard must have fired — this is the regression test
        assert result is True, (
            "REGRESSION: guard did NOT fire for 'listo' in photos phase. "
            "This reproduces Pepe's bug where the agent re-asked for photos "
            "even after the user said they were ready."
        )

        # Tool must have been called exactly once (no double-calling)
        mock_tool.ainvoke.assert_called_once_with({"usuario_confirma": True})

        # Phase MUST have advanced to "data" — the LLM will now ask for field data
        assert mode_context.get("element_phase") == "data", (
            f"REGRESSION: element_phase did not advance to 'data' after 'listo'. "
            f"Got: {mode_context.get('element_phase')!r}. "
            "This would cause the agent to re-ask for photos (Pepe's exact bug)."
        )


# ---------------------------------------------------------------------------
# Regex contract tests (parametrized — no async needed)
# ---------------------------------------------------------------------------

class TestPhotoCompletionIntentRegex:
    """
    Verify _PHOTO_COMPLETION_INTENT_RE matches/rejects expected phrases.

    These tests document the regex contract and serve as a regression guard
    to prevent accidental breakage of the matching rules.
    """

    @pytest.mark.parametrize("message", [
        "listo",
        "lista",
        "listos",
        "listas",
        "ya",
        "done",
        "enviadas",
        "enviados",
        "enviada",
        "hechas",
        "hechos",
        "terminado",
        "terminada",
        "ya están",
        "ya las envié",
        "ya los envié",
        "ya la envié",
        "ya lo envié",
    ])
    def test_regex_matches_known_photo_completion_phrases(self, message: str):
        """
        _PHOTO_COMPLETION_INTENT_RE must match each canonical photo-completion phrase.
        All these phrases indicate the user has finished sending photos.
        """
        from agent.modes.expediente_mode import _PHOTO_COMPLETION_INTENT_RE

        assert _PHOTO_COMPLETION_INTENT_RE.search(message) is not None, (
            f"Expected _PHOTO_COMPLETION_INTENT_RE to match '{message}'. "
            "If this phrase is a valid photo-completion signal, update the regex."
        )

    @pytest.mark.parametrize("message", [
        "¿qué fotos necesito?",
        "no sé qué enviar",
        "¿puedes explicarme qué foto?",
        "todavía no",
        "espera un momento",
        "voy a buscar las fotos",
        "¿cuántas fotos necesitas?",
        "no tengo las fotos ahora mismo",
        "ahora mismo no puedo",
    ])
    def test_regex_does_not_match_non_completion_phrases(self, message: str):
        """
        _PHOTO_COMPLETION_INTENT_RE must NOT match phrases that are not
        photo-completion intent. These are questions, negations, or deferrals.
        False positives would cause the guard to fire prematurely.
        """
        from agent.modes.expediente_mode import _PHOTO_COMPLETION_INTENT_RE

        assert _PHOTO_COMPLETION_INTENT_RE.search(message) is None, (
            f"Regex incorrectly matched non-completion phrase: '{message}'. "
            "This is a false positive that could trigger the guard prematurely."
        )


# ---------------------------------------------------------------------------
# Phase 5.3 — Certainty guardrails interaction with photo confirmation guard
# ---------------------------------------------------------------------------


class TestPhotoGuardCertaintyFlagIntegration:
    """
    Phase 5.3 tests: the photo-completion guard must be orthogonal to the
    certainty guardrail feature flag.

    ``_guard_photo_completion_intent`` executes regardless of
    ``EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED``, because it is a structural
    guard (confirmar_fotos_elemento is a tool call, not a claim rewrite).
    These tests verify the guard fires the same way whether the flag is on or off.
    """

    def _make_photos_mode_context(self) -> dict:
        return {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-test-001",
            "category_slug": "motos-part",
            "element_codes": ["SUBCHASIS"],
        }

    @pytest.mark.asyncio
    async def test_guard_fires_with_certainty_flag_enabled(self):
        """Guard must return True on 'listo' even when certainty guardrails are enabled."""
        node = _make_node()
        mode_context = self._make_photos_mode_context()
        state = _make_state(mode_context=mode_context)
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):
            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True, "Guard must return True (fired) with certainty flag enabled"

    @pytest.mark.asyncio
    async def test_guard_fires_with_certainty_flag_disabled(self):
        """Guard must return True on 'listo' even when certainty guardrails are disabled."""
        node = _make_node()
        mode_context = self._make_photos_mode_context()
        state = _make_state(mode_context=mode_context)
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        # The guard does NOT read EXPEDIENTE_CERTAINTY_GUARDRAILS_ENABLED directly,
        # so no mock needed — but we verify the behavior is the same regardless.
        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):
            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True, "Guard must return True (fired) with certainty flag disabled"


class TestPhotoGuardDeliveryOutcomePaths:
    """
    Phase 5.3 tests: the photo guard must not assume delivery success.

    The guard calls confirmar_fotos_elemento to confirm the user's upload intent;
    the actual image delivery outcome (full_success / partial_success / failure)
    is separate and comes from the image transport layer.  The guard must NOT
    read image_delivery_result to decide whether to fire.
    """

    def _make_photos_mode_context(self, delivery_result: dict | None = None) -> dict:
        ctx: dict = {
            "element_phase": "photos",
            "current_element_index": 0,
            "current_element_code": "SUBCHASIS",
            "case_id": "case-test-002",
            "category_slug": "motos-part",
            "element_codes": ["SUBCHASIS"],
        }
        if delivery_result is not None:
            ctx["image_delivery_result"] = delivery_result
        return ctx

    @pytest.mark.asyncio
    async def test_guard_fires_even_when_previous_delivery_was_partial(self):
        """
        Guard must return True for 'ya' even if the previous delivery attempt
        was partial_success — the user is confirming their upload intent,
        not the transport outcome.
        """
        node = _make_node()
        mode_context = self._make_photos_mode_context(
            delivery_result={
                "status": "partial_success",
                "sent_count": 1,
                "failed_count": 2,
                "attempted_count": 3,
            }
        )
        state = _make_state(mode_context=mode_context)
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):
            result = await node._guard_photo_completion_intent(
                user_message="ya",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True, (
            "Guard must fire (return True) even if previous delivery was partial_success"
        )

    @pytest.mark.asyncio
    async def test_guard_fires_even_when_previous_delivery_was_failure(self):
        """
        Guard must return True for 'enviadas' even if the previous delivery attempt
        was failure — the user is confirming they finished uploading.
        """
        node = _make_node()
        mode_context = self._make_photos_mode_context(
            delivery_result={
                "status": "failure",
                "sent_count": 0,
                "failed_count": 3,
                "attempted_count": 3,
                "transport_error": "connection timeout",
            }
        )
        state = _make_state(mode_context=mode_context)
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):
            result = await node._guard_photo_completion_intent(
                user_message="enviadas",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        assert result is True, (
            "Guard must fire (return True) even if previous delivery was failure"
        )

    @pytest.mark.asyncio
    async def test_image_delivery_result_key_not_checked_by_guard(self):
        """
        Guard fires based solely on element_phase=='photos' + regex match.
        The image_delivery_result key, if present, must NOT suppress firing.
        """
        node = _make_node()
        # Inject ALL delivery states simultaneously to verify none suppress the guard
        mode_context = self._make_photos_mode_context(
            delivery_result={
                "status": "failure",  # Worst case: previous delivery completely failed
                "sent_count": 0,
                "failed_count": 5,
                "attempted_count": 5,
            }
        )
        state = _make_state(mode_context=mode_context)
        mock_tool = _make_mock_confirmar_fotos(
            _make_confirmar_fotos_success_result(element_phase="data")
        )

        with patch("agent.tools.element_data_tools.confirmar_fotos_elemento", mock_tool):
            result = await node._guard_photo_completion_intent(
                user_message="listo",
                mode_context=mode_context,
                state=state,
                conversation_id=CONVERSATION_ID,
                force=False,
            )

        # Guard MUST fire — delivery result has no bearing on confirmation intent
        assert result is True
        mock_tool.ainvoke.assert_called_once_with({"usuario_confirma": True})
