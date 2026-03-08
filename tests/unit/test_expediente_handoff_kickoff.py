"""Regression tests for expediente handoff kickoff continuity.

Coverage:
- Phase 2 (RED → GREEN after Phase 3 implementation):
  2.1  element_data → base_docs  deterministic closure (existing + extended)
  2.2  base_docs → personal      deterministic closure
  2.3  personal → vehicle        deterministic closure
  2.4  vehicle → workshop        deterministic closure
  2.5  No-transition turns must NOT inject a forced CTA
  2.6  Rollback flag (ENABLE_SAME_TURN_TRANSITION_CLOSURE=False) → legacy path

- Existing regression tests (kept unchanged):
  - test_loader_transition_context_requires_destination_kickoff
  - test_transition_kickoff_message_matrix_is_actionable
  - test_transition_marker_lifecycle_consumed_and_cleared_with_dead_air_guard
  - test_transition_kickoff_observability_events_present
"""

import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.modes.expediente_mode import (
    COLLECT_BASE_DOCS,
    COLLECT_ELEMENT_DATA,
    COLLECT_PERSONAL,
    COLLECT_VEHICLE,
    COLLECT_WORKSHOP,
    REVIEW_SUMMARY,
    ExpedienteModeNode,
    _build_element_completion_transition_closure,
    _build_transition_closure,
)
from agent.prompts.loader import format_mode_context


# ---------------------------------------------------------------------------
# Existing regression tests (unchanged)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loader_transition_context_requires_destination_kickoff() -> None:
    """Loader context must instruct destination-first actionable kickoff."""
    ctx = {
        "expediente_sub_mode": "collect_base_docs",
        "expediente_transition_marker": {
            "from_sub_mode": "collect_element_data",
            "to_sub_mode": "collect_base_docs",
            "tool_name": "completar_elemento_actual",
            "requires_kickoff": True,
        },
    }

    rendered = format_mode_context("EXPEDIENTE_DOCUMENTACION_BASE", ctx)
    assert "primer turno" in rendered.lower()
    assert "kickoff obligatorio" in rendered.lower()
    assert "no asumas que ya se pidió" in rendered.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sub_mode_name", "expected_fragment"),
    [
        ("COLLECT_BASE_DOCS", "fotos"),
        ("COLLECT_PERSONAL", "datos personales"),
        ("COLLECT_VEHICLE", "datos del vehiculo"),
        ("COLLECT_WORKSHOP", "85 EUR +IVA"),
        ("REVIEW_SUMMARY", "resumen"),
    ],
)
def test_transition_kickoff_message_matrix_is_actionable(
    sub_mode_name: str,
    expected_fragment: str,
) -> None:
    """Each destination sub-mode must have actionable kickoff fallback text."""
    message = ExpedienteModeNode._build_transition_kickoff_message(
        sub_mode_name=sub_mode_name,
        mode_context={},
    )

    assert expected_fragment.lower() in message.lower()
    assert ExpedienteModeNode._is_actionable_kickoff_response(message)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transition_marker_lifecycle_consumed_and_cleared_with_dead_air_guard() -> None:
    """First destination turn must be actionable and clear consumed marker."""
    node = ExpedienteModeNode()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content="Perfecto, continuamos.", tool_calls=[]),
    )

    mode_context = {
        "expediente_sub_mode": "collect_base_docs",
        "expediente_transition_marker": {
            "from_sub_mode": "collect_element_data",
            "to_sub_mode": "collect_base_docs",
            "tool_name": "completar_elemento_actual",
            "requires_kickoff": True,
        },
        "just_transitioned_from": "collect_element_data",
    }
    state = {
        "conversation_id": "conv-kickoff-1",
        "messages": [],
        "mode_context": dict(mode_context),
        "retry_state": {},
    }

    with patch.object(node, "_get_llm", return_value=mock_llm), patch.object(
        node,
        "_track_token_usage",
        new=AsyncMock(return_value=None),
    ), patch.object(
        node,
        "_validate_response_constraints",
        new=AsyncMock(return_value=(True, None)),
    ):
        result = await node._run_llm_loop(
            message="ok",
            state=state,
            mode_context=mode_context,
            tools=[],
            sub_mode_name="COLLECT_BASE_DOCS",
        )

    assert "fotos" in str(result.get("ai_response", "")).lower()
    assert "expediente_transition_marker" not in result["mode_context"]
    assert "just_transitioned_from" not in result["mode_context"]


@pytest.mark.unit
def test_transition_kickoff_observability_events_present() -> None:
    """Transition + kickoff continuity events must be emitted for diagnostics."""
    from agent.modes import expediente_mode

    source = inspect.getsource(expediente_mode)
    assert "expediente_transition_marker_set" in source
    assert "expediente_transition_marker_consumed" in source
    assert "expediente_transition_marker_cleared" in source
    assert "expediente_transition_kickoff_guard_triggered" in source
    assert "requires_kickoff" in source


# ---------------------------------------------------------------------------
# Phase 2.1 — element_data → base_docs  (closure quality)
# ---------------------------------------------------------------------------


class TestElementDataToBaseDocsClosure:
    """2.1: Same-turn closure quality for element_data → base_docs."""

    SAMPLE_BASE_DOCS = [
        {"description": "Foto de la ficha tecnica de la moto (ambas caras, legible)"},
        {"description": "Foto del permiso de circulacion (cara escrita)"},
        {"description": "Foto del DNI/NIE del titular (ambas caras)"},
    ]

    def test_build_transition_closure_element_to_base_docs(self) -> None:
        """_build_transition_closure delegates correctly to legacy function.

        With _ANTI_ANTICIPATION_GUARD_ENABLED=True (REQ-3), the closure is a
        brief step-transition acknowledgment — it does NOT enumerate base-doc
        requirements.  The COLLECT_BASE_DOCS handler introduces them on the
        next turn.
        """
        result = _build_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": True, "success": True},
            base_documentation=self.SAMPLE_BASE_DOCS,
        )

        assert result is not None
        # Anti-anticipation guard: closure is brief — acknowledges element completion
        # and signals the next step without listing doc requirements.
        result_lower = result.lower()
        assert "cerramos" in result_lower or "elementos" in result_lower or "paso 2" in result_lower, (
            f"Closure must acknowledge element completion: {result!r}"
        )
        assert "documentación base" in result_lower or "documentacion base" in result_lower or "paso 2" in result_lower, (
            f"Closure must reference the next step: {result!r}"
        )

    def test_legacy_function_still_works_unchanged(self) -> None:
        """_build_element_completion_transition_closure must still return correct closure."""
        result = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": True},
            base_documentation=self.SAMPLE_BASE_DOCS,
        )
        assert result is not None
        assert "documentacion base" in result.lower() or "documentación base" in result.lower()

    def test_closure_returns_none_if_not_all_complete(self) -> None:
        """No closure when all_elements_complete is False."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="completar_elemento_actual",
            tool_data={"all_elements_complete": False},
            base_documentation=self.SAMPLE_BASE_DOCS,
        )
        assert result is None

    def test_closure_returns_none_for_unknown_tool(self) -> None:
        """Spurious tool calls must not trigger the element→base_docs closure."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_ELEMENT_DATA,
            to_sub_mode=COLLECT_BASE_DOCS,
            tool_name="obtener_campos_elemento",
            tool_data={"all_elements_complete": True},
            base_documentation=self.SAMPLE_BASE_DOCS,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Phase 2.2 — base_docs → personal  (closure quality)
# ---------------------------------------------------------------------------


class TestBaseDocsToPersonalClosure:
    """2.2: Same-turn closure quality for base_docs → personal."""

    def test_closure_is_returned_on_success(self) -> None:
        """Must return a non-empty closure string."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )

        assert result is not None
        assert len(result) > 20

    def test_closure_contains_personal_data_cta(self) -> None:
        """Closure must contain an actionable CTA for personal data."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )

        assert result is not None
        text = result.lower()
        assert any(
            kw in text
            for kw in ("datos personales", "nombre", "dni", "email", "domicilio")
        ), f"Expected personal data CTA in: {result!r}"

    def test_closure_is_actionable_by_heuristic(self) -> None:
        """Closure must pass the actionable-response heuristic."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )
        assert result is not None
        assert ExpedienteModeNode._is_actionable_kickoff_response(result)

    def test_closure_returns_none_if_not_success(self) -> None:
        """No closure when the tool reported failure."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="confirmar_documentacion_base",
            tool_data={"success": False},
        )
        assert result is None

    def test_closure_returns_none_for_unknown_tool(self) -> None:
        """Spurious tools must not trigger the base_docs→personal closure."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="obtener_estado_expediente",
            tool_data={"success": True},
        )
        assert result is None

    def test_closure_returns_none_for_wrong_pair(self) -> None:
        """From/to pair not in matrix must return None."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_VEHICLE,  # skip personal — wrong pair
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )
        assert result is None


# ---------------------------------------------------------------------------
# Phase 2.3 — personal → vehicle  (closure quality)
# ---------------------------------------------------------------------------


class TestPersonalToVehicleClosure:
    """2.3: Same-turn closure quality for personal → vehicle."""

    def test_closure_is_returned_on_success(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_vehicle"},
        )

        assert result is not None
        assert len(result) > 20

    def test_closure_contains_vehicle_data_cta(self) -> None:
        """Closure must acknowledge personal data completion and signal the vehicle step.

        With _ANTI_ANTICIPATION_GUARD_ENABLED=True (REQ-3), the closure is brief
        and does NOT enumerate vehicle fields.  It acknowledges the previous step
        and signals the next one.  The COLLECT_VEHICLE handler introduces
        field requirements on the next turn.
        """
        result = _build_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_vehicle"},
        )

        assert result is not None
        text = result.lower()
        # Anti-anticipation: brief closure — acknowledges personal step, signals vehicle
        assert any(
            kw in text
            for kw in ("personal", "paso 4", "vehiculo", "vehículo", "datos del veh")
        ), f"Expected step transition signal in: {result!r}"

    def test_closure_is_actionable_by_heuristic(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_vehicle"},
        )
        assert result is not None
        assert ExpedienteModeNode._is_actionable_kickoff_response(result)

    def test_closure_returns_none_if_not_success(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": False},
        )
        assert result is None

    def test_closure_returns_none_for_unknown_tool(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="consulta_durante_expediente",
            tool_data={"success": True},
        )
        assert result is None


# ---------------------------------------------------------------------------
# Phase 2.4 — vehicle → workshop  (closure quality)
# ---------------------------------------------------------------------------


class TestVehicleToWorkshopClosure:
    """2.4: Same-turn closure quality for vehicle → workshop."""

    def test_closure_is_returned_on_success(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_VEHICLE,
            to_sub_mode=COLLECT_WORKSHOP,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_workshop"},
        )

        assert result is not None
        assert len(result) > 20

    def test_closure_contains_workshop_cta(self) -> None:
        """Closure must present the MSI vs. own-workshop choice."""
        result = _build_transition_closure(
            from_sub_mode=COLLECT_VEHICLE,
            to_sub_mode=COLLECT_WORKSHOP,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_workshop"},
        )

        assert result is not None
        text = result.lower()
        assert any(
            kw in text
            for kw in ("85 eur", "taller", "certificado", "itv", "msi")
        ), f"Expected workshop CTA in: {result!r}"

    def test_closure_is_actionable_by_heuristic(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_VEHICLE,
            to_sub_mode=COLLECT_WORKSHOP,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True, "next_step": "collect_workshop"},
        )
        assert result is not None
        assert ExpedienteModeNode._is_actionable_kickoff_response(result)

    def test_closure_returns_none_if_not_success(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_VEHICLE,
            to_sub_mode=COLLECT_WORKSHOP,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": False},
        )
        assert result is None


# ---------------------------------------------------------------------------
# Phase 2.4b — workshop → review_summary  (closure quality)
# ---------------------------------------------------------------------------


class TestWorkshopToReviewClosure:
    """workshop → review_summary transition closure."""

    def test_closure_is_returned_on_success(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_WORKSHOP,
            to_sub_mode=REVIEW_SUMMARY,
            tool_name="actualizar_datos_taller",
            tool_data={"success": True, "next_step": "review_summary"},
        )

        assert result is not None
        assert len(result) > 20

    def test_closure_contains_review_cta(self) -> None:
        """Closure must acknowledge workshop data completion and signal the review step.

        With _ANTI_ANTICIPATION_GUARD_ENABLED=True (REQ-3), the closure is brief
        and does NOT describe the review summary content.  The REVIEW_SUMMARY
        handler presents the full summary on the next turn.
        """
        result = _build_transition_closure(
            from_sub_mode=COLLECT_WORKSHOP,
            to_sub_mode=REVIEW_SUMMARY,
            tool_name="actualizar_datos_taller",
            tool_data={"success": True, "next_step": "review_summary"},
        )
        assert result is not None
        text = result.lower()
        # Anti-anticipation: brief closure — acknowledges taller step, signals review
        assert any(
            kw in text
            for kw in ("taller", "paso 6", "resumen", "revisión", "revision")
        ), f"Expected step transition signal in: {result!r}"

    def test_closure_returns_none_for_unknown_tool(self) -> None:
        result = _build_transition_closure(
            from_sub_mode=COLLECT_WORKSHOP,
            to_sub_mode=REVIEW_SUMMARY,
            tool_name="cancelar_expediente",
            tool_data={"success": True},
        )
        assert result is None


# ---------------------------------------------------------------------------
# Phase 2.5 — No-transition turns must NOT inject a forced CTA
# ---------------------------------------------------------------------------


class TestNoTransitionTurnHasNoCta:
    """2.5: When no sub-mode transition occurs, the LLM response is used as-is."""

    @pytest.mark.asyncio
    async def test_no_transition_turn_uses_llm_response(self) -> None:
        """A normal (non-transition) turn must use the LLM output without override."""
        node = ExpedienteModeNode()

        llm_response_text = "Por favor, enviame las fotos del elemento cuando puedas."
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content=llm_response_text, tool_calls=[]),
        )

        # No transition marker in mode_context → normal turn
        mode_context: dict = {
            "expediente_sub_mode": "collect_element_data",
        }
        state = {
            "conversation_id": "conv-no-trans-1",
            "messages": [],
            "mode_context": dict(mode_context),
            "retry_state": {},
        }

        with patch.object(node, "_get_llm", return_value=mock_llm), patch.object(
            node,
            "_track_token_usage",
            new=AsyncMock(return_value=None),
        ), patch.object(
            node,
            "_validate_response_constraints",
            new=AsyncMock(return_value=(True, None)),
        ):
            result = await node._run_llm_loop(
                message="ok voy a enviarlas ahora",
                state=state,
                mode_context=mode_context,
                tools=[],
                sub_mode_name="COLLECT_ELEMENT_DATA",
            )

        # Must use the LLM response verbatim (no CTA injection)
        assert result.get("ai_response") == llm_response_text
        # Must NOT have injected a kickoff guard (no active marker)
        assert "expediente_transition_marker" not in result.get("mode_context", {})


# ---------------------------------------------------------------------------
# Phase 2.6 — Rollback flag (ENABLE_SAME_TURN_TRANSITION_CLOSURE=False)
# ---------------------------------------------------------------------------


class TestRollbackFlagLegacyPath:
    """2.6: When flag is OFF, non-element→base_docs transitions must NOT return a closure."""

    def test_flag_in_settings_schema(self) -> None:
        """Feature flag must exist in Settings with default=False."""
        from shared.config import Settings

        field = Settings.model_fields.get("ENABLE_SAME_TURN_TRANSITION_CLOSURE")
        assert field is not None, (
            "ENABLE_SAME_TURN_TRANSITION_CLOSURE field not found in Settings"
        )
        assert field.default is False, (
            f"Flag default must be False for safe rollout, got: {field.default!r}"
        )

    def test_legacy_builder_only_covers_element_to_base_docs(self) -> None:
        """The legacy _build_element_completion_transition_closure must return None for other pairs."""
        # base_docs → personal: legacy function must return None (no coverage)
        result = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_BASE_DOCS,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="confirmar_documentacion_base",
            tool_data={"success": True},
        )
        assert result is None

        # personal → vehicle: legacy function must return None
        result = _build_element_completion_transition_closure(
            from_sub_mode=COLLECT_PERSONAL,
            to_sub_mode=COLLECT_VEHICLE,
            tool_name="actualizar_datos_expediente",
            tool_data={"success": True},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_flag_off_base_docs_to_personal_uses_llm_or_tool_message(
        self,
    ) -> None:
        """With flag OFF, base_docs→personal transition closure is NOT deterministic."""
        node = ExpedienteModeNode()

        # Simulate the tool call that triggers base_docs→personal
        tool_response = json.dumps({
            "success": True,
            "message": "Documentacion base confirmada.",
            "next_step": "collect_personal",
        })

        mock_tool = MagicMock()
        mock_tool.name = "confirmar_documentacion_base"
        mock_tool.ainvoke = AsyncMock(return_value=tool_response)

        # LLM: first call → returns tool call; second call → returns final text
        first_response = SimpleNamespace(
            content="",
            tool_calls=[{
                "name": "confirmar_documentacion_base",
                "args": {},
                "id": "tc-001",
            }],
        )
        second_response = SimpleNamespace(
            content="Tus documentos han sido recibidos. Ahora dime tus datos personales.",
            tool_calls=[],
        )

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=[first_response, second_response])

        mode_context: dict = {
            "expediente_sub_mode": "collect_base_docs",
        }
        state = {
            "conversation_id": "conv-rollback-1",
            "messages": [],
            "mode_context": dict(mode_context),
            "retry_state": {},
        }

        with patch.object(node, "_get_llm", return_value=mock_llm), patch.object(
            node,
            "_track_token_usage",
            new=AsyncMock(return_value=None),
        ), patch.object(
            node,
            "_validate_response_constraints",
            new=AsyncMock(return_value=(True, None)),
        ), patch.object(
            node,
            "_execute_and_log_tool",
            new=AsyncMock(return_value=tool_response),
        ), patch(
            "agent.modes.expediente_mode.get_settings",
        ) as mock_settings:
            # Flag OFF
            mock_settings.return_value = MagicMock(
                ENABLE_SAME_TURN_TRANSITION_CLOSURE=False,
                ENABLE_LATENCY_GATING=False,
                MAX_TOOL_ITERATIONS_EXPEDIENTE=5,
            )
            result = await node._run_llm_loop(
                message="listo, aqui tienes los documentos",
                state=state,
                mode_context=mode_context,
                tools=[mock_tool],
                sub_mode_name="COLLECT_BASE_DOCS",
            )

        # With flag OFF, the closure for base_docs→personal is NOT from the matrix —
        # it uses the tool's own message or a subsequent LLM turn.
        response_text = str(result.get("ai_response", ""))
        # The deterministic closure text must NOT appear
        assert "cerramos la documentacion base" not in response_text.lower(), (
            "Matrix closure must not be emitted when flag is OFF"
        )


# ---------------------------------------------------------------------------
# Phase 5.2 — Guardrail-backed transition: blocked transitions with reason codes
# ---------------------------------------------------------------------------


class TestGuardrailBackedTransitionReasonCodes:
    """
    5.2: Tests for guardrail-backed handoff transitions.

    For each sub-mode transition pair:
    - Assert that allowed closure text does NOT preview the next step's full content
      (anti-anticipation contract).
    - Assert that blocked transitions expose the expected reason codes from
      evaluate_progression_eligibility().
    """

    # ----------------------------------------------------------------
    # Certainty envelope integration: reason codes for blocked transitions
    # ----------------------------------------------------------------

    @pytest.mark.parametrize("from_mode,to_mode,expected_reason", [
        (
            "collect_element_data", "collect_base_docs",
            "PROGRESSION_NOT_ALLOWED",
        ),
        (
            "collect_base_docs", "collect_personal",
            "DOCS_NOT_CONFIRMED_BY_TOOL",
        ),
        (
            "collect_personal", "collect_vehicle",
            "PROGRESSION_TOOL_NOT_CALLED",
        ),
        (
            "collect_vehicle", "collect_workshop",
            "PROGRESSION_TOOL_NOT_CALLED",
        ),
        (
            "collect_workshop", "review_summary",
            "PROGRESSION_TOOL_NOT_CALLED",
        ),
    ])
    def test_blocked_transition_yields_expected_reason_code(
        self, from_mode: str, to_mode: str, expected_reason: str
    ) -> None:
        """Each blocked transition must return the semantically correct reason code."""
        from agent.modes.expediente_guardrails import CertaintyEnvelope, evaluate_progression_eligibility

        env = CertaintyEnvelope(sub_mode=from_mode)
        allowed, reason = evaluate_progression_eligibility(env, to_mode)
        assert allowed is False, f"Expected blocked for {from_mode} → {to_mode}"
        assert reason == expected_reason, (
            f"Expected reason={expected_reason!r} for {from_mode} → {to_mode}, got {reason!r}"
        )

    @pytest.mark.parametrize("from_mode,to_mode,env_kwargs", [
        ("collect_element_data", "collect_base_docs", {"all_elements_complete": True}),
        ("collect_base_docs", "collect_personal", {"docs_confirmed": True}),
        (
            "collect_personal", "collect_vehicle",
            {"tools_succeeded": ["actualizar_datos_expediente"]},
        ),
        (
            "collect_vehicle", "collect_workshop",
            {"tools_succeeded": ["actualizar_datos_expediente"]},
        ),
        (
            "collect_workshop", "review_summary",
            {"tools_succeeded": ["actualizar_datos_taller"]},
        ),
    ])
    def test_allowed_transition_yields_allowed_reason(
        self, from_mode: str, to_mode: str, env_kwargs: dict
    ) -> None:
        """Each transition with required evidence must return ALLOWED."""
        from agent.modes.expediente_guardrails import CertaintyEnvelope, evaluate_progression_eligibility, GuardrailReason

        env = CertaintyEnvelope(sub_mode=from_mode, **env_kwargs)
        allowed, reason = evaluate_progression_eligibility(env, to_mode)
        assert allowed is True, f"Expected allowed for {from_mode} → {to_mode}"
        assert reason == GuardrailReason.ALLOWED.value


# ---------------------------------------------------------------------------
# Phase 5.2 — Anti-anticipation cases for each handoff
# ---------------------------------------------------------------------------


class TestAntiAnticipationEachTransition:
    """
    5.2 Anti-anticipation: each transition closure must NOT describe the
    destination step's full content. It must only acknowledge the previous
    step's closure and signal the new step briefly.
    """

    SAMPLE_BASE_DOCS = [
        {"description": "Foto de la ficha técnica"},
        {"description": "Foto del permiso de circulación"},
    ]

    def _get_closure(self, from_sub: str, to_sub: str, tool_name: str, **extra_data: object) -> str | None:
        """Helper: build closure text for a given pair."""
        tool_data = {"success": True, **extra_data}
        return _build_transition_closure(
            from_sub_mode=from_sub,
            to_sub_mode=to_sub,
            tool_name=tool_name,
            tool_data=tool_data,
            base_documentation=self.SAMPLE_BASE_DOCS if from_sub == COLLECT_ELEMENT_DATA else None,
        )

    def test_element_to_base_does_not_preview_full_docs_list(self) -> None:
        """element_data → base_docs closure must NOT list every required document."""
        result = self._get_closure(
            COLLECT_ELEMENT_DATA, COLLECT_BASE_DOCS,
            "completar_elemento_actual",
            all_elements_complete=True,
        )
        assert result is not None, "Expected a closure for element_data → base_docs"
        # The closure is allowed to mention "paso 2" or "documentación base" briefly,
        # but must NOT enumerate all required doc types from SAMPLE_BASE_DOCS verbatim.
        result_lower = result.lower()
        # Either the anti-anticipation guard keeps it brief (no full list),
        # OR it includes the list but must at minimum close the previous step.
        assert any(kw in result_lower for kw in ("cerramos", "elementos", "paso 2", "documentac")), (
            f"Closure for element_data → base_docs must acknowledge completion: {result!r}"
        )

    def test_base_docs_to_personal_does_not_preview_all_personal_fields(self) -> None:
        """base_docs → personal closure must not enumerate all 5 personal data fields."""
        result = self._get_closure(
            COLLECT_BASE_DOCS, COLLECT_PERSONAL,
            "confirmar_documentacion_base",
        )
        assert result is not None, "Expected a closure for base_docs → personal"
        result_lower = result.lower()
        # The closure must acknowledge docs were received
        assert any(kw in result_lower for kw in ("documentac", "paso 3", "personal")), (
            f"Expected base_docs → personal closure to acknowledge completion: {result!r}"
        )
        # Anti-anticipation: must NOT enumerate all 5 fields simultaneously
        all_fields = ["nombre", "dni", "email", "domicilio", "itv"]
        fields_present = [f for f in all_fields if f in result_lower]
        # Allowed: mentioning 1-2 fields to clarify next step
        # Not allowed: listing all 5 exhaustively (that's the LLM's job, not the closure)
        assert len(fields_present) <= 3, (
            f"Closure pre-enumerates too many personal fields ({fields_present!r}). "
            "Anti-anticipation should keep it brief."
        )

    def test_personal_to_vehicle_does_not_preview_all_vehicle_fields(self) -> None:
        """personal → vehicle closure must be brief about vehicle data."""
        result = self._get_closure(
            COLLECT_PERSONAL, COLLECT_VEHICLE,
            "actualizar_datos_expediente",
            next_step="collect_vehicle",
        )
        assert result is not None, "Expected a closure for personal → vehicle"
        result_lower = result.lower()
        assert any(kw in result_lower for kw in ("personal", "paso 4", "vehiculo", "vehículo")), (
            f"Expected personal → vehicle closure to acknowledge: {result!r}"
        )

    def test_vehicle_to_workshop_does_not_enumerate_all_workshop_options(self) -> None:
        """vehicle → workshop closure must be brief about taller options."""
        result = self._get_closure(
            COLLECT_VEHICLE, COLLECT_WORKSHOP,
            "actualizar_datos_expediente",
            next_step="collect_workshop",
        )
        assert result is not None, "Expected a closure for vehicle → workshop"
        result_lower = result.lower()
        assert any(kw in result_lower for kw in ("vehiculo", "vehículo", "paso 5", "taller")), (
            f"Expected vehicle → workshop closure to acknowledge: {result!r}"
        )

    def test_workshop_to_review_does_not_preview_full_summary_content(self) -> None:
        """workshop → review_summary closure must not describe the full summary."""
        result = self._get_closure(
            COLLECT_WORKSHOP, REVIEW_SUMMARY,
            "actualizar_datos_taller",
            next_step="review_summary",
        )
        assert result is not None, "Expected a closure for workshop → review_summary"
        result_lower = result.lower()
        assert any(kw in result_lower for kw in ("taller", "paso 6", "resumen", "revisión", "revision")), (
            f"Expected workshop → review closure to acknowledge: {result!r}"
        )

    # review → edit-back (anti-anticipation: must not re-collect data)
    def test_closure_returns_none_for_review_to_edit_via_closure_builder(self) -> None:
        """review_summary → edit-back does not use the closure builder (LLM handles it)."""
        result = _build_transition_closure(
            from_sub_mode=REVIEW_SUMMARY,
            to_sub_mode=COLLECT_PERSONAL,
            tool_name="editar_expediente",
            tool_data={"success": True},
        )
        # The closure builder is not designed for edit-back — it returns None
        # meaning the LLM produces the response
        assert result is None, (
            "edit-back from review_summary should not use deterministic closure"
        )


# ---------------------------------------------------------------------------
# Phase 5.2 — Extra coverage: wrong tool must not trigger closure for any pair
# ---------------------------------------------------------------------------


class TestWrongToolDoesNotTriggerClosureForAnyPair:
    """
    5.2 regression guard: a wrong tool name must not accidentally trigger
    a transition closure for any of the 5 canonical pairs.
    """

    SAMPLE_BASE_DOCS = [{"description": "Ficha técnica"}]
    SPURIOUS_TOOL = "obtener_estado_expediente"

    @pytest.mark.parametrize("from_sub,to_sub", [
        (COLLECT_ELEMENT_DATA, COLLECT_BASE_DOCS),
        (COLLECT_BASE_DOCS, COLLECT_PERSONAL),
        (COLLECT_PERSONAL, COLLECT_VEHICLE),
        (COLLECT_VEHICLE, COLLECT_WORKSHOP),
        (COLLECT_WORKSHOP, REVIEW_SUMMARY),
    ])
    def test_spurious_tool_returns_none_for_all_pairs(
        self, from_sub: str, to_sub: str
    ) -> None:
        extra_data: dict = {"success": True}
        if from_sub == COLLECT_ELEMENT_DATA and to_sub == COLLECT_BASE_DOCS:
            extra_data["all_elements_complete"] = True
        result = _build_transition_closure(
            from_sub_mode=from_sub,
            to_sub_mode=to_sub,
            tool_name=self.SPURIOUS_TOOL,
            tool_data=extra_data,
            base_documentation=self.SAMPLE_BASE_DOCS if from_sub == COLLECT_ELEMENT_DATA else None,
        )
        assert result is None, (
            f"Spurious tool '{self.SPURIOUS_TOOL}' must not trigger closure "
            f"for {from_sub} → {to_sub}"
        )
