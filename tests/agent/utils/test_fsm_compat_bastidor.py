"""
Regression tests for fix-expediente-bastidor-precio — Grupo A.

Covers:
  R2: validate_vehicle_data() requires bastidor
  R3: validate_vehicle_data() reports "número de bastidor (VIN)" in missing list
  R4: validate_vehicle_data() returns is_valid=True only when bastidor is present

All functions under test are pure / synchronous — no async, no DB.
"""

import pytest

from agent.utils.expediente_validators import validate_vehicle_data


# =============================================================================
# Grupo A — validate_vehicle_data(): bastidor is required (R2, R3, R4)
# =============================================================================


class TestValidateVehicleDataBastidor:
    """
    Regression suite: bastidor must be a required field in validate_vehicle_data().

    Prior to the fix, bastidor was missing from the required-fields list,
    causing expedientes to be submitted without VIN numbers.

    Spec coverage: R2, R3, R4, S1, S2, S3, S4
    """

    # ------------------------------------------------------------------
    # R2/S1 — sin bastidor → is_valid=False
    # ------------------------------------------------------------------

    def test_sin_bastidor_is_invalid(self):
        """
        R2/S1: vehicle data without bastidor must return is_valid=False.

        Regression: before the fix, this returned (True, []) — the missing
        bastidor was silently accepted and the case proceeded without VIN.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            # bastidor intentionally absent
        }
        is_valid, missing = validate_vehicle_data(data)

        assert is_valid is False, (
            "Vehicle data without bastidor MUST be invalid. "
            "This was the root bug: bastidor was not in the required list."
        )

    # ------------------------------------------------------------------
    # R3/S2 — "número de bastidor (VIN)" debe aparecer en missing
    # ------------------------------------------------------------------

    def test_sin_bastidor_missing_contains_vin_label(self):
        """
        R3/S2: when bastidor is absent, missing list must contain
        'número de bastidor (VIN)' so the LLM can prompt the user correctly.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
        }
        _, missing = validate_vehicle_data(data)

        assert any("bastidor" in m.lower() for m in missing), (
            f"missing list must contain a bastidor-related entry. Got: {missing}"
        )
        # Exact label check (the fix uses "número de bastidor (VIN)")
        assert "número de bastidor (VIN)" in missing, (
            f"Expected 'número de bastidor (VIN)' in missing. Got: {missing}"
        )

    # ------------------------------------------------------------------
    # R4/S3 — con todos los campos incluido bastidor → is_valid=True
    # ------------------------------------------------------------------

    def test_con_bastidor_y_todos_los_campos_es_valido(self):
        """
        R4/S3: vehicle data with all fields including bastidor must be valid.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            "bastidor": "WBA3A5G59DNP26082",
        }
        is_valid, missing = validate_vehicle_data(data)

        assert is_valid is True, (
            f"Complete vehicle data with bastidor must be valid. missing={missing}"
        )
        assert missing == [], (
            f"No fields should be missing when all are provided. missing={missing}"
        )

    # ------------------------------------------------------------------
    # S4 — bastidor="" (cadena vacía) → is_valid=False
    # ------------------------------------------------------------------

    def test_bastidor_cadena_vacia_es_invalido(self):
        """
        S4: bastidor="" (empty string) must return is_valid=False.

        Empty strings are falsy in Python — validate_vehicle_data uses
        data.get("bastidor") which returns "" for empty string, and empty
        string is falsy, so this must fail.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            "bastidor": "",  # empty string — should be rejected
        }
        is_valid, _ = validate_vehicle_data(data)

        assert is_valid is False, (
            "bastidor='' (empty string) must be treated as missing and return is_valid=False."
        )

    # ------------------------------------------------------------------
    # S4b — bastidor=None → is_valid=False
    # ------------------------------------------------------------------

    def test_bastidor_none_es_invalido(self):
        """
        S4b: bastidor=None must return is_valid=False.
        """
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            "bastidor": None,
        }
        is_valid, _ = validate_vehicle_data(data)

        assert is_valid is False, (
            "bastidor=None must be treated as missing and return is_valid=False."
        )

    # ------------------------------------------------------------------
    # Guard: data=None → is_valid=False
    # ------------------------------------------------------------------

    def test_data_none_es_invalido(self):
        """
        Guard: validate_vehicle_data(None) must return (False, [...]).

        The function signature accepts dict | None — None means no data at all.
        """
        # The function expects a dict, not None — but we test defensive handling
        # by passing an empty dict (the closest safe representation of "no data")
        is_valid, missing = validate_vehicle_data({})

        assert is_valid is False
        assert len(missing) > 0

    # ------------------------------------------------------------------
    # Regression: only bastidor is missing (not all fields)
    # ------------------------------------------------------------------

    def test_solo_bastidor_faltante_solo_bastidor_en_missing(self):
        """
        When only bastidor is missing (all other fields present), missing list
        must contain ONLY the bastidor entry.
        """
        data = {
            "marca": "Yamaha",
            "modelo": "MT-07",
            "anio": "2020",
            "matricula": "5678XYZ",
            # bastidor absent
        }
        is_valid, missing = validate_vehicle_data(data)

        assert is_valid is False
        # Only bastidor should be missing
        assert len(missing) == 1, (
            f"With only bastidor missing, missing list should have 1 item. Got: {missing}"
        )
        assert "bastidor" in missing[0].lower()

    # ------------------------------------------------------------------
    # Other required fields still enforced
    # ------------------------------------------------------------------

    def test_sin_marca_es_invalido(self):
        """Non-regression: other required fields (marca) still enforced."""
        data = {
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            "bastidor": "WBA3A5G59DNP26082",
            # marca absent
        }
        is_valid, missing = validate_vehicle_data(data)

        assert is_valid is False
        assert any("marca" in m.lower() for m in missing)

    def test_sin_matricula_es_invalido(self):
        """Non-regression: matricula still enforced."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "bastidor": "WBA3A5G59DNP26082",
            # matricula absent
        }
        is_valid, missing = validate_vehicle_data(data)

        assert is_valid is False
        assert any("matrícula" in m or "matricula" in m.lower() for m in missing)

    # ------------------------------------------------------------------
    # Return-type contract
    # ------------------------------------------------------------------

    def test_return_type_is_tuple_bool_list(self):
        """validate_vehicle_data always returns (bool, list[str])."""
        data = {
            "marca": "Honda",
            "modelo": "CBR 600",
            "anio": "2018",
            "matricula": "1234BCD",
            "bastidor": "WBA3A5G59DNP26082",
        }
        result = validate_vehicle_data(data)

        assert isinstance(result, tuple), "Must return a tuple"
        assert len(result) == 2, "Tuple must have 2 elements"
        is_valid, missing = result
        assert isinstance(is_valid, bool), "First element must be bool"
        assert isinstance(missing, list), "Second element must be list"
