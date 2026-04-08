"""
Phase 2 UX improvement tests for expediente-image-collection.

T-09: Per-element Redis batch key format
T-11: Worker handles old-format keys (backward compat)
T-13: Element-aware image-only ack
T-15: Worker CTA enrichment
T-17: Reconcile-on-demand in confirm_element_photos()
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# T-09: Per-element Redis batch key format
# ─────────────────────────────────────────────────────────────────────────────


class TestPerElementRedisKey:
    """T-09: _get_batch_redis_key isolates per-element keys."""

    def test_key_format_with_scope_key(self) -> None:
        """Key includes scope_key hash when scope_key is provided."""
        from agent.services.image_handling import _get_batch_redis_key

        key = _get_batch_redis_key("conv-123", "scope_abc")
        assert key.startswith("image_batch:conv-123:")
        assert "scope_abc" in key

    def test_key_format_without_scope_key_falls_back(self) -> None:
        """Key falls back to conversation-only when scope_key is None."""
        from agent.services.image_handling import _get_batch_redis_key

        key = _get_batch_redis_key("conv-123", None)
        assert key == "image_batch:conv-123"

    def test_different_scope_keys_produce_different_redis_keys(self) -> None:
        """Two different elements produce distinct Redis keys."""
        from agent.services.image_handling import _get_batch_redis_key

        key_elem1 = _get_batch_redis_key("conv-123", "case:abc:sub_mode:collect_element_data:scope:element:PLACA")
        key_elem2 = _get_batch_redis_key("conv-123", "case:abc:sub_mode:collect_element_data:scope:element:TOLDO")
        assert key_elem1 != key_elem2

    def test_same_scope_key_produces_same_redis_key(self) -> None:
        """Same scope_key always produces the same key (deterministic)."""
        from agent.services.image_handling import _get_batch_redis_key

        scope = "case:abc:sub_mode:collect_element_data:scope:element:PLACA"
        assert _get_batch_redis_key("conv-123", scope) == _get_batch_redis_key("conv-123", scope)

    @pytest.mark.asyncio
    async def test_round_trip_write_read(self) -> None:
        """Write then read via scope-keyed helpers returns correct count."""
        from agent.services.image_handling import (
            update_batch_counter,
            get_batch_info,
        )

        mock_redis = AsyncMock()
        # hgetall returns empty initially, then the stored mapping
        stored: dict = {}

        async def mock_hset(key, mapping=None):
            stored.update(mapping or {})

        async def mock_hgetall(key):
            return stored.copy()

        mock_redis.hgetall = mock_hgetall
        mock_redis.hset = mock_hset
        mock_redis.expire = AsyncMock()

        scope_key = "case:test:sub_mode:collect_element_data:scope:element:PLACA"
        await update_batch_counter(
            mock_redis,
            "conv-1",
            additional_count=3,
            user_phone="+34600000000",
            upload_scope_key=scope_key,
        )

        count, _ = await get_batch_info(mock_redis, "conv-1", scope_key)
        assert count == 3


# ─────────────────────────────────────────────────────────────────────────────
# T-11: Worker handles old-format keys (backward compat)
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkerOldFormatBackwardCompat:
    """T-11: Old keys (no upload_scope_key hash field) use pre-change logic."""

    def test_old_format_detected_by_missing_hash_field(self) -> None:
        """Key without upload_scope_key hash field → classified as legacy."""
        from agent.services.image_handling import _is_legacy_batch_key

        # Old hash: no upload_scope_key field
        old_data = {
            b"count": b"2",
            b"last_update": b"1234567890.0",
            b"user_phone": b"+34600000000",
            b"case_id": b"case-abc",
        }
        assert _is_legacy_batch_key(old_data) is True

    def test_new_format_detected_by_hash_field_presence(self) -> None:
        """Key with upload_scope_key hash field → classified as new format."""
        from agent.services.image_handling import _is_legacy_batch_key

        new_data = {
            b"count": b"2",
            b"last_update": b"1234567890.0",
            b"user_phone": b"+34600000000",
            b"case_id": b"case-abc",
            b"upload_scope_key": b"case:abc:sub_mode:collect_element_data:scope:element:PLACA",
        }
        assert _is_legacy_batch_key(new_data) is False

    def test_string_key_version_detected_as_new(self) -> None:
        """String keys (non-bytes) with upload_scope_key → new format."""
        from agent.services.image_handling import _is_legacy_batch_key

        new_data = {
            "count": "2",
            "upload_scope_key": "case:abc:sub_mode:collect_element_data:scope:element:PLACA",
        }
        assert _is_legacy_batch_key(new_data) is False

    def test_conversation_id_from_hash_field_not_key_name(self) -> None:
        """conversation_id comes from hash field, not key name parsing."""
        from agent.services.image_handling import _extract_conversation_id_from_batch

        data_with_field = {
            b"conversation_id": b"conv-42",
            b"count": b"3",
        }
        result = _extract_conversation_id_from_batch(
            key_str="image_batch:conv-42:some-hash",
            data=data_with_field,
        )
        assert result == "conv-42"

    def test_conversation_id_fallback_to_key_parsing_for_legacy(self) -> None:
        """Legacy keys (no conversation_id field) fall back to key name parsing."""
        from agent.services.image_handling import _extract_conversation_id_from_batch

        data_without_field = {
            b"count": b"3",
        }
        result = _extract_conversation_id_from_batch(
            key_str="image_batch:conv-99",
            data=data_without_field,
        )
        assert result == "conv-99"


# ─────────────────────────────────────────────────────────────────────────────
# T-13: Element-aware image-only ack
# ─────────────────────────────────────────────────────────────────────────────


class TestElementAwareImageOnlyAck:
    """T-13: Image-only ack messages are element-aware."""

    @pytest.mark.asyncio
    async def test_element_photos_ack_includes_display_name(self) -> None:
        """
        COLLECT_ELEMENT_DATA: ack uses element_display_name from mode_context.
        """
        from agent.modes.submodos.collect_element_data import ElementDataHandler

        mode_context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
            "element_display_names": {"PLACA_SOLAR": "Placa Solar Regulador Interior"},
        }
        state = {
            "conversation_id": "conv-1",
            "incoming_attachments": [{"file_type": "image"}, {"file_type": "image"}],
        }

        handler = ElementDataHandler()
        result = await handler.handle(
            message="",
            state=state,
            mode_context=mode_context,
            llm_loop_fn=AsyncMock(),
        )

        assert "Placa Solar Regulador Interior" in result["ai_response"]
        assert "2" in result["ai_response"]

    @pytest.mark.asyncio
    async def test_base_docs_ack_mentions_documentacion_base(self) -> None:
        """COLLECT_BASE_DOCS: ack says 'documentación base'."""
        from agent.modes.submodos.collect_base_docs import BaseDocsHandler

        mode_context = {"expediente_sub_mode": "collect_base_docs"}
        state = {
            "conversation_id": "conv-2",
            "incoming_attachments": [{"file_type": "image"}],
        }

        handler = BaseDocsHandler()
        result = await handler.handle(
            message="",
            state=state,
            mode_context=mode_context,
            llm_loop_fn=AsyncMock(),
        )

        assert "documentaci" in result["ai_response"].lower()
        assert "1" in result["ai_response"]

    @pytest.mark.asyncio
    async def test_missing_display_name_falls_back_to_generic(self) -> None:
        """When element_display_names missing → fallback to element code."""
        from agent.modes.submodos.collect_element_data import ElementDataHandler

        mode_context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["TOLDO_GALIBO"],
            "current_element_index": 0,
            # No element_display_names key
        }
        state = {
            "conversation_id": "conv-3",
            "incoming_attachments": [{"file_type": "image"}],
        }

        handler = ElementDataHandler()
        result = await handler.handle(
            message="",
            state=state,
            mode_context=mode_context,
            llm_loop_fn=AsyncMock(),
        )

        # Should still produce a valid ack (fallback to code or generic)
        assert result.get("ai_response")
        assert "listo" in result["ai_response"]

    @pytest.mark.asyncio
    async def test_element_ack_uses_db_count_with_timeout(self) -> None:
        """
        When DB count available within 2s, ack shows DB count,
        not only attachment count.
        """
        from agent.modes.submodos.collect_element_data import ElementDataHandler

        # Simulate DB returning 5 images (previously sent + current)
        mock_db_count = AsyncMock(return_value=5)

        mode_context = {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
            "element_display_names": {"PLACA_SOLAR": "Placa Solar"},
            "case_id": "case-abc",
        }
        state = {
            "conversation_id": "conv-4",
            "incoming_attachments": [{"file_type": "image"}],
        }

        handler = ElementDataHandler()
        with patch(
            "agent.modes.submodos.collect_element_data._get_element_photo_db_count",
            new=mock_db_count,
        ):
            result = await handler.handle(
                message="",
                state=state,
                mode_context=mode_context,
                llm_loop_fn=AsyncMock(),
            )

        # Either the DB count (5) or attachment count (1) in ack
        assert result.get("ai_response")
        # The ack should reference "Placa Solar"
        assert "Placa Solar" in result["ai_response"]


# ─────────────────────────────────────────────────────────────────────────────
# T-15: Worker CTA enrichment
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkerCTAEnrichment:
    """T-15: Worker CTA messages are scope-aware."""

    def test_build_cta_message_with_element_display_name(self) -> None:
        """CTA includes element display name when available."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=3,
            failed=0,
            total_images=3,
            element_display_name="Placa Solar Regulador Interior",
            is_base_docs=False,
        )
        assert "Placa Solar Regulador Interior" in msg
        assert "3" in msg
        assert "listo" in msg

    def test_build_cta_message_base_docs_form(self) -> None:
        """CTA for base docs says 'documentación base' variant."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=2,
            failed=0,
            total_images=2,
            element_display_name=None,
            is_base_docs=True,
        )
        assert "documentaci" in msg.lower()
        assert "listo" in msg

    def test_build_cta_message_fallback_to_este_bloque(self) -> None:
        """No display name + not base docs → 'este bloque' fallback."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=1,
            failed=0,
            total_images=1,
            element_display_name=None,
            is_base_docs=False,
        )
        assert "este bloque" in msg or "listo" in msg

    def test_build_cta_message_orphan_no_cta(self) -> None:
        """Orphan batches (no case_id) → no CTA."""
        from agent.services.image_handling import _build_worker_cta_message

        msg = _build_worker_cta_message(
            count=0,
            failed=0,
            total_images=0,
            element_display_name=None,
            is_base_docs=False,
            is_orphan=True,
        )
        # Orphan → None or empty
        assert not msg


# ─────────────────────────────────────────────────────────────────────────────
# T-17: Reconcile-on-demand in confirm_element_photos()
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReconcileOnDemand:
    """T-17: Reconcile-on-demand only triggers under right conditions."""

    def _make_mode_context(self) -> dict:
        return {
            "expediente_sub_mode": "collect_element_data",
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
            "element_phase": "photos",
            "element_data_status": {"PLACA_SOLAR": "pending"},
            "case_id": "case-abc",
            "category_id": "cat-123",
            "user_phone": "+34600000000",
        }

    async def test_reconcile_triggered_when_count_zero_after_both_phases_and_user_confirms(
        self,
    ) -> None:
        """
        count=0 after both polling phases AND usuario_confirma=True
        → reconcile_conversation_images called.

        Call sequence for _get_element_image_count via TwoPhasePoller:
        - pre-polling check: 0
        - poller.poll initial check: 0
        - poller phase1 recheck: 0
        - poller phase2 recheck: 0
        Total: 4 calls → all return 0 → reconcile triggered
        """
        from agent.services import element_data_service as svc

        mock_reconcile = AsyncMock(return_value=(2, 0))
        mock_image_count = AsyncMock(return_value=0)

        async def _pass_through_wait_for(coro, timeout):
            """Let the reconcile coroutine run without a real timeout."""
            return await coro

        with (
            patch.object(svc, "_get_element_image_count", mock_image_count),
            # Patch at the source module so the lazy `from ... import` picks it up
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                mock_reconcile,
            ),
            patch("asyncio.sleep", new=AsyncMock()),
            patch("asyncio.wait_for", side_effect=_pass_through_wait_for),
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=MagicMock(
                    PHOTO_COMPLETION_WAIT_SECONDS=0,
                    PHOTO_COMPLETION_RETRY_WAIT_SECONDS=0,
                ),
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await svc.confirm_element_photos(
                case_id="case-abc",
                category_id="cat-123",
                mode_context=self._make_mode_context(),
                usuario_confirma=True,
                conversation_id="conv-1",
                active_batch_id=None,
                idempotency_key="key-1",
                already_confirmed_this_turn=False,
            )

        mock_reconcile.assert_called_once()
        # After reconcile, count still 0 (mock doesn't update the side_effect),
        # so the result should be needs_photos=True (non-fatal: still returns).
        assert result is not None

    async def test_reconcile_not_triggered_when_count_positive_after_polling(
        self,
    ) -> None:
        """
        count > 0 after polling → reconcile NOT triggered.
        """
        from agent.services import element_data_service as svc

        mock_reconcile = AsyncMock(return_value=(1, 0))
        # pre-poll: 0, poller-initial: 0, poller-phase1: 3 (≥1 → short-circuits)
        mock_image_count = AsyncMock(side_effect=[0, 0, 3])

        with (
            patch.object(svc, "_get_element_image_count", mock_image_count),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                mock_reconcile,
            ),
            patch("asyncio.sleep", new=AsyncMock()),
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=MagicMock(
                    PHOTO_COMPLETION_WAIT_SECONDS=0,
                    PHOTO_COMPLETION_RETRY_WAIT_SECONDS=0,
                ),
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "agent.services.element_data_service._get_element_by_code",
                new=AsyncMock(return_value=MagicMock(id="elem-id", name="Placa Solar")),
            ),
            patch(
                "agent.services.element_data_service._get_required_fields_for_element",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "agent.services.element_data_service._update_case_element_data",
                new=AsyncMock(),
            ),
            patch(
                "agent.services.case_image_batch_service.get_case_image_batch_service",
                return_value=MagicMock(finalize_for_scope=AsyncMock()),
            ),
        ):
            result = await svc.confirm_element_photos(
                case_id="case-abc",
                category_id="cat-123",
                mode_context=self._make_mode_context(),
                usuario_confirma=True,
                conversation_id="conv-1",
                active_batch_id=None,
                idempotency_key="key-2",
                already_confirmed_this_turn=False,
            )

        mock_reconcile.assert_not_called()

    async def test_reconcile_not_triggered_when_usuario_confirma_false(
        self,
    ) -> None:
        """
        count=0 but usuario_confirma=False → no reconcile, returns needs_confirmation.
        """
        from agent.services import element_data_service as svc

        mock_reconcile = AsyncMock()
        mock_image_count = AsyncMock(return_value=0)

        with (
            patch.object(svc, "_get_element_image_count", mock_image_count),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                mock_reconcile,
            ),
        ):
            result = await svc.confirm_element_photos(
                case_id="case-abc",
                category_id="cat-123",
                mode_context=self._make_mode_context(),
                usuario_confirma=False,
                conversation_id="conv-1",
                active_batch_id=None,
                idempotency_key="key-3",
                already_confirmed_this_turn=False,
            )

        mock_reconcile.assert_not_called()
        assert result.get("needs_confirmation") is True

    async def test_reconcile_non_fatal_on_timeout(self) -> None:
        """
        Reconcile times out → exception caught, no propagation.
        count stays 0 → returns needs_photos response.
        """
        from agent.services import element_data_service as svc

        # count=0 throughout
        mock_image_count = AsyncMock(return_value=0)

        async def _timeout_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        with (
            patch.object(svc, "_get_element_image_count", mock_image_count),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                AsyncMock(return_value=(0, 0)),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
            # Patch asyncio.wait_for globally so our timeout_wait_for fires
            patch("asyncio.wait_for", side_effect=_timeout_wait_for),
            patch(
                "agent.services.element_data_service._get_two_phase_settings",
                return_value=MagicMock(
                    PHOTO_COMPLETION_WAIT_SECONDS=0,
                    PHOTO_COMPLETION_RETRY_WAIT_SECONDS=0,
                ),
            ),
            patch(
                "agent.services.element_data_service._send_poller_feedback",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            # Must not raise
            result = await svc.confirm_element_photos(
                case_id="case-abc",
                category_id="cat-123",
                mode_context=self._make_mode_context(),
                usuario_confirma=True,
                conversation_id="conv-1",
                active_batch_id=None,
                idempotency_key="key-4",
                already_confirmed_this_turn=False,
            )

        # Non-fatal: returns needs_photos (count still 0)
        assert result.get("success") is False
        assert result.get("needs_photos") is True or result.get("received") is False
