"""
Unit tests for C2 — T2: enviar_imagenes_ejemplo phase gate.

Spec: R3 — Phase-Gated Image Tool Message.
AC-3.1: POST_PRICE presupuesto call returns compact message (no desc_block).
AC-3.2: PRICING presupuesto call (precio_comunicado=False) returns full desc_block.
AC-3.3: elemento tipo calls unaffected regardless of precio_comunicado.

RED before C2: the current tool always emits desc_block regardless of state.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_config(precio_comunicado: bool = False) -> dict:
    return {
        "configurable": {
            "state": {
                "conversation_id": "test-image-gate",
                "client_type": "particular",
                "mode_context": {
                    "precio_comunicado": precio_comunicado,
                    "categoria_slug": "motos-part",
                    "element_codes": ["ESCAPE"],
                },
                "shared_context": {
                    "precio_comunicado": precio_comunicado,
                },
            }
        }
    }


def _make_image_svc_result(n_images: int = 2) -> dict:
    """Minimal successful result from image_service.queue_example_images."""
    return {
        "success": True,
        "message": "",
        "images_to_queue": [
            {
                "url": f"https://example.com/img{i}.jpg",
                "tipo": "element",
                "element_code": "ESCAPE",
                "descripcion": f"Foto ejemplo {i}",
                "instruccion_usuario": f"Instrucción {i}",
                "titulo": f"Foto {i}",
                "status": "active",
            }
            for i in range(n_images)
        ],
        "follow_up_message": None,
        "sent_element_codes": ["ESCAPE"],
        "sent_base_docs": False,
    }


def _make_image_svc(svc_result: dict | None = None) -> MagicMock:
    svc = MagicMock()
    svc.queue_example_images = AsyncMock(return_value=svc_result or _make_image_svc_result())
    return svc


_COMPACT_PATTERN = re.compile(
    r"OK: \d+ imágenes encoladas.*Responde EXACTAMENTE \{\{CTA_5\}\}",
    re.IGNORECASE | re.DOTALL,
)


async def _invoke_presupuesto(precio_comunicado: bool) -> dict:
    svc = _make_image_svc()
    with patch("agent.services.image_service.get_image_service", return_value=svc):
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        return await enviar_imagenes_ejemplo.ainvoke(
            {"tipo": "presupuesto"},
            config=_make_config(precio_comunicado=precio_comunicado),
        )


# ---------------------------------------------------------------------------
# AC-3.1 — POST_PRICE presupuesto: compact message
# ---------------------------------------------------------------------------

class TestPostPricePresupuestoCompact:
    """precio_comunicado=True + tipo=presupuesto → compact message, no desc_block."""

    @pytest.mark.asyncio
    async def test_compact_message_matches_pattern(self):
        result = await _invoke_presupuesto(precio_comunicado=True)
        message = result.get("message", "")
        assert _COMPACT_PATTERN.search(message), (
            f"POST_PRICE presupuesto message must match compact pattern. "
            f"Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_compact_message_no_instrucciones(self):
        result = await _invoke_presupuesto(precio_comunicado=True)
        message = result.get("message", "")
        assert "INSTRUCCIONES DE FOTOS" not in message, (
            f"POST_PRICE presupuesto message must NOT contain INSTRUCCIONES DE FOTOS. "
            f"Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_compact_message_no_desc_content(self):
        """No photo description content from the desc_block should appear."""
        result = await _invoke_presupuesto(precio_comunicado=True)
        message = result.get("message", "")
        # desc_block contains instruccion_usuario values like "Instrucción 0"
        assert "Instrucción 0" not in message, (
            f"POST_PRICE compact message must NOT contain desc_block content. "
            f"Got: {message!r}"
        )


# ---------------------------------------------------------------------------
# AC-3.2 — PRICING presupuesto (precio_comunicado=False): full desc_block
# ---------------------------------------------------------------------------

class TestPricingPresupuestoFullMessage:
    """precio_comunicado=False + tipo=presupuesto → desc_block present."""

    @pytest.mark.asyncio
    async def test_full_message_has_instrucciones(self):
        result = await _invoke_presupuesto(precio_comunicado=False)
        message = result.get("message", "")
        # When images have instruccion_usuario, the desc_block must be in message.
        assert "INSTRUCCIONES DE FOTOS" in message, (
            f"PRICING presupuesto message must contain INSTRUCCIONES DE FOTOS. "
            f"Got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_full_message_no_compact_pattern(self):
        result = await _invoke_presupuesto(precio_comunicado=False)
        message = result.get("message", "")
        assert not _COMPACT_PATTERN.search(message), (
            f"PRICING presupuesto message must NOT match compact pattern (should be full). "
            f"Got: {message!r}"
        )


# ---------------------------------------------------------------------------
# AC-3.3 — elemento tipo: gate does NOT fire regardless of precio_comunicado
# ---------------------------------------------------------------------------

class TestElementoTipoUnaffected:
    """Gate must NOT fire for tipo=elemento even when precio_comunicado=True."""

    @pytest.mark.asyncio
    async def test_elemento_desc_block_present_when_precio_true(self):
        svc_result = {
            "success": True,
            "message": "",
            "images_to_queue": [
                {
                    "url": "https://example.com/elem.jpg",
                    "tipo": "element",
                    "element_code": "ESCAPE",
                    "descripcion": "Foto del escape",
                    "instruccion_usuario": "Instrucción escape visible",
                    "titulo": "Escape",
                    "status": "active",
                }
            ],
            "follow_up_message": None,
            "sent_element_codes": ["ESCAPE"],
            "sent_base_docs": False,
        }
        svc = _make_image_svc(svc_result)
        with patch("agent.services.image_service.get_image_service", return_value=svc):
            from agent.tools.image_tools import enviar_imagenes_ejemplo

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "ESCAPE", "categoria": "motos-part"},
                config=_make_config(precio_comunicado=True),
            )
        message = result.get("message", "")
        # For elemento, desc_block must remain — gate only activates for presupuesto
        assert "INSTRUCCIONES DE FOTOS" in message or "Instrucción escape" in message, (
            f"elemento tipo must still include desc_block when precio_comunicado=True. "
            f"Got: {message!r}"
        )
        # Must NOT be the presupuesto compact pattern
        assert not _COMPACT_PATTERN.search(message), (
            f"elemento tipo must NOT use compact presupuesto pattern. Got: {message!r}"
        )
