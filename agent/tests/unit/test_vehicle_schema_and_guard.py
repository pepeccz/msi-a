"""
Unit tests for vehicle schema optionality and tool-layer empty guard
(fix-vehicle-data-hallucination, Phase 2).

Tasks 2.1 — Schema accepts partial call (no ValidationError)
Tasks 2.2 — Tool returns EMPTY_VEHICLE_PAYLOAD on all-None call
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from agent.tools.schemas import ActualizarDatosVehiculoInput


# ---------------------------------------------------------------------------
# Task 2.1 — Schema accepts partial call
# ---------------------------------------------------------------------------


class TestActualizarDatosVehiculoInputSchema:
    """SC-3: schema must accept any non-empty subset of fields."""

    def test_schema_partial_vehicle_call_valid(self):
        """
        Only matricula + bastidor provided — schema must NOT raise ValidationError.
        All other fields should be None.
        """
        obj = ActualizarDatosVehiculoInput(
            matricula="6384BRN",
            bastidor="WVWZZZ3CZWE123456",
        )
        assert obj.matricula == "6384BRN"
        assert obj.bastidor == "WVWZZZ3CZWE123456"
        assert obj.marca is None
        assert obj.modelo is None
        assert obj.anio is None

    def test_schema_only_marca_valid(self):
        """
        Triangulation: a single field (marca) is enough — no ValidationError.
        Proves schema is fully optional, not just 'bastidor' is optional.
        """
        obj = ActualizarDatosVehiculoInput(marca="Fiat")
        assert obj.marca == "Fiat"
        assert obj.modelo is None
        assert obj.matricula is None

    def test_schema_all_none_accepted(self):
        """
        All fields omitted → schema accepts (guard lives at tool layer, not schema).
        """
        obj = ActualizarDatosVehiculoInput()
        assert obj.marca is None
        assert obj.modelo is None
        assert obj.anio is None
        assert obj.matricula is None
        assert obj.bastidor is None


# ---------------------------------------------------------------------------
# Task 2.2 — Tool guard rejects all-None call
# ---------------------------------------------------------------------------


class TestActualizarDatosVehiculoToolGuard:
    """SC-4: tool wrapper must return EMPTY_VEHICLE_PAYLOAD when all fields are None/empty."""

    @pytest.mark.asyncio
    async def test_actualizar_datos_vehiculo_all_none_returns_empty_payload_error(self):
        """
        All args None → tool must return success=False, error_code=EMPTY_VEHICLE_PAYLOAD.
        No call to case_service.update_personal_data must occur.
        """
        from agent.tools.case_tools import actualizar_datos_vehiculo

        mock_state = {
            "mode_context": {
                "case_id": "00000000-0000-0000-0000-000000000003",
                "current_step": "collect_vehicle",
            }
        }

        with patch("agent.tools.case_tools.get_tool_state", return_value=mock_state), \
             patch("agent.tools.case_tools.case_service") as mock_service:
            result = await actualizar_datos_vehiculo.ainvoke(
                {
                    "marca": None,
                    "modelo": None,
                    "anio": None,
                    "matricula": None,
                    "bastidor": None,
                }
            )

        # Service must NOT be called
        mock_service.update_personal_data.assert_not_called()

        # Parse result if JSON string
        if isinstance(result, str):
            result = json.loads(result)

        assert result["success"] is False, f"Expected success=False, got: {result}"
        assert result.get("error_code") == "EMPTY_VEHICLE_PAYLOAD", (
            f"Expected error_code=EMPTY_VEHICLE_PAYLOAD, got: {result.get('error_code')!r}"
        )

    @pytest.mark.asyncio
    async def test_actualizar_datos_vehiculo_all_empty_strings_returns_empty_payload_error(self):
        """
        Triangulation: empty strings (not None) should also be treated as no data.
        The .strip() guard drops them.
        """
        from agent.tools.case_tools import actualizar_datos_vehiculo

        mock_state = {"mode_context": {"case_id": "00000000-0000-0000-0000-000000000003"}}

        with patch("agent.tools.case_tools.get_tool_state", return_value=mock_state), \
             patch("agent.tools.case_tools.case_service") as mock_service:
            result = await actualizar_datos_vehiculo.ainvoke(
                {
                    "marca": "  ",
                    "modelo": "",
                    "anio": None,
                    "matricula": None,
                    "bastidor": None,
                }
            )

        mock_service.update_personal_data.assert_not_called()

        if isinstance(result, str):
            result = json.loads(result)

        assert result["success"] is False
        assert result.get("error_code") == "EMPTY_VEHICLE_PAYLOAD"

    @pytest.mark.asyncio
    async def test_actualizar_datos_vehiculo_with_data_calls_service(self):
        """
        Triangulation: at least one real field → tool must call the service.
        Proves the guard doesn't block legitimate calls.
        """
        from agent.tools.case_tools import actualizar_datos_vehiculo

        mock_state = {"mode_context": {"case_id": "00000000-0000-0000-0000-000000000003"}}
        expected = {"success": True, "message": "ok", "next_step": "collect_workshop"}

        with patch("agent.tools.case_tools.get_tool_state", return_value=mock_state), \
             patch(
                 "agent.tools.case_tools.case_service.update_personal_data",
                 new_callable=AsyncMock,
                 return_value=expected,
             ) as mock_update:
            result = await actualizar_datos_vehiculo.ainvoke(
                {
                    "marca": "Fiat",
                    "modelo": None,
                    "anio": None,
                    "matricula": None,
                    "bastidor": None,
                }
            )

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        # datos_vehiculo is passed as keyword argument
        datos = call_args.kwargs.get("datos_vehiculo")
        # datos_vehiculo must contain only the non-None/non-empty fields
        assert datos is not None, f"datos_vehiculo not found in call kwargs: {call_args}"
        assert "marca" in datos
        assert datos["marca"] == "Fiat"
