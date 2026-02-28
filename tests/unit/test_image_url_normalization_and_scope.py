"""Tests for image URL normalization and presupuesto scope guardrails.

Covers:
- Task 3.2: ``ChatwootClient.normalize_image_url`` with /images/, /case-images/,
  /datos/Imagenes/ paths, absolute URLs, and invalid relative paths.
- Task 3.3: Scope guardrails for mixed presupuesto scope and stale budget
  rejection via ``enviar_imagenes_ejemplo``.
"""

from unittest.mock import patch

import pytest

from shared.chatwoot_client import ChatwootClient


# ---------------------------------------------------------------------------
# 3.2 — URL normalization unit tests
# ---------------------------------------------------------------------------

class TestNormalizeImageUrl:
    """Tests for ChatwootClient.normalize_image_url (static method)."""

    @patch("shared.chatwoot_client.get_settings")
    def test_images_prefix_normalized(self, mock_settings) -> None:
        mock_settings.return_value.API_BASE_URL = "http://api:8000"
        result = ChatwootClient.normalize_image_url("/images/abc-123.png")
        assert result == "http://api:8000/images/abc-123.png"

    @patch("shared.chatwoot_client.get_settings")
    def test_case_images_prefix_normalized(self, mock_settings) -> None:
        mock_settings.return_value.API_BASE_URL = "http://api:8000"
        result = ChatwootClient.normalize_image_url("/case-images/foto.jpg")
        assert result == "http://api:8000/case-images/foto.jpg"

    @patch("shared.chatwoot_client.get_settings")
    def test_datos_imagenes_prefix_normalized(self, mock_settings) -> None:
        mock_settings.return_value.API_BASE_URL = "http://api:8000"
        result = ChatwootClient.normalize_image_url(
            "/datos/Imagenes/Autocaravanas/03_Placas_Solares/placas_solarres.png"
        )
        assert result == (
            "http://api:8000/datos/Imagenes/Autocaravanas/03_Placas_Solares/placas_solarres.png"
        )

    @patch("shared.chatwoot_client.get_settings")
    def test_datos_imagenes_motos_path(self, mock_settings) -> None:
        """Motos paths with accented directory names must be preserved."""
        mock_settings.return_value.API_BASE_URL = "https://prod.example.com"
        url = "/datos/Imagenes/Motos/05_Suspensión/suspension_delantera.png"
        result = ChatwootClient.normalize_image_url(url)
        assert result == f"https://prod.example.com{url}"

    @patch("shared.chatwoot_client.get_settings")
    def test_trailing_slash_stripped_from_base(self, mock_settings) -> None:
        """API_BASE_URL with trailing slash should not produce double-slash."""
        mock_settings.return_value.API_BASE_URL = "http://api:8000/"
        result = ChatwootClient.normalize_image_url("/images/test.png")
        assert result == "http://api:8000/images/test.png"

    def test_absolute_http_url_unchanged(self) -> None:
        url = "http://storage.example.com/img.png"
        assert ChatwootClient.normalize_image_url(url) == url

    def test_absolute_https_url_unchanged(self) -> None:
        url = "https://cdn.chatwoot.com/attachments/photo.jpg"
        assert ChatwootClient.normalize_image_url(url) == url

    def test_invalid_relative_path_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("/unknown/path/img.png")

    def test_slash_only_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("/")

    def test_datos_wrong_case_raises(self) -> None:
        """Only /datos/Imagenes/ is supported (case-sensitive)."""
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("/datos/imagenes/file.png")

    def test_uploads_path_raises(self) -> None:
        """Arbitrary relative paths like /uploads/ should be rejected."""
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("/uploads/secret.txt")

    def test_empty_string_raises(self) -> None:
        """Empty string is not a valid URL."""
        # Empty string doesn't start with http or any prefix, so → ValueError
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("")


# ---------------------------------------------------------------------------
# 3.3 — Scope guardrail tests
# ---------------------------------------------------------------------------

class TestPresupuestoScopeGuardrails:
    """Integration tests for presupuesto scope guardrails in enviar_imagenes_ejemplo."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_mixed_scope_blocks_stale_budget(self) -> None:
        """When element_codes differ from tarifa element_codes, sending is rejected."""
        from agent.tools.image_tools import (
            clear_image_tools_state,
            enviar_imagenes_ejemplo,
            set_current_state_for_image_tools,
        )

        state = {
            "conversation_id": "99",
            "mode_context": {
                "precio_comunicado": True,
                "element_codes": ["TOLDO", "PLACA_SOLAR"],
                "tarifa_calculada": {
                    "datos": {"element_codes": ["PLACA_SOLAR"]},
                    "imagenes_ejemplo": [
                        {"url": "/datos/Imagenes/Autocaravanas/03_Placas_Solares/placas_solarres.png", "status": "active", "descripcion": "Placa"}
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
        assert "recalcula" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_matching_scope_allows_sending(self) -> None:
        """When element_codes match tarifa element_codes, sending proceeds."""
        from agent.tools.image_tools import (
            clear_image_tools_state,
            enviar_imagenes_ejemplo,
            set_current_state_for_image_tools,
        )

        state = {
            "conversation_id": "100",
            "mode_context": {
                "precio_comunicado": True,
                "element_codes": ["PLACA_SOLAR", "TOLDO"],
                "tarifa_calculada": {
                    "datos": {"element_codes": ["PLACA_SOLAR", "TOLDO"]},
                    "imagenes_ejemplo": [
                        {"url": "/datos/Imagenes/Autocaravanas/03_Placas_Solares/placas_solarres.png", "status": "active", "descripcion": "Placa"},
                        {"url": "/datos/Imagenes/Autocaravanas/04_Toldos/toldo.png", "status": "active", "descripcion": "Toldo"},
                    ],
                },
            },
        }

        set_current_state_for_image_tools(state)
        try:
            result = await enviar_imagenes_ejemplo.ainvoke({"tipo": "presupuesto"})
        finally:
            clear_image_tools_state()

        assert result["success"] is True
        assert result["data"]["images_count"] == 2
        contract = result["_pending_images"]["delivery_contract"]
        assert contract["delivery_scope"] == "presupuesto"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_datos_imagenes_urls_in_delivery_payload(self) -> None:
        """Images with /datos/Imagenes/ URLs are passed through in delivery payload unchanged."""
        from agent.tools.image_tools import (
            clear_image_tools_state,
            enviar_imagenes_ejemplo,
            set_current_state_for_image_tools,
        )

        datos_url = "/datos/Imagenes/Motos/06_Sistema_Frenado/sistemaFrenado_discos.png"
        state = {
            "conversation_id": "200",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {
                    "imagenes_ejemplo": [
                        {"url": datos_url, "status": "active", "descripcion": "Discos freno"},
                    ],
                },
            },
        }

        set_current_state_for_image_tools(state)
        try:
            result = await enviar_imagenes_ejemplo.ainvoke({"tipo": "presupuesto"})
        finally:
            clear_image_tools_state()

        assert result["success"] is True
        images = result["_pending_images"]["images"]
        assert len(images) == 1
        assert images[0]["url"] == datos_url

    @pytest.mark.unit
    def test_normalize_rejects_invalid_url_for_send_image_log(self) -> None:
        """Invalid URLs produce structured error with INVALID_IMAGE_URL code.

        This verifies the caller-side integration: ``send_image`` will call
        ``normalize_image_url`` and return None on ValueError.  We only test
        the static method here (no HTTP calls).
        """
        with pytest.raises(ValueError, match="Unsupported relative image path"):
            ChatwootClient.normalize_image_url("/etc/passwd")


# ---------------------------------------------------------------------------
# 4.1 — Redis idempotency key tests
# ---------------------------------------------------------------------------

class TestImageDeliveryRedisKeys:
    """Tests for image delivery idempotency keys in RedisKeys."""

    def test_request_level_key_format(self) -> None:
        from shared.redis_keys import RedisKeys

        key = RedisKeys.image_delivery_request("conv-42", "req-abc123")
        assert key == "img_delivery:req:conv-42:req-abc123"

    def test_image_level_key_format(self) -> None:
        from shared.redis_keys import RedisKeys

        key = RedisKeys.image_delivery_image("conv-42", "a1b2c3d4e5f6")
        assert key == "img_delivery:img:conv-42:a1b2c3d4e5f6"

    def test_outcome_key_format(self) -> None:
        from shared.redis_keys import RedisKeys

        key = RedisKeys.image_delivery_outcome("conv-42", "req-abc123")
        assert key == "img_delivery:outcome:conv-42:req-abc123"

    def test_pattern_scoped_to_conversation(self) -> None:
        from shared.redis_keys import RedisKeys

        pattern = RedisKeys.image_delivery_pattern("conv-42")
        assert pattern == "img_delivery:*:conv-42:*"

    def test_pattern_global(self) -> None:
        from shared.redis_keys import RedisKeys

        pattern = RedisKeys.image_delivery_pattern()
        assert pattern == "img_delivery:*"

    def test_ttl_values_are_positive(self) -> None:
        from shared.redis_keys import RedisKeyTTL

        assert RedisKeyTTL.IMAGE_DELIVERY_REQUEST > 0
        assert RedisKeyTTL.IMAGE_DELIVERY_IMAGE > 0
        assert RedisKeyTTL.IMAGE_DELIVERY_OUTCOME > 0

    def test_request_ttl_shorter_than_outcome(self) -> None:
        """Outcome should persist longer than request idempotency for audit."""
        from shared.redis_keys import RedisKeyTTL

        assert RedisKeyTTL.IMAGE_DELIVERY_REQUEST <= RedisKeyTTL.IMAGE_DELIVERY_OUTCOME

    def test_keys_are_unique_across_conversations(self) -> None:
        from shared.redis_keys import RedisKeys

        key1 = RedisKeys.image_delivery_request("conv-1", "req-x")
        key2 = RedisKeys.image_delivery_request("conv-2", "req-x")
        assert key1 != key2

    def test_keys_are_unique_across_requests(self) -> None:
        from shared.redis_keys import RedisKeys

        key1 = RedisKeys.image_delivery_request("conv-1", "req-a")
        key2 = RedisKeys.image_delivery_request("conv-1", "req-b")
        assert key1 != key2
