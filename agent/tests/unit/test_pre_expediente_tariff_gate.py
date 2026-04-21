"""
L3 tariff-gate tests — premature-CTA/footer red-net.

Covers the <tariff_gate> rule in pre_expediente_pricing.md (L2/L3):
when no price was communicated AND no tarifa is stored AND the response
has no numeric price literal, premature CTAs (3/4/5) and the
"_Precios válidos por 30 días._" footer must be stripped.

Defense-in-depth for the prompt-level rule. If the LLM emits them anyway,
_strip_premature_price_artifacts removes them before render.
"""
from __future__ import annotations

from pathlib import Path

from agent.modes.pre_expediente_mode import _strip_premature_price_artifacts
from agent.prompts.ctas_catalog import CTAS


_PRICING_MD = (
    Path(__file__).parents[3]
    / "agent"
    / "prompts"
    / "modes"
    / "pre_expediente_pricing.md"
)


# ---------------------------------------------------------------------------
# Prompt-level drift guards
# ---------------------------------------------------------------------------

def test_pricing_prompt_has_tariff_gate_block() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    assert "<tariff_gate>" in text
    assert "</tariff_gate>" in text
    assert "calcular_tarifa_con_elementos" in text


def test_pricing_prompt_has_priority_hierarchy() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    assert "<priority_hierarchy>" in text
    assert "L1" in text and "L2" in text and "L3" in text


def test_pricing_prompt_footer_is_conditional() -> None:
    text = _PRICING_MD.read_text(encoding="utf-8")
    # Old unconditional wording must be gone
    assert "SIEMPRE incluye al final de toda comunicación de precio" not in text
    # New conditional wording present
    assert 'SOLO si el mensaje contiene el precio numérico' in text


# ---------------------------------------------------------------------------
# _strip_premature_price_artifacts behaviour
# ---------------------------------------------------------------------------

def test_strip_removes_cta3_when_no_price() -> None:
    raw = f"Documentación general:\n- Foto\n\n{CTAS[3]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[3] not in out
    assert "Documentación general" in out


def test_strip_removes_cta4_when_no_price() -> None:
    raw = f"Info útil.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[4] not in out


def test_strip_removes_cta5_when_no_price() -> None:
    raw = f"Texto.\n\n{CTAS[5]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[5] not in out


def test_strip_removes_footer_when_no_price() -> None:
    raw = "Documentación...\n\n_Precios válidos por 30 días._"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "Precios válidos por 30 días" not in out


def test_strip_noop_when_precio_comunicado() -> None:
    raw = f"El presupuesto es *410€ +IVA*.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=True, tarifa_calculada={"total": 410}
    )
    assert out == raw


def test_strip_noop_when_tarifa_present() -> None:
    raw = f"Texto.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada={"total": 410}
    )
    assert out == raw


def test_strip_noop_when_price_literal_in_response() -> None:
    # Self-healing: if the response somehow contains a price, assume valid
    raw = f"El presupuesto es *410€ +IVA*.\n\n{CTAS[4]}"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert out == raw


def test_strip_removes_tuteo_cta5_variant() -> None:
    raw = "Texto.\n\n¿Abrimos expediente o tienes alguna duda?"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "Abrimos expediente" not in out


def test_strip_regression_subchasis_agarraderas_case() -> None:
    """Exact repro of the reported bug: subchasis + agarraderas without price."""
    raw = (
        "Documentación general:\n"
        "- Foto de la ficha técnica\n"
        "- Foto del DNI\n\n"
        "Documentación del subchasis:\n"
        "- subchasis-tanque-moto\n\n"
        "⚠️ Esta modificación es compleja.\n\n"
        "_Precios válidos por 30 días._\n\n"
        f"{CTAS[4]}"
    )
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert CTAS[4] not in out
    assert "Precios válidos por 30 días" not in out
    # Documentation survives
    assert "Documentación general" in out
    assert "subchasis-tanque-moto" in out
    assert "⚠️" in out


def test_strip_collapses_triple_newlines() -> None:
    raw = f"Texto.\n\n\n\n{CTAS[4]}\n\n_Precios válidos por 30 días._"
    out = _strip_premature_price_artifacts(
        ai_response=raw, precio_comunicado=False, tarifa_calculada=None
    )
    assert "\n\n\n" not in out
