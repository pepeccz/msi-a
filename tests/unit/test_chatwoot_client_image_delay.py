"""Unit tests for Chatwoot batched image delay behavior."""

import pytest

from shared.chatwoot_client import ChatwootClient
from shared.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Ensure environment changes are reflected in settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_send_images_uses_configured_delay_for_multiple_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It should sleep between consecutive images using configured delay."""
    configured_delay = 1.25
    monkeypatch.setenv("CHATWOOT_IMAGE_SEND_DELAY_SECONDS", str(configured_delay))
    get_settings.cache_clear()

    client = ChatwootClient()

    sleep_calls: list[float] = []

    async def fake_send_image(
        *,
        conversation_id: int,
        image_url: str,
        caption: str | None = None,
    ) -> int:
        _ = (conversation_id, image_url, caption)
        return 123

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(client, "send_image", fake_send_image)
    monkeypatch.setattr("shared.chatwoot_client.asyncio.sleep", fake_sleep)

    sent_count = await client.send_images(
        conversation_id=456,
        image_urls=["https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg"],
    )

    assert sent_count == 3
    assert sleep_calls == [configured_delay, configured_delay]


@pytest.mark.asyncio
async def test_send_images_skips_delay_for_single_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It should not sleep when sending only one image."""
    monkeypatch.setenv("CHATWOOT_IMAGE_SEND_DELAY_SECONDS", "2.0")
    get_settings.cache_clear()

    client = ChatwootClient()

    sleep_calls: list[float] = []

    async def fake_send_image(
        *,
        conversation_id: int,
        image_url: str,
        caption: str | None = None,
    ) -> int:
        _ = (conversation_id, image_url, caption)
        return 123

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(client, "send_image", fake_send_image)
    monkeypatch.setattr("shared.chatwoot_client.asyncio.sleep", fake_sleep)

    sent_count = await client.send_images(
        conversation_id=456,
        image_urls=["https://img/1.jpg"],
    )

    assert sent_count == 1
    assert sleep_calls == []
