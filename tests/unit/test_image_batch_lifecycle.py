"""
Regression tests for get_current_element_code() — image batch lifecycle fix.

Production bug (Scenario B): At 17:04 UTC, TOLDO photos arrived while FSM had:
  - element_phase = "data"  (set by confirmar_fotos_elemento for PLACA)
  - current_element_index = 0  (still pointing to PLACA)
  - element_data_status = {"PLACA_SOLAR_REGULADOR_INTERIOR": "photos_done", ...}

The agent had already asked for TOLDO photos without calling completar_elemento_actual.
Old code returned None in this case → images wrongly treated as base docs.
Fixed code detects the "narrated ahead of state" condition and returns TOLDO.
"""

import pytest

from agent.services.image_handling import get_current_element_code


# ──────────────────────────────────────────────────────────────────
# Happy path: phase = "photos"
# ──────────────────────────────────────────────────────────────────


def test_get_current_element_code_photos_phase():
    """Normal case: phase=photos → returns current element."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "photos",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
        "element_data_status": {
            "PLACA_SOLAR_REGULADOR_INTERIOR": "pending",
            "TOLDO_GALIBO": "pending",
        },
    }
    result = get_current_element_code(mode_context)
    assert result == "PLACA_SOLAR_REGULADOR_INTERIOR"


def test_get_current_element_code_photos_phase_second_element():
    """phase=photos at index 1 → returns second element."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "photos",
        "current_element_index": 1,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
        "element_data_status": {
            "PLACA_SOLAR_REGULADOR_INTERIOR": "photos_done",
            "TOLDO_GALIBO": "pending",
        },
    }
    result = get_current_element_code(mode_context)
    assert result == "TOLDO_GALIBO"


# ──────────────────────────────────────────────────────────────────
# Scenario B: the production bug
# ──────────────────────────────────────────────────────────────────


def test_get_current_element_code_data_phase_photos_done_has_next():
    """
    THE PRODUCTION BUG SCENARIO (Scenario B):

    element_phase=data, current status=photos_done, next element exists
    → must return the NEXT element (TOLDO_GALIBO), not None.

    At 17:04 UTC the agent had already asked for TOLDO photos while
    completar_elemento_actual() had not been called yet for PLACA.
    Old code returned None, losing the photos.  Fixed code returns TOLDO.
    """
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "data",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
        "element_data_status": {
            "PLACA_SOLAR_REGULADOR_INTERIOR": "photos_done",
            "TOLDO_GALIBO": "pending",
        },
    }
    result = get_current_element_code(mode_context)
    assert result == "TOLDO_GALIBO"


def test_get_current_element_code_data_phase_photos_done_last_element():
    """
    element_phase=data, current status=photos_done, but NO next element
    → returns None (last element, no N+1 to attribute photos to).
    """
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "data",
        "current_element_index": 1,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
        "element_data_status": {
            "PLACA_SOLAR_REGULADOR_INTERIOR": "photos_done",
            "TOLDO_GALIBO": "photos_done",
        },
    }
    result = get_current_element_code(mode_context)
    assert result is None


def test_get_current_element_code_data_phase_not_photos_done():
    """
    element_phase=data, current status NOT photos_done
    → returns None (base docs or unrelated images).

    This ensures the original base-doc case is preserved:
    images during the data phase of element N (before confirmation)
    are NOT element photos.
    """
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "data",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"],
        "element_data_status": {
            "PLACA_SOLAR_REGULADOR_INTERIOR": "pending",  # Not photos_done
            "TOLDO_GALIBO": "pending",
        },
    }
    result = get_current_element_code(mode_context)
    assert result is None


# ──────────────────────────────────────────────────────────────────
# Guard: wrong sub-mode
# ──────────────────────────────────────────────────────────────────


def test_get_current_element_code_wrong_sub_mode():
    """
    expediente_sub_mode != collect_element_data → returns None.
    Existing guard must be preserved (e.g. collect_base_docs sub-mode).
    """
    mode_context = {
        "expediente_sub_mode": "collect_base_docs",
        "element_phase": "photos",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
        "element_data_status": {},
    }
    result = get_current_element_code(mode_context)
    assert result is None


def test_get_current_element_code_no_sub_mode():
    """Missing expediente_sub_mode key → returns None (defaults to empty string)."""
    mode_context = {
        "element_phase": "photos",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
    }
    result = get_current_element_code(mode_context)
    assert result is None


# ──────────────────────────────────────────────────────────────────
# Guard: None / empty context
# ──────────────────────────────────────────────────────────────────


def test_get_current_element_code_none_context():
    """mode_context=None → returns None."""
    result = get_current_element_code(None)
    assert result is None


def test_get_current_element_code_empty_context():
    """mode_context={} → returns None (no sub-mode set)."""
    result = get_current_element_code({})
    assert result is None


# ──────────────────────────────────────────────────────────────────
# Edge cases: empty element_codes / out-of-bounds index
# ──────────────────────────────────────────────────────────────────


def test_get_current_element_code_photos_phase_empty_codes():
    """phase=photos but element_codes is empty → returns None."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "photos",
        "current_element_index": 0,
        "element_codes": [],
        "element_data_status": {},
    }
    result = get_current_element_code(mode_context)
    assert result is None


def test_get_current_element_code_photos_phase_index_out_of_bounds():
    """phase=photos but current_element_index >= len(element_codes) → returns None."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "photos",
        "current_element_index": 5,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
        "element_data_status": {},
    }
    result = get_current_element_code(mode_context)
    assert result is None


def test_get_current_element_code_data_phase_empty_codes():
    """phase=data but element_codes is empty → returns None (no current_code)."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "data",
        "current_element_index": 0,
        "element_codes": [],
        "element_data_status": {},
    }
    result = get_current_element_code(mode_context)
    assert result is None


def test_get_current_element_code_unknown_phase():
    """Unknown element_phase value → returns None (catch-all else branch)."""
    mode_context = {
        "expediente_sub_mode": "collect_element_data",
        "element_phase": "unknown_phase",
        "current_element_index": 0,
        "element_codes": ["PLACA_SOLAR_REGULADOR_INTERIOR"],
        "element_data_status": {},
    }
    result = get_current_element_code(mode_context)
    assert result is None
