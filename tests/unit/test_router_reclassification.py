"""
Tests for CONSULTA_MODE intent reclassification in router_node.

Verifies that when a user in CONSULTA_MODE expresses clear intent
for a quote (PRESUPUESTO_DIRECTO), the router transitions to
PRESUPUESTO_MODE automatically instead of staying in CONSULTA.

Covers plan items from docs/plans/fix-consulta-mode-price-leak-and-routing.md:
- Test: router_node reclasifica PRESUPUESTO_DIRECTO en CONSULTA_MODE
- Test: router_node NO reclasifica con confianza baja
- Test: router_node NO reclasifica en modos que no son CONSULTA
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from agent.router.intent_router import UserIntent, IntentResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(current_mode: str = "CONSULTA_MODE", user_message: str = "") -> dict:
    """Build a minimal ConversationState-compatible dict for testing.

    ConversationState is a TypedDict(total=False) so a plain dict works.
    We include only the keys that router_node actually reads.
    """
    now = datetime.now(UTC).isoformat()
    return {
        "current_mode": current_mode,
        "user_message": user_message,
        "mode_context": {},
        "messages": [],
        "conversation_id": "1",
        "user_phone": "+34600000001",
        "total_message_count": 2,
        "mode_message_count": 2,
        "last_node": "preprocess",
        "updated_at": now,
        "last_activity_at": now,
        "previous_mode": None,
        "mode_history": [],
        "draft_contexts": {},
        "retry_state": {},
        "agent_disabled": False,
    }


def _make_intent_result(
    intent: UserIntent,
    confidence: float,
    suggested_mode: str | None = None,
) -> IntentResult:
    """Build an IntentResult dataclass with sensible defaults."""
    if suggested_mode is None:
        from agent.router.intent_router import INTENT_TO_MODE

        suggested_mode = INTENT_TO_MODE.get(intent, "CONSULTA_MODE")

    return IntentResult(
        intent=intent,
        confidence=confidence,
        suggested_mode=suggested_mode,
    )


def _mock_digression_no_digression() -> MagicMock:
    """Return a digression manager mock that always says 'no digression'."""
    from agent.router.digression_manager import DigressionType

    dig_result = MagicMock()
    dig_result.is_digression = False
    dig_result.digression_type = DigressionType.NOT_A_DIGRESSION

    manager = MagicMock()
    manager.check = AsyncMock(return_value=dig_result)
    return manager


# ---------------------------------------------------------------------------
# Test class: CONSULTA → PRESUPUESTO reclassification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConsultaToPresupuestoReclassification:
    """Router should reclassify PRESUPUESTO_DIRECTO intents in CONSULTA_MODE."""

    async def test_reclassifies_presupuesto_directo_high_confidence(self):
        """CONSULTA + 'quiero homologar X' (conf>=0.75) -> PRESUPUESTO_MODE."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="quiero homologar el subchasis de mi honda CBF600",
        )

        mock_intent = _make_intent_result(UserIntent.PRESUPUESTO_DIRECTO, 0.90)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            assert result["current_mode"] == "PRESUPUESTO_MODE"
            assert result["previous_mode"] == "CONSULTA_MODE"
            assert result["last_node"] == "router"
            # classify() is now called with history and mode_context kwargs too
            mock_router_instance.classify.assert_called_once()
            call_kwargs = mock_router_instance.classify.call_args.kwargs
            assert call_kwargs["message"] == state["user_message"]
            assert call_kwargs["current_mode"] == "CONSULTA_MODE"
            assert "history" in call_kwargs
            assert "mode_context" in call_kwargs

    async def test_no_reclassification_low_confidence(self):
        """CONSULTA + ambiguous intent (conf<0.75) -> stay in CONSULTA_MODE."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="tengo una moto honda",
        )

        mock_intent = _make_intent_result(UserIntent.PRESUPUESTO_DIRECTO, 0.50)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # Should stay in CONSULTA (router returns only last_node + updated_at)
            assert result.get("current_mode") is None
            assert result["last_node"] == "router"

    async def test_no_reclassification_consulta_general_intent(self):
        """CONSULTA + CONSULTA_GENERAL intent -> stay in CONSULTA_MODE."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="que es la homologacion?",
        )

        mock_intent = _make_intent_result(UserIntent.CONSULTA_GENERAL, 0.95)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # CONSULTA_GENERAL does not trigger reclassification
            assert result.get("current_mode") is None
            assert result["last_node"] == "router"

    async def test_presupuesto_at_threshold_boundary(self):
        """CONSULTA + PRESUPUESTO_DIRECTO at exactly 0.75 -> PRESUPUESTO_MODE."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="cuanto cuesta homologar la suspension?",
        )

        mock_intent = _make_intent_result(UserIntent.PRESUPUESTO_DIRECTO, 0.75)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # Exactly at threshold should transition (>= 0.75)
            assert result["current_mode"] == "PRESUPUESTO_MODE"

    async def test_presupuesto_just_below_threshold(self):
        """CONSULTA + PRESUPUESTO_DIRECTO at 0.74 -> stay in CONSULTA_MODE."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="tengo una moto y quiza modificarla",
        )

        mock_intent = _make_intent_result(UserIntent.PRESUPUESTO_DIRECTO, 0.74)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # Just below threshold: stay in CONSULTA
            assert result.get("current_mode") is None
            assert result["last_node"] == "router"

    async def test_reclassification_resets_retry_state(self):
        """Reclassification transition should reset retry counters."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="quiero presupuesto para escape",
        )

        mock_intent = _make_intent_result(UserIntent.PRESUPUESTO_DIRECTO, 0.90)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # transition_mode() resets retry state
            assert result["current_mode"] == "PRESUPUESTO_MODE"
            assert result["retry_state"]["retry_count"] == 0
            assert result["mode_message_count"] == 0

    async def test_no_reclassification_for_escalar_intent(self):
        """CONSULTA + ESCALAR intent -> should NOT trigger PRESUPUESTO transition."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="CONSULTA_MODE",
            user_message="quiero hablar con una persona",
        )

        mock_intent = _make_intent_result(UserIntent.ESCALAR, 0.95)

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock(return_value=mock_intent)
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # ESCALAR is not PRESUPUESTO_DIRECTO, so no reclassification
            assert result.get("current_mode") is None
            assert result["last_node"] == "router"


# ---------------------------------------------------------------------------
# Test class: No reclassification in other modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNoReclassificationInOtherModes:
    """Router must NOT reclassify intents in modes other than CONSULTA.

    The reclassification logic is inside ``if current_mode == "CONSULTA_MODE":``
    so the intent router should never be called for non-CONSULTA active modes.
    """

    async def test_presupuesto_mode_no_reclassification(self):
        """PRESUPUESTO_MODE should NOT trigger intent reclassification."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="PRESUPUESTO_MODE",
            user_message="quiero homologar otro elemento",
        )

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock()
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            # Intent router.classify should NOT be called for PRESUPUESTO
            mock_router_instance.classify.assert_not_called()
            # Should stay in mode (no current_mode change)
            assert result.get("current_mode") is None
            assert result["last_node"] == "router"

    async def test_expediente_mode_no_reclassification(self):
        """EXPEDIENTE_MODE should NOT trigger intent reclassification."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="EXPEDIENTE_MODE",
            user_message="quiero homologar el escape tambien",
        )

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
                return_value=_mock_digression_no_digression(),
            ),
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance.classify = AsyncMock()
            mock_get_router.return_value = mock_router_instance

            result = await router_node(state)

            mock_router_instance.classify.assert_not_called()


# ---------------------------------------------------------------------------
# Test class: Terminal modes bypass reclassification entirely
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTerminalModesBypass:
    """Terminal modes (ESCALATION, COMPLETED) short-circuit before any check."""

    async def test_escalation_mode_no_checks(self):
        """ESCALATION mode returns immediately without digression or intent check."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="ESCALATION",
            user_message="hola sigo aqui",
        )

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
            ) as mock_dig_mgr,
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            result = await router_node(state)

            # Neither digression manager nor intent router should be invoked
            mock_dig_mgr.assert_not_called()
            mock_get_router.assert_not_called()
            assert result["last_node"] == "router"

    async def test_completed_mode_no_checks(self):
        """COMPLETED mode returns immediately without digression or intent check."""
        from agent.graph.conversation_graph import router_node

        state = _make_state(
            current_mode="COMPLETED",
            user_message="gracias por todo",
        )

        with (
            patch(
                "agent.graph.conversation_graph.get_digression_manager",
            ) as mock_dig_mgr,
            patch(
                "agent.graph.conversation_graph.get_intent_router",
            ) as mock_get_router,
        ):
            result = await router_node(state)

            mock_dig_mgr.assert_not_called()
            mock_get_router.assert_not_called()
            assert result["last_node"] == "router"
