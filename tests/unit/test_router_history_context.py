"""
Tests for router-history-context change.

Covers:
- Task 5.1: _format_history_context() unit tests
- Task 5.2: _classify_llm() prompt assembly with/without history
- Task 5.3: _validate_keyword_with_context() — 6 parametrized cases
- Task 5.4: Backward compat — classify(message, mode) unchanged behavior
- Task 5.5: Integration — LLM called when keyword downgraded by context

All tests are offline (no Redis, no DB, no Ollama required).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.router.intent_router import (
    IntentResult,
    IntentRouter,
    UserIntent,
    CONFIDENCE_THRESHOLD,
    get_intent_router,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_router() -> IntentRouter:
    """Return a fresh IntentRouter instance (not the global singleton)."""
    return IntentRouter()


def _make_intent_result(intent: UserIntent, confidence: float) -> IntentResult:
    from agent.router.intent_router import INTENT_TO_MODE

    return IntentResult(
        intent=intent,
        confidence=confidence,
        suggested_mode=INTENT_TO_MODE.get(intent, "CONSULTA_MODE"),
    )


# ---------------------------------------------------------------------------
# Task 5.1 — _format_history_context()
# ---------------------------------------------------------------------------


class TestFormatHistoryContext:
    """Unit tests for IntentRouter._format_history_context()."""

    def test_empty_list_returns_empty_string(self):
        result = IntentRouter._format_history_context([])
        assert result == ""

    def test_none_equivalent_empty_list(self):
        """Empty list is the canonical 'no history' case."""
        result = IntentRouter._format_history_context([])
        assert result == ""

    def test_tool_messages_skipped(self):
        history = [
            {"role": "user", "content": "¿cuánto cuesta?"},
            {"role": "tool", "content": '{"success": true, "price": 410}'},
            {"role": "assistant", "content": "El presupuesto es 410€."},
        ]
        result = IntentRouter._format_history_context(history)
        assert "tool" not in result
        assert '{"success":' not in result
        assert "U: ¿cuánto cuesta?" in result
        assert "A: El presupuesto es 410€." in result

    def test_hard_cap_at_500_chars(self):
        """Total block must not exceed 500 characters."""
        long_content = "x" * 300
        history = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
        ]
        result = IntentRouter._format_history_context(history)
        # 500 chars + "..." = 503 max
        assert len(result) <= 503

    def test_custom_max_chars(self):
        """Custom max_chars param is respected."""
        history = [
            {"role": "user", "content": "a" * 200},
            {"role": "assistant", "content": "b" * 200},
        ]
        result = IntentRouter._format_history_context(history, max_chars=100)
        assert len(result) <= 103  # 100 + "..."

    def test_security_tags_stripped(self):
        """<USER_MESSAGE> tags from preprocessing are removed."""
        history = [
            {"role": "user", "content": "<USER_MESSAGE>Hola</USER_MESSAGE>"},
        ]
        result = IntentRouter._format_history_context(history)
        assert "<USER_MESSAGE>" not in result
        assert "</USER_MESSAGE>" not in result
        assert "U: Hola" in result

    def test_user_prefixed_u_assistant_prefixed_a(self):
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Buenos días"},
        ]
        result = IntentRouter._format_history_context(history)
        assert result.startswith("U: Hola")
        assert "A: Buenos días" in result

    def test_per_message_truncation_at_120_chars(self):
        """Each individual message is truncated to 120 chars before block assembly."""
        long_msg = "a" * 200
        history = [{"role": "user", "content": long_msg}]
        result = IntentRouter._format_history_context(history)
        # "U: " + 120 chars = 123 chars total for a single message
        assert len(result) <= 123

    def test_short_history_not_truncated(self):
        """Short history is returned verbatim (no trailing ellipsis)."""
        history = [
            {"role": "user", "content": "Sí"},
        ]
        result = IntentRouter._format_history_context(history)
        assert result == "U: Sí"
        assert "..." not in result


# ---------------------------------------------------------------------------
# Task 5.2 — _classify_llm() prompt assembly
# ---------------------------------------------------------------------------


class TestClassifyLlmPromptAssembly:
    """_classify_llm() must inject CONTEXTO block only when history is non-empty."""

    @pytest.mark.asyncio
    async def test_non_empty_history_injects_contexto_block(self):
        """Non-empty history → LLM user_prompt contains CONTEXTO RECIENTE: block."""
        router = _make_router()

        history = [
            {"role": "user", "content": "¿cuánto cuesta el escape?"},
            {
                "role": "assistant",
                "content": "El presupuesto es 410€ +IVA. ¿Continuamos?",
            },
        ]

        captured_messages: list = []

        async def fake_invoke(*, task_type, messages):
            captured_messages.extend(messages)
            mock_resp = MagicMock()
            mock_resp.content = (
                '{"intent": "confirmacion", "confidence": 0.85, "entities": {}}'
            )
            return mock_resp

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=fake_invoke)
        router._llm_router = mock_llm

        await router._classify_llm("sí", "PRESUPUESTO_MODE", history)

        assert len(captured_messages) == 2  # system + user
        user_msg = captured_messages[1]["content"]
        assert "CONTEXTO RECIENTE:" in user_msg
        assert "MODO ACTUAL: PRESUPUESTO_MODE" in user_msg
        assert "MENSAJE: sí" in user_msg

    @pytest.mark.asyncio
    async def test_empty_history_produces_current_format(self):
        """Empty history → prompt is ONLY 'MODO ACTUAL + MENSAJE' (no regression)."""
        router = _make_router()

        captured_messages: list = []

        async def fake_invoke(*, task_type, messages):
            captured_messages.extend(messages)
            mock_resp = MagicMock()
            mock_resp.content = (
                '{"intent": "ambiguo", "confidence": 0.5, "entities": {}}'
            )
            return mock_resp

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=fake_invoke)
        router._llm_router = mock_llm

        await router._classify_llm("sí", "START", [])

        user_msg = captured_messages[1]["content"]
        assert user_msg == "MODO ACTUAL: START\nMENSAJE: sí"
        assert "CONTEXTO RECIENTE:" not in user_msg

    @pytest.mark.asyncio
    async def test_none_history_treated_as_empty(self):
        """history=None → same behavior as empty list (classify() calls with [] by default)."""
        router = _make_router()

        captured_messages: list = []

        async def fake_invoke(*, task_type, messages):
            captured_messages.extend(messages)
            mock_resp = MagicMock()
            mock_resp.content = (
                '{"intent": "ambiguo", "confidence": 0.5, "entities": {}}'
            )
            return mock_resp

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=fake_invoke)
        router._llm_router = mock_llm

        # classify() converts None → [], so we call _classify_llm with [] directly
        await router._classify_llm("sí", "START", [])

        user_msg = captured_messages[1]["content"]
        assert "CONTEXTO RECIENTE:" not in user_msg

    @pytest.mark.asyncio
    async def test_tool_messages_not_in_contexto_block(self):
        """Tool messages in history are not included in the CONTEXTO block."""
        router = _make_router()

        history = [
            {"role": "user", "content": "quiero el presupuesto"},
            {"role": "tool", "content": '{"success": true, "price": 350}'},
            {"role": "assistant", "content": "El precio es 350€ +IVA."},
        ]

        captured_messages: list = []

        async def fake_invoke(*, task_type, messages):
            captured_messages.extend(messages)
            mock_resp = MagicMock()
            mock_resp.content = (
                '{"intent": "confirmacion", "confidence": 0.80, "entities": {}}'
            )
            return mock_resp

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=fake_invoke)
        router._llm_router = mock_llm

        await router._classify_llm("sí", "PRESUPUESTO_MODE", history)

        user_msg = captured_messages[1]["content"]
        assert "CONTEXTO RECIENTE:" in user_msg
        assert '{"success":' not in user_msg


# ---------------------------------------------------------------------------
# Task 5.3 — _validate_keyword_with_context() — 6 parametrized cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent, context_hints, expected_result",
    [
        # VER_IMAGENES: any context → confidence always preserved (no downgrade — Spec 4)
        (
            UserIntent.VER_IMAGENES,
            {"waiting_for_image_choice": True},
            0.95,  # original confidence returned unchanged
        ),
        # VER_IMAGENES: flag=False → STILL preserved (downgrade logic was removed, Spec 4 / AD-2)
        (
            UserIntent.VER_IMAGENES,
            {"waiting_for_image_choice": False},
            0.95,  # NO downgrade — waiting_for_image_choice was never set to True in practice
        ),
        # ABRIR_EXPEDIENTE: any context → confidence always preserved (no downgrade — Spec 4)
        (
            UserIntent.ABRIR_EXPEDIENTE,
            {"waiting_for_image_choice": True},
            0.95,
        ),
        # ABRIR_EXPEDIENTE: flag=False → STILL preserved (downgrade logic was removed, Spec 4 / AD-2)
        (
            UserIntent.ABRIR_EXPEDIENTE,
            {"waiting_for_image_choice": False},
            0.95,  # NO downgrade — dead downgrade block removed
        ),
        # CONFIRMACION: precio_comunicado present → preserved
        (
            UserIntent.CONFIRMACION,
            {"precio_comunicado": True, "tarifa_calculada": False},
            0.90,
        ),
        # CONFIRMACION: neither flag set → downgraded (this downgrade is still valid)
        (
            UserIntent.CONFIRMACION,
            {"precio_comunicado": False, "tarifa_calculada": False},
            0.50,
        ),
    ],
    ids=[
        "ver_imagenes_with_flag",
        "ver_imagenes_without_flag",
        "abrir_expediente_with_flag",
        "abrir_expediente_without_flag",
        "confirmacion_with_precio",
        "confirmacion_without_context",
    ],
)
def test_validate_keyword_with_context_parametrized(
    intent: UserIntent,
    context_hints: dict,
    expected_result: float,
):
    router = _make_router()
    original_confidence = 0.95 if intent != UserIntent.CONFIRMACION else 0.90
    result = router._validate_keyword_with_context(
        intent, original_confidence, context_hints
    )
    assert result == expected_result


def test_validate_keyword_with_context_noop_for_other_intents():
    """Intents not in the validation list return original confidence unchanged."""
    router = _make_router()
    context_hints = {"precio_comunicado": False, "waiting_for_image_choice": False}

    for intent in [
        UserIntent.CONSULTA_GENERAL,
        UserIntent.PRESUPUESTO_DIRECTO,
        UserIntent.INICIAR_EXPEDIENTE,
        UserIntent.ESCALAR,
        UserIntent.RECHAZO,
        UserIntent.CANCELAR,
        UserIntent.MODIFICAR_ELEMENTOS,
        UserIntent.AMBIGUO,
    ]:
        result = router._validate_keyword_with_context(intent, 0.88, context_hints)
        assert result == 0.88, f"Expected 0.88 for {intent}, got {result}"


def test_validate_keyword_with_context_empty_dict_returns_original():
    """Empty context_hints dict → no downgrade (treat as no context)."""
    router = _make_router()
    result = router._validate_keyword_with_context(UserIntent.VER_IMAGENES, 0.95, {})
    # {} is falsy for the `if not context_hints:` guard
    assert result == 0.95


def test_validate_keyword_with_context_confirmacion_tarifa_calculada_truthy():
    """CONFIRMACION: tarifa_calculada=True alone is sufficient (no downgrade)."""
    router = _make_router()
    result = router._validate_keyword_with_context(
        UserIntent.CONFIRMACION,
        0.90,
        {"precio_comunicado": False, "tarifa_calculada": True},
    )
    assert result == 0.90


# ---------------------------------------------------------------------------
# Task 5.4 — Backward compat: classify(message, mode) unchanged behavior
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """classify() with no history/mode_context must behave identically to before."""

    @pytest.mark.asyncio
    async def test_keyword_match_no_history_no_context(self):
        """High-confidence keyword match returns immediately without history/context."""
        router = _make_router()

        # "quiero homologar" → PRESUPUESTO_DIRECTO (0.90 keyword)
        result = await router.classify("quiero homologar el escape")
        assert result.intent == UserIntent.PRESUPUESTO_DIRECTO
        assert result.confidence >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_confirmacion_keyword_no_context_not_downgraded(self):
        """Without mode_context, 'sí' keyword match is NOT downgraded (backward compat)."""
        router = _make_router()

        # mode_context=None → no validation → keyword returned as-is
        result = await router.classify("sí", "START", history=None, mode_context=None)
        assert result.intent == UserIntent.CONFIRMACION
        assert result.confidence == 0.90  # Original keyword confidence

    @pytest.mark.asyncio
    async def test_classify_positional_compat(self):
        """classify(message, mode) — positional call still works."""
        router = _make_router()
        # "quiero homologar" should still classify correctly
        result = await router.classify("quiero homologar el escape", "START")
        assert result.intent == UserIntent.PRESUPUESTO_DIRECTO

    @pytest.mark.asyncio
    async def test_escalar_no_context_unchanged(self):
        """ESCALAR keyword match (no context) returns at original confidence."""
        router = _make_router()
        result = await router.classify("quiero hablar con una persona")
        assert result.intent == UserIntent.ESCALAR
        assert result.confidence == 0.95


# ---------------------------------------------------------------------------
# Task 5.5 — Integration: LLM called when keyword downgraded
# ---------------------------------------------------------------------------


class TestKeywordDowngradeFallsToLlm:
    """When keyword is downgraded by context, _classify_llm() must be called."""

    @pytest.mark.asyncio
    async def test_llm_called_when_confirmacion_downgraded(self):
        """'sí' + no presupuesto context → keyword downgraded → LLM called."""
        router = _make_router()

        llm_mock_response = MagicMock()
        llm_mock_response.content = (
            '{"intent": "consulta_general", "confidence": 0.80, "entities": {}}'
        )

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=llm_mock_response)
        router._llm_router = mock_llm

        context_hints = {
            "precio_comunicado": False,
            "waiting_for_image_choice": False,
            "tarifa_calculada": False,
        }
        result = await router.classify(
            "sí",
            current_mode="EXPEDIENTE_MODE",
            history=[{"role": "user", "content": "nombre: Juan García"}],
            mode_context=context_hints,
        )

        # LLM was invoked because keyword was downgraded (0.90 → 0.50 < 0.75)
        mock_llm.invoke.assert_called_once()
        # Result comes from LLM
        assert result.intent == UserIntent.CONSULTA_GENERAL

    @pytest.mark.asyncio
    async def test_ver_imagenes_not_downgraded_llm_not_called(self):
        """'A' keyword → VER_IMAGENES at 0.95 — no downgrade (Spec 4 / AD-2), LLM NOT called."""
        router = _make_router()

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock()
        router._llm_router = mock_llm

        context_hints = {
            "precio_comunicado": False,
            "waiting_for_image_choice": False,
            "tarifa_calculada": False,
        }
        result = await router.classify(
            "A",
            current_mode="CONSULTA_MODE",
            history=[],
            mode_context=context_hints,
        )

        # LLM must NOT be called — VER_IMAGENES keyword confidence (0.95) is above threshold
        # and is no longer downgraded by waiting_for_image_choice (dead flag removed, Spec 4)
        mock_llm.invoke.assert_not_called()
        assert result.intent == UserIntent.VER_IMAGENES
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_llm_not_called_when_keyword_consistent_with_context(self):
        """'sí' + precio_comunicado=True → keyword NOT downgraded → LLM NOT called."""
        router = _make_router()

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock()
        router._llm_router = mock_llm

        context_hints = {
            "precio_comunicado": True,
            "waiting_for_image_choice": False,
            "tarifa_calculada": False,
        }
        result = await router.classify(
            "sí",
            current_mode="PRESUPUESTO_MODE",
            history=[],
            mode_context=context_hints,
        )

        # LLM should NOT have been called
        mock_llm.invoke.assert_not_called()
        assert result.intent == UserIntent.CONFIRMACION
        assert result.confidence == 0.90

    @pytest.mark.asyncio
    async def test_llm_receives_history_when_keyword_downgraded(self):
        """Confirm history is forwarded to LLM when keyword falls through."""
        router = _make_router()

        captured_messages: list = []

        async def fake_invoke(*, task_type, messages):
            captured_messages.extend(messages)
            mock_resp = MagicMock()
            mock_resp.content = (
                '{"intent": "ambiguo", "confidence": 0.55, "entities": {}}'
            )
            return mock_resp

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=fake_invoke)
        router._llm_router = mock_llm

        history = [
            {"role": "user", "content": "¿Cuánto cuesta homologar el freno?"},
            {"role": "assistant", "content": "El freno ya está incluido en el kit."},
        ]
        context_hints = {
            "precio_comunicado": False,
            "waiting_for_image_choice": False,
            "tarifa_calculada": False,
        }
        await router.classify(
            "sí",
            current_mode="PRESUPUESTO_MODE",
            history=history,
            mode_context=context_hints,
        )

        # History was forwarded → CONTEXTO RECIENTE in LLM user prompt
        user_msg = captured_messages[1]["content"]
        assert "CONTEXTO RECIENTE:" in user_msg
        assert "¿Cuánto cuesta homologar el freno?" in user_msg
