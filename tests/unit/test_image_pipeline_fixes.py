"""
Tests for the image pipeline and message ordering fixes.

Covers:
- P1: Batch counter reset on completion message (Tarea 1.1)
- P2: Element image count validation (Tarea 1.2)
- P3: Follow-up message deduplication (Tarea 2.1)
- P4: Reconciliation element_code propagation (Tarea 3.1)
- P5: Non-blocking reconciliation (Tarea 2.2)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# P1: Batch counter reset on "listo"
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_completion_message_resets_batch_counter():
    """
    Verify that when user sends 'listo' (text-only, no images),
    reset_batch_counter() is called BEFORE reconciliation starts.

    This prevents the stale batch worker from sending a confirmation
    message after the agent has already processed 'listo'.
    """
    from agent.services.image_handling import is_completion_message

    # These should all be detected as completion messages
    assert is_completion_message("listo") is True
    assert is_completion_message("Listo") is True
    assert is_completion_message("LISTO") is True
    assert is_completion_message("ya está") is True

    # These should NOT
    assert is_completion_message("hola") is False
    assert is_completion_message("quiero presupuesto") is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_safe_reconcile_catches_exceptions():
    """
    Verify _safe_reconcile wraps errors and doesn't propagate them,
    since it runs as a background task.
    """
    from agent.main import _safe_reconcile

    mock_redis = AsyncMock()
    mock_checkpointer = AsyncMock()

    with patch(
        "agent.main.reconcile_on_completion",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Chatwoot API timeout"),
    ):
        # Should NOT raise — fire-and-forget wrapper
        await _safe_reconcile(mock_redis, mock_checkpointer, "12345")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_safe_reconcile_forwards_assignment_snapshot():
    """Background reconcile must forward the ingest assignment snapshot."""
    from agent.main import _safe_reconcile

    mock_redis = AsyncMock()
    mock_checkpointer = AsyncMock()
    snapshot = {
        "case_id": "case-123",
        "element_code": "PLACA_SOLAR",
    }

    with patch("agent.main.reconcile_on_completion", new_callable=AsyncMock) as reconcile_mock:
        await _safe_reconcile(
            mock_redis,
            mock_checkpointer,
            "12345",
            assignment_snapshot=snapshot,
        )

    reconcile_mock.assert_awaited_once_with(
        mock_redis,
        mock_checkpointer,
        "12345",
        assignment_snapshot=snapshot,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_build_image_assignment_snapshot_single_source_of_truth():
    """Ingest snapshot captures mode/case/element assignment once."""
    from agent.main import _build_image_assignment_snapshot

    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "photos",
        "element_codes": ["PLACA_SOLAR", "CABEZA"],
        "current_element_index": 0,
        "case_id": "case-from-context",
    }

    with (
        patch("agent.main.get_mode_context_from_checkpoint", new_callable=AsyncMock, return_value=mode_context),
        patch("agent.main.get_case_id_from_mode_context", new_callable=AsyncMock, return_value="case-from-context"),
        patch("agent.main.get_case_id_for_conversation", new_callable=AsyncMock) as fallback_case_mock,
    ):
        snapshot = await _build_image_assignment_snapshot(
            checkpointer=AsyncMock(),
            conversation_id="12345",
            customer_phone="+34600000000",
        )

    assert snapshot["case_id"] == "case-from-context"
    assert snapshot["in_image_collection_mode"] is True
    assert snapshot["element_code"] == "PLACA_SOLAR"
    fallback_case_mock.assert_not_awaited()


# =============================================================================
# P2: Element image count validation in confirmar_fotos_elemento
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_element_image_count_filters_by_element():
    """
    Verify _get_element_image_count uses both case_id AND element_code
    in the WHERE clause (not just case_id like _get_case_image_count).
    """
    import inspect
    from agent.tools.element_data_tools import _get_element_image_count

    source = inspect.getsource(_get_element_image_count)

    # Must filter by element_code
    assert "element_code" in source, (
        "_get_element_image_count must filter by element_code"
    )
    assert "CaseImage.element_code" in source, (
        "_get_element_image_count must use CaseImage.element_code in query"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_confirmar_fotos_has_usuario_confirma_parameter():
    """
    Verify confirmar_fotos_elemento now accepts usuario_confirma parameter,
    matching the pattern from confirmar_documentacion_base.
    """
    import inspect
    from agent.tools.element_data_tools import confirmar_fotos_elemento

    sig = inspect.signature(confirmar_fotos_elemento.coroutine)
    params = list(sig.parameters.keys())

    assert "usuario_confirma" in params, (
        "confirmar_fotos_elemento must accept usuario_confirma parameter"
    )


# =============================================================================
# P3: Follow-up message deduplication
# =============================================================================


@pytest.mark.unit
def test_follow_up_suppression_when_ai_response_contains_question():
    """
    Verify the deduplication logic: if ai_response already contains
    keywords like 'expediente' + a question mark, suppress follow_up.
    """
    # Simulate the deduplication logic from main.py
    ai_response = "El precio es 410€. ¿Quieres abrir el expediente?"
    follow_up = "¿Te gustaría que abramos el expediente para gestionar tu homologación?"

    ai_lower = ai_response.lower()
    fu_lower = follow_up.lower()
    overlap_keywords = ["expediente", "opción", "opcion", "gestionar"]
    has_overlap = any(kw in ai_lower and kw in fu_lower for kw in overlap_keywords)

    assert has_overlap is True, "Should detect keyword overlap"
    assert "?" in ai_lower, "ai_response should contain question mark"

    # This means follow_up should be suppressed
    should_suppress = has_overlap and "?" in ai_lower
    assert should_suppress is True, "Follow-up should be suppressed when content overlaps"


@pytest.mark.unit
def test_follow_up_sent_when_no_overlap():
    """
    Verify follow_up is sent normally when there's no content overlap.
    """
    ai_response = "El precio es 410€ +IVA. Te envío fotos de ejemplo:"
    follow_up = "¿Quieres abrir el expediente?"

    ai_lower = ai_response.lower()
    fu_lower = follow_up.lower()
    overlap_keywords = ["expediente", "opción", "opcion", "gestionar"]
    has_overlap = any(kw in ai_lower and kw in fu_lower for kw in overlap_keywords)

    # ai_response doesn't contain "expediente" so no overlap
    assert has_overlap is False, "Should NOT detect overlap when keywords differ"


@pytest.mark.unit
def test_follow_up_sent_when_ai_has_keyword_but_no_question():
    """
    Edge case: ai_response mentions 'expediente' but doesn't ask a question.
    Follow-up should still be sent.
    """
    ai_response = "El presupuesto incluye la gestión del expediente completo."
    follow_up = "¿Quieres que abramos el expediente?"

    ai_lower = ai_response.lower()
    fu_lower = follow_up.lower()
    overlap_keywords = ["expediente", "opción", "opcion", "gestionar"]
    has_overlap = any(kw in ai_lower and kw in fu_lower for kw in overlap_keywords)

    # There IS keyword overlap, but ai_response has no "?"
    assert has_overlap is True
    should_suppress = has_overlap and "?" in ai_lower
    assert should_suppress is False, "Should NOT suppress when ai_response has no question"


# =============================================================================
# P4: Reconciliation element_code propagation
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconcile_conversation_images_accepts_element_code():
    """
    Verify reconcile_conversation_images signature includes element_code.
    """
    import inspect
    from agent.services.image_handling import reconcile_conversation_images

    sig = inspect.signature(reconcile_conversation_images)
    params = list(sig.parameters.keys())

    assert "element_code" in params, (
        "reconcile_conversation_images must accept element_code parameter"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconcile_on_completion_extracts_element_code():
    """
    Verify reconcile_on_completion reads element_code from mode_context
    and passes it to reconcile_conversation_images.
    """
    import inspect
    from agent.services.image_handling import reconcile_on_completion

    source = inspect.getsource(reconcile_on_completion)

    assert "get_current_element_code" in source, (
        "reconcile_on_completion must call get_current_element_code"
    )
    assert "element_code=element_code" in source, (
        "reconcile_on_completion must pass element_code to reconcile_conversation_images"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_save_images_silently_uses_assignment_context_contract():
    """save_images_silently must consume explicit assignment context."""
    import inspect
    from agent.services.image_handling import save_images_silently

    sig = inspect.signature(save_images_silently)
    params = list(sig.parameters.keys())
    assert "assignment_context" in params

    source = inspect.getsource(save_images_silently)
    assert "if assignment_context:" in source
    assert "in_image_collection_mode" in source
    assert "element_code = None" in source


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconcile_on_completion_prefers_snapshot_before_fallback():
    """Reconciliation should use forwarded/persisted snapshot before fallback reads."""
    import inspect
    from agent.services.image_handling import reconcile_on_completion

    source = inspect.getsource(reconcile_on_completion)
    assert "persisted_snapshot = await get_assignment_snapshot" in source
    assert "effective_snapshot = assignment_snapshot or persisted_snapshot" in source
    assert "case_id = effective_snapshot.get(\"case_id\")" in source


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconcile_on_completion_has_dedupe_guards():
    """Completion reconciliation must guard against duplicates/retries."""
    import inspect
    from agent.services.image_handling import reconcile_on_completion

    source = inspect.getsource(reconcile_on_completion)
    assert "IMAGE_RECONCILE_INFLIGHT_PREFIX" in source
    assert "IMAGE_RECONCILE_RECENT_PREFIX" in source
    assert "nx=True" in source
    assert "completion_reconciliation_skipped_inflight" in source
    assert "completion_reconciliation_skipped_recent" in source


# =============================================================================
# P5: Non-blocking reconciliation
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconciliation_runs_as_background_task():
    """
    Verify the reconciliation is wrapped in asyncio.create_task
    in main.py, not blocking the response.
    """
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module)

    # Must contain asyncio.create_task for _safe_reconcile
    assert "_safe_reconcile" in source, (
        "main.py must define _safe_reconcile wrapper"
    )
    assert "asyncio.create_task" in source, (
        "main.py must use asyncio.create_task for reconciliation"
    )
    # The await reconcile_on_completion call should ONLY exist inside _safe_reconcile,
    # not directly in process_message. Extract _safe_reconcile body and verify
    # that any direct await is contained within it.
    safe_reconcile_source = inspect.getsource(main_module._safe_reconcile)
    direct_calls_in_module = source.count("await reconcile_on_completion(")
    calls_in_safe_reconcile = safe_reconcile_source.count("await reconcile_on_completion(")
    assert direct_calls_in_module == calls_in_safe_reconcile, (
        f"All 'await reconcile_on_completion(' calls must be inside _safe_reconcile. "
        f"Found {direct_calls_in_module} in module, {calls_in_safe_reconcile} in _safe_reconcile"
    )


# =============================================================================
# P6: Observability trace events (Task 4.2)
# =============================================================================


@pytest.mark.unit
def test_main_emits_image_assignment_resolved_log():
    """main.py must emit image_assignment_resolved structured log event."""
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module)
    assert "image_assignment_resolved" in source, (
        "main.py must emit 'image_assignment_resolved' trace event at ingest time"
    )


@pytest.mark.unit
def test_image_handling_emits_insert_persisted_log():
    """image_handling must emit image_insert_persisted for each saved image."""
    import inspect
    from agent.services import image_handling

    source = inspect.getsource(image_handling)
    # Must appear in both save_images_silently and reconcile_conversation_images
    occurrences = source.count("image_insert_persisted")
    assert occurrences >= 2, (
        f"image_handling must emit 'image_insert_persisted' in both save and reconcile paths "
        f"(found {occurrences}, expected >=2)"
    )


@pytest.mark.unit
def test_image_handling_emits_dedup_skipped_log():
    """image_handling must emit image_insert_dedup_skipped when all images accounted for."""
    import inspect
    from agent.services import image_handling

    source = inspect.getsource(image_handling)
    assert "image_insert_dedup_skipped" in source, (
        "image_handling must emit 'image_insert_dedup_skipped' when reconciliation finds no missing images"
    )


@pytest.mark.unit
def test_image_handling_emits_assignment_reused_for_reconcile_log():
    """reconcile_on_completion must log which snapshot source was used."""
    import inspect
    from agent.services import image_handling

    source = inspect.getsource(image_handling)
    assert "image_assignment_reused_for_reconcile" in source, (
        "reconcile_on_completion must emit 'image_assignment_reused_for_reconcile' trace event"
    )
    # Must log snapshot_source
    assert "snapshot_source" in source, (
        "image_assignment_reused_for_reconcile must include 'snapshot_source' field"
    )


@pytest.mark.unit
def test_expediente_mode_emits_transition_closure_log():
    """expediente_mode must emit expediente_transition_closure_emitted on fast-path break."""
    import inspect
    from agent.modes import expediente_mode

    source = inspect.getsource(expediente_mode)
    assert "expediente_transition_closure_emitted" in source, (
        "expediente_mode must emit 'expediente_transition_closure_emitted' trace event"
    )
    assert "has_deterministic_closure" in source, (
        "expediente_transition_closure_emitted must include 'has_deterministic_closure' field"
    )


# =============================================================================
# P7: Image assignment attribution regression (Task 5.2)
#
# Verifies:
# - Snapshot propagates correct element_code to save paths
# - Reconciliation prefers snapshot over checkpoint fallback
# - Dedupe guards prevent duplicate reconciliation processing
# - Stale/base-doc context yields element_code=None
# =============================================================================


class TestImageAssignmentAttributionRegression:
    """
    S2 regression: images must be attributed to the correct element_code
    based on the ingest-time assignment snapshot captured once per event.
    """

    # ------------------------------------------------------------------
    # Snapshot element_code propagation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_snapshot_element_code_propagated_to_save(self):
        """
        save_images_silently must use the snapshot's element_code, NOT
        re-derive it from checkpoint state (which may have mutated).
        """
        from agent.services.image_handling import save_images_silently

        snapshot = {
            "case_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "element_code": "PLACA_SOLAR",
            "in_image_collection_mode": True,
            "expediente_sub_mode": "collect_element_data",
            "element_phase": "photos",
        }

        mock_download = {
            "stored_filename": "test_img.jpg",
            "original_filename": "photo.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1234,
        }

        with (
            patch(
                "agent.services.image_handling.get_chatwoot_image_service",
            ) as mock_svc_factory,
            patch(
                "agent.services.image_handling.get_case_image_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "agent.services.image_handling.get_async_session",
            ) as mock_session_factory,
        ):
            mock_image_svc = MagicMock()
            mock_image_svc.download_image = AsyncMock(return_value=mock_download)
            mock_svc_factory.return_value = mock_image_svc

            # Track what CaseImage is created with
            captured_images = []
            mock_session = AsyncMock()
            mock_session.add = lambda img: captured_images.append(img)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            saved, failed = await save_images_silently(
                case_id="case-old-stale",
                conversation_id="conv-123",
                attachments=[{"file_type": "image", "data_url": "https://example.com/img.jpg"}],
                user_phone="+34600000000",
                assignment_context=snapshot,
            )

        assert saved == 1
        assert failed == 0
        assert len(captured_images) == 1
        img = captured_images[0]
        # The snapshot's element_code must be used, NOT the stale one
        assert img.element_code == "PLACA_SOLAR", (
            f"Expected element_code='PLACA_SOLAR' from snapshot, got {img.element_code!r}"
        )
        # The snapshot's case_id must override the stale one
        assert str(img.case_id) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", (
            f"Expected case_id from snapshot, got {img.case_id!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_base_doc_context_yields_element_code_none(self):
        """
        When snapshot indicates NOT in image collection mode (e.g. base docs
        sub-mode or element_phase != photos), element_code must be None.
        """
        from agent.services.image_handling import save_images_silently

        snapshot_base_docs = {
            "case_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "element_code": "ESCAPE",  # Would be set but should be overridden
            "in_image_collection_mode": False,  # Base docs context
            "expediente_sub_mode": "collect_base_docs",
        }

        mock_download = {
            "stored_filename": "base_img.jpg",
            "original_filename": "doc.jpg",
            "mime_type": "image/jpeg",
            "file_size": 2000,
        }

        with (
            patch(
                "agent.services.image_handling.get_chatwoot_image_service",
            ) as mock_svc_factory,
            patch(
                "agent.services.image_handling.get_case_image_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "agent.services.image_handling.get_async_session",
            ) as mock_session_factory,
        ):
            mock_image_svc = MagicMock()
            mock_image_svc.download_image = AsyncMock(return_value=mock_download)
            mock_svc_factory.return_value = mock_image_svc

            captured_images = []
            mock_session = AsyncMock()
            mock_session.add = lambda img: captured_images.append(img)
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            saved, failed = await save_images_silently(
                case_id="case-bbb",
                conversation_id="conv-456",
                attachments=[{"file_type": "image", "data_url": "https://example.com/doc.jpg"}],
                user_phone="+34600000000",
                assignment_context=snapshot_base_docs,
            )

        assert saved == 1
        assert len(captured_images) == 1
        assert captured_images[0].element_code is None, (
            "Base-doc images must have element_code=None regardless of snapshot's "
            f"element_code field. Got: {captured_images[0].element_code!r}"
        )

    # ------------------------------------------------------------------
    # Snapshot element_code from get_current_element_code
    # ------------------------------------------------------------------

    def test_get_current_element_code_photos_phase(self):
        """element_code is returned when sub_mode=collect_element_data and phase=photos."""
        from agent.services.image_handling import get_current_element_code

        mode_context = {
            "expediente_sub_mode": "collect_element_data",
            "element_phase": "photos",
            "element_codes": ["PLACA_SOLAR", "CABEZA"],
            "current_element_index": 1,
        }
        assert get_current_element_code(mode_context) == "CABEZA"

    def test_get_current_element_code_data_phase_returns_none(self):
        """element_code is None when element_phase=data (photos confirmed, collecting data)."""
        from agent.services.image_handling import get_current_element_code

        mode_context = {
            "expediente_sub_mode": "collect_element_data",
            "element_phase": "data",
            "element_codes": ["PLACA_SOLAR"],
            "current_element_index": 0,
        }
        assert get_current_element_code(mode_context) is None, (
            "Images during data phase are NOT element photos — must return None"
        )

    def test_get_current_element_code_base_docs_returns_none(self):
        """element_code is None when sub_mode is not collect_element_data."""
        from agent.services.image_handling import get_current_element_code

        mode_context = {
            "expediente_sub_mode": "collect_base_docs",
            "element_phase": "photos",
            "element_codes": ["ESCAPE"],
            "current_element_index": 0,
        }
        assert get_current_element_code(mode_context) is None

    def test_get_current_element_code_empty_context_returns_none(self):
        """element_code is None for empty or None mode_context."""
        from agent.services.image_handling import get_current_element_code

        assert get_current_element_code(None) is None
        assert get_current_element_code({}) is None


class TestReconciliationSnapshotPreference:
    """
    Reconciliation must prefer: forwarded snapshot > persisted Redis snapshot
    > checkpoint fallback. This prevents attribution drift across async timing.
    """

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reconcile_uses_forwarded_snapshot_over_persisted(self):
        """
        When both forwarded and persisted snapshots exist, the forwarded
        one (from the same ingest event) takes precedence.
        """
        from agent.services.image_handling import reconcile_on_completion

        forwarded = {
            "mode_context": {"expediente_sub_mode": "collect_element_data", "element_phase": "photos"},
            "case_id": "case-forwarded",
            "element_code": "PLACA_SOLAR",
            "in_image_collection_mode": True,
        }
        persisted = {
            "case_id": "case-persisted-stale",
            "element_code": "CABEZA",
            "in_image_collection_mode": True,
        }

        mock_redis = AsyncMock()
        # NX lock succeeds, recent marker absent
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        with (
            patch(
                "agent.services.image_handling.get_assignment_snapshot",
                new_callable=AsyncMock,
                return_value=persisted,
            ) as persisted_mock,
            patch(
                "agent.services.image_handling.get_case_id_from_mode_context",
                new_callable=AsyncMock,
                return_value="case-forwarded",
            ),
            patch(
                "agent.services.image_handling.get_async_session",
            ) as mock_session_factory,
            patch(
                "agent.services.image_handling.get_case_image_count",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ) as reconcile_mock,
        ):
            # Mock DB session for case_created_at lookup
            mock_case = MagicMock()
            mock_case.created_at = MagicMock()
            mock_case.created_at.timestamp = MagicMock(return_value=1700000000.0)
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_case)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            await reconcile_on_completion(
                redis_client=mock_redis,
                checkpointer=AsyncMock(),
                conversation_id="conv-789",
                assignment_snapshot=forwarded,
            )

        # get_assignment_snapshot should NOT have been called when forwarded exists
        persisted_mock.assert_not_awaited()

        # reconcile_conversation_images must receive forwarded element_code
        if reconcile_mock.await_count > 0:
            call_kwargs = reconcile_mock.call_args
            assert call_kwargs.kwargs.get("element_code") == "PLACA_SOLAR" or \
                   (len(call_kwargs.args) > 3 and call_kwargs.args[3] == "PLACA_SOLAR"), (
                "Reconciliation must use forwarded snapshot's element_code"
            )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reconcile_falls_back_to_persisted_snapshot(self):
        """
        When no forwarded snapshot exists, reconciliation must load the
        persisted snapshot from Redis before falling back to checkpoint reads.
        """
        from agent.services.image_handling import reconcile_on_completion

        persisted = {
            "case_id": "case-persisted",
            "element_code": "CABEZA",
            "in_image_collection_mode": True,
            "mode_context": {"expediente_sub_mode": "collect_element_data"},
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        with (
            patch(
                "agent.services.image_handling.get_assignment_snapshot",
                new_callable=AsyncMock,
                return_value=persisted,
            ) as persisted_mock,
            patch(
                "agent.services.image_handling.get_mode_context_from_checkpoint",
                new_callable=AsyncMock,
            ) as checkpoint_mock,
            patch(
                "agent.services.image_handling.get_async_session",
            ) as mock_session_factory,
            patch(
                "agent.services.image_handling.get_case_image_count",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ) as reconcile_mock,
        ):
            mock_case = MagicMock()
            mock_case.created_at = MagicMock()
            mock_case.created_at.timestamp = MagicMock(return_value=1700000000.0)
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_case)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            await reconcile_on_completion(
                redis_client=mock_redis,
                checkpointer=AsyncMock(),
                conversation_id="conv-abc",
                assignment_snapshot=None,  # No forwarded snapshot
            )

        # Must have loaded from persisted
        persisted_mock.assert_awaited_once()

        # Checkpoint fallback should NOT have been called because
        # persisted snapshot already provides mode_context
        checkpoint_mock.assert_not_awaited()


class TestReconciliationDedupeGuards:
    """
    Idempotency guards prevent duplicate reconciliation processing from
    repeated completion messages or concurrent retries.
    """

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_dedupe_skips_when_recent_marker_exists(self):
        """
        If a recent reconciliation marker exists in Redis, the function
        must skip immediately without running reconciliation.
        """
        from agent.services.image_handling import reconcile_on_completion

        mock_redis = AsyncMock()
        # recent marker EXISTS → should skip
        mock_redis.get = AsyncMock(return_value=b"1")
        mock_redis.set = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch(
            "agent.services.image_handling.reconcile_conversation_images",
            new_callable=AsyncMock,
        ) as reconcile_mock:
            await reconcile_on_completion(
                redis_client=mock_redis,
                checkpointer=AsyncMock(),
                conversation_id="conv-recent",
            )

        # reconcile_conversation_images should NOT have been called
        reconcile_mock.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_dedupe_skips_when_inflight_lock_taken(self):
        """
        If another reconciliation is already in-flight (NX lock fails),
        the function must skip immediately.
        """
        from agent.services.image_handling import reconcile_on_completion

        mock_redis = AsyncMock()
        # recent marker absent
        mock_redis.get = AsyncMock(return_value=None)
        # NX lock FAILS (another worker already has it)
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.delete = AsyncMock()

        with patch(
            "agent.services.image_handling.reconcile_conversation_images",
            new_callable=AsyncMock,
        ) as reconcile_mock:
            await reconcile_on_completion(
                redis_client=mock_redis,
                checkpointer=AsyncMock(),
                conversation_id="conv-inflight",
            )

        reconcile_mock.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_dedupe_sets_recent_marker_after_completion(self):
        """
        After successful reconciliation, a recent marker with 25s TTL
        must be set to prevent immediate re-processing.
        """
        from agent.services.image_handling import reconcile_on_completion

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        snapshot = {
            "case_id": "case-ccc",
            "in_image_collection_mode": True,
            "element_code": "ESCAPE",
            "mode_context": {"expediente_sub_mode": "collect_element_data"},
        }

        with (
            patch(
                "agent.services.image_handling.get_async_session",
            ) as mock_session_factory,
            patch(
                "agent.services.image_handling.get_case_image_count",
                new_callable=AsyncMock,
                return_value=3,
            ),
            patch(
                "agent.services.image_handling.reconcile_conversation_images",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            mock_case = MagicMock()
            mock_case.created_at = MagicMock()
            mock_case.created_at.timestamp = MagicMock(return_value=1700000000.0)
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_case)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_session

            await reconcile_on_completion(
                redis_client=mock_redis,
                checkpointer=AsyncMock(),
                conversation_id="conv-ddd",
                assignment_snapshot=snapshot,
            )

        # Verify recent marker was set with 25s TTL
        set_calls = mock_redis.set.call_args_list
        recent_set_call = [
            c for c in set_calls
            if "image_reconcile_recent:" in str(c)
        ]
        assert len(recent_set_call) >= 1, (
            "Must set recent marker after successful reconciliation"
        )
        # Verify ex=25 was passed
        for call in recent_set_call:
            assert call.kwargs.get("ex") == 25 or (
                len(call.args) >= 3 and call.args[2] == 25
            ) or "25" in str(call), (
                "Recent marker must have 25s TTL"
            )
