"""
Tests for Phase 2 of memory system refactor (refactor-memory-system).

Covers:
- WS2: build_structured_summary — deterministic summary content
- WS2: maybe_summarize — threshold logic, RemoveMessage emission, window retention

All tests are synchronous or use pytest-asyncio.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from agent.graph.summarize_node import build_structured_summary, maybe_summarize


# ---------------------------------------------------------------------------
# build_structured_summary
# ---------------------------------------------------------------------------


class TestBuildStructuredSummary:
    """Tests for deterministic structured summary builder."""

    def test_empty_state(self):
        summary = build_structured_summary({})
        assert summary == "Conversación sin contexto relevante registrado."

    def test_user_identity(self):
        state = {"user_name": "Carlos", "client_type": "particular", "user_phone": "+34612345678"}
        summary = build_structured_summary(state)
        assert "Carlos" in summary
        assert "particular" in summary
        assert "+34612345678" in summary

    def test_current_mode(self):
        state = {"current_mode": "PRESUPUESTO_MODE"}
        summary = build_structured_summary(state)
        assert "PRESUPUESTO_MODE" in summary

    def test_mode_history(self):
        state = {"mode_history": ["START", "CONSULTA_MODE", "PRESUPUESTO_MODE"]}
        summary = build_structured_summary(state)
        assert "START → CONSULTA_MODE → PRESUPUESTO_MODE" in summary

    def test_presupuesto_context(self):
        state = {
            "mode_context": {
                "elementos_confirmados": [{"codigo": "ESCAPE"}, {"codigo": "SUSPENSION"}],
                "tarifa_calculada": {"datos": {"price": 410}},
                "precio_comunicado": True,
                "imagenes_enviadas": True,
            },
        }
        summary = build_structured_summary(state)
        assert "ESCAPE" in summary
        assert "SUSPENSION" in summary
        assert "410€" in summary
        assert "Precio comunicado" in summary
        assert "Imágenes ejemplo enviadas" in summary

    def test_expediente_context(self):
        state = {
            "mode_context": {
                "case_id": "abc-123",
                "element_codes": ["ESCAPE", "SUSPENSION", "FARO"],
                "current_element_index": 1,
                "element_phase": "data",
                "personal_data": {"nombre": "Carlos", "apellidos": "López", "email": None},
                "vehicle_data": {"marca": "Toyota", "modelo": None},
            },
        }
        summary = build_structured_summary(state)
        assert "abc-123" in summary
        assert "2/3" in summary  # current_element_index + 1 / total
        assert "data" in summary
        assert "nombre" in summary
        assert "apellidos" in summary
        assert "marca" in summary

    def test_escalation(self):
        state = {
            "escalation_triggered": True,
            "escalation_reason": "usuario solicitó hablar con humano",
        }
        summary = build_structured_summary(state)
        assert "Escalación: sí" in summary
        assert "usuario solicitó" in summary

    def test_message_count(self):
        state = {"total_message_count": 45}
        summary = build_structured_summary(state)
        assert "45" in summary


# ---------------------------------------------------------------------------
# maybe_summarize — threshold logic
# ---------------------------------------------------------------------------


class TestMaybeSummarize:
    """Tests for the conditional summarization node.

    All tests pass explicit threshold/window to avoid pollution from
    conftest fixtures that mock get_settings().
    """

    THRESHOLD = 30
    WINDOW = 10

    @pytest.mark.asyncio
    async def test_below_threshold_noop(self):
        """No summarization when below threshold."""
        state = {
            "messages": [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(10)],
            "total_message_count": 10,
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert result == {}

    @pytest.mark.asyncio
    async def test_not_at_threshold_boundary_noop(self):
        """No summarization when at 31 messages (not divisible by 30)."""
        state = {
            "messages": [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(31)],
            "total_message_count": 31,
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert result == {}

    @pytest.mark.asyncio
    async def test_at_threshold_triggers(self):
        """Summarization triggers at exactly threshold (30)."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(30)]
        state = {
            "messages": messages,
            "total_message_count": 30,
            "current_mode": "PRESUPUESTO_MODE",
            "user_name": "Carlos",
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert "conversation_summary" in result
        assert "messages" in result
        assert "Carlos" in result["conversation_summary"]

    @pytest.mark.asyncio
    async def test_at_double_threshold_triggers(self):
        """Summarization triggers again at 60 messages."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(35)]
        state = {
            "messages": messages,
            "total_message_count": 60,
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert "conversation_summary" in result

    @pytest.mark.asyncio
    async def test_remove_message_ids_correct(self):
        """RemoveMessage IDs match the oldest messages, retaining window."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(30)]
        state = {
            "messages": messages,
            "total_message_count": 30,
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)

        # Window = 10, so 20 messages should be removed
        remove_ops = result["messages"]
        assert len(remove_ops) == 20
        assert all(isinstance(op, RemoveMessage) for op in remove_ops)

        # Verify correct IDs are being removed (the oldest 20)
        removed_ids = {op.id for op in remove_ops}
        expected_removed = {f"id_{i}" for i in range(20)}
        assert removed_ids == expected_removed

    @pytest.mark.asyncio
    async def test_window_respected(self):
        """After trim, last MEMORY_MESSAGES_WINDOW messages remain."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(30)]
        state = {
            "messages": messages,
            "total_message_count": 30,
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)

        # 20 removed, 10 retained
        removed_ids = {op.id for op in result["messages"]}
        retained_ids = {f"id_{i}" for i in range(20, 30)}
        assert removed_ids.isdisjoint(retained_ids)

    @pytest.mark.asyncio
    async def test_few_messages_in_checkpoint_noop(self):
        """If checkpoint has fewer messages than window, skip trim."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(8)]
        state = {
            "messages": messages,
            "total_message_count": 30,  # Threshold met but not enough messages to trim
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert result == {}

    @pytest.mark.asyncio
    async def test_summary_contains_state_data(self):
        """Summary extracts relevant fields from state."""
        messages = [HumanMessage(content=f"msg{i}", id=f"id_{i}") for i in range(30)]
        state = {
            "messages": messages,
            "total_message_count": 30,
            "user_name": "María",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "case_id": "case-xyz",
                "element_codes": ["ESCAPE"],
                "current_element_index": 0,
            },
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        summary = result["conversation_summary"]
        assert "María" in summary
        assert "EXPEDIENTE_MODE" in summary
        assert "case-xyz" in summary

    @pytest.mark.asyncio
    async def test_messages_without_ids_still_saves_summary(self):
        """If messages lack IDs, summary is saved but no RemoveMessage emitted."""
        # Simulate legacy dicts without id field
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
        state = {
            "messages": messages,
            "total_message_count": 30,
            "current_mode": "CONSULTA_MODE",
        }
        result = await maybe_summarize(state, threshold=self.THRESHOLD, window=self.WINDOW)
        assert "conversation_summary" in result
        # No RemoveMessage since no IDs
        assert "messages" not in result
