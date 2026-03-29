"""Unit tests for the taller domain guard in expediente kickoff turns (Tasks G1+G2).

Tests cover:
- G1: _TALLER_DOMAIN_GUARD_SUBMODES constant — correct sub-modes included
- G1: _TALLER_DOMAIN_RE constant — compiles and matches expected phrases
- G2: Guard fires in collect_personal / collect_vehicle with taller content
- G2: Guard does NOT fire in collect_workshop (correct domain)
- G2: Guard does NOT fire for personal/vehicle content in personal/vehicle sub-modes
- Production bug: exact phrase from bug report is caught

All tests are pure unit tests — no database, no Redis, no async I/O.
The guard logic is tested by importing the constants directly from
expediente_mode.py and replicating the same strip logic.
"""

from __future__ import annotations

import re

import pytest

from agent.modes.expediente_mode import (
    _TALLER_DOMAIN_GUARD_SUBMODES,
    _TALLER_DOMAIN_RE,
)


# ---------------------------------------------------------------------------
# Helpers — replicate exact guard logic from expediente_mode.py kickoff branch
# ---------------------------------------------------------------------------


def _apply_domain_guard(sub_mode: str, response: str) -> tuple[str, bool]:
    """Apply the same domain guard logic as expediente_mode.py kickoff branch.

    Returns:
        (output_response, was_stripped)
    """
    if sub_mode and sub_mode.lower() in _TALLER_DOMAIN_GUARD_SUBMODES:
        if _TALLER_DOMAIN_RE.search(response):
            stripped = _TALLER_DOMAIN_RE.sub("", response).strip()
            return stripped, True
    return response, False


# ---------------------------------------------------------------------------
# G1 — Constant definitions
# ---------------------------------------------------------------------------


class TestTallerDomainGuardConstants:
    """Verify _TALLER_DOMAIN_GUARD_SUBMODES and _TALLER_DOMAIN_RE are correct."""

    def test_guard_submodes_contains_collect_personal(self) -> None:
        assert "collect_personal" in _TALLER_DOMAIN_GUARD_SUBMODES

    def test_guard_submodes_contains_collect_vehicle(self) -> None:
        assert "collect_vehicle" in _TALLER_DOMAIN_GUARD_SUBMODES

    def test_guard_submodes_does_not_contain_collect_workshop(self) -> None:
        assert "collect_workshop" not in _TALLER_DOMAIN_GUARD_SUBMODES

    def test_guard_submodes_does_not_contain_collect_base_docs(self) -> None:
        assert "collect_base_docs" not in _TALLER_DOMAIN_GUARD_SUBMODES

    def test_guard_submodes_does_not_contain_review_summary(self) -> None:
        assert "review_summary" not in _TALLER_DOMAIN_GUARD_SUBMODES

    def test_taller_domain_re_is_compiled_pattern(self) -> None:
        assert isinstance(_TALLER_DOMAIN_RE, re.Pattern)

    def test_taller_domain_re_has_ignorecase(self) -> None:
        assert _TALLER_DOMAIN_RE.flags & re.IGNORECASE

    @pytest.mark.parametrize(
        "phrase",
        [
            "taller",
            "Taller",
            "TALLER",
            "taller propio",
            "taller registrado",
            "certificado de montaje",
            "85€",
            "85 €",
            "85 EUR",
            "85EUR",
            "MSI gestione",
            "MSI gestiona",
            "instalación",
            "instalacion",
        ],
    )
    def test_taller_domain_re_matches_expected_phrases(self, phrase: str) -> None:
        assert _TALLER_DOMAIN_RE.search(phrase) is not None, (
            f"Expected _TALLER_DOMAIN_RE to match '{phrase}'"
        )


# ---------------------------------------------------------------------------
# G2 — Guard parametrized cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sub_mode,response_text,should_strip",
    [
        # ── Taller content in collect_personal → strip ──────────────────────────
        ("collect_personal", "¿Tienes taller propio o externo?", True),
        (
            "collect_personal",
            "¿Quieres que MSI gestione el certificado por 85 EUR?",
            True,
        ),
        ("collect_personal", "¿Tienes un taller registrado?", True),
        ("collect_personal", "Necesito el certificado de montaje del taller.", True),
        ("collect_personal", "La instalación se realiza en el taller.", True),
        # ── Personal content in collect_personal → pass ──────────────────────────
        ("collect_personal", "¿Cuál es tu nombre completo y DNI?", False),
        ("collect_personal", "Necesito tu email y dirección postal.", False),
        ("collect_personal", "¿Cuál es tu número de teléfono de contacto?", False),
        # ── Taller content in collect_vehicle → strip ────────────────────────────
        ("collect_vehicle", "¿Tienes taller propio?", True),
        (
            "collect_vehicle",
            "¿Quieres que MSI gestione el certificado de montaje?",
            True,
        ),
        ("collect_vehicle", "El coste del certificado es de 85 EUR.", True),
        # ── Vehicle content in collect_vehicle → pass ────────────────────────────
        ("collect_vehicle", "¿Cuál es la matrícula del vehículo?", False),
        ("collect_vehicle", "Necesito el número de bastidor.", False),
        ("collect_vehicle", "¿Cuál es la marca y modelo de tu moto?", False),
        # ── Taller content in collect_workshop → PASS (correct domain) ──────────
        (
            "collect_workshop",
            "¿Quieres que MSI gestione el certificado por 85 EUR +IVA?",
            False,
        ),
        ("collect_workshop", "¿Tienes tu propio taller registrado?", False),
        ("collect_workshop", "La instalación será realizada por tu taller.", False),
        # ── Taller content in collect_base_docs → PASS (not in guard list) ───────
        (
            "collect_base_docs",
            "El taller debe emitir el certificado de montaje.",
            False,
        ),
        # ── Taller content in review_summary → PASS (not in guard list) ──────────
        ("review_summary", "El taller propio gestiona la instalación.", False),
    ],
)
def test_taller_domain_guard(
    sub_mode: str, response_text: str, should_strip: bool
) -> None:
    """Guard strips taller content in collect_personal/collect_vehicle only."""
    _result, was_stripped = _apply_domain_guard(sub_mode, response_text)

    if should_strip:
        assert was_stripped, (
            f"Expected guard to STRIP taller content in sub_mode='{sub_mode}'\n"
            f"Response: '{response_text}'"
        )
    else:
        assert not was_stripped, (
            f"Expected guard to PASS (no stripping) for sub_mode='{sub_mode}'\n"
            f"Response: '{response_text}'"
        )


def test_strip_preserves_non_taller_content() -> None:
    """After stripping, non-taller content in the same response is preserved."""
    response = "Necesito tu nombre completo. ¿Tienes taller propio? También el DNI."
    stripped, was_stripped = _apply_domain_guard("collect_personal", response)

    assert was_stripped
    assert "taller propio" not in stripped.lower()
    # Non-taller content should survive
    assert "nombre completo" in stripped.lower()
    assert "DNI" in stripped


def test_strip_result_is_non_empty_when_content_remains() -> None:
    """Stripping taller phrase from mixed response leaves non-empty string."""
    response = "Hola, ¿cuál es tu nombre? ¿Tienes taller propio?"
    stripped, was_stripped = _apply_domain_guard("collect_personal", response)

    assert was_stripped
    assert stripped  # Not empty


def test_case_insensitive_match_in_guard() -> None:
    """Guard fires regardless of case."""
    for variant in ("TALLER", "Taller", "tAlLeR"):
        _, was_stripped = _apply_domain_guard(
            "collect_personal", f"¿Tienes {variant} propio?"
        )
        assert was_stripped, f"Case variant '{variant}' was not caught"


# ---------------------------------------------------------------------------
# Production bug regression
# ---------------------------------------------------------------------------


def test_production_bug_phrase_is_caught() -> None:
    """The exact phrase from the production bug should be stripped in collect_personal."""
    response = "¿Es tuyo propio o externo el taller?"
    assert "collect_personal" in _TALLER_DOMAIN_GUARD_SUBMODES
    assert _TALLER_DOMAIN_RE.search(response) is not None

    stripped, was_stripped = _apply_domain_guard("collect_personal", response)
    assert was_stripped
    assert "taller" not in stripped.lower()


def test_production_bug_full_sentence_variation() -> None:
    """Variation of the production bug phrase."""
    response = "¿Tienes taller propio o externo?"
    assert _TALLER_DOMAIN_RE.search(response) is not None

    stripped, was_stripped = _apply_domain_guard("collect_personal", response)
    assert was_stripped


def test_85_eur_phrase_is_caught_in_collect_personal() -> None:
    """The 85 EUR certification cost phrase should be stripped in collect_personal."""
    response = "¿Quieres que MSI gestione el certificado por 85 EUR?"
    assert "collect_personal" in _TALLER_DOMAIN_GUARD_SUBMODES

    stripped, was_stripped = _apply_domain_guard("collect_personal", response)
    assert was_stripped
    # The price should not remain as a domain signal
    assert "85 EUR" not in stripped


def test_85_eur_phrase_passes_in_collect_workshop() -> None:
    """The 85 EUR certification cost phrase is VALID in collect_workshop."""
    response = "¿Quieres que MSI gestione el certificado por 85 EUR + IVA?"
    assert "collect_workshop" not in _TALLER_DOMAIN_GUARD_SUBMODES

    _result, was_stripped = _apply_domain_guard("collect_workshop", response)
    assert not was_stripped
