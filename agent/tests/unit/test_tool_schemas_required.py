"""Tests for required field enforcement in tool schemas.

Task 1.1 [RED]: These tests MUST fail until the schemas are split
and required fields are enforced (Task 1.2).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestActualizarDatosPersonalesInput:
    """Schema for personal data tool must require datos_personales."""

    def test_rejects_empty_construction(self):
        """Constructing without datos_personales must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        with pytest.raises(ValidationError):
            ActualizarDatosPersonalesInput()

    def test_rejects_none_value(self):
        """Passing datos_personales=None must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        with pytest.raises(ValidationError):
            ActualizarDatosPersonalesInput(datos_personales=None)

    def test_accepts_valid_dict(self):
        """Passing a non-empty dict must succeed."""
        from agent.tools.schemas import ActualizarDatosPersonalesInput

        obj = ActualizarDatosPersonalesInput(
            datos_personales={"nombre": "Pepe", "apellidos": "Cabeza"}
        )
        assert obj.datos_personales == {"nombre": "Pepe", "apellidos": "Cabeza"}


class TestActualizarDatosVehiculoInput:
    """Schema for vehicle data tool must require datos_vehiculo."""

    def test_rejects_empty_construction(self):
        """Constructing without datos_vehiculo must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        with pytest.raises(ValidationError):
            ActualizarDatosVehiculoInput()

    def test_rejects_none_value(self):
        """Passing datos_vehiculo=None must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        with pytest.raises(ValidationError):
            ActualizarDatosVehiculoInput(datos_vehiculo=None)

    def test_accepts_valid_dict(self):
        """Passing a non-empty dict must succeed."""
        from agent.tools.schemas import ActualizarDatosVehiculoInput

        obj = ActualizarDatosVehiculoInput(
            datos_vehiculo={"marca": "Honda", "modelo": "CBR"}
        )
        assert obj.datos_vehiculo == {"marca": "Honda", "modelo": "CBR"}


class TestActualizarDatosTallerRequiredField:
    """taller_propio must be required (no default=None)."""

    def test_rejects_empty_construction(self):
        """Constructing without taller_propio must raise ValidationError."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        with pytest.raises(ValidationError):
            ActualizarDatosTallerInput()

    def test_accepts_false(self):
        """taller_propio=False must succeed (datos_taller stays optional)."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        obj = ActualizarDatosTallerInput(taller_propio=False)
        assert obj.taller_propio is False
        assert obj.datos_taller is None

    def test_accepts_true_with_data(self):
        """taller_propio=True with datos_taller must succeed."""
        from agent.tools.schemas import ActualizarDatosTallerInput

        obj = ActualizarDatosTallerInput(
            taller_propio=True,
            datos_taller={"nombre": "Taller X", "responsable": "Juan"},
        )
        assert obj.taller_propio is True
        assert obj.datos_taller["nombre"] == "Taller X"


class TestOldSchemaRemoved:
    """The merged schema must no longer exist."""

    def test_old_schema_not_importable(self):
        """ActualizarDatosExpedienteInput must not exist in schemas module."""
        from agent.tools import schemas

        assert not hasattr(schemas, "ActualizarDatosExpedienteInput")
