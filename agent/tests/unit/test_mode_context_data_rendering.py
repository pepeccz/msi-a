"""Tests for personal_data and vehicle_data rendering in format_mode_context.

Task 5.1-5.2: format_mode_context() must render pre-loaded personal and
vehicle data when available in EXPEDIENTE_MODE context.
"""

from __future__ import annotations

from agent.prompts.loader import format_mode_context


class TestPersonalDataRendering:
    """Personal data must appear in rendered context when present."""

    def test_renders_personal_data_fields(self):
        """Non-empty personal_data dict must be rendered."""
        ctx = {
            "expediente_sub_mode": "collect_personal",
            "personal_data": {
                "nombre": "Pepe",
                "apellidos": "Cabeza Cruz",
                "email": "pepe@test.com",
            },
        }
        result = format_mode_context("EXPEDIENTE_MODE", ctx)

        assert "DATOS PERSONALES REGISTRADOS" in result
        assert "Pepe" in result
        assert "Cabeza Cruz" in result
        assert "pepe@test.com" in result

    def test_no_rendering_when_empty(self):
        """Empty personal_data must not produce a block."""
        ctx = {
            "expediente_sub_mode": "collect_personal",
            "personal_data": {},
        }
        result = format_mode_context("EXPEDIENTE_MODE", ctx)

        assert "DATOS PERSONALES REGISTRADOS" not in result

    def test_no_rendering_when_none(self):
        """None personal_data must not produce a block."""
        ctx = {
            "expediente_sub_mode": "collect_personal",
            "personal_data": None,
        }
        result = format_mode_context("EXPEDIENTE_MODE", ctx)

        assert "DATOS PERSONALES REGISTRADOS" not in result


class TestVehicleDataRendering:
    """Vehicle data must appear in rendered context when present."""

    def test_renders_vehicle_data_fields(self):
        """Non-empty vehicle_data dict must be rendered."""
        ctx = {
            "expediente_sub_mode": "collect_vehicle",
            "vehicle_data": {
                "marca": "Honda",
                "modelo": "CBR 600",
            },
        }
        result = format_mode_context("EXPEDIENTE_MODE", ctx)

        assert "DATOS VEHÍCULO REGISTRADOS" in result
        assert "Honda" in result
        assert "CBR 600" in result

    def test_no_rendering_when_absent(self):
        """Missing vehicle_data key must not produce a block."""
        ctx = {
            "expediente_sub_mode": "collect_vehicle",
        }
        result = format_mode_context("EXPEDIENTE_MODE", ctx)

        assert "DATOS VEHÍCULO REGISTRADOS" not in result
