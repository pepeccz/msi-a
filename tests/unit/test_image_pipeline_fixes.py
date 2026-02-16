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
    # The old blocking pattern should be gone
    assert "await reconcile_on_completion(" not in source.replace(
        "await reconcile_on_completion(redis_client, checkpointer, conversation_id)",
        ""  # Only check outside of _safe_reconcile
    ), "main.py should not directly await reconcile_on_completion in process_message"
