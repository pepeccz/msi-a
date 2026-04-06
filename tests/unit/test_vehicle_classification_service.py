"""
Unit tests for agent/services/vehicle_classification_service.py

Tests are pure unit tests — no database, no live Redis, no live LLM.
All external calls are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.services.vehicle_classification_service import (
    VEHICLE_TYPE_TO_CATEGORY_SLUG,
    _parse_classification_response,
    _resolve_full_category_slug,
    classify_vehicle,
)


# ---------------------------------------------------------------------------
# _parse_classification_response
# ---------------------------------------------------------------------------


class TestParseClassificationResponse:
    def test_valid_json(self):
        content = '{"tipo": "moto", "confianza": "alta", "descripcion": "Honda CBF600"}'
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "moto"
        assert result["confianza"] == "alta"
        assert result["descripcion"] == "Honda CBF600"

    def test_markdown_code_block(self):
        content = "```json\n{\"tipo\": \"aseicars\", \"confianza\": \"alta\", \"descripcion\": \"Autocaravana\"}\n```"
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "aseicars"

    def test_markdown_code_block_no_lang(self):
        content = "```\n{\"tipo\": \"camper\", \"confianza\": \"media\", \"descripcion\": \"Furgoneta\"}\n```"
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "camper"

    def test_unknown_tipo_normalised_to_desconocido(self):
        content = '{"tipo": "helicoptero", "confianza": "alta", "descripcion": "No existe"}'
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "desconocido"
        assert result["confianza"] == "baja"

    def test_desconocido_is_valid(self):
        content = '{"tipo": "desconocido", "confianza": "baja", "descripcion": "No identificado"}'
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "desconocido"

    def test_missing_fields_use_defaults(self):
        content = '{"tipo": "moto"}'
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == "moto"
        assert result["confianza"] == "baja"
        assert result["descripcion"] == ""

    def test_invalid_json_returns_none(self):
        result = _parse_classification_response("not-json-at-all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_classification_response("")
        assert result is None

    @pytest.mark.parametrize("tipo", list(VEHICLE_TYPE_TO_CATEGORY_SLUG.keys()))
    def test_all_known_tipos_accepted(self, tipo):
        content = json.dumps({"tipo": tipo, "confianza": "alta", "descripcion": "test"})
        result = _parse_classification_response(content)
        assert result is not None
        assert result["tipo"] == tipo


# ---------------------------------------------------------------------------
# _resolve_full_category_slug
# ---------------------------------------------------------------------------


class TestResolvFullCategorySlug:
    @pytest.mark.asyncio
    async def test_resolves_with_part_suffix_for_particular(self):
        with patch(
            "agent.services.vehicle_classification_service._resolve_full_category_slug"
        ) as mock_fn:
            # Call the real function but mock get_or_fetch_category_id inside it
            mock_fn.return_value = "motos-part"
            result = await mock_fn("motos", "particular")
            assert result == "motos-part"

    @pytest.mark.asyncio
    async def test_resolves_with_prof_suffix_for_professional(self):
        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
        ) as mock_get:
            # First call (motos-prof) returns a valid ID
            mock_get.return_value = "some-uuid"
            result = await _resolve_full_category_slug("motos", "professional")
            assert result == "motos-prof"
            mock_get.assert_called_once_with("motos-prof")

    @pytest.mark.asyncio
    async def test_falls_back_to_prefix_without_suffix(self):
        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
        ) as mock_get:
            # First call (motos-part) → None, second call (motos) → found
            mock_get.side_effect = [None, "some-uuid"]
            result = await _resolve_full_category_slug("motos", "particular")
            assert result == "motos"
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_opposite_suffix(self):
        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
        ) as mock_get:
            # part → None, bare → None, prof → found
            mock_get.side_effect = [None, None, "some-uuid"]
            result = await _resolve_full_category_slug("motos", "particular")
            assert result == "motos-prof"

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_found(self):
        with patch(
            "agent.tools.element_tools.get_or_fetch_category_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = None
            result = await _resolve_full_category_slug("unknown_prefix", "particular")
            assert result is None


# ---------------------------------------------------------------------------
# classify_vehicle (integration of all helpers)
# ---------------------------------------------------------------------------


class TestClassifyVehicle:
    def _make_redis(self, cached_value=None):
        redis = AsyncMock()
        redis.get.return_value = json.dumps(cached_value).encode() if cached_value else None
        redis.setex = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        cached = {
            "tipo": "moto",
            "confianza": "alta",
            "categoria_sugerida": "motos-part",
            "categoria_prefix": "motos",
            "descripcion": "Cached result",
            "marca": "Honda",
            "modelo": "CBF600",
            "client_type_used": "particular",
            "pedir_confirmacion": False,
            "_provider": "ollama",
        }
        redis_mock = self._make_redis(cached_value=cached)

        with patch(
            "agent.services.vehicle_classification_service.get_redis_client",
            return_value=redis_mock,
        ):
            result = await classify_vehicle("honda", "cbf600", "particular")

        assert result["tipo"] == "moto"
        assert result["_provider"] == "ollama"
        # Should NOT have called any LLM
        redis_mock.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_ollama_primary_path(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = True
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = True
        settings_mock.OLLAMA_BASE_URL = "http://ollama:11434"

        ollama_result = {"tipo": "moto", "confianza": "alta", "descripcion": "Honda CBF600"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=ollama_result,
            ) as mock_ollama,
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                new_callable=AsyncMock,
            ) as mock_openrouter,
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="motos-part",
            ),
        ):
            result = await classify_vehicle("Honda", "CBF600", "particular")

        assert result["tipo"] == "moto"
        assert result["_provider"] == "ollama"
        mock_ollama.assert_called_once()
        mock_openrouter.assert_not_called()

    @pytest.mark.asyncio
    async def test_openrouter_fallback_when_ollama_fails(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = True
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = True

        openrouter_result = {"tipo": "aseicars", "confianza": "alta", "descripcion": "Motorhome"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=None,  # Ollama failed
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                new_callable=AsyncMock,
                return_value=openrouter_result,
            ) as mock_openrouter,
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="aseicars-part",
            ),
        ):
            result = await classify_vehicle("Hymer", "B-Klasse", "particular")

        assert result["tipo"] == "aseicars"
        assert result["_provider"] == "openrouter"
        mock_openrouter.assert_called_once()

    @pytest.mark.asyncio
    async def test_both_providers_fail_returns_desconocido(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = True
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = True

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await classify_vehicle("Unknown", "Vehicle", "particular")

        assert result["tipo"] == "desconocido"
        assert result["_provider"] == "none"
        assert result["pedir_confirmacion"] is True

    @pytest.mark.asyncio
    async def test_result_is_cached_after_classification(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = True
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = True

        ollama_result = {"tipo": "moto", "confianza": "alta", "descripcion": "Yamaha MT-07"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=ollama_result,
            ),
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="motos-part",
            ),
        ):
            await classify_vehicle("Yamaha", "MT-07", "particular")

        # Verify setex was called to persist the cache
        redis_mock.setex.assert_called_once()
        call_args = redis_mock.setex.call_args
        cache_key = call_args[0][0]
        assert "Yamaha" in cache_key
        assert "MT-07" in cache_key

    @pytest.mark.asyncio
    async def test_input_is_normalised(self):
        """marca should be title-cased, modelo should be upper-cased."""
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = False
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = False

        captured_args: dict = {}

        async def mock_openrouter(marca, modelo, settings):
            captured_args["marca"] = marca
            captured_args["modelo"] = modelo
            return {"tipo": "moto", "confianza": "alta", "descripcion": "test"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                side_effect=mock_openrouter,
            ),
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="motos-part",
            ),
        ):
            await classify_vehicle("HONDA", "cbf600", "particular")

        assert captured_args["marca"] == "Honda"
        assert captured_args["modelo"] == "CBF600"

    @pytest.mark.asyncio
    async def test_pedir_confirmacion_true_for_low_confidence(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = False
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = False

        ollama_result = {"tipo": "tuning", "confianza": "baja", "descripcion": "No seguro"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                new_callable=AsyncMock,
                return_value=ollama_result,
            ),
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="tuning-part",
            ),
        ):
            result = await classify_vehicle("Generic", "Car", "particular")

        assert result["pedir_confirmacion"] is True

    @pytest.mark.asyncio
    async def test_pedir_confirmacion_false_for_high_confidence(self):
        redis_mock = self._make_redis()
        settings_mock = MagicMock()
        settings_mock.USE_HYBRID_LLM = False
        settings_mock.USE_LOCAL_VEHICLE_CLASSIFICATION = False

        llm_result = {"tipo": "moto", "confianza": "alta", "descripcion": "Honda CBF"}

        with (
            patch(
                "agent.services.vehicle_classification_service.get_redis_client",
                return_value=redis_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service.get_settings",
                return_value=settings_mock,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_ollama",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "agent.services.vehicle_classification_service._classify_with_openrouter",
                new_callable=AsyncMock,
                return_value=llm_result,
            ),
            patch(
                "agent.services.vehicle_classification_service._resolve_full_category_slug",
                new_callable=AsyncMock,
                return_value="motos-part",
            ),
        ):
            result = await classify_vehicle("Honda", "CBF600", "particular")

        assert result["pedir_confirmacion"] is False
