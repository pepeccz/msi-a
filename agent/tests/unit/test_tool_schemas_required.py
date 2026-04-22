"""Tests for required field enforcement in tool schemas.

Updated after schema refactor: dict[str, str] parameters replaced with
explicit Pydantic fields to fix DeepSeek empty tool_call args issue.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestActualizarDatosPersonalesInput:
    """Schema for personal data tool must require all fields."""

    def test_rejects_empty_construction(self):
        """Constructing without required fields must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        with pytest.raises(ValidationError):
            ActualizarDatosPersonalesInput()

    def test_accepts_valid_fields(self):
        """Passing all required fields must succeed."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        obj = ActualizarDatosPersonalesInput(
            nombre="Pepe",
            apellidos="Cabeza Cruz",
            dni_cif="77429548W",
            email="pepe@email.com",
            domicilio_calle="Urb. Haza del Algarrobo 50",
            domicilio_localidad="Mijas",
            domicilio_provincia="Malaga",
            domicilio_cp="29650",
            itv_nombre="ITV Guadalhorce",
        )
        assert obj.nombre == "Pepe"
        assert obj.apellidos == "Cabeza Cruz"

    def test_rejects_missing_field(self):
        """Missing a required field must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        with pytest.raises(ValidationError):
            ActualizarDatosPersonalesInput(
                nombre="Pepe",
                # missing apellidos and others
            )


class TestActualizarDatosVehiculoInput:
    """Schema for vehicle data tool.

    After fix-vehicle-data-hallucination: all fields are optional (None by default).
    The tool-layer guard (not the schema) rejects all-None calls with EMPTY_VEHICLE_PAYLOAD.
    This prevents the LLM from being forced to fabricate values for missing fields.
    """

    def test_accepts_empty_construction(self):
        """Constructing without any field must NOT raise ValidationError — all fields optional.
        The EMPTY_VEHICLE_PAYLOAD guard lives at the tool wrapper level, not the schema.
        """
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        obj = ActualizarDatosVehiculoInput()
        assert obj.marca is None
        assert obj.modelo is None
        assert obj.anio is None
        assert obj.matricula is None
        assert obj.bastidor is None

    def test_accepts_valid_fields(self):
        """Passing required fields must succeed (bastidor optional)."""
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        obj = ActualizarDatosVehiculoInput(
            marca="Fiat",
            modelo="Ducato",
            anio="2001",
            matricula="6384BRN",
        )
        assert obj.marca == "Fiat"
        assert obj.bastidor is None

    def test_accepts_with_bastidor(self):
        """Passing bastidor must also succeed."""
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        obj = ActualizarDatosVehiculoInput(
            marca="Fiat",
            modelo="Ducato",
            anio="2001",
            matricula="6384BRN",
            bastidor="WVWZZZ3CZWE123456",
        )
        assert obj.bastidor == "WVWZZZ3CZWE123456"


class TestActualizarDatosTallerRequiredField:
    """taller_propio must be required; workshop fields are optional."""

    def test_rejects_empty_construction(self):
        """Constructing without taller_propio must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        with pytest.raises(ValidationError):
            ActualizarDatosTallerInput()

    def test_accepts_false(self):
        """taller_propio=False must succeed (workshop fields stay None)."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        obj = ActualizarDatosTallerInput(taller_propio=False)
        assert obj.taller_propio is False
        assert obj.taller_nombre is None

    def test_accepts_true_with_data(self):
        """taller_propio=True with workshop fields must succeed."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        obj = ActualizarDatosTallerInput(
            taller_propio=True,
            taller_nombre="Taller X",
            taller_responsable="Juan",
        )
        assert obj.taller_propio is True
        assert obj.taller_nombre == "Taller X"


class TestOldSchemaRemoved:
    """The merged schema must no longer exist."""

    def test_old_schema_not_importable(self):
        """ActualizarDatosExpedienteInput must not exist in schemas module."""
        from agent.tools import schemas

        assert not hasattr(schemas, "ActualizarDatosExpedienteInput")
