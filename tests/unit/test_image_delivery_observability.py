import pytest

from agent.tools.image_tools import (
    clear_image_tools_state,
    enviar_imagenes_ejemplo,
    set_current_state_for_image_tools,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_enviar_imagenes_marks_intent_only_and_emits_contract() -> None:
    state = {
        "conversation_id": "12345",
        "mode_context": {
            "precio_comunicado": True,
            "imagenes_enviadas": False,
            "tarifa_calculada": {
                "imagenes_ejemplo": [
                    {
                        "url": "https://example.com/placa.jpg",
                        "status": "active",
                        "descripcion": "Foto de placa",
                    },
                ]
            },
        },
    }

    set_current_state_for_image_tools(state)
    try:
        result = await enviar_imagenes_ejemplo.ainvoke(
            {
                "tipo": "presupuesto",
                "follow_up_message": "Te envio ejemplos.",
            }
        )
    finally:
        clear_image_tools_state()

    assert result["success"] is True
    assert result["_internal_flags"]["imagenes_enviadas"] is False
    assert result["_internal_flags"]["imagenes_envio_intent_creado"] is True
    assert result["_internal_flags"]["imagenes_delivery_request_id"]
    outcome = result["_internal_flags"]["imagenes_delivery_outcome"]
    assert outcome["status"] == "intent_created"
    assert outcome["requested_count"] == 1
    assert outcome["sent_count"] == 0

    contract = result["_pending_images"]["delivery_contract"]
    assert contract["version"] == "v1"
    assert contract["delivery_request_id"]
    assert contract["delivery_scope"] == "presupuesto"
    assert contract["delivery_source_tool"] == "enviar_imagenes_ejemplo"
    assert contract["delivery_conversation_id"] == "12345"
    assert contract["delivery_requested_count"] == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_enviar_imagenes_blocks_stale_budget_scope() -> None:
    state = {
        "conversation_id": "12345",
        "mode_context": {
            "precio_comunicado": True,
            "element_codes": ["TOLDO"],
            "tarifa_calculada": {
                "datos": {"element_codes": ["PLACA_SOLAR"]},
                "imagenes_ejemplo": [
                    {
                        "url": "https://example.com/placa.jpg",
                        "status": "active",
                        "descripcion": "Foto de placa",
                    }
                ],
            },
        },
    }

    set_current_state_for_image_tools(state)
    try:
        result = await enviar_imagenes_ejemplo.ainvoke({"tipo": "presupuesto"})
    finally:
        clear_image_tools_state()

    assert result["success"] is False
    assert "presupuesto" in result["message"].lower()
    assert "recalcula" in result["message"].lower()


@pytest.mark.unit
def test_resolve_image_delivery_contract_defaults() -> None:
    pytest.importorskip("phonenumbers")
    from agent.main import _resolve_image_delivery_contract

    resolved = _resolve_image_delivery_contract({}, "conv-1")

    assert resolved["delivery_contract_version"] == "v1"
    assert resolved["delivery_request_id"]
    assert resolved["delivery_scope"] == "presupuesto"
    assert resolved["delivery_conversation_id"] == "conv-1"
    assert resolved["delivery_requested_count"] == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("attempted_count", "sent_count", "expected"),
    [
        (0, 0, "failure"),
        (2, 2, "full_success"),
        (3, 1, "partial_success"),
        (2, 0, "failure"),
    ],
)
def test_classify_image_delivery_outcome(
    attempted_count: int,
    sent_count: int,
    expected: str,
) -> None:
    pytest.importorskip("phonenumbers")
    from agent.main import _classify_image_delivery_outcome

    assert _classify_image_delivery_outcome(attempted_count, sent_count) == expected


@pytest.mark.unit
def test_build_image_delivery_outcome_state_payload() -> None:
    pytest.importorskip("phonenumbers")
    from agent.main import _build_image_delivery_outcome_state

    payload = _build_image_delivery_outcome_state(
        delivery_contract={
            "delivery_request_id": "req-1",
            "delivery_scope": "presupuesto",
            "delivery_requested_count": 2,
        },
        attempted_count=2,
        sent_count=1,
        transport_error=None,
    )

    assert payload["status"] == "partial_success"
    assert payload["request_id"] == "req-1"
    assert payload["scope"] == "presupuesto"
    assert payload["requested_count"] == 2
    assert payload["attempted_count"] == 2
    assert payload["sent_count"] == 1
    assert payload["failed_count"] == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_persist_image_delivery_outcome_uses_thread_scoped_config() -> None:
    pytest.importorskip("phonenumbers")
    from agent.main import _persist_image_delivery_outcome
    from unittest.mock import AsyncMock

    graph = AsyncMock()

    await _persist_image_delivery_outcome(
        graph=graph,
        config={"configurable": {"thread_id": "conv-77", "checkpoint_ns": "conversation"}},
        delivery_contract={
            "delivery_scope": "presupuesto",
            "delivery_request_id": "req-77",
            "delivery_requested_count": 2,
        },
        attempted_count=2,
        sent_count=1,
        transport_error="timeout",
    )

    graph.aupdate_state.assert_awaited_once()
    aupdate_config = graph.aupdate_state.await_args.args[0]
    assert aupdate_config == {"configurable": {"thread_id": "conv-77"}}

    state_update = graph.aupdate_state.await_args.args[1]
    outcome = state_update["mode_context"]["imagenes_delivery_outcome"]
    assert outcome["status"] == "partial_success"
    assert outcome["transport_error"] == "timeout"
    assert state_update["mode_context"]["imagenes_enviadas"] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_persist_image_delivery_outcome_skips_non_presupuesto_scope() -> None:
    pytest.importorskip("phonenumbers")
    from agent.main import _persist_image_delivery_outcome
    from unittest.mock import AsyncMock

    graph = AsyncMock()
    await _persist_image_delivery_outcome(
        graph=graph,
        config={"configurable": {"thread_id": "conv-99", "checkpoint_ns": "conversation"}},
        delivery_contract={"delivery_scope": "consulta", "delivery_request_id": "req-99"},
        attempted_count=1,
        sent_count=1,
        transport_error=None,
    )

    graph.aupdate_state.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4.2 — Idempotency helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_image_url_hash_deterministic() -> None:
    """_image_url_hash must return the same value for same URL."""
    pytest.importorskip("phonenumbers")
    from agent.main import _image_url_hash

    url = "https://example.com/placa.jpg"
    h1 = _image_url_hash(url)
    h2 = _image_url_hash(url)
    assert h1 == h2
    assert len(h1) == 16  # SHA-256 hex[:16]


@pytest.mark.unit
def test_image_url_hash_different_urls() -> None:
    """Different URLs must produce different hashes."""
    pytest.importorskip("phonenumbers")
    from agent.main import _image_url_hash

    h1 = _image_url_hash("https://example.com/placa.jpg")
    h2 = _image_url_hash("https://example.com/toldo.jpg")
    assert h1 != h2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_request_idempotency_check_and_mark() -> None:
    """Round-trip: check → miss → mark → check → hit."""
    pytest.importorskip("phonenumbers")
    from agent.main import (
        _check_request_idempotency,
        _mark_request_processed,
    )
    from unittest.mock import AsyncMock

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=[None, b"1"])  # first miss, then hit

    is_dup_before = await _check_request_idempotency(redis, "conv-1", "req-a")
    assert is_dup_before is False

    await _mark_request_processed(redis, "conv-1", "req-a")
    redis.set.assert_called_once()

    is_dup_after = await _check_request_idempotency(redis, "conv-1", "req-a")
    assert is_dup_after is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_image_level_dedup_check_and_mark() -> None:
    """Image-level: check → miss → mark → check → hit."""
    pytest.importorskip("phonenumbers")
    from agent.main import (
        _check_image_already_sent,
        _mark_image_sent,
    )
    from unittest.mock import AsyncMock

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=[None, b"1"])

    is_dup_before = await _check_image_already_sent(redis, "conv-1", "https://img.com/a.jpg")
    assert is_dup_before is False

    await _mark_image_sent(redis, "conv-1", "https://img.com/a.jpg")
    redis.set.assert_called_once()

    is_dup_after = await _check_image_already_sent(redis, "conv-1", "https://img.com/a.jpg")
    assert is_dup_after is True


# ---------------------------------------------------------------------------
# 4.3 — Bounded retry + reconciliation via _send_images_with_idempotency_and_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_with_retry_full_success() -> None:
    """All images sent on first attempt — no retries needed."""
    pytest.importorskip("phonenumbers")
    from agent.main import _send_images_with_idempotency_and_retry
    from unittest.mock import AsyncMock, MagicMock

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # No dedup hits
    redis.set = AsyncMock()

    chatwoot = MagicMock()
    chatwoot.send_image = AsyncMock(return_value=True)
    chatwoot.image_send_delay_seconds = 0

    sent, error = await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg", "https://img.com/b.jpg"],
        image_captions=["Cap A", None],
        delivery_contract={"delivery_request_id": "req-1"},
    )

    assert sent == 2
    assert error is None
    assert chatwoot.send_image.call_count == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_request_level_dedup_skip() -> None:
    """If request already processed, return full count immediately."""
    pytest.importorskip("phonenumbers")
    from agent.main import _send_images_with_idempotency_and_retry
    from unittest.mock import AsyncMock, MagicMock

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"1")  # Request already processed

    chatwoot = MagicMock()
    chatwoot.send_image = AsyncMock()

    sent, error = await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg"],
        image_captions=[None],
        delivery_contract={"delivery_request_id": "req-dup"},
    )

    assert sent == 1
    assert error is None
    chatwoot.send_image.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_retry_recovers_failed_subset() -> None:
    """First attempt: img 0 ok, img 1 fails. Retry: img 1 succeeds."""
    pytest.importorskip("phonenumbers")
    from agent.main import _send_images_with_idempotency_and_retry
    from unittest.mock import AsyncMock, MagicMock

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # No dedup
    redis.set = AsyncMock()

    # send_image: first call ok, second fails, third (retry) ok
    chatwoot = MagicMock()
    chatwoot.send_image = AsyncMock(side_effect=[True, False, True])
    chatwoot.image_send_delay_seconds = 0

    sent, error = await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg", "https://img.com/b.jpg"],
        image_captions=[None, None],
        delivery_contract={"delivery_request_id": "req-retry"},
    )

    assert sent == 2
    # 3 send_image calls total (2 initial + 1 retry for img 1)
    assert chatwoot.send_image.call_count == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_retry_exhausted_partial() -> None:
    """Image 1 fails all retries → partial_success with 1 sent."""
    pytest.importorskip("phonenumbers")
    from agent.main import (
        _send_images_with_idempotency_and_retry,
        IMAGE_DELIVERY_MAX_RETRIES,
    )
    from unittest.mock import AsyncMock, MagicMock

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    # img 0 always succeeds, img 1 always fails
    call_count = 0

    async def mock_send_image(conversation_id, image_url, caption=None):
        nonlocal call_count
        call_count += 1
        return "a.jpg" in image_url  # Only a.jpg succeeds

    chatwoot = MagicMock()
    chatwoot.send_image = mock_send_image
    chatwoot.image_send_delay_seconds = 0

    sent, error = await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg", "https://img.com/b.jpg"],
        image_captions=[None, None],
        delivery_contract={"delivery_request_id": "req-fail"},
    )

    assert sent == 1
    assert error is not None
    # 1 + (1 + MAX_RETRIES) = 1 call for a.jpg (first attempt) + (1+MAX_RETRIES) for b.jpg
    expected_calls = 1 + (1 + IMAGE_DELIVERY_MAX_RETRIES)
    assert call_count == expected_calls


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_image_level_dedup_skips_already_sent() -> None:
    """If an image is already marked sent in Redis, skip it without calling Chatwoot."""
    pytest.importorskip("phonenumbers")
    from agent.main import _send_images_with_idempotency_and_retry, _image_url_hash
    from shared.redis_keys import RedisKeys
    from unittest.mock import AsyncMock, MagicMock

    # img_delivery:req:<conv>:<req> → None (not dup)
    # img_delivery:img:<conv>:<hash_a> → b"1" (already sent)
    # img_delivery:img:<conv>:<hash_b> → None (not sent)
    request_key = RedisKeys.image_delivery_request("conv-42", "req-dedup")
    img_a_key = RedisKeys.image_delivery_image("conv-42", _image_url_hash("https://img.com/a.jpg"))
    img_b_key = RedisKeys.image_delivery_image("conv-42", _image_url_hash("https://img.com/b.jpg"))

    async def mock_redis_get(key):
        if key == request_key:
            return None
        if key == img_a_key:
            return b"1"  # Already sent
        return None

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=mock_redis_get)
    redis.set = AsyncMock()

    chatwoot = MagicMock()
    chatwoot.send_image = AsyncMock(return_value=True)
    chatwoot.image_send_delay_seconds = 0

    sent, error = await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg", "https://img.com/b.jpg"],
        image_captions=[None, None],
        delivery_contract={"delivery_request_id": "req-dedup"},
    )

    assert sent == 2  # Both counted (one from dedup, one sent)
    assert error is None
    # Only img B should have been sent via Chatwoot
    chatwoot.send_image.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_images_stores_audit_outcome() -> None:
    """After delivery, outcome is stored in Redis for audit."""
    pytest.importorskip("phonenumbers")
    from agent.main import _send_images_with_idempotency_and_retry
    from shared.redis_keys import RedisKeys, RedisKeyTTL
    from unittest.mock import AsyncMock, MagicMock
    import json

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    chatwoot = MagicMock()
    chatwoot.send_image = AsyncMock(return_value=True)
    chatwoot.image_send_delay_seconds = 0

    await _send_images_with_idempotency_and_retry(
        chatwoot=chatwoot,
        redis_client=redis,
        chatwoot_conv_id=42,
        conversation_id="conv-42",
        image_urls=["https://img.com/a.jpg"],
        image_captions=[None],
        delivery_contract={"delivery_request_id": "req-audit"},
    )

    # Find the audit call among redis.set calls
    outcome_key = RedisKeys.image_delivery_outcome("conv-42", "req-audit")
    audit_calls = [
        c for c in redis.set.call_args_list
        if c.args[0] == outcome_key or (c.kwargs and c.kwargs.get("name") == outcome_key)
    ]
    assert len(audit_calls) >= 1
    # Parse the stored JSON
    stored_json = audit_calls[0].args[1] if len(audit_calls[0].args) > 1 else audit_calls[0].kwargs["value"]
    stored = json.loads(stored_json)
    assert stored["outcome"] == "full_success"
    assert stored["sent"] == 1
    assert stored["failed"] == 0


# ---------------------------------------------------------------------------
# 5.1 — User-facing fallback messages
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fallback_message_full_success_is_none() -> None:
    """full_success needs no fallback message."""
    pytest.importorskip("phonenumbers")
    from agent.main import build_image_delivery_fallback_message

    msg = build_image_delivery_fallback_message(
        "full_success", sent_count=3, failed_count=0, total_requested=3,
    )
    assert msg is None


@pytest.mark.unit
def test_fallback_message_partial_success_in_spanish() -> None:
    """partial_success returns a Spanish message mentioning counts."""
    pytest.importorskip("phonenumbers")
    from agent.main import build_image_delivery_fallback_message

    msg = build_image_delivery_fallback_message(
        "partial_success", sent_count=2, failed_count=1, total_requested=3,
    )
    assert msg is not None
    assert "2 de 3" in msg
    assert "enviarte" in msg.lower() or "podido" in msg.lower()
    # Must be in Spanish
    assert "could not" not in msg.lower()
    assert "failed" not in msg.lower()


@pytest.mark.unit
def test_fallback_message_failure_no_claim_sent() -> None:
    """failure message must NOT claim images were sent."""
    pytest.importorskip("phonenumbers")
    from agent.main import build_image_delivery_fallback_message

    msg = build_image_delivery_fallback_message(
        "failure", sent_count=0, failed_count=3, total_requested=3,
    )
    assert msg is not None
    # Must not claim images were sent
    assert "enviad" not in msg.lower() or "no he podido" in msg.lower()
    # Must offer alternatives
    assert "intento de nuevo" in msg.lower() or "texto" in msg.lower()
    # Must be in Spanish
    assert "could not" not in msg.lower()


@pytest.mark.unit
def test_fallback_message_partial_singular() -> None:
    """partial_success with 1 missing image uses singular grammar."""
    pytest.importorskip("phonenumbers")
    from agent.main import build_image_delivery_fallback_message

    msg = build_image_delivery_fallback_message(
        "partial_success", sent_count=1, failed_count=1, total_requested=2,
    )
    assert msg is not None
    assert "1 de 2" in msg
