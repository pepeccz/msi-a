"""
Unit tests for agent.services.image_service.ImageService.

Tests each tipo branch (presupuesto / elemento / documentacion_base) and
their guardrails independently, without hitting the database or Redis.

Run with:
    pytest tests/unit/test_image_service.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image(status: str = "active") -> dict:
    return {
        "image_url": "https://storage.example.com/img.jpg",
        "image_type": "frontal",
        "title": "Vista frontal",
        "description": "Foto frontal del elemento",
        "user_instruction": "Toma la foto con la matrícula visible",
        "is_required": True,
        "status": status,
    }


def _make_element_details(images: list[dict] | None = None) -> dict:
    return {
        "id": "elem-uuid-1",
        "code": "ESCAPE",
        "name": "Escape",
        "description": "Descripción del escape",
        "images": images or [],
    }


# ---------------------------------------------------------------------------
# T2.1a: tipo="presupuesto" — happy path
# ---------------------------------------------------------------------------


class TestPresupuestoBranch:
    """Tests for tipo='presupuesto' branch in ImageService."""

    @pytest.mark.asyncio
    async def test_returns_pending_payload_with_active_images(self):
        """Happy path: state has tarifa_calculada with active images."""
        from agent.services.image_service import ImageService

        svc = ImageService()

        active_image = {
            "url": "https://storage.example.com/foto.jpg",
            "tipo": "frontal",
            "elemento": "Escape",
            "descripcion": "Vista frontal",
            "instruccion_usuario": "Foto con matrícula",
            "status": "active",
        }
        state = {
            "conversation_id": "conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {
                    "imagenes_ejemplo": [active_image],
                    "datos": {"element_codes": ["ESCAPE"]},
                },
                "element_codes": ["ESCAPE"],
                "imagenes_enviadas": False,
            },
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is True
        assert result["images_to_queue"] == [active_image]
        assert result["follow_up_message"] is None

    @pytest.mark.asyncio
    async def test_blocks_when_imagenes_enviadas(self):
        """Should reject if imagenes_enviadas is True."""
        from agent.services.image_service import ImageService

        svc = ImageService()
        state = {
            "conversation_id": "conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": True,
                "imagenes_enviadas": True,
                "tarifa_calculada": {"imagenes_ejemplo": []},
            },
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is False
        assert "ya fueron enviadas" in result["message"]

    @pytest.mark.asyncio
    async def test_blocks_in_expediente_mode(self):
        """tipo='presupuesto' is invalid in EXPEDIENTE_MODE."""
        from agent.services.image_service import ImageService

        svc = ImageService()
        state = {
            "conversation_id": "conv-123",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {},
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is False
        assert "EXPEDIENTE_MODE" in result["message"]

    @pytest.mark.asyncio
    async def test_blocks_without_precio_comunicado(self):
        """Should reject if price has not been communicated yet."""
        from agent.services.image_service import ImageService

        svc = ImageService()
        state = {
            "conversation_id": "conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": False,
                "tarifa_calculada": None,
            },
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is False
        assert "precio" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_blocks_without_tarifa_calculada(self):
        """Should reject if no tarifa_calculada in mode_context."""
        from agent.services.image_service import ImageService

        svc = ImageService()
        state = {
            "conversation_id": "conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": None,
            },
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_filters_placeholder_images(self):
        """Active filter: placeholder images should not be queued."""
        from agent.services.image_service import ImageService

        svc = ImageService()
        state = {
            "conversation_id": "conv-123",
            "current_mode": "PRESUPUESTO_MODE",
            "mode_context": {
                "precio_comunicado": True,
                "tarifa_calculada": {
                    "imagenes_ejemplo": [
                        {"url": "...", "status": "placeholder"},
                        {"url": "...", "status": "active"},
                    ],
                    "datos": {"element_codes": []},
                },
                "element_codes": [],
                "imagenes_enviadas": False,
            },
        }

        result = await svc.queue_example_images(
            tipo="presupuesto",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 1


# ---------------------------------------------------------------------------
# T2.1b: tipo="elemento"
# ---------------------------------------------------------------------------


class TestElementoBranch:
    """Tests for tipo='elemento' branch in ImageService."""

    @pytest.mark.asyncio
    async def test_requires_codigo_elemento(self):
        from agent.services.image_service import ImageService

        svc = ImageService()
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento=None,
            categoria="motos-part",
            follow_up_message=None,
            state_context={},
        )

        assert result["success"] is False
        assert "codigo_elemento" in result["message"]

    @pytest.mark.asyncio
    async def test_requires_categoria(self):
        from agent.services.image_service import ImageService

        svc = ImageService()
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="ESCAPE",
            categoria=None,
            follow_up_message=None,
            state_context={},
        )

        assert result["success"] is False
        assert "categoria" in result["message"]

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_or_fetch_category_id")
    async def test_returns_active_images_for_element(self, mock_get_category):
        """Happy path: element found, has active images."""
        from agent.services.image_service import ImageService

        mock_get_category.return_value = "cat-uuid"

        element_service_mock = MagicMock()
        element_service_mock.get_elements_by_category = AsyncMock(
            return_value=[
                {"id": "elem-id", "code": "ESCAPE", "name": "Escape"}
            ]
        )
        element_service_mock.get_element_with_images = AsyncMock(
            return_value=_make_element_details(
                images=[_make_image("active"), _make_image("placeholder")]
            )
        )

        svc = ImageService()

        with patch("agent.services.image_service.get_element_service", return_value=element_service_mock):
            result = await svc.queue_example_images(
                tipo="elemento",
                codigo_elemento="ESCAPE",
                categoria="motos-part",
                follow_up_message=None,
                state_context={"conversation_id": "conv-1"},
            )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 1  # only active

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_or_fetch_category_id")
    async def test_category_not_found(self, mock_get_category):
        from agent.services.image_service import ImageService

        mock_get_category.return_value = None

        svc = ImageService()
        result = await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="ESCAPE",
            categoria="nonexistent-cat",
            follow_up_message=None,
            state_context={},
        )

        assert result["success"] is False
        assert "no encontrada" in result["message"]

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_or_fetch_category_id")
    async def test_element_not_found_returns_valid_codes(self, mock_get_category):
        """When element code is invalid, return list of valid codes."""
        from agent.services.image_service import ImageService

        mock_get_category.return_value = "cat-uuid"

        element_service_mock = MagicMock()
        element_service_mock.get_elements_by_category = AsyncMock(
            return_value=[
                {"id": "id1", "code": "ESCAPE", "name": "Escape"},
                {"id": "id2", "code": "MANILLAR", "name": "Manillar"},
            ]
        )

        svc = ImageService()
        with patch("agent.services.image_service.get_element_service", return_value=element_service_mock):
            result = await svc.queue_example_images(
                tipo="elemento",
                codigo_elemento="INVALID_CODE",
                categoria="motos-part",
                follow_up_message=None,
                state_context={},
            )

        assert result["success"] is False
        assert "valid_codes" in result

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_or_fetch_category_id")
    async def test_overrides_categoria_in_expediente_mode(self, mock_get_category):
        """In EXPEDIENTE_MODE, state categoria_slug overrides LLM-supplied categoria."""
        from agent.services.image_service import ImageService

        mock_get_category.return_value = None  # Will be called with overridden slug

        svc = ImageService()
        state = {
            "conversation_id": "conv-1",
            "current_mode": "EXPEDIENTE_MODE",
            "mode_context": {
                "categoria_slug": "aseicars-prof",  # correct category from state
            },
        }

        # Call with wrong categoria, should use state's value
        # (category lookup will fail with None → error about category not found,
        # but we verify the override happened via the call arg to mock)
        await svc.queue_example_images(
            tipo="elemento",
            codigo_elemento="ESCAPE",
            categoria="motos-part",  # wrong, should be overridden
            follow_up_message=None,
            state_context=state,
        )

        # The mock should have been called with the overridden slug
        mock_get_category.assert_called_with("aseicars-prof")


# ---------------------------------------------------------------------------
# T2.1c: tipo="documentacion_base"
# ---------------------------------------------------------------------------


class TestDocumentacionBaseBranch:
    """Tests for tipo='documentacion_base' branch in ImageService."""

    @pytest.mark.asyncio
    async def test_requires_categoria(self):
        from agent.services.image_service import ImageService

        svc = ImageService()
        result = await svc.queue_example_images(
            tipo="documentacion_base",
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context={},
        )

        assert result["success"] is False
        assert "categoria" in result["message"]

    @pytest.mark.asyncio
    async def test_invalid_tipo_raises_error(self):
        from agent.services.image_service import ImageService

        svc = ImageService()
        result = await svc.queue_example_images(
            tipo="invalid_tipo",  # type: ignore[arg-type]
            codigo_elemento=None,
            categoria=None,
            follow_up_message=None,
            state_context={},
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_tarifa_service")
    async def test_happy_path_with_images(self, mock_get_tarifa):
        """Happy path: category has base documentation with images."""
        from agent.services.image_service import ImageService
        from agent.utils.expediente_types import CollectionStep

        tarifa_service_mock = MagicMock()
        tarifa_service_mock.get_category_data = AsyncMock(
            return_value={
                "base_documentation": [
                    {
                        "description": "Ficha técnica",
                        "image_url": "https://storage.example.com/ficha.jpg",
                    },
                    {
                        "description": "Permiso de circulación",
                        "image_url": "https://storage.example.com/permiso.jpg",
                    },
                ]
            }
        )
        mock_get_tarifa.return_value = tarifa_service_mock

        svc = ImageService()
        state = {
            "conversation_id": "conv-1",
            "mode_context": {
                "expediente_sub_mode": CollectionStep.COLLECT_BASE_DOCS.value,
            },
        }

        result = await svc.queue_example_images(
            tipo="documentacion_base",
            codigo_elemento=None,
            categoria="motos-part",
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is True
        assert len(result["images_to_queue"]) == 2

    @pytest.mark.asyncio
    @patch("agent.services.image_service.get_tarifa_service")
    async def test_blocks_outside_collect_base_docs_phase(self, mock_get_tarifa):
        """tipo='documentacion_base' should be blocked outside COLLECT_BASE_DOCS."""
        from agent.services.image_service import ImageService
        from agent.utils.expediente_types import CollectionStep

        svc = ImageService()
        state = {
            "conversation_id": "conv-1",
            "mode_context": {
                "expediente_sub_mode": CollectionStep.COLLECT_PERSONAL.value,
            },
        }

        result = await svc.queue_example_images(
            tipo="documentacion_base",
            codigo_elemento=None,
            categoria="motos-part",
            follow_up_message=None,
            state_context=state,
        )

        assert result["success"] is False
