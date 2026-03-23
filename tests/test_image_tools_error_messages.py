"""
Tests for improved error messages in enviar_imagenes_ejemplo (Phase 2).

Verifies that when an element code is not found after normalization,
the error response includes:
  - The invalid code that was searched for
  - A sorted list of valid codes (capped at 20)
  - An explicit retry instruction
  - A `valid_codes` key in the return dict

Run with: pytest tests/test_image_tools_error_messages.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build fake element dicts (mimic element_service return shape)
# ---------------------------------------------------------------------------

def _make_element(code: str) -> dict:
    """Create a minimal element dict as returned by element_service."""
    return {"id": f"uuid-{code}", "code": code, "name": code.replace("_", " ").title()}


def _make_elements(codes: list[str]) -> list[dict]:
    return [_make_element(c) for c in codes]


# ---------------------------------------------------------------------------
# Fixture: small category (12 elements — under the 20-code cap)
# ---------------------------------------------------------------------------

SMALL_CATEGORY_CODES = sorted([
    "ASIDEROS",
    "DEFENSA_DELANTERA",
    "DEFENSA_TRASERA",
    "ESCAPE",
    "ESCAPE_DELANTERO",
    "ESCAPE_TRASERO",
    "PLACA_SOLAR_REGULADOR_INTERIOR",
    "SUBCHASIS",
    "SUSPENSION_DELANTERA",
    "SUSPENSION_TRASERA",
    "TOLDO_COFRE",
    "TOLDO_SIMPLE",
])

# ---------------------------------------------------------------------------
# Fixture: large category (25 elements — exceeds the 20-code cap)
# ---------------------------------------------------------------------------

LARGE_CATEGORY_CODES = sorted([f"ELEMENT_{chr(65 + i)}{j}" for i in range(5) for j in range(5)])
assert len(LARGE_CATEGORY_CODES) == 25  # sanity check


# ---------------------------------------------------------------------------
# Shared patch targets
# ---------------------------------------------------------------------------

_PATCH_GET_CAT = "agent.tools.image_tools.get_or_fetch_category_id"
_PATCH_ELEM_SVC = "agent.tools.image_tools.get_element_service"
_PATCH_NORMALIZE = "agent.tools.image_tools.normalize_element_code"
_PATCH_CONV_ID = "agent.tools.image_tools._conversation_id_var"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestErrorMessageSmallCategory:
    """Error response when invalid code is used with a small category (<= 20 codes)."""

    @pytest.mark.asyncio
    async def test_error_contains_valid_codes_key(self) -> None:
        """Return dict must include a `valid_codes` key with sorted list."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "CODIGO_INVENTADO", "categoria": "motos-part"}
            )

        assert result["success"] is False
        assert "valid_codes" in result
        assert isinstance(result["valid_codes"], list)
        assert result["valid_codes"] == SMALL_CATEGORY_CODES
        assert len(result["valid_codes"]) == 12

    @pytest.mark.asyncio
    async def test_error_message_contains_all_codes(self) -> None:
        """For a small category, ALL valid codes appear in the message."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "CODIGO_INVENTADO", "categoria": "motos-part"}
            )

        msg = result["message"]
        for code in SMALL_CATEGORY_CODES:
            assert code in msg, f"Expected code '{code}' in error message"

    @pytest.mark.asyncio
    async def test_error_message_contains_searched_code(self) -> None:
        """The error message must mention what code was searched for."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "CODIGO_INVENTADO", "categoria": "motos-part"}
            )

        assert "CODIGO_INVENTADO" in result["message"]

    @pytest.mark.asyncio
    async def test_error_message_contains_retry_instruction(self) -> None:
        """The error message must tell the LLM to retry with a correct code."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "CODIGO_INVENTADO", "categoria": "motos-part"}
            )

        msg = result["message"]
        assert "DEBES usar uno de estos codigos EXACTOS" in msg
        assert "reintenta" in msg.lower()

    @pytest.mark.asyncio
    async def test_no_truncation_note_for_small_category(self) -> None:
        """Small categories should NOT have truncation indicator."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "CODIGO_INVENTADO", "categoria": "motos-part"}
            )

        assert "en total" not in result["message"]
        assert "primeros 20" not in result["message"]


class TestErrorMessageLargeCategory:
    """Error response when invalid code is used with a large category (> 20 codes)."""

    @pytest.mark.asyncio
    async def test_valid_codes_capped_at_20(self) -> None:
        """The valid_codes list must be capped at 20 entries."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(LARGE_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "NONEXISTENT", "categoria": "big-cat"}
            )

        assert len(result["valid_codes"]) == 20
        # Must be sorted alphabetically (first 20 of sorted list)
        assert result["valid_codes"] == LARGE_CATEGORY_CODES[:20]

    @pytest.mark.asyncio
    async def test_truncation_note_in_message(self) -> None:
        """When > 20 codes, the message must indicate truncation."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(LARGE_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "NONEXISTENT", "categoria": "big-cat"}
            )

        msg = result["message"]
        assert "25 codigos en total" in msg
        assert "primeros 20" in msg


class TestErrorMessageStructure:
    """Verify the overall error dict structure for LLM parseability."""

    @pytest.mark.asyncio
    async def test_error_dict_keys(self) -> None:
        """Error return must have success, message, valid_codes, data, tool_name."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(SMALL_CATEGORY_CODES)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "INVENTADO", "categoria": "motos-part"}
            )

        expected_keys = {"success", "message", "valid_codes", "data", "tool_name"}
        assert set(result.keys()) == expected_keys
        assert result["success"] is False
        assert result["data"] is None
        assert result["tool_name"] == "enviar_imagenes_ejemplo"

    @pytest.mark.asyncio
    async def test_valid_codes_are_sorted(self) -> None:
        """The valid_codes list must be sorted alphabetically."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        # Intentionally unsorted input
        unsorted_codes = ["ZEBRA_CODE", "ALPHA_CODE", "MIDDLE_CODE"]
        elements = _make_elements(unsorted_codes)

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "NOPE", "categoria": "test-cat"}
            )

        assert result["valid_codes"] == ["ALPHA_CODE", "MIDDLE_CODE", "ZEBRA_CODE"]

    @pytest.mark.asyncio
    async def test_no_escalation_instruction(self) -> None:
        """The error must explicitly say NOT to escalate to human."""
        from agent.tools.image_tools import enviar_imagenes_ejemplo

        elements = _make_elements(["CODE_A", "CODE_B"])

        with (
            patch(_PATCH_GET_CAT, new_callable=AsyncMock, return_value="cat-uuid"),
            patch(_PATCH_ELEM_SVC) as mock_svc_factory,
            patch(_PATCH_NORMALIZE, return_value=(None, False)),
            patch(_PATCH_CONV_ID, new_callable=lambda: MagicMock(get=MagicMock(return_value="conv-1"))),
        ):
            mock_svc = AsyncMock()
            mock_svc.get_elements_by_category = AsyncMock(return_value=elements)
            mock_svc_factory.return_value = mock_svc

            result = await enviar_imagenes_ejemplo.ainvoke(
                {"tipo": "elemento", "codigo_elemento": "BAD", "categoria": "x"}
            )

        assert "NO escales a humano" in result["message"]
