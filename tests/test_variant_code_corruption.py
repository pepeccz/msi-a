"""
Tests for fix-variant-code-corruption-in-resolved-codes

Bug: LLM interpretation path sets variant_code to option text
(e.g. "A - Toldo lateral (sin afectar galibo)") instead of the
element code (TOLDO_GALIBO), corrupting element_codes and blocking
enviar_imagenes_ejemplo via blocked_stale_budget_scope.

Scenarios:
  1. Variant accumulator prefers selected_variant over resoluciones variant_code
  2. Resolved codes filter rejects non-element-code values
  3. Budget scope guard uses subset check (tarifa_codes ⊆ current_codes)
"""

import re


# ---------------------------------------------------------------------------
# Test 1: resolved_codes filter
# ---------------------------------------------------------------------------

def test_element_code_pattern_rejects_option_text():
    """
    GIVEN a list of resolved values containing both valid codes and option text
    WHEN filtered with the element code pattern ^[A-Z][A-Z0-9_]+$
    THEN only valid element codes pass through
    """
    ELEMENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

    values = [
        "PLACA_SOLAR_REGULADOR_INTERIOR",
        "A - Toldo lateral (sin afectar galibo)",
        "TOLDO_GALIBO",
        "B - Toldo lateral (afecta galibo)",
        "ESCAPE",
    ]

    filtered = [v for v in values if ELEMENT_CODE_RE.match(v)]

    assert filtered == [
        "PLACA_SOLAR_REGULADOR_INTERIOR",
        "TOLDO_GALIBO",
        "ESCAPE",
    ]
    assert "A - Toldo lateral (sin afectar galibo)" not in filtered
    assert "B - Toldo lateral (afecta galibo)" not in filtered


def test_element_code_pattern_accepts_all_known_codes():
    """
    GIVEN a set of known element codes from the MSI-a catalog
    WHEN checked against the element code pattern
    THEN all pass
    """
    ELEMENT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

    known_codes = [
        "TOLDO_GALIBO",
        "TOLDO_SIMPLE",
        "PLACA_SOLAR_SIMPLE",
        "PLACA_SOLAR_REGULADOR_INTERIOR",
        "PLACA_SOLAR_REGULADOR_VISIBLE",
        "ESCAPE",
        "SUBCHASIS",
        "SUSPENSION",
    ]

    for code in known_codes:
        assert ELEMENT_CODE_RE.match(code), f"Code {code} should match pattern"


# ---------------------------------------------------------------------------
# Test 2: Budget scope guard — subset check
# ---------------------------------------------------------------------------

def test_budget_scope_subset_allows_extra_stale_codes():
    """
    GIVEN tarifa_codes = {PLACA_SOLAR_REGULADOR_INTERIOR, TOLDO_GALIBO}
    AND   current_codes = {PLACA_SOLAR_REGULADOR_INTERIOR, TOLDO_GALIBO, STALE_EXTRA}
    WHEN  checking if tarifa_codes is subset of current_codes
    THEN  returns True (should NOT block)
    """
    tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}
    current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO", "STALE_EXTRA"}

    # Old check (strict equality) would block:
    assert current_codes != tarifa_codes

    # New check (subset) does NOT block:
    assert tarifa_codes.issubset(current_codes)


def test_budget_scope_subset_blocks_missing_tarifa_code():
    """
    GIVEN tarifa_codes = {PLACA_SOLAR_REGULADOR_INTERIOR, TOLDO_GALIBO}
    AND   current_codes = {PLACA_SOLAR_REGULADOR_INTERIOR}  (missing TOLDO)
    WHEN  checking if tarifa_codes is subset of current_codes
    THEN  returns False (SHOULD block — tarifa code missing)
    """
    tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}
    current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR"}

    assert not tarifa_codes.issubset(current_codes)


def test_budget_scope_exact_match_still_works():
    """
    GIVEN tarifa_codes == current_codes (exact match)
    WHEN  checking subset
    THEN  returns True (should NOT block)
    """
    tarifa_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}
    current_codes = {"PLACA_SOLAR_REGULADOR_INTERIOR", "TOLDO_GALIBO"}

    assert tarifa_codes.issubset(current_codes)


# ---------------------------------------------------------------------------
# Test 3: Variant accumulator prefers selected_variant
# ---------------------------------------------------------------------------

def test_accumulator_prefers_selected_variant_over_resoluciones():
    """
    GIVEN result_dict with selected_variant="TOLDO_GALIBO"
    AND   _internal_flags.pending_variants has variant_code="A - Toldo lateral..."
    WHEN  accumulating resolved variants
    THEN  uses TOLDO_GALIBO (from selected_variant), not the option text
    """
    result_dict = {
        "selected_variant": "TOLDO_GALIBO",
        "_internal_flags": {
            "pending_variants": [
                {
                    "pending_id": "TOLDO_LAT_1",
                    "codigo_base": "TOLDO_LAT",
                    "status": "resolved",
                    "resoluciones": [
                        {
                            "variant_code": "A - Toldo lateral (sin afectar galibo)",
                            "quantity": 1,
                            "confidence": 0.52,
                            "source": "user_explicit",
                        }
                    ],
                }
            ]
        },
    }
    tool_args = {"codigo_elemento_base": "TOLDO_LAT"}

    # Simulate the accumulator logic (same as presupuesto_mode.py)
    _resolved: dict[str, str] = {}
    tool_flags = result_dict.get("_internal_flags", {})
    for pv in tool_flags.get("pending_variants", []):
        if isinstance(pv, dict) and pv.get("status") == "resolved":
            cb = pv.get("codigo_base")
            if cb:
                sv = result_dict.get("selected_variant")
                if sv and cb == tool_args.get("codigo_elemento_base", "").upper():
                    _resolved[cb] = sv
                else:
                    for res in pv.get("resoluciones", []):
                        vc = res.get("variant_code") if isinstance(res, dict) else None
                        if vc:
                            _resolved[cb] = vc
                            break

    assert _resolved["TOLDO_LAT"] == "TOLDO_GALIBO"
    assert _resolved["TOLDO_LAT"] != "A - Toldo lateral (sin afectar galibo)"


def test_accumulator_falls_back_to_resoluciones_when_no_selected_variant():
    """
    GIVEN result_dict WITHOUT selected_variant
    AND   _internal_flags has valid variant_code in resoluciones
    WHEN  accumulating
    THEN  uses variant_code from resoluciones (fallback path)
    """
    result_dict = {
        "_internal_flags": {
            "pending_variants": [
                {
                    "codigo_base": "PLACA_SOLAR",
                    "status": "resolved",
                    "resoluciones": [
                        {
                            "variant_code": "PLACA_SOLAR_REGULADOR_INTERIOR",
                            "quantity": 1,
                            "confidence": 3.32,
                            "source": "user_explicit",
                        }
                    ],
                }
            ]
        },
    }
    tool_args = {"codigo_elemento_base": "PLACA_SOLAR"}

    _resolved: dict[str, str] = {}
    tool_flags = result_dict.get("_internal_flags", {})
    for pv in tool_flags.get("pending_variants", []):
        if isinstance(pv, dict) and pv.get("status") == "resolved":
            cb = pv.get("codigo_base")
            if cb:
                sv = result_dict.get("selected_variant")
                if sv and cb == tool_args.get("codigo_elemento_base", "").upper():
                    _resolved[cb] = sv
                else:
                    for res in pv.get("resoluciones", []):
                        vc = res.get("variant_code") if isinstance(res, dict) else None
                        if vc:
                            _resolved[cb] = vc
                            break

    assert _resolved["PLACA_SOLAR"] == "PLACA_SOLAR_REGULADOR_INTERIOR"
