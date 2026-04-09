"""
Unit tests for expediente_validators composite validators.

Phase 1 TDD: tests that validators return 3-tuple (bool, list[str], list[str])
where the third element contains the field_key strings for missing fields.
"""

from agent.utils.expediente_validators import (
    validate_personal_data,
    validate_vehicle_data,
    validate_workshop_data,
)

# =============================================================================
# validate_personal_data
# =============================================================================

VALID_PERSONAL = {
    "nombre": "Pepe",
    "apellidos": "Cabeza Cruz",
    "email": "pepe@example.com",
    "dni_cif": "77429548W",
    "domicilio_calle": "Calle Mayor 12",
    "domicilio_localidad": "Mijas",
    "domicilio_provincia": "Málaga",
    "domicilio_cp": "29650",
    "itv_nombre": "ITV Guadalhorce",
}


class TestValidatePersonalDataReturnShape:
    """validate_personal_data must return a 3-tuple."""

    def test_returns_three_tuple_on_valid_data(self):
        result = validate_personal_data(VALID_PERSONAL)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"

    def test_valid_data_returns_true_empty_labels_empty_keys(self):
        is_valid, missing_labels, missing_keys = validate_personal_data(VALID_PERSONAL)
        assert is_valid is True
        assert missing_labels == []
        assert missing_keys == []

    def test_missing_itv_nombre_adds_key_to_third_element(self):
        data = {**VALID_PERSONAL}
        del data["itv_nombre"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "itv_nombre" in missing_keys

    def test_missing_nombre_adds_key_to_third_element(self):
        data = {**VALID_PERSONAL}
        del data["nombre"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "nombre" in missing_keys

    def test_missing_apellidos_adds_key_to_third_element(self):
        data = {**VALID_PERSONAL}
        del data["apellidos"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "apellidos" in missing_keys

    def test_missing_email_adds_key_to_third_element(self):
        data = {**VALID_PERSONAL}
        del data["email"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "email" in missing_keys

    def test_invalid_email_adds_email_key(self):
        data = {**VALID_PERSONAL, "email": "not-an-email"}
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "email" in missing_keys

    def test_missing_dni_cif_adds_key(self):
        data = {**VALID_PERSONAL}
        del data["dni_cif"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "dni_cif" in missing_keys

    def test_invalid_dni_cif_adds_key(self):
        data = {**VALID_PERSONAL, "dni_cif": "INVALID"}
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "dni_cif" in missing_keys

    def test_missing_domicilio_cp_adds_key(self):
        data = {**VALID_PERSONAL}
        del data["domicilio_cp"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "domicilio_cp" in missing_keys

    def test_missing_domicilio_calle_adds_key(self):
        data = {**VALID_PERSONAL}
        del data["domicilio_calle"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "domicilio_calle" in missing_keys

    def test_missing_domicilio_localidad_adds_key(self):
        data = {**VALID_PERSONAL}
        del data["domicilio_localidad"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "domicilio_localidad" in missing_keys

    def test_missing_domicilio_provincia_adds_key(self):
        data = {**VALID_PERSONAL}
        del data["domicilio_provincia"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert "domicilio_provincia" in missing_keys

    def test_missing_keys_parallel_to_missing_labels(self):
        """Third element (keys) must have same count as second element (labels)."""
        data = {**VALID_PERSONAL}
        del data["nombre"]
        del data["itv_nombre"]
        is_valid, missing_labels, missing_keys = validate_personal_data(data)
        assert is_valid is False
        assert len(missing_labels) == len(missing_keys)
        assert "nombre" in missing_keys
        assert "itv_nombre" in missing_keys


# =============================================================================
# validate_vehicle_data
# =============================================================================

VALID_VEHICLE = {
    "marca": "Honda",
    "modelo": "CBR 1000",
    "anio": "2019",
    "matricula": "1234ABC",
    "bastidor": "WVWZZZ3CZWE123456",
}


class TestValidateVehicleDataReturnShape:
    """validate_vehicle_data must return a 3-tuple."""

    def test_returns_three_tuple_on_valid_data(self):
        result = validate_vehicle_data(VALID_VEHICLE)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"

    def test_valid_data_returns_true_empty_lists(self):
        is_valid, missing_labels, missing_keys = validate_vehicle_data(VALID_VEHICLE)
        assert is_valid is True
        assert missing_labels == []
        assert missing_keys == []

    def test_missing_bastidor_adds_key(self):
        data = {**VALID_VEHICLE}
        del data["bastidor"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "bastidor" in missing_keys

    def test_missing_matricula_adds_key(self):
        data = {**VALID_VEHICLE}
        del data["matricula"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "matricula" in missing_keys

    def test_invalid_matricula_adds_key(self):
        data = {**VALID_VEHICLE, "matricula": "INVALID"}
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "matricula" in missing_keys

    def test_missing_marca_adds_key(self):
        data = {**VALID_VEHICLE}
        del data["marca"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "marca" in missing_keys

    def test_missing_modelo_adds_key(self):
        data = {**VALID_VEHICLE}
        del data["modelo"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "modelo" in missing_keys

    def test_missing_anio_adds_key(self):
        data = {**VALID_VEHICLE}
        del data["anio"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "anio" in missing_keys

    def test_multiple_missing_fields_all_keys_present(self):
        data = {**VALID_VEHICLE}
        del data["bastidor"]
        del data["matricula"]
        is_valid, missing_labels, missing_keys = validate_vehicle_data(data)
        assert is_valid is False
        assert "bastidor" in missing_keys
        assert "matricula" in missing_keys
        assert len(missing_labels) == len(missing_keys)


# =============================================================================
# validate_workshop_data
# =============================================================================

VALID_WORKSHOP = {
    "nombre": "Taller García",
    "responsable": "Luis Martínez",
    "domicilio": "C/ Industrial 10",
    "provincia": "Málaga",
    "ciudad": "Mijas",
    "telefono": "912345678",
    "registro_industrial": "TAL-12345",
    "actividad": "reparación de vehículos",
}


class TestValidateWorkshopDataReturnShape:
    """validate_workshop_data must return a 3-tuple."""

    def test_returns_three_tuple_on_valid_data(self):
        result = validate_workshop_data(VALID_WORKSHOP)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"

    def test_valid_data_returns_true_empty_lists(self):
        is_valid, missing_labels, missing_keys = validate_workshop_data(VALID_WORKSHOP)
        assert is_valid is True
        assert missing_labels == []
        assert missing_keys == []

    def test_none_data_returns_three_tuple(self):
        result = validate_workshop_data(None)
        assert len(result) == 3, f"Expected 3-tuple on None, got {len(result)}-tuple"

    def test_none_data_is_invalid(self):
        is_valid, missing_labels, missing_keys = validate_workshop_data(None)
        assert is_valid is False
        assert len(missing_labels) > 0

    def test_missing_registro_industrial_adds_key(self):
        data = {**VALID_WORKSHOP}
        del data["registro_industrial"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "registro_industrial" in missing_keys

    def test_missing_actividad_adds_key(self):
        data = {**VALID_WORKSHOP}
        del data["actividad"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "actividad" in missing_keys

    def test_missing_nombre_adds_key(self):
        data = {**VALID_WORKSHOP}
        del data["nombre"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "nombre" in missing_keys

    def test_missing_responsable_adds_key(self):
        data = {**VALID_WORKSHOP}
        del data["responsable"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "responsable" in missing_keys

    def test_missing_telefono_adds_key(self):
        data = {**VALID_WORKSHOP}
        del data["telefono"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "telefono" in missing_keys

    def test_multiple_missing_fields_all_keys_present(self):
        data = {**VALID_WORKSHOP}
        del data["registro_industrial"]
        del data["actividad"]
        is_valid, missing_labels, missing_keys = validate_workshop_data(data)
        assert is_valid is False
        assert "registro_industrial" in missing_keys
        assert "actividad" in missing_keys
        assert len(missing_labels) == len(missing_keys)
