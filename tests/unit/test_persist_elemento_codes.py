"""
T04: Failing tests for _persist_image_delivery_outcome — elemento + docbase scopes.

Spec scenarios covered:
  Scenario 2 — scope="elemento" + sent_count>0 → delivery_element_code uppercased and
                merged into mode_context.imagenes_enviadas_codigos
  Scenario 6 — scope="documentacion_base" + sent_count>0 → "_BASE_DOCS" sentinel added
  Scenario 7 — sent_count=0 → code NOT added (retry must work)
  Regression — scope="presupuesto" behavior unchanged (imagenes_enviadas_codigos written)
  Edge — missing delivery_element_code in contract → warning logged, no crash,
          code merge skipped (but outcome still persisted)

Pattern mirrors test_main_delivery_codes_append.py.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _import_persist():
    from agent.main import _persist_image_delivery_outcome
    return _persist_image_delivery_outcome


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_graph_with_state(mc: dict) -> MagicMock:
    """Return a mock graph whose aget_state returns mode_context=mc."""
    graph = MagicMock()
    state_snapshot = MagicMock()
    state_snapshot.values = {"mode_context": mc}
    graph.aget_state = AsyncMock(return_value=state_snapshot)
    graph.aupdate_state = AsyncMock(return_value=None)
    return graph


def _make_elemento_contract(element_code: str | None = "SUBCHASIS") -> dict:
    contract: dict = {
        "delivery_scope": "elemento",
        "delivery_request_id": "req-elem-001",
        "delivery_requested_count": 1,
    }
    if element_code is not None:
        contract["delivery_element_code"] = element_code
    return contract


def _make_docbase_contract() -> dict:
    return {
        "delivery_scope": "documentacion_base",
        "delivery_request_id": "req-docbase-001",
        "delivery_requested_count": 3,
    }


def _make_presupuesto_contract() -> dict:
    return {
        "delivery_scope": "presupuesto",
        "delivery_request_id": "req-pres-001",
        "delivery_requested_count": 2,
    }


# ---------------------------------------------------------------------------
# Scenario 2: scope="elemento" persists delivery_element_code uppercased
# ---------------------------------------------------------------------------


class TestPersistElementoScope:
    """_persist_image_delivery_outcome — scope='elemento' new branch."""

    @pytest.mark.asyncio
    async def test_elemento_code_added_to_imagenes_enviadas_codigos(self):
        """
        Spec Scenario 2: scope="elemento", sent_count=1, delivery_element_code="ESCAPE"
        → "ESCAPE" must appear in mode_context.imagenes_enviadas_codigos after persist.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-elem-01"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_elemento_contract("ESCAPE"),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=None,
        )

        # At least one aupdate_state call must include imagenes_enviadas_codigos with ESCAPE
        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "ESCAPE" in codes_written, (
            f"Expected 'ESCAPE' in imagenes_enviadas_codigos across aupdate_state calls. "
            f"All calls: {all_calls}"
        )

    @pytest.mark.asyncio
    async def test_elemento_code_normalized_to_uppercase(self):
        """
        delivery_element_code is lowercase "escape" → must be stored as "ESCAPE".
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-elem-02"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_elemento_contract("escape"),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "ESCAPE" in codes_written, (
            f"Lowercase code must be stored uppercased. Got codes: {codes_written}"
        )

    @pytest.mark.asyncio
    async def test_elemento_code_merged_with_existing_codes(self):
        """
        Existing imagenes_enviadas_codigos=["MOTOR"] in checkpoint,
        new delivery of "ESCAPE" → both must be present after merge.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({"imagenes_enviadas_codigos": ["MOTOR"]})
        config = {"configurable": {"thread_id": "conv-elem-03"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_elemento_contract("ESCAPE"),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "MOTOR" in codes_written, "Existing code must be preserved"
        assert "ESCAPE" in codes_written, "New code must be added"

    # Scenario 7: sent_count=0 → code NOT persisted

    @pytest.mark.asyncio
    async def test_elemento_sent_count_zero_skips_code_merge(self):
        """
        Spec Scenario 7: sent_count=0 (transport failure) → MOTOR must NOT be added.
        Retry must work.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-elem-zero"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_elemento_contract("MOTOR"),
            attempted_count=1,
            sent_count=0,
            transport_error="timeout",
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "MOTOR" not in codes_written, (
            f"sent_count=0 must NOT persist the code. Got codes: {codes_written}"
        )

    # Edge: missing delivery_element_code → warn, no crash

    @pytest.mark.asyncio
    async def test_elemento_missing_delivery_element_code_no_crash(self):
        """
        delivery_element_code absent from contract → warning logged, no crash.
        aupdate_state may still be called (for image_delivery_result) but
        imagenes_enviadas_codigos must NOT contain any code.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-elem-missing"}}

        # No delivery_element_code in contract
        contract = _make_elemento_contract(element_code=None)

        with patch("agent.main.logger") as mock_logger:
            await _persist(
                graph=graph,
                config=config,
                delivery_contract=contract,
                attempted_count=1,
                sent_count=1,
                transport_error=None,
                images=None,
            )

        # Must not crash — function completes
        # Check no rogue code was added to imagenes_enviadas_codigos
        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert codes_written == [], (
            f"Missing delivery_element_code must not add any codes. Got: {codes_written}"
        )

    @pytest.mark.asyncio
    async def test_elemento_logs_warning_on_missing_code(self):
        """
        Missing delivery_element_code → a warning must be logged.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-elem-warn"}}
        contract = _make_elemento_contract(element_code=None)

        with patch("agent.main.logger") as mock_logger:
            await _persist(
                graph=graph,
                config=config,
                delivery_contract=contract,
                attempted_count=1,
                sent_count=1,
                transport_error=None,
                images=None,
            )
            # At least one warning call
            assert mock_logger.warning.called, (
                "logger.warning must be called when delivery_element_code is missing"
            )


# ---------------------------------------------------------------------------
# Scenario 6: scope="documentacion_base" → _BASE_DOCS sentinel added
# ---------------------------------------------------------------------------


class TestPersistDocbaseScope:
    """_persist_image_delivery_outcome — scope='documentacion_base' extension."""

    @pytest.mark.asyncio
    async def test_docbase_adds_base_docs_sentinel(self):
        """
        Spec Scenario 6: scope="documentacion_base", sent_count>0 →
        "_BASE_DOCS" must be merged into imagenes_enviadas_codigos.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-docbase-01"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_docbase_contract(),
            attempted_count=3,
            sent_count=3,
            transport_error=None,
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "_BASE_DOCS" in codes_written, (
            f"'_BASE_DOCS' sentinel must be added for documentacion_base scope. "
            f"Got codes: {codes_written}"
        )

    @pytest.mark.asyncio
    async def test_docbase_sent_count_zero_skips_sentinel(self):
        """
        sent_count=0 → _BASE_DOCS must NOT be added.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-docbase-zero"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_docbase_contract(),
            attempted_count=3,
            sent_count=0,
            transport_error="network",
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "_BASE_DOCS" not in codes_written, (
            f"sent_count=0 must NOT add _BASE_DOCS. Got codes: {codes_written}"
        )

    @pytest.mark.asyncio
    async def test_docbase_sentinel_merged_with_existing_codes(self):
        """
        Existing codes ["ESCAPE"] + docbase delivery → both "ESCAPE" and "_BASE_DOCS" present.
        """
        _persist = _import_persist()
        graph = _make_graph_with_state({"imagenes_enviadas_codigos": ["ESCAPE"]})
        config = {"configurable": {"thread_id": "conv-docbase-merge"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_docbase_contract(),
            attempted_count=3,
            sent_count=3,
            transport_error=None,
            images=None,
        )

        all_calls = graph.aupdate_state.call_args_list
        codes_written = []
        for call in all_calls:
            mc = (call[0][1] if call[0] else call[1]).get("mode_context", {})
            if "imagenes_enviadas_codigos" in mc:
                codes_written.extend(mc["imagenes_enviadas_codigos"])

        assert "ESCAPE" in codes_written, "Existing code must be preserved"
        assert "_BASE_DOCS" in codes_written, "_BASE_DOCS must be added"


# ---------------------------------------------------------------------------
# Regression: scope="presupuesto" must remain unchanged
# ---------------------------------------------------------------------------


class TestPersistPresupuestoRegression:
    """Regression: presupuesto branch behavior unchanged after refactor."""

    @pytest.mark.asyncio
    async def test_presupuesto_codes_still_written(self):
        """
        scope="presupuesto" with images having element_code →
        codes still written to imagenes_enviadas_codigos (unchanged behavior).
        """
        _persist = _import_persist()
        images = [{"element_code": "ESCAPE"}, {"tipo": "base"}]
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-pres-reg"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_presupuesto_contract(),
            attempted_count=2,
            sent_count=2,
            transport_error=None,
            images=images,
        )

        call_args = graph.aupdate_state.call_args
        mc_update = call_args[0][1]["mode_context"]
        assert "ESCAPE" in mc_update["imagenes_enviadas_codigos"]
        assert "_BASE_DOCS" in mc_update["imagenes_enviadas_codigos"]
        assert mc_update["imagenes_enviadas"] is True

    @pytest.mark.asyncio
    async def test_presupuesto_sent_count_zero_no_codes(self):
        """
        scope="presupuesto", sent_count=0 → no codes, imagenes_enviadas=False (regression).
        """
        _persist = _import_persist()
        images = [{"element_code": "ESCAPE"}]
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-pres-zero"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_presupuesto_contract(),
            attempted_count=1,
            sent_count=0,
            transport_error="timeout",
            images=images,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert mc_update["imagenes_enviadas"] is False
        assert mc_update["imagenes_enviadas_codigos"] == []
