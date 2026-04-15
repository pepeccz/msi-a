"""
T-10: Tests for _persist_image_delivery_outcome imagenes_enviadas_codigos append.

Verifies:
- imagenes_enviadas_codigos is written on presupuesto scope delivery
- Codes are extracted from images list (element_code + tipo=base sentinel)
- Existing codes are merged (append) from current checkpoint state
- Fallback: images without element_code but tipo=base → "_BASE_DOCS"
- sent_count=0 → no new codes written, bool=False
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Import helpers — same pattern as other unit tests in this project
# ---------------------------------------------------------------------------

def _import_module():
    """Import agent.main functions under test with stubs in place."""
    from agent.main import _extract_sent_codes_from_images, _persist_image_delivery_outcome
    return _extract_sent_codes_from_images, _persist_image_delivery_outcome


# ---------------------------------------------------------------------------
# _extract_sent_codes_from_images
# ---------------------------------------------------------------------------


class TestExtractSentCodes:
    """Unit tests for the pure helper that extracts codes from image dicts."""

    def test_element_code_extracted_and_uppercased(self):
        _extract, _ = _import_module()
        images = [{"element_code": "escape", "url": "http://x"}, {"element_code": "SUSPENSION", "url": "http://y"}]
        result = _extract(images)
        assert result == ["ESCAPE", "SUSPENSION"]

    def test_tipo_base_becomes_sentinel(self):
        _extract, _ = _import_module()
        images = [{"tipo": "base", "url": "http://x"}]
        result = _extract(images)
        assert result == ["_BASE_DOCS"]

    def test_mixed_element_and_base(self):
        _extract, _ = _import_module()
        images = [
            {"element_code": "ESCAPE", "tipo": "element"},
            {"tipo": "base"},
            {"element_code": "SUSPENSION"},
        ]
        result = _extract(images)
        assert "ESCAPE" in result
        assert "_BASE_DOCS" in result
        assert "SUSPENSION" in result
        assert len(result) == 3

    def test_dedup_same_code(self):
        _extract, _ = _import_module()
        images = [
            {"element_code": "ESCAPE"},
            {"element_code": "escape"},  # duplicate after upper
        ]
        result = _extract(images)
        assert result == ["ESCAPE"]

    def test_dedup_base_docs_sentinel(self):
        _extract, _ = _import_module()
        images = [{"tipo": "base"}, {"tipo": "base"}]
        result = _extract(images)
        assert result == ["_BASE_DOCS"]

    def test_unknown_image_skipped(self):
        """Images without element_code and tipo != base are silently skipped."""
        _extract, _ = _import_module()
        images = [{"url": "http://unknown", "tipo": "element"}]
        result = _extract(images)
        assert result == []

    def test_empty_list_returns_empty(self):
        _extract, _ = _import_module()
        assert _extract([]) == []

    def test_non_dict_entries_skipped(self):
        _extract, _ = _import_module()
        images = ["http://str", None, {"element_code": "ESCAPE"}]
        result = _extract(images)
        assert result == ["ESCAPE"]


# ---------------------------------------------------------------------------
# _persist_image_delivery_outcome — presupuesto scope
# ---------------------------------------------------------------------------


def _make_delivery_contract(**overrides) -> dict:
    base = {
        "delivery_scope": "presupuesto",
        "delivery_request_id": "req-123",
        "delivery_requested_count": 2,
    }
    base.update(overrides)
    return base


def _make_graph_with_state(mc: dict) -> MagicMock:
    """Return a mock graph whose aget_state returns mode_context=mc."""
    graph = MagicMock()
    state_snapshot = MagicMock()
    state_snapshot.values = {"mode_context": mc}
    graph.aget_state = AsyncMock(return_value=state_snapshot)
    graph.aupdate_state = AsyncMock(return_value=None)
    return graph


class TestPersistDeliveryCodes:
    """Integration tests for the presupuesto branch of _persist_image_delivery_outcome."""

    @pytest.mark.asyncio
    async def test_codes_written_on_success(self):
        _, _persist = _import_module()
        images = [{"element_code": "ESCAPE"}, {"tipo": "base"}]
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-1"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
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
    async def test_codes_appended_to_existing(self):
        """New codes are merged with existing codes from checkpoint (not replaced)."""
        _, _persist = _import_module()
        images = [{"element_code": "SUSPENSION"}]
        graph = _make_graph_with_state({"imagenes_enviadas_codigos": ["ESCAPE"]})
        config = {"configurable": {"thread_id": "conv-1"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=images,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert "ESCAPE" in mc_update["imagenes_enviadas_codigos"]
        assert "SUSPENSION" in mc_update["imagenes_enviadas_codigos"]

    @pytest.mark.asyncio
    async def test_no_duplicate_codes_after_merge(self):
        """Codes already present in checkpoint are NOT duplicated."""
        _, _persist = _import_module()
        images = [{"element_code": "ESCAPE"}]
        graph = _make_graph_with_state({"imagenes_enviadas_codigos": ["ESCAPE"]})
        config = {"configurable": {"thread_id": "conv-dedup"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=images,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert mc_update["imagenes_enviadas_codigos"].count("ESCAPE") == 1

    @pytest.mark.asyncio
    async def test_sent_count_zero_no_new_codes(self):
        """sent_count=0 → no codes extracted, bool=False."""
        _, _persist = _import_module()
        images = [{"element_code": "ESCAPE"}]
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-zero"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
            attempted_count=1,
            sent_count=0,
            transport_error="timeout",
            images=images,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert mc_update["imagenes_enviadas"] is False
        assert mc_update["imagenes_enviadas_codigos"] == []

    @pytest.mark.asyncio
    async def test_fallback_to_images_none(self):
        """images=None → empty codes list, no crash."""
        _, _persist = _import_module()
        graph = _make_graph_with_state({})
        config = {"configurable": {"thread_id": "conv-none"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
            attempted_count=0,
            sent_count=0,
            transport_error=None,
            images=None,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert mc_update["imagenes_enviadas_codigos"] == []

    @pytest.mark.asyncio
    async def test_aget_state_failure_does_not_crash(self):
        """If aget_state raises, we still persist with empty existing codes."""
        _, _persist = _import_module()
        images = [{"element_code": "ESCAPE"}]
        graph = MagicMock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("checkpoint error"))
        graph.aupdate_state = AsyncMock(return_value=None)
        config = {"configurable": {"thread_id": "conv-err"}}

        await _persist(
            graph=graph,
            config=config,
            delivery_contract=_make_delivery_contract(),
            attempted_count=1,
            sent_count=1,
            transport_error=None,
            images=images,
        )

        mc_update = graph.aupdate_state.call_args[0][1]["mode_context"]
        assert "ESCAPE" in mc_update["imagenes_enviadas_codigos"]
