"""Unit tests for `agent.utils.tariff_render.render_tariff_summary_from_state`.

Spec: sdd/fix-pricing-gate-self-heal-loop/spec — Requirement "Deterministic
Safety-Net Render" scenarios.

The helper produces a deterministic Castilian-tuteo price summary from the
`tarifa_calculada` payload stored in `mode_context`. It is invoked by
`base_mode.empty_ai_response_safety_net` when the LLM-generated text is empty
but the tariff is already available in state.
"""
from __future__ import annotations

import pytest

from agent.prompts.ctas_catalog import CTAS
from agent.utils.tariff_render import render_tariff_summary_from_state


# ---------------------------------------------------------------------------
# Canonical fixture (shape mirrors agent/tools/element_tools.py result_dict)
# ---------------------------------------------------------------------------

_CANONICAL_TARIFA: dict = {
    "datos": {
        "tier_id": "tier-moto-2",
        "tier_name": "Moto - 2 elementos",
        "price": 410.0,
        "elements": ["Subchasis", "Asideros / Agarraderas"],
        "element_codes": ["SUBCHASIS", "ASIDEROS"],
        "warnings": [
            {
                "message": "Debes aportar factura del taller homologador.",
                "severity": "warning",
                "element_code": "SUBCHASIS",
                "element_name": "Subchasis",
            },
        ],
    },
}


def _mc_with_tarifa(tarifa: dict | None) -> dict:
    return {"tarifa_calculada": tarifa} if tarifa is not None else {}


# ---------------------------------------------------------------------------
# Happy path — full payload
# ---------------------------------------------------------------------------

def test_renders_price_literal_with_iva_suffix() -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert "410" in out
    assert "€" in out
    assert "IVA" in out


def test_renders_all_element_names() -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert "Subchasis" in out
    assert "Asideros" in out


def test_renders_warning_with_icon() -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert "⚠️" in out
    assert "factura del taller homologador" in out


def test_renders_validity_footer() -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert "Precios válidos por 30 días" in out


def test_ends_with_cta_estado_4() -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert out.rstrip().endswith(CTAS[4])


# ---------------------------------------------------------------------------
# Tuteo enforcement — no voseo forms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "voseo_form",
    [
        "tenés",
        "podés",
        "querés",
        "necesitás",
        "vos ",
        "ponete",
        "fijate",
        "dale,",
    ],
)
def test_render_contains_no_voseo_forms(voseo_form: str) -> None:
    out = render_tariff_summary_from_state(_mc_with_tarifa(_CANONICAL_TARIFA))
    assert voseo_form not in out.lower(), (
        f"Voseo form '{voseo_form}' leaked into safety-net render"
    )


# ---------------------------------------------------------------------------
# Edge cases — missing/malformed payload returns empty (caller handles fallback)
# ---------------------------------------------------------------------------

def test_returns_empty_when_no_tarifa_in_mc() -> None:
    assert render_tariff_summary_from_state({}) == ""


def test_returns_empty_when_tarifa_is_none() -> None:
    assert render_tariff_summary_from_state({"tarifa_calculada": None}) == ""


def test_returns_empty_when_datos_missing() -> None:
    assert render_tariff_summary_from_state({"tarifa_calculada": {}}) == ""


def test_returns_empty_when_price_missing() -> None:
    payload = {"datos": {"tier_name": "X", "elements": ["A"]}}
    assert render_tariff_summary_from_state({"tarifa_calculada": payload}) == ""


# ---------------------------------------------------------------------------
# Triangulation — different price/tier renders different output
# ---------------------------------------------------------------------------

def test_different_price_renders_different_output() -> None:
    cheap = {
        "datos": {
            "tier_name": "Moto - 1 elemento",
            "price": 250.0,
            "elements": ["Escape"],
            "warnings": [],
        }
    }
    expensive = {
        "datos": {
            "tier_name": "Moto - 5 elementos",
            "price": 980.0,
            "elements": ["A", "B", "C", "D", "E"],
            "warnings": [],
        }
    }
    out_cheap = render_tariff_summary_from_state(_mc_with_tarifa(cheap))
    out_expensive = render_tariff_summary_from_state(_mc_with_tarifa(expensive))
    assert "250" in out_cheap and "250" not in out_expensive
    assert "980" in out_expensive and "980" not in out_cheap
    assert out_cheap != out_expensive


def test_no_warnings_omits_warnings_block() -> None:
    payload = {
        "datos": {
            "tier_name": "Moto - 1 elemento",
            "price": 250.0,
            "elements": ["Escape"],
            "warnings": [],
        }
    }
    out = render_tariff_summary_from_state(_mc_with_tarifa(payload))
    assert "⚠️" not in out
    assert "250" in out
