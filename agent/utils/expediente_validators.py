"""
Expediente data validation functions for case collection.

These are the canonical validation functions for personal data, vehicle
data, workshop data, and Spanish document/address formats.
"""

from __future__ import annotations

import re


# =============================================================================
# Validation Regexes
# =============================================================================

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

MATRICULA_REGEX = re.compile(
    r"^([0-9]{4}[A-Z]{3}|[A-Z]{1,2}[0-9]{4}[A-Z]{0,2})$",
    re.IGNORECASE,
)

DNI_CIF_REGEX = re.compile(
    r"^([0-9]{8}[A-Z]|[XYZ][0-9]{7}[A-Z]|[A-Z][0-9]{7,8}[A-Z0-9]?)$",
    re.IGNORECASE,
)

CP_REGEX = re.compile(r"^(0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}$")


# =============================================================================
# Field-Level Validators
# =============================================================================


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_matricula(matricula: str) -> bool:
    """Validate Spanish vehicle plate format."""
    if not matricula:
        return False
    clean = matricula.strip().replace(" ", "").replace("-", "").upper()
    return bool(MATRICULA_REGEX.match(clean))


def normalize_matricula(matricula: str) -> str:
    """Normalize matricula to uppercase without spaces."""
    return matricula.strip().replace(" ", "").replace("-", "").upper()


def validate_dni_cif(dni_cif: str) -> bool:
    """Validate Spanish DNI/NIE/CIF format."""
    if not dni_cif:
        return False
    clean = dni_cif.strip().replace(" ", "").replace("-", "").upper()
    return bool(DNI_CIF_REGEX.match(clean))


def validate_cp(cp: str) -> bool:
    """Validate Spanish postal code format."""
    if not cp:
        return False
    clean = cp.strip().replace(" ", "")
    return bool(CP_REGEX.match(clean))


# =============================================================================
# Composite Validators
# =============================================================================


def validate_personal_data(data: dict[str, str | None]) -> tuple[bool, list[str], list[str]]:
    """
    Validate personal data completeness.

    Required fields:
        - nombre, apellidos
        - dni_cif
        - email
        - domicilio_calle, domicilio_localidad, domicilio_provincia, domicilio_cp
        - itv_nombre

    Args:
        data: Personal data dict

    Returns:
        Tuple of (is_valid, list_of_missing_labels, list_of_missing_field_keys)
    """
    missing: list[str] = []
    missing_keys: list[str] = []

    # Basic personal info
    if not data.get("nombre"):
        missing.append("nombre")
        missing_keys.append("nombre")

    if not data.get("apellidos"):
        missing.append("apellidos")
        missing_keys.append("apellidos")

    # DNI/CIF
    dni_cif = data.get("dni_cif")
    if not dni_cif:
        missing.append("DNI/CIF")
        missing_keys.append("dni_cif")
    elif not validate_dni_cif(dni_cif):
        missing.append("DNI/CIF (formato inválido)")
        missing_keys.append("dni_cif")

    # Email
    email = data.get("email")
    if not email:
        missing.append("email")
        missing_keys.append("email")
    elif not validate_email(email):
        missing.append("email (formato inválido)")
        missing_keys.append("email")

    # Domicilio
    if not data.get("domicilio_calle"):
        missing.append("calle")
        missing_keys.append("domicilio_calle")

    if not data.get("domicilio_localidad"):
        missing.append("localidad")
        missing_keys.append("domicilio_localidad")

    if not data.get("domicilio_provincia"):
        missing.append("provincia")
        missing_keys.append("domicilio_provincia")

    cp = data.get("domicilio_cp")
    if not cp:
        missing.append("codigo postal")
        missing_keys.append("domicilio_cp")
    elif not validate_cp(cp):
        missing.append("codigo postal (formato inválido)")
        missing_keys.append("domicilio_cp")

    # ITV
    if not data.get("itv_nombre"):
        missing.append("nombre de la ITV")
        missing_keys.append("itv_nombre")

    # telefono is optional (we have WhatsApp)

    return len(missing) == 0, missing, missing_keys


def validate_vehicle_data(data: dict[str, str | None]) -> tuple[bool, list[str], list[str]]:
    """
    Validate vehicle data completeness.

    Args:
        data: Vehicle data dict

    Returns:
        Tuple of (is_valid, list_of_missing_labels, list_of_missing_field_keys)
    """
    missing: list[str] = []
    missing_keys: list[str] = []

    if not data.get("marca"):
        missing.append("marca")
        missing_keys.append("marca")

    if not data.get("modelo"):
        missing.append("modelo")
        missing_keys.append("modelo")

    # anio is REQUIRED
    anio = data.get("anio")
    if not anio:
        missing.append("año")
        missing_keys.append("anio")
    else:
        try:
            year = int(anio)
            if year < 1900 or year > 2030:
                missing.append("año (debe ser entre 1900 y 2030)")
                missing_keys.append("anio")
        except (ValueError, TypeError):
            missing.append("año (formato inválido)")
            missing_keys.append("anio")

    matricula = data.get("matricula")
    if not matricula:
        missing.append("matrícula")
        missing_keys.append("matricula")
    elif not validate_matricula(matricula):
        missing.append("matrícula (formato inválido)")
        missing_keys.append("matricula")

    if not data.get("bastidor"):
        missing.append("número de bastidor (VIN)")
        missing_keys.append("bastidor")

    return len(missing) == 0, missing, missing_keys


def validate_workshop_data(
    data: dict[str, str | None] | None,
) -> tuple[bool, list[str], list[str]]:
    """
    Validate workshop data completeness (only required if taller_propio=True).

    Required fields when client uses own workshop:
        - nombre (workshop name)
        - responsable (responsible person)
        - domicilio (address)
        - provincia
        - ciudad
        - telefono
        - registro_industrial (industrial registry number)
        - actividad (activity description)

    Args:
        data: Workshop data dict or None

    Returns:
        Tuple of (is_valid, list_of_missing_labels, list_of_missing_field_keys)
    """
    if not data:
        return False, ["datos del taller"], []

    missing: list[str] = []
    missing_keys: list[str] = []

    if not data.get("nombre"):
        missing.append("nombre del taller")
        missing_keys.append("nombre")

    if not data.get("responsable"):
        missing.append("responsable del taller")
        missing_keys.append("responsable")

    if not data.get("domicilio"):
        missing.append("domicilio del taller")
        missing_keys.append("domicilio")

    if not data.get("provincia"):
        missing.append("provincia del taller")
        missing_keys.append("provincia")

    if not data.get("ciudad"):
        missing.append("ciudad del taller")
        missing_keys.append("ciudad")

    if not data.get("telefono"):
        missing.append("telefono del taller")
        missing_keys.append("telefono")

    if not data.get("registro_industrial"):
        missing.append("numero de registro industrial")
        missing_keys.append("registro_industrial")

    if not data.get("actividad"):
        missing.append("actividad del taller")
        missing_keys.append("actividad")

    return len(missing) == 0, missing, missing_keys
