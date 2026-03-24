"""
Expediente data validation functions for case collection.

Extracted from fsm_compat.py as part of the FSM compat layer removal.
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


def validate_personal_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
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
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing = []

    # Basic personal info
    if not data.get("nombre"):
        missing.append("nombre")

    if not data.get("apellidos"):
        missing.append("apellidos")

    # DNI/CIF
    dni_cif = data.get("dni_cif")
    if not dni_cif:
        missing.append("DNI/CIF")
    elif not validate_dni_cif(dni_cif):
        missing.append("DNI/CIF (formato inválido)")

    # Email
    email = data.get("email")
    if not email:
        missing.append("email")
    elif not validate_email(email):
        missing.append("email (formato inválido)")

    # Domicilio
    if not data.get("domicilio_calle"):
        missing.append("calle")

    if not data.get("domicilio_localidad"):
        missing.append("localidad")

    if not data.get("domicilio_provincia"):
        missing.append("provincia")

    cp = data.get("domicilio_cp")
    if not cp:
        missing.append("codigo postal")
    elif not validate_cp(cp):
        missing.append("codigo postal (formato inválido)")

    # ITV
    if not data.get("itv_nombre"):
        missing.append("nombre de la ITV")

    # telefono is optional (we have WhatsApp)

    return len(missing) == 0, missing


def validate_vehicle_data(data: dict[str, str | None]) -> tuple[bool, list[str]]:
    """
    Validate vehicle data completeness.

    Args:
        data: Vehicle data dict

    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing = []

    if not data.get("marca"):
        missing.append("marca")

    if not data.get("modelo"):
        missing.append("modelo")

    # anio is REQUIRED
    anio = data.get("anio")
    if not anio:
        missing.append("año")
    else:
        try:
            year = int(anio)
            if year < 1900 or year > 2030:
                missing.append("año (debe ser entre 1900 y 2030)")
        except (ValueError, TypeError):
            missing.append("año (formato inválido)")

    matricula = data.get("matricula")
    if not matricula:
        missing.append("matrícula")
    elif not validate_matricula(matricula):
        missing.append("matrícula (formato inválido)")

    if not data.get("bastidor"):
        missing.append("número de bastidor (VIN)")

    return len(missing) == 0, missing


def validate_workshop_data(
    data: dict[str, str | None] | None,
) -> tuple[bool, list[str]]:
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
        Tuple of (is_valid, list_of_missing_fields)
    """
    if not data:
        return False, ["datos del taller"]

    missing = []

    if not data.get("nombre"):
        missing.append("nombre del taller")

    if not data.get("responsable"):
        missing.append("responsable del taller")

    if not data.get("domicilio"):
        missing.append("domicilio del taller")

    if not data.get("provincia"):
        missing.append("provincia del taller")

    if not data.get("ciudad"):
        missing.append("ciudad del taller")

    if not data.get("telefono"):
        missing.append("telefono del taller")

    if not data.get("registro_industrial"):
        missing.append("numero de registro industrial")

    if not data.get("actividad"):
        missing.append("actividad del taller")

    return len(missing) == 0, missing
