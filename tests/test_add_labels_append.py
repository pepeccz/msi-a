"""
Tests for ChatwootClient.add_labels() — Bug 3: label append behaviour.

Fix: add_labels() now does GET + set-union + POST instead of replacing
all labels. An idempotency guard skips the POST when nothing changed.

Scenarios covered:
  1. Existing labels present — new label is merged (POST contains both)
  2. Label already present — idempotency guard fires, POST is skipped
  3. No existing labels — new label POSTed correctly
  4. Chatwoot GET returns 500 — HTTPError is re-raised
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> Any:
    """Return a ChatwootClient with mocked settings so no real env is needed."""
    with patch("shared.chatwoot_client.get_settings") as mock_settings, \
         patch("shared.errors.get_error_logger") as mock_error_logger:

        settings = MagicMock()
        settings.CHATWOOT_API_URL = "https://chatwoot.example.com"
        settings.CHATWOOT_API_TOKEN = "test-token"
        settings.CHATWOOT_ACCOUNT_ID = "1"
        settings.CHATWOOT_INBOX_ID = "1"
        settings.CHATWOOT_IMAGE_SEND_DELAY_SECONDS = 0
        mock_settings.return_value = settings

        mock_error_logger.return_value = MagicMock()

        from shared.chatwoot_client import ChatwootClient
        return ChatwootClient()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestAddLabelsAppend:
    """Bug 3 — add_labels() must append rather than replace existing labels."""

    # ------------------------------------------------------------------
    # Scenario 1: Conversation already has labels — new label is merged
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_existing_labels_are_preserved_when_adding_new(self):
        """
        GIVEN conversation has labels ["escalado"]
        WHEN  add_labels(["expediente-pendiente"]) is called
        THEN  POST body contains ["escalado", "expediente-pendiente"] (both)
        """
        client = _make_client()

        # Patch get_conversation to return existing labels
        async def mock_get_conversation(conversation_id: int):
            return {"labels": ["escalado"], "id": conversation_id}

        # Capture what is POSTed
        posted_labels: list[str] = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        async def mock_post(url, json=None, headers=None, timeout=None):
            if json and "labels" in json:
                posted_labels.extend(json["labels"])
            return mock_response

        mock_http_client.post = mock_post

        with patch.object(client, "get_conversation", side_effect=mock_get_conversation), \
             patch("shared.chatwoot_client.httpx.AsyncClient", return_value=mock_http_client):

            result = await client.add_labels(
                conversation_id=42,
                labels=["expediente-pendiente"],
            )

        assert result is True
        assert set(posted_labels) == {"escalado", "expediente-pendiente"}, (
            f"Expected both labels in POST, got: {posted_labels}"
        )

    # ------------------------------------------------------------------
    # Scenario 2: Label already present — idempotency guard skips POST
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_idempotency_guard_skips_post_when_label_already_present(self):
        """
        GIVEN conversation already has labels ["a", "b"]
        WHEN  add_labels(["a"]) is called  (label already present)
        THEN  POST is NOT made, and True is returned
        """
        client = _make_client()

        async def mock_get_conversation(conversation_id: int):
            return {"labels": ["a", "b"], "id": conversation_id}

        post_called = False
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        async def mock_post(*args, **kwargs):
            nonlocal post_called
            post_called = True
            return MagicMock()

        mock_http_client.post = mock_post

        with patch.object(client, "get_conversation", side_effect=mock_get_conversation), \
             patch("shared.chatwoot_client.httpx.AsyncClient", return_value=mock_http_client):

            result = await client.add_labels(
                conversation_id=42,
                labels=["a"],
            )

        assert result is True, "Should return True (already present is success)"
        assert not post_called, "POST should be skipped — idempotency guard"

    # ------------------------------------------------------------------
    # Scenario 3: No existing labels — new label is POSTed alone
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_new_label_posted_when_conversation_has_no_labels(self):
        """
        GIVEN conversation has no labels []
        WHEN  add_labels(["new-label"]) is called
        THEN  POST body contains ["new-label"] exactly
        """
        client = _make_client()

        async def mock_get_conversation(conversation_id: int):
            return {"labels": [], "id": conversation_id}

        posted_body: dict = {}

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        async def mock_post(url, json=None, headers=None, timeout=None):
            if json:
                posted_body.update(json)
            return mock_response

        mock_http_client.post = mock_post

        with patch.object(client, "get_conversation", side_effect=mock_get_conversation), \
             patch("shared.chatwoot_client.httpx.AsyncClient", return_value=mock_http_client):

            result = await client.add_labels(
                conversation_id=42,
                labels=["new-label"],
            )

        assert result is True
        assert "labels" in posted_body
        assert posted_body["labels"] == ["new-label"], (
            f"Expected ['new-label'], got {posted_body['labels']}"
        )

    # ------------------------------------------------------------------
    # Scenario 4: GET returns 500 — HTTPError is re-raised
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_http_error_on_get_is_reraised(self):
        """
        GIVEN Chatwoot API returns 500 on GET
        WHEN  add_labels() is called
        THEN  httpx.HTTPError is raised (after retries)
        """
        client = _make_client()

        # get_conversation raises HTTPError (simulating Chatwoot 500)
        async def mock_get_conversation_error(conversation_id: int):
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

        with patch.object(client, "get_conversation", side_effect=mock_get_conversation_error):
            with pytest.raises(httpx.HTTPError):
                # tenacity will retry 3×; we patch retry to not wait
                await client.add_labels(
                    conversation_id=42,
                    labels=["any-label"],
                )

    # ------------------------------------------------------------------
    # Additional: merging multiple new labels at once
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_multiple_new_labels_merged_with_existing(self):
        """
        GIVEN conversation has labels ["existing"]
        WHEN  add_labels(["new1", "new2"]) is called
        THEN  POST body contains all three labels
        """
        client = _make_client()

        async def mock_get_conversation(conversation_id: int):
            return {"labels": ["existing"], "id": conversation_id}

        posted_labels: list[str] = []

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        async def mock_post(url, json=None, headers=None, timeout=None):
            if json and "labels" in json:
                posted_labels.extend(json["labels"])
            return mock_response

        mock_http_client.post = mock_post

        with patch.object(client, "get_conversation", side_effect=mock_get_conversation), \
             patch("shared.chatwoot_client.httpx.AsyncClient", return_value=mock_http_client):

            result = await client.add_labels(
                conversation_id=42,
                labels=["new1", "new2"],
            )

        assert result is True
        assert set(posted_labels) == {"existing", "new1", "new2"}, (
            f"Expected all three labels in POST, got: {posted_labels}"
        )
