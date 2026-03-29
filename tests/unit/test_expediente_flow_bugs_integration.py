"""
Integration tests for expediente-flow-bugs T1 + T2.

Verifies non-recurrence of BUG 1 (stale price in review) and BUG 2
(taller vocabulary leaking into collect_personal) at an integration level.

All tests are pure-logic / lightweight — no database, no Redis, no real LLM.
External calls are mocked.
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    conversation_id: str = "test-bug-regression-001",
    history_price: str = "410 EUR",
) -> dict:
    """State that includes a stale price in message history (BUG 1 scenario)."""
    return {
        "conversation_id": conversation_id,
        "messages": [
            {
                "role": "user",
                "content": "Quiero homologar el escape de mi moto",
            },
            {
                "role": "assistant",
                "content": (
                    f"El presupuesto para homologar el escape es de {history_price} +IVA. "
                    "Vamos a proceder con el expediente."
                ),
            },
            {
                "role": "user",
                "content": "Sí, quiero proceder.",
            },
        ],
        "current_mode": "EXPEDIENTE_MODE",
        "mode_context": {},
        "retry_state": None,
        "incoming_attachments": [],
    }


def _make_review_mode_context() -> dict:
    """Minimal mode_context for review_summary sub-mode."""
    return {
        "expediente_sub_mode": "review_summary",
        "case_id": "00000000-0000-0000-0000-000000000042",
    }


# ---------------------------------------------------------------------------
# T1 — BUG 1 non-recurrence: review uses DB price, not history price
# ---------------------------------------------------------------------------


class TestReviewUsesPrecallPriceNotHistoryPrice:
    """
    Integration test: _handle_review() must always call obtener_estado_expediente
    deterministically and inject its precio_total into _run_llm_loop, ignoring
    any stale price in the conversation history.
    """

    @pytest.mark.asyncio
    async def test_review_uses_tool_price_not_history_price(self):
        """
        BUG 1 regression: review_summary must use obtener_estado_expediente
        precio_total, not "410 EUR" from PRESUPUESTO_MODE message history.

        Scenario:
        - Message history contains "410 EUR" (old presupuesto quote)
        - obtener_estado_expediente returns precio_total=65.0 (corrected DB value)

        Assertions:
        - The pre-call fires exactly once
        - The injected pre_call_tool_result contains "65"
        - The injected pre_call_tool_result does NOT contain "410"
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        state = _make_state(history_price="410 EUR")
        mode_context = _make_review_mode_context()

        # DB returns a DIFFERENT price (65, not 410)
        db_tool_result = {
            "has_active_case": True,
            "precio_total": 65.0,
            "tariff_amount": 50.0,
            "case_id": "00000000-0000-0000-0000-000000000042",
        }

        captured_pre_call_result: list[str] = []
        mock_tool = AsyncMock(return_value=db_tool_result)

        async def fake_run_llm_loop(
            message, state, mode_context, tools, sub_mode_name, **kwargs
        ):
            """Capture kwargs from _handle_review → _run_llm_loop call."""
            pre_result = kwargs.get("pre_call_tool_result")
            if pre_result:
                captured_pre_call_result.append(pre_result)
            return {
                "ai_response": "Resumen del expediente listo.",
                "mode_context": mode_context,
            }

        import agent.tools.case_tools as _ct_module

        original_tool = getattr(_ct_module, "obtener_estado_expediente", None)
        try:
            mock_obj = MagicMock()
            mock_obj.ainvoke = mock_tool
            _ct_module.obtener_estado_expediente = mock_obj

            with (
                patch("agent.modes.expediente_mode.set_current_state"),
                patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
                patch.object(node, "_run_llm_loop", side_effect=fake_run_llm_loop),
            ):
                await node._handle_review(
                    message="¿Cómo queda el resumen?",
                    state=state,
                    mode_context=mode_context,
                )
        finally:
            if original_tool is not None:
                _ct_module.obtener_estado_expediente = original_tool

        # ── Assertion 1: pre-call fired exactly once ──────────────────────────
        mock_tool.assert_called_once_with({})

        # ── Assertion 2: pre_call_tool_result was injected ────────────────────
        assert len(captured_pre_call_result) == 1, (
            "Expected exactly one pre_call_tool_result kwarg to reach _run_llm_loop"
        )
        injected = captured_pre_call_result[0]

        # ── Assertion 3: injected data contains DB price (65), not stale (410) ─
        assert "65" in injected, (
            f"Expected DB precio_total=65 in injected result, got: {injected!r}"
        )
        assert "410" not in injected, (
            f"Stale history price '410' must NOT appear in injected result, got: {injected!r}"
        )

    @pytest.mark.asyncio
    async def test_pre_call_tool_name_is_correct(self):
        """
        The pre_call_tool_name kwarg passed to _run_llm_loop must be
        'obtener_estado_expediente' so the tool is registered in tools_called
        and not called a second time by the LLM.
        """
        from agent.modes.expediente_mode import ExpedienteModeNode

        node = ExpedienteModeNode()
        state = _make_state()
        mode_context = _make_review_mode_context()

        db_tool_result = {"has_active_case": True, "precio_total": 65.0}
        mock_tool = AsyncMock(return_value=db_tool_result)

        captured_kwargs: dict = {}

        async def fake_run_llm_loop(
            message, state, mode_context, tools, sub_mode_name, **kwargs
        ):
            captured_kwargs.update(kwargs)
            return {"ai_response": "Ok.", "mode_context": mode_context}

        import agent.tools.case_tools as _ct_module

        original_tool = getattr(_ct_module, "obtener_estado_expediente", None)
        try:
            mock_obj = MagicMock()
            mock_obj.ainvoke = mock_tool
            _ct_module.obtener_estado_expediente = mock_obj

            with (
                patch("agent.modes.expediente_mode.set_current_state"),
                patch("agent.modes.expediente_mode.set_current_state_for_image_tools"),
                patch.object(node, "_run_llm_loop", side_effect=fake_run_llm_loop),
            ):
                await node._handle_review(
                    message="Ver resumen",
                    state=state,
                    mode_context=mode_context,
                )
        finally:
            if original_tool is not None:
                _ct_module.obtener_estado_expediente = original_tool

        assert (
            captured_kwargs.get("pre_call_tool_name") == "obtener_estado_expediente"
        ), (
            f"Expected pre_call_tool_name='obtener_estado_expediente', "
            f"got: {captured_kwargs.get('pre_call_tool_name')!r}"
        )

    def test_injected_system_message_format(self):
        """
        Verify the exact format of the system message injected by _run_llm_loop
        when pre_call kwargs are present — mirrors the logic in expediente_mode.py.

        This is a pure-logic test: it replays the injection block directly
        and asserts the resulting message structure.
        """
        pre_call_tool_name = "obtener_estado_expediente"
        pre_call_tool_result = json.dumps(
            {"has_active_case": True, "precio_total": 65.0},
            ensure_ascii=False,
        )

        llm_messages: list[dict] = []
        tools_called: set[str] = set()

        # Replicate the injection block from _run_llm_loop
        if pre_call_tool_result and pre_call_tool_name:
            llm_messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[RESULTADO PRE-CARGADO de {pre_call_tool_name}]: "
                        f"{pre_call_tool_result}\n\n"
                        "IMPORTANTE: Usa EXCLUSIVAMENTE estos datos para el resumen. "
                        "No uses precios ni datos de mensajes anteriores."
                    ),
                }
            )

        # Replicate the registration block from _run_llm_loop
        if pre_call_tool_name and pre_call_tool_result:
            tools_called.add(pre_call_tool_name)

        # Assertions
        assert len(llm_messages) == 1
        assert llm_messages[0]["role"] == "system"
        content = llm_messages[0]["content"]

        assert "[RESULTADO PRE-CARGADO de obtener_estado_expediente]" in content
        assert "65" in content, "DB precio_total must appear in injected message"
        assert "410" not in content, (
            "Stale history price must NOT appear in injected message"
        )
        assert "EXCLUSIVAMENTE" in content
        assert "No uses precios ni datos de mensajes anteriores" in content

        # Tool registered — LLM won't call it again
        assert "obtener_estado_expediente" in tools_called


# ---------------------------------------------------------------------------
# T2 — BUG 2 non-recurrence: taller domain guard in collect_personal
# ---------------------------------------------------------------------------


class TestCollectPersonalTallerWordingIsStripped:
    """
    Integration test: the exact phrase from the production bug must be
    stripped by the domain guard in collect_personal.
    """

    def test_collect_personal_taller_wording_is_stripped(self):
        """
        BUG 2 regression: the exact phrase that appeared in production
        must be stripped by the domain guard in collect_personal.
        """
        from agent.modes.expediente_mode import (
            _TALLER_DOMAIN_RE,
            _TALLER_DOMAIN_GUARD_SUBMODES,
        )

        # Production bug phrase
        bad_response = (
            "Para completar el expediente, necesito saber si el montaje fue "
            "realizado en un taller propio o externo."
        )

        # Assert: guard is active for collect_personal
        assert "collect_personal" in _TALLER_DOMAIN_GUARD_SUBMODES, (
            "'collect_personal' must be in _TALLER_DOMAIN_GUARD_SUBMODES"
        )

        # Assert: the production phrase is caught
        assert _TALLER_DOMAIN_RE.search(bad_response) is not None, (
            f"Expected _TALLER_DOMAIN_RE to match production bug phrase:\n{bad_response!r}"
        )

        # Assert: after stripping, taller vocabulary is gone
        cleaned = _TALLER_DOMAIN_RE.sub("", bad_response).strip()
        assert "taller propio" not in cleaned.lower(), (
            f"'taller propio' must be stripped, remaining content: {cleaned!r}"
        )

        # Also test: correct personal question passes through untouched
        good_response = "Para continuar, necesito tu nombre completo, DNI y email."
        assert _TALLER_DOMAIN_RE.search(good_response) is None, (
            f"Guard must NOT match a valid personal data question:\n{good_response!r}"
        )

    def test_collect_vehicle_taller_wording_is_stripped(self):
        """
        BUG 2 non-recurrence: taller vocabulary must also be stripped
        in collect_vehicle (same guard applies).
        """
        from agent.modes.expediente_mode import (
            _TALLER_DOMAIN_RE,
            _TALLER_DOMAIN_GUARD_SUBMODES,
        )

        assert "collect_vehicle" in _TALLER_DOMAIN_GUARD_SUBMODES

        bad_response = "¿Me puedes indicar la marca y modelo de la moto, y si tienes taller propio?"
        assert _TALLER_DOMAIN_RE.search(bad_response) is not None

        cleaned = _TALLER_DOMAIN_RE.sub("", bad_response).strip()
        assert "taller propio" not in cleaned.lower()

        # Valid vehicle question passes through
        good_response = "¿Cuál es la matrícula y el número de bastidor del vehículo?"
        assert _TALLER_DOMAIN_RE.search(good_response) is None

    def test_collect_workshop_taller_wording_passes_through(self):
        """
        collect_workshop is the CORRECT domain for taller questions.
        The guard must NOT be active there.
        """
        from agent.modes.expediente_mode import _TALLER_DOMAIN_GUARD_SUBMODES

        assert "collect_workshop" not in _TALLER_DOMAIN_GUARD_SUBMODES, (
            "'collect_workshop' must NOT be in _TALLER_DOMAIN_GUARD_SUBMODES"
        )

    def test_full_production_phrase_variation(self):
        """
        Additional variation of the production phrase that triggered BUG 2.
        """
        from agent.modes.expediente_mode import (
            _TALLER_DOMAIN_RE,
            _TALLER_DOMAIN_GUARD_SUBMODES,
        )

        # Another phrasing seen in production logs
        bad_response = (
            "Para continuar con el Paso 3/6 de datos personales, necesito saber "
            "si el montaje fue hecho en un taller externo o en instalación propia."
        )

        assert "collect_personal" in _TALLER_DOMAIN_GUARD_SUBMODES

        # 'instalación' is covered by the guard pattern
        assert _TALLER_DOMAIN_RE.search(bad_response) is not None, (
            f"'instalaci[oó]n' pattern must catch: {bad_response!r}"
        )

        cleaned = _TALLER_DOMAIN_RE.sub("", bad_response).strip()
        # After stripping, installation/taller vocabulary should be gone
        assert (
            "instalación" not in cleaned.lower()
            and "instalacion" not in cleaned.lower()
        ), f"'instalación' must be stripped, remaining: {cleaned!r}"
