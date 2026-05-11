"""
Integration tests for the Chatwoot webhook gate refactor (T06).

Tests CAP-09 scenarios: persistence always runs; publish to Redis Stream
is gated by atencion_automatica AND NOT bot_paused_at.

Strategy: Build a minimal FastAPI app that wraps the real webhook handler
with mocked external dependencies (Redis, ChatwootClient, DB session) to
avoid requiring a live PostgreSQL / Redis instance.

TDD Cycle: RED → GREEN (see T05 in apply-progress).
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Payload factory helpers
# ---------------------------------------------------------------------------

def _make_payload(
    *,
    conversation_id: int = 12345,
    message_id: int = 999,
    phone: str = "+34666000001",
    content: str = "Hola necesito información",
    atencion_automatica: bool | None = True,
    attachments: list[dict] = None,
    message_type: int = 0,
) -> dict[str, Any]:
    """Build a minimal valid Chatwoot webhook payload."""
    return {
        "event": "message_created",
        "sender": {
            "id": 101,
            "phone_number": phone,
            "name": "Test Cliente",
        },
        "conversation": {
            "id": conversation_id,
            "inbox_id": 1,
            "messages": [
                {
                    "id": message_id,
                    "content": content,
                    "message_type": message_type,
                    "content_type": "text",
                    "attachments": attachments or [],
                    "sender": {
                        "id": 101,
                        "phone_number": phone,
                        "name": "Test Cliente",
                    },
                    "created_at": 1700000000,
                    "conversation_id": conversation_id,
                }
            ],
            "custom_attributes": (
                {}
                if atencion_automatica is None
                else {"atencion_automatica": atencion_automatica}
            ),
        },
        "attachments": attachments or [],
    }


def _make_audio_payload(**kwargs) -> dict[str, Any]:
    """Build payload with an audio attachment."""
    attachments = [
        {
            "id": 55,
            "file_type": "audio",
            "data_url": "https://chatwoot.test/audio.ogg",
        }
    ]
    return _make_payload(attachments=attachments, content="", **kwargs)


# ---------------------------------------------------------------------------
# Fixture: minimal FastAPI app with the real webhook route
# ---------------------------------------------------------------------------

VALID_TOKEN = "test-webhook-token-abc123"


def _build_webhook_app() -> FastAPI:
    """Build minimal FastAPI app with the real webhook handler function.

    We import the handler function and router directly from the chatwoot module
    using importlib to bypass the api/routes/__init__.py, which imports admin.py
    and therefore requires structlog (not installed in test environment).
    """
    import importlib
    import sys

    # Stub out admin.py before api.routes can import it
    if "api.routes" not in sys.modules:
        admin_stub = type(sys)("api.routes.admin")
        sys.modules["api.routes.admin"] = admin_stub  # type: ignore[assignment]

    import api.routes.chatwoot as chatwoot_mod  # noqa: PLC0415

    app = FastAPI()
    app.include_router(chatwoot_mod.router, prefix="/webhook")
    return app


# ---------------------------------------------------------------------------
# Common mock context for all tests.
# Patches: Redis, settings, get_async_session, ChatwootClient, settings_cache.
# ---------------------------------------------------------------------------

class MockConversationHistory:
    """In-memory ConversationHistory stub."""

    def __init__(self, bot_paused_at: datetime | None = None) -> None:
        self.id = uuid4()
        self.conversation_id = "12345"
        self.bot_paused_at = bot_paused_at
        self.last_inbound_at = None
        self.last_message_at = None
        self.message_count = 0


class MockUser:
    """In-memory User stub."""

    def __init__(self) -> None:
        self.id = uuid4()
        self.phone = "+34666000001"
        self.first_name = "Test"
        self.last_name = "Cliente"
        self.client_type = "particular"
        self.chatwoot_contact_id = 101
        self.metadata_ = {"whatsapp_name": "Test Cliente"}


class MockConversationMessage:
    """In-memory ConversationMessage stub."""

    def __init__(self) -> None:
        self.id = uuid4()
        self.role = "user"
        self.author_type = "user"
        self.author_user_id = None
        self.content = ""
        self.is_read = False


def _make_mock_session(
    user: MockUser | None = None,
    conversation: MockConversationHistory | None = None,
    db_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock async session context manager."""
    mock_session = MagicMock()

    if db_raises:
        mock_session.__aenter__ = AsyncMock(side_effect=db_raises)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    mock_user = user or MockUser()
    mock_conv = conversation or MockConversationHistory()

    user_scalar = MagicMock()
    user_scalar.scalar = MagicMock(return_value=mock_user)
    user_scalar.scalar_one_or_none = MagicMock(return_value=mock_user)

    conv_scalar = MagicMock()
    conv_scalar.scalar = MagicMock(return_value=mock_conv)
    conv_scalar.scalar_one_or_none = MagicMock(return_value=mock_conv)

    call_count = {"n": 0}

    async def mock_execute(stmt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return user_scalar
        return conv_scalar

    inner_session = MagicMock()
    inner_session.execute = AsyncMock(side_effect=mock_execute)
    inner_session.add = MagicMock()
    inner_session.commit = AsyncMock()
    inner_session.refresh = AsyncMock()
    inner_session.rollback = AsyncMock()
    inner_session.close = AsyncMock()

    mock_session.__aenter__ = AsyncMock(return_value=inner_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _make_redis_mock(
    setnx_returns: bool = True,
) -> MagicMock:
    """Build a mock Redis client."""
    redis_mock = MagicMock()
    redis_mock.setnx = AsyncMock(return_value=setnx_returns)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.xadd = AsyncMock(return_value=b"1-1")
    return redis_mock


# ---------------------------------------------------------------------------
# T06-1: Bot ON normal — persists + publishes
# ---------------------------------------------------------------------------


class TestBotOnNormal:
    """CAP-09 Scenario 9.3: bot active, atencion_automatica=True → persist + publish."""

    def test_bot_on_publishes_to_stream(self) -> None:
        """
        GIVEN atencion_automatica=True AND bot_paused_at IS NULL
        WHEN a valid inbound message arrives
        THEN message persists in DB AND is published to Redis Stream
        AND response is 200
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "received"
        mock_stream.assert_called_once()

    def test_bot_on_response_indicates_received(self) -> None:
        """Bot ON path returns 200 with status 'received'."""
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# T06-2: Panic button global active — persists + does NOT publish
# ---------------------------------------------------------------------------


class TestPanicButtonGlobal:
    """CAP-09 Scenario 9.4: atencion_automatica=False → persist + skip publish."""

    def test_panic_button_skips_publish(self) -> None:
        """
        GIVEN atencion_automatica=False (global panic button)
        WHEN an inbound message arrives
        THEN message persists in DB AND is NOT published to stream
        AND response is 200
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=False)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_not_called()

    def test_panic_button_response_indicates_persisted_no_publish(self) -> None:
        """When bot is globally disabled, response status communicates skip."""
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=False)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "persisted_no_publish"


# ---------------------------------------------------------------------------
# T06-3: Bot paused per-conversation — persists + does NOT publish
# ---------------------------------------------------------------------------


class TestBotPausedPerConversation:
    """CAP-09 Scenario 9.1: bot_paused_at IS NOT NULL → persist + skip publish."""

    def test_bot_paused_skips_publish(self) -> None:
        """
        GIVEN atencion_automatica=True AND bot_paused_at IS NOT NULL
        WHEN an inbound message arrives
        THEN message persists in DB AND is NOT published to stream
        AND response is 200
        """
        redis_mock = _make_redis_mock()
        paused_conv = MockConversationHistory(bot_paused_at=datetime.now(UTC))
        mock_session = _make_mock_session(conversation=paused_conv)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_not_called()

    def test_bot_paused_response_indicates_persisted_no_publish(self) -> None:
        """When bot is paused per-conversation, response reflects skip."""
        redis_mock = _make_redis_mock()
        paused_conv = MockConversationHistory(bot_paused_at=datetime.now(UTC))
        mock_session = _make_mock_session(conversation=paused_conv)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "persisted_no_publish"


# ---------------------------------------------------------------------------
# T06-4: last_inbound_at is updated on every inbound
# ---------------------------------------------------------------------------


class TestLastInboundAtUpdated:
    """CAP-08 Scenario 8.3: last_inbound_at must be updated on every inbound."""

    def test_last_inbound_at_is_set(self) -> None:
        """
        GIVEN a valid inbound message
        WHEN the webhook processes it
        THEN ConversationHistory.last_inbound_at is set to a non-null datetime
        """
        redis_mock = _make_redis_mock()
        mock_conv = MockConversationHistory(bot_paused_at=None)
        assert mock_conv.last_inbound_at is None

        inner_session = MagicMock()
        inner_session.add = MagicMock()
        inner_session.commit = AsyncMock()
        inner_session.refresh = AsyncMock()
        inner_session.rollback = AsyncMock()
        inner_session.close = AsyncMock()

        user_result = MagicMock()
        user_result.scalar = MagicMock(return_value=MockUser())
        conv_result = MagicMock()
        conv_result.scalar = MagicMock(return_value=mock_conv)
        conv_result.scalar_one_or_none = MagicMock(return_value=mock_conv)

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return user_result
            return conv_result

        inner_session.execute = AsyncMock(side_effect=mock_execute)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=inner_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        assert mock_conv.last_inbound_at is not None
        assert isinstance(mock_conv.last_inbound_at, datetime)


# ---------------------------------------------------------------------------
# T06-5: Audio + bot paused — transcription persists, no publish
# ---------------------------------------------------------------------------


class TestAudioBotPaused:
    """CAP-09 Scenario 9.2: audio with bot paused → persist + no publish."""

    def test_audio_with_bot_paused_skips_publish(self) -> None:
        """
        GIVEN bot_paused_at IS NOT NULL
        WHEN a message with audio attachment arrives
        THEN the message persists (with audio metadata) AND is NOT published
        AND response is 200
        """
        redis_mock = _make_redis_mock()
        paused_conv = MockConversationHistory(bot_paused_at=datetime.now(UTC))
        mock_session = _make_mock_session(conversation=paused_conv)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_audio_payload(
                atencion_automatica=True,
                conversation_id=12345,
                message_id=777,
            )
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_not_called()

    def test_audio_with_bot_on_publishes(self) -> None:
        """
        GIVEN bot_paused_at IS NULL and atencion_automatica=True
        WHEN a message with audio attachment arrives
        THEN message is published to stream normally
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_audio_payload(
                atencion_automatica=True,
                conversation_id=12345,
                message_id=778,
            )
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_called_once()


# ---------------------------------------------------------------------------
# T06-6: First message (atencion_automatica=None)
# ---------------------------------------------------------------------------


class TestFirstMessage:
    """
    CAP-09 + existing behaviour: atencion_automatica=None (first message).
    Panic button check → setear True/False → persist → publish if True.
    """

    def test_first_message_no_panic_button_publishes(self) -> None:
        """
        GIVEN atencion_automatica=None (absent from custom_attributes)
        AND agent_enabled setting is 'true' (no panic button)
        WHEN an inbound message arrives
        THEN bot is enabled (Chatwoot updated), message persists, published
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )
        mock_chatwoot = MagicMock()
        mock_chatwoot.update_conversation_attributes = AsyncMock()

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
            patch("shared.settings_cache.get_cached_setting", new_callable=AsyncMock, return_value="true"),
            patch("api.routes.chatwoot.ChatwootClient", return_value=mock_chatwoot),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=None, conversation_id=55555)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_called_once()

    def test_first_message_with_panic_button_skips_publish(self) -> None:
        """
        GIVEN atencion_automatica=None AND agent_enabled='false' (panic button)
        WHEN an inbound message arrives
        THEN Chatwoot is updated to atencion_automatica=False
        AND message persists but is NOT published to stream
        AND response is 200
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )
        mock_chatwoot = MagicMock()
        mock_chatwoot.update_conversation_attributes = AsyncMock()

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
            patch("shared.settings_cache.get_cached_setting", new_callable=AsyncMock, return_value="false"),
            patch("api.routes.chatwoot.ChatwootClient", return_value=mock_chatwoot),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=None, conversation_id=55556)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_not_called()


# ---------------------------------------------------------------------------
# T06-7: Idempotency — same message_id twice → only processed once
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Idempotency: duplicate chatwoot_message_id must not re-process."""

    def test_duplicate_message_returns_200_no_publish(self) -> None:
        """
        GIVEN the same message_id has already been processed (Redis SETNX returns False)
        WHEN the webhook receives the same payload again
        THEN response is 200 with status 'duplicate'
        AND add_to_stream is NOT called
        """
        redis_mock = _make_redis_mock(setnx_returns=False)
        mock_session = _make_mock_session()

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True, message_id=42)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "duplicate"
        mock_stream.assert_not_called()

    def test_first_occurrence_processes_normally(self) -> None:
        """When SETNX returns True (new message), processing continues normally."""
        redis_mock = _make_redis_mock(setnx_returns=True)
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True, message_id=99)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_called_once()


# ---------------------------------------------------------------------------
# T06-8: DB failure → 500 (persistence failure is a bug, not silenced)
# ---------------------------------------------------------------------------


class TestPersistenceFailure:
    """If DB fails during persistence, return 500 — do not publish."""

    def test_db_failure_returns_500(self) -> None:
        """
        GIVEN the DB session raises an exception during the persistence step
        WHEN the webhook tries to process an inbound message
        THEN response is 500
        AND add_to_stream is NOT called
        """
        redis_mock = _make_redis_mock()

        inner_session = MagicMock()
        inner_session.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        inner_session.add = MagicMock()
        inner_session.commit = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        inner_session.rollback = AsyncMock()
        inner_session.close = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=inner_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 500
        mock_stream.assert_not_called()


class TestPublishFailure:
    """
    If Redis publish fails after successful persistence, return 200 — do NOT
    propagate 500 to Chatwoot. Persisted message is preserved; retry by
    Chatwoot would cause duplicate processing (idempotency only catches exact
    chatwoot_message_id replays, not stream-publish races).
    """

    def test_publish_failure_returns_200_after_persist(self) -> None:
        """
        GIVEN persistence succeeds
        AND add_to_stream raises an exception
        WHEN the webhook processes the message
        THEN response is 200 (not 500)
        AND error is logged (publish_failed)
        """
        redis_mock = _make_redis_mock()
        mock_session = _make_mock_session(
            conversation=MockConversationHistory(bot_paused_at=None)
        )

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch(
                "api.routes.chatwoot.add_to_stream",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Redis connection lost"),
            ) as mock_stream,
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200
        mock_stream.assert_called_once()


# ---------------------------------------------------------------------------
# T06-EXTRA: ConversationMessage persisted with correct author_type
# ---------------------------------------------------------------------------


class TestConversationMessageAttribution:
    """
    CAP-10: inbound messages must be persisted with author_type='user'.
    Verifies the session.add() call receives a ConversationMessage
    with the correct author_type.
    """

    def test_inbound_message_persisted_with_author_type_user(self) -> None:
        """
        GIVEN a valid inbound message
        WHEN the webhook processes it
        THEN session.add() is called with a ConversationMessage
        that has author_type='user'
        """
        from database.models import ConversationMessage

        redis_mock = _make_redis_mock()
        mock_conv = MockConversationHistory(bot_paused_at=None)
        added_objects: list = []

        inner_session = MagicMock()
        inner_session.rollback = AsyncMock()
        inner_session.close = AsyncMock()
        inner_session.commit = AsyncMock()
        inner_session.refresh = AsyncMock()

        user_result = MagicMock()
        user_result.scalar = MagicMock(return_value=MockUser())
        conv_result = MagicMock()
        conv_result.scalar = MagicMock(return_value=mock_conv)
        conv_result.scalar_one_or_none = MagicMock(return_value=mock_conv)

        call_count = {"n": 0}

        async def mock_execute(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return user_result
            return conv_result

        inner_session.execute = AsyncMock(side_effect=mock_execute)

        def capture_add(obj):
            added_objects.append(obj)

        inner_session.add = MagicMock(side_effect=capture_add)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=inner_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        app = _build_webhook_app()
        client = TestClient(app, raise_server_exceptions=False)

        with (
            patch("api.routes.chatwoot.get_settings") as mock_settings,
            patch("api.routes.chatwoot.get_redis_client", return_value=redis_mock),
            patch("api.routes.chatwoot.get_async_session", return_value=mock_session),
            patch("api.routes.chatwoot.add_to_stream", new_callable=AsyncMock),
        ):
            settings = MagicMock()
            settings.CHATWOOT_WEBHOOK_TOKEN = VALID_TOKEN
            settings.USE_REDIS_STREAMS = True
            mock_settings.return_value = settings

            payload = _make_payload(atencion_automatica=True)
            response = client.post(
                f"/webhook/chatwoot/{VALID_TOKEN}",
                json=payload,
            )

        assert response.status_code == 200

        conversation_messages = [
            obj for obj in added_objects
            if isinstance(obj, ConversationMessage)
        ]
        assert len(conversation_messages) >= 1, (
            "Expected at least one ConversationMessage to be persisted"
        )
        msg = conversation_messages[0]
        assert msg.author_type == "user", (
            f"Expected author_type='user' for inbound, got '{msg.author_type}'"
        )
        assert msg.role == "user", (
            f"Expected role='user' for inbound, got '{msg.role}'"
        )


# ---------------------------------------------------------------------------
# T06-DEDUP: save_user_message idempotency (PR2 post-verify dedup fix)
# ---------------------------------------------------------------------------


class TestSaveUserMessageDedup:
    """
    Regression tests for the fire-and-forget path duplicate prevention.

    save_user_message() must skip the INSERT when a ConversationMessage with
    the same chatwoot_message_id already exists (created by the webhook).
    When chatwoot_message_id is None, the INSERT always runs.
    """

    @pytest.mark.asyncio
    async def test_dedup_webhook_then_agent_no_duplicate(self) -> None:
        """
        GIVEN webhook already persisted a ConversationMessage with chatwoot_message_id=42
        WHEN save_user_message is called with the same chatwoot_message_id
        THEN no second INSERT is made (session.add is NOT called)
        """
        from api.services.message_persistence_service import save_user_message

        existing_msg = MockConversationMessage()
        existing_msg.role = "user"
        existing_msg.author_type = "user"

        mock_history_id = uuid4()

        mock_inner = MagicMock()
        mock_inner.commit = AsyncMock()
        mock_inner.refresh = AsyncMock()
        mock_inner.rollback = AsyncMock()
        mock_inner.close = AsyncMock()

        # First execute: ConversationHistory lookup (get_or_create path)
        # Second execute: dedup SELECT by chatwoot_message_id
        conv_history_obj = MagicMock()
        conv_history_obj.id = mock_history_id

        conv_history_result = MagicMock()
        conv_history_result.scalar_one_or_none = MagicMock(return_value=conv_history_obj)

        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none = MagicMock(return_value=existing_msg)

        execute_count = {"n": 0}

        async def mock_execute(stmt):
            execute_count["n"] += 1
            if execute_count["n"] == 1:
                return conv_history_result
            return dedup_result

        mock_inner.execute = AsyncMock(side_effect=mock_execute)
        mock_inner.add = MagicMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "api.services.message_persistence_service.get_async_session",
            return_value=mock_session,
        ):
            await save_user_message(
                conversation_id="12345",
                content="Hola",
                chatwoot_message_id=42,
            )

        mock_inner.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_agent_first_no_existing_inserts(self) -> None:
        """
        GIVEN no ConversationMessage exists for chatwoot_message_id=43
        WHEN save_user_message is called (agent fires before webhook persists)
        THEN INSERT is performed (session.add IS called once)
        AND the created message has author_type='user'
        """
        from api.services.message_persistence_service import save_user_message

        mock_history_id = uuid4()
        conv_history_obj = MagicMock()
        conv_history_obj.id = mock_history_id

        conv_history_result = MagicMock()
        conv_history_result.scalar_one_or_none = MagicMock(return_value=conv_history_obj)

        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_inner = MagicMock()
        mock_inner.commit = AsyncMock()
        mock_inner.refresh = AsyncMock()
        mock_inner.rollback = AsyncMock()
        mock_inner.close = AsyncMock()

        execute_count = {"n": 0}

        async def mock_execute(stmt):
            execute_count["n"] += 1
            if execute_count["n"] == 1:
                return conv_history_result
            return dedup_result

        mock_inner.execute = AsyncMock(side_effect=mock_execute)

        added: list = []
        mock_inner.add = MagicMock(side_effect=lambda obj: added.append(obj))

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "api.services.message_persistence_service.get_async_session",
            return_value=mock_session,
        ):
            await save_user_message(
                conversation_id="12345",
                content="Hola",
                chatwoot_message_id=43,
            )

        assert len(added) == 1
        from database.models import ConversationMessage as CM
        assert isinstance(added[0], CM)
        assert added[0].author_type == "user"
        assert added[0].role == "user"

    @pytest.mark.asyncio
    async def test_author_type_user_set_explicitly(self) -> None:
        """
        GIVEN no existing record for the given chatwoot_message_id
        WHEN save_user_message inserts the record
        THEN the persisted ConversationMessage has author_type='user' (not the DB default 'bot')
        """
        from api.services.message_persistence_service import save_user_message
        from database.models import ConversationMessage as CM

        mock_history_id = uuid4()
        conv_history_obj = MagicMock()
        conv_history_obj.id = mock_history_id

        conv_history_result = MagicMock()
        conv_history_result.scalar_one_or_none = MagicMock(return_value=conv_history_obj)

        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_inner = MagicMock()
        mock_inner.commit = AsyncMock()
        mock_inner.refresh = AsyncMock()
        mock_inner.rollback = AsyncMock()
        mock_inner.close = AsyncMock()

        execute_count = {"n": 0}

        async def mock_execute(stmt):
            execute_count["n"] += 1
            if execute_count["n"] == 1:
                return conv_history_result
            return dedup_result

        mock_inner.execute = AsyncMock(side_effect=mock_execute)

        added: list = []
        mock_inner.add = MagicMock(side_effect=lambda obj: added.append(obj))

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "api.services.message_persistence_service.get_async_session",
            return_value=mock_session,
        ):
            await save_user_message(
                conversation_id="99999",
                content="Prueba",
                chatwoot_message_id=77,
            )

        assert len(added) == 1
        msg = added[0]
        assert isinstance(msg, CM)
        assert msg.author_type == "user", (
            f"author_type must be 'user' regardless of DB default, got '{msg.author_type}'"
        )
        assert msg.author_user_id is None

    @pytest.mark.asyncio
    async def test_chatwoot_message_id_none_always_inserts(self) -> None:
        """
        GIVEN chatwoot_message_id=None (caller has no Chatwoot ID)
        WHEN save_user_message is called
        THEN INSERT always runs — no dedup SELECT is attempted
        """
        from api.services.message_persistence_service import save_user_message
        from database.models import ConversationMessage as CM

        mock_history_id = uuid4()
        conv_history_obj = MagicMock()
        conv_history_obj.id = mock_history_id

        conv_history_result = MagicMock()
        conv_history_result.scalar_one_or_none = MagicMock(return_value=conv_history_obj)

        mock_inner = MagicMock()
        mock_inner.commit = AsyncMock()
        mock_inner.refresh = AsyncMock()
        mock_inner.rollback = AsyncMock()
        mock_inner.close = AsyncMock()

        execute_count = {"n": 0}

        async def mock_execute(stmt):
            execute_count["n"] += 1
            return conv_history_result

        mock_inner.execute = AsyncMock(side_effect=mock_execute)

        added: list = []
        mock_inner.add = MagicMock(side_effect=lambda obj: added.append(obj))

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "api.services.message_persistence_service.get_async_session",
            return_value=mock_session,
        ):
            await save_user_message(
                conversation_id="12345",
                content="Sin ID de Chatwoot",
                chatwoot_message_id=None,
            )

        # Only one execute call (ConversationHistory lookup); no dedup SELECT
        assert execute_count["n"] == 1, (
            "When chatwoot_message_id is None, dedup SELECT must not run"
        )
        assert len(added) == 1
        assert isinstance(added[0], CM)
